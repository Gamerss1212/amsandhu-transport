"""Shared indicator engine.

Every indicator here is a pure function of a Frame's completed bars. Position i of an output
uses bars 0..i only, so nothing looks ahead; a value never changes after it is written (no
repainting). Indicators whose textbook definition needs future bars are either shifted to
their causal form (Ichimoku spans, swing points confirmed n bars later) or left out
(zig-zag). Missing values are None. Each indicator is registered with its formula,
parameters, inputs, warm-up and missing-data behaviour; INDICATORS.md is generated from this
registry, so the documentation cannot drift from the code.

Warm-up is reported as two numbers:
* first  - bars before the first value is produced
* stable - bars after which the value no longer depends on where the history started, to
           within 1e-4 relative (recursive smoothers only). Live buffers are sized to at least
           `stable`, which is what makes live, replay and backtest values agree.

Update timing: all indicators update once per completed bar of their timeframe.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from mab.clock import is_equity
from mab.frame import Frame

Num = Optional[float]
Series = List[Num]


# ============================================================================ primitives

def _nones(n: int) -> Series:
    return [None] * n


def sma(x: Sequence[Num], n: int) -> Series:
    out = _nones(len(x))
    s, cnt, last_none = 0.0, 0, -1
    for i, v in enumerate(x):
        if v is None:
            last_none = i
        else:
            s += v
            cnt += 1
        if i >= n:
            old = x[i - n]
            if old is not None:
                s -= old
                cnt -= 1
        if i - last_none >= n and cnt == n:
            out[i] = s / n
    return out


def ema(x: Sequence[Num], n: int) -> Series:
    """EMA with alpha = 2/(n+1), seeded with the SMA of the first n values."""
    out = _nones(len(x))
    k = 2.0 / (n + 1)
    seed: List[float] = []
    prev = None
    for i, v in enumerate(x):
        if v is None:
            continue
        if prev is None:
            seed.append(v)
            if len(seed) == n:
                prev = sum(seed) / n
                out[i] = prev
            continue
        prev = prev + k * (v - prev)
        out[i] = prev
    return out


def rma(x: Sequence[Num], n: int) -> Series:
    """Wilder's smoothing (alpha = 1/n), seeded with the SMA of the first n values."""
    out = _nones(len(x))
    seed: List[float] = []
    prev = None
    for i, v in enumerate(x):
        if v is None:
            continue
        if prev is None:
            seed.append(v)
            if len(seed) == n:
                prev = sum(seed) / n
                out[i] = prev
            continue
        prev = prev + (v - prev) / n
        out[i] = prev
    return out


def wma(x: Sequence[Num], n: int) -> Series:
    out = _nones(len(x))
    denom = n * (n + 1) / 2
    for i in range(n - 1, len(x)):
        w = x[i - n + 1:i + 1]
        if None in w:
            continue
        out[i] = sum((j + 1) * v for j, v in enumerate(w)) / denom
    return out


def stdev(x: Sequence[Num], n: int, ddof: int = 0) -> Series:
    """Rolling standard deviation (population by default, as Bollinger specified)."""
    out = _nones(len(x))
    ref = next((v for v in x if v is not None), 0.0)
    s = ss = 0.0
    cnt, last_none = 0, -1
    for i, v in enumerate(x):
        if v is None:
            last_none = i
        else:
            d = v - ref
            s += d
            ss += d * d
            cnt += 1
        if i >= n and x[i - n] is not None:
            d = x[i - n] - ref
            s -= d
            ss -= d * d
            cnt -= 1
        if i - last_none >= n and cnt == n and n - ddof > 0:
            var = (ss - s * s / n) / (n - ddof)
            out[i] = math.sqrt(var) if var > 0 else 0.0
    return out


def rolling_max(x: Sequence[Num], n: int) -> Series:
    return _rolling_extreme(x, n, True)


def rolling_min(x: Sequence[Num], n: int) -> Series:
    return _rolling_extreme(x, n, False)


def _rolling_extreme(x: Sequence[Num], n: int, is_max: bool) -> Series:
    out = _nones(len(x))
    dq: deque = deque()
    last_none = -1
    for i, v in enumerate(x):
        if v is None:
            last_none = i
            dq.clear()
            continue
        while dq and ((x[dq[-1]] <= v) if is_max else (x[dq[-1]] >= v)):
            dq.pop()
        dq.append(i)
        while dq[0] <= i - n:
            dq.popleft()
        if i - last_none >= n:
            out[i] = x[dq[0]]
    return out


def rolling_sum(x: Sequence[Num], n: int) -> Series:
    m = sma(x, n)
    return [None if v is None else v * n for v in m]


def shift(x: Sequence[Num], k: int) -> Series:
    """Value k bars ago (k >= 0). Negative k would look ahead and is refused."""
    if k < 0:
        raise ValueError("negative shift would read future bars")
    if k == 0:
        return list(x)
    return _nones(min(k, len(x))) + list(x[:-k]) if k < len(x) else _nones(len(x))


def diff(x: Sequence[Num], k: int = 1) -> Series:
    p = shift(x, k)
    return [None if a is None or b is None else a - b for a, b in zip(x, p)]


def true_range(f: Frame) -> Series:
    out = _nones(f.n)
    for i in range(f.n):
        hl = f.h[i] - f.l[i]
        if i == 0:
            out[i] = hl
        else:
            pc = f.c[i - 1]
            out[i] = max(hl, abs(f.h[i] - pc), abs(f.l[i] - pc))
    return out


def _session_reset_cumsum(f: Frame, values: Sequence[Num]) -> Series:
    out = _nones(f.n)
    acc, cur = 0.0, None
    for i in range(f.n):
        if f.sess[i] < 0:
            continue
        if f.sess[i] != cur:
            cur, acc = f.sess[i], 0.0
        if values[i] is not None:
            acc += values[i]
        out[i] = acc
    return out


# ============================================================================ registry

@dataclass
class Indicator:
    name: str
    category: str
    fn: Callable
    params: List[Tuple[str, object]]
    outputs: List[str]
    formula: str
    inputs: str
    warmup: Callable[[dict], Tuple[int, int]]
    series_input: bool = False
    missing: str = "None until warm; a None input resets rolling windows"
    requires: Tuple[str, ...] = ()
    notes: str = ""
    sessions: Optional[Callable[[dict], int]] = None   # earlier COMPLETE sessions needed (None = not session-based)


REGISTRY: Dict[str, Indicator] = {}


def register(name, category, params, outputs, formula, inputs, warmup, series_input=False,
             missing=None, requires=(), notes="", sessions=None):
    def deco(fn):
        REGISTRY[name] = Indicator(name, category, fn, list(params), list(outputs), formula, inputs, warmup,
                                   series_input, missing or "None until warm; a None input resets rolling windows",
                                   tuple(requires), notes, sessions)
        return fn
    return deco


def compute(name: str, frame: Frame, x: Optional[Series] = None, **params) -> Dict[str, Series]:
    ind = REGISTRY[name]
    kw = {k: params.get(k, d) for k, d in ind.params}
    unknown = set(params) - {k for k, _ in ind.params}
    if unknown:
        raise ValueError(f"{name}: unknown parameter(s) {sorted(unknown)}")
    if ind.series_input:
        return ind.fn(frame, x, **kw)
    return ind.fn(frame, **kw)


def warmup_of(name: str, **params) -> Tuple[int, int]:
    ind = REGISTRY[name]
    kw = {k: params.get(k, d) for k, d in ind.params}
    return ind.warmup(kw)


# ============================================================================ trend

@register("sma", "trend", [("n", 20)], ["value"], "mean(x[i-n+1..i])", "any series", lambda p: (p["n"] - 1, p["n"]), True)
def _i_sma(f, x, n):
    return {"value": sma(x, int(n))}


@register("ema", "trend", [("n", 20)], ["value"],
          "e[i] = e[i-1] + a*(x[i]-e[i-1]), a = 2/(n+1); seeded with SMA of first n values",
          "any series", lambda p: (p["n"] - 1, 5 * p["n"]), True)
def _i_ema(f, x, n):
    return {"value": ema(x, int(n))}


@register("wma", "trend", [("n", 20)], ["value"], "sum(k*x[i-n+k]) / (n(n+1)/2), k = 1..n",
          "any series", lambda p: (p["n"] - 1, p["n"]), True)
def _i_wma(f, x, n):
    return {"value": wma(x, int(n))}


@register("rma", "trend", [("n", 14)], ["value"], "Wilder smoothing: r[i] = r[i-1] + (x[i]-r[i-1])/n",
          "any series", lambda p: (p["n"] - 1, 10 * p["n"]), True)
def _i_rma(f, x, n):
    return {"value": rma(x, int(n))}


@register("hma", "trend", [("n", 21)], ["value"], "WMA(2*WMA(x,n/2) - WMA(x,n), sqrt(n))",
          "any series", lambda p: (p["n"] + int(math.sqrt(p["n"])), p["n"] + int(math.sqrt(p["n"]))), True)
def _i_hma(f, x, n):
    n = int(n)
    a, b = wma(x, max(1, n // 2)), wma(x, n)
    raw = [None if u is None or w is None else 2 * u - w for u, w in zip(a, b)]
    return {"value": wma(raw, max(1, int(math.sqrt(n))))}


@register("dema", "trend", [("n", 21)], ["value"], "2*EMA(x,n) - EMA(EMA(x,n),n)", "any series",
          lambda p: (2 * p["n"], 10 * p["n"]), True)
def _i_dema(f, x, n):
    e1 = ema(x, int(n))
    e2 = ema(e1, int(n))
    return {"value": [None if a is None or b is None else 2 * a - b for a, b in zip(e1, e2)]}


@register("tema", "trend", [("n", 21)], ["value"], "3*E1 - 3*E2 + E3 of nested EMAs", "any series",
          lambda p: (3 * p["n"], 15 * p["n"]), True)
def _i_tema(f, x, n):
    e1 = ema(x, int(n)); e2 = ema(e1, int(n)); e3 = ema(e2, int(n))
    return {"value": [None if None in (a, b, c) else 3 * a - 3 * b + c for a, b, c in zip(e1, e2, e3)]}


@register("kama", "trend", [("n", 10), ("fast", 2), ("slow", 30)], ["value"],
          "Kaufman: sc = (ER*(2/(fast+1)-2/(slow+1)) + 2/(slow+1))^2; k[i] = k[i-1] + sc*(x-k[i-1])",
          "any series", lambda p: (p["n"], 10 * p["slow"]), True)
def _i_kama(f, x, n, fast, slow):
    n = int(n)
    out = _nones(len(x))
    fs, ss = 2 / (fast + 1), 2 / (slow + 1)
    prev = None
    for i in range(n, len(x)):
        if x[i] is None or x[i - n] is None:
            continue
        change = abs(x[i] - x[i - n])
        vol = sum(abs(x[j] - x[j - 1]) for j in range(i - n + 1, i + 1) if x[j] is not None and x[j - 1] is not None)
        er = change / vol if vol else 0.0
        sc = (er * (fs - ss) + ss) ** 2
        prev = x[i - 1] if prev is None else prev
        prev = prev + sc * (x[i] - prev)
        out[i] = prev
    return {"value": out}


@register("macd", "trend", [("fast", 12), ("slow", 26), ("signal", 9)], ["line", "signal", "hist"],
          "line = EMA(x,fast) - EMA(x,slow); signal = EMA(line,signal); hist = line - signal",
          "any series", lambda p: (p["slow"] + p["signal"] - 2, 5 * (p["slow"] + p["signal"])), True)
def _i_macd(f, x, fast, slow, signal):
    a, b = ema(x, int(fast)), ema(x, int(slow))
    line = [None if u is None or w is None else u - w for u, w in zip(a, b)]
    sig = ema(line, int(signal))
    hist = [None if u is None or w is None else u - w for u, w in zip(line, sig)]
    return {"line": line, "signal": sig, "hist": hist}


@register("adx", "trend", [("n", 14)], ["adx", "plus_di", "minus_di"],
          "+DM/-DM (Wilder), DI = 100*RMA(DM,n)/ATR(n), DX = 100*|+DI - -DI|/(+DI + -DI), ADX = RMA(DX,n)",
          "high, low, close", lambda p: (2 * p["n"], 20 * p["n"]))
def _i_adx(f, n):
    n = int(n)
    pdm, mdm = _nones(f.n), _nones(f.n)
    for i in range(1, f.n):
        up, dn = f.h[i] - f.h[i - 1], f.l[i - 1] - f.l[i]
        pdm[i] = up if (up > dn and up > 0) else 0.0
        mdm[i] = dn if (dn > up and dn > 0) else 0.0
    tr = true_range(f)
    tr[0] = None
    atr_ = rma(tr, n)
    sp, sm = rma(pdm, n), rma(mdm, n)
    pdi, mdi, dx = _nones(f.n), _nones(f.n), _nones(f.n)
    for i in range(f.n):
        if atr_[i] and sp[i] is not None and sm[i] is not None:
            pdi[i] = 100 * sp[i] / atr_[i]
            mdi[i] = 100 * sm[i] / atr_[i]
            s = pdi[i] + mdi[i]
            dx[i] = 100 * abs(pdi[i] - mdi[i]) / s if s else 0.0
    return {"adx": rma(dx, n), "plus_di": pdi, "minus_di": mdi}


@register("supertrend", "trend", [("n", 10), ("mult", 3.0)], ["line", "dir"],
          "basic bands = hl2 -/+ mult*ATR(n); final bands ratchet; dir = +1 while close stays above the "
          "final lower band, -1 while below the final upper band", "high, low, close",
          lambda p: (p["n"], 10 * p["n"]))
def _i_supertrend(f, n, mult):
    atr_ = rma(true_range(f), int(n))
    line, dirs = _nones(f.n), _nones(f.n)
    fu = fl = None
    d = 1
    for i in range(f.n):
        if atr_[i] is None:
            continue
        mid = (f.h[i] + f.l[i]) / 2
        bu, bl = mid + mult * atr_[i], mid - mult * atr_[i]
        if fu is None:
            fu, fl = bu, bl
            d = 1 if f.c[i] >= mid else -1
        else:
            pc = f.c[i - 1]
            fu = bu if (bu < fu or pc > fu) else fu
            fl = bl if (bl > fl or pc < fl) else fl
            if d == 1 and f.c[i] < fl:
                d = -1
            elif d == -1 and f.c[i] > fu:
                d = 1
        line[i] = fl if d == 1 else fu
        dirs[i] = float(d)
    return {"line": line, "dir": dirs}


@register("ichimoku", "trend", [("conv", 9), ("base", 26), ("span_b", 52)],
          ["conv", "base", "span_a", "span_b", "lag_close"],
          "conv = mid(HH,LL over conv); base = mid over base; span_a = (conv+base)/2 and span_b = mid over "
          "span_b, both as computed `base` bars AGO (the cloud drawn over bar i); lag_close = close `base` bars ago "
          "(the causal form of the Chikou comparison)", "high, low, close",
          lambda p: (p["span_b"] + p["base"] - 1, p["span_b"] + p["base"]),
          notes="Chikou span plotted backwards is not used: comparing close with lag_close is the same test, causally.")
def _i_ichimoku(f, conv, base, span_b):
    def mid(n):
        hh, ll = rolling_max(f.h, int(n)), rolling_min(f.l, int(n))
        return [None if a is None or b is None else (a + b) / 2 for a, b in zip(hh, ll)]
    cv, bs, sb = mid(conv), mid(base), mid(span_b)
    sa_raw = [None if a is None or b is None else (a + b) / 2 for a, b in zip(cv, bs)]
    return {"conv": cv, "base": bs, "span_a": shift(sa_raw, int(base)), "span_b": shift(sb, int(base)),
            "lag_close": shift(f.c, int(base))}


@register("psar", "trend", [("step", 0.02), ("max_step", 0.2)], ["value", "dir"],
          "Wilder's Parabolic SAR; the SAR for bar i uses bars up to i-1 and is never revised",
          "high, low", lambda p: (2, 2))
def _i_psar(f, step, max_step):
    out, dirs = _nones(f.n), _nones(f.n)
    if f.n < 2:
        return {"value": out, "dir": dirs}
    up = f.c[1] >= f.c[0]
    sar = f.l[0] if up else f.h[0]
    ep = f.h[1] if up else f.l[1]
    af = step
    for i in range(1, f.n):
        sar = sar + af * (ep - sar)
        if up:
            sar = min(sar, f.l[i - 1], f.l[i - 2] if i >= 2 else f.l[i - 1])
            if f.l[i] < sar:
                up, sar, ep, af = False, ep, f.l[i], step
            elif f.h[i] > ep:
                ep, af = f.h[i], min(max_step, af + step)
        else:
            sar = max(sar, f.h[i - 1], f.h[i - 2] if i >= 2 else f.h[i - 1])
            if f.h[i] > sar:
                up, sar, ep, af = True, ep, f.h[i], step
            elif f.l[i] < ep:
                ep, af = f.l[i], min(max_step, af + step)
        out[i] = sar
        dirs[i] = 1.0 if up else -1.0
    return {"value": out, "dir": dirs}


@register("aroon", "trend", [("n", 25)], ["up", "down", "osc"],
          "up = 100*(n - bars since n-bar high)/n; down likewise for the low; osc = up - down",
          "high, low", lambda p: (p["n"], p["n"] + 1))
def _i_aroon(f, n):
    n = int(n)
    up, dn, osc = _nones(f.n), _nones(f.n), _nones(f.n)
    for i in range(n, f.n):
        wh, wl = f.h[i - n:i + 1], f.l[i - n:i + 1]
        hi = max(range(n + 1), key=lambda k: (wh[k], k))
        lo = min(range(n + 1), key=lambda k: (wl[k], -k))
        up[i] = 100 * hi / n
        dn[i] = 100 * lo / n
        osc[i] = up[i] - dn[i]
    return {"up": up, "down": dn, "osc": osc}


@register("vortex", "trend", [("n", 14)], ["plus", "minus"],
          "VM+ = |H - L[-1]|, VM- = |L - H[-1]|; VI+ = sum(VM+,n)/sum(TR,n)", "high, low, close",
          lambda p: (p["n"], p["n"] + 1))
def _i_vortex(f, n):
    vp, vm = _nones(f.n), _nones(f.n)
    for i in range(1, f.n):
        vp[i] = abs(f.h[i] - f.l[i - 1])
        vm[i] = abs(f.l[i] - f.h[i - 1])
    tr = true_range(f); tr[0] = None
    sp, sm, st = rolling_sum(vp, int(n)), rolling_sum(vm, int(n)), rolling_sum(tr, int(n))
    return {"plus": [None if a is None or not c else a / c for a, c in zip(sp, st)],
            "minus": [None if a is None or not c else a / c for a, c in zip(sm, st)]}


@register("linreg", "trend", [("n", 20)], ["value", "slope", "r2"],
          "least-squares line through the last n values: value at the current bar, slope per bar, R^2",
          "any series", lambda p: (p["n"] - 1, p["n"]), True)
def _i_linreg(f, x, n):
    n = int(n)
    val, slope, r2 = _nones(len(x)), _nones(len(x)), _nones(len(x))
    xs = list(range(n))
    mx = (n - 1) / 2
    sxx = sum((k - mx) ** 2 for k in xs)
    for i in range(n - 1, len(x)):
        w = x[i - n + 1:i + 1]
        if None in w:
            continue
        my = sum(w) / n
        sxy = sum((k - mx) * (y - my) for k, y in zip(xs, w))
        b = sxy / sxx
        a = my - b * mx
        val[i], slope[i] = a + b * (n - 1), b
        syy = sum((y - my) ** 2 for y in w)
        r2[i] = (sxy * sxy / (sxx * syy)) if syy else 0.0
    return {"value": val, "slope": slope, "r2": r2}


@register("trix", "trend", [("n", 15)], ["value"], "100 * 1-bar % change of EMA(EMA(EMA(x,n)))", "any series",
          lambda p: (3 * p["n"], 15 * p["n"]), True)
def _i_trix(f, x, n):
    e = ema(ema(ema(x, int(n)), int(n)), int(n))
    p = shift(e, 1)
    return {"value": [None if a is None or not b else 100 * (a / b - 1) for a, b in zip(e, p)]}


@register("heikin_ashi", "trend", [], ["open", "high", "low", "close"],
          "ha_close = ohlc4; ha_open = (ha_open[-1] + ha_close[-1])/2 (seed (o+c)/2); ha_high/low = extremes",
          "open, high, low, close", lambda p: (0, 20))
def _i_ha(f):
    ho, hh, hl, hc = _nones(f.n), _nones(f.n), _nones(f.n), _nones(f.n)
    for i in range(f.n):
        hc[i] = (f.o[i] + f.h[i] + f.l[i] + f.c[i]) / 4
        ho[i] = (f.o[i] + f.c[i]) / 2 if i == 0 else (ho[i - 1] + hc[i - 1]) / 2
        hh[i] = max(f.h[i], ho[i], hc[i])
        hl[i] = min(f.l[i], ho[i], hc[i])
    return {"open": ho, "high": hh, "low": hl, "close": hc}


# ============================================================================ momentum

@register("rsi", "momentum", [("n", 14)], ["value"],
          "Wilder: RS = RMA(gains,n)/RMA(losses,n); RSI = 100 - 100/(1+RS) (100 when losses are 0)",
          "any series", lambda p: (p["n"], 10 * p["n"]), True)
def _i_rsi(f, x, n):
    n = int(n)
    g, l = _nones(len(x)), _nones(len(x))
    for i in range(1, len(x)):
        if x[i] is None or x[i - 1] is None:
            continue
        d = x[i] - x[i - 1]
        g[i], l[i] = max(d, 0.0), max(-d, 0.0)
    ag, al = rma(g, n), rma(l, n)
    out = _nones(len(x))
    for i in range(len(x)):
        if ag[i] is None or al[i] is None:
            continue
        out[i] = 100.0 if al[i] == 0 else (0.0 if ag[i] == 0 else 100 - 100 / (1 + ag[i] / al[i]))
        if al[i] == 0 and ag[i] == 0:
            out[i] = 50.0
    return {"value": out}


@register("stoch", "momentum", [("k", 14), ("smooth", 3), ("d", 3)], ["k", "d"],
          "raw = 100*(close - LL(k))/(HH(k) - LL(k)); %K = SMA(raw, smooth); %D = SMA(%K, d)",
          "high, low, close", lambda p: (p["k"] + p["smooth"] + p["d"] - 3, p["k"] + p["smooth"] + p["d"]))
def _i_stoch(f, k, smooth, d):
    hh, ll = rolling_max(f.h, int(k)), rolling_min(f.l, int(k))
    raw = [None if a is None else (50.0 if a == b else 100 * (c - b) / (a - b)) for a, b, c in zip(hh, ll, f.c)]
    kk = sma(raw, int(smooth))
    return {"k": kk, "d": sma(kk, int(d))}


@register("stochrsi", "momentum", [("rsi_n", 14), ("n", 14), ("smooth", 3), ("d", 3)], ["k", "d"],
          "stochastic formula applied to RSI(rsi_n) over n bars, smoothed", "any series",
          lambda p: (p["rsi_n"] + p["n"] + p["smooth"] + p["d"], 10 * p["rsi_n"] + p["n"] + p["smooth"] + p["d"]), True)
def _i_stochrsi(f, x, rsi_n, n, smooth, d):
    r = _i_rsi(f, x, rsi_n)["value"]
    hh, ll = rolling_max(r, int(n)), rolling_min(r, int(n))
    raw = [None if a is None or c is None else (50.0 if a == b else 100 * (c - b) / (a - b)) for a, b, c in zip(hh, ll, r)]
    kk = sma(raw, int(smooth))
    return {"k": kk, "d": sma(kk, int(d))}


@register("cci", "momentum", [("n", 20)], ["value"],
          "tp = hlc3; CCI = (tp - SMA(tp,n)) / (0.015 * mean |tp - SMA(tp,n)|)", "high, low, close",
          lambda p: (p["n"] - 1, p["n"]))
def _i_cci(f, n):
    n = int(n)
    tp = f.col("hlc3")
    m = sma(tp, n)
    out = _nones(f.n)
    for i in range(n - 1, f.n):
        md = sum(abs(tp[j] - m[i]) for j in range(i - n + 1, i + 1)) / n
        out[i] = 0.0 if md == 0 else (tp[i] - m[i]) / (0.015 * md)
    return {"value": out}


@register("roc", "momentum", [("n", 12)], ["value"], "100 * (x / x[n bars ago] - 1)", "any series",
          lambda p: (p["n"], p["n"]), True)
def _i_roc(f, x, n):
    p = shift(x, int(n))
    return {"value": [None if a is None or not b else 100 * (a / b - 1) for a, b in zip(x, p)]}


@register("willr", "momentum", [("n", 14)], ["value"], "-100 * (HH(n) - close) / (HH(n) - LL(n))",
          "high, low, close", lambda p: (p["n"] - 1, p["n"]))
def _i_willr(f, n):
    hh, ll = rolling_max(f.h, int(n)), rolling_min(f.l, int(n))
    return {"value": [None if a is None else (-50.0 if a == b else -100 * (a - c) / (a - b))
                      for a, b, c in zip(hh, ll, f.c)]}


@register("uo", "momentum", [("p1", 7), ("p2", 14), ("p3", 28)], ["value"],
          "Ultimate Oscillator: BP = close - min(low, prev close); weighted 4:2:1 average of BP/TR sums",
          "high, low, close", lambda p: (p["p3"], p["p3"] + 1))
def _i_uo(f, p1, p2, p3):
    bp, tr = _nones(f.n), _nones(f.n)
    for i in range(1, f.n):
        pc = f.c[i - 1]
        bp[i] = f.c[i] - min(f.l[i], pc)
        tr[i] = max(f.h[i], pc) - min(f.l[i], pc)
    out = _nones(f.n)
    s = [(rolling_sum(bp, int(p)), rolling_sum(tr, int(p))) for p in (p1, p2, p3)]
    for i in range(f.n):
        vals = [(b[i], t[i]) for b, t in s]
        if any(b is None or not t for b, t in vals):
            continue
        a1, a2, a3 = (b / t for b, t in vals)
        out[i] = 100 * (4 * a1 + 2 * a2 + a3) / 7
    return {"value": out}


@register("ao", "momentum", [], ["value"], "Awesome Oscillator: SMA(hl2,5) - SMA(hl2,34)", "high, low",
          lambda p: (33, 34))
def _i_ao(f):
    m = f.col("hl2")
    a, b = sma(m, 5), sma(m, 34)
    return {"value": [None if u is None or w is None else u - w for u, w in zip(a, b)]}


@register("connors_rsi", "momentum", [("rsi_n", 3), ("streak_n", 2), ("rank_n", 100)], ["value"],
          "mean of RSI(close,rsi_n), RSI(streak,streak_n) and the percent rank of the 1-bar return over rank_n",
          "close", lambda p: (p["rank_n"], max(10 * p["rsi_n"], p["rank_n"] + 1)))
def _i_crsi(f, rsi_n, streak_n, rank_n):
    c = f.c
    streak = [0.0] * f.n
    for i in range(1, f.n):
        if c[i] > c[i - 1]:
            streak[i] = streak[i - 1] + 1 if streak[i - 1] > 0 else 1
        elif c[i] < c[i - 1]:
            streak[i] = streak[i - 1] - 1 if streak[i - 1] < 0 else -1
    r1 = _i_rsi(f, c, rsi_n)["value"]
    r2 = _i_rsi(f, streak, streak_n)["value"]
    ret = [None] + [c[i] / c[i - 1] - 1 for i in range(1, f.n)]
    pr = percent_rank(ret, int(rank_n))
    return {"value": [None if None in (a, b, d) else (a + b + d) / 3 for a, b, d in zip(r1, r2, pr)]}


def percent_rank(x: Sequence[Num], n: int) -> Series:
    """Share (0-100) of the previous n values strictly below the current value."""
    out = _nones(len(x))
    for i in range(n, len(x)):
        if x[i] is None:
            continue
        w = [v for v in x[i - n:i] if v is not None]
        if len(w) < n:
            continue
        out[i] = 100.0 * sum(1 for v in w if v < x[i]) / n
    return out


# ============================================================================ volatility

@register("atr", "volatility", [("n", 14)], ["value"], "RMA(true range, n); TR = max(H-L, |H-C[-1]|, |L-C[-1]|)",
          "high, low, close", lambda p: (p["n"] - 1, 10 * p["n"]))
def _i_atr(f, n):
    return {"value": rma(true_range(f), int(n))}


@register("natr", "volatility", [("n", 14)], ["value"], "100 * ATR(n) / close", "high, low, close",
          lambda p: (p["n"] - 1, 10 * p["n"]))
def _i_natr(f, n):
    a = rma(true_range(f), int(n))
    return {"value": [None if v is None else 100 * v / c for v, c in zip(a, f.c)]}


@register("bb", "volatility", [("n", 20), ("mult", 2.0)], ["mid", "upper", "lower", "width", "pctb"],
          "mid = SMA(x,n); sd = population stdev(x,n); upper/lower = mid +/- mult*sd; width = (upper-lower)/mid; "
          "pctb = (x - lower)/(upper - lower)", "any series", lambda p: (p["n"] - 1, p["n"]), True)
def _i_bb(f, x, n, mult):
    m, s = sma(x, int(n)), stdev(x, int(n))
    up = [None if a is None else a + mult * b for a, b in zip(m, s)]
    lo = [None if a is None else a - mult * b for a, b in zip(m, s)]
    width = [None if a is None or not c else (a - b) / c for a, b, c in zip(up, lo, m)]
    pctb = [None if a is None or a == b or v is None else (v - b) / (a - b) for a, b, v in zip(up, lo, x)]
    return {"mid": m, "upper": up, "lower": lo, "width": width, "pctb": pctb}


@register("kc", "volatility", [("n", 20), ("mult", 2.0), ("atr_n", 10)], ["mid", "upper", "lower"],
          "mid = EMA(close,n); bands = mid +/- mult*ATR(atr_n)", "high, low, close",
          lambda p: (max(p["n"], p["atr_n"]), max(5 * p["n"], 10 * p["atr_n"])))
def _i_kc(f, n, mult, atr_n):
    m = ema(f.c, int(n))
    a = rma(true_range(f), int(atr_n))
    return {"mid": m, "upper": [None if u is None or v is None else u + mult * v for u, v in zip(m, a)],
            "lower": [None if u is None or v is None else u - mult * v for u, v in zip(m, a)]}


@register("donchian", "volatility", [("n", 20)], ["upper", "lower", "mid"],
          "upper = highest high of the last n bars INCLUDING the current bar; lower likewise; "
          "use donchian(n).upper[1] for the channel of the n bars before the current one",
          "high, low", lambda p: (p["n"] - 1, p["n"]))
def _i_donchian(f, n):
    u, l = rolling_max(f.h, int(n)), rolling_min(f.l, int(n))
    return {"upper": u, "lower": l, "mid": [None if a is None else (a + b) / 2 for a, b in zip(u, l)]}


@register("squeeze", "volatility", [("n", 20), ("bb_mult", 2.0), ("kc_mult", 1.5)], ["on", "mom"],
          "on = 1 while BB(n,bb_mult) sits inside KC(n,kc_mult, ATR n); mom = linreg value of "
          "close - mean(mid(HH,LL), SMA(close)) over n", "high, low, close",
          lambda p: (2 * p["n"], 10 * p["n"]))
def _i_squeeze(f, n, bb_mult, kc_mult):
    n = int(n)
    b = _i_bb(f, f.c, n, bb_mult)
    m = sma(f.c, n)
    a = rma(true_range(f), n)
    on = _nones(f.n)
    for i in range(f.n):
        if b["upper"][i] is None or a[i] is None or m[i] is None:
            continue
        on[i] = 1.0 if (b["upper"][i] < m[i] + kc_mult * a[i] and b["lower"][i] > m[i] - kc_mult * a[i]) else 0.0
    hh, ll = rolling_max(f.h, n), rolling_min(f.l, n)
    base = [None if None in (h, l_, s) else c - ((h + l_) / 2 + s) / 2 for h, l_, s, c in zip(hh, ll, m, f.c)]
    return {"on": on, "mom": _i_linreg(f, base, n)["value"]}


@register("realized_vol", "volatility", [("n", 30)], ["value", "per_bar"],
          "per_bar = sample stdev of log returns over n bars; value = per_bar * sqrt(bars per year) "
          "(stocks: 252 sessions x 390 minutes; crypto: 365 x 1440 minutes)", "close",
          lambda p: (p["n"], p["n"] + 1))
def _i_rv(f, n):
    lr = [None] + [math.log(f.c[i] / f.c[i - 1]) for i in range(1, f.n)]
    sd = stdev(lr, int(n), ddof=1)
    k = math.sqrt(f.bars_per_year())
    return {"value": [None if s is None else s * k for s in sd], "per_bar": sd}


@register("chop", "volatility", [("n", 14)], ["value"],
          "100 * log10(sum(TR,n) / (HH(n) - LL(n))) / log10(n)", "high, low, close", lambda p: (p["n"], p["n"] + 1))
def _i_chop(f, n):
    tr = true_range(f)
    st = rolling_sum(tr, int(n))
    hh, ll = rolling_max(f.h, int(n)), rolling_min(f.l, int(n))
    lg = math.log10(n)
    return {"value": [None if s is None or a is None or a == b else 100 * math.log10(s / (a - b)) / lg
                      for s, a, b in zip(st, hh, ll)]}


@register("er", "volatility", [("n", 10)], ["value"],
          "Kaufman efficiency ratio: |x - x[n]| / sum(|x[k] - x[k-1]|, n)", "any series",
          lambda p: (p["n"], p["n"] + 1), True)
def _i_er(f, x, n):
    n = int(n)
    out = _nones(len(x))
    ad = [None] + [None if x[i] is None or x[i - 1] is None else abs(x[i] - x[i - 1]) for i in range(1, len(x))]
    s = rolling_sum(ad, n)
    for i in range(n, len(x)):
        if s[i] and x[i] is not None and x[i - n] is not None:
            out[i] = abs(x[i] - x[i - n]) / s[i]
    return {"value": out}


# ============================================================================ volume and price references

@register("vwap", "volume", [], ["value", "sd", "upper1", "lower1", "upper2", "lower2"],
          "session-anchored: cumsum(hlc3*v)/cumsum(v) from the session's first bar; sd = sqrt(cumsum(v*tp^2)/cumsum(v) - vwap^2); "
          "bands at +/-1 and +/-2 sd", "high, low, close, volume, session",
          lambda p: (0, 0), missing="None outside the session; zero cumulative volume gives the bar's typical price", sessions=lambda p: 0)
def _i_vwap(f):
    return _anchored_vwap(f, [f.bar_in_sess[i] == 0 for i in range(f.n)], session_bound=True)


def _anchored_vwap(f: Frame, anchor: Sequence, session_bound: bool) -> Dict[str, Series]:
    tp = f.col("hlc3")
    val, sd = _nones(f.n), _nones(f.n)
    pv = pv2 = vv = 0.0
    started = False
    for i in range(f.n):
        if session_bound and f.sess[i] < 0:
            continue
        if anchor[i]:
            pv = pv2 = vv = 0.0
            started = True
        if not started:
            continue
        pv += tp[i] * f.v[i]
        pv2 += tp[i] * tp[i] * f.v[i]
        vv += f.v[i]
        if vv > 0:
            m = pv / vv
            var = pv2 / vv - m * m
            val[i], sd[i] = m, math.sqrt(var) if var > 0 else 0.0
        else:
            val[i], sd[i] = tp[i], 0.0
    out = {"value": val, "sd": sd}
    for k in (1, 2):
        out[f"upper{k}"] = [None if a is None else a + k * b for a, b in zip(val, sd)]
        out[f"lower{k}"] = [None if a is None else a - k * b for a, b in zip(val, sd)]
    return out


def anchored_vwap(f: Frame, anchor: Sequence) -> Dict[str, Series]:
    """VWAP accumulated from each bar where `anchor` is true (inclusive); used by avwap(cond)."""
    return _anchored_vwap(f, [bool(a) for a in anchor], session_bound=False)


@register("obv", "volume", [], ["value"], "cumulative +v on up closes, -v on down closes, 0 unchanged; starts at 0",
          "close, volume", lambda p: (0, 0),
          missing="cumulative from the first bar in the buffer, so only its changes (not its level) are comparable")
def _i_obv(f):
    out = _nones(f.n)
    acc = 0.0
    for i in range(f.n):
        if i:
            acc += f.v[i] if f.c[i] > f.c[i - 1] else (-f.v[i] if f.c[i] < f.c[i - 1] else 0.0)
        out[i] = acc
    return {"value": out}


@register("ad", "volume", [], ["value"], "Chaikin A/D: cumsum(((C-L)-(H-C))/(H-L) * V); 0 when H == L",
          "high, low, close, volume", lambda p: (0, 0),
          missing="cumulative from the buffer start: compare changes, not levels")
def _i_ad(f):
    out = _nones(f.n)
    acc = 0.0
    for i in range(f.n):
        rng = f.h[i] - f.l[i]
        acc += ((f.c[i] - f.l[i]) - (f.h[i] - f.c[i])) / rng * f.v[i] if rng else 0.0
        out[i] = acc
    return {"value": out}


@register("cmf", "volume", [("n", 20)], ["value"], "sum(MFM*V,n)/sum(V,n), MFM = ((C-L)-(H-C))/(H-L)",
          "high, low, close, volume", lambda p: (p["n"] - 1, p["n"]))
def _i_cmf(f, n):
    mfv = [(((c - l) - (h - c)) / (h - l) * v) if h != l else 0.0 for h, l, c, v in zip(f.h, f.l, f.c, f.v)]
    a, b = rolling_sum(mfv, int(n)), rolling_sum(f.v, int(n))
    return {"value": [None if x is None or not y else x / y for x, y in zip(a, b)]}


@register("mfi", "volume", [("n", 14)], ["value"],
          "tp = hlc3; raw flow = tp*v; MFI = 100 - 100/(1 + sum(pos flow,n)/sum(neg flow,n))",
          "high, low, close, volume", lambda p: (p["n"], p["n"] + 1))
def _i_mfi(f, n):
    tp = f.col("hlc3")
    pos, neg = _nones(f.n), _nones(f.n)
    for i in range(1, f.n):
        flow = tp[i] * f.v[i]
        pos[i] = flow if tp[i] > tp[i - 1] else 0.0
        neg[i] = flow if tp[i] < tp[i - 1] else 0.0
    sp, sn = rolling_sum(pos, int(n)), rolling_sum(neg, int(n))
    return {"value": [None if a is None else (100.0 if b == 0 else 100 - 100 / (1 + a / b)) for a, b in zip(sp, sn)]}


@register("force", "volume", [("n", 13)], ["value"], "EMA((close - close[-1]) * volume, n)", "close, volume",
          lambda p: (p["n"], 5 * p["n"]))
def _i_force(f, n):
    raw = [None] + [(f.c[i] - f.c[i - 1]) * f.v[i] for i in range(1, f.n)]
    return {"value": ema(raw, int(n))}


@register("rvol", "volume", [("n", 20)], ["value"],
          "volume / mean volume of the PREVIOUS n bars (the current bar is excluded from its own baseline)",
          "volume", lambda p: (p["n"], p["n"] + 1))
def _i_rvol(f, n):
    base = shift(sma(f.v, int(n)), 1)
    return {"value": [None if b is None or b == 0 else v / b for v, b in zip(f.v, base)]}


@register("rvol_tod", "volume", [("days", 10)], ["value"],
          "volume / mean volume of the bar at the same position in the previous `days` sessions",
          "volume, session", lambda p: (0, 0),
          missing="None until `days` earlier sessions contain a bar at the same position", sessions=lambda p: int(p['days']))
def _i_rvol_tod(f, days):
    days = int(days)
    hist: Dict[int, deque] = {}
    out = _nones(f.n)
    for i in range(f.n):
        k = f.bar_in_sess[i]
        if k < 0:
            continue
        q = hist.setdefault(k, deque(maxlen=days))
        if len(q) == days:
            m = sum(q) / days
            out[i] = f.v[i] / m if m else None
        q.append(f.v[i])
    return {"value": out}


@register("volume_profile", "volume", [("bins", 40), ("va", 0.70)], ["poc", "vah", "val", "dev_poc"],
          "each bar's volume spread evenly over its [low, high] in `bins` price bins per session; POC = fullest bin; "
          "value area grows from the POC to `va` of volume. poc/vah/val are the PREVIOUS session's; dev_poc is the "
          "developing POC of the current session through the current bar",
          "high, low, volume, session", lambda p: (0, 0),
          missing="approximated from OHLCV bars, not trade-level volume at price; None for the first session",
          notes="Bar-based approximation. A trade-level profile needs tick data (see data requirements).", sessions=lambda p: 1)
def _i_vp(f, bins, va):
    bins = int(bins)
    poc, vah, val, dev = _nones(f.n), _nones(f.n), _nones(f.n), _nones(f.n)
    cur, prev_levels = None, None
    idx: List[int] = []
    for i in range(f.n):
        s = f.sess[i]
        if s < 0:
            continue
        if s != cur:
            if idx:
                prev_levels = _profile(f, idx, bins, va)
            cur, idx = s, []
        idx.append(i)
        if prev_levels:
            poc[i], vah[i], val[i] = prev_levels
        dev[i] = _profile(f, idx, bins, va)[0]
    return {"poc": poc, "vah": vah, "val": val, "dev_poc": dev}


def _profile(f: Frame, idx: List[int], bins: int, va: float):
    lo = min(f.l[i] for i in idx)
    hi = max(f.h[i] for i in idx)
    if hi <= lo:
        return (lo, lo, lo)
    w = (hi - lo) / bins
    vol = [0.0] * bins
    for i in idx:
        a = min(bins - 1, int((f.l[i] - lo) / w))
        b = min(bins - 1, int((f.h[i] - lo) / w))
        share = f.v[i] / (b - a + 1)
        for k in range(a, b + 1):
            vol[k] += share
    p = max(range(bins), key=lambda k: vol[k])
    total = sum(vol)
    a = b = p
    acc = vol[p]
    while total and acc / total < va and (a > 0 or b < bins - 1):
        up = vol[b + 1] if b < bins - 1 else -1
        dn = vol[a - 1] if a > 0 else -1
        if up >= dn:
            b += 1; acc += vol[b]
        else:
            a -= 1; acc += vol[a]
    return (lo + (p + 0.5) * w, lo + (b + 1) * w, lo + a * w)


# ============================================================================ market structure

@register("session", "structure", [], ["open", "high", "low", "prev_open", "prev_high", "prev_low", "prev_close", "gap"],
          "current session's open and running high/low through the current bar; previous session's OHLC; "
          "gap = session open / previous close - 1", "open, high, low, close, session", lambda p: (0, 0),
          missing="prev_* and gap are None during the first session in the buffer", sessions=lambda p: 1)
def _i_session(f):
    names = ["open", "high", "low", "prev_open", "prev_high", "prev_low", "prev_close", "gap"]
    out = {k: _nones(f.n) for k in names}
    cur = None
    so = sh = sl = None
    prev = None           # (o, h, l, c)
    last_close = None
    for i in range(f.n):
        s = f.sess[i]
        if s < 0:
            continue
        if s != cur:
            if cur is not None:
                prev = (so, sh, sl, last_close)
            cur, so, sh, sl = s, f.o[i], f.h[i], f.l[i]
        sh, sl = max(sh, f.h[i]), min(sl, f.l[i])
        last_close = f.c[i]
        out["open"][i], out["high"][i], out["low"][i] = so, sh, sl
        if prev:
            out["prev_open"][i], out["prev_high"][i], out["prev_low"][i], out["prev_close"][i] = prev
            out["gap"][i] = so / prev[3] - 1 if prev[3] else None
    return out


@register("opening_range", "structure", [("minutes", 30)], ["high", "low", "mid", "done"],
          "high/low of the session's bars that open within the first `minutes`; published from the bar that "
          "completes the range and held for the rest of the session; done = 1 once published",
          "high, low, session", lambda p: (0, 0),
          missing="None before the range completes (no look-ahead); crypto sessions start 00:00 UTC", sessions=lambda p: 0)
def _i_or(f, minutes):
    span = int(minutes) * 60_000
    out = {k: _nones(f.n) for k in ("high", "low", "mid", "done")}
    cur, hi, lo, pub = None, None, None, False
    for i in range(f.n):
        s = f.sess[i]
        if s < 0:
            continue
        if s != cur:
            cur, hi, lo, pub = s, None, None, False
        start = f.sess_open[i]
        if f.t[i] < start + span:
            hi = f.h[i] if hi is None else max(hi, f.h[i])
            lo = f.l[i] if lo is None else min(lo, f.l[i])
            if f.t[i] + f.step >= start + span:
                pub = True
        if pub and hi is not None:
            out["high"][i], out["low"][i], out["mid"][i], out["done"][i] = hi, lo, (hi + lo) / 2, 1.0
        else:
            out["done"][i] = 0.0
    return out


@register("window_range", "structure", [("start", 0), ("end", 480)], ["high", "low", "done"],
          "high/low of the current day's bars opening between local minute `start` and `end` (minutes after "
          "local midnight: New York for stocks, UTC for crypto); published once the window has closed",
          "high, low", lambda p: (0, 0), missing="None until the window closes each day", sessions=lambda p: 1)
def _i_window(f, start, end):
    start, end = int(start), int(end)
    out = {k: _nones(f.n) for k in ("high", "low", "done")}
    day, hi, lo = None, None, None
    for i in range(f.n):
        d = f.t[i] // 86_400_000 if not is_equity(f.asset_type) else f.sess[i]
        if d != day:
            day, hi, lo = d, None, None
        tod = f.tod[i]
        if start <= tod < end:
            hi = f.h[i] if hi is None else max(hi, f.h[i])
            lo = f.l[i] if lo is None else min(lo, f.l[i])
        closed = tod + f.step // 60_000 >= end
        if closed and hi is not None and tod >= start:
            out["high"][i], out["low"][i], out["done"][i] = hi, lo, 1.0
        else:
            out["done"][i] = 0.0
    return out


@register("pivots", "structure", [("kind", "classic")], ["p", "r1", "r2", "r3", "s1", "s2", "s3"],
          "from the previous session's H, L, C. classic: P=(H+L+C)/3, R1=2P-L, S1=2P-H, R2=P+(H-L), S2=P-(H-L), "
          "R3=H+2(P-L), S3=L-2(H-P). camarilla: C +/- (H-L)*1.1/12, /6, /4. fibonacci: P +/- 0.382, 0.618, 1.0 x (H-L). "
          "woodie: P=(H+L+2C)/4, R1=2P-L, S1=2P-H, R2=P+H-L, S2=P-(H-L)", "high, low, close, session",
          lambda p: (0, 0), missing="None during the first session in the buffer", sessions=lambda p: 1)
def _i_pivots(f, kind):
    s = _i_session(f)
    out = {k: _nones(f.n) for k in ("p", "r1", "r2", "r3", "s1", "s2", "s3")}
    for i in range(f.n):
        H, L, C = s["prev_high"][i], s["prev_low"][i], s["prev_close"][i]
        if H is None:
            continue
        R = H - L
        if kind == "camarilla":
            P = (H + L + C) / 3
            vals = (P, C + R * 1.1 / 12, C + R * 1.1 / 6, C + R * 1.1 / 4, C - R * 1.1 / 12, C - R * 1.1 / 6, C - R * 1.1 / 4)
        elif kind == "fibonacci":
            P = (H + L + C) / 3
            vals = (P, P + 0.382 * R, P + 0.618 * R, P + R, P - 0.382 * R, P - 0.618 * R, P - R)
        elif kind == "woodie":
            P = (H + L + 2 * C) / 4
            vals = (P, 2 * P - L, P + R, H + 2 * (P - L), 2 * P - H, P - R, L - 2 * (H - P))
        else:
            P = (H + L + C) / 3
            vals = (P, 2 * P - L, P + R, H + 2 * (P - L), 2 * P - H, P - R, L - 2 * (H - P))
        for k, v in zip(("p", "r1", "r2", "r3", "s1", "s2", "s3"), vals):
            out[k][i] = v
    return out


@register("swings", "structure", [("n", 3)], ["high", "low", "high_prev", "low_prev", "high_prev2", "low_prev2",
                                             "age_high", "age_low"],
          "a swing high at bar j has a high greater than the n bars on each side; it becomes KNOWN at bar j+n "
          "(confirmation delay) and is published from then on. high/low = latest confirmed swing prices; "
          "*_prev and *_prev2 = the one and two before (for higher-high / pattern tests); age = bars since the swing bar",
          "high, low", lambda p: (2 * p["n"], 2 * p["n"] + 1),
          missing="None until enough swings are confirmed", notes="Never repaints: a swing is published only once confirmed.")
def _i_swings(f, n):
    n = int(n)
    keys = ("high", "low", "high_prev", "low_prev", "high_prev2", "low_prev2", "age_high", "age_low")
    out = {k: _nones(f.n) for k in keys}
    hs, ls = [None, None, None], [None, None, None]
    jh = jl = None
    for i in range(f.n):
        j = i - n
        if j - n >= 0:
            if all(f.h[j] > f.h[k] for k in range(j - n, j + n + 1) if k != j):
                hs = [f.h[j], hs[0], hs[1]]
                jh = j
            if all(f.l[j] < f.l[k] for k in range(j - n, j + n + 1) if k != j):
                ls = [f.l[j], ls[0], ls[1]]
                jl = j
        out["high"][i], out["high_prev"][i], out["high_prev2"][i] = hs
        out["low"][i], out["low_prev"][i], out["low_prev2"][i] = ls
        out["age_high"][i] = None if jh is None else float(i - jh)
        out["age_low"][i] = None if jl is None else float(i - jl)
    return out


@register("fvg", "structure", [], ["bull_top", "bull_bottom", "bear_top", "bear_bottom"],
          "three-bar fair value gap known at bar i: bullish when low[i] > high[i-2] (gap = high[i-2]..low[i]); "
          "bearish when high[i] < low[i-2]. The most recent gap of each side is held until price trades back through it",
          "high, low", lambda p: (2, 3))
def _i_fvg(f):
    out = {k: _nones(f.n) for k in ("bull_top", "bull_bottom", "bear_top", "bear_bottom")}
    bull = bear = None
    for i in range(f.n):
        if bull and f.l[i] <= bull[1]:
            bull = None                      # filled
        if bear and f.h[i] >= bear[0]:
            bear = None
        if i >= 2 and f.l[i] > f.h[i - 2]:
            bull = (f.l[i], f.h[i - 2])
        if i >= 2 and f.h[i] < f.l[i - 2]:
            bear = (f.l[i - 2], f.h[i])
        if bull:
            out["bull_top"][i], out["bull_bottom"][i] = bull
        if bear:
            out["bear_top"][i], out["bear_bottom"][i] = bear
    return out


# ============================================================================ candles

def _candle_parts(f: Frame, i: int):
    o, h, l, c = f.o[i], f.h[i], f.l[i], f.c[i]
    body = abs(c - o)
    rng = h - l
    return o, h, l, c, body, rng, h - max(o, c), min(o, c) - l


@register("candle", "pattern", [], ["bull_engulf", "bear_engulf", "hammer", "shooting_star", "doji", "inside",
                                     "outside", "morning_star", "evening_star", "three_soldiers", "three_crows",
                                     "marubozu_up", "marubozu_down", "ibs", "range"],
          "bull_engulf: prior bar bearish, current bullish, current body covers prior body and is larger. "
          "hammer: range > 0, body >= 5% of range, lower wick >= 2x body, upper wick <= 25% of range (shooting star mirrored). "
          "doji: body <= 10% of range. inside: H < H[-1] and L > L[-1]; outside: H > H[-1] and L < L[-1]. "
          "morning_star: bar -2 bearish with body >= 60% of its range, bar -1 body <= 30% of bar -2 body, current bullish "
          "closing above bar -2's body midpoint (no gap requirement, since crypto trades continuously). "
          "three_soldiers: 3 bullish bars, rising closes, each opening inside the prior body, upper wicks <= 25% of range. "
          "marubozu: body >= 90% of range. ibs = (C-L)/(H-L). Each flag is 1.0 or 0.0",
          "open, high, low, close", lambda p: (2, 3))
def _i_candle(f):
    names = ["bull_engulf", "bear_engulf", "hammer", "shooting_star", "doji", "inside", "outside", "morning_star",
             "evening_star", "three_soldiers", "three_crows", "marubozu_up", "marubozu_down", "ibs", "range"]
    out = {k: _nones(f.n) for k in names}
    for i in range(f.n):
        o, h, l, c, body, rng, uw, lw = _candle_parts(f, i)
        out["range"][i] = rng
        out["ibs"][i] = (c - l) / rng if rng else 0.5
        out["doji"][i] = 1.0 if rng and body <= 0.1 * rng else 0.0
        out["hammer"][i] = 1.0 if rng and body >= 0.05 * rng and lw >= 2 * body and uw <= 0.25 * rng else 0.0
        out["shooting_star"][i] = 1.0 if rng and body >= 0.05 * rng and uw >= 2 * body and lw <= 0.25 * rng else 0.0
        out["marubozu_up"][i] = 1.0 if rng and c > o and body >= 0.9 * rng else 0.0
        out["marubozu_down"][i] = 1.0 if rng and c < o and body >= 0.9 * rng else 0.0
        if i < 1:
            continue
        o1, h1, l1, c1, body1, rng1, _, _ = _candle_parts(f, i - 1)
        out["bull_engulf"][i] = 1.0 if c1 < o1 and c > o and o <= c1 and c >= o1 and body > body1 else 0.0
        out["bear_engulf"][i] = 1.0 if c1 > o1 and c < o and o >= c1 and c <= o1 and body > body1 else 0.0
        out["inside"][i] = 1.0 if h < h1 and l > l1 else 0.0
        out["outside"][i] = 1.0 if h > h1 and l < l1 else 0.0
        if i < 2:
            continue
        o2, h2, l2, c2, body2, rng2, _, _ = _candle_parts(f, i - 2)
        mid2 = (o2 + c2) / 2
        out["morning_star"][i] = 1.0 if (c2 < o2 and rng2 and body2 >= 0.6 * rng2 and body1 <= 0.3 * body2
                                         and c > o and c > mid2) else 0.0
        out["evening_star"][i] = 1.0 if (c2 > o2 and rng2 and body2 >= 0.6 * rng2 and body1 <= 0.3 * body2
                                         and c < o and c < mid2) else 0.0
        bars = [(f.o[k], f.h[k], f.l[k], f.c[k]) for k in (i - 2, i - 1, i)]
        out["three_soldiers"][i] = 1.0 if all(
            b[3] > b[0] and (b[1] - b[3]) <= 0.25 * (b[1] - b[2] or 1) for b in bars) and all(
            bars[k][3] > bars[k - 1][3] and bars[k - 1][0] <= bars[k][0] <= bars[k - 1][3] for k in (1, 2)) else 0.0
        out["three_crows"][i] = 1.0 if all(
            b[3] < b[0] and (b[3] - b[2]) <= 0.25 * (b[1] - b[2] or 1) for b in bars) and all(
            bars[k][3] < bars[k - 1][3] and bars[k - 1][3] <= bars[k][0] <= bars[k - 1][0] for k in (1, 2)) else 0.0
    return out


@register("nr", "pattern", [("n", 7)], ["value"],
          "1.0 when the current bar's range (H-L) is the smallest of the last n bars (NR4 / NR7), else 0.0",
          "high, low", lambda p: (p["n"] - 1, p["n"]))
def _i_nr(f, n):
    r = [h - l for h, l in zip(f.h, f.l)]
    m = rolling_min(r, int(n))
    return {"value": [None if b is None else (1.0 if a <= b else 0.0) for a, b in zip(r, m)]}


# ============================================================================ order flow (real data only)

@register("orderflow", "orderflow", [], ["delta", "cvd", "imbalance", "trades"],
          "from venue trade prints aggregated per bar by aggressor side: delta = buy volume - sell volume; "
          "cvd = session cumulative delta; imbalance = delta / (buy + sell); trades = print count",
          "buy_vol, sell_vol, n_trades (recorded from the venue's trade feed)", lambda p: (0, 0),
          missing="None for bars without recorded prints. Never estimated from OHLCV; see est_delta for a labelled estimate",
          requires=("buy_vol", "sell_vol"), sessions=lambda p: 0)
def _i_orderflow(f):
    b, s, n = f.col("buy_vol"), f.col("sell_vol"), f.col("n_trades")
    delta = [None if x is None or y is None else x - y for x, y in zip(b, s)]
    imb = [None if x is None or y is None or (x + y) == 0 else (x - y) / (x + y) for x, y in zip(b, s)]
    cvd = _nones(f.n)
    cur, acc = None, 0.0
    for i in range(f.n):
        if delta[i] is None:
            continue
        if f.sess[i] != cur:
            cur, acc = f.sess[i], 0.0
        acc += delta[i]
        cvd[i] = acc
    return {"delta": delta, "cvd": cvd, "imbalance": imb, "trades": list(n)}


@register("book", "orderflow", [], ["spread_bps", "imbalance", "bid_depth", "ask_depth"],
          "from the order-book snapshot taken at bar close: spread_bps = 1e4*(ask-bid)/mid; imbalance = "
          "(bid_depth - ask_depth)/(bid_depth + ask_depth) over the recorded levels",
          "bid, ask, bid_depth, ask_depth (recorded snapshots)", lambda p: (0, 0),
          missing="None for bars without a recorded snapshot; never estimated", requires=("bid", "ask"))
def _i_book(f):
    bid, ask, bd, ad = f.col("bid"), f.col("ask"), f.col("bid_depth"), f.col("ask_depth")
    spread = [None if a is None or b is None else 1e4 * (a - b) / ((a + b) / 2) for b, a in zip(bid, ask)]
    imb = [None if x is None or y is None or (x + y) == 0 else (x - y) / (x + y) for x, y in zip(bd, ad)]
    return {"spread_bps": spread, "imbalance": imb, "bid_depth": list(bd), "ask_depth": list(ad)}


@register("est_delta", "orderflow", [], ["value"],
          "ESTIMATE, not order flow: close-location value x volume = ((C-L)-(H-C))/(H-L) * V. Labelled so it "
          "is never mistaken for measured aggressor volume", "high, low, close, volume", lambda p: (0, 0))
def _i_est_delta(f):
    return {"value": [(((c - l) - (h - c)) / (h - l) * v) if h != l else 0.0 for h, l, c, v in zip(f.h, f.l, f.c, f.v)]}


# ============================================================================ additions for the strategy library

@register("fisher", "momentum", [("n", 10)], ["value", "signal"],
          "Ehlers: x = 0.33*2*((hl2 - LL(n))/(HH(n) - LL(n)) - 0.5) + 0.67*x[-1], clipped to +/-0.999; "
          "fish = 0.5*ln((1+x)/(1-x)) + 0.5*fish[-1]; signal = fish one bar ago", "high, low",
          lambda p: (p["n"], 10 * p["n"]))
def _i_fisher(f, n):
    n = int(n)
    mid = f.col("hl2")
    hh, ll = rolling_max(mid, n), rolling_min(mid, n)
    val, sig = _nones(f.n), _nones(f.n)
    x = fish = 0.0
    started = False
    for i in range(f.n):
        if hh[i] is None:
            continue
        rng = hh[i] - ll[i]
        raw = 0.0 if rng == 0 else (mid[i] - ll[i]) / rng - 0.5
        x = 0.33 * 2 * raw + 0.67 * x
        x = max(-0.999, min(0.999, x))
        prev = fish
        fish = 0.5 * math.log((1 + x) / (1 - x)) + 0.5 * fish
        val[i] = fish
        sig[i] = prev if started else None
        started = True
    return {"value": val, "signal": sig}


@register("mass_index", "volatility", [("ema_n", 9), ("sum_n", 25)], ["value"],
          "Dorsey: sum over sum_n bars of EMA(H-L, ema_n) / EMA(EMA(H-L, ema_n), ema_n)", "high, low",
          lambda p: (2 * p["ema_n"] + p["sum_n"], 10 * p["ema_n"] + p["sum_n"]))
def _i_mass(f, ema_n, sum_n):
    r = [h - l for h, l in zip(f.h, f.l)]
    e1 = ema(r, int(ema_n))
    e2 = ema(e1, int(ema_n))
    ratio = [None if a is None or not b else a / b for a, b in zip(e1, e2)]
    return {"value": rolling_sum(ratio, int(sum_n))}


@register("td_setup", "pattern", [("lookback", 4)], ["buy", "sell"],
          "DeMark setup counts: buy = consecutive bars with close < close `lookback` bars earlier (resets otherwise); "
          "sell = consecutive bars with close > close `lookback` bars earlier", "close", lambda p: (p["lookback"], p["lookback"] + 9))
def _i_td(f, lookback):
    k = int(lookback)
    b, s_ = _nones(f.n), _nones(f.n)
    cb = cs = 0
    for i in range(f.n):
        if i < k:
            continue
        cb = cb + 1 if f.c[i] < f.c[i - k] else 0
        cs = cs + 1 if f.c[i] > f.c[i - k] else 0
        b[i], s_[i] = float(cb), float(cs)
    return {"buy": b, "sell": s_}


@register("streak", "pattern", [], ["value"],
          "signed count of consecutive higher (+) or lower (-) closes; 0 on an unchanged close", "close", lambda p: (1, 2))
def _i_streak(f):
    out = _nones(f.n)
    run = 0
    for i in range(1, f.n):
        if f.c[i] > f.c[i - 1]:
            run = run + 1 if run > 0 else 1
        elif f.c[i] < f.c[i - 1]:
            run = run - 1 if run < 0 else -1
        else:
            run = 0
        out[i] = float(run)
    return {"value": out}


@register("variance_ratio", "statistical", [("n", 120), ("k", 5)], ["value"],
          "Lo-MacKinlay style: var of k-bar log returns / (k * var of 1-bar log returns), both over the last n bars; "
          ">1 trending, <1 mean-reverting", "close", lambda p: (p["n"] + p["k"], p["n"] + p["k"] + 1))
def _i_vr(f, n, k):
    n, k = int(n), int(k)
    lr = [None] + [math.log(f.c[i] / f.c[i - 1]) for i in range(1, f.n)]
    lk = [None] * f.n
    for i in range(k, f.n):
        lk[i] = math.log(f.c[i] / f.c[i - k])
    v1, vk = stdev(lr, n, ddof=1), stdev(lk, n, ddof=1)
    return {"value": [None if a is None or not b else (a * a) / (k * b * b) for a, b in zip(vk, v1)]}


@register("autocorr", "statistical", [("n", 60), ("lag", 1)], ["value"],
          "Pearson autocorrelation of 1-bar returns at `lag` over the last n bars", "close",
          lambda p: (p["n"] + p["lag"] + 1, p["n"] + p["lag"] + 2))
def _i_autocorr(f, n, lag):
    r = [None] + [f.c[i] / f.c[i - 1] - 1 for i in range(1, f.n)]
    return {"value": rolling_corr(r, shift(r, int(lag)), int(n))}


@register("tod_return", "statistical", [("days", 20), ("k", 6)], ["mean", "t"],
          "for the bar at position p of the session: mean (and t-statistic) of the k-bar return that started at the same "
          "position p on each of the previous `days` sessions. Uses only sessions already finished",
          "close, session", lambda p: (0, 0), missing="None until `days` earlier sessions have that position",
          sessions=lambda p: int(p["days"]))
def _i_tod_return(f, days, k):
    days, k = int(days), int(k)
    hist: Dict[int, deque] = {}
    pending: List[tuple] = []           # (position, start index) awaiting completion of their k-bar return
    mean, tstat = _nones(f.n), _nones(f.n)
    for i in range(f.n):
        p = f.bar_in_sess[i]
        still = []
        for pos, st in pending:
            if i - st == k and f.sess[i] == f.sess[st]:
                hist.setdefault(pos, deque(maxlen=days)).append(f.c[i] / f.c[st] - 1)
            elif i - st < k and f.sess[i] == f.sess[st]:
                still.append((pos, st))
        pending = still
        if p < 0:
            continue
        q = hist.get(p)
        if q and len(q) == days:
            m = sum(q) / days
            sd = math.sqrt(sum((x - m) ** 2 for x in q) / (days - 1)) if days > 1 else 0.0
            mean[i] = m
            tstat[i] = m / (sd / math.sqrt(days)) if sd else 0.0
        pending.append((p, i))
    return {"mean": mean, "t": tstat}


@register("premarket", "structure", [], ["high", "low", "last", "volume", "done"],
          "stocks with extended-hours bars: high, low, last price and volume of the bars before the regular open on the "
          "same local date; published from the session's first bar", "high, low, close, volume (extended hours)",
          lambda p: (0, 0), missing="None when the series has no pre-market bars (subscribe with extended hours)",
          sessions=lambda p: 0)
def _i_premarket(f):
    out = {k: _nones(f.n) for k in ("high", "low", "last", "volume", "done")}
    cur, hi, lo, last, vol, day = None, None, None, None, 0.0, None
    for i in range(f.n):
        if f.day[i] != day:
            day, hi, lo, last, vol, cur = f.day[i], None, None, None, 0.0, None
        if f.sess[i] < 0:
            if f.sess_open[i] == 0 or f.tod[i] < 570:
                hi = f.h[i] if hi is None else max(hi, f.h[i])
                lo = f.l[i] if lo is None else min(lo, f.l[i])
                last, vol = f.c[i], vol + f.v[i]
            continue
        if hi is not None:
            out["high"][i], out["low"][i], out["last"][i], out["volume"][i], out["done"][i] = hi, lo, last, vol, 1.0
        else:
            out["done"][i] = 0.0
    return out


@register("weekend", "structure", [("fri_close_hour", 21), ("reopen_hour", 23)], ["high", "low", "fri_close", "gap"],
          "crypto: high/low of Saturday-Sunday UTC, published from Monday 00:00 UTC for the week; fri_close = close of the "
          "bar ending at Friday `fri_close_hour`:00 UTC (a proxy for the CME bitcoin futures close), published from Sunday "
          "`reopen_hour`:00 UTC; gap = price at that reopen / fri_close - 1", "high, low, close",
          lambda p: (0, 0), missing="None until the first full weekend in the buffer", sessions=lambda p: 3)
def _i_weekend(f, fri_close_hour, reopen_hour):
    out = {k: _nones(f.n) for k in ("high", "low", "fri_close", "gap")}
    wk_hi = wk_lo = pub_hi = pub_lo = None
    fri = fri_pub = gap = None
    for i in range(f.n):
        dow, tod = f.dow[i], f.tod[i]
        end_tod = tod + f.step // 60_000
        if dow in (5, 6):
            wk_hi = f.h[i] if wk_hi is None else max(wk_hi, f.h[i])
            wk_lo = f.l[i] if wk_lo is None else min(wk_lo, f.l[i])
        if dow == 0 and wk_hi is not None:
            pub_hi, pub_lo, wk_hi, wk_lo = wk_hi, wk_lo, None, None
        if dow == 4 and end_tod == int(fri_close_hour) * 60:
            fri = f.c[i]
        if dow == 6 and end_tod == int(reopen_hour) * 60 and fri:
            fri_pub, gap = fri, f.c[i] / fri - 1
        if dow == 4 and end_tod >= int(fri_close_hour) * 60:
            fri_pub = gap = None
        out["high"][i], out["low"][i] = pub_hi, pub_lo
        out["fri_close"][i], out["gap"][i] = fri_pub, gap
    return out


# ============================================================================ relative (two series)

def rolling_corr(x: Sequence[Num], y: Sequence[Num], n: int) -> Series:
    out = _nones(len(x))
    for i in range(n - 1, len(x)):
        a, b = x[i - n + 1:i + 1], y[i - n + 1:i + 1]
        if None in a or None in b:
            continue
        ma, mb = sum(a) / n, sum(b) / n
        sab = sum((p - ma) * (q - mb) for p, q in zip(a, b))
        saa = sum((p - ma) ** 2 for p in a)
        sbb = sum((q - mb) ** 2 for q in b)
        out[i] = sab / math.sqrt(saa * sbb) if saa and sbb else 0.0
    return out


def rolling_beta(x: Sequence[Num], y: Sequence[Num], n: int) -> Series:
    """OLS slope of x on y over the last n pairs."""
    out = _nones(len(x))
    for i in range(n - 1, len(x)):
        a, b = x[i - n + 1:i + 1], y[i - n + 1:i + 1]
        if None in a or None in b:
            continue
        ma, mb = sum(a) / n, sum(b) / n
        sab = sum((p - ma) * (q - mb) for p, q in zip(a, b))
        sbb = sum((q - mb) ** 2 for q in b)
        out[i] = sab / sbb if sbb else None
    return out


def zscore(x: Sequence[Num], n: int) -> Series:
    m, s = sma(x, n), stdev(x, n, ddof=1)
    return [None if v is None or a is None or not b else (v - a) / b for v, a, b in zip(x, m, s)]


def spread_z(x: Sequence[Num], y: Sequence[Num], n: int) -> Series:
    """z-score of log(x) - beta*log(y), beta re-estimated by OLS over the same n bars each bar."""
    lx = [None if v is None or v <= 0 else math.log(v) for v in x]
    ly = [None if v is None or v <= 0 else math.log(v) for v in y]
    beta = rolling_beta(lx, ly, n)
    spread = [None if a is None or b is None or c is None else a - c * b for a, b, c in zip(lx, ly, beta)]
    return zscore(spread, n)


def catalog() -> List[dict]:
    rows = []
    for ind in REGISTRY.values():
        first, stable = ind.warmup({k: d for k, d in ind.params})
        rows.append({"name": ind.name, "category": ind.category, "params": {k: d for k, d in ind.params},
                     "outputs": ind.outputs, "inputs": ind.inputs, "formula": ind.formula,
                     "warmup_first": first, "warmup_stable": stable, "missing": ind.missing,
                     "requires": list(ind.requires), "series_input": ind.series_input, "notes": ind.notes,
                     "sessions_needed": None if ind.sessions is None else ind.sessions({k: d for k, d in ind.params}),
                     "update": "once per completed bar"})
    return rows
