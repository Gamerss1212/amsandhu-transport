"""Structured logs (JSON lines in logs/trading-ai.log, rotated) with secrets scrubbed before anything is written."""

from __future__ import annotations

import json
import logging
import logging.handlers
import re
import sys
from pathlib import Path

_SECRET_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|secret|token|password|passphrase|authorization|signature)(\"?\s*[:=]\s*\"?)([^\s\",}]+)"),
    re.compile(r"(?i)(bearer\s+)([A-Za-z0-9\-._~+/]+=*)"),
]


def scrub(text: str) -> str:
    out = str(text)
    for p in _SECRET_PATTERNS:
        out = p.sub(lambda m: m.group(1) + (m.group(2) if m.lastindex and m.lastindex >= 3 else "") + "***", out)
    return out


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        d = {"ts": round(record.created, 3), "level": record.levelname, "logger": record.name,
             "msg": scrub(record.getMessage())}
        for k in ("correlation_id", "order_id", "decision_id"):
            if hasattr(record, k):
                d[k] = getattr(record, k)
        if record.exc_info:
            d["exc"] = scrub(self.formatException(record.exc_info))
        return json.dumps(d)


def setup(log_dir: Path, console: bool = True) -> logging.Logger:
    log_dir.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger("tradingai")
    if getattr(root, "_configured", False):
        return root
    root.setLevel(logging.INFO)
    fh = logging.handlers.RotatingFileHandler(log_dir / "trading-ai.log", maxBytes=5_000_000, backupCount=5,
                                              encoding="utf-8")
    fh.setFormatter(_JsonFormatter())
    root.addHandler(fh)
    if console and sys.stdout is not None:
        ch = logging.StreamHandler(sys.stdout)
        ch.setFormatter(logging.Formatter("  %(asctime)s  %(levelname)-7s %(message)s", "%H:%M:%S"))
        ch.setLevel(logging.WARNING)
        root.addHandler(ch)
    root._configured = True  # type: ignore[attr-defined]
    return root


def get(name: str) -> logging.Logger:
    return logging.getLogger(f"tradingai.{name}")
