"""A49 Risk & Compliance Governor: deterministic code with absolute authority (spec section 48).

Rules, in order:
1. Risk-reducing orders (they shrink an existing position) are always allowed.
2. Opening orders must pass every hard check, or they are rejected.
3. Sizing checks can only shrink an order, never grow it.
Changes to this file need a human-reviewed commit and 100% branch coverage (Phase 3).
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from quantagents.config import AppConfig, ExecutionMode, live_approval_present
from quantagents.schemas import (
    DegradationLevel,
    LimitCheck,
    OrderIntent,
    OrderSide,
    RiskCheckResult,
    RiskVerdict,
)
from quantagents.sizing import floor_to_step

ENGINE_VERSION = "a49-1.0"

LEVEL_MULTIPLIER: dict[DegradationLevel, float] = {
    DegradationLevel.NORMAL: 1.0,
    DegradationLevel.REDUCED: 0.5,
    DegradationLevel.DEFENSIVE: 0.0,
    DegradationLevel.HALTED: 0.0,
}


@dataclass(frozen=True)
class RiskInputs:
    """Everything A49 looks at. Loss figures are percents of equity (positive = loss)."""

    equity: float
    cash: float
    positions: Mapping[str, float] = field(default_factory=dict)
    prices: Mapping[str, float] = field(default_factory=dict)
    data_health: float = 100.0
    quorum: float = 1.0
    kill_switch_engaged: bool = False
    reconciliation_ok: bool = True
    daily_loss_pct: float = 0.0
    weekly_loss_pct: float = 0.0
    drawdown_pct: float = 0.0
    transition_alert: bool = False
    novelty_high: bool = False
    orders_last_minute: int = 0


def _fired(rules: Sequence[tuple[bool, str]]) -> tuple[str, ...]:
    return tuple(message for hit, message in rules if hit)


def degradation_level(
    inputs: RiskInputs, cfg: AppConfig
) -> tuple[DegradationLevel, tuple[str, ...]]:
    """The degradation ladder (spec section 18). Only a human can resume from HALTED."""
    r = cfg.risk
    used = inputs.drawdown_pct / r.max_drawdown_pct
    halted = _fired(
        [
            (inputs.kill_switch_engaged, "kill switch engaged"),
            (not inputs.reconciliation_ok, "reconciliation break"),
            (
                inputs.data_health < r.data_health_halt,
                f"data health {inputs.data_health:.0f} below {r.data_health_halt:.0f}",
            ),
            (inputs.daily_loss_pct >= r.max_daily_loss_pct, "daily loss limit hit"),
            (inputs.weekly_loss_pct >= r.max_weekly_loss_pct, "weekly loss limit hit"),
            (inputs.drawdown_pct >= r.max_drawdown_pct, "maximum drawdown hit"),
        ]
    )
    if halted:
        return DegradationLevel.HALTED, halted
    defensive = _fired(
        [
            (
                inputs.data_health < r.data_health_defensive,
                f"data health {inputs.data_health:.0f} below {r.data_health_defensive:.0f}",
            ),
            (inputs.quorum < r.quorum_pct, f"quorum {inputs.quorum:.0%} below {r.quorum_pct:.0%}"),
            (used >= r.drawdown_defensive_frac, f"{used:.0%} of the drawdown limit used"),
        ]
    )
    if defensive:
        return DegradationLevel.DEFENSIVE, defensive
    reduced = _fired(
        [
            (inputs.transition_alert, "regime transition alert"),
            (inputs.novelty_high, "high novelty"),
            (used >= r.drawdown_reduced_frac, f"{used:.0%} of the drawdown limit used"),
            (
                inputs.quorum < r.quorum_reduced_pct,
                f"quorum {inputs.quorum:.0%} below {r.quorum_reduced_pct:.0%}",
            ),
        ]
    )
    if reduced:
        return DegradationLevel.REDUCED, reduced
    return DegradationLevel.NORMAL, ("all clear",)


@dataclass
class _Book:
    """Running view of the book while orders in one cycle are approved."""

    positions: dict[str, float]
    gross: float
    cash: float
    approved_orders: int


class RiskGovernor:
    agent_id = "A49"
    name = "Risk & Compliance Governor"
    kind = "code"

    def __init__(self, cfg: AppConfig) -> None:
        self.cfg = cfg

    def mode_allows_orders(self) -> bool:
        """Defense in depth: live orders also need the approval token at order time."""
        system = self.cfg.system
        if system.execution_mode is not ExecutionMode.LIVE:
            return True
        return system.live_trading_approved and live_approval_present()

    def review(
        self, cycle_id: str, intents: Sequence[OrderIntent], inputs: RiskInputs
    ) -> RiskVerdict:
        level, level_reasons = degradation_level(inputs, self.cfg)
        gross = sum(
            abs(q) * inputs.prices.get(s, math.inf) for s, q in inputs.positions.items() if q
        )
        book = _Book(dict(inputs.positions), gross, inputs.cash, inputs.orders_last_minute)
        order = sorted(range(len(intents)), key=lambda i: (not self._reduces(intents[i], book), i))
        results: dict[int, RiskCheckResult] = {}
        for i in order:
            result = self._review_one(cycle_id, i, intents[i], inputs, level, book)
            results[i] = result
            if result.approved_qty > 0:
                self._apply(book, intents[i], result.approved_qty, inputs.prices)
        return RiskVerdict(
            cycle_id=cycle_id,
            level=level,
            level_reasons=level_reasons,
            results=tuple(results[i] for i in range(len(intents))),
            kill_switch_engaged=inputs.kill_switch_engaged,
        )

    @staticmethod
    def _signed(intent: OrderIntent) -> float:
        return intent.qty if intent.side is OrderSide.BUY else -intent.qty

    def _reduces(self, intent: OrderIntent, book: _Book) -> bool:
        q0 = book.positions.get(intent.symbol, 0.0)
        return q0 * self._signed(intent) < 0 and intent.qty <= abs(q0) + 1e-9

    @staticmethod
    def _apply(book: _Book, intent: OrderIntent, qty: float, prices: Mapping[str, float]) -> None:
        price = prices.get(intent.symbol, intent.ref_price)
        signed = qty if intent.side is OrderSide.BUY else -qty
        q0 = book.positions.get(intent.symbol, 0.0)
        book.gross += (abs(q0 + signed) - abs(q0)) * price
        book.positions[intent.symbol] = q0 + signed
        book.cash -= signed * price
        book.approved_orders += 1

    def _result(
        self,
        cycle_id: str,
        index: int,
        intent: OrderIntent,
        level: DegradationLevel,
        *,
        approved: float,
        reducing: bool,
        checks: Sequence[LimitCheck],
        reason: str,
    ) -> RiskCheckResult:
        return RiskCheckResult(
            risk_check_id=f"{cycle_id}-R{index:03d}",
            intent_id=intent.intent_id,
            decision_id=intent.decision_id,
            symbol=intent.symbol,
            side=intent.side,
            requested_qty=intent.qty,
            approved_qty=approved,
            passed=approved > 0,
            risk_reducing=reducing,
            checks=tuple(checks),
            size_adjustment=min(1.0, approved / intent.qty),
            degradation_level=level,
            reason=reason,
            engine_version=ENGINE_VERSION,
        )

    def _review_one(
        self,
        cycle_id: str,
        index: int,
        intent: OrderIntent,
        inputs: RiskInputs,
        level: DegradationLevel,
        book: _Book,
    ) -> RiskCheckResult:
        if self._reduces(intent, book):
            check = LimitCheck(name="risk_reducing", passed=True, detail="shrinks an open position")
            return self._result(
                cycle_id,
                index,
                intent,
                level,
                approved=intent.qty,
                reducing=True,
                checks=[check],
                reason="risk-reducing order: always allowed",
            )
        r = self.cfg.risk
        q0 = book.positions.get(intent.symbol, 0.0)
        signed = self._signed(intent)
        price = inputs.prices.get(intent.symbol, math.nan)
        price_ok = math.isfinite(price) and price > 0
        deviation = abs(intent.ref_price / price - 1.0) * 100.0 if price_ok else math.inf
        stop = intent.stop_price
        stop_ok = stop is not None and (
            stop < intent.ref_price if intent.side is OrderSide.BUY else stop > intent.ref_price
        )
        hard = [
            LimitCheck(name="kill_switch", passed=not inputs.kill_switch_engaged),
            LimitCheck(
                name="degradation_level", passed=LEVEL_MULTIPLIER[level] > 0, detail=level.value
            ),
            LimitCheck(
                name="execution_mode",
                passed=self.mode_allows_orders(),
                detail=self.cfg.system.execution_mode.value,
            ),
            LimitCheck(name="price_known", passed=price_ok),
            LimitCheck(
                name="price_band",
                passed=deviation <= r.price_band_pct,
                limit=r.price_band_pct,
                value=deviation if price_ok else None,
            ),
            LimitCheck(
                name="no_flip",
                passed=q0 * signed >= 0,
                detail="close first, then open the other side",
            ),
            LimitCheck(name="shorting_allowed", passed=r.shorting_allowed or q0 + signed >= 0),
            LimitCheck(name="stop_on_correct_side", passed=stop_ok),
            LimitCheck(
                name="order_rate",
                passed=book.approved_orders < r.max_orders_per_minute,
                limit=float(r.max_orders_per_minute),
                value=float(book.approved_orders),
            ),
            LimitCheck(
                name="book_valued",
                passed=math.isfinite(book.gross),
                detail="every open position needs a price",
            ),
        ]
        failed = [c.name for c in hard if not c.passed]
        if failed or stop is None:
            return self._result(
                cycle_id,
                index,
                intent,
                level,
                approved=0.0,
                reducing=False,
                checks=hard,
                reason=f"rejected: {', '.join(failed)}",
            )
        equity = inputs.equity
        multiplier = LEVEL_MULTIPLIER[level]
        stop_distance = abs(intent.ref_price - stop)
        buys_cash = intent.side is OrderSide.BUY and not r.leverage_allowed
        cash_limit = (
            book.cash / (price * (1.0 + self.cfg.costs.one_way_cost)) if buys_cash else math.inf
        )
        caps = [
            (
                "risk_per_trade",
                equity * r.max_risk_per_trade_pct / 100.0 * multiplier / stop_distance,
            ),
            ("position_cap", equity * r.max_position_pct / 100.0 / price - abs(q0)),
            ("gross_exposure", (equity * r.max_gross_exposure_pct / 100.0 - book.gross) / price),
            ("order_notional", equity * r.max_order_notional_pct / 100.0 / price),
            ("cash_available", cash_limit),
        ]
        sizing = [
            LimitCheck(
                name=name,
                passed=intent.qty <= cap + 1e-9,
                limit=cap if math.isfinite(cap) else None,
                value=intent.qty,
                detail="" if intent.qty <= cap + 1e-9 else "order shrunk to fit",
            )
            for name, cap in caps
        ]
        approved = floor_to_step(min(intent.qty, *(cap for _, cap in caps)), r.quantity_step)
        shrunk = [c.name for c in sizing if not c.passed]
        if approved <= 0:
            reason = f"rejected: size rounds to zero ({', '.join(shrunk)})"
        elif shrunk:
            reason = f"approved, resized by {', '.join(shrunk)}"
        else:
            reason = "approved"
        return self._result(
            cycle_id,
            index,
            intent,
            level,
            approved=approved,
            reducing=False,
            checks=[*hard, *sizing],
            reason=reason,
        )
