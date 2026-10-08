"""The app's state machine (master prompt section 269) and its start-up checks (section 120).

Two parts, both honest about where they come from:

* `Lifecycle`: the program's own life, driven by serve(): BOOTING -> READY -> SHUTTING_DOWN, or ERROR when a
  start-up check fails. Every move is checked against TRANSITIONS; an impossible one raises InvalidTransition and
  changes nothing.
* `trading_state(facts)`: what the owner's workspace is doing right now, read from facts the engines record (engine
  running, emergency stop, reconciliation breaks, live authorisation, running live deployments). It is never set by
  hand, so it cannot claim more than the engines did. Real money still needs the existing arming steps (the typed
  acknowledgement on Connections, then START LIVE for each bot); this module only names the state.

    m = Lifecycle(); m.to(READY, "start-up checks passed"); m.state -> "READY"
    trading_state({"engine_running": True}) -> "PAPER_RUNNING"
"""

from __future__ import annotations

import os
import sqlite3
import threading
import time
from collections import deque
from typing import Callable, Dict, FrozenSet, List, Optional

BOOTING = "BOOTING"
READY = "READY"
RESEARCHING = "RESEARCHING"
PAPER_RUNNING = "PAPER_RUNNING"
SHADOW_RUNNING = "SHADOW_RUNNING"
LIVE_LOCKED = "LIVE_LOCKED"
LIVE_ARMED = "LIVE_ARMED"
LIVE_RUNNING = "LIVE_RUNNING"
PAUSED = "PAUSED"
RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"
ERROR = "ERROR"
SHUTTING_DOWN = "SHUTTING_DOWN"

STATES = (BOOTING, READY, RESEARCHING, PAPER_RUNNING, SHADOW_RUNNING, LIVE_LOCKED, LIVE_ARMED, LIVE_RUNNING, PAUSED,
          RECONCILIATION_REQUIRED, ERROR, SHUTTING_DOWN)

_ANY_STOP = frozenset({PAUSED, ERROR, SHUTTING_DOWN, RECONCILIATION_REQUIRED})
# Real money is reached only through LIVE_LOCKED -> LIVE_ARMED -> LIVE_RUNNING: never one jump from paper.
TRANSITIONS: Dict[str, FrozenSet[str]] = {
    BOOTING: frozenset({READY, ERROR, SHUTTING_DOWN}),
    READY: frozenset({RESEARCHING, PAPER_RUNNING, SHADOW_RUNNING, LIVE_LOCKED}) | _ANY_STOP,
    RESEARCHING: frozenset({READY, PAPER_RUNNING}) | _ANY_STOP,
    PAPER_RUNNING: frozenset({READY, RESEARCHING, SHADOW_RUNNING, LIVE_LOCKED}) | _ANY_STOP,
    SHADOW_RUNNING: frozenset({READY, PAPER_RUNNING, LIVE_LOCKED}) | _ANY_STOP,
    LIVE_LOCKED: frozenset({READY, PAPER_RUNNING, LIVE_ARMED}) | _ANY_STOP,
    LIVE_ARMED: frozenset({LIVE_LOCKED, LIVE_RUNNING, PAPER_RUNNING}) | _ANY_STOP,
    LIVE_RUNNING: frozenset({LIVE_ARMED, LIVE_LOCKED}) | _ANY_STOP,
    PAUSED: frozenset({READY, PAPER_RUNNING, LIVE_LOCKED}) | (_ANY_STOP - {PAUSED}),
    RECONCILIATION_REQUIRED: frozenset({READY, PAUSED, LIVE_LOCKED, ERROR, SHUTTING_DOWN}),
    ERROR: frozenset({READY, SHUTTING_DOWN}),
    SHUTTING_DOWN: frozenset(),
}


class InvalidTransition(ValueError):
    pass


class Lifecycle:
    """A thread-safe state machine over STATES. Keeps the last 50 moves for /health."""

    def __init__(self, initial: str = BOOTING, clock: Callable[[], float] = time.time):
        if initial not in STATES:
            raise ValueError(f"unknown state {initial!r}")
        self._clock = clock
        self._lock = threading.Lock()
        self.state = initial
        self.since = clock()
        self.history: deque = deque(maxlen=50)

    def can(self, new: str) -> bool:
        return new in TRANSITIONS.get(self.state, frozenset())

    def to(self, new: str, reason: str) -> str:
        if new not in STATES:
            raise InvalidTransition(f"unknown state {new!r}")
        with self._lock:
            if new not in TRANSITIONS[self.state]:
                raise InvalidTransition(f"{self.state} -> {new} is not allowed")
            old, self.state, self.since = self.state, new, self._clock()
            self.history.append({"time": int(self.since * 1000), "from": old, "to": new, "reason": reason[:200]})
            return old

    def view(self) -> dict:
        return {"state": self.state, "since": int(self.since * 1000), "history": list(self.history)[-10:]}


def trading_state(facts: dict) -> str:
    """The workspace's trading state from recorded facts. Stop states win: a reconciliation break or an emergency stop
    is shown even while bots run."""
    if facts.get("reconciliation_problems"):
        return RECONCILIATION_REQUIRED
    if facts.get("emergency"):
        return PAUSED
    if not facts.get("engine_running"):
        return READY
    if facts.get("live_deployments_running", 0) > 0:
        return LIVE_RUNNING
    if facts.get("live_authorized"):
        return LIVE_ARMED
    return PAPER_RUNNING


def live_state(facts: dict) -> str:
    """LOCKED / ARMED / RUNNING: the real-money part of trading_state, shown on its own so it is never ambiguous."""
    if facts.get("live_deployments_running", 0) > 0 and facts.get("engine_running"):
        return "RUNNING"
    return "ARMED" if facts.get("live_authorized") else "LOCKED"


# ----------------------------------------------------------------------------- start-up checks (section 120)

def check(name: str, fn: Callable[[], str]) -> dict:
    """Run one start-up check: {"name", "ok", "detail", "ms"}. A check passes by returning its detail and fails by
    raising; nothing is assumed to pass."""
    t = time.perf_counter()
    try:
        detail, ok = fn(), True
    except Exception as e:                               # noqa: BLE001 - every failure is reported, none hidden
        detail, ok = f"{type(e).__name__}: {e}", False
    return {"name": name, "ok": ok, "detail": str(detail)[:300], "ms": round((time.perf_counter() - t) * 1000, 1)}


def sqlite_quick_check(path: str) -> str:
    """PRAGMA quick_check on an existing database, opened read-only. A missing file is created later by the app."""
    if not os.path.exists(path):
        return "not created yet (first start)"
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=10)
    try:
        res = con.execute("PRAGMA quick_check").fetchone()[0]
    finally:
        con.close()
    if res != "ok":
        raise RuntimeError(f"{os.path.basename(path)} failed its integrity check: {res}")
    return f"{os.path.basename(path)}: ok"


def summarize(checks: List[dict]) -> Optional[str]:
    """None when every check passed, else one line naming the failures."""
    bad = [c for c in checks if not c["ok"]]
    return None if not bad else "; ".join(f"{c['name']}: {c['detail']}" for c in bad)
