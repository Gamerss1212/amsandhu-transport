"""Agent base classes and the shared code contract (spec section 10).

Rules every agent follows:
- ``predict``/``run`` is a pure function of its inputs (same inputs, same outputs).
- No network calls, no file access, no reading of other agents' outputs before sealing.
- Outputs are schema-validated messages from ``quantagents.schemas``.
"""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from statistics import NormalDist
from typing import ClassVar

from quantagents.config import AppConfig
from quantagents.market import MarketView
from quantagents.schemas import AgentPrediction, ContextReport, Direction, FeatureFrame, team_of

_NORMAL = NormalDist()
P_LIMIT = 0.02  # no single agent may claim more than 98% certainty


@dataclass(frozen=True)
class AgentContext:
    """Everything a signal agent may read in one cycle. Built once, shared read-only."""

    cycle_id: str
    snapshot_id: str
    view: MarketView
    cfg: AppConfig
    features: FeatureFrame
    context: ContextReport
    tradable: tuple[str, ...]

    @property
    def as_of(self) -> date:
        return self.view.as_of


class Agent:
    """Base for every agent. Subclasses set the class attributes below."""

    agent_id: ClassVar[str]
    name: ClassVar[str]
    kind: ClassVar[str]
    version: ClassVar[str] = "1.0"
    info_subset: ClassVar[tuple[str, ...]] = ()

    @property
    def team(self) -> int:
        return team_of(self.agent_id)


class SignalAgent(Agent, ABC):
    """A Team 3-7 agent that seals one prediction per tradable symbol each cycle."""

    horizon_bars: ClassVar[int]

    @abstractmethod
    def predict(self, ctx: AgentContext) -> list[AgentPrediction]:
        """Return exactly one prediction (or abstention) per symbol in ``ctx.tradable``."""

    def abstain(self, ctx: AgentContext, symbol: str, reason: str) -> AgentPrediction:
        return AgentPrediction(
            agent_id=self.agent_id,
            team=self.team,
            model_version=self.version,
            cycle_id=ctx.cycle_id,
            snapshot_id=ctx.snapshot_id,
            symbol=symbol,
            horizon_bars=self.horizon_bars,
            abstain=True,
            direction=Direction.FLAT,
            p_up=0.5,
            confidence=0.0,
            reasoning_summary=reason[:500],
            info_subset=self.info_subset,
        )

    def forecast(
        self,
        ctx: AgentContext,
        symbol: str,
        p_up: float,
        reason: str,
        horizon: int | None = None,
    ) -> AgentPrediction:
        """Build a prediction. Expected return is implied from p and A08's volatility:
        mu = sigma * sqrt(h) * inverse_normal(p) (a normal approximation, computed by code)."""
        p = min(max(p_up, P_LIMIT), 1.0 - P_LIMIT)
        if math.isclose(p, 0.5):
            return self.abstain(ctx, symbol, f"{reason} (no lean)")
        h = horizon if horizon is not None else self.horizon_bars
        vol = ctx.context.vol(symbol)
        exp_vol = vol.sigma_daily * math.sqrt(h) if vol is not None else 0.0
        return AgentPrediction(
            agent_id=self.agent_id,
            team=self.team,
            model_version=self.version,
            cycle_id=ctx.cycle_id,
            snapshot_id=ctx.snapshot_id,
            symbol=symbol,
            horizon_bars=h,
            direction=Direction.LONG if p > 0.5 else Direction.SHORT,
            p_up=p,
            confidence=min(1.0, abs(p - 0.5) * 2.0),
            exp_return=exp_vol * _NORMAL.inv_cdf(p),
            exp_vol=exp_vol,
            reasoning_summary=reason[:500],
            info_subset=self.info_subset,
        )
