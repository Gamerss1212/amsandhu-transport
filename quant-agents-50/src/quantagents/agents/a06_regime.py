"""A06 Regime Classifier (Team 2, Phase 4). Spec sections 27 and 79.

Market level (an equal-weight index of the tradable symbols):
- volatility regime: a 2-component Gaussian mixture (calm vs turbulent days) filtered by a
  sticky 2-state hidden Markov model, voted with 20-day volatility vs its 2-year median.
  The mixture only counts when it beats a single bell curve by BIC (otherwise EM "finds"
  two regimes in pure noise).
- risk-on vs risk-off: a vote of breadth (share above the 200-day average), the share with
  positive 3-month momentum, the index's own 200-day trend and the calm-volatility probability
- crisis: turbulent AND weak breadth AND the index 10-25%+ below its one-year high
Symbol level: trending vs ranging from ADX(14) and the 20-day efficiency ratio, direction from
the 50/200-day averages and 3-month momentum.

Context only: A06 never trades. A40 treats a crisis label as a red flag, A07 watches for
sudden jumps in the volatility probability, and A35 splits scorecards by regime.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import ClassVar, Literal

import numpy as np

from quantagents.agents.base import Agent
from quantagents.features import rolling_std
from quantagents.market import FloatArray, MarketView
from quantagents.regime_models import fit_two_state_mixture, market_returns, sticky_filter
from quantagents.schemas import Direction, FeatureFrame, RegimeReport, SymbolRegime

RegimeLabel = Literal["risk_on", "risk_off", "mixed", "crisis", "unknown"]


def _clip01(x: float) -> float:
    return min(1.0, max(0.0, x))


def symbol_regime(symbol: str, f: dict[str, float]) -> SymbolRegime:
    """Trending vs ranging for one symbol from its A03 feature row."""
    strength = []
    if "adx_14" in f:
        strength.append(_clip01((f["adx_14"] - 15.0) / 20.0))  # 15 -> 0, 35 -> 1
    if "er_20" in f:
        strength.append(_clip01((f["er_20"] - 0.10) / 0.30))  # 0.1 -> 0, 0.4 -> 1
    votes = []
    if "sma_50" in f and "sma_200" in f:
        votes.append(1 if f["sma_50"] > f["sma_200"] else -1)
    if "mom_63" in f:
        votes.append(1 if f["mom_63"] > 0 else -1)
    if not strength or not votes:
        return SymbolRegime(
            symbol=symbol, p_trending=0.5, direction=Direction.FLAT, label="unknown"
        )
    p_trending = sum(strength) / len(strength)
    total = sum(votes)
    direction = Direction.LONG if total > 0 else Direction.SHORT if total < 0 else Direction.FLAT
    label: Literal["trending_up", "trending_down", "ranging"] = "ranging"
    if p_trending >= 0.5 and direction is Direction.LONG:
        label = "trending_up"
    elif p_trending >= 0.5 and direction is Direction.SHORT:
        label = "trending_down"
    return SymbolRegime(symbol=symbol, p_trending=p_trending, direction=direction, label=label)


def vol_elevation(returns: FloatArray, window: int = 20, history: int = 504) -> float:
    """0-1 score for "volatility is unusually high": 20-day vol vs its median over the window.

    At or below the median scores 0; 1.8x the median or more scores 1. A ratio is used
    rather than a percentile because a percentile is high 20% of the time by construction,
    even when volatility never changes.
    """
    vol = rolling_std(returns, window)
    finite = vol[np.isfinite(vol)][-history:]
    if len(finite) == 0:
        return 0.0
    median = float(np.median(finite))
    if median <= 0:
        return 0.0
    return _clip01((float(finite[-1]) / median - 1.0) / 0.8)


class RegimeAgent(Agent):
    agent_id = "A06"
    name = "Regime Classifier"
    kind = "stat"
    info_subset = ("returns", "volatility", "breadth")

    window: ClassVar[int] = 504
    min_obs: ClassVar[int] = 120
    stay: ClassVar[float] = 0.97
    distinct_ratio: ClassVar[float] = 1.5  # mixture components must differ this much in variance
    prev_lag: ClassVar[int] = 5
    crisis_drawdown_start: ClassVar[float] = 0.10  # index drawdown where crisis odds start
    crisis_drawdown_span: ClassVar[float] = 0.15  # ... and reach full weight at 25%

    def classify(
        self, view: MarketView, snapshot_id: str, symbols: Sequence[str], features: FeatureFrame
    ) -> RegimeReport:
        per_symbol = tuple(symbol_regime(s, features.get(s)) for s in symbols)
        index = market_returns(view, symbols, self.window)
        index = index[np.isfinite(index)]
        if len(index) < self.min_obs:
            return RegimeReport(
                snapshot_id=snapshot_id,
                p_high_vol=0.5,
                p_high_vol_prev=0.5,
                p_risk_on=0.5,
                p_crisis=0.0,
                breadth=0.5,
                confidence=0.0,
                label="unknown",
                vol_label="unknown",
                symbols=per_symbol,
                methods=(f"not enough history ({len(index)} of {self.min_obs} index returns)",),
            )
        methods: list[str] = []
        elev_now = vol_elevation(index)
        elev_prev = vol_elevation(index[: -self.prev_lag])
        mixture = fit_two_state_mixture(index)
        if mixture.bic_prefers_two and mixture.variance_ratio >= self.distinct_ratio:
            filtered = sticky_filter(index, mixture, self.stay)
            p_high = 0.5 * float(filtered[-1]) + 0.5 * elev_now
            p_prev = 0.5 * float(filtered[-1 - self.prev_lag]) + 0.5 * elev_prev
            methods.append(
                f"mixture + sticky HMM (variance ratio {mixture.variance_ratio:.1f}) voted with "
                "20-day volatility vs its 2-year median"
            )
        else:
            p_high, p_prev = elev_now, elev_prev
            methods.append(
                "20-day volatility vs its 2-year median only (no evidence of two volatility "
                "regimes: the 2-state mixture did not beat one bell curve by BIC with a "
                f"variance ratio of {self.distinct_ratio}+)"
            )

        rows = [features.get(s) for s in symbols]
        above = [r["close"] > r["sma_200"] for r in rows if "close" in r and "sma_200" in r]
        rising = [r["mom_63"] > 0 for r in rows if "mom_63" in r]
        breadth = sum(above) / len(above) if above else 0.5
        votes = [breadth, 1.0 - p_high]
        if rising:
            votes.append(sum(rising) / len(rising))
        level = np.cumsum(index)
        if len(level) >= 200:
            votes.append(1.0 if level[-1] > float(np.mean(level[-200:])) else 0.0)
        methods.append(f"risk-on vote of {len(votes)} signals; trend/range from ADX and efficiency")
        p_risk_on = sum(votes) / len(votes)
        drawdown = 1.0 - math.exp(float(level[-1] - np.max(level[-252:])))
        depth = _clip01((drawdown - self.crisis_drawdown_start) / self.crisis_drawdown_span)
        p_crisis = p_high * (1.0 - breadth) * depth
        agreement = 1.0 - 2.0 * float(np.std(votes))
        confidence = _clip01(agreement) * min(1.0, len(index) / 252.0)

        label: RegimeLabel = "mixed"
        if p_crisis >= 0.5:
            label = "crisis"
        elif p_risk_on >= 0.6:
            label = "risk_on"
        elif p_risk_on <= 0.4:
            label = "risk_off"
        return RegimeReport(
            snapshot_id=snapshot_id,
            p_high_vol=_clip01(p_high),
            p_high_vol_prev=_clip01(p_prev),
            p_risk_on=_clip01(p_risk_on),
            p_crisis=_clip01(p_crisis),
            breadth=breadth,
            confidence=confidence,
            label=label,
            vol_label="turbulent" if p_high >= 0.5 else "calm",
            symbols=per_symbol,
            methods=tuple(methods),
        )
