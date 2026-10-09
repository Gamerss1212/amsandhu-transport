"""Base signal generators: each returns a causal desired-direction series in {-1, 0, +1} (NaN-free).

+1 = want to be long, -1 = want to be short, 0 = flat. Whether shorting is allowed is decided later by the market
(no stock shorting without borrow data; no spot-crypto shorting) and by the risk engine, never here.

Each generator is registered with its family, economic hypothesis, data needs, default parameters, a small parameter
grid for stability tests, and an evidence grade for the IDEA (A peer-reviewed, B working paper / credible quant
source, C industry or book, D trader hypothesis). A grade describes the published evidence for the idea, not this
software's own test result, which is always reported separately.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import numpy as np

from tradingai.features import indicators as I
from tradingai.features.registry import FeatureFrame

A = np.ndarray


@dataclass(frozen=True)
class Generator:
    key: str
    family: str
    fn: Callable[..., A]
    hypothesis: str
    params: dict
    grid: dict
    features: tuple[str, ...]
    markets: tuple[str, ...]
    timeframes: tuple[str, ...]
    grade: str
    source: str
    failure_regimes: str
    requires: tuple[str, ...] = ()
    filters: tuple[str, ...] = ("none", "trend200", "adx", "vol_band", "session", "relvol")
    exits: tuple[str, ...] = ("flip", "atr_bracket", "time", "trail")
    pairs: bool = False


GEN: dict[str, Generator] = {}
ALL = ("crypto", "stock", "etf", "fx", "future")
INTRA = ("1m", "5m", "15m", "30m", "1h")
ANY_TF = ("5m", "15m", "30m", "1h", "4h", "1d")
SESSION_MARKETS = ("stock", "etf", "future")


def gen(key, family, hypothesis, params, grid, features=(), markets=ALL, timeframes=ANY_TF, grade="D",
        source="trader hypothesis: needs independent testing", failure="", requires=(), filters=None, exits=None,
        pairs=False):
    def deco(fn):
        kw = {}
        if filters is not None:
            kw["filters"] = tuple(filters)
        if exits is not None:
            kw["exits"] = tuple(exits)
        GEN[key] = Generator(key, family, fn, hypothesis, dict(params), dict(grid), tuple(features), tuple(markets),
                             tuple(timeframes), grade, source, failure, tuple(requires), pairs=pairs, **kw)
        return fn
    return deco


# ----------------------------------------------------------------------------- helpers

def _z(x: A) -> A:
    return np.nan_to_num(x, nan=0.0)


def state(cond_long: A, cond_short: A | None = None) -> A:
    out = np.where(_z(cond_long.astype(float)) > 0, 1.0, 0.0)
    if cond_short is not None:
        out = np.where(_z(cond_short.astype(float)) > 0, -1.0, out)
    return out


def latch(enter_long: A, exit_long: A, enter_short: A | None = None, exit_short: A | None = None) -> A:
    """Stateful: enter on a condition, stay until the exit condition. Causal (one pass forward)."""
    n = len(enter_long)
    out = np.zeros(n)
    pos = 0.0
    el, xl = np.nan_to_num(enter_long.astype(float)) > 0, np.nan_to_num(exit_long.astype(float)) > 0
    es = np.nan_to_num(enter_short.astype(float)) > 0 if enter_short is not None else np.zeros(n, bool)
    xs = np.nan_to_num(exit_short.astype(float)) > 0 if exit_short is not None else np.zeros(n, bool)
    for i in range(n):
        if pos > 0 and xl[i]:
            pos = 0.0
        elif pos < 0 and xs[i]:
            pos = 0.0
        if pos == 0:
            if el[i]:
                pos = 1.0
            elif es[i]:
                pos = -1.0
        out[i] = pos
    return out


def cross_up(a: A, b: A) -> A:
    return (a > b) & (I.shift(a, 1) <= I.shift(b, 1))


def cross_dn(a: A, b: A) -> A:
    return (a < b) & (I.shift(a, 1) >= I.shift(b, 1))


# ============================================================================ trend following

@gen("sma_cross", "trend", "Persistent trends: a fast average above a slow one tends to stay above for a while",
     {"fast": 20, "slow": 100}, {"fast": [10, 20, 50], "slow": [50, 100, 200]}, ("sma",), grade="C",
     source="moving-average timing (Faber 2007, B for the monthly version); intraday use is a hypothesis",
     failure="choppy ranges: repeated whipsaw")
def sma_cross(f: FeatureFrame, fast=20, slow=100):
    return state(I.sma(f.c, fast) > I.sma(f.c, slow), I.sma(f.c, fast) < I.sma(f.c, slow))


@gen("ema_cross", "trend", "Same as SMA cross, faster reaction", {"fast": 12, "slow": 48},
     {"fast": [8, 12, 21], "slow": [34, 48, 89]}, ("ema",), failure="ranges")
def ema_cross(f, fast=12, slow=48):
    return state(I.ema(f.c, fast) > I.ema(f.c, slow), I.ema(f.c, fast) < I.ema(f.c, slow))


@gen("triple_ma", "trend", "Trend confirmed only when three averages are stacked in order", {"a": 10, "b": 30, "c": 90},
     {"a": [5, 10], "b": [20, 30], "c": [60, 90, 150]}, ("ema",), failure="late entries; ranges")
def triple_ma(f, a=10, b=30, c=90):
    e1, e2, e3 = I.ema(f.c, a), I.ema(f.c, b), I.ema(f.c, c)
    return state((e1 > e2) & (e2 > e3), (e1 < e2) & (e2 < e3))


@gen("hma_trend", "trend", "Hull MA direction: low-lag trend proxy", {"n": 50}, {"n": [21, 50, 100]}, ("hma",))
def hma_trend(f, n=50):
    h = I.hma(f.c, n)
    return state(h > I.shift(h, 1), h < I.shift(h, 1))


@gen("kama_trend", "trend", "Adaptive MA flattens in noise, follows in trends", {"n": 10}, {"n": [10, 20, 30]},
     ("kama",))
def kama_trend(f, n=10):
    k = I.kama(f.c, n)
    return state(f.c > k, f.c < k)


@gen("linreg_trend", "trend", "A significant positive regression slope signals a trend",
     {"n": 50, "r2": 0.5}, {"n": [30, 50, 100], "r2": [0.3, 0.5, 0.7]}, ("linreg",))
def linreg_trend(f, n=50, r2=0.5):
    s, _, q = I.linreg(f.c, n)
    return state((s > 0) & (q >= r2), (s < 0) & (q >= r2))


@gen("donchian_trend", "trend", "Turtle-style: buy new N-bar highs, exit on M-bar lows", {"entry": 55, "exit": 20},
     {"entry": [20, 55, 100], "exit": [10, 20, 50]}, ("donchian",), grade="C",
     source="Turtle trading rules (industry, C)", failure="false breakouts in ranges", exits=("flip", "trail"))
def donchian_trend(f, entry=55, exit=20):
    up, dn, _ = I.donchian(f.h, f.l, entry)
    xup, xdn, _ = I.donchian(f.h, f.l, exit)
    return latch(f.c > up, f.c < xdn, f.c < dn, f.c > xup)


@gen("supertrend", "trend", "ATR-band trend flip", {"n": 10, "m": 3.0}, {"n": [7, 10, 14], "m": [2.0, 3.0, 4.0]},
     ("supertrend",))
def supertrend(f, n=10, m=3.0):
    return _z(I.supertrend(f.h, f.l, f.c, n, m)[1])


@gen("adx_di", "trend", "Directional movement: trade +DI/-DI only when ADX shows a trend", {"n": 14, "adx": 25},
     {"n": [14, 21], "adx": [20, 25, 30]}, ("adx",), grade="D", source="Wilder (1978), trader hypothesis")
def adx_di(f, n=14, adx=25):
    a, p, m = I.adx(f.h, f.l, f.c, n)
    return state((a >= adx) & (p > m), (a >= adx) & (m > p))


@gen("ichimoku_cloud", "trend", "Price above the cloud with tenkan over kijun", {}, {}, ("ichimoku",))
def ichimoku_cloud(f):
    k = I.ichimoku(f.h, f.l)
    top, bot = np.fmax(k["senkou_a"], k["senkou_b"]), np.fmin(k["senkou_a"], k["senkou_b"])
    return state((f.c > top) & (k["tenkan"] > k["kijun"]), (f.c < bot) & (k["tenkan"] < k["kijun"]))


@gen("macd_trend", "trend", "MACD above its signal line", {"fast": 12, "slow": 26},
     {"fast": [8, 12], "slow": [21, 26, 35]}, ("macd",))
def macd_trend(f, fast=12, slow=26):
    line, sig, _ = I.macd(f.c, fast, slow)
    return state(line > sig, line < sig)


@gen("psar_trend", "trend", "Parabolic SAR direction", {"step": 0.02}, {"step": [0.01, 0.02, 0.03]}, ("psar",))
def psar_trend(f, step=0.02):
    return _z(I.psar(f.h, f.l, step)[1])


@gen("aroon_trend", "trend", "Recent highs more recent than recent lows", {"n": 25, "th": 70},
     {"n": [14, 25, 50], "th": [60, 70, 80]}, ("aroon",))
def aroon_trend(f, n=25, th=70):
    u, d = I.aroon(f.h, f.l, n)
    return state((u > th) & (d < 100 - th), (d > th) & (u < 100 - th))


@gen("tsmom", "trend", "Time-series momentum: past return sign predicts future return sign",
     {"n": 126}, {"n": [21, 63, 126, 252]}, ("tsmom",), grade="A",
     source="Moskowitz, Ooi & Pedersen (2012), Time series momentum, JFE (monthly, futures)",
     failure="sharp reversals; intraday use is untested by the paper")
def tsmom(f, n=126):
    r = I.ret(f.c, n)
    return state(r > 0, r < 0)


@gen("ma_slope", "trend", "Slope of a long average", {"n": 100, "k": 10}, {"n": [50, 100, 200], "k": [5, 10, 20]},
     ("sma",))
def ma_slope(f, n=100, k=10):
    s = I.sma(f.c, n)
    return state(s > I.shift(s, k), s < I.shift(s, k))


@gen("keltner_trend", "trend", "Close outside the Keltner channel starts a trend", {"n": 20, "m": 2.0},
     {"n": [20, 50], "m": [1.5, 2.0, 2.5]}, ("keltner",), exits=("flip", "atr_bracket", "trail"))
def keltner_trend(f, n=20, m=2.0):
    mid, up, dn = I.keltner(f.h, f.l, f.c, n, m)
    return latch(f.c > up, f.c < mid, f.c < dn, f.c > mid)


@gen("vortex_trend", "trend", "VI+ above VI-", {"n": 14}, {"n": [14, 21, 28]}, ("vortex",))
def vortex_trend(f, n=14):
    p, m = I.vortex(f.h, f.l, f.c, n)
    return state(p > m, m > p)


@gen("price_above_vwap", "vwap", "Holding above the session VWAP shows buyers in control of the session", {}, {},
     ("vwap_session",), markets=("crypto", "stock", "etf", "future"), timeframes=INTRA)
def price_above_vwap(f):
    v = I.vwap_session(f.h, f.l, f.c, f.v, f.session)
    return state(f.c > v, f.c < v)


@gen("mtf_trend", "trend", "Trade the lower-timeframe trend only in the higher-timeframe direction (4x and 16x bars)",
     {"n": 20}, {"n": [10, 20, 50]}, ("ema",))
def mtf_trend(f, n=20):
    fast, mid, slow = I.ema(f.c, n), I.ema(f.c, 4 * n), I.ema(f.c, 16 * n)
    return state((f.c > fast) & (fast > mid) & (mid > slow), (f.c < fast) & (fast < mid) & (mid < slow))


@gen("trend_pullback", "trend", "In an uptrend, buy a pullback to the fast average", {"fast": 20, "slow": 100},
     {"fast": [10, 20], "slow": [50, 100, 200]}, ("ema",), exits=("atr_bracket", "time", "trail"))
def trend_pullback(f, fast=20, slow=100):
    e1, e2 = I.ema(f.c, fast), I.ema(f.c, slow)
    up = (e1 > e2) & (f.l <= e1) & (f.c > e1)
    dn = (e1 < e2) & (f.h >= e1) & (f.c < e1)
    return latch(up, f.c < e2, dn, f.c > e2)


@gen("vol_scaled_trend", "volatility", "Trend signal only when volatility is not extreme (vol-managed momentum)",
     {"n": 63}, {"n": [21, 63, 126]}, ("tsmom", "rvol"), grade="A",
     source="Moreira & Muir (2017), Volatility-managed portfolios, JF (monthly factors)")
def vol_scaled_trend(f, n=63):
    r = I.ret(f.c, n)
    vr = I.percent_rank(I.realized_vol(f.c, 20, f.ppy), 250)
    calm = _z(vr) < 80
    return state((r > 0) & calm, (r < 0) & calm)


# ============================================================================ momentum

@gen("roc_threshold", "momentum", "Strong recent return continues", {"n": 10, "th": 2.0},
     {"n": [5, 10, 20], "th": [1.0, 2.0, 3.0]}, ("roc",))
def roc_threshold(f, n=10, th=2.0):
    r = I.roc(f.c, n)
    sd = I.rstd(I.roc(f.c, n), 100)
    return state(r > th * sd / 2, r < -th * sd / 2)


@gen("rsi_momentum", "momentum", "RSI above 55 marks momentum (not overbought)", {"n": 14, "hi": 55},
     {"n": [7, 14, 21], "hi": [55, 60, 65]}, ("rsi",))
def rsi_momentum(f, n=14, hi=55):
    r = I.rsi(f.c, n)
    return state(r > hi, r < 100 - hi)


@gen("macd_accel", "momentum", "Rising MACD histogram above zero: accelerating momentum", {}, {}, ("macd",))
def macd_accel(f):
    _, _, h = I.macd(f.c)
    return state((h > 0) & (h > I.shift(h, 1)), (h < 0) & (h < I.shift(h, 1)))


@gen("tsi_cross", "momentum", "TSI crosses its signal", {"long": 25, "short": 13},
     {"long": [25, 40], "short": [7, 13]}, ("tsi",))
def tsi_cross(f, long=25, short=13):
    t = I.tsi(f.c, long, short)
    s = I.ema(t, 7)
    return state(t > s, t < s)


@gen("kst_cross", "momentum", "KST above its signal line", {}, {}, ("kst",))
def kst_cross(f):
    k, s = I.kst(f.c)
    return state(k > s, k < s)


@gen("stoch_momentum", "momentum", "%K above %D in the upper half", {"n": 14}, {"n": [9, 14, 21]}, ("stoch",))
def stoch_momentum(f, n=14):
    k, d = I.stoch(f.h, f.l, f.c, n)
    return state((k > d) & (k > 50), (k < d) & (k < 50))


@gen("cmo_momentum", "momentum", "Chande momentum above a threshold", {"n": 14, "th": 20},
     {"n": [9, 14, 21], "th": [10, 20, 30]}, ("cmo",))
def cmo_momentum(f, n=14, th=20):
    c = I.cmo(f.c, n)
    return state(c > th, c < -th)


@gen("ao_zero", "momentum", "Awesome oscillator above zero", {}, {}, ("ao",))
def ao_zero(f):
    a = I.awesome_osc(f.h, f.l)
    return state(a > 0, a < 0)


@gen("volume_momentum", "momentum", "Momentum confirmed by above-average volume", {"n": 10, "rv": 1.5},
     {"n": [5, 10, 20], "rv": [1.2, 1.5, 2.0]}, ("roc", "relvol"), markets=("crypto", "stock", "etf", "future"))
def volume_momentum(f, n=10, rv=1.5):
    r = I.ret(f.c, n)
    v = I.rvol(f.v, 20)
    return latch((r > 0) & (v > rv), r < 0, (r < 0) & (v > rv), r > 0)


@gen("gap_continuation", "momentum", "A large opening gap in the trend direction continues during the session",
     {"g": 0.005}, {"g": [0.003, 0.005, 0.01]}, ("gap",), markets=SESSION_MARKETS, timeframes=INTRA,
     exits=("time", "atr_bracket"))
def gap_continuation(f, g=0.005):
    gp = I.gap(f.o, f.c, f.session)
    tr = I.ema(f.c, 50)
    return latch((gp > g) & (f.c > tr), f.session != I.shift(f.session, 1), (gp < -g) & (f.c < tr),
                 f.session != I.shift(f.session, 1))


@gen("fisher_turn", "momentum", "Fisher transform turns up from below zero", {"n": 10}, {"n": [9, 10, 20]},
     ("fisher",))
def fisher_turn(f, n=10):
    x = I.fisher(f.h, f.l, n)
    return latch(cross_up(x, I.shift(x, 1)) & (x < 0), x > 1.5, cross_dn(x, I.shift(x, 1)) & (x > 0), x < -1.5)


@gen("elder_impulse", "momentum", "EMA13 rising and MACD histogram rising", {}, {}, ("ema", "macd"))
def elder_impulse(f):
    e = I.ema(f.c, 13)
    _, _, h = I.macd(f.c)
    return state((e > I.shift(e, 1)) & (h > I.shift(h, 1)), (e < I.shift(e, 1)) & (h < I.shift(h, 1)))


@gen("coppock_turn", "momentum", "Coppock curve turning up below zero", {}, {}, ("coppock",),
     exits=("time", "atr_bracket", "trail"))
def coppock_turn(f):
    c = I.coppock(f.c)
    return latch((c < 0) & (c > I.shift(c, 1)) & (I.shift(c, 1) < I.shift(c, 2)), c < I.shift(c, 1))


# ============================================================================ mean reversion

@gen("rsi2_reversion", "mean_reversion", "Short-term oversold in an uptrend reverts", {"lo": 10, "exit": 70},
     {"lo": [5, 10, 15], "exit": [50, 70]}, ("rsi", "sma"), grade="C",
     source="Connors & Alvarez, Short Term Trading Strategies That Work (2008, book, C)",
     failure="crashes and strong downtrends", filters=("trend200", "none", "vol_band", "session"))
def rsi2_reversion(f, lo=10, exit=70):
    r = I.rsi(f.c, 2)
    return latch(r < lo, r > exit, r > 100 - lo, r < 100 - exit)


@gen("bollinger_reversion", "mean_reversion", "Closes outside 2-sigma bands snap back to the mean",
     {"n": 20, "k": 2.0}, {"n": [20, 50], "k": [1.5, 2.0, 2.5]}, ("bollinger",), failure="breakouts that keep going")
def bollinger_reversion(f, n=20, k=2.0):
    m, up, dn, _, _ = I.bollinger(f.c, n, k)
    return latch(f.c < dn, f.c > m, f.c > up, f.c < m)


@gen("zscore_reversion", "mean_reversion", "Price far from its mean in z-score terms reverts", {"n": 50, "z": 2.0},
     {"n": [20, 50, 100], "z": [1.5, 2.0, 2.5]}, ("zscore",))
def zscore_reversion(f, n=50, z=2.0):
    s = I.zscore(f.c, n)
    return latch(s < -z, s > 0, s > z, s < 0)


@gen("vwap_reversion", "vwap", "Stretched far from the session VWAP, price returns toward it", {"k": 2.0},
     {"k": [1.5, 2.0, 2.5]}, ("vwap_bands",), markets=("crypto", "stock", "etf", "future"), timeframes=INTRA)
def vwap_reversion(f, k=2.0):
    m, up, dn = I.vwap_bands(f.h, f.l, f.c, f.v, f.session, k)
    return latch(f.c < dn, f.c > m, f.c > up, f.c < m)


@gen("keltner_reversion", "mean_reversion", "Outside Keltner bands in a non-trending market reverts",
     {"n": 20, "m": 2.0}, {"n": [20, 50], "m": [1.5, 2.0, 2.5]}, ("keltner", "adx"))
def keltner_reversion(f, n=20, m=2.0):
    mid, up, dn = I.keltner(f.h, f.l, f.c, n, m)
    a = I.adx(f.h, f.l, f.c, 14)[0]
    calm = _z(a) < 25
    return latch((f.c < dn) & calm, f.c > mid, (f.c > up) & calm, f.c < mid)


@gen("percentile_reversion", "mean_reversion", "Close in the bottom percentile of its range reverts",
     {"n": 100, "p": 5}, {"n": [50, 100, 200], "p": [5, 10]}, ("price_pctrank",))
def percentile_reversion(f, n=100, p=5):
    r = I.percent_rank(f.c, n)
    return latch(r < p, r > 50, r > 100 - p, r < 50)


@gen("willr_reversion", "mean_reversion", "Williams %R extreme reverts", {"n": 10}, {"n": [5, 10, 14]}, ("willr",))
def willr_reversion(f, n=10):
    w = I.williams_r(f.h, f.l, f.c, n)
    return latch(w < -90, w > -50, w > -10, w < -50)


@gen("cci_reversion", "mean_reversion", "CCI beyond +/-200 reverts", {"n": 20, "th": 200},
     {"n": [14, 20], "th": [150, 200]}, ("cci",))
def cci_reversion(f, n=20, th=200):
    c = I.cci(f.h, f.l, f.c, n)
    return latch(c < -th, c > 0, c > th, c < 0)


@gen("stoch_reversion", "mean_reversion", "Stochastic below 20 turning up", {"n": 14}, {"n": [9, 14]}, ("stoch",))
def stoch_reversion(f, n=14):
    k, d = I.stoch(f.h, f.l, f.c, n)
    return latch((k < 20) & cross_up(k, d), k > 80, (k > 80) & cross_dn(k, d), k < 20)


@gen("extreme_fade", "mean_reversion", "A bar move beyond 3 standard deviations partly reverses next",
     {"z": 3.0}, {"z": [2.5, 3.0, 4.0]}, ("ret",), exits=("time", "atr_bracket"),
     failure="news shocks that start new trends")
def extreme_fade(f, z=3.0):
    r = I.ret(f.c, 1)
    s = I.shift(I.rstd(r, 100), 1)
    return latch(r < -z * s, f.c > I.shift(f.c, 1), r > z * s, f.c < I.shift(f.c, 1))


@gen("connors_rsi_rev", "mean_reversion", "Composite Connors RSI below 10 reverts", {"lo": 10}, {"lo": [5, 10, 15]},
     ("connors_rsi",), grade="C", source="Connors Research (industry, C)")
def connors_rsi_rev(f, lo=10):
    c = I.connors_rsi(f.c)
    return latch(c < lo, c > 70, c > 100 - lo, c < 30)


@gen("ibs_reversion", "mean_reversion", "A close near the bar's low (low IBS) tends to bounce next bar",
     {"lo": 0.2}, {"lo": [0.1, 0.2, 0.3]}, ("ibs",), grade="B",
     source="internal bar strength studies (e.g. Pagonidis 2013, working paper, B)", exits=("time", "flip"))
def ibs_reversion(f, lo=0.2):
    x = I.ibs(f.h, f.l, f.c)
    return latch(x < lo, x > 0.8, x > 1 - lo, x < 0.2)


@gen("gap_fade", "mean_reversion", "Small overnight gaps against the trend tend to fill", {"g": 0.004},
     {"g": [0.002, 0.004, 0.008]}, ("gap",), markets=SESSION_MARKETS, timeframes=INTRA, exits=("time", "atr_bracket"))
def gap_fade(f, g=0.004):
    gp = I.gap(f.o, f.c, f.session)
    _, _, pc = I.prior_session_levels(f.h, f.l, f.c, f.session)
    return latch((gp < -g) & (gp > -3 * g), f.c >= pc, (gp > g) & (gp < 3 * g), f.c <= pc)


@gen("vol_adjusted_reversion", "mean_reversion", "Return in ATR units below -2 reverts", {"n": 5, "k": 2.0},
     {"n": [3, 5, 10], "k": [1.5, 2.0, 3.0]}, ("atr",))
def vol_adjusted_reversion(f, n=5, k=2.0):
    move = I.safe_div(f.c - I.shift(f.c, n), I.atr(f.h, f.l, f.c, 14))
    return latch(move < -k, move > 0, move > k, move < 0)


@gen("mfi_reversion", "mean_reversion", "Money flow index extreme with volume reverts", {"n": 14},
     {"n": [10, 14]}, ("mfi",), markets=("crypto", "stock", "etf", "future"))
def mfi_reversion(f, n=14):
    m = I.mfi(f.h, f.l, f.c, f.v, n)
    return latch(m < 15, m > 50, m > 85, m < 50)


# ============================================================================ breakout

@gen("donchian_breakout", "breakout", "Range breakouts start moves", {"n": 20}, {"n": [10, 20, 55]}, ("donchian",),
     exits=("atr_bracket", "time", "trail"), failure="false breakouts")
def donchian_breakout(f, n=20):
    up, dn, _ = I.donchian(f.h, f.l, n)
    return latch(f.c > up, f.c < I.donchian(f.h, f.l, n // 2)[1], f.c < dn, f.c > I.donchian(f.h, f.l, n // 2)[0])


@gen("prior_session_breakout", "breakout", "Breaking the prior session's high or low attracts follow-through",
     {}, {}, ("prior_session",), exits=("atr_bracket", "time"), timeframes=INTRA)
def prior_session_breakout(f):
    ph, pl, _ = I.prior_session_levels(f.h, f.l, f.c, f.session)
    new = f.session != I.shift(f.session, 1)
    return latch(cross_up(f.c, ph), new, cross_dn(f.c, pl), new)


def _confirmed_swings(h: A, lo: A, k: int) -> tuple[A, A]:
    """Last confirmed swing high/low as known at each bar: a pivot k bars back that is the extreme of the 2k+1
    bars around it is only known k bars later, so nothing here repaints."""
    n = len(h)
    sh, sl = np.full(n, np.nan), np.full(n, np.nan)
    last_h = last_l = np.nan
    for i in range(2 * k, n):
        j = i - k
        if h[j] == np.max(h[j - k:i + 1]):
            last_h = h[j]
        if lo[j] == np.min(lo[j - k:i + 1]):
            last_l = lo[j]
        sh[i], sl[i] = last_h, last_l
    return sh, sl


@gen("structure_break", "trend", "A close beyond the last CONFIRMED swing (k bars each side, known only k bars later) "
     "starts a move; the opposite confirmed swing invalidates it", {"k": 3}, {"k": [2, 3, 5]}, ("donchian",),
     source="owner catalog ST031 (H): confirmed market-structure break, non-repainting definition",
     failure="ranges with frequent small breaks; gaps through the invalidation level",
     exits=("flip", "atr_bracket", "time", "trail"))
def structure_break(f, k=3):
    sh, sl = _confirmed_swings(f.h, f.l, k)
    psh, psl = I.shift(sh, 1), I.shift(sl, 1)
    return latch(cross_up(f.c, psh), f.c < psl, cross_dn(f.c, psl), f.c > psh)


def _hold(long_: A, short: A, bars: int) -> A:
    """A trigger opens a position for `bars` bars (an opposite trigger replaces it). Causal."""
    out = np.zeros(len(long_))
    pos, left = 0.0, 0
    for i in range(len(long_)):
        if long_[i]:
            pos, left = 1.0, bars
        elif short[i]:
            pos, left = -1.0, bars
        elif left > 0:
            left -= 1
        if left == 0:
            pos = 0.0
        out[i] = pos
    return out


@gen("sweep_reclaim", "mean_reversion", "Price briefly trades through a known level (prior n-bar low/high) by at least "
     "x ATR and closes back inside it in the same bar: the excursion failed", {"n": 20, "x": 0.1, "hold": 10},
     {"n": [20, 50], "x": [0.0, 0.1, 0.25], "hold": [10]}, ("donchian", "atr"),
     source="owner catalog ST032 (H): liquidity-sweep-and-reclaim; inferred stop clusters are a hypothesis only",
     failure="genuine breakdowns that retest and continue", exits=("atr_bracket", "time", "trail"))
def sweep_reclaim(f, n=20, x=0.1, hold=10):
    lo_lvl, hi_lvl = I.shift(I.rmin(f.l, n), 1), I.shift(I.rmax(f.h, n), 1)
    a = I.shift(I.atr(f.h, f.l, f.c, 14), 1)
    long_ = np.nan_to_num((f.l < lo_lvl - x * a) & (f.c > lo_lvl)).astype(bool)
    short = np.nan_to_num((f.h > hi_lvl + x * a) & (f.c < hi_lvl)).astype(bool)
    return _hold(long_, short, int(hold))


@gen("failed_breakout", "mean_reversion", "A break of a known n-bar range that closes back inside within m bars is a "
     "failed breakout: trade back toward the range middle, invalidated beyond the excursion", {"n": 20, "m": 3},
     {"n": [20, 50], "m": [1, 3, 5]}, ("donchian",),
     source="owner catalog ST026 (H): failed-breakout reversal, confirmation on a completed bar",
     failure="trend continuation after a retest", exits=("flip", "atr_bracket", "time"))
def failed_breakout(f, n=20, m=3):
    up, dn = I.shift(I.rmax(f.h, n), m + 1), I.shift(I.rmin(f.l, n), m + 1)       # range known before the excursion
    mid = (up + dn) / 2
    broke_up = I.rmax(f.h, m) > up
    broke_dn = I.rmin(f.l, m) < dn
    exc_hi, exc_lo = I.rmax(f.h, m), I.rmin(f.l, m)
    short = broke_up & (f.c < up) & (I.shift(f.c, 1) >= I.shift(up, 1))
    long_ = broke_dn & (f.c > dn) & (I.shift(f.c, 1) <= I.shift(dn, 1))
    return latch(long_, (f.c >= mid) | (f.c < exc_lo), short, (f.c <= mid) | (f.c > exc_hi))


@gen("vol_breakout", "breakout", "A move beyond k ATR from the session open is a breakout", {"k": 0.6},
     {"k": [0.4, 0.6, 1.0]}, ("atr",), grade="C", source="volatility breakout (Larry Williams, industry, C)",
     exits=("time", "atr_bracket"))
def vol_breakout(f, k=0.6):
    sess_open = np.zeros(len(f.c))
    cur = f.o[0]
    for i in range(len(f.c)):
        if i == 0 or f.session[i] != f.session[i - 1]:
            cur = f.o[i]
        sess_open[i] = cur
    a = I.shift(I.atr(f.h, f.l, f.c, 14), 1)
    new = f.session != I.shift(f.session, 1)
    return latch(f.c > sess_open + k * a, new, f.c < sess_open - k * a, new)


@gen("nr7_breakout", "breakout", "After the narrowest range of 7 bars, the next break starts a move", {"n": 7},
     {"n": [4, 7]}, ("nr7",), exits=("time", "atr_bracket"), grade="C", source="Crabel (1990), book, C")
def nr7_breakout(f, n=7):
    nr = I.narrow_range(f.h, f.l, n)
    ph, pl = I.shift(f.h, 1), I.shift(f.l, 1)
    setup = I.shift(nr, 1) > 0
    return latch(setup & (f.c > ph), f.c < pl, setup & (f.c < pl), f.c > ph)


@gen("inside_bar_breakout", "breakout", "Break of an inside bar's mother bar", {}, {}, ("inside_bar",),
     exits=("time", "atr_bracket"))
def inside_bar_breakout(f):
    ib = I.shift(I.inside_bar(f.h, f.l), 1) > 0
    mh, ml = I.shift(f.h, 2), I.shift(f.l, 2)
    return latch(ib & (f.c > mh), f.c < ml, ib & (f.c < ml), f.c > mh)


@gen("squeeze_breakout", "breakout", "Bollinger bandwidth at a 120-bar low, then a band break", {"p": 10},
     {"p": [5, 10, 20]}, ("bb_width_pctrank",), exits=("atr_bracket", "trail", "time"))
def squeeze_breakout(f, p=10):
    m, up, dn, _, bw = I.bollinger(f.c, 20, 2.0)
    sq = I.shift(I.percent_rank(bw, 120), 1) < p
    return latch(sq & (f.c > up), f.c < m, sq & (f.c < dn), f.c > m)


@gen("atr_channel_breakout", "breakout", "Close beyond SMA +/- k ATR", {"n": 50, "k": 2.0},
     {"n": [20, 50, 100], "k": [1.5, 2.0, 3.0]}, ("atr", "sma"), exits=("flip", "trail", "atr_bracket"))
def atr_channel_breakout(f, n=50, k=2.0):
    s, a = I.sma(f.c, n), I.atr(f.h, f.l, f.c, 14)
    return latch(f.c > s + k * a, f.c < s, f.c < s - k * a, f.c > s)


@gen("orb", "breakout", "Opening-range breakout: the first minutes' range break sets the session direction",
     {"bars": 3}, {"bars": [1, 3, 6]}, ("opening_range",), markets=("stock", "etf", "future", "fx"),
     timeframes=("5m", "15m"), grade="C", source="Crabel (1990); Zarattini & Aziz (2023, working paper, B) on ORB",
     exits=("time", "atr_bracket"), failure="range days; high costs at short timeframes")
def orb(f, bars=3):
    oh, ol, done = I.opening_range(f.h, f.l, f.session, bars)
    new = f.session != I.shift(f.session, 1)
    return latch((done > 0) & (f.c > oh), new, (done > 0) & (f.c < ol), new)


@gen("consolidation_breakout", "breakout", "A tight range (low ATR rank) broken with volume", {"n": 30},
     {"n": [20, 30, 50]}, ("atr_pctrank", "donchian"), exits=("atr_bracket", "trail"))
def consolidation_breakout(f, n=30):
    tight = I.shift(I.percent_rank(I.atr(f.h, f.l, f.c, 14), 250), 1) < 25
    up, dn, _ = I.donchian(f.h, f.l, n)
    return latch(tight & (f.c > up), f.c < I.donchian(f.h, f.l, n // 2)[1], tight & (f.c < dn),
                 f.c > I.donchian(f.h, f.l, n // 2)[0])


@gen("volume_breakout", "breakout", "A 20-bar high on twice the normal volume", {"rv": 2.0}, {"rv": [1.5, 2.0, 3.0]},
     ("donchian", "relvol"), markets=("crypto", "stock", "etf", "future"), exits=("atr_bracket", "time", "trail"))
def volume_breakout(f, rv=2.0):
    up, dn, _ = I.donchian(f.h, f.l, 20)
    v = I.rvol(f.v, 20)
    return latch((f.c > up) & (v > rv), f.c < I.ema(f.c, 20), (f.c < dn) & (v > rv), f.c > I.ema(f.c, 20))


@gen("initial_balance_breakout", "breakout", "Break of the first hour's range (initial balance)", {}, {},
     ("opening_range",), markets=("stock", "etf", "future"), timeframes=("5m", "15m"), exits=("time", "atr_bracket"))
def initial_balance_breakout(f):
    bars = max(1, int(3_600_000 // f.b.step))
    oh, ol, done = I.opening_range(f.h, f.l, f.session, bars)
    new = f.session != I.shift(f.session, 1)
    return latch((done > 0) & (f.c > oh), new, (done > 0) & (f.c < ol), new)


@gen("overnight_range_breakout", "breakout", "Futures: break of the overnight (Globex) range after the cash open",
     {}, {}, ("minutes_ny",), markets=("future",), timeframes=("5m", "15m"), exits=("time", "atr_bracket"))
def overnight_range_breakout(f):
    from tradingai.features.registry import REGISTRY
    mins = REGISTRY["minutes_ny"].fn(f)
    out_h, out_l = np.full(len(f.c), np.nan), np.full(len(f.c), np.nan)
    hi = lo = np.nan
    for i in range(len(f.c)):
        if i == 0 or f.session[i] != f.session[i - 1]:
            hi, lo = -np.inf, np.inf
        if mins[i] < 570:                       # before 09:30 New York: overnight
            hi, lo = max(hi, f.h[i]), min(lo, f.l[i])
        else:
            out_h[i], out_l[i] = hi, lo
    new = f.session != I.shift(f.session, 1)
    return latch(f.c > out_h, new, f.c < out_l, new)


# ============================================================================ VWAP

@gen("vwap_reclaim", "vwap", "A close back above the session VWAP after trading below it", {}, {}, ("vwap_session",),
     markets=("crypto", "stock", "etf", "future"), timeframes=INTRA, exits=("atr_bracket", "time"))
def vwap_reclaim(f):
    v = I.vwap_session(f.h, f.l, f.c, f.v, f.session)
    return latch(cross_up(f.c, v), cross_dn(f.c, v), cross_dn(f.c, v), cross_up(f.c, v))


@gen("vwap_rejection", "vwap", "A test of VWAP from below that fails, in a downtrend", {}, {}, ("vwap_session",),
     markets=("crypto", "stock", "etf", "future"), timeframes=INTRA, exits=("atr_bracket", "time"))
def vwap_rejection(f):
    v = I.vwap_session(f.h, f.l, f.c, f.v, f.session)
    e = I.ema(f.c, 50)
    short = (f.h >= v) & (f.c < v) & (f.c < e)
    long_ = (f.l <= v) & (f.c > v) & (f.c > e)
    return latch(long_, f.c < v, short, f.c > v)


@gen("vwap_band_breakout", "vwap", "A close beyond the 2-sigma VWAP band in a trending session", {"k": 2.0},
     {"k": [1.5, 2.0]}, ("vwap_bands", "adx"), markets=("crypto", "stock", "etf", "future"), timeframes=INTRA,
     exits=("atr_bracket", "time", "trail"))
def vwap_band_breakout(f, k=2.0):
    m, up, dn = I.vwap_bands(f.h, f.l, f.c, f.v, f.session, k)
    a = I.adx(f.h, f.l, f.c, 14)[0]
    return latch((f.c > up) & (a > 20), f.c < m, (f.c < dn) & (a > 20), f.c > m)


@gen("vwap_rvol", "vwap", "Above VWAP with heavy relative volume", {"rv": 1.5}, {"rv": [1.2, 1.5, 2.0]},
     ("vwap_session", "relvol"), markets=("crypto", "stock", "etf", "future"), timeframes=INTRA)
def vwap_rvol(f, rv=1.5):
    v = I.vwap_session(f.h, f.l, f.c, f.v, f.session)
    r = I.rvol(f.v, 20)
    return latch((f.c > v) & (r > rv), f.c < v, (f.c < v) & (r > rv), f.c > v)


@gen("anchored_vwap_trend", "vwap", "Above the VWAP anchored at the last 100-bar low", {"n": 100}, {"n": [50, 100]},
     ("anchored_vwap",), markets=("crypto", "stock", "etf", "future"))
def anchored_vwap_trend(f, n=100):
    out = np.zeros(len(f.c))
    tp = (f.h + f.l + f.c) / 3
    for i in range(n, len(f.c)):
        a = i - n + int(np.argmin(f.l[i - n:i + 1]))
        vv = f.v[a:i + 1].sum()
        av = (tp[a:i + 1] * f.v[a:i + 1]).sum() / vv if vv > 0 else np.nan
        out[i] = 1.0 if f.c[i] > av else 0.0
    return out


# ============================================================================ volatility regime

@gen("vol_compression", "volatility", "Low volatility clusters end in expansion: ride the first expansion bar",
     {"p": 15}, {"p": [10, 15, 25]}, ("vol_pctrank",), exits=("atr_bracket", "time"))
def vol_compression(f, p=15):
    vr = I.shift(I.percent_rank(I.realized_vol(f.c, 20, f.ppy), 250), 1)
    big = np.abs(I.ret(f.c, 1)) > 1.5 * I.shift(I.rstd(I.ret(f.c, 1), 50), 1)
    up = I.ret(f.c, 1) > 0
    return latch((vr < p) & big & up, I.ret(f.c, 5) < 0, (vr < p) & big & ~up, I.ret(f.c, 5) > 0)


@gen("vol_regime_switch", "volatility", "Trend-follow in high volatility, mean-revert in low volatility", {}, {},
     ("vol_pctrank", "rsi", "ema"))
def vol_regime_switch(f):
    vr = _z(I.percent_rank(I.realized_vol(f.c, 20, f.ppy), 250))
    trend = state(I.ema(f.c, 20) > I.ema(f.c, 100), I.ema(f.c, 20) < I.ema(f.c, 100))
    rev = latch(I.rsi(f.c, 2) < 10, I.rsi(f.c, 2) > 60, I.rsi(f.c, 2) > 90, I.rsi(f.c, 2) < 40)
    return np.where(vr > 60, trend, rev)


@gen("atr_expansion", "volatility", "A range expansion bar (TR > 2 ATR) closing near its high", {"k": 2.0},
     {"k": [1.5, 2.0, 2.5]}, ("atr", "ibs"), exits=("time", "atr_bracket", "trail"))
def atr_expansion(f, k=2.0):
    tr = I.true_range(f.h, f.l, f.c)
    a = I.shift(I.atr(f.h, f.l, f.c, 14), 1)
    x = I.ibs(f.h, f.l, f.c)
    return latch((tr > k * a) & (x > 0.8), I.ret(f.c, 1) < -0.5 * I.safe_div(a, f.c), (tr > k * a) & (x < 0.2),
                 I.ret(f.c, 1) > 0.5 * I.safe_div(a, f.c))


@gen("vol_target_hold", "volatility", "Hold long only while volatility is below its long-run median",
     {"p": 50}, {"p": [40, 50, 70]}, ("vol_pctrank",), grade="A",
     source="Moreira & Muir (2017), JF; Harvey et al. (2018) on volatility targeting (B)", exits=("flip",))
def vol_target_hold(f, p=50):
    vr = I.percent_rank(I.realized_vol(f.c, 20, f.ppy), 250)
    return state(vr < p)


# ============================================================================ statistical / regime-character

@gen("hurst_switch", "statistical", "Trend when Hurst > 0.55, revert when < 0.45", {}, {}, ("hurst",),
     filters=("none", "vol_band"))
def hurst_switch(f):
    hh = I.hurst(f.c, 100)
    tr = state(I.ema(f.c, 10) > I.ema(f.c, 40), I.ema(f.c, 10) < I.ema(f.c, 40))
    rv = latch(I.zscore(f.c, 20) < -1.5, I.zscore(f.c, 20) > 0, I.zscore(f.c, 20) > 1.5, I.zscore(f.c, 20) < 0)
    return np.where(_z(hh) > 0.55, tr, np.where((hh < 0.45) & np.isfinite(hh), rv, 0.0))


@gen("variance_ratio_switch", "statistical", "Lo-MacKinlay variance ratio picks trend or reversion", {}, {},
     ("variance_ratio",), grade="A", source="Lo & MacKinlay (1988), RFS (the test; trading rule is a hypothesis)",
     filters=("none", "vol_band"))
def variance_ratio_switch(f):
    vr = I.variance_ratio(f.c, 100, 4)
    tr = state(I.ret(f.c, 20) > 0, I.ret(f.c, 20) < 0)
    rv = latch(I.zscore(f.c, 20) < -1.5, I.zscore(f.c, 20) > 0, I.zscore(f.c, 20) > 1.5, I.zscore(f.c, 20) < 0)
    return np.where(_z(vr) > 1.1, tr, np.where((vr < 0.9) & np.isfinite(vr), rv, 0.0))


@gen("autocorr_follow", "statistical", "Positive return autocorrelation: follow the last move", {"n": 60},
     {"n": [30, 60, 120]}, ("autocorr",), exits=("time", "flip"))
def autocorr_follow(f, n=60):
    ac = I.autocorr(I.logret(f.c), n, 1)
    r = I.ret(f.c, 1)
    return np.where(_z(ac) > 0.1, np.sign(_z(r)), np.where(_z(ac) < -0.1, -np.sign(_z(r)), 0.0))


@gen("skew_reversal", "statistical", "Strongly negative skew after selling: rebound", {"th": -1.0},
     {"th": [-0.5, -1.0, -1.5]}, ("skew",), exits=("time", "atr_bracket"))
def skew_reversal(f, th=-1.0):
    s = I.rskew(I.logret(f.c), 60)
    return latch((s < th) & (I.ret(f.c, 10) < 0), s > 0)


# ============================================================================ session and seasonality

@gen("turn_of_month", "seasonality", "Equity inflows around month-end lift prices", {}, {}, ("turn_of_month",),
     markets=("stock", "etf", "future"), timeframes=("1h", "1d"), grade="A",
     source="Ariel (1987), JFE; Lakonishok & Smidt (1988), RFS", exits=("flip",), filters=("none", "trend200"))
def turn_of_month(f):
    from tradingai.features.registry import REGISTRY
    return REGISTRY["turn_of_month"].fn(f)


@gen("overnight_drift", "seasonality", "Equity returns concentrate overnight: hold from the last bar to the open",
     {}, {}, ("bar_in_session",), markets=("stock", "etf"), timeframes=("5m", "15m", "30m", "1h"), grade="B",
     source="Kelly & Clark (2011); Lou, Polk & Skouras (2019), JFE (overnight vs intraday returns)",
     exits=("flip",), filters=("none", "trend200"))
def overnight_drift(f):
    last = np.r_[f.session[1:] != f.session[:-1], False]
    first = np.r_[True, f.session[1:] != f.session[:-1]]
    return latch(last, first)


@gen("first_hour_momentum", "seasonality", "The first half-hour's direction predicts the last half-hour",
     {}, {}, ("bar_in_session",), markets=("stock", "etf", "future"), timeframes=("5m", "15m", "30m"), grade="A",
     source="Gao, Han, Li & Zhou (2018), Market intraday momentum, JFE", exits=("time", "flip"))
def first_hour_momentum(f):
    bars = max(1, int(1_800_000 // f.b.step))
    n = len(f.c)
    starts = np.flatnonzero(np.r_[True, f.session[1:] != f.session[:-1]])
    ends = np.r_[starts[1:] - 1, n - 1]
    out = np.zeros(n)
    for s, e in zip(starts, ends):
        if e - s + 1 < 3 * bars:
            continue
        first = f.c[s + bars - 1] / f.o[s] - 1
        # hold over the last half hour only: from the bar that closes `bars` before the session's last bar
        a = max(s + bars, e - bars)
        out[a:e] = np.sign(first)
    return out


@gen("day_of_week", "seasonality", "Weekday effects (weak evidence; included as a control)", {"dow": 0},
     {"dow": [0, 4]}, ("dow_utc",), timeframes=("1d",), grade="B",
     source="French (1980); the effect largely disappeared after publication", exits=("time",),
     filters=("none",))
def day_of_week(f, dow=0):
    d = (((f.b.ts // 86_400_000) + 3) % 7)
    return state(d == dow)


@gen("crypto_weekend", "seasonality", "Crypto weekends trade thinner: fade weekend moves on Monday",
     {}, {}, ("weekend",), markets=("crypto",), timeframes=("1h", "4h"), exits=("time",), filters=("none",))
def crypto_weekend(f):
    d = (((f.b.ts // 86_400_000) + 3) % 7)
    wk = I.ret(f.c, max(1, int(2 * 86_400_000 // f.b.step)))
    monday = d == 0
    return np.where(monday, -np.sign(_z(wk)), 0.0)


# ============================================================================ forex sessions

@gen("asian_range_breakout", "forex", "London breaks the Asian session range", {}, {}, ("fx_session_tokyo",),
     markets=("fx",), timeframes=("5m", "15m", "30m", "1h"), exits=("time", "atr_bracket"), filters=("none", "adx"))
def asian_range_breakout(f):
    from tradingai.market.calendars import fx_sessions
    tk = np.array(["tokyo" in fx_sessions(int(t)) for t in f.b.ts])
    ld = np.array(["london" in fx_sessions(int(t)) for t in f.b.ts])
    hi = lo = np.nan
    rh, rl = np.full(len(f.c), np.nan), np.full(len(f.c), np.nan)
    for i in range(len(f.c)):
        if i > 0 and f.session[i] != f.session[i - 1]:
            hi, lo = -np.inf, np.inf
        if tk[i] and not ld[i]:
            hi, lo = (f.h[i] if not np.isfinite(hi) else max(hi, f.h[i])), (f.l[i] if not np.isfinite(lo) else min(lo, f.l[i]))
        elif ld[i]:
            rh[i], rl[i] = hi, lo
    new = f.session != I.shift(f.session, 1)
    return latch(ld & (f.c > rh), new, ld & (f.c < rl), new)


@gen("london_open_momentum", "forex", "The first London hour sets the day's direction", {}, {}, ("fx_session_london",),
     markets=("fx",), timeframes=("15m", "30m", "1h"), exits=("time",), filters=("none", "adx"))
def london_open_momentum(f):
    from tradingai.market.calendars import fx_sessions
    ld = np.array(["london" in fx_sessions(int(t)) for t in f.b.ts])
    start = ld & ~np.r_[False, ld[:-1]]
    out = np.zeros(len(f.c))
    pos, ref = 0.0, np.nan
    for i in range(len(f.c)):
        if start[i]:
            ref, pos = f.o[i], 0.0
        elif ld[i] and pos == 0 and np.isfinite(ref):
            pos = np.sign(f.c[i] - ref)
        if not ld[i]:
            pos = 0.0
        out[i] = pos
    return out


@gen("ny_overlap_continuation", "forex", "London/New York overlap continues the London trend", {}, {},
     ("fx_session_london", "fx_session_new_york"), markets=("fx",), timeframes=("15m", "30m", "1h"),
     exits=("time",), filters=("none",))
def ny_overlap_continuation(f):
    from tradingai.market.calendars import fx_sessions
    s = [fx_sessions(int(t)) for t in f.b.ts]
    overlap = np.array([("london" in x and "new_york" in x) for x in s])
    trend = np.sign(_z(I.ret(f.c, max(1, int(14_400_000 // f.b.step)))))
    return np.where(overlap, trend, 0.0)


# ============================================================================ cross-market (pairs: two instruments)

@gen("pairs_zscore", "stat_arb", "Two cointegrated prices: trade the spread back to its mean",
     {"n": 100, "z": 2.0}, {"n": [60, 100, 200], "z": [1.5, 2.0, 2.5]}, (), grade="A",
     source="Gatev, Goetzmann & Rouwenhorst (2006), Pairs trading, RFS; Engle & Granger (1987)",
     failure="relationship breaks (structural change)", pairs=True, filters=("none",), exits=("flip", "time"))
def pairs_zscore(f, other_close: A | None = None, n=100, z=2.0):
    if other_close is None:
        return np.zeros(len(f.c))
    y, x = np.log(f.c), np.log(other_close)
    beta = I.rolling_beta(I.logret(f.c), I.logret(other_close), n)
    spread = y - _z(I.shift(beta, 1)) * x
    s = I.zscore(spread, n)
    return latch(s < -z, s > 0, s > z, s < 0)


@gen("ratio_momentum", "stat_arb", "Relative strength: hold the leg whose ratio to the other is trending up",
     {"n": 50}, {"n": [20, 50, 100]}, (), pairs=True, filters=("none",), exits=("flip",))
def ratio_momentum(f, other_close: A | None = None, n=50):
    if other_close is None:
        return np.zeros(len(f.c))
    r = f.c / other_close
    return state(r > I.ema(r, n), r < I.ema(r, n))


@gen("lead_lag", "cross_market", "The leader's (e.g. BTC) last return predicts the follower's next", {"k": 1},
     {"k": [1, 2, 3]}, (), pairs=True, filters=("none", "vol_band"), exits=("time",))
def lead_lag(f, other_close: A | None = None, k=1):
    if other_close is None:
        return np.zeros(len(f.c))
    lr = I.ret(other_close, k)
    sd = I.rstd(I.ret(other_close, 1), 100)
    return state(lr > sd, lr < -sd)


@gen("cross_venue_spread", "stat_arb", "Two venues quoting the same coin: fade a wide premium", {"z": 2.5},
     {"z": [2.0, 2.5, 3.0]}, (), markets=("crypto",), timeframes=("1m", "5m", "15m"), pairs=True, filters=("none",),
     exits=("flip", "time"), failure="withdrawal limits and fees make the spread untradable")
def cross_venue_spread(f, other_close: A | None = None, z=2.5):
    if other_close is None:
        return np.zeros(len(f.c))
    s = I.zscore(np.log(f.c / other_close), 200)
    return latch(s < -z, s > 0, s > z, s < 0)


# ============================================================================ needs data this install does not have

for key, fam, hyp, req, mk in (
        ("funding_reversion", "crypto", "Extreme perpetual funding reverses", ("funding",), ("crypto",)),
        ("funding_momentum", "crypto", "Rising funding confirms trend", ("funding",), ("crypto",)),
        ("basis_convergence", "crypto", "Spot-perpetual basis converges", ("mark_price", "index_price"), ("crypto",)),
        ("oi_breakout", "crypto", "Breakout with rising open interest", ("open_interest",), ("crypto", "future")),
        ("oi_price_divergence", "crypto", "Price up, open interest down: weak rally", ("open_interest",), ("crypto",)),
        ("liquidation_reversal", "crypto", "Liquidation cascades reverse", ("liquidations",), ("crypto",)),
        ("orderbook_imbalance", "microstructure", "Book imbalance predicts the next tick", ("order_book",), ALL),
        ("cumulative_delta_divergence", "microstructure", "Price/delta divergence", ("trades",), ALL),
        ("absorption", "microstructure", "Heavy volume without price progress", ("trades", "order_book"), ALL),
        ("news_breakout", "event", "Trade the break after a scheduled release", ("economic_calendar",), ALL),
        ("earnings_drift", "event", "Post-earnings announcement drift", ("earnings",), ("stock",)),
        ("carry_filter", "forex", "Hold the higher-yielding currency", ("rates",), ("fx",)),
        ("calendar_spread", "futures", "Front/next contract spread mean reversion", ("contract_data",), ("future",)),
        ("cash_futures_basis", "futures", "Index cash vs futures basis", ("contract_data",), ("future",)),
        ("breadth_thrust", "breadth", "Breadth thrust starts rallies", ("breadth",), ("etf", "stock"))):
    GEN[key] = Generator(key, fam, lambda f, **k: np.zeros(len(f.c)), hyp, {}, {}, (), mk, ANY_TF, "D",
                         "needs data this installation does not have", "", req)


def evaluate(key: str, f: FeatureFrame, params: dict | None = None, other_close: A | None = None) -> A:
    g = GEN[key]
    p = dict(g.params, **(params or {}))
    if g.pairs:
        out = g.fn(f, other_close=other_close, **p)
    else:
        out = g.fn(f, **p)
    out = np.nan_to_num(np.asarray(out, dtype=np.float64), nan=0.0)
    return np.clip(np.round(out), -1, 1)
