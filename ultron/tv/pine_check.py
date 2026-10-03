#!/usr/bin/env python3
"""Compile Pine Script with TradingView's own compiler service and print errors and warnings.

  python3 ultron/tv/pine_check.py FILE.pine [FILE2.pine ...]     # exit 1 if any file has errors
"""
import json
import subprocess
import sys

URL = "https://pine-facade.tradingview.com/pine-facade/translate_light?user_name=Guest&pine_id=00000000-0000-0000-0000-000000000000"


def check(path):
    out = subprocess.run(["curl", "-sS", "-m", "60", "-X", "POST", URL, "-H", "Referer: https://www.tradingview.com/",
                          "-F", f"source=<{path}"], capture_output=True, text=True).stdout
    try:
        r = json.loads(out)
    except ValueError:
        return None, [f"no JSON from compiler: {out[:200]}"], []
    res = r.get("result") or {}
    errs = res.get("errors2") or res.get("errors") or []
    warns = res.get("warnings2") or res.get("warnings") or []
    fmt = lambda e: f"line {((e.get('start') or {}).get('line'))}: {e.get('message')}"     # noqa: E731
    if not r.get("success"):
        errs = errs or [{"message": r.get("reason") or str(r)[:300]}]
    return bool(r.get("success")) and not errs, [fmt(e) for e in errs], [fmt(w) for w in warns]


bad = 0
for p in sys.argv[1:]:
    ok, errs, warns = check(p)
    print(f"{p}: {'OK' if ok else 'ERRORS'} ({len(errs)} errors, {len(warns)} warnings)")
    for e in errs[:30]:
        print("  E", e)
    for w in warns[:30]:
        print("  W", w)
    bad += not ok
sys.exit(1 if bad else 0)
