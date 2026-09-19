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


# =============================================================================
# Extended library
# =============================================================================
# Everything below is a from-scratch implementation of an indicator you would
# normally reach for on TradingView. They are written against plain lists so the
# app keeps its no-install promise, and each returns a list the same length as its
# input with None where the value is not yet defined.
#
# A note on what "any TradingView indicator" can and cannot mean: the standard
# library below is the real thing, computed from the same formulas. What cannot be
# imported is somebody's closed-source Pine script, because that code is not
# public. If you have the Pine source, the formulas here are the building blocks
# to port it with; `engine/strategies/custom/` is where it would live.


def wma(values: Sequence[Num], period: int) -> List[Num]:
    """Weighted moving average: linearly more weight on recent values."""
    out: List[Num] = [None] * len(values)
    denom = period * (period + 1) / 2
    for i in range(len(values)):
        window = values[i - period + 1:i + 1]
        if len(window) < period or any(v is None for v in window):
            continue
        out[i] = sum(v * (j + 1) for j, v in enumerate(window)) / denom
    return out


def hma(values: Sequence[Num], period: int = 21) -> List[Num]:
    """Hull moving average: much less lag than an EMA at the cost of overshoot."""
    half = wma(values, max(1, period // 2))
    full = wma(values, period)
    raw = [None if (a is None or b is None) else 2 * a - b for a, b in zip(half, full)]
    return wma(raw, max(1, int(math.sqrt(period))))


def dema(values: Sequence[Num], period: int = 21) -> List[Num]:
    e1 = ema(values, period)
    e2 = ema(e1, period)
    return [None if (a is None or b is None) else 2 * a - b for a, b in zip(e1, e2)]


def tema(values: Sequence[Num], period: int = 21) -> List[Num]:
    e1 = ema(values, period)
    e2 = ema(e1, period)
    e3 = ema(e2, period)
    return [None if (a is None or b is None or c is None) else 3 * a - 3 * b + c
            for a, b, c in zip(e1, e2, e3)]


def rma(values: Sequence[Num], period: int) -> List[Num]:
    """Wilder's smoothing, the averaging used inside RSI, ATR, ADX."""
    out: List[Num] = [None] * len(values)
    acc, seed = None, []
    for i, v in enumerate(values):
        if v is None:
            continue
        if acc is None:
            seed.append(v)
            if len(seed) == period:
                acc = sum(seed) / period
                out[i] = acc
            continue
        acc = (acc * (period - 1) + v) / period
        out[i] = acc
    return out


def supertrend(highs, lows, closes, period: int = 10, multiplier: float = 3.0):
    """Supertrend: an ATR band that flips sides and then acts as a trailing stop.

    Returns (line, direction) where direction is 1 while the trend is up and -1
    while it is down. The flip rule is what makes it a trend follower rather than a
    band: the line only ever moves in the trend's favour until price closes through
    it, at which point it jumps to the other side.
    """
    n = len(closes)
    a = atr(highs, lows, closes, period)
    line: List[Num] = [None] * n
    direction: List[Optional[int]] = [None] * n
    final_upper = final_lower = None
    prev_dir = 1
    for i in range(n):
        if a[i] is None:
            continue
        mid = (highs[i] + lows[i]) / 2
        basic_upper = mid + multiplier * a[i]
        basic_lower = mid - multiplier * a[i]
        prev_close = closes[i - 1] if i else closes[i]
        # the bands only tighten while the trend holds
        final_upper = (basic_upper if final_upper is None or basic_upper < final_upper
                       or prev_close > final_upper else final_upper)
        final_lower = (basic_lower if final_lower is None or basic_lower > final_lower
                       or prev_close < final_lower else final_lower)
        if closes[i] > final_upper:
            prev_dir = 1
        elif closes[i] < final_lower:
            prev_dir = -1
        direction[i] = prev_dir
        line[i] = final_lower if prev_dir == 1 else final_upper
    return line, direction


def adx(highs, lows, closes, period: int = 14):
    """Average directional index with its +DI / -DI components.

    ADX measures how *strong* a trend is without saying which way, which makes it a
    filter rather than a signal: above roughly 25 the trend-following setups behave,
    below roughly 20 they get chopped up.
    """
    n = len(closes)
    plus_dm, minus_dm, tr = [0.0] * n, [0.0] * n, [0.0] * n
    for i in range(1, n):
        up = highs[i] - highs[i - 1]
        down = lows[i - 1] - lows[i]
        plus_dm[i] = up if (up > down and up > 0) else 0.0
        minus_dm[i] = down if (down > up and down > 0) else 0.0
        tr[i] = max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
    atr_s, plus_s, minus_s = rma(tr, period), rma(plus_dm, period), rma(minus_dm, period)
    plus_di: List[Num] = [None] * n
    minus_di: List[Num] = [None] * n
    dx: List[Num] = [None] * n
    for i in range(n):
        if not atr_s[i] or plus_s[i] is None or minus_s[i] is None:
            continue
        plus_di[i] = 100 * plus_s[i] / atr_s[i]
        minus_di[i] = 100 * minus_s[i] / atr_s[i]
        denom = plus_di[i] + minus_di[i]
        dx[i] = 100 * abs(plus_di[i] - minus_di[i]) / denom if denom else 0.0
    return rma(dx, period), plus_di, minus_di


def keltner(highs, lows, closes, period: int = 20, mult: float = 2.0):
    """Keltner channels: an EMA with ATR bands. Smoother than Bollinger."""
    mid = ema(closes, period)
    a = atr(highs, lows, closes, period)
    up = [None if (m is None or x is None) else m + mult * x for m, x in zip(mid, a)]
    lo = [None if (m is None or x is None) else m - mult * x for m, x in zip(mid, a)]
    return mid, up, lo


def squeeze_momentum(highs, lows, closes, bb_period=20, bb_mult=2.0, kc_period=20, kc_mult=1.5):
    """TTM-style squeeze: Bollinger bands inside Keltner channels.

    True means volatility is compressed and an expansion is pending. It says nothing
    about direction, which is exactly why it pairs with the volatility gate.
    """
    _, bb_up, bb_lo, _ = bollinger(closes, bb_period, bb_mult)
    _, kc_up, kc_lo = keltner(highs, lows, closes, kc_period, kc_mult)
    return [None if None in (a, b, c, d) else (a < c and b > d)
            for a, b, c, d in zip(bb_up, bb_lo, kc_up, kc_lo)]


def stochastic(highs, lows, closes, k_period: int = 14, k_smooth: int = 3, d_smooth: int = 3):
    """Stochastic oscillator: where the close sits inside the recent range."""
    n = len(closes)
    raw: List[Num] = [None] * n
    for i in range(k_period - 1, n):
        hh, ll = max(highs[i - k_period + 1:i + 1]), min(lows[i - k_period + 1:i + 1])
        raw[i] = 100 * (closes[i] - ll) / (hh - ll) if hh > ll else 50.0
    k = sma(raw, k_smooth)
    return k, sma(k, d_smooth)


def stoch_rsi(closes, rsi_period: int = 14, stoch_period: int = 14, k_smooth: int = 3, d_smooth: int = 3):
    """Stochastic applied to RSI: faster, noisier, useful only at extremes."""
    r = rsi(closes, rsi_period)
    n = len(closes)
    raw: List[Num] = [None] * n
    for i in range(n):
        window = [v for v in r[max(0, i - stoch_period + 1):i + 1] if v is not None]
        if len(window) < stoch_period or r[i] is None:
            continue
        hi, lo = max(window), min(window)
        raw[i] = 100 * (r[i] - lo) / (hi - lo) if hi > lo else 50.0
    k = sma(raw, k_smooth)
    return k, sma(k, d_smooth)


def cci(highs, lows, closes, period: int = 20) -> List[Num]:
    """Commodity channel index: deviation from a typical-price mean."""
    n = len(closes)
    tp = [(highs[i] + lows[i] + closes[i]) / 3 for i in range(n)]
    m = sma(tp, period)
    out: List[Num] = [None] * n
    for i in range(n):
        if m[i] is None:
            continue
        window = tp[i - period + 1:i + 1]
        md = sum(abs(v - m[i]) for v in window) / period
        out[i] = (tp[i] - m[i]) / (0.015 * md) if md else 0.0
    return out


def williams_r(highs, lows, closes, period: int = 14) -> List[Num]:
    n = len(closes)
    out: List[Num] = [None] * n
    for i in range(period - 1, n):
        hh, ll = max(highs[i - period + 1:i + 1]), min(lows[i - period + 1:i + 1])
        out[i] = -100 * (hh - closes[i]) / (hh - ll) if hh > ll else -50.0
    return out


def obv(closes, volumes) -> List[Num]:
    """On-balance volume: volume signed by the day's direction."""
    out: List[Num] = [0.0] * len(closes)
    for i in range(1, len(closes)):
        out[i] = out[i - 1] + (volumes[i] if closes[i] > closes[i - 1]
                               else -volumes[i] if closes[i] < closes[i - 1] else 0.0)
    return out


def mfi(highs, lows, closes, volumes, period: int = 14) -> List[Num]:
    """Money flow index: RSI weighted by volume."""
    n = len(closes)
    tp = [(highs[i] + lows[i] + closes[i]) / 3 for i in range(n)]
    out: List[Num] = [None] * n
    for i in range(period, n):
        pos = neg = 0.0
        for j in range(i - period + 1, i + 1):
            flow = tp[j] * volumes[j]
            if tp[j] > tp[j - 1]:
                pos += flow
            elif tp[j] < tp[j - 1]:
                neg += flow
        out[i] = 100.0 if neg == 0 else 100 - 100 / (1 + pos / neg)
    return out


def cmf(highs, lows, closes, volumes, period: int = 20) -> List[Num]:
    """Chaikin money flow: where closes sit in their bars, weighted by volume."""
    n = len(closes)
    mfv = []
    for i in range(n):
        rng = highs[i] - lows[i]
        mult = ((closes[i] - lows[i]) - (highs[i] - closes[i])) / rng if rng else 0.0
        mfv.append(mult * volumes[i])
    out: List[Num] = [None] * n
    for i in range(period - 1, n):
        vsum = sum(volumes[i - period + 1:i + 1])
        out[i] = sum(mfv[i - period + 1:i + 1]) / vsum if vsum else 0.0
    return out


def parabolic_sar(highs, lows, step: float = 0.02, max_step: float = 0.2) -> List[Num]:
    """Parabolic SAR: an accelerating trailing stop. Good exit, poor entry."""
    n = len(highs)
    out: List[Num] = [None] * n
    if n < 3:
        return out
    up = True
    sar, ep, af = lows[0], highs[0], step
    for i in range(1, n):
        sar = sar + af * (ep - sar)
        if up:
            sar = min(sar, lows[i - 1], lows[max(0, i - 2)])
            if lows[i] < sar:                      # flip down
                up, sar, ep, af = False, ep, lows[i], step
            elif highs[i] > ep:
                ep, af = highs[i], min(af + step, max_step)
        else:
            sar = max(sar, highs[i - 1], highs[max(0, i - 2)])
            if highs[i] > sar:                     # flip up
                up, sar, ep, af = True, ep, highs[i], step
            elif lows[i] < ep:
                ep, af = lows[i], min(af + step, max_step)
        out[i] = sar
    return out


def donchian(highs, lows, period: int = 20):
    """Donchian channels: the N-bar high and low. The original turtle breakout."""
    n = len(highs)
    up: List[Num] = [None] * n
    lo: List[Num] = [None] * n
    mid: List[Num] = [None] * n
    for i in range(period - 1, n):
        up[i] = max(highs[i - period + 1:i + 1])
        lo[i] = min(lows[i - period + 1:i + 1])
        mid[i] = (up[i] + lo[i]) / 2
    return up, mid, lo


def ichimoku(highs, lows, closes, conv: int = 9, base: int = 26, span_b: int = 52):
    """Ichimoku cloud. Returns (tenkan, kijun, span_a, span_b).

    Spans are returned unshifted: displacing them forward is a drawing decision, and
    shifting inside the calculation is how lookahead bias sneaks into a backtest.
    """
    n = len(closes)

    def mid(period):
        out: List[Num] = [None] * n
        for i in range(period - 1, n):
            out[i] = (max(highs[i - period + 1:i + 1]) + min(lows[i - period + 1:i + 1])) / 2
        return out

    tenkan, kijun, sb = mid(conv), mid(base), mid(span_b)
    span_a = [None if (a is None or b is None) else (a + b) / 2 for a, b in zip(tenkan, kijun)]
    return tenkan, kijun, span_a, sb


def aroon(highs, lows, period: int = 25):
    n = len(highs)
    up: List[Num] = [None] * n
    dn: List[Num] = [None] * n
    for i in range(period, n):
        w_h = highs[i - period:i + 1]
        w_l = lows[i - period:i + 1]
        up[i] = 100 * (period - (len(w_h) - 1 - w_h.index(max(w_h)))) / period
        dn[i] = 100 * (period - (len(w_l) - 1 - w_l.index(min(w_l)))) / period
    return up, dn


def roc(values, period: int = 12) -> List[Num]:
    return [None if (i < period or not values[i - period]) else
            (values[i] / values[i - period] - 1) * 100 for i in range(len(values))]


def trix(closes, period: int = 15) -> List[Num]:
    e3 = ema(ema(ema(closes, period), period), period)
    return [None if (i == 0 or e3[i] is None or e3[i - 1] in (None, 0)) else
            (e3[i] / e3[i - 1] - 1) * 10000 for i in range(len(e3))]


def vortex(highs, lows, closes, period: int = 14):
    n = len(closes)
    vp, vm, tr = [0.0] * n, [0.0] * n, [0.0] * n
    for i in range(1, n):
        vp[i] = abs(highs[i] - lows[i - 1])
        vm[i] = abs(lows[i] - highs[i - 1])
        tr[i] = max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
    out_p: List[Num] = [None] * n
    out_m: List[Num] = [None] * n
    for i in range(period, n):
        s = sum(tr[i - period + 1:i + 1])
        if s:
            out_p[i] = sum(vp[i - period + 1:i + 1]) / s
            out_m[i] = sum(vm[i - period + 1:i + 1]) / s
    return out_p, out_m


def awesome_oscillator(highs, lows) -> List[Num]:
    mid = [(h + l) / 2 for h, l in zip(highs, lows)]
    f, s = sma(mid, 5), sma(mid, 34)
    return [None if (a is None or b is None) else a - b for a, b in zip(f, s)]


def ultimate_oscillator(highs, lows, closes, p1=7, p2=14, p3=28) -> List[Num]:
    n = len(closes)
    bp, tr = [0.0] * n, [0.0] * n
    for i in range(1, n):
        low_or_prev = min(lows[i], closes[i - 1])
        bp[i] = closes[i] - low_or_prev
        tr[i] = max(highs[i], closes[i - 1]) - low_or_prev
    out: List[Num] = [None] * n
    for i in range(p3, n):
        def avg(p):
            t = sum(tr[i - p + 1:i + 1])
            return sum(bp[i - p + 1:i + 1]) / t if t else 0.0
        out[i] = 100 * (4 * avg(p1) + 2 * avg(p2) + avg(p3)) / 7
    return out


def choppiness(highs, lows, closes, period: int = 14) -> List[Num]:
    """Choppiness index: above ~61 is a range, below ~38 is a trend."""
    n = len(closes)
    tr = true_range(highs, lows, closes)
    out: List[Num] = [None] * n
    for i in range(period, n):
        s = sum(tr[i - period + 1:i + 1])
        hh, ll = max(highs[i - period + 1:i + 1]), min(lows[i - period + 1:i + 1])
        if s > 0 and hh > ll:
            out[i] = 100 * math.log10(s / (hh - ll)) / math.log10(period)
    return out


def force_index(closes, volumes, period: int = 13) -> List[Num]:
    raw = [0.0] + [(closes[i] - closes[i - 1]) * volumes[i] for i in range(1, len(closes))]
    return ema(raw, period)


def elder_ray(highs, lows, closes, period: int = 13):
    e = ema(closes, period)
    bull = [None if v is None else h - v for h, v in zip(highs, e)]
    bear = [None if v is None else l - v for l, v in zip(lows, e)]
    return bull, bear


def vwap_bands(highs, lows, closes, volumes, session_flags, mult: float = 2.0):
    """Session VWAP with standard-deviation bands around it."""
    n = len(closes)
    vw = vwap(highs, lows, closes, volumes, session_flags)
    up: List[Num] = [None] * n
    lo: List[Num] = [None] * n
    cum_v = cum_pv2 = 0.0
    for i in range(n):
        if session_flags[i]:
            cum_v = cum_pv2 = 0.0
        tp = (highs[i] + lows[i] + closes[i]) / 3
        cum_v += volumes[i]
        cum_pv2 += volumes[i] * tp * tp
        if vw[i] is not None and cum_v > 0:
            var = max(0.0, cum_pv2 / cum_v - vw[i] ** 2)
            sd = math.sqrt(var)
            up[i], lo[i] = vw[i] + mult * sd, vw[i] - mult * sd
    return vw, up, lo


def pivot_points(high: float, low: float, close: float) -> dict:
    """Classic floor-trader pivots from the prior period."""
    p = (high + low + close) / 3
    return {"P": p, "R1": 2 * p - low, "S1": 2 * p - high,
            "R2": p + (high - low), "S2": p - (high - low),
            "R3": high + 2 * (p - low), "S3": low - 2 * (high - p)}


def fib_levels(low: float, high: float) -> dict:
    d = high - low
    return {f"{r:g}": high - d * r for r in (0, 0.236, 0.382, 0.5, 0.618, 0.786, 1)}


def linreg_channel(values: Sequence[float], period: int = 100):
    """Least-squares line over the last `period` points, with its slope and residual."""
    ys = [v for v in values[-period:] if v is not None]
    n = len(ys)
    if n < 10:
        return None
    xs = list(range(n))
    mx, my = sum(xs) / n, sum(ys) / n
    denom = sum((x - mx) ** 2 for x in xs)
    if denom == 0:
        return None
    slope = sum((xs[i] - mx) * (ys[i] - my) for i in range(n)) / denom
    intercept = my - slope * mx
    resid = [ys[i] - (intercept + slope * xs[i]) for i in range(n)]
    sd = (sum(r * r for r in resid) / n) ** 0.5
    return {"slope": slope, "intercept": intercept, "stdev": sd,
            "value_now": intercept + slope * (n - 1),
            "slope_pct_per_bar": (slope / my * 100) if my else 0.0}


def zigzag(highs, lows, pct: float = 5.0) -> List[dict]:
    """Swing pivots that ignore moves smaller than `pct`. Useful for wave counting."""
    pivots: List[dict] = []
    if not highs:
        return pivots
    direction = 0
    last_i, last_v = 0, highs[0]
    for i in range(1, len(highs)):
        if direction >= 0:
            if highs[i] > last_v:
                last_i, last_v = i, highs[i]
            elif last_v and (last_v - lows[i]) / last_v * 100 >= pct:
                pivots.append({"index": last_i, "price": last_v, "kind": "high"})
                direction, last_i, last_v = -1, i, lows[i]
        if direction <= 0:
            if lows[i] < last_v:
                last_i, last_v = i, lows[i]
            elif last_v and (highs[i] - last_v) / last_v * 100 >= pct:
                pivots.append({"index": last_i, "price": last_v, "kind": "low"})
                direction, last_i, last_v = 1, i, highs[i]
    return pivots


# A registry so the UI can offer indicators by name without hard-coding a list.
CATALOG = {
    "sma": {"fn": sma, "needs": ["close"], "params": {"period": 20}, "group": "trend"},
    "ema": {"fn": ema, "needs": ["close"], "params": {"period": 21}, "group": "trend"},
    "wma": {"fn": wma, "needs": ["close"], "params": {"period": 20}, "group": "trend"},
    "hma": {"fn": hma, "needs": ["close"], "params": {"period": 21}, "group": "trend"},
    "dema": {"fn": dema, "needs": ["close"], "params": {"period": 21}, "group": "trend"},
    "tema": {"fn": tema, "needs": ["close"], "params": {"period": 21}, "group": "trend"},
    "supertrend": {"fn": supertrend, "needs": ["high", "low", "close"],
                   "params": {"period": 10, "multiplier": 3.0}, "group": "trend", "multi": True},
    "ichimoku": {"fn": ichimoku, "needs": ["high", "low", "close"],
                 "params": {"conv": 9, "base": 26, "span_b": 52}, "group": "trend", "multi": True},
    "parabolic_sar": {"fn": parabolic_sar, "needs": ["high", "low"],
                      "params": {"step": 0.02, "max_step": 0.2}, "group": "trend"},
    "donchian": {"fn": donchian, "needs": ["high", "low"], "params": {"period": 20},
                 "group": "trend", "multi": True},
    "linreg_channel": {"fn": linreg_channel, "needs": ["close"], "params": {"period": 100},
                       "group": "trend", "scalar": True},
    "adx": {"fn": adx, "needs": ["high", "low", "close"], "params": {"period": 14},
            "group": "strength", "multi": True},
    "aroon": {"fn": aroon, "needs": ["high", "low"], "params": {"period": 25},
              "group": "strength", "multi": True},
    "vortex": {"fn": vortex, "needs": ["high", "low", "close"], "params": {"period": 14},
               "group": "strength", "multi": True},
    "choppiness": {"fn": choppiness, "needs": ["high", "low", "close"], "params": {"period": 14},
                   "group": "strength"},
    "rsi": {"fn": rsi, "needs": ["close"], "params": {"period": 14}, "group": "momentum"},
    "stoch_rsi": {"fn": stoch_rsi, "needs": ["close"], "params": {"rsi_period": 14, "stoch_period": 14},
                  "group": "momentum", "multi": True},
    "stochastic": {"fn": stochastic, "needs": ["high", "low", "close"],
                   "params": {"k_period": 14}, "group": "momentum", "multi": True},
    "macd": {"fn": macd, "needs": ["close"], "params": {"fast": 12, "slow": 26, "signal": 9},
             "group": "momentum", "multi": True},
    "cci": {"fn": cci, "needs": ["high", "low", "close"], "params": {"period": 20}, "group": "momentum"},
    "williams_r": {"fn": williams_r, "needs": ["high", "low", "close"], "params": {"period": 14},
                   "group": "momentum"},
    "roc": {"fn": roc, "needs": ["close"], "params": {"period": 12}, "group": "momentum"},
    "trix": {"fn": trix, "needs": ["close"], "params": {"period": 15}, "group": "momentum"},
    "awesome_oscillator": {"fn": awesome_oscillator, "needs": ["high", "low"], "params": {},
                           "group": "momentum"},
    "ultimate_oscillator": {"fn": ultimate_oscillator, "needs": ["high", "low", "close"],
                            "params": {}, "group": "momentum"},
    "atr": {"fn": atr, "needs": ["high", "low", "close"], "params": {"period": 14}, "group": "volatility"},
    "bollinger": {"fn": bollinger, "needs": ["close"], "params": {"period": 20, "mult": 2.0},
                  "group": "volatility", "multi": True},
    "keltner": {"fn": keltner, "needs": ["high", "low", "close"], "params": {"period": 20, "mult": 2.0},
                "group": "volatility", "multi": True},
    "squeeze_momentum": {"fn": squeeze_momentum, "needs": ["high", "low", "close"], "params": {},
                         "group": "volatility"},
    "obv": {"fn": obv, "needs": ["close", "volume"], "params": {}, "group": "volume"},
    "mfi": {"fn": mfi, "needs": ["high", "low", "close", "volume"], "params": {"period": 14},
            "group": "volume"},
    "cmf": {"fn": cmf, "needs": ["high", "low", "close", "volume"], "params": {"period": 20},
            "group": "volume"},
    "force_index": {"fn": force_index, "needs": ["close", "volume"], "params": {"period": 13},
                    "group": "volume"},
    "relative_volume": {"fn": relative_volume, "needs": ["volume"], "params": {"period": 20},
                        "group": "volume"},
    "elder_ray": {"fn": elder_ray, "needs": ["high", "low", "close"], "params": {"period": 13},
                  "group": "volume", "multi": True},
    "zigzag": {"fn": zigzag, "needs": ["high", "low"], "params": {"pct": 5.0},
               "group": "structure", "scalar": True},
}


def catalog_names() -> List[str]:
    return sorted(CATALOG)


def compute(name: str, candles: List[dict], **params):
    """Run any catalogued indicator over a list of candle dicts."""
    spec = CATALOG.get(name)
    if not spec:
        raise KeyError(f"unknown indicator: {name}")
    cols = {k: [c[k] for c in candles] for k in ("open", "high", "low", "close", "volume")}
    args = [cols[k] for k in spec["needs"]]
    kwargs = {**spec["params"], **params}
    return spec["fn"](*args, **kwargs)
