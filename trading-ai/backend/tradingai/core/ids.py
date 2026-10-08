"""Durable, sortable ids. A client order id is derived from the decision it serves, so a retry of the same logical
order reuses the same id and the broker (or the paper broker) can refuse a duplicate (section 219)."""

from __future__ import annotations

import hashlib
import os
import time


def new_id(prefix: str) -> str:
    """<prefix>-<ms timestamp base36>-<random>: unique, roughly time-ordered."""
    ms = int(time.time() * 1000)
    return f"{prefix}-{_b36(ms)}-{os.urandom(5).hex()}"


def client_order_id(decision_id: str, leg: int = 0) -> str:
    """Deterministic for one decision and leg: retrying a timed-out submission never creates a second order."""
    h = hashlib.sha256(f"{decision_id}:{leg}".encode()).hexdigest()[:20]
    return f"TA{h}"


def _b36(n: int) -> str:
    chars = "0123456789abcdefghijklmnopqrstuvwxyz"
    out = ""
    while n:
        n, r = divmod(n, 36)
        out = chars[r] + out
    return out or "0"
