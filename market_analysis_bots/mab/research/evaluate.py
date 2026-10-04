"""Walk-forward evaluation of one strategy on one market, with baselines and uncertainty.

Protocol (the same rules the batch evaluation uses, applied to one research job):
* Parameters are fixed before the data is seen; nothing is fitted or optimised inside a job.
* Chronological split: train 60% | validation 20% | test 20%, with a one-day embargo between segments. The
  test segment is the untouched, most recent data; its result is what a verdict rests on.
* Walk-forward: the whole period is also cut into k consecutive folds; the share of positive folds shows whether
  a result is consistent or carried by one stretch of time.
* No leakage: every rule and indicator is causal (tested in tests/test_platform.py); decisions are made at a bar's
  close and filled at the next bar's open (one bar of latency), never at a price already seen.
* Realistic costs: fees (the chosen fee profile or the venue's), assumed spread and slippage by liquidity tier
  (doubled for stops), partial fills when an order exceeds a share of the bar's volume (liquidity limit), and a
  cost-sensitivity rerun at twice the costs.
* Baselines on the test segment: no trade (0R), buy-and-hold over the same period, and random entries with the
  strategy's own exits (same number of trades, many draws): a strategy must beat randomly timed entries, not just
  zero, to show timing skill.
* Uncertainty: bootstrap 95% interval of the expectancy per trade, t statistic, sample size, maximum drawdown,
  expectancy after costs. A single job is one test among many ever run: the verdict says so.
"""

from __future__ import annotations

import math
import random
from dataclasses import replace
from typing import Dict, List, Optional

from mab import backtest, metrics as M
from mab.clock import DAY
from mab.evaluate import boundaries
from mab.frame import Frame
from mab.strategy import RuleSeries, compile_strategy, evaluate as eval_rules

MIN_TEST_TRADES = 30


def _stats(rs: List[float], seed: int = 7) -> dict:
    n = len(rs)
    if not n:
        return {"trades": 0, "expectancy_r": None, "ci95": None, "t": None, "p_one_sided": None, "win_rate": None}
    mean = sum(rs) / n
    sd = M._std(rs)
    t = mean / (sd / math.sqrt(n)) if sd else None
    return {"trades": n, "expectancy_r": round(mean, 4), "ci95": M.bootstrap_ci(rs, seed=seed),
            "t": round(t, 3) if t is not None else None, "p_one_sided": M.p_value_from_t(t) if n >= 10 else None,
            "win_rate": round(sum(1 for x in rs if x > 0) / n, 4), "sd_r": round(sd, 4) if sd else None}


def _seg(res) -> dict:
    rs = [t.r for t in res.trades if t.r is not None]
    m = res.metrics
    out = _stats(rs)
    out.update({"net_return": m.get("net_return"), "max_drawdown": m.get("max_drawdown"),
                "profit_factor": m.get("profit_factor"), "fees": m.get("fees"), "sharpe": m.get("sharpe"),
                "avg_bars_held": m.get("avg_bars_held"), "start": res.start, "end": res.end, "skipped": res.skipped})
    return out


def random_baseline(c, rs: RuleSeries, frame: Frame, start: int, end: int, n_trades: int, draws: int, seed: int,
                    venue: str, fees, cost_mult: float, participation, can_short: bool) -> dict:
    """Expectancy of randomly timed long entries with the strategy's own stop, target and time rules."""
    if n_trades <= 0:
        return {"draws": 0, "expectancy_r": None}
    idx = [i for i, t in enumerate(frame.t) if start <= t < end and frame.sess[i] >= 0]
    if len(idx) < n_trades * 2:
        return {"draws": 0, "expectancy_r": None, "note": "too few bars"}
    rnd = random.Random(seed)
    vals = {k: v for k, v in rs.values.items() if not k.startswith(("entry_", "filter_"))}
    means = []
    for _ in range(draws):
        pick = set(rnd.sample(idx, n_trades))
        el = [i in pick for i in range(frame.n)]
        rr = replace(rs, values=dict(vals, entry_long=el))
        res = backtest.run(c, frame, venue, cost_mult=cost_mult, start=start, end=end, period="random", rs=rr,
                           can_short=can_short, fees=fees, max_participation=participation)
        r = [t.r for t in res.trades if t.r is not None]
        if r:
            means.append(sum(r) / len(r))
    means.sort()
    if not means:
        return {"draws": 0, "expectancy_r": None}
    return {"draws": len(means), "expectancy_r": round(sum(means) / len(means), 4),
            "p05": round(means[int(0.05 * len(means))], 4), "p50": round(means[len(means) // 2], 4),
            "p95": round(means[min(len(means) - 1, int(0.95 * len(means)))], 4), "values": [round(x, 4) for x in means]}


def run(definition: dict, frame: Frame, venue: str, fees: Optional[dict] = None, cost_mult: float = 1.0,
        participation: Optional[float] = 0.05, k_folds: int = 5, draws: int = 100, seed: int = 7,
        can_short: bool = False, progress=None, resolver=None) -> dict:
    step = progress or (lambda frac, msg: None)
    c = compile_strategy(definition, None, frame.asset_type)
    step(0.05, "evaluating rules on the whole history (causal)")
    rs = eval_rules(c, frame, resolver)
    b = boundaries(frame)
    segs = {}
    for k, (name, (s, e)) in enumerate(b.items()):
        step(0.1 + 0.2 * k, f"{name} segment")
        segs[name] = _seg(backtest.run(c, frame, venue, cost_mult=cost_mult, start=s, end=e, period=name, rs=rs,
                                       can_short=can_short, fees=fees, max_participation=participation))
    t0, t1 = frame.t[0], frame.t[-1] + frame.step
    w = (t1 - t0) // k_folds
    folds = []
    for k in range(k_folds):
        s, e = t0 + k * w + (DAY if k else 0), t0 + (k + 1) * w
        r = backtest.run(c, frame, venue, cost_mult=cost_mult, start=s, end=e, period=f"fold{k + 1}", rs=rs,
                         can_short=can_short, fees=fees, max_participation=participation)
        folds.append({"fold": k + 1, "start": s, "end": e, **{kk: v for kk, v in _seg(r).items() if kk != "skipped"}})
    step(0.7, "cost sensitivity (2x costs) and gross (no costs)")
    ts, te = b["test"]
    stress = _seg(backtest.run(c, frame, venue, cost_mult=cost_mult * 2, start=ts, end=te, period="test_2x", rs=rs,
                               can_short=can_short, fees=fees, max_participation=participation))
    gross = _seg(backtest.run(c, frame, venue, cost_mult=0.0, start=ts, end=te, period="test_gross", rs=rs,
                              can_short=can_short, fees={"taker": 0.0, "maker": 0.0} if fees is not None else None,
                              max_participation=participation))
    step(0.8, f"random-entry baseline ({draws} draws)")
    i0 = next((i for i, t in enumerate(frame.t) if t >= ts), frame.n - 1)
    i1 = next((i for i, t in enumerate(frame.t) if t >= te), frame.n) - 1
    bh = (frame.c[i1] / frame.o[i0] - 1) if frame.n and i1 > i0 else None
    rnd = random_baseline(c, rs, frame, ts, te, segs["test"]["trades"], draws, seed, venue, fees, cost_mult,
                          participation, can_short)
    test = segs["test"]
    val = segs["validation"]
    beats_random = (test["expectancy_r"] is not None and rnd.get("p95") is not None and test["expectancy_r"] > rnd["p95"])
    ci = test["ci95"]
    checks = {
        "enough_test_trades": test["trades"] >= MIN_TEST_TRADES,
        "test_positive_after_costs": (test["expectancy_r"] or -1) > 0,
        "test_ci_above_zero": bool(ci and ci[0] > 0),
        "validation_positive": (val["expectancy_r"] or -1) > 0,
        "survives_double_costs": (stress["expectancy_r"] or -1) > 0,
        "beats_random_entries": beats_random,
        "consistent_folds": sum(1 for f in folds if (f["expectancy_r"] or -1) > 0) >= math.ceil(0.6 * k_folds),
    }
    if all(checks.values()):
        verdict = "passes every check on this data (one test among many: confirm on paper before any live use)"
    elif checks["test_positive_after_costs"] and checks["enough_test_trades"]:
        verdict = "positive on the untouched test but not conclusive: " + ", ".join(k.replace("_", " ") for k, v in checks.items() if not v)
    elif not checks["enough_test_trades"]:
        verdict = f"not enough trades to judge ({test['trades']} in the test segment; needs {MIN_TEST_TRADES})"
    else:
        verdict = "no edge shown after costs on the untouched test"
    step(1.0, "done")
    return {"strategy_id": definition.get("id"), "strategy_version": c.version_hash, "segments": segs, "folds": folds,
            "positive_folds": sum(1 for f in folds if (f["expectancy_r"] or -1) > 0), "k_folds": k_folds,
            "test_double_costs": stress, "test_gross": gross,
            "baselines": {"no_trade_r": 0.0, "buy_and_hold_return": round(bh, 5) if bh is not None else None,
                          "random_entries": {k: v for k, v in rnd.items() if k != "values"},
                          "random_values": rnd.get("values", [])[:200]},
            "checks": checks, "passes": all(checks.values()), "verdict": verdict,
            "assumptions": {"latency": "decided at bar close, filled at the next bar's open",
                            "costs": "fees + assumed spread/slippage by liquidity tier; stops pay 2x slippage",
                            "liquidity": f"an entry may take at most {participation:.0%} of its bar's volume"
                            if participation else "no liquidity limit", "split": "60/20/20 chronological, 1-day embargo",
                            "parameters": "fixed in the definition before the data was seen", "short_selling": can_short}}
