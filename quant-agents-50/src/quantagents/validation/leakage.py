"""A39 Red-Team Auditor: attacks a strategy before anyone trusts it (spec section 59).

Tests run here:
- future perturbation: scramble every bar after date t; the strategy's output up to t
  must not change (catches look-ahead and full-sample normalization)
- determinism: the same inputs must give the same outputs
- bounds: weights must be finite, long-only unless shorting is on, and within gross limits
- time shift: the same strategy fed data one bar older must not do better. A signal that
  improves when it arrives late was built on inputs whose dates are off somewhere. The test is
  paired (same days) and only fires on a clear difference (t >= 3 and >= 1% a year), so chance
  alone almost never trips it.
Duplicate timestamps cannot reach a strategy: MarketData, load_csv, RawDaily and the store all
refuse them (tests/test_leakage.py proves each entry point).
Any critical finding blocks the strategy until it is fixed (Tier 1 power).
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Literal

import numpy as np

from quantagents.backtest.engine import Backtester, Strategy, StrategyFactory
from quantagents.market import FIELDS, Bars, MarketData, MarketView
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


def delayed(factory: StrategyFactory, lag: int) -> StrategyFactory:
    """The same strategy, but at day t it sees only data up to t - ``lag`` (its signal is late)."""
    if lag < 1:
        raise ValueError("lag must be >= 1")

    def build(market: MarketData) -> Strategy:
        inner = factory(market)

        def strategy(view: MarketView) -> Mapping[str, float]:
            k = len(view) - 1 - lag
            return inner(market.view_at(k)) if k >= 0 else {}

        return strategy

    return build


class TimeShiftResult(Message):
    lag: int
    days: int
    original_annual: float
    delayed_annual: float
    t_stat: float
    finding: Finding | None


def time_shift_test(
    factory: StrategyFactory,
    market: MarketData,
    *,
    lag: int = 1,
    warmup: int = 260,
    cost_rate: float = 0.0,
    t_limit: float = 3.0,
    min_annual_gain: float = 0.01,
) -> TimeShiftResult:
    """Spec section 59: shifting the inputs forward in time must not help."""
    engine = Backtester(cost_rate)
    original = engine.run(market, factory(market), warmup=warmup, name="original")
    late = engine.run(market, delayed(factory, lag)(market), warmup=warmup, name="delayed")
    diff = late.returns - original.returns
    n = len(diff)
    sd = float(np.std(diff, ddof=1)) if n > 1 else 0.0
    mean = float(np.mean(diff)) if n else 0.0
    t = mean / (sd / math.sqrt(n)) if sd > 0 else 0.0
    gain = 252.0 * mean
    finding = None
    if t >= t_limit and gain >= min_annual_gain:
        finding = Finding(
            severity="critical",
            test="time_shift",
            detail=(
                f"data {lag} bar(s) older did better by {gain:+.1%} a year (t = {t:.1f}): "
                "the inputs' dates are probably off"
            ),
        )
    return TimeShiftResult(
        lag=lag,
        days=n,
        original_annual=252.0 * float(np.mean(original.returns)) if n else 0.0,
        delayed_annual=252.0 * float(np.mean(late.returns)) if n else 0.0,
        t_stat=t,
        finding=finding,
    )


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
        time_shift: bool = True,
    ) -> None:
        self.max_gross = max_gross
        self.allow_short = allow_short
        self.window = window
        self.probes = probes
        self.seed = seed
        self.time_shift = time_shift

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
        # the time shift needs a full backtest, which refuses out-of-bounds weights
        if self.time_shift and warmup + 2 < n and not any(f.test == "bounds" for f in findings):
            try:
                shift = time_shift_test(factory, market, warmup=warmup)
            except ValueError as exc:
                findings.append(
                    Finding(severity="high", test="time_shift", detail=f"could not run: {exc}")
                )
            else:
                if shift.finding is not None:
                    findings.append(shift.finding)
        return RedTeamReport(
            strategy=name,
            tests_run=("future_perturbation", "determinism", "bounds")
            + (("time_shift",) if self.time_shift else ()),
            findings=tuple(findings),
            passed=not any(f.severity == "critical" for f in findings),
        )
