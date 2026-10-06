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
from quantagents.backtest import library
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
        # Phase 2 library (backtest/library.py): grids fixed before any real-data run
        "tsmom_blend": lambda: [
            ("tsmom_blend_vt10", library.tsmom_blend(target_vol=0.10)),
            ("tsmom_blend_raw", library.tsmom_blend(target_vol=None)),
        ],
        "xs_mom": lambda: [
            ("xsmom_12_1", library.xs_momentum()),
            ("xsmom_12_1_trend", library.xs_momentum(trend_filter=True)),
        ],
        "faber": lambda: [(f"faber_{m}m", library.faber(m)) for m in (10, 8, 12)],
        "rsi2": lambda: [
            ("rsi2_10", library.rsi2(10.0)),
            ("rsi2_5", library.rsi2(5.0)),
        ],
        "vol_target": lambda: [
            ("vt10_hold", library.vol_target(buy_and_hold(), 0.10)),
            ("vt15_hold", library.vol_target(buy_and_hold(), 0.15)),
        ],
        # added with the research grid (backtest/grid.py), same parameters as there
        "sma_cross": lambda: [
            (f"sma_cross_{f}_{s}", library.sma_cross(f, s))
            for f, s in ((50, 200), (20, 100), (50, 150), (100, 200))
        ],
        "dual_mom": lambda: [
            (f"dual_mom_{lb}_top{k}", library.dual_momentum(lb, k))
            for lb in (252, 126)
            for k in (1, 2, 3)
        ],
        "donchian": lambda: [
            (f"donchian_{e}_{x}", library.donchian(e, x))
            for e, x in ((55, 20), (20, 10), (100, 50))
        ],
    }
    if name not in grids:
        raise KeyError(f"unknown strategy {name!r}; choose from {sorted(grids)}")
    return grids[name]()


DEFAULT_VARIANT = {
    "buy_and_hold": "buy_and_hold",
    "tsmom": "tsmom_126",
    "sma": "sma_200",
    "ensemble": "ensemble",
    "tsmom_blend": "tsmom_blend_vt10",
    "xs_mom": "xsmom_12_1",
    "faber": "faber_10m",
    "rsi2": "rsi2_10",
    "vol_target": "vt10_hold",
    "sma_cross": "sma_cross_50_200",
    "dual_mom": "dual_mom_252_top1",
    "donchian": "donchian_55_20",
}
