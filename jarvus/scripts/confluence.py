#!/usr/bin/env python3
"""Confluence score for a candidate trade, from snapshot/scan JSON plus derivatives JSON.

  python3 fetch_ohlcv.py --symbol BTCUSDT --interval 4h  --limit 300 --out /tmp/btc_4h.csv
  python3 fetch_ohlcv.py --symbol BTCUSDT --interval 15m --limit 600 --out /tmp/btc_15m.csv
  python3 snapshot.py /tmp/btc_4h.csv /tmp/btc_15m.csv --json /tmp/snap.json
  python3 fetch_ohlcv.py --symbol BTCUSDT --derivs --out /tmp/derivs.json
  python3 confluence.py --snapshot /tmp/snap.json --derivs /tmp/derivs.json --direction long
  python3 confluence.py --snapshot /tmp/snap.json --direction short --entry 76050 --stop 76480 --target 75200

Scores the eleven factors of SKILL.md (factor 0 = the volatility gate, then the ten of the strategy
encyclopedia Part 1). Most are computed mechanically; location and trigger need a chart read, reward and
stop quality need --entry/--stop/--target (otherwise they are reported as "manual" and score 0).
The score is a filter, not a signal: 10-11 A+, 9 A, 8 B (half risk), 7 or less skip; alts and memes need
one point more at every grade (--alt). A QUIET gate or a cost above 0.33R makes the verdict skip whatever
the score. Stop quality and reward are judged on the real cost in R at --fees (NDAX by default):
cost <= 0.20R earns the stop point (v5/v6: in practice 3-4x ATR at spot fees), 0.20-0.33R does not,
above 0.33R is a NO.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import events  # noqa: E402


def load(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def pick_timeframes(snap: dict):
    tfs = snap.get("timeframes") or []
    if not tfs and "results" in snap:  # scan.json: caller must pass --symbol
        raise SystemExit("this is a scan.json; pass a snapshot.json (or use --symbol with scan output)")
    def minutes(tf):
        u = tf[-1]; n = int(tf[:-1]) if tf[:-1].isdigit() else 0
        return n * {"m": 1, "h": 60, "d": 1440, "w": 10080}.get(u, 1)
    tfs = sorted(tfs, key=lambda s: -minutes(s["timeframe"]))
    htf = tfs[0]
    ltf = tfs[-1]
    return htf, ltf


FEE_LEVELS = {"ndax": (0.20, 0.20), "kraken": (0.40, 0.80), "kraken10k": (0.22, 0.38), "coinbase": (0.60, 1.20),
              "low": (0.08, 0.10)}                   # per side, % (maker, taker), base tiers verified Sept 2026


def round_trip_pct(fees="ndax", maker_entry=False, slip_pct=0.02) -> float:
    if fees in FEE_LEVELS:
        mk, tk = FEE_LEVELS[fees]
    else:
        mk = tk = float(fees)
    return (mk if maker_entry else tk) + tk + 2 * slip_pct


def score(htf: dict, ltf: dict, derivs: dict, direction: str, now: datetime, entry=None, stop=None, target=None, alt=False,
          gate=None, fees="ndax", maker_entry=False):
    long = direction == "long"
    rows = []
    cost_r = None
    if entry and stop and abs(entry - stop) > 0:
        cost_r = round_trip_pct(fees, maker_entry) / (abs(entry - stop) / entry * 100)

    def add(n, name, pts, why, manual=False):
        rows.append({"factor": n, "name": name, "points": pts, "why": why, "manual": manual})

    # 0 Volatility gate (run scripts/volgate.py, or read it manually)
    g = (gate or "").upper()
    if g == "LOUD":
        add(0, "Vol gate", 1, "gate LOUD: enter, 0.6x size, 4x ATR stop, 2R target, 96h limit")
    elif g == "NORMAL":
        add(0, "Vol gate", 0, "gate NORMAL: wait for LOUD (v6.1 backtest: NORMAL-hour entries lost after costs)")
    elif g == "QUIET":
        add(0, "Vol gate", 0, "gate QUIET: no new trades")
    else:
        add(0, "Vol gate", 0, "pass --gate LOUD|NORMAL|QUIET (scripts/volgate.py)", manual=True)

    # 1 HTF bias
    t = htf.get("trend")
    if (long and t == "uptrend") or (not long and t == "downtrend"):
        add(1, "HTF bias", 1, f"{htf['timeframe']} trend is {t}")
    elif t == "range":
        rr = htf.get("recent_range", {})
        pos = rr.get("price_position_pct")
        edge_ok = pos is not None and ((long and pos <= 25) or (not long and pos >= 75))
        add(1, "HTF bias", 1 if edge_ok else 0, f"{htf['timeframe']} is a range; price at {pos}% of it" + (" (at the right edge)" if edge_ok else " (not at the edge)"))
    else:
        add(1, "HTF bias", 0, f"{htf['timeframe']} trend is {t}: against the trade")

    # 2 EMA regime
    stack = ltf.get("ema_stack", "")
    side = ltf.get("price_vs_ema200")
    ok = (long and stack.startswith("bullish") and side == "above") or (not long and stack.startswith("bearish") and side == "below")
    half = (long and side == "above") or (not long and side == "below")
    add(2, "EMA regime", 1 if ok else 0, f"{ltf['timeframe']} stack {stack}, price {side} 200 EMA" + ("" if ok else (" (partial: right side of 200 but stack not aligned)" if half else "")))

    # 3 Location (mechanical proxy: within 0.5 ATR of a tier-1 level or value)
    atr = ltf.get("atr14") or 0
    near = [lv for lv in ltf.get("levels_by_distance", []) if lv.get("distance_atr") is not None and abs(lv["distance_atr"]) <= 0.5
            and lv["level"] in ("ema21", "session_vwap", "prior_day_high", "prior_day_low", "today_open", "last_swing_low", "last_swing_high",
                                "equal_lows", "equal_highs", "range60_low", "range60_high")]
    if near:
        add(3, "Location", 1, "price within 0.5 ATR of " + ", ".join(f"{lv['level']} {lv['price']}" for lv in near[:3]))
    else:
        add(3, "Location", 0, "price is not within 0.5 ATR of a tier-1 level or value zone (mid-range)", manual=True)

    # 4 Trigger (mechanical proxy from flags)
    flags = " | ".join(ltf.get("flags", []))
    trig_words = ["SWEEP OF LOWS", "VWAP RECLAIM", "CLOSE ABOVE SWING HIGH", "PULLBACK TO VALUE (long)", "CLOSE BACK INSIDE LOWER BAND"] if long else \
                 ["SWEEP OF HIGHS", "VWAP LOSS", "CLOSE BELOW SWING LOW", "PULLBACK TO VALUE (short)", "CLOSE BACK INSIDE UPPER BAND"]
    hit = [w for w in trig_words if w in flags]
    add(4, "Trigger", 1 if hit else 0, ("flagged: " + ", ".join(hit)) if hit else "no closed-candle trigger flagged on the setup timeframe", manual=not hit)

    # 5 Volume
    rv = ltf.get("rvol_last_closed")
    add(5, "Volume", 1 if (rv is not None and rv >= 1.5) else 0, f"RVOL on last closed candle {rv}")

    # 6 Positioning
    f = (derivs or {}).get("funding_rate_8h_pct")
    if f is None:
        add(6, "Positioning", 0, "funding unknown (no derivatives data): cannot award the point")
    else:
        crowded_same = (long and f > 0.03) or (not long and f < -0.02)
        crowded_against = (long and f < -0.01) or (not long and f > 0.03)
        pts = 0 if crowded_same else 1
        add(6, "Positioning", pts, f"funding {f:+.3f}%/8h " + ("crowded in the trade direction" if crowded_same else "crowded against the trade (fuel)" if crowded_against else "neutral"))

    # 7 Session
    h = now.hour; wd = now.weekday()
    us_open = events.et_to_utc(now.date(), 9, 30).hour
    in_overlap = us_open <= h < us_open + 3
    in_london = 7 <= h < 13
    if wd >= 5:
        add(7, "Session", 0, "weekend")
    elif in_overlap:
        add(7, "Session", 1, "London/NY overlap or first NY hours")
    elif in_london:
        add(7, "Session", 1, "London session")
    else:
        add(7, "Session", 0, f"{h:02d}:xx UTC is outside the best windows")

    # 8 Calendar
    t1 = events.next_tier1(now)
    if t1.get("loaded") and t1.get("inside_no_trade_window"):
        add(8, "Calendar", 0, t1["warning"])
    else:
        add(8, "Calendar", 1, f"next tier-1: {t1.get('event')} at {t1.get('utc')} UTC" if t1.get("loaded") else "calendar not loaded for this year (assumed clear)")

    # 9 Reward
    if entry and stop and target:
        risk = abs(entry - stop)
        reward = (target - entry) if long else (entry - target)
        rr_net = reward / risk - (cost_r or 0) if risk else 0
        add(9, "Reward", 1 if rr_net >= 2 else 0, f"net R:R to target {rr_net:.2f} after {cost_r:.2f}R of costs ({fees})")
    else:
        add(9, "Reward", 0, "pass --entry/--stop/--target to score reward", manual=True)

    # 10 Stop quality
    if entry and stop and atr:
        dist = abs(entry - stop)
        beyond_noise = dist >= 1.0 * atr
        pts = 1 if (beyond_noise and cost_r <= 0.20) else 0
        why = f"stop {dist / atr:.2f} ATR ({ltf['timeframe']}), costs {cost_r:.2f}R at {fees}"
        if not beyond_noise:
            why += ": inside the noise (under 1 ATR)"
        elif cost_r > 0.33:
            why += ": above 0.33R, NO (cost gate)"
        elif cost_r > 0.20:
            why += ": 0.20-0.33R, half size"
        add(10, "Stop quality", pts, why)
    else:
        add(10, "Stop quality", 0, "pass --entry/--stop to score the stop", manual=True)

    total = sum(r["points"] for r in rows)
    manual = [r["factor"] for r in rows if r["manual"]]
    need = {"A+": 10, "A": 9, "B": 8}
    if alt:
        need = {k: v + 1 for k, v in need.items()}
    grade = "A+" if total >= need["A+"] else "A" if total >= need["A"] else "B" if total >= need["B"] else "skip"
    blocked = None
    if g == "QUIET":
        blocked = "volatility gate QUIET"
    elif g == "NORMAL":
        blocked = "volatility gate NORMAL: wait for LOUD"
    elif cost_r is not None and cost_r > 0.33:
        blocked = f"costs {cost_r:.2f}R > 0.33R"
    if blocked:
        grade = "skip"
    return {"direction": direction, "score": total, "max": 11, "grade": grade, "alt_thresholds": alt, "blocked": blocked,
            "cost_r": None if cost_r is None else round(cost_r, 3), "fees": fees,
            "manual_factors_unscored": manual, "rows": rows,
            "note": "factors marked manual were scored 0 because they need a chart read or entry/stop/target; re-score with them" if manual else None}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--snapshot", required=True, help="snapshot.py --json output with a bias and a setup timeframe")
    ap.add_argument("--derivs", help="fetch_ohlcv.py --derivs --out output")
    ap.add_argument("--direction", choices=["long", "short"], required=True)
    ap.add_argument("--entry", type=float); ap.add_argument("--stop", type=float); ap.add_argument("--target", type=float)
    ap.add_argument("--alt", action="store_true", help="apply the stricter alt/meme thresholds")
    ap.add_argument("--gate", help="LOUD | NORMAL | QUIET (from scripts/volgate.py)")
    ap.add_argument("--fees", default="ndax", help="ndax | kraken | kraken10k | coinbase | low | <taker %% per side>")
    ap.add_argument("--maker", action="store_true", help="entry is a limit (maker) order")
    ap.add_argument("--now", help="ISO UTC override")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    snap = load(a.snapshot)
    derivs = load(a.derivs) if a.derivs else {}
    now = datetime.strptime(a.now, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc) if a.now else datetime.now(timezone.utc)
    htf, ltf = pick_timeframes(snap)
    res = score(htf, ltf, derivs, a.direction, now, a.entry, a.stop, a.target, a.alt, a.gate, a.fees, a.maker)
    res["bias_timeframe"] = htf["timeframe"]; res["setup_timeframe"] = ltf["timeframe"]; res["price"] = ltf["price"]
    if a.json:
        print(json.dumps(res, indent=2)); return
    print(f"CONFLUENCE {a.direction.upper()} @ {ltf['price']}  bias {htf['timeframe']} / setup {ltf['timeframe']}  ->  {res['score']}/11  grade {res['grade']}" + (f"  BLOCKED: {res['blocked']}" if res.get("blocked") else ""))
    for r in res["rows"]:
        print(f"  [{r['points']}] {r['factor']:>2}. {r['name']:<12} {r['why']}" + ("  (manual)" if r["manual"] else ""))
    if res["note"]:
        print("  note: " + res["note"])


if __name__ == "__main__":
    main()
