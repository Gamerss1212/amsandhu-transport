"""Phase 3 watchdog and daily run: they can only stop trading, and never run a day twice."""

from __future__ import annotations

import json
import os
import shutil
import time
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import numpy as np
import pytest

from quantagents import watchdog
from quantagents.cli import main
from quantagents.data import sources
from quantagents.data.sources import RawDaily
from quantagents.data.synthetic import business_days
from quantagents.market import as_readonly
from quantagents.risk.killswitch import KillSwitch


def test_weekdays_between_matches_a_day_by_day_count() -> None:
    start = date(2026, 1, 1)
    for a in range(15):
        for span in range(30):
            s, e = start + timedelta(days=a), start + timedelta(days=a + span)
            brute = sum(1 for k in range(1, span + 1) if (s + timedelta(days=k)).weekday() < 5)
            assert watchdog.weekdays_between(s, e) == brute, (s, e)
    assert watchdog.weekdays_between(date(2026, 1, 9), date(2026, 1, 5)) == 0


def write_cycle(runs: Path, as_of: date, ran: datetime) -> None:
    path = runs / "cycles" / f"C{as_of:%Y%m%d}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"as_of": as_of.isoformat()}), encoding="utf-8")
    stamp = ran.timestamp()
    os.utime(path, (stamp, stamp))


def write_csv(path: Path, last: date) -> None:
    path.write_text(
        "date,symbol,open,high,low,close,volume\n"
        f"{(last - timedelta(days=1)).isoformat()},X,1,1,1,1,1\n{last.isoformat()},X,1,1,1,1,1\n",
        encoding="utf-8",
    )


def test_watchdog_checks_cycles_data_and_state(tmp_path: Path) -> None:
    runs, state, kill = tmp_path / "runs", tmp_path / "state.json", tmp_path / "kill.json"
    data = tmp_path / "prices.csv"
    friday = date(2026, 10, 2)
    monday = date(2026, 10, 5)

    def wd(today: date, engage: bool = True) -> watchdog.WatchdogReport:
        return watchdog.run(
            runs_dir=runs, state_file=state, kill_file=kill, data=data, today=today, engage=engage
        )

    write_csv(data, friday)
    first = wd(monday, engage=False)
    assert first.problems == ("no paper cycle has run yet",) and not first.engaged

    write_cycle(runs, friday, datetime(2026, 10, 2, 22, 0, tzinfo=UTC))
    assert wd(monday).ok  # a weekend is not a missed day
    assert not KillSwitch(kill).engaged

    thursday = date(2026, 10, 8)
    late = wd(thursday)
    assert any("4 weekdays ago (limit 2)" in p for p in late.problems)
    assert any(
        "newest bar in prices.csv is 2026-10-02: 4 weekdays old (limit 3)" in p
        for p in late.problems
    )
    assert late.engaged and KillSwitch(kill).state().by == "watchdog"

    kill.unlink()
    state.write_text("{broken", encoding="utf-8")
    data.write_text("date,symbol,open,high,low,close,volume\n", encoding="utf-8")
    broken = wd(monday)
    assert any("paper account state unreadable" in p for p in broken.problems)
    assert any("data file unreadable" in p for p in broken.problems)
    (runs / "cycles" / "bad.json").write_text("not json", encoding="utf-8")
    assert any("cycle reports unreadable" in p for p in wd(monday).problems)


def test_watchdog_never_resets_the_switch(tmp_path: Path) -> None:
    kill = tmp_path / "kill.json"
    KillSwitch(kill).engage("manual stop", by="human")
    runs = tmp_path / "runs"
    write_cycle(runs, date(2026, 10, 5), datetime.now(UTC))
    report = watchdog.run(
        runs_dir=runs,
        state_file=tmp_path / "none.json",
        kill_file=kill,
        data=None,
        today=date(2026, 10, 5),
    )
    assert report.ok
    assert KillSwitch(kill).state().reason == "manual stop"  # still engaged: only a human resets


def fake_history(symbol: str, end: date, n: int = 320) -> RawDaily:
    days = business_days(end, n)
    t = np.arange(n, dtype=np.float64)
    close = 100.0 * np.exp(0.0004 * t) * (1.0 + 0.01 * np.sin(t / 5.0))
    open_ = np.concatenate([[close[0]], close[:-1]])
    return RawDaily(
        symbol=symbol,
        dates=tuple(days),
        open=as_readonly(open_),
        high=as_readonly(np.maximum(open_, close) * 1.003),
        low=as_readonly(np.minimum(open_, close) * 0.997),
        close=as_readonly(close),
        adj_close=as_readonly(close),
        volume=as_readonly(np.full(n, 1e6)),
    )


@pytest.fixture
def daily_dir(tmp_path: Path, repo_root: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    shutil.copytree(repo_root / "config", tmp_path / "config")
    (tmp_path / "config" / "mine.yaml").write_text(
        "universe:\n  asset_class: US_equities\n  symbols: [AAA, BBB]\n", encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_daily_runs_each_trading_day_once(
    daily_dir: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    today = datetime.now(UTC).date()
    last = today - timedelta(days=1)
    while last.weekday() >= 5:
        last -= timedelta(days=1)
    ends = {"end": last}

    def fake_yahoo(symbol: str, start: date, end: date) -> RawDaily:
        return fake_history(symbol, ends["end"])

    monkeypatch.setattr(sources, "fetch_yahoo", fake_yahoo)
    argv = ["--config", "config/mine.yaml", "daily", "--yahoo", "AAA", "BBB", "--out", "data/p.csv"]
    assert main(argv) == 0
    out = capsys.readouterr().out
    assert "--- fetch (exit 0)" in out and "--- export (exit 0)" in out
    assert "--- cycle (exit 0)" in out and "Watchdog: all clear." in out
    assert "nothing can trade" not in out  # AAA and BBB are in this config's universe
    log = (daily_dir / "runs" / "daily.log").read_text(encoding="utf-8")
    assert "=== daily run" in log and "--- watchdog (exit 0)" in log

    time.sleep(0.01)  # a new ingest timestamp for the second snapshot
    assert main(argv) == 0  # same data again: the cycle must not run twice
    assert "no new trading day" in capsys.readouterr().out
    assert len(list((daily_dir / "runs" / "cycles").glob("*.json"))) == 1


def test_daily_stops_before_the_cycle_when_the_fetch_fails(
    daily_dir: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def down(symbol: str, start: date, end: date) -> RawDaily:
        raise ConnectionError("no network")

    monkeypatch.setattr(sources, "fetch_yahoo", down)
    assert main(["daily", "--yahoo", "AAA", "--out", "data/p.csv"]) == 1
    out = capsys.readouterr().out
    assert "--- fetch (exit 1)" in out and "--- cycle" not in out
    assert "--- watchdog (exit 1)" in out  # no cycle has ever run: the watchdog stops trading
    assert KillSwitch(daily_dir / "state" / "kill_switch.json").engaged
    assert main(["daily"]) == 2


def test_account_files_are_backed_up_and_old_backups_pruned(tmp_path: Path) -> None:
    from quantagents.daily import BACKUP_DAYS, backup_state

    state = tmp_path / "state"
    assert backup_state(state, date(2026, 10, 1)) is None  # nothing to save yet
    state.mkdir()
    (state / "paper_account.json").write_text('{"v": 1}', encoding="utf-8")
    (state / "daily.lock").write_text("pid", encoding="utf-8")
    for i in range(BACKUP_DAYS + 3):
        saved = backup_state(state, date(2026, 1, 1) + timedelta(days=i))
    assert (
        saved is not None
        and (saved / "paper_account.json").read_text(encoding="utf-8") == '{"v": 1}'
    )
    assert not (saved / "daily.lock").exists()  # only account files
    days = sorted(p.name for p in (state / "backups").iterdir())
    assert len(days) == BACKUP_DAYS and days[-1] == saved.name and days[0] == "2026-01-04"
