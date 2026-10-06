from __future__ import annotations

from collections.abc import Mapping

import numpy as np
import pytest

from quantagents.backtest.engine import Backtester, performance_metrics
from quantagents.backtest.strategies import (
    DEFAULT_VARIANT,
    AgentEnsembleStrategy,
    buy_and_hold,
    sma_filter,
    strategy_grid,
    tsmom,
)
from quantagents.config import AppConfig
from quantagents.market import MarketData, MarketView

WARMUP = 260


def single(market: MarketData, symbol: str = "SYN_A") -> MarketData:
    return MarketData(market.dates, {symbol: market.bars(symbol)})


def test_buy_and_hold_matches_the_price_change_exactly(market: MarketData) -> None:
    one = single(market)
    result = Backtester(0.0).run(one, buy_and_hold()(one), warmup=WARMUP)
    bars = one.bars("SYN_A")
    assert result.equity[-1] == pytest.approx(bars.close[-1] / bars.open[WARMUP + 1], rel=1e-12)
    assert len(result.equity) == len(result.dates) == len(one) - WARMUP
    assert len(result.returns) == len(result.turnover) == len(result.weights)


def test_costs_only_reduce_returns(market: MarketData) -> None:
    free = Backtester(0.0).run(market, tsmom(63)(market), warmup=WARMUP)
    paid = Backtester(0.002).run(market, tsmom(63)(market), warmup=WARMUP)
    assert paid.equity[-1] < free.equity[-1]
    assert np.array_equal(paid.turnover, free.turnover)


def test_strategy_only_sees_the_past(market: MarketData) -> None:
    seen: list[int] = []

    def spy(view: MarketView) -> Mapping[str, float]:
        seen.append(len(view))
        return {}

    Backtester(0.0).run(market, spy, warmup=WARMUP)
    assert seen == list(range(WARMUP + 1, len(market)))


@pytest.mark.parametrize(
    ("weights", "message"),
    [
        ({"NOPE": 0.1}, "unknown"),
        ({"SYN_A": float("nan")}, "non-finite"),
        ({"SYN_A": -0.1}, "short"),
        ({"SYN_A": 0.8, "SYN_B": 0.8}, "gross"),
    ],
)
def test_invalid_weights_are_refused(
    market: MarketData, weights: dict[str, float], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        Backtester(0.0).run(market, lambda view: weights, warmup=WARMUP)


def test_engine_argument_checks(market: MarketData) -> None:
    with pytest.raises(ValueError):
        Backtester(-0.1)
    with pytest.raises(ValueError):
        Backtester(0.0).run(market, buy_and_hold()(market), warmup=len(market))
    shorts = Backtester(0.0, allow_short=True, max_gross=2.0).run(
        market, lambda view: {"SYN_A": -0.5}, warmup=WARMUP
    )
    assert shorts.metrics["exposure_days_pct"] == 100.0


def test_performance_metrics() -> None:
    returns = np.array([0.01, -0.02, 0.03, 0.0])
    m = performance_metrics(returns, np.zeros(4))
    assert m["total_return"] == pytest.approx(1.01 * 0.98 * 1.03 - 1)
    assert m["max_drawdown"] == pytest.approx(0.02)
    assert performance_metrics(np.array([]), np.array([])) == {"n_days": 0.0}
    assert performance_metrics(np.array([-1.0, 0.0]), np.zeros(2))["cagr"] == -1.0


def test_reference_strategies_and_grid(market: MarketData, cfg: AppConfig) -> None:
    view = market.view(market.dates[-1])
    assert sum(buy_and_hold()(market)(view).values()) == pytest.approx(1.0)
    assert all(w == pytest.approx(1 / 6) for w in sma_filter(200)(market)(view).values())
    assert sma_filter(200)(market)(market.view(market.dates[50])) == {}
    names = {name for family in DEFAULT_VARIANT for name, _ in strategy_grid(family, cfg)}
    assert set(DEFAULT_VARIANT.values()) <= names
    assert len(strategy_grid("tsmom", cfg)) == 6
    with pytest.raises(KeyError):
        strategy_grid("magic", cfg)


def test_agent_ensemble_strategy_is_long_only_and_bounded(
    market: MarketData, cfg: AppConfig
) -> None:
    strategy = AgentEnsembleStrategy(cfg)
    start = market.index_of(market.dates[-40])
    outputs = [strategy(market.view_at(i)) for i in range(start, len(market))]
    assert any(outputs), "the ensemble should hold something in the last 40 days"
    for weights in outputs:
        assert all(0 < w <= cfg.risk.max_position_pct / 100 for w in weights.values())
        assert sum(weights.values()) <= 1.0 + 1e-9


def test_an_unchanged_target_drifts_like_real_buy_and_hold(market: MarketData) -> None:
    """Fix 2026-10-06: the engine no longer resets the book to its targets every day for free."""
    two = MarketData(market.dates, {s: market.bars(s) for s in ("SYN_A", "SYN_B")})
    result = Backtester(0.0).run(two, lambda _: {"SYN_A": 0.5, "SYN_B": 0.5}, warmup=WARMUP)
    a, b = two.bars("SYN_A"), two.bars("SYN_B")
    expected = 0.5 * a.close[-1] / a.open[WARMUP + 1] + 0.5 * b.close[-1] / b.open[WARMUP + 1]
    assert result.equity[-1] == pytest.approx(expected, rel=1e-12)
    assert result.turnover[0] == 1.0 and np.all(result.turnover[1:] == 0.0)


def test_a_changed_target_trades_from_the_drifted_holdings(market: MarketData) -> None:
    two = MarketData(market.dates, {s: market.bars(s) for s in ("SYN_A", "SYN_B")})

    def tilt(view: MarketView) -> Mapping[str, float]:
        return {"SYN_A": 0.5, "SYN_B": 0.5 if len(view) == WARMUP + 1 else 0.4}

    result = Backtester(0.001).run(two, tilt, warmup=WARMUP)
    a, b = two.bars("SYN_A"), two.bars("SYN_B")
    t = WARMUP + 1  # bought at this open; prices then move to the next open
    ra, rb = a.open[t + 1] / a.open[t], b.open[t + 1] / b.open[t]
    growth = 0.5 * ra + 0.5 * rb
    held_a, held_b = 0.5 * ra / growth, 0.5 * rb / growth
    assert result.turnover[1] == pytest.approx(abs(0.5 - held_a) + abs(0.4 - held_b), rel=1e-12)
    assert np.all(result.turnover[2:] == 0.0)  # 0.5/0.4 then stays the same: held
