#!/usr/bin/env python3
"""Jarvus Terminal launcher.

    python3 run.py                 start the dashboard (default)
    python3 run.py scan            one scan printed to the terminal, no server
    python3 run.py resolve         grade every prediction whose horizon has passed
    python3 run.py learn           what the app has measured about itself
    python3 run.py selftest        verify the install
    python3 run.py --port 9000     start on a different port

No pip install. Python 3.8+ and an internet connection are the only requirements.
"""

from __future__ import annotations

import argparse
import os
import sys
import webbrowser

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def cmd_scan(args):
    import config
    from engine import scanner
    r = scanner.scan(deep_n=args.n, fee_tier=args.fee_tier, write=not args.no_write)
    u = r["universe"]
    print(f"\n  {u['discovered']:,} markets seen -> {u['liquid']} liquid -> {u['assets_after_dedupe']} assets "
          f"-> {u['analysed']} analysed in {r['elapsed_s']}s")
    print(f"  fee tier: {r['fee_tier']} · predictions logged: {r['predictions_written']} "
          f"(graded in {r['resolve_horizon_h']}h)\n")
    print(f"  {'MARKET':<14}{'STATE':<8}{'HEAT':>6}{'24H':>9}{'MOVE/BAR':>10}{'PLAN':>7}{'GRADE':>7}{'COST':>7}")
    print("  " + "-" * 74)
    for m in r["markets"][:args.n]:
        if m.get("error"):
            print(f"  {m['symbol'][:13]:<14}{m['error']}")
            continue
        g, s, st = m["gate"], m["signal"], m["structure"]
        print(f"  {m['base'][:13]:<14}{g['label']:<8}{g['blow_score']:>6.2f}{m['change_24h_pct']:>+8.1f}%"
              f"{st['atr_pct']:>9.2f}%{s['verdict']:>7}{s['confluence']['grade']:>7}"
              f"{s['confluence']['cost_r']*100:>6.0f}%")
    print()
    top = next((m for m in r["markets"] if not m.get("error")), None)
    if top:
        print(f"  Hottest: {top['symbol']} — {top['gate']['explain']}\n")
    print("  Heat forecasts how much a market moves, never which way.\n")


def cmd_resolve(args):
    from engine import learn
    print("  grading predictions past their horizon…")
    r = learn.resolve_due(args.limit)
    print(f"  graded {r['graded']}, {r['failed']} had no forward data\n")


def cmd_learn(args):
    import json
    from engine import learn
    print(json.dumps(learn.summary(), indent=2, default=str))


def cmd_selftest(args):
    import selftest
    sys.exit(selftest.main())


def cmd_serve(args):
    import config
    if args.port:
        config.PORT = args.port
    if args.host:
        config.HOST = args.host
    import server
    if not args.no_browser:
        url = f"http://{config.HOST}:{config.PORT}"
        try:
            webbrowser.open(url)
        except Exception:      # noqa: BLE001 - headless machines have no browser
            pass
    server.serve()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd")

    p = sub.add_parser("scan", help="one scan, printed here")
    p.add_argument("-n", type=int, default=20)
    p.add_argument("--fee-tier", default=None)
    p.add_argument("--no-write", action="store_true", help="do not log predictions")
    p.set_defaults(fn=cmd_scan)

    p = sub.add_parser("resolve", help="grade predictions whose horizon has passed")
    p.add_argument("--limit", type=int, default=200)
    p.set_defaults(fn=cmd_resolve)

    sub.add_parser("learn", help="what the app has measured about itself").set_defaults(fn=cmd_learn)
    sub.add_parser("selftest", help="verify the install").set_defaults(fn=cmd_selftest)

    p = sub.add_parser("serve", help="start the dashboard (default)")
    p.add_argument("--port", type=int); p.add_argument("--host")
    p.add_argument("--no-browser", action="store_true")
    p.set_defaults(fn=cmd_serve)

    ap.add_argument("--port", type=int); ap.add_argument("--host")
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()
    (getattr(args, "fn", None) or cmd_serve)(args)


if __name__ == "__main__":
    main()
