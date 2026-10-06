"""A12 Cross-Sectional Momentum Agent (Team 3, Phase 2). Appendix A2.

Ranks the universe by volatility-adjusted 12-1 momentum. Top third leans long, bottom
third leans short (A48 only shorts if config allows), middle abstains.
Crash filter: when the average 12-1 momentum is negative, the tilt is halved.
"""

from __future__ import annotations

from typing import ClassVar

from quantagents.agents.base import AgentContext, SignalAgent
from quantagents.schemas import AgentPrediction


class CrossSectionalMomentumAgent(SignalAgent):
    agent_id = "A12"
    name = "Cross-Sectional Momentum Agent"
    kind = "stat"
    info_subset = ("ohlcv_panel", "vol_forecast")
    horizon_bars = 20

    tilt: ClassVar[float] = 0.08
    min_assets: ClassVar[int] = 3

    def predict(self, ctx: AgentContext) -> list[AgentPrediction]:
        scores: dict[str, float] = {}
        raw: dict[str, float] = {}
        for symbol in ctx.tradable:
            f = ctx.features.get(symbol)
            vol = ctx.context.vol(symbol)
            if vol is not None and "mom_12_1" in f:
                raw[symbol] = f["mom_12_1"]
                scores[symbol] = f["mom_12_1"] / vol.sigma_annual
        if len(scores) < self.min_assets:
            return [
                self.abstain(ctx, s, f"needs at least {self.min_assets} ranked assets")
                for s in ctx.tradable
            ]
        ranked = sorted(scores, key=lambda s: (scores[s], s))
        size = max(1, len(ranked) // 3)
        bottom, top = set(ranked[:size]), set(ranked[-size:])
        crash = sum(raw.values()) / len(raw) < 0
        tilt = self.tilt * (0.5 if crash else 1.0)
        note = " (crash filter on)" if crash else ""
        out: list[AgentPrediction] = []
        for symbol in ctx.tradable:
            if symbol not in scores:
                out.append(self.abstain(ctx, symbol, "no 12-1 momentum yet"))
            elif symbol in top:
                out.append(
                    self.forecast(ctx, symbol, 0.5 + tilt, f"top third by 12-1 momentum{note}")
                )
            elif symbol in bottom:
                out.append(
                    self.forecast(ctx, symbol, 0.5 - tilt, f"bottom third by 12-1 momentum{note}")
                )
            else:
                out.append(self.abstain(ctx, symbol, "middle third"))
        return out
