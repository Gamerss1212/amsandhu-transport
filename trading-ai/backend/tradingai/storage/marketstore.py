"""Historical bars in partitioned Parquet files, queried with DuckDB (section 124).

Layout: market/provider=<p>/symbol=<s>/tf=<tf>/year=<YYYY>/month=<MM>/bars.parquet. A read names one symbol and
timeframe and a time range, so DuckDB only opens the matching files (partition pruning) and only the matching row
groups (predicate pushdown): years of minute bars are never loaded whole into memory.

Writes are merges: new bars replace stored bars with the same open time; a month file is rewritten atomically.
Every dataset's provenance (provider, rows, range, download time, SHA-256, transforms, simulated) is recorded.
"""

from __future__ import annotations

import os
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import duckdb
import numpy as np

from tradingai.data.bars import Bars

COLS = ("ts", "o", "h", "l", "c", "v", "avail")


def _safe(s: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in s)


class MarketStore:
    def __init__(self, root: Path, db=None):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.db = db                                     # storage.db.Database, for provenance
        self._lock = threading.Lock()

    def _dir(self, provider: str, symbol: str, tf: str) -> Path:
        return self.root / f"provider={_safe(provider)}" / f"symbol={_safe(symbol)}" / f"tf={tf}"

    def _con(self) -> duckdb.DuckDBPyConnection:
        return duckdb.connect(":memory:")

    # ------------------------------------------------------------------ write
    def write(self, provider: str, symbol: str, b: Bars, transforms: str = "") -> int:
        if not len(b):
            return 0
        avail = b.available_at
        months: dict[tuple[int, int], np.ndarray] = {}
        dts = [datetime.fromtimestamp(int(t) / 1000, tz=timezone.utc) for t in b.ts]
        keys = np.array([d.year * 100 + d.month for d in dts])
        for k in np.unique(keys):
            months[(int(k) // 100, int(k) % 100)] = np.flatnonzero(keys == k)
        written = 0
        with self._lock:
            con = self._con()
            try:
                for (y, m), idx in months.items():
                    folder = self._dir(provider, symbol, b.tf) / f"year={y}" / f"month={m:02d}"
                    folder.mkdir(parents=True, exist_ok=True)
                    target = folder / "bars.parquet"
                    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, dir=folder) as fh:
                        csv_path = fh.name
                        data = np.column_stack([b.ts[idx].astype(np.float64), b.open[idx], b.high[idx], b.low[idx],
                                                b.close[idx], b.volume[idx], avail[idx].astype(np.float64)])
                        np.savetxt(fh, data, delimiter=",", fmt=["%d", "%.10g", "%.10g", "%.10g", "%.10g", "%.10g",
                                                                 "%d"])
                    tmp_parquet = folder / "bars.parquet.tmp"
                    cols = "{'ts':'BIGINT','o':'DOUBLE','h':'DOUBLE','l':'DOUBLE','c':'DOUBLE','v':'DOUBLE','avail':'BIGINT'}"
                    new_rel = f"read_csv('{_q(csv_path)}', header=false, columns={cols})"
                    if target.exists():
                        sql = (f"SELECT * FROM (SELECT *, row_number() OVER (PARTITION BY ts ORDER BY src DESC) AS rn "
                               f"FROM (SELECT *, 1 AS src FROM {new_rel} UNION ALL SELECT *, 0 AS src FROM "
                               f"read_parquet('{_q(target)}'))) WHERE rn = 1")
                        sql = f"SELECT ts, o, h, l, c, v, avail FROM ({sql}) ORDER BY ts"
                    else:
                        sql = f"SELECT * FROM {new_rel} ORDER BY ts"
                    con.execute(f"COPY ({sql}) TO '{_q(tmp_parquet)}' (FORMAT PARQUET, COMPRESSION ZSTD)")
                    os.replace(tmp_parquet, target)
                    os.remove(csv_path)
                    written += len(idx)
            finally:
                con.close()
        if self.db is not None:
            self._provenance(provider, symbol, b, transforms)
        return written

    # ------------------------------------------------------------------ read
    def read(self, instrument_id: str, provider: str, symbol: str, tf: str, start_ms: Optional[int] = None,
             end_ms: Optional[int] = None, simulated: bool = False) -> Bars:
        folder = self._dir(provider, symbol, tf)
        if not folder.exists():
            return Bars.empty(instrument_id, tf)
        where, args = [], []
        if start_ms is not None:
            where.append("ts >= ?")
            args.append(int(start_ms))
        if end_ms is not None:
            where.append("ts < ?")
            args.append(int(end_ms))
        if start_ms is not None:                         # prune whole year partitions before reading
            where.append("year >= ?")
            args.append(datetime.fromtimestamp(start_ms / 1000, tz=timezone.utc).year)
        sql = (f"SELECT ts, o, h, l, c, v, avail FROM read_parquet('{_q(folder)}/*/*/bars.parquet', "
               f"hive_partitioning=true)" + (" WHERE " + " AND ".join(where) if where else "") + " ORDER BY ts")
        with self._lock:
            con = self._con()
            try:
                r = con.execute(sql, args).fetchnumpy()
            finally:
                con.close()
        if not len(r["ts"]):
            return Bars.empty(instrument_id, tf)
        b = Bars(instrument_id, tf, np.asarray(r["ts"], dtype=np.int64), np.asarray(r["o"]), np.asarray(r["h"]),
                 np.asarray(r["l"]), np.asarray(r["c"]), np.asarray(r["v"]), simulated=simulated,
                 source=f"{provider}:{symbol}")
        b.meta["avail"] = np.asarray(r["avail"], dtype=np.int64)
        return b

    def last_ts(self, provider: str, symbol: str, tf: str) -> Optional[int]:
        folder = self._dir(provider, symbol, tf)
        if not folder.exists():
            return None
        with self._lock:
            con = self._con()
            try:
                r = con.execute(f"SELECT max(ts) FROM read_parquet('{_q(folder)}/*/*/bars.parquet')").fetchone()
            finally:
                con.close()
        return int(r[0]) if r and r[0] is not None else None

    def datasets(self) -> list[dict]:
        out = []
        for p in sorted(self.root.glob("provider=*/symbol=*/tf=*")):
            files = list(p.glob("*/*/bars.parquet"))
            out.append({"provider": p.parts[-3].split("=", 1)[1], "symbol": p.parts[-2].split("=", 1)[1],
                        "tf": p.parts[-1].split("=", 1)[1], "files": len(files),
                        "bytes": sum(f.stat().st_size for f in files)})
        return out

    def _provenance(self, provider: str, symbol: str, b: Bars, transforms: str) -> None:
        full = self.read(b.instrument_id, provider, symbol, b.tf, simulated=b.simulated)
        self.db.execute(
            "INSERT INTO provenance (dataset_id, provider, market, symbol, tf, start_ms, end_ms, rows, downloaded, "
            "sha256, transforms, simulated) VALUES (?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(dataset_id) DO UPDATE SET "
            "start_ms=excluded.start_ms, end_ms=excluded.end_ms, rows=excluded.rows, downloaded=excluded.downloaded, "
            "sha256=excluded.sha256, transforms=excluded.transforms",
            (f"{provider}:{symbol}:{b.tf}", provider, b.instrument_id.split(":")[0], symbol, b.tf,
             int(full.ts[0]) if len(full) else None, int(full.ts[-1]) if len(full) else None, len(full),
             int(time.time() * 1000), full.sha256(), transforms or b.source, int(b.simulated)))


def _q(p) -> str:
    return str(p).replace("\\", "/").replace("'", "''")
