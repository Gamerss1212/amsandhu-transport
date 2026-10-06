"""Phase 2 strategy library: each rule does what its paper says, causally, within bounds."""

from __future__ import annotations

from datetime import date

import numpy as np
import pytest

from quantagents.backtest import library
from quantagents.backtest.engine import Backtester
from quantagents.backtest.strategies import DEFAULT_VARIANT, buy_and_hold, strategy_grid
from quantagents.config import AppConfig
from quantagents.market import MarketData
from quantagents.validation.leakage import RedTeamAuditor
from tests.helpers import path_market, regime_market, wavy_market

LIBRARY = ("tsmom_blend", "xs_mom", "faber", "rsi2", "vol_target")


@pytest.mark.parametrize("family", LIBRARY)
def test_every_library_strategy_passes_the_red_team(family: str, market: MarketData) -> None:
    for name, factory in strategy_grid(family, AppConfig()):
        report = RedTeamAuditor(probes=3, window=25).audit(factory, market, name=name)
        assert report.passed and report.findings == (), (name, report.findings)
        result = Backtester(0.0015).run(market, factory(market), name=name)
        assert len(result.returns) == len(market) - 261
    assert DEFAULT_VARIANT[family] == strategy_grid(family, AppConfig())[0][0]  # primary first


def test_monthly_recomputes_only_on_a_new_month() -> None:
    market = wavy_market(("AAA",), n=300)
    calls: list[date] = []

    def compute(view: object) -> dict[str, float]:
        calls.append(view.as_of)  # type: ignore[attr-defined]
        return {"AAA": 1.0}

    monthly = library.Monthly(compute)
    for t in range(250, 300):
        assert monthly(market.view_at(t)) == {"AAA": 1.0}
    assert calls[0] == market.dates[250]
    assert all(d.day <= 3 or d == calls[0] for d in calls)  # first trading day of each month
    assert len(calls) == len({(d.year, d.month) for d in market.dates[250:300]})


def test_tsmom_blend_holds_uptrends_and_scales_by_volatility() -> None:
    market = wavy_market(("UP", "DOWN"), n=400, drifts=(0.001, -0.003))
    view = market.view_at(399)
    raw = library.tsmom_blend(target_vol=None)(market)(view)
    assert raw == {"UP": 0.5}
    scaled = library.tsmom_blend(target_vol=0.001)(market)(view)
    assert 0 < scaled["UP"] < 0.5 and "DOWN" not in scaled
    calm = library.tsmom_blend(target_vol=10.0)(market)(view)
    assert calm == {"UP": 0.5}  # never levered above the equal-weight slot


def test_xs_momentum_buys_the_strongest_third() -> None:
    drifts = (0.002, 0.001, 0.0, -0.001, -0.0015, -0.002)
    market = wavy_market(("A", "B", "C", "D", "E", "F"), n=400, drifts=drifts)
    view = market.view_at(399)
    assert library.xs_momentum()(market)(view) == {"A": 0.5, "B": 0.5}
    falling = wavy_market(("A", "B", "C"), n=400, drifts=(-0.001, -0.002, -0.003))
    assert library.xs_momentum(trend_filter=True)(falling)(falling.view_at(399)) == {}
    assert library.xs_momentum(trend_filter=False)(falling)(falling.view_at(399)) == {"A": 1.0}
    short = wavy_market(("A", "B"), n=100)
    assert library.xs_momentum()(short)(short.view_at(99)) == {}


def test_faber_uses_completed_month_end_closes() -> None:
    market = wavy_market(("UP", "DOWN"), n=400, drifts=(0.001, -0.001))
    view = market.view_at(399)
    ends = library.month_end_closes(view, "UP", 10)
    assert len(ends) == 10
    last_end = max(i for i in range(399) if market.dates[i].month != market.dates[i + 1].month)
    assert ends[-1] == market.bars("UP").close[last_end]
    assert library.faber(10)(market)(view) == {"UP": 0.5}
    young = wavy_market(("UP",), n=120, drifts=(0.001,))
    assert library.faber(10)(young)(young.view_at(119)) == {}  # not 10 months of history yet


def test_rsi2_buys_a_dip_in_an_uptrend_and_sells_the_bounce() -> None:
    up = [100.0 * 1.002**k for k in range(260)]
    dip = [up[-1] * f for f in (0.98, 0.96, 0.94)]
    bounce = [dip[-1] * f for f in (1.03, 1.06)]
    market = path_market(up + dip + bounce)
    strategy = library.rsi2(10.0)(market)
    held = [strategy(market.view_at(t)) for t in range(250, len(market))]
    first_in = next(i for i, w in enumerate(held) if w) + 250
    assert first_in >= 260  # only after the dip
    assert held[first_in - 250] == {"AAA": 1.0}
    assert held[-1] == {}  # sold on the close above the 5-day average
    crash = path_market([100.0 * 0.998**k for k in range(263)])
    below = library.rsi2(10.0)(crash)
    assert all(below(crash.view_at(t)) == {} for t in range(200, 263))  # under the 200-day: never


def test_vol_target_scales_the_book() -> None:
    noisy = regime_market(n=300, vol=0.03)
    hold = library.vol_target(buy_and_hold(), 0.10)(noisy)(noisy.view_at(299))
    assert 0 < sum(hold.values()) < 0.5  # 3% a day is ~48% a year: scaled well below 1x
    calm = regime_market(n=300, vol=0.001)
    full = library.vol_target(buy_and_hold(), 0.10)(calm)(calm.view_at(299))
    assert sum(full.values()) == pytest.approx(1.0)  # capped at fully invested, no leverage

    def nothing(_: MarketData) -> object:
        return lambda view: {}

    assert library.vol_target(nothing, 0.1)(calm)(calm.view_at(299)) == {}  # type: ignore[arg-type]
    young = regime_market(n=40)
    assert library.vol_target(buy_and_hold(), 0.1)(young)(young.view_at(39)) == {}


def test_annual_volatility_helper() -> None:
    c = np.array([100.0, 101.0, 100.0, 101.0, 100.0])
    assert library._ann_vol(c, 10) != library._ann_vol(c, 10)  # nan: not enough data
    assert library._ann_vol(c, 4) > 0
    assert np.isnan(library._ann_vol(np.array([1.0, np.nan, 1.0]), 2))
