"""A13 Structure & Breakout Agent and A15 Trend Exhaustion Agent."""

from __future__ import annotations

import numpy as np
import pytest

from quantagents.agents.a03_features import FeatureAgent
from quantagents.agents.a08_volatility import VolatilityAgent
from quantagents.agents.a13_breakout import (
    BreakoutAgent,
    Breakouts,
    breakout_events,
    follow_through_rate,
    structure,
)
from quantagents.agents.a15_exhaustion import ExhaustionAgent
from quantagents.agents.base import AgentContext
from quantagents.config import AppConfig
from quantagents.market import MarketData
from quantagents.schemas import Direction
from tests.helpers import path_market, staircase


def ctx_for(market: MarketData) -> AgentContext:
    view = market.view(market.dates[-1])
    features = FeatureAgent().compute(view, "S", market.symbols)
    context = VolatilityAgent().forecast(view, "S", market.symbols)
    return AgentContext("C", "S", view, AppConfig(), features, context, market.symbols)


# ---- A13 --------------------------------------------------------------------------------


def test_breakout_events_count_each_run_once() -> None:
    close = np.array([1, 2, 3, 3, 1, 3, 0, 0], dtype=float)
    upper = np.full(8, 2.5)
    lower = np.full(8, 0.5)
    events = breakout_events(close, upper, lower)
    assert events.up == (2, 5) and events.down == (6,)
    nan_channel = breakout_events(close, np.full(8, np.nan), np.full(8, np.nan))
    assert nan_channel == Breakouts((), ())


def test_follow_through_only_uses_finished_events() -> None:
    close = np.array([10, 11, 12, 13, 14, 15, 9, 8, 7], dtype=float)
    events = Breakouts(up=(1, 6), down=(3,))
    rate, n = follow_through_rate(close, events, horizon=2, prior=0.0)
    # up@1: 13 > 11 hit; down@3: 15 < 13 miss; up@6: 7 > 9 miss -> but 6 + 2 = 8 is the last bar
    assert n == 3 and rate == pytest.approx(1 / 3)
    rate, n = follow_through_rate(close[:8], events, horizon=2, prior=0.0)
    assert n == 2 and rate == pytest.approx(0.5)  # the event at 6 has not finished yet
    assert follow_through_rate(close, Breakouts((), ()), 2)[0] == 0.5  # prior only


def test_structure_reads_swings() -> None:
    up = np.array([1, 3, 2, 4, 3, 5, 4, 6, 5, 7, 6, 8, 7], dtype=float)
    assert structure(up, up - 1.0, k=1) == 1
    assert structure(-up, -up - 1.0, k=1) == -1
    assert structure(np.ones(10), np.ones(10), k=2) == 0


def test_a13_backs_a_confirmed_breakout() -> None:
    prices = staircase()
    up = path_market([*prices, prices[-1] * 1.03], volume=[1e6] * len(prices) + [3e6])
    p = BreakoutAgent().predict(ctx_for(up))[0]
    assert p.direction is Direction.LONG and 0.55 < p.p_up <= 0.58
    assert "volume confirmed" in p.reasoning_summary and "follow-through" in p.reasoning_summary
    down_prices = [1e4 / x for x in prices]
    down = path_market([*down_prices, down_prices[-1] * 0.97], volume=[1e6] * len(prices) + [3e6])
    assert BreakoutAgent().predict(ctx_for(down))[0].direction is Direction.SHORT


def test_a13_unconfirmed_breakout_is_weaker() -> None:
    prices = staircase()
    loud = path_market([*prices, prices[-1] * 1.03], volume=[1e6] * len(prices) + [3e6])
    quiet = path_market([*prices, prices[-1] * 1.03])
    loud_score = BreakoutAgent().score(loud.view(loud.dates[-1]), "AAA")
    quiet_score = BreakoutAgent().score(quiet.view(quiet.dates[-1]), "AAA")
    assert loud_score is not None and quiet_score is not None
    assert 0 < quiet_score[0] < loud_score[0]


def test_a13_fades_a_false_breakout() -> None:
    prices = staircase()
    level = prices[-4]
    trap = path_market([*prices[:-3], level * 1.03, level, level * 0.97, level * 0.97])
    p = BreakoutAgent().predict(ctx_for(trap))[0]
    assert p.direction is Direction.SHORT and "false breakout" in p.reasoning_summary


def test_a13_abstains_without_clean_history() -> None:
    short = path_market(staircase(steps=5))
    assert BreakoutAgent().predict(ctx_for(short))[0].abstain
    flat = path_market([100.0] * 300)
    p = BreakoutAgent().predict(ctx_for(flat))[0]
    assert p.abstain and "no breakout" in p.reasoning_summary


# ---- A15 --------------------------------------------------------------------------------


def exhaustion_signs(close: list[float], volume: list[float] | None = None) -> list[str]:
    market = path_market(close, volume=volume)
    view = market.view(market.dates[-1])
    features = FeatureAgent().compute(view, "S", market.symbols).get("AAA")
    return ExhaustionAgent().signs(view, "AAA", features, 1)


def test_a15_leans_against_a_parabolic_trend() -> None:
    base = 100 * np.exp(0.002 * np.arange(300))
    parabolic = [*base[:-15], *(base[-16] * np.exp(np.cumsum(np.full(15, 0.025))))]
    p = ExhaustionAgent().predict(ctx_for(path_market(parabolic)))[0]
    assert p.direction is Direction.SHORT and 0.44 <= p.p_up < 0.5
    assert "extension" in p.reasoning_summary and "stretched_rsi" in p.reasoning_summary


def test_a15_signs() -> None:
    base = list(100 * np.exp(np.cumsum(np.full(240, 0.001))))
    moves = [0.025] * 8 + [-0.008] * 20 + [0.009] * 20  # sharp peak, dip, slow new high
    assert "divergence" in exhaustion_signs(base + list(base[-1] * np.exp(np.cumsum(moves))))
    trend = list(100 * np.exp(np.cumsum(np.full(300, 0.001))))
    climax = exhaustion_signs([*trend, trend[-1] * 1.045], [1e6] * 300 + [4e6])
    assert "climax_volume" in climax
    clean = list(100 * np.exp(np.cumsum(np.full(290, 0.003))))
    chop = [clean[-1] * (1.01 if i % 2 == 0 else 0.995) for i in range(10)]
    assert "efficiency_decay" in exhaustion_signs(clean + chop)


def test_a15_abstains_on_healthy_or_absent_trends() -> None:
    rng = np.random.default_rng(1)
    healthy = list(100 * np.exp(np.cumsum(rng.normal(0.001, 0.01, 300))))
    p = ExhaustionAgent().predict(ctx_for(path_market(healthy)))[0]
    assert p.abstain and "looks healthy" in p.reasoning_summary
    flat = [100 + np.sin(i / 5) for i in range(300)]
    p = ExhaustionAgent().predict(ctx_for(path_market(flat)))[0]
    assert p.abstain and "no established trend" in p.reasoning_summary
    short = ExhaustionAgent().predict(ctx_for(path_market(healthy[:60])))[0]
    assert short.abstain and "insufficient" in short.reasoning_summary


def test_a15_skips_volume_signs_when_data_has_gaps() -> None:
    base = 100 * np.exp(0.002 * np.arange(300))
    parabolic = [*base[:-15], *(base[-16] * np.exp(np.cumsum(np.full(15, 0.025))))]
    volume = [1e6] * 300
    volume[-30] = float("nan")
    signs = exhaustion_signs(parabolic, volume)
    assert set(signs) <= {"extension", "stretched_rsi"}  # window checks need clean data
