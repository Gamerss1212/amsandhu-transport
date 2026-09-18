#!/usr/bin/env python3
"""Scale-out ladder simulator: measures what partial exits actually do to the win rate.

The question this answers
------------------------
Every trading course says "take partials and move your stop to breakeven, you'll win
80% of your trades". That claim has two halves and they are usually confused:

  * the GREEN RATE (what fraction of trades close above zero) -- which partials
    genuinely do raise, almost mechanically, and
  * the EXPECTANCY (average R per trade) -- which partials can easily destroy,
    because every extra exit is another fee and because capping the winner while
    keeping the full loser is a bad trade in isolation.

So this script measures both at once, on real candles, with pessimistic fills, and
it also runs the same ladder over a BENCHMARK of indiscriminate entries. If the
ladder produces the same green rate on random entries as on the setup, the green
rate is an artifact of the exit mechanics and not evidence of any edge. That
comparison is the whole point.

  python3 ladder.py data/BTC_1h.csv --setup orb --ladder 1.0:0.5 --stop-atr 4 --target-r 2
  python3 ladder.py data/BTC_1h.csv --sweep --fee-bps 30
  python3 ladder.py data/BTC_1h.csv --sweep --fee-bps 30 --json out.json

Ladder syntax: comma-separated `R:fraction` rungs, e.g. "0.25:0.34,1.0:0.33" sells
34% of the position at +0.25R and 33% more at +1R. Whatever is left runs to the
final target (--target-r) or the time stop. The stop moves to breakeven once the
first rung fills (disable with --no-breakeven).

Fill rules are deliberately pessimistic: entry at the next bar's open plus slippage;
if a bar touches both the stop and a rung, the STOP is taken; the stop is a market
order so it pays slippage too; every fill pays the fee.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
from typing import Callable, Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import indicators as ind  # noqa: E402
from snapshot import load_csv  # noqa: E402


# ------------------------------------------------------------------ setups ---
# Each setup returns None or a direction string for bar i, using only data <= i.

def _ctx(d: dict) -> dict:
    c, h, l, v = d["close"], d["high"], d["low"], d["volume"]
    bb_mid, bb_up, bb_lo, bb_w = ind.bollinger(c, 20, 2.0)
    return {
        "ema9": ind.ema(c, 9), "ema21": ind.ema(c, 21), "ema50": ind.ema(c, 50),
        "ema200": ind.ema(c, 200), "atr": ind.atr(h, l, c, 14),
        "rsi14": ind.rsi(c, 14), "rsi2": ind.rsi(c, 2),
        "bb_mid": bb_mid, "bb_up": bb_up, "bb_lo": bb_lo, "bb_w": bb_w,
        "rvol": ind.relative_volume(v, 20),
    }


def s_trend_pullback(i, d, x) -> Optional[str]:
    """P1: uptrend (21>50>200, price>200), previous bar's low touched the 21 EMA,
    this bar closes up and above the 9 EMA."""
    if i < 205:
        return None
    e9, e21, e50, e200 = x["ema9"][i], x["ema21"][i], x["ema50"][i], x["ema200"][i]
    if None in (e9, e21, e50, e200):
        return None
    c, o = d["close"][i], d["open"][i]
    if not (c > e200 and e21 > e50 > e200):
        return None
    e21p = x["ema21"][i - 1]
    if e21p is None or not (d["low"][i - 1] <= e21p <= d["high"][i - 1]):
        return None
    return "long" if (c > o and c > e9) else None


def s_breakout_retest(i, d, x) -> Optional[str]:
    """P3: close above the prior 40-bar high within the last 6 bars, then a pullback
    bar that wicks back to the level and closes above it."""
    if i < 205:
        return None
    e200 = x["ema200"][i]
    if e200 is None or d["close"][i] < e200:
        return None
    for back in range(1, 7):
        j = i - back
        if j < 45:
            continue
        level = max(d["high"][j - 40:j])
        if d["close"][j] > level and d["close"][j - 1] <= level:
            # breakout happened at j; now require a retest at i
            if d["low"][i] <= level <= d["high"][i] and d["close"][i] > level:
                return "long"
    return None


def s_sweep_reclaim(i, d, x) -> Optional[str]:
    """P4: this bar's low pierces the prior 30-bar low but it closes back above it."""
    if i < 205:
        return None
    e200 = x["ema200"][i]
    if e200 is None or d["close"][i] < e200:
        return None
    pool = min(d["low"][i - 30:i])
    a = x["atr"][i]
    if a is None:
        return None
    if d["low"][i] < pool - 0.05 * a and d["close"][i] > pool:
        return "long"
    return None


def s_orb(i, d, x) -> Optional[str]:
    """P6: on hourly bars, the first bar after 13:00 UTC defines the open range;
    a later bar in the session closing above that high with RVOL >= 1.2 is the break."""
    if i < 205:
        return None
    ts = d["ts"][i]
    if ts.hour < 14 or ts.hour > 18:
        return None
    # find the 13:00 bar of this same day
    j = i
    while j > 0 and d["ts"][j].hour > 13 and d["ts"][j].date() == ts.date():
        j -= 1
    if d["ts"][j].hour != 13 or d["ts"][j].date() != ts.date():
        return None
    or_high = d["high"][j]
    if i <= j:
        return None
    # first close above the OR high in the window
    if d["close"][i] <= or_high:
        return None
    if any(d["close"][k] > or_high for k in range(j + 1, i)):
        return None
    rv = x["rvol"][i]
    if rv is None or rv < 1.2:
        return None
    e200 = x["ema200"][i]
    return "long" if (e200 is not None and d["close"][i] > e200) else None


def s_rsi2(i, d, x) -> Optional[str]:
    """RSI(2) < 10 while above the 200 EMA (Connors-style reversion in an uptrend)."""
    if i < 205:
        return None
    r, e200 = x["rsi2"][i], x["ema200"][i]
    if r is None or e200 is None:
        return None
    return "long" if (r < 10 and d["close"][i] > e200) else None


def s_benchmark(i, d, x) -> Optional[str]:
    """Indiscriminate control: go long every 12th bar, no filter at all.

    This exists so the ladder's green rate can be compared against entries with no
    edge whatsoever. If the setup's green rate matches this, the ladder is doing the
    work, not the setup."""
    if i < 205:
        return None
    return "long" if i % 12 == 0 else None


SETUPS: Dict[str, Callable] = {
    "trend_pullback": s_trend_pullback,
    "breakout_retest": s_breakout_retest,
    "sweep_reclaim": s_sweep_reclaim,
    "orb": s_orb,
    "rsi2": s_rsi2,
    "benchmark": s_benchmark,
}


# ------------------------------------------------------------------ engine ---

def parse_ladder(spec: str) -> List[Dict[str, float]]:
    rungs = []
    if not spec or spec.lower() in ("none", "off", ""):
        return rungs
    for part in spec.split(","):
        r, f = part.split(":")
        rungs.append({"r": float(r), "frac": float(f)})
    total = sum(x["frac"] for x in rungs)
    if total > 1.0 + 1e-9:
        raise SystemExit(f"ladder fractions sum to {total}, which is more than the whole position")
    rungs.sort(key=lambda x: x["r"])
    return rungs


def simulate(d: dict, setup: Callable, x: dict, *, stop_atr: float, target_r: float,
             rungs: List[Dict[str, float]], horizon: int, fee_bps: float, slip_bps: float,
             breakeven: bool, start: int = 0, end: Optional[int] = None) -> List[dict]:
    n = len(d["close"])
    end = n if end is None else end
    fee = fee_bps / 10000.0
    slip = slip_bps / 10000.0
    trades: List[dict] = []
    i = max(start, 205)
    while i < end - 1:
        direction = setup(i, d, x)
        if direction is None:
            i += 1
            continue
        a = x["atr"][i]
        if a is None or a <= 0:
            i += 1
            continue
        entry_i = i + 1
        entry = d["open"][entry_i] * (1 + slip)          # long-only, pay the offer
        stop0 = entry - stop_atr * a
        risk = entry - stop0
        if risk <= 0:
            i += 1
            continue
        final_tp = entry + target_r * risk

        remaining = 1.0
        realized_r = 0.0                                  # R banked, gross of fees
        fills = 1                                         # the entry itself
        gross_notional = entry                            # for fee accounting, per unit
        fee_paid_price = entry * fee                      # entry fee on the full unit
        stop = stop0
        moved_be = False
        next_rung = 0
        exit_i = None
        reason = None

        for j in range(entry_i, min(end, entry_i + horizon)):
            hi, lo = d["high"][j], d["low"][j]

            # Pessimistic: the stop is always checked first.
            if lo <= stop:
                fill = stop * (1 - slip)
                realized_r += remaining * (fill - entry) / risk
                fee_paid_price += remaining * fill * fee
                fills += 1
                remaining = 0.0
                exit_i, reason = j, ("breakeven" if moved_be else "stop")
                break

            # Then the rungs, in order, as many as this bar reaches.
            while next_rung < len(rungs) and remaining > 0:
                rung = rungs[next_rung]
                price = entry + rung["r"] * risk
                if hi >= price:
                    take = min(rung["frac"], remaining)
                    realized_r += take * (price - entry) / risk
                    fee_paid_price += take * price * fee
                    fills += 1
                    remaining -= take
                    next_rung += 1
                    if breakeven and not moved_be:
                        stop = entry + entry * fee * 2    # entry plus round-trip fee
                        moved_be = True
                else:
                    break

            if remaining <= 1e-9:
                exit_i, reason = j, "ladder_complete"
                break

            if hi >= final_tp:
                realized_r += remaining * (final_tp - entry) / risk
                fee_paid_price += remaining * final_tp * fee
                fills += 1
                remaining = 0.0
                exit_i, reason = j, "target"
                break

        if remaining > 1e-9:
            exit_i = min(end, entry_i + horizon) - 1
            fill = d["close"][exit_i] * (1 - slip)
            realized_r += remaining * (fill - entry) / risk
            fee_paid_price += remaining * fill * fee
            fills += 1
            remaining = 0.0
            reason = "time"

        cost_r = fee_paid_price / risk
        net_r = realized_r - cost_r
        trades.append({
            "signal_time": d["ts"][i].strftime("%Y-%m-%d %H:%M"),
            "entry": round(entry, 6), "stop": round(stop0, 6),
            "gross_r": round(realized_r, 4), "cost_r": round(cost_r, 4),
            "r": round(net_r, 4), "fills": fills, "reason": reason,
            "bars": (exit_i - entry_i + 1) if exit_i is not None else 0,
        })
        i = (exit_i + 1) if exit_i is not None else (i + 1)   # one position at a time
    return trades


def stats(trades: List[dict]) -> dict:
    n = len(trades)
    if n == 0:
        return {"n": 0}
    rs = [t["r"] for t in trades]
    green = [r for r in rs if r > 1e-9]
    flat = [r for r in rs if -1e-9 <= r <= 1e-9]
    red = [r for r in rs if r < -1e-9]
    gross_win = sum(green)
    gross_loss = -sum(red)
    eq = 0.0; peak = 0.0; dd = 0.0
    for r in rs:
        eq += r; peak = max(peak, eq); dd = max(dd, peak - eq)
    return {
        "n": n,
        "green_rate_pct": round(100 * len(green) / n, 1),
        "non_loss_rate_pct": round(100 * (len(green) + len(flat)) / n, 1),
        "loss_rate_pct": round(100 * len(red) / n, 1),
        "expectancy_r": round(sum(rs) / n, 4),
        "total_r": round(sum(rs), 1),
        "avg_win_r": round(gross_win / len(green), 3) if green else 0.0,
        "avg_loss_r": round(-gross_loss / len(red), 3) if red else 0.0,
        "profit_factor": round(gross_win / gross_loss, 2) if gross_loss > 0 else None,
        "max_dd_r": round(dd, 1),
        "avg_cost_r": round(sum(t["cost_r"] for t in trades) / n, 4),
        "avg_fills": round(sum(t["fills"] for t in trades) / n, 2),
        "median_r": round(statistics.median(rs), 4),
    }


LADDERS = {
    "none":        "",
    "half_at_1R":  "1.0:0.5",
    "third_at_1R": "1.0:0.34,2.0:0.33",
    "half_at_p5":  "0.5:0.5",
    "half_at_p33": "0.33:0.5",
    "half_at_p25": "0.25:0.5",
    "two_thirds_p25": "0.25:0.67",
    "three_quarter_p25": "0.25:0.75",
    "three_quarter_p33": "0.33:0.75",
    "ladder_p25_1R": "0.25:0.4,1.0:0.3",
    # aggressive rungs, included to find where a target green rate actually lands
    "half_at_p2":   "0.2:0.5",
    "most_at_p2":   "0.2:0.85",
    "most_at_p15":  "0.15:0.85",
    "most_at_p1":   "0.1:0.85",
    "all_at_p25":   "0.25:1.0",
    "all_at_p2":    "0.2:1.0",
    "all_at_p15":   "0.15:1.0",
    "all_at_p1":    "0.1:1.0",
}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csv", nargs="*")
    ap.add_argument("--setup", default="orb", choices=sorted(SETUPS))
    ap.add_argument("--ladder", default="1.0:0.5", help="R:fraction rungs, or a name from --list-ladders")
    ap.add_argument("--stop-atr", type=float, default=4.0)
    ap.add_argument("--target-r", type=float, default=2.0)
    ap.add_argument("--horizon", type=int, default=96, help="time stop, in bars")
    ap.add_argument("--fee-bps", type=float, default=30.0,
                    help="per fill, ONE SIDE (a plain entry+exit therefore pays 2x this)")
    ap.add_argument("--slip-bps", type=float, default=2.0)
    ap.add_argument("--no-breakeven", action="store_true")
    ap.add_argument("--sweep", action="store_true", help="run every ladder against every setup")
    ap.add_argument("--split", type=float, help="in/out-of-sample fraction, e.g. 0.6")
    ap.add_argument("--json", help="write full results here")
    ap.add_argument("--list-ladders", action="store_true")
    a = ap.parse_args()

    if a.list_ladders:
        for k, v in LADDERS.items():
            print(f"{k:<20} {v or '(single exit at the target)'}")
        return
    if not a.csv:
        raise SystemExit("give at least one OHLCV csv (or --list-ladders)")

    data = {}
    for path in a.csv:
        d = load_csv(path)
        label = os.path.basename(path).split("_")[0]
        data[label] = (d, _ctx(d))
        print(f"loaded {label}: {len(d['close'])} bars, {d['ts'][0]:%Y-%m-%d} -> {d['ts'][-1]:%Y-%m-%d}", file=sys.stderr)

    def run(setup_name: str, ladder_spec: str) -> dict:
        rungs = parse_ladder(ladder_spec)
        all_trades = []
        for label, (d, x) in data.items():
            t = simulate(d, SETUPS[setup_name], x, stop_atr=a.stop_atr, target_r=a.target_r,
                         rungs=rungs, horizon=a.horizon, fee_bps=a.fee_bps, slip_bps=a.slip_bps,
                         breakeven=not a.no_breakeven)
            for tr in t:
                tr["symbol"] = label
            all_trades += t
        all_trades.sort(key=lambda t: t["signal_time"])
        return {"trades": all_trades, "stats": stats(all_trades)}

    out = {"config": {"stop_atr": a.stop_atr, "target_r": a.target_r, "horizon": a.horizon,
                      "fee_bps": a.fee_bps, "slip_bps": a.slip_bps, "breakeven": not a.no_breakeven,
                      "symbols": list(data)}}

    if a.sweep:
        print(f"\nstop {a.stop_atr}xATR · target {a.target_r}R · horizon {a.horizon} bars · "
              f"fee {a.fee_bps}bps/fill · slip {a.slip_bps}bps · breakeven-after-first-rung {not a.no_breakeven}")
        print(f"{'setup':<17}{'ladder':<20}{'n':>6}{'green%':>8}{'nonloss%':>10}{'E(R)':>9}{'PF':>7}{'avgW':>7}{'avgL':>7}{'cost':>7}{'fills':>7}{'maxDD':>8}")
        results = {}
        for sname in ["orb", "trend_pullback", "breakout_retest", "sweep_reclaim", "rsi2", "benchmark"]:
            for lname, lspec in LADDERS.items():
                r = run(sname, lspec)
                s = r["stats"]
                results[f"{sname}|{lname}"] = s
                if s["n"] == 0:
                    continue
                print(f"{sname:<17}{lname:<20}{s['n']:>6}{s['green_rate_pct']:>8}{s['non_loss_rate_pct']:>10}"
                      f"{s['expectancy_r']:>9.3f}{str(s['profit_factor']):>7}{s['avg_win_r']:>7.2f}{s['avg_loss_r']:>7.2f}"
                      f"{s['avg_cost_r']:>7.3f}{s['avg_fills']:>7.1f}{s['max_dd_r']:>8.1f}")
            print()
        out["sweep"] = results
    else:
        spec = LADDERS.get(a.ladder, a.ladder)
        r = run(a.setup, spec)
        s = r["stats"]
        print(f"\n{a.setup} · ladder {spec or 'single exit'} · stop {a.stop_atr}xATR · target {a.target_r}R · fee {a.fee_bps}bps/fill")
        for k, v in s.items():
            print(f"  {k:<20} {v}")
        if a.split and r["trades"]:
            cut = int(len(r["trades"]) * a.split)
            print("\n  in-sample :", stats(r["trades"][:cut]))
            print("  out-sample:", stats(r["trades"][cut:]))
        out["single"] = s
        out["trades"] = r["trades"]

    if a.json:
        with open(a.json, "w", encoding="utf-8") as fh:
            json.dump(out, fh, indent=2, default=str)
        print(f"\njson -> {a.json}")


if __name__ == "__main__":
    main()
