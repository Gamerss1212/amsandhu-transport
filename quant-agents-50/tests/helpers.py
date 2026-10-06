"""Small builders shared by the tests."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date
from typing import Literal

import numpy as np

from quantagents.agents.base import AgentContext, SignalAgent
from quantagents.config import AppConfig
from quantagents.data.synthetic import business_days
from quantagents.market import FIELDS, Bars, MarketData
from quantagents.registry import Registry
from quantagents.schemas import (
    AgentPrediction,
    ContextReport,
    Direction,
    FeatureFrame,
    OrderIntent,
    OrderSide,
    VolForecast,
    team_of,
)


def wavy_market(
    symbols: Sequence[str] = ("AAA", "BBB", "CCC"),
    n: int = 300,
    end: date = date(2026, 9, 30),
    drifts: Sequence[float] | None = None,
) -> MarketData:
    """Smooth, valid OHLCV data with a gentle wave and an optional daily drift per symbol."""
    days = business_days(end, n)
    t = np.arange(n, dtype=np.float64)
    bars: dict[str, Bars] = {}
    for k, symbol in enumerate(symbols):
        drift = drifts[k] if drifts is not None else 0.0
        close = 100.0 * np.exp(drift * t) * (1.0 + 0.02 * np.sin(t / 7.0 + k))
        open_ = close * (1.0 - 0.001 * np.cos(t + k))
        high = np.maximum(open_, close) * 1.004
        low = np.minimum(open_, close) * 0.996
        bars[symbol] = Bars.from_arrays(
            open=open_, high=high, low=low, close=close, volume=np.full(n, 1e5)
        )
    return MarketData(days, bars)


def with_value(market: MarketData, symbol: str, field: str, index: int, value: float) -> MarketData:
    """Copy of ``market`` with one value replaced (for fault injection)."""
    bars: dict[str, Bars] = {}
    for s in market.symbols:
        arrays = {f: np.array(market.bars(s).field(f)) for f in FIELDS}
        if s == symbol:
            arrays[field][index] = value
        bars[s] = Bars.from_arrays(**arrays)
    return MarketData(market.dates, bars)


def prediction(
    agent_id: str = "A11",
    symbol: str = "AAA",
    p_up: float = 0.6,
    *,
    horizon: int = 20,
    abstain: bool = False,
    cycle_id: str = "C1",
) -> AgentPrediction:
    if abstain:
        direction, p = Direction.FLAT, 0.5
    else:
        direction, p = (Direction.LONG if p_up > 0.5 else Direction.SHORT), p_up
    return AgentPrediction(
        agent_id=agent_id,
        team=team_of(agent_id),
        cycle_id=cycle_id,
        snapshot_id="S1",
        symbol=symbol,
        horizon_bars=horizon,
        abstain=abstain,
        direction=direction,
        p_up=p,
        confidence=abs(p - 0.5) * 2.0,
    )


def intent(
    symbol: str = "AAA",
    side: OrderSide = OrderSide.BUY,
    qty: float = 10.0,
    *,
    ref: float = 100.0,
    stop: float | None = 95.0,
    intent_id: str = "I1",
    decision_id: str | None = "D1",
) -> OrderIntent:
    return OrderIntent(
        intent_id=intent_id,
        decision_id=decision_id,
        symbol=symbol,
        side=side,
        qty=qty,
        ref_price=ref,
        stop_price=stop,
        reason="test",
    )


def context_for(
    symbols: Sequence[str],
    sigma: float = 0.01,
    regime: Literal["low", "normal", "high"] = "normal",
    shock: bool = False,
) -> ContextReport:
    return ContextReport(
        snapshot_id="S1",
        agent_id="A08",
        vol_forecasts=tuple(
            VolForecast(
                symbol=s,
                sigma_daily=sigma,
                sigma_annual=sigma * 252**0.5,
                regime=regime,
                shock=shock,
            )
            for s in symbols
        ),
    )


def make_ctx(
    cfg: AppConfig,
    market: MarketData,
    as_of: date,
    features: Mapping[str, dict[str, float]],
    context: ContextReport | None = None,
) -> AgentContext:
    symbols = tuple(features)
    return AgentContext(
        cycle_id="C1",
        snapshot_id="S1",
        view=market.view(as_of),
        cfg=cfg,
        features=FeatureFrame(snapshot_id="S1", feature_version="test", values=dict(features)),
        context=context if context is not None else context_for(symbols),
        tradable=symbols,
    )


class AlwaysLongAgent(SignalAgent):
    """Test double: a confident long view on every symbol (stands in for a second team)."""

    agent_id = "A17"
    name = "Always-long test agent"
    kind = "stat"
    horizon_bars = 20
    p_up = 0.62

    def predict(self, ctx: AgentContext) -> list[AgentPrediction]:
        return [self.forecast(ctx, s, self.p_up, "test double: always long") for s in ctx.tradable]


def with_second_team(registry: Registry, agent_id: str = "A17") -> Registry:
    """Copy of ``registry`` where ``agent_id`` is an active AlwaysLongAgent from Phase 4."""
    return Registry(
        [
            s.model_copy(
                update={
                    "state": "active",
                    "implementation": "tests.helpers:AlwaysLongAgent",
                    "phase": 4,
                }
            )
            if s.id == agent_id
            else s
            for s in registry.specs
        ]
    )


def regime_market(
    *,
    n: int = 600,
    symbols: Sequence[str] = ("AAA", "BBB", "CCC", "DDD"),
    end: date = date(2026, 9, 30),
    vol: float = 0.01,
    shift_at: int | None = None,
    vol_after: float = 0.01,
    corr: float = 0.0,
    corr_after: float | None = None,
    drift: float = 0.0,
    drift_after: float | None = None,
    volume: float = 1e6,
    volume_after: float | None = None,
    seed: int = 3,
) -> MarketData:
    """Synthetic market with an optional regime change at bar ``shift_at``: volatility,
    correlation (one common factor), drift and volume can all change there."""
    rng = np.random.default_rng(seed)
    days = business_days(end, n)
    switch = n if shift_at is None else shift_at
    sig = np.where(np.arange(n) < switch, vol, vol_after)
    rho = np.where(np.arange(n) < switch, corr, corr if corr_after is None else corr_after)
    mu = np.where(np.arange(n) < switch, drift, drift if drift_after is None else drift_after)
    common = rng.standard_normal(n)
    bars: dict[str, Bars] = {}
    for j, symbol in enumerate(symbols):
        own = rng.standard_normal(n)
        r = mu + sig * (np.sqrt(rho) * common + np.sqrt(1.0 - rho) * own)
        close = 100.0 * np.exp(np.cumsum(r))
        open_ = np.concatenate([[100.0], close[:-1]])
        span = np.abs(r) + 0.25 * sig
        high = np.maximum(open_, close) * np.exp(0.5 * span)
        low = np.minimum(open_, close) * np.exp(-0.5 * span)
        vol_series = np.where(
            np.arange(n) < switch, volume, volume if volume_after is None else volume_after
        ) * (1.0 + 0.1 * j)
        bars[symbol] = Bars.from_arrays(
            open=open_, high=high, low=low, close=close, volume=vol_series
        )
    return MarketData(days, bars)


def path_market(
    close: Sequence[float],
    *,
    volume: Sequence[float] | None = None,
    spread: float = 0.002,
    symbol: str = "AAA",
    end: date = date(2026, 9, 30),
) -> MarketData:
    """One symbol following ``close`` exactly: opens at the prior close, a small range."""
    c = np.asarray(close, dtype=np.float64)
    n = len(c)
    o = np.concatenate([[c[0]], c[:-1]])
    high = np.maximum(o, c) * (1.0 + spread)
    low = np.minimum(o, c) * (1.0 - spread)
    v = np.full(n, 1e6) if volume is None else np.asarray(volume, dtype=np.float64)
    bars = {symbol: Bars.from_arrays(open=o, high=high, low=low, close=c, volume=v)}
    return MarketData(business_days(end, n), bars)


def staircase(
    steps: int = 30, flat: int = 10, jump: float = 0.02, drift: float = 0.001
) -> list[float]:
    """Prices that climb in steps: every step is a breakout that keeps going."""
    out: list[float] = []
    level = 100.0
    for _ in range(steps):
        level *= 1.0 + jump
        for _ in range(flat):
            level *= 1.0 + drift
            out.append(level)
    return out
