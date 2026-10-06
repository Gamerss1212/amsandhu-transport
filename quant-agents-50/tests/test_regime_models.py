from __future__ import annotations

import math

import numpy as np
import pytest

from quantagents import regime_models as R
from tests.helpers import regime_market


def test_mixture_separates_calm_and_turbulent_days() -> None:
    rng = np.random.default_rng(0)
    x = np.concatenate([rng.normal(0, 0.01, 400), rng.normal(0, 0.03, 200)])
    m = R.fit_two_state_mixture(x)
    assert m.variances[0] < m.variances[1]  # index 0 is the calm component
    assert math.sqrt(m.variances[0]) == pytest.approx(0.01, rel=0.25)
    assert math.sqrt(m.variances[1]) == pytest.approx(0.03, rel=0.25)
    assert m.variance_ratio > 4 and sum(m.weights) == pytest.approx(1.0)
    assert m.bic_prefers_two and m.n_obs == 600
    # EM always "finds" two components, even in one bell curve; BIC says they are not real.
    false_alarms = sum(
        R.fit_two_state_mixture(np.random.default_rng(s).normal(0, 0.01, 500)).bic_prefers_two
        for s in range(20)
    )
    assert false_alarms <= 2
    with pytest.raises(ValueError, match="10 finite"):
        R.fit_two_state_mixture(np.ones(5))
    with pytest.raises(ValueError, match="zero variance"):
        R.fit_two_state_mixture(np.ones(50))


def test_mixture_is_deterministic() -> None:
    x = np.random.default_rng(1).standard_t(4, 300) * 0.01
    assert R.fit_two_state_mixture(x) == R.fit_two_state_mixture(x.copy())


def test_sticky_filter_tracks_regimes_and_is_causal() -> None:
    rng = np.random.default_rng(2)
    x = np.concatenate([rng.normal(0, 0.01, 300), rng.normal(0, 0.035, 60)])
    m = R.fit_two_state_mixture(x)
    p = R.sticky_filter(x, m)
    assert np.mean(p[100:290]) < 0.2 and np.mean(p[320:]) > 0.8
    changed = x.copy()
    changed[200:] *= 5.0
    assert np.array_equal(R.sticky_filter(changed, m)[:200], p[:200])  # forward-only
    with_gap = x.copy()
    with_gap[50] = np.nan
    gap = R.sticky_filter(with_gap, m)
    assert math.isfinite(gap[50])
    with pytest.raises(ValueError):
        R.sticky_filter(x, m, stay=1.0)


def test_bocpd_finds_a_volatility_shift_but_not_noise() -> None:
    calm_alarms = 0
    for seed in range(20):
        calm = np.random.default_rng(seed).normal(0, 0.01, 252)
        calm_alarms += R.bocpd_run_length(calm, hazard=1 / 500, recent=30).p_recent_change >= 0.5
    assert calm_alarms <= 2  # about 0-3% false alarms when tuned this way
    found = 0
    for seed in range(20):
        rng = np.random.default_rng(100 + seed)
        shifted = np.concatenate([rng.normal(0, 0.01, 232), rng.normal(0, 0.025, 20)])
        result = R.bocpd_run_length(shifted, hazard=1 / 500, recent=30)
        found += result.p_recent_change >= 0.5
    assert found >= 14  # most 2.5x volatility shifts are caught within 20 bars


def test_bocpd_rarely_mistakes_one_outlier_day_for_a_new_regime() -> None:
    flips = 0
    for seed in range(30):
        calm = np.random.default_rng(seed).normal(0, 0.01, 252)
        before = R.bocpd_run_length(calm, hazard=1 / 500, recent=30).p_recent_change
        spiked = calm.copy()
        spiked[240] = 0.12  # a 12-sigma day, clipped to 4 sigma before the model sees it
        after = R.bocpd_run_length(spiked, hazard=1 / 500, recent=30).p_recent_change
        flips += before < 0.5 <= after
    assert flips <= 2
    x = np.random.default_rng(1).normal(0, 0.01, 100)
    with pytest.raises(ValueError):
        R.bocpd_run_length(x, hazard=0.0)
    with pytest.raises(ValueError):
        R.bocpd_run_length(x[:10])
    constant = np.full(100, 0.001)
    assert 0.0 <= R.bocpd_run_length(constant).p_recent_change <= 1.0


def test_average_correlation_and_returns() -> None:
    rng = np.random.default_rng(3)
    common = rng.standard_normal(200)
    m = np.column_stack([common + 0.1 * rng.standard_normal(200) for _ in range(3)])
    assert R.average_correlation(m) > 0.95
    assert math.isnan(R.average_correlation(m[:, :1]))
    assert math.isnan(R.average_correlation(m[:2]))
    flat = np.column_stack([np.ones(10), np.ones(10), rng.standard_normal(10)])
    assert math.isnan(R.average_correlation(flat))
    market = regime_market(n=60)
    view = market.view(market.dates[-1])
    matrix = R.return_matrix(view, market.symbols, 20)
    assert matrix.shape == (20, 4) and np.all(np.isfinite(matrix))
    assert R.return_matrix(view, (), 20).size == 0
    assert len(R.market_returns(view, market.symbols, 20)) == 20
    assert len(R.market_returns(view, (), 20)) == 0
    short = R.return_matrix(market.view(market.dates[3]), market.symbols, 20)
    assert np.isnan(short[0, 0]) and np.isfinite(short[-1, 0])  # padded at the front
    with pytest.raises(ValueError):
        R.return_matrix(view, market.symbols, 0)
