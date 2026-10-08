"""Execution algorithms (section 147: kept separate from trading signals). They split a parent order into child
orders; the OMS and the risk service see every child. Volume curves come from the instrument's OWN past bars only.

  twap(qty, slices)                 equal children at equal intervals
  vwap(qty, volume_profile)         children in proportion to the historical volume by time bucket
  pov(qty, rate, observed_volumes)  each child = rate x the volume actually traded in the previous interval
  limit_with_timeout(...)           a passive limit order that turns into a market order (or is cancelled) after N bars
"""

from __future__ import annotations

from decimal import ROUND_DOWN, Decimal

import numpy as np


def _split(qty: Decimal, weights: list[float], step: Decimal) -> list[Decimal]:
    w = np.asarray(weights, dtype=float)
    w = w / w.sum() if w.sum() > 0 else np.full(len(w), 1 / len(w))
    out = [(qty * Decimal(str(x)) / step).to_integral_value(ROUND_DOWN) * step for x in w]
    out[-1] += qty - sum(out)                          # rounding remainder goes into the last child
    return [x for x in out if x > 0]


def twap(qty: Decimal, slices: int, step: Decimal = Decimal("1")) -> list[Decimal]:
    return _split(qty, [1.0] * max(1, slices), step)


def volume_profile(ts: np.ndarray, volume: np.ndarray, bucket_ms: int, day_ms: int = 86_400_000) -> dict[int, float]:
    """Average share of a day's volume in each time-of-day bucket, from past bars."""
    tod = (ts % day_ms) // bucket_ms
    days = ts // day_ms
    prof: dict[int, list[float]] = {}
    for d in np.unique(days):
        m = days == d
        tot = volume[m].sum()
        if tot <= 0:
            continue
        for b, v in zip(tod[m], volume[m]):
            prof.setdefault(int(b), []).append(float(v / tot))
    return {k: float(np.mean(v)) for k, v in sorted(prof.items())}


def vwap(qty: Decimal, profile: dict[int, float], buckets: list[int], step: Decimal = Decimal("1")) -> list[Decimal]:
    return _split(qty, [profile.get(b, 0.0) for b in buckets], step)


def pov(remaining: Decimal, rate: float, last_interval_volume: float, step: Decimal = Decimal("1")) -> Decimal:
    q = Decimal(str(max(0.0, rate * last_interval_volume)))
    return min(remaining, (q / step).to_integral_value(ROUND_DOWN) * step)


def limit_with_timeout(side: str, last: Decimal, offset_bps: float, bars_waited: int, timeout_bars: int,
                       on_timeout: str = "market") -> dict:
    """Price for a passive order this bar, or the action at timeout ("market" or "cancel")."""
    if bars_waited >= timeout_bars:
        return {"action": on_timeout}
    off = last * Decimal(str(offset_bps)) / Decimal(10_000)
    return {"action": "limit", "price": last - off if side == "buy" else last + off}
