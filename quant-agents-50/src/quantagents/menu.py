"""The simple menu: double-click ``QuantAgents.bat`` (Windows) or run ``bash QuantAgents.sh``.

    python -m quantagents --config config/my_universe.yaml menu

Each choice runs an ordinary ``quantagents`` command, so the menu adds no new powers: it cannot
raise a limit or switch on real money. Stopping is one key; resuming needs the reset phrase.
It can also put the daily run in Windows Task Scheduler (or cron on macOS and Linux).
"""

from __future__ import annotations

import argparse
import json
import platform
import shlex
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from quantagents import envfile
from quantagents.config import LIVE_APPROVAL_ENV, AppConfig, ExecutionMode, load_config
from quantagents.data.sources import split_universe
from quantagents.execution import live
from quantagents.risk.killswitch import RESET_PHRASE, KillSwitch

Ask = Callable[[str], str]
Say = Callable[[str], None]
Run = Callable[[list[str]], int]
Shell = Callable[[list[str], str | None], tuple[int, str]]
Opener = Callable[[Path], bool]

TASK_PREFIX = "QuantAgents daily"
CHOICES = (
    ("1", "Run today's paper trading day now"),
    ("2", "Show the full dashboard"),
    ("3", "Turn the automatic daily run ON"),
    ("4", "Turn the automatic daily run OFF"),
    ("5", "STOP all trading now (kill switch)"),
    ("6", "Resume trading after a stop"),
    ("7", "Change my symbols (opens the settings file)"),
    ("8", "Real money: what is still needed"),
    ("9", "Real money: preview the real orders (sends nothing)"),
    ("10", "Real money: send a tiny test order (cancelled at once)"),
    ("11", "Check the install"),
    ("0", "Quit"),
)


def _shell(cmd: list[str], stdin: str | None) -> tuple[int, str]:  # pragma: no cover - OS
    try:
        done = subprocess.run(cmd, input=stdin, capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 127, str(exc)
    return done.returncode, (done.stdout + done.stderr).strip()


def _open(path: Path) -> bool:  # pragma: no cover - opens an editor window
    system = platform.system()
    cmd = {"Windows": ["notepad", str(path)], "Darwin": ["open", "-e", str(path)]}.get(
        system, ["xdg-open", str(path)]
    )
    try:
        subprocess.run(cmd, check=False)  # Notepad waits here until it is closed
    except OSError:
        return False
    return True


@dataclass(frozen=True)
class Schedule:
    """When the daily run happens: stocks on weekdays after the close, crypto every evening."""

    name: str
    time: str  # HH:MM on this computer's clock
    every_day: bool

    @property
    def words(self) -> str:
        days = "every day" if self.every_day else "Monday to Friday"
        return f"{days} at {self.time} (this computer's clock)"


def schedule_for(cfg: AppConfig, folder: Path) -> Schedule:
    _, crypto = split_universe(list(cfg.universe.symbols))
    every_day = bool(crypto)  # crypto trades on weekends and its day ends at midnight UTC
    return Schedule(f"{TASK_PREFIX} ({folder.name})", "19:00" if every_day else "15:30", every_day)


def windows_commands(s: Schedule, folder: Path) -> dict[str, list[str]]:
    days = ["/SC", "DAILY"] if s.every_day else ["/SC", "WEEKLY", "/D", "MON,TUE,WED,THU,FRI"]
    bat = folder / "daily.bat"
    return {
        "on": ["schtasks", "/Create", "/TN", s.name, "/TR", f'"{bat}"', *days, "/ST", s.time, "/F"],
        "off": ["schtasks", "/Delete", "/TN", s.name, "/F"],
        "query": ["schtasks", "/Query", "/TN", s.name, "/FO", "LIST"],
    }


def cron_line(s: Schedule, folder: Path) -> str:
    hour, minute = (int(x) for x in s.time.split(":"))
    days = "*" if s.every_day else "1-5"
    script = shlex.quote(str(folder / "daily.sh"))
    return f"{minute} {hour} * * {days} bash {script} >/dev/null 2>&1 # {s.name}"


def is_scheduled(s: Schedule, folder: Path, system: str, shell: Shell) -> bool:
    command = windows_commands(s, folder)["query"] if system == "Windows" else ["crontab", "-l"]
    code, text = shell(command, None)
    return code == 0 and s.name in text  # only a task listed by its full name counts


def set_schedule(on: bool, s: Schedule, folder: Path, system: str, shell: Shell) -> list[str]:
    """Add or remove the daily task. Returns what to tell the owner."""
    if system == "Windows":
        code, text = shell(windows_commands(s, folder)["on" if on else "off"], None)
        if code != 0:
            if not on and "cannot find" in text.lower():
                return ["The automatic daily run was already off."]
            return [f"Windows Task Scheduler said no ({text or code}).", "See docs/schedule.md."]
        if not on:
            return ["The automatic daily run is OFF."]
        return [
            f"The automatic daily run is ON: {s.words}.",
            "Keep the computer on and signed in at that time. A missed day is picked up on the "
            "next run.",
        ]
    code, text = shell(["crontab", "-l"], None)
    lines = [ln for ln in (text.splitlines() if code == 0 else []) if s.name not in ln]
    if on:
        lines.append(cron_line(s, folder))
    code, text = shell(["crontab", "-"], "\n".join(lines) + "\n")
    if code != 0:
        todo = "Add this line" if on else "Remove the line ending like this one"
        return [f"crontab said no ({text or code}). {todo} with crontab -e:", cron_line(s, folder)]
    return [
        f"The automatic daily run is ON: {s.words}." if on else "The automatic daily run is OFF."
    ]


def _paper_days(runs: Path) -> int:
    days: set[str] = set()
    for path in (runs / "cycles").glob("*.json"):
        try:
            days.add(str(json.loads(path.read_text(encoding="utf-8"))["as_of"]))
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return len(days)


def header(cfg: AppConfig, config: str, folder: Path, system: str, shell: Shell) -> list[str]:
    s = schedule_for(cfg, folder)
    symbols = list(cfg.universe.symbols)
    switch = KillSwitch(live.KILL_FILE).state()
    if cfg.system.execution_mode is ExecutionMode.LIVE:
        checks = live.gates(
            cfg,
            status_file=live.STATUS_FILE,
            kill_file=live.KILL_FILE,
            runs_dir=live.RUNS_DIR,
            today=datetime.now(UTC).date(),
            ccxt_installed=live.has_ccxt(),
        )
        closed = sum(1 for g in checks if not g.ok)
        money = (
            "ARMED (every gate open)"
            if not closed
            else f"NOT armed: {closed} gates closed (choice 8)"
        )
    else:
        money = "OFF (paper only)"
    return [
        "",
        "=" * 60,
        f"QuantAgents-50 | folder {folder.name} | settings {config}",
        f"Symbols: {', '.join(symbols[:6])}{' ...' if len(symbols) > 6 else ''}",
        f"Kill switch: {'ENGAGED - ' + switch.reason if switch.engaged else 'armed (trading allowed)'}",
        f"Paper days so far: {_paper_days(live.RUNS_DIR)} of 30 | automatic daily run: "
        + ("ON" if is_scheduled(s, folder, system, shell) else "OFF"),
        f"Real money: {money}",
        "=" * 60,
    ]


def run_menu(
    *,
    config: str,
    run: Run,
    ask: Ask = input,
    say: Say = print,
    shell: Shell = _shell,
    opener: Opener = _open,
    folder: Path | None = None,
    system: str | None = None,
) -> int:
    folder = folder or Path.cwd()
    system = system or platform.system()
    base = ["--config", config]

    def do(argv: list[str]) -> None:
        try:
            run(base + argv)
        except Exception as exc:  # the menu stays open whatever a command does
            say(f"error: {type(exc).__name__}: {exc}")

    while True:
        envfile.load()  # picks up a line just added to .env (values are never shown)
        try:
            cfg = load_config(Path(config) if Path(config).exists() else None)
        except ValueError as exc:
            say(f"\nYour settings file {config} has a problem:\n{exc}")
            if LIVE_APPROVAL_ENV in str(exc):
                say(
                    "For real money, add the line named above to .env (docs/REAL_MONEY.md, step 6)."
                )
                say("Otherwise put the three live settings back to their paper values.")
            else:
                say("Fix it (choice 7 opens it), or copy config/us_etfs.example.yaml over it.")
            cfg = AppConfig()
        for line in header(cfg, config, folder, system, shell):
            say(line)
        for key, text in CHOICES:
            say(f"  {key:>2}  {text}")
        try:
            choice = ask("\nType a number and press Enter: ").strip().lower()
        except EOFError:
            return 0
        if choice in ("0", "q", "quit", "exit"):
            say("Goodbye. The automatic daily run (if ON) keeps working without this window.")
            return 0
        s = schedule_for(cfg, folder)
        if choice == "1":
            say("Downloading prices and running today's paper day. This takes a minute...")
            do(["daily"])
        elif choice == "2":
            do(["status", "--data", "data/prices.csv"])
        elif choice in ("3", "4"):
            for line in set_schedule(choice == "3", s, folder, system, shell):
                say(line)
        elif choice == "5":
            do(["killswitch", "engage", "--reason", "stopped from the menu"])
            say("Nothing new will trade until you resume (choice 6).")
        elif choice == "6":
            do(["killswitch", "status"])
            typed = ask(
                f"To resume, first read runs/daily.log, then type {RESET_PHRASE} (Enter cancels): "
            ).strip()
            if typed:
                do(["killswitch", "reset", "--confirm", typed])
            else:
                say("Cancelled: trading stays stopped.")
        elif choice == "7":
            path = Path(config)
            say(f"Opening {path}. Change the list after 'symbols:', save, and close the window.")
            say("One folder holds one paper account: for other symbols, use a second folder.")
            if not opener(path):
                say(f"Could not open an editor. Open {path} in any text editor.")
            do(["config"])
        elif choice == "8":
            do(["live", "check"])
        elif choice == "9":
            do(["live", "sync", "--dry-run"])
        elif choice == "10":
            say("This sends a REAL order to your exchange: the smallest buy it accepts, 20% under")
            say("the price so it does not fill, and cancels it at once. Every gate must be open.")
            if ask("Type YES to send it (Enter cancels): ").strip() == "YES":
                do(["live", "test-order"])
            else:
                say("Cancelled: nothing was sent.")
        elif choice == "11":
            do(["doctor"])
        else:
            say("Please type one of the numbers in the list.")
            continue
        try:
            ask("\nPress Enter to go back to the menu...")
        except EOFError:
            return 0


def add_parser(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    p = sub.add_parser("menu", help="the simple numbered menu (what QuantAgents.bat opens)")

    def run(args: argparse.Namespace) -> int:
        from quantagents.cli import main  # late import: cli imports this module

        return run_menu(config=args.config or "config/default.yaml", run=main)

    p.set_defaults(func=run)
