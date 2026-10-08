"""Portfolio construction and execution-algorithm arithmetic."""

from decimal import Decimal as D

import numpy as np

from tradingai.execution import algos
from tradingai.portfolio import optimize as P


def returns(n=500, k=4, seed=3):
    rng = np.random.default_rng(seed)
    vols = np.array([0.01, 0.02, 0.03, 0.015])[:k]
    common = rng.normal(0, 0.006, n)
    return rng.normal(0, 1, (n, k)) * vols + common[:, None]


def test_weights_are_long_only_and_sum_to_one():
    X = returns()
    for w in (P.inverse_vol(X), P.risk_parity(P.ledoit_wolf(X)[0]), P.min_variance(P.ledoit_wolf(X)[0]), P.hrp(X)):
        assert np.all(w >= -1e-12) and abs(w.sum() - 1) < 1e-9


def test_risk_parity_equalizes_risk_contributions():
    cov = P.ledoit_wolf(returns())[0]
    w = P.risk_parity(cov)
    rc = w * (cov @ w)
    assert rc.max() / rc.min() < 1.05


def test_lower_vol_gets_more_weight_in_inverse_vol():
    w = P.inverse_vol(returns())
    assert w[0] > w[3] > w[1] > w[2]                       # vols 1% < 1.5% < 2% < 3%


def test_ledoit_wolf_is_positive_definite():
    cov, shrink = P.ledoit_wolf(returns(n=60))
    assert 0 <= shrink <= 1 and np.all(np.linalg.eigvalsh(cov) > 0)


def test_twap_and_vwap_split_exactly():
    assert algos.twap(D(10), 3) == [D(3), D(3), D(4)]
    parts = algos.vwap(D("1.0"), {0: 0.2, 1: 0.5, 2: 0.3}, [0, 1, 2], step=D("0.01"))
    assert sum(parts) == D("1.0") and parts[1] == D("0.5")


def test_pov_never_exceeds_remaining_or_rate():
    assert algos.pov(D(100), 0.1, 2_000) == D(100)          # 10% of 2000 = 200, capped at what is left
    assert algos.pov(D(100), 0.1, 555) == D(55)             # rounded down to the step
    assert algos.pov(D(100), 0.1, 0) == D(0)


def test_limit_with_timeout():
    r = algos.limit_with_timeout("buy", D(100), 10, bars_waited=0, timeout_bars=3)
    assert r["action"] == "limit" and r["price"] == D("99.9")
    assert algos.limit_with_timeout("buy", D(100), 10, 3, 3)["action"] == "market"
    assert algos.limit_with_timeout("sell", D(100), 10, 3, 3, on_timeout="cancel")["action"] == "cancel"
