#!/usr/bin/env python3
"""Should this trade be taken? The Jarvus Terminal's brain, as a command.

The Terminal ran 311 rule-based bots; every entry they wanted went to a "brain" that took it, resized it or
refused it. This script applies the same checks, in the same order, with the same thresholds, to one planned
trade, so Jarvus decides the way the software did (Abhi still clicks buy or sell):

  1. COST GATE    round-trip costs / risk = cost in R. Above 0.33R -> SKIP. 0.20-0.33R -> half size.
  2. VOLATILITY   gate QUIET -> SKIP (the next hours are unlikely to pay the fees). LOUD -> 0.6x size.
  3. BENCH        the strategy's estimate is confidently negative (30+ trades of evidence and
                  mean + 1.64 x standard error < 0) -> SKIP until it improves.
  4. LEARNED EDGE with 8+ trades of evidence and an expected result below -0.05R per trade -> SKIP.
  5. SIZE         otherwise size = 1 + 1.5 x edge (between 0.5x and 1.5x), then the cost and LOUD cuts,
                  never below 0.25x or above 1.5x of the normal 0.5-1% risk. The brain can shrink a trade,
                  never push it past the risk cap.

Where the edge estimate comes from (no estimate = steps 3-4 are skipped and the trade is judged on costs and
the gate alone, at normal size, and the output says so):
  * --strategy: the Terminal's measured result for that strategy (assets/strategy_scoreboard.json, from
    references/strategy-scoreboard.md), at your fee level (interpolated linearly between the low-fee and the
    Kraken-retail runs; the same trades cost more or less), on --market if it was tested there;
  * --journal: Abhi's own closed trades for --playbook update it. History counts as at most 25 pseudo-trades
    (0.5 per backtest trade), so after a few dozen real trades his own results dominate, exactly like the
    Terminal's brain.

Examples:
  python3 decide.py --entry 84800 --stop 83100 --target 88200 --fees ndax --gate NORMAL
  python3 decide.py --entry 84800 --stop 83100 --fees kraken --maker --gate auto --symbol BTC
  python3 decide.py --entry 119.5 --stop 115.4 --fees ndax --strategy STRAT-407 --market SOL-USD
  python3 decide.py --entry 84800 --stop 83100 --fees ndax --journal journal.csv --playbook 6-orb
  python3 decide.py ... --account 2500 --risk-pct 1           # adds units and notional at the decided size

Fee levels (per side, verified Sept 2026; check yours): ndax 0.20/0.20 · kraken (Pro, $0+ tier) 0.40 maker /
0.80 taker · kraken2 ($2.5K+) 0.30/0.60 · kraken3 ($10K+ and $20K on platform) 0.22/0.38 · coinbase (Advanced,
entry) 0.60/1.20 · low 0.08/0.10 · stock 0 (commission-free; spread and regulatory fees only), or a number
(taker % per side). Exits are assumed to pay taker (stops fill at market). Educational, not advice.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import subprocess
import sys
from datetime import datetime, timezone
from typing import Optional

HERE = os.path.dirname(os.path.abspath(__file__))
BOARD = os.path.join(os.path.dirname(HERE), "assets", "strategy_scoreboard.json")

COST_VETO_R = 0.33
COST_HALF_R = 0.20
LOUD_SIZE = 0.6
VETO_EDGE = -0.05
MIN_EVIDENCE = 8.0
BENCH_EVIDENCE = 30.0
PRIOR_WEIGHT = 0.5
PRIOR_CAP = 25.0
R_CLIP = 3.0
R_VAR = 1.0

FEES = {  # per side, fraction: (maker, taker)
    "ndax": (0.0020, 0.0020), "kraken": (0.0040, 0.0080), "kraken2": (0.0030, 0.0060), "kraken3": (0.0022, 0.0038),
    "coinbase": (0.0060, 0.0120), "low": (0.0008, 0.0010), "stock": (0.0, 0.0),
}
LOW_T, RETAIL_T = 0.0010, 0.0080        # the two measured crypto fee levels the scoreboard holds


def fee_pair(level: str):
    if level in FEES:
        return FEES[level]
    t = float(level) / 100.0
    return (t, t)


def cost_r(entry: float, stop: float, maker_entry: bool, level: str, slip_pct: float) -> dict:
    mk, tk = fee_pair(level)
    stop_pct = abs(entry - stop) / entry * 100
    rt = ((mk if maker_entry else tk) + tk) * 100 + 2 * slip_pct
    return {"stop_pct": stop_pct, "round_trip_pct": rt, "cost_r": rt / stop_pct if stop_pct else float("inf")}


# ------------------------------------------------------------------ the prior: what the Terminal measured
def strategy_prior(query: str, market: Optional[str], level: str) -> Optional[dict]:
    with open(BOARD, encoding="utf-8") as fh:
        board = json.load(fh)["strategies"]
    q = query.strip().lower()
    sid = next((k for k in board if k.lower() == q), None) or \
        next((k for k, v in board.items() if q in v["name"].lower()), None)
    if sid is None:
        return None
    s = board[sid]
    taker = fee_pair(level)[1]
    rows = []
    for inst, e in s["runs"].items():
        if market and inst.upper().replace("/", "-") != market.upper().replace("/", "-"):
            continue
        if e["asset"] == "stock":
            v = e.get("base")
            if v:
                rows.append((inst, v[0], v[1], "stock net"))
            continue
        lo, hi = e.get("low"), e.get("retail")
        if not (lo and hi):
            continue
        w = (taker - LOW_T) / (RETAIL_T - LOW_T)          # linear in the fee; extrapolates beyond both ends
        r = lo[0] + (hi[0] - lo[0]) * w
        rows.append((inst, r, min(lo[1], hi[1]), f"interpolated at {taker * 100:.2f}% taker"))
    if not rows:
        return {"id": sid, "name": s["name"], "mean": None, "trades": 0, "markets": [], "note":
                f"not tested on {market}" if market else "no runs at this fee level"}
    tot = sum(n for _, _, n, _ in rows) or 1
    mean = sum(max(-R_CLIP, min(R_CLIP, r)) * n for _, r, n, _ in rows) / tot
    return {"id": sid, "name": s["name"], "mean": mean, "trades": tot,
            "markets": [(i, round(r, 3), n) for i, r, n, _ in rows], "note": rows[0][3]}


def journal_rs(path: str, playbook: Optional[str]) -> list:
    out = []
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if playbook and (row.get("playbook") or "").strip().lower() != playbook.strip().lower():
                continue
            r = row.get("r_multiple")
            try:
                if r not in (None, ""):
                    out.append(float(r))
                    continue
                e, s, x = float(row["entry"]), float(row["stop"]), float(row["exit"])
                d = 1 if (row.get("direction") or "long").lower().startswith("l") else -1
                risk = abs(e - s)
                if risk:
                    out.append((x - e) * d / risk - float(row.get("fees_r") or 0))
            except (ValueError, KeyError, TypeError):
                continue
    return out


def estimate(prior: Optional[dict], own: list) -> Optional[dict]:
    """The brain's shrinkage: history as at most 25 pseudo-trades, then every real trade on top."""
    p_mean = prior["mean"] if prior and prior.get("mean") is not None else None
    p_n = min(PRIOR_CAP, PRIOR_WEIGHT * prior["trades"]) if p_mean is not None else 0.0
    own = [max(-R_CLIP, min(R_CLIP, x)) for x in own]
    n = len(own)
    if p_mean is None and n == 0:
        return None
    total = p_n + n
    mean = ((p_mean or 0.0) * p_n + sum(own)) / total
    if n >= 5:
        m = sum(own) / n
        var = max(0.05, sum((x - m) ** 2 for x in own) / (n - 1))
    else:
        var = R_VAR
    return {"mean": mean, "sd": math.sqrt(var / total), "evidence": total, "own_trades": n, "history_weight": p_n}


# ------------------------------------------------------------------ the decision
def decide(c: dict, gate: str, est: Optional[dict]) -> dict:
    reasons, action, size, kind = [], "TAKE", 1.0, None
    cr = c["cost_r"]
    if cr > COST_VETO_R:
        return {"action": "SKIP", "size": 0.0, "kind": "cost",
                "reasons": [f"costs are {cr:.2f}R (round trip {c['round_trip_pct']:.2f}% vs a {c['stop_pct']:.2f}% stop); the limit is "
                            f"{COST_VETO_R:.2f}R. Fix: limit (maker) entry, cheaper venue, or a wider structural stop with "
                            f"smaller size; the stop needs to be at least {c['round_trip_pct'] / COST_VETO_R:.2f}% away "
                            f"({c['round_trip_pct'] / COST_HALF_R:.2f}% for full size)."]}
    if gate == "QUIET":
        return {"action": "SKIP", "size": 0.0, "kind": "quiet",
                "reasons": ["volatility gate QUIET: the coming hours are unlikely to move enough to pay the fees"]}
    if est is not None:
        benched = est["evidence"] >= BENCH_EVIDENCE and est["mean"] + 1.64 * est["sd"] < 0
        if benched:
            return {"action": "SKIP", "size": 0.0, "kind": "benched",
                    "reasons": [f"benched: expected {est['mean']:+.2f}R per trade, 95% confident it is below zero "
                                f"({est['evidence']:.0f} trades of evidence)"]}
        if est["evidence"] >= MIN_EVIDENCE and est["mean"] < VETO_EDGE:
            return {"action": "SKIP", "size": 0.0, "kind": "learned",
                    "reasons": [f"expected result {est['mean']:+.2f}R per trade (below {VETO_EDGE:+.2f}R) on "
                                f"{est['evidence']:.0f} trades of evidence"]}
        size = max(0.5, min(1.5, 1.0 + 1.5 * est["mean"]))
        reasons.append(f"expected {est['mean']:+.2f}R per trade (+/-{est['sd']:.2f}; {est['evidence']:.0f} trades of evidence, "
                       f"{est['own_trades']} of them yours) -> {size:.2f}x")
    else:
        reasons.append("no measured edge for this setup: judged on costs and the gate only, normal size "
                       "(add --strategy or --journal to let the evidence size it)")
    if cr > COST_HALF_R:
        size *= 0.5
        reasons.append(f"half size: costs are {cr:.2f}R (between {COST_HALF_R:.2f} and {COST_VETO_R:.2f})")
    if gate == "LOUD":
        size *= LOUD_SIZE
        reasons.append(f"volatility gate LOUD: x{LOUD_SIZE}")
    size = max(0.25, min(1.5, size))
    if abs(size - 1.0) > 0.05:
        action = "RESIZE"
    return {"action": action, "size": round(size, 2), "kind": kind, "reasons": reasons}


def auto_gate(symbol: str, stock: bool) -> tuple:
    cmd = [sys.executable, os.path.join(HERE, "volgate.py"), "--json"] + (["--stock", symbol] if stock else [symbol])
    try:
        out = json.loads(subprocess.run(cmd, capture_output=True, text=True, timeout=120).stdout)[0]
        return out.get("state", "UNKNOWN"), out
    except Exception as e:                                   # noqa: BLE001
        return "UNKNOWN", {"why": str(e)}


def main() -> int:
    ap = argparse.ArgumentParser(description="The Terminal's brain for one planned trade: TAKE, RESIZE or SKIP.")
    ap.add_argument("--entry", type=float, required=True)
    ap.add_argument("--stop", type=float, required=True)
    ap.add_argument("--target", type=float)
    ap.add_argument("--fees", default="ndax", help="ndax | kraken | kraken2 | kraken3 | coinbase | low | stock | <taker %% per side>")
    ap.add_argument("--maker", action="store_true", help="entry is a limit (maker) order")
    ap.add_argument("--slip-pct", type=float, default=0.02, help="slippage per side in %% (majors ~0.02, alts 0.05-0.2)")
    ap.add_argument("--gate", default="UNKNOWN", help="LOUD | NORMAL | QUIET | auto (needs --symbol)")
    ap.add_argument("--symbol", help="for --gate auto, e.g. BTC or SPY (with --stock)")
    ap.add_argument("--stock", action="store_true")
    ap.add_argument("--strategy", help="scoreboard id (STRAT-407) or part of the name")
    ap.add_argument("--market", help="instrument as tested, e.g. BTC-USD, SOL-USD, NVDA")
    ap.add_argument("--journal", help="journal CSV with Abhi's closed trades")
    ap.add_argument("--playbook", help="only journal rows with this playbook")
    ap.add_argument("--account", type=float)
    ap.add_argument("--risk-pct", type=float, default=1.0, help="normal risk per trade before the brain's multiplier (cap 1%%)")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    if a.entry <= 0 or a.stop <= 0 or a.entry == a.stop:
        ap.error("entry and stop must be positive and different")
    level = "stock" if a.stock and a.fees == "ndax" else a.fees
    c = cost_r(a.entry, a.stop, a.maker, level, a.slip_pct)
    gate, gate_detail = a.gate.upper(), None
    if gate == "AUTO":
        if not a.symbol:
            ap.error("--gate auto needs --symbol")
        gate, gate_detail = auto_gate(a.symbol, a.stock)
    prior = strategy_prior(a.strategy, a.market, level) if a.strategy else None
    own = journal_rs(a.journal, a.playbook) if a.journal else []
    est = estimate(prior, own)
    d = decide(c, gate, est)
    now = datetime.now(timezone.utc)
    weekend = now.weekday() >= 5
    out = {"decision": d["action"], "size_multiplier": d["size"], "skip_kind": d["kind"], "reasons": d["reasons"],
           "cost_r": round(c["cost_r"], 3), "stop_pct": round(c["stop_pct"], 3), "round_trip_pct": round(c["round_trip_pct"], 3),
           "fees": level, "maker_entry": a.maker, "gate": gate, "estimate": est, "prior": prior}
    if a.target:
        risk = abs(a.entry - a.stop)
        gross = abs(a.target - a.entry) / risk
        out["target_r_gross"] = round(gross, 2)
        out["target_r_net"] = round(gross - c["cost_r"], 2)
        if out["target_r_net"] < 2.0:
            out["reasons"] = out["reasons"] + [f"note: target is {out['target_r_net']:.2f}R after costs; Jarvus wants 2R net to TP2"]
    if weekend and not a.stock:
        out["reasons"] = out["reasons"] + ["note: it is the weekend (UTC): no new majors trades (rule M4; measured zero edge)"]
    if a.account:
        risk_pct = min(1.0, min(1.0, a.risk_pct) * d["size"])      # the brain shrinks; Jarvus's 1% cap still binds
        risk_amt = a.account * risk_pct / 100
        units = risk_amt / abs(a.entry - a.stop) if d["size"] else 0.0
        out["sizing"] = {"risk_pct": round(risk_pct, 3), "risk_amount": round(risk_amt, 2), "units": units,
                         "notional": round(units * a.entry, 2),
                         "note": "check the venue's minimum order; if the notional is below it the trade cannot be placed "
                                 "at this risk (do not raise the risk to fit; skip or use fewer, larger positions)"}
        if units * a.entry > a.account:
            out["sizing"]["note"] = "notional exceeds the account (spot, no leverage): the stop is too tight for this risk; widen the stop and cut size"
    if a.json:
        print(json.dumps(out, indent=1, default=str))
        return 0
    print(f"DECISION: {out['decision']}" + (f"  (size {out['size_multiplier']}x)" if out['decision'] != 'SKIP' else ""))
    print(f"  cost {out['cost_r']:.2f}R  (round trip {out['round_trip_pct']:.2f}% on a {out['stop_pct']:.2f}% stop; "
          f"fees {level}{', maker entry' if a.maker else ', taker entry'})  ·  gate {gate}")
    for r in out["reasons"]:
        print("  - " + r)
    if prior:
        mk = ", ".join(f"{i} {r:+.2f}R ({n})" for i, r, n in prior.get("markets", [])[:6])
        print(f"  history: {prior['id']} {prior['name']}: " + (f"{prior['mean']:+.2f}R over {prior['trades']} backtest trades [{mk}] ({prior['note']})"
                                                              if prior.get("mean") is not None else prior.get("note", "")))
    if a.target:
        print(f"  target {out['target_r_gross']:.2f}R gross, {out['target_r_net']:.2f}R after costs")
    if a.account:
        s = out["sizing"]
        print(f"  size: risk {s['risk_pct']}% = {s['risk_amount']} -> {s['units']:.6g} units, notional {s['notional']}  ({s['note']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
