"""A43 event-driven mode: next-open fills, whole units, fees, impact, ADV cap, rejections."""

from __future__ import annotations

import math
from collections.abc import Mapping

import numpy as np
import pytest

from quantagents.backtest.engine import Backtester
from quantagents.backtest.event import (
    EventBacktester,
    EventCosts,
    FillStatus,
    _round_toward_zero,
)
from quantagents.backtest.strategies import buy_and_hold, tsmom
from quantagents.config import AppConfig
from quantagents.market import Bars, MarketData, MarketView
from tests.helpers import wavy_market, with_value

FREE = EventCosts(0.0, 0.0, 0.0, quantity_step=1e-9, max_adv_participation=1e9)
WARMUP = 260


def single(market: MarketData, symbol: str = "SYN_A") -> MarketData:
    return MarketData(market.dates, {symbol: market.bars(symbol)})


def hold(symbol: str, weight: float = 1.0) -> object:
    def strategy(_: MarketView) -> Mapping[str, float]:
        return {symbol: weight}

    return strategy


def with_volume(market: MarketData, volume: float) -> MarketData:
    bars = {
        s: Bars.from_arrays(
            open=market.bars(s).open,
            high=market.bars(s).high,
            low=market.bars(s).low,
            close=market.bars(s).close,
            volume=np.full(len(market), volume),
        )
        for s in market.symbols
    }
    return MarketData(market.dates, bars)


def test_orders_fill_at_the_next_open_never_the_signal_close(market: MarketData) -> None:
    result = EventBacktester(FREE, 10_000).run(market, tsmom(63)(market), warmup=WARMUP)
    assert result.orders
    for order in result.orders:
        t = market.index_of(order.signal_date)
        assert order.fill_date == market.dates[t + 1]
        if order.filled_qty:
            assert order.price == pytest.approx(market.bars(order.symbol).open[t + 1])


def test_buy_and_hold_matches_the_price_change_at_zero_cost(market: MarketData) -> None:
    one = single(market)
    result = EventBacktester(FREE, 10_000).run(one, buy_and_hold()(one), warmup=WARMUP)
    bars = one.bars("SYN_A")
    expected = bars.close[-1] / bars.open[WARMUP + 1]
    # cash left over when the open is below the prior close is invested on later days
    assert result.equity[-1] / 10_000 == pytest.approx(expected, rel=1e-4)
    assert len(result.equity) == len(result.dates) == len(one) - WARMUP


def test_close_to_the_vectorized_engine_at_zero_cost(market: MarketData) -> None:
    """Not identical: the event engine sizes orders from the prior close and keeps leftover cash."""
    for factory in (buy_and_hold(), tsmom(63)):
        vec = Backtester(0.0).run(market, factory(market), warmup=WARMUP)
        evt = EventBacktester(FREE, 10_000).run(market, factory(market), warmup=WARMUP)
        assert abs(evt.metrics["cagr"] - vec.metrics["cagr"]) < 0.005


def test_whole_shares_and_cash_never_negative(market: MarketData) -> None:
    costs = EventCosts.from_config(AppConfig())
    result = EventBacktester(costs, 10_000).run(market, tsmom(63)(market), warmup=WARMUP)
    for order in result.orders:
        assert order.filled_qty == round(order.filled_qty)
        assert abs(order.filled_qty) <= abs(order.requested_qty)
    cash = 10_000.0
    for order in result.orders:
        if order.filled_qty:
            cash -= order.filled_qty * order.price + order.fee
            assert cash >= -1e-6


def test_fees_slippage_and_impact_only_cost_money(market: MarketData) -> None:
    costs = EventCosts.from_config(AppConfig())
    free = EventBacktester(FREE, 10_000).run(market, tsmom(63)(market), warmup=WARMUP)
    paid = EventBacktester(costs, 10_000).run(market, tsmom(63)(market), warmup=WARMUP)
    stressed = EventBacktester(costs.doubled(), 10_000).run(
        market, tsmom(63)(market), warmup=WARMUP
    )
    assert stressed.equity[-1] < paid.equity[-1] < free.equity[-1]
    assert paid.metrics["fees_paid"] > 0
    for order in paid.orders:
        if not order.filled_qty:
            continue
        t = market.index_of(order.fill_date)
        open_ = market.bars(order.symbol).open[t]
        if order.filled_qty > 0:
            assert order.price > open_
        else:
            assert order.price < open_
        assert order.fee == pytest.approx(abs(order.filled_qty) * order.price * 10 / 1e4)
        assert order.impact_bps > 0


def test_bigger_orders_pay_more_impact() -> None:
    market = wavy_market(("AAA",), n=300)
    costs = EventCosts(0.0, 0.0, 0.8, quantity_step=1.0, max_adv_participation=1.0)
    small = EventBacktester(costs, 10_000).run(market, hold("AAA"), warmup=WARMUP)  # type: ignore[arg-type]
    big = EventBacktester(costs, 1_000_000).run(market, hold("AAA"), warmup=WARMUP)  # type: ignore[arg-type]
    assert big.orders[0].impact_bps > small.orders[0].impact_bps > 0
    # square-root law: 100x the order value gives about 10x the impact
    assert big.orders[0].impact_bps / small.orders[0].impact_bps == pytest.approx(10, rel=0.05)


def test_orders_above_one_percent_of_adv_are_partly_filled() -> None:
    market = with_volume(wavy_market(("AAA",), n=300), 5_000.0)  # ~500,000 traded a day
    costs = EventCosts(0.0, 0.0, 0.0, quantity_step=1.0)
    result = EventBacktester(costs, 10_000).run(market, hold("AAA"), warmup=WARMUP)  # type: ignore[arg-type]
    first = result.orders[0]
    bars = market.bars("AAA")
    adv = float(np.median(bars.close[WARMUP - 19 : WARMUP + 1] * 5_000.0))
    assert first.status is FillStatus.PARTIAL
    assert "1% of daily traded value" in first.reason
    assert first.filled_qty == math.floor(0.01 * adv / bars.open[WARMUP + 1])
    assert first.filled_qty < first.requested_qty
    assert result.count(FillStatus.PARTIAL) > 1  # it keeps working the rest on later days
    tiny = EventBacktester(costs, 10_000).run(with_volume(market, 50.0), hold("AAA"), warmup=WARMUP)  # type: ignore[arg-type]
    assert tiny.orders[0].status is FillStatus.REJECTED  # 1% of ADV is less than one share


def test_missing_open_rejects_the_order() -> None:
    market = wavy_market(("AAA", "BBB"), n=300)
    gap = with_value(market, "AAA", "open", WARMUP + 1, math.nan)
    result = EventBacktester(FREE, 10_000).run(gap, hold("AAA", 0.5), warmup=WARMUP)  # type: ignore[arg-type]
    first = result.orders[0]
    assert first.status is FillStatus.REJECTED
    assert first.filled_qty == 0 and math.isnan(first.price)
    assert "no opening price" in first.reason
    assert result.orders[1].fill_date == market.dates[WARMUP + 2]  # retried the next day
    assert result.orders[1].filled_qty > 0


def test_thin_history_and_tiny_sizes_are_rejected() -> None:
    market = wavy_market(("AAA",), n=300)
    no_volume = with_volume(market, 0.0)
    costs = EventCosts(0.0, 0.0, 0.0, quantity_step=1.0)
    result = EventBacktester(costs, 10_000).run(no_volume, hold("AAA"), warmup=WARMUP)  # type: ignore[arg-type]
    assert result.orders[0].status is FillStatus.REJECTED
    assert "volume history" in result.orders[0].reason
    # two half-weights with whole shares: drift asks for 1-share top-ups once cash is spent
    pair = wavy_market(("AAA", "BBB"), n=300)
    halves = EventBacktester(costs, 10_000).run(
        pair, lambda _: {"AAA": 0.5, "BBB": 0.5}, warmup=WARMUP
    )
    unfunded = [o for o in halves.orders if o.status is FillStatus.UNFUNDED]
    assert unfunded and all("no cash" in o.reason for o in unfunded)
    assert halves.metrics["unfunded"] == len(unfunded)
    assert halves.metrics["rejections"] == 0  # they are not counted as rejections
    broke = EventBacktester(costs, 50).run(market, hold("AAA"), warmup=WARMUP)  # type: ignore[arg-type]
    assert broke.orders == ()  # 50 buys less than one 100-priced share: no order at all
    assert broke.equity[-1] == 50


def test_buys_are_shrunk_to_the_cash_available() -> None:
    market = wavy_market(("AAA",), n=300)
    gap_up = with_value(market, "AAA", "open", WARMUP + 1, market.bars("AAA").close[WARMUP] * 1.05)
    gap_up = with_value(gap_up, "AAA", "high", WARMUP + 1, market.bars("AAA").close[WARMUP] * 1.06)
    costs = EventCosts(10.0, 5.0, 0.0, quantity_step=1.0, max_adv_participation=1.0)
    result = EventBacktester(costs, 10_000).run(gap_up, hold("AAA"), warmup=WARMUP)  # type: ignore[arg-type]
    first = result.orders[0]
    assert first.status is FillStatus.PARTIAL
    assert "cash" in first.reason
    assert first.filled_qty * first.price + first.fee <= 10_000


def test_strategy_only_sees_the_past(market: MarketData) -> None:
    seen: list[int] = []

    def spy(view: MarketView) -> Mapping[str, float]:
        seen.append(len(view))
        return {}

    result = EventBacktester(FREE, 10_000).run(market, spy, warmup=WARMUP)
    assert seen == list(range(WARMUP + 1, len(market)))
    assert result.orders == ()
    assert np.all(result.equity == 10_000)


@pytest.mark.parametrize(
    ("weights", "message"),
    [
        ({"NOPE": 0.1}, "unknown"),
        ({"SYN_A": float("nan")}, "non-finite"),
        ({"SYN_A": -0.1}, "short"),
        ({"SYN_A": 0.8, "SYN_B": 0.8}, "gross"),
    ],
)
def test_bad_weights_are_refused(
    market: MarketData, weights: dict[str, float], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        EventBacktester(FREE, 10_000).run(market, lambda _: weights, warmup=WARMUP)


def test_settings_are_validated() -> None:
    with pytest.raises(ValueError, match=">= 0"):
        EventCosts(fee_bps=-1)
    with pytest.raises(ValueError, match="quantity_step"):
        EventCosts(quantity_step=0)
    with pytest.raises(ValueError, match="capital"):
        EventBacktester(FREE, 0)
    with pytest.raises(ValueError, match="no days"):
        EventBacktester(FREE, 1).run(wavy_market(n=30), hold("AAA"), warmup=29)  # type: ignore[arg-type]
    cfg = AppConfig()
    costs = EventCosts.from_config(cfg)
    assert costs.fee_bps == cfg.costs.fee_bps and costs.quantity_step == cfg.risk.quantity_step
    assert costs.max_adv_participation == pytest.approx(0.01)
    assert costs.doubled().impact_coef == 2 * costs.impact_coef


def test_rounding_toward_zero() -> None:
    assert _round_toward_zero(2.9, 1.0) == 2.0
    assert _round_toward_zero(-2.9, 1.0) == -2.0
    assert _round_toward_zero(0.4, 1.0) == 0.0
    assert _round_toward_zero(0.12345, 0.001) == pytest.approx(0.123)
