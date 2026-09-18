#!/usr/bin/env python3
"""The self-learning loop: grade past predictions, then trust the measurement over the model.

What "self-learning" means here, and what it does not
-----------------------------------------------------
It does not mean the app discovers a way to predict direction. Direction on short
horizons is close to unforecastable and no amount of logging changes that; if
anything, this loop is the fastest way to *demonstrate* it, because the measured
direction accuracy will sit near 50% no matter how confident any signal looked.

What it does mean is calibration. The volatility gate emits a score between 0 and 1
that was hand-designed, so its numbers are arbitrary until proven otherwise. This
module takes every score the app has ever emitted, checks what actually happened
afterwards, and builds a reliability curve: of the times this app said 0.8, how often
did a big move follow? After enough samples the app stops showing its own raw score
and starts showing that measured rate instead. It learns how much to believe itself.

That is a real and unusually honest form of learning. A system that says 0.8 and is
right 55% of the time is not improved by tuning the 0.8; it is improved by reporting
55%.
"""

from __future__ import annotations

import statistics
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

import config
from engine import marketdata, store


# --- grading ----------------------------------------------------------------

def forward_outcome(symbol: str, venue: str, made_at: datetime, horizon_h: int) -> Optional[dict]:
    """What the market actually did between the prediction and its horizon."""
    candles = marketdata.candles(symbol, venue or "okx", "1h", 300)
    if not candles:
        return None
    end = made_at + timedelta(hours=horizon_h)
    window = [c for c in candles if made_at <= c["ts"] <= end]
    if len(window) < max(2, horizon_h // 3):
        return None
    hi = max(c["high"] for c in window)
    lo = min(c["low"] for c in window)
    first_open = window[0]["open"]
    last_close = window[-1]["close"]
    if first_open <= 0:
        return None
    return {
        "realized_range_pct": (hi - lo) / first_open * 100,
        "realized_change_pct": (last_close - first_open) / first_open * 100,
        "bars": len(window),
    }


def resolve_due(limit: int = 100) -> Dict[str, int]:
    """Grade every prediction whose horizon has passed. Safe to call repeatedly."""
    rows = store.due_for_resolution(limit)
    graded = failed = 0
    for r in rows:
        made = store.parse_iso(r["made_at"])
        out = forward_outcome(r["symbol"], r["venue"], made, config.RESOLVE_HORIZON_H)
        if not out:
            store.resolve(r["id"], None, None, None, error="no forward candles available")
            failed += 1
            continue
        store.resolve(r["id"], out["realized_range_pct"], out["realized_change_pct"],
                      r["big_move_threshold"])
        graded += 1
    return {"graded": graded, "failed": failed, "remaining": max(0, len(rows) - limit)}


# --- calibration ------------------------------------------------------------

BUCKETS = [(0.0, 0.2), (0.2, 0.4), (0.4, 0.6), (0.6, 0.8), (0.8, 1.01)]


def calibration() -> dict:
    """Reliability curve for the volatility gate, plus the direction reality check."""
    rows = store.resolved()
    n = len(rows)
    if n == 0:
        return {"samples": 0, "ready": False,
                "note": "No graded predictions yet. Run scans, then let the horizon pass; "
                        "the app grades itself automatically."}

    buckets = []
    for lo, hi in BUCKETS:
        sel = [r for r in rows if r["blow_score"] is not None and lo <= r["blow_score"] < hi]
        if not sel:
            buckets.append({"range": f"{lo:.1f}-{min(hi,1.0):.1f}", "n": 0,
                            "big_move_rate": None, "mean_score": None})
            continue
        big = sum(1 for r in sel if r["big_move"])
        buckets.append({
            "range": f"{lo:.1f}-{min(hi,1.0):.1f}", "n": len(sel),
            "big_move_rate": round(100 * big / len(sel), 1),
            "mean_score": round(statistics.fmean(r["blow_score"] for r in sel), 3),
        })

    by_label = {}
    for label in ("LOUD", "COILED", "NORMAL", "QUIET"):
        sel = [r for r in rows if r["gate_label"] == label]
        if sel:
            by_label[label] = {
                "n": len(sel),
                "big_move_rate": round(100 * sum(1 for r in sel if r["big_move"]) / len(sel), 1),
                "median_realized_range_pct": round(statistics.median(
                    [r["realized_range_pct"] for r in sel if r["realized_range_pct"] is not None] or [0]), 2),
            }

    ups = [r for r in rows if r["direction_up"] is not None]
    direction_rate = round(100 * sum(1 for r in ups if r["direction_up"]) / len(ups), 1) if ups else None

    buy = [r for r in rows if r["verdict"] == "BUY" and r["direction_up"] is not None]
    buy_up = round(100 * sum(1 for r in buy if r["direction_up"]) / len(buy), 1) if buy else None

    return {
        "samples": n,
        "ready": n >= config.MIN_SAMPLES_FOR_CALIBRATION,
        "min_samples": config.MIN_SAMPLES_FOR_CALIBRATION,
        "horizon_hours": config.RESOLVE_HORIZON_H,
        "buckets": buckets,
        "by_label": by_label,
        "direction_up_rate": direction_rate,
        "buy_signal_up_rate": buy_up,
        "direction_note": (
            "This is the honesty check, not a target. A coin flip is 50%. If the BUY signals' "
            "up-rate sits near 50% that is the expected result and matches the published "
            "measurement (AUC 0.513 on 67,585 hours); it is the reason this app ranks markets by "
            "volatility rather than by direction."),
    }


def calibrated_probability(blow_score: float) -> Optional[dict]:
    """Translate a raw gate score into this app's own measured big-move rate.

    Returns None until there is enough evidence, because an uncalibrated number
    dressed up as a probability is worse than no number at all.
    """
    cal = calibration()
    if not cal.get("ready"):
        return None
    for (lo, hi), b in zip(BUCKETS, cal["buckets"]):
        if lo <= blow_score < hi:
            if b["n"] >= 5 and b["big_move_rate"] is not None:
                return {"probability_pct": b["big_move_rate"], "sample": b["n"], "bucket": b["range"],
                        "source": "measured on this app's own graded predictions"}
            return None
    return None


def summary() -> dict:
    c = store.counts()
    cal = calibration()
    return {"counts": c, "calibration": cal}
