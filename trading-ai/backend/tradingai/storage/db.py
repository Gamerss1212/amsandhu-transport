"""SQLite for financial state: orders, fills, ledger, positions, decisions, audit, research ledger, settings.

* Crash safety: WAL journal, synchronous=FULL, every write in a transaction (`with db.tx() as c:`), versioned
  migrations, integrity check at start-up, online backups.
* The audit log is append-only and hash-chained: each row stores the hash of the previous row, so a deleted or edited
  row is detectable (`verify_audit()`).
* Money is stored as TEXT holding a Decimal, never as a float.

Large market history does not live here; it lives in Parquet files read through DuckDB (storage/marketstore.py).
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import time
from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterator, Optional

MIGRATIONS: list[str] = [
    # 1: the core
    """
    CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
    CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL, updated INTEGER NOT NULL);
    CREATE TABLE audit (
        id INTEGER PRIMARY KEY AUTOINCREMENT, ts INTEGER NOT NULL, kind TEXT NOT NULL, severity TEXT NOT NULL,
        correlation_id TEXT, message TEXT NOT NULL, data TEXT, prev_hash TEXT NOT NULL, hash TEXT NOT NULL);
    CREATE INDEX audit_kind ON audit(kind, ts);
    CREATE INDEX audit_corr ON audit(correlation_id);
    CREATE TABLE accounts (
        account_id TEXT PRIMARY KEY, broker TEXT NOT NULL, environment TEXT NOT NULL, label TEXT NOT NULL,
        base_currency TEXT NOT NULL, simulated INTEGER NOT NULL, created INTEGER NOT NULL);
    CREATE TABLE ledger (
        id INTEGER PRIMARY KEY AUTOINCREMENT, account_id TEXT NOT NULL, ts INTEGER NOT NULL, kind TEXT NOT NULL,
        currency TEXT NOT NULL, amount TEXT NOT NULL, ref TEXT, note TEXT);
    CREATE INDEX ledger_acct ON ledger(account_id, ts);
    CREATE TABLE positions (
        account_id TEXT NOT NULL, instrument_id TEXT NOT NULL, qty TEXT NOT NULL, avg_price TEXT NOT NULL,
        realized TEXT NOT NULL, currency TEXT NOT NULL, strategy_lots TEXT NOT NULL DEFAULT '{}',
        updated INTEGER NOT NULL, PRIMARY KEY (account_id, instrument_id));
    CREATE TABLE orders (
        client_order_id TEXT PRIMARY KEY, decision_id TEXT, strategy_id TEXT, account_id TEXT NOT NULL,
        environment TEXT NOT NULL, instrument_id TEXT NOT NULL, side TEXT NOT NULL, qty TEXT NOT NULL,
        filled_qty TEXT NOT NULL DEFAULT '0', avg_fill_price TEXT, order_type TEXT NOT NULL, limit_price TEXT,
        stop_price TEXT, tif TEXT NOT NULL, status TEXT NOT NULL, broker_order_id TEXT, algo TEXT, parent_id TEXT,
        reason TEXT, created INTEGER NOT NULL, updated INTEGER NOT NULL);
    CREATE INDEX orders_status ON orders(status);
    CREATE TABLE fills (
        fill_id TEXT PRIMARY KEY, client_order_id TEXT NOT NULL, account_id TEXT NOT NULL, instrument_id TEXT NOT NULL,
        side TEXT NOT NULL, qty TEXT NOT NULL, price TEXT NOT NULL, fee TEXT NOT NULL, fee_currency TEXT NOT NULL,
        liquidity TEXT, environment TEXT NOT NULL, ts INTEGER NOT NULL, decision_price TEXT, arrival_mid TEXT);
    CREATE INDEX fills_order ON fills(client_order_id);
    CREATE TABLE decisions (
        decision_id TEXT PRIMARY KEY, ts INTEGER NOT NULL, instrument_id TEXT NOT NULL, strategy_id TEXT,
        mode TEXT NOT NULL, signal TEXT, regime TEXT, votes TEXT, risk TEXT, order_json TEXT, outcome TEXT NOT NULL,
        reason TEXT, latency TEXT);
    CREATE INDEX decisions_ts ON decisions(ts);
    CREATE TABLE experiments (
        experiment_id TEXT PRIMARY KEY, created INTEGER NOT NULL, family TEXT NOT NULL, strategy_id TEXT NOT NULL,
        hypothesis TEXT, params TEXT NOT NULL, dataset TEXT NOT NULL, profile TEXT NOT NULL, results TEXT,
        status TEXT NOT NULL, reason TEXT, code_version TEXT NOT NULL, seed INTEGER NOT NULL,
        trials_at_run INTEGER NOT NULL, finished INTEGER);
    CREATE INDEX experiments_family ON experiments(family);
    CREATE TABLE connections (
        connection_id TEXT PRIMARY KEY, broker TEXT NOT NULL, environment TEXT NOT NULL, label TEXT NOT NULL,
        status TEXT NOT NULL, last_test TEXT, capabilities TEXT, created INTEGER NOT NULL, updated INTEGER NOT NULL);
    CREATE TABLE strategy_status (
        strategy_id TEXT PRIMARY KEY, version TEXT NOT NULL, status TEXT NOT NULL, reason TEXT, updated INTEGER NOT NULL);
    CREATE TABLE provenance (
        dataset_id TEXT PRIMARY KEY, provider TEXT NOT NULL, market TEXT NOT NULL, symbol TEXT NOT NULL,
        tf TEXT NOT NULL, start_ms INTEGER, end_ms INTEGER, rows INTEGER NOT NULL, downloaded INTEGER NOT NULL,
        sha256 TEXT NOT NULL, transforms TEXT, simulated INTEGER NOT NULL);
    CREATE TABLE session_snapshots (
        session_id TEXT PRIMARY KEY, ts INTEGER NOT NULL, mode TEXT NOT NULL, config TEXT NOT NULL);
    """,
    # 2: decisions carry the bot, timeframe and whether the data was simulated (the pages show them after a reload)
    """
    ALTER TABLE decisions ADD COLUMN bot_id TEXT;
    ALTER TABLE decisions ADD COLUMN tf TEXT;
    ALTER TABLE decisions ADD COLUMN simulated INTEGER;
    CREATE INDEX decisions_instrument ON decisions(instrument_id, ts);
    """,
]

GENESIS = "0" * 64


def now_ms() -> int:
    return int(time.time() * 1000)


def _canon(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=_default)


def _default(o: Any) -> Any:
    if isinstance(o, Decimal):
        return str(o)
    if isinstance(o, (set, frozenset)):
        return sorted(o)
    if hasattr(o, "model_dump"):
        return o.model_dump()
    if hasattr(o, "__dict__"):
        return {k: v for k, v in vars(o).items() if not k.startswith("_")}
    return str(o)


def dumps(obj: Any) -> str:
    return json.dumps(obj, default=_default)


class Database:
    """One connection, serialized by a lock (SQLite allows one writer at a time anyway)."""

    def __init__(self, path: str | Path):
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._con = sqlite3.connect(self.path, check_same_thread=False, isolation_level=None, timeout=30)
        self._con.row_factory = sqlite3.Row
        self._con.execute("PRAGMA journal_mode=WAL")
        self._con.execute("PRAGMA synchronous=FULL")
        self._con.execute("PRAGMA foreign_keys=ON")
        self._migrate()

    # ------------------------------------------------------------------ schema
    def _migrate(self) -> None:
        with self._lock:
            self._con.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)")
            row = self._con.execute("SELECT version FROM schema_version").fetchone()
            current = row[0] if row else 0
            if row is None:
                self._con.execute("INSERT INTO schema_version (version) VALUES (0)")
            for i, sql in enumerate(MIGRATIONS[current:], start=current + 1):
                self._con.execute("BEGIN IMMEDIATE")
                try:
                    for stmt in [s for s in sql.split(";") if s.strip()]:
                        self._con.execute(stmt)
                    self._con.execute("UPDATE schema_version SET version=?", (i,))
                    self._con.execute("COMMIT")
                except Exception:
                    self._con.execute("ROLLBACK")
                    raise

    @property
    def version(self) -> int:
        return int(self._con.execute("SELECT version FROM schema_version").fetchone()[0])

    # ------------------------------------------------------------------ access
    @contextmanager
    def tx(self) -> Iterator[sqlite3.Connection]:
        """A write transaction: all or nothing."""
        with self._lock:
            self._con.execute("BEGIN IMMEDIATE")
            try:
                yield self._con
                self._con.execute("COMMIT")
            except BaseException:
                self._con.execute("ROLLBACK")
                raise

    def query(self, sql: str, args: tuple = ()) -> list[dict]:
        with self._lock:
            return [dict(r) for r in self._con.execute(sql, args).fetchall()]

    def one(self, sql: str, args: tuple = ()) -> Optional[dict]:
        rows = self.query(sql, args)
        return rows[0] if rows else None

    def execute(self, sql: str, args: tuple = ()) -> None:
        with self.tx() as c:
            c.execute(sql, args)

    # ------------------------------------------------------------------ settings
    def get_setting(self, key: str, default: Any = None) -> Any:
        r = self.one("SELECT value FROM settings WHERE key=?", (key,))
        return json.loads(r["value"]) if r else default

    def set_setting(self, key: str, value: Any) -> None:
        self.execute("INSERT INTO settings (key, value, updated) VALUES (?,?,?) ON CONFLICT(key) DO UPDATE SET "
                     "value=excluded.value, updated=excluded.updated", (key, dumps(value), now_ms()))

    # ------------------------------------------------------------------ audit (append-only, hash-chained)
    def audit(self, kind: str, message: str, *, severity: str = "info", correlation_id: Optional[str] = None,
              data: Any = None) -> dict:
        if severity not in ("debug", "info", "warning", "error", "critical"):
            raise ValueError(f"bad severity {severity!r}")
        with self.tx() as c:
            prev = c.execute("SELECT hash FROM audit ORDER BY id DESC LIMIT 1").fetchone()
            prev_hash = prev[0] if prev else GENESIS
            ts = now_ms()
            body = {"ts": ts, "kind": kind, "severity": severity, "correlation_id": correlation_id,
                    "message": message, "data": data}
            h = hashlib.sha256((prev_hash + _canon(body)).encode()).hexdigest()
            cur = c.execute("INSERT INTO audit (ts, kind, severity, correlation_id, message, data, prev_hash, hash) "
                            "VALUES (?,?,?,?,?,?,?,?)", (ts, kind, severity, correlation_id, message,
                                                         None if data is None else _canon(data), prev_hash, h))
            return {"id": cur.lastrowid, **body, "hash": h}

    def audit_rows(self, *, since_id: int = 0, kind: Optional[str] = None, correlation_id: Optional[str] = None,
                   min_severity: str = "debug", limit: int = 500) -> list[dict]:
        order = ["debug", "info", "warning", "error", "critical"]
        sev = order[order.index(min_severity):]
        sql = f"SELECT * FROM audit WHERE id>? AND severity IN ({','.join('?' * len(sev))})"
        args: list = [since_id, *sev]
        if kind:
            sql += " AND kind=?"
            args.append(kind)
        if correlation_id:
            sql += " AND correlation_id=?"
            args.append(correlation_id)
        sql += " ORDER BY id DESC LIMIT ?"
        args.append(int(limit))
        rows = self.query(sql, tuple(args))
        for r in rows:
            r["data"] = json.loads(r["data"]) if r["data"] else None
        return rows

    def verify_audit(self) -> tuple[bool, Optional[int]]:
        """(True, None) when every row chains to the previous one; else (False, first broken id)."""
        prev = GENESIS
        for r in self.query("SELECT * FROM audit ORDER BY id"):
            body = {"ts": r["ts"], "kind": r["kind"], "severity": r["severity"], "correlation_id": r["correlation_id"],
                    "message": r["message"], "data": json.loads(r["data"]) if r["data"] else None}
            if r["prev_hash"] != prev or hashlib.sha256((prev + _canon(body)).encode()).hexdigest() != r["hash"]:
                return False, r["id"]
            prev = r["hash"]
        return True, None

    # ------------------------------------------------------------------ health
    def integrity(self) -> str:
        return str(self._con.execute("PRAGMA quick_check").fetchone()[0])

    def backup(self, dest: str | Path) -> Path:
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            out = sqlite3.connect(str(dest))
            try:
                self._con.backup(out)
            finally:
                out.close()
        return dest

    def size_bytes(self) -> int:
        p = Path(self.path)
        return sum(f.stat().st_size for f in (p, Path(self.path + "-wal")) if f.exists())

    def close(self) -> None:
        with self._lock:
            self._con.close()
