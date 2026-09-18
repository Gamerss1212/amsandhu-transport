#!/usr/bin/env python3
"""Pure-Python (standard library only) technical indicators and structure helpers.

Imported by snapshot.py and backtest.py. Every function takes plain lists and
returns a list of the same length, with None where the value is not yet defined.
No numpy or pandas so the scripts run anywhere Python 3.8+ runs.
"""

from __future__ import annotations

import math
from typing import List, Optional, Sequence, Tuple

Num = Optional[float]


# ---------------------------------------------------------------- averages ---

def sma(values: Sequence[Num], period: int) -> List[Num]:
    out: List[Num] = [None] * len(values)
    window: List[float] = []
    total = 0.0
    for i, v in enumerate(values):
        if v is None:
            window.clear()
            total = 0.0
            continue
        window.append(v)
        total += v
        if len(window) > period:
            total -= window.pop(0)
        if len(window) == period:
            out[i] = total / period
    return out


def ema(values: Sequence[Num], period: int) -> List[Num]:
    """Exponential moving average seeded with the SMA of the first `period` values."""
    out: List[Num] = [None] * len(values)
    k = 2.0 / (period + 1)
    seed: List[float] = []
    prev: Optional[float] = None
    for i, v in enumerate(values):
        if v is None:
            continue
        if prev is None:
            seed.append(v)
            if len(seed) == period:
                prev = sum(seed) / period
                out[i] = prev
            continue
        prev = v * k + prev * (1 - k)
        out[i] = prev
    return out


def stdev(values: Sequence[Num], period: int) -> List[Num]:
    out: List[Num] = [None] * len(values)
    window: List[float] = []
    for i, v in enumerate(values):
        if v is None:
            window.clear()
            continue
        window.append(v)
        if len(window) > period:
            window.pop(0)
        if len(window) == period:
            m = sum(window) / period
            out[i] = math.sqrt(sum((x - m) ** 2 for x in window) / period)
    return out


# --------------------------------------------------------------- momentum ---

def rsi(closes: Sequence[float], period: int = 14) -> List[Num]:
    """Wilder's RSI."""
    out: List[Num] = [None] * len(closes)
    if len(closes) <= period:
        return out
    gains = 0.0
    losses = 0.0
    for i in range(1, period + 1):
        d = closes[i] - closes[i - 1]
        if d >= 0:
            gains += d
        else:
            losses -= d
    avg_gain = gains / period
    avg_loss = losses / period
    out[period] = _rsi_value(avg_gain, avg_loss)
    for i in range(period + 1, len(closes)):
        d = closes[i] - closes[i - 1]
        g = d if d > 0 else 0.0
        l = -d if d < 0 else 0.0
        avg_gain = (avg_gain * (period - 1) + g) / period
        avg_loss = (avg_loss * (period - 1) + l) / period
        out[i] = _rsi_value(avg_gain, avg_loss)
    return out


def _rsi_value(avg_gain: float, avg_loss: float) -> float:
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - 100.0 / (1.0 + rs)


def macd(closes: Sequence[float], fast: int = 12, slow: int = 26, signal: int = 9):
    """Returns (macd_line, signal_line, histogram)."""
    ef = ema(closes, fast)
    es = ema(closes, slow)
    line: List[Num] = [None if (a is None or b is None) else a - b for a, b in zip(ef, es)]
    sig = ema(line, signal)
    hist: List[Num] = [None if (a is None or b is None) else a - b for a, b in zip(line, sig)]
    return line, sig, hist


# ------------------------------------------------------------- volatility ---

def true_range(highs: Sequence[float], lows: Sequence[float], closes: Sequence[float]) -> List[Num]:
    out: List[Num] = [None] * len(closes)
    for i in range(len(closes)):
        if i == 0:
            out[i] = highs[i] - lows[i]
        else:
            pc = closes[i - 1]
            out[i] = max(highs[i] - lows[i], abs(highs[i] - pc), abs(lows[i] - pc))
    return out


def atr(highs: Sequence[float], lows: Sequence[float], closes: Sequence[float], period: int = 14) -> List[Num]:
    """Wilder's ATR."""
    tr = true_range(highs, lows, closes)
    out: List[Num] = [None] * len(closes)
    if len(closes) < period:
        return out
    first = sum(tr[:period]) / period  # type: ignore[arg-type]
    out[period - 1] = first
    prev = first
    for i in range(period, len(closes)):
        prev = (prev * (period - 1) + tr[i]) / period  # type: ignore[operator]
        out[i] = prev
    return out


def bollinger(closes: Sequence[float], period: int = 20, mult: float = 2.0):
    """Returns (middle, upper, lower, bandwidth) where bandwidth = (upper-lower)/middle."""
    mid = sma(closes, period)
    sd = stdev(closes, period)
    upper: List[Num] = []
    lower: List[Num] = []
    width: List[Num] = []
    for m, s in zip(mid, sd):
        if m is None or s is None:
            upper.append(None)
            lower.append(None)
            width.append(None)
        else:
            u = m + mult * s
            l = m - mult * s
            upper.append(u)
            lower.append(l)
            width.append((u - l) / m if m else None)
    return mid, upper, lower, width


# ------------------------------------------------------------------ volume ---

def vwap(highs: Sequence[float], lows: Sequence[float], closes: Sequence[float],
         volumes: Sequence[float], session_start_flags: Sequence[bool]) -> List[Num]:
    """Session VWAP. `session_start_flags[i]` is True on the first candle of a session."""
    out: List[Num] = [None] * len(closes)
    cum_pv = 0.0
    cum_v = 0.0
    for i in range(len(closes)):
        if session_start_flags[i]:
            cum_pv = 0.0
            cum_v = 0.0
        tp = (highs[i] + lows[i] + closes[i]) / 3.0
        cum_pv += tp * volumes[i]
        cum_v += volumes[i]
        out[i] = cum_pv / cum_v if cum_v > 0 else None
    return out


def relative_volume(volumes: Sequence[float], period: int = 20) -> List[Num]:
    """Volume divided by the average of the previous `period` candles (excludes current)."""
    out: List[Num] = [None] * len(volumes)
    for i in range(period, len(volumes)):
        window = volumes[i - period:i]
        avg = sum(window) / period
        out[i] = volumes[i] / avg if avg > 0 else None
    return out


# --------------------------------------------------------------- structure ---

def swing_points(highs: Sequence[float], lows: Sequence[float], n: int = 3
                 ) -> Tuple[List[int], List[int]]:
    """Fractal swing highs and lows: a high greater than the `n` highs on each side.

    The last `n` candles can never be confirmed swings, which is the honest answer:
    a swing is only known in hindsight.
    """
    sh: List[int] = []
    sl: List[int] = []
    for i in range(n, len(highs) - n):
        h = highs[i]
        l = lows[i]
        if all(h > highs[i - k] for k in range(1, n + 1)) and all(h >= highs[i + k] for k in range(1, n + 1)):
            sh.append(i)
        if all(l < lows[i - k] for k in range(1, n + 1)) and all(l <= lows[i + k] for k in range(1, n + 1)):
            sl.append(i)
    return sh, sl


def classify_trend(highs: Sequence[float], lows: Sequence[float],
                   swing_highs: Sequence[int], swing_lows: Sequence[int]) -> str:
    """'uptrend' (HH+HL), 'downtrend' (LH+LL), or 'range' from the last two swings of each kind."""
    if len(swing_highs) < 2 or len(swing_lows) < 2:
        return "unknown"
    h1, h2 = highs[swing_highs[-2]], highs[swing_highs[-1]]
    l1, l2 = lows[swing_lows[-2]], lows[swing_lows[-1]]
    if h2 > h1 and l2 > l1:
        return "uptrend"
    if h2 < h1 and l2 < l1:
        return "downtrend"
    return "range"


def equal_levels(prices: Sequence[float], tolerance: float) -> List[float]:
    """Groups of prices within `tolerance` of each other; returns the mean of each group."""
    if not prices:
        return []
    srt = sorted(prices)
    groups: List[List[float]] = [[srt[0]]]
    for p in srt[1:]:
        if p - groups[-1][-1] <= tolerance:
            groups[-1].append(p)
        else:
            groups.append([p])
    return [sum(g) / len(g) for g in groups if len(g) >= 2]


def last_value(series: Sequence[Num]) -> Num:
    for v in reversed(series):
        if v is not None:
            return v
    return None


def percentile_rank(series: Sequence[Num], value: float, lookback: int = 100) -> Num:
    """Where `value` sits within the last `lookback` non-None values (0-100)."""
    vals = [v for v in series[-lookback:] if v is not None]
    if not vals:
        return None
    below = sum(1 for v in vals if v < value)
    return 100.0 * below / len(vals)
