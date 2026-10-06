"""A23 Calendar & Seasonality Agent (Team 5, Phase 2). Appendix A9.

Turn-of-the-month tilt: from the last trading day of a month through the third trading
day of the next, lean slightly long. Abstains on every other day.
Uses a Monday-Friday calendar; add exchange holidays before relying on it.
Re-validate the effect yearly (spec section 64); disable it if it fails.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import ClassVar

from quantagents.agents.base import AgentContext, SignalAgent
from quantagents.schemas import AgentPrediction


def next_business_day(day: date) -> date:
    nxt = day + timedelta(days=1)
    while nxt.weekday() >= 5:
        nxt += timedelta(days=1)
    return nxt


def business_day_of_month(day: date) -> int:
    """1 for the first Monday-Friday of the month, 2 for the second, and so on."""
    count = 0
    d = day.replace(day=1)
    while d <= day:
        if d.weekday() < 5:
            count += 1
        d += timedelta(days=1)
    return count


def turn_of_month_position(day: date) -> int | None:
    """0 on the last business day of a month, 1-3 on the first three, otherwise None."""
    if day.weekday() >= 5:
        return None
    if next_business_day(day).month != day.month:
        return 0
    position = business_day_of_month(day)
    return position if position <= 3 else None


class CalendarAgent(SignalAgent):
    agent_id = "A23"
    name = "Calendar & Seasonality Agent"
    kind = "code"
    info_subset = ("calendar",)
    horizon_bars = 4

    tilt: ClassVar[float] = 0.05

    def predict(self, ctx: AgentContext) -> list[AgentPrediction]:
        position = turn_of_month_position(ctx.as_of)
        if position is None:
            return [self.abstain(ctx, s, "outside the turn-of-month window") for s in ctx.tradable]
        horizon = 4 - position if position > 0 else 4
        label = (
            "last trading day of the month"
            if position == 0
            else f"trading day {position} of the month"
        )
        return [
            self.forecast(ctx, s, 0.5 + self.tilt, f"turn-of-month tilt ({label})", horizon=horizon)
            for s in ctx.tradable
        ]
