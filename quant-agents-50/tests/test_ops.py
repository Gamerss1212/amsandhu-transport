"""Everyday commands: status, doctor, the config-driven daily run and research record safety."""

from __future__ import annotations

import shutil
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from quantagents.cli import _free_path, main
from quantagents.data import sources
from quantagents.data.sources import RawDaily, split_universe
from quantagents.risk.killswitch import KillSwitch
from tests.test_watchdog_daily import fake_history


@pytest.fixture
def home(tmp_path: Path, repo_root: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    shutil.copytree(repo_root / "config", tmp_path / "config")
    (tmp_path / "config" / "mine.yaml").write_text(
        "universe:\n  asset_class: US_equities\n  symbols: [AAA, BTC-USD.KRAKEN]\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    return tmp_path


def last_weekday() -> date:
    day = datetime.now(UTC).date() - timedelta(days=1)
    while day.weekday() >= 5:
        day -= timedelta(days=1)
    return day


def test_split_universe_sends_each_symbol_to_its_source() -> None:
    yahoo, ccxt = split_universe(["SPY", "XIC.TO", "BTC-USD", "BTC-USD.KRAKEN", "ETH-CAD.NDAX"])
    assert yahoo == ["SPY", "XIC.TO", "BTC-USD"]
    assert ccxt == ["kraken:BTC/USD", "ndax:ETH/CAD"]


def test_daily_reads_its_symbols_from_the_config(
    home: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls: list[tuple[str, str, date]] = []

    def fake_yahoo(symbol: str, start: date, end: date) -> RawDaily:
        calls.append(("yahoo", symbol, start))
        return fake_history(symbol, last_weekday())

    def fake_ccxt(exchange: str, pair: str, start: date, end: date) -> RawDaily:
        calls.append((exchange, pair, start))
        return fake_history(sources.ccxt_symbol(exchange, pair), last_weekday())

    monkeypatch.setattr(sources, "fetch_yahoo", fake_yahoo)
    monkeypatch.setattr(sources, "fetch_ccxt", fake_ccxt)
    assert main(["--config", "config/mine.yaml", "daily", "--out", "data/p.csv"]) in (0, 1)
    out = capsys.readouterr().out
    assert [(c[0], c[1]) for c in calls] == [("yahoo", "AAA"), ("kraken", "BTC/USD")]
    years = {(datetime.now(UTC).date() - c[2]).days // 365 for c in calls}
    assert years == {5}  # five years of history, not the whole of it
    assert "BTC-USD.KRAKEN: stored" in out and "--- export (exit 0)" in out
    # the synthetic default universe is refused with a clear next step
    assert main(["daily"]) == 2
    assert "my_universe.yaml" in capsys.readouterr().out


def test_status_shows_account_switch_cycles_and_progress(
    home: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["status"]) == 0
    out = capsys.readouterr().out
    assert "Mode: paper" in out and "Kill switch: armed" in out
    assert "No paper account yet" in out and "No paper cycle has run yet" in out
    assert "synthetic demo universe" in out

    monkeypatch.setattr(sources, "fetch_yahoo", lambda s, a, b: fake_history(s, last_weekday()))
    main(["daily", "--yahoo", "AAA", "BBB", "--out", "data/p.csv"])
    KillSwitch(home / "state" / "kill_switch.json").engage("test stop", by="human")
    capsys.readouterr()
    assert main(["status", "--data", "data/p.csv"]) == 0
    out = capsys.readouterr().out
    assert "Kill switch: ENGAGED - test stop" in out and "killswitch reset" in out
    assert "Equity 10,000.00 CAD" in out
    assert "Paper days: 1 of 30" in out and "halted cycles: 0" in out
    assert "Last daily run" in out and "cycle (exit 0)" in out


def test_doctor_checks_the_install(home: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["doctor"]) == 0
    out = capsys.readouterr().out
    assert "[ok]    numpy installed" in out and "folder state/ is writable" in out
    assert "synthetic demo" in out and "Everything needed is in place." in out
    (home / "config" / "broken.yaml").write_text(
        "risk:\n  max_daily_loss_pct: -5\n", encoding="utf-8"
    )
    assert main(["--config", "config/broken.yaml", "doctor"]) == 1
    assert "[ERROR] config config/broken.yaml is invalid" in capsys.readouterr().out


def test_research_never_overwrites_a_report(home: Path) -> None:
    first = _free_path("docs/research/grid-2026-10-06.md")
    assert first == Path("docs/research/grid-2026-10-06.md")
    first.parent.mkdir(parents=True)
    first.write_text("old", encoding="utf-8")
    assert _free_path(str(first)) == Path("docs/research/grid-2026-10-06-2.md")
    Path("docs/research/grid-2026-10-06-2.csv").write_text("old", encoding="utf-8")
    assert _free_path(str(first)) == Path("docs/research/grid-2026-10-06-3.md")
