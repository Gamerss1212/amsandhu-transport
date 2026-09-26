#!/usr/bin/env python3
"""The day-trading classics: the setups professional intraday traders are known for.

Five families, all long-only like the rest of the library:

  * session        opening-range breakouts, VWAP reclaims and pullbacks, gap-and-go,
                   gap-down reclaims, first-hour momentum, prior-day level trades and
                   floor-trader pivots. These only exist because markets have a daily
                   rhythm, so they read the session table (see SeriesCache.session),
                   which works on stocks' 9:30-16:00 sessions and on crypto's UTC day.
  * price action   engulfing bars, hammers, morning stars, three white soldiers,
                   outside-bar reversals, bull flags, the Fibonacci golden pocket and
                   pin bars at moving averages.
  * quant classics the Larry Connors-style short-term mean-reversion rules famous for
                   high win rates on stock indices: IBS, Double 7s, Connors RSI,
                   cumulative RSI(2) and three lower lows, all only above the 200 SMA.
  * trend/momentum Kaufman's adaptive average, Heikin-Ashi flips, the MACD zero-line
                   cross, the +DI/-DI cross, Keltner breakouts and the 9/21 EMA cross.
  * volume         selling-climax reversals and anchored-VWAP bounces.

None of these is here because someone said it works. They are here so they can be
*measured* the same way as everything else, on crypto and on stocks, and so the bots can
use the ones that measure well on a given market and ignore the rest.
"""

from __future__ import annotations

from engine.strategies import Ctx, Signal, strategy


def _s(strength, reason, stop=None, tags=None):
    return Signal(direction="long", strength=strength, reason=reason, stop_hint=stop, tags=tags or [])


FLAT = None


def _up_bias(c: Ctx) -> bool:
    """A light trend filter shared by the setups that should not buy into a downtrend."""
    e50 = c.last(c.ind("ema", period=50))
    return e50 is not None and c.price > e50


def _above_sma200(c: Ctx) -> bool:
    s = c.last(c.ind("sma", period=200))
    return s is not None and c.price > s


def _body(c: Ctx, k: int = 0) -> float:
    return c.close[-1 - k] - c.open[-1 - k]


def _range(c: Ctx, k: int = 0) -> float:
    return c.high[-1 - k] - c.low[-1 - k]


# =============================================================================
# Session: the setups that exist because markets have a daily rhythm
# =============================================================================

@strategy("opening_range_breakout", "session",
          "First close above the opening range (first hour of a stock session, 00:00-08:00 UTC on crypto) while above VWAP")
def opening_range_breakout(c: Ctx):
    s, p = c.sess(), c.sess(1)
    if not s or not p or not s["or_done"] or s["or_high"] is None or p["idx"] is None:
        return FLAT
    if not (c.close[-1] > s["or_high"] >= c.close[-2]):
        return FLAT
    late = s["idx"] >= 5 if s["gapped"] else c.candles[-1]["ts"].hour >= 20
    if late or c.close[-1] < s["vwap"]:
        return FLAT
    width = s["or_high"] - s["or_low"]
    atr = c.atr
    if not atr or width > 3 * atr:
        return FLAT                                   # a huge opening range leaves no room to run
    return _s(0.7, f"broke the opening range high {s['or_high']:.6g} above VWAP",
              stop=s["or_low"], tags=["session", "orb"])


@strategy("orb_retest_hold", "session", "Broke the opening range earlier, pulled back to its high and held it")
def orb_retest_hold(c: Ctx):
    s = c.sess()
    if not s or not s["or_done"] or s["or_high"] is None or s["idx"] < 2:
        return FLAT
    atr = c.atr
    if not atr:
        return FLAT
    k0 = s["idx"]                                    # bars since the session began
    closes = [c.close[-1 - k] for k in range(1, min(k0, 12) + 1)]
    if not any(x > s["or_high"] + 0.3 * atr for x in closes):
        return FLAT
    if not (c.low[-1] <= s["or_high"] + 0.2 * atr and c.close[-1] > s["or_high"] and _body(c) > 0):
        return FLAT
    return _s(0.65, "retested the broken opening-range high and held it",
              stop=s["or_high"] - 0.5 * atr, tags=["session", "orb"])


@strategy("vwap_reclaim", "session", "Close back above session VWAP after trading below it, in an up-biased market")
def vwap_reclaim(c: Ctx):
    s, p = c.sess(), c.sess(1)
    if not s or not p or s["start"] or s["idx"] < 1 or not _up_bias(c):
        return FLAT
    if not (c.close[-2] < p["vwap"] and c.close[-1] > s["vwap"] and _body(c) > 0):
        return FLAT
    return _s(0.6, "reclaimed session VWAP", stop=s["s_low"], tags=["session", "vwap"])


@strategy("vwap_trend_pullback", "session", "Trend day holding above VWAP; pullback touches VWAP and bounces")
def vwap_trend_pullback(c: Ctx):
    s = c.sess()
    atr = c.atr
    if not s or not atr or s["idx"] < 3:
        return FLAT
    s_all = c.cache.session()
    i = c.n - 1
    held = all(c.close[-1 - k] > s_all["vwap"][i - k] for k in range(1, s["idx"] + 1))
    if not held:
        return FLAT
    if not (c.low[-1] <= s["vwap"] + 0.2 * atr and c.close[-1] > s["vwap"] and _body(c) > 0):
        return FLAT
    return _s(0.7, "trend day: every close above VWAP, then a bounce off it",
              stop=s["vwap"] - 0.6 * atr, tags=["session", "vwap", "trend"])


@strategy("gap_and_go", "session", "Stock gaps up 1%+, first bar closes strong, then breaks the first bar's high")
def gap_and_go(c: Ctx):
    s = c.sess()
    if not s or not s["gapped"] or s["gap_pct"] is None or s["gap_pct"] < 1.0 or s["idx"] not in (1, 2):
        return FLAT
    i0 = c.n - 1 - s["idx"]                          # the session's first bar
    o0, h0, l0, c0 = c.open[i0 - c.n], c.high[i0 - c.n], c.low[i0 - c.n], c.close[i0 - c.n]
    if not (c0 > o0 and h0 > l0 and (c0 - l0) / (h0 - l0) > 0.6):
        return FLAT
    if not (c.close[-1] > h0 >= c.close[-2]):
        return FLAT
    return _s(0.7, f"gapped up {s['gap_pct']:.1f}% and went: broke the first bar's high",
              stop=l0, tags=["session", "gap"])


@strategy("gap_down_reclaim", "session", "Stock gaps down 1.5%+ then reclaims the first bar's high: sellers exhausted")
def gap_down_reclaim(c: Ctx):
    s = c.sess()
    if not s or not s["gapped"] or s["gap_pct"] is None or s["gap_pct"] > -1.5 or s["idx"] < 1 or s["idx"] > 4:
        return FLAT
    i0 = c.n - 1 - s["idx"]
    h0 = c.high[i0 - c.n]
    if not (c.close[-1] > h0 >= c.close[-2]):
        return FLAT
    return _s(0.6, f"gapped down {s['gap_pct']:.1f}% and reclaimed the opening bar's high",
              stop=s["s_low"], tags=["session", "gap", "reversal"])


@strategy("first_hour_momentum", "session",
          "Strong first hour (top of its range, +0.4% or more) predicts the rest of the day")
def first_hour_momentum(c: Ctx):
    s = c.sess()
    if not s or not s["gapped"] or s["idx"] != 0:
        return FLAT
    o, h, l, cl = c.open[-1], c.high[-1], c.low[-1], c.close[-1]
    if h <= l or o <= 0:
        return FLAT
    ret = (cl / o - 1) * 100
    if ret < 0.4 or (cl - l) / (h - l) < 0.75:
        return FLAT
    return _s(0.6, f"first hour +{ret:.2f}% closing near its high", stop=l, tags=["session", "momentum"])


@strategy("prior_day_low_reclaim", "session", "Swept below the prior day's low, then closed back above it (turtle soup)")
def prior_day_low_reclaim(c: Ctx):
    s = c.sess()
    if not s or s["prev_low"] is None:
        return FLAT
    pdl = s["prev_low"]
    if not (c.low[-1] < pdl < c.close[-1] or (s["s_low"] < pdl and c.close[-2] <= pdl < c.close[-1])):
        return FLAT
    if _body(c) <= 0:
        return FLAT
    return _s(0.65, "false break of the prior day's low, reclaimed", stop=s["s_low"],
              tags=["session", "liquidity"])


@strategy("pivot_bounce", "session", "Bounce off yesterday's floor pivot or S1 in an up-biased market")
def pivot_bounce(c: Ctx):
    s = c.sess()
    atr = c.atr
    if not s or s["prev_high"] is None or not atr or not _up_bias(c):
        return FLAT
    p = (s["prev_high"] + s["prev_low"] + s["prev_close"]) / 3
    s1 = 2 * p - s["prev_high"]
    for name, lvl in (("pivot", p), ("S1", s1)):
        if c.low[-1] <= lvl + 0.15 * atr and c.close[-1] > lvl and _body(c) > 0:
            return _s(0.6, f"bounced off yesterday's {name} {lvl:.6g}", stop=lvl - 0.8 * atr,
                      tags=["session", "pivot"])
    return FLAT


@strategy("inside_day_breakout", "session", "Yesterday was an inside day; today breaks yesterday's high")
def inside_day_breakout(c: Ctx):
    s = c.sess()
    if not s or s["prev_high"] is None or s["idx"] < 1:
        return FLAT
    sa = c.cache.session()
    # the session before yesterday: read prev_* at yesterday's first bar
    i0 = c.n - 1 - s["idx"] - 1                      # last bar of yesterday
    if i0 < 1 or sa["prev_high"][i0] is None:
        return FLAT
    y_hi, y_lo = s["prev_high"], s["prev_low"]
    d_hi, d_lo = sa["prev_high"][i0], sa["prev_low"][i0]
    if not (y_hi < d_hi and y_lo > d_lo):
        return FLAT
    if not (c.close[-1] > y_hi >= c.close[-2]):
        return FLAT
    return _s(0.65, "broke out of an inside day", stop=y_lo, tags=["session", "breakout"])


# =============================================================================
# Price action: candlestick and chart patterns
# =============================================================================

def _near_support(c: Ctx, atr: float) -> bool:
    lo20 = min(c.low[-20:]) if c.n >= 20 else None
    e50 = c.last(c.ind("ema", period=50))
    return ((lo20 is not None and c.low[-1] <= lo20 + 0.3 * atr)
            or (e50 is not None and abs(c.low[-1] - e50) <= 0.4 * atr))


@strategy("bullish_engulfing", "structure", "Green bar engulfs the prior red bar's body at support, above the 200 SMA")
def bullish_engulfing(c: Ctx):
    atr = c.atr
    if not atr or c.n < 30 or not _above_sma200(c):
        return FLAT
    if not (_body(c, 1) < 0 and _body(c) > 0 and c.open[-1] <= c.close[-2] and c.close[-1] >= c.open[-2]):
        return FLAT
    if abs(_body(c)) < 0.5 * atr or not _near_support(c, atr):
        return FLAT
    return _s(0.65, "bullish engulfing at support", stop=min(c.low[-1], c.low[-2]), tags=["price-action"])


@strategy("hammer_reversal", "structure", "Hammer (long lower wick, close near the high) at a 20-bar low, above the 200 SMA")
def hammer_reversal(c: Ctx):
    atr = c.atr
    if not atr or c.n < 30 or not _above_sma200(c):
        return FLAT
    o, h, l, cl = c.open[-1], c.high[-1], c.low[-1], c.close[-1]
    body = abs(cl - o)
    lower = min(o, cl) - l
    upper = h - max(o, cl)
    if (h - l) < 0.8 * atr or lower < 2 * max(body, 1e-12) or upper > max(body, 0.1 * (h - l)):
        return FLAT
    if l > min(c.low[-20:]) + 0.3 * atr:
        return FLAT
    return _s(0.6, "hammer at a 20-bar low", stop=l, tags=["price-action"])


@strategy("morning_star", "structure", "Big red bar, small indecision bar, big green bar closing past the red bar's midpoint")
def morning_star(c: Ctx):
    atr = c.atr
    if not atr or c.n < 30:
        return FLAT
    b1, b2, b3 = _body(c, 2), _body(c, 1), _body(c)
    if not (b1 < -0.8 * atr and abs(b2) < 0.35 * atr and b3 > 0.6 * atr):
        return FLAT
    if c.close[-1] < (c.open[-3] + c.close[-3]) / 2 or not _above_sma200(c):
        return FLAT
    return _s(0.6, "morning star reversal", stop=min(c.low[-1], c.low[-2], c.low[-3]), tags=["price-action"])


@strategy("three_white_soldiers", "structure", "Three strong green bars in a row after a pullback")
def three_white_soldiers(c: Ctx):
    atr = c.atr
    if not atr or c.n < 30:
        return FLAT
    for k in range(3):
        o, h, l, cl = c.open[-1 - k], c.high[-1 - k], c.low[-1 - k], c.close[-1 - k]
        if cl <= o or (cl - o) < 0.4 * atr or (h - cl) > 0.3 * (h - l):
            return FLAT
    if not (c.close[-1] > c.close[-2] > c.close[-3]):
        return FLAT
    e20 = c.ind("ema", period=20)
    if c.last(e20, 5) is None or c.close[-6] > c.last(e20, 5):
        return FLAT                                   # must come out of a pullback, not extend a run
    return _s(0.6, "three white soldiers out of a pullback", stop=c.low[-3], tags=["price-action"])


@strategy("outside_bar_reversal", "structure", "After 3+ down bars, a bar engulfs the prior range and closes near its high")
def outside_bar_reversal(c: Ctx):
    if c.n < 30:
        return FLAT
    if not (c.high[-1] > c.high[-2] and c.low[-1] < c.low[-2]):
        return FLAT
    rng = _range(c)
    if rng <= 0 or (c.close[-1] - c.low[-1]) / rng < 0.75:
        return FLAT
    if not all(c.close[-1 - k] < c.close[-2 - k] for k in range(1, 4)):
        return FLAT
    return _s(0.6, "outside-bar reversal after a selloff", stop=c.low[-1], tags=["price-action"])


@strategy("bull_flag", "structure", "A strong pole, a tight shallow flag on lighter volume, then a break of the flag high")
def bull_flag(c: Ctx):
    atr = c.atr
    if not atr or c.n < 40:
        return FLAT
    for flag_len in range(3, 9):
        top_i = -1 - flag_len                          # the pole's top bar
        pole_start = min(c.low[top_i - 8:top_i])
        pole = c.high[top_i] - pole_start
        if pole < 3 * atr:
            continue
        flag_hi = max(c.high[top_i:-1])
        flag_lo = min(c.low[top_i + 1:-1]) if flag_len > 1 else c.low[-2]
        if flag_lo < c.high[top_i] - 0.5 * pole:
            continue                                   # pulled back too far to be a flag
        pole_vol = sum(c.volume[top_i - 4:top_i + 1]) / 5
        flag_vol = sum(c.volume[top_i + 1:-1]) / max(1, flag_len - 1)
        if flag_vol > pole_vol:
            continue
        if c.close[-1] > flag_hi >= c.close[-2]:
            return _s(0.7, f"bull flag break after a {pole / atr:.1f} ATR pole", stop=flag_lo,
                      tags=["price-action", "continuation"])
    return FLAT


@strategy("fib_golden_pocket", "structure", "Pullback into the 50-61.8% retracement of the last up-swing, then a green bar")
def fib_golden_pocket(c: Ctx):
    from engine import indicators as ind
    atr = c.atr
    if not atr or c.n < 60 or not _up_bias(c):
        return FLAT
    hs = c.high[-60:]
    ls = c.low[-60:]
    sh, sl = ind.swing_points(hs, ls, 3)
    if not sh or not sl:
        return FLAT
    top = sh[-1]
    lows_before = [i for i in sl if i < top]
    if not lows_before:
        return FLAT
    bot = lows_before[-1]
    hi, lo = hs[top], ls[bot]
    if hi - lo < 3 * atr:
        return FLAT
    z_top, z_bot = hi - 0.5 * (hi - lo), hi - 0.618 * (hi - lo)
    if not (c.low[-1] <= z_top and c.low[-1] >= z_bot - 0.2 * atr and _body(c) > 0 and c.close[-1] > c.high[-2]):
        return FLAT
    return _s(0.65, "bounce from the golden pocket (50-61.8%)", stop=hi - 0.786 * (hi - lo),
              tags=["price-action", "fibonacci"])


@strategy("pin_bar_at_ema", "structure", "Bullish pin bar tagging the 21 or 50 EMA inside a bull stack")
def pin_bar_at_ema(c: Ctx):
    atr = c.atr
    e21, e50, e200 = (c.last(c.ind("ema", period=p)) for p in (21, 50, 200))
    if not atr or None in (e21, e50, e200) or not (e21 > e50 > e200):
        return FLAT
    o, h, l, cl = c.open[-1], c.high[-1], c.low[-1], c.close[-1]
    rng = h - l
    if rng <= 0 or (min(o, cl) - l) < 0.6 * rng:
        return FLAT
    for name, e in (("21 EMA", e21), ("50 EMA", e50)):
        if l <= e <= min(o, cl):
            return _s(0.65, f"pin bar rejected the {name}", stop=l, tags=["price-action", "trend"])
    return FLAT


# =============================================================================
# Quant classics: short-term mean reversion above the 200-day line
# =============================================================================

@strategy("ibs_reversion", "mean-reversion", "Internal bar strength under 0.15 (close at the bar's low) above the 200 SMA")
def ibs_reversion(c: Ctx):
    if not _above_sma200(c):
        return FLAT
    v = c.last(c.ind("ibs"))
    if v is None or v > 0.15:
        return FLAT
    return _s(0.55 + (0.15 - v), f"IBS {v:.2f}: closed at the low of its bar in an uptrend", tags=["quant", "ibs"])


@strategy("double_sevens", "mean-reversion", "Close at a 7-bar low while above the 200 SMA (Connors' Double 7s)")
def double_sevens(c: Ctx):
    if c.n < 210 or not _above_sma200(c):
        return FLAT
    if c.close[-1] > min(c.close[-7:]):
        return FLAT
    return _s(0.55, "closed at a 7-bar low above the 200 SMA", tags=["quant"])


@strategy("connors_rsi_dip", "mean-reversion", "Connors RSI under 10 while above the 200 SMA")
def connors_rsi_dip(c: Ctx):
    if not _above_sma200(c):
        return FLAT
    v = c.last(c.ind("connors_rsi"))
    if v is None or v >= 10:
        return FLAT
    return _s(0.6 + (10 - v) / 50, f"Connors RSI {v:.1f}: a deep short-term washout", tags=["quant"])


@strategy("cumulative_rsi2", "mean-reversion", "Two-bar sum of RSI(2) under 35 while above the 200 SMA")
def cumulative_rsi2(c: Ctx):
    if not _above_sma200(c):
        return FLAT
    r = c.ind("rsi", period=2)
    a, b = c.last(r), c.last(r, 1)
    if None in (a, b) or a + b >= 35:
        return FLAT
    return _s(0.6, f"cumulative RSI(2) {a + b:.0f}", tags=["quant"])


@strategy("three_lower_lows", "mean-reversion", "Three lower lows and lower closes in a row, above the 200 SMA")
def three_lower_lows(c: Ctx):
    if c.n < 210 or not _above_sma200(c):
        return FLAT
    if not all(c.low[-1 - k] < c.low[-2 - k] and c.close[-1 - k] < c.close[-2 - k] for k in range(3)):
        return FLAT
    return _s(0.55, "three lower lows in an uptrend", tags=["quant"])


# =============================================================================
# Trend and momentum
# =============================================================================

@strategy("kama_turn_up", "trend", "Kaufman's adaptive average turns up with price above it, above the 200 SMA")
def kama_turn_up(c: Ctx):
    k = c.ind("kama", period=10)
    a, b, d = c.last(k), c.last(k, 1), c.last(k, 2)
    if None in (a, b, d) or not (a > b <= d) or c.price <= a or not _above_sma200(c):
        return FLAT
    return _s(0.6, "adaptive average turned up", stop=min(c.low[-5:]), tags=["trend"])


@strategy("heikin_ashi_flip", "trend", "Heikin-Ashi turns green with no lower wick after three red bars")
def heikin_ashi_flip(c: Ctx):
    res = c.ind("heikin_ashi")
    if not res:
        return FLAT
    ho, hh, hl, hc = res
    vals = [(c.last(ho, k), c.last(hl, k), c.last(hc, k)) for k in range(4)]
    if any(None in v for v in vals):
        return FLAT
    o0, l0, c0 = vals[0]
    # no lower wick: the HA low is the HA open, i.e. the real low never traded below it
    if not (c0 > o0 and l0 >= o0 * (1 - 1e-9)):
        return FLAT
    if not all(v[2] < v[0] for v in vals[1:]):
        return FLAT
    if not _up_bias(c):
        return FLAT
    return _s(0.6, "Heikin-Ashi flipped green with no lower wick", stop=min(c.low[-4:]), tags=["trend"])


@strategy("macd_zero_cross", "momentum", "MACD line crosses above zero with the histogram positive")
def macd_zero_cross(c: Ctx):
    res = c.ind("macd")
    if not res:
        return FLAT
    line, sig, hist = res
    a, b, h = c.last(line), c.last(line, 1), c.last(hist)
    if None in (a, b, h) or not (a > 0 >= b) or h <= 0:
        return FLAT
    return _s(0.6, "MACD crossed above zero", stop=min(c.low[-8:]), tags=["momentum"])


@strategy("adx_di_cross", "trend", "+DI crosses above -DI with ADX above 20 and rising")
def adx_di_cross(c: Ctx):
    res = c.ind("adx", period=14)
    if not res:
        return FLAT
    adx, pdi, mdi = res
    if not c.crossed_up(pdi, mdi):
        return FLAT
    a, a1 = c.last(adx), c.last(adx, 3)
    if None in (a, a1) or a < 20 or a <= a1:
        return FLAT
    return _s(0.6, f"+DI crossed -DI with ADX {a:.0f} rising", stop=min(c.low[-6:]), tags=["trend"])


@strategy("keltner_breakout", "breakout", "First close above the upper Keltner channel in 10 bars, on above-average volume")
def keltner_breakout(c: Ctx):
    res = c.ind("keltner", period=20, mult=2.0)
    if not res:
        return FLAT
    mid, up, lo = res
    u = c.last(up)
    if u is None or c.close[-1] <= u:
        return FLAT
    if any(c.last(up, k) is not None and c.close[-1 - k] > c.last(up, k) for k in range(1, 10)):
        return FLAT
    rv = c.last(c.ind("relative_volume", period=20))
    if rv is None or rv < 1.2:
        return FLAT
    return _s(0.6, "broke out of the Keltner channel on volume", stop=c.last(mid), tags=["breakout"])


@strategy("ema_9_21_cross", "momentum", "9 EMA crosses above the 21 EMA while price is above the 200 EMA")
def ema_9_21_cross(c: Ctx):
    e9, e21 = c.ind("ema", period=9), c.ind("ema", period=21)
    e200 = c.last(c.ind("ema", period=200))
    if e200 is None or c.price <= e200 or not c.crossed_up(e9, e21):
        return FLAT
    return _s(0.55, "9 EMA crossed the 21 EMA above the 200", stop=min(c.low[-6:]), tags=["momentum"])


# =============================================================================
# Volume
# =============================================================================

@strategy("selling_climax_reversal", "volume", "A new 20-bar low on 3x volume that closes in the top half: capitulation")
def selling_climax_reversal(c: Ctx):
    atr = c.atr
    if not atr or c.n < 30:
        return FLAT
    rv = c.last(c.ind("relative_volume", period=20))
    if rv is None or rv < 3:
        return FLAT
    if c.low[-1] > min(c.low[-20:-1]):
        return FLAT
    rng = _range(c)
    if rng <= 0 or (c.close[-1] - c.low[-1]) / rng < 0.5:
        return FLAT
    if c.close[-6] - c.close[-1] < 2 * atr:
        return FLAT                                   # needs a real selloff into it
    return _s(0.6, f"selling climax on {rv:.1f}x volume, closed off the low", stop=c.low[-1],
              tags=["volume", "reversal"])


@strategy("anchored_vwap_bounce", "volume", "Pullback to the VWAP anchored at the 100-bar low, holding above it")
def anchored_vwap_bounce(c: Ctx):
    atr = c.atr
    if not atr or c.n < 110 or not _up_bias(c):
        return FLAT
    lows = c.low[-100:]
    k0 = min(range(len(lows)), key=lambda k: lows[k])
    start = c.n - 100 + k0
    pv = vv = 0.0
    for i in range(start, c.n):
        tp = (c.high[i - c.n] + c.low[i - c.n] + c.close[i - c.n]) / 3
        pv += tp * c.volume[i - c.n]
        vv += c.volume[i - c.n]
    if vv <= 0 or c.n - start < 10:
        return FLAT
    av = pv / vv
    if not (c.low[-1] <= av + 0.2 * atr and c.close[-1] > av and _body(c) > 0):
        return FLAT
    return _s(0.65, "held the VWAP anchored at the swing low", stop=av - 0.8 * atr, tags=["volume", "vwap"])
