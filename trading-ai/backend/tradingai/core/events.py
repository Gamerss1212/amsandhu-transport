"""In-process event bus: the engines publish, the WebSocket endpoint streams to the browser.

Thread-safe (engines run in threads; the web server in asyncio). Each subscriber gets its own bounded queue; a slow
browser tab drops its oldest events instead of slowing trading down. Every event has a monotonically increasing id so
a reconnecting page can ask for what it missed (`since`)."""

from __future__ import annotations

import itertools
import threading
import time
from collections import deque
from typing import Any, Optional


class EventBus:
    def __init__(self, history: int = 2000, queue_size: int = 1000):
        self._lock = threading.Lock()
        self._seq = itertools.count(1)
        self._history: deque = deque(maxlen=history)
        self._subs: dict[int, deque] = {}
        self._sub_ids = itertools.count(1)
        self._queue_size = queue_size
        self._cond = threading.Condition(self._lock)

    def publish(self, topic: str, data: Any, *, severity: str = "info", correlation_id: Optional[str] = None) -> dict:
        with self._cond:
            ev = {"id": next(self._seq), "ts": int(time.time() * 1000), "topic": topic, "severity": severity,
                  "correlation_id": correlation_id, "data": data}
            self._history.append(ev)
            for q in self._subs.values():
                q.append(ev)
            self._cond.notify_all()
            return ev

    def subscribe(self) -> int:
        with self._lock:
            sid = next(self._sub_ids)
            self._subs[sid] = deque(maxlen=self._queue_size)
            return sid

    def unsubscribe(self, sid: int) -> None:
        with self._lock:
            self._subs.pop(sid, None)

    def drain(self, sid: int, timeout: float = 0.0) -> list[dict]:
        with self._cond:
            q = self._subs.get(sid)
            if q is None:
                return []
            if not q and timeout > 0:
                self._cond.wait(timeout)
            out = list(q)
            q.clear()
            return out

    def since(self, last_id: int, topics: Optional[set[str]] = None, limit: int = 500) -> list[dict]:
        with self._lock:
            evs = [e for e in self._history if e["id"] > last_id and (not topics or e["topic"] in topics)]
        return evs[-limit:]

    @property
    def subscribers(self) -> int:
        return len(self._subs)
