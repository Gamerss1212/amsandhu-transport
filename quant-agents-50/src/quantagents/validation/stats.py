"""A44 Statistical Validator (spec sections 60-64): is a backtest result statistically real?

Implements Newey-West t-statistics, the Probabilistic and Deflated Sharpe Ratios
(Bailey and Lopez de Prado), minimum backtest length, PBO via CSCV, Benjamini-Hochberg
FDR, the stationary bootstrap, and walk-forward / purged k-fold splits.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from itertools import combinations
from statistics import NormalDist
from typing import Literal

import numpy as np
import numpy.typing as npt

from quantagents.config import ValidationConfig
from quantagents.market import FloatArray
from quantagents.schemas import CheckResult, Message

EULER_GAMMA = 0.5772156649015329
_NORMAL = NormalDist()


def clean_returns(returns: npt.ArrayLike) -> FloatArray:
    r = np.asarray(returns, dtype=np.float64)
    if r.ndim != 1:
        raise ValueError("returns must be one-dimensional")
    r = r[np.isfinite(r)]
    if len(r) < 3:
        raise ValueError("need at least 3 finite returns")
    return r


def sharpe_ratio(returns: npt.ArrayLike, periods_per_year: int = 252) -> float:
    r = clean_returns(returns)
    sd = float(np.std(r, ddof=1))
    return float(np.mean(r)) / sd * math.sqrt(periods_per_year) if sd > 0 else 0.0


def newey_west_tstat(returns: npt.ArrayLike, lags: int | None = None) -> float:
    """t-statistic of the mean with HAC (Bartlett kernel) standard errors."""
    r = clean_returns(returns)
    n = len(r)
    lag_count = int(4 * (n / 100.0) ** (2.0 / 9.0)) if lags is None else lags
    e = r - np.mean(r)
    s = float(e @ e) / n
    for lag in range(1, min(lag_count, n - 1) + 1):
        s += 2.0 * (1.0 - lag / (lag_count + 1.0)) * float(e[lag:] @ e[:-lag]) / n
    return float(np.mean(r)) / math.sqrt(s / n) if s > 0 else 0.0


def probabilistic_sharpe_ratio(returns: npt.ArrayLike, sr_benchmark: float = 0.0) -> float:
    """P(true per-period Sharpe > benchmark), adjusting for skew and fat tails."""
    r = clean_returns(returns)
    n = len(r)
    sd = float(np.std(r, ddof=1))
    if sd == 0:
        return 0.0
    sr = float(np.mean(r)) / sd
    z = (r - np.mean(r)) / np.std(r)
    skew = float(np.mean(z**3))
    kurt = float(np.mean(z**4))
    denom = max(1.0 - skew * sr + (kurt - 1.0) / 4.0 * sr * sr, 1e-12)
    return _NORMAL.cdf((sr - sr_benchmark) * math.sqrt(n - 1) / math.sqrt(denom))


def _expected_max_z(n_trials: int) -> float:
    a = _NORMAL.inv_cdf(1.0 - 1.0 / n_trials)
    b = _NORMAL.inv_cdf(1.0 - 1.0 / (n_trials * math.e))
    return (1.0 - EULER_GAMMA) * a + EULER_GAMMA * b


def expected_max_sharpe(n_trials: int, sr_variance: float) -> float:
    """Expected best per-period Sharpe among n_trials skill-less strategies."""
    if n_trials <= 1:
        return 0.0
    return math.sqrt(sr_variance) * _expected_max_z(n_trials)


def deflated_sharpe_ratio(
    returns: npt.ArrayLike, n_trials: int, sr_variance: float | None = None
) -> float:
    """PSR against the Sharpe you would expect from luck alone after n_trials attempts."""
    r = clean_returns(returns)
    variance = sr_variance if sr_variance is not None else 1.0 / (len(r) - 1)
    return probabilistic_sharpe_ratio(r, expected_max_sharpe(n_trials, variance))


def min_backtest_length_years(n_trials: int, target_annual_sharpe: float) -> float:
    """Years of data needed so that n_trials skill-less tries are unlikely to reach the target."""
    if target_annual_sharpe <= 0:
        raise ValueError("target Sharpe must be positive")
    if n_trials <= 1:
        return 0.0
    return (_expected_max_z(n_trials) / target_annual_sharpe) ** 2


def pbo_cscv(performance: npt.ArrayLike, n_splits: int = 16) -> float:
    """Probability of Backtest Overfitting via combinatorially symmetric cross-validation.

    ``performance`` is a T x N matrix: per-period returns of every variant tried.
    Returns the share of splits where the in-sample winner ranks at or below the
    out-of-sample median. Around 0.5 or more means the selection process is overfit.
    """
    m = np.asarray(performance, dtype=np.float64)
    if m.ndim != 2 or m.shape[1] < 2:
        raise ValueError("need a T x N matrix with N >= 2 variants")
    if n_splits < 2 or n_splits % 2 or m.shape[0] < 2 * n_splits:
        raise ValueError("n_splits must be even and the sample at least 2 x n_splits long")
    blocks = np.array_split(np.arange(m.shape[0]), n_splits)
    sums = np.array([m[b].sum(axis=0) for b in blocks])
    squares = np.array([(m[b] ** 2).sum(axis=0) for b in blocks])
    counts = np.array([len(b) for b in blocks], dtype=np.float64)
    combos = list(combinations(range(n_splits), n_splits // 2))
    mask = np.zeros((len(combos), n_splits))
    for i, combo in enumerate(combos):
        mask[i, list(combo)] = 1.0

    def sharpe(selection: FloatArray) -> FloatArray:
        c = (selection @ counts)[:, None]
        mean = (selection @ sums) / c
        var = (selection @ squares) / c - mean**2
        result: FloatArray = mean / np.sqrt(np.clip(var, 1e-18, None))
        return result

    in_sample, out_sample = sharpe(mask), sharpe(1.0 - mask)
    best = np.argmax(in_sample, axis=1)
    chosen = out_sample[np.arange(len(combos)), best][:, None]
    rank = (
        1.0 + np.sum(out_sample < chosen, axis=1) + 0.5 * (np.sum(out_sample == chosen, axis=1) - 1)
    )
    omega = rank / (m.shape[1] + 1.0)
    logits = np.log(omega / (1.0 - omega))
    return float(np.mean(logits <= 0))


def benjamini_hochberg(pvalues: Sequence[float], q: float = 0.10) -> list[bool]:
    """Which hypotheses survive at false-discovery rate q."""
    p = np.asarray(pvalues, dtype=np.float64)
    m = len(p)
    if m == 0:
        return []
    order = np.argsort(p, kind="stable")
    passed = p[order] <= q * np.arange(1, m + 1) / m
    reject = np.zeros(m, dtype=bool)
    if passed.any():
        k = int(np.max(np.flatnonzero(passed)))
        reject[order[: k + 1]] = True
    return [bool(x) for x in reject]


def stationary_bootstrap_indices(
    n: int, mean_block: float, rng: np.random.Generator
) -> npt.NDArray[np.int64]:
    """Politis-Romano stationary bootstrap: blocks of geometric length, wrapping around."""
    starts = rng.random(n) < 1.0 / mean_block
    jumps = rng.integers(0, n, size=n)
    idx = np.empty(n, dtype=np.int64)
    idx[0] = jumps[0]
    for t in range(1, n):
        idx[t] = jumps[t] if starts[t] else (idx[t - 1] + 1) % n
    return idx


def bootstrap_sharpe_interval(
    returns: npt.ArrayLike, *, samples: int, mean_block: float, alpha: float = 0.05, seed: int = 0
) -> tuple[float, float]:
    r = clean_returns(returns)
    rng = np.random.default_rng(seed)
    stats = []
    for _ in range(samples):
        s = r[stationary_bootstrap_indices(len(r), mean_block, rng)]
        sd = float(np.std(s, ddof=1))
        stats.append(float(np.mean(s)) / sd * math.sqrt(252.0) if sd > 0 else 0.0)
    lo, hi = np.quantile(stats, [alpha / 2.0, 1.0 - alpha / 2.0])
    return float(lo), float(hi)


def walk_forward_splits(
    n: int, train: int, test: int, *, anchored: bool = False
) -> list[tuple[range, range]]:
    """Rolling (or anchored) train/test windows that never look forward."""
    if min(n, train, test) <= 0:
        raise ValueError("n, train and test must be positive")
    splits: list[tuple[range, range]] = []
    start = 0
    while start + train + test <= n:
        train_start = 0 if anchored else start
        splits.append(
            (range(train_start, start + train), range(start + train, start + train + test))
        )
        start += test
    return splits


def purged_kfold_splits(
    n: int, k: int, embargo: int
) -> list[tuple[npt.NDArray[np.int64], npt.NDArray[np.int64]]]:
    """K contiguous test folds; training drops the test fold plus ``embargo`` bars each side."""
    if k < 2 or n < k:
        raise ValueError("need k >= 2 and n >= k")
    idx = np.arange(n, dtype=np.int64)
    splits = []
    for fold in np.array_split(idx, k):
        lo, hi = int(fold[0]), int(fold[-1])
        keep = (idx < lo - embargo) | (idx > hi + embargo)
        splits.append((idx[keep], fold.astype(np.int64)))
    return splits


class ValidationReport(Message):
    strategy: str
    n_obs: int
    n_trials: int
    metrics: dict[str, float]
    checks: tuple[CheckResult, ...]
    passed: bool
    verdict: Literal["PASS", "FAIL"]
    notes: tuple[str, ...] = ()


class StatisticalValidator:
    agent_id = "A44"
    name = "Statistical Validator"
    kind = "code"

    def __init__(self, cfg: ValidationConfig) -> None:
        self.cfg = cfg

    def validate(
        self,
        returns: npt.ArrayLike,
        *,
        strategy: str,
        n_trials: int = 1,
        trial_matrix: npt.ArrayLike | None = None,
        stressed_returns: npt.ArrayLike | None = None,
        notes: Sequence[str] = (),
        seed: int = 0,
    ) -> ValidationReport:
        cfg = self.cfg
        r = clean_returns(returns)
        t_stat = newey_west_tstat(r)
        psr = probabilistic_sharpe_ratio(r)
        dsr = deflated_sharpe_ratio(r, n_trials)
        lo, hi = bootstrap_sharpe_interval(
            r, samples=cfg.bootstrap_samples, mean_block=cfg.bootstrap_mean_block, seed=seed
        )
        metrics = {
            "sharpe": sharpe_ratio(r),
            "sharpe_ci_low": lo,
            "sharpe_ci_high": hi,
            "newey_west_t": t_stat,
            "psr": psr,
            "dsr": dsr,
            "min_backtest_years_for_sharpe_1": min_backtest_length_years(n_trials, 1.0),
        }
        checks = [
            CheckResult(
                name="observations",
                passed=len(r) >= cfg.min_observations,
                detail=f"{len(r)} days (need {cfg.min_observations})",
            ),
            CheckResult(
                name="newey_west_t",
                passed=t_stat >= cfg.min_t_stat,
                detail=f"t = {t_stat:.2f} (need {cfg.min_t_stat:g})",
            ),
            CheckResult(
                name="psr",
                passed=psr >= cfg.min_psr,
                detail=f"PSR = {psr:.3f} (need {cfg.min_psr:g})",
            ),
            CheckResult(
                name="dsr",
                passed=dsr >= cfg.min_dsr,
                detail=f"DSR = {dsr:.3f} after {n_trials} trial(s) (need {cfg.min_dsr:g})",
            ),
        ]
        if trial_matrix is None:
            checks.append(
                CheckResult(
                    name="pbo",
                    passed=False,
                    detail="not run: needs the returns of every variant tried",
                )
            )
        else:
            pbo = pbo_cscv(trial_matrix)
            metrics["pbo"] = pbo
            checks.append(
                CheckResult(
                    name="pbo",
                    passed=pbo <= cfg.max_pbo,
                    detail=f"PBO = {pbo:.2f} (need <= {cfg.max_pbo:g})",
                )
            )
        if stressed_returns is None:
            checks.append(CheckResult(name="sharpe_at_2x_costs", passed=False, detail="not run"))
        else:
            stressed = sharpe_ratio(stressed_returns)
            metrics["sharpe_at_2x_costs"] = stressed
            checks.append(
                CheckResult(
                    name="sharpe_at_2x_costs",
                    passed=stressed > 0,
                    detail=f"Sharpe at 2x costs = {stressed:.2f} (need > 0)",
                )
            )
        passed = all(c.passed for c in checks)
        return ValidationReport(
            strategy=strategy,
            n_obs=len(r),
            n_trials=n_trials,
            metrics=metrics,
            checks=tuple(checks),
            passed=passed,
            verdict="PASS" if passed else "FAIL",
            notes=tuple(notes),
        )
