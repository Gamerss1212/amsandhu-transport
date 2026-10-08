"""Feature registry (sections 155-156): every feature with its metadata, computed lazily and cached per series.

A feature value at bar i is AVAILABLE_AT the close of bar i (`Bars.available_at[i]`); nothing may use it earlier.
Features that need data this installation does not have (funding rates, open interest, order books, breadth,
economic releases) are registered with `requires` and report UNAVAILABLE: they are never approximated from candles.

    ff = FeatureFrame(bars, calendar="CRYPTO")
    ff["rsi_14"]            -> numpy array, NaN during warm-up
    ff.available()          -> names computable on these bars
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

import numpy as np

from tradingai.data.bars import Bars
from tradingai.features import indicators as I

ALL_MARKETS = ("crypto", "stock", "etf", "fx", "future", "index")


@dataclass(frozen=True)
class FeatureSpec:
    name: str
    category: str
    formula: str
    inputs: tuple[str, ...]
    warmup: int
    fn: Optional[Callable[["FeatureFrame"], np.ndarray]]
    markets: tuple[str, ...] = ALL_MARKETS
    normalization: str = "raw"
    missing: str = "NaN during warm-up; NaN propagates"
    requires: tuple[str, ...] = ()            # extra data beyond OHLCV; empty = OHLCV is enough
    future_risk: str = "none: uses bars up to and including the current closed bar"
    function: str = ""

    def meta(self) -> dict:
        return {k: getattr(self, k) for k in ("name", "category", "formula", "inputs", "warmup", "markets",
                                              "normalization", "missing", "requires", "future_risk", "function")}


REGISTRY: dict[str, FeatureSpec] = {}


def reg(name, category, formula, warmup, fn, *, inputs=("close",), markets=ALL_MARKETS, norm="raw", requires=(),
        function=""):
    REGISTRY[name] = FeatureSpec(name, category, formula, tuple(inputs), int(warmup), fn, tuple(markets), norm,
                                 requires=tuple(requires), function=function or name.split("_")[0])


# ----------------------------------------------------------------------------- sessions

def session_ids(ts: np.ndarray, calendar: str) -> np.ndarray:
    """A number per bar that changes when a new trading session starts (UTC day for crypto, New York date for US
    stocks, 17:00 New York for FX, 18:00 New York for CME futures)."""
    if calendar == "CRYPTO" or not len(ts):
        return ts // 86_400_000
    from zoneinfo import ZoneInfo
    ny = ZoneInfo("America/New_York")
    shift_h = {"XNYS": 0, "FX": 7, "CME": 6}.get(calendar, 0)
    days = ts // 86_400_000
    out = np.empty(len(ts), dtype=np.int64)
    for d in np.unique(days):
        m = days == d
        off = datetime.fromtimestamp(int(d) * 86400 + 43200, tz=timezone.utc).astimezone(ny).utcoffset()
        local = ts[m] + int(off.total_seconds() * 1000) + shift_h * 3_600_000
        out[m] = local // 86_400_000
    return out


class FeatureFrame:
    def __init__(self, bars: Bars, calendar: str = "CRYPTO", market: str = "crypto",
                 extra: Optional[dict[str, np.ndarray]] = None, periods_per_year: Optional[float] = None):
        self.b = bars
        self.calendar = calendar
        self.market = market
        self.extra = extra or {}
        self._cache: dict[str, np.ndarray] = {}
        self._session: Optional[np.ndarray] = None
        step_days = bars.step / 86_400_000
        self.ppy = periods_per_year or ((365.0 if calendar == "CRYPTO" else 252.0) / step_days if bars.tf == "1d" else
                                        (365.0 if calendar == "CRYPTO" else 252.0) * (
                                            1440 if calendar == "CRYPTO" else 390) / (bars.step / 60_000))

    @property
    def o(self):
        return self.b.open

    @property
    def h(self):
        return self.b.high

    @property
    def l(self):          # noqa: E743
        return self.b.low

    @property
    def c(self):
        return self.b.close

    @property
    def v(self):
        return self.b.volume

    @property
    def session(self) -> np.ndarray:
        if self._session is None:
            self._session = session_ids(self.b.ts, self.calendar)
        return self._session

    def status(self, name: str) -> str:
        spec = REGISTRY[name]
        if self.market not in spec.markets:
            return "INCOMPATIBLE"
        missing = [r for r in spec.requires if r not in self.extra]
        return "UNAVAILABLE: needs " + ", ".join(missing) if missing else "OK"

    def __getitem__(self, name: str) -> np.ndarray:
        if name in self._cache:
            return self._cache[name]
        spec = REGISTRY.get(name)
        if spec is None:
            raise KeyError(f"unknown feature {name!r}")
        st = self.status(name)
        if st != "OK":
            raise KeyError(f"{name}: {st}")
        with np.errstate(all="ignore"):
            out = np.asarray(spec.fn(self), dtype=np.float64)
        if out.shape != self.c.shape:
            raise ValueError(f"{name} returned shape {out.shape}, expected {self.c.shape}")
        self._cache[name] = out
        return out

    def get(self, name: str, default=None):
        try:
            return self[name]
        except KeyError:
            return default

    def available(self) -> list[str]:
        return [n for n in REGISTRY if self.status(n) == "OK"]

    def matrix(self, names: list[str]) -> np.ndarray:
        return np.column_stack([self[n] for n in names]) if names else np.zeros((len(self.c), 0))


# ============================================================================ registrations
# trend
for n in (5, 10, 20, 50, 100, 200):
    reg(f"sma_{n}", "trend", f"mean(close, {n})", n, lambda f, n=n: I.sma(f.c, n), function="sma")
    reg(f"ema_{n}", "trend", f"EMA(close, {n}), alpha=2/({n}+1)", 3 * n, lambda f, n=n: I.ema(f.c, n), function="ema")
    reg(f"dist_sma_{n}_atr", "trend", f"(close - SMA{n}) / ATR14", n, lambda f, n=n: I.safe_div(f.c - I.sma(f.c, n),
        I.atr(f.h, f.l, f.c, 14)), inputs=("high", "low", "close"), norm="ATR units", function="dist")
for n in (9, 21, 50):
    reg(f"wma_{n}", "trend", f"linearly weighted mean(close, {n})", n, lambda f, n=n: I.wma(f.c, n), function="wma")
    reg(f"hma_{n}", "trend", f"Hull MA {n}", n + int(np.sqrt(n)), lambda f, n=n: I.hma(f.c, n), function="hma")
    reg(f"dema_{n}", "trend", f"2*EMA - EMA(EMA), {n}", 6 * n, lambda f, n=n: I.dema(f.c, n), function="dema")
    reg(f"tema_{n}", "trend", f"triple EMA {n}", 9 * n, lambda f, n=n: I.tema(f.c, n), function="tema")
    reg(f"zlema_{n}", "trend", f"zero-lag EMA {n}", 3 * n, lambda f, n=n: I.zlema(f.c, n), function="zlema")
    reg(f"trima_{n}", "trend", f"triangular MA {n}", n, lambda f, n=n: I.trima(f.c, n), function="trima")
    reg(f"vwma_{n}", "trend", f"sum(close*vol)/sum(vol), {n}", n, lambda f, n=n: I.vwma(f.c, f.v, n),
        inputs=("close", "volume"), function="vwma")
reg("kama_10", "trend", "Kaufman adaptive MA (10, 2, 30)", 11, lambda f: I.kama(f.c, 10), function="kama")
reg("alma_9", "trend", "Arnaud Legoux MA (9, 0.85, 6)", 9, lambda f: I.alma(f.c, 9), function="alma")
for n in (20, 50, 100):
    reg(f"linreg_slope_{n}", "trend", f"OLS slope of close over {n} bars / close", n,
        lambda f, n=n: I.safe_div(I.linreg(f.c, n)[0], f.c), norm="fraction per bar", function="linreg")
    reg(f"linreg_r2_{n}", "trend", f"R squared of the {n}-bar line", n, lambda f, n=n: I.linreg(f.c, n)[2],
        function="linreg")
for f_, s_ in ((12, 26), (5, 35)):
    reg(f"macd_{f_}_{s_}", "trend", f"EMA{f_} - EMA{s_}", 3 * s_, lambda f, a=f_, b=s_: I.macd(f.c, a, b)[0],
        function="macd")
    reg(f"macd_hist_{f_}_{s_}", "momentum", f"MACD - EMA9(MACD), {f_}/{s_}", 3 * s_ + 27,
        lambda f, a=f_, b=s_: I.macd(f.c, a, b)[2], function="macd")
    reg(f"macd_signal_{f_}_{s_}", "trend", f"EMA9 of MACD {f_}/{s_}", 3 * s_ + 27,
        lambda f, a=f_, b=s_: I.macd(f.c, a, b)[1], function="macd")
reg("ppo_12_26", "trend", "100*(EMA12-EMA26)/EMA26", 78, lambda f: I.ppo(f.c), norm="percent", function="ppo")
reg("trix_15", "trend", "1-bar change of triple EMA 15", 50, lambda f: I.trix(f.c, 15), function="trix")
for n in (14, 28):
    reg(f"adx_{n}", "trend", f"Wilder ADX {n}", 3 * n, lambda f, n=n: I.adx(f.h, f.l, f.c, n)[0],
        inputs=("high", "low", "close"), function="adx")
    reg(f"pdi_{n}", "trend", f"+DI {n}", 2 * n, lambda f, n=n: I.adx(f.h, f.l, f.c, n)[1],
        inputs=("high", "low", "close"), function="adx")
    reg(f"mdi_{n}", "trend", f"-DI {n}", 2 * n, lambda f, n=n: I.adx(f.h, f.l, f.c, n)[2],
        inputs=("high", "low", "close"), function="adx")
reg("aroon_up_25", "trend", "100*bars since 25-bar high, inverted", 26, lambda f: I.aroon(f.h, f.l, 25)[0],
    inputs=("high", "low"), function="aroon")
reg("aroon_dn_25", "trend", "100*bars since 25-bar low, inverted", 26, lambda f: I.aroon(f.h, f.l, 25)[1],
    inputs=("high", "low"), function="aroon")
reg("aroon_osc_25", "trend", "aroon up - aroon down", 26, lambda f: np.subtract(*I.aroon(f.h, f.l, 25)),
    inputs=("high", "low"), function="aroon")
for n, m in ((10, 3.0), (7, 2.0)):
    reg(f"supertrend_dir_{n}_{int(m)}", "trend", f"Supertrend direction (ATR {n} x {m})", 3 * n,
        lambda f, n=n, m=m: I.supertrend(f.h, f.l, f.c, n, m)[1], inputs=("high", "low", "close"),
        function="supertrend")
    reg(f"supertrend_dist_{n}_{int(m)}", "trend", f"(close - Supertrend line)/close ({n}, {m})", 3 * n,
        lambda f, n=n, m=m: I.safe_div(f.c - I.supertrend(f.h, f.l, f.c, n, m)[0], f.c),
        inputs=("high", "low", "close"), function="supertrend")
reg("psar_dir", "trend", "Parabolic SAR direction (0.02, 0.2)", 3, lambda f: I.psar(f.h, f.l)[1],
    inputs=("high", "low"), function="psar")
for k in ("tenkan", "kijun", "senkou_a", "senkou_b"):
    reg(f"ichimoku_{k}", "trend", f"Ichimoku {k} (9/26/52, cloud not shifted forward)", 78,
        lambda f, k=k: I.ichimoku(f.h, f.l)[k], inputs=("high", "low"), function="ichimoku")
reg("ichimoku_cloud_pos", "trend", "+1 above the cloud, -1 below, 0 inside", 78,
    lambda f: np.sign(f.c - np.fmax(I.ichimoku(f.h, f.l)["senkou_a"], I.ichimoku(f.h, f.l)["senkou_b"])).clip(0)
    - np.sign(np.fmin(I.ichimoku(f.h, f.l)["senkou_a"], I.ichimoku(f.h, f.l)["senkou_b"]) - f.c).clip(0),
    inputs=("high", "low", "close"), function="ichimoku")
for n in (20, 55):
    reg(f"donchian_pos_{n}", "trend", f"(close - prior {n}-bar low)/(high - low) of the prior {n} bars", n + 1,
        lambda f, n=n: I.safe_div(f.c - I.donchian(f.h, f.l, n)[1], I.donchian(f.h, f.l, n)[0] -
                                  I.donchian(f.h, f.l, n)[1]), inputs=("high", "low", "close"), norm="0..1",
        function="donchian")
    reg(f"donchian_break_{n}", "breakout", f"+1 close above prior {n}-bar high, -1 below prior low", n + 1,
        lambda f, n=n: (f.c > I.donchian(f.h, f.l, n)[0]).astype(float) - (f.c < I.donchian(f.h, f.l, n)[1]).astype(float),
        inputs=("high", "low", "close"), function="donchian")
reg("keltner_pos_20", "trend", "(close - Keltner mid)/(2 ATR)", 40, lambda f: I.safe_div(
    f.c - I.keltner(f.h, f.l, f.c)[0], I.keltner(f.h, f.l, f.c)[1] - I.keltner(f.h, f.l, f.c)[0]),
    inputs=("high", "low", "close"), function="keltner")
reg("vortex_diff_14", "trend", "VI+ - VI- (14)", 15, lambda f: np.subtract(*I.vortex(f.h, f.l, f.c, 14)),
    inputs=("high", "low", "close"), function="vortex")
reg("mass_index_25", "volatility", "sum over 25 of EMA9(range)/EMA9(EMA9(range))", 45,
    lambda f: I.mass_index(f.h, f.l), inputs=("high", "low"), function="mass")
reg("chop_14", "trend", "Choppiness index 14", 15, lambda f: I.choppiness(f.h, f.l, f.c, 14),
    inputs=("high", "low", "close"), function="chop")
reg("er_10", "trend", "Kaufman efficiency ratio 10", 11, lambda f: I.efficiency_ratio(f.c, 10), norm="0..1",
    function="er")
for n in (20, 63, 126, 252):
    reg(f"tsmom_{n}", "momentum", f"close/close[{n}] - 1", n + 1, lambda f, n=n: I.ret(f.c, n), norm="fraction",
        function="tsmom")
reg("hh_ll_10", "trend", "higher highs - lower lows over 10 bars", 11, lambda f: I.hh_ll_count(f.h, f.l, 10),
    inputs=("high", "low"), function="hhll")

# momentum
for n in (2, 3, 7, 14, 21):
    reg(f"rsi_{n}", "momentum", f"Wilder RSI {n}", 3 * n, lambda f, n=n: I.rsi(f.c, n), norm="0..100", function="rsi")
reg("stoch_k_14", "momentum", "%K 14 (3)", 17, lambda f: I.stoch(f.h, f.l, f.c)[0], inputs=("high", "low", "close"),
    norm="0..100", function="stoch")
reg("stoch_d_14", "momentum", "%D 14 (3,3)", 19, lambda f: I.stoch(f.h, f.l, f.c)[1], inputs=("high", "low", "close"),
    norm="0..100", function="stoch")
reg("stochrsi_14", "momentum", "stochastic of RSI 14", 56, lambda f: I.stoch_rsi(f.c, 14), norm="0..100",
    function="stochrsi")
for n in (10, 14):
    reg(f"willr_{n}", "momentum", f"Williams %R {n}", n, lambda f, n=n: I.williams_r(f.h, f.l, f.c, n),
        inputs=("high", "low", "close"), norm="-100..0", function="willr")
for n in (14, 20):
    reg(f"cci_{n}", "momentum", f"CCI {n}", n, lambda f, n=n: I.cci(f.h, f.l, f.c, n), inputs=("high", "low", "close"),
        function="cci")
for n in (1, 5, 10, 20):
    reg(f"roc_{n}", "momentum", f"100*(close/close[{n}] - 1)", n + 1, lambda f, n=n: I.roc(f.c, n), norm="percent",
        function="roc")
reg("mom_10", "momentum", "close - close[10]", 11, lambda f: I.momentum(f.c, 10), function="mom")
reg("cmo_14", "momentum", "Chande momentum oscillator 14", 15, lambda f: I.cmo(f.c, 14), norm="-100..100",
    function="cmo")
reg("uo", "momentum", "Ultimate oscillator 7/14/28", 29, lambda f: I.ultimate_osc(f.h, f.l, f.c),
    inputs=("high", "low", "close"), norm="0..100", function="uo")
reg("ao", "momentum", "SMA5(median) - SMA34(median)", 34, lambda f: I.awesome_osc(f.h, f.l), inputs=("high", "low"),
    function="ao")
reg("kst", "momentum", "Know Sure Thing", 45, lambda f: I.kst(f.c)[0], function="kst")
reg("kst_signal", "momentum", "SMA9 of KST", 54, lambda f: I.kst(f.c)[1], function="kst")
reg("tsi_25_13", "momentum", "True strength index 25/13", 120, lambda f: I.tsi(f.c), norm="-100..100",
    function="tsi")
reg("rvi_10", "momentum", "Relative vigor index 10", 14, lambda f: I.rvi(f.o, f.h, f.l, f.c),
    inputs=("open", "high", "low", "close"), function="rvi")
reg("fisher_10", "momentum", "Fisher transform of median price, 10", 14, lambda f: I.fisher(f.h, f.l, 10),
    inputs=("high", "low"), function="fisher")
reg("connors_rsi", "momentum", "(RSI3 + RSI2(streak) + percent rank of 1-bar return, 100)/3", 101,
    lambda f: I.connors_rsi(f.c), norm="0..100", function="crsi")
reg("bop_14", "momentum", "SMA14 of (close-open)/(high-low)", 14, lambda f: I.balance_of_power(f.o, f.h, f.l, f.c),
    inputs=("open", "high", "low", "close"), norm="-1..1", function="bop")
reg("bull_power_13", "momentum", "high - EMA13", 39, lambda f: I.elder_ray(f.h, f.l, f.c)[0],
    inputs=("high", "low", "close"), function="elder")
reg("bear_power_13", "momentum", "low - EMA13", 39, lambda f: I.elder_ray(f.h, f.l, f.c)[1],
    inputs=("high", "low", "close"), function="elder")
reg("coppock", "momentum", "WMA10(ROC14 + ROC11)", 25, lambda f: I.coppock(f.c), function="coppock")
reg("qstick_14", "momentum", "SMA14(close - open)", 14, lambda f: I.qstick(f.o, f.c), inputs=("open", "close"),
    function="qstick")
reg("ibs", "momentum", "(close - low)/(high - low)", 1, lambda f: I.ibs(f.h, f.l, f.c),
    inputs=("high", "low", "close"), norm="0..1", function="ibs")
reg("streak", "momentum", "consecutive up (+) or down (-) closes", 2, lambda f: I.streak(f.c), function="streak")
reg("ret_pctrank_100", "momentum", "percent rank of the 1-bar return over 100 bars", 101,
    lambda f: I.percent_rank(I.ret(f.c, 1), 100), norm="0..100", function="pctrank")

# volatility
for n in (7, 14, 21):
    reg(f"atr_{n}", "volatility", f"Wilder ATR {n}", 3 * n, lambda f, n=n: I.atr(f.h, f.l, f.c, n),
        inputs=("high", "low", "close"), norm="price units", function="atr")
    reg(f"natr_{n}", "volatility", f"100*ATR{n}/close", 3 * n, lambda f, n=n: I.natr(f.h, f.l, f.c, n),
        inputs=("high", "low", "close"), norm="percent", function="natr")
reg("tr", "volatility", "true range", 1, lambda f: I.true_range(f.h, f.l, f.c), inputs=("high", "low", "close"),
    function="tr")
for n in (20,):
    reg(f"bb_pctb_{n}", "volatility", f"Bollinger %B ({n}, 2)", n, lambda f, n=n: I.bollinger(f.c, n)[3], norm="%B",
        function="bollinger")
    reg(f"bb_width_{n}", "volatility", f"Bollinger bandwidth ({n}, 2)", n, lambda f, n=n: I.bollinger(f.c, n)[4],
        function="bollinger")
    reg(f"bb_width_pctrank_{n}", "volatility", f"percent rank of bandwidth over 120 bars", n + 120,
        lambda f, n=n: I.percent_rank(I.bollinger(f.c, n)[4], 120), norm="0..100", function="bollinger")
for n in (10, 20, 60):
    reg(f"rvol_{n}", "volatility", f"annualized stdev of log returns, {n} bars", n + 1,
        lambda f, n=n: I.realized_vol(f.c, n, f.ppy), norm="annualized", function="realized_vol")
reg("parkinson_20", "volatility", "Parkinson high-low volatility 20", 20, lambda f: I.parkinson(f.h, f.l, 20, f.ppy),
    inputs=("high", "low"), norm="annualized", function="parkinson")
reg("garman_klass_20", "volatility", "Garman-Klass volatility 20", 20,
    lambda f: I.garman_klass(f.o, f.h, f.l, f.c, 20, f.ppy), inputs=("open", "high", "low", "close"),
    norm="annualized", function="gk")
reg("rogers_satchell_20", "volatility", "Rogers-Satchell volatility 20", 20,
    lambda f: I.rogers_satchell(f.o, f.h, f.l, f.c, 20, f.ppy), inputs=("open", "high", "low", "close"),
    norm="annualized", function="rs")
reg("yang_zhang_20", "volatility", "Yang-Zhang volatility 20", 21, lambda f: I.yang_zhang(f.o, f.h, f.l, f.c, 20, f.ppy),
    inputs=("open", "high", "low", "close"), norm="annualized", function="yz")
reg("chaikin_vol_10", "volatility", "10-bar change of EMA10(high-low)", 20, lambda f: I.chaikin_vol(f.h, f.l),
    inputs=("high", "low"), norm="percent", function="chaikinvol")
reg("ulcer_14", "volatility", "Ulcer index 14", 28, lambda f: I.ulcer_index(f.c), function="ulcer")
reg("vol_ratio_10_60", "volatility", "stdev(10)/stdev(60) of log returns", 61, lambda f: I.vol_ratio(f.c),
    function="volratio")
reg("vol_pctrank_20", "volatility", "percent rank of 20-bar realized vol over 250 bars", 271,
    lambda f: I.percent_rank(I.realized_vol(f.c, 20, f.ppy), 250), norm="0..100", function="volrank")
reg("nr4", "volatility", "narrowest range of 4 bars", 4, lambda f: I.narrow_range(f.h, f.l, 4), inputs=("high", "low"),
    function="nr")
reg("nr7", "volatility", "narrowest range of 7 bars", 7, lambda f: I.narrow_range(f.h, f.l, 7), inputs=("high", "low"),
    function="nr")
reg("inside_bar", "volatility", "high < previous high and low > previous low", 2, lambda f: I.inside_bar(f.h, f.l),
    inputs=("high", "low"), function="inside")
reg("vol_of_vol_20", "volatility", "stdev of 20-bar stdev", 40, lambda f: I.vol_of_vol(f.c), function="volvol")
reg("atr_pctrank_14", "volatility", "percent rank of ATR14 over 250 bars", 290,
    lambda f: I.percent_rank(I.atr(f.h, f.l, f.c, 14), 250), inputs=("high", "low", "close"), norm="0..100",
    function="atrrank")

# volume
VOL = ("crypto", "stock", "etf", "future")
reg("obv", "volume", "on-balance volume", 1, lambda f: I.obv(f.c, f.v), inputs=("close", "volume"), markets=VOL,
    function="obv")
reg("obv_slope_20", "volume", "20-bar OLS slope of OBV / mean volume", 20,
    lambda f: I.safe_div(I.linreg(I.obv(f.c, f.v), 20)[0], I.sma(f.v, 20)), inputs=("close", "volume"), markets=VOL,
    function="obv")
reg("ad_line", "volume", "accumulation/distribution line", 1, lambda f: I.ad_line(f.h, f.l, f.c, f.v),
    inputs=("high", "low", "close", "volume"), markets=VOL, function="ad")
reg("cmf_20", "volume", "Chaikin money flow 20", 20, lambda f: I.cmf(f.h, f.l, f.c, f.v),
    inputs=("high", "low", "close", "volume"), markets=VOL, norm="-1..1", function="cmf")
reg("mfi_14", "volume", "money flow index 14", 15, lambda f: I.mfi(f.h, f.l, f.c, f.v),
    inputs=("high", "low", "close", "volume"), markets=VOL, norm="0..100", function="mfi")
reg("vwap_session", "volume", "session VWAP (resets each session)", 1,
    lambda f: I.vwap_session(f.h, f.l, f.c, f.v, f.session), inputs=("high", "low", "close", "volume"), markets=VOL,
    function="vwap")
reg("vwap_dist_atr", "volume", "(close - session VWAP)/ATR14", 14,
    lambda f: I.safe_div(f.c - I.vwap_session(f.h, f.l, f.c, f.v, f.session), I.atr(f.h, f.l, f.c, 14)),
    inputs=("high", "low", "close", "volume"), markets=VOL, norm="ATR units", function="vwap")
reg("vwap_band_pos", "volume", "(close - VWAP)/(2 sd VWAP band)", 2,
    lambda f: I.safe_div(f.c - I.vwap_bands(f.h, f.l, f.c, f.v, f.session)[0],
                         I.vwap_bands(f.h, f.l, f.c, f.v, f.session)[1] - I.vwap_bands(f.h, f.l, f.c, f.v, f.session)[0]),
    inputs=("high", "low", "close", "volume"), markets=VOL, function="vwap")
reg("vwap_roll_20_dist", "volume", "(close - rolling VWAP 20)/close", 20,
    lambda f: I.safe_div(f.c - I.vwap_rolling(f.h, f.l, f.c, f.v, 20), f.c), inputs=("high", "low", "close", "volume"),
    markets=VOL, function="vwap")
reg("force_13", "volume", "EMA13(change * volume)", 39, lambda f: I.force_index(f.c, f.v), inputs=("close", "volume"),
    markets=VOL, function="force")
reg("eom_14", "volume", "ease of movement 14", 15, lambda f: I.ease_of_movement(f.h, f.l, f.v),
    inputs=("high", "low", "volume"), markets=VOL, function="eom")
reg("vol_osc_5_20", "volume", "100*(EMA5(vol)-EMA20(vol))/EMA20(vol)", 60, lambda f: I.volume_osc(f.v),
    inputs=("volume",), markets=VOL, norm="percent", function="volosc")
reg("pvt", "volume", "price-volume trend", 2, lambda f: I.pvt(f.c, f.v), inputs=("close", "volume"), markets=VOL,
    function="pvt")
reg("nvi", "volume", "negative volume index", 2, lambda f: I.nvi(f.c, f.v), inputs=("close", "volume"), markets=VOL,
    function="nvi")
reg("pvi", "volume", "positive volume index", 2, lambda f: I.pvi(f.c, f.v), inputs=("close", "volume"), markets=VOL,
    function="pvi")
reg("klinger", "volume", "Klinger volume oscillator 34/55", 165, lambda f: I.klinger(f.h, f.l, f.c, f.v),
    inputs=("high", "low", "close", "volume"), markets=VOL, function="klinger")
for n in (10, 20):
    reg(f"relvol_{n}", "volume", f"volume / mean volume of the previous {n} bars", n + 1,
        lambda f, n=n: I.rvol(f.v, n), inputs=("volume",), markets=VOL, function="rvol")
reg("volume_z_20", "volume", "z-score of volume vs previous 20 bars", 21, lambda f: I.volume_z(f.v),
    inputs=("volume",), markets=VOL, function="volz")
reg("updown_vol_20", "volume", "up-bar volume / down-bar volume, 20", 21, lambda f: I.up_down_volume(f.c, f.v),
    inputs=("close", "volume"), markets=VOL, function="updownvol")
reg("ii_21", "volume", "intraday intensity 21", 21, lambda f: I.intraday_intensity(f.h, f.l, f.c, f.v),
    inputs=("high", "low", "close", "volume"), markets=VOL, function="ii")

# statistical
for n in (20, 50, 100):
    reg(f"zscore_{n}", "statistical", f"(close - SMA{n})/stdev{n}", n, lambda f, n=n: I.zscore(f.c, n), norm="z",
        function="zscore")
reg("ret_1", "statistical", "close/close[1] - 1", 2, lambda f: I.ret(f.c, 1), norm="fraction", function="ret")
reg("logret_1", "statistical", "log(close/close[1])", 2, lambda f: I.logret(f.c, 1), function="logret")
reg("skew_60", "statistical", "skew of 60 log returns", 61, lambda f: I.rskew(I.logret(f.c), 60), function="skew")
reg("kurt_60", "statistical", "excess kurtosis of 60 log returns", 61, lambda f: I.rkurt(I.logret(f.c), 60),
    function="kurt")
reg("autocorr_60", "statistical", "lag-1 autocorrelation of 60 log returns", 62,
    lambda f: I.autocorr(I.logret(f.c), 60, 1), norm="-1..1", function="autocorr")
reg("hurst_100", "statistical", "rescaled-range Hurst exponent, 100 returns", 101, lambda f: I.hurst(f.c, 100),
    function="hurst")
reg("variance_ratio_100", "statistical", "var(4-bar returns)/(4 var(1-bar returns)), 100", 104,
    lambda f: I.variance_ratio(f.c, 100, 4), function="vr")
reg("sign_entropy_50", "statistical", "binary entropy of up/down closes, 50", 51, lambda f: I.sign_entropy(f.c, 50),
    norm="0..1 bits", function="entropy")
reg("half_life_100", "statistical", "mean-reversion half-life of close, 100", 101, lambda f: I.half_life(f.c, 100),
    norm="bars", function="halflife")
reg("price_pctrank_100", "statistical", "percent rank of close over 100", 100, lambda f: I.percent_rank(f.c, 100),
    norm="0..100", function="pctrank")

# structure and candles
reg("swing_high_dist", "structure", "(last confirmed swing high - close)/ATR14, swings need 3 bars after", 20,
    lambda f: I.safe_div(I.swing_points(f.h, f.l, 3)[0] - f.c, I.atr(f.h, f.l, f.c, 14)),
    inputs=("high", "low", "close"), norm="ATR units", function="swing")
reg("swing_low_dist", "structure", "(close - last confirmed swing low)/ATR14", 20,
    lambda f: I.safe_div(f.c - I.swing_points(f.h, f.l, 3)[1], I.atr(f.h, f.l, f.c, 14)),
    inputs=("high", "low", "close"), norm="ATR units", function="swing")
for k in ("high", "low", "close"):
    idx = {"high": 0, "low": 1, "close": 2}[k]
    reg(f"prior_session_{k}", "structure", f"previous session's {k}", 2,
        lambda f, i=idx: I.prior_session_levels(f.h, f.l, f.c, f.session)[i], inputs=("high", "low", "close"),
        function="prior_session")
reg("dist_prior_high_atr", "structure", "(close - prior session high)/ATR14", 20,
    lambda f: I.safe_div(f.c - I.prior_session_levels(f.h, f.l, f.c, f.session)[0], I.atr(f.h, f.l, f.c, 14)),
    inputs=("high", "low", "close"), norm="ATR units", function="prior_session")
reg("dist_prior_low_atr", "structure", "(close - prior session low)/ATR14", 20,
    lambda f: I.safe_div(f.c - I.prior_session_levels(f.h, f.l, f.c, f.session)[1], I.atr(f.h, f.l, f.c, 14)),
    inputs=("high", "low", "close"), norm="ATR units", function="prior_session")
reg("pivot_dist_atr", "structure", "(close - classic pivot of prior session)/ATR14", 20,
    lambda f: I.safe_div(f.c - I.pivots_classic(*I.prior_session_levels(f.h, f.l, f.c, f.session))["pivot"],
                         I.atr(f.h, f.l, f.c, 14)), inputs=("high", "low", "close"), function="pivot")
reg("gap", "structure", "session open / prior session close - 1", 2, lambda f: I.gap(f.o, f.c, f.session),
    inputs=("open", "close"), norm="fraction", function="gap")
for k in ("body_frac", "upper_wick", "lower_wick"):
    reg(f"candle_{k}", "candle", f"candle {k.replace('_', ' ')} as a share of the range", 1,
        lambda f, k=k: I.candle_parts(f.o, f.h, f.l, f.c)[k], inputs=("open", "high", "low", "close"), norm="0..1",
        function="candle")
reg("engulfing", "candle", "+1 bullish engulfing, -1 bearish", 2, lambda f: I.engulfing(f.o, f.c),
    inputs=("open", "close"), function="engulfing")
reg("hammer", "candle", "long lower wick, small body", 1, lambda f: I.hammer(f.o, f.h, f.l, f.c),
    inputs=("open", "high", "low", "close"), function="hammer")
reg("doji", "candle", "body under 10% of range", 1, lambda f: I.doji(f.o, f.h, f.l, f.c),
    inputs=("open", "high", "low", "close"), function="doji")


# calendar / session
def _local(f: FeatureFrame, tz: str) -> np.ndarray:
    from zoneinfo import ZoneInfo
    z = ZoneInfo(tz)
    return np.array([datetime.fromtimestamp(int(t) / 1000, tz=timezone.utc).astimezone(z).hour * 60 +
                     datetime.fromtimestamp(int(t) / 1000, tz=timezone.utc).astimezone(z).minute for t in f.b.ts])


reg("hour_utc", "calendar", "hour of the bar's open, UTC", 0, lambda f: ((f.b.ts // 3_600_000) % 24).astype(float),
    function="calendar")
reg("dow_utc", "calendar", "weekday of the bar's open (0 = Monday), UTC", 0,
    lambda f: (((f.b.ts // 86_400_000) + 3) % 7).astype(float), function="calendar")
reg("weekend", "calendar", "1 on Saturday/Sunday (UTC)", 0,
    lambda f: ((((f.b.ts // 86_400_000) + 3) % 7) >= 5).astype(float), markets=("crypto",), function="calendar")
reg("minutes_ny", "calendar", "minutes since midnight, New York time", 0, lambda f: _local(f, "America/New_York"),
    function="calendar")
reg("bar_in_session", "calendar", "bars since the session started", 0,
    lambda f: np.concatenate([np.arange(c) for c in np.diff(np.flatnonzero(np.r_[True, f.session[1:] != f.session[:-1],
                                                                                   True]))]).astype(float),
    function="calendar")
reg("turn_of_month", "calendar", "1 in the last 2 and first 3 calendar days of a month (UTC)", 0,
    lambda f: np.array([1.0 if (d.day <= 3 or (d + timedelta(days=2)).month != d.month) else 0.0 for d in
                        (datetime.fromtimestamp(int(t) / 1000, tz=timezone.utc) for t in f.b.ts)]), function="calendar")
for s in ("london", "new_york", "tokyo", "sydney"):
    reg(f"fx_session_{s}", "calendar", f"1 inside the {s} session (local business hours)", 0,
        lambda f, s=s: np.array([1.0 if s in _fx_sessions(int(t)) else 0.0 for t in f.b.ts]), markets=("fx",),
        function="fx_session")


def _fx_sessions(ms: int) -> list[str]:
    from tradingai.market.calendars import fx_sessions
    return fx_sessions(ms)


# data this installation does not have: registered so strategies can declare them, never approximated
for name, cat, formula, req, markets in (
        ("funding_rate", "derivatives", "perpetual funding rate per interval", ("funding",), ("crypto",)),
        ("funding_z_30", "derivatives", "z-score of funding over 30 intervals", ("funding",), ("crypto",)),
        ("open_interest_chg", "derivatives", "change in open interest", ("open_interest",), ("crypto", "future")),
        ("basis_spot_perp", "derivatives", "perpetual mark / spot index - 1", ("mark_price", "index_price"), ("crypto",)),
        ("liquidations_1h", "derivatives", "liquidated notional, last hour", ("liquidations",), ("crypto",)),
        ("book_imbalance", "microstructure", "(bid size - ask size)/(bid size + ask size), top 10 levels",
         ("order_book",), ALL_MARKETS),
        ("microprice", "microstructure", "size-weighted mid price", ("order_book",), ALL_MARKETS),
        ("spread_bps", "microstructure", "10000*(ask - bid)/mid", ("quotes",), ALL_MARKETS),
        ("trade_delta", "microstructure", "buyer-initiated minus seller-initiated volume", ("trades",), ALL_MARKETS),
        ("cumulative_delta", "microstructure", "session cumulative trade delta", ("trades",), ALL_MARKETS),
        ("breadth_adv_dec", "breadth", "advancing minus declining constituents", ("breadth",), ("index", "etf")),
        ("pct_above_vwap", "breadth", "share of constituents above their VWAP", ("breadth",), ("index", "etf")),
        ("econ_surprise", "macro", "actual - consensus of the latest release", ("economic_calendar",), ALL_MARKETS),
        ("rate_differential", "macro", "2y yield difference between the pair's currencies", ("rates",), ("fx",)),
        ("stablecoin_flows", "onchain", "net stablecoin exchange inflow", ("onchain",), ("crypto",)),
        ("exchange_netflow", "onchain", "coin exchange inflow - outflow", ("onchain",), ("crypto",)),
        ("auction_imbalance", "microstructure", "closing auction imbalance", ("auction",), ("stock", "etf")),
        ("borrow_fee", "shorting", "annualized stock borrow fee", ("borrow",), ("stock", "etf")),
        ("implied_vol_30d", "volatility", "30-day implied volatility", ("options",), ("stock", "etf", "index"))):
    reg(name, cat, formula, 0, None, inputs=req, markets=markets, requires=req, function=name)


def summary() -> dict:
    by: dict[str, int] = {}
    for s in REGISTRY.values():
        by[s.category] = by.get(s.category, 0) + 1
    funcs = {s.function for s in REGISTRY.values()}
    return {"features": len(REGISTRY), "distinct_functions": len(funcs), "by_category": by,
            "need_external_data": sum(1 for s in REGISTRY.values() if s.requires)}
