"""Server-Sent Events: the live feed from a workspace database to the browser.

The bots run in another process, so the stream follows the audit log in the shared database (WAL lets it
read while the fleet writes). A client that reconnects sends Last-Event-ID and resumes exactly after the
last event it saw; nothing is skipped or repeated. Periodic `state` messages carry small snapshots (bot
states, account figures, service health) supplied by the caller, and comment lines keep proxies and the
browser from timing the connection out.

    for chunk in follow(storage, last_id, snapshot=fn, stop=event):   # bytes, ready to write
        wfile.write(chunk); wfile.flush()
"""

from __future__ import annotations

import json
import threading
import time
from typing import Callable, Iterator, Optional

POLL_S = 0.5
STATE_EVERY_S = 2.0
KEEPALIVE_S = 15.0
BATCH = 200


def sse(data, event: Optional[str] = None, eid: Optional[int] = None, retry_ms: Optional[int] = None) -> bytes:
    lines = []
    if retry_ms:
        lines.append(f"retry: {int(retry_ms)}")
    if eid is not None:
        lines.append(f"id: {int(eid)}")
    if event:
        lines.append(f"event: {event}")
    text = data if isinstance(data, str) else json.dumps(data, default=str, separators=(",", ":"))
    for ln in text.split("\n"):
        lines.append(f"data: {ln}")
    return ("\n".join(lines) + "\n\n").encode("utf-8")


def parse_last_id(header: Optional[str], query_value: Optional[str] = None) -> Optional[int]:
    for v in (header, query_value):
        try:
            if v is not None and str(v).strip() != "":
                return max(0, int(str(v).strip()))
        except ValueError:
            continue
    return None


def follow(storage, last_id: Optional[int] = None, snapshot: Optional[Callable[[], dict]] = None,
           stop: Optional[threading.Event] = None, min_severity: str = "debug", backlog: int = 50,
           max_seconds: Optional[float] = None, sleep=time.sleep, clock=time.monotonic) -> Iterator[bytes]:
    """Yield SSE chunks: first the recent backlog (or everything after last_id), then new events as they
    are written, with a state snapshot every few seconds. Ends when `stop` is set or after max_seconds."""
    t0 = clock()
    yield sse({"hello": True, "time": int(time.time() * 1000)}, event="hello", retry_ms=3000)
    if last_id is None:
        last_id = max(0, storage.audit_last_id() - backlog)
    next_state, next_ping = 0.0, clock() + KEEPALIVE_S
    while not (stop is not None and stop.is_set()):
        rows = storage.audit_since(last_id, BATCH, min_severity)
        for r in rows:
            last_id = r["id"]
            yield sse(r, event="audit", eid=r["id"])
        now = clock()
        if snapshot is not None and now >= next_state:
            try:
                yield sse(snapshot(), event="state")
            except Exception as e:                                       # noqa: BLE001
                yield sse({"error": f"{type(e).__name__}: {e}"}, event="state_error")
            next_state = now + STATE_EVERY_S
        if now >= next_ping:
            yield b": keep-alive\n\n"
            next_ping = now + KEEPALIVE_S
        if max_seconds is not None and now - t0 >= max_seconds:
            return
        if len(rows) < BATCH:
            sleep(POLL_S)
