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
