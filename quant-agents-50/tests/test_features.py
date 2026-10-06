from __future__ import annotations

import math

import numpy as np
import pytest

from quantagents import features as F
from quantagents.market import FloatArray, MarketData

RNG = np.random.default_rng(1)
CLOSE: FloatArray = 100.0 * np.exp(np.cumsum(RNG.normal(0, 0.01, 400)))
HIGH: FloatArray = CLOSE * 1.01
LOW: FloatArray = CLOSE * 0.99


def _naive_wilder(x: list[float], n: int) -> list[float]:
    out = [math.nan] * len(x)
    value = sum(x[:n]) / n
    out[n - 1] = value
    for i in range(n, len(x)):
        value = (value * (n - 1) + x[i]) / n
        out[i] = value
    return out


def test_sma_std_max_min_match_naive() -> None:
    n = 20
    assert F.sma(CLOSE, n)[-1] == pytest.approx(np.mean(CLOSE[-n:]))
    assert F.rolling_std(CLOSE, n)[-1] == pytest.approx(np.std(CLOSE[-n:], ddof=1))
    assert F.rolling_max(CLOSE, n)[-1] == np.max(CLOSE[-n:])
    assert F.rolling_min(CLOSE, n)[-1] == np.min(CLOSE[-n:])
    assert math.isnan(F.sma(CLOSE, n)[n - 2])
    assert np.all(np.isnan(F.sma(CLOSE[:5], 10)))
    with pytest.raises(ValueError):
        F.sma(CLOSE, 0)
    with pytest.raises(ValueError):
        F.rolling_std(CLOSE, 1)


def test_ema_and_wilder_recursions() -> None:
    e = F.ema(CLOSE, 10)
    alpha = 2 / 11
    assert e[10] == pytest.approx(alpha * CLOSE[10] + (1 - alpha) * e[9])
    assert np.allclose(F.wilder(CLOSE, 14)[13:], _naive_wilder(list(CLOSE), 14)[13:])
    assert np.all(np.isnan(F.ema(CLOSE[:3], 5)))


def test_rsi_matches_naive_wilder() -> None:
    delta = np.diff(CLOSE)
    gains = _naive_wilder(list(np.clip(delta, 0, None)), 14)
    losses = _naive_wilder(list(np.clip(-delta, 0, None)), 14)
    expected = 100 - 100 / (1 + gains[-1] / losses[-1])
    assert F.rsi(CLOSE, 14)[-1] == pytest.approx(expected)
    rising = np.arange(1.0, 40.0)
    assert F.rsi(rising, 14)[-1] == 100.0
    assert F.rsi(np.full(30, 5.0), 14)[-1] == 50.0
    assert np.all(np.isnan(F.rsi(CLOSE[:10], 14)))


def test_atr_true_range_and_returns() -> None:
    tr = F.true_range(HIGH, LOW, CLOSE)
    assert tr[0] == pytest.approx(HIGH[0] - LOW[0])
    i = 50
    assert tr[i] == pytest.approx(
        max(HIGH[i] - LOW[i], abs(HIGH[i] - CLOSE[i - 1]), abs(LOW[i] - CLOSE[i - 1]))
    )
    assert F.atr(HIGH, LOW, CLOSE, 14)[-1] > 0
    assert len(F.true_range(HIGH[:0], LOW[:0], CLOSE[:0])) == 0
    r = F.log_returns(CLOSE)
    assert math.isnan(r[0]) and r[1] == pytest.approx(math.log(CLOSE[1] / CLOSE[0]))


def test_momentum_zscore_ibs_channel() -> None:
    assert F.momentum(CLOSE, 21)[-1] == pytest.approx(CLOSE[-1] / CLOSE[-22] - 1)
    assert F.momentum(CLOSE, 252, 21)[-1] == pytest.approx(CLOSE[-22] / CLOSE[-253] - 1)
    with pytest.raises(ValueError):
        F.momentum(CLOSE, 10, 10)
    z = F.zscore(CLOSE, 20)[-1]
    assert z == pytest.approx((CLOSE[-1] - np.mean(CLOSE[-20:])) / np.std(CLOSE[-20:], ddof=1))
    assert math.isnan(F.zscore(np.full(30, 1.0), 20)[-1])
    flat = np.full(5, 10.0)
    assert np.all(F.ibs(flat, flat, flat) == 0.5)
    assert F.ibs(np.array([12.0]), np.array([10.0]), np.array([11.5]))[0] == pytest.approx(0.75)
    pos = F.channel_position(HIGH, LOW, CLOSE, 55)
    assert -1.0 <= pos[-1] <= 1.0
    assert F.channel_position(flat, flat, flat, 3)[-1] == 0.0


def test_ewma_vol() -> None:
    r = F.log_returns(CLOSE)
    vol = F.ewma_vol(r)
    assert 0.005 < vol[-1] < 0.02
    assert np.all(np.isnan(F.ewma_vol(r[:10])))
    with pytest.raises(ValueError):
        F.ewma_vol(r, lam=1.0)


@pytest.mark.parametrize("t", [100, 250, 399])
def test_features_are_causal(t: int) -> None:
    changed = CLOSE.copy()
    changed[t + 1 :] *= 3.0

    def run_all(x: FloatArray) -> list[FloatArray]:
        return [F.sma(x, 20), F.rsi(x, 14), F.ema(x, 30), F.momentum(x, 63)]

    for full, altered in zip(run_all(CLOSE), run_all(changed), strict=True):
        a, b = full[: t + 1], altered[: t + 1]
        assert np.array_equal(np.nan_to_num(a, nan=-1.0), np.nan_to_num(b, nan=-1.0))


def test_symbol_features_are_finite(market: MarketData) -> None:
    values = F.symbol_features(market.view(market.dates[-1]), "SYN_A")
    assert {"mom_12_1", "sma_200", "rsi_2", "atr_14", "channel_55"} <= set(values)
    assert all(math.isfinite(v) for v in values.values())
    early = F.symbol_features(market.view(market.dates[30]), "SYN_A")
    assert "sma_200" not in early and "rsi_14" in early
    assert F.symbol_features(market.view(market.dates[0]), "SYN_A") == {}
    assert math.isnan(F.last_value(np.array([])))
