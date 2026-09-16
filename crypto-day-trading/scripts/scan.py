#!/usr/bin/env python3
"""Scan several pairs for playbook conditions in one call.

  python3 scan.py                                   # BTC, ETH, SOL on 4h (bias) + 15m (setup)
  python3 scan.py --symbols BTC,ETH,SOL,XRP,DOGE --htf 4h --ltf 15m --derivs
  python3 scan.py --symbols BTC --ltf 5m --json scan.json

For each symbol it fetches the higher-timeframe candles (bias) and the lower-timeframe
candles (setup), runs the same analysis as snapshot.py, and prints one line per pair
plus every setup flag. Flags are reasons to LOOK at a chart, not signals. A pair with
zero flags is a pair to leave alone right now.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fetch_ohlcv import fetch_candles, fetch_derivs, interpret_derivs  # noqa: E402
from snapshot import analyze, clock, clock_summary  # noqa: E402


def rows_to_data(rows):
    return {"ts": [datetime.fromtimestamp(r[0] / 1000, tz=timezone.utc) for r in rows],
            "open": [r[1] for r in rows], "high": [r[2] for r in rows], "low": [r[3] for r in rows],
            "close": [r[4] for r in rows], "volume": [r[5] for r in rows]}


def scan_symbol(sym: str, htf: str, ltf: str, limit: int, exchange: str, derivs: bool, swing_n: int, now) -> dict:
    out = {"symbol": sym, "errors": []}
    for key, tf in (("htf", htf), ("ltf", ltf)):
        try:
            source, rows = fetch_candles(sym, tf, limit, exchange)
            s = analyze(rows_to_data(rows), swing_n, now)
            s["source"] = source
            out[key] = s
        except SystemExit as exc:
            out["errors"].append(f"{tf}: {exc}")
        time.sleep(0.25)
    if derivs:
        d = fetch_derivs(sym)
        d["interpretation"] = interpret_derivs(d)
        out["derivs"] = d
    return out


def line(res: dict) -> str:
    h, l = res.get("htf"), res.get("ltf")
    if not h or not l:
        return f"{res['symbol']:<9} ERROR {'; '.join(res['errors'])}"
    d = res.get("derivs") or {}
    fund = d.get("funding_rate_8h_pct")
    fund_s = f"{fund:+.3f}%" if fund is not None else "n/a"
    oi = d.get("oi_change_24h_pct")
    oi_s = f"{oi:+.1f}%" if oi is not None else "n/a"
    nflags = len(h["flags"]) + len(l["flags"])
    return (f"{res['symbol']:<9} {l['price']:>12.6g}  HTF {h['trend']:<9} {h['ema_stack'][:7]:<7} "
            f"LTF {l['trend']:<9} atr {l['atr14_pct']:>5}%  rvol {str(l['rvol_last_closed']):>5}  "
            f"21ema {str(l['ema'].get('ema21_distance_atr')):>5} atr  vwap {str(l.get('price_vs_vwap')):<5} "
            f"fund {fund_s:>8}  oi24h {oi_s:>6}  flags {nflags}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--symbols", default="BTC,ETH,SOL")
    ap.add_argument("--htf", default="4h")
    ap.add_argument("--ltf", default="15m")
    ap.add_argument("--limit", type=int, default=300)
    ap.add_argument("--exchange", default="auto")
    ap.add_argument("--derivs", action="store_true", help="also fetch funding / OI per symbol")
    ap.add_argument("--swing-n", type=int, default=3)
    ap.add_argument("--json", help="write full results here")
    a = ap.parse_args()

    now = datetime.now(timezone.utc)
    ck = clock(now)
    print(clock_summary(ck))
    print()
    results = []
    for sym in [s.strip() for s in a.symbols.split(",") if s.strip()]:
        results.append(scan_symbol(sym, a.htf, a.ltf, a.limit, a.exchange, a.derivs, a.swing_n, now))
    results.sort(key=lambda r: -(len(r.get("htf", {}).get("flags", [])) + len(r.get("ltf", {}).get("flags", []))))

    print(f"{'pair':<9} {'price':>12}  {'bias (' + a.htf + ')':<22} {'setup (' + a.ltf + ')':<43} positioning")
    for res in results:
        print(line(res))
    print()
    for res in results:
        h, l = res.get("htf"), res.get("ltf")
        if not h or not l:
            continue
        flags = [f"[{a.htf}] " + f for f in h["flags"]] + [f"[{a.ltf}] " + f for f in l["flags"]]
        if flags or res.get("derivs"):
            print(f"{res['symbol']}:")
            for f in flags:
                print("  - " + f)
            for note in (res.get("derivs") or {}).get("interpretation", []):
                print("  - positioning: " + note)
            if not flags:
                print("  - no setup flags")
    if a.json:
        with open(a.json, "w", encoding="utf-8") as fh:
            json.dump({"generated_utc": now.isoformat(), "clock": ck, "results": results}, fh, indent=2, default=str)
        print(f"\njson written to {a.json}")


if __name__ == "__main__":
    main()
