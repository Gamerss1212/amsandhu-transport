"""A39 Red-Team Auditor: attacks a strategy before anyone trusts it (spec section 59).

Tests run here:
- future perturbation: scramble every bar after date t; the strategy's output up to t
  must not change (catches look-ahead and full-sample normalization)
- determinism: the same inputs must give the same outputs
- bounds: weights must be finite, long-only unless shorting is on, and within gross limits
Any critical finding blocks the strategy until it is fixed (Tier 1 power).
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Literal

import numpy as np

from quantagents.backtest.engine import StrategyFactory
from quantagents.market import FIELDS, Bars, MarketData
from quantagents.schemas import Message

Severity = Literal["critical", "high", "medium", "low"]


class Finding(Message):
    severity: Severity
    test: str
    detail: str


class RedTeamReport(Message):
    strategy: str
    tests_run: tuple[str, ...]
    findings: tuple[Finding, ...]
    passed: bool


def perturb_future(market: MarketData, after_index: int, seed: int) -> MarketData:
    """Copy of ``market`` where every bar after ``after_index`` is randomly rescaled."""
    rng = np.random.default_rng(seed)
    n = len(market)
    later = n - after_index - 1
    price_factor = np.ones(n)
    price_factor[after_index + 1 :] = np.exp(rng.normal(0.0, 0.25, later))
    volume_factor = np.ones(n)
    volume_factor[after_index + 1 :] = np.exp(rng.normal(0.0, 0.50, later))
    bars: dict[str, Bars] = {}
    for symbol in market.symbols:
        b = market.bars(symbol)
        arrays = {f: np.array(b.field(f)) for f in FIELDS}
        for f in ("open", "high", "low", "close"):
            arrays[f] = arrays[f] * price_factor
        arrays["volume"] = arrays["volume"] * volume_factor
        bars[symbol] = Bars.from_arrays(**arrays)
    return MarketData(market.dates, bars)


def _same(a: Sequence[Mapping[str, float]], b: Sequence[Mapping[str, float]]) -> bool:
    if len(a) != len(b):
        return False
    for x, y in zip(a, b, strict=True):
        keys = set(x) | set(y)
        if any(not math.isclose(x.get(k, 0.0), y.get(k, 0.0), abs_tol=1e-12) for k in keys):
            return False
    return True


def run_window(
    factory: StrategyFactory, market: MarketData, start: int, end: int
) -> list[dict[str, float]]:
    """Run a fresh strategy instance over bar indices start..end (inclusive)."""
    strategy = factory(market)
    return [dict(strategy(market.view_at(i))) for i in range(start, end + 1)]


class RedTeamAuditor:
    agent_id = "A39"
    name = "Red-Team Auditor"
    kind = "mixed"

    def __init__(
        self,
        *,
        max_gross: float = 1.0,
        allow_short: bool = False,
        window: int = 15,
        probes: int = 4,
        seed: int = 0,
    ) -> None:
        self.max_gross = max_gross
        self.allow_short = allow_short
        self.window = window
        self.probes = probes
        self.seed = seed

    def audit(
        self, factory: StrategyFactory, market: MarketData, *, name: str, warmup: int = 260
    ) -> RedTeamReport:
        n = len(market)
        first = min(warmup + self.window, n - 2)
        probe_points = sorted({int(x) for x in np.linspace(first, n - 2, self.probes)})
        findings: list[Finding] = []
        for t in probe_points:
            start = max(0, t - self.window)
            day = market.dates[t].isoformat()
            original = run_window(factory, market, start, t)
            scrambled = run_window(factory, perturb_future(market, t, self.seed + t), start, t)
            if not _same(original, scrambled):
                findings.append(
                    Finding(
                        severity="critical",
                        test="future_perturbation",
                        detail=f"output up to {day} changed when only later data changed: look-ahead",
                    )
                )
            if not _same(original, run_window(factory, market, start, t)):
                findings.append(
                    Finding(
                        severity="high",
                        test="determinism",
                        detail=f"two identical runs disagree by {day}",
                    )
                )
            for weights in original:
                values = list(weights.values())
                if any(not math.isfinite(v) for v in values):
                    findings.append(
                        Finding(
                            severity="critical",
                            test="bounds",
                            detail=f"non-finite weight near {day}",
                        )
                    )
                    break
                if not self.allow_short and any(v < 0 for v in values):
                    findings.append(
                        Finding(
                            severity="high",
                            test="bounds",
                            detail=f"short weight near {day} with shorting off",
                        )
                    )
                    break
                if sum(abs(v) for v in values) > self.max_gross + 1e-9:
                    findings.append(
                        Finding(
                            severity="high",
                            test="bounds",
                            detail=f"gross exposure above {self.max_gross} near {day}",
                        )
                    )
                    break
        return RedTeamReport(
            strategy=name,
            tests_run=("future_perturbation", "determinism", "bounds"),
            findings=tuple(findings),
            passed=not any(f.severity == "critical" for f in findings),
        )
