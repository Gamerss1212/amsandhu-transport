"""Causal technical features (Appendix B). Owned by A03, the Feature Factory.

Every function returns an array of the same length as its input. Position ``t`` depends
only on inputs at positions ``<= t``; warm-up positions are NaN. tests/test_features.py
checks each function against a slow reference and checks causality.
"""

from __future__ import annotations

import math

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

from quantagents.market import FloatArray, MarketView

FEATURE_VERSION = "1.1"  # 1.1 adds ADX, +DI/-DI and efficiency ratios
FEATURE_TAIL = 320  # bars used per computation; covers the longest lookback (252) plus warm-up


def _nan(n: int) -> FloatArray:
    return np.full(n, np.nan, dtype=np.float64)


def _check_window(n: int) -> None:
    if n < 1:
        raise ValueError("window must be >= 1")


def sma(x: FloatArray, n: int) -> FloatArray:
    """Simple moving average."""
    _check_window(n)
    out = _nan(len(x))
    if len(x) >= n:
        out[n - 1 :] = sliding_window_view(x, n).mean(axis=1)
    return out


def rolling_std(x: FloatArray, n: int, ddof: int = 1) -> FloatArray:
    """Rolling standard deviation (sample by default)."""
    if n <= ddof:
        raise ValueError("window must be larger than ddof")
    out = _nan(len(x))
    if len(x) >= n:
        out[n - 1 :] = sliding_window_view(x, n).std(axis=1, ddof=ddof)
    return out


def rolling_max(x: FloatArray, n: int) -> FloatArray:
    _check_window(n)
    out = _nan(len(x))
    if len(x) >= n:
        out[n - 1 :] = sliding_window_view(x, n).max(axis=1)
    return out


def rolling_min(x: FloatArray, n: int) -> FloatArray:
    _check_window(n)
    out = _nan(len(x))
    if len(x) >= n:
        out[n - 1 :] = sliding_window_view(x, n).min(axis=1)
    return out


def _recursive_average(x: FloatArray, n: int, alpha: float) -> FloatArray:
    """Exponential smoothing seeded with the simple average of the first n values."""
    out = _nan(len(x))
    if len(x) < n:
        return out
    value = float(np.mean(x[:n]))
    out[n - 1] = value
    for i in range(n, len(x)):
        value = alpha * float(x[i]) + (1.0 - alpha) * value
        out[i] = value
    return out


def ema(x: FloatArray, n: int) -> FloatArray:
    """Exponential moving average, alpha = 2 / (n + 1)."""
    _check_window(n)
    return _recursive_average(x, n, 2.0 / (n + 1.0))


def wilder(x: FloatArray, n: int) -> FloatArray:
    """Wilder's smoothing (RMA), alpha = 1 / n. Used by RSI and ATR."""
    _check_window(n)
    return _recursive_average(x, n, 1.0 / n)


def log_returns(close: FloatArray) -> FloatArray:
    out = _nan(len(close))
    if len(close) > 1:
        out[1:] = np.diff(np.log(close))
    return out


def momentum(close: FloatArray, lookback: int, skip: int = 0) -> FloatArray:
    """close[t - skip] / close[t - lookback] - 1. Use skip=21 for 12-1 momentum."""
    if lookback < 1 or not 0 <= skip < lookback:
        raise ValueError("need lookback >= 1 and 0 <= skip < lookback")
    out = _nan(len(close))
    if len(close) > lookback:
        t = np.arange(lookback, len(close))
        out[lookback:] = close[t - skip] / close[t - lookback] - 1.0
    return out


def rsi(close: FloatArray, n: int = 14) -> FloatArray:
    """Wilder's relative strength index, 0-100."""
    _check_window(n)
    out = _nan(len(close))
    if len(close) <= n:
        return out
    delta = np.diff(close)
    avg_gain = wilder(np.clip(delta, 0.0, None), n)
    avg_loss = wilder(np.clip(-delta, 0.0, None), n)
    values = _nan(len(delta))
    for i in range(len(delta)):
        gain, loss = float(avg_gain[i]), float(avg_loss[i])
        if math.isnan(gain) or math.isnan(loss):
            continue
        if loss == 0.0:
            values[i] = 50.0 if gain == 0.0 else 100.0
        else:
            values[i] = 100.0 - 100.0 / (1.0 + gain / loss)
    out[1:] = values
    return out


def true_range(high: FloatArray, low: FloatArray, close: FloatArray) -> FloatArray:
    out = _nan(len(close))
    if len(close) == 0:
        return out
    out[0] = high[0] - low[0]
    if len(close) > 1:
        prev = close[:-1]
        out[1:] = np.maximum(
            np.maximum(high[1:] - low[1:], np.abs(high[1:] - prev)), np.abs(low[1:] - prev)
        )
    return out


def atr(high: FloatArray, low: FloatArray, close: FloatArray, n: int = 14) -> FloatArray:
    """Average true range (Wilder)."""
    return wilder(true_range(high, low, close), n)


def zscore(x: FloatArray, n: int) -> FloatArray:
    mean = sma(x, n)
    std = rolling_std(x, n)
    out = _nan(len(x))
    ok = np.isfinite(std) & (std > 0)
    out[ok] = (x[ok] - mean[ok]) / std[ok]
    return out


def ibs(high: FloatArray, low: FloatArray, close: FloatArray) -> FloatArray:
    """Internal bar strength: where the close sits inside the day's range (0-1)."""
    rng = high - low
    out = np.full(len(close), 0.5, dtype=np.float64)
    ok = rng > 0
    out[ok] = (close[ok] - low[ok]) / rng[ok]
    return out


def channel_position(high: FloatArray, low: FloatArray, close: FloatArray, n: int) -> FloatArray:
    """Position of the close inside the n-bar Donchian channel, scaled to [-1, 1]."""
    hi = rolling_max(high, n)
    lo = rolling_min(low, n)
    out = _nan(len(close))
    width = hi - lo
    ok = np.isfinite(width) & (width > 0)
    out[ok] = 2.0 * (close[ok] - lo[ok]) / width[ok] - 1.0
    flat = np.isfinite(width) & (width == 0)
    out[flat] = 0.0
    return out


def ewma_vol(returns: FloatArray, lam: float = 0.94, seed_window: int = 20) -> FloatArray:
    """RiskMetrics EWMA volatility of returns (same units as the returns)."""
    if not 0.0 < lam < 1.0:
        raise ValueError("lam must be in (0, 1)")
    out = _nan(len(returns))
    finite = np.flatnonzero(np.isfinite(returns))
    if len(finite) < seed_window:
        return out
    start = int(finite[seed_window - 1])
    variance = float(np.mean(returns[finite[:seed_window]] ** 2))
    out[start] = math.sqrt(variance)
    for i in range(start + 1, len(returns)):
        r = float(returns[i])
        if math.isfinite(r):
            variance = lam * variance + (1.0 - lam) * r * r
        out[i] = math.sqrt(variance)
    return out


def _wilder_from_first_finite(x: FloatArray, n: int) -> FloatArray:
    """Wilder smoothing that starts at the first finite value (skips a NaN warm-up)."""
    out = _nan(len(x))
    finite = np.flatnonzero(np.isfinite(x))
    if len(finite) == 0:
        return out
    start = int(finite[0])
    out[start:] = wilder(np.ascontiguousarray(x[start:]), n)
    return out


def directional_indicators(
    high: FloatArray, low: FloatArray, close: FloatArray, n: int = 14
) -> tuple[FloatArray, FloatArray, FloatArray]:
    """Wilder's +DI, -DI and ADX (all 0-100). ADX above about 25 means a trending market.

    +DM = up-move when it beats the down-move, -DM the reverse; both are smoothed with the
    true range, and ADX is the Wilder average of DX = 100 |+DI - -DI| / (+DI + -DI).
    """
    _check_window(n)
    size = len(close)
    plus_di, minus_di, adx_out = _nan(size), _nan(size), _nan(size)
    if size <= n:
        return plus_di, minus_di, adx_out
    up = high[1:] - high[:-1]
    down = low[:-1] - low[1:]
    plus_dm = np.where((up > down) & (up > 0), up, 0.0)
    minus_dm = np.where((down > up) & (down > 0), down, 0.0)
    tr = true_range(high, low, close)[1:]
    s_tr = wilder(np.ascontiguousarray(tr), n)
    s_plus = wilder(np.ascontiguousarray(plus_dm), n)
    s_minus = wilder(np.ascontiguousarray(minus_dm), n)
    p_di, m_di = _nan(size - 1), _nan(size - 1)
    known = np.isfinite(s_tr)
    p_di[known], m_di[known] = 0.0, 0.0  # no range at all: no direction either
    ok = known & (s_tr > 0)
    p_di[ok] = 100.0 * s_plus[ok] / s_tr[ok]
    m_di[ok] = 100.0 * s_minus[ok] / s_tr[ok]
    total = p_di + m_di
    dx = _nan(size - 1)
    has = np.isfinite(total)
    dx[has] = 0.0
    pos = has & (total > 0)
    dx[pos] = 100.0 * np.abs(p_di[pos] - m_di[pos]) / total[pos]
    plus_di[1:], minus_di[1:] = p_di, m_di
    adx_out[1:] = _wilder_from_first_finite(dx, n)
    return plus_di, minus_di, adx_out


def adx(high: FloatArray, low: FloatArray, close: FloatArray, n: int = 14) -> FloatArray:
    """Average directional index (trend strength, 0-100; direction-free)."""
    return directional_indicators(high, low, close, n)[2]


def efficiency_ratio(close: FloatArray, n: int = 10) -> FloatArray:
    """Kaufman efficiency ratio, 0-1: net move over n bars / sum of absolute bar moves.

    1 means a straight line (clean trend), near 0 means choppy noise.
    """
    _check_window(n)
    out = _nan(len(close))
    if len(close) > n:
        change = np.abs(close[n:] - close[:-n])
        path = sliding_window_view(np.abs(np.diff(close)), n).sum(axis=1)
        values = np.zeros(len(change))
        ok = path > 0
        values[ok] = change[ok] / path[ok]
        out[n:] = values
    return out


def prior_channel(high: FloatArray, low: FloatArray, n: int) -> tuple[FloatArray, FloatArray]:
    """Donchian channel of the n bars BEFORE each bar (today is excluded).

    A close above ``upper[t]`` is a breakout to a new n-bar high.
    """
    _check_window(n)
    upper, lower = _nan(len(high)), _nan(len(low))
    if len(high) > n:
        upper[1:] = rolling_max(high, n)[:-1]
        lower[1:] = rolling_min(low, n)[:-1]
    return upper, lower


def swing_points(high: FloatArray, low: FloatArray, k: int = 3) -> tuple[list[int], list[int]]:
    """Confirmed swing highs and lows (fractals) as bar indices, oldest first.

    Bar i is a swing high when its high beats the k bars before it and is not beaten by the
    k bars after it. It is only confirmed k bars later, so the last k bars never qualify:
    this is what keeps the function causal.
    """
    if k < 1:
        raise ValueError("k must be >= 1")
    highs: list[int] = []
    lows: list[int] = []
    for i in range(k, len(high) - k):
        h_left, h_right = high[i - k : i], high[i + 1 : i + k + 1]
        if np.all(np.isfinite(h_left)) and high[i] > np.max(h_left) and high[i] >= np.max(h_right):
            highs.append(i)
        l_left, l_right = low[i - k : i], low[i + 1 : i + k + 1]
        if np.all(np.isfinite(l_left)) and low[i] < np.min(l_left) and low[i] <= np.min(l_right):
            lows.append(i)
    return highs, lows


def corwin_schultz_spread(
    high: FloatArray, low: FloatArray, close: FloatArray, n: int = 20
) -> FloatArray:
    """Corwin-Schultz (2012) bid-ask spread estimate from daily highs and lows (fraction).

    Two-day estimates with the paper's overnight adjustment, negatives set to zero,
    averaged over n days. Rough, but needs no quote data.
    """
    _check_window(n)
    size = len(close)
    out = _nan(size)
    if size < n + 1:
        return out
    # Pair (t-1, t). Overnight adjustment from the paper: when day t gapped away from the
    # day t-1 close, shift day t's high and low back by the size of the gap.
    h0, l0, prev_close = high[:-1], low[:-1], close[:-1]
    gap_up = np.maximum(low[1:] - prev_close, 0.0)
    gap_down = np.maximum(prev_close - high[1:], 0.0)
    h1 = high[1:] - gap_up + gap_down
    l1 = low[1:] - gap_up + gap_down
    with np.errstate(divide="ignore", invalid="ignore"):
        beta = np.log(h1 / l1) ** 2 + np.log(h0 / l0) ** 2
        gamma = np.log(np.maximum(h0, h1) / np.minimum(l0, l1)) ** 2
        k = 3.0 - 2.0 * math.sqrt(2.0)
        alpha = (np.sqrt(2.0 * beta) - np.sqrt(beta)) / k - np.sqrt(gamma / k)
        spread = 2.0 * (np.exp(alpha) - 1.0) / (1.0 + np.exp(alpha))
    two_day = _nan(size)
    two_day[1:] = np.where(np.isfinite(spread), np.maximum(spread, 0.0), np.nan)
    out[n:] = sliding_window_view(two_day[1:], n).mean(axis=1)
    return out


def abdi_ranaldo_spread(
    high: FloatArray, low: FloatArray, close: FloatArray, n: int = 20
) -> FloatArray:
    """Abdi-Ranaldo (2017) spread estimate from close, high and low prices (fraction).

    s^2 = 4 E[(c_t - eta_t)(c_t - eta_{t+1})], with c the log close and eta the log
    mid-range. Each term uses bars t and t+1, so the value at bar T only uses bars <= T.
    """
    _check_window(n)
    size = len(close)
    out = _nan(size)
    if size < n + 1:
        return out
    with np.errstate(divide="ignore", invalid="ignore"):
        c = np.log(close)
        eta = (np.log(high) + np.log(low)) / 2.0
    product = (c[:-1] - eta[:-1]) * (c[:-1] - eta[1:])  # pair (t, t+1) is known at t+1
    mean = sliding_window_view(product, n).mean(axis=1)
    out[n:] = np.sqrt(np.maximum(4.0 * mean, 0.0))
    return out


def amihud_illiquidity(close: FloatArray, volume: FloatArray, n: int = 20) -> FloatArray:
    """Amihud (2002): average |return| per unit of traded value, scaled per million.

    Bigger means each dollar traded moves the price more (less liquid). Days with no trading
    are skipped (their ratio is undefined); with fewer than n / 2 trading days the value is
    NaN, meaning "cannot be measured", never "perfectly liquid".
    """
    _check_window(n)
    out = _nan(len(close))
    if len(close) <= n:
        return out
    ret = np.abs(np.diff(close) / close[:-1])
    value = close[1:] * volume[1:]
    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = np.where(value > 0, ret / value * 1e6, np.nan)
    windows = sliding_window_view(ratio, n)
    counts = np.sum(np.isfinite(windows), axis=1)
    sums = np.nansum(windows, axis=1)
    means = np.full(len(counts), np.nan)
    ok = counts >= max(1, n // 2)
    means[ok] = sums[ok] / counts[ok]
    out[n:] = means
    return out


def last_value(x: FloatArray) -> float:
    return float(x[-1]) if len(x) else math.nan


def symbol_features(view: MarketView, symbol: str) -> dict[str, float]:
    """The A03 feature row for one symbol at the view's as-of date (finite values only)."""
    c = np.ascontiguousarray(view.close(symbol)[-FEATURE_TAIL:])
    h = np.ascontiguousarray(view.high(symbol)[-FEATURE_TAIL:])
    lo = np.ascontiguousarray(view.low(symbol)[-FEATURE_TAIL:])
    v = np.ascontiguousarray(view.volume(symbol)[-FEATURE_TAIL:])
    if len(c) < 2:
        return {}
    rets = log_returns(c)
    vol_sma = last_value(sma(v, 20))
    plus_di, minus_di, adx_14 = directional_indicators(h, lo, c, 14)
    values = {
        "close": last_value(c),
        "ret_1": float(c[-1] / c[-2] - 1.0),
        "mom_21": last_value(momentum(c, 21)),
        "mom_63": last_value(momentum(c, 63)),
        "mom_126": last_value(momentum(c, 126)),
        "mom_252": last_value(momentum(c, 252)),
        "mom_12_1": last_value(momentum(c, 252, 21)),
        "sma_50": last_value(sma(c, 50)),
        "sma_200": last_value(sma(c, 200)),
        "rsi_2": last_value(rsi(c, 2)),
        "rsi_14": last_value(rsi(c, 14)),
        "atr_14": last_value(atr(h, lo, c, 14)),
        "vol_20": last_value(rolling_std(rets, 20)),
        "zscore_20": last_value(zscore(c, 20)),
        "ibs": last_value(ibs(h, lo, c)),
        "channel_55": last_value(channel_position(h, lo, c, 55)),
        "adx_14": last_value(adx_14),
        "plus_di_14": last_value(plus_di),
        "minus_di_14": last_value(minus_di),
        "er_10": last_value(efficiency_ratio(c, 10)),
        "er_20": last_value(efficiency_ratio(c, 20)),
        "rel_volume_20": float(v[-1] / vol_sma) if vol_sma and math.isfinite(vol_sma) else math.nan,
    }
    return {k: float(val) for k, val in values.items() if math.isfinite(val)}
