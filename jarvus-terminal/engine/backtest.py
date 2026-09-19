#!/usr/bin/env python3
"""Backtest every strategy on every market, and turn the results into swarm weights.

Why the weights come only from out-of-sample results
----------------------------------------------------
Any strategy can be made to look good on the data used to build it. With 65
strategies on offer, ranking them by how they did on all of history and then
trusting the winner is not research, it is picking the luckiest of 65 draws. So
history is cut in two: the strategy never gets credit for the first part, and its
weight is set purely by how it did on the part that came after.

This is also the honest form of "self-learning". The app does not tune its strategies
until they look profitable. It measures them, gives more say to the ones that held up
on data they were not built on, mutes the ones that did not, and re-measures as new
data arrives. Learning here means changing how much to believe something, which is
the only kind of learning the evidence supports.

Fills are pessimistic throughout: entry at the next bar's open plus slippage, and
when a bar touches both the stop and the target the stop is taken.
"""

from __future__ import annotations

import statistics
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Optional

import config
from engine import strategies as S


def simulate(candles: List[dict], spec: S.StrategySpec, *, stop_atr: float = None,
             target_r: float = None, horizon: int = 96, fee_bps: float = None,
             slip_bps: float = None, warmup: int = 210,
             cache: "S.SeriesCache" = None) -> List[dict]:
    """Walk the history once, taking every trade this strategy would have taken."""
    stop_atr = stop_atr if stop_atr is not None else config.STOP_ATR_MULT
    target_r = target_r if target_r is not None else config.TARGET_R
    fee_bps = fee_bps if fee_bps is not None else config.FEE_TIERS.get(config.DEFAULT_FEE_TIER, 26.0)
    slip_bps = slip_bps if slip_bps is not None else config.SLIPPAGE_BPS
    fee, slip = fee_bps / 10000.0, slip_bps / 10000.0

    n = len(candles)
    trades: List[dict] = []
    if n < warmup + 30:
        return trades

    # One indicator computation for the whole market, reused by every bar below.
    cache = cache or S.SeriesCache(candles)
    i = warmup
    while i < n - 2:
        # `at` makes every series a prefix view, so the strategy physically cannot
        # read bar i+1 — the bar its own entry will be filled on.
        ctx = S.Ctx(candles, "backtest", cache=cache, at=i)
        sig = S.evaluate(spec, ctx)
        if not sig or sig.direction != "long":
            i += 1
            continue
        a = ctx.atr
        if not a or a <= 0:
            i += 1
            continue

        entry = candles[i + 1]["open"] * (1 + slip)
        stop = entry - stop_atr * a
        risk = entry - stop
        if risk <= 0:
            i += 1
            continue
        target = entry + target_r * risk

        exit_i, exit_px, reason = None, None, None
        for j in range(i + 1, min(n, i + 1 + horizon)):
            if candles[j]["low"] <= stop:              # pessimistic: stop wins ties
                exit_i, exit_px, reason = j, stop * (1 - slip), "stop"
                break
            if candles[j]["high"] >= target:
                exit_i, exit_px, reason = j, target, "target"
                break
        if exit_i is None:
            exit_i = min(n - 1, i + horizon)
            exit_px, reason = candles[exit_i]["close"] * (1 - slip), "time"

        cost_r = (entry + exit_px) * fee / risk
        r = (exit_px - entry) / risk - cost_r
        trades.append({"i": i, "t": candles[i]["ts"], "entry": entry, "exit": exit_px,
                       "r": round(r, 4), "reason": reason, "bars": exit_i - i})
        i = exit_i + 1                                  # one position at a time
    return trades


def stats(trades: List[dict]) -> Dict:
    n = len(trades)
    if n == 0:
        return {"n": 0}
    rs = [t["r"] for t in trades]
    wins = [r for r in rs if r > 0]
    losses = [r for r in rs if r <= 0]
    gw, gl = sum(wins), -sum(losses)
    eq = peak = dd = 0.0
    for r in rs:
        eq += r
        peak = max(peak, eq)
        dd = max(dd, peak - eq)
    return {
        "n": n,
        "win_rate": round(100 * len(wins) / n, 1),
        "expectancy": round(sum(rs) / n, 4),
        "total_r": round(sum(rs), 2),
        "avg_win": round(gw / len(wins), 3) if wins else 0.0,
        "avg_loss": round(-gl / len(losses), 3) if losses else 0.0,
        "profit_factor": round(gw / gl, 2) if gl > 0 else None,
        "max_dd_r": round(dd, 2),
        "stdev": round(statistics.pstdev(rs), 3) if n > 1 else 0.0,
    }


def walk_forward(candles: List[dict], spec: S.StrategySpec, split: float = 0.6, **kw) -> Dict:
    """Backtest once, then report the two halves separately.

    The split is on *time*, not on trades, so the out-of-sample period is genuinely
    the future relative to the in-sample one.
    """
    trades = simulate(candles, spec, **kw)
    if not trades:
        return {"n": 0, "in_sample": {"n": 0}, "out_sample": {"n": 0}, "all": {"n": 0}}
    cut_index = int(len(candles) * split)
    ins = [t for t in trades if t["i"] < cut_index]
    oos = [t for t in trades if t["i"] >= cut_index]
    return {"n": len(trades), "all": stats(trades), "in_sample": stats(ins), "out_sample": stats(oos)}


CONTROL_NAMES = ("_control_random_entry", "_control_always_long")


def weight_from(result: Dict, min_trades: int = 8, control_expectancy: float = 0.0) -> Optional[float]:
    """Turn an out-of-sample record into how much this strategy's vote should count.

    The number that matters is not expectancy, it is expectancy *above the control*.
    In a bull market a coin-flip entry makes money, so judging long-only strategies
    on raw expectancy rewards them for the weather. Measured on 14 markets over
    mid-2026, buying every twelfth bar with no analysis at all returned +0.18R out of
    sample and only 22 of 64 strategies beat it — meaning two thirds of them were
    worse than not thinking. Subtracting the control is what separates a strategy
    from a rising tide.

    Returns None when there is not enough evidence either way, which the swarm shows
    as "unweighted" rather than quietly treating as average. A strategy that failed
    to beat the control gets zero: muted for that market, not merely demoted.
    """
    oos = result.get("out_sample") or {}
    if oos.get("n", 0) < min_trades:
        return None
    excess = oos.get("expectancy", 0.0) - control_expectancy
    if excess <= 0:
        return 0.0
    # +0.1R of excess over the control is already a good strategy; cap so none dominates
    return round(min(2.0, 0.5 + excess * 5.0), 3)


def run_grid(markets: List[Dict], candles_by_symbol: Dict[str, List[dict]],
             specs: List[S.StrategySpec] = None, split: float = 0.6,
             max_workers: int = None, **kw) -> Dict:
    """Every strategy against every market. This is the expensive one."""
    t0 = time.time()
    specs = specs if specs is not None else S.all_strategies()
    caches: Dict[str, S.SeriesCache] = {}
    jobs = []
    for m in markets:
        c = candles_by_symbol.get(m["symbol"])
        if c and len(c) >= 300:
            # built once per market, then shared by all 65 strategies
            caches[m["symbol"]] = S.SeriesCache(c)
            for spec in specs:
                jobs.append((m["symbol"], spec, c))

    def work(job):
        symbol, spec, c = job
        try:
            res = walk_forward(c, spec, split=split, cache=caches.get(symbol), **kw)
        except Exception:                               # noqa: BLE001
            return None
        return {"symbol": symbol, "strategy": spec.name, "group": spec.group, **res}

    rows: List[Dict] = []
    if jobs:
        with ThreadPoolExecutor(max_workers=max_workers or config.MAX_WORKERS) as pool:
            for r in pool.map(work, jobs):
                if r and r["n"] > 0:
                    rows.append(r)

    # The control's own out-of-sample record sets the bar every strategy is judged
    # against, per market, so a market that simply went up does not flatter everything
    # traded on it.
    control_by_symbol: Dict[str, float] = {}
    for r in rows:
        if r["strategy"] in CONTROL_NAMES:
            oos = r.get("out_sample") or {}
            if oos.get("n", 0) >= 8:
                prev = control_by_symbol.get(r["symbol"])
                e = oos.get("expectancy", 0.0)
                control_by_symbol[r["symbol"]] = e if prev is None else max(prev, e)

    for r in rows:
        r["control_expectancy"] = round(control_by_symbol.get(r["symbol"], 0.0), 4)
        r["weight"] = (None if r["strategy"] in CONTROL_NAMES
                       else weight_from(r, control_expectancy=control_by_symbol.get(r["symbol"], 0.0)))
        oos = r.get("out_sample") or {}
        if oos.get("n") and r["strategy"] not in CONTROL_NAMES:
            # a control is the baseline, so measuring its excess over itself is noise
            r["excess_over_control"] = round(oos.get("expectancy", 0.0) - r["control_expectancy"], 4)

    # Per-strategy summary pooled across markets, which is a larger and therefore
    # more trustworthy sample than any single market's record.
    by_strategy: Dict[str, Dict] = {}
    for r in rows:
        e = by_strategy.setdefault(r["strategy"], {"strategy": r["strategy"], "group": r["group"],
                                                   "markets": 0, "trades": 0, "oos_trades": 0,
                                                   "oos_expectancy_sum": 0.0, "total_r": 0.0})
        e["markets"] += 1
        e["trades"] += r["n"]
        oos = r.get("out_sample") or {}
        if oos.get("n"):
            e["oos_trades"] += oos["n"]
            e["oos_expectancy_sum"] += oos["expectancy"] * oos["n"]
            e["excess_sum"] = e.get("excess_sum", 0.0) + (r.get("excess_over_control") or 0.0) * oos["n"]
            e["total_r"] += oos.get("total_r", 0.0)
    for e in by_strategy.values():
        e["oos_expectancy"] = round(e["oos_expectancy_sum"] / e["oos_trades"], 4) if e["oos_trades"] else None
        e["excess_over_control"] = round(e.get("excess_sum", 0.0) / e["oos_trades"], 4) if e["oos_trades"] else None
        e.pop("oos_expectancy_sum", None)
        e.pop("excess_sum", None)
        e["total_r"] = round(e["total_r"], 2)
        e["beats_control"] = bool(e["excess_over_control"] and e["excess_over_control"] > 0)

    # ranked by excess over the control, because that is the question
    ranked = sorted(by_strategy.values(),
                    key=lambda e: (e["excess_over_control"] is None, -(e["excess_over_control"] or 0)))

    beat = sum(1 for e in ranked if e["beats_control"])
    judged = sum(1 for e in ranked if e["excess_over_control"] is not None
                 and e["strategy"] not in CONTROL_NAMES)
    return {
        "rows": rows,
        "by_strategy": ranked,
        "control_by_symbol": control_by_symbol,
        "strategies_beating_control": beat,
        "strategies_judged": judged,
        "combinations_tested": len(jobs),
        "combinations_with_trades": len(rows),
        "total_trades_simulated": sum(r["n"] for r in rows),
        "elapsed_s": round(time.time() - t0, 2),
        "split": split,
    }


def weights_by_symbol(rows: List[Dict]) -> Dict[str, Dict[str, float]]:
    out: Dict[str, Dict[str, float]] = {}
    for r in rows:
        if r.get("weight") is not None:
            out.setdefault(r["symbol"], {})[r["strategy"]] = r["weight"]
    return out
