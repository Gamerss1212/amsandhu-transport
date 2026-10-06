"""A48 Portfolio & Sizing Agent (Team 10, Phase 3).

Turns GO proposals into order intents:
- entries: fixed-fractional risk to an ATR stop, risk = max risk x size hint;
  before the debate layer is live, capped just below major_trade_risk_pct (spec section 14)
- holds: an open position is kept while the pooled view does not point the other way
- exits: close the whole position when the pooled view turns against it
A49 re-checks every intent and can only shrink or reject it.
"""

from __future__ import annotations

from collections.abc import Mapping

from quantagents.agents.base import Agent
from quantagents.config import AppConfig
from quantagents.schemas import (
    DecisionProposal,
    Direction,
    OrderIntent,
    OrderSide,
    TargetPortfolio,
    TargetPosition,
)
from quantagents.sizing import floor_to_step

MAJOR_CAP_FRACTION = 0.99  # "just below major size"


class PortfolioAgent(Agent):
    agent_id = "A48"
    name = "Portfolio & Sizing Agent"
    kind = "stat"
    info_subset = ("proposals", "positions", "prices", "atr")

    def construct(
        self,
        *,
        cycle_id: str,
        proposals: Mapping[str, DecisionProposal],
        positions: Mapping[str, float],
        prices: Mapping[str, float],
        atr: Mapping[str, float],
        equity: float,
        cfg: AppConfig,
        debate_available: bool,
        max_notional: Mapping[str, float] | None = None,
        risk_scale: float = 1.0,
    ) -> tuple[TargetPortfolio, list[OrderIntent]]:
        """``max_notional`` (A09 participation caps) and ``risk_scale`` (A45, 0-1) can only
        shrink new entries. Holds and exits are never affected by either."""
        if not 0.0 <= risk_scale <= 1.0:
            raise ValueError("risk_scale must be between 0 and 1")
        risk = cfg.risk
        targets: list[TargetPosition] = []
        intents: list[OrderIntent] = []
        notes: list[str] = []

        def next_id() -> str:
            return f"{cycle_id}-I{len(intents):03d}"

        held = {s for s, q in positions.items() if q != 0}
        for symbol in sorted(set(proposals) | held):
            q0 = positions.get(symbol, 0.0)
            proposal = proposals.get(symbol)
            price = prices.get(symbol)
            if q0 != 0:
                current = Direction.LONG if q0 > 0 else Direction.SHORT
                turned = proposal is not None and proposal.direction not in (
                    current,
                    Direction.FLAT,
                )
                if turned and price is not None and proposal is not None:
                    intents.append(
                        OrderIntent(
                            intent_id=next_id(),
                            decision_id=proposal.decision_id,
                            symbol=symbol,
                            side=OrderSide.SELL if q0 > 0 else OrderSide.BUY,
                            qty=abs(q0),
                            ref_price=price,
                            reason=f"exit: pooled view turned {proposal.direction.value}",
                        )
                    )
                    targets.append(TargetPosition(symbol=symbol, target_qty=0.0))
                else:
                    targets.append(TargetPosition(symbol=symbol, target_qty=q0))
                continue
            if proposal is None or not proposal.go or price is None:
                continue
            if proposal.direction is Direction.SHORT and not risk.shorting_allowed:
                notes.append(f"{symbol}: short signal skipped (shorting_allowed is false)")
                continue
            range_ = atr.get(symbol)
            if range_ is None or range_ <= 0:
                notes.append(f"{symbol}: skipped, no ATR for a stop")
                continue
            risk_pct = risk.max_risk_per_trade_pct * proposal.size_hint
            if not debate_available:
                risk_pct = min(risk_pct, MAJOR_CAP_FRACTION * risk.major_trade_risk_pct)
            stop_distance = risk.stop_atr_multiple * range_
            qty = equity * risk_pct / 100.0 / stop_distance
            qty = min(qty, equity * risk.max_position_pct / 100.0 / price)
            cap = (max_notional or {}).get(symbol)
            if cap is not None and cap / price < qty:
                qty = cap / price
                notes.append(
                    f"{symbol}: capped at {floor_to_step(qty, risk.quantity_step):g} by A09 "
                    "participation limit"
                )
            # A45's scale goes on LAST, after every cap, so it always shrinks what is sent.
            if risk_scale < 1.0:
                qty *= risk_scale
                risk_pct *= risk_scale
                notes.append(f"{symbol}: size scaled to {risk_scale:.0%} by A45 stress test")
            qty = floor_to_step(qty, risk.quantity_step)
            long = proposal.direction is Direction.LONG
            stop = price - stop_distance if long else price + stop_distance
            if qty <= 0 or stop <= 0:
                notes.append(f"{symbol}: size rounds to zero at {risk_pct:.3f}% risk")
                continue
            risk_pct = qty * stop_distance / equity * 100.0  # what is actually at risk
            intents.append(
                OrderIntent(
                    intent_id=next_id(),
                    decision_id=proposal.decision_id,
                    symbol=symbol,
                    side=OrderSide.BUY if long else OrderSide.SELL,
                    qty=qty,
                    ref_price=price,
                    stop_price=stop,
                    reason=(
                        f"entry {proposal.direction.value}: p={proposal.p_direction:.3f}, "
                        f"risk {risk_pct:.3f}% of equity, stop {risk.stop_atr_multiple:g}x ATR"
                    ),
                )
            )
            targets.append(
                TargetPosition(
                    symbol=symbol,
                    target_qty=qty if long else -qty,
                    stop_price=stop,
                    risk_pct=risk_pct,
                )
            )
        if not debate_available:
            notes.append("debate layer not live: entries capped just below major_trade_risk_pct")
        return TargetPortfolio(
            cycle_id=cycle_id, positions=tuple(targets), notes=tuple(notes)
        ), intents
