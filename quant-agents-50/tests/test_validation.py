from __future__ import annotations

import math
from collections.abc import Mapping

import numpy as np
import pytest

from quantagents.backtest.engine import Strategy
from quantagents.backtest.strategies import tsmom
from quantagents.config import ValidationConfig
from quantagents.market import MarketData, MarketView
from quantagents.validation import stats as S
from quantagents.validation.leakage import RedTeamAuditor, perturb_future

RNG = np.random.default_rng(7)
NOISE = RNG.normal(0.0, 0.01, 1000)
GOOD = RNG.normal(0.002, 0.01, 1000)


def test_sharpe_and_newey_west() -> None:
    assert S.sharpe_ratio(GOOD) > 2.0
    assert S.sharpe_ratio(np.zeros(10)) == 0.0
    classic = np.mean(NOISE) / (np.std(NOISE, ddof=0) / math.sqrt(len(NOISE)))
    assert S.newey_west_tstat(NOISE, lags=0) == pytest.approx(classic)
    assert S.newey_west_tstat(GOOD) > 3.0
    assert S.newey_west_tstat(np.zeros(10)) == 0.0
    with pytest.raises(ValueError):
        S.clean_returns([1.0, float("nan")])
    with pytest.raises(ValueError):
        S.clean_returns(np.zeros((2, 2)))


def test_psr_dsr_and_minimum_backtest_length() -> None:
    assert S.probabilistic_sharpe_ratio(GOOD) > 0.99
    assert S.probabilistic_sharpe_ratio(-GOOD) < 0.01
    assert S.probabilistic_sharpe_ratio(np.zeros(10)) == 0.0
    assert S.deflated_sharpe_ratio(GOOD, 1) == pytest.approx(S.probabilistic_sharpe_ratio(GOOD))
    assert S.deflated_sharpe_ratio(NOISE, 100) < S.probabilistic_sharpe_ratio(NOISE)
    assert S.expected_max_sharpe(1, 1.0) == 0.0
    assert S.expected_max_sharpe(1000, 1.0) > S.expected_max_sharpe(10, 1.0) > 0
    assert S.min_backtest_length_years(1, 1.0) == 0.0
    assert S.min_backtest_length_years(45, 1.0) == pytest.approx(
        5.0, abs=0.2
    )  # Bailey et al. (2014): ~5 years
    with pytest.raises(ValueError):
        S.min_backtest_length_years(10, 0.0)


def test_pbo_separates_noise_from_real_skill() -> None:
    rng = np.random.default_rng(3)
    noise = rng.normal(0.0, 0.01, (800, 10))
    assert 0.25 < S.pbo_cscv(noise) < 0.85
    skilled = noise.copy()
    skilled[:, 0] += 0.004
    assert S.pbo_cscv(skilled) < 0.05
    with pytest.raises(ValueError):
        S.pbo_cscv(noise[:, :1])
    with pytest.raises(ValueError):
        S.pbo_cscv(noise, n_splits=7)


def test_benjamini_hochberg() -> None:
    assert S.benjamini_hochberg(
        [0.001, 0.008, 0.039, 0.041, 0.042, 0.06, 0.074, 0.205], q=0.05
    ) == [True, True, False, False, False, False, False, False]
    assert S.benjamini_hochberg([0.5, 0.9]) == [False, False]
    assert S.benjamini_hochberg([]) == []


def test_bootstrap_is_seeded_and_in_range() -> None:
    idx = S.stationary_bootstrap_indices(50, 5.0, np.random.default_rng(0))
    assert int(np.min(idx)) >= 0 and int(np.max(idx)) < 50
    a = S.bootstrap_sharpe_interval(GOOD, samples=100, mean_block=10, seed=1)
    assert a == S.bootstrap_sharpe_interval(GOOD, samples=100, mean_block=10, seed=1)
    assert a[0] < S.sharpe_ratio(GOOD) < a[1]
    assert S.bootstrap_sharpe_interval(np.zeros(20), samples=10, mean_block=5) == (0.0, 0.0)


def test_splits_never_leak() -> None:
    for train, test in S.walk_forward_splits(100, 40, 20):
        assert max(train) < min(test)
    anchored = S.walk_forward_splits(100, 40, 20, anchored=True)
    assert all(train.start == 0 for train, _ in anchored) and len(anchored) == 3
    with pytest.raises(ValueError):
        S.walk_forward_splits(100, 0, 10)
    for kept, fold in S.purged_kfold_splits(100, 5, embargo=3):
        assert not set(kept.tolist()) & set(range(int(fold[0]) - 3, int(fold[-1]) + 4))
    with pytest.raises(ValueError):
        S.purged_kfold_splits(3, 5, 1)


def test_validator_pass_and_fail() -> None:
    validator = S.StatisticalValidator(ValidationConfig())
    rng = np.random.default_rng(11)
    variants = rng.normal(0.0, 0.01, (1000, 5))
    variants[:, 0] = GOOD
    report = validator.validate(
        GOOD, strategy="good", n_trials=5, trial_matrix=variants, stressed_returns=GOOD - 0.0005
    )
    assert report.verdict == "PASS", [c for c in report.checks if not c.passed]
    bad = validator.validate(NOISE, strategy="noise", notes=["synthetic"])
    assert bad.verdict == "FAIL" and not bad.passed
    failed = {c.name for c in bad.checks if not c.passed}
    assert {"pbo", "sharpe_at_2x_costs", "newey_west_t"} <= failed
    assert bad.notes == ("synthetic",)


def test_red_team_passes_causal_strategies(market: MarketData) -> None:
    report = RedTeamAuditor(probes=2, window=5).audit(tsmom(63), market, name="tsmom_63")
    assert report.passed and report.findings == ()


def full_sample_normalized(market: MarketData) -> Strategy:
    """Classic leak: uses each symbol's whole-history mean return, including the future."""
    means = {s: float(np.mean(np.diff(np.log(market.bars(s).close)))) for s in market.symbols}

    def strategy(view: MarketView) -> Mapping[str, float]:
        return {s: 0.1 / (1.0 + math.exp(-1000.0 * means[s])) for s in view.symbols}

    return strategy


def test_red_team_catches_look_ahead(market: MarketData) -> None:
    report = RedTeamAuditor(probes=2, window=3).audit(full_sample_normalized, market, name="leaky")
    assert not report.passed
    assert any(
        f.severity == "critical" and f.test == "future_perturbation" for f in report.findings
    )


def test_red_team_flags_randomness_and_bounds(market: MarketData) -> None:
    rng = np.random.default_rng()

    def noisy(market: MarketData) -> Strategy:
        return lambda view: {"SYN_A": float(rng.random()) * 0.1}

    report = RedTeamAuditor(probes=1, window=2).audit(noisy, market, name="noisy")
    assert any(f.test == "determinism" for f in report.findings)
    for weights, label in (
        ({"SYN_A": 2.0}, "gross"),
        ({"SYN_A": -0.5}, "short"),
        ({"SYN_A": float("inf")}, "non-finite"),
    ):
        fixed = dict(weights)

        def factory(market: MarketData, fixed: dict[str, float] = fixed) -> Strategy:
            return lambda view: fixed

        found = RedTeamAuditor(probes=1, window=1).audit(factory, market, name=label).findings
        assert any(label in f.detail for f in found), (label, found)


def test_perturb_future_keeps_the_past(market: MarketData) -> None:
    t = 400
    changed = perturb_future(market, t, seed=1)
    for s in market.symbols:
        assert np.array_equal(changed.bars(s).close[: t + 1], market.bars(s).close[: t + 1])
        assert not np.array_equal(changed.bars(s).close[t + 1 :], market.bars(s).close[t + 1 :])
