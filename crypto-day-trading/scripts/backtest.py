#!/usr/bin/env python3
"""Minimal rule-based backtester so a strategy can be checked before money is risked.

  python3 backtest.py btc_15m.csv --strategy ema_pullback --target-r 2 --fee-pct 0.05
  python3 backtest.py btc_15m.csv --strategy range_fade --split 0.7 --json

Fills are pessimistic on purpose:
  * entry at the NEXT candle's open (you cannot trade a close you have not seen)
  * stop and target checked on every candle; if both are touched, the STOP wins
  * fees and slippage are charged on both sides and expressed in R
  * a time stop closes any trade still open after --max-bars candles

Adding a strategy: write a function `def my_setup(i, d, ctx)` that returns None or a
dict {"direction": "long"|"short", "stop": price, "target": price} using only data up
to index i, then register it in STRATEGIES. `d` holds the candle lists and `ctx` the
precomputed indicators.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Callable, Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import indicators as ind  # noqa: E402
from snapshot import load_csv  # noqa: E402
from tradestats import format_summary, summarize  # noqa: E402


# --------------------------------------------------------------- strategies ---

def ema_pullback(i: int, d: dict, ctx: dict) -> Optional[dict]:
    """Long-only trend pullback (playbook #1, mechanical version).

    Trend: close > EMA200 and EMA21 > EMA50. Setup: the previous candle's low touched
    the EMA21 (pullback to value). Trigger: this candle closes above the EMA9 and is
    an up candle. Stop: pullback low - 0.3 ATR. Target: target_r * stop distance.
    """
    if i < 201:
        return None
    e9, e21, e50, e200, a = ctx["ema9"][i], ctx["ema21"][i], ctx["ema50"][i], ctx["ema200"][i], ctx["atr"][i]
    if None in (e9, e21, e50, e200, a):
        return None
    c, o, lo_prev = d["close"][i], d["open"][i], d["low"][i - 1]
    if not (c > e200 and e21 > e50):
        return None
    touched = lo_prev <= ctx["ema21"][i - 1] <= d["high"][i - 1]
    if not touched:
        return None
    if not (c > o and c > e9):
        return None
    stop = min(lo_prev, d["low"][i]) - 0.3 * a
    entry_est = c
    if entry_est - stop < 0.5 * a:
        return None
    return {"direction": "long", "stop": stop, "target": entry_est + ctx["target_r"] * (entry_est - stop)}


def range_fade(i: int, d: dict, ctx: dict) -> Optional[dict]:
    """Mean reversion (playbook #2, mechanical version).

    Previous candle closed outside the 2-sigma Bollinger band; this candle closes back
    inside. Trade toward the middle band. Stop beyond the extreme + 0.3 ATR. Target the
    middle band or target_r, whichever is closer. Skipped when EMA stack is strongly
    trending (band walks kill fades).
    """
    if i < 21:
        return None
    up, lo, mid, a = ctx["bb_up"], ctx["bb_lo"], ctx["bb_mid"], ctx["atr"][i]
    if None in (up[i], lo[i], mid[i], up[i - 1], lo[i - 1], a):
        return None
    c_prev, c = d["close"][i - 1], d["close"][i]
    e21, e50 = ctx["ema21"][i], ctx["ema50"][i]
    if e21 is not None and e50 is not None and abs(e21 - e50) > 1.5 * a:
        return None  # strong trend; do not fade
    if c_prev > up[i - 1] and c <= up[i]:
        extreme = max(d["high"][i - 1], d["high"][i])
        stop = extreme + 0.3 * a
        risk = stop - c
        if risk < 0.4 * a:
            return None
        target = max(mid[i], c - ctx["target_r"] * risk)
        if (c - target) / risk < ctx["min_rr"]:
            return None  # the middle band is too close to pay for the risk
        return {"direction": "short", "stop": stop, "target": target}
    if c_prev < lo[i - 1] and c >= lo[i]:
        extreme = min(d["low"][i - 1], d["low"][i])
        stop = extreme - 0.3 * a
        risk = c - stop
        if risk < 0.4 * a:
            return None
        target = min(mid[i], c + ctx["target_r"] * risk)
        if (target - c) / risk < ctx["min_rr"]:
            return None
        return {"direction": "long", "stop": stop, "target": target}
    return None


STRATEGIES: Dict[str, Callable] = {"ema_pullback": ema_pullback, "range_fade": range_fade}


# ------------------------------------------------------------------- engine ---

def precompute(d: dict, target_r: float, min_rr: float = 1.5) -> dict:
    c, h, l = d["close"], d["high"], d["low"]
    bb_mid, bb_up, bb_lo, _ = ind.bollinger(c, 20, 2.0)
    return {
        "ema9": ind.ema(c, 9), "ema21": ind.ema(c, 21), "ema50": ind.ema(c, 50), "ema200": ind.ema(c, 200),
        "atr": ind.atr(h, l, c, 14), "rsi": ind.rsi(c, 14),
        "bb_mid": bb_mid, "bb_up": bb_up, "bb_lo": bb_lo, "target_r": target_r, "min_rr": min_rr,
    }


def run(d: dict, strategy: Callable, ctx: dict, fee_pct: float, slip_pct: float, max_bars: int,
        start: int = 0, end: Optional[int] = None) -> List[dict]:
    n = len(d["close"])
    end = n if end is None else end
    trades: List[dict] = []
    i = max(start, 1)
    while i < end - 1:
        sig = strategy(i, d, ctx)
        if not sig:
            i += 1
            continue
        entry_i = i + 1
        entry = d["open"][entry_i]
        long = sig["direction"] == "long"
        entry = entry * (1 + slip_pct / 100) if long else entry * (1 - slip_pct / 100)
        stop, target = sig["stop"], sig["target"]
        risk = (entry - stop) if long else (stop - entry)
        if risk <= 0 or ((target - entry) if long else (entry - target)) <= 0:
            i += 1
            continue
        exit_price = None
        exit_i = None
        reason = None
        for j in range(entry_i, min(end, entry_i + max_bars)):
            hi, lo = d["high"][j], d["low"][j]
            if long:
                if lo <= stop:
                    exit_price, reason = stop * (1 - slip_pct / 100), "stop"
                elif hi >= target:
                    exit_price, reason = target, "target"
            else:
                if hi >= stop:
                    exit_price, reason = stop * (1 + slip_pct / 100), "stop"
                elif lo <= target:
                    exit_price, reason = target, "target"
            if exit_price is not None:
                exit_i = j
                break
        if exit_price is None:
            exit_i = min(end, entry_i + max_bars) - 1
            exit_price, reason = d["close"][exit_i], "time"
        pnl = (exit_price - entry) if long else (entry - exit_price)
        fees_r = (entry + exit_price) * fee_pct / 100 / risk
        r_mult = pnl / risk - fees_r
        trades.append({"signal_time": d["ts"][i].strftime("%Y-%m-%d %H:%M"), "direction": sig["direction"],
                       "entry": round(entry, 6), "stop": round(stop, 6), "target": round(target, 6),
                       "exit": round(exit_price, 6), "bars_held": exit_i - entry_i + 1, "reason": reason,
                       "r_multiple": round(r_mult, 3)})
        i = exit_i + 1  # one trade at a time
    return trades


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csv")
    ap.add_argument("--strategy", default="ema_pullback", choices=sorted(STRATEGIES))
    ap.add_argument("--target-r", type=float, default=2.0)
    ap.add_argument("--min-rr", type=float, default=1.5, help="skip signals whose target is closer than this many R")
    ap.add_argument("--fee-pct", type=float, default=0.05, help="per side")
    ap.add_argument("--slippage-pct", type=float, default=0.02, help="per side")
    ap.add_argument("--max-bars", type=int, default=48, help="time stop in candles")
    ap.add_argument("--split", type=float, help="fraction for in-sample; rest is out-of-sample (e.g. 0.7)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--trades", action="store_true", help="list every trade")
    a = ap.parse_args()

    d = load_csv(a.csv)
    ctx = precompute(d, a.target_r, a.min_rr)
    strat = STRATEGIES[a.strategy]
    n = len(d["close"])

    report = {"strategy": a.strategy, "csv": a.csv, "candles": n, "target_r": a.target_r, "min_rr": a.min_rr,
              "fee_pct_per_side": a.fee_pct, "slippage_pct_per_side": a.slippage_pct, "max_bars": a.max_bars,
              "period": f"{d['ts'][0].strftime('%Y-%m-%d')} to {d['ts'][-1].strftime('%Y-%m-%d')}"}
    if a.split:
        cut = int(n * a.split)
        ins = run(d, strat, ctx, a.fee_pct, a.slippage_pct, a.max_bars, 0, cut)
        oos = run(d, strat, ctx, a.fee_pct, a.slippage_pct, a.max_bars, cut, n)
        report["in_sample"] = summarize([t["r_multiple"] for t in ins])
        report["out_of_sample"] = summarize([t["r_multiple"] for t in oos])
        all_trades = ins + oos
    else:
        all_trades = run(d, strat, ctx, a.fee_pct, a.slippage_pct, a.max_bars)
        report["all"] = summarize([t["r_multiple"] for t in all_trades])
    reasons = {}
    for t in all_trades:
        reasons[t["reason"]] = reasons.get(t["reason"], 0) + 1
    report["exit_reasons"] = reasons
    if a.trades or a.json:
        report["trades"] = all_trades

    if a.json:
        print(json.dumps(report, indent=2))
        return
    print(f"backtest {a.strategy} on {a.csv}: {n} candles, {report['period']}, target {a.target_r}R, "
          f"fees {a.fee_pct}%/side, slippage {a.slippage_pct}%/side, time stop {a.max_bars} bars")
    for key in ("all", "in_sample", "out_of_sample"):
        if key in report:
            print(format_summary(report[key], key.replace("_", " ")))
    print(f"exit reasons: {reasons}")
    if a.trades:
        for t in all_trades:
            print(f"  {t['signal_time']} {t['direction']:<5} entry {t['entry']} stop {t['stop']} target {t['target']} "
                  f"exit {t['exit']} ({t['reason']}, {t['bars_held']} bars) -> {t['r_multiple']:+}R")
    print("reminder: a backtest is an estimate under pessimistic fills; forward test at minimum size before trusting it.")


if __name__ == "__main__":
    main()
