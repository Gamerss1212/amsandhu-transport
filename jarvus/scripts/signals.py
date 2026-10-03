#!/usr/bin/env python3
"""Every candle pattern, chart pattern and indicator signal Jarvus/Ultron knows, as code (numpy).

Shared by tools/measure_signals.py (the measurement), the Ultron trainer and the Ultron app, so the signals
traded live are exactly the signals that were measured. Decisions use completed bars only.
  vector_signals(t, o, h, l, c, v, bars_day) -> ({id: bool array}, ATR, RSI14)
  loop_signals(t, o, h, l, c, ATR, RSI14, bars_day) -> {id: bool array}   (swing patterns, gaps, levels)
  all_signals(t, o, h, l, c, v, bars_day) -> {id: bool array}
  to4h(t, o, h, l, c, v, gate) -> completed 4h bars built from 1h bars
"""

from __future__ import annotations

import math

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view as swv

HOUR = 3_600_000

# id: (name, side, family, exact rule as tested). side: bull = a buy idea, bear = a sell/avoid idea, neutral.
DEFS = {
    # ---------------- single candles
    "hammer": ("Hammer", "bull", "candle", "after a 5-bar drop; lower wick >= 2x body; upper wick <= 10% of range; body >= 5% of range; range >= 0.5 ATR"),
    "inverted_hammer": ("Inverted hammer", "bull", "candle", "after a 5-bar drop; upper wick >= 2x body; lower wick <= 10% of range; range >= 0.5 ATR"),
    "hanging_man": ("Hanging man", "bear", "candle", "hammer shape after a 5-bar rise"),
    "shooting_star": ("Shooting star", "bear", "candle", "inverted-hammer shape after a 5-bar rise"),
    "dragonfly_doji": ("Dragonfly doji", "bull", "candle", "after a 5-bar drop; body <= 5% of range; upper wick <= 10%; range >= 0.5 ATR"),
    "gravestone_doji": ("Gravestone doji", "bear", "candle", "after a 5-bar rise; body <= 5% of range; lower wick <= 10%; range >= 0.5 ATR"),
    "doji_after_drop": ("Doji after a drop", "bull", "candle", "after a 5-bar drop; body <= 10% of range; range >= 0.5 ATR"),
    "doji_after_rise": ("Doji after a rise", "bear", "candle", "after a 5-bar rise; body <= 10% of range; range >= 0.5 ATR"),
    "long_legged_doji": ("Long-legged doji", "neutral", "candle", "body <= 10% of range, both wicks >= 35%, range >= 1 ATR"),
    "spinning_top": ("Spinning top", "neutral", "candle", "body 10-30% of range, both wicks >= the body"),
    "bull_marubozu": ("Bullish marubozu", "bull", "candle", "green, body >= 90% of range, range >= 1 ATR"),
    "bear_marubozu": ("Bearish marubozu", "bear", "candle", "red, body >= 90% of range, range >= 1 ATR"),
    "bull_belt_hold": ("Bullish belt hold", "bull", "candle", "after a 5-bar drop; green, opens at the low (<= 5% of range), body >= 60%, range >= 1 ATR"),
    "big_bull_bar": ("Big green candle (momentum ignition)", "bull", "candle", "green, range >= 2x the prior ATR, body >= 60% of range"),
    "big_bear_bar": ("Big red candle (capitulation bar)", "bear", "candle", "red, range >= 2x the prior ATR, body >= 60% of range"),
    # ---------------- two candles
    "bull_engulfing": ("Bullish engulfing", "bull", "candle", "after a 5-bar drop; red then green whose body covers the red body"),
    "bear_engulfing": ("Bearish engulfing", "bear", "candle", "after a 5-bar rise; green then red whose body covers the green body"),
    "bull_harami": ("Bullish harami", "bull", "candle", "after a drop; big red (body >= 0.75 ATR, >= 60% of range) then a green body inside it, <= half its size"),
    "bear_harami": ("Bearish harami", "bear", "candle", "after a rise; big green then a red body inside it, <= half its size"),
    "bull_harami_cross": ("Bullish harami cross", "bull", "candle", "bullish harami whose second candle is a doji"),
    "piercing_line": ("Piercing line", "bull", "candle", "after a drop; big red, then green opening at/below its close and closing above its midpoint (not above its open)"),
    "dark_cloud_cover": ("Dark cloud cover", "bear", "candle", "after a rise; big green, then red opening at/above its close and closing below its midpoint"),
    "tweezer_bottom": ("Tweezer bottom", "bull", "candle", "after a drop; red then green with lows within 0.05 ATR"),
    "tweezer_top": ("Tweezer top", "bear", "candle", "after a rise; green then red with highs within 0.05 ATR"),
    "bull_kicker": ("Bullish kicker", "bull", "candle", "strong red, then strong green opening above the red's open (a gap; rare in 24/7 crypto)"),
    "outside_bar_up": ("Outside bar, up close", "bull", "candle", "range covers the prior bar and closes above the prior high"),
    "outside_bar_down": ("Outside bar, down close", "bear", "candle", "range covers the prior bar and closes below the prior low"),
    "inside_bar": ("Inside bar", "neutral", "candle", "high below and low above the prior bar's"),
    "inside_bar_break_up": ("Inside bar breakout up", "bull", "candle", "an inside bar, then a close above the mother bar's high"),
    "inside_bar_break_down": ("Inside bar breakdown", "bear", "candle", "an inside bar, then a close below the mother bar's low"),
    "nr7_break_up": ("NR7 breakout up", "bull", "candle", "prior bar has the narrowest range of 7, then a close above its high"),
    # ---------------- three+ candles
    "morning_star": ("Morning star", "bull", "candle", "after a drop; big red, small body (<= 30% of it), green closing above the red's midpoint"),
    "evening_star": ("Evening star", "bear", "candle", "after a rise; big green, small body, red closing below the green's midpoint"),
    "morning_doji_star": ("Morning doji star", "bull", "candle", "morning star whose middle candle is a doji"),
    "evening_doji_star": ("Evening doji star", "bear", "candle", "evening star whose middle candle is a doji"),
    "three_white_soldiers": ("Three white soldiers", "bull", "candle", "3 green, higher closes, each opening inside the prior body, bodies >= 60% of range and >= 0.5 ATR, small upper wicks"),
    "three_black_crows": ("Three black crows", "bear", "candle", "3 red, lower closes, each opening inside the prior body, bodies >= 60% of range and >= 0.5 ATR"),
    "three_inside_up": ("Three inside up", "bull", "candle", "bullish harami, then a close above the first candle's open"),
    "three_inside_down": ("Three inside down", "bear", "candle", "bearish harami, then a close below the first candle's open"),
    "three_outside_up": ("Three outside up", "bull", "candle", "bullish engulfing, then a higher close"),
    "three_outside_down": ("Three outside down", "bear", "candle", "bearish engulfing, then a lower close"),
    "bull_three_line_strike": ("Bullish three-line strike", "bull", "candle", "three black crows, then one green candle opening at/below the last close and closing above the first open"),
    "bear_three_line_strike": ("Bearish three-line strike", "bear", "candle", "three white soldiers, then one red candle closing below the first open"),
    "rising_three": ("Rising three methods", "bull", "candle", "big green, 3 small candles inside its range, then a green close above it"),
    "falling_three": ("Falling three methods", "bear", "candle", "big red, 3 small candles inside its range, then a red close below it"),
    # ---------------- chart patterns and price structure
    "double_bottom": ("Double bottom (neckline break)", "bull", "chart", "two swing lows 10-80 bars apart within 0.5 ATR, neckline >= 1.5 ATR above; close breaks the neckline within 30 bars"),
    "double_top": ("Double top (neckline break)", "bear", "chart", "two swing highs within 0.5 ATR; close breaks below the neckline"),
    "inverse_hs": ("Inverse head and shoulders", "bull", "chart", "3 swing lows, middle >= 1 ATR lowest, shoulders within 1 ATR; close breaks the neckline"),
    "hs_top": ("Head and shoulders top", "bear", "chart", "3 swing highs, middle >= 1 ATR highest, shoulders within 1 ATR; close breaks below the neckline"),
    "bos_up": ("Break of structure up (trend continuation)", "bull", "chart", "higher highs and higher lows, then a close above the last swing high"),
    "choch_up": ("Change of character up (CHoCH)", "bull", "chart", "lower highs and lower lows, then a close above the last swing high"),
    "choch_down": ("Change of character down", "bear", "chart", "higher highs and higher lows, then a close below the last swing low"),
    "asc_triangle": ("Ascending triangle breakout", "bull", "chart", "two swing highs within 0.3 ATR, rising swing lows; close above the flat top"),
    "desc_triangle": ("Descending triangle breakdown", "bear", "chart", "two swing lows within 0.3 ATR, falling swing highs; close below the flat bottom"),
    "sym_triangle_up": ("Symmetrical triangle breakout up", "bull", "chart", "falling swing highs and rising swing lows; close above the upper trendline"),
    "falling_wedge": ("Falling wedge breakout", "bull", "chart", "highs and lows both falling, highs faster; close above the upper trendline"),
    "rising_wedge": ("Rising wedge breakdown", "bear", "chart", "highs and lows both rising, lows faster; close below the lower trendline"),
    "bull_flag": ("Bull flag breakout", "bull", "chart", "a >= 3 ATR rise in <= 8 bars, a 4-15 bar pause holding the top half, then a close above the pause"),
    "bear_flag": ("Bear flag breakdown", "bear", "chart", "a >= 3 ATR drop in <= 8 bars, a 4-15 bar pause, then a close below it"),
    "fvg_retest": ("Fair value gap retest (bullish FVG)", "bull", "chart", "3-bar gap (low > high 2 bars back, >= 0.1 ATR); first return into it within 30 bars that closes above its bottom"),
    "ob_retest": ("Order block retest (bullish)", "bull", "chart", "last red candle before a close above the 20-bar high; first return into it within 40 bars that closes above its low"),
    "pdl_sweep": ("Prior-day low sweep and reclaim", "bull", "chart", "trades below yesterday's low (UTC) and closes back above it, first time that day"),
    "pdh_break": ("Prior-day high breakout", "bull", "chart", "first close above yesterday's high that day"),
    "pdh_reject": ("Prior-day high sweep and rejection", "bear", "chart", "trades above yesterday's high and closes back below it"),
    "fib_618": ("Fibonacci 61.8% retracement bounce", "bull", "chart", "after a >= 4 ATR swing up (40 bars), the first touch of the 61.8% retracement that closes above it"),
    "pivot_s1": ("Floor pivot S1 bounce", "bull", "chart", "touches today's S1 (from yesterday's H/L/C) and closes above it, first time that day"),
    "pivot_r1_reject": ("Floor pivot R1 rejection", "bear", "chart", "trades above R1 and closes back below it"),
    "rsi_bull_div": ("RSI bullish divergence", "bull", "chart", "close below the lowest close of bars 5-20 back while RSI(14) is >= 3 higher than at that low (which was < 35)"),
    "rsi_bear_div": ("RSI bearish divergence", "bear", "chart", "close above the highest close of bars 5-20 back while RSI(14) is >= 3 lower than at that high (which was > 65)"),
    # ---------------- indicators
    "rsi_os_30": ("RSI(14) drops below 30 (oversold)", "bull", "indicator", "RSI(14) crosses below 30"),
    "rsi_up_30": ("RSI(14) back above 30", "bull", "indicator", "RSI(14) crosses back above 30"),
    "rsi_ob_70": ("RSI(14) rises above 70 (overbought)", "bear", "indicator", "RSI(14) crosses above 70"),
    "rsi_dn_70": ("RSI(14) back below 70", "bear", "indicator", "RSI(14) crosses back below 70"),
    "rsi2_10": ("RSI(2) below 10", "bull", "indicator", "RSI(2) crosses below 10"),
    "rsi2_connors": ("RSI(2) below 10 above the 200 SMA (Connors)", "bull", "indicator", "RSI(2) crosses below 10 while close > SMA(200)"),
    "macd_up": ("MACD crosses above signal", "bull", "indicator", "MACD(12,26,9) line crosses above its signal line"),
    "macd_up_below0": ("MACD bullish cross below zero", "bull", "indicator", "MACD crosses above signal while both are below zero"),
    "macd_zero_up": ("MACD crosses above zero", "bull", "indicator", "MACD line crosses above 0"),
    "macd_down": ("MACD crosses below signal", "bear", "indicator", "MACD line crosses below its signal line"),
    "macd_hist_turn": ("MACD histogram turns up", "bull", "indicator", "histogram below 0 and rising after falling"),
    "ema_9_21_up": ("EMA 9/21 bullish cross", "bull", "indicator", "EMA(9) crosses above EMA(21)"),
    "ema_9_21_down": ("EMA 9/21 bearish cross", "bear", "indicator", "EMA(9) crosses below EMA(21)"),
    "golden_cross": ("Golden cross (50/200)", "bull", "indicator", "SMA(50) crosses above SMA(200)"),
    "death_cross": ("Death cross (50/200)", "bear", "indicator", "SMA(50) crosses below SMA(200)"),
    "ema200_reclaim": ("Close back above the 200 EMA", "bull", "indicator", "close crosses above EMA(200)"),
    "ema200_lose": ("Close below the 200 EMA", "bear", "indicator", "close crosses below EMA(200)"),
    "bb_below": ("Close below the lower Bollinger band", "bull", "indicator", "close crosses below BB(20,2) lower band"),
    "bb_reentry": ("Back inside the Bollinger band from below", "bull", "indicator", "close back above the lower band after closing below it"),
    "bb_above": ("Close above the upper Bollinger band", "bull", "indicator", "close crosses above BB(20,2) upper band (breakout reading)"),
    "bb_squeeze_up": ("Bollinger squeeze breakout", "bull", "indicator", "band width within 10% of its 120-bar low, then a close above the upper band"),
    "keltner_up": ("Keltner channel breakout", "bull", "indicator", "close crosses above EMA(20) + 2 ATR"),
    "keltner_below": ("Below the lower Keltner channel", "bull", "indicator", "close crosses below EMA(20) - 2 ATR (stretch)"),
    "ttm_squeeze": ("TTM squeeze fires up", "bull", "indicator", "Bollinger bands were inside the Keltner channel and come out, close above EMA(20)"),
    "stoch_up": ("Stochastic bullish cross below 20", "bull", "indicator", "slow %K(14,3) crosses above %D(3) from below 20"),
    "stoch_down": ("Stochastic bearish cross above 80", "bear", "indicator", "%K crosses below %D from above 80"),
    "stochrsi_up": ("Stochastic RSI bullish cross below 0.2", "bull", "indicator", "StochRSI(14) K crosses above D below 0.2"),
    "willr_up": ("Williams %R leaves oversold", "bull", "indicator", "%R(14) crosses above -80"),
    "cci_up": ("CCI back above -100", "bull", "indicator", "CCI(20) crosses above -100"),
    "cci_break": ("CCI above +100 (momentum)", "bull", "indicator", "CCI(20) crosses above +100"),
    "mfi_os": ("MFI below 20", "bull", "indicator", "MFI(14) crosses below 20"),
    "mfi_ob": ("MFI above 80", "bear", "indicator", "MFI(14) crosses above 80"),
    "adx_di_up": ("ADX/DMI bullish cross", "bull", "indicator", "+DI crosses above -DI while ADX(14) > 20"),
    "holy_grail": ("ADX Holy Grail pullback (Raschke)", "bull", "indicator", "ADX > 30, +DI > -DI, low touches EMA(20) and closes above it"),
    "psar_up": ("Parabolic SAR flips up", "bull", "indicator", "SAR(0.02, 0.2) flips below price"),
    "psar_down": ("Parabolic SAR flips down", "bear", "indicator", "SAR flips above price"),
    "supertrend_up": ("Supertrend flips up", "bull", "indicator", "Supertrend(10,3) turns up"),
    "supertrend_down": ("Supertrend flips down", "bear", "indicator", "Supertrend(10,3) turns down"),
    "ichi_tk_up": ("Ichimoku TK cross above the cloud", "bull", "indicator", "Tenkan(9) crosses above Kijun(26) with close above the cloud"),
    "ichi_cloud_up": ("Ichimoku cloud breakout", "bull", "indicator", "close crosses above the cloud (spans shifted 26)"),
    "ichi_cloud_down": ("Ichimoku cloud breakdown", "bear", "indicator", "close crosses below the cloud"),
    "aroon_up": ("Aroon bullish cross", "bull", "indicator", "Aroon up(25) crosses above Aroon down while >= 70"),
    "donchian20": ("Donchian 20 breakout", "bull", "indicator", "close above the prior 20-bar high"),
    "donchian55": ("Donchian 55 breakout (turtle)", "bull", "indicator", "close above the prior 55-bar high"),
    "donchian20_down": ("Donchian 20 breakdown", "bear", "indicator", "close below the prior 20-bar low"),
    "obv_lead": ("OBV new high before price", "bull", "indicator", "OBV at a 20-bar high while the close is not"),
    "obv_confirm": ("Breakout confirmed by OBV", "bull", "indicator", "close and OBV both at new 20-bar highs"),
    "vol_spike_bull": ("Volume spike on a green candle", "bull", "indicator", "volume >= 3x its 20-bar average, green body >= 50% of range"),
    "vol_spike_bear": ("Volume spike on a red candle", "bear", "indicator", "volume >= 3x average, red body >= 50% of range"),
    "vwap_reclaim": ("Reclaim of the 24h VWAP", "bull", "indicator", "close crosses above the rolling 24h VWAP"),
    "vwap_lose": ("Loss of the 24h VWAP", "bear", "indicator", "close crosses below the rolling 24h VWAP"),
    "ha_green": ("Heikin-Ashi turns green", "bull", "indicator", "first green Heikin-Ashi candle after 3 red"),
    "ha_red": ("Heikin-Ashi turns red", "bear", "indicator", "first red Heikin-Ashi candle after 3 green"),
    "rally_24h": ("Big 24h rally (momentum)", "bull", "indicator", "24h return crosses above 2.5x its average absolute 24h move (30 days)"),
    "drop_24h": ("Big 24h drop (dip)", "bear", "indicator", "24h return crosses below -2.5x its average absolute 24h move"),
    "five_green": ("Five green candles in a row", "bull", "indicator", "5 consecutive green closes"),
    "five_red": ("Five red candles in a row", "bear", "indicator", "5 consecutive red closes"),
    "stretch_ema20": ("Stretched 2.5 ATR below the 20 EMA", "bull", "indicator", "close crosses below EMA(20) - 2.5 ATR"),
    "zscore_m2": ("Z-score below -2 (50 bars)", "bull", "indicator", "(close - SMA50) / stdev50 crosses below -2"),
    # ---------------- Jarvus's own playbooks (1h only)
    "p1_trend_pullback": ("P1 trend pullback (Jarvus)", "bull", "playbook", "scripts/ladder.py s_trend_pullback"),
    "p3_breakout_retest": ("P3 breakout retest (Jarvus)", "bull", "playbook", "scripts/ladder.py s_breakout_retest"),
    "p4_sweep_reclaim": ("P4 sweep reclaim (Jarvus)", "bull", "playbook", "scripts/ladder.py s_sweep_reclaim"),
    "p6_orb": ("P6 opening range breakout (Jarvus)", "bull", "playbook", "scripts/ladder.py s_orb"),
    "p_rsi2": ("RSI(2) dip (Jarvus)", "bull", "playbook", "scripts/ladder.py s_rsi2"),
}
PLAYBOOK = {"p1_trend_pullback": "trend_pullback", "p3_breakout_retest": "breakout_retest",
            "p4_sweep_reclaim": "sweep_reclaim", "p6_orb": "orb", "p_rsi2": "rsi2"}




# ------------------------------------------------------------------ helpers
def P(a, k=1):
    """a, k bars ago (NaN / False padded)."""
    if a.dtype == bool:
        out = np.zeros(len(a), bool)
    else:
        out = np.full(len(a), np.nan)
    if k < len(a):
        out[k:] = a[:-k] if k else a
    return out


def roll(a, n, fn):
    out = np.full(len(a), np.nan)
    if len(a) < n:
        return out
    if n > 256 and fn in (np.sum, np.mean, np.nanmean):                  # long windows (5m-30m charts): O(n) memory
        cum = lambda x: np.concatenate([[0.0], np.cumsum(x)])                # noqa: E731
        nan = np.isnan(a)
        s = cum(np.where(nan, 0.0, a))
        s = s[n:] - s[:-n]
        k = cum(~nan)
        k = k[n:] - k[:-n]                                               # valid values in each window
        if fn is np.nanmean:
            out[n - 1:] = np.where(k > 0, s / np.maximum(k, 1), np.nan)
        else:
            out[n - 1:] = np.where(k == n, s if fn is np.sum else s / n, np.nan)
        return out
    out[n - 1:] = fn(swv(a, n), axis=1)
    return out


def ema(a, n):
    out, e, k, cnt = np.full(len(a), np.nan), None, 2 / (n + 1), 0
    for i, x in enumerate(a):
        if x != x:
            continue
        e = x if e is None else e + k * (x - e)
        cnt += 1
        if cnt >= n:
            out[i] = e
    return out


def wilder(x, n):
    out, s = np.full(len(x), np.nan), None
    for i in range(len(x)):
        if x[i] != x[i]:
            continue
        s = x[i] if s is None else (s * (n - 1) + x[i]) / n
        out[i] = s
    return out


def rsi(c, n):
    d = np.diff(c, prepend=c[0])
    g, lo = np.where(d > 0, d, 0.0), np.where(d < 0, -d, 0.0)
    ag, al = wilder(g, n), wilder(lo, n)
    with np.errstate(divide="ignore", invalid="ignore"):
        r = 100 - 100 / (1 + ag / al)
    r[al == 0] = 100.0
    r[:n] = np.nan
    return r


def atr(h, l, c, n=14):
    pc = P(c)
    tr = np.fmax(h - l, np.fmax(np.abs(h - pc), np.abs(l - pc)))
    a = wilder(tr, n)
    a[:n - 1] = np.nan
    return a


def cross_up(a, b):
    return (a > b) & (P(a) <= P(b))


def cross_dn(a, b):
    return (a < b) & (P(a) >= P(b))


def first_in_run(m):
    return m & ~P(m)


# ------------------------------------------------------------------ signals
def vector_signals(t, o, h, l, c, v, bars_day):
    n = len(c)
    S = {}
    A = atr(h, l, c)
    A1 = P(A)
    body, rng = np.abs(c - o), h - l
    upw, low = h - np.maximum(o, c), np.minimum(o, c) - l
    bull, bear = c > o, c < o
    with np.errstate(invalid="ignore"):
        dn = lambda k: P(c, k + 1) < P(c, k + 6)       # noqa: E731  5-bar drop before the pattern's first bar
        up = lambda k: P(c, k + 1) > P(c, k + 6)       # noqa: E731
        big = rng >= 0.5 * A
        ham = (low >= 2 * body) & (upw <= 0.1 * rng) & (body >= 0.05 * rng) & big
        inv = (upw >= 2 * body) & (low <= 0.1 * rng) & (body >= 0.05 * rng) & big
        S["hammer"] = dn(0) & ham
        S["inverted_hammer"] = dn(0) & inv
        S["hanging_man"] = up(0) & ham
        S["shooting_star"] = up(0) & inv
        S["dragonfly_doji"] = dn(0) & (body <= 0.05 * rng) & (upw <= 0.1 * rng) & big
        S["gravestone_doji"] = up(0) & (body <= 0.05 * rng) & (low <= 0.1 * rng) & big
        doji = (body <= 0.1 * rng) & big
        S["doji_after_drop"] = dn(0) & doji
        S["doji_after_rise"] = up(0) & doji
        S["long_legged_doji"] = (body <= 0.1 * rng) & (upw >= 0.35 * rng) & (low >= 0.35 * rng) & (rng >= A)
        S["spinning_top"] = (body <= 0.3 * rng) & (body >= 0.1 * rng) & (upw >= body) & (low >= body)
        S["bull_marubozu"] = bull & (body >= 0.9 * rng) & (rng >= A)
        S["bear_marubozu"] = bear & (body >= 0.9 * rng) & (rng >= A)
        S["bull_belt_hold"] = dn(0) & bull & (o - l <= 0.05 * rng) & (body >= 0.6 * rng) & (rng >= A)
        S["big_bull_bar"] = bull & (rng >= 2 * A1) & (body >= 0.6 * rng)
        S["big_bear_bar"] = bear & (rng >= 2 * A1) & (body >= 0.6 * rng)

        o1, h1, l1, c1 = P(o), P(h), P(l), P(c)
        o2, h2, l2, c2 = P(o, 2), P(h, 2), P(l, 2), P(c, 2)
        o3, c3 = P(o, 3), P(c, 3)
        b1, r1, b2, r2 = P(body), P(rng), P(body, 2), P(rng, 2)
        bull1, bear1, bull2, bear2 = P(bull), P(bear), P(bull, 2), P(bear, 2)
        A2 = P(A, 2)
        eng_up = bear1 & bull & (c >= o1) & (o <= c1) & (body > b1)
        eng_dn = bull1 & bear & (c <= o1) & (o >= c1) & (body > b1)
        S["bull_engulfing"] = dn(1) & eng_up
        S["bear_engulfing"] = up(1) & eng_dn
        bigred1 = bear1 & (b1 >= 0.6 * r1) & (b1 >= 0.75 * A1)
        biggrn1 = bull1 & (b1 >= 0.6 * r1) & (b1 >= 0.75 * A1)
        har_up = bigred1 & (np.maximum(o, c) <= o1) & (np.minimum(o, c) >= c1) & (body <= 0.5 * b1)
        har_dn = biggrn1 & (np.maximum(o, c) <= c1) & (np.minimum(o, c) >= o1) & (body <= 0.5 * b1)
        S["bull_harami"] = dn(1) & har_up & bull
        S["bear_harami"] = up(1) & har_dn & bear
        S["bull_harami_cross"] = dn(1) & har_up & (body <= 0.1 * rng)
        S["piercing_line"] = dn(1) & bigred1 & bull & (o <= c1) & (c > (o1 + c1) / 2) & (c < o1)
        S["dark_cloud_cover"] = up(1) & biggrn1 & bear & (o >= c1) & (c < (o1 + c1) / 2) & (c > o1)
        S["tweezer_bottom"] = dn(1) & bear1 & bull & (np.abs(l - l1) <= 0.05 * A) & (r1 >= 0.5 * A1)
        S["tweezer_top"] = up(1) & bull1 & bear & (np.abs(h - h1) <= 0.05 * A) & (r1 >= 0.5 * A1)
        S["bull_kicker"] = bear1 & (b1 >= 0.6 * r1) & bull & (o > o1) & (body >= 0.6 * rng)
        S["outside_bar_up"] = (h > h1) & (l < l1) & (c > h1)
        S["outside_bar_down"] = (h > h1) & (l < l1) & (c < l1)
        ins = (h < h1) & (l > l1)
        ins1 = P(ins)
        S["inside_bar"] = ins
        S["inside_bar_break_up"] = ins1 & (c > h2)
        S["inside_bar_break_down"] = ins1 & (c < l2)
        nr7 = rng <= roll(rng, 7, np.min)
        S["nr7_break_up"] = P(nr7) & (c > h1)

        bigred2 = bear2 & (b2 >= 0.6 * r2) & (b2 >= 0.75 * A2)
        biggrn2 = bull2 & (b2 >= 0.6 * r2) & (b2 >= 0.75 * A2)
        S["morning_star"] = dn(2) & bigred2 & (b1 <= 0.3 * b2) & bull & (c > (o2 + c2) / 2)
        S["evening_star"] = up(2) & biggrn2 & (b1 <= 0.3 * b2) & bear & (c < (o2 + c2) / 2)
        S["morning_doji_star"] = S["morning_star"] & (b1 <= 0.1 * r1)
        S["evening_doji_star"] = S["evening_star"] & (b1 <= 0.1 * r1)
        sold = bull & (body >= 0.6 * rng) & (body >= 0.5 * A) & (upw <= 0.3 * body)
        crow = bear & (body >= 0.6 * rng) & (body >= 0.5 * A)
        tws = sold & P(sold) & P(sold, 2) & (c > c1) & (c1 > c2) & (o >= o1) & (o <= c1) & (o1 >= o2) & (o1 <= c2)
        tbc = crow & P(crow) & P(crow, 2) & (c < c1) & (c1 < c2) & (o <= o1) & (o >= c1) & (o1 <= o2) & (o1 >= c2)
        S["three_white_soldiers"] = tws
        S["three_black_crows"] = tbc
        S["three_inside_up"] = P(S["bull_harami"]) & bull & (c > o2)
        S["three_inside_down"] = P(S["bear_harami"]) & bear & (c < o2)
        S["three_outside_up"] = P(S["bull_engulfing"]) & (c > c1)
        S["three_outside_down"] = P(S["bear_engulfing"]) & (c < c1)
        S["bull_three_line_strike"] = P(tbc) & bull & (o <= c1) & (c >= P(o, 3))
        S["bear_three_line_strike"] = P(tws) & bear & (o >= c1) & (c <= P(o, 3))
        o4, h4, l4, c4, b4, r4 = P(o, 4), P(h, 4), P(l, 4), P(c, 4), P(body, 4), P(rng, 4)
        A4 = P(A, 4)
        small3 = np.ones(n, bool)
        for k in (1, 2, 3):
            small3 &= (P(body, k) <= 0.5 * b4) & (P(h, k) <= h4) & (P(l, k) >= l4)
        S["rising_three"] = P(bull, 4) & (b4 >= A4) & (b4 >= 0.6 * r4) & small3 & bull & (c > c4)
        S["falling_three"] = P(bear, 4) & (b4 >= A4) & (b4 >= 0.6 * r4) & small3 & bear & (c < c4)

        # ---------------- indicators
        r14, r2 = rsi(c, 14), rsi(c, 2)
        S["rsi_os_30"] = cross_dn(r14, np.full(n, 30.0))
        S["rsi_up_30"] = cross_up(r14, np.full(n, 30.0))
        S["rsi_ob_70"] = cross_up(r14, np.full(n, 70.0))
        S["rsi_dn_70"] = cross_dn(r14, np.full(n, 70.0))
        sma200 = roll(c, 200, np.mean)
        S["rsi2_10"] = cross_dn(r2, np.full(n, 10.0))
        S["rsi2_connors"] = S["rsi2_10"] & (c > sma200)
        e12, e26 = ema(c, 12), ema(c, 26)
        macd = e12 - e26
        sig = ema(macd, 9)
        hist = macd - sig
        S["macd_up"] = cross_up(macd, sig)
        S["macd_up_below0"] = S["macd_up"] & (macd < 0) & (sig < 0)
        S["macd_zero_up"] = cross_up(macd, np.zeros(n))
        S["macd_down"] = cross_dn(macd, sig)
        S["macd_hist_turn"] = (hist < 0) & (hist > P(hist)) & (P(hist) <= P(hist, 2))
        e9, e20, e21, e200 = ema(c, 9), ema(c, 20), ema(c, 21), ema(c, 200)
        S["ema_9_21_up"] = cross_up(e9, e21)
        S["ema_9_21_down"] = cross_dn(e9, e21)
        sma50 = roll(c, 50, np.mean)
        S["golden_cross"] = cross_up(sma50, sma200)
        S["death_cross"] = cross_dn(sma50, sma200)
        S["ema200_reclaim"] = cross_up(c, e200)
        S["ema200_lose"] = cross_dn(c, e200)
        mid20, sd20 = roll(c, 20, np.mean), roll(c, 20, np.std)
        bu, bl = mid20 + 2 * sd20, mid20 - 2 * sd20
        S["bb_below"] = cross_dn(c, bl)
        S["bb_reentry"] = cross_up(c, bl)
        S["bb_above"] = cross_up(c, bu)
        bw = (bu - bl) / mid20
        S["bb_squeeze_up"] = (P(bw) <= 1.1 * P(roll(bw, 120, np.min))) & (c > bu)
        ku, kl = e20 + 2 * A, e20 - 2 * A
        S["keltner_up"] = cross_up(c, ku)
        S["keltner_below"] = cross_dn(c, kl)
        sq = (bu < ku) & (bl > kl)
        S["ttm_squeeze"] = P(sq) & ~sq & (c > e20)
        hh14, ll14 = roll(h, 14, np.max), roll(l, 14, np.min)
        kraw = 100 * (c - ll14) / (hh14 - ll14)
        K = roll(kraw, 3, np.mean)
        D = roll(K, 3, np.mean)
        S["stoch_up"] = cross_up(K, D) & (P(K) < 20)
        S["stoch_down"] = cross_dn(K, D) & (P(K) > 80)
        rmin, rmax = roll(r14, 14, np.min), roll(r14, 14, np.max)
        srsi = (r14 - rmin) / (rmax - rmin)
        sK = roll(srsi, 3, np.mean)
        sD = roll(sK, 3, np.mean)
        S["stochrsi_up"] = cross_up(sK, sD) & (P(sK) < 0.2)
        wr = -100 * (hh14 - c) / (hh14 - ll14)
        S["willr_up"] = cross_up(wr, np.full(n, -80.0))
        tp = (h + l + c) / 3
        w = swv(tp, 20)
        md = np.full(n, np.nan)
        md[19:] = np.abs(w - w.mean(axis=1, keepdims=True)).mean(axis=1)
        cci = (tp - roll(tp, 20, np.mean)) / (0.015 * md)
        S["cci_up"] = cross_up(cci, np.full(n, -100.0))
        S["cci_break"] = cross_up(cci, np.full(n, 100.0))
        rmf = tp * v
        ptp = P(tp)
        pos, neg = np.where(tp > ptp, rmf, 0.0), np.where(tp < ptp, rmf, 0.0)
        with np.errstate(divide="ignore"):
            mfi = 100 - 100 / (1 + roll(pos, 14, np.sum) / roll(neg, 14, np.sum))
        S["mfi_os"] = cross_dn(mfi, np.full(n, 20.0))
        S["mfi_ob"] = cross_up(mfi, np.full(n, 80.0))
        upm, dnm = h - h1, l1 - l
        pdm = np.where((upm > dnm) & (upm > 0), upm, 0.0)
        mdm = np.where((dnm > upm) & (dnm > 0), dnm, 0.0)
        pdi, mdi = 100 * wilder(pdm, 14) / A, 100 * wilder(mdm, 14) / A
        dx = 100 * np.abs(pdi - mdi) / (pdi + mdi)
        adx = wilder(np.nan_to_num(dx), 14)
        adx[:28] = np.nan
        S["adx_di_up"] = cross_up(pdi, mdi) & (adx > 20)
        S["holy_grail"] = (adx > 30) & (pdi > mdi) & (l <= e20) & (c > e20)
    sar_dir = psar(h, l)
    S["psar_up"] = (sar_dir == 1) & (P(sar_dir.astype(float)) == -1)
    S["psar_down"] = (sar_dir == -1) & (P(sar_dir.astype(float)) == 1)
    std = supertrend(h, l, c)
    S["supertrend_up"] = (std == 1) & (P(std.astype(float)) == -1)
    S["supertrend_down"] = (std == -1) & (P(std.astype(float)) == 1)
    with np.errstate(invalid="ignore"):
        mid = lambda k: (roll(h, k, np.max) + roll(l, k, np.min)) / 2   # noqa: E731
        ten, kij = mid(9), mid(26)
        ca, cb = P((ten + kij) / 2, 26), P(mid(52), 26)
        ctop, cbot = np.maximum(ca, cb), np.minimum(ca, cb)
        S["ichi_tk_up"] = cross_up(ten, kij) & (c > ctop)
        S["ichi_cloud_up"] = cross_up(c, ctop)
        S["ichi_cloud_down"] = cross_dn(c, cbot)
        au, ad = np.full(n, np.nan), np.full(n, np.nan)
        au[25:] = 100 * swv(h, 26).argmax(axis=1) / 25
        ad[25:] = 100 * swv(l, 26).argmin(axis=1) / 25
        S["aroon_up"] = cross_up(au, ad) & (au >= 70)
        S["donchian20"] = c > P(roll(h, 20, np.max))
        S["donchian20"] = first_in_run(S["donchian20"])
        S["donchian55"] = first_in_run(c > P(roll(h, 55, np.max)))
        S["donchian20_down"] = first_in_run(c < P(roll(l, 20, np.min)))
        obv = np.cumsum(np.sign(np.diff(c, prepend=c[0])) * v)
        obv_hi = obv >= P(roll(obv, 20, np.max))
        c_hi = c >= P(roll(c, 20, np.max))
        S["obv_lead"] = first_in_run(obv_hi & ~c_hi)
        S["obv_confirm"] = first_in_run(obv_hi & c_hi)
        rv = v / P(roll(v, 20, np.mean))
        S["vol_spike_bull"] = (rv >= 3) & bull & (body >= 0.5 * rng)
        S["vol_spike_bear"] = (rv >= 3) & bear & (body >= 0.5 * rng)
        vw = roll(tp * v, bars_day, np.sum) / roll(v, bars_day, np.sum)
        S["vwap_reclaim"] = cross_up(c, vw)
        S["vwap_lose"] = cross_dn(c, vw)
        hac = (o + h + l + c) / 4
        hao = np.empty(n)
        hao[0] = (o[0] + c[0]) / 2
        for i in range(1, n):
            hao[i] = (hao[i - 1] + hac[i - 1]) / 2
        hg = hac > hao
        S["ha_green"] = hg & ~P(hg) & ~P(hg, 2) & ~P(hg, 3)
        S["ha_red"] = ~hg & P(hg) & P(hg, 2) & P(hg, 3)
        ret = c / P(c, bars_day) - 1
        avg = roll(np.abs(ret), 30 * bars_day, np.nanmean) if n > 30 * bars_day else np.full(n, np.nan)
        S["rally_24h"] = cross_up(ret, 2.5 * avg)
        S["drop_24h"] = cross_dn(ret, -2.5 * avg)
        g5 = bull & P(bull) & P(bull, 2) & P(bull, 3) & P(bull, 4)
        r5 = bear & P(bear) & P(bear, 2) & P(bear, 3) & P(bear, 4)
        S["five_green"] = first_in_run(g5)
        S["five_red"] = first_in_run(r5)
        S["stretch_ema20"] = cross_dn(c, e20 - 2.5 * A)
        z = (c - sma50) / roll(c, 50, np.std)
        S["zscore_m2"] = cross_dn(z, np.full(n, -2.0))
    return S, A, r14


def psar(h, l, step=0.02, mx=0.2):
    n = len(h)
    out = np.zeros(n, int)
    upt, af, ep, s = True, step, h[0], l[0]
    for i in range(1, n):
        s = s + af * (ep - s)
        if upt:
            s = min(s, l[i - 1], l[i - 2] if i >= 2 else l[i - 1])
            if l[i] < s:
                upt, s, ep, af = False, ep, l[i], step
            elif h[i] > ep:
                ep, af = h[i], min(af + step, mx)
        else:
            s = max(s, h[i - 1], h[i - 2] if i >= 2 else h[i - 1])
            if h[i] > s:
                upt, s, ep, af = True, ep, h[i], step
            elif l[i] < ep:
                ep, af = l[i], min(af + step, mx)
        out[i] = 1 if upt else -1
    return out


def supertrend(h, l, c, n=10, m=3.0):
    a = atr(h, l, c, n)
    hl2 = (h + l) / 2
    ub, lb = hl2 + m * a, hl2 - m * a
    fu, fl = ub.copy(), lb.copy()
    d = np.ones(len(c), int)
    for i in range(1, len(c)):
        if a[i] != a[i] or a[i - 1] != a[i - 1]:
            continue
        fu[i] = ub[i] if (ub[i] < fu[i - 1] or c[i - 1] > fu[i - 1]) else fu[i - 1]
        fl[i] = lb[i] if (lb[i] > fl[i - 1] or c[i - 1] < fl[i - 1]) else fl[i - 1]
        d[i] = (-1 if c[i] < fl[i] else 1) if d[i - 1] == 1 else (1 if c[i] > fu[i] else -1)
    return d


def loop_signals(t, o, h, l, c, A, r14, bars_day):
    """Swing-based chart patterns, gaps, order blocks, daily levels, fibs, pivots, divergences."""
    n = len(c)
    names = ["double_bottom", "double_top", "inverse_hs", "hs_top", "bos_up", "choch_up", "choch_down",
             "asc_triangle", "desc_triangle", "sym_triangle_up", "falling_wedge", "rising_wedge", "bull_flag",
             "bear_flag", "fvg_retest", "ob_retest", "pdl_sweep", "pdh_break", "pdh_reject", "fib_618", "pivot_s1",
             "pivot_r1_reject", "rsi_bull_div", "rsi_bear_div"]
    S = {k: np.zeros(n, bool) for k in names}
    SL, SH = [], []                                   # confirmed swings: (index, price)
    fvgs, obs = [], []
    day = t // (24 * HOUR)
    # prior UTC day's H/L/C for every bar
    pdh, pdl, pdc = np.full(n, np.nan), np.full(n, np.nan), np.full(n, np.nan)
    cur, dh, dl, dc, prev = None, None, None, None, None
    for i in range(n):
        if day[i] != cur:
            if cur is not None:
                prev = (dh, dl, dc)
            cur, dh, dl = day[i], h[i], l[i]
        dh, dl, dc = max(dh, h[i]), min(dl, l[i]), c[i]
        if prev:
            pdh[i], pdl[i], pdc[i] = prev
    used = {"pdl": None, "pdh": None, "s1": None}
    for i in range(205, n):
        a = A[i]
        if a != a or a <= 0:
            continue
        j = i - 2                                      # a 2-bar fractal at j is confirmed at i
        if l[j] < min(l[j - 2], l[j - 1], l[j + 1], l[j + 2]):
            SL.append((j, l[j]))
        if h[j] > max(h[j - 2], h[j - 1], h[j + 1], h[j + 2]):
            SH.append((j, h[j]))
        ci, cp = c[i], c[i - 1]
        if len(SL) >= 2:
            (i1, p1), (i2, p2) = SL[-2], SL[-1]
            if 10 <= i2 - i1 <= 80 and abs(p1 - p2) <= 0.5 * a and i - i2 <= 30:
                neck = h[i1:i2 + 1].max()
                if neck - max(p1, p2) >= 1.5 * a and ci > neck >= cp and l[i2 + 1:i + 1].min() > min(p1, p2) - 0.5 * a:
                    S["double_bottom"][i] = True
        if len(SH) >= 2:
            (i1, p1), (i2, p2) = SH[-2], SH[-1]
            if 10 <= i2 - i1 <= 80 and abs(p1 - p2) <= 0.5 * a and i - i2 <= 30:
                neck = l[i1:i2 + 1].min()
                if min(p1, p2) - neck >= 1.5 * a and ci < neck <= cp and h[i2 + 1:i + 1].max() < max(p1, p2) + 0.5 * a:
                    S["double_top"][i] = True
        if len(SL) >= 3:
            (a1, q1), (a2, q2), (a3, q3) = SL[-3:]
            if q2 < min(q1, q3) - a and abs(q1 - q3) <= a and a2 - a1 >= 5 and a3 - a2 >= 5 and a3 - a1 <= 120 and i - a3 <= 30:
                neck = h[a1:a3 + 1].max()
                if ci > neck >= cp:
                    S["inverse_hs"][i] = True
        if len(SH) >= 3:
            (a1, q1), (a2, q2), (a3, q3) = SH[-3:]
            if q2 > max(q1, q3) + a and abs(q1 - q3) <= a and a2 - a1 >= 5 and a3 - a2 >= 5 and a3 - a1 <= 120 and i - a3 <= 30:
                neck = l[a1:a3 + 1].min()
                if ci < neck <= cp:
                    S["hs_top"][i] = True
        if len(SL) >= 2 and len(SH) >= 2:
            (hi1, hp1), (hi2, hp2) = SH[-2], SH[-1]
            (li1, lp1), (li2, lp2) = SL[-2], SL[-1]
            if ci > hp2 >= cp:
                if hp2 > hp1 and lp2 > lp1:
                    S["bos_up"][i] = True
                if hp2 < hp1 and lp2 < lp1:
                    S["choch_up"][i] = True
            if ci < lp2 <= cp and hp2 > hp1 and lp2 > lp1:
                S["choch_down"][i] = True
            recent = i - min(hi1, li1) <= 60
            if recent and abs(hp1 - hp2) <= 0.3 * a and lp2 > lp1 + 0.5 * a and ci > max(hp1, hp2) >= cp:
                S["asc_triangle"][i] = True
            if recent and abs(lp1 - lp2) <= 0.3 * a and hp2 < hp1 - 0.5 * a and ci < min(lp1, lp2) <= cp:
                S["desc_triangle"][i] = True
            if recent and hi2 > hi1 and li2 > li1:
                su = (hp2 - hp1) / (hi2 - hi1)
                sl_ = (lp2 - lp1) / (li2 - li1)
                upper_now, upper_prev = hp2 + su * (i - hi2), hp2 + su * (i - 1 - hi2)
                lower_now, lower_prev = lp2 + sl_ * (i - li2), lp2 + sl_ * (i - 1 - li2)
                if su < 0 < sl_ and ci > upper_now and cp <= upper_prev:
                    S["sym_triangle_up"][i] = True
                if su < 0 and sl_ < 0 and su < sl_ and ci > upper_now and cp <= upper_prev:
                    S["falling_wedge"][i] = True
                if su > 0 and sl_ > 0 and sl_ > su and ci < lower_now and cp >= lower_prev:
                    S["rising_wedge"][i] = True
        for k in range(4, 16):                          # flags: pause = bars i-k .. i-1
            s0 = i - k
            if s0 - 9 < 0:
                break
            ftop, fbot = h[s0:i].max(), l[s0:i].min()
            pole_lo, pole_hi = l[s0 - 9:s0].min(), h[s0 - 9:s0].max()
            if ci > ftop >= cp and c[s0 - 1] - pole_lo >= 3 * a and fbot >= c[s0 - 1] - 0.5 * (c[s0 - 1] - pole_lo) \
                    and ftop <= pole_hi + 0.2 * a:
                S["bull_flag"][i] = True
                break
            if ci < fbot <= cp and pole_hi - c[s0 - 1] >= 3 * a and ftop <= c[s0 - 1] + 0.5 * (pole_hi - c[s0 - 1]) \
                    and fbot >= pole_lo - 0.2 * a:
                S["bear_flag"][i] = True
                break
        # fair value gaps
        if l[i] > h[i - 2] + 0.1 * a:
            fvgs.append([i, h[i - 2], l[i]])
        keep = []
        for g in fvgs:
            gi, gb, gt = g
            if i == gi:
                keep.append(g)
                continue
            if i - gi > 30 or ci < gb:
                continue
            if l[i] <= gt and ci > gb:
                S["fvg_retest"][i] = True
                continue
            keep.append(g)
        fvgs = keep
        # order blocks
        if ci > h[i - 20:i].max() and cp <= h[i - 21:i - 1].max():
            for k in range(1, 6):
                if c[i - k] < o[i - k]:
                    obs.append([i, l[i - k], h[i - k]])
                    break
        keep = []
        for g in obs:
            gi, ob_l, ob_h = g
            if i == gi:
                keep.append(g)
                continue
            if i - gi > 40 or ci < ob_l:
                continue
            if l[i] <= ob_h and ci > ob_l:
                S["ob_retest"][i] = True
                continue
            keep.append(g)
        obs = keep
        # prior-day levels and floor pivots
        if pdh[i] == pdh[i]:
            if l[i] < pdl[i] < ci and used["pdl"] != day[i]:
                S["pdl_sweep"][i], used["pdl"] = True, day[i]
            if ci > pdh[i] and used["pdh"] != day[i]:
                S["pdh_break"][i], used["pdh"] = True, day[i]
            if h[i] > pdh[i] > ci:
                S["pdh_reject"][i] = True
            pv = (pdh[i] + pdl[i] + pdc[i]) / 3
            s1, r1 = 2 * pv - pdh[i], 2 * pv - pdl[i]
            if l[i] <= s1 < ci and used["s1"] != day[i]:
                S["pivot_s1"][i], used["s1"] = True, day[i]
            if h[i] > r1 > ci:
                S["pivot_r1_reject"][i] = True
        # fib 61.8%
        w = h[i - 40:i]
        ih = i - 40 + int(w.argmax())
        if ih > i - 40:
            lo_i = i - 40 + int(l[i - 40:ih].argmin())
            hi_v, lo_v = h[ih], l[lo_i]
            if hi_v - lo_v >= 4 * a and ih < i - 1:
                lvl = hi_v - 0.618 * (hi_v - lo_v)
                if l[i] <= lvl < ci and l[ih + 1:i].min() > lvl:
                    S["fib_618"][i] = True
        # RSI divergences
        if r14[i] == r14[i]:
            seg = c[i - 20:i - 4]
            jl = i - 20 + int(seg.argmin())
            if ci < c[jl] and r14[jl] < 35 and r14[i] >= r14[jl] + 3 and c[i - 1] >= c[jl]:
                S["rsi_bull_div"][i] = True
            jh = i - 20 + int(seg.argmax())
            if ci > c[jh] and r14[jh] > 65 and r14[i] <= r14[jh] - 3 and c[i - 1] <= c[jh]:
                S["rsi_bear_div"][i] = True
    return S


def to4h(t, o, h, l, c, v, gate):
    k = t // (4 * HOUR)
    br = np.flatnonzero(np.diff(k)) + 1
    starts = np.concatenate([[0], br])
    ends = np.concatenate([br, [len(t)]]) - 1
    full = (ends - starts + 1) == 4
    return (t[starts][full], o[starts][full], np.maximum.reduceat(h, starts)[full],
            np.minimum.reduceat(l, starts)[full], c[ends][full], np.add.reduceat(v, starts)[full], gate[ends][full])




def all_signals(t, o, h, l, c, v, bars_day):
    S, A, r14 = vector_signals(t, o, h, l, c, v, bars_day)
    S.update(loop_signals(t, o, h, l, c, A, r14, bars_day))
    return S, A


def bars4h_index(t):
    """For 1h timestamps, (starts, ends) index arrays of the complete 4h buckets (4 hourly bars each)."""
    k = t // (4 * HOUR)
    br = np.flatnonzero(np.diff(k)) + 1
    starts = np.concatenate([[0], br])
    ends = np.concatenate([br, [len(t)]]) - 1
    full = (ends - starts + 1) == 4
    return starts[full], ends[full]
