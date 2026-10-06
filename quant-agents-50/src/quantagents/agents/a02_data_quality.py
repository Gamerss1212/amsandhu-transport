"""A02 Data Quality Sentinel (Team 1, Phase 1, Tier 1: blocks the cycle on bad data).

Scores data health 0-100. Symbols with hard faults are blocked from trading.
Score below 80 means no new entries; below 50 requests the kill switch (spec section 18).
"""

from __future__ import annotations

import math
from typing import ClassVar

import numpy as np

from quantagents.agents.base import Agent
from quantagents.config import RiskConfig
from quantagents.features import FEATURE_TAIL
from quantagents.market import MarketView
from quantagents.schemas import CheckResult, DataHealthReport, HealthAction


class DataQualityAgent(Agent):
    agent_id = "A02"
    name = "Data Quality Sentinel"
    kind = "code"
    info_subset = ("ohlcv",)

    window: ClassVar[int] = FEATURE_TAIL
    spike_limit: ClassVar[float] = 0.25  # |log return| on the last bar
    min_history: ClassVar[int] = 260
    warning_penalty: ClassVar[float] = 2.0

    def _hard_faults(self, view: MarketView, symbol: str) -> list[str]:
        o, h, lo, c, v = (
            view.series(symbol, f)[-self.window :]
            for f in ("open", "high", "low", "close", "volume")
        )
        faults: list[str] = []
        if not view.last(symbol).is_finite():
            faults.append("no complete bar on the as-of date")
        if not np.all(np.isfinite(np.stack([o, h, lo, c, v]))):
            faults.append("gaps (NaN) in the recent window")
        prices = np.stack([o, h, lo, c])
        prices = prices[:, np.all(np.isfinite(prices), axis=0)]
        if np.any(prices <= 0):
            faults.append("non-positive prices")
        else:
            oo, hh, ll, cc = prices
            tol = 1e-9 * hh
            if np.any(ll > np.minimum(oo, cc) + tol) or np.any(hh < np.maximum(oo, cc) - tol):
                faults.append("high/low inconsistent with open/close")
        finite_volume = v[np.isfinite(v)]
        if np.any(finite_volume < 0):
            faults.append("negative volume")
        return faults

    def _warnings(self, view: MarketView, symbol: str) -> list[str]:
        warnings: list[str] = []
        if len(view) < self.min_history:
            warnings.append(f"short history ({len(view)} bars)")
        c = view.close(symbol)
        if len(c) >= 2:
            a, b = float(c[-2]), float(c[-1])
            finite = a > 0 and b > 0 and math.isfinite(a) and math.isfinite(b)
            if finite and abs(math.log(b / a)) > self.spike_limit:
                warnings.append("price spike on the last bar")
        volume = float(view.volume(symbol)[-1])
        if volume == 0:
            warnings.append("zero volume on the last bar")
        return warnings

    def check(self, view: MarketView, snapshot_id: str, limits: RiskConfig) -> DataHealthReport:
        checks: list[CheckResult] = []
        blocked: list[str] = []
        stale: list[str] = []
        n_warnings = 0
        for symbol in view.symbols:
            faults = self._hard_faults(view, symbol)
            warnings = self._warnings(view, symbol)
            if faults:
                blocked.append(symbol)
            if not view.last(symbol).is_finite():
                stale.append(symbol)
            n_warnings += len(warnings)
            checks.append(
                CheckResult(
                    name=symbol, passed=not faults, detail="; ".join(faults + warnings) or "ok"
                )
            )
        score = 100.0 * (1.0 - len(blocked) / len(view.symbols)) - self.warning_penalty * n_warnings
        score = min(100.0, max(0.0, score))
        if score < limits.data_health_halt:
            action = HealthAction.HALT
        elif score < limits.data_health_defensive:
            action = HealthAction.DEFENSIVE
        else:
            action = HealthAction.OK
        return DataHealthReport(
            snapshot_id=snapshot_id,
            score_0_100=score,
            checks=tuple(checks),
            stale_symbols=tuple(stale),
            blocked_symbols=tuple(blocked),
            action=action,
        )
