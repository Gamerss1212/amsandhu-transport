"""What could a balance become? Answered from MEASUREMENTS, not hopes.

The inputs are the full-system backtest's returns: for each fee level and starting balance, the result (as a
fraction of the balance) of the whole software over many random 10-day windows of recent real market data,
with order sizes modelled as the engine places them (venue minimums, whole shares or fractions, the cash a
spot account has). This module bootstraps those windows end to end (draw N windows at random with replacement
and compound them) to show the spread of outcomes over a horizon, and says what a goal would REQUIRE.

It is not a forecast: the sample is a few months of history, windows are drawn independently, and markets
change. It exists so the numbers on screen come from the same place as everything else in the app.
"""

from __future__ import annotations

import math
import random
from typing import Dict, List, Optional

SIMS = 5000


def nearest_tier(tiers: List[int], balance: float) -> int:
    return min(tiers, key=lambda t: abs(math.log(t / balance)))


def _q(sorted_vals: List[float], p: float) -> float:
    return sorted_vals[min(len(sorted_vals) - 1, max(0, int(p * len(sorted_vals))))]


def project(inputs: dict, fees: str, balance: float, days: int, target: Optional[float] = None) -> dict:
    if not inputs or not inputs.get("profiles"):
        raise ValueError("no measured results are bundled with this build")
    if not (1.0 <= balance <= 1e12):
        raise ValueError("balance must be between 1 and 1,000,000,000,000")
    if not (7 <= days <= 730):
        raise ValueError("choose a horizon between 7 and 730 days")
    prof = inputs["profiles"].get(fees) or inputs["profiles"].get("venue") or next(iter(inputs["profiles"].values()))
    used = fees if fees in inputs["profiles"] else ("venue" if "venue" in inputs["profiles"] else next(iter(inputs["profiles"])))
    tiers = sorted(int(k) for k in prof)
    tier = nearest_tier(tiers, balance)
    rets: List[float] = prof[str(tier)]["returns"] if isinstance(prof[str(tier)], dict) else prof[str(tier)]
    win = int(inputs.get("window_days", 10))
    n = max(1, round(days / win))
    rng = random.Random(20260930)                                 # same inputs, same answer: numbers do not jump
    finals = []
    for _ in range(SIMS):
        m = 1.0
        for _ in range(n):
            m *= 1.0 + rets[rng.randrange(len(rets))]
        finals.append(balance * m)
    finals.sort()
    best, worst = max(rets), min(rets)
    out = {
        "fees": used, "balance": balance, "days": days, "windows": n, "window_days": win, "tier": tier,
        "sample": {"windows_measured": len(rets), "period": inputs.get("period"), "generated": inputs.get("generated")},
        "outcome": {"worst": finals[0], "p05": _q(finals, 0.05), "p25": _q(finals, 0.25), "median": _q(finals, 0.5),
                    "p75": _q(finals, 0.75), "p95": _q(finals, 0.95), "best": finals[-1]},
        "share_ending_up": sum(1 for f in finals if f > balance * 1.0000001) / SIMS,
        "share_losing_10pct": sum(1 for f in finals if f < balance * 0.9) / SIMS,
        "best_window_pct": best * 100, "worst_window_pct": worst * 100,
        "mean_window_pct": sum(rets) / len(rets) * 100,
        "even_the_best_window_every_time": balance * (1.0 + best) ** n,
        "trades_per_window": prof[str(tier)].get("trades_per_window") if isinstance(prof[str(tier)], dict) else None,
    }
    if target and target > 0:
        need_win = (target / balance) ** (1.0 / n) - 1.0 if target > 0 else 0.0
        out["goal"] = {"target": target, "multiple": target / balance,
                       "needed_per_day_pct": ((target / balance) ** (1.0 / days) - 1.0) * 100,
                       "needed_per_window_pct": need_win * 100,
                       "share_reaching": sum(1 for f in finals if f >= target) / SIMS,
                       "simulations": SIMS,
                       "times_the_best_window": (need_win / best) if best > 0 else None}
    return out
