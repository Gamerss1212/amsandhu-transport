"""A02 Data Quality Sentinel (Team 1, Phase 1, Tier 1: blocks the cycle on bad data).

Scores data health 0-100. Symbols with hard faults are blocked from trading.
Score below 80 means no new entries; below 50 requests the kill switch (spec section 18).

Corporate actions (spec section 57, Phase 1): a one-day close-to-close jump near a split ratio
(x2, x3, x4, x5, x10 or the inverse) that the other symbols do not share is almost always an
unadjusted split, not a real move. It is a hard fault for as long as it sits inside the feature
window, because every return-based feature over that window would be wrong. The fix is adjusted
data (the store's ``load`` adjusts by default), not trading through it.

Stale feed (Phase 3 chaos): a last bar identical in every field (open, high, low, close and
volume) to the bar before is a feed re-sending old data, so the symbol is blocked that day.
"""

from __future__ import annotations

import math
from typing import ClassVar

import numpy as np
import numpy.typing as npt

from quantagents.agents.base import Agent
from quantagents.config import RiskConfig
from quantagents.features import FEATURE_TAIL
from quantagents.market import MarketView
from quantagents.schemas import CheckResult, DataHealthReport, HealthAction


def _repeats(*series: npt.NDArray[np.float64]) -> bool:
    """True when every field of the last bar equals the bar before: a feed re-sending old data."""
    return all(float(x[-1]) == float(x[-2]) for x in series)


class DataQualityAgent(Agent):
    agent_id = "A02"
    name = "Data Quality Sentinel"
    kind = "code"
    info_subset = ("ohlcv",)

    window: ClassVar[int] = FEATURE_TAIL
    spike_limit: ClassVar[float] = 0.25  # |log return| on the last bar
    min_history: ClassVar[int] = 260
    warning_penalty: ClassVar[float] = 2.0
    split_ratios: ClassVar[tuple[float, ...]] = (2.0, 3.0, 4.0, 5.0, 10.0)
    split_tolerance: ClassVar[float] = 0.03  # |log jump - log ratio| that still counts as a split
    peer_calm: ClassVar[float] = 0.10  # peers' median |log return| on a day they "did not move"

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
        if len(c) >= 2 and _repeats(o, h, lo, c, v):  # NaN never equals NaN: gaps do not count
            faults.append("last bar is an exact copy of the one before (stale feed?)")
        faults.extend(self._split_like(view, symbol))
        return faults

    def _log_returns(self, view: MarketView, symbol: str) -> npt.NDArray[np.float64]:
        c = view.close(symbol)[-self.window :]
        out = np.full(max(len(c) - 1, 0), np.nan)
        prev, now = c[:-1], c[1:]
        ok = np.isfinite(prev) & np.isfinite(now) & (prev > 0) & (now > 0)
        out[ok] = np.log(now[ok] / prev[ok])
        return out

    def _split_like(self, view: MarketView, symbol: str) -> list[str]:
        """Jumps that look like an unadjusted split and that peers do not share."""
        lr = self._log_returns(view, symbol)
        if len(lr) == 0:
            return []
        peers = [self._log_returns(view, p) for p in view.symbols if p != symbol]
        peer_move = (
            np.median(np.nan_to_num(np.abs(np.stack(peers)), nan=0.0), axis=0)
            if peers
            else np.zeros(len(lr))
        )
        logs = np.log(np.array(self.split_ratios))
        dates = view.dates[-len(lr) :]
        hits = [
            k
            for k in np.flatnonzero(np.isfinite(lr))
            if np.min(np.abs(abs(lr[k]) - logs)) < self.split_tolerance
            and peer_move[k] <= self.peer_calm
        ]
        if not hits:
            return []
        k = hits[-1]
        more = f" (+{len(hits) - 1} more)" if len(hits) > 1 else ""
        return [
            f"split-like jump x{math.exp(lr[k]):.2f} on {dates[k].isoformat()} that peers do "
            f"not share{more}: unadjusted split? use adjusted data"
        ]

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
