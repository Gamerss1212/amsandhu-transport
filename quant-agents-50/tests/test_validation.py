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
    # 1000 days: walk-forward windows of 500 in, 250 out give 2 folds
    validator = S.StatisticalValidator(ValidationConfig(wf_train_days=500, wf_test_days=250))
    rng = np.random.default_rng(11)
    variants = rng.normal(0.0, 0.01, (1000, 5))
    variants[:, 0] = GOOD
    report = validator.validate(
        GOOD,
        strategy="good",
        n_trials=5,
        trial_matrix=variants,
        stressed_returns=GOOD - 0.0005,
        trial_names=["good", "n1", "n2", "n3", "n4"],
        market_returns=NOISE,
    )
    assert report.verdict == "PASS", [c for c in report.checks if not c.passed]
    assert [f.chosen for f in report.folds] == ["good", "good"]
    assert [g.regime for g in report.regimes] == ["low vol", "mid vol", "high vol"]
    assert report.metrics["spa_p"] <= 0.05
    bad = validator.validate(NOISE, strategy="noise", notes=["synthetic"])
    assert bad.verdict == "FAIL" and not bad.passed
    failed = {c.name for c in bad.checks if not c.passed}
    assert {"pbo", "sharpe_at_2x_costs", "newey_west_t", "spa", "walk_forward"} <= failed
    assert bad.notes == ("synthetic",)
    one = validator.validate(GOOD, strategy="one", trial_matrix=GOOD)  # a single variant
    detail = {c.name: c.detail for c in one.checks}
    assert "2 or more" in detail["pbo"] and "Hansen SPA" in detail["spa"]
    short = S.StatisticalValidator(ValidationConfig()).validate(
        GOOD, strategy="short", trial_matrix=variants
    )
    assert "not run: needs 1008 days" in {c.name: c.detail for c in short.checks}["walk_forward"]


def test_spa_separates_luck_from_edge() -> None:
    rng = np.random.default_rng(5)
    noise = rng.normal(0.0, 0.01, (1500, 20))
    luck = S.spa_test(noise, samples=300, seed=1)
    assert luck.p_value > 0.10 and luck.n_models == 20
    assert luck.p_value_upper >= luck.p_value  # the White RC form is the conservative one
    edge = noise.copy()
    edge[:, 7] += 0.0015
    found = S.spa_test(edge, samples=300, seed=1)
    assert found.p_value < 0.01 and found.statistic > 3
    losers = S.spa_test(noise - 0.002, samples=200, seed=1)
    assert losers.statistic == 0.0 and losers.p_value == 1.0
    flat = S.spa_test(np.zeros((100, 2)), samples=50)  # never invested: no edge, no crash
    assert flat.p_value == 1.0
    assert S.spa_test(GOOD, samples=100).n_models == 1
    with pytest.raises(ValueError, match="30 periods"):
        S.spa_test(np.zeros((10, 2)))


def test_walk_forward_selection_reports_every_fold() -> None:
    rng = np.random.default_rng(9)
    m = rng.normal(0.0, 0.01, (1000, 3))
    m[:600, 1] += 0.003  # variant 1 shines early, then stops working
    folds = S.walk_forward_selection(m, ["a", "b", "c"], train=400, test=200)
    assert [(f.train_start, f.test_start, f.test_end) for f in folds] == [
        (0, 400, 600),
        (200, 600, 800),
        (400, 800, 1000),
    ]
    assert folds[0].chosen == "b" and folds[0].out_sample_sharpe > 1
    assert folds[1].chosen == "b" and folds[1].out_sample_sharpe < folds[1].in_sample_sharpe
    ratio = S.oos_is_ratio(folds)
    assert 0 < ratio < 1
    assert math.isnan(S.oos_is_ratio([]))
    losers = S.walk_forward_selection(-np.abs(m), ["a", "b", "c"], train=400, test=200)
    assert math.isnan(S.oos_is_ratio(losers))  # no positive in-sample Sharpe to compare with
    assert len(S.walk_forward_selection(m[:, 0], ["only"], train=400, test=200)) == 3
    with pytest.raises(ValueError, match="one name"):
        S.walk_forward_selection(m, ["a"], train=400, test=200)


def test_regime_split_uses_only_past_volatility() -> None:
    rng = np.random.default_rng(4)
    calm = rng.normal(0.0, 0.005, 400)
    wild = rng.normal(0.0, 0.03, 400)
    market = np.concatenate([calm, wild, calm])
    strategy = np.concatenate([np.full(400, 0.001), np.full(400, -0.002), np.full(400, 0.001)])
    regimes = S.regime_split(strategy, market)
    by = {g.regime: g for g in regimes}
    assert by["low vol"].annual_return > 0 > by["high vol"].annual_return
    assert sum(g.days for g in regimes) == len(market) - 63
    assert S.regime_split(strategy[:100], market[:100]) == []  # too short
    with pytest.raises(ValueError, match="same length"):
        S.regime_split(strategy, market[:-1])


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
