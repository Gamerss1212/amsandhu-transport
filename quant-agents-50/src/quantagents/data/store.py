"""A01 data store: append-only daily bars in Parquet, read with DuckDB (spec sections 57, 73).

- Append-only: every download becomes a new Parquet file named by symbol and ingest time. Files
  are written once (to a temporary name, then renamed) and never modified or deleted.
- Vintages: each file is one complete snapshot of a symbol's history as known at ``ingested_at``.
  ``load(as_of_ingest=T)`` uses, per symbol, the newest snapshot ingested at or before T: what was
  known then. Snapshots are never mixed, because each source re-adjusts its whole history when a
  dividend or split happens (mixing vintages would create fake price jumps).
- Provenance: every file keeps its ``SourceInfo`` (spec section 74), so every result can carry the
  right caveat ("survivorship-biased: upper bound only").
- File names are safe on every operating system (anything but letters, digits, ``.``, ``_`` and
  ``-`` becomes ``_``), and reading one symbol opens only the one file it needs: the store stays
  fast after years of daily snapshots.
DuckDB and PyArrow are optional ([data] extra); only this module and the CLI import them.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
from collections.abc import Iterable, Sequence
from dataclasses import asdict
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np

from quantagents.data.sources import SURVIVORSHIP_LABEL, RawDaily, SourceInfo
from quantagents.market import Bars, MarketData, as_readonly, save_csv

PRICE_COLUMNS = ("open", "high", "low", "close", "adj_close", "volume", "dividend", "split")


def _duckdb() -> Any:
    import duckdb  # optional [data] extra

    return duckdb


STAMP = "%Y%m%dT%H%M%S%fZ"
_UNSAFE = re.compile(r"[^A-Za-z0-9._-]")


def safe_name(symbol: str) -> str:
    """A form of ``symbol`` that is a valid file name everywhere (Windows forbids : * ? and more)."""
    return _UNSAFE.sub("_", symbol) or "_"


class BarStore:
    """Append-only store of daily bars under ``root`` (default ``data/store``)."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)
        self.bars_dir = self.root / "bars"

    # ------------------------------------------------------------------ writing
    def append(
        self, raw: RawDaily, info: SourceInfo, *, ingested_at: datetime | None = None
    ) -> Path:
        """Write one snapshot of ``raw`` as a new Parquet file and return its path."""
        if len(raw) == 0:
            raise ValueError(f"{raw.symbol}: nothing to store")
        import pyarrow as pa
        import pyarrow.parquet as pq

        when = (ingested_at or datetime.now(UTC)).astimezone(UTC)
        digest = hashlib.sha256()
        for d in raw.dates:
            digest.update(d.isoformat().encode())
        for arr in (raw.open, raw.high, raw.low, raw.close, raw.adj_close, raw.volume):
            digest.update(np.ascontiguousarray(arr).tobytes())
        safe = safe_name(raw.symbol)
        self.bars_dir.mkdir(parents=True, exist_ok=True)
        stamp = f"{when:{STAMP}}"
        path = self.bars_dir / f"{safe}__{stamp}__{digest.hexdigest()[:10]}.parquet"
        if path.exists() or any(self.bars_dir.glob(f"{safe}__{stamp}__*.parquet")):
            raise FileExistsError(
                f"{raw.symbol} already has a snapshot at {when.isoformat()}: the store never "
                "overwrites or mixes snapshots"
            )
        n = len(raw)
        table = pa.table(
            {
                "symbol": [raw.symbol] * n,
                "date": list(raw.dates),
                "open": raw.open.tolist(),
                "high": raw.high.tolist(),
                "low": raw.low.tolist(),
                "close": raw.close.tolist(),
                "adj_close": raw.adj_close.tolist(),
                "volume": raw.volume.tolist(),
                "dividend": [float(raw.dividends.get(d, 0.0)) for d in raw.dates],
                "split": [float(raw.splits.get(d, 1.0)) for d in raw.dates],
                "ingested_at": [when] * n,
                "source": [json.dumps(asdict(info), sort_keys=True)] * n,
            }
        )
        tmp = path.with_suffix(".parquet.tmp")
        pq.write_table(table, tmp)
        os.replace(tmp, path)
        return path

    # ------------------------------------------------------------------ reading
    def _files(self) -> list[Path]:
        return sorted(self.bars_dir.glob("*.parquet")) if self.bars_dir.exists() else []

    def _query(
        self, sql: str, params: Sequence[Any] = (), files: Sequence[Path] | None = None
    ) -> list[tuple[Any, ...]]:
        files = self._files() if files is None else list(files)
        if not files:
            return []
        con = _duckdb().connect()
        try:
            con.read_parquet([str(f) for f in files]).create_view("bars")
            return list(con.execute(sql, list(params)).fetchall())
        finally:
            con.close()

    def vintages(self, symbol: str | None = None) -> list[tuple[str, datetime, int]]:
        """(symbol, ingested_at, rows) for every snapshot, oldest first."""
        where = "WHERE symbol = ?" if symbol else ""
        rows = self._query(
            f"SELECT symbol, epoch_us(ingested_at) AS t, count(*) FROM bars {where} "
            "GROUP BY symbol, t ORDER BY symbol, t",
            [symbol] if symbol else [],
        )
        return [(str(s), _from_epoch_us(int(t)), int(n)) for s, t, n in rows]

    def symbols(self) -> list[str]:
        return sorted({s for s, _, _ in self.vintages()})

    def _candidates(self, symbol: str) -> list[tuple[datetime, Path]]:
        """Snapshot files that may hold ``symbol``, newest first, found from file names alone."""
        safe = safe_name(symbol)
        out: list[tuple[datetime, Path]] = []
        if not self.bars_dir.exists():
            return out
        for path in self.bars_dir.glob(f"{safe}__*.parquet"):
            parts = path.stem.rsplit("__", 2)
            if len(parts) != 3 or parts[0] != safe:
                continue
            try:
                when = datetime.strptime(parts[1], STAMP).replace(tzinfo=UTC)
            except ValueError:
                continue
            out.append((when, path))
        return sorted(out, reverse=True)

    def _snapshot(
        self, symbol: str, as_of_ingest: datetime | None
    ) -> tuple[datetime, list[tuple[Any, ...]]]:
        cutoff = (as_of_ingest or datetime.now(UTC)).astimezone(UTC)
        for when, path in self._candidates(symbol):
            if when > cutoff:
                continue
            rows = self._query(
                "SELECT date, open, high, low, close, adj_close, volume, dividend, split, source "
                "FROM bars WHERE symbol = ? AND epoch_us(ingested_at) = ? ORDER BY date",
                [symbol, _epoch_us(when)],
                files=[path],
            )
            if rows:  # another symbol with the same file-safe name is skipped
                return when, rows
        raise KeyError(f"{symbol}: no snapshot ingested by {cutoff.isoformat()}")

    def snapshot_time(self, symbol: str, *, as_of_ingest: datetime | None = None) -> datetime:
        """Ingest time of the newest snapshot of ``symbol`` at or before ``as_of_ingest``."""
        return self._snapshot(symbol, as_of_ingest)[0]

    def raw(
        self, symbol: str, *, as_of_ingest: datetime | None = None
    ) -> tuple[RawDaily, SourceInfo]:
        """The newest snapshot of ``symbol`` ingested at or before ``as_of_ingest``."""
        _, rows = self._snapshot(symbol, as_of_ingest)
        dates = tuple(_as_date(r[0]) for r in rows)
        table = np.array([r[1:9] for r in rows], dtype=np.float64)
        raw = RawDaily(
            symbol=symbol,
            dates=dates,
            open=as_readonly(table[:, 0]),
            high=as_readonly(table[:, 1]),
            low=as_readonly(table[:, 2]),
            close=as_readonly(table[:, 3]),
            adj_close=as_readonly(table[:, 4]),
            volume=as_readonly(table[:, 5]),
            dividends={d: float(v) for d, v in zip(dates, table[:, 6], strict=True) if v != 0.0},
            splits={d: float(v) for d, v in zip(dates, table[:, 7], strict=True) if v != 1.0},
        )
        return raw, SourceInfo(**json.loads(rows[0][9]))

    def load(
        self,
        symbols: Iterable[str] | None = None,
        *,
        as_of_ingest: datetime | None = None,
        start: date | None = None,
        end: date | None = None,
    ) -> tuple[MarketData, dict[str, SourceInfo]]:
        """Adjusted daily panel for ``symbols`` (all stored symbols by default) + each source.

        Adjusted OHLC = raw OHLC x (adj_close / close) of the same row, so returns include
        dividends and splits. Volume is left as the source gave it.
        """
        wanted = list(symbols) if symbols is not None else self.symbols()
        if not wanted:
            raise ValueError("the store is empty: run `quantagents data fetch` first")
        raws = {s: self.raw(s, as_of_ingest=as_of_ingest) for s in wanted}
        return adjusted_market({s: r for s, (r, _) in raws.items()}, start, end), {
            s: i for s, (_, i) in raws.items()
        }


META_SUFFIX = ".meta.json"


def meta_path(csv_path: Path | str) -> Path:
    """Where the provenance sidecar of an exported CSV lives (``prices.csv.meta.json``)."""
    return Path(str(csv_path) + META_SUFFIX)


def export_csv(
    store: BarStore,
    out: Path | str,
    symbols: Iterable[str] | None = None,
    *,
    as_of_ingest: datetime | None = None,
    start: date | None = None,
    end: date | None = None,
) -> dict[str, Any]:
    """Write the adjusted panel as a CSV the other commands read, plus a provenance sidecar.

    The sidecar lists each symbol's source, snapshot time and caveat (spec section 74), so any
    result built from the CSV can print "survivorship-biased: upper bound only" where it applies.
    """
    market, sources = store.load(symbols, as_of_ingest=as_of_ingest, start=start, end=end)
    save_csv(market, out)
    gaps = {
        s: int(np.sum(~np.isfinite(market.bars(s).close)))
        for s in market.symbols
        if not np.all(np.isfinite(market.bars(s).close))
    }
    meta: dict[str, Any] = {
        "file": Path(out).name,
        "prices": "adjusted for splits and dividends (raw x adj_close / close)",
        "first_date": market.dates[0].isoformat(),
        "last_date": market.dates[-1].isoformat(),
        "symbols": {
            s: {
                "source": sources[s].name,
                "snapshot_ingested_at": store.snapshot_time(
                    s, as_of_ingest=as_of_ingest
                ).isoformat(),
                "label": sources[s].label,
            }
            for s in market.symbols
        },
        "labels": sorted({sources[s].label for s in market.symbols}),
        "missing_days": gaps,
    }
    meta_path(out).write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    return meta


def data_labels(csv_path: Path | str) -> list[str]:
    """The caveats for results built on ``csv_path`` (from its sidecar, or the safe default)."""
    sidecar = meta_path(csv_path)
    if sidecar.exists():
        labels: list[str] = json.loads(sidecar.read_text(encoding="utf-8"))["labels"]
        return labels
    return [f"source not recorded; {SURVIVORSHIP_LABEL}"]


def adjusted_market(
    raws: dict[str, RawDaily], start: date | None = None, end: date | None = None
) -> MarketData:
    """Union-of-dates panel of adjusted bars; a symbol missing a date gets NaN (A02 flags it)."""
    days = sorted({d for r in raws.values() for d in r.dates})
    days = [d for d in days if (start is None or d >= start) and (end is None or d <= end)]
    if not days:
        raise ValueError("no bars in the requested date range")
    bars: dict[str, Bars] = {}
    for symbol, r in raws.items():
        pos = {d: k for k, d in enumerate(r.dates)}
        table = np.full((len(days), 5), math.nan)
        for i, d in enumerate(days):
            k = pos.get(d)
            if k is None:
                continue
            c = float(r.close[k])
            f = float(r.adj_close[k]) / c if c > 0 and math.isfinite(float(r.adj_close[k])) else 1.0
            table[i] = (
                float(r.open[k]) * f,
                float(r.high[k]) * f,
                float(r.low[k]) * f,
                c * f,
                float(r.volume[k]),
            )
        bars[symbol] = Bars.from_arrays(
            open=table[:, 0],
            high=table[:, 1],
            low=table[:, 2],
            close=table[:, 3],
            volume=table[:, 4],
        )
    return MarketData(days, bars)


_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


def _epoch_us(t: datetime) -> int:
    """Microseconds since 1970 UTC (exact integer, so equality lookups are safe)."""
    delta = t.astimezone(UTC) - _EPOCH
    return (delta.days * 86_400 + delta.seconds) * 1_000_000 + delta.microseconds


def _from_epoch_us(us: int) -> datetime:
    return _EPOCH + timedelta(microseconds=us)


def _as_date(x: Any) -> date:
    if isinstance(x, datetime):
        return x.date()
    if isinstance(x, date):
        return x
    raise TypeError(f"not a date: {x!r}")
