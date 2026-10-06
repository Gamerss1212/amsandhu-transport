"""One paper-trading day, in order, for the task scheduler (Phase 3 daily schedule).

    python -m quantagents --config config/my_universe.yaml daily --yahoo SPY EFA TLT --out data/prices.csv

1. ``data fetch``: a new snapshot in the append-only store (never overwrites).
2. ``data export``: adjusted prices to ``--out``, with the sources' caveats in the sidecar.
3. ``cycle``: one paper cycle, but only when the data has a trading day the last cycle has not
   seen. The same day is never run twice (it would re-process orders and stops).
4. ``watchdog``: engages the kill switch if cycles or data have gone stale.

Everything printed is also appended to ``runs/daily.log``. Paper trading only: no step can
send a real order.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
from collections.abc import Callable
from datetime import UTC, date, datetime
from pathlib import Path

from quantagents.watchdog import last_data_date

LOG_FILE = Path("runs/daily.log")


def last_cycle_as_of(runs_dir: Path) -> date | None:
    days = [
        date.fromisoformat(json.loads(p.read_text(encoding="utf-8"))["as_of"])
        for p in (runs_dir / "cycles").glob("*.json")
    ]
    return max(days) if days else None


def run_daily(args: argparse.Namespace, cli: Callable[[list[str]], int]) -> int:
    runs = Path("runs")
    log: list[str] = [f"=== daily run {datetime.now(UTC).isoformat(timespec='seconds')}"]
    prefix = ["--config", args.config] if args.config else []

    def call(label: str, argv: list[str]) -> int:
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(buffer):
            code = cli(prefix + argv)
        text = buffer.getvalue().rstrip()
        log.append(f"--- {label} (exit {code})\n{text}")
        print(f"--- {label} (exit {code})\n{text}")
        return code

    store = ["data", "--store", args.store]
    failed = False
    fetch = [*store, "fetch", "--start", args.start]
    if args.yahoo:
        fetch += ["--yahoo", *args.yahoo]
    if args.ccxt:
        fetch += ["--ccxt", *args.ccxt]
    if (
        call("fetch", fetch) != 0
        or call("export", [*store, "export", "--out", args.out, "--symbols", *args.symbols]) != 0
    ):
        failed = True
    else:
        newest = last_data_date(Path(args.out))
        done = last_cycle_as_of(runs)
        if done is not None and newest <= done:
            msg = f"no new trading day (data ends {newest}, last cycle {done}): cycle skipped"
            log.append(f"--- cycle\n{msg}")
            print(f"--- cycle\n{msg}")
        elif call("cycle", ["cycle", "--data", args.out]) != 0:
            failed = True
    if call("watchdog", ["watchdog", "--data", args.out]) != 0:
        failed = True
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with LOG_FILE.open("a", encoding="utf-8") as handle:
        handle.write("\n".join(log) + "\n")
    return 1 if failed else 0


def add_parser(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    p = sub.add_parser("daily", help="fetch, export, one paper cycle, watchdog (for a scheduler)")
    p.add_argument("--yahoo", nargs="+", metavar="SYMBOL", default=[])
    p.add_argument("--ccxt", nargs="+", metavar="EXCHANGE:PAIR", default=[])
    p.add_argument("--out", default="data/prices.csv")
    p.add_argument("--store", default="data/store")
    p.add_argument("--start", default="2000-01-01", help="history to download (default 2000)")

    def run(args: argparse.Namespace) -> int:
        from quantagents.cli import main  # late import: cli imports this module

        args.symbols = [*args.yahoo, *(c.partition(":")[2].replace("/", "-") for c in args.ccxt)]
        if not args.symbols:
            print("Nothing to do: add --yahoo SYMBOLS and/or --ccxt exchange:PAIR")
            return 2
        return run_daily(args, main)

    p.set_defaults(func=run)
