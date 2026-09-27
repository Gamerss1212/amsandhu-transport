"""SQLite storage: every signal, intent, risk decision, order, fill, trade, health record and
event, plus bars for replay, bot state for restarts, the account, and the control queue.

* WAL mode, one connection per thread, writes serialised by a lock, busy timeout.
* Writes retry briefly; a write that still fails raises StorageError. The runtime treats that as
  a critical fault: it stops opening new trades (open positions keep their stops) until storage
  works again, and keeps the unsaved records in a bounded buffer to flush later.
* Retention: `prune()` deletes old bars / health rows / signals by age (defaults below).
* Backups: `backup()` writes a consistent copy with SQLite's online backup API and keeps the
  newest N copies.
* Integrity: `check()` runs PRAGMA integrity_check; `recover` in the CLI restores the newest
  good backup if the live file is corrupt.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from typing import Any, Dict, Iterable, List, Optional

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS bars (venue TEXT, instrument TEXT, tf TEXT, t INTEGER, o REAL, h REAL, l REAL, c REAL,
    v REAL, recv INTEGER, prov TEXT, PRIMARY KEY (venue, instrument, tf, t)) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS signals (id INTEGER PRIMARY KEY, bot_id TEXT, strategy_id TEXT, strategy_version TEXT,
    config_version TEXT, instrument TEXT, venue TEXT, tf TEXT, bar_time INTEGER, decision_time INTEGER, action TEXT,
    reason TEXT, features TEXT, rules TEXT);
CREATE INDEX IF NOT EXISTS ix_signals_bot ON signals (bot_id, bar_time);
CREATE TABLE IF NOT EXISTS intents (intent_id TEXT PRIMARY KEY, bot_id TEXT, time INTEGER, body TEXT);
CREATE TABLE IF NOT EXISTS risk_decisions (intent_id TEXT, bot_id TEXT, approved INTEGER, adjusted_qty REAL,
    checks TEXT, time INTEGER);
CREATE INDEX IF NOT EXISTS ix_risk_bot ON risk_decisions (bot_id, time);
CREATE TABLE IF NOT EXISTS orders (order_id TEXT PRIMARY KEY, intent_id TEXT, bot_id TEXT, instrument TEXT,
    venue TEXT, side TEXT, qty REAL, filled_qty REAL, avg_price REAL, status TEXT, reason TEXT, model TEXT,
    time INTEGER);
CREATE TABLE IF NOT EXISTS fills (fill_id TEXT PRIMARY KEY, order_id TEXT, intent_id TEXT, bot_id TEXT,
    instrument TEXT, venue TEXT, side TEXT, qty REAL, price REAL, fee REAL, liquidity TEXT, time INTEGER,
    simulated INTEGER, model TEXT);
CREATE INDEX IF NOT EXISTS ix_fills_bot ON fills (bot_id, time);
CREATE TABLE IF NOT EXISTS trades (id INTEGER PRIMARY KEY, bot_id TEXT, strategy_id TEXT, instrument TEXT,
    venue TEXT, side INTEGER, qty REAL, entry_time INTEGER, entry_price REAL, exit_time INTEGER, exit_price REAL,
    fees REAL, pnl REAL, r REAL, bars INTEGER, entry_reason TEXT, exit_reason TEXT, mfe_r REAL, mae_r REAL);
CREATE INDEX IF NOT EXISTS ix_trades_bot ON trades (bot_id, exit_time);
CREATE TABLE IF NOT EXISTS bot_state (bot_id TEXT PRIMARY KEY, state TEXT, updated INTEGER);
CREATE TABLE IF NOT EXISTS bot_health (time INTEGER, bot_id TEXT, state TEXT, last_eval INTEGER, last_data INTEGER,
    last_decision TEXT, errors INTEGER, message TEXT);
CREATE INDEX IF NOT EXISTS ix_health_time ON bot_health (time);
CREATE TABLE IF NOT EXISTS system_health (time INTEGER PRIMARY KEY, body TEXT);
CREATE TABLE IF NOT EXISTS equity (time INTEGER PRIMARY KEY, equity REAL, cash REAL, gross REAL, twr REAL);
CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY, time INTEGER, level TEXT, kind TEXT, bot_id TEXT,
    message TEXT, body TEXT);
CREATE INDEX IF NOT EXISTS ix_events_time ON events (time);
CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT, updated INTEGER);
CREATE TABLE IF NOT EXISTS cash_flows (id INTEGER PRIMARY KEY, time INTEGER, kind TEXT, amount REAL,
    equity_before REAL, equity_after REAL, note TEXT);
CREATE TABLE IF NOT EXISTS control (id INTEGER PRIMARY KEY, time INTEGER, command TEXT, args TEXT,
    status TEXT DEFAULT 'pending', result TEXT, done INTEGER);
CREATE TABLE IF NOT EXISTS experiments (experiment_id TEXT PRIMARY KEY, created INTEGER, kind TEXT, spec TEXT,
    code_version TEXT, summary TEXT);
CREATE TABLE IF NOT EXISTS evaluation_results (id INTEGER PRIMARY KEY, experiment_id TEXT, strategy_id TEXT,
    strategy_version TEXT, instrument TEXT, tf TEXT, period TEXT, config TEXT, dataset TEXT, metrics TEXT,
    code_version TEXT, seed INTEGER, created INTEGER);
CREATE INDEX IF NOT EXISTS ix_eval_strategy ON evaluation_results (strategy_id, period);
"""

SCHEMA_VERSION = "1"

RETENTION_DAYS = {"bars": 14, "bot_health": 3, "system_health": 7, "signals": 30, "equity": 90, "events": 90}


class StorageError(RuntimeError):
    pass


def _j(x) -> str:
    return json.dumps(x, default=str, separators=(",", ":"))


class Storage:
    def __init__(self, path: str, fail_hook=None):
        self.path = path
        os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
        self.local = threading.local()
        self.wlock = threading.Lock()
        self.fail_hook = fail_hook               # test hook: callable() -> raise to simulate storage failure
        self.write_errors = 0
        self.writes = 0
        conn = self._conn()
        with self.wlock:
            conn.executescript(SCHEMA)
            conn.execute("INSERT OR IGNORE INTO meta VALUES ('schema_version', ?)", (SCHEMA_VERSION,))
            conn.commit()

    def _conn(self) -> sqlite3.Connection:
        c = getattr(self.local, "conn", None)
        if c is None:
            c = sqlite3.connect(self.path, timeout=15, check_same_thread=False)
            c.execute("PRAGMA journal_mode=WAL")
            c.execute("PRAGMA synchronous=NORMAL")
            c.execute("PRAGMA busy_timeout=15000")
            c.row_factory = sqlite3.Row
            self.local.conn = c
        return c

    def close(self):
        c = getattr(self.local, "conn", None)
        if c is not None:
            c.close()
            self.local.conn = None

    # ------------------------------------------------------------------ core write
    def write(self, sql: str, rows: Iterable[tuple] = None, many: bool = False):
        last = None
        for attempt in range(3):
            try:
                if self.fail_hook:
                    self.fail_hook()
                with self.wlock:
                    c = self._conn()
                    if many:
                        c.executemany(sql, list(rows or []))
                    else:
                        c.execute(sql, rows or ())
                    c.commit()
                self.writes += 1
                return
            except (sqlite3.OperationalError, sqlite3.DatabaseError, OSError) as e:
                last = e
                time.sleep(0.05 * (attempt + 1))
        self.write_errors += 1
        raise StorageError(f"storage write failed: {last}")

    def query(self, sql: str, args: tuple = ()) -> List[dict]:
        return [dict(r) for r in self._conn().execute(sql, args).fetchall()]

    # ------------------------------------------------------------------ records
    def save_bars(self, bars):
        self.write("INSERT OR REPLACE INTO bars VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                   [(b.venue, b.instrument, b.timeframe, b.event_time, b.open, b.high, b.low, b.close, b.volume,
                     b.receipt_time, b.provenance) for b in bars], many=True)

    def load_bars(self, venue, instrument, tf, start=None, end=None) -> List[dict]:
        q = "SELECT * FROM bars WHERE venue=? AND instrument=? AND tf=?"
        a: list = [venue, instrument, tf]
        if start is not None:
            q += " AND t>=?"; a.append(start)
        if end is not None:
            q += " AND t<?"; a.append(end)
        return self.query(q + " ORDER BY t", tuple(a))

    def save_signals(self, sigs: List[dict]):
        self.write("INSERT INTO signals (bot_id, strategy_id, strategy_version, config_version, instrument, venue, tf,"
                   " bar_time, decision_time, action, reason, features, rules) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                   [(s["bot_id"], s["strategy_id"], s["strategy_version"], s["config_version"], s["instrument"],
                     s["venue"], s["timeframe"], s["bar_time"], s["decision_time"], s["action"], s["reason"],
                     _j(s.get("features", {})), _j(s.get("rules", []))) for s in sigs], many=True)

    def save_intent(self, intent: dict):
        self.write("INSERT OR IGNORE INTO intents VALUES (?,?,?,?)",
                   (intent["intent_id"], intent["bot_id"], intent.get("created_time"), _j(intent)))

    def save_risk(self, d: dict):
        self.write("INSERT INTO risk_decisions VALUES (?,?,?,?,?,?)",
                   (d["intent_id"], d["bot_id"], int(d["approved"]), d.get("adjusted_quantity"), _j(d["checks"]),
                    d["decision_time"]))

    def save_order(self, o: dict, intent: dict):
        self.write("INSERT OR REPLACE INTO orders VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                   (o["order_id"], o["intent_id"], intent["bot_id"], intent["instrument"], intent["venue"],
                    intent["side"], intent["quantity"], o.get("filled_qty"), o.get("avg_price"), o["status"],
                    o.get("reason"), o.get("model"), intent.get("created_time")))

    def save_fill(self, f: dict):
        self.write("INSERT OR IGNORE INTO fills VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                   (f["fill_id"], f["order_id"], f["intent_id"], f["bot_id"], f["instrument"], f["venue"], f["side"],
                    f["quantity"], f["price"], f["fee"], f["liquidity"], f["event_time"], int(f["simulated"]),
                    f["model"]))

    def save_trade(self, bot_id: str, venue: str, t: dict):
        self.write("INSERT INTO trades (bot_id, strategy_id, instrument, venue, side, qty, entry_time, entry_price,"
                   " exit_time, exit_price, fees, pnl, r, bars, entry_reason, exit_reason, mfe_r, mae_r)"
                   " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                   (bot_id, t["strategy_id"], t["instrument"], venue, t["side"], t["qty"], t["entry_time"],
                    t["entry_price"], t["exit_time"], t["exit_price"], t["fees"], t["pnl"], t["r"], t["bars"],
                    t["entry_reason"], t["exit_reason"], t["mfe_r"], t["mae_r"]))

    def save_bot_states(self, states: Dict[str, dict]):
        now = int(time.time() * 1000)
        self.write("INSERT OR REPLACE INTO bot_state VALUES (?,?,?)",
                   [(k, _j(v), now) for k, v in states.items()], many=True)

    def load_bot_states(self) -> Dict[str, dict]:
        out = {}
        for r in self.query("SELECT bot_id, state FROM bot_state"):
            try:
                out[r["bot_id"]] = json.loads(r["state"])
            except ValueError:
                out[r["bot_id"]] = {"corrupt": True}
        return out

    def save_health(self, rows: List[dict], system: dict, t: int):
        self.write("INSERT INTO bot_health VALUES (?,?,?,?,?,?,?,?)",
                   [(t, h["bot_id"], h["state"], h.get("last_evaluation_time"), h.get("last_data_time"),
                     h.get("last_decision"), h.get("consecutive_errors", 0), h.get("message", "")) for h in rows],
                   many=True)
        self.write("INSERT OR REPLACE INTO system_health VALUES (?,?)", (t, _j(system)))

    def save_equity(self, t, equity, cash, gross, twr):
        self.write("INSERT OR REPLACE INTO equity VALUES (?,?,?,?,?)", (t, equity, cash, gross, twr))

    def event(self, level: str, kind: str, message: str, bot_id: str = None, body: Any = None):
        self.write("INSERT INTO events (time, level, kind, bot_id, message, body) VALUES (?,?,?,?,?,?)",
                   (int(time.time() * 1000), level, kind, bot_id, message, _j(body) if body is not None else None))

    def kv_set(self, key: str, value: Any):
        self.write("INSERT OR REPLACE INTO kv VALUES (?,?,?)", (key, _j(value), int(time.time() * 1000)))

    def kv_get(self, key: str, default=None):
        r = self.query("SELECT value FROM kv WHERE key=?", (key,))
        if not r:
            return default
        try:
            return json.loads(r[0]["value"])
        except ValueError:
            return default

    def save_cash_flow(self, f: dict):
        self.write("INSERT INTO cash_flows (time, kind, amount, equity_before, equity_after, note) VALUES (?,?,?,?,?,?)",
                   (f["time"], f["kind"], f["amount"], f["equity_before"], f["equity_after"], f.get("note", "")))

    # ------------------------------------------------------------------ control queue
    def command(self, command: str, args: dict = None) -> int:
        with self.wlock:
            c = self._conn()
            cur = c.execute("INSERT INTO control (time, command, args) VALUES (?,?,?)",
                            (int(time.time() * 1000), command, _j(args or {})))
            c.commit()
            return cur.lastrowid

    def pending_commands(self) -> List[dict]:
        rows = self.query("SELECT * FROM control WHERE status='pending' ORDER BY id")
        for r in rows:
            r["args"] = json.loads(r["args"] or "{}")
        return rows

    def finish_command(self, cid: int, status: str, result: Any):
        self.write("UPDATE control SET status=?, result=?, done=? WHERE id=?",
                   (status, _j(result), int(time.time() * 1000), cid))

    def command_result(self, cid: int) -> Optional[dict]:
        r = self.query("SELECT * FROM control WHERE id=?", (cid,))
        return r[0] if r else None

    # ------------------------------------------------------------------ experiments
    def save_experiment(self, exp_id: str, kind: str, spec: dict, code_version: str, summary: dict):
        self.write("INSERT OR REPLACE INTO experiments VALUES (?,?,?,?,?,?)",
                   (exp_id, int(time.time() * 1000), kind, _j(spec), code_version, _j(summary)))

    def save_evaluation(self, exp_id: str, r: dict):
        self.write("INSERT INTO evaluation_results (experiment_id, strategy_id, strategy_version, instrument, tf, period,"
                   " config, dataset, metrics, code_version, seed, created) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                   (exp_id, r["strategy_id"], r.get("strategy_version"), r.get("instrument"), r.get("tf"),
                    r["period"], _j(r.get("config", {})), r.get("dataset"), _j(r["metrics"]), r.get("code_version"),
                    r.get("seed"), int(time.time() * 1000)))

    # ------------------------------------------------------------------ maintenance
    def prune(self, now_ms: Optional[int] = None, days: Dict[str, int] = None) -> Dict[str, int]:
        now_ms = now_ms or int(time.time() * 1000)
        d = dict(RETENTION_DAYS, **(days or {}))
        cols = {"bars": "t", "bot_health": "time", "system_health": "time", "signals": "decision_time",
                "equity": "time", "events": "time"}
        out = {}
        for table, col in cols.items():
            cut = now_ms - d[table] * 86_400_000
            with self.wlock:
                c = self._conn()
                cur = c.execute(f"DELETE FROM {table} WHERE {col} < ?", (cut,))
                c.commit()
            out[table] = cur.rowcount
        return out

    def backup(self, dest_dir: str, keep: int = 7) -> str:
        os.makedirs(dest_dir, exist_ok=True)
        dest = os.path.join(dest_dir, time.strftime("mab-%Y%m%d-%H%M%S.db"))
        src = self._conn()
        dst = sqlite3.connect(dest)
        with self.wlock:
            src.backup(dst)
        dst.close()
        files = sorted(f for f in os.listdir(dest_dir) if f.startswith("mab-") and f.endswith(".db"))
        for f in files[:-keep]:
            os.remove(os.path.join(dest_dir, f))
        return dest

    def check(self) -> str:
        return self._conn().execute("PRAGMA integrity_check").fetchone()[0]

    def size_bytes(self) -> int:
        total = 0
        for suffix in ("", "-wal", "-shm"):
            p = self.path + suffix
            if os.path.exists(p):
                total += os.path.getsize(p)
        return total
