"""The one HTTP client every data provider and broker adapter uses: timeouts, retries with exponential backoff,
HTTP 429 handling (honours Retry-After), a per-host minimum interval, and request counters for the health page.
Request bodies and auth headers are never logged."""

from __future__ import annotations

import statistics
import threading
import time
from collections import defaultdict
from email.utils import parsedate_to_datetime
from typing import Any, Optional

import httpx

from tradingai.core.logs import get

log = get("net")


class HttpError(RuntimeError):
    def __init__(self, message: str, status: Optional[int] = None):
        super().__init__(message)
        self.status = status


class Http:
    def __init__(self, timeout: float = 15.0, retries: int = 3, min_interval: dict[str, float] | None = None):
        self.client = httpx.Client(timeout=timeout, headers={"User-Agent": "trading-ai/1.0 (local research)"},
                                   follow_redirects=True)
        self.retries = retries
        self.min_interval = min_interval or {}
        self._last: dict[str, float] = defaultdict(float)
        self._lock = threading.Lock()
        self.stats: dict[str, dict[str, Any]] = defaultdict(lambda: {"requests": 0, "errors": 0, "http_429": 0,
                                                                     "last_ms": None, "latency_ms": []})
        self._offsets: list[float] = []

    def _clock(self, r: httpx.Response, t_send: float, t_recv: float) -> None:
        """Server Date header minus this computer's clock at the request midpoint (1-second header resolution)."""
        d = r.headers.get("Date")
        if not d:
            return
        try:
            server = parsedate_to_datetime(d).timestamp()
        except (TypeError, ValueError):
            return
        with self._lock:
            self._offsets = (self._offsets + [server - (t_send + t_recv) / 2])[-25:]

    def clock_offset(self) -> Optional[float]:
        """Median measured offset in seconds (positive: this computer is behind). None before any response."""
        with self._lock:
            return round(statistics.median(self._offsets), 2) if self._offsets else None

    def _pace(self, host: str) -> None:
        gap = self.min_interval.get(host, 0.0)
        if not gap:
            return
        with self._lock:
            wait = self._last[host] + gap - time.monotonic()
            self._last[host] = max(time.monotonic(), self._last[host] + gap)
        if wait > 0:
            time.sleep(wait)

    def request(self, method: str, url: str, **kw: Any) -> httpx.Response:
        host = httpx.URL(url).host
        st = self.stats[host]
        delay = 1.0
        for attempt in range(self.retries + 1):
            self._pace(host)
            t0 = time.perf_counter()
            w0 = time.time()
            try:
                r = self.client.request(method, url, **kw)
            except httpx.HTTPError as e:
                st["errors"] += 1
                if attempt == self.retries:
                    raise HttpError(f"{host}: {type(e).__name__}") from None
                time.sleep(delay)
                delay *= 2
                continue
            st["requests"] += 1
            self._clock(r, w0, time.time())
            ms = (time.perf_counter() - t0) * 1000
            st["last_ms"] = round(ms, 1)
            st["latency_ms"] = (st["latency_ms"] + [ms])[-200:]
            if r.status_code == 429:
                st["http_429"] += 1
                wait = float(r.headers.get("Retry-After") or delay)
                if attempt == self.retries:
                    raise HttpError(f"{host}: rate limited (HTTP 429)", 429)
                time.sleep(min(wait, 30.0))
                delay *= 2
                continue
            if r.status_code >= 500 and attempt < self.retries:
                st["errors"] += 1
                time.sleep(delay)
                delay *= 2
                continue
            if r.status_code >= 400:
                st["errors"] += 1
                raise HttpError(f"{host}: HTTP {r.status_code}", r.status_code)
            return r
        raise HttpError(f"{host}: no response")

    def get_json(self, url: str, **kw: Any) -> Any:
        return self.request("GET", url, **kw).json()

    def summary(self) -> dict:
        out = {}
        for host, s in self.stats.items():
            lat = sorted(s["latency_ms"])
            out[host] = {"requests": s["requests"], "errors": s["errors"], "http_429": s["http_429"],
                         "p50_ms": round(lat[len(lat) // 2], 1) if lat else None,
                         "p95_ms": round(lat[int(len(lat) * 0.95) - 1], 1) if len(lat) >= 20 else None}
        return out
