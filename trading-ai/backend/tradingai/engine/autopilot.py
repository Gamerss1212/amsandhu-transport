"""System loop: the on/off switch ("Start System" / "Stop") that drives the master system agent.

Since 1.5.0 the master agent (engine/master.py) does all of the work this module used to do itself:
* training and validating its 100 trading agents,
* promoting and rolling back their versions,
* running each agent's execution loop,
* enforcing per-agent loss limits.
This module keeps the switch, its saved settings and the activity feed shown on the pages. It runs paper only. It
never trades real money, changes a risk limit, re-arms a kill switch or writes trading code.
"""

from __future__ import annotations

import json
import threading
from collections import deque
from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING, Any, Optional

from tradingai.core import logs
from tradingai.storage.db import now_ms

if TYPE_CHECKING:
    from tradingai.app import App

log = logs.get("autopilot")
DAY = 86_400_000
# intraday operating mode (engine/daytrade.py): only bar sizes that can open and close inside one session are screened
MARKET_TFS = {"crypto": ("15m", "1h", "4h"), "stock": ("15m", "1h")}
LOOKBACK = {"15m": 2000, "1h": 5000, "4h": 3000, "1d": 2500}
DISCOVERED_RESEARCH = 12                 # discovered pairs screened: the most liquid few, not hundreds
MARKETS = ("crypto", "stock")


@dataclass
class APConfig:
    enabled: bool = True
    max_bots: int = 6
    markets: list = field(default_factory=lambda: list(MARKETS))
    allow_probation: bool = False        # fixed off: the owner's rules allow no unverified fallback (revision 12/13)
    screens_per_hour: int = 60
    confirms_per_hour: int = 12
    risk_profile: str = "conservative"


class Autopilot:
    def __init__(self, app: "App"):
        self.app = app
        saved = app.db.get_setting("autopilot", {}) or {}
        known = APConfig.__dataclass_fields__
        self.cfg = APConfig(**{k: v for k, v in (saved.get("config") or {}).items() if k in known})
        self.cfg.allow_probation = False                    # an older saved setting cannot turn it back on
        self.mem: dict[str, Any] = {"retired": {}, "cursor": {}, "slot_cursor": 0, "unavailable": {},
                                    "screened": 0, "confirmed": 0, "deployed": 0, "retired_count": 0}
        self.mem.update({k: v for k, v in (saved.get("memory") or {}).items() if k in self.mem})
        self.jobs: dict[str, dict] = {}                   # job id -> {"kind", "key", ...} for jobs this run started
        self.activity: deque = deque(maxlen=60)
        self.doing = "starting"
        self.last_cycle: Optional[int] = None
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._rate: dict[str, list[float]] = {"screen": [], "confirm": []}

    # ------------------------------------------------------------------ lifecycle
    def start(self) -> None:
        if self._thread is None:
            self._thread = threading.Thread(target=self._loop, name="autopilot", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._save()

    def _loop(self) -> None:
        self._stop.wait(5)                                 # let the trading loop and the page come up first
        while not self._stop.is_set():
            try:
                self.cycle()
            except Exception as e:                         # noqa: BLE001 - the autopilot survives; the error is shown
                log.error(f"autopilot cycle error: {type(e).__name__}: {e}")
                self._note(f"error: {type(e).__name__}: {e}", "error")
            self._stop.wait(10)

    def _save(self) -> None:
        self.app.db.set_setting("autopilot", {"config": asdict(self.cfg), "memory": self.mem})

    def _note(self, msg: str, severity: str = "info", **data) -> None:
        ev = {"ts": now_ms(), "message": msg, **data}
        self.activity.appendleft(ev)
        self.app.bus.publish("autopilot", ev, severity=severity)

    def _counts(self) -> dict:
        m = self.app.fleet.history() if hasattr(self.app, "fleet") else {}
        c = self.app.fleet.counts() if hasattr(self.app, "fleet") else {}
        return {"screened": m.get("trained_runs", 0), "confirmed": c.get("validated", 0),
                "deployed": m.get("promoted", 0), "retired_count": m.get("rolled_back", 0),
                "trained_runs": m.get("trained_runs", 0), "validated_agents": c.get("validated", 0),
                "promoted": m.get("promoted", 0), "rolled_back": m.get("rolled_back", 0),
                "rejected_versions": m.get("rejected", 0), "shadow_versions": m.get("shadow", 0)}

    # ------------------------------------------------------------------ owner controls
    def configure(self, changes: dict) -> dict:
        with self._lock:
            if "enabled" in changes:
                self.cfg.enabled = bool(changes["enabled"])
            if "max_bots" in changes:
                self.cfg.max_bots = max(0, min(20, int(changes["max_bots"])))
            if "markets" in changes:
                self.cfg.markets = [m for m in changes["markets"] if m in MARKETS]
            self._save()
        self.app.audit("autopilot", f"autopilot settings changed: {changes}", data=asdict(self.cfg))
        if "enabled" in changes:
            self._note("AUTOPILOT ON" if self.cfg.enabled else "AUTOPILOT OFF: its bots were stopped")
        else:
            self._note("autopilot settings changed")
        if changes.get("enabled") is False:
            for b in self.bots():
                if b.state == "running":
                    self.app.bot_action(b.bot_id, "stop", by="autopilot")
        return self.view()

    def bots(self) -> list:
        return [b for b in self.app.bots.values() if getattr(b, "managed_by", "owner") in ("master", "autopilot")]

    def view(self) -> dict:
        bots = self.bots()
        return {"config": asdict(self.cfg), "doing": self.doing if self.cfg.enabled else "off",
                "last_cycle": self.last_cycle, "bots": [b.as_dict() for b in bots],
                "running": sum(1 for b in bots if b.state == "running"),
                "counts": self._counts(),
                "candidates": self.candidates()[:10],
                "activity": list(self.app.fleet.activity)[:25] if hasattr(self.app, "fleet") else list(self.activity)[:25],
                "rules": "paper only; never live; chooses among fixed strategy templates; risk limits unchanged"}

    # ------------------------------------------------------------------ one cycle
    def cycle(self) -> dict:
        app = self.app
        with self._lock:
            self.last_cycle = now_ms()
            if not self.cfg.enabled:
                self.doing = "off"
                return {"skipped": "off"}
            if app.state.state in ("ERROR", "SHUTTING_DOWN", "BOOTING"):
                return {"skipped": app.state.state}
            if app.mode == "live":
                self.doing = "paused: the system is in LIVE mode (the master runs paper only)"
                return {"skipped": "live"}
            out = app.fleet.operate()
            self.doing = app.fleet.doing
            self._save()
            return out

    def candidates(self) -> list[dict]:
        """Validated versions that may trade (paper), as the pages list them."""
        rows = self.app.db.query(
            "SELECT v.agent_id, v.version, v.strategy_id, v.tf, v.experiment_id, json_extract(v.training, '$.quality') "
            "AS quality, json_extract(v.training, '$.dataset.instrument') AS iid FROM agent_versions v "
            "WHERE v.status='active' ORDER BY v.agent_id")
        return [{"key": f"{r['strategy_id']}|{r['iid']}|{r['tf']}", "strategy_id": r["strategy_id"], "iid": r["iid"],
                 "tf": r["tf"], "tier": "qualified", "quality": r["quality"], "verdict": "PAPER TEST",
                 "agent": r["agent_id"], "version": r["version"], "experiment_id": r["experiment_id"]} for r in rows]

    @staticmethod
    def _key(sid: str, iid: str, tf: str) -> str:
        return f"{sid}|{iid}|{tf}"

    def _clear_unavailable(self) -> None:
        self.mem["unavailable"] = {}

    def export(self) -> str:
        return json.dumps(self.view(), default=str)
