#!/usr/bin/env python3
"""P7 4h momentum: the signals that held up in Jarvus's signal measurement (tools/measure_signals.py).

A completed 4h candle (built from 1h candles on UTC 4h boundaries) fires P7 when ANY of:
  big green candle   green, range >= 2x the prior ATR(14, 4h), body >= 60% of the range
  volume spike       green, volume >= 3x its 20-bar average, body >= 50% of the range
  big 24h rally      the 24h return crosses above 2.5x its average absolute 24h move (30 days of 4h bars)
The trade uses Jarvus's plan with the stop at 4x ATR(4h) (about twice the 1h stop) and one exit at 2R, 96h.
"""

from __future__ import annotations

HOUR = 3_600_000


def _wilder_atr(h, l, c, n=14):
    out, a = [None] * len(c), None
    for i in range(len(c)):
        tr = h[i] - l[i] if i == 0 else max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1]))
        a = tr if a is None else (a * (n - 1) + tr) / n
        out[i] = a if i >= n - 1 else None
    return out


def bars4h(t, o, h, l, c, v):
    """Completed 4h bars: list of (index of the bar's last 1h candle, o, h, l, c, v)."""
    out, cur, start = [], None, 0
    for i in range(len(t) + 1):
        k = t[i] // (4 * HOUR) if i < len(t) else None
        if k != cur:
            if cur is not None and i - start == 4:
                out.append((i - 1, o[start], max(h[start:i]), min(l[start:i]), c[i - 1], sum(v[start:i])))
            cur, start = k, i
    return out


def signals(t, o, h, l, c, v, avg_bars=180):
    """{1h index: (reasons, ATR(4h))} for every completed 4h candle that fires P7."""
    b = bars4h(t, o, h, l, c, v)
    if len(b) < 30:
        return {}
    o4, h4, l4, c4, v4 = ([x[k] for x in b] for k in range(1, 6))
    atr = _wilder_atr(h4, l4, c4)
    out = {}
    ret = [None] * len(b)
    for j in range(6, len(b)):
        ret[j] = c4[j] / c4[j - 6] - 1
    for j in range(21, len(b)):
        rng, body = h4[j] - l4[j], c4[j] - o4[j]
        why = []
        if body > 0 and atr[j - 1] and rng >= 2 * atr[j - 1] and body >= 0.6 * rng:
            why.append("big green 4h candle")
        avg_v = sum(v4[j - 20:j]) / 20
        if body > 0 and avg_v > 0 and v4[j] >= 3 * avg_v and body >= 0.5 * rng:
            why.append("4h volume spike")
        w = [abs(x) for x in ret[max(6, j - avg_bars + 1):j + 1] if x is not None]
        if len(w) >= min(avg_bars, 60) and ret[j - 1] is not None:
            m = sum(w) / len(w)
            if ret[j] > 2.5 * m and ret[j - 1] <= 2.5 * m:
                why.append("big 24h rally")
        if why and atr[j]:
            out[b[j][0]] = (why, atr[j])
    return out
