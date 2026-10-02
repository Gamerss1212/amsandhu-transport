#!/usr/bin/env python3
""""Can $X become $Y in N days?" answered from measurements, not hopes (the Jarvus Terminal's goal calculator).

Two parts:
  1. The arithmetic: the daily return a goal REQUIRES, compounded every single day: (Y / X) ** (1 / days) - 1.
  2. The evidence: the whole Terminal (311 bots + the brain + the volatility gate + realistic order sizes) was
     replayed on 400 random 10-day windows of real June-September 2026 market data, at five fee levels and five
     account sizes ($100, $1,000, $10,000, $100,000, $10,000,000). This script strings those measured windows
     together at random (5,000 times) for your horizon and shows the spread of outcomes. Data:
     ../assets/projection_inputs.json (see references/terminal-evidence.md for how it was made).

It is not a forecast: three months of history, windows drawn independently, markets change. It shows what the
measured system did, so a goal can be compared with something real. The AI never aims at a goal; Jarvus has no
profit target and decides trade by trade.

Examples:
  python3 goal.py 100 300000 90                 # $100 -> $300,000 in 90 days
  python3 goal.py 1000 2000 365 --fees kraken
  python3 goal.py 10000 --days 90               # no goal: just the spread of measured outcomes
Fee levels: ndax (default), low_fee, kraken, coinbase, venue (each bot's own exchange).
"""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
INPUTS = os.path.join(os.path.dirname(HERE), "assets", "projection_inputs.json")
SIMS = 5000


def project(inputs: dict, fees: str, balance: float, days: int, target=None) -> dict:
    profiles = inputs["profiles"]
    used = fees if fees in profiles else "venue"
    prof = profiles[used]
    tiers = sorted(int(k) for k in prof)
    tier = min(tiers, key=lambda t: abs(math.log(t / balance)))
    rets = prof[str(tier)]["returns"]
    win = int(inputs.get("window_days", 10))
    n = max(1, round(days / win))
    rng = random.Random(20260930)                   # same inputs, same answer
    finals = []
    for _ in range(SIMS):
        m = 1.0
        for _ in range(n):
            m *= 1.0 + rets[rng.randrange(len(rets))]
        finals.append(balance * m)
    finals.sort()
    q = lambda p: finals[min(SIMS - 1, int(p * SIMS))]  # noqa: E731
    best = max(rets)
    out = {"fees": used, "balance": balance, "days": days, "windows": n, "window_days": win, "tier": tier,
           "measured_windows": len(rets), "period": inputs.get("period"),
           "trades_per_window": prof[str(tier)].get("trades_per_window"),
           "worst": finals[0], "p05": q(0.05), "median": q(0.5), "p95": q(0.95), "best": finals[-1],
           "share_up": sum(1 for f in finals if f > balance) / SIMS,
           "share_down_10": sum(1 for f in finals if f < balance * 0.9) / SIMS,
           "mean_window_pct": sum(rets) / len(rets) * 100, "best_window_pct": best * 100,
           "worst_window_pct": min(rets) * 100, "best_every_time": balance * (1 + best) ** n}
    if target:
        need_day = (target / balance) ** (1 / days) - 1
        need_win = (target / balance) ** (1 / n) - 1
        out["goal"] = {"target": target, "multiple": target / balance, "per_day_pct": need_day * 100,
                       "per_window_pct": need_win * 100, "share_reaching": sum(1 for f in finals if f >= target) / SIMS,
                       "times_best_window": need_win / best if best > 0 else None}
    return out


def money(x: float) -> str:
    return f"${x:,.2f}" if x < 1000 else f"${x:,.0f}"


def main() -> int:
    ap = argparse.ArgumentParser(description="What could a balance become? Measured, not promised.")
    ap.add_argument("balance", type=float)
    ap.add_argument("target", type=float, nargs="?")
    ap.add_argument("days", type=int, nargs="?")
    ap.add_argument("--days", dest="days_opt", type=int)
    ap.add_argument("--fees", default="ndax", choices=["ndax", "low_fee", "kraken", "coinbase", "venue"])
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    days = a.days or a.days_opt or 90
    if not (1 <= a.balance <= 1e12) or not (1 <= days <= 3650):
        ap.error("balance 1 to 1e12, days 1 to 3650")
    with open(INPUTS, encoding="utf-8") as fh:
        inputs = json.load(fh)
    r = project(inputs, a.fees, a.balance, days, a.target)
    if a.json:
        print(json.dumps(r, indent=1))
        return 0
    print(f"{money(a.balance)} over {days} days at {r['fees']} fees (measured at the {money(r['tier'])} account size; "
          f"{r['measured_windows']} real 10-day windows, {' to '.join(r['period'] or [])}; about {r['trades_per_window']} trades per window)")
    print(f"  middle outcome {money(r['median'])}; 9 in 10 end between {money(r['p05'])} and {money(r['p95'])}; "
          f"best of {SIMS:,} {money(r['best'])}, worst {money(r['worst'])}")
    print(f"  ends higher in {r['share_up'] * 100:.0f}% of simulations; loses 10%+ in {r['share_down_10'] * 100:.0f}%. "
          f"Measured average {r['mean_window_pct']:+.3f}% per 10 days; best window {r['best_window_pct']:+.2f}%, worst {r['worst_window_pct']:+.2f}%")
    g = r.get("goal")
    if g:
        print(f"  GOAL {money(g['target'])} = {g['multiple']:,.1f}x in {days} days needs {g['per_day_pct']:+.2f}% EVERY day "
              f"({g['per_window_pct']:+.1f}% every 10 days, {g['times_best_window']:.1f}x the best 10 days measured). "
              f"Reached in {g['share_reaching'] * 100:.1f}% of {SIMS:,} simulations. "
              f"Repeating the single best window every time ends at {money(r['best_every_time'])}.")
        if g["per_day_pct"] > 1.0:
            print("  Plain answer: no strategy measured here comes near that. Anything that claims it (all-in bets, leverage, "
                  "signal groups) mostly ends at zero. A realistic aim is to survive, learn, and compound slowly.")
    print("  A measurement of recent history, not a forecast.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
