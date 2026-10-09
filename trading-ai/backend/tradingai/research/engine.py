"""The research engine (sections 157-166, 193-194, 233-238, 255, 297-300).

    run_research(spec, bars, inst, calendar, market, profile="STANDARD", ledger=..., progress=..., cancel=...)

Pipeline (each stage reports progress; a cancel request stops between stages and leaves the ledger consistent):
  1. chronological split: TRAIN 60% / VALIDATION 20% / final TEST 20% (the test window is touched once per run,
     with the parameters chosen on TRAIN and checked on VALIDATION)
  2. parameter grid on TRAIN (every combination is a trial, written to the ledger)
  3. walk-forward: rolling windows, best parameters picked in-sample, traded on the next unseen window
  4. Monte Carlo: trade-order reshuffles, block bootstrap of bar returns, cost and slippage shocks, missed fills
  5. parameter stability (neighbour Sharpe / best Sharpe) and the regime breakdown
  6. cost stress at 1.25x, 1.5x, 2x and 3x
  7. capacity: the largest capital where net Sharpe keeps half of its base value (needs volume data)
  8. adversarial checks: remove the best trades, remove the best period, placebo (shifted and random signals)
  9. statistics: PSR, Deflated Sharpe (charged with EVERY trial ever logged for this family), Newey-West t,
     bootstrap interval, PBO (CSCV over the grid's variants)
 10. a transparent quality score and a verdict: REJECT, RESEARCH FURTHER or PAPER TEST.
     Research alone never says LIVE CANDIDATE: that needs a paper track record (research/compare.py).
"""

from __future__ import annotations

import itertools
import math
import threading
import time
from dataclasses import replace
from typing import Callable, Optional

import numpy as np

from tradingai import __version__
from tradingai.backtest import metrics as M
from tradingai.backtest.engine import BTConfig, BTResult, run
from tradingai.data.bars import Bars
from tradingai.features.registry import FeatureFrame
from tradingai.market.instruments import Instrument
from tradingai.regime.detect import detect
from tradingai.core.reasons import code_for
from tradingai.research import stats as S
from tradingai.strategies.library import Strategy, StrategySpec

PROFILES = {
    "FAST": {"grid": 1, "wf_folds": 3, "mc": 0, "placebo": 0, "capacity": False, "cost_stress": (2.0,)},
    "STANDARD": {"grid": 9, "wf_folds": 5, "mc": 200, "placebo": 20, "capacity": False,
                 "cost_stress": (1.25, 1.5, 2.0, 3.0)},
    "DEEP": {"grid": 27, "wf_folds": 8, "mc": 1000, "placebo": 100, "capacity": True,
             "cost_stress": (1.25, 1.5, 2.0, 3.0)},
}
GATES = {"min_test_trades": 30, "dsr": 0.95, "pbo_max": 0.2, "wf_ratio": 0.5, "stability": 0.5,
         "placebo_pct": 95.0}
WEIGHTS = {"oos_return": 0.15, "drawdown": 0.10, "risk_adjusted": 0.15, "sample_size": 0.10, "param_stability": 0.10,
           "walk_forward": 0.10, "cost_robustness": 0.10, "regime_stability": 0.05, "overfit_penalty": 0.10,
           "execution_feasibility": 0.05}


class Cancelled(Exception):
    pass


def _grid(spec: StrategySpec, limit: int) -> list[dict]:
    g = spec.parameter_grid or {}
    keys = list(g)
    combos = [dict(zip(keys, v)) for v in itertools.product(*[g[k] for k in keys])] if keys else [{}]
    base = {k: spec.parameters.get(k) for k in keys}
    combos.sort(key=lambda p: (p != base,))                       # the published default first
    if limit <= 1:
        return [base if keys else {}]
    if len(combos) > limit:
        idx = np.linspace(0, len(combos) - 1, limit).round().astype(int)
        combos = [combos[i] for i in sorted(set(idx.tolist()))]
        if base not in combos:
            combos[0] = base
    return combos


def _signal(spec: StrategySpec, bars: Bars, calendar: str, market: str, params: dict,
            other: Optional[np.ndarray] = None) -> np.ndarray:
    s = Strategy(spec, params)
    s.on_market_data(bars, calendar, market, other)
    return s.signal_series()


def _bt(spec, bars, sig, inst, ppy, params=None, **kw) -> BTResult:
    p = dict(spec.parameters, **(params or {}))
    ep = {k: p[k] for k in ("stop_atr", "target_r", "max_bars", "trail_atr") if k in p}
    return run(bars, sig, inst, BTConfig(exit_model=spec.exit_model, exit_params=ep, ppy=ppy, **kw))


def _sharpe(rets: np.ndarray, ppy: float) -> float:
    r = rets[np.isfinite(rets)]
    if len(r) < 3 or np.std(r, ddof=1) == 0:
        return 0.0
    return float(np.mean(r) / np.std(r, ddof=1) * math.sqrt(ppy))


def run_research(spec: StrategySpec, bars: Bars, inst: Instrument, calendar: str, market: str, *,
                 profile: str = "STANDARD", trials_so_far: int = 0, seed: int = 7,
                 progress: Optional[Callable[[float, str], None]] = None,
                 cancel: Optional[threading.Event] = None, other: Optional[np.ndarray] = None) -> dict:
    cfgp = PROFILES[profile]
    t0 = time.time()
    step = progress or (lambda f, m: None)

    def check(frac: float, msg: str) -> None:
        if cancel is not None and cancel.is_set():
            raise Cancelled(msg)
        step(frac, msg)

    n = len(bars)
    if n < 400:
        return {"status": "insufficient_data", "bars": n, "needed": 400, "reason_codes": ["INSUFFICIENT_DATA"]}
    ff_all = FeatureFrame(bars, calendar, market)
    ppy = ff_all.ppy
    a, b = int(n * 0.6), int(n * 0.8)
    seg = {"train": (0, a), "validation": (a, b), "test": (b, n)}
    rng = np.random.default_rng(seed)

    # signals are computed on the FULL history (causal), then each segment is backtested on its own bars, so
    # indicators arrive warm and nothing from later bars is used
    check(0.02, "computing signals for every parameter set")
    grid = _grid(spec, cfgp["grid"])
    sigs = [_signal(spec, bars, calendar, market, p, other) for p in grid]

    def seg_bt(i: int, name: str, **kw) -> BTResult:
        lo, hi = seg[name]
        return _bt(spec, bars.slice(lo, hi), sigs[i][lo:hi], inst, ppy, grid[i], **kw)

    check(0.10, f"parameter grid on TRAIN ({len(grid)} variant(s))")
    train_runs = [seg_bt(i, "train") for i in range(len(grid))]
    train_sh = [_sharpe(r.returns, ppy) for r in train_runs]
    best = int(np.argmax(train_sh))
    check(0.20, "validation and the final test window")
    val = seg_bt(best, "validation")
    test = seg_bt(best, "test")
    full = _bt(spec, bars, sigs[best], inst, ppy, grid[best])
    reg, series = detect(ff_all)
    regimes = {"trend": series["trend"], "volatility": series["volatility"]}
    rep_test = M.report(test, ppy)
    rep_full = M.report(full, ppy, regimes)

    # ---- walk-forward
    check(0.30, "walk-forward")
    k = cfgp["wf_folds"]
    first = int(n * 0.3)
    wlen = max(50, (n - first) // k)
    oos_rets, folds = [], []
    for f in range(k):
        lo, hi = first + f * wlen, (first + (f + 1) * wlen if f < k - 1 else n)
        if hi - lo < 20:
            continue
        is_sh = [_sharpe(_bt(spec, bars.slice(0, lo), s[:lo], inst, ppy, p).returns, ppy) for s, p in zip(sigs, grid)]
        j = int(np.argmax(is_sh))
        r = _bt(spec, bars.slice(lo, hi), sigs[j][lo:hi], inst, ppy, grid[j])
        oos_rets.append(r.returns[1:])
        folds.append({"fold": f, "is_end": int(bars.ts[lo - 1]), "oos": [int(bars.ts[lo]), int(bars.ts[hi - 1])],
                      "chosen": grid[j], "is_sharpe": round(is_sh[j], 3),
                      "oos_sharpe": round(_sharpe(r.returns, ppy), 3), "oos_trades": len(r.trades)})
        check(0.30 + 0.15 * (f + 1) / k, f"walk-forward fold {f + 1}/{k}")
    wf = np.concatenate(oos_rets) if oos_rets else np.zeros(0)
    wf_sh = _sharpe(wf, ppy) if len(wf) else 0.0
    is_mean = float(np.mean([x["is_sharpe"] for x in folds])) if folds else 0.0
    wf_ratio = wf_sh / is_mean if is_mean > 0 else None

    # ---- Monte Carlo
    mc = {}
    if cfgp["mc"]:
        check(0.48, "Monte Carlo")
        nets = np.array([t.net for t in full.trades])
        cap = float(full.config["capital"])
        dds, finals, streaks = [], [], []
        for _ in range(cfgp["mc"]):
            if len(nets) < 5:
                break
            seq = rng.permutation(nets)
            eq = cap + np.cumsum(seq)
            peak = np.maximum.accumulate(np.r_[cap, eq])
            dds.append(float(np.max(1 - np.r_[cap, eq] / peak)))
            finals.append(float(eq[-1] / cap - 1))
            s = m = 0
            for x in seq:
                s = s + 1 if x <= 0 else 0
                m = max(m, s)
            streaks.append(m)
        boot = []
        r = full.returns[1:]
        if len(r) > 50:
            for _ in range(min(cfgp["mc"], 300)):
                idx = S.stationary_bootstrap_indices(len(r), 20.0, rng)
                boot.append(_sharpe(r[idx], ppy))
        shocks = []
        for mult in rng.uniform(0.75, 2.0, size=min(10, cfgp["mc"] // 20 or 1)):
            shocks.append(_sharpe(_bt(spec, bars, sigs[best], inst, ppy, grid[best], cost_mult=float(mult)).returns,
                                  ppy))
        missed = _bt(spec, bars, sigs[best], inst, ppy, grid[best], fill_ratio=0.9, seed=seed)
        mc = {"runs": cfgp["mc"], "trade_reshuffle": {
            "max_drawdown_p50": _q(dds, 0.5), "max_drawdown_p95": _q(dds, 0.95),
            "final_return_p5": _q(finals, 0.05), "final_return_p50": _q(finals, 0.5),
            "losing_streak_p95": _q(streaks, 0.95),
            "risk_of_ruin_50pct_dd": float(np.mean(np.array(dds) >= 0.5)) if dds else None},
            "bootstrap_sharpe_p5_p95": [_q(boot, 0.05), _q(boot, 0.95)],
            "cost_shock_sharpe_min": min(shocks) if shocks else None,
            "missed_10pct_fills_sharpe": round(_sharpe(missed.returns, ppy), 4)}

    # ---- parameter stability
    check(0.62, "parameter stability")
    stability = None
    if len(grid) > 1:
        bs = train_sh[best]
        others = [s for i, s in enumerate(train_sh) if i != best]
        stability = round(float(np.mean(others) / bs), 3) if bs > 0 else 0.0
    heat = [{"params": p, "train_sharpe": round(s, 3)} for p, s in zip(grid, train_sh)]

    # ---- cost stress
    check(0.70, "cost stress")
    stress = {}
    for mult in cfgp["cost_stress"]:
        r = _bt(spec, bars, sigs[best], inst, ppy, grid[best], cost_mult=mult)
        stress[f"{mult}x"] = {"sharpe": round(_sharpe(r.returns, ppy), 4),
                              "net_return": round(float(r.equity[-1] / r.equity[0] - 1), 6)}

    # ---- capacity
    capacity = None
    if cfgp["capacity"] and np.any(bars.volume > 0):
        check(0.75, "capacity")
        base_sh = _sharpe(full.returns, ppy)
        capacity = {"method": "largest capital keeping >= 50% of base net Sharpe under square-root impact"}
        last_ok = None
        for capi in (1e4, 1e5, 1e6, 1e7, 1e8):
            r = _bt(spec, bars, sigs[best], inst, ppy, grid[best], capital=capi)
            sh = _sharpe(r.returns, ppy)
            capacity[f"{capi:,.0f}"] = round(sh, 3)
            if base_sh > 0 and sh >= 0.5 * base_sh:
                last_ok = capi
        capacity["estimate_usd"] = last_ok
    elif cfgp["capacity"]:
        capacity = {"estimate_usd": None, "note": "no volume data: capacity cannot be estimated"}

    # ---- adversarial checks
    check(0.80, "adversarial checks")
    nets = sorted((t.net for t in full.trades), reverse=True)
    total_net = float(sum(nets))
    remove = {f"top_{k}": round(total_net - sum(nets[:k]), 2) for k in (1, 5, 10) if len(nets) > k}
    if len(nets) >= 100:
        remove["top_1pct"] = round(total_net - sum(nets[: max(1, len(nets) // 100)]), 2)
    period = _period_exclusion(full, bars)
    placebo = {}
    if cfgp["placebo"]:
        real = _sharpe(full.returns, ppy)
        sh_shift, sh_rand = [], []
        expo = float(np.mean(sigs[best] != 0))
        for _ in range(cfgp["placebo"]):
            kshift = int(rng.integers(50, max(51, n // 3)))
            sh_shift.append(_sharpe(_bt(spec, bars, np.roll(sigs[best], kshift), inst, ppy, grid[best]).returns, ppy))
            rs = np.where(rng.random(n) < expo, rng.choice([-1.0, 1.0], n), 0.0)
            rs = _smooth(rs, max(1, int(np.mean([t.bars for t in full.trades])) if full.trades else 5))
            sh_rand.append(_sharpe(_bt(spec, bars, rs, inst, ppy, grid[best]).returns, ppy))
        placebo = {"real_sharpe": round(real, 4), "shifted_p95": _q(sh_shift, 0.95), "random_p95": _q(sh_rand, 0.95),
                   "percentile_vs_shifted": round(float(np.mean(np.array(sh_shift) < real) * 100), 1),
                   "percentile_vs_random": round(float(np.mean(np.array(sh_rand) < real) * 100), 1)}

    # ---- statistics
    check(0.90, "statistics")
    trials = trials_so_far + len(grid)
    tr = test.returns[1:]
    stat = {"trials_charged": trials}
    try:
        stat.update(psr=round(S.probabilistic_sharpe_ratio(tr), 4),
                    dsr=round(S.deflated_sharpe_ratio(tr, max(trials, 1)), 4),
                    newey_west_t=round(S.newey_west_tstat(tr), 3),
                    sharpe_ci95=[round(x, 3) for x in S.bootstrap_sharpe_interval(
                        tr, samples=300, mean_block=20, seed=seed, periods_per_year=int(ppy))])
    except ValueError as e:
        stat["error"] = str(e)
    if len(grid) >= 4:
        mat = np.column_stack([_bt(spec, bars, s, inst, ppy, p).returns[1:] for s, p in zip(sigs, grid)])
        try:
            stat["pbo"] = round(S.pbo_cscv(mat, 10 if len(mat) >= 20 else 2), 4)
        except ValueError as e:
            stat["pbo_error"] = str(e)
    else:
        stat["pbo"] = None
        stat["pbo_note"] = "fewer than 4 variants: PBO not meaningful"

    # ---- verdict and quality score
    check(0.96, "verdict")
    checks = _gates(rep_test, stat, wf_sh, wf_ratio, stability, stress, remove, placebo)
    score = _quality(rep_test, stat, wf_sh, wf_ratio, stability, stress, rep_full, placebo, test)
    for c in checks:
        c["code"] = None if c["passed"] else code_for(c["name"])
    reason_codes = sorted({c["code"] for c in checks if c["code"] and c["required"]})
    passed = all(c["passed"] for c in checks if c["required"])
    # a handful of test trades proves nothing either way: below 10 the verdict is REJECT (insufficient sample)
    promising = sum(1 for c in checks if c["passed"]) >= len(checks) * 0.6 and rep_test["trades"] >= 10
    verdict = "PAPER TEST" if passed else ("RESEARCH FURTHER" if promising else "REJECT")
    return {
        "status": "ok", "verdict": verdict, "reason_codes": reason_codes, "strategy_id": spec.strategy_id, "instrument": inst.instrument_id,
        "profile": profile, "params_chosen": grid[best], "grid": heat, "segments": {
            k: [int(bars.ts[v[0]]), int(bars.ts[v[1] - 1])] for k, v in seg.items()},
        "train": M.report(train_runs[best], ppy), "validation": M.report(val, ppy), "test": rep_test,
        "full": rep_full, "walk_forward": {"folds": folds, "oos_sharpe": round(wf_sh, 4),
                                          "oos_is_ratio": None if wf_ratio is None else round(wf_ratio, 3)},
        "monte_carlo": mc, "param_stability": stability, "cost_stress": stress, "capacity": capacity,
        "robustness": {"remove_best_trades": remove, "period_exclusion": period, "placebo": placebo},
        "statistics": stat, "checks": checks, "quality": score,
        "regime_now": reg.as_dict(), "reproducibility": {
            "dataset_sha256": bars.sha256(), "bars": n, "start": int(bars.ts[0]), "end": int(bars.ts[-1]),
            "strategy_version": spec.version, "code_version": __version__, "seed": seed, "profile": profile,
            "cost_model": full.costs.get("model"), "simulated_data": bars.simulated},
        "runtime_s": round(time.time() - t0, 2),
        "equity_curve": _curve(bars.ts, full.equity),
        "test_trades": [_trade_row(t) for t in test.trades[-300:]],
        "language_note": "Results describe past data under the stated assumptions. They are not a promise of future "
                         "returns.",
    }


def _curve(ts: np.ndarray, equity: np.ndarray, points: int = 400) -> list[list]:
    """The full-history equity curve, thinned to at most `points` (every point is a real value from the run)."""
    n = min(len(ts), len(equity))
    if n == 0:
        return []
    idx = np.unique(np.linspace(0, n - 1, min(points, n)).astype(int))
    return [[int(ts[i]), round(float(equity[i]), 2)] for i in idx]


def _trade_row(t) -> dict:
    notional = t.qty * t.entry_px
    return {"side": t.side, "entry_ts": t.entry_ts, "exit_ts": t.exit_ts, "entry": round(t.entry_px, 6),
            "exit": round(t.exit_px, 6), "net": round(t.net, 2), "fees": round(t.fees, 2),
            "ret": round(t.net / notional, 6) if notional else None, "r": None if t.r_multiple is None else
            round(t.r_multiple, 3), "bars": t.bars, "exit_reason": t.exit_reason}


def _q(x, q):
    return None if not len(x) else round(float(np.quantile(np.asarray(x, dtype=float), q)), 4)


def _smooth(sig: np.ndarray, hold: int) -> np.ndarray:
    out = sig.copy()
    i = 0
    while i < len(out):
        if out[i] != 0:
            out[i:i + hold] = out[i]
            i += hold
        else:
            i += 1
    return out


def _period_exclusion(r: BTResult, bars: Bars) -> dict:
    if not r.trades:
        return {}
    from datetime import datetime, timezone
    by: dict[str, dict[str, float]] = {"month": {}, "quarter": {}, "year": {}}
    for t in r.trades:
        d = datetime.fromtimestamp(t.exit_ts / 1000, tz=timezone.utc)
        for k, key in (("month", f"{d.year}-{d.month:02d}"), ("quarter", f"{d.year}-Q{(d.month - 1) // 3 + 1}"),
                       ("year", str(d.year))):
            by[k][key] = by[k].get(key, 0.0) + t.net
    total = sum(t.net for t in r.trades)
    out = {}
    for k, v in by.items():
        if len(v) > 1:
            best = max(v, key=v.get)
            out[f"without_best_{k}"] = {"removed": best, "net": round(total - v[best], 2)}
    return out


def _gates(rep, stat, wf_sh, wf_ratio, stab, stress, remove, placebo) -> list[dict]:
    g = GATES
    out = [
        {"name": "test trades", "value": rep["trades"], "need": f">= {g['min_test_trades']}",
         "passed": rep["trades"] >= g["min_test_trades"], "required": True},
        {"name": "test net return positive", "value": rep["net_pnl"], "need": "> 0",
         "passed": (rep["net_pnl"] or 0) > 0, "required": True},
        {"name": "deflated Sharpe", "value": stat.get("dsr"), "need": f">= {g['dsr']}",
         "passed": (stat.get("dsr") or 0) >= g["dsr"], "required": True},
        {"name": "walk-forward OOS Sharpe", "value": round(wf_sh, 3), "need": "> 0", "passed": wf_sh > 0,
         "required": True},
        {"name": "OOS / IS Sharpe", "value": wf_ratio, "need": f">= {g['wf_ratio']}",
         "passed": wf_ratio is not None and wf_ratio >= g["wf_ratio"], "required": True},
        {"name": "Sharpe at 2x costs", "value": stress.get("2.0x", {}).get("sharpe"), "need": "> 0",
         "passed": (stress.get("2.0x", {}).get("sharpe") or 0) > 0, "required": True},
        {"name": "net without the 5 best trades", "value": remove.get("top_5"), "need": "> 0",
         "passed": (remove.get("top_5") or 0) > 0, "required": True},
    ]
    if stat.get("pbo") is not None:
        out.append({"name": "PBO", "value": stat["pbo"], "need": f"<= {g['pbo_max']}",
                    "passed": stat["pbo"] <= g["pbo_max"], "required": True})
    if stab is not None:
        out.append({"name": "parameter stability", "value": stab, "need": f">= {g['stability']}",
                    "passed": stab >= g["stability"], "required": False})
    if placebo:
        out.append({"name": "beats random placebo", "value": placebo["percentile_vs_random"],
                    "need": f">= {g['placebo_pct']} percentile", "passed": placebo["percentile_vs_random"] >=
                    g["placebo_pct"], "required": True})
    return out


def _quality(rep, stat, wf_sh, wf_ratio, stab, stress, full, placebo, test) -> dict:
    def clip(x):
        return float(max(0.0, min(1.0, x)))
    comp = {
        "oos_return": clip(0.5 + 2 * (rep.get("total_return") or 0)),
        "drawdown": clip(1 - 2 * (rep.get("max_drawdown") or 1)),
        "risk_adjusted": clip(((rep.get("sharpe") or 0) + 1) / 3),
        "sample_size": clip(rep["trades"] / 100),
        "param_stability": clip(stab if stab is not None else 0.5),
        "walk_forward": clip((wf_ratio or 0) if wf_sh > 0 else 0),
        "cost_robustness": clip(((stress.get("2.0x", {}).get("sharpe") or 0) + 1) / 3),
        "regime_stability": clip(sum(1 for v in (full.get("by_regime", {}).get("trend") or {}).values()
                                     if v["net"] > 0) / 3),
        "overfit_penalty": clip(stat.get("dsr") or 0) * (1 - (stat.get("pbo") or 0)),
        "execution_feasibility": clip(1 - (test.partial_fills / max(1, len(test.trades))) / 2),
    }
    total = sum(WEIGHTS[k] * v for k, v in comp.items())
    return {"score": round(100 * total, 1), "components": {k: round(v, 3) for k, v in comp.items()},
            "weights": WEIGHTS, "note": "0-100; each component is shown so the score can be checked"}
