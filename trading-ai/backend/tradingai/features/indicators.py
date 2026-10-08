"""Indicator functions: numpy, vectorized where possible, and CAUSAL: the value at bar i uses bars 0..i only.

Every function returns arrays the same length as its input, with NaN during warm-up. Inputs are float64 arrays.
The registry (features/registry.py) holds each function's metadata: formula, inputs, warm-up, market compatibility and
what happens with missing data. tests/test_features.py checks causality for every registered feature by computing it
on a prefix and on the full series and requiring identical values on the prefix.
"""

from __future__ import annotations

import numpy as np

A = np.ndarray
NAN = np.nan


# ============================================================================ building blocks

def _nan(n: int) -> A:
    return np.full(n, NAN)


def sma(x: A, n: int) -> A:
    out = _nan(len(x))
    if n <= 0 or len(x) < n:
        return out
    c = np.cumsum(np.insert(np.nan_to_num(x), 0, 0.0))
    out[n - 1:] = (c[n:] - c[:-n]) / n
    bad = np.convolve(np.isnan(x).astype(float), np.ones(n), "full")[: len(x)] > 0
    out[bad] = NAN
    return out


def ema(x: A, n: int, alpha: float | None = None) -> A:
    out = _nan(len(x))
    a = alpha if alpha is not None else 2.0 / (n + 1)
    start = next((i for i in range(len(x)) if np.isfinite(x[i])), None)
    if start is None or len(x) - start < n:
        return out
    s = np.nanmean(x[start:start + n])
    out[start + n - 1] = s
    for i in range(start + n, len(x)):
        v = x[i]
        s = s if not np.isfinite(v) else a * v + (1 - a) * s
        out[i] = s
    return out


def rma(x: A, n: int) -> A:
    """Wilder's moving average (alpha = 1/n)."""
    return ema(x, n, alpha=1.0 / n)


def wma(x: A, n: int) -> A:
    out = _nan(len(x))
    if len(x) < n:
        return out
    w = np.arange(1, n + 1, dtype=float)
    v = np.lib.stride_tricks.sliding_window_view(x, n)
    out[n - 1:] = v @ w / w.sum()
    return out


def rolling(x: A, n: int, fn) -> A:
    out = _nan(len(x))
    if len(x) < n:
        return out
    v = np.lib.stride_tricks.sliding_window_view(x, n)
    out[n - 1:] = fn(v, axis=1)
    return out


def rstd(x: A, n: int) -> A:
    return rolling(x, n, lambda v, axis: np.std(v, axis=axis, ddof=1))


def rmax(x: A, n: int) -> A:
    return rolling(x, n, np.max)


def rmin(x: A, n: int) -> A:
    return rolling(x, n, np.min)


def shift(x: A, k: int) -> A:
    out = _nan(len(x))
    if k < len(x):
        out[k:] = x[: len(x) - k]
    return out


def ret(c: A, k: int = 1) -> A:
    return c / shift(c, k) - 1.0


def logret(c: A, k: int = 1) -> A:
    return np.log(c / shift(c, k))


def true_range(h: A, lo: A, c: A) -> A:
    pc = shift(c, 1)
    tr = np.maximum(h - lo, np.maximum(np.abs(h - pc), np.abs(lo - pc)))
    tr[0] = h[0] - lo[0]
    return tr


def safe_div(a: A, b: A) -> A:
    with np.errstate(divide="ignore", invalid="ignore"):
        out = a / b
    out[~np.isfinite(out)] = NAN
    return out


# ============================================================================ trend

def dema(x: A, n: int) -> A:
    e = ema(x, n)
    return 2 * e - ema(e, n)


def tema(x: A, n: int) -> A:
    e1 = ema(x, n)
    e2 = ema(e1, n)
    return 3 * e1 - 3 * e2 + ema(e2, n)


def hma(x: A, n: int) -> A:
    return wma(2 * wma(x, max(1, n // 2)) - wma(x, n), max(1, int(np.sqrt(n))))


def zlema(x: A, n: int) -> A:
    lag = (n - 1) // 2
    return ema(x + (x - shift(x, lag)), n)


def trima(x: A, n: int) -> A:
    return sma(sma(x, (n + 1) // 2), n // 2 + 1)


def kama(x: A, n: int = 10, fast: int = 2, slow: int = 30) -> A:
    out = _nan(len(x))
    if len(x) <= n:
        return out
    change = np.abs(x - shift(x, n))
    vol = rolling(np.abs(np.diff(x, prepend=NAN)), n, np.sum)
    er = safe_div(change, vol)
    fsc, ssc = 2 / (fast + 1), 2 / (slow + 1)
    sc = (er * (fsc - ssc) + ssc) ** 2
    k = x[n]
    out[n] = k
    for i in range(n + 1, len(x)):
        if np.isfinite(sc[i]):
            k = k + sc[i] * (x[i] - k)
        out[i] = k
    return out


def alma(x: A, n: int = 9, offset: float = 0.85, sigma: float = 6.0) -> A:
    out = _nan(len(x))
    if len(x) < n:
        return out
    m = offset * (n - 1)
    s = n / sigma
    w = np.exp(-((np.arange(n) - m) ** 2) / (2 * s * s))
    v = np.lib.stride_tricks.sliding_window_view(x, n)
    out[n - 1:] = v @ w / w.sum()
    return out


def vwma(c: A, v: A, n: int) -> A:
    return safe_div(sma(c * v, n), sma(v, n))


def linreg(x: A, n: int) -> tuple[A, A, A]:
    """Rolling least-squares line over the last n bars: (slope per bar, end-point value, r squared)."""
    slope, endp, r2 = _nan(len(x)), _nan(len(x)), _nan(len(x))
    if len(x) < n:
        return slope, endp, r2
    t = np.arange(n, dtype=float)
    tm = t.mean()
    tt = ((t - tm) ** 2).sum()
    v = np.lib.stride_tricks.sliding_window_view(x, n)
    ym = v.mean(axis=1)
    b = ((v - ym[:, None]) * (t - tm)).sum(axis=1) / tt
    a = ym - b * tm
    fit = a[:, None] + b[:, None] * t
    ss_res = ((v - fit) ** 2).sum(axis=1)
    ss_tot = ((v - ym[:, None]) ** 2).sum(axis=1)
    slope[n - 1:] = b
    endp[n - 1:] = a + b * (n - 1)
    r2[n - 1:] = np.where(ss_tot > 0, 1 - ss_res / np.where(ss_tot > 0, ss_tot, 1), 0.0)
    return slope, endp, r2


def macd(x: A, fast: int = 12, slow: int = 26, signal: int = 9) -> tuple[A, A, A]:
    line = ema(x, fast) - ema(x, slow)
    sig = ema(line, signal)
    return line, sig, line - sig


def ppo(x: A, fast: int = 12, slow: int = 26) -> A:
    s = ema(x, slow)
    return 100 * safe_div(ema(x, fast) - s, s)


def trix(x: A, n: int = 15) -> A:
    e = ema(ema(ema(x, n), n), n)
    return 100 * ret(e, 1)


def adx(h: A, lo: A, c: A, n: int = 14) -> tuple[A, A, A]:
    up = h - shift(h, 1)
    dn = shift(lo, 1) - lo
    pdm = np.where((up > dn) & (up > 0), up, 0.0)
    mdm = np.where((dn > up) & (dn > 0), dn, 0.0)
    pdm[0] = mdm[0] = 0.0
    atr_ = rma(true_range(h, lo, c), n)
    pdi = 100 * safe_div(rma(pdm, n), atr_)
    mdi = 100 * safe_div(rma(mdm, n), atr_)
    dx = 100 * safe_div(np.abs(pdi - mdi), pdi + mdi)
    return rma(dx, n), pdi, mdi


def aroon(h: A, lo: A, n: int = 25) -> tuple[A, A]:
    up, dn = _nan(len(h)), _nan(len(h))
    if len(h) <= n:
        return up, dn
    vh = np.lib.stride_tricks.sliding_window_view(h, n + 1)
    vl = np.lib.stride_tricks.sliding_window_view(lo, n + 1)
    up[n:] = 100 * np.argmax(vh, axis=1) / n
    dn[n:] = 100 * np.argmin(vl, axis=1) / n
    return up, dn


def supertrend(h: A, lo: A, c: A, n: int = 10, mult: float = 3.0) -> tuple[A, A]:
    """(line, direction +1/-1)."""
    atr_ = rma(true_range(h, lo, c), n)
    mid = (h + lo) / 2
    ub, lb = mid + mult * atr_, mid - mult * atr_
    line, d = _nan(len(c)), _nan(len(c))
    fu, fl, dirn = NAN, NAN, 1
    for i in range(len(c)):
        if not np.isfinite(atr_[i]):
            continue
        fu = ub[i] if not np.isfinite(fu) or ub[i] < fu or c[i - 1] > fu else fu
        fl = lb[i] if not np.isfinite(fl) or lb[i] > fl or c[i - 1] < fl else fl
        if dirn == 1 and c[i] < fl:
            dirn = -1
        elif dirn == -1 and c[i] > fu:
            dirn = 1
        line[i] = fl if dirn == 1 else fu
        d[i] = dirn
    return line, d


def psar(h: A, lo: A, step: float = 0.02, max_af: float = 0.2) -> tuple[A, A]:
    """Parabolic SAR: (sar, direction)."""
    n = len(h)
    sar, d = _nan(n), _nan(n)
    if n < 3:
        return sar, d
    up = True
    af, ep, s = step, h[0], lo[0]
    for i in range(1, n):
        s = s + af * (ep - s)
        if up:
            s = min(s, lo[i - 1], lo[i - 2] if i > 1 else lo[i - 1])
            if lo[i] < s:
                up, s, ep, af = False, ep, lo[i], step
            elif h[i] > ep:
                ep, af = h[i], min(max_af, af + step)
        else:
            s = max(s, h[i - 1], h[i - 2] if i > 1 else h[i - 1])
            if h[i] > s:
                up, s, ep, af = True, ep, h[i], step
            elif lo[i] < ep:
                ep, af = lo[i], min(max_af, af + step)
        sar[i], d[i] = s, 1.0 if up else -1.0
    return sar, d


def ichimoku(h: A, lo: A, tenkan: int = 9, kijun: int = 26, senkou: int = 52) -> dict[str, A]:
    """Causal parts only: the cloud is shown at the time it becomes known (no forward shift into the future)."""
    t = (rmax(h, tenkan) + rmin(lo, tenkan)) / 2
    k = (rmax(h, kijun) + rmin(lo, kijun)) / 2
    return {"tenkan": t, "kijun": k, "senkou_a": shift((t + k) / 2, kijun),
            "senkou_b": shift((rmax(h, senkou) + rmin(lo, senkou)) / 2, kijun)}


def donchian(h: A, lo: A, n: int = 20) -> tuple[A, A, A]:
    """Channel of the PREVIOUS n bars (excludes the current bar, so a breakout can be detected without look-ahead)."""
    up, dn = shift(rmax(h, n), 1), shift(rmin(lo, n), 1)
    return up, dn, (up + dn) / 2


def keltner(h: A, lo: A, c: A, n: int = 20, mult: float = 2.0) -> tuple[A, A, A]:
    mid = ema(c, n)
    a = atr(h, lo, c, n)
    return mid, mid + mult * a, mid - mult * a


def vortex(h: A, lo: A, c: A, n: int = 14) -> tuple[A, A]:
    vmp = np.abs(h - shift(lo, 1))
    vmm = np.abs(lo - shift(h, 1))
    tr = rolling(true_range(h, lo, c), n, np.sum)
    return safe_div(rolling(vmp, n, np.sum), tr), safe_div(rolling(vmm, n, np.sum), tr)


def mass_index(h: A, lo: A, n: int = 25) -> A:
    r = h - lo
    e1 = ema(r, 9)
    return rolling(safe_div(e1, ema(e1, 9)), n, np.sum)


def choppiness(h: A, lo: A, c: A, n: int = 14) -> A:
    s = rolling(true_range(h, lo, c), n, np.sum)
    return 100 * np.log10(safe_div(s, rmax(h, n) - rmin(lo, n))) / np.log10(n)


def efficiency_ratio(c: A, n: int = 10) -> A:
    return safe_div(np.abs(c - shift(c, n)), rolling(np.abs(np.diff(c, prepend=NAN)), n, np.sum))


# ============================================================================ momentum

def rsi(c: A, n: int = 14) -> A:
    d = np.diff(c, prepend=NAN)
    g, l_ = np.where(d > 0, d, 0.0), np.where(d < 0, -d, 0.0)
    g[0] = l_[0] = NAN
    ag, al = rma(g, n), rma(l_, n)
    out = 100 - 100 / (1 + safe_div(ag, al))
    out[np.isfinite(ag) & (al == 0)] = 100.0
    return out


def stoch(h: A, lo: A, c: A, n: int = 14, k_smooth: int = 3, d_smooth: int = 3) -> tuple[A, A]:
    raw = 100 * safe_div(c - rmin(lo, n), rmax(h, n) - rmin(lo, n))
    k = sma(raw, k_smooth)
    return k, sma(k, d_smooth)


def stoch_rsi(c: A, n: int = 14) -> A:
    r = rsi(c, n)
    return 100 * safe_div(r - rmin(r, n), rmax(r, n) - rmin(r, n))


def williams_r(h: A, lo: A, c: A, n: int = 14) -> A:
    return -100 * safe_div(rmax(h, n) - c, rmax(h, n) - rmin(lo, n))


def cci(h: A, lo: A, c: A, n: int = 20) -> A:
    tp = (h + lo + c) / 3
    m = sma(tp, n)
    md = rolling(tp, n, lambda v, axis: np.mean(np.abs(v - v.mean(axis=axis, keepdims=True)), axis=axis))
    return safe_div(tp - m, 0.015 * md)


def roc(c: A, n: int = 10) -> A:
    return 100 * ret(c, n)


def momentum(c: A, n: int = 10) -> A:
    return c - shift(c, n)


def cmo(c: A, n: int = 14) -> A:
    d = np.diff(c, prepend=NAN)
    up = rolling(np.where(d > 0, d, 0.0), n, np.sum)
    dn = rolling(np.where(d < 0, -d, 0.0), n, np.sum)
    return 100 * safe_div(up - dn, up + dn)


def ultimate_osc(h: A, lo: A, c: A) -> A:
    pc = shift(c, 1)
    bp = c - np.minimum(lo, pc)
    tr = np.maximum(h, pc) - np.minimum(lo, pc)
    avg = lambda k: safe_div(rolling(bp, k, np.sum), rolling(tr, k, np.sum))   # noqa: E731
    return 100 * (4 * avg(7) + 2 * avg(14) + avg(28)) / 7


def awesome_osc(h: A, lo: A) -> A:
    m = (h + lo) / 2
    return sma(m, 5) - sma(m, 34)


def kst(c: A) -> tuple[A, A]:
    k = sma(roc(c, 10), 10) + 2 * sma(roc(c, 15), 10) + 3 * sma(roc(c, 20), 10) + 4 * sma(roc(c, 30), 15)
    return k, sma(k, 9)


def tsi(c: A, long: int = 25, short: int = 13) -> A:
    d = np.diff(c, prepend=NAN)
    return 100 * safe_div(ema(ema(d, long), short), ema(ema(np.abs(d), long), short))


def rvi(o: A, h: A, lo: A, c: A, n: int = 10) -> A:
    num = (c - o) + 2 * shift(c - o, 1) + 2 * shift(c - o, 2) + shift(c - o, 3)
    den = (h - lo) + 2 * shift(h - lo, 1) + 2 * shift(h - lo, 2) + shift(h - lo, 3)
    return safe_div(sma(num, n), sma(den, n))


def fisher(h: A, lo: A, n: int = 10) -> A:
    m = (h + lo) / 2
    x = 2 * safe_div(m - rmin(m, n), rmax(m, n) - rmin(m, n)) - 1
    x = np.clip(np.nan_to_num(x, nan=0.0), -0.999, 0.999)
    out = 0.5 * np.log((1 + x) / (1 - x))
    out[: n - 1] = NAN
    return ema(out, 3)


def streak(c: A) -> A:
    out = np.zeros(len(c))
    for i in range(1, len(c)):
        if c[i] > c[i - 1]:
            out[i] = out[i - 1] + 1 if out[i - 1] > 0 else 1
        elif c[i] < c[i - 1]:
            out[i] = out[i - 1] - 1 if out[i - 1] < 0 else -1
    out[0] = NAN
    return out


def percent_rank(x: A, n: int) -> A:
    return rolling(x, n, lambda v, axis: (v[:, :-1] < v[:, -1:]).mean(axis=1) * 100)


def connors_rsi(c: A) -> A:
    return (rsi(c, 3) + rsi(streak(c), 2) + percent_rank(100 * ret(c, 1), 100)) / 3


def balance_of_power(o: A, h: A, lo: A, c: A, n: int = 14) -> A:
    return sma(safe_div(c - o, h - lo), n)


def elder_ray(h: A, lo: A, c: A, n: int = 13) -> tuple[A, A]:
    e = ema(c, n)
    return h - e, lo - e


def coppock(c: A) -> A:
    return wma(roc(c, 14) + roc(c, 11), 10)


def qstick(o: A, c: A, n: int = 14) -> A:
    return sma(c - o, n)


def ibs(h: A, lo: A, c: A) -> A:
    """Internal bar strength: where the close sits in the bar's range (0 = low, 1 = high)."""
    return safe_div(c - lo, h - lo)


# ============================================================================ volatility

def atr(h: A, lo: A, c: A, n: int = 14) -> A:
    return rma(true_range(h, lo, c), n)


def natr(h: A, lo: A, c: A, n: int = 14) -> A:
    return 100 * safe_div(atr(h, lo, c, n), c)


def bollinger(c: A, n: int = 20, k: float = 2.0) -> tuple[A, A, A, A, A]:
    """(mid, upper, lower, %b, bandwidth)."""
    m = sma(c, n)
    s = rolling(c, n, lambda v, axis: np.std(v, axis=axis))
    up, dn = m + k * s, m - k * s
    return m, up, dn, safe_div(c - dn, up - dn), safe_div(up - dn, m)


def realized_vol(c: A, n: int = 20, periods: float = 252.0) -> A:
    return rstd(logret(c), n) * np.sqrt(periods)


def parkinson(h: A, lo: A, n: int = 20, periods: float = 252.0) -> A:
    x = np.log(h / lo) ** 2
    return np.sqrt(sma(x, n) / (4 * np.log(2)) * periods)


def garman_klass(o: A, h: A, lo: A, c: A, n: int = 20, periods: float = 252.0) -> A:
    x = 0.5 * np.log(h / lo) ** 2 - (2 * np.log(2) - 1) * np.log(c / o) ** 2
    return np.sqrt(np.maximum(sma(x, n), 0) * periods)


def rogers_satchell(o: A, h: A, lo: A, c: A, n: int = 20, periods: float = 252.0) -> A:
    x = np.log(h / c) * np.log(h / o) + np.log(lo / c) * np.log(lo / o)
    return np.sqrt(np.maximum(sma(x, n), 0) * periods)


def yang_zhang(o: A, h: A, lo: A, c: A, n: int = 20, periods: float = 252.0) -> A:
    oc = np.log(o / shift(c, 1))
    co = np.log(c / o)
    k = 0.34 / (1.34 + (n + 1) / (n - 1))
    rs = np.log(h / c) * np.log(h / o) + np.log(lo / c) * np.log(lo / o)
    v = rstd(oc, n) ** 2 + k * rstd(co, n) ** 2 + (1 - k) * sma(rs, n)
    return np.sqrt(np.maximum(v, 0) * periods)


def chaikin_vol(h: A, lo: A, n: int = 10) -> A:
    e = ema(h - lo, n)
    return 100 * ret(e, n)


def ulcer_index(c: A, n: int = 14) -> A:
    dd = 100 * (c / rmax(c, n) - 1)
    return np.sqrt(sma(dd ** 2, n))


def vol_ratio(c: A, short: int = 10, long: int = 60) -> A:
    return safe_div(rstd(logret(c), short), rstd(logret(c), long))


def narrow_range(h: A, lo: A, n: int = 7) -> A:
    """1 when this bar's range is the narrowest of the last n bars (NR4 / NR7)."""
    r = h - lo
    return (r <= rmin(r, n) + 1e-15).astype(float) * np.where(np.isfinite(rmin(r, n)), 1, NAN)


def inside_bar(h: A, lo: A) -> A:
    out = ((h < shift(h, 1)) & (lo > shift(lo, 1))).astype(float)
    out[0] = NAN
    return out


def vol_of_vol(c: A, n: int = 20) -> A:
    return rstd(rstd(logret(c), n), n)


# ============================================================================ volume

def obv(c: A, v: A) -> A:
    d = np.sign(np.diff(c, prepend=c[0]))
    return np.cumsum(d * v)


def ad_line(h: A, lo: A, c: A, v: A) -> A:
    mfm = np.nan_to_num(safe_div((c - lo) - (h - c), h - lo))
    return np.cumsum(mfm * v)


def cmf(h: A, lo: A, c: A, v: A, n: int = 20) -> A:
    mfm = np.nan_to_num(safe_div((c - lo) - (h - c), h - lo))
    return safe_div(rolling(mfm * v, n, np.sum), rolling(v, n, np.sum))


def mfi(h: A, lo: A, c: A, v: A, n: int = 14) -> A:
    tp = (h + lo + c) / 3
    raw = tp * v
    d = np.diff(tp, prepend=NAN)
    pos = rolling(np.where(d > 0, raw, 0.0), n, np.sum)
    neg = rolling(np.where(d < 0, raw, 0.0), n, np.sum)
    return 100 - 100 / (1 + safe_div(pos, neg))


def vwap_session(h: A, lo: A, c: A, v: A, session_id: A) -> A:
    """Volume-weighted average price since the start of each session (resets when session_id changes)."""
    tp = (h + lo + c) / 3
    out = _nan(len(c))
    pv = vv = 0.0
    for i in range(len(c)):
        if i == 0 or session_id[i] != session_id[i - 1]:
            pv = vv = 0.0
        pv += tp[i] * v[i]
        vv += v[i]
        out[i] = pv / vv if vv > 0 else tp[i]
    return out


def vwap_rolling(h: A, lo: A, c: A, v: A, n: int = 20) -> A:
    tp = (h + lo + c) / 3
    return safe_div(rolling(tp * v, n, np.sum), rolling(v, n, np.sum))


def vwap_bands(h: A, lo: A, c: A, v: A, session_id: A, k: float = 2.0) -> tuple[A, A, A]:
    """Session VWAP with volume-weighted standard deviation bands."""
    tp = (h + lo + c) / 3
    mid, up, dn = _nan(len(c)), _nan(len(c)), _nan(len(c))
    pv = pv2 = vv = 0.0
    for i in range(len(c)):
        if i == 0 or session_id[i] != session_id[i - 1]:
            pv = pv2 = vv = 0.0
        pv += tp[i] * v[i]
        pv2 += tp[i] * tp[i] * v[i]
        vv += v[i]
        if vv > 0:
            m = pv / vv
            sd = np.sqrt(max(pv2 / vv - m * m, 0.0))
            mid[i], up[i], dn[i] = m, m + k * sd, m - k * sd
    return mid, up, dn


def anchored_vwap(h: A, lo: A, c: A, v: A, anchor: int) -> A:
    tp = (h + lo + c) / 3
    out = _nan(len(c))
    if 0 <= anchor < len(c):
        pv = np.cumsum((tp * v)[anchor:])
        vv = np.cumsum(v[anchor:])
        out[anchor:] = safe_div(pv, vv)
    return out


def force_index(c: A, v: A, n: int = 13) -> A:
    return ema(np.diff(c, prepend=NAN) * v, n)


def ease_of_movement(h: A, lo: A, v: A, n: int = 14) -> A:
    mid = (h + lo) / 2
    box = safe_div(v / 1e6, h - lo)
    return sma(safe_div(np.diff(mid, prepend=NAN), box), n)


def volume_osc(v: A, fast: int = 5, slow: int = 20) -> A:
    return 100 * safe_div(ema(v, fast) - ema(v, slow), ema(v, slow))


def pvt(c: A, v: A) -> A:
    return np.nancumsum(np.nan_to_num(ret(c, 1)) * v)


def nvi(c: A, v: A) -> A:
    out = np.ones(len(c)) * 1000.0
    for i in range(1, len(c)):
        out[i] = out[i - 1] * (1 + (c[i] / c[i - 1] - 1)) if v[i] < v[i - 1] else out[i - 1]
    return out


def pvi(c: A, v: A) -> A:
    out = np.ones(len(c)) * 1000.0
    for i in range(1, len(c)):
        out[i] = out[i - 1] * (1 + (c[i] / c[i - 1] - 1)) if v[i] > v[i - 1] else out[i - 1]
    return out


def klinger(h: A, lo: A, c: A, v: A) -> A:
    tp = h + lo + c
    sv = np.where(np.diff(tp, prepend=NAN) > 0, v, -v)
    return ema(sv, 34) - ema(sv, 55)


def rvol(v: A, n: int = 20) -> A:
    """Relative volume: this bar's volume over the average of the PREVIOUS n bars."""
    return safe_div(v, shift(sma(v, n), 1))


def volume_z(v: A, n: int = 20) -> A:
    return safe_div(v - shift(sma(v, n), 1), shift(rstd(v, n), 1))


def up_down_volume(c: A, v: A, n: int = 20) -> A:
    d = np.diff(c, prepend=NAN)
    return safe_div(rolling(np.where(d > 0, v, 0.0), n, np.sum), rolling(np.where(d < 0, v, 0.0), n, np.sum))


def intraday_intensity(h: A, lo: A, c: A, v: A, n: int = 21) -> A:
    return safe_div(rolling(np.nan_to_num(safe_div(2 * c - h - lo, h - lo)) * v, n, np.sum), rolling(v, n, np.sum))


# ============================================================================ statistical

def zscore(x: A, n: int = 20) -> A:
    return safe_div(x - sma(x, n), rstd(x, n))


def rskew(x: A, n: int = 60) -> A:
    def f(v, axis):
        m = v.mean(axis=1, keepdims=True)
        s = v.std(axis=1)
        return np.where(s > 0, ((v - m) ** 3).mean(axis=1) / np.where(s > 0, s, 1) ** 3, 0.0)
    return rolling(x, n, f)


def rkurt(x: A, n: int = 60) -> A:
    def f(v, axis):
        m = v.mean(axis=1, keepdims=True)
        s = v.std(axis=1)
        return np.where(s > 0, ((v - m) ** 4).mean(axis=1) / np.where(s > 0, s, 1) ** 4 - 3, 0.0)
    return rolling(x, n, f)


def autocorr(x: A, n: int = 60, lag: int = 1) -> A:
    def f(v, axis):
        a, b = v[:, lag:], v[:, :-lag]
        am, bm = a.mean(axis=1, keepdims=True), b.mean(axis=1, keepdims=True)
        num = ((a - am) * (b - bm)).sum(axis=1)
        den = np.sqrt(((a - am) ** 2).sum(axis=1) * ((b - bm) ** 2).sum(axis=1))
        return np.where(den > 0, num / np.where(den > 0, den, 1), 0.0)
    return rolling(x, n, f)


def hurst(c: A, n: int = 100) -> A:
    """Rescaled-range Hurst exponent over the last n log returns (about 0.5 = random walk)."""
    r = logret(c)

    def h_of(v: A) -> float:
        out = []
        for size in (n // 8, n // 4, n // 2, n):
            if size < 8:
                continue
            chunks = v[: (len(v) // size) * size].reshape(-1, size)
            dev = np.cumsum(chunks - chunks.mean(axis=1, keepdims=True), axis=1)
            rs = (dev.max(axis=1) - dev.min(axis=1)) / np.where(chunks.std(axis=1) > 0, chunks.std(axis=1), np.nan)
            m = np.nanmean(rs)
            if np.isfinite(m) and m > 0:
                out.append((np.log(size), np.log(m)))
        if len(out) < 2:
            return NAN
        xs, ys = np.array(out).T
        return float(np.polyfit(xs, ys, 1)[0])
    res = _nan(len(c))
    for i in range(n, len(c)):
        res[i] = h_of(r[i - n + 1:i + 1])
    return res


def variance_ratio(c: A, n: int = 100, q: int = 4) -> A:
    r = logret(c)
    v1 = rolling(r, n, lambda v, axis: np.var(v, axis=axis, ddof=1))
    rq = logret(c, q)
    vq = rolling(rq, n, lambda v, axis: np.var(v, axis=axis, ddof=1))
    return safe_div(vq, q * v1)


def sign_entropy(c: A, n: int = 50) -> A:
    up = rolling((np.diff(c, prepend=NAN) > 0).astype(float), n, np.mean)
    p = np.clip(up, 1e-9, 1 - 1e-9)
    return -(p * np.log2(p) + (1 - p) * np.log2(1 - p))


def rolling_beta(x: A, y: A, n: int = 60) -> A:
    """Beta of returns x on benchmark returns y over n bars."""
    cov = sma(x * y, n) - sma(x, n) * sma(y, n)
    return safe_div(cov, sma(y * y, n) - sma(y, n) ** 2)


def rolling_corr(x: A, y: A, n: int = 60) -> A:
    cov = sma(x * y, n) - sma(x, n) * sma(y, n)
    return safe_div(cov, np.sqrt((sma(x * x, n) - sma(x, n) ** 2) * (sma(y * y, n) - sma(y, n) ** 2)))


def half_life(x: A, n: int = 100) -> A:
    """Mean-reversion half-life (bars) from regressing the change on the lagged level over n bars."""
    out = _nan(len(x))
    for i in range(n, len(x)):
        y = x[i - n + 1:i + 1]
        dy, ly = np.diff(y), y[:-1] - y[:-1].mean()
        den = (ly * ly).sum()
        if den <= 0:
            continue
        b = (ly * (dy - dy.mean())).sum() / den
        out[i] = -np.log(2) / b if b < 0 else NAN
    return out


# ============================================================================ market structure and candles

def swing_points(h: A, lo: A, k: int = 3) -> tuple[A, A]:
    """Last CONFIRMED swing high and low: a swing at bar j is only known at bar j + k (when k bars followed it)."""
    sh, sl = _nan(len(h)), _nan(len(h))
    last_h = last_l = NAN
    for i in range(2 * k, len(h)):
        j = i - k
        if h[j] == h[j - k:i + 1].max():
            last_h = h[j]
        if lo[j] == lo[j - k:i + 1].min():
            last_l = lo[j]
        sh[i], sl[i] = last_h, last_l
    return sh, sl


def prior_session_levels(h: A, lo: A, c: A, session_id: A) -> tuple[A, A, A]:
    """Previous session's high, low and close at every bar (known once that session ended)."""
    ph, pl, pc = _nan(len(c)), _nan(len(c)), _nan(len(c))
    cur_h, cur_l = -np.inf, np.inf
    prev = (NAN, NAN, NAN)
    for i in range(len(c)):
        if i > 0 and session_id[i] != session_id[i - 1]:
            prev = (cur_h, cur_l, c[i - 1])
            cur_h, cur_l = -np.inf, np.inf
        cur_h, cur_l = max(cur_h, h[i]), min(cur_l, lo[i])
        ph[i], pl[i], pc[i] = prev
    return ph, pl, pc


def pivots_classic(ph: A, pl: A, pc: A) -> dict[str, A]:
    p = (ph + pl + pc) / 3
    return {"pivot": p, "r1": 2 * p - pl, "s1": 2 * p - ph, "r2": p + (ph - pl), "s2": p - (ph - pl)}


def opening_range(h: A, lo: A, session_id: A, bars: int) -> tuple[A, A, A]:
    """(range high, range low, 1 when the range is complete) of each session's first `bars` bars."""
    oh, ol, done = _nan(len(h)), _nan(len(h)), np.zeros(len(h))
    start, rh, rl = 0, -np.inf, np.inf
    for i in range(len(h)):
        if i == 0 or session_id[i] != session_id[i - 1]:
            start, rh, rl = i, -np.inf, np.inf
        k = i - start
        if k < bars:
            rh, rl = max(rh, h[i]), min(rl, lo[i])
        if k >= bars - 1:
            oh[i], ol[i], done[i] = rh, rl, 1.0
    return oh, ol, done


def gap(o: A, c: A, session_id: A) -> A:
    """Opening gap of each session versus the previous session's last close, as a fraction (0 within a session)."""
    out = np.zeros(len(o))
    for i in range(1, len(o)):
        if session_id[i] != session_id[i - 1]:
            out[i] = o[i] / c[i - 1] - 1
    return out


def candle_parts(o: A, h: A, lo: A, c: A) -> dict[str, A]:
    rng = h - lo
    body = np.abs(c - o)
    return {"body_frac": safe_div(body, rng), "upper_wick": safe_div(h - np.maximum(o, c), rng),
            "lower_wick": safe_div(np.minimum(o, c) - lo, rng)}


def engulfing(o: A, c: A) -> A:
    po, pc = shift(o, 1), shift(c, 1)
    bull = (c > o) & (pc < po) & (c >= po) & (o <= pc)
    bear = (c < o) & (pc > po) & (c <= po) & (o >= pc)
    out = bull.astype(float) - bear.astype(float)
    out[0] = NAN
    return out


def hammer(o: A, h: A, lo: A, c: A) -> A:
    p = candle_parts(o, h, lo, c)
    return ((p["lower_wick"] > 0.6) & (p["body_frac"] < 0.3)).astype(float)


def doji(o: A, h: A, lo: A, c: A) -> A:
    return (candle_parts(o, h, lo, c)["body_frac"] < 0.1).astype(float)


def hh_ll_count(h: A, lo: A, n: int = 10) -> A:
    """Higher highs minus lower lows over the last n bars: a simple structure trend score."""
    hh = (h > shift(h, 1)).astype(float)
    ll = (lo < shift(lo, 1)).astype(float)
    return rolling(hh - ll, n, np.sum)
