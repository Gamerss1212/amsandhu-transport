#!/usr/bin/env python3
"""Trade journal CLI: record a plan BEFORE the outcome, close it after, review with journal_stats.py.

  python3 journal.py init                                   # create trades.csv with the right header
  python3 journal.py add --symbol BTCUSDT --playbook 1-trend-pullback --grade A \
        --entry 64350 --stop 63780 --target 65900 --risk-pct 1 --account 10000 --planned yes \
        --notes "NY open pullback to 21 EMA + VWAP"
  python3 journal.py close --id 3 --exit 65100 --execution-grade 4 --mistake none --notes "took 1/2 at PDH"
  python3 journal.py open                                    # trades without an exit
  python3 journal.py last 10
  python3 journal.py stats                                   # delegates to journal_stats.py

The file defaults to ./trades.csv, or $CRYPTO_JOURNAL if set, or --file.
Direction is inferred from the stop (below entry = long). R is computed on close,
net of --fees-r (default 0.1R, a reasonable round-trip cost on a ~1% stop).
"""

from __future__ import annotations

import argparse
import csv
import os
import subprocess
import sys
from datetime import datetime, timezone

HEADER = ["id", "date_utc", "time_utc", "symbol", "direction", "playbook", "grade", "entry", "stop", "target",
          "exit", "risk_pct", "size", "r_multiple", "fees_r", "planned", "execution_grade", "mistake", "notes"]

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


def journal_path(args) -> str:
    return args.file or os.environ.get("CRYPTO_JOURNAL") or "trades.csv"


def load(path: str):
    if not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8") as fh:
        return [dict(r) for r in csv.DictReader(fh)]


def save(path: str, rows) -> None:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=HEADER, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in HEADER})


def fnum(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def cmd_init(args):
    path = journal_path(args)
    if os.path.exists(path):
        print(f"{path} already exists ({len(load(path))} rows)")
        return
    save(path, [])
    print(f"created {path}")


def cmd_add(args):
    path = journal_path(args)
    rows = load(path)
    if args.entry == args.stop:
        sys.exit("entry and stop must differ")
    direction = args.direction or ("long" if args.stop < args.entry else "short")
    stop_dist = abs(args.entry - args.stop)
    warnings = []
    if args.target is not None:
        reward = (args.target - args.entry) if direction == "long" else (args.entry - args.target)
        rr = reward / stop_dist
        if reward <= 0:
            warnings.append(f"target is on the wrong side for a {direction}")
        elif rr < 2:
            warnings.append(f"target is only {rr:.2f}R; the skill's minimum is 2R")
    if args.risk_pct > 2:
        warnings.append(f"risk {args.risk_pct}% exceeds the 2% ceiling")
    size = args.size
    if size is None and args.account:
        size = args.account * args.risk_pct / 100 / stop_dist
    now = datetime.now(timezone.utc)
    next_id = max([int(r["id"]) for r in rows if str(r.get("id", "")).isdigit()] + [0]) + 1
    row = {"id": next_id, "date_utc": args.date or now.strftime("%Y-%m-%d"), "time_utc": args.time or now.strftime("%H:%M"),
           "symbol": args.symbol.upper(), "direction": direction, "playbook": args.playbook, "grade": args.grade.upper(),
           "entry": args.entry, "stop": args.stop, "target": args.target if args.target is not None else "",
           "exit": "", "risk_pct": args.risk_pct, "size": round(size, 6) if size else "", "r_multiple": "",
           "fees_r": args.fees_r, "planned": args.planned, "execution_grade": "", "mistake": "", "notes": args.notes or ""}
    rows.append(row)
    save(path, rows)
    print(f"logged trade #{next_id}: {direction.upper()} {row['symbol']} entry {args.entry} stop {args.stop} "
          f"target {row['target']} risk {args.risk_pct}%" + (f" size {row['size']}" if size else ""))
    for w in warnings:
        print("WARNING: " + w)


def cmd_close(args):
    path = journal_path(args)
    rows = load(path)
    target = next((r for r in rows if str(r.get("id")) == str(args.id)), None)
    if target is None:
        sys.exit(f"no trade with id {args.id}")
    if target.get("exit") not in ("", None) and not args.force:
        sys.exit(f"trade #{args.id} is already closed at {target['exit']} (use --force to overwrite)")
    entry, stop = fnum(target["entry"]), fnum(target["stop"])
    direction = target.get("direction") or ("long" if stop < entry else "short")
    move = (args.exit - entry) if direction == "long" else (entry - args.exit)
    fees_r = args.fees_r if args.fees_r is not None else (fnum(target.get("fees_r")) or 0.0)
    r_mult = move / abs(entry - stop) - fees_r
    target["exit"] = args.exit
    target["r_multiple"] = round(r_mult, 3)
    target["fees_r"] = fees_r
    if args.execution_grade is not None:
        target["execution_grade"] = args.execution_grade
    if args.mistake:
        target["mistake"] = args.mistake
    if args.notes:
        target["notes"] = (target.get("notes") or "") + (" | " if target.get("notes") else "") + args.notes
    save(path, rows)
    closed = [fnum(r["r_multiple"]) for r in rows if fnum(r.get("r_multiple")) is not None]
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    today_r = sum(fnum(r["r_multiple"]) for r in rows if r.get("date_utc") == today and fnum(r.get("r_multiple")) is not None)
    print(f"closed #{args.id} at {args.exit}: {r_mult:+.2f}R (net of {fees_r}R costs). "
          f"Today {today_r:+.2f}R. Lifetime {sum(closed):+.2f}R over {len(closed)} trades.")
    if today_r <= -3:
        print("DAILY LOSS LIMIT REACHED (-3R): stop trading for the day.")


def cmd_open(args):
    rows = [r for r in load(journal_path(args)) if r.get("exit") in ("", None)]
    if not rows:
        print("no open trades")
        return
    for r in rows:
        print(f"#{r['id']} {r['date_utc']} {r['time_utc']} {r['direction'].upper():<5} {r['symbol']:<9} "
              f"entry {r['entry']} stop {r['stop']} target {r['target']} risk {r['risk_pct']}% [{r['playbook']}/{r['grade']}]")


def cmd_last(args):
    rows = load(journal_path(args))[-args.n:]
    for r in rows:
        status = f"{fnum(r['r_multiple']):+.2f}R" if fnum(r.get("r_multiple")) is not None else "open"
        print(f"#{r['id']} {r['date_utc']} {r['time_utc']} {r['direction'].upper():<5} {r['symbol']:<9} "
              f"{r['playbook']}/{r['grade']} planned={r['planned']} -> {status} {('(' + r['mistake'] + ')') if r.get('mistake') and r['mistake'] != 'none' else ''}")


def cmd_stats(args):
    subprocess.call([sys.executable, os.path.join(HERE, "journal_stats.py"), journal_path(args)] + (["--json"] if args.json else []))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--file", help="journal CSV (default ./trades.csv or $CRYPTO_JOURNAL)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init").set_defaults(fn=cmd_init)

    a = sub.add_parser("add")
    a.add_argument("--symbol", required=True)
    a.add_argument("--playbook", required=True, help="e.g. 1-trend-pullback, 2-range-fade, 4-sweep-reversal")
    a.add_argument("--grade", default="B", help="A or B")
    a.add_argument("--entry", type=float, required=True)
    a.add_argument("--stop", type=float, required=True)
    a.add_argument("--target", type=float)
    a.add_argument("--direction", choices=["long", "short"])
    a.add_argument("--risk-pct", type=float, default=1.0)
    a.add_argument("--account", type=float, help="equity, to compute size")
    a.add_argument("--size", type=float)
    a.add_argument("--fees-r", type=float, default=0.1)
    a.add_argument("--planned", default="yes", choices=["yes", "no"])
    a.add_argument("--date"); a.add_argument("--time")
    a.add_argument("--notes")
    a.set_defaults(fn=cmd_add)

    c = sub.add_parser("close")
    c.add_argument("--id", required=True)
    c.add_argument("--exit", type=float, required=True)
    c.add_argument("--fees-r", type=float)
    c.add_argument("--execution-grade", type=int, choices=[1, 2, 3, 4, 5])
    c.add_argument("--mistake", help="none, chased, moved stop, early exit, oversized, revenge, ...")
    c.add_argument("--notes")
    c.add_argument("--force", action="store_true")
    c.set_defaults(fn=cmd_close)

    sub.add_parser("open").set_defaults(fn=cmd_open)
    l = sub.add_parser("last"); l.add_argument("n", type=int, nargs="?", default=10); l.set_defaults(fn=cmd_last)
    s = sub.add_parser("stats"); s.add_argument("--json", action="store_true"); s.set_defaults(fn=cmd_stats)

    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
