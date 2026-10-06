"""Reference strategies for the backtester. Every strategy is built by a factory from the
data it will run on, so the red-team leakage test (A39) can rebuild it on altered data."""

from __future__ import annotations

from collections.abc import Callable

import numpy as np

from quantagents.agents.a03_features import FeatureAgent
from quantagents.agents.a08_volatility import VolatilityAgent
from quantagents.agents.a11_trend import TrendAgent
from quantagents.agents.a12_xs_momentum import CrossSectionalMomentumAgent
from quantagents.agents.a16_reversion import ShortTermReversionAgent
from quantagents.agents.a23_calendar import CalendarAgent
from quantagents.agents.base import AgentContext, SignalAgent
from quantagents.aggregation import go_decision, pool_votes, size_hint, votes_from_predictions
from quantagents.backtest.engine import Strategy, StrategyFactory
from quantagents.config import AppConfig
from quantagents.features import momentum, sma
from quantagents.market import MarketData, MarketView
from quantagents.schemas import Direction


def buy_and_hold() -> StrategyFactory:
    def factory(market: MarketData) -> Strategy:
        def strategy(view: MarketView) -> dict[str, float]:
            return {s: 1.0 / len(view.symbols) for s in view.symbols}

        return strategy

    return factory


def tsmom(lookback: int = 126) -> StrategyFactory:
    """Long-only time-series momentum: equal weight in every symbol with a positive return."""

    def factory(market: MarketData) -> Strategy:
        def strategy(view: MarketView) -> dict[str, float]:
            n = len(view.symbols)
            out: dict[str, float] = {}
            for s in view.symbols:
                value = float(
                    momentum(np.ascontiguousarray(view.close(s)[-(lookback + 1) :]), lookback)[-1]
                )
                if value > 0:
                    out[s] = 1.0 / n
            return out

        return strategy

    return factory


def sma_filter(window: int = 200) -> StrategyFactory:
    """Faber-style filter: hold a symbol while it closes above its moving average."""

    def factory(market: MarketData) -> Strategy:
        def strategy(view: MarketView) -> dict[str, float]:
            n = len(view.symbols)
            out: dict[str, float] = {}
            for s in view.symbols:
                c = np.ascontiguousarray(view.close(s)[-window:])
                if len(c) == window and c[-1] > float(sma(c, window)[-1]):
                    out[s] = 1.0 / n
            return out

        return strategy

    return factory


class AgentEnsembleStrategy:
    """The starter signal agents + pooling + GO rules as long-only daily weights.

    A research proxy for the live cycle: no sealing, no A40 and no A49, so expect the live
    cycle to trade less. Sizing mirrors A48 (risk to a 2x ATR stop, capped below major size).
    """

    def __init__(self, cfg: AppConfig) -> None:
        self.cfg = cfg
        self.signal_agents: list[SignalAgent] = [
            TrendAgent(),
            CrossSectionalMomentumAgent(),
            ShortTermReversionAgent(),
            CalendarAgent(),
        ]
        self.features = FeatureAgent()
        self.vol = VolatilityAgent()
        self.held: dict[str, float] = {}

    def __call__(self, view: MarketView) -> dict[str, float]:
        cfg, agg, risk = self.cfg, self.cfg.aggregation, self.cfg.risk
        phase = cfg.system.phase
        sid = f"bt-{view.as_of:%Y%m%d}"
        frame = self.features.compute(view, sid, view.symbols)
        context = self.vol.forecast(view, sid, view.symbols)
        ctx = AgentContext(sid, sid, view, cfg, frame, context, view.symbols)
        predictions = [p for agent in self.signal_agents for p in agent.predict(ctx)]
        weights: dict[str, float] = {}
        for s in view.symbols:
            votes = votes_from_predictions(
                [p for p in predictions if p.symbol == s], agg.decision_horizon_days
            )
            pool = pool_votes(s, votes, agg, two_stage=phase >= agg.two_stage_from_phase)
            vol = context.vol(s)
            decision = go_decision(
                pool,
                sigma_daily=vol.sigma_daily if vol else None,
                agg=agg,
                costs=cfg.costs,
                phase=phase,
                p_no_trade=None,
                blocks=(),
            )
            f = frame.get(s)
            if decision.go and pool.direction is Direction.LONG and "atr_14" in f:
                risk_pct = min(
                    risk.max_risk_per_trade_pct * size_hint(pool, agg),
                    0.99 * risk.major_trade_risk_pct,
                )
                stop_fraction = risk.stop_atr_multiple * f["atr_14"] / f["close"]
                weights[s] = min(risk_pct / 100.0 / stop_fraction, risk.max_position_pct / 100.0)
            elif s in self.held and pool.direction is not Direction.SHORT:
                weights[s] = self.held[s]
        gross = sum(weights.values())
        if gross > 1.0:
            weights = {s: w / gross for s, w in weights.items()}
        self.held = {s: w for s, w in weights.items() if w > 0}
        return weights


def ensemble(cfg: AppConfig) -> StrategyFactory:
    def factory(market: MarketData) -> Strategy:
        return AgentEnsembleStrategy(cfg)

    return factory


def strategy_grid(name: str, cfg: AppConfig) -> list[tuple[str, StrategyFactory]]:
    """Every variant tried for a strategy family. Count them all as trials (spec section 63)."""
    grids: dict[str, Callable[[], list[tuple[str, StrategyFactory]]]] = {
        "buy_and_hold": lambda: [("buy_and_hold", buy_and_hold())],
        "tsmom": lambda: [(f"tsmom_{k}", tsmom(k)) for k in (21, 42, 63, 126, 189, 252)],
        "sma": lambda: [(f"sma_{k}", sma_filter(k)) for k in (50, 100, 150, 200, 250)],
        "ensemble": lambda: [("ensemble", ensemble(cfg))],
    }
    if name not in grids:
        raise KeyError(f"unknown strategy {name!r}; choose from {sorted(grids)}")
    return grids[name]()


DEFAULT_VARIANT = {
    "buy_and_hold": "buy_and_hold",
    "tsmom": "tsmom_126",
    "sma": "sma_200",
    "ensemble": "ensemble",
}
