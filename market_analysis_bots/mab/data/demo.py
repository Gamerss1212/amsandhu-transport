"""The DEMO market: synthetic prices for the demo workspace (and offline tests). Nothing here is real.

Prices follow a deterministic, self-similar random path (value noise summed over time scales from one minute
to about three days, with amplitudes growing like the square root of the scale, as a random walk's would),
with volatility regimes that change every few hours, so strategies see trends, ranges, quiet and loud spells.
Every value is a pure function of (symbol, minute), so restarts, different timeframes and different processes
all see the same history. The order book is synthetic around the current price.

Symbols are prefixed DEMO- and the venue is "demo"; the app labels everything from here DEMO.
"""

from __future__ import annotations

import hashlib
import math
import struct
from typing import Dict, List, Optional

from mab.clock import tf_ms
from mab.data.adapters import ADAPTERS, Adapter
from mab.models import Bar, BookSnapshot, Trade, now_ms

MIN = 60_000
MARKETS = {                          # symbol: (anchor price, daily volatility, spread bps, lot, tick)
    "DEMO-BTC": (65_000.0, 0.030, 1.0, 1e-6, 0.01),
    "DEMO-ETH": (3_200.0, 0.040, 1.5, 1e-5, 0.01),
    "DEMO-SOL": (150.0, 0.055, 3.0, 1e-4, 0.001),
    "DEMO-DOGE": (0.15, 0.070, 5.0, 1.0, 0.00001),
    "DEMO-MEME": (0.0042, 0.120, 12.0, 100.0, 0.0000001),
}
OCTAVES = [1, 4, 16, 64, 256, 1024, 4096]      # minutes


def _u(*parts) -> float:
    """Uniform in [-1, 1) from a hash of the parts."""
    h = hashlib.blake2b("|".join(map(str, parts)).encode(), digest_size=8).digest()
    return struct.unpack(">Q", h)[0] / 2 ** 63 - 1.0


def _smooth(a: float, b: float, x: float) -> float:
    s = x * x * (3 - 2 * x)
    return a + (b - a) * s


class DemoPath:
    def __init__(self, symbol: str):
        self.symbol = symbol
        self.p0, self.dvol, self.spread_bps, self.lot, self.tick = MARKETS[symbol]
        # per-minute volatility of a random walk with this daily volatility
        self.mvol = self.dvol / math.sqrt(1440)
        self._cache: Dict[int, float] = {}

    def regime(self, minute: int) -> float:
        """Volatility multiplier: changes every 4 hours, sometimes quiet (0.5x), sometimes loud (2x)."""
        block = minute // 240
        u = _u(self.symbol, "regime", block)
        return 0.5 if u < -0.4 else (2.0 if u > 0.6 else 1.0)

    def logp(self, minute: int) -> float:
        v = self._cache.get(minute)
        if v is not None:
            return v
        x = 0.0
        for L in OCTAVES:
            k, r = divmod(minute, L)
            a, b = _u(self.symbol, L, k), _u(self.symbol, L, k + 1)
            x += _smooth(a, b, r / L) * math.sqrt(L)
        v = math.log(self.p0) + x * self.mvol * 1.6 * self.regime(minute)
        if len(self._cache) > 200_000:
            self._cache.clear()
        self._cache[minute] = v
        return v

    def price(self, minute: int) -> float:
        return math.exp(self.logp(minute))

    def bar(self, t_ms: int, step_ms: int) -> tuple:
        m0 = t_ms // MIN
        n = max(1, step_ms // MIN)
        pts = [self.price(m0 + j) for j in range(n + 1)]
        o, c = pts[0], pts[-1]
        wig = [abs(_u(self.symbol, "wick", m0 + j)) * self.mvol * self.regime(m0 + j) * p for j, p in enumerate(pts[:-1])]
        h = max(max(pts), max(p + w for p, w in zip(pts[:-1], wig)))
        l = min(min(pts), min(p - w for p, w in zip(pts[:-1], wig)))
        move = abs(math.log(c / o)) / (self.mvol * math.sqrt(n))
        vol = sum(math.exp(1.2 * _u(self.symbol, "vol", m0 + j)) for j in range(n)) * (1 + move) * 1_000_000 / self.p0
        return o, h, l, c, vol


class DemoAdapter(Adapter):
    venue = "demo"
    timeframes = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600, "4h": 14400, "1d": 86400}

    def __init__(self, http=None):
        super().__init__(http)
        self.paths = {s: DemoPath(s) for s in MARKETS}

    def instruments(self) -> List[dict]:
        return [{"venue": self.venue, "symbol": s, "asset_type": "crypto", "base": s.split("-")[1], "quote": "USD",
                 "tick_size": m[4], "lot_size": m[3], "min_notional": 1.0, "can_short": False, "calendar": "CRYPTO-UTC",
                 "demo": True} for s, m in MARKETS.items()]

    def bars(self, symbol, tf, limit=300, end_ms=None):
        if symbol not in self.paths:
            raise ValueError(f"unknown demo market {symbol}")
        step = tf_ms(tf)
        now = now_ms()
        end = min(end_ms or now, now)
        last_open = (end // step) * step - step                 # the newest COMPLETED bar
        out = []
        recv = now_ms()
        for k in range(min(limit, 1000) - 1, -1, -1):
            t = last_open - k * step
            o, h, l, c, v = self.paths[symbol].bar(t, step)
            out.append(Bar(self.venue, symbol, tf, t, o, h, l, c, v, recv, "demo.synthetic"))
        return self._complete(out, tf, now)

    def trades(self, symbol, limit=500):
        return []

    def book(self, symbol, depth=50):
        p = self.paths[symbol]
        now = now_ms()
        mid = p.price(now // MIN)
        half = mid * p.spread_bps / 2e4
        bids, asks = [], []
        step = max(p.tick, mid * p.spread_bps / 1e4)
        slot = now // 10_000
        for k in range(depth):
            size = (0.5 + abs(_u(symbol, "bsz", slot, k))) * 5_000 / mid * (1 + k * 0.15)
            bids.append([round(mid - half - k * step, 10), size])
            size2 = (0.5 + abs(_u(symbol, "asz", slot, k))) * 5_000 / mid * (1 + k * 0.15)
            asks.append([round(mid + half + k * step, 10), size2])
        return BookSnapshot(self.venue, symbol, now, bids, asks, now, "demo.synthetic.book")


ADAPTERS["demo"] = DemoAdapter
