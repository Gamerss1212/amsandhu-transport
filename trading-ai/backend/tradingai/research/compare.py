"""Backtest vs paper vs shadow vs live (sections 225-226, 306): the same metrics side by side, a reality-gap score,
and drift warnings. Each column is computed from its own records only; nothing is blended into one number.

LIVE CANDIDATE needs a paper record: at least `min_paper_trades` closed paper trades whose mean net result lies
inside the backtest's bootstrap interval for the mean (i.e. paper has not degraded beyond what chance explains).
"""

from __future__ import annotations

from typing import Optional

import numpy as np

MIN_PAPER_TRADES = 30


def summarize(nets: list[float], slippage_bps: Optional[list[float]] = None) -> dict:
    a = np.asarray(nets, dtype=float)
    if not len(a):
        return {"trades": 0}
    wins, losses = a[a > 0], a[a <= 0]
    return {"trades": int(len(a)), "win_rate": round(float(np.mean(a > 0)), 4),
            "expectancy": round(float(a.mean()), 4),
            "profit_factor": round(float(wins.sum() / -losses.sum()), 4) if len(losses) and losses.sum() < 0 else None,
            "net": round(float(a.sum()), 2),
            "avg_slippage_bps": round(float(np.mean(slippage_bps)), 2) if slippage_bps else None}


def mean_interval(nets: list[float], samples: int = 1000, seed: int = 7) -> Optional[tuple[float, float]]:
    a = np.asarray(nets, dtype=float)
    if len(a) < 10:
        return None
    rng = np.random.default_rng(seed)
    means = [float(rng.choice(a, len(a)).mean()) for _ in range(samples)]
    return float(np.quantile(means, 0.025)), float(np.quantile(means, 0.975))


def compare(backtest: list[float], paper: list[float], shadow: list[float] | None = None,
            live: list[float] | None = None, *, backtest_slip: list[float] | None = None,
            paper_slip: list[float] | None = None, live_slip: list[float] | None = None) -> dict:
    cols = {"backtest": summarize(backtest, backtest_slip), "paper": summarize(paper, paper_slip),
            "shadow": summarize(shadow or []), "live": summarize(live or [], live_slip)}
    ci = mean_interval(backtest)
    flags, gap = [], None
    bt, pp = cols["backtest"], cols["paper"]
    if ci and pp["trades"]:
        if pp["expectancy"] < ci[0]:
            flags.append("PAPER_BELOW_BACKTEST_RANGE")
        e_bt = bt.get("expectancy") or 0.0
        gap = round(float(abs(pp["expectancy"] - e_bt) / (abs(e_bt) + 1e-9)), 3)
    eligible = bool(ci and pp["trades"] >= MIN_PAPER_TRADES and ci[0] <= pp["expectancy"] <= ci[1]
                    and pp["expectancy"] > 0)
    return {"columns": cols, "backtest_mean_ci95": ci, "reality_gap": gap, "flags": flags,
            "live_candidate": eligible,
            "rule": f"LIVE CANDIDATE needs >= {MIN_PAPER_TRADES} paper trades with a positive mean inside the "
                    "backtest's 95% interval; even then the owner must approve live trading"}
