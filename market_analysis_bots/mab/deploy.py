"""Deployments: a bot the owner started, in one mode, on one account, with its own capital and risk limits.

States
    stopped             not trading (the bot still evaluates its rules, so its signals stay visible)
    running             entries allowed; positions managed
    paused              PAUSE NEW ENTRIES: no new entries; open positions keep being managed (stops, targets,
                        exit rules)
    stopped_retaining   STOP with "retain protective orders": the strategy no longer acts; the position stays
                        open with its protective stop (on the provider for broker accounts, watched on completed
                        bars for simulated ones) until it fills or the owner closes it
    error               stopped by a fault that needs the owner (a protective stop that could not be placed,
                        an exit that did not complete, a reconciliation mismatch)

Controls and what they do
    START               readiness checks first; starts only this bot in its chosen mode; live needs the
                        owner's separate live authorisation and an explicit confirmation of account, strategy,
                        allocation and limits
    PAUSE NEW ENTRIES   blocks entries at once; positions keep being managed
    STOP                blocks entries at once and cancels working entry orders; then either keeps the
                        protective orders (retain) or closes the position (close), and reports what happened
    EMERGENCY STOP      (the whole workspace) blocks every new entry at once and tries to cancel every working
                        entry order; closing positions is a separate, separately confirmed action; every
                        failure or unfilled order is reported, never hidden

Limits are enforced in the order path by the fleet (mab.runtime), after the brain and before any order: the
brain or the research assistant can make a trade smaller or refuse it, never larger than these limits.
"""

from __future__ import annotations

import json
import secrets
import time
from typing import Dict, List, Optional

STATES = ("stopped", "running", "paused", "stopped_retaining", "error")
ACTIVE = ("running", "paused", "stopped_retaining", "error")
MODES = ("demo", "paper", "live")
DEFAULT_LIMITS = {
    "risk_per_trade_pct": None,          # None: the strategy's own sizing (a % of the deployment's equity)
    "max_position_pct": 100.0,           # one position's value as % of the deployment's equity
    "max_order_notional": None,          # hard cap per order, in the account's currency
    "daily_loss_limit_pct": 3.0,         # of the allocation: entries stop for the rest of the UTC day
    "max_drawdown_pct": 15.0,            # from the deployment's equity peak: the deployment stops entering
    "max_orders_per_minute": 4,
}
LIMIT_BOUNDS = {"risk_per_trade_pct": (0.01, 5.0), "max_position_pct": (1.0, 100.0), "max_order_notional": (1.0, 1e9),
                "daily_loss_limit_pct": (0.1, 50.0), "max_drawdown_pct": (1.0, 90.0), "max_orders_per_minute": (1, 60)}


def now_ms() -> int:
    return int(time.time() * 1000)


def validate_limits(limits: Optional[dict]) -> dict:
    out = dict(DEFAULT_LIMITS)
    for k, v in (limits or {}).items():
        if k not in DEFAULT_LIMITS:
            raise ValueError(f"unknown risk limit {k!r}")
        if v in (None, ""):
            out[k] = None if DEFAULT_LIMITS[k] is None else DEFAULT_LIMITS[k]
            continue
        try:
            x = float(v)
        except (TypeError, ValueError):
            raise ValueError(f"{k.replace('_', ' ')} must be a number")
        lo, hi = LIMIT_BOUNDS[k]
        if not lo <= x <= hi:
            raise ValueError(f"{k.replace('_', ' ')} must be between {lo:g} and {hi:g}")
        out[k] = int(x) if k == "max_orders_per_minute" else x
    return out


class Deployments:
    def __init__(self, storage):
        self.st = storage

    # ------------------------------------------------------------------ user bots
    def create_bot(self, strategy_id: str, venue: str, instrument: str, params: Optional[dict] = None,
                   name: str = None, source_bot: str = None) -> dict:
        bid = "U-" + secrets.token_hex(3).upper()
        self.st.write("INSERT INTO user_bots (bot_id, name, strategy_id, venue, instrument, params, source_bot, created)"
                      " VALUES (?,?,?,?,?,?,?,?)", (bid, name or f"{strategy_id} on {instrument}", strategy_id, venue,
                                                   instrument, json.dumps(params or {}), source_bot, now_ms()))
        return self.bot(bid)

    def bot(self, bot_id: str) -> Optional[dict]:
        r = self.st.query("SELECT * FROM user_bots WHERE bot_id=?", (bot_id,))
        if not r:
            return None
        d = dict(r[0])
        d["params"] = json.loads(d["params"] or "{}")
        return d

    def bots(self, include_archived: bool = False) -> List[dict]:
        rows = self.st.query("SELECT * FROM user_bots" + ("" if include_archived else " WHERE archived=0") + " ORDER BY created")
        for d in rows:
            d["params"] = json.loads(d["params"] or "{}")
        return rows

    def bot_configs(self) -> List[dict]:
        """Fleet bot configurations for the owner's bots (same shape as the registry file)."""
        return [{"bot_id": b["bot_id"], "name": b["name"], "strategy_id": b["strategy_id"], "venue": b["venue"],
                 "instrument": b["instrument"], "params": b["params"], "enabled": True, "user": True}
                for b in self.bots()]

    def archive_bot(self, bot_id: str):
        if self.active_for(bot_id):
            raise ValueError("stop this bot's deployment first")
        self.st.write("UPDATE user_bots SET archived=1 WHERE bot_id=?", (bot_id,))

    # ------------------------------------------------------------------ deployments
    @staticmethod
    def _row(r: dict) -> dict:
        d = dict(r)
        for k in ("limits", "readiness", "confirmation"):
            try:
                d[k] = json.loads(d[k]) if d.get(k) else None
            except ValueError:
                d[k] = None
        return d

    def get(self, dep_id: str) -> Optional[dict]:
        r = self.st.query("SELECT * FROM deployments WHERE deployment_id=?", (dep_id,))
        return self._row(r[0]) if r else None

    def list(self, active_only: bool = False) -> List[dict]:
        q = "SELECT * FROM deployments"
        if active_only:
            q += " WHERE state IN (%s)" % ",".join("?" * len(ACTIVE))
            return [self._row(r) for r in self.st.query(q + " ORDER BY created", ACTIVE)]
        return [self._row(r) for r in self.st.query(q + " ORDER BY created")]

    def active_for(self, bot_id: str) -> Optional[dict]:
        r = self.st.query("SELECT * FROM deployments WHERE bot_id=? AND state IN (%s) ORDER BY created DESC LIMIT 1"
                          % ",".join("?" * len(ACTIVE)), (bot_id, *ACTIVE))
        return self._row(r[0]) if r else None

    def latest_for(self, bot_id: str) -> Optional[dict]:
        r = self.st.query("SELECT * FROM deployments WHERE bot_id=? ORDER BY created DESC LIMIT 1", (bot_id,))
        return self._row(r[0]) if r else None

    def create(self, bot_id: str, mode: str, connection_id: str, allocation: float, currency: str,
               limits: Optional[dict], strategy_version: str = None, config_version: str = None) -> dict:
        if mode not in MODES:
            raise ValueError(f"mode must be one of {', '.join(MODES)}")
        if self.active_for(bot_id):
            raise ValueError("this bot already has an active deployment; stop it first")
        try:
            allocation = float(allocation)
        except (TypeError, ValueError):
            raise ValueError("allocation must be a number")
        if not allocation > 0:
            raise ValueError("allocate more than zero")
        lim = validate_limits(limits)
        dep_id = "D-" + secrets.token_hex(4).upper()
        t = now_ms()
        self.st.write("INSERT INTO deployments (deployment_id, bot_id, mode, connection_id, state, allocation, currency, limits,"
                      " strategy_version, config_version, created, updated) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                      (dep_id, bot_id, mode, connection_id, "stopped", allocation, currency, json.dumps(lim),
                       strategy_version, config_version, t, t))
        return self.get(dep_id)

    def update(self, dep_id: str, **fields) -> dict:
        for k in ("limits", "readiness", "confirmation"):
            if k in fields and not isinstance(fields[k], str):
                fields[k] = json.dumps(fields[k], default=str)
        fields["updated"] = now_ms()
        cols = ", ".join(f"{k}=?" for k in fields)
        self.st.write(f"UPDATE deployments SET {cols} WHERE deployment_id=?", (*fields.values(), dep_id))
        return self.get(dep_id)

    def set_state(self, dep_id: str, state: str, reason: str = "", actor: str = "owner") -> dict:
        if state not in STATES:
            raise ValueError(f"unknown state {state}")
        old = self.get(dep_id)
        f = {"state": state}
        if state == "running" and old["state"] != "paused":
            f["started"] = now_ms()
        if state in ("stopped", "stopped_retaining", "error"):
            f["stopped"] = now_ms()
            f["stop_reason"] = reason or None
        dep = self.update(dep_id, **f)
        self.st.audit("control", f"{dep['bot_id']} [{dep['mode'].upper()}]: {old['state']} -> {state}"
                      + (f" ({reason})" if reason else ""), stage="deployment_state",
                      severity="warning" if state in ("error", "stopped_retaining") else "info", mode=dep["mode"],
                      bot_id=dep["bot_id"], deployment_id=dep_id, connection_id=dep["connection_id"],
                      payload={"from": old["state"], "to": state, "reason": reason, "by": actor})
        return dep

    # ------------------------------------------------------------------ money
    def realized(self, dep_id: str, since: Optional[int] = None) -> float:
        q = "SELECT COALESCE(SUM(pnl), 0) AS s FROM trades WHERE deployment_id=?"
        a: list = [dep_id]
        if since is not None:
            q += " AND exit_time >= ?"
            a.append(since)
        return float(self.st.query(q, tuple(a))[0]["s"] or 0.0)

    def allocated(self, connection_id: str, exclude: Optional[str] = None) -> float:
        rows = self.st.query("SELECT deployment_id, allocation FROM deployments WHERE connection_id=? AND state IN (%s)"
                             % ",".join("?" * len(ACTIVE)), (connection_id, *ACTIVE))
        return sum(r["allocation"] for r in rows if r["deployment_id"] != exclude)


class Checks:
    """Readiness report builder: every check has a status (pass, warn, fail, waived, skip) and a reason."""

    def __init__(self):
        self.items: List[dict] = []

    def add(self, cid: str, label: str, ok, detail: str = "", required: bool = True, warn: bool = False,
            waived: bool = False) -> bool:
        if ok is None:
            status = "skip"
        elif ok:
            status = "pass"
        elif waived:
            status = "waived"
        elif warn or not required:
            status = "warn"
        else:
            status = "fail"
        self.items.append({"id": cid, "label": label, "status": status, "detail": detail, "required": required})
        return bool(ok)

    @property
    def ok(self) -> bool:
        return not any(x["status"] == "fail" for x in self.items)

    def report(self) -> dict:
        return {"ok": self.ok, "time": now_ms(), "checks": self.items,
                "failed": [x["label"] + (f": {x['detail']}" if x["detail"] else "") for x in self.items if x["status"] == "fail"]}
