#!/usr/bin/env python3
"""The built-in strategy library.

Sixty long-only strategies drawn from the families in the 320-strategy encyclopedia.
Long-only because this is a spot tool: on spot, the bearish version of every setup is
"stay flat", not "short".

Each one is deliberately small. A strategy answers one question — is my specific
pattern present right now — and returns how textbook this instance looks. It never
decides size, stop distance or whether the trade is affordable; those are decided
once, centrally, so that changing the risk model does not mean editing sixty files.
"""

from __future__ import annotations

from engine.strategies import Ctx, Signal, strategy


def _s(direction, strength, reason, stop=None, tags=None):
    return Signal(direction=direction, strength=strength, reason=reason,
                  stop_hint=stop, tags=tags or [])


FLAT = None   # returning None means "this pattern is not present", the common case


# =============================================================================
# Trend following
# =============================================================================

@strategy("ema_stack_pullback", "trend", "Price pulls back to the 21 EMA inside a 21>50>200 stack")
def ema_stack_pullback(c: Ctx):
    e9, e21 = c.ind("ema", period=9), c.ind("ema", period=21)
    e50, e200 = c.ind("ema", period=50), c.ind("ema", period=200)
    a, b, d, e = c.last(e9), c.last(e21), c.last(e50), c.last(e200)
    if None in (a, b, d, e) or not (b > d > e and c.price > e):
        return FLAT
    atr = c.atr
    if not atr:
        return FLAT
    dist = abs(c.price - b) / atr
    if dist > 0.7:
        return FLAT
    fresh = c.close[-1] > c.open[-1] and c.price > a
    return _s("long", 0.75 if fresh else 0.5,
              f"pullback to the 21 EMA ({dist:.2f} ATR away) in a clean bull stack",
              stop=b - 1.5 * atr, tags=["trend", "pullback"])


@strategy("supertrend_flip", "trend", "Supertrend flips up and price holds above the line")
def supertrend_flip(c: Ctx):
    res = c.ind("supertrend", period=10, multiplier=3.0)
    if not res:
        return FLAT
    line, direction = res
    if c.last(direction) != 1:
        return FLAT
    flipped_recently = any(direction[-k] == 1 and direction[-k - 1] == -1
                           for k in range(1, 6) if len(direction) > k + 1)
    lv = c.last(line)
    if lv is None:
        return FLAT
    return _s("long", 0.8 if flipped_recently else 0.45,
              "Supertrend flipped up within 5 bars" if flipped_recently else "Supertrend is up",
              stop=lv, tags=["trend", "supertrend"])


@strategy("supertrend_adx", "trend", "Supertrend up confirmed by ADX above 25")
def supertrend_adx(c: Ctx):
    res, adx_res = c.ind("supertrend"), c.ind("adx", period=14)
    if not res or not adx_res:
        return FLAT
    _, direction = res
    a, pdi, mdi = adx_res
    av, p, m = c.last(a), c.last(pdi), c.last(mdi)
    if c.last(direction) != 1 or None in (av, p, m):
        return FLAT
    if av < 25 or p <= m:
        return FLAT
    return _s("long", min(1.0, 0.5 + (av - 25) / 50),
              f"Supertrend up with ADX {av:.0f} and +DI over -DI: a trend with strength behind it",
              tags=["trend", "adx"])


@strategy("ichimoku_cloud_break", "trend", "Price above a rising cloud with Tenkan over Kijun")
def ichimoku_cloud_break(c: Ctx):
    res = c.ind("ichimoku")
    if not res:
        return FLAT
    tenkan, kijun, span_a, span_b = res
    t, k, sa, sb = c.last(tenkan), c.last(kijun), c.last(span_a), c.last(span_b)
    if None in (t, k, sa, sb):
        return FLAT
    cloud_top, cloud_bot = max(sa, sb), min(sa, sb)
    if c.price <= cloud_top or t <= k or sa <= sb:
        return FLAT
    return _s("long", 0.7, "above a rising Ichimoku cloud with Tenkan over Kijun",
              stop=cloud_bot, tags=["trend", "ichimoku"])


@strategy("ichimoku_kijun_bounce", "trend", "Pullback to the Kijun while above the cloud")
def ichimoku_kijun_bounce(c: Ctx):
    res = c.ind("ichimoku")
    if not res:
        return FLAT
    tenkan, kijun, span_a, span_b = res
    k, sa, sb = c.last(kijun), c.last(span_a), c.last(span_b)
    atr = c.atr
    if None in (k, sa, sb) or not atr or c.price < max(sa, sb):
        return FLAT
    if abs(c.price - k) / atr > 0.6:
        return FLAT
    return _s("long", 0.65, "pullback into the Kijun with the cloud still below",
              stop=min(sa, sb), tags=["trend", "ichimoku", "pullback"])


@strategy("golden_cross_pullback", "trend", "50 EMA above 200 EMA, buying the first dip to the 50")
def golden_cross_pullback(c: Ctx):
    e50, e200 = c.ind("ema", period=50), c.ind("ema", period=200)
    a, b, atr = c.last(e50), c.last(e200), c.atr
    if None in (a, b) or not atr or a <= b:
        return FLAT
    if abs(c.price - a) / atr > 0.8 or c.price < b:
        return FLAT
    return _s("long", 0.6, "dip into the 50 EMA while it sits above the 200",
              stop=b, tags=["trend"])


@strategy("hma_slope", "trend", "Hull moving average turning up")
def hma_slope(c: Ctx):
    h = c.ind("hma", period=21)
    a, b, d = c.last(h), c.last(h, 1), c.last(h, 3)
    if None in (a, b, d) or not (a > b > d) or c.price < a:
        return FLAT
    return _s("long", 0.55, "Hull MA rising for three bars with price above it", tags=["trend"])


@strategy("parabolic_sar_flip", "trend", "Parabolic SAR flips beneath price")
def parabolic_sar_flip(c: Ctx):
    sar = c.ind("parabolic_sar")
    v, prev = c.last(sar), c.last(sar, 2)
    if v is None or prev is None:
        return FLAT
    if not (v < c.price and prev > c.close[-3]):
        return FLAT
    return _s("long", 0.6, "SAR flipped below price", stop=v, tags=["trend"])


@strategy("aroon_up", "trend", "Aroon up dominant and above 70")
def aroon_up(c: Ctx):
    res = c.ind("aroon", period=25)
    if not res:
        return FLAT
    up, dn = res
    u, d = c.last(up), c.last(dn)
    if None in (u, d) or u < 70 or u <= d:
        return FLAT
    return _s("long", 0.55, f"Aroon up at {u:.0f} with down at {d:.0f}", tags=["trend"])


@strategy("vortex_cross", "trend", "Vortex +VI crosses above -VI")
def vortex_cross(c: Ctx):
    res = c.ind("vortex", period=14)
    if not res:
        return FLAT
    vp, vm = res
    if not c.crossed_up(vp, vm, within=3):
        return FLAT
    return _s("long", 0.55, "Vortex +VI crossed above -VI in the last 3 bars", tags=["trend"])


@strategy("linreg_slope", "trend", "Linear regression slope positive and price near the line")
def linreg_slope(c: Ctx):
    r = c.ind("linreg_channel", period=100)
    if not r or r["slope"] <= 0:
        return FLAT
    if r["stdev"] <= 0:
        return FLAT
    z = (c.price - r["value_now"]) / r["stdev"]
    if z > 0.5 or z < -2.5:
        return FLAT
    return _s("long", 0.6, f"regression channel rising {r['slope_pct_per_bar']:.2f}%/bar, "
                           f"price {z:+.1f} sigma from the line", tags=["trend", "mean-reversion"])


@strategy("higher_low_sequence", "trend", "Three rising swing lows")
def higher_low_sequence(c: Ctx):
    from engine import indicators as ind2
    sh, sl = ind2.swing_points(c.high, c.low, 3)
    if len(sl) < 3:
        return FLAT
    lows = [c.low[i] for i in sl[-3:]]
    if not (lows[0] < lows[1] < lows[2]) or c.price < lows[2]:
        return FLAT
    return _s("long", 0.7, "three rising swing lows with price holding above the last",
              stop=lows[2], tags=["trend", "structure"])


# =============================================================================
# Mean reversion
# =============================================================================

@strategy("rsi2_reversion", "mean-reversion", "RSI(2) washout while above the 200 EMA")
def rsi2_reversion(c: Ctx):
    from engine import indicators as ind2
    r2 = ind2.rsi(c.close, 2)
    e200 = c.ind("ema", period=200)
    v, e = c.last(r2), c.last(e200)
    if None in (v, e) or c.price < e or v > 10:
        return FLAT
    return _s("long", 0.75 if v < 5 else 0.6,
              f"RSI(2) at {v:.0f} inside an uptrend — a short-term washout, not a trend change",
              tags=["mean-reversion"])


@strategy("bollinger_reversion", "mean-reversion", "Close back inside the lower Bollinger band")
def bollinger_reversion(c: Ctx):
    res = c.ind("bollinger", period=20, mult=2.0)
    if not res:
        return FLAT
    mid, up, lo, width = res
    l_now, l_prev, m = c.last(lo), c.last(lo, 1), c.last(mid)
    if None in (l_now, l_prev, m):
        return FLAT
    if not (c.close[-2] < l_prev and c.close[-1] >= l_now):
        return FLAT
    e50, e200 = c.last(c.ind("ema", period=50)), c.last(c.ind("ema", period=200))
    if e50 and e200 and e50 < e200:
        return FLAT                                # do not fade a downtrend
    return _s("long", 0.65, "closed back inside the lower band after poking outside",
              stop=min(c.low[-2], c.low[-1]), tags=["mean-reversion"])


@strategy("keltner_reversion", "mean-reversion", "Rejection off the lower Keltner channel")
def keltner_reversion(c: Ctx):
    res = c.ind("keltner", period=20, mult=2.0)
    if not res:
        return FLAT
    mid, up, lo = res
    l, m = c.last(lo), c.last(mid)
    if None in (l, m) or c.low[-1] > l or c.close[-1] < l:
        return FLAT
    return _s("long", 0.6, "wicked below the Keltner channel and closed back inside",
              stop=c.low[-1], tags=["mean-reversion"])


@strategy("stretch_snapback", "mean-reversion", "More than 2.5 ATR below the 20 EMA, then a green bar")
def stretch_snapback(c: Ctx):
    e20, atr = c.ind("ema", period=20), c.atr
    e = c.last(e20)
    if None in (e,) or not atr:
        return FLAT
    stretch = (e - c.price) / atr
    if stretch < 2.0 or c.close[-1] <= c.open[-1]:
        return FLAT
    return _s("long", min(0.8, 0.4 + stretch / 8),
              f"{stretch:.1f} ATR below the 20 EMA with a green close — a rubber band, not a trend",
              tags=["mean-reversion"])


@strategy("williams_r_extreme", "mean-reversion", "Williams %R leaving oversold in an uptrend")
def williams_r_extreme(c: Ctx):
    w = c.ind("williams_r", period=14)
    e200 = c.last(c.ind("ema", period=200))
    v, prev = c.last(w), c.last(w, 1)
    if None in (v, prev) or not e200 or c.price < e200:
        return FLAT
    if not (prev < -80 and v >= -80):
        return FLAT
    return _s("long", 0.55, "Williams %R climbing out of oversold above the 200 EMA",
              tags=["mean-reversion"])


@strategy("cci_reversal", "mean-reversion", "CCI crossing back above -100")
def cci_reversal(c: Ctx):
    v = c.ind("cci", period=20)
    cur, prev = c.last(v), c.last(v, 1)
    if None in (cur, prev) or not (prev < -100 and cur >= -100):
        return FLAT
    return _s("long", 0.5, "CCI crossed back above -100", tags=["mean-reversion"])


@strategy("stoch_oversold_cross", "mean-reversion", "Stochastic %K crosses %D from below 20")
def stoch_oversold_cross(c: Ctx):
    res = c.ind("stochastic", k_period=14)
    if not res:
        return FLAT
    k, d = res
    kv = c.last(k)
    if kv is None or kv > 35 or not c.crossed_up(k, d, within=2):
        return FLAT
    return _s("long", 0.55, f"stochastic crossed up from {kv:.0f}", tags=["mean-reversion"])


@strategy("vwap_band_fade", "mean-reversion", "Tag of the lower VWAP band on a range day")
def vwap_band_fade(c: Ctx):
    from engine import indicators as ind2
    flags = [i == 0 or c.candles[i]["ts"].date() != c.candles[i - 1]["ts"].date()
             for i in range(c.n)]
    vw, up, lo = ind2.vwap_bands(c.high, c.low, c.close, c.volume, flags, mult=2.0)
    v, l = c.last(vw), c.last(lo)
    if None in (v, l) or c.low[-1] > l or c.close[-1] < l:
        return FLAT
    return _s("long", 0.6, "tagged the lower VWAP band and closed back inside",
              stop=c.low[-1], tags=["mean-reversion", "vwap"])


@strategy("range_low_fade", "mean-reversion", "Rejection at the bottom of an established range")
def range_low_fade(c: Ctx):
    look = min(c.n, 60)
    hi, lo = max(c.high[-look:]), min(c.low[-look:])
    atr = c.atr
    if not atr or (hi - lo) / atr < 2.5:
        return FLAT
    if (c.price - lo) / (hi - lo) > 0.2:
        return FLAT
    if c.close[-1] <= c.open[-1]:
        return FLAT
    return _s("long", 0.6, "green close at the bottom of a range at least 2.5 ATR tall",
              stop=lo - 0.5 * atr, tags=["mean-reversion", "range"])


@strategy("mfi_oversold", "mean-reversion", "Money flow index leaving oversold")
def mfi_oversold(c: Ctx):
    v = c.ind("mfi", period=14)
    cur, prev = c.last(v), c.last(v, 1)
    if None in (cur, prev) or not (prev < 20 and cur >= 20):
        return FLAT
    return _s("long", 0.55, "money flow climbing out of oversold", tags=["mean-reversion", "volume"])


# =============================================================================
# Breakout
# =============================================================================

@strategy("donchian_breakout", "breakout", "Close above the 20-bar Donchian high")
def donchian_breakout(c: Ctx):
    res = c.ind("donchian", period=20)
    if not res:
        return FLAT
    up, mid, lo = res
    prev_up = c.last(up, 1)
    if prev_up is None or c.close[-1] <= prev_up:
        return FLAT
    rv = c.last(c.ind("relative_volume", period=20))
    return _s("long", 0.75 if (rv and rv >= 1.5) else 0.5,
              f"closed above the 20-bar high" + (f" on {rv:.1f}x volume" if rv else ""),
              stop=c.last(mid), tags=["breakout"])


@strategy("donchian_55", "breakout", "Close above the 55-bar high, the original turtle entry")
def donchian_55(c: Ctx):
    res = c.ind("donchian", period=55)
    if not res:
        return FLAT
    up, mid, lo = res
    prev = c.last(up, 1)
    if prev is None or c.close[-1] <= prev:
        return FLAT
    return _s("long", 0.65, "closed above the 55-bar high", stop=c.last(mid), tags=["breakout"])


@strategy("squeeze_release", "breakout", "Bollinger squeeze inside Keltner releases upward")
def squeeze_release(c: Ctx):
    sq = c.ind("squeeze_momentum")
    if not sq:
        return FLAT
    was = any(sq[-k] for k in range(2, 8) if sq[-k] is not None)
    now = c.last(sq)
    if not was or now:
        return FLAT                                 # want the release, not the squeeze
    if c.close[-1] <= c.open[-1]:
        return FLAT
    res = c.ind("bollinger", period=20, mult=2.0)
    mid = c.last(res[0]) if res else None
    return _s("long", 0.75, "volatility squeeze released with an up bar — expansion has begun",
              stop=mid, tags=["breakout", "volatility"])


@strategy("bollinger_breakout", "breakout", "Close above the upper Bollinger band on volume")
def bollinger_breakout(c: Ctx):
    res = c.ind("bollinger", period=20, mult=2.0)
    if not res:
        return FLAT
    mid, up, lo, width = res
    u = c.last(up)
    rv = c.last(c.ind("relative_volume", period=20))
    if u is None or c.close[-1] <= u or not rv or rv < 1.5:
        return FLAT
    return _s("long", 0.6, f"closed above the upper band on {rv:.1f}x volume",
              stop=c.last(mid), tags=["breakout"])


@strategy("breakout_retest", "breakout", "Broke a 40-bar high, then came back and held it")
def breakout_retest(c: Ctx):
    if c.n < 60:
        return FLAT
    for back in range(1, 8):
        j = c.n - 1 - back
        if j < 45:
            continue
        level = max(c.high[j - 40:j])
        if c.close[j] > level >= c.close[j - 1]:
            if c.low[-1] <= level <= c.high[-1] and c.close[-1] > level:
                return _s("long", 0.8, f"retested the broken {level:.6g} level and held it",
                          stop=level - (c.atr or 0) * 0.5, tags=["breakout", "retest"])
    return FLAT


@strategy("inside_bar_break", "breakout", "Break of an inside bar in an uptrend")
def inside_bar_break(c: Ctx):
    if c.n < 210:
        return FLAT
    e200 = c.last(c.ind("ema", period=200))
    if not e200 or c.price < e200:
        return FLAT
    mh, ml = c.high[-3], c.low[-3]
    inside = c.high[-2] < mh and c.low[-2] > ml
    if not inside or c.close[-1] <= mh:
        return FLAT
    return _s("long", 0.6, "broke the mother bar of an inside bar with the trend",
              stop=ml, tags=["breakout"])


@strategy("prior_day_high_break", "breakout", "Close above the prior day's high")
def prior_day_high_break(c: Ctx):
    days = {}
    for cd in c.candles:
        d = cd["ts"].date()
        e = days.setdefault(d, {"high": cd["high"], "low": cd["low"]})
        e["high"] = max(e["high"], cd["high"])
        e["low"] = min(e["low"], cd["low"])
    keys = sorted(days)
    if len(keys) < 2:
        return FLAT
    pdh = days[keys[-2]]["high"]
    if c.close[-1] <= pdh or c.close[-2] > pdh:
        return FLAT
    return _s("long", 0.65, "first close above the prior day's high", stop=pdh, tags=["breakout"])


@strategy("nr7_break", "breakout", "Narrowest range in 7 bars, then a break upward")
def nr7_break(c: Ctx):
    if c.n < 10:
        return FLAT
    ranges = [c.high[i] - c.low[i] for i in range(c.n - 8, c.n - 1)]
    if not ranges or (c.high[-2] - c.low[-2]) > min(ranges):
        return FLAT
    if c.close[-1] <= c.high[-2]:
        return FLAT
    return _s("long", 0.6, "broke out of the narrowest bar in seven", stop=c.low[-2],
              tags=["breakout", "volatility"])


@strategy("volume_ignition", "breakout", "An outsized bar on heavy volume with the trend")
def volume_ignition(c: Ctx):
    atr, rv = c.atr, c.last(c.ind("relative_volume", period=20))
    if not atr or not rv or rv < 2.5:
        return FLAT
    rng = c.high[-1] - c.low[-1]
    if rng / atr < 1.8 or c.close[-1] <= c.open[-1]:
        return FLAT
    body = abs(c.close[-1] - c.open[-1]) / rng if rng else 0
    if body < 0.5:
        return FLAT
    return _s("long", 0.7, f"{rng/atr:.1f} ATR bar on {rv:.1f}x volume closing strong",
              stop=c.low[-1], tags=["breakout", "momentum"])


@strategy("channel_break_adx", "breakout", "Donchian break while ADX confirms a trend")
def channel_break_adx(c: Ctx):
    res, adx_res = c.ind("donchian", period=20), c.ind("adx", period=14)
    if not res or not adx_res:
        return FLAT
    up, mid, lo = res
    a, pdi, mdi = adx_res
    av = c.last(a)
    prev_up = c.last(up, 1)
    if None in (av, prev_up) or av < 20 or c.close[-1] <= prev_up:
        return FLAT
    return _s("long", 0.7, f"20-bar breakout with ADX at {av:.0f}", stop=c.last(mid),
              tags=["breakout", "trend"])


# =============================================================================
# Momentum
# =============================================================================

@strategy("macd_cross", "momentum", "MACD line crosses its signal below zero")
def macd_cross(c: Ctx):
    res = c.ind("macd")
    if not res:
        return FLAT
    line, sig, hist = res
    if not c.crossed_up(line, sig, within=2):
        return FLAT
    lv = c.last(line)
    return _s("long", 0.65 if (lv is not None and lv < 0) else 0.5,
              "MACD crossed up" + (" from below zero" if (lv is not None and lv < 0) else ""),
              tags=["momentum"])


@strategy("macd_hist_turn", "momentum", "MACD histogram turns up during a pullback")
def macd_hist_turn(c: Ctx):
    res = c.ind("macd")
    e50 = c.last(c.ind("ema", period=50))
    if not res or not e50 or c.price < e50:
        return FLAT
    line, sig, hist = res
    h0, h1, h2 = c.last(hist), c.last(hist, 1), c.last(hist, 2)
    if None in (h0, h1, h2) or not (h2 > h1 and h0 > h1 and h1 < 0):
        return FLAT
    return _s("long", 0.6, "MACD histogram turned up from below zero in an uptrend",
              tags=["momentum", "pullback"])


@strategy("rsi_50_reclaim", "momentum", "RSI reclaims 50 in an uptrend")
def rsi_50_reclaim(c: Ctx):
    r = c.ind("rsi", period=14)
    e200 = c.last(c.ind("ema", period=200))
    cur, prev = c.last(r), c.last(r, 1)
    if None in (cur, prev) or not e200 or c.price < e200:
        return FLAT
    if not (prev < 50 and cur >= 50):
        return FLAT
    return _s("long", 0.6, "RSI reclaimed 50 above the 200 EMA", tags=["momentum"])


@strategy("rsi_bullish_divergence", "momentum", "Price makes a lower low, RSI does not")
def rsi_bullish_divergence(c: Ctx):
    from engine import indicators as ind2
    r = c.ind("rsi", period=14)
    sh, sl = ind2.swing_points(c.high, c.low, 3)
    if not r or len(sl) < 2:
        return FLAT
    i1, i2 = sl[-2], sl[-1]
    if r[i1] is None or r[i2] is None:
        return FLAT
    if not (c.low[i2] < c.low[i1] and r[i2] > r[i1]):
        return FLAT
    return _s("long", 0.6, "lower low in price against a higher low in RSI",
              stop=c.low[i2], tags=["momentum", "divergence"])


@strategy("stoch_rsi_turn", "momentum", "Stochastic RSI turns up from oversold")
def stoch_rsi_turn(c: Ctx):
    res = c.ind("stoch_rsi")
    if not res:
        return FLAT
    k, d = res
    kv = c.last(k)
    if kv is None or kv > 30 or not c.crossed_up(k, d, within=2):
        return FLAT
    return _s("long", 0.5, "stochastic RSI turned up from oversold", tags=["momentum"])


@strategy("awesome_saucer", "momentum", "Awesome oscillator saucer above zero")
def awesome_saucer(c: Ctx):
    ao = c.ind("awesome_oscillator")
    a0, a1, a2 = c.last(ao), c.last(ao, 1), c.last(ao, 2)
    if None in (a0, a1, a2) or a0 <= 0:
        return FLAT
    if not (a2 > a1 and a0 > a1):
        return FLAT
    return _s("long", 0.55, "awesome oscillator saucer above zero", tags=["momentum"])


@strategy("roc_thrust", "momentum", "Rate of change accelerating from a base")
def roc_thrust(c: Ctx):
    r = c.ind("roc", period=12)
    cur, prev = c.last(r), c.last(r, 3)
    if None in (cur, prev) or cur < 3 or cur <= prev:
        return FLAT
    e50 = c.last(c.ind("ema", period=50))
    if not e50 or c.price < e50:
        return FLAT
    return _s("long", 0.55, f"12-bar rate of change accelerating to {cur:.1f}%", tags=["momentum"])


@strategy("ultimate_oscillator_turn", "momentum", "Ultimate oscillator leaving oversold")
def ultimate_oscillator_turn(c: Ctx):
    u = c.ind("ultimate_oscillator")
    cur, prev = c.last(u), c.last(u, 1)
    if None in (cur, prev) or not (prev < 35 and cur >= 35):
        return FLAT
    return _s("long", 0.5, "ultimate oscillator climbing out of oversold", tags=["momentum"])


# =============================================================================
# Volatility and regime
# =============================================================================

@strategy("atr_expansion", "volatility", "ATR expanding sharply against its own average")
def atr_expansion(c: Ctx):
    a = c.ind("atr", period=14)
    cur = c.last(a)
    hist = [v for v in a[-100:] if v is not None]
    if not cur or len(hist) < 30:
        return FLAT
    avg = sum(hist) / len(hist)
    ratio = cur / avg if avg else 1
    if ratio < 1.4 or c.close[-1] <= c.open[-1]:
        return FLAT
    return _s("long", min(0.8, 0.35 + ratio / 5),
              f"ATR at {ratio:.1f}x its recent average with an up bar", tags=["volatility"])


@strategy("choppiness_exit", "volatility", "Choppiness falling out of the range zone")
def choppiness_exit(c: Ctx):
    ch = c.ind("choppiness", period=14)
    cur, prev = c.last(ch), c.last(ch, 2)
    if None in (cur, prev) or not (prev > 61 and cur < 55):
        return FLAT
    if c.close[-1] <= c.open[-1]:
        return FLAT
    return _s("long", 0.6, "choppiness dropped out of the range zone — a trend may be starting",
              tags=["volatility", "regime"])


@strategy("volatility_contraction", "volatility", "Successively narrower bars into a coil")
def volatility_contraction(c: Ctx):
    if c.n < 12:
        return FLAT
    r = [c.high[i] - c.low[i] for i in range(c.n - 6, c.n)]
    if not all(r[i] >= r[i + 1] for i in range(len(r) - 2)):
        return FLAT
    e50 = c.last(c.ind("ema", period=50))
    if not e50 or c.price < e50:
        return FLAT
    return _s("long", 0.55, "bars contracting into a coil above the 50 EMA",
              tags=["volatility", "coil"])


@strategy("bb_width_floor", "volatility", "Bollinger width at a 100-bar low")
def bb_width_floor(c: Ctx):
    res = c.ind("bollinger", period=20, mult=2.0)
    if not res:
        return FLAT
    mid, up, lo, width = res
    w = c.last(width)
    hist = [v for v in width[-100:] if v is not None]
    if w is None or len(hist) < 50:
        return FLAT
    rank = 100 * sum(1 for v in hist if v < w) / len(hist)
    if rank > 12:
        return FLAT
    return _s("long", 0.5, f"Bollinger width in the {rank:.0f}th percentile — coiled, direction unknown",
              tags=["volatility", "coil"])


@strategy("post_cascade_reclaim", "volatility", "A violent drop that reclaims its midpoint")
def post_cascade_reclaim(c: Ctx):
    atr = c.atr
    if not atr or c.n < 10:
        return FLAT
    for k in range(2, 7):
        rng = c.high[-k] - c.low[-k]
        if rng / atr < 2.5 or c.close[-k] >= c.open[-k]:
            continue
        mid = (c.high[-k] + c.low[-k]) / 2
        if c.price > mid and min(c.low[-k + 1:]) > c.low[-k]:
            return _s("long", 0.65,
                      f"reclaimed the midpoint of a {rng/atr:.1f} ATR flush without retesting its low",
                      stop=c.low[-k], tags=["volatility", "reversal"])
    return FLAT


@strategy("elder_ray_bull", "volatility", "Bear power rising while the trend is up")
def elder_ray_bull(c: Ctx):
    res = c.ind("elder_ray", period=13)
    if not res:
        return FLAT
    bull, bear = res
    b0, b1 = c.last(bear), c.last(bear, 1)
    e13 = c.last(c.ind("ema", period=13))
    if None in (b0, b1, e13) or c.price < e13:
        return FLAT
    if not (b0 < 0 and b0 > b1):
        return FLAT
    return _s("long", 0.5, "bear power rising while price holds above the 13 EMA", tags=["momentum"])


# =============================================================================
# Volume
# =============================================================================

@strategy("obv_breakout", "volume", "On-balance volume makes a new high before price")
def obv_breakout(c: Ctx):
    o = c.ind("obv")
    if not o or len(o) < 60:
        return FLAT
    cur = c.last(o)
    window = o[-50:-1]
    if cur is None or not window or cur <= max(window):
        return FLAT
    if c.price >= max(c.high[-50:-1]):
        return FLAT                                 # want OBV leading, not confirming
    return _s("long", 0.65, "on-balance volume at a 50-bar high while price is not — accumulation",
              tags=["volume", "divergence"])


@strategy("cmf_positive_turn", "volume", "Chaikin money flow crosses above zero")
def cmf_positive_turn(c: Ctx):
    v = c.ind("cmf", period=20)
    cur, prev = c.last(v), c.last(v, 1)
    if None in (cur, prev) or not (prev < 0 and cur >= 0):
        return FLAT
    return _s("long", 0.55, "Chaikin money flow crossed above zero", tags=["volume"])


@strategy("force_index_turn", "volume", "Force index turns positive in an uptrend")
def force_index_turn(c: Ctx):
    f = c.ind("force_index", period=13)
    e50 = c.last(c.ind("ema", period=50))
    cur, prev = c.last(f), c.last(f, 1)
    if None in (cur, prev) or not e50 or c.price < e50:
        return FLAT
    if not (prev < 0 and cur >= 0):
        return FLAT
    return _s("long", 0.55, "force index turned positive above the 50 EMA", tags=["volume"])


@strategy("volume_dryup_pullback", "volume", "Pullback on drying volume in an uptrend")
def volume_dryup_pullback(c: Ctx):
    rv = c.ind("relative_volume", period=20)
    e21, e50 = c.last(c.ind("ema", period=21)), c.last(c.ind("ema", period=50))
    v = c.last(rv)
    if None in (v, e21, e50) or e21 < e50 or c.price < e50:
        return FLAT
    if v > 0.7:
        return FLAT
    atr = c.atr
    if not atr or abs(c.price - e21) / atr > 1.0:
        return FLAT
    return _s("long", 0.6, f"pullback to the 21 EMA on {v:.1f}x volume — sellers are not pressing",
              stop=e50, tags=["volume", "pullback"])


@strategy("absorption_bar", "volume", "Huge volume, small body, closing off the low")
def absorption_bar(c: Ctx):
    rv, atr = c.last(c.ind("relative_volume", period=20)), c.atr
    if not rv or rv < 3.0 or not atr:
        return FLAT
    rng = c.high[-1] - c.low[-1]
    if rng <= 0 or rng / atr < 1.2:
        return FLAT
    body = abs(c.close[-1] - c.open[-1]) / rng
    close_pos = (c.close[-1] - c.low[-1]) / rng
    if body > 0.35 or close_pos < 0.6:
        return FLAT
    return _s("long", 0.65, f"{rv:.1f}x volume with a small body closing near the high — sellers absorbed",
              stop=c.low[-1], tags=["volume", "absorption"])


@strategy("mfi_divergence", "volume", "Money flow rising while price makes a lower low")
def mfi_divergence(c: Ctx):
    from engine import indicators as ind2
    m = c.ind("mfi", period=14)
    sh, sl = ind2.swing_points(c.high, c.low, 3)
    if not m or len(sl) < 2:
        return FLAT
    i1, i2 = sl[-2], sl[-1]
    if m[i1] is None or m[i2] is None:
        return FLAT
    if not (c.low[i2] < c.low[i1] and m[i2] > m[i1]):
        return FLAT
    return _s("long", 0.6, "money flow higher on a lower price low", stop=c.low[i2],
              tags=["volume", "divergence"])


# =============================================================================
# Structure and liquidity
# =============================================================================

@strategy("sweep_reclaim", "structure", "Wicked below a swing pool and closed back above it")
def sweep_reclaim(c: Ctx):
    if c.n < 40:
        return FLAT
    pool = min(c.low[-31:-1])
    atr = c.atr
    if not atr:
        return FLAT
    if not (c.low[-1] < pool - 0.05 * atr and c.close[-1] > pool):
        return FLAT
    rv = c.last(c.ind("relative_volume", period=20))
    return _s("long", 0.8 if (rv and rv > 1.3) else 0.65,
              "swept the 30-bar low and closed back above it — the forced sellers were absorbed",
              stop=c.low[-1] - 0.2 * atr, tags=["structure", "liquidity"])


@strategy("equal_lows_sweep", "structure", "Sweep of clustered equal lows")
def equal_lows_sweep(c: Ctx):
    from engine import indicators as ind2
    sh, sl = ind2.swing_points(c.high, c.low, 3)
    atr = c.atr
    if len(sl) < 2 or not atr:
        return FLAT
    pools = ind2.equal_levels([c.low[i] for i in sl[-8:]], 0.15 * atr)
    if not pools:
        return FLAT
    pool = max(pools)
    if not (c.low[-1] < pool - 0.05 * atr and c.close[-1] > pool):
        return FLAT
    return _s("long", 0.8, "swept a cluster of equal lows and reclaimed it — a stop pool, taken",
              stop=c.low[-1] - 0.2 * atr, tags=["structure", "liquidity"])


@strategy("break_of_structure", "structure", "Close above the last swing high")
def break_of_structure(c: Ctx):
    from engine import indicators as ind2
    sh, sl = ind2.swing_points(c.high, c.low, 3)
    if not sh:
        return FLAT
    level = c.high[sh[-1]]
    if c.close[-1] <= level or c.close[-2] > level:
        return FLAT
    return _s("long", 0.7, "first close above the last swing high", stop=c.low[sl[-1]] if sl else None,
              tags=["structure"])


@strategy("order_block_retest", "structure", "Return to the last down bar before an impulsive rally")
def order_block_retest(c: Ctx):
    atr = c.atr
    if not atr or c.n < 40:
        return FLAT
    for j in range(c.n - 30, c.n - 3):
        move = c.close[j + 2] - c.open[j]
        if move / atr < 2.0:
            continue
        if c.close[j] >= c.open[j]:
            continue
        top, bot = max(c.open[j], c.close[j]), min(c.open[j], c.close[j])
        if c.low[-1] <= top and c.close[-1] > bot and c.price > bot:
            return _s("long", 0.65, "retested the last down bar before an impulsive rally",
                      stop=bot - 0.3 * atr, tags=["structure", "order-block"])
    return FLAT


@strategy("fair_value_gap_fill", "structure", "Price fills back into a bullish three-bar gap")
def fair_value_gap_fill(c: Ctx):
    atr = c.atr
    if not atr or c.n < 20:
        return FLAT
    for j in range(c.n - 20, c.n - 2):
        gap_lo, gap_hi = c.high[j], c.low[j + 2]
        if gap_hi <= gap_lo or (gap_hi - gap_lo) / atr < 0.4:
            continue
        mid = (gap_hi + gap_lo) / 2
        if c.low[-1] <= gap_hi and c.close[-1] > mid:
            return _s("long", 0.6, "filled into a bullish fair-value gap and held its midpoint",
                      stop=gap_lo, tags=["structure", "fvg"])
    return FLAT


@strategy("double_bottom", "structure", "Two lows at the same level, then a neckline break")
def double_bottom(c: Ctx):
    from engine import indicators as ind2
    sh, sl = ind2.swing_points(c.high, c.low, 3)
    atr = c.atr
    if len(sl) < 2 or not sh or not atr:
        return FLAT
    a, b = c.low[sl[-2]], c.low[sl[-1]]
    if abs(a - b) / atr > 0.4:
        return FLAT
    neck = max(c.high[i] for i in sh if sl[-2] < i < sl[-1]) if any(sl[-2] < i < sl[-1] for i in sh) else None
    if neck is None or c.close[-1] <= neck:
        return FLAT
    return _s("long", 0.7, "double bottom with the neckline broken", stop=min(a, b), tags=["structure"])


@strategy("round_number_reclaim", "structure", "Reclaim of a round number after a sweep")
def round_number_reclaim(c: Ctx):
    import math as _m
    p, atr = c.price, c.atr
    if not atr or p <= 0:
        return FLAT
    mag = 10 ** _m.floor(_m.log10(p))
    level = round(p / (mag / 2)) * (mag / 2)
    if not level or abs(p - level) / atr > 0.5:
        return FLAT
    if not (c.low[-1] < level and c.close[-1] > level):
        return FLAT
    return _s("long", 0.55, f"wicked under {level:.6g} and closed back above it",
              stop=c.low[-1], tags=["structure"])


@strategy("trend_line_bounce", "structure", "Bounce off a rising regression channel's lower band")
def trend_line_bounce(c: Ctx):
    r = c.ind("linreg_channel", period=60)
    if not r or r["slope"] <= 0 or r["stdev"] <= 0:
        return FLAT
    lower = r["value_now"] - 2 * r["stdev"]
    if c.low[-1] > lower or c.close[-1] < lower:
        return FLAT
    return _s("long", 0.6, "tagged the lower edge of a rising regression channel and closed back inside",
              stop=lower - r["stdev"] * 0.5, tags=["structure", "mean-reversion"])


# =============================================================================
# Composite
# =============================================================================

@strategy("triple_confluence", "composite", "Trend, momentum and volume all agree")
def triple_confluence(c: Ctx):
    e21, e50, e200 = c.last(c.ind("ema", period=21)), c.last(c.ind("ema", period=50)), c.last(c.ind("ema", period=200))
    r = c.last(c.ind("rsi", period=14))
    rv = c.last(c.ind("relative_volume", period=20))
    if None in (e21, e50, e200, r, rv):
        return FLAT
    if not (e21 > e50 > e200 and c.price > e200 and 45 <= r <= 70 and rv >= 1.2):
        return FLAT
    return _s("long", 0.8, "EMA stack, RSI in the trend band and volume above average all line up",
              stop=e50, tags=["composite"])


@strategy("htf_aligned_pullback", "composite", "Bias timeframe up and the setup timeframe pulling back")
def htf_aligned_pullback(c: Ctx):
    agree = c.htf_uptrend()
    if agree is not True:
        return FLAT
    e21, atr = c.last(c.ind("ema", period=21)), c.atr
    if not e21 or not atr or abs(c.price - e21) / atr > 0.8:
        return FLAT
    return _s("long", 0.8, "higher timeframe is up and this one is resting on the 21 EMA",
              stop=e21 - 1.5 * atr, tags=["composite", "multi-timeframe"])


@strategy("momentum_plus_structure", "composite", "Break of structure with MACD agreeing")
def momentum_plus_structure(c: Ctx):
    from engine import indicators as ind2
    res = c.ind("macd")
    sh, sl = ind2.swing_points(c.high, c.low, 3)
    if not res or not sh:
        return FLAT
    line, sig, hist = res
    h = c.last(hist)
    level = c.high[sh[-1]]
    if h is None or h <= 0 or c.close[-1] <= level:
        return FLAT
    return _s("long", 0.75, "broke the last swing high with the MACD histogram positive",
              stop=c.low[sl[-1]] if sl else None, tags=["composite", "structure"])


@strategy("quiet_then_volume", "composite", "A quiet coil broken by a volume bar")
def quiet_then_volume(c: Ctx):
    rv = c.ind("relative_volume", period=20)
    now = c.last(rv)
    before = [v for v in rv[-8:-1] if v is not None]
    if now is None or not before or now < 2.0:
        return FLAT
    if sum(before) / len(before) > 0.9:
        return FLAT
    if c.close[-1] <= c.open[-1]:
        return FLAT
    return _s("long", 0.7, f"a quiet stretch broken by a {now:.1f}x volume up bar",
              stop=min(c.low[-8:]), tags=["composite", "volume"])


# =============================================================================
# Controls
# =============================================================================
# These exist to be beaten. Long-only strategies all look brilliant in a bull
# market, so a ranking without a control tells you about the period rather than
# about the strategies. Any strategy that cannot beat an entry with no thought
# behind it is not adding anything, and the grid shows them side by side.

@strategy("_control_random_entry", "control",
          "Buys every 12th bar with no filter at all. The bar every strategy must clear.")
def _control_random_entry(c: Ctx):
    if c.n % 12 != 0:
        return FLAT
    return _s("long", 0.5, "no analysis whatsoever — this is the control", tags=["control"])


@strategy("_control_always_long", "control",
          "Buys whenever flat. Approximates buy-and-hold under the same risk model.")
def _control_always_long(c: Ctx):
    return _s("long", 0.5, "always long — the buy-and-hold control", tags=["control"])
