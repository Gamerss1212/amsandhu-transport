"""Feature library 1.1: ADX, efficiency ratio, channels, swings, spread and liquidity proxies.

Each function is checked against a slow, obvious reference and for causality.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from quantagents import features as F
from quantagents.market import FloatArray

RNG = np.random.default_rng(5)
N = 300
CLOSE: FloatArray = 100.0 * np.exp(np.cumsum(RNG.normal(0.0005, 0.012, N)))
OPEN: FloatArray = np.concatenate([[100.0], CLOSE[:-1] * np.exp(RNG.normal(0, 0.003, N - 1))])
HIGH: FloatArray = np.maximum(OPEN, CLOSE) * np.exp(np.abs(RNG.normal(0, 0.004, N)))
LOW: FloatArray = np.minimum(OPEN, CLOSE) * np.exp(-np.abs(RNG.normal(0, 0.004, N)))
VOLUME: FloatArray = RNG.lognormal(12.0, 0.3, N)


def _naive_wilder(x: list[float], n: int) -> list[float]:
    out = [math.nan] * len(x)
    value = sum(x[:n]) / n
    out[n - 1] = value
    for i in range(n, len(x)):
        value = (value * (n - 1) + x[i]) / n
        out[i] = value
    return out


def _naive_adx(h: FloatArray, lo: FloatArray, c: FloatArray, n: int) -> tuple[float, float, float]:
    tr, pdm, mdm = [], [], []
    for t in range(1, len(c)):
        up, down = h[t] - h[t - 1], lo[t - 1] - lo[t]
        pdm.append(up if up > down and up > 0 else 0.0)
        mdm.append(down if down > up and down > 0 else 0.0)
        tr.append(max(h[t] - lo[t], abs(h[t] - c[t - 1]), abs(lo[t] - c[t - 1])))
    s_tr, s_p, s_m = (_naive_wilder(x, n) for x in (tr, pdm, mdm))
    dx = []
    for a, b, rng_ in zip(s_p, s_m, s_tr, strict=True):
        if math.isnan(rng_):
            continue
        p, m = 100 * a / rng_, 100 * b / rng_
        dx.append(100 * abs(p - m) / (p + m) if p + m > 0 else 0.0)
    adx = _naive_wilder(dx, n)
    return 100 * s_p[-1] / s_tr[-1], 100 * s_m[-1] / s_tr[-1], adx[-1]


def test_adx_matches_wilder_reference() -> None:
    plus, minus, adx = F.directional_indicators(HIGH, LOW, CLOSE, 14)
    ref = _naive_adx(HIGH, LOW, CLOSE, 14)
    assert (plus[-1], minus[-1], adx[-1]) == pytest.approx(ref)
    assert F.adx(HIGH, LOW, CLOSE, 14)[-1] == pytest.approx(ref[2])
    assert 0 <= adx[-1] <= 100
    first = int(np.flatnonzero(np.isfinite(adx))[0])
    assert first == 2 * 14 - 1  # 14 bars for DI, then 14 DX values for the first ADX
    assert np.all(np.isnan(F.adx(HIGH[:10], LOW[:10], CLOSE[:10], 14)))


def test_adx_sees_a_clean_trend() -> None:
    t = np.arange(120.0)
    close = 100.0 + t
    high, low = close + 0.5, close - 0.5
    plus, minus, adx = F.directional_indicators(high, low, close, 14)
    assert adx[-1] > 90 and plus[-1] > minus[-1]
    flat = np.full(60, 100.0)
    assert F.adx(flat, flat, flat, 14)[-1] == 0.0


def test_efficiency_ratio() -> None:
    er = F.efficiency_ratio(CLOSE, 10)
    t = 200
    path = sum(abs(CLOSE[i] - CLOSE[i - 1]) for i in range(t - 9, t + 1))
    assert er[t] == pytest.approx(abs(CLOSE[t] - CLOSE[t - 10]) / path)
    assert math.isnan(er[9]) and math.isfinite(er[10])
    assert F.efficiency_ratio(np.arange(30.0), 10)[-1] == pytest.approx(1.0)
    zigzag = np.array([100.0, 101.0] * 15)
    assert F.efficiency_ratio(zigzag, 10)[-1] == 0.0
    assert F.efficiency_ratio(np.full(20, 5.0), 10)[-1] == 0.0


def test_prior_channel_excludes_today() -> None:
    upper, lower = F.prior_channel(HIGH, LOW, 20)
    t = 150
    assert upper[t] == np.max(HIGH[t - 20 : t]) and lower[t] == np.min(LOW[t - 20 : t])
    assert math.isnan(upper[19]) and math.isfinite(upper[20])
    up2, _ = F.prior_channel(HIGH[:5], LOW[:5], 20)
    assert np.all(np.isnan(up2))


def test_swing_points_are_confirmed_k_bars_later() -> None:
    high = np.array([1, 2, 3, 9, 3, 2, 1, 2, 3, 4, 10, 4, 3, 2, 1, 8], dtype=float)
    low = high - 0.5
    highs, lows = F.swing_points(high, low, k=3)
    assert highs == [3, 10]
    assert lows == [6]
    # Bar 15 (value 8) cannot be a swing high yet: it needs 3 more bars to confirm it.
    for end in range(8, len(high) + 1):
        h, lo = F.swing_points(high[:end], low[:end], k=3)
        assert all(i + 3 <= end - 1 for i in h + lo)
    with pytest.raises(ValueError):
        F.swing_points(high, low, k=0)
    plateau = np.array([1, 2, 5, 5, 2, 1, 0, 1], dtype=float)
    assert F.swing_points(plateau, plateau, k=2)[0] == [2]  # one swing, not two


def _naive_cs(h: FloatArray, lo: FloatArray, c: FloatArray, t: int) -> float:
    h1, l1 = h[t], lo[t]
    gap = max(lo[t] - c[t - 1], 0.0) - max(c[t - 1] - h[t], 0.0)
    h1, l1 = h1 - gap, l1 - gap
    beta = math.log(h1 / l1) ** 2 + math.log(h[t - 1] / lo[t - 1]) ** 2
    gamma = math.log(max(h[t - 1], h1) / min(lo[t - 1], l1)) ** 2
    k = 3 - 2 * math.sqrt(2)
    alpha = (math.sqrt(2 * beta) - math.sqrt(beta)) / k - math.sqrt(gamma / k)
    return max(2 * (math.exp(alpha) - 1) / (1 + math.exp(alpha)), 0.0)


def test_corwin_schultz_matches_formula() -> None:
    est = F.corwin_schultz_spread(HIGH, LOW, CLOSE, 20)
    t = 250
    expected = np.mean([_naive_cs(HIGH, LOW, CLOSE, i) for i in range(t - 19, t + 1)])
    assert est[t] == pytest.approx(expected)
    assert math.isnan(est[19]) and math.isfinite(est[20]) and est[20] >= 0
    assert np.all(np.isnan(F.corwin_schultz_spread(HIGH[:10], LOW[:10], CLOSE[:10], 20)))


def test_abdi_ranaldo_matches_formula() -> None:
    est = F.abdi_ranaldo_spread(HIGH, LOW, CLOSE, 20)
    t = 250
    c, eta = np.log(CLOSE), (np.log(HIGH) + np.log(LOW)) / 2
    terms = [(c[i] - eta[i]) * (c[i] - eta[i + 1]) for i in range(t - 20, t)]
    assert est[t] == pytest.approx(math.sqrt(max(4 * float(np.mean(terms)), 0.0)))
    assert math.isnan(est[19]) and math.isfinite(est[20])
    assert np.all(np.isnan(F.abdi_ranaldo_spread(HIGH[:10], LOW[:10], CLOSE[:10], 20)))


def test_amihud() -> None:
    est = F.amihud_illiquidity(CLOSE, VOLUME, 20)
    t = 200
    ratios = [
        abs(CLOSE[i] / CLOSE[i - 1] - 1) / (CLOSE[i] * VOLUME[i]) * 1e6
        for i in range(t - 19, t + 1)
    ]
    assert est[t] == pytest.approx(np.mean(ratios))
    one_gap = VOLUME.copy()
    one_gap[t] = 0.0  # a day without trading is skipped, not treated as perfectly liquid
    assert F.amihud_illiquidity(CLOSE, one_gap, 20)[t] == pytest.approx(np.mean(ratios[:-1]))
    mostly_idle = VOLUME.copy()
    mostly_idle[t - 15 : t + 1] = 0.0  # only 4 of 20 days traded: cannot be measured
    assert math.isnan(F.amihud_illiquidity(CLOSE, mostly_idle, 20)[t])
    assert np.all(np.isnan(F.amihud_illiquidity(CLOSE[:10], VOLUME[:10], 20)))


@pytest.mark.parametrize("t", [60, 150, 298])
def test_new_features_are_causal(t: int) -> None:
    scale = np.ones(N)
    scale[t + 1 :] = 1.7

    def run_all(h: FloatArray, lo: FloatArray, c: FloatArray, v: FloatArray) -> list[FloatArray]:
        p, m, a = F.directional_indicators(h, lo, c, 14)
        up, dn = F.prior_channel(h, lo, 20)
        return [
            p,
            m,
            a,
            F.efficiency_ratio(c, 10),
            up,
            dn,
            F.corwin_schultz_spread(h, lo, c, 20),
            F.abdi_ranaldo_spread(h, lo, c, 20),
            F.amihud_illiquidity(c, v, 20),
        ]

    full = run_all(HIGH, LOW, CLOSE, VOLUME)
    changed = run_all(
        HIGH * scale, LOW * scale, CLOSE * scale, VOLUME * scale * 2.0 ** (np.arange(N) > t)
    )
    for a, b in zip(full, changed, strict=True):
        assert np.array_equal(
            np.nan_to_num(a[: t + 1], nan=-1.0), np.nan_to_num(b[: t + 1], nan=-1.0)
        )
    h1, l1 = F.swing_points(HIGH[: t + 1], LOW[: t + 1])
    h2, l2 = F.swing_points((HIGH * scale)[: t + 1], (LOW * scale)[: t + 1])
    assert (h1, l1) == (h2, l2)
