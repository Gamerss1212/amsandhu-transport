"""What the voice assistant (JARVIS) may ask this program to do.

The rule that decides everything here: an action that REDUCES risk may run at once; an action that INCREASES activity or
changes the account waits for the owner's click in the dashboard. Nothing else exists for JARVIS: no order, no limit, no
live trading, no broker or credential, no emergency-stop re-arm, no code change. Those are not "refused by a prompt";
the actions simply are not in the two tables below, and the risk service stays the final judge of every order.

Text that reaches JARVIS from the internet cannot change this: it can at most make JARVIS ask for one of these actions,
and the actions that matter still wait for a person.
"""

from __future__ import annotations

import re
import threading
import time
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from tradingai.app import App

# run at once: each one makes the system do LESS
IMMEDIATE = {
    "pause_entries": "stop opening new positions (open ones are managed as before)",
    "stop_system": "switch the automatic system off (Stop)",
    "stop_thermal_check": "stop the temperature test",
}
# wait for the owner's approval: each one makes the system do MORE or changes the account
APPROVAL = {
    "resume_entries": "allow new positions again",
    "start_system": "switch the automatic system on (Start System, paper trading)",
    "run_thermal_check": "run the temperature test (full CPU load for 1 to 10 minutes)",
    "set_paper_balance": "set the paper account balance",
}
EXPIRES_S = 15 * 60
MAX_PENDING = 10
_CLEAN = re.compile(r"[^\w .,:;!?'()/%$+\-]")


def _clean(text: str, n: int = 200) -> str:
    return _CLEAN.sub("", str(text or ""))[:n].strip()


class JarvisCommands:
    def __init__(self, app: "App"):
        self.app = app
        self.pending: dict[str, dict] = {}
        self.history: list[dict] = []
        self._lock = threading.RLock()
        self._n = 0

    # ---------------------------------------------------------------- JARVIS side
    def submit(self, action: str, reason: str = "", minutes: Optional[float] = None,
               amount: Optional[Decimal] = None) -> dict:
        if action not in IMMEDIATE and action not in APPROVAL:
            raise PermissionError(f"JARVIS may not do '{action[:40]}'. It can read the system and ask only for: " +
                                  ", ".join(sorted(set(IMMEDIATE) | set(APPROVAL))))
        args = self._args(action, minutes, amount)
        reason = _clean(reason)
        if action in IMMEDIATE:
            out = self._execute(action, args)
            self._record("done", action, args, reason, out)
            return {"status": "done", "action": action, "result": out}
        with self._lock:
            self._expire()
            if len(self.pending) >= MAX_PENDING:
                raise PermissionError("too many requests are waiting for the owner")
            for k in [k for k, v in self.pending.items() if v["action"] == action]:
                del self.pending[k]                                   # a newer request replaces an older one
            self._n += 1
            cid = f"J{int(time.time())}-{self._n}"
            self.pending[cid] = {"id": cid, "action": action, "what": APPROVAL[action], "args": args,
                                 "reason": reason, "ts": int(time.time() * 1000)}
        self.app.audit("jarvis", f"JARVIS asks to: {APPROVAL[action]} ({reason or 'no reason given'}); waiting for the owner")
        self.app.bus.publish("jarvis", {"id": cid, "action": action, "message": f"JARVIS asks: {APPROVAL[action]}"},
                             severity="warning")
        return {"status": "waiting_for_owner", "id": cid, "action": action,
                "note": "the owner must approve this in the Trading AI window; it has not happened yet"}

    @staticmethod
    def _args(action: str, minutes: Optional[float], amount: Optional[Decimal]) -> dict:
        if action == "run_thermal_check":
            m = 5.0 if minutes is None else float(minutes)
            if not 1 <= m <= 10:
                raise ValueError("the temperature test runs 1 to 10 minutes")
            return {"minutes": m}
        if action == "set_paper_balance":
            try:
                a = Decimal(str(amount))
            except (InvalidOperation, TypeError):
                raise ValueError("set_paper_balance needs an amount") from None
            if not Decimal(1) <= a <= Decimal("1000000000"):
                raise ValueError("the paper balance must be between 1 and 1,000,000,000")
            return {"amount": str(a)}
        return {}

    # ---------------------------------------------------------------- owner side (full session token only)
    def approve(self, cid: str) -> dict:
        with self._lock:
            self._expire()
            item = self.pending.pop(cid, None)
        if item is None:
            raise KeyError(cid)
        out = self._execute(item["action"], item["args"])
        self._record("approved", item["action"], item["args"], item["reason"], out)
        return {"status": "done", "action": item["action"], "result": out}

    def reject(self, cid: str) -> dict:
        with self._lock:
            item = self.pending.pop(cid, None)
        if item is None:
            raise KeyError(cid)
        self._record("rejected", item["action"], item["args"], item["reason"], None)
        return {"status": "rejected", "action": item["action"]}

    def view(self) -> dict:
        with self._lock:
            self._expire()
            return {"pending": sorted(self.pending.values(), key=lambda p: p["ts"]), "recent": self.history[-10:],
                    "immediate": IMMEDIATE, "needs_approval": APPROVAL,
                    "never": "orders, risk limits, live trading, brokers, credentials, the emergency stop and code changes"}

    # ---------------------------------------------------------------- internals
    def _expire(self) -> None:
        now = int(time.time() * 1000)
        for k in [k for k, v in self.pending.items() if now - v["ts"] > EXPIRES_S * 1000]:
            del self.pending[k]

    def _record(self, how: str, action: str, args: dict, reason: str, out) -> None:
        self.history.append({"ts": int(time.time() * 1000), "how": how, "action": action, "reason": reason})
        self.app.audit("jarvis", f"JARVIS action {action}: {how}" + (f" ({reason})" if reason else ""),
                       data={"args": args})

    def _execute(self, action: str, args: dict):
        app = self.app
        if action == "pause_entries":
            return app.pause_entries(True, "jarvis", "asked by JARVIS")
        if action == "resume_entries":
            if app.risk.kill_switch:
                raise PermissionError("STOP ALL TRADING is engaged: re-arm trading first (a person types the phrase)")
            return app.pause_entries(False, "owner (approved JARVIS request)", "")
        if action == "stop_system":
            return app.autopilot.configure({"enabled": False})
        if action == "start_system":
            if app.risk.kill_switch:
                raise PermissionError("STOP ALL TRADING is engaged: re-arm trading first")
            return app.autopilot.configure({"enabled": True})
        if action == "stop_thermal_check":
            return {"check": app.hardware.stop_check()["check"]["state"]}
        if action == "run_thermal_check":
            return {"check": app.hardware.start_check(args["minutes"])["check"]["state"]}
        if action == "set_paper_balance":
            return app.set_paper_balance(Decimal(args["amount"]))
        raise PermissionError(action)
