#!/usr/bin/env python3
"""Tiny cached HTTP/JSON client. Standard library only.

Public exchange APIs rate-limit and occasionally geo-block, so every call goes
through one place that caches, times out, and never raises into the caller's face:
failures come back as None with the reason recorded, so one dead venue degrades the
dashboard instead of breaking it.
"""

from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional, Tuple

import config

_UA = "JarvusTerminal/1.0 (+local research tool)"
_cache: Dict[str, Tuple[float, Any]] = {}
_lock = threading.Lock()
_errors: Dict[str, str] = {}


def cache_get(key: str, ttl: float) -> Optional[Any]:
    with _lock:
        hit = _cache.get(key)
    if hit and (time.time() - hit[0]) < ttl:
        return hit[1]
    return None


def cache_put(key: str, value: Any) -> None:
    with _lock:
        _cache[key] = (time.time(), value)


def cache_clear() -> None:
    with _lock:
        _cache.clear()


def last_errors() -> Dict[str, str]:
    with _lock:
        return dict(_errors)


def get_text(url: str, params: Optional[dict] = None, ttl: float = 60.0) -> Optional[str]:
    full = url + ("?" + urllib.parse.urlencode(params) if params else "")
    cached = cache_get(full, ttl)
    if cached is not None:
        return cached
    req = urllib.request.Request(full, headers={"User-Agent": _UA, "Accept": "*/*"})
    try:
        with urllib.request.urlopen(req, timeout=config.HTTP_TIMEOUT) as resp:
            text = resp.read().decode("utf-8", errors="replace")
        cache_put(full, text)
        with _lock:
            _errors.pop(full, None)
        return text
    except Exception as exc:  # noqa: BLE001 - one bad venue must not kill a scan
        with _lock:
            _errors[full] = f"{type(exc).__name__}: {exc}"
        return None


def get_json(url: str, params: Optional[dict] = None, ttl: float = 60.0) -> Optional[Any]:
    text = get_text(url, params, ttl)
    if text is None:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        with _lock:
            _errors[url] = f"bad JSON: {exc}"
        return None
