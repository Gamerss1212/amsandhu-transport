"""A45 Stress & Simulation Agent."""

from __future__ import annotations

import numpy as np
import pytest

from quantagents.agents.a08_volatility import VolatilityAgent
from quantagents.agents.a09_liquidity import LiquidityAgent
from quantagents.agents.a45_stress import (
    StressAgent,
    bootstrap_paths,
    max_drawdown,
    seed_from,
    stress_returns,
)
from quantagents.config import AppConfig
from quantagents.market import MarketData
from quantagents.schemas import ContextReport, StressReport
from tests.helpers import regime_market

MARKET = regime_market(n=400, vol=0.012, seed=21)
PRICES = {s: float(MARKET.bars(s).close[-1]) for s in MARKET.symbols}
VIEW = MARKET.view(MARKET.dates[-1])
CONTEXT = VolatilityAgent().forecast(VIEW, "S", MARKET.symbols)


def shares(symbol: str, weight: float, equity: float = 10_000.0) -> float:
    return round(weight * equity / PRICES[symbol], 6)


def assess(
    before: dict[str, float],
    after: dict[str, float],
    *,
    stops: dict[str, float] | None = None,
    cfg: AppConfig | None = None,
    drawdown: float = 0.0,
    market: MarketData = MARKET,
    context: ContextReport = CONTEXT,
    cycle_id: str = "C1",
) -> StressReport:
    return StressAgent().assess(
        cycle_id=cycle_id,
        view=market.view(market.dates[-1]),
        before=before,
        after=after,
        prices={s: float(market.bars(s).close[-1]) for s in market.symbols},
        stops=stops or {},
        equity=10_000.0,
        drawdown_pct=drawdown,
        context=context,
        cfg=cfg or AppConfig(),
    )


def scenario(report: StressReport, name: str) -> float:
    return next(s.loss_pct for s in report.scenarios if s.name == name)


def test_empty_book_is_not_stressed() -> None:
    report = assess({}, {})
    assert report.entry_scale == 1.0 and report.scenarios == () and report.notes


def test_scenarios_for_one_position() -> None:
    qty = shares("AAA", 0.20)
    stop = PRICES["AAA"] * 0.95
    report = assess({}, {"AAA": qty}, stops={"AAA": stop})
    assert report.gross_exposure_pct == pytest.approx(20.0, rel=1e-4)
    assert scenario(report, "gap_down_10") == pytest.approx(2.0, rel=1e-4)
    assert scenario(report, "stops_gap_through") == pytest.approx(
        qty * (PRICES["AAA"] - stop) * 1.5 / 100.0, rel=1e-6
    )
    sigma = CONTEXT.vol("AAA")
    assert sigma is not None
    assert scenario(report, "correlation_one_3sigma") == pytest.approx(
        20.0 * 3 * sigma.sigma_daily, rel=1e-4
    )
    assert scenario(report, "historical_worst_day") > 0
    assert (
        scenario(report, "historical_worst_week") >= scenario(report, "historical_worst_day") * 0.5
    )
    assert scenario(report, "liquidity_crunch") == pytest.approx(0.2 * 5 * 5 / 1e4 * 100)
    assert (
        0 < report.var_99_1d_pct <= report.es_99_1d_pct <= scenario(report, "historical_worst_day")
    )
    assert report.mc_es_99_20d_pct > report.es_99_1d_pct
    assert report.entry_scale == 1.0  # well inside the 2% daily budget
    no_stop = assess({}, {"AAA": qty})
    assert scenario(no_stop, "stops_gap_through") == pytest.approx(
        scenario(no_stop, "correlation_one_3sigma")
    )


def test_entries_are_scaled_to_the_budget() -> None:
    before = {"AAA": shares("AAA", 0.10)}
    after = {**before, "BBB": shares("BBB", 0.90), "CCC": shares("CCC", 0.90)}
    report = assess(before, after)
    assert report.tail_loss_before_pct < report.budget_pct < report.tail_loss_pct
    assert 0 < report.entry_scale < 1 and "scaled" in report.notes[0]
    # Scaling the new entries by that factor keeps the tail inside the budget.
    s = report.entry_scale
    scaled = {**before, "BBB": after["BBB"] * s, "CCC": after["CCC"] * s}
    assert assess(before, scaled).tail_loss_pct <= report.budget_pct * 1.02


def test_full_book_blocks_new_entries_but_never_exits() -> None:
    heavy = {s: shares(s, 0.95) for s in ("AAA", "BBB", "CCC")}
    more = {**heavy, "DDD": shares("DDD", 0.05)}
    report = assess(heavy, more)
    assert report.tail_loss_before_pct >= report.budget_pct and report.entry_scale == 0.0
    trimmed = {**heavy, "AAA": heavy["AAA"] / 2}
    assert assess(heavy, trimmed).entry_scale == 1.0  # shrinking is never blocked


def test_ruin_risk_halves_entries() -> None:
    cfg = AppConfig.model_validate(
        {"risk": {"max_daily_loss_pct": 1.0, "max_weekly_loss_pct": 1.0, "max_drawdown_pct": 1.0}}
    )
    report = assess({}, {"AAA": shares("AAA", 0.15)}, cfg=cfg, drawdown=0.9)
    assert report.p_ruin_20d >= 0.05 and report.entry_scale <= 0.5
    assert any("drawdown limit" in n for n in report.notes)


def test_short_history_and_missing_volatility() -> None:
    young = regime_market(n=40, seed=22)
    empty = ContextReport(snapshot_id="S", agent_id="A08", vol_forecasts=())
    qty = round(0.2 * 10_000 / float(young.bars("AAA").close[-1]), 6)
    report = assess({}, {"AAA": qty}, market=young, context=empty)
    assert any("historical scenarios skipped" in n for n in report.notes)
    assert any("sigma from history" in n for n in report.notes)
    assert report.p_ruin_20d == 0.0 and report.mc_es_99_20d_pct == 0.0
    assert {s.name for s in report.scenarios} == {
        "gap_down_10",
        "stops_gap_through",
        "correlation_one_3sigma",
        "liquidity_crunch",
    }


def test_monte_carlo_is_deterministic_per_cycle() -> None:
    book = {"AAA": shares("AAA", 0.3), "BBB": shares("BBB", 0.3)}
    assert assess({}, book) == assess({}, book)
    assert seed_from("C1") == seed_from("C1") != seed_from("C2")


def test_bootstrap_paths_and_drawdown() -> None:
    rng = np.random.default_rng(0)
    idx = bootstrap_paths(50, 200, 20, 5.0, rng)
    assert idx.shape == (200, 20) and int(np.min(idx)) >= 0 and int(np.max(idx)) < 50
    runs = np.mean(np.diff(idx, axis=1) == 1)
    assert 0.7 < runs < 0.9  # blocks continue with probability 1 - 1/5
    with pytest.raises(ValueError):
        bootstrap_paths(0, 1, 1, 5.0, rng)
    dd = max_drawdown(np.array([[0.1, -0.5, 0.2], [0.01, 0.01, 0.01]]))
    assert dd[0] == pytest.approx(0.5) and dd[1] == 0.0


def test_stress_returns_for_promotion_reviews() -> None:
    steady = stress_returns(np.full(300, 0.001), ruin_drawdown=0.15)
    assert steady.p_losing_year == 0.0 and steady.p95_max_drawdown == 0.0 and steady.p_ruin == 0.0
    rng = np.random.default_rng(3)
    risky = stress_returns(rng.normal(0.0, 0.03, 500), ruin_drawdown=0.15, paths=500)
    assert 0.3 < risky.p_losing_year < 0.8 and risky.p_ruin > 0.5
    assert risky.worst_1pct_return <= risky.worst_5pct_return <= risky.median_return
    with pytest.raises(ValueError, match="20"):
        stress_returns([0.01] * 5, ruin_drawdown=0.15)


def test_untradable_holdings_are_priced_at_the_worst_cost() -> None:
    unknown = LiquidityAgent().unknown("AAA", 2_000.0, "no traded value", 5.0)
    assert unknown.tradability == 0.0 and unknown.est_cost_bps == 20.0 and unknown.amihud is None
    context = CONTEXT.model_copy(update={"liquidity": (unknown,)})
    report = assess({}, {"AAA": shares("AAA", 0.20)}, context=context)
    # 20% of equity x 5 (crunch multiple) x 20 bps (4x the 5 bps assumption) = 0.20%
    assert scenario(report, "liquidity_crunch") == pytest.approx(0.20, rel=1e-4)
