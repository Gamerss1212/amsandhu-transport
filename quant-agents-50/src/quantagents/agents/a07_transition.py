"""A07 Transition Detector (Team 2, Phase 4, Tier 1: halves system risk). Spec sections 28, 49.

Five independent detectors on the equal-weight index of the tradable symbols:
1. change point: Bayesian online change-point detection says a new regime probably began
   within the last 30 bars (Adams-MacKay; tuned to about 1-3% false alarms on calm data)
2. volatility breakout: 10-day volatility at least 2x the volatility of the 120 days before
3. correlation breakdown: average correlation jumps by 0.30+ to 0.60+ ("everything moves together")
4. regime shift: A06's turbulence probability moved by 0.5+ in 5 bars
5. liquidity drain: traded value over the last 5 days at most 40% of the prior 60-day median

Alert when a strong detector (1 or 2) fires, or when any two fire. The alert can only
reduce risk: A49 drops to REDUCED (risk x 0.5) while it is on.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import ClassVar

import numpy as np

from quantagents.agents.base import Agent
from quantagents.market import FloatArray, MarketView
from quantagents.regime_models import (
    average_correlation,
    bocpd_run_length,
    market_returns,
    return_matrix,
)
from quantagents.schemas import DetectorResult, RegimeReport, TransitionReport

STRONG = frozenset({"change_point", "volatility_breakout"})


def _skip(name: str, threshold: float, why: str) -> DetectorResult:
    return DetectorResult(name=name, ran=False, fired=False, threshold=threshold, detail=why)


class TransitionAgent(Agent):
    agent_id = "A07"
    name = "Transition Detector"
    kind = "stat"
    info_subset = ("returns", "volatility", "correlations", "regime_probs", "traded_value")

    window: ClassVar[int] = 252
    hazard: ClassVar[float] = 1.0 / 500.0
    recent: ClassVar[int] = 30
    p_change: ClassVar[float] = 0.5
    vol_short: ClassVar[int] = 10
    vol_long: ClassVar[int] = 120
    vol_ratio: ClassVar[float] = 2.0
    corr_short: ClassVar[int] = 20
    corr_long: ClassVar[int] = 120
    corr_jump: ClassVar[float] = 0.30
    corr_level: ClassVar[float] = 0.60
    regime_jump: ClassVar[float] = 0.50
    liq_short: ClassVar[int] = 5
    liq_long: ClassVar[int] = 60
    liq_drop: ClassVar[float] = 0.40

    def _change_point(self, index: FloatArray) -> tuple[DetectorResult, float]:
        if len(index) < 2 * self.recent:
            return (
                _skip("change_point", self.p_change, f"not run: {len(index)} returns"),
                0.0,
            )
        result = bocpd_run_length(index, hazard=self.hazard, recent=self.recent)
        p = result.p_recent_change
        return (
            DetectorResult(
                name="change_point",
                fired=p >= self.p_change,
                value=p,
                threshold=self.p_change,
                detail=f"P(new regime in last {self.recent} bars) {p:.2f}; "
                f"most likely {result.map_run_length} bars since the last change",
            ),
            p,
        )

    def _vol_breakout(self, index: FloatArray) -> DetectorResult:
        if len(index) < self.vol_short + self.vol_long:
            return _skip("volatility_breakout", self.vol_ratio, "not run: short history")
        recent = float(np.std(index[-self.vol_short :], ddof=1))
        base = float(np.std(index[-(self.vol_short + self.vol_long) : -self.vol_short], ddof=1))
        ratio = recent / base if base > 0 else math.inf
        return DetectorResult(
            name="volatility_breakout",
            fired=ratio >= self.vol_ratio,
            value=ratio if math.isfinite(ratio) else None,
            threshold=self.vol_ratio,
            detail=f"{self.vol_short}-day vol is {ratio:.1f}x the prior {self.vol_long} days",
        )

    def _correlation(self, view: MarketView, symbols: Sequence[str]) -> DetectorResult:
        if len(symbols) < 3:
            return _skip("correlation_breakdown", self.corr_jump, "not run: needs 3+ symbols")
        matrix = return_matrix(view, symbols, self.corr_short + self.corr_long)
        now = average_correlation(matrix[-self.corr_short :])
        before = average_correlation(matrix[: -self.corr_short])
        if not (math.isfinite(now) and math.isfinite(before)):
            return _skip("correlation_breakdown", self.corr_jump, "not run: not enough clean data")
        jump = now - before
        return DetectorResult(
            name="correlation_breakdown",
            fired=jump >= self.corr_jump and now >= self.corr_level,
            value=jump,
            threshold=self.corr_jump,
            detail=f"average correlation {before:.2f} -> {now:.2f}",
        )

    def _regime_shift(self, regime: RegimeReport | None) -> DetectorResult:
        if regime is None or regime.label == "unknown":
            return _skip("regime_shift", self.regime_jump, "not run: no A06 regime")
        move = abs(regime.p_high_vol - regime.p_high_vol_prev)
        return DetectorResult(
            name="regime_shift",
            fired=move >= self.regime_jump,
            value=move,
            threshold=self.regime_jump,
            detail=f"A06 turbulence probability {regime.p_high_vol_prev:.2f} -> {regime.p_high_vol:.2f}",
        )

    def _liquidity(self, view: MarketView, symbols: Sequence[str]) -> DetectorResult:
        n = self.liq_short + self.liq_long
        if len(view) < n or not symbols:
            return _skip("liquidity_drain", self.liq_drop, "not run: short history")
        value = np.zeros(n)
        for s in symbols:
            traded = np.asarray(view.close(s)[-n:] * view.volume(s)[-n:], dtype=np.float64)
            value += np.where(np.isfinite(traded), traded, 0.0)
        base = float(np.median(value[: self.liq_long]))
        now = float(np.median(value[self.liq_long :]))
        if base <= 0:
            return _skip("liquidity_drain", self.liq_drop, "not run: no traded value")
        ratio = now / base
        return DetectorResult(
            name="liquidity_drain",
            fired=ratio <= self.liq_drop,
            value=ratio,
            threshold=self.liq_drop,
            detail=f"traded value at {ratio:.0%} of its {self.liq_long}-day median",
        )

    def detect(
        self,
        view: MarketView,
        snapshot_id: str,
        symbols: Sequence[str],
        regime: RegimeReport | None,
    ) -> TransitionReport:
        index = market_returns(view, symbols, self.window)
        index = index[np.isfinite(index)]
        change, p_change = self._change_point(index)
        detectors = (
            change,
            self._vol_breakout(index),
            self._correlation(view, symbols),
            self._regime_shift(regime),
            self._liquidity(view, symbols),
        )
        ran = [d for d in detectors if d.ran]
        fired = [d.name for d in detectors if d.fired]
        alert = bool(STRONG & set(fired)) or len(fired) >= 2
        return TransitionReport(
            snapshot_id=snapshot_id,
            alert=alert,
            severity=len(fired) / len(ran) if ran else 0.0,
            p_recent_change=p_change,
            detectors=detectors,
        )
