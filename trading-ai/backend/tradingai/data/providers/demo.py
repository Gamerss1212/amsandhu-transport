"""DEMO market: SIMULATED prices for offline use and tests. Nothing here is a real market, and every bar it makes is
flagged `simulated=True`, which the API and the page show as DEMO DATA.

Deterministic: one-minute bars from a fixed anchor (2026-01-01 UTC) are generated from a seeded generator, so a restart
shows the same history and new bars appear as real time passes. Three characters:
  DEMO-TREND     drifting random walk with a slowly changing trend
  DEMO-RANGE     mean-reverting around a level (Ornstein-Uhlenbeck)
  DEMO-VOLATILE  volatility clustering (GARCH(1,1)) with occasional jumps
"""

from __future__ import annotations

import time
import zlib

import numpy as np

from tradingai.data.bars import TF_MS, Bars, resample
from tradingai.data.providers.base import Provider

ANCHOR = 1_767_225_600_000           # 2026-01-01T00:00:00Z
_CACHE: dict[str, tuple[int, Bars]] = {}


BLOCK = 14_400                       # cache in 10-day blocks of one-minute bars


def _stream(symbol: str, k: int) -> np.random.Generator:
    """An independent seeded stream per purpose, so a longer history keeps every earlier value unchanged."""
    return np.random.default_rng([zlib.crc32(symbol.encode()), k])


def _one_minute(symbol: str, n: int) -> tuple[np.ndarray, ...]:
    z = _stream(symbol, 1).standard_normal(n)
    if symbol == "DEMO-RANGE":
        r = np.empty(n)
        x = 0.0
        for i in range(n):
            x += -0.002 * x + 0.0009 * z[i]
            r[i] = x
        logp = np.log(100.0) + r
    elif symbol == "DEMO-VOLATILE":
        jumps = _stream(symbol, 2).random(n) < 0.0004
        js = _stream(symbol, 3).standard_normal(n) * 0.02
        r = np.empty(n)
        v, prev = 1e-6, 0.0
        for i in range(n):
            v = 2e-8 + 0.08 * prev * prev + 0.9 * v
            prev = np.sqrt(v) * z[i] + (js[i] if jumps[i] else 0.0)
            r[i] = prev
        logp = np.log(50.0) + np.cumsum(r)
    else:
        trend = np.repeat(_stream(symbol, 4).standard_normal(n // 2880 + 1) * 4e-5, 2880)[:n]
        logp = np.log(1000.0) + np.cumsum(trend + 0.0007 * z)
    close = np.exp(logp)
    open_ = np.r_[close[0], close[:-1]]
    wig = np.abs(_stream(symbol, 5).standard_normal(n)) * 0.0004 * close
    high = np.maximum(open_, close) + wig
    low = np.minimum(open_, close) - wig * _stream(symbol, 6).random(n)
    vol = np.round(np.exp(_stream(symbol, 7).standard_normal(n) * 0.5 + 3.0), 4)
    return open_, high, low, close, vol


class Demo(Provider):
    name = "demo"
    simulated = True
    timeframes = tuple(TF_MS)

    def fetch(self, instrument_id: str, symbol: str, tf: str, start_ms: int, end_ms: int | None = None) -> Bars:
        now = int(time.time() * 1000) if end_ms is None else end_ms
        n = int(max(0, (now - ANCHOR) // 60_000))
        cap = (n // BLOCK + 1) * BLOCK
        cached = _CACHE.get(symbol)
        if cached is None or cached[0] < n:
            o, h, lo, c, v = _one_minute(symbol, cap)
            ts = ANCHOR + np.arange(cap, dtype=np.int64) * 60_000
            _CACHE[symbol] = (cap, Bars(instrument_id, "1m", ts, o, h, lo, c, v, simulated=True,
                                        source=f"demo:{symbol} (SIMULATED)"))
        base = _CACHE[symbol][1].slice(0, n)
        b = base if tf == "1m" else resample(base, tf, now)
        b = b.window(start_ms, end_ms)
        b.instrument_id, b.simulated = instrument_id, True
        return self.complete_only(b, now)
