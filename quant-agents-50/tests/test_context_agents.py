"""A06 Regime Classifier, A07 Transition Detector and A09 Liquidity Analyst."""

from __future__ import annotations

import math

import numpy as np
import pytest

from quantagents.agents.a03_features import FeatureAgent
from quantagents.agents.a06_regime import RegimeAgent, symbol_regime, vol_elevation
from quantagents.agents.a07_transition import TransitionAgent
from quantagents.agents.a08_volatility import VolatilityAgent
from quantagents.agents.a09_liquidity import LiquidityAgent
from quantagents.config import AppConfig
from quantagents.market import MarketData
from quantagents.schemas import (
    ContextReport,
    Direction,
    FeatureFrame,
    LiquidityReport,
    RegimeReport,
)
from tests.helpers import path_market, regime_market, with_value


def classify(market: MarketData) -> RegimeReport:
    view = market.view(market.dates[-1])
    features = FeatureAgent().compute(view, "S", market.symbols)
    return RegimeAgent().classify(view, "S", market.symbols, features)


# ---- A06 --------------------------------------------------------------------------------


def test_a06_calm_market_is_calm() -> None:
    report = classify(regime_market(vol=0.01, drift=0.0008))
    assert report.vol_label == "calm" and report.p_high_vol < 0.5
    assert report.label == "risk_on" and report.p_crisis < 0.1
    assert report.breadth == 1.0 and len(report.symbols) == 4
    assert any("2-year median only" in m for m in report.methods)  # no fake second regime
    assert report == classify(regime_market(vol=0.01, drift=0.0008))  # deterministic


def test_a06_sees_turbulence() -> None:
    report = classify(regime_market(vol=0.008, shift_at=560, vol_after=0.035))
    assert report.vol_label == "turbulent" and report.p_high_vol >= 0.5
    assert any("sticky HMM" in m for m in report.methods)


def test_a06_flags_a_crisis() -> None:
    market = regime_market(
        vol=0.008, shift_at=520, vol_after=0.035, drift_after=-0.006, corr_after=0.7
    )
    report = classify(market)
    assert report.label == "crisis" and report.p_crisis >= 0.5
    assert report.breadth <= 0.25 and report.p_risk_on < 0.3


def test_a06_unknown_with_short_history() -> None:
    report = classify(regime_market(n=90))
    assert report.label == "unknown" and report.confidence == 0.0
    assert report.p_high_vol == 0.5 and "not enough history" in report.methods[0]


def test_symbol_regime_labels() -> None:
    trending = {"adx_14": 40.0, "er_20": 0.5, "sma_50": 110.0, "sma_200": 100.0, "mom_63": 0.1}
    assert symbol_regime("X", trending).label == "trending_up"
    falling = {**trending, "sma_50": 90.0, "mom_63": -0.1}
    assert symbol_regime("X", falling).label == "trending_down"
    choppy = {**trending, "adx_14": 12.0, "er_20": 0.05}
    assert symbol_regime("X", choppy).label == "ranging"
    mixed = {**trending, "mom_63": -0.1}
    result = symbol_regime("X", mixed)
    assert result.direction is Direction.FLAT and result.label == "ranging"
    assert symbol_regime("X", {"close": 1.0}).label == "unknown"


# ---- A07 --------------------------------------------------------------------------------


def detect(market: MarketData, regime: RegimeReport | None = None) -> list[str]:
    view = market.view(market.dates[-1])
    report = TransitionAgent().detect(view, "S", market.symbols, regime)
    return [d.name for d in report.detectors if d.fired]


def test_a07_quiet_market_no_alert() -> None:
    market = regime_market(vol=0.01, corr=0.2)
    report = TransitionAgent().detect(
        market.view(market.dates[-1]), "S", market.symbols, classify(market)
    )
    assert not report.alert and report.severity == 0.0
    assert all(d.ran for d in report.detectors)
    assert report.fired == ()


def test_a07_catches_a_volatility_shift() -> None:
    market = regime_market(vol=0.008, shift_at=585, vol_after=0.03)
    view = market.view(market.dates[-1])
    report = TransitionAgent().detect(view, "S", market.symbols, None)
    assert report.alert
    assert {"volatility_breakout", "change_point"} & set(report.fired)
    assert report.severity > 0


def test_a07_correlation_breakdown_and_liquidity_drain() -> None:
    together = regime_market(vol=0.01, corr=0.0, shift_at=580, corr_after=0.95, seed=11)
    assert "correlation_breakdown" in detect(together)
    drained = regime_market(vol=0.01, shift_at=596, volume_after=2e5)
    assert detect(drained) == ["liquidity_drain"]
    view = drained.view(drained.dates[-1])
    assert not TransitionAgent().detect(view, "S", drained.symbols, None).alert  # 1 weak signal


def test_a07_regime_shift_needs_a_big_move() -> None:
    market = regime_market()
    base = classify(market)
    jumped = base.model_copy(update={"p_high_vol": 0.9, "p_high_vol_prev": 0.2})
    assert "regime_shift" in detect(market, jumped)
    assert "regime_shift" not in detect(market, base)


def test_a07_skips_what_it_cannot_measure() -> None:
    market = regime_market(n=40, symbols=("AAA", "BBB"))
    report = TransitionAgent().detect(market.view(market.dates[-1]), "S", market.symbols, None)
    skipped = {d.name for d in report.detectors if not d.ran}
    assert skipped == {
        "change_point",
        "volatility_breakout",
        "correlation_breakdown",
        "regime_shift",
        "liquidity_drain",
    }
    assert report.severity == 0.0 and not report.alert
    no_value = regime_market(n=200, volume=0.0)
    report = TransitionAgent().detect(
        no_value.view(no_value.dates[-1]), "S", no_value.symbols, None
    )
    assert not next(d for d in report.detectors if d.name == "liquidity_drain").ran


# ---- A09 --------------------------------------------------------------------------------


def assess(
    market: MarketData, reference: float = 2_000.0, cfg: AppConfig | None = None
) -> tuple[LiquidityReport, ...]:
    view = market.view(market.dates[-1])
    context = VolatilityAgent().forecast(view, "S", market.symbols)
    return LiquidityAgent().assess(
        view, market.symbols, context, reference_notional=reference, cfg=cfg or AppConfig()
    )


def test_a09_deep_market_is_tradable() -> None:
    cfg = AppConfig()
    report = assess(regime_market(volume=1e6), cfg=cfg)[0]
    assert report.tradability > 0.95
    assert report.est_cost_bps == pytest.approx(cfg.costs.slippage_bps + report.impact_bps)
    assert report.max_order_notional == pytest.approx(0.01 * report.adv_notional)
    assert report.impact_bps < 1.0 and report.adv_notional > 1e7


def test_a09_thin_market_is_not() -> None:
    report = assess(regime_market(volume=20.0), reference=2_000.0)[0]
    assert report.tradability == 0.0 and report.impact_bps > 15
    assert report.max_order_notional < 100


def test_a09_unknown_liquidity_is_untradable() -> None:
    for market in (regime_market(volume=0.0), regime_market(n=15)):
        report = assess(market)[0]
        assert report.tradability == 0.0 and report.max_order_notional == 0.0
        assert "unknown liquidity" in report.detail


def test_a09_without_a08_uses_history() -> None:
    market = regime_market(volume=1e6)
    view = market.view(market.dates[-1])
    empty = ContextReport(snapshot_id="S", agent_id="A08", vol_forecasts=())
    report = LiquidityAgent().assess(
        view, market.symbols, empty, reference_notional=2_000.0, cfg=AppConfig()
    )[0]
    assert report.tradability > 0.9 and report.impact_bps > 0


def test_a09_spread_proxy_is_information_only() -> None:
    narrow = regime_market(volume=1e6, seed=4)
    wide = regime_market(volume=1e6, seed=4)
    a, b = assess(narrow)[0], assess(wide)[0]
    assert a.est_cost_bps == b.est_cost_bps
    assert a.spread_ratio > 0 and "information only" in a.detail


def test_defensive_paths_with_missing_or_flat_data() -> None:
    assert vol_elevation(np.full(10, np.nan)) == 0.0
    assert vol_elevation(np.zeros(60)) == 0.0
    # A06 without any feature rows and with a short (<200 bar) index.
    market = regime_market(n=160)
    view = market.view(market.dates[-1])
    bare = FeatureFrame(snapshot_id="S", feature_version="t", values={})
    report = RegimeAgent().classify(view, "S", market.symbols, bare)
    assert report.breadth == 0.5 and all(s.label == "unknown" for s in report.symbols)
    assert "vote of 2 signals" in report.methods[-1]
    # A07: a symbol with no clean recent prices -> correlation cannot be measured.
    gappy = regime_market(n=200)
    for i in range(len(gappy) - 20, len(gappy)):
        gappy = with_value(gappy, "AAA", "close", i, math.nan)
    corr = next(
        d
        for d in TransitionAgent()
        .detect(gappy.view(gappy.dates[-1]), "S", gappy.symbols, None)
        .detectors
        if d.name == "correlation_breakdown"
    )
    assert not corr.ran and "clean data" in corr.detail
    # A09: perfectly flat prices give no volatility estimate -> unknown, untradable.
    flat = path_market([100.0] * 80)
    empty = ContextReport(snapshot_id="S", agent_id="A08", vol_forecasts=())
    liq = LiquidityAgent().assess(
        flat.view(flat.dates[-1]), flat.symbols, empty, reference_notional=2000, cfg=AppConfig()
    )[0]
    assert liq.tradability == 0.0 and "no volatility estimate" in liq.detail
