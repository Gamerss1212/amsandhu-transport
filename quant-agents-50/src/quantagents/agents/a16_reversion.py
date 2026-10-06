"""A16 Short-Term Reversion Agent (Team 4, Phase 2). Appendix A3.

RSI(2) with a 200-day trend filter: buy short-term oversold inside an uptrend, sell
short-term overbought inside a downtrend. Internal bar strength (IBS) strengthens the call.
Horizon 5 days; abstains when nothing is stretched.
"""

from __future__ import annotations

from typing import ClassVar

from quantagents.agents.base import AgentContext, SignalAgent
from quantagents.schemas import AgentPrediction

NEEDED = ("close", "sma_200", "rsi_2", "ibs")


class ShortTermReversionAgent(SignalAgent):
    agent_id = "A16"
    name = "Short-Term Reversion Agent"
    kind = "stat"
    info_subset = ("ohlcv",)
    horizon_bars = 5

    oversold: ClassVar[float] = 10.0
    overbought: ClassVar[float] = 90.0

    def predict(self, ctx: AgentContext) -> list[AgentPrediction]:
        out: list[AgentPrediction] = []
        for symbol in ctx.tradable:
            f = ctx.features.get(symbol)
            if any(k not in f for k in NEEDED):
                out.append(self.abstain(ctx, symbol, "insufficient history"))
                continue
            uptrend = f["close"] > f["sma_200"]
            rsi2, ibs = f["rsi_2"], f["ibs"]
            if uptrend and rsi2 < self.oversold:
                p = 0.60 if ibs < 0.2 else 0.58
                out.append(self.forecast(ctx, symbol, p, f"oversold in uptrend (RSI2 {rsi2:.0f})"))
            elif not uptrend and rsi2 > self.overbought:
                p = 0.40 if ibs > 0.8 else 0.42
                out.append(
                    self.forecast(ctx, symbol, p, f"overbought in downtrend (RSI2 {rsi2:.0f})")
                )
            else:
                out.append(self.abstain(ctx, symbol, f"nothing stretched (RSI2 {rsi2:.0f})"))
        return out
