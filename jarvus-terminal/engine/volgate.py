#!/usr/bin/env python3
"""The volatility gate: which markets are most likely to make a big move next.

Why this is the headline feature rather than a direction forecast
----------------------------------------------------------------
Direction on short horizons is close to unforecastable. Measured on 67,585 hours of
BTC data, a 77-feature model reached AUC 0.513 on direction, where 0.500 is a coin
flip. The same model on the question "will the next 12 hours be a big move" reached
0.716, and "will it go dead" reached 0.747. Volatility is forecastable because it
clusters: loud hours follow loud hours and quiet follows quiet. Direction does not
cluster that way.

So "which markets are about to blow" is a question that can be answered honestly,
and "which way" is not. This module answers the first one and refuses the second.

What this gate is, precisely
----------------------------
It is a **transparent heuristic** built from the same feature families the trained
model used, not the trained model itself. It therefore does not inherit that model's
82-85% accuracy, and this app never claims it does. Instead every reading is written
to the database and scored against what actually happened, so the number shown in the
Learning tab is this gate's own measured hit rate on your data. Trust that one.

Two distinct ways a market becomes loud, which the gate reports separately:
  * EXPANSION  - it is already moving: ATR rising, volume surging, ranges widening.
                 Volatility clustering says this tends to persist.
  * COMPRESSION- it is unusually still: bands at multi-day narrows, volume drained.
                 Stillness resolves into movement, direction unknown.
A market can score high on either. They imply different trades, so they are not
averaged into one number.

Both of those are *relative* measures: they ask whether a market is unusual against
its own recent history. On their own they mislabel a market that has been violently
volatile for days as calm, because nothing is changing. So a third, *absolute* term is
carried alongside them:
  * ENERGY     - how far this market actually travels per bar right now, as a share of
                 price. A coin with 3% hourly ATR will produce large moves whether or
                 not it is accelerating, and that is what "likely to blow" means to
                 someone looking for a big move to trade.
The headline score blends absolute energy with the relative signal, because a market
worth looking at is either already fast, speeding up, or wound tight.
"""

from __future__ import annotations

import math
import statistics
from typing import Dict, List, Optional

from engine import indicators as ind


def _series(candles: List[dict]):
    return ([c["open"] for c in candles], [c["high"] for c in candles],
            [c["low"] for c in candles], [c["close"] for c in candles],
            [c["volume"] for c in candles])


def _pct_rank(values: List[Optional[float]], current: Optional[float]) -> Optional[float]:
    vals = [v for v in values if v is not None]
    if not vals or current is None:
        return None
    return 100.0 * sum(1 for v in vals if v < current) / len(vals)


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def features(candles: List[dict]) -> Optional[Dict[str, Optional[float]]]:
    """Every input the gate uses, exposed so a reading can always be explained."""
    if not candles or len(candles) < 60:
        return None
    o, h, l, c, v = _series(candles)
    n = len(c)

    atr = ind.atr(h, l, c, 14)
    atr_now = ind.last_value(atr)
    if not atr_now or c[-1] <= 0:
        return None
    atr_hist = [a for a in atr[-100:] if a is not None]
    atr_mean = statistics.fmean(atr_hist) if atr_hist else None

    bb_mid, bb_up, bb_lo, bb_w = ind.bollinger(c, 20, 2.0)
    w_now = ind.last_value(bb_w)

    # realised volatility: stdev of log-ish returns over a short and a long window
    rets = [(c[i] / c[i - 1] - 1.0) for i in range(1, n) if c[i - 1] > 0]
    rv_short = statistics.pstdev(rets[-24:]) if len(rets) >= 24 else None
    rv_long = statistics.pstdev(rets[-168:]) if len(rets) >= 168 else (
        statistics.pstdev(rets) if len(rets) >= 30 else None)

    vol_recent = statistics.fmean(v[-6:]) if n >= 6 else None
    vol_base = statistics.fmean(v[-50:]) if n >= 50 else None

    last_range = h[-1] - l[-1]
    recent_ranges = [h[i] - l[i] for i in range(max(0, n - 20), n)]

    return {
        "atr": atr_now,
        "atr_pct": atr_now / c[-1] * 100,
        "atr_ratio": (atr_now / atr_mean) if atr_mean else None,
        "bb_bandwidth_pct": (w_now * 100) if w_now else None,
        "bb_bandwidth_percentile": _pct_rank(bb_w[-100:], w_now),
        "rv_short": rv_short, "rv_long": rv_long,
        "rv_ratio": (rv_short / rv_long) if (rv_short and rv_long) else None,
        "rvol_recent": (vol_recent / vol_base) if (vol_recent and vol_base) else None,
        "last_range_atr": (last_range / atr_now) if atr_now else None,
        "range_percentile": _pct_rank(recent_ranges, last_range),
        "bars": n,
    }


def score(candles: List[dict]) -> Optional[dict]:
    f = features(candles)
    if not f:
        return None

    # --- ENERGY: absolute travel per bar, independent of any trend in volatility.
    # Log-scaled because crypto hourly ATR spans two orders of magnitude, from a
    # sleepy major near 0.25% to a meme in flight above 8%. A linear scale saturates
    # immediately and stops telling the fast markets apart, which is exactly the
    # comparison this ranking exists to make. Maps 0.25%/bar -> 0, 10%/bar -> 1.
    energy = 0.0
    if f["atr_pct"]:
        energy = _clamp01(math.log(max(f["atr_pct"], 0.05) / 0.25) / math.log(10.0 / 0.25))

    # --- EXPANSION: already moving, and movement persists -------------------
    # Each term is scaled so that "normal" sits near 0 and a clear signal near 1.
    exp_terms = {}
    if f["atr_ratio"] is not None:
        exp_terms["atr_rising"] = _clamp01((f["atr_ratio"] - 1.0) / 0.6)
    if f["rv_ratio"] is not None:
        exp_terms["realised_vol_rising"] = _clamp01((f["rv_ratio"] - 1.0) / 0.8)
    if f["rvol_recent"] is not None:
        exp_terms["volume_surge"] = _clamp01((f["rvol_recent"] - 1.0) / 1.5)
    if f["last_range_atr"] is not None:
        exp_terms["wide_last_bar"] = _clamp01((f["last_range_atr"] - 1.0) / 1.5)
    expansion = statistics.fmean(exp_terms.values()) if exp_terms else 0.0

    # --- COMPRESSION: unusually still, and stillness resolves ---------------
    comp_terms = {}
    if f["bb_bandwidth_percentile"] is not None:
        comp_terms["bands_narrow"] = _clamp01((25.0 - f["bb_bandwidth_percentile"]) / 25.0)
    if f["atr_ratio"] is not None:
        comp_terms["atr_falling"] = _clamp01((1.0 - f["atr_ratio"]) / 0.4)
    if f["rvol_recent"] is not None:
        comp_terms["volume_drained"] = _clamp01((1.0 - f["rvol_recent"]) / 0.5)
    if f["range_percentile"] is not None:
        comp_terms["narrow_bars"] = _clamp01((25.0 - f["range_percentile"]) / 25.0)
    compression = statistics.fmean(comp_terms.values()) if comp_terms else 0.0

    # A market cannot be strongly both; the dominant one names the state. Energy is
    # checked first because a market that is already fast is loud whatever its trend.
    if compression >= 0.55 and compression > expansion:
        label, driver = "COILED", "compression"
    elif expansion >= 0.55 or (energy >= 0.45 and expansion >= 0.30):
        label, driver = "LOUD", "expansion"
    elif energy >= 0.55:
        label, driver = "LOUD", "energy"
    elif energy < 0.22 and expansion < 0.30 and compression < 0.40:
        label, driver = "QUIET", "neither"
    else:
        label, driver = "NORMAL", "mixed"

    # One number for ranking "most likely to move soon". Absolute speed and the
    # relative signal each carry half: a fast market and a coiled one both qualify,
    # for different reasons, and a market that is both ranks highest.
    relative = max(expansion, compression * 0.85)   # compression is slower to pay out
    blow_score = 0.5 * energy + 0.5 * relative

    return {
        "label": label, "driver": driver,
        "blow_score": round(blow_score, 4),
        "energy": round(energy, 4),
        "expansion": round(expansion, 4),
        "compression": round(compression, 4),
        "expansion_terms": {k: round(v, 3) for k, v in exp_terms.items()},
        "compression_terms": {k: round(v, 3) for k, v in comp_terms.items()},
        "features": {k: (round(v, 6) if isinstance(v, float) else v) for k, v in f.items()},
        "explain": explain(label, driver, exp_terms, comp_terms, f, energy),
    }


def explain(label: str, driver: str, exp_terms: dict, comp_terms: dict, f: dict, energy: float = 0.0) -> str:
    speed = f"Currently travels {f['atr_pct']:.2f}% per bar." if f.get("atr_pct") else ""
    bits = []
    if driver == "energy":
        return f"{speed} Fast in absolute terms without accelerating — big moves are normal here right now. Direction unknown."
    if driver == "expansion":
        top = sorted(exp_terms.items(), key=lambda kv: -kv[1])[:2]
        names = {"atr_rising": f"ATR {f['atr_ratio']:.2f}x its recent average" if f.get("atr_ratio") else "ATR rising",
                 "realised_vol_rising": f"24-bar volatility {f['rv_ratio']:.2f}x the longer window" if f.get("rv_ratio") else "realised volatility rising",
                 "volume_surge": f"volume {f['rvol_recent']:.2f}x normal" if f.get("rvol_recent") else "volume surging",
                 "wide_last_bar": f"last bar {f['last_range_atr']:.2f}x ATR" if f.get("last_range_atr") else "wide bars"}
        bits = [names.get(k, k) for k, _ in top]
        return "Already moving: " + ", ".join(bits) + f". {speed} Volatility clusters, so expect follow-through — direction unknown."
    if driver == "compression":
        top = sorted(comp_terms.items(), key=lambda kv: -kv[1])[:2]
        names = {"bands_narrow": f"Bollinger width in the {f['bb_bandwidth_percentile']:.0f}th percentile" if f.get("bb_bandwidth_percentile") is not None else "bands narrow",
                 "atr_falling": "ATR below its recent average",
                 "volume_drained": f"volume {f['rvol_recent']:.2f}x normal" if f.get("rvol_recent") else "volume drained",
                 "narrow_bars": "recent bars unusually narrow"}
        bits = [names.get(k, k) for k, _ in top]
        return "Coiled: " + ", ".join(bits) + ". Compression resolves into expansion — timing uncertain, direction unknown."
    if label == "QUIET":
        return f"Dead. {speed} Costs are fixed and range is not; this is where accounts bleed out one fee at a time."
    return f"Mixed signals. {speed} No strong volatility read either way."
