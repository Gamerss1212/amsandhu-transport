"""A49 tests. Phase 3 acceptance needs 100% branch coverage of src/quantagents/risk/."""

from __future__ import annotations

from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from quantagents.config import LIVE_APPROVAL_ENV, LIVE_APPROVAL_TOKEN, AppConfig
from quantagents.risk.governor import (
    ENGINE_VERSION,
    LEVEL_MULTIPLIER,
    RiskGovernor,
    RiskInputs,
    degradation_level,
)
from quantagents.schemas import DegradationLevel, OrderSide
from tests.helpers import intent

PRICES = {"AAA": 100.0, "BBB": 50.0}


def inputs(**changes: Any) -> RiskInputs:
    base: dict[str, Any] = {"equity": 10_000.0, "cash": 10_000.0, "positions": {}, "prices": PRICES}
    base.update(changes)
    return RiskInputs(**base)


def level(cfg: AppConfig, **changes: Any) -> DegradationLevel:
    return degradation_level(inputs(**changes), cfg)[0]


def test_degradation_ladder(cfg: AppConfig) -> None:
    assert degradation_level(inputs(), cfg) == (DegradationLevel.NORMAL, ("all clear",))
    for change in (
        {"kill_switch_engaged": True},
        {"reconciliation_ok": False},
        {"data_health": 40.0},
        {"daily_loss_pct": 2.0},
        {"weekly_loss_pct": 4.0},
        {"drawdown_pct": 15.0},
    ):
        assert level(cfg, **change) is DegradationLevel.HALTED, change
    for change in ({"data_health": 70.0}, {"quorum": 0.5}, {"drawdown_pct": 11.25}):
        assert level(cfg, **change) is DegradationLevel.DEFENSIVE, change
    for change in (
        {"transition_alert": True},
        {"novelty_high": True},
        {"drawdown_pct": 7.5},
        {"quorum": 0.8},
    ):
        assert level(cfg, **change) is DegradationLevel.REDUCED, change


def test_clean_entry_is_approved(cfg: AppConfig) -> None:
    verdict = RiskGovernor(cfg).review("C1", [intent(qty=6, stop=96.0)], inputs())
    result = verdict.results[0]
    assert result.passed and result.approved_qty == 6 and result.reason == "approved"
    assert result.size_adjustment == 1.0 and not result.risk_reducing
    assert result.engine_version == ENGINE_VERSION and result.risk_check_id == "C1-R000"
    assert verdict.level is DegradationLevel.NORMAL and not verdict.kill_switch_engaged


def test_oversized_entry_is_shrunk_never_grown(cfg: AppConfig) -> None:
    result = RiskGovernor(cfg).review("C1", [intent(qty=50, stop=96.0)], inputs()).results[0]
    assert result.approved_qty == 12  # 0.5% of 10,000 = 50 risk / 4.00 stop distance = 12.5
    assert result.reason.startswith("approved, resized by") and "risk_per_trade" in result.reason
    assert result.size_adjustment == pytest.approx(12 / 50)
    shrunk = {c.name for c in result.checks if not c.passed}
    assert {"risk_per_trade", "position_cap", "order_notional"} <= shrunk


def test_reduced_level_halves_the_risk_budget(cfg: AppConfig) -> None:
    result = (
        RiskGovernor(cfg).review("C1", [intent(qty=10, stop=96.0)], inputs(quorum=0.8)).results[0]
    )
    assert result.approved_qty == 6 and result.degradation_level is DegradationLevel.REDUCED
    assert LEVEL_MULTIPLIER[DegradationLevel.REDUCED] == 0.5


def test_halt_blocks_entries_but_always_allows_exits(cfg: AppConfig) -> None:
    exit_order = intent("AAA", OrderSide.SELL, 10, stop=None, intent_id="I-exit")
    entry = intent("BBB", OrderSide.BUY, 5, ref=50.0, stop=48.0, intent_id="I-entry")
    verdict = RiskGovernor(cfg).review(
        "C1", [entry, exit_order], inputs(positions={"AAA": 10.0}, kill_switch_engaged=True)
    )
    assert verdict.level is DegradationLevel.HALTED and verdict.kill_switch_engaged
    entry_result, exit_result = verdict.results
    assert exit_result.risk_reducing and exit_result.approved_qty == 10
    assert exit_result.reason == "risk-reducing order: always allowed"
    assert entry_result.approved_qty == 0 and not entry_result.passed
    assert "kill_switch" in entry_result.reason and "degradation_level" in entry_result.reason


@pytest.mark.parametrize(
    ("order", "state", "failed"),
    [
        (intent("CCC", stop=95.0), {}, "price_known"),
        (intent(ref=110.0, stop=105.0), {}, "price_band"),
        (intent(stop=101.0), {}, "stop_on_correct_side"),
        (intent(stop=None), {}, "stop_on_correct_side"),
        (intent(side=OrderSide.SELL, qty=10, stop=105.0), {"positions": {"AAA": 5.0}}, "no_flip"),
        (intent(side=OrderSide.SELL, qty=5, stop=105.0), {}, "shorting_allowed"),
        (intent(stop=96.0), {"orders_last_minute": 10}, "order_rate"),
        (intent(stop=96.0), {"positions": {"ZZZ": 5.0}}, "book_valued"),
    ],
)
def test_each_hard_check_rejects(
    cfg: AppConfig, order: Any, state: dict[str, Any], failed: str
) -> None:
    result = RiskGovernor(cfg).review("C1", [order], inputs(**state)).results[0]
    assert result.approved_qty == 0 and failed in result.reason, result.reason


def test_short_entries_when_allowed(cfg: AppConfig) -> None:
    shorting = cfg.model_copy(
        update={"risk": cfg.risk.model_copy(update={"shorting_allowed": True})}
    )
    good = (
        RiskGovernor(shorting)
        .review("C1", [intent(side=OrderSide.SELL, qty=5, stop=104.0)], inputs())
        .results[0]
    )
    assert good.approved_qty == 5
    wrong_stop = (
        RiskGovernor(shorting)
        .review("C1", [intent(side=OrderSide.SELL, qty=5, stop=99.0)], inputs())
        .results[0]
    )
    assert "stop_on_correct_side" in wrong_stop.reason


def test_size_can_round_to_zero(cfg: AppConfig) -> None:
    result = (
        RiskGovernor(cfg)
        .review("C1", [intent(qty=3, stop=96.0)], inputs(equity=100.0, cash=100.0))
        .results[0]
    )
    assert result.approved_qty == 0 and "rounds to zero" in result.reason


def test_orders_in_one_cycle_share_the_limits(cfg: AppConfig) -> None:
    first = intent("AAA", qty=6, stop=96.0, intent_id="I1")
    second = intent("BBB", qty=10, ref=50.0, stop=48.0, intent_id="I2")
    verdict = RiskGovernor(cfg).review("C1", [first, second], inputs(cash=1_000.0))
    assert verdict.results[0].approved_qty == 6
    assert verdict.results[1].approved_qty == 7 and "cash_available" in verdict.results[1].reason


def test_live_mode_needs_the_token_at_order_time(
    cfg: AppConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert RiskGovernor(cfg).mode_allows_orders()
    monkeypatch.setenv(LIVE_APPROVAL_ENV, LIVE_APPROVAL_TOKEN)
    live = AppConfig.model_validate(
        {"system": {"execution_mode": "live", "autonomy_level": 3, "live_trading_approved": True}}
    )
    governor = RiskGovernor(live)
    assert governor.mode_allows_orders()
    monkeypatch.delenv(LIVE_APPROVAL_ENV)
    assert not governor.mode_allows_orders()
    result = governor.review("C1", [intent(qty=1, stop=96.0)], inputs()).results[0]
    assert "execution_mode" in result.reason


@settings(max_examples=300, deadline=None)
@given(
    equity=st.floats(min_value=1_000, max_value=1_000_000),
    held=st.floats(min_value=0, max_value=500),
    price=st.floats(min_value=1, max_value=1_000),
    qty=st.floats(min_value=0.5, max_value=5_000),
    stop_fraction=st.floats(min_value=0.001, max_value=0.5),
    buy=st.booleans(),
    health=st.floats(min_value=0, max_value=100),
    quorum=st.floats(min_value=0, max_value=1),
    drawdown=st.floats(min_value=0, max_value=20),
    killed=st.booleans(),
)
def test_governor_invariants(
    equity: float,
    held: float,
    price: float,
    qty: float,
    stop_fraction: float,
    buy: bool,
    health: float,
    quorum: float,
    drawdown: float,
    killed: bool,
) -> None:
    cfg = AppConfig()
    held = float(int(held))
    side = OrderSide.BUY if buy else OrderSide.SELL
    stop = price * (1 - stop_fraction) if buy else price * (1 + stop_fraction)
    order = intent("AAA", side, qty, ref=price, stop=stop)
    state = inputs(
        equity=equity,
        cash=equity - held * price,
        positions={"AAA": held} if held else {},
        prices={"AAA": price},
        data_health=health,
        quorum=quorum,
        drawdown_pct=drawdown,
        kill_switch_engaged=killed,
    )
    verdict = RiskGovernor(cfg).review("C1", [order], state)
    result = verdict.results[0]
    assert result.approved_qty <= qty + 1e-9  # never grows an order
    if not buy and held and qty <= held + 1e-9:
        assert result.risk_reducing and result.approved_qty == qty  # exits always allowed
        return
    if result.approved_qty > 0:
        assert verdict.level in (DegradationLevel.NORMAL, DegradationLevel.REDUCED)
        multiplier = LEVEL_MULTIPLIER[verdict.level]
        risk = cfg.risk
        assert (
            result.approved_qty * abs(price - stop)
            <= equity * risk.max_risk_per_trade_pct / 100 * multiplier + 1e-6
        )
        assert (held + result.approved_qty) * price <= equity * risk.max_position_pct / 100 + 1e-6
        assert result.approved_qty * price <= equity * risk.max_order_notional_pct / 100 + 1e-6
        assert buy  # shorting is off by default
