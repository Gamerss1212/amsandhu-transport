#!/usr/bin/env python3
"""Structure, levels, confluence and the signal card.

The order of operations here is deliberate and it is the opposite of most retail
tooling. Cost is checked early rather than last, because at retail fees it decides
more outcomes than setup selection does: cost in R equals round-trip cost divided by
stop distance, so a tight stop on a cheap-looking market can hand a third of the risk
budget to the exchange before the trade has an opinion. A setup that cannot clear the
cost gate is not a worse trade, it is not a trade.

Direction is treated as the weak signal it is. Measured on 67,585 hours, a trained
model reached AUC 0.513 on direction. So this module never reports a directional
probability. It reports structure, a confluence count, and a plan whose stop and
target are known in advance.
"""

from __future__ import annotations

from typing import Dict, List, Optional

import config
from engine import indicators as ind


def _series(candles: List[dict]):
    return ([c["open"] for c in candles], [c["high"] for c in candles],
            [c["low"] for c in candles], [c["close"] for c in candles],
            [c["volume"] for c in candles])


def structure(candles: List[dict], swing_n: int = 3) -> Optional[dict]:
    if not candles or len(candles) < 60:
        return None
    o, h, l, c, v = _series(candles)
    price = c[-1]
    atr = ind.last_value(ind.atr(h, l, c, 14))
    emas = {p: ind.last_value(ind.ema(c, p)) for p in (9, 21, 50, 200)}
    sh, sl = ind.swing_points(h, l, swing_n)
    trend = ind.classify_trend(h, l, sh, sl)
    rsi = ind.last_value(ind.rsi(c, 14))
    rvol = ind.last_value(ind.relative_volume(v, 20))

    e21, e50, e200 = emas[21], emas[50], emas[200]
    if None not in (e21, e50, e200):
        stack = ("bullish" if e21 > e50 > e200 else "bearish" if e21 < e50 < e200 else "mixed")
    else:
        stack = "insufficient history"

    look = min(len(c), 60)
    rng_hi, rng_lo = max(h[-look:]), min(l[-look:])

    levels = []
    def add(name, val):
        if val and val > 0:
            levels.append({"name": name, "price": round(val, 8),
                           "distance_pct": round((val - price) / price * 100, 2),
                           "distance_atr": round((val - price) / atr, 2) if atr else None})
    for p in (21, 50, 200):
        add(f"EMA{p}", emas[p])
    add("range high", rng_hi)
    add("range low", rng_lo)
    if sh:
        add("last swing high", h[sh[-1]])
    if sl:
        add("last swing low", l[sl[-1]])
    if atr:
        for x in ind.equal_levels([h[i] for i in sh[-8:]], 0.15 * atr):
            add("equal highs", x)
        for x in ind.equal_levels([l[i] for i in sl[-8:]], 0.15 * atr):
            add("equal lows", x)
    levels.sort(key=lambda d: abs(d["distance_pct"]))

    return {
        "price": price, "atr": atr, "atr_pct": (atr / price * 100) if atr else None,
        "trend": trend, "ema_stack": stack,
        "ema": {f"ema{p}": (round(v, 8) if v else None) for p, v in emas.items()},
        "price_vs_ema200": ("above" if (e200 and price > e200) else "below" if e200 else None),
        "dist_ema21_atr": round((price - e21) / atr, 2) if (e21 and atr) else None,
        "rsi14": round(rsi, 1) if rsi else None,
        "rvol": round(rvol, 2) if rvol else None,
        "last_swing_high": h[sh[-1]] if sh else None,
        "last_swing_low": l[sl[-1]] if sl else None,
        "range_high": rng_hi, "range_low": rng_lo,
        "position_in_range_pct": round((price - rng_lo) / (rng_hi - rng_lo) * 100, 1) if rng_hi > rng_lo else None,
        "levels": levels[:10],
    }


def cost_in_r(stop_distance_pct: float, fee_bps_per_side: float, slippage_bps: float = None) -> float:
    """Round-trip cost as a fraction of the risk on the trade. The gate that decides most outcomes."""
    slip = config.SLIPPAGE_BPS if slippage_bps is None else slippage_bps
    round_trip_pct = 2.0 * (fee_bps_per_side + slip) / 100.0
    return round_trip_pct / stop_distance_pct if stop_distance_pct > 0 else 99.0


def confluence(htf: dict, ltf: dict, gate: dict, market: dict, fee_bps: float) -> dict:
    """Count the independent reasons to take a long here. Each is worth one point.

    Long-only by design: this is a spot tool, and on spot the bearish version of every
    setup is 'stay flat', not 'short'.
    """
    rows = []

    def add(name, ok, why):
        rows.append({"factor": name, "point": 1 if ok else 0, "why": why})

    add("Volatility gate", gate and gate["label"] in ("LOUD", "COILED", "NORMAL"),
        f"gate reads {gate['label']}" if gate else "no gate reading")

    add("HTF trend", htf and htf["trend"] == "uptrend",
        f"higher timeframe is {htf['trend']}" if htf else "no higher timeframe")

    add("Above 200 EMA", ltf and ltf["price_vs_ema200"] == "above",
        f"price {ltf['price_vs_ema200']} the 200 EMA" if ltf and ltf["price_vs_ema200"] else "200 EMA unavailable")

    add("EMA stack", ltf and ltf["ema_stack"] == "bullish",
        f"EMA stack {ltf['ema_stack']}" if ltf else "no stack")

    near = None
    if ltf and ltf["levels"]:
        near = next((lv for lv in ltf["levels"] if lv["distance_atr"] is not None and abs(lv["distance_atr"]) <= 0.5), None)
    add("Location", near is not None,
        f"within 0.5 ATR of {near['name']}" if near else "no tier-1 level within 0.5 ATR (mid-range)")

    add("Volume", ltf and ltf["rvol"] is not None and ltf["rvol"] >= 1.5,
        f"RVOL {ltf['rvol']}" if ltf and ltf["rvol"] is not None else "no volume reading")

    not_stretched = ltf and ltf["dist_ema21_atr"] is not None and abs(ltf["dist_ema21_atr"]) <= 2.0
    add("Not stretched", bool(not_stretched),
        f"{ltf['dist_ema21_atr']} ATR from the 21 EMA" if ltf and ltf["dist_ema21_atr"] is not None else "unknown")

    liquid = market["usd_volume_24h"] >= config.MIN_USD_VOLUME_24H * 3
    add("Liquidity", liquid, f"${market['usd_volume_24h']/1e6:.1f}M 24h volume")

    stop_pct = (config.STOP_ATR_MULT * ltf["atr"] / ltf["price"] * 100) if (ltf and ltf["atr"]) else 0
    c_r = cost_in_r(stop_pct, fee_bps) if stop_pct else 99
    add("Cost", c_r <= 0.20, f"cost {c_r:.0%} of 1R at a {config.STOP_ATR_MULT}x ATR stop")

    score = sum(r["point"] for r in rows)
    total = len(rows)
    grade = "A+" if score >= total - 1 else "A" if score >= total - 2 else "B" if score >= total - 3 else "skip"
    return {"score": score, "max": total, "grade": grade, "rows": rows,
            "cost_r": round(c_r, 3), "stop_pct": round(stop_pct, 3)}


def signal(market: dict, htf: dict, ltf: dict, gate: dict, fee_bps: float,
           account: float = None) -> dict:
    """The plan, or the reason there is no plan."""
    account = account or config.DEFAULT_ACCOUNT
    conf = confluence(htf, ltf, gate, market, fee_bps)
    blockers: List[str] = []

    if not ltf or not ltf["atr"]:
        return {"verdict": "NO DATA", "blockers": ["not enough candles to analyse"], "confluence": conf}

    price = ltf["price"]
    stop = price - config.STOP_ATR_MULT * ltf["atr"]
    risk = price - stop
    target = price + config.TARGET_R * risk

    if conf["cost_r"] > config.MAX_COST_R:
        blockers.append(f"cost is {conf['cost_r']:.0%} of 1R, above the {config.MAX_COST_R:.0%} limit — "
                        f"fees would eat the trade at this fee tier")
    if gate and gate["label"] == "QUIET":
        blockers.append("volatility gate reads QUIET — no new positions")
    if conf["grade"] == "skip":
        blockers.append(f"confluence {conf['score']}/{conf['max']} — not enough independent reasons")
    if ltf["price_vs_ema200"] == "below" and (not htf or htf["trend"] != "uptrend"):
        blockers.append("below the 200 EMA with no higher-timeframe uptrend — spot longs fight the tape here")

    risk_pct = config.RISK_PCT_A if conf["grade"] in ("A+", "A") else config.RISK_PCT_B
    risk_amount = account * risk_pct / 100
    units = risk_amount / risk if risk > 0 else 0

    verdict = "WAIT" if blockers else "BUY"
    return {
        "verdict": verdict,
        "blockers": blockers,
        "confluence": conf,
        "entry": round(price, 8),
        "stop": round(stop, 8),
        "stop_pct": conf["stop_pct"],
        "target": round(target, 8),
        "net_r_to_target": round(config.TARGET_R - conf["cost_r"], 2),
        "risk_pct": risk_pct,
        "risk_amount": round(risk_amount, 2),
        "units": round(units, 8),
        "notional": round(units * price, 2),
        "tp1": round(price + 1.0 * risk, 8),
        "tp1_note": "sell half, then move the stop to breakeven plus fees",
        "direction_note": "Direction is the weak part of any such call: a trained model on 67,585 hours "
                          "reached AUC 0.513, barely above a coin flip. The edge, if any, is in the "
                          "volatility read, the cost gate and the defined stop — not in knowing which way.",
    }
