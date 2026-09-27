"""The one HTTP client every adapter uses.

* Per-host token-bucket rate limits, set below each venue's published public limits.
* Bounded retries with exponential backoff and jitter; HTTP 429 honours Retry-After.
* A per-host circuit breaker: after repeated failures the host is left alone for a cooldown
  instead of being hammered, and callers get an immediate, explicit failure.
* Counters for every request, error and throttle, so shared-data claims can be verified.

Failures never raise into strategy code: the adapter layer turns them into "no data",
which the data-quality layer then reports as stale.
"""

from __future__ import annotations

import json
import random
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from typing import Any, Dict, Optional

USER_AGENT = "market-analysis-bots/1.0 (research; paper trading)"

# requests per second (sustained, burst) per host: conservative against published public limits
DEFAULT_LIMITS = {
    "api.exchange.coinbase.com": (6.0, 10),       # public: 10 rps
    "api.kraken.com": (0.8, 3),                   # public: ~1 rps sustained
    "www.okx.com": (8.0, 15),                     # public market data: 20 req / 2 s per endpoint
    "query1.finance.yahoo.com": (3.0, 6),         # unofficial; bursts draw 429s
    "query2.finance.yahoo.com": (3.0, 6),
    "www.deribit.com": (5.0, 10),
    "api.nasdaq.com": (1.0, 2),
}


class TokenBucket:
    def __init__(self, rate: float, burst: int):
        self.rate, self.burst = rate, float(burst)
        self.tokens = float(burst)
        self.t = time.monotonic()
        self.lock = threading.Lock()

    def acquire(self, timeout: float = 30.0) -> bool:
        deadline = time.monotonic() + timeout
        while True:
            with self.lock:
                now = time.monotonic()
                self.tokens = min(self.burst, self.tokens + (now - self.t) * self.rate)
                self.t = now
                if self.tokens >= 1:
                    self.tokens -= 1
                    return True
                wait = (1 - self.tokens) / self.rate
            if time.monotonic() + wait > deadline:
                return False
            time.sleep(min(wait, 0.5))


class HostState:
    def __init__(self):
        self.consecutive_failures = 0
        self.open_until = 0.0


class HttpError(Exception):
    def __init__(self, msg: str, status: Optional[int] = None):
        super().__init__(msg)
        self.status = status


class Http:
    """Thread-safe JSON-over-HTTP client with limits, retries, breaker and counters."""

    def __init__(self, limits: Dict[str, tuple] = None, timeout: float = 15.0, max_retries: int = 3,
                 breaker_threshold: int = 5, breaker_cooldown_s: float = 60.0, opener=None):
        self.limits = dict(DEFAULT_LIMITS, **(limits or {}))
        self.timeout = timeout
        self.max_retries = max_retries
        self.breaker_threshold = breaker_threshold
        self.breaker_cooldown_s = breaker_cooldown_s
        self._buckets: Dict[str, TokenBucket] = {}
        self._hosts: Dict[str, HostState] = defaultdict(HostState)
        self._lock = threading.Lock()
        self.stats = defaultdict(lambda: defaultdict(int))   # host -> counter -> n
        self._opener = opener or urllib.request.urlopen      # injectable for failure tests

    def _bucket(self, host: str) -> TokenBucket:
        with self._lock:
            b = self._buckets.get(host)
            if b is None:
                rate, burst = self.limits.get(host, (2.0, 4))
                b = self._buckets[host] = TokenBucket(rate, burst)
            return b

    def breaker_open(self, host: str) -> bool:
        return self._hosts[host].open_until > time.monotonic()

    def get_json(self, url: str, params: Dict[str, Any] = None, headers: Dict[str, str] = None) -> Any:
        full = url + ("?" + urllib.parse.urlencode(params) if params else "")
        host = urllib.parse.urlparse(full).netloc
        st = self.stats[host]
        if self.breaker_open(host):
            st["breaker_rejections"] += 1
            raise HttpError(f"{host}: circuit open after repeated failures; retrying later")
        last_exc: Optional[Exception] = None
        for attempt in range(self.max_retries + 1):
            if not self._bucket(host).acquire():
                st["rate_limit_waits_exhausted"] += 1
                raise HttpError(f"{host}: local rate limit wait exceeded")
            st["requests"] += 1
            try:
                req = urllib.request.Request(full, headers={"User-Agent": USER_AGENT, "Accept": "application/json",
                                                            **(headers or {})})
                with self._opener(req, timeout=self.timeout) as resp:
                    body = resp.read()
                st["bytes"] += len(body)
                data = json.loads(body.decode("utf-8"))
                self._hosts[host].consecutive_failures = 0
                return data
            except urllib.error.HTTPError as exc:
                last_exc = exc
                if exc.code == 429:
                    st["http_429"] += 1
                    retry_after = float(exc.headers.get("Retry-After") or 0) if exc.headers else 0
                    time.sleep(min(10.0, max(retry_after, 0.5 * 2 ** attempt)) + random.random() * 0.3)
                    continue
                st[f"http_{exc.code}"] += 1
                if 400 <= exc.code < 500:            # a client error will not fix itself on retry
                    self._fail(host)
                    raise HttpError(f"{host}: HTTP {exc.code}", exc.code) from None
            except (urllib.error.URLError, TimeoutError, ConnectionError, OSError, ValueError) as exc:
                last_exc = exc
                st["network_errors"] += 1
            time.sleep(min(8.0, 0.4 * 2 ** attempt) + random.random() * 0.3)
        self._fail(host)
        raise HttpError(f"{host}: failed after {self.max_retries + 1} attempts: {type(last_exc).__name__}: {last_exc}")

    def _fail(self, host: str):
        hs = self._hosts[host]
        hs.consecutive_failures += 1
        if hs.consecutive_failures >= self.breaker_threshold:
            hs.open_until = time.monotonic() + self.breaker_cooldown_s
            self.stats[host]["breaker_trips"] += 1
            hs.consecutive_failures = 0

    def snapshot(self) -> Dict[str, Dict[str, int]]:
        return {h: dict(c) for h, c in self.stats.items()}
