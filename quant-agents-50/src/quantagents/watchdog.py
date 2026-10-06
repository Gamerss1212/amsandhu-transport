"""Watchdog (Phase 3, spec section 51): a separate check that can only stop trading.

Run it on its own schedule (for example an hour after the daily cycle). It engages the kill
switch when:
- no paper cycle has run for more than ``max_missed_days`` weekdays;
- the newest bar in the data file is more than ``max_data_age_days`` weekdays old;
- the data file or the paper account state cannot be read.

It never resets the switch and never trades. Only a human resets the switch, with the phrase.
Weekdays are counted Monday to Friday; exchange holidays are covered by the slack in the limits.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from quantagents.risk.killswitch import KillSwitch


def weekdays_between(start: date, end: date) -> int:
    """Weekdays d with start < d <= end (0 when end is not after start)."""
    if end <= start:
        return 0
    full_weeks, extra = divmod((end - start).days, 7)
    count = 5 * full_weeks
    for k in range(1, extra + 1):
        if (start + timedelta(days=7 * full_weeks + k)).weekday() < 5:
            count += 1
    return count


def last_data_date(path: Path) -> date:
    """The newest date in a long CSV (date,symbol,...). Raises on an unreadable file."""
    newest: date | None = None
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            day = date.fromisoformat(row["date"].strip())
            newest = day if newest is None or day > newest else newest
    if newest is None:
        raise ValueError(f"{path}: no data rows")
    return newest


def last_cycle(runs_dir: Path) -> tuple[date, datetime] | None:
    """(as-of date, file time in UTC) of the newest saved cycle report, if any."""
    best: tuple[date, datetime] | None = None
    for path in (runs_dir / "cycles").glob("*.json"):
        as_of = date.fromisoformat(json.loads(path.read_text(encoding="utf-8"))["as_of"])
        when = datetime.fromtimestamp(path.stat().st_mtime, UTC)
        if best is None or when > best[1]:
            best = (as_of, when)
    return best


@dataclass(frozen=True)
class WatchdogReport:
    problems: tuple[str, ...]
    engaged: bool

    @property
    def ok(self) -> bool:
        return not self.problems


def check(
    *,
    runs_dir: Path,
    state_file: Path,
    data: Path | None,
    today: date,
    max_missed_days: int = 2,
    max_data_age_days: int = 3,
) -> list[str]:
    problems: list[str] = []
    try:
        cycle = last_cycle(runs_dir)
    except (OSError, ValueError, KeyError) as exc:
        problems.append(f"cycle reports unreadable ({exc})")
        cycle = None
    if cycle is None and not problems:
        problems.append("no paper cycle has run yet")
    elif cycle is not None:
        missed = weekdays_between(cycle[1].date(), today)
        if missed > max_missed_days:
            problems.append(
                f"last cycle ran {cycle[1].date().isoformat()}: {missed} weekdays ago "
                f"(limit {max_missed_days})"
            )
    if data is not None:
        try:
            newest = last_data_date(data)
        except (OSError, ValueError, KeyError) as exc:
            problems.append(f"data file unreadable ({exc})")
        else:
            age = weekdays_between(newest, today)
            if age > max_data_age_days:
                problems.append(
                    f"newest bar in {data.name} is {newest.isoformat()}: {age} weekdays old "
                    f"(limit {max_data_age_days})"
                )
    if state_file.exists():
        try:
            json.loads(state_file.read_text(encoding="utf-8"))["ledger_fills"]
        except (OSError, ValueError, KeyError, TypeError) as exc:
            problems.append(f"paper account state unreadable ({type(exc).__name__})")
    return problems


def run(
    *,
    runs_dir: Path,
    state_file: Path,
    kill_file: Path,
    data: Path | None,
    today: date | None = None,
    max_missed_days: int = 2,
    max_data_age_days: int = 3,
    engage: bool = True,
) -> WatchdogReport:
    problems = check(
        runs_dir=runs_dir,
        state_file=state_file,
        data=data,
        today=today or datetime.now(UTC).date(),
        max_missed_days=max_missed_days,
        max_data_age_days=max_data_age_days,
    )
    engaged = False
    if problems and engage:
        KillSwitch(kill_file).engage("watchdog: " + "; ".join(problems), by="watchdog")
        engaged = True
    return WatchdogReport(tuple(problems), engaged)
