"""Phase 3 chaos tests: stale data, duplicate fills, a dropped broker, a corrupted kill switch.

In every case the system must fail safe: no new risk, no crash, and a clear reason on record.
"""

from __future__ import annotations

import itertools
import shutil
from datetime import date
from pathlib import Path

import numpy as np
import pytest

from quantagents.cli import main
from quantagents.config import AppConfig
from quantagents.data.synthetic import DEMO_AS_OF
from quantagents.execution.paper import PaperAccount, PaperBroker, reconcile
from quantagents.market import FIELDS, Bars, MarketData, save_csv
from quantagents.orchestrator import CycleReport, Orchestrator
from quantagents.registry import Registry
from quantagents.risk.killswitch import RESET_PHRASE, KillSwitch
from quantagents.schemas import DegradationLevel

PHASE3 = AppConfig.model_validate({"system": {"phase": 3}})


def cycle(
    market: MarketData,
    registry: Registry,
    *,
    switch: KillSwitch | None = None,
    account: PaperAccount | None = None,
    as_of: date = DEMO_AS_OF,
) -> CycleReport:
    nonces = itertools.count()
    return Orchestrator(
        PHASE3,
        registry,
        account if account is not None else PaperAccount(PHASE3.system.capital, PHASE3.costs),
        switch if switch is not None else KillSwitch(),
        nonce_factory=lambda: f"nonce-{next(nonces)}",
    ).run_cycle(market, as_of)


def stale(market: MarketData, symbols: tuple[str, ...], index: int) -> MarketData:
    """The feed re-sends bar ``index - 1`` as bar ``index`` for ``symbols``."""
    bars = {}
    for s in market.symbols:
        arrays = {f: np.array(market.bars(s).field(f)) for f in FIELDS}
        if s in symbols:
            for f in FIELDS:
                arrays[f][index] = arrays[f][index - 1]
        bars[s] = Bars.from_arrays(**arrays)
    return MarketData(market.dates, bars)


# ---------------------------------------------------------------- stale data


def test_a_stale_symbol_is_blocked_and_the_rest_trade(
    market: MarketData, registry: Registry
) -> None:
    i = market.index_of(DEMO_AS_OF)
    report = cycle(stale(market, ("SYN_A",), i), registry)
    assert report.health.blocked_symbols == ("SYN_A",)
    detail = next(c.detail for c in report.health.checks if c.name == "SYN_A")
    assert "exact copy" in detail
    assert all(f.symbol != "SYN_A" for f in report.fills)
    assert all(i.symbol != "SYN_A" for i in report.intents)


def test_a_fully_stale_feed_halts_and_fires_the_kill_switch(
    market: MarketData, registry: Registry
) -> None:
    i = market.index_of(DEMO_AS_OF)
    switch = KillSwitch()
    report = cycle(stale(market, market.symbols, i), registry, switch=switch)
    assert set(report.health.blocked_symbols) == set(market.symbols)
    assert report.risk.level is DegradationLevel.HALTED
    assert report.fills == () and switch.engaged
    assert "data health" in switch.state().reason


def test_a_cycle_past_the_end_of_the_data_refuses_to_run(
    market: MarketData, tmp_path: Path, repo_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    shutil.copytree(repo_root / "config", tmp_path / "config")
    monkeypatch.chdir(tmp_path)
    save_csv(market, tmp_path / "prices.csv")
    assert main(["cycle", "--data", "prices.csv", "--as-of", "2030-01-02"]) == 2
    assert not (tmp_path / "state" / "paper_account.json").exists()  # nothing was traded


# ---------------------------------------------------------------- duplicate fills


def test_a_repeated_fill_is_applied_once(market: MarketData, registry: Registry) -> None:
    report = cycle(market, registry)
    assert report.fills
    account = PaperAccount(PHASE3.system.capital, PHASE3.costs)
    fill = report.fills[0]
    assert account.ledger.record(fill)
    cash = account.ledger.book.cash
    assert not account.ledger.record(fill)  # the same fill id again: ignored
    assert account.ledger.book.cash == cash and len(account.ledger.fills) == 1


def test_a_broker_that_double_books_a_fill_halts_the_next_cycle(
    market: MarketData, registry: Registry, tmp_path: Path
) -> None:
    account = PaperAccount(PHASE3.system.capital, PHASE3.costs)
    first = cycle(market, registry, account=account)
    assert first.fills and first.reconciliation.ok
    account.broker.book.apply(first.fills[0])  # the broker reports the same fill twice
    assert not reconcile(account.ledger, account.broker).ok
    switch = KillSwitch()
    nxt = market.dates[market.index_of(DEMO_AS_OF) + 1]
    second = cycle(market, registry, account=account, switch=switch, as_of=nxt)
    assert not second.reconciliation.ok
    assert second.risk.level is DegradationLevel.HALTED
    assert all(r.approved_qty == 0 for r in second.risk.results)
    assert switch.engaged and "reconciliation" in switch.state().reason


def test_a_saved_state_with_replayed_fills_loads_cleanly(
    market: MarketData, registry: Registry, tmp_path: Path
) -> None:
    account = PaperAccount(PHASE3.system.capital, PHASE3.costs)
    cycle(market, registry, account=account)
    data = account.to_json()
    data["ledger_fills"] = data["ledger_fills"] * 2  # a crash replayed the journal
    loaded = PaperAccount.from_json(data, PHASE3.costs)
    assert len(loaded.ledger.fills) == len(account.ledger.fills)
    assert reconcile(loaded.ledger, loaded.broker).ok


# ---------------------------------------------------------------- dropped broker


def _drop(*args: object, **kwargs: object) -> object:
    raise ConnectionError("paper broker unreachable")


def test_fills_before_a_drop_are_still_recorded(
    market: MarketData, registry: Registry, monkeypatch: pytest.MonkeyPatch
) -> None:
    account = PaperAccount(PHASE3.system.capital, PHASE3.costs)
    nonces = itertools.count()
    Orchestrator(
        PHASE3,
        registry,
        account,
        KillSwitch(),
        nonce_factory=lambda: f"nonce-{next(nonces)}",
        simulate_next_open=False,
    ).run_cycle(market, DEMO_AS_OF)
    assert account.broker.pending
    monkeypatch.setattr(PaperBroker, "check_stops", _drop)  # fills happen, then the line drops
    nxt = market.dates[market.index_of(DEMO_AS_OF) + 1]
    report = cycle(market, registry, account=account, as_of=nxt)
    assert account.ledger.fills  # the open's fills made it into the ledger
    assert len(account.ledger.fills) == len(account.broker.fills)
    assert not report.reconciliation.ok  # still a break: what else the broker did is unknown
    assert report.risk.level is DegradationLevel.HALTED


def test_a_broker_that_drops_before_the_open_halts_without_losing_orders(
    market: MarketData, registry: Registry, monkeypatch: pytest.MonkeyPatch
) -> None:
    account = PaperAccount(PHASE3.system.capital, PHASE3.costs)
    nonces = itertools.count()
    orchestrator = Orchestrator(
        PHASE3,
        registry,
        account,
        KillSwitch(),
        nonce_factory=lambda: f"nonce-{next(nonces)}",
        simulate_next_open=False,  # orders wait for tomorrow's open
    )
    first = orchestrator.run_cycle(market, DEMO_AS_OF)
    queued = list(account.broker.pending)
    assert queued and first.fills == ()
    monkeypatch.setattr(PaperBroker, "fill_pending", _drop)
    switch = KillSwitch()
    nxt = market.dates[market.index_of(DEMO_AS_OF) + 1]
    report = cycle(market, registry, account=account, switch=switch, as_of=nxt)
    assert not report.reconciliation.ok
    assert any("broker unreachable" in d for d in report.reconciliation.diffs)
    assert report.risk.level is DegradationLevel.HALTED
    assert switch.engaged and report.fills == ()
    assert account.broker.pending == queued  # nothing lost: still queued for a human to review


def test_a_broker_that_drops_at_submit_sends_nothing_and_stops(
    market: MarketData, registry: Registry, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(PaperBroker, "submit", _drop)
    switch = KillSwitch()
    report = cycle(market, registry, switch=switch)
    assert report.fills == () and report.positions == {}
    assert "NOT confirmed" in report.steps[11].summary
    assert switch.engaged and switch.state().by == "A46"
    assert report.records and all(
        r.outcome == "not confirmed: broker unreachable" for r in report.records if r.order
    )
    assert "broker unreachable at submit" in switch.state().reason
    assert report.kill_switch_engaged


# ---------------------------------------------------------------- corrupted kill switch


@pytest.mark.parametrize(
    "content",
    ["", "not json at all", '{"reason": "half written', "[1, 2, 3]", "null", "\x00\x01\x02"],
)
def test_a_corrupted_kill_switch_file_counts_as_engaged(tmp_path: Path, content: str) -> None:
    path = tmp_path / "kill_switch.json"
    path.write_text(content, encoding="utf-8")
    switch = KillSwitch(path)
    state = switch.state()
    assert state.engaged and "unreadable" in state.reason
    assert switch.engage("again", by="human").reason == state.reason  # first reason kept
    with pytest.raises(PermissionError):
        switch.reset("yes please", by="human")
    assert switch.engaged
    switch.reset(RESET_PHRASE, by="human")
    assert not switch.engaged and not path.exists()


def test_a_kill_switch_path_that_cannot_be_read_counts_as_engaged(tmp_path: Path) -> None:
    path = tmp_path / "kill_switch.json"
    path.mkdir()  # a folder where the file should be: reading it raises OSError
    assert KillSwitch(path).engaged


def test_a_cycle_with_a_corrupted_kill_switch_trades_nothing(
    market: MarketData, registry: Registry, tmp_path: Path
) -> None:
    path = tmp_path / "kill_switch.json"
    path.write_text("{garbage", encoding="utf-8")
    report = cycle(market, registry, switch=KillSwitch(path))
    assert report.risk.level is DegradationLevel.HALTED
    assert all(r.approved_qty == 0 for r in report.risk.results)
    assert report.fills == () and report.kill_switch_engaged


def test_cli_shows_a_corrupted_kill_switch(
    tmp_path: Path,
    repo_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    shutil.copytree(repo_root / "config", tmp_path / "config")
    monkeypatch.chdir(tmp_path)
    (tmp_path / "state").mkdir()
    (tmp_path / "state" / "kill_switch.json").write_text("oops", encoding="utf-8")
    assert main(["killswitch", "status"]) == 0
    out = capsys.readouterr().out
    assert "ENGAGED" in out and "unreadable" in out and RESET_PHRASE in out
