#!/usr/bin/env python3
"""The 80% experiment: can a real 80% win rate be built, and what is it worth?

Runs the ladder simulator across setups, ladders and fee tiers on real candles and
prints the three tables that answer the question:

  A. Where does an 80% green rate actually come from? (ladder vs setup)
  B. What does it cost in expectancy? (gross, then each fee tier)
  C. Does it hold out of sample? (first 60% vs last 40% of the trade sequence)

Usage: python3 experiment_80.py data/BTC_1h.csv data/ETH_1h.csv data/SOL_1h.csv
"""
from __future__ import annotations
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ladder import SETUPS, LADDERS, parse_ladder, simulate, stats, _ctx
from snapshot import load_csv

STOP_ATR, TARGET_R, HORIZON, SLIP = 4.0, 2.0, 96, 2.0
# one side, in bps. Round trip for a plain entry+exit is 2x these.
FEE_TIERS = {"gross (0)": 0.0, "maker 10 (Coinbase/MEXC)": 5.0, "Binance/OKX spot 20": 10.0,
             "good maker 30": 15.0, "NDAX 40": 20.0, "Kraken taker 52": 26.0}
KEY_LADDERS = ["none", "half_at_1R", "half_at_p5", "half_at_p33", "half_at_p25", "half_at_p2", "most_at_p15"]


def load_all(paths):
    out = {}
    for p in paths:
        d = load_csv(p)
        out[os.path.basename(p).split("_")[0]] = (d, _ctx(d))
        print(f"  {os.path.basename(p)}: {len(d['close'])} bars {d['ts'][0]:%Y-%m-%d}..{d['ts'][-1]:%Y-%m-%d}", file=sys.stderr)
    return out


def run(data, setup, ladder, fee):
    rungs = parse_ladder(LADDERS.get(ladder, ladder))
    trades = []
    for label, (d, x) in data.items():
        t = simulate(d, SETUPS[setup], x, stop_atr=STOP_ATR, target_r=TARGET_R, rungs=rungs,
                     horizon=HORIZON, fee_bps=fee, slip_bps=SLIP, breakeven=True)
        for tr in t:
            tr["symbol"] = label
        trades += t
    trades.sort(key=lambda t: t["signal_time"])
    return trades


def main():
    paths = sys.argv[1:]
    if not paths:
        raise SystemExit("give OHLCV csv paths")
    print("loading:", file=sys.stderr)
    data = load_all(paths)
    syms = "+".join(data)
    results = {"config": {"stop_atr": STOP_ATR, "target_r": TARGET_R, "horizon": HORIZON,
                          "slip_bps": SLIP, "symbols": list(data)}}

    print(f"\n{'='*104}\nA. WHERE THE 80% COMES FROM — gross (zero fees), {syms} hourly")
    print(f"{'='*104}")
    print("   If the benchmark column matches the setup column, the win rate is the exit ladder's doing, not the setup's.\n")
    print(f"{'ladder (sell X at +YR, then stop to breakeven)':<48}{'ORB green%':>12}{'ORB E(R)':>11}{'rand green%':>13}{'rand E(R)':>11}")
    tblA = {}
    for lad in KEY_LADDERS:
        o = stats(run(data, "orb", lad, 0.0))
        b = stats(run(data, "benchmark", lad, 0.0))
        tblA[lad] = {"orb": o, "benchmark": b}
        spec = LADDERS[lad] or "single exit at +2R"
        print(f"{lad + '  [' + spec + ']':<48}{o['green_rate_pct']:>11.1f}%{o['expectancy_r']:>11.3f}"
              f"{b['green_rate_pct']:>12.1f}%{b['expectancy_r']:>11.3f}")
    results["A_gross_ladder_vs_benchmark"] = tblA

    print(f"\n{'='*104}\nB. WHAT THE 80% LADDER COSTS — ORB, by fee tier (bps are ONE SIDE)")
    print(f"{'='*104}\n")
    print(f"{'fee tier':<28}{'ladder':<16}{'n':>6}{'green%':>9}{'E(R)':>9}{'PF':>7}{'avgW':>7}{'avgL':>7}{'cost R':>9}{'maxDD R':>9}")
    tblB = {}
    for tier, fee in FEE_TIERS.items():
        for lad in ("half_at_1R", "half_at_p25"):
            s = stats(run(data, "orb", lad, fee))
            tblB[f"{tier}|{lad}"] = s
            print(f"{tier:<28}{lad:<16}{s['n']:>6}{s['green_rate_pct']:>8.1f}%{s['expectancy_r']:>9.3f}"
                  f"{str(s['profit_factor']):>7}{s['avg_win_r']:>7.2f}{s['avg_loss_r']:>7.2f}{s['avg_cost_r']:>9.3f}{s['max_dd_r']:>9.1f}")
        print()
    results["B_fee_tiers"] = tblB

    print(f"{'='*104}\nC. OUT-OF-SAMPLE — first 60% of trades vs last 40%, gross")
    print(f"{'='*104}\n")
    print(f"{'setup':<18}{'ladder':<14}{'IS n':>6}{'IS green%':>11}{'IS E':>8}{'OOS n':>7}{'OOS green%':>12}{'OOS E':>8}")
    tblC = {}
    for setup in ("orb", "trend_pullback", "rsi2", "benchmark"):
        for lad in ("half_at_1R", "half_at_p25"):
            tr = run(data, setup, lad, 0.0)
            cut = int(len(tr) * 0.6)
            a, b = stats(tr[:cut]), stats(tr[cut:])
            tblC[f"{setup}|{lad}"] = {"in_sample": a, "out_sample": b}
            if a.get("n") and b.get("n"):
                print(f"{setup:<18}{lad:<14}{a['n']:>6}{a['green_rate_pct']:>10.1f}%{a['expectancy_r']:>8.3f}"
                      f"{b['n']:>7}{b['green_rate_pct']:>11.1f}%{b['expectancy_r']:>8.3f}")
    results["C_out_of_sample"] = tblC

    out = os.path.join(os.path.dirname(paths[0]), "..", "experiment_80.json")
    with open(out, "w") as fh:
        json.dump(results, fh, indent=2, default=str)
    print(f"\njson -> {os.path.abspath(out)}")


if __name__ == "__main__":
    main()
