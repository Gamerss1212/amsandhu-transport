"""A15 Trend Exhaustion Agent (Team 3, Phase 4). Spec section 9.

Looks for signs that an established trend is tired:
1. extension: price 3.5+ ATRs beyond its 50-day average (weight 1.0)
2. stretched RSI: RSI(14) above 75 in an uptrend, below 25 in a downtrend (0.75)
3. divergence: a new 60-bar price extreme in the last 5 bars while RSI(14) stays 5+ points
   below its earlier peak (1.0)
4. climax volume: a bar in the last 3 with 2.5x normal volume, moving with the trend, with a
   range of 1.5+ ATRs (0.75)
5. efficiency decay: the 10-bar efficiency ratio halves from a clean trend (0.4+) (0.5)

exhaustion = fired weight / total weight. When it reaches 0.25, A15 leans AGAINST the trend:
p_up = 0.5 - direction x 0.06 x exhaustion (at most 6 points). It never edits another agent;
inside Team 3's pooled vote this simply offsets A11's trend call when the trend looks tired.
Starts in shadow: sealed and scored by A35, no vote until the owner promotes it.
"""

from __future__ import annotations

from typing import ClassVar

import numpy as np

from quantagents.agents.base import AgentContext, SignalAgent
from quantagents.features import atr, efficiency_ratio, rsi
from quantagents.market import MarketView
from quantagents.schemas import AgentPrediction

NEEDED = ("close", "sma_50", "sma_200", "atr_14", "rsi_14", "mom_63")
WEIGHTS: dict[str, float] = {
    "extension": 1.0,
    "stretched_rsi": 0.75,
    "divergence": 1.0,
    "climax_volume": 0.75,
    "efficiency_decay": 0.5,
}


class ExhaustionAgent(SignalAgent):
    agent_id = "A15"
    name = "Trend Exhaustion Agent"
    kind = "stat"
    info_subset = ("ohlcv", "adx", "efficiency_ratio")
    horizon_bars = 10

    max_tilt: ClassVar[float] = 0.06
    min_exhaustion: ClassVar[float] = 0.25
    extension_atr: ClassVar[float] = 3.5
    rsi_high: ClassVar[float] = 75.0
    rsi_low: ClassVar[float] = 25.0
    divergence_window: ClassVar[int] = 60
    divergence_gap: ClassVar[float] = 5.0
    climax_volume: ClassVar[float] = 2.5
    climax_range_atr: ClassVar[float] = 1.5
    er_clean: ClassVar[float] = 0.4

    def signs(self, view: MarketView, symbol: str, f: dict[str, float], trend: int) -> list[str]:
        """Names of the exhaustion signs that fire for a trend in direction ``trend``."""
        fired: list[str] = []
        if (f["close"] - f["sma_50"]) / f["atr_14"] * trend >= self.extension_atr:
            fired.append("extension")
        if (trend > 0 and f["rsi_14"] >= self.rsi_high) or (
            trend < 0 and f["rsi_14"] <= self.rsi_low
        ):
            fired.append("stretched_rsi")
        tail = self.divergence_window + 40
        c = np.ascontiguousarray(view.close(symbol)[-tail:])
        h = np.ascontiguousarray(view.high(symbol)[-tail:])
        lo = np.ascontiguousarray(view.low(symbol)[-tail:])
        o = np.ascontiguousarray(view.open(symbol)[-tail:])
        v = np.ascontiguousarray(view.volume(symbol)[-tail:])
        if len(c) < tail or not np.all(np.isfinite(np.stack([o, h, lo, c, v]))):
            return fired
        w = self.divergence_window
        r = rsi(c, 14)
        if trend > 0:
            new_extreme = np.max(c[-5:]) >= np.max(c[-w:])
            weaker = np.max(r[-5:]) <= np.max(r[-w:-5]) - self.divergence_gap
        else:
            new_extreme = np.min(c[-5:]) <= np.min(c[-w:])
            weaker = np.min(r[-5:]) >= np.min(r[-w:-5]) + self.divergence_gap
        if new_extreme and weaker:
            fired.append("divergence")
        a = atr(h, lo, c, 14)
        for i in range(len(c) - 3, len(c)):
            base = float(np.median(v[i - 20 : i]))
            with_trend = (c[i] - o[i]) * trend > 0
            wide = h[i] - lo[i] >= self.climax_range_atr * a[i - 1]
            if base > 0 and v[i] >= self.climax_volume * base and with_trend and wide:
                fired.append("climax_volume")
                break
        er = efficiency_ratio(c, 10)
        if er[-11] >= self.er_clean and er[-1] <= 0.5 * er[-11]:
            fired.append("efficiency_decay")
        return fired

    def predict(self, ctx: AgentContext) -> list[AgentPrediction]:
        out: list[AgentPrediction] = []
        total = sum(WEIGHTS.values())
        for symbol in ctx.tradable:
            f = ctx.features.get(symbol)
            if any(k not in f for k in NEEDED) or f["atr_14"] <= 0:
                out.append(self.abstain(ctx, symbol, "insufficient history"))
                continue
            up = f["sma_50"] > f["sma_200"] and f["mom_63"] > 0
            down = f["sma_50"] < f["sma_200"] and f["mom_63"] < 0
            if not (up or down):
                out.append(self.abstain(ctx, symbol, "no established trend to exhaust"))
                continue
            trend = 1 if up else -1
            fired = self.signs(ctx.view, symbol, f, trend)
            exhaustion = sum(WEIGHTS[name] for name in fired) / total
            word = "uptrend" if trend > 0 else "downtrend"
            if exhaustion < self.min_exhaustion:
                detail = f" ({', '.join(fired)})" if fired else ""
                out.append(self.abstain(ctx, symbol, f"{word} looks healthy{detail}"))
                continue
            p_up = 0.5 - trend * self.max_tilt * exhaustion
            reason = f"tired {word}: {', '.join(fired)} (exhaustion {exhaustion:.2f})"
            out.append(self.forecast(ctx, symbol, p_up, reason))
        return out
