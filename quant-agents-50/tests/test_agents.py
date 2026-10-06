from __future__ import annotations

import math
from datetime import date

import numpy as np
import pytest

from quantagents.agents.a01_market_data import MarketDataAgent
from quantagents.agents.a02_data_quality import DataQualityAgent
from quantagents.agents.a03_features import FeatureAgent
from quantagents.agents.a08_volatility import VolatilityAgent
from quantagents.agents.a11_trend import TrendAgent
from quantagents.agents.a12_xs_momentum import CrossSectionalMomentumAgent
from quantagents.agents.a13_breakout import BreakoutAgent
from quantagents.agents.a15_exhaustion import ExhaustionAgent
from quantagents.agents.a16_reversion import ShortTermReversionAgent
from quantagents.agents.a23_calendar import (
    CalendarAgent,
    business_day_of_month,
    turn_of_month_position,
)
from quantagents.agents.a40_no_trade import NoTradeAgent
from quantagents.agents.a47_aggregator import MetaAggregator
from quantagents.agents.a48_portfolio import PortfolioAgent
from quantagents.agents.base import AgentContext, SignalAgent
from quantagents.aggregation import go_decision
from quantagents.config import AppConfig, RiskConfig
from quantagents.market import Bars, MarketData
from quantagents.schemas import (
    DecisionProposal,
    Direction,
    HealthAction,
    LiquidityReport,
    OrderSide,
    RegimeReport,
    VolForecast,
)
from tests.helpers import context_for, make_ctx, prediction, wavy_market, with_value

AS_OF = date(2026, 9, 30)
SIGNAL_AGENTS: list[SignalAgent] = [
    TrendAgent(),
    CrossSectionalMomentumAgent(),
    BreakoutAgent(),
    ExhaustionAgent(),
    ShortTermReversionAgent(),
    CalendarAgent(),
]


def _real_ctx(cfg: AppConfig, market: MarketData, as_of: date = AS_OF) -> AgentContext:
    view = market.view(as_of)
    symbols = market.symbols
    return AgentContext(
        "C1",
        "S1",
        view,
        cfg,
        FeatureAgent().compute(view, "S1", symbols),
        VolatilityAgent().forecast(view, "S1", symbols),
        symbols,
    )


@pytest.mark.parametrize("agent", SIGNAL_AGENTS, ids=lambda a: a.agent_id)
def test_signal_agent_contract(agent: SignalAgent, cfg: AppConfig, market: MarketData) -> None:
    ctx = _real_ctx(cfg, market)
    first = agent.predict(ctx)
    assert [p.symbol for p in first] == list(ctx.tradable)
    assert all(p.agent_id == agent.agent_id and p.team == agent.team for p in first)
    assert all(0.02 <= p.p_up <= 0.98 for p in first)
    assert first == agent.predict(ctx)  # deterministic


@pytest.mark.parametrize("agent", SIGNAL_AGENTS, ids=lambda a: a.agent_id)
def test_signal_agents_abstain_without_history(
    agent: SignalAgent, cfg: AppConfig, market: MarketData
) -> None:
    ctx = _real_ctx(cfg, market, market.dates[5])
    if isinstance(agent, CalendarAgent):
        return
    assert all(p.abstain for p in agent.predict(ctx))


def test_snapshot_id_tracks_the_data(market: MarketData) -> None:
    a01 = MarketDataAgent()
    view = market.view(AS_OF)
    snap = a01.snapshot(view)
    assert snap.snapshot_id == a01.snapshot(view).snapshot_id
    assert set(snap.last_close) == set(market.symbols)
    changed = with_value(market, "SYN_A", "close", market.index_of(AS_OF) - 5, 1.0)
    assert a01.snapshot(changed.view(AS_OF)).snapshot_id != snap.snapshot_id
    nan_close = with_value(market, "SYN_A", "close", market.index_of(AS_OF), math.nan)
    assert "SYN_A" not in a01.snapshot(nan_close.view(AS_OF)).last_close


@pytest.mark.parametrize(
    ("field", "offset", "value", "fault"),
    [
        ("close", 0, math.nan, "no complete bar"),
        ("open", -10, math.nan, "gaps"),
        ("low", -3, -1.0, "non-positive"),
        ("high", -2, 1.0, "inconsistent"),
        ("volume", -4, -5.0, "negative volume"),
    ],
)
def test_a02_catches_injected_faults(field: str, offset: int, value: float, fault: str) -> None:
    market = wavy_market(n=300)
    bad = with_value(market, "BBB", field, len(market) - 1 + offset, value)
    report = DataQualityAgent().check(bad.view(market.dates[-1]), "S1", RiskConfig())
    assert report.blocked_symbols == ("BBB",)
    assert fault in next(c.detail for c in report.checks if c.name == "BBB")
    assert report.score_0_100 == pytest.approx(100 * 2 / 3)
    assert report.action is HealthAction.DEFENSIVE


def test_a02_warnings_and_actions() -> None:
    market = wavy_market(n=300)
    clean = DataQualityAgent().check(market.view(market.dates[-1]), "S1", RiskConfig())
    assert clean.score_0_100 == 100 and clean.action is HealthAction.OK
    spiked = with_value(market, "AAA", "close", len(market) - 1, 140.0)  # a spike, not split-like
    spiked = with_value(spiked, "AAA", "high", len(market) - 1, 141.0)
    spiked = with_value(spiked, "AAA", "volume", len(market) - 1, 0.0)
    report = DataQualityAgent().check(spiked.view(market.dates[-1]), "S1", RiskConfig())
    assert report.score_0_100 == 96 and report.blocked_symbols == ()
    short = DataQualityAgent().check(market.view(market.dates[100]), "S1", RiskConfig())
    assert short.score_0_100 == 94
    bad = with_value(market, "AAA", "close", len(market) - 1, math.nan)
    bad = with_value(bad, "BBB", "close", len(market) - 1, math.nan)
    halted = DataQualityAgent().check(bad.view(market.dates[-1]), "S1", RiskConfig())
    assert halted.action is HealthAction.HALT and halted.stale_symbols == ("AAA", "BBB")


def split_at(market: MarketData, symbols: tuple[str, ...], index: int, ratio: float) -> MarketData:
    """Prices of ``symbols`` divided by ``ratio`` from ``index`` on (an unadjusted split)."""
    bars = {}
    for s in market.symbols:
        b = market.bars(s)
        scale = np.where(np.arange(len(market)) >= index, 1.0 / ratio, 1.0) if s in symbols else 1.0
        bars[s] = Bars.from_arrays(
            open=b.open * scale,
            high=b.high * scale,
            low=b.low * scale,
            close=b.close * scale,
            volume=b.volume,
        )
    return MarketData(market.dates, bars)


@pytest.mark.parametrize("ratio", [2.0, 3.0, 10.0, 0.5, 0.25])
def test_a02_blocks_an_unadjusted_split(ratio: float) -> None:
    market = wavy_market(n=300)
    split = split_at(market, ("BBB",), len(market) - 40, ratio)
    report = DataQualityAgent().check(split.view(market.dates[-1]), "S1", RiskConfig())
    assert report.blocked_symbols == ("BBB",)
    detail = next(c.detail for c in report.checks if c.name == "BBB")
    assert "split-like jump" in detail
    assert market.dates[-40].isoformat() in detail


def test_a02_split_check_ignores_shared_moves_and_old_splits() -> None:
    market = wavy_market(n=400)
    # every symbol halves on the same day: a market-wide move (or a currency switch), not a split
    shared = split_at(market, market.symbols, len(market) - 40, 2.0)
    report = DataQualityAgent().check(shared.view(market.dates[-1]), "S1", RiskConfig())
    assert report.blocked_symbols == ()
    # a split older than the feature window no longer affects any feature
    old = split_at(market, ("BBB",), 30, 2.0)
    assert (
        DataQualityAgent().check(old.view(market.dates[-1]), "S1", RiskConfig()).blocked_symbols
        == ()
    )
    # with no peers a split-like jump still counts
    alone = MarketData(market.dates, {"BBB": split_at(market, ("BBB",), 380, 2.0).bars("BBB")})
    lonely = DataQualityAgent().check(alone.view(market.dates[-1]), "S1", RiskConfig())
    assert lonely.blocked_symbols == ("BBB",)


def test_a08_volatility_and_shock() -> None:
    market = wavy_market(n=300)
    report = VolatilityAgent().forecast(market.view(market.dates[-1]), "S1", market.symbols)
    assert len(report.vol_forecasts) == 3 and report.novelty_score == 0
    forecast = report.vol("AAA")
    assert forecast is not None and forecast.sigma_daily > 0
    assert report.vol("ZZZ") is None
    shocked = with_value(market, "AAA", "close", len(market) - 1, 160.0)
    shocked = with_value(shocked, "AAA", "high", len(market) - 1, 161.0)
    shock_report = VolatilityAgent().forecast(shocked.view(market.dates[-1]), "S1", ["AAA"])
    assert shock_report.vol_forecasts[0].shock and shock_report.novelty_score == 1.0
    assert (
        VolatilityAgent().forecast(market.view(market.dates[30]), "S1", ["AAA"]).vol_forecasts == ()
    )


def test_turn_of_month_calendar() -> None:
    assert turn_of_month_position(date(2026, 9, 30)) == 0
    assert turn_of_month_position(date(2026, 10, 1)) == 1
    assert turn_of_month_position(date(2026, 10, 5)) == 3
    assert turn_of_month_position(date(2026, 10, 6)) is None
    assert turn_of_month_position(date(2026, 10, 3)) is None
    assert turn_of_month_position(date(2026, 7, 31)) == 0
    assert business_day_of_month(date(2026, 10, 2)) == 2


def test_a23_votes_only_at_turn_of_month(cfg: AppConfig, market: MarketData) -> None:
    on = CalendarAgent().predict(_real_ctx(cfg, market, date(2026, 9, 30)))
    assert all(p.direction is Direction.LONG and p.horizon_bars == 4 for p in on)
    day2 = CalendarAgent().predict(_real_ctx(cfg, market, date(2026, 10, 2)))
    assert {p.horizon_bars for p in day2} == {2}
    off = CalendarAgent().predict(_real_ctx(cfg, market, date(2026, 9, 22)))
    assert all(p.abstain for p in off)


def test_a12_ranks_and_needs_three_assets(cfg: AppConfig) -> None:
    market = wavy_market(("AAA", "BBB", "CCC"), n=300)
    feats = {"AAA": {"mom_12_1": 0.3}, "BBB": {"mom_12_1": 0.0}, "CCC": {"mom_12_1": -0.2}}
    preds = CrossSectionalMomentumAgent().predict(make_ctx(cfg, market, market.dates[-1], feats))
    by = {p.symbol: p for p in preds}
    assert (
        by["AAA"].direction is Direction.LONG
        and by["CCC"].direction is Direction.SHORT
        and by["BBB"].abstain
    )
    crash = {"AAA": {"mom_12_1": -0.1}, "BBB": {"mom_12_1": -0.2}, "CCC": {"mom_12_1": -0.3}}
    tilt = next(
        p
        for p in CrossSectionalMomentumAgent().predict(
            make_ctx(cfg, market, market.dates[-1], crash)
        )
        if p.symbol == "AAA"
    )
    assert tilt.p_up == pytest.approx(0.54)
    two = {"AAA": {"mom_12_1": 0.3}, "BBB": {"mom_12_1": 0.1}}
    assert all(
        p.abstain
        for p in CrossSectionalMomentumAgent().predict(make_ctx(cfg, market, market.dates[-1], two))
    )
    missing = {**feats, "DDD": {}}
    preds = CrossSectionalMomentumAgent().predict(
        make_ctx(cfg, market, market.dates[-1], missing, context_for(["AAA", "BBB", "CCC", "DDD"]))
    )
    assert next(p for p in preds if p.symbol == "DDD").abstain


def test_a16_reversion_rules(cfg: AppConfig) -> None:
    market = wavy_market(n=300)
    feats = {
        "AAA": {"close": 110.0, "sma_200": 100.0, "rsi_2": 5.0, "ibs": 0.1},
        "BBB": {"close": 90.0, "sma_200": 100.0, "rsi_2": 95.0, "ibs": 0.9},
        "CCC": {"close": 110.0, "sma_200": 100.0, "rsi_2": 50.0, "ibs": 0.5},
    }
    by = {
        p.symbol: p
        for p in ShortTermReversionAgent().predict(make_ctx(cfg, market, market.dates[-1], feats))
    }
    assert by["AAA"].p_up == 0.60 and by["BBB"].p_up == 0.40 and by["CCC"].abstain
    assert by["AAA"].horizon_bars == 5
    milder = {"AAA": {**feats["AAA"], "ibs": 0.5}, "BBB": {**feats["BBB"], "ibs": 0.5}, "CCC": {}}
    by = {
        p.symbol: p
        for p in ShortTermReversionAgent().predict(make_ctx(cfg, market, market.dates[-1], milder))
    }
    assert by["AAA"].p_up == 0.58 and by["BBB"].p_up == 0.42 and by["CCC"].abstain


def test_a11_trend_direction(cfg: AppConfig) -> None:
    market = wavy_market(n=300)
    up = {
        "mom_21": 0.05,
        "mom_63": 0.1,
        "mom_252": 0.3,
        "sma_50": 110.0,
        "sma_200": 100.0,
        "channel_55": 0.9,
    }
    down = {
        "mom_21": -0.05,
        "mom_63": -0.1,
        "mom_252": -0.3,
        "sma_50": 90.0,
        "sma_200": 100.0,
        "channel_55": -0.9,
    }
    flat = {
        "mom_21": 0.0,
        "mom_63": 0.0,
        "mom_252": 0.0,
        "sma_50": 100.0,
        "sma_200": 100.0,
        "channel_55": 0.0,
    }
    by = {
        p.symbol: p
        for p in TrendAgent().predict(
            make_ctx(cfg, market, market.dates[-1], {"AAA": up, "BBB": down, "CCC": flat})
        )
    }
    assert (
        by["AAA"].direction is Direction.LONG
        and by["BBB"].direction is Direction.SHORT
        and by["CCC"].abstain
    )
    assert by["AAA"].p_up <= 0.62 and by["AAA"].exp_return > 0 and by["AAA"].exp_vol > 0


def test_forecast_helper_edge_cases(cfg: AppConfig) -> None:
    market = wavy_market(n=300)
    ctx = make_ctx(cfg, market, market.dates[-1], {"AAA": {}}, context_for([]))
    agent = TrendAgent()
    assert agent.forecast(ctx, "AAA", 0.5, "no lean").abstain
    p = agent.forecast(ctx, "AAA", 0.999, "very sure")
    assert p.p_up == 0.98 and p.exp_vol == 0.0


def test_a40_no_trade_rules(cfg: AppConfig) -> None:
    a40 = NoTradeAgent()
    normal = VolForecast(symbol="AAA", sigma_daily=0.01, sigma_annual=0.16, regime="normal")
    calm = a40.verdict(
        cycle_id="C1",
        symbol="AAA",
        health_score=100,
        vol=normal,
        disagreement=0.1,
        net_edge=0.02,
        drawdown_used=0.0,
        cfg=cfg,
    )
    assert calm.p_no_trade == pytest.approx(0.15) and calm.reasons == ("no red flags",)
    shock = normal.model_copy(update={"shock": True})
    bad = a40.verdict(
        cycle_id="C1",
        symbol="AAA",
        health_score=85,
        vol=shock,
        disagreement=0.9,
        net_edge=None,
        drawdown_used=0.6,
        cfg=cfg,
    )
    assert bad.p_no_trade == pytest.approx(0.95) and len(bad.reasons) == 5
    high = normal.model_copy(update={"regime": "high"})
    assert a40.verdict(
        cycle_id="C1",
        symbol="AAA",
        health_score=100,
        vol=high,
        disagreement=0.1,
        net_edge=0.02,
        drawdown_used=0,
        cfg=cfg,
    ).p_no_trade == pytest.approx(0.30)
    assert a40.verdict(
        cycle_id="C1",
        symbol="AAA",
        health_score=100,
        vol=None,
        disagreement=0.1,
        net_edge=0.02,
        drawdown_used=0,
        cfg=cfg,
    ).p_no_trade == pytest.approx(0.45)


def test_a40_reads_regime_liquidity_and_cost(cfg: AppConfig) -> None:
    a40 = NoTradeAgent()
    normal = VolForecast(symbol="AAA", sigma_daily=0.01, sigma_annual=0.16, regime="normal")
    regime = RegimeReport(
        snapshot_id="S",
        p_high_vol=0.9,
        p_high_vol_prev=0.9,
        p_risk_on=0.1,
        p_crisis=0.8,
        breadth=0.0,
        confidence=0.8,
        label="crisis",
        vol_label="turbulent",
    )
    thin = LiquidityReport(
        symbol="AAA",
        spread_bps=0.0,
        spread_ratio=1.0,
        adv_notional=1000.0,
        amihud=0.0,
        impact_bps=40.0,
        est_cost_bps=45.0,
        tradability=0.0,
        max_order_notional=10.0,
        reference_notional=2000.0,
        detail="impact 40 bps",
    )

    def verdict(**kwargs: object) -> float:
        return a40.verdict(
            cycle_id="C1",
            symbol="AAA",
            health_score=100,
            vol=normal,
            disagreement=0.1,
            net_edge=0.006,
            drawdown_used=0.0,
            cfg=cfg,
            **kwargs,  # type: ignore[arg-type]
        ).p_no_trade

    assert verdict() == pytest.approx(0.15)
    assert verdict(regime=regime) == pytest.approx(0.40)
    assert verdict(liquidity=thin) == pytest.approx(0.40)
    assert verdict(regime=regime.model_copy(update={"label": "risk_off"})) == pytest.approx(0.15)
    assert verdict(round_trip_cost=0.01) == pytest.approx(0.50)  # A09 cost raises the edge bar
    assert verdict(round_trip_cost=0.0001) == pytest.approx(0.15)  # but can never lower it


def test_a48_liquidity_cap_and_stress_scale(cfg: AppConfig) -> None:
    a48 = PortfolioAgent()
    proposal = _proposal("AAA", Direction.LONG, True)

    def entry_qty(**kwargs: object) -> tuple[float, str]:
        target, intents = a48.construct(
            cycle_id="C1",
            proposals={"AAA": proposal},
            positions={},
            prices={"AAA": 100.0},
            atr={"AAA": 1.0},
            equity=10_000.0,
            cfg=cfg,
            debate_available=True,
            **kwargs,  # type: ignore[arg-type]
        )
        return (intents[0].qty if intents else 0.0), " ".join(target.notes)

    full, _ = entry_qty()
    assert full == 20  # position cap
    capped, notes = entry_qty(max_notional={"AAA": 750.0})
    assert capped == 7 and "A09 participation" in notes
    half, notes = entry_qty(risk_scale=0.5)
    assert half == 10 and "scaled to 50%" in notes  # applied AFTER the 20-share position cap
    both, _ = entry_qty(max_notional={"AAA": 750.0}, risk_scale=0.5)
    assert both == 3  # 7.5 shares allowed by A09, then halved by A45, then floored
    none, notes = entry_qty(risk_scale=0.0)
    assert none == 0 and "rounds to zero" in notes
    with pytest.raises(ValueError, match="risk_scale"):
        entry_qty(risk_scale=1.5)
    _, exits = a48.construct(
        cycle_id="C1",
        proposals={"AAA": _proposal("AAA", Direction.SHORT, False)},
        positions={"AAA": 30.0},
        prices={"AAA": 100.0},
        atr={"AAA": 1.0},
        equity=10_000.0,
        cfg=cfg,
        debate_available=True,
        max_notional={"AAA": 0.0},
        risk_scale=0.0,
    )
    assert exits[0].side is OrderSide.SELL and exits[0].qty == 30  # exits are never capped


def _proposal(symbol: str, direction: Direction, go: bool, hint: float = 1.0) -> DecisionProposal:
    p = 0.6 if direction is Direction.LONG else 0.4
    return DecisionProposal(
        decision_id=f"D-{symbol}",
        cycle_id="C1",
        symbol=symbol,
        direction=direction,
        pooled_p=p,
        p_direction=0.6,
        n_eff=3,
        disagreement=0.1,
        teams_agree=2,
        net_edge=0.01,
        exp_return=0.01,
        go=go,
        reasons=("test",),
        debate_outcome="not_live",
        size_hint=hint,
    )


def test_a48_entries_holds_exits_and_caps(cfg: AppConfig) -> None:
    a48 = PortfolioAgent()
    proposals = {
        "AAA": _proposal("AAA", Direction.LONG, True),
        "BBB": _proposal("BBB", Direction.SHORT, True),
        "CCC": _proposal("CCC", Direction.SHORT, False),
        "DDD": _proposal("DDD", Direction.LONG, False),
        "EEE": _proposal("EEE", Direction.LONG, True),
        "FFF": _proposal("FFF", Direction.LONG, True, hint=0.001),
    }
    prices = {"AAA": 100.0, "BBB": 50.0, "CCC": 20.0, "DDD": 30.0, "EEE": 10.0, "FFF": 100.0}
    atr = {"AAA": 2.0, "BBB": 1.0, "FFF": 2.0}
    target, intents = a48.construct(
        cycle_id="C1",
        proposals=proposals,
        positions={"CCC": 10.0, "DDD": 5.0},
        prices=prices,
        atr=atr,
        equity=10_000.0,
        cfg=cfg,
        debate_available=False,
    )
    by = {i.symbol: i for i in intents}
    entry = by["AAA"]
    assert entry.side is OrderSide.BUY and entry.stop_price == pytest.approx(96.0)
    assert entry.qty == 6  # 0.2475% of 10,000 = 24.75 risk / 4.0 stop distance
    assert by["CCC"].side is OrderSide.SELL and by["CCC"].qty == 10 and by["CCC"].stop_price is None
    assert "DDD" not in by and "BBB" not in by and "EEE" not in by and "FFF" not in by
    held = {t.symbol: t.target_qty for t in target.positions}
    assert held["DDD"] == 5.0 and held["CCC"] == 0.0
    notes = " ".join(target.notes)
    assert (
        "shorting_allowed" in notes
        and "no ATR" in notes
        and "rounds to zero" in notes
        and "debate layer" in notes
    )
    _, live = a48.construct(
        cycle_id="C1",
        proposals={"AAA": proposals["AAA"]},
        positions={},
        prices=prices,
        atr=atr,
        equity=10_000.0,
        cfg=cfg,
        debate_available=True,
    )
    assert live[0].qty == 12  # full 0.5% risk once the debate layer is live
    short_cfg = cfg.model_copy(
        update={"risk": cfg.risk.model_copy(update={"shorting_allowed": True})}
    )
    _, shorts = a48.construct(
        cycle_id="C1",
        proposals={"BBB": proposals["BBB"]},
        positions={},
        prices=prices,
        atr=atr,
        equity=10_000.0,
        cfg=short_cfg,
        debate_available=False,
    )
    assert shorts[0].side is OrderSide.SELL and shorts[0].stop_price == pytest.approx(52.0)


def test_a48_position_cap(cfg: AppConfig) -> None:
    proposal = _proposal("AAA", Direction.LONG, True)
    _, intents = PortfolioAgent().construct(
        cycle_id="C1",
        proposals={"AAA": proposal},
        positions={},
        prices={"AAA": 100.0},
        atr={"AAA": 0.01},
        equity=10_000.0,
        cfg=cfg,
        debate_available=True,
    )
    assert intents[0].qty == 20  # 20% position cap binds before the risk budget


def test_a47_proposal_memo(cfg: AppConfig) -> None:
    a47 = MetaAggregator()
    preds = [
        prediction("A11", p_up=0.62),
        prediction("A23", p_up=0.55, horizon=4),
        prediction("A16", abstain=True),
    ]
    pool = a47.pool("AAA", preds, cfg, two_stage=False)
    decision = go_decision(
        pool,
        sigma_daily=0.02,
        agg=cfg.aggregation,
        costs=cfg.costs,
        phase=3,
        p_no_trade=0.1,
        blocks=(),
    )
    proposal = a47.propose(
        decision_id="D1", cycle_id="C1", pool=pool, decision=decision, predictions=preds, cfg=cfg
    )
    assert proposal.go and proposal.size_hint > 0
    assert proposal.rationale_ids == ("C1:A11:AAA", "C1:A23:AAA")
    assert "AAA: GO" in proposal.memo
    blocked = go_decision(
        pool,
        sigma_daily=0.02,
        agg=cfg.aggregation,
        costs=cfg.costs,
        phase=3,
        p_no_trade=0.9,
        blocks=(),
    )
    assert (
        a47.propose(
            decision_id="D1", cycle_id="C1", pool=pool, decision=blocked, predictions=preds, cfg=cfg
        ).size_hint
        == 0
    )


def test_feature_agent_values(market: MarketData) -> None:
    frame = FeatureAgent().compute(market.view(AS_OF), "S1", ["SYN_A"])
    assert (
        frame.feature_version == "1.1" and "atr_14" in frame.get("SYN_A") and frame.get("ZZZ") == {}
    )
    assert np.isfinite(list(frame.get("SYN_A").values())).all()
