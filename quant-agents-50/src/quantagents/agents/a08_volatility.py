"""A08 Volatility Forecaster (Team 2, Phase 2).

EWMA (RiskMetrics, lambda 0.94) daily volatility per symbol, a volatility regime from the
percentile of 20-day realized volatility over the last year, and a shock flag for moves
larger than 4 sigma. Later phases can blend HAR-RV, GARCH and implied volatility here.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import ClassVar, Literal

import numpy as np

from quantagents.agents.base import Agent
from quantagents.features import FEATURE_TAIL, ewma_vol, log_returns, rolling_std
from quantagents.market import MarketView
from quantagents.schemas import ContextReport, VolForecast


class VolatilityAgent(Agent):
    agent_id = "A08"
    name = "Volatility Forecaster"
    kind = "stat"
    info_subset = ("ohlcv",)

    min_returns: ClassVar[int] = 60
    shock_sigmas: ClassVar[float] = 4.0

    def forecast_symbol(self, view: MarketView, symbol: str) -> VolForecast | None:
        returns = log_returns(np.ascontiguousarray(view.close(symbol)[-FEATURE_TAIL:]))
        if np.count_nonzero(np.isfinite(returns)) < self.min_returns:
            return None
        ewma = ewma_vol(returns)
        sigma = float(ewma[-1])
        if not math.isfinite(sigma) or sigma <= 0:
            return None
        realized = rolling_std(returns, 20)
        history = realized[np.isfinite(realized)][-252:]
        percentile = float(np.mean(history <= history[-1])) if len(history) else 0.5
        regime: Literal["low", "normal", "high"] = "normal"
        if percentile >= 0.8:
            regime = "high"
        elif percentile <= 0.2:
            regime = "low"
        previous = float(ewma[-2])
        last = float(returns[-1])
        shock = math.isfinite(previous) and math.isfinite(last) and previous > 0
        shock = shock and abs(last) > self.shock_sigmas * previous
        return VolForecast(
            symbol=symbol,
            sigma_daily=sigma,
            sigma_annual=sigma * math.sqrt(252.0),
            regime=regime,
            shock=shock,
        )

    def forecast(self, view: MarketView, snapshot_id: str, symbols: Sequence[str]) -> ContextReport:
        forecasts = [f for s in symbols if (f := self.forecast_symbol(view, s)) is not None]
        novelty = sum(f.shock for f in forecasts) / len(forecasts) if forecasts else 0.0
        return ContextReport(
            snapshot_id=snapshot_id,
            agent_id=self.agent_id,
            vol_forecasts=tuple(forecasts),
            novelty_score=novelty,
        )
