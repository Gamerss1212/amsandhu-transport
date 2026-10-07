from __future__ import annotations

import itertools
import math
from datetime import date
from pathlib import Path

import pytest

from quantagents.agents.a11_trend import TrendAgent
from quantagents.agents.a35_scorekeeper import Scorekeeper
from quantagents.agents.base import AgentContext
from quantagents.audit import AuditLog, verify_chain
from quantagents.bus import MessageBus
from quantagents.config import AppConfig
from quantagents.data.synthetic import DEMO_AS_OF
from quantagents.execution.paper import PaperAccount, reconcile
from quantagents.market import MarketData
from quantagents.orchestrator import CycleReport, Orchestrator
from quantagents.registry import Registry
from quantagents.report import format_cycle_report
from quantagents.risk.killswitch import KillSwitch
from quantagents.schemas import AgentPrediction, DegradationLevel
from tests.helpers import with_second_team, with_value

PHASE3 = AppConfig.model_validate({"system": {"phase": 3}})


def run(
    cfg: AppConfig,
    registry: Registry,
    market: MarketData,
    as_of: date = DEMO_AS_OF,
    *,
    switch: KillSwitch | None = None,
    account: PaperAccount | None = None,
    simulate: bool = True,
) -> tuple[CycleReport, Orchestrator]:
    orchestrator = make(cfg, registry, switch=switch, account=account, simulate=simulate)
    return orchestrator.run_cycle(market, as_of), orchestrator


def make(
    cfg: AppConfig,
    registry: Registry,
    *,
    switch: KillSwitch | None = None,
    account: PaperAccount | None = None,
    simulate: bool = True,
) -> Orchestrator:
    nonces = itertools.count()
    return Orchestrator(
        cfg,
        registry,
        account if account is not None else PaperAccount(cfg.system.capital, cfg.costs),
        switch if switch is not None else KillSwitch(),
        nonce_factory=lambda: f"nonce-{next(nonces)}",
        simulate_next_open=simulate,
    )


def test_full_core_cycle_runs_all_25_agents(
    cfg: AppConfig, registry: Registry, market: MarketData
) -> None:
    report, orchestrator = run(cfg, registry, market)
    assert cfg.system.phase == 4
    assert [s.number for s in report.steps] == list(range(1, 16))
    assert "25 agents running (2 in shadow)" in report.steps[0].summary
    assert {report.steps[i].status for i in (5, 6, 8, 9)} == {"done"}  # A35, A47, A47, A48+A45
    assert report.context.regime is not None and report.context.transition is not None
    assert len(report.context.liquidity) == len(market.symbols)
    assert report.scores is not None and report.stress is not None
    assert report.context_failures == {}
    assert len(report.predictions) == 6 * len(market.symbols)  # A11 A12 A13 A15 A16 A23
    assert "shadow (scored, no vote): A13, A15" in report.steps[4].summary
    for proposal in report.proposals:  # every no-trade is explained
        assert proposal.go or proposal.reasons
    assert verify_chain(orchestrator.audit.records)[0]
    topics = {e.topic for e in orchestrator.bus.messages()}
    assert {
        "context.vol",
        "context.regime",
        "context.transition",
        "context.liquidity",
        "governance.scorecards",
        "risk.stress",
        "risk.verdict",
    } <= topics
    stored = orchestrator.a35.records
    assert len(stored) == len(report.predictions)
    assert {r.voting for r in stored.values() if r.prediction.agent_id in {"A13", "A15"}} == {False}


def test_phase_3_cycle_trades_through_a45_and_a49(registry: Registry, market: MarketData) -> None:
    cfg = PHASE3
    report, orchestrator = run(cfg, registry, market)
    assert report.health.score_0_100 == 100 and report.quorum == 1.0
    assert len(report.predictions) == 4 * len(market.symbols)
    assert report.steps[5].status == "skipped"  # A35 is a Phase 4 agent
    go = [p for p in report.proposals if p.go]
    assert go, "the phase 3 demo should show at least one GO decision"
    assert report.risk.level is DegradationLevel.NORMAL
    assert report.stress is not None and report.stress.entry_scale == 1.0
    assert report.stress.tail_loss_pct < report.stress.budget_pct
    assert report.fills and all(f.trade_date == date(2026, 10, 1) for f in report.fills)
    assert report.reconciliation.ok
    assert report.records and report.records[0].outcome == "filled"
    for intent in report.intents:
        assert intent.stop_price is not None and intent.stop_price < intent.ref_price
        liq = report.context.liq(intent.symbol)
        assert liq is not None and intent.qty * intent.ref_price <= liq.max_order_notional
    risk_pct = [t.risk_pct for t in report.target.positions if t.risk_pct]
    assert risk_pct and max(risk_pct) < cfg.risk.major_trade_risk_pct  # capped below major size
    topics = {e.topic for e in orchestrator.bus.messages()}
    assert {"signals.commit", "signals.reveal", "orders.fills", "decision.proposal"} <= topics


def test_phase_4_trades_when_two_teams_agree(registry: Registry, market: MarketData) -> None:
    cfg = AppConfig()
    report, _ = run(cfg, with_second_team(registry), market)
    go = [p for p in report.proposals if p.go]
    assert go and all(p.teams_agree >= 2 for p in go)
    assert report.stress is not None
    assert report.fills, "a GO that passes A45 and A49 should fill at the next open"
    assert report.risk.level is DegradationLevel.NORMAL


def test_cycle_is_deterministic(cfg: AppConfig, registry: Registry, market: MarketData) -> None:
    first, _ = run(cfg, registry, market)
    second, _ = run(cfg, registry, market)
    assert first.model_dump() == second.model_dump()


def test_kill_switch_blocks_new_entries(
    cfg: AppConfig, registry: Registry, market: MarketData
) -> None:
    switch = KillSwitch()
    switch.engage("manual test", by="human")
    report, _ = run(PHASE3, registry, market, switch=switch)
    assert report.risk.level is DegradationLevel.HALTED
    assert all(r.approved_qty == 0 for r in report.risk.results)
    assert report.fills == () and report.kill_switch_engaged


def test_bad_data_blocks_symbol_and_halts(
    cfg: AppConfig, registry: Registry, market: MarketData
) -> None:
    i = market.index_of(DEMO_AS_OF)
    one_bad = with_value(market, "SYN_E", "close", i, math.nan)
    report, _ = run(cfg, registry, one_bad)
    assert "SYN_E" in report.health.blocked_symbols
    assert all(p.symbol != "SYN_E" for p in report.proposals)
    assert report.context.liq("SYN_E") is None
    many_bad = one_bad
    for symbol in ("SYN_A", "SYN_B", "SYN_C"):
        many_bad = with_value(many_bad, symbol, "close", i, math.nan)
    switch = KillSwitch()
    report, _ = run(cfg, registry, many_bad, switch=switch)
    assert report.risk.level is DegradationLevel.HALTED
    assert switch.engaged and "data health" in switch.state().reason  # A49 fired the kill switch


class CrashingAgent(TrendAgent):
    def predict(self, ctx: AgentContext) -> list[AgentPrediction]:
        raise RuntimeError("model file missing")


def test_agent_crash_is_an_abstention(
    cfg: AppConfig, registry: Registry, market: MarketData
) -> None:
    orchestrator = make(cfg, registry)
    orchestrator.signal_agents[0] = CrashingAgent()
    report = orchestrator.run_cycle(market, DEMO_AS_OF)
    assert "RuntimeError" in report.seal_rejections["A11"]
    assert report.quorum == 0.75  # 3 of the 4 voting agents (A13 and A15 are shadow)
    assert report.risk.level is DegradationLevel.REDUCED


def _boom(*args: object, **kwargs: object) -> None:
    raise RuntimeError("boom")


def test_transition_detector_failure_fails_safe(
    cfg: AppConfig, registry: Registry, market: MarketData, monkeypatch: pytest.MonkeyPatch
) -> None:
    orchestrator = make(cfg, registry)
    monkeypatch.setattr(orchestrator.a07, "detect", _boom)
    report = orchestrator.run_cycle(market, DEMO_AS_OF)
    assert "A07" in report.context_failures
    assert report.context.transition is None and report.context.transition_alert
    assert report.risk.level is DegradationLevel.REDUCED
    assert "FAILED" in report.steps[3].summary


def test_regime_failure_is_survivable(
    cfg: AppConfig, registry: Registry, market: MarketData, monkeypatch: pytest.MonkeyPatch
) -> None:
    orchestrator = make(cfg, registry)
    monkeypatch.setattr(orchestrator.a06, "classify", _boom)
    report = orchestrator.run_cycle(market, DEMO_AS_OF)
    assert "A06" in report.context_failures and report.context.regime is None
    # Missing context must never make trading easier: A40 counts the failure as a red flag.
    assert all("A06 regime check failed" in " ".join(v.reasons) for v in report.no_trade)
    healthy, _ = run(cfg, registry, market)
    for broken, ok in zip(report.no_trade, healthy.no_trade, strict=True):
        assert broken.p_no_trade >= min(ok.p_no_trade + 0.25, 0.95) - 1e-9
    regime_detector = (
        next(d for d in report.context.transition.detectors if d.name == "regime_shift")
        if report.context.transition
        else None
    )
    assert regime_detector is not None and not regime_detector.ran


def test_stress_failure_blocks_new_entries(
    registry: Registry, market: MarketData, monkeypatch: pytest.MonkeyPatch
) -> None:
    orchestrator = make(PHASE3, registry)
    monkeypatch.setattr(orchestrator.a45, "assess", _boom)
    report = orchestrator.run_cycle(market, DEMO_AS_OF)
    assert any(p.go for p in report.proposals)  # the decision said GO...
    assert report.intents == () and report.fills == ()  # ...but no entry without a stress test
    assert "A45" in report.context_failures and "fail safe" in report.steps[9].summary


def test_liquidity_failure_blocks_new_entries(
    registry: Registry, market: MarketData, monkeypatch: pytest.MonkeyPatch
) -> None:
    orchestrator = make(PHASE3, registry)
    monkeypatch.setattr(orchestrator.a09, "assess", _boom)
    report = orchestrator.run_cycle(market, DEMO_AS_OF)
    assert "A09" in report.context_failures
    assert all(x.tradability == 0 for x in report.context.liquidity)
    assert report.intents == ()


def test_multi_day_paper_loop(registry: Registry, market: MarketData, tmp_path: Path) -> None:
    cfg = PHASE3
    account = PaperAccount(cfg.system.capital, cfg.costs)
    audit = AuditLog(tmp_path / "audit.jsonl")
    bus = MessageBus()
    start = market.index_of(date(2026, 9, 1))
    days = market.dates[start : market.index_of(DEMO_AS_OF) + 2]
    for day in days:
        orchestrator = Orchestrator(
            cfg, registry, account, KillSwitch(), audit=audit, bus=bus, simulate_next_open=False
        )
        report = orchestrator.run_cycle(market, day)
        assert report.reconciliation.ok, report.reconciliation.diffs
        path = tmp_path / "account.json"
        account.save(path)
        account = PaperAccount.load_or_new(path, cfg.system.capital, cfg.costs)
    assert account.ledger.fills, "the loop should have traded"
    assert reconcile(account.ledger, account.broker).ok
    assert all(f.trade_date > date(2026, 9, 1) for f in account.ledger.fills)
    assert verify_chain(AuditLog(tmp_path / "audit.jsonl").records)[0]
    assert len(account.equity_history) == len(days)


def test_a35_memory_scores_predictions_across_days(
    cfg: AppConfig, registry: Registry, market: MarketData, tmp_path: Path
) -> None:
    keeper = Scorekeeper()
    account = PaperAccount(cfg.system.capital, cfg.costs)
    start = market.index_of(date(2026, 8, 3))
    report = None
    for day in market.dates[start : market.index_of(DEMO_AS_OF) + 1]:
        orchestrator = Orchestrator(
            cfg, registry, account, KillSwitch(), scorekeeper=keeper, simulate_next_open=False
        )
        report = orchestrator.run_cycle(market, day)
        keeper.save(tmp_path / "scores.json")
        keeper = Scorekeeper.load_or_new(tmp_path / "scores.json")
    assert report is not None and report.scores is not None
    assert report.scores.n_scored > 0 and report.scores.pooled_n > 0
    a11 = report.scores.card("A11")
    assert a11 is not None and a11.n_scored > 0 and a11.brier is not None
    # Nothing is scored before its horizon has passed.
    last = market.index_of(DEMO_AS_OF)
    for record in keeper.records.values():
        if record.outcome is not None:
            assert market.index_of(record.as_of) + record.prediction.horizon_bars <= last


def test_phase_4_uses_two_stage_pooling(registry: Registry, market: MarketData) -> None:
    cfg = AppConfig.model_validate({"system": {"phase": 4}})
    report, _ = run(cfg, registry, market)
    pool_step = next(s for s in report.steps if s.number == 7)
    assert pool_step.status == "done" and "two-stage" in pool_step.summary
    assert next(s for s in report.steps if s.number == 6).summary.startswith("A35 scored")
    assert all(p.n_eff == 3.0 for p in report.proposals if p.teams_agree == 3)


def test_shadow_agents_are_scored_but_do_not_vote(
    cfg: AppConfig, registry: Registry, market: MarketData
) -> None:
    shadowed = Registry(
        [s.model_copy(update={"state": "shadow"}) if s.id == "A12" else s for s in registry.specs]
    )
    report, _ = run(cfg, shadowed, market)
    assert any(p.agent_id == "A12" for p in report.predictions)  # sealed and stored for scoring
    assert all(":A12:" not in rid for prop in report.proposals for rid in prop.rationale_ids)
    assert report.quorum == 1.0
    assert "shadow (scored, no vote): A12, A13, A15" in report.steps[4].summary


def test_a45_scaling_is_rechecked_on_the_book_actually_sent(
    registry: Registry, market: MarketData
) -> None:
    tight = AppConfig.model_validate(
        {"risk": {"max_daily_loss_pct": 0.15, "max_weekly_loss_pct": 4, "max_drawdown_pct": 15}}
    )
    loose, _ = run(AppConfig(), with_second_team(registry), market)
    report, _ = run(tight, with_second_team(registry), market)
    assert report.stress is not None and report.stress.entry_scale < 1.0
    final = report.stress.tail_loss_final_pct
    assert final is not None and final <= report.stress.budget_pct + 1e-9
    full = {i.symbol: i.qty for i in loose.intents}
    for intent in report.intents:
        assert intent.qty < full[intent.symbol]  # every entry really was shrunk
    assert "re-checked after scaling" in format_cycle_report(report)


def test_scorekeeper_failure_fails_safe(
    cfg: AppConfig, registry: Registry, market: MarketData, monkeypatch: pytest.MonkeyPatch
) -> None:
    orchestrator = make(cfg, registry)
    monkeypatch.setattr(orchestrator.a35, "score_matured", _boom)
    monkeypatch.setattr(orchestrator.a35, "record", _boom)
    report = orchestrator.run_cycle(market, DEMO_AS_OF)
    assert "A35" in report.context_failures and report.scores is None
    assert "A35 FAILED" in report.steps[5].summary and "FAILED" in report.steps[14].summary
    assert all("A35 calibration failed" in " ".join(v.reasons) for v in report.no_trade)


def test_long_symbol_names_keep_the_report_columns_apart(
    cfg: AppConfig, registry: Registry
) -> None:
    from quantagents.data.synthetic import DEFAULT_SPECS, SyntheticSpec, synthetic_market

    specs = [
        SyntheticSpec(f"{s.symbol}-CAD.KRAKEN", s.annual_drift, s.annual_vol)
        for s in DEFAULT_SPECS[:3]
    ]
    every = AppConfig.model_validate({"universe": {"symbols": []}})  # every symbol in the data
    report = make(every, registry).run_cycle(synthetic_market(specs=specs), DEMO_AS_OF)
    text = format_cycle_report(report)
    for spec in specs:
        rows = [line for line in text.splitlines() if line.startswith(spec.symbol)]
        assert rows and all(row[len(spec.symbol)] == " " for row in rows), rows
