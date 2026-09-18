#!/usr/bin/env python3
"""Expectancy and discipline statistics from a trading journal CSV.

  python3 journal_stats.py trades.csv
  python3 journal_stats.py trades.csv --json

Expected columns (see assets/journal-template.csv): date_utc,time_utc,symbol,direction,
playbook,grade,entry,stop,target,exit,risk_pct,size,r_multiple,fees_r,planned,
execution_grade,mistake,notes.  r_multiple is computed from entry/stop/exit when blank.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tradestats import format_summary, group_by, summarize  # noqa: E402


def to_float(v, default=None):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def session_of(time_utc: str) -> str:
    try:
        h = int(time_utc.split(":")[0])
    except (ValueError, AttributeError, IndexError):
        return "unknown"
    if 0 <= h < 7:
        return "asia 00-07"
    if 7 <= h < 13:
        return "london 07-13"
    if 13 <= h < 21:
        return "new york 13-21"
    return "late us 21-24"


def load(path: str):
    with open(path, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    trades = []
    skipped = 0
    for r in rows:
        entry, stop, exit_ = to_float(r.get("entry")), to_float(r.get("stop")), to_float(r.get("exit"))
        rm = to_float(r.get("r_multiple"))
        if rm is None:
            if entry is None or stop is None or exit_ is None or entry == stop:
                skipped += 1
                continue
            direction = (r.get("direction") or "").lower()
            if direction not in ("long", "short"):
                direction = "long" if stop < entry else "short"
            move = (exit_ - entry) if direction == "long" else (entry - exit_)
            rm = move / abs(entry - stop)
            fees = to_float(r.get("fees_r"), 0.0) or 0.0
            rm -= fees
        r = dict(r)
        r["r_multiple"] = rm
        r["session"] = session_of(r.get("time_utc", ""))
        r["planned"] = (r.get("planned") or "").strip().lower() or "unknown"
        r["grade"] = (r.get("grade") or "").strip().upper() or "unknown"
        r["mistake"] = (r.get("mistake") or "none").strip().lower() or "none"
        trades.append(r)
    return trades, skipped


def discipline(trades):
    n = len(trades)
    unplanned = [t for t in trades if t["planned"] in ("no", "n", "false", "0")]
    mistakes = {}
    for t in trades:
        if t["mistake"] != "none":
            mistakes[t["mistake"]] = mistakes.get(t["mistake"], 0) + 1
    risk = [to_float(t.get("risk_pct")) for t in trades]
    risk = [x for x in risk if x is not None]
    over = sum(1 for x in risk if x > 1.0)
    exec_grades = [(to_float(t.get("execution_grade")), t["r_multiple"]) for t in trades]
    exec_grades = [(g, r) for g, r in exec_grades if g is not None]
    good = [r for g, r in exec_grades if g >= 4]
    bad = [r for g, r in exec_grades if g <= 2]
    breaks = set()
    for idx, t in enumerate(trades):
        if t["planned"] in ("no", "n", "false", "0") or t["mistake"] != "none":
            breaks.add(idx)
        rp = to_float(t.get("risk_pct"))
        if rp is not None and rp > 1.0:
            breaks.add(idx)
    return {
        "unplanned_trades": len(unplanned),
        "unplanned_total_r": round(sum(t["r_multiple"] for t in unplanned), 2),
        "trades_over_1pct_risk": over,
        "mistake_counts": dict(sorted(mistakes.items(), key=lambda kv: -kv[1])),
        "avg_r_when_execution_ge4": round(sum(good) / len(good), 3) if good else None,
        "avg_r_when_execution_le2": round(sum(bad) / len(bad), 3) if bad else None,
        "trades_with_any_rule_break": len(breaks),
        "rule_break_rate_pct": round(100 * len(breaks) / n, 1) if n else None,
        "avg_r_clean_trades": round(sum(t["r_multiple"] for i, t in enumerate(trades) if i not in breaks) / max(1, n - len(breaks)), 3) if n > len(breaks) else None,
        "avg_r_rule_break_trades": round(sum(t["r_multiple"] for i, t in enumerate(trades) if i in breaks) / len(breaks), 3) if breaks else None,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csv")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    trades, skipped = load(a.csv)
    if not trades:
        sys.exit("no usable trades (need r_multiple, or entry+stop+exit)")
    rs = [t["r_multiple"] for t in trades]
    report = {
        "overall": summarize(rs),
        "by_playbook": {k: summarize(v) for k, v in group_by(trades, "playbook").items()},
        "by_session": {k: summarize(v) for k, v in group_by(trades, "session").items()},
        "by_symbol": {k: summarize(v) for k, v in group_by(trades, "symbol").items()},
        "by_grade": {k: summarize(v) for k, v in group_by(trades, "grade").items()},
        "by_direction": {k: summarize(v) for k, v in group_by(trades, "direction").items()},
        "planned_vs_unplanned": {k: summarize(v) for k, v in group_by(trades, "planned").items()},
        "discipline": discipline(trades),
        "skipped_rows": skipped,
    }
    if a.json:
        print(json.dumps(report, indent=2))
        return
    print(format_summary(report["overall"], "overall"))
    for section in ("by_playbook", "by_session", "by_symbol", "by_grade", "by_direction", "planned_vs_unplanned"):
        print()
        print(f"-- {section.replace('_', ' ')} --")
        for k, s in sorted(report[section].items(), key=lambda kv: -(kv[1].get("n") or 0)):
            print(f"  {k:<22} n={s['n']:<4} win {s['win_rate_pct']:>5}%  exp {s['expectancy_r']:+.2f}R  "
                  f"total {s['total_r']:+.1f}R  pf {s['profit_factor']}")
    d = report["discipline"]
    print()
    print("-- discipline --")
    print(f"  unplanned trades: {d['unplanned_trades']} (total {d['unplanned_total_r']:+}R)")
    print(f"  trades risking > 1%: {d['trades_over_1pct_risk']}")
    print(f"  mistakes: {d['mistake_counts'] or 'none logged'}")
    print(f"  avg R with execution grade >= 4: {d['avg_r_when_execution_ge4']}   <= 2: {d['avg_r_when_execution_le2']}")
    print(f"  trades with any rule break: {d['trades_with_any_rule_break']} ({d['rule_break_rate_pct']}%)  "
          f"avg R clean {d['avg_r_clean_trades']} vs rule-break {d['avg_r_rule_break_trades']}")
    if skipped:
        print(f"  ({skipped} rows skipped: missing r_multiple and entry/stop/exit)")


if __name__ == "__main__":
    main()
