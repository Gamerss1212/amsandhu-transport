"""One paper-trading day, in order, for the task scheduler (Phase 3 daily schedule).

    python -m quantagents --config config/my_universe.yaml daily

The symbols come from the config's ``universe.symbols`` (``BTC-USD.KRAKEN`` style names are
downloaded from that exchange, everything else from Yahoo), or from ``--yahoo`` / ``--ccxt``.
Each day downloads the last 5 years (enough for every agent), not the whole history again.

1. ``data fetch``: a new snapshot in the append-only store (never overwrites).
2. ``data export``: adjusted prices to ``--out``, with the sources' caveats in the sidecar.
3. ``cycle``: one paper cycle, but only when the data has a trading day the last cycle has not
   seen. The same day is never run twice (it would re-process orders and stops).
4. ``watchdog``: engages the kill switch if cycles or data have gone stale.
5. ``live sync``: only when the config's ``execution_mode`` is ``live``. It copies the paper
   portfolio onto the exchange, and it refuses unless the owner has opened every real-money
   gate (see ``execution/live.py``). Skipped after any failed step.

Everything printed is also appended to ``runs/daily.log``, and the account files are copied
to ``state/backups/<date>/`` (the newest 30 days are kept). If Telegram is set up in ``.env``,
one line goes to the owner's phone: what failed, or the day's result. In paper mode no step
can send a real order.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import shutil
from collections.abc import Callable
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from quantagents import alerts
from quantagents.config import ExecutionMode, load_config
from quantagents.data.sources import ccxt_symbol, split_universe
from quantagents.runlock import RunLock
from quantagents.watchdog import last_data_date

LOG_FILE = Path("runs/daily.log")
BACKUP_DAYS = 30  # days of account backups kept in state/backups/
HISTORY_YEARS = 5  # A06 needs 2 years of volatility history; the features need about 15 months


def last_cycle_as_of(runs_dir: Path) -> date | None:
    days = [
        date.fromisoformat(json.loads(p.read_text(encoding="utf-8"))["as_of"])
        for p in (runs_dir / "cycles").glob("*.json")
    ]
    return max(days) if days else None


def last_cycle_symbols(runs_dir: Path) -> set[str]:
    """The symbols of the newest cycle in this folder (from its market snapshot)."""
    newest: tuple[str, set[str]] | None = None
    for p in (runs_dir / "cycles").glob("*.json"):
        data = json.loads(p.read_text(encoding="utf-8"))
        key = str(data["as_of"])
        if newest is None or key > newest[0]:
            newest = (key, set(data.get("snapshot", {}).get("last_close", {})))
    return newest[1] if newest else set()


def run_daily(args: argparse.Namespace, cli: Callable[[list[str]], int]) -> int:
    runs = Path("runs")
    log: list[str] = [f"=== daily run {datetime.now(UTC).isoformat(timespec='seconds')}"]
    prefix = ["--config", args.config] if args.config else []

    codes: dict[str, int] = {}
    notes: list[str] = []

    def call(label: str, argv: list[str]) -> int:
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(buffer):
            code = cli(prefix + argv)
        text = buffer.getvalue().rstrip()
        log.append(f"--- {label} (exit {code})\n{text}")
        print(f"--- {label} (exit {code})\n{text}")
        codes[label] = code
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
        before = last_cycle_symbols(runs)
        if before and not before & set(args.symbols):
            msg = (
                f"REFUSED: this folder's paper account trades {', '.join(sorted(before))}, but "
                f"this run is for {', '.join(args.symbols)}. One folder holds one paper account: "
                "unzip a second copy of QuantAgents-50 for another universe."
            )
            log.append(f"--- cycle\n{msg}")
            print(f"--- cycle\n{msg}")
            codes["cycle"] = 2
            failed = True
        elif done is not None and newest <= done:
            msg = f"no new trading day (data ends {newest}, last cycle {done}): cycle skipped"
            notes.append("no new trading day")
            log.append(f"--- cycle\n{msg}")
            print(f"--- cycle\n{msg}")
        elif call("cycle", ["cycle", "--data", args.out]) != 0:
            failed = True
    if call("watchdog", ["watchdog", "--data", args.out]) != 0:
        failed = True
    if getattr(args, "live", False) and not failed and call("live sync", ["live", "sync"]) != 0:
        failed = True
    try:
        saved = backup_state(Path("state"), datetime.now(UTC).date())
        if saved is not None:
            log.append(f"--- backup\nstate saved to {saved}")
    except OSError as exc:  # a failed backup is reported, never fatal
        log.append(f"--- backup\nfailed: {exc}")
        print(f"--- backup\nfailed: {exc}")
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with LOG_FILE.open("a", encoding="utf-8") as handle:
        handle.write("\n".join(log) + "\n")
    alerts.send(summary(codes, notes, runs))
    return 1 if failed else 0


def backup_state(state: Path, day: date) -> Path | None:
    """Copy the account files (paper account, real-money ledger, kill switch...) to
    ``state/backups/<day>/``, keeping the newest ``BACKUP_DAYS`` days."""
    files = sorted(state.glob("*.json"))
    if not files:
        return None
    target = state / "backups" / day.isoformat()
    target.mkdir(parents=True, exist_ok=True)
    for path in files:
        shutil.copy2(path, target / path.name)
    days = sorted(p for p in (state / "backups").iterdir() if p.is_dir())
    for old in days[:-BACKUP_DAYS]:
        shutil.rmtree(old)
    return target


def summary(codes: dict[str, int], notes: list[str], runs: Path) -> str:
    """The one-line phone alert for a daily run (sent only if Telegram is set up in .env)."""
    bad = [f"{label} (exit {code})" for label, code in codes.items() if code != 0]
    if bad:
        return (
            f"Daily run FAILED: {', '.join(bad)}. Read runs/daily.log; menu choice 2 shows "
            "the account and the kill switch."
        )
    newest: tuple[str, float, dict[str, Any]] | None = None
    for path in (runs / "cycles").glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            key = (str(data["as_of"]), path.stat().st_mtime, data)
        except (OSError, ValueError, KeyError, TypeError):
            continue
        if newest is None or key[:2] > newest[:2]:
            newest = key
    parts = list(notes)
    if newest is not None:
        data = newest[2]
        go = [str(p.get("symbol")) for p in data.get("proposals", []) if p.get("go")]
        parts += [
            f"as of {newest[0]}",
            f"paper equity {float(data.get('equity', 0.0)):,.2f}",
            f"GO: {', '.join(go) or 'none'}",
            f"paper fills {len(data.get('fills', []))}",
            f"risk level {data.get('risk', {}).get('level', '?')}",
        ]
    return "Daily run OK: " + "; ".join(parts) + "."


def add_parser(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    p = sub.add_parser("daily", help="fetch, export, one paper cycle, watchdog (for a scheduler)")
    p.add_argument("--yahoo", nargs="+", metavar="SYMBOL", default=[])
    p.add_argument("--ccxt", nargs="+", metavar="EXCHANGE:PAIR", default=[])
    p.add_argument("--out", default="data/prices.csv")
    p.add_argument("--store", default="data/store")
    p.add_argument("--start", help=f"history to download (default: the last {HISTORY_YEARS} years)")

    def run(args: argparse.Namespace) -> int:
        from quantagents.cli import main  # late import: cli imports this module

        path = Path(args.config) if args.config else Path("config/default.yaml")
        cfg = load_config(path if path.exists() else None)
        args.live = cfg.system.execution_mode is ExecutionMode.LIVE
        if not (args.yahoo or args.ccxt):
            symbols = cfg.universe.symbols
            if not symbols or all(s.startswith("SYN_") for s in symbols):
                print(
                    "Nothing to do: the config's universe is empty or still the synthetic demo "
                    "(SYN_A...). Copy config/us_etfs.example.yaml to config/my_universe.yaml, "
                    "list your symbols, and pass --config config/my_universe.yaml."
                )
                return 2
            args.yahoo, args.ccxt = split_universe(symbols)
        args.symbols = [
            *args.yahoo,
            *(ccxt_symbol(*c.split(":", 1)) for c in args.ccxt if ":" in c),
        ]
        if not args.symbols:
            print("Nothing to do: add --yahoo SYMBOLS and/or --ccxt exchange:PAIR")
            return 2
        if not args.start:
            today = datetime.now(UTC).date()
            args.start = today.replace(
                year=today.year - HISTORY_YEARS, day=min(today.day, 28)
            ).isoformat()
        lock = RunLock(Path("state/daily.lock"))
        if not lock.acquire():
            print(f"Another daily run is still going ({lock.path}). This one did nothing.")
            return 0
        try:
            return run_daily(args, main)
        finally:
            lock.release()

    p.set_defaults(func=run)
