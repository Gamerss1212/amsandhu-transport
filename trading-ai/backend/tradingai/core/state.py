"""The app's explicit state machine (section 269).

Real money is reachable only through LIVE_LOCKED -> LIVE_ARMED -> LIVE_RUNNING: never one jump from paper. Stop states
(PAUSED, RECONCILIATION_REQUIRED, ERROR, SHUTTING_DOWN) are reachable from any running state. An impossible move raises
InvalidTransition and changes nothing.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from typing import Callable, Optional

BOOTING, READY, RESEARCHING = "BOOTING", "READY", "RESEARCHING"
PAPER_RUNNING, SHADOW_RUNNING = "PAPER_RUNNING", "SHADOW_RUNNING"
LIVE_LOCKED, LIVE_ARMED, LIVE_RUNNING = "LIVE_LOCKED", "LIVE_ARMED", "LIVE_RUNNING"
PAUSED, RECONCILIATION_REQUIRED, ERROR, SHUTTING_DOWN = "PAUSED", "RECONCILIATION_REQUIRED", "ERROR", "SHUTTING_DOWN"

STATES = (BOOTING, READY, RESEARCHING, PAPER_RUNNING, SHADOW_RUNNING, LIVE_LOCKED, LIVE_ARMED, LIVE_RUNNING, PAUSED,
          RECONCILIATION_REQUIRED, ERROR, SHUTTING_DOWN)
_STOPS = frozenset({PAUSED, RECONCILIATION_REQUIRED, ERROR, SHUTTING_DOWN})
TRANSITIONS: dict[str, frozenset[str]] = {
    BOOTING: frozenset({READY, ERROR, SHUTTING_DOWN, RECONCILIATION_REQUIRED}),
    READY: frozenset({RESEARCHING, PAPER_RUNNING, SHADOW_RUNNING, LIVE_LOCKED}) | _STOPS,
    RESEARCHING: frozenset({READY, PAPER_RUNNING, SHADOW_RUNNING}) | _STOPS,
    PAPER_RUNNING: frozenset({READY, SHADOW_RUNNING, LIVE_LOCKED}) | _STOPS,
    SHADOW_RUNNING: frozenset({READY, PAPER_RUNNING, LIVE_LOCKED}) | _STOPS,
    LIVE_LOCKED: frozenset({READY, PAPER_RUNNING, LIVE_ARMED}) | _STOPS,
    LIVE_ARMED: frozenset({READY, LIVE_LOCKED, LIVE_RUNNING}) | _STOPS,
    LIVE_RUNNING: frozenset({LIVE_ARMED, LIVE_LOCKED}) | _STOPS,
    PAUSED: frozenset({READY, PAPER_RUNNING, SHADOW_RUNNING, LIVE_LOCKED}) | (_STOPS - {PAUSED}),
    RECONCILIATION_REQUIRED: frozenset({READY, PAUSED, ERROR, SHUTTING_DOWN}),
    ERROR: frozenset({READY, SHUTTING_DOWN}),
    SHUTTING_DOWN: frozenset(),
}
TRADING = frozenset({PAPER_RUNNING, SHADOW_RUNNING, LIVE_RUNNING})


class InvalidTransition(ValueError):
    pass


class StateMachine:
    def __init__(self, initial: str = BOOTING, on_change: Optional[Callable[[str, str, str], None]] = None):
        if initial not in STATES:
            raise ValueError(initial)
        self._lock = threading.Lock()
        self.state = initial
        self.since = time.time()
        self.history: deque = deque(maxlen=100)
        self.on_change = on_change

    def can(self, new: str) -> bool:
        return new in TRANSITIONS.get(self.state, frozenset())

    def to(self, new: str, reason: str) -> str:
        if new not in STATES:
            raise InvalidTransition(f"unknown state {new!r}")
        with self._lock:
            if new == self.state:
                return new
            if new not in TRANSITIONS[self.state]:
                raise InvalidTransition(f"{self.state} -> {new} is not allowed")
            old, self.state, self.since = self.state, new, time.time()
            self.history.append({"ts": int(self.since * 1000), "from": old, "to": new, "reason": reason[:300]})
        if self.on_change:
            self.on_change(old, new, reason)
        return old

    def view(self) -> dict:
        return {"state": self.state, "since": int(self.since * 1000), "trading": self.state in TRADING,
                "history": list(self.history)[-15:]}
