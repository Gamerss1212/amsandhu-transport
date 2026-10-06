"""A11 Time-Series Trend Agent (Team 3, Phase 2). Appendix A1.

Blend of three trend views, each scaled to [-1, 1]:
- TSMOM: volatility-scaled 1-, 3- and 12-month returns (tanh of a z-score), weight 0.5
- moving averages: 50-day vs 200-day, weight 0.25
- Donchian: position inside the 55-day channel, weight 0.25
p_up = 0.5 + 0.12 * score, so this agent alone never claims more than 62%.
"""

from __future__ import annotations

import math
from typing import ClassVar

from quantagents.agents.base import AgentContext, SignalAgent
from quantagents.schemas import AgentPrediction

NEEDED = ("mom_21", "mom_63", "mom_252", "sma_50", "sma_200", "channel_55")


class TrendAgent(SignalAgent):
    agent_id = "A11"
    name = "Time-Series Trend Agent"
    kind = "stat"
    info_subset = ("ohlcv", "vol_forecast")
    horizon_bars = 20

    max_tilt: ClassVar[float] = 0.12
    min_score: ClassVar[float] = 0.10

    def predict(self, ctx: AgentContext) -> list[AgentPrediction]:
        out: list[AgentPrediction] = []
        for symbol in ctx.tradable:
            f = ctx.features.get(symbol)
            vol = ctx.context.vol(symbol)
            if vol is None or any(k not in f for k in NEEDED):
                out.append(self.abstain(ctx, symbol, "insufficient history for trend"))
                continue
            sd = vol.sigma_daily
            tsmom = sum(math.tanh(f[f"mom_{k}"] / (sd * math.sqrt(k))) for k in (21, 63, 252)) / 3.0
            ma = math.tanh((f["sma_50"] / f["sma_200"] - 1.0) / 0.05)
            channel = f["channel_55"]
            score = 0.5 * tsmom + 0.25 * ma + 0.25 * channel
            reason = f"TSMOM {tsmom:+.2f}, MA50/200 {ma:+.2f}, channel {channel:+.2f}"
            if abs(score) < self.min_score:
                out.append(self.abstain(ctx, symbol, f"weak trend ({reason})"))
                continue
            out.append(self.forecast(ctx, symbol, 0.5 + self.max_tilt * score, reason))
        return out
