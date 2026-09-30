"""SQLite storage: every signal, intent, risk decision, order, fill, trade, health record and
event, plus bars for replay, bot state for restarts, the account, and the control queue.

* Schema: versioned migrations (mab/migrations.py) run when a database is opened.
* WAL mode, one connection per thread, writes serialised by a lock, busy timeout.
* Writes retry briefly; a write that still fails raises StorageError. The runtime treats that as
  a critical fault: it stops opening new trades (open positions keep their stops) until storage
  works again, and keeps the unsaved records in a bounded buffer to flush later.
* Audit log: `audit()` appends one step of a decision's lifecycle (market update, signal, risk
  decision, order, acknowledgement, fill, position management, exit) or a control/connection/research
  event. Payloads are sanitised: anything that looks like a credential is removed before it is written.
* Retention: `prune()` deletes old bars / health rows / signals by age (defaults below); order,
  fill, risk and control records in the audit log are kept for a year.
* Backups: `backup()` writes a consistent copy with SQLite's online backup API and keeps the
  newest N copies.
* Integrity: `check()` runs PRAGMA integrity_check; `recover` in the CLI restores the newest
  good backup if the live file is corrupt.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import threading
import time
from typing import Any, Dict, Iterable, List, Optional

from mab import migrations

SCHEMA = migrations.V1                    # the original schema (kept for tools that print it)
SCHEMA_VERSION = str(migrations.LATEST)

RETENTION_DAYS = {"bars": 14, "bot_health": 3, "system_health": 7, "signals": 30, "equity": 90, "events": 90,
                  "connection_snapshots": 30}
# audit events: routine evaluation records are kept for a short time, everything about orders, money,
# controls and connections for a year
AUDIT_SHORT_KINDS = ("market_update", "signal", "data")
AUDIT_RETENTION_DAYS = {"short": 14, "long": 366}

SEVERITIES = ("debug", "info", "warning", "error", "critical")
_SECRET_KEY = re.compile(r"(secret|password|passwd|token|api[_-]?key|apikey|signature|authorization|private|"
                         r"credential|cookie|session)", re.I)
_SAFE_KEYS = {"input_tokens", "output_tokens", "tokens", "token_budget", "session_close", "max_tokens", "session_id_hash"}
_PREFIXED = re.compile(r"\b(?:sk|pk|ak|rk)-[A-Za-z0-9_\-]{12,}")
_OPAQUE = re.compile(r"[A-Za-z0-9+/_\-]{32,}={0,2}")


def _mask_opaque(m: "re.Match") -> str:
    s = m.group(0)
    # credentials are long mixed-case strings; hashes and ids (lower-case hex, UUID parts) are left readable
    if any(c.isupper() for c in s) and any(c.islower() for c in s) and any(c.isdigit() for c in s):
        return "[masked]"
    return s


def _redact_text(s: str) -> str:
    try:                                          # values the secret store has handed out in this process
        from mab.secrets_store import RedactingFilter
        for v in RedactingFilter.values:
            if v in s:
                s = s.replace(v, "***")
    except Exception:                             # noqa: BLE001
        pass
    return _OPAQUE.sub(_mask_opaque, _PREFIXED.sub("[masked]", s))


def sanitize(obj: Any, depth: int = 0) -> Any:
    """A copy of obj that is safe to log: keys that name credentials are dropped and long opaque strings
    that look like keys are masked. Used on every audit payload and summary."""
    if depth > 6:
        return "..."
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if isinstance(k, str) and _SECRET_KEY.search(k) and k not in _SAFE_KEYS:
                out[k] = "[removed]"
            else:
                out[k] = sanitize(v, depth + 1)
        return out
    if isinstance(obj, (list, tuple)):
        return [sanitize(v, depth + 1) for v in list(obj)[:500]]
    if isinstance(obj, str):
        return _redact_text(obj if len(obj) <= 4000 else obj[:4000] + "...")
    return obj


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
        self.audit_hook = None                   # callable(event dict) after each audit write (in-process listeners)
        conn = self._conn()
        with self.wlock:
            self.migrated = migrations.migrate(conn, path)

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

    # ------------------------------------------------------------------ audit log (the lifecycle record)
    def audit(self, kind: str, summary: str, *, stage: str = None, severity: str = "info", mode: str = None,
              bot_id: str = None, deployment_id: str = None, symbol: str = None, venue: str = None,
              connection_id: str = None, correlation_id: str = None, order_id: str = None, payload: Any = None,
              ts: Optional[int] = None) -> int:
        """Append one audit event and return its id. Evidence goes in `payload` (sanitised: no credentials)."""
        if severity not in SEVERITIES:
            severity = "info"
        t = int(ts if ts is not None else time.time() * 1000)
        body = _j(sanitize(payload)) if payload is not None else None
        row = (t, kind, stage, severity, mode, bot_id, deployment_id, symbol, venue, connection_id, correlation_id,
               order_id, sanitize(str(summary))[:1000], body)
        last = None
        for attempt in range(3):
            try:
                if self.fail_hook:
                    self.fail_hook()
                with self.wlock:
                    c = self._conn()
                    cur = c.execute("INSERT INTO audit_events (ts, kind, stage, severity, mode, bot_id, deployment_id,"
                                    " symbol, venue, connection_id, correlation_id, order_id, summary, payload)"
                                    " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", row)
                    c.commit()
                    eid = cur.lastrowid
                self.writes += 1
                break
            except (sqlite3.OperationalError, sqlite3.DatabaseError, OSError) as e:
                last = e
                time.sleep(0.05 * (attempt + 1))
        else:
            self.write_errors += 1
            raise StorageError(f"storage write failed: {last}")
        if self.audit_hook is not None:
            try:
                self.audit_hook({"id": eid, "ts": t, "kind": kind, "stage": stage, "severity": severity, "mode": mode,
                                 "bot_id": bot_id, "deployment_id": deployment_id, "symbol": symbol, "venue": venue,
                                 "connection_id": connection_id, "correlation_id": correlation_id,
                                 "order_id": order_id, "summary": row[12]})
            except Exception:                                           # noqa: BLE001 - a listener never breaks a write
                pass
        return eid

    @staticmethod
    def _audit_row(r: dict) -> dict:
        if r.get("payload"):
            try:
                r["payload"] = json.loads(r["payload"])
            except ValueError:
                pass
        return r

    def audit_since(self, after_id: int = 0, limit: int = 200, min_severity: str = "debug") -> List[dict]:
        """Events newer than after_id, oldest first (what a live stream sends next)."""
        sev = SEVERITIES[SEVERITIES.index(min_severity):] if min_severity in SEVERITIES else SEVERITIES
        q = ("SELECT * FROM audit_events WHERE id > ? AND severity IN (%s) ORDER BY id LIMIT ?"
             % ",".join("?" * len(sev)))
        return [self._audit_row(r) for r in self.query(q, (int(after_id), *sev, int(limit)))]

    def audit_last_id(self) -> int:
        r = self.query("SELECT MAX(id) AS m FROM audit_events")
        return int(r[0]["m"] or 0) if r else 0

    def audit_search(self, *, text: str = None, kinds: Iterable[str] = None, bot_id: str = None,
                     deployment_id: str = None, symbol: str = None, mode: str = None, severity: str = None,
                     correlation_id: str = None, since: int = None, until: int = None, before_id: int = None,
                     limit: int = 200) -> List[dict]:
        """Filtered history, newest first. Every filter is optional; text matches summary or ids."""
        where, args = [], []
        if text:
            like = f"%{text}%"
            where.append("(summary LIKE ? OR bot_id LIKE ? OR symbol LIKE ? OR correlation_id LIKE ? OR order_id LIKE ?)")
            args += [like] * 5
        kinds = [k for k in (kinds or []) if k]
        if kinds:
            where.append("kind IN (%s)" % ",".join("?" * len(kinds)))
            args += kinds
        for col, val in (("bot_id", bot_id), ("deployment_id", deployment_id), ("symbol", symbol), ("mode", mode),
                         ("correlation_id", correlation_id)):
            if val:
                where.append(f"{col} = ?")
                args.append(val)
        if severity and severity in SEVERITIES:
            sev = SEVERITIES[SEVERITIES.index(severity):]
            where.append("severity IN (%s)" % ",".join("?" * len(sev)))
            args += list(sev)
        if since:
            where.append("ts >= ?")
            args.append(int(since))
        if until:
            where.append("ts <= ?")
            args.append(int(until))
        if before_id:
            where.append("id < ?")
            args.append(int(before_id))
        q = "SELECT * FROM audit_events" + (" WHERE " + " AND ".join(where) if where else "") + " ORDER BY id DESC LIMIT ?"
        args.append(max(1, min(int(limit), 5000)))
        return [self._audit_row(r) for r in self.query(q, tuple(args))]

    def lifecycle(self, correlation_id: str) -> List[dict]:
        """Every audit event of one decision, in order: signal -> risk -> order -> ack -> fills -> exit."""
        return [self._audit_row(r) for r in self.query(
            "SELECT * FROM audit_events WHERE correlation_id = ? ORDER BY id", (correlation_id,))]

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
                "equity": "time", "events": "time", "connection_snapshots": "ts"}
        out = {}
        for table, col in cols.items():
            cut = now_ms - d[table] * 86_400_000
            with self.wlock:
                c = self._conn()
                cur = c.execute(f"DELETE FROM {table} WHERE {col} < ?", (cut,))
                c.commit()
            out[table] = cur.rowcount
        short = ",".join("?" * len(AUDIT_SHORT_KINDS))
        with self.wlock:
            c = self._conn()
            n1 = c.execute(f"DELETE FROM audit_events WHERE kind IN ({short}) AND ts < ?",
                           (*AUDIT_SHORT_KINDS, now_ms - AUDIT_RETENTION_DAYS["short"] * 86_400_000)).rowcount
            n2 = c.execute("DELETE FROM audit_events WHERE ts < ?",
                           (now_ms - AUDIT_RETENTION_DAYS["long"] * 86_400_000,)).rowcount
            c.commit()
        out["audit_events"] = n1 + n2
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
