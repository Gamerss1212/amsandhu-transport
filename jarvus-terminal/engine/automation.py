#!/usr/bin/env python3
"""Automation: scans on a schedule, alert rules, and the background grader.

What is automated here is the *watching*, not the trading. The app will scan every
market continuously, tell you the moment a condition you defined comes true, mark
open paper positions to market and close them at their stops, and grade its own past
predictions when their horizon passes — all without anyone present.

What it will not do is send an order. See engine/portfolio.py for why that line is
where it is.
"""

from __future__ import annotations

import json
import threading
import time
import traceback
from typing import Callable, Dict, List, Optional

import config
from engine import learn, portfolio, store

SCHEMA = """
CREATE TABLE IF NOT EXISTS alert_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    symbol TEXT,                       -- NULL means any market
    min_heat REAL, gate_label TEXT,
    min_consensus REAL, min_families INTEGER,
    verdict TEXT,                      -- e.g. 'BUY'
    max_cost_r REAL,
    min_volume_usd REAL,
    cooldown_min INTEGER NOT NULL DEFAULT 60,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_id INTEGER, rule_name TEXT,
    fired_at TEXT NOT NULL,
    symbol TEXT NOT NULL, price REAL,
    heat REAL, gate_label TEXT, consensus REAL, verdict TEXT,
    detail TEXT, seen INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_alerts_time ON alerts(fired_at DESC);
"""


def _init():
    c = store.conn()
    c.executescript(SCHEMA)
    c.commit()


# --- rules -------------------------------------------------------------------

def add_rule(**kw) -> int:
    _init()
    cols = ("name", "symbol", "min_heat", "gate_label", "min_consensus", "min_families",
            "verdict", "max_cost_r", "min_volume_usd", "cooldown_min")
    c = store.conn()
    cur = c.execute(
        f"INSERT INTO alert_rules({','.join(cols)}, created_at) "
        f"VALUES({','.join('?' * len(cols))}, ?)",
        tuple(kw.get(k) for k in cols) + (store.now_iso(),))
    c.commit()
    return cur.lastrowid


def rules(enabled_only: bool = False) -> List[Dict]:
    _init()
    q = "SELECT * FROM alert_rules" + (" WHERE enabled=1" if enabled_only else "") + " ORDER BY id"
    return [dict(r) for r in store.conn().execute(q).fetchall()]


def set_rule_enabled(rule_id: int, enabled: bool) -> None:
    _init()
    c = store.conn()
    c.execute("UPDATE alert_rules SET enabled=? WHERE id=?", (1 if enabled else 0, rule_id))
    c.commit()


def delete_rule(rule_id: int) -> None:
    _init()
    c = store.conn()
    c.execute("DELETE FROM alert_rules WHERE id=?", (rule_id,))
    c.commit()


def seed_default_rules() -> int:
    """A few rules worth having on day one, if none exist yet."""
    _init()
    if rules():
        return 0
    add_rule(name="A big move is brewing", min_heat=0.7, cooldown_min=90,
             min_volume_usd=config.MIN_USD_VOLUME_24H * 3)
    add_rule(name="Coiled and ready", gate_label="COILED", min_heat=0.45, cooldown_min=120)
    add_rule(name="A plan that passed every gate", verdict="BUY", min_consensus=0.35,
             min_families=3, max_cost_r=0.2, cooldown_min=60)
    return 3


# --- matching ----------------------------------------------------------------

def _recently_fired(rule_id: int, symbol: str, cooldown_min: int) -> bool:
    row = store.conn().execute(
        "SELECT fired_at FROM alerts WHERE rule_id=? AND symbol=? ORDER BY id DESC LIMIT 1",
        (rule_id, symbol)).fetchone()
    if not row:
        return False
    age = (store.parse_iso(store.now_iso()) - store.parse_iso(row["fired_at"])).total_seconds()
    return age < cooldown_min * 60


def check(scan: Dict, swarm_by_symbol: Dict = None) -> List[Dict]:
    """Test every enabled rule against a finished scan and record what fired.

    Cooldowns matter more than they look: without them a market sitting just over a
    threshold fires on every scan, and an alert stream that cries constantly is one
    you stop reading, which is worse than having no alerts.
    """
    _init()
    swarm_by_symbol = swarm_by_symbol or {}
    fired: List[Dict] = []
    c = store.conn()

    for rule in rules(enabled_only=True):
        for m in scan.get("markets", []):
            if m.get("error"):
                continue
            gate, sig = m.get("gate") or {}, m.get("signal") or {}
            sw = swarm_by_symbol.get(m["symbol"]) or {}

            if rule["symbol"] and rule["symbol"] not in (m["symbol"], m.get("base")):
                continue
            if rule["min_heat"] is not None and (gate.get("blow_score") or 0) < rule["min_heat"]:
                continue
            if rule["gate_label"] and gate.get("label") != rule["gate_label"]:
                continue
            if rule["verdict"] and sig.get("verdict") != rule["verdict"]:
                continue
            if rule["min_consensus"] is not None and (sw.get("consensus") or 0) < rule["min_consensus"]:
                continue
            if rule["min_families"] is not None and (sw.get("families_agreeing") or 0) < rule["min_families"]:
                continue
            conf = sig.get("confluence") or {}
            if rule["max_cost_r"] is not None and (conf.get("cost_r") or 9) > rule["max_cost_r"]:
                continue
            if rule["min_volume_usd"] is not None and (m.get("usd_volume_24h") or 0) < rule["min_volume_usd"]:
                continue
            if _recently_fired(rule["id"], m["symbol"], rule["cooldown_min"]):
                continue

            detail = "; ".join(filter(None, [
                gate.get("explain"),
                f"{sw.get('agents_fired')} of {sw.get('agents_run')} strategies agree "
                f"across {sw.get('families_agreeing')} families" if sw else None,
                f"verdict {sig.get('verdict')}" if sig.get("verdict") else None,
            ]))[:600]
            cur = c.execute(
                "INSERT INTO alerts(rule_id, rule_name, fired_at, symbol, price, heat, gate_label, "
                "consensus, verdict, detail) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (rule["id"], rule["name"], store.now_iso(), m["symbol"], m.get("price"),
                 gate.get("blow_score"), gate.get("label"), sw.get("consensus"),
                 sig.get("verdict"), detail))
            fired.append({"id": cur.lastrowid, "rule": rule["name"], "symbol": m["symbol"],
                          "detail": detail})
    c.commit()
    return fired


def recent_alerts(limit: int = 80, unseen_only: bool = False) -> List[Dict]:
    _init()
    q = "SELECT * FROM alerts" + (" WHERE seen=0" if unseen_only else "") + " ORDER BY id DESC LIMIT ?"
    return [dict(r) for r in store.conn().execute(q, (limit,)).fetchall()]


def mark_seen(ids: List[int] = None) -> int:
    _init()
    c = store.conn()
    if ids:
        c.executemany("UPDATE alerts SET seen=1 WHERE id=?", [(i,) for i in ids])
    else:
        c.execute("UPDATE alerts SET seen=1 WHERE seen=0")
    c.commit()
    return c.total_changes


# --- the scheduler -----------------------------------------------------------

class Scheduler:
    """One background thread that rescans, checks alerts, marks positions and grades.

    Deliberately a single thread on a plain interval rather than anything cleverer:
    a trading dashboard that quietly spawns work it cannot account for is how a free
    API ends up rate-limiting you mid-session.
    """

    def __init__(self, scan_fn: Callable, interval_s: int = 300):
        self.scan_fn = scan_fn
        self.interval_s = max(60, interval_s)
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self.last_run: Optional[str] = None
        self.last_error: Optional[str] = None
        self.runs = 0
        self.alerts_fired = 0
        self.enabled = False

    def start(self, interval_s: int = None):
        if interval_s:
            self.interval_s = max(60, interval_s)
        if self._thread and self._thread.is_alive():
            self.enabled = True
            return
        self._stop.clear()
        self.enabled = True
        self._thread = threading.Thread(target=self._loop, name="jarvus-scheduler", daemon=True)
        self._thread.start()

    def stop(self):
        self.enabled = False
        self._stop.set()

    def status(self) -> Dict:
        return {"enabled": self.enabled, "interval_s": self.interval_s, "runs": self.runs,
                "last_run": self.last_run, "last_error": self.last_error,
                "alerts_fired": self.alerts_fired,
                "alive": bool(self._thread and self._thread.is_alive())}

    def _loop(self):
        while not self._stop.is_set():
            if self.enabled:
                try:
                    scan, swarm_res = self.scan_fn()
                    fired = check(scan, (swarm_res or {}).get("by_symbol", {}))
                    self.alerts_fired += len(fired)

                    prices = {m["symbol"]: m["price"] for m in scan.get("markets", [])
                              if not m.get("error")}
                    for pf in portfolio.list_all():
                        portfolio.mark_to_market(pf["name"], prices)

                    learn.resolve_due(50)          # grade anything past its horizon
                    self.runs += 1
                    self.last_run = store.now_iso()
                    self.last_error = None
                except Exception:                  # noqa: BLE001 - a bad cycle must not end the loop
                    self.last_error = traceback.format_exc(limit=2).strip().splitlines()[-1]
            self._stop.wait(self.interval_s)


SCHEDULER: Optional[Scheduler] = None


def get_scheduler(scan_fn: Callable = None, interval_s: int = 300) -> Scheduler:
    global SCHEDULER
    if SCHEDULER is None and scan_fn is not None:
        SCHEDULER = Scheduler(scan_fn, interval_s)
    return SCHEDULER
