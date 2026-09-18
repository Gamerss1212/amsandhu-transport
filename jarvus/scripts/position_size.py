#!/usr/bin/env python3
"""Position sizing from the stop, never from leverage.

  python3 position_size.py --account 10000 --risk-pct 1 --entry 64200 --stop 63550 --target 65600
  python3 position_size.py --account 2500 --risk-pct 0.5 --entry 150 --stop 156 --target 141 --margin 500
  python3 position_size.py ... --json

Direction is inferred: stop below entry = long, stop above entry = short.
Fees default to 0.05% per side (taker); slippage to 0.02% per side.
"""

from __future__ import annotations

import argparse
import json
import sys


def compute(account: float, risk_pct: float, entry: float, stop: float, targets, fee_pct: float,
            slippage_pct: float, margin=None, leverage=None, maint_margin_pct: float = 0.5,
            min_notional: float = 0.0) -> dict:
    if entry <= 0 or stop <= 0 or entry == stop:
        raise ValueError("entry and stop must be positive and different")
    direction = "long" if stop < entry else "short"
    stop_dist = abs(entry - stop)
    stop_pct = stop_dist / entry * 100
    risk_amount = account * risk_pct / 100
    units = risk_amount / stop_dist
    notional = units * entry

    # costs, in currency and in R
    fee_cost = notional * fee_pct / 100 * 2
    slip_cost = notional * slippage_pct / 100 * 2
    cost_r = (fee_cost + slip_cost) / risk_amount

    out = {
        "direction": direction,
        "entry": entry,
        "stop": stop,
        "stop_distance": stop_dist,
        "stop_pct": round(stop_pct, 3),
        "risk_amount": round(risk_amount, 2),
        "risk_pct": risk_pct,
        "units": units,
        "notional": round(notional, 2),
        "notional_pct_of_account": round(notional / account * 100, 1),
        "round_trip_fees": round(fee_cost, 2),
        "round_trip_slippage": round(slip_cost, 2),
        "costs_in_r": round(cost_r, 3),
        "loss_if_stopped_incl_costs": round(risk_amount + fee_cost + slip_cost, 2),
        "loss_if_stopped_pct_of_account": round((risk_amount + fee_cost + slip_cost) / account * 100, 2),
        "warnings": [],
    }

    tgt_rows = []
    for t in targets or []:
        reward = (t - entry) if direction == "long" else (entry - t)
        gross_r = reward / stop_dist
        net_r = gross_r - cost_r
        tgt_rows.append({"target": t, "gross_r": round(gross_r, 2), "net_r": round(net_r, 2),
                         "pnl_if_hit": round(reward * units - fee_cost - slip_cost, 2)})
        if reward <= 0:
            out["warnings"].append(f"target {t} is on the wrong side of entry for a {direction}")
        elif net_r < 2.0:
            out["warnings"].append(f"target {t} is only {net_r:.2f}R net of costs; the skill's minimum is 2R")
    out["targets"] = tgt_rows

    if margin is not None and margin > 0:
        leverage = notional / margin
    if leverage is not None and leverage > 0:
        margin = notional / leverage
        out["leverage"] = round(leverage, 2)
        out["margin_required"] = round(margin, 2)
        # approximate isolated-margin liquidation price
        mm = maint_margin_pct / 100
        if direction == "long":
            liq = entry * (1 - 1 / leverage + mm)
            liq_dist = entry - liq
        else:
            liq = entry * (1 + 1 / leverage - mm)
            liq_dist = liq - entry
        out["liquidation_price_est"] = round(liq, 4)
        out["liquidation_distance_vs_stop"] = round(liq_dist / stop_dist, 2) if stop_dist else None
        if liq_dist <= stop_dist:
            out["warnings"].append("LIQUIDATION BEFORE STOP: leverage is far too high for this stop")
        elif liq_dist < 3 * stop_dist:
            out["warnings"].append("liquidation is less than 3x the stop distance away; lower leverage or post more margin")
        if leverage > 5:
            out["warnings"].append(f"effective leverage {leverage:.1f}x is above the 5x day-trade guideline")
    else:
        out["leverage"] = round(notional / account, 2)
        out["margin_required"] = round(notional, 2)
        if notional > account:
            out["warnings"].append("notional exceeds account; this size needs leverage "
                                   f"(~{notional / account:.1f}x) or a wider risk budget")

    if risk_pct > 2:
        out["warnings"].append(f"risk {risk_pct}% per trade is above the 2% hard ceiling")
    if min_notional and notional < min_notional:
        out["warnings"].append(f"notional {notional:.2f} is below the exchange minimum {min_notional}; "
                               "this account cannot take this trade at this risk %")
    if stop_pct < 0.15:
        out["warnings"].append("stop under 0.15% is almost certainly inside noise on any timeframe")
    return out


def fmt(res: dict) -> str:
    lines = [
        f"{res['direction'].upper()}  entry {res['entry']}  stop {res['stop']}  "
        f"(stop distance {res['stop_distance']:.6g} = {res['stop_pct']}%)",
        f"risk {res['risk_pct']}% = {res['risk_amount']}  ->  size {res['units']:.6g} units, "
        f"notional {res['notional']} ({res['notional_pct_of_account']}% of account)",
        f"leverage {res['leverage']}x, margin {res['margin_required']}",
        f"costs: fees {res['round_trip_fees']} + slippage {res['round_trip_slippage']} = {res['costs_in_r']}R; "
        f"loss if stopped {res['loss_if_stopped_incl_costs']} ({res['loss_if_stopped_pct_of_account']}%)",
    ]
    if "liquidation_price_est" in res:
        lines.append(f"est. liquidation {res['liquidation_price_est']} "
                     f"({res['liquidation_distance_vs_stop']}x the stop distance away)")
    for t in res["targets"]:
        lines.append(f"target {t['target']}: {t['gross_r']}R gross, {t['net_r']}R net, P&L {t['pnl_if_hit']}")
    for w in res["warnings"]:
        lines.append("WARNING: " + w)
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--account", type=float, required=True, help="account equity")
    ap.add_argument("--risk-pct", type=float, default=1.0)
    ap.add_argument("--entry", type=float, required=True)
    ap.add_argument("--stop", type=float, required=True)
    ap.add_argument("--target", type=float, action="append", help="repeatable")
    ap.add_argument("--fee-pct", type=float, default=0.05, help="per side")
    ap.add_argument("--slippage-pct", type=float, default=0.02, help="per side")
    ap.add_argument("--margin", type=float, help="margin you intend to post (derives leverage)")
    ap.add_argument("--leverage", type=float, help="leverage you intend to use (derives margin)")
    ap.add_argument("--maint-margin-pct", type=float, default=0.5)
    ap.add_argument("--min-notional", type=float, default=0.0)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    try:
        res = compute(a.account, a.risk_pct, a.entry, a.stop, a.target, a.fee_pct, a.slippage_pct,
                      a.margin, a.leverage, a.maint_margin_pct, a.min_notional)
    except ValueError as exc:
        sys.exit(f"error: {exc}")
    print(json.dumps(res, indent=2) if a.json else fmt(res))


if __name__ == "__main__":
    main()
