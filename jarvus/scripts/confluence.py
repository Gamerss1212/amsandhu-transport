#!/usr/bin/env python3
"""Confluence score for a candidate trade, from snapshot/scan JSON plus derivatives JSON.

  python3 fetch_ohlcv.py --symbol BTCUSDT --interval 4h  --limit 300 --out /tmp/btc_4h.csv
  python3 fetch_ohlcv.py --symbol BTCUSDT --interval 15m --limit 600 --out /tmp/btc_15m.csv
  python3 snapshot.py /tmp/btc_4h.csv /tmp/btc_15m.csv --json /tmp/snap.json
  python3 fetch_ohlcv.py --symbol BTCUSDT --derivs --out /tmp/derivs.json
  python3 confluence.py --snapshot /tmp/snap.json --derivs /tmp/derivs.json --direction long
  python3 confluence.py --snapshot /tmp/snap.json --direction short --entry 76050 --stop 76480 --target 75200

Scores the ten factors from the strategy encyclopedia (Part 1). Seven are computed
mechanically; the location, trigger, and reward factors need the entry/stop/target
(pass them) or a human reading of the chart (then they are reported as "manual").
The score is a filter, not a signal: 9-10 A+, 8 A, 7 B (half risk), 6 or less skip.
Alts and memes need one point more at every grade (--alt).
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


def score(htf: dict, ltf: dict, derivs: dict, direction: str, now: datetime, entry=None, stop=None, target=None, alt=False):
    long = direction == "long"
    rows = []

    def add(n, name, pts, why, manual=False):
        rows.append({"factor": n, "name": name, "points": pts, "why": why, "manual": manual})

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
        rr_net = reward / risk - 0.14 if risk else 0
        add(9, "Reward", 1 if rr_net >= 2 else 0, f"net R:R to target {rr_net:.2f}")
    else:
        add(9, "Reward", 0, "pass --entry/--stop/--target to score reward", manual=True)

    # 10 Stop quality
    if entry and stop and atr:
        dist = abs(entry - stop)
        pts = 1 if 0.5 * atr <= dist <= 2.5 * atr else 0
        add(10, "Stop quality", pts, f"stop distance {dist:.6g} = {dist / atr:.2f} ATR ({ltf['timeframe']})")
    else:
        add(10, "Stop quality", 0, "pass --entry/--stop to score the stop", manual=True)

    total = sum(r["points"] for r in rows)
    manual = [r["factor"] for r in rows if r["manual"]]
    need = {"A+": 9, "A": 8, "B": 7}
    if alt:
        need = {k: v + 1 for k, v in need.items()}
    grade = "A+" if total >= need["A+"] else "A" if total >= need["A"] else "B" if total >= need["B"] else "skip"
    return {"direction": direction, "score": total, "max": 10, "grade": grade, "alt_thresholds": alt,
            "manual_factors_unscored": manual, "rows": rows,
            "note": "factors marked manual were scored 0 because they need a chart read or entry/stop/target; re-score with them" if manual else None}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--snapshot", required=True, help="snapshot.py --json output with a bias and a setup timeframe")
    ap.add_argument("--derivs", help="fetch_ohlcv.py --derivs --out output")
    ap.add_argument("--direction", choices=["long", "short"], required=True)
    ap.add_argument("--entry", type=float); ap.add_argument("--stop", type=float); ap.add_argument("--target", type=float)
    ap.add_argument("--alt", action="store_true", help="apply the stricter alt/meme thresholds")
    ap.add_argument("--now", help="ISO UTC override")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    snap = load(a.snapshot)
    derivs = load(a.derivs) if a.derivs else {}
    now = datetime.strptime(a.now, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc) if a.now else datetime.now(timezone.utc)
    htf, ltf = pick_timeframes(snap)
    res = score(htf, ltf, derivs, a.direction, now, a.entry, a.stop, a.target, a.alt)
    res["bias_timeframe"] = htf["timeframe"]; res["setup_timeframe"] = ltf["timeframe"]; res["price"] = ltf["price"]
    if a.json:
        print(json.dumps(res, indent=2)); return
    print(f"CONFLUENCE {a.direction.upper()} @ {ltf['price']}  bias {htf['timeframe']} / setup {ltf['timeframe']}  ->  {res['score']}/10  grade {res['grade']}")
    for r in res["rows"]:
        print(f"  [{r['points']}] {r['factor']:>2}. {r['name']:<12} {r['why']}" + ("  (manual)" if r["manual"] else ""))
    if res["note"]:
        print("  note: " + res["note"])


if __name__ == "__main__":
    main()
