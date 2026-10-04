#!/usr/bin/env python3
"""Write ULTRON for TradingView (Pine Script v5) from the per-timeframe models: an indicator and a strategy.

  python3 ultron/tv/build_pine.py      # reads ultron/tv/models/*.json -> ULTRON_indicator.pine, ULTRON_strategy.pine
  python3 ultron/tv/pine_check.py ultron/tv/ULTRON_*.pine     # compile with TradingView's compiler

The script picks the council trained for the chart's timeframe (5m, 15m, 30m, 1h, 2h, 4h, 1D), or the nearest one
on other timeframes. Every constant (agents, learned edges, brain settings, gate weights) comes from training, and
every formula matches ultron/tools/train_tf.py: chart-bar signals, higher-timeframe signals acted on at the chart bar
that closes the higher-timeframe bar, the same trend, Bitcoin-regime and weekend rules.
"""

from __future__ import annotations

import json
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ORDER = ["5m", "15m", "30m", "1h", "2h", "4h", "1D"]
SEC = {"5m": 300, "15m": 900, "30m": 1800, "1h": 3600, "2h": 7200, "4h": 14400, "1D": 86400}
HTF = {"5m": "15", "15m": "60", "30m": "120", "1h": "240", "2h": "480", "4h": "D", "1D": "W"}
HTF_SEC = {"15": 900, "60": 3600, "120": 7200, "240": 14400, "480": 28800, "D": 86400, "W": 604800}
VAR = {"any": 0, "loud": 1, "trend": 2, "loudtrend": 3}

# Pine translations of signals.py (inside f_all(bd); bd = bars per day of the timeframe being evaluated)
SNIP = {
    "hammer": "f_dn(0) and ham", "hanging_man": "f_up(0) and ham", "inverted_hammer": "f_dn(0) and inv",
    "shooting_star": "f_up(0) and inv",
    "dragonfly_doji": "f_dn(0) and body <= 0.05 * rng and upw <= 0.1 * rng and big",
    "gravestone_doji": "f_up(0) and body <= 0.05 * rng and loww <= 0.1 * rng and big",
    "doji_after_drop": "f_dn(0) and doji", "doji_after_rise": "f_up(0) and doji",
    "long_legged_doji": "body <= 0.1 * rng and upw >= 0.35 * rng and loww >= 0.35 * rng and rng >= A",
    "spinning_top": "body <= 0.3 * rng and body >= 0.1 * rng and upw >= body and loww >= body",
    "bull_marubozu": "isBull and body >= 0.9 * rng and rng >= A", "bear_marubozu": "isBear and body >= 0.9 * rng and rng >= A",
    "bull_belt_hold": "f_dn(0) and isBull and open - low <= 0.05 * rng and body >= 0.6 * rng and rng >= A",
    "big_bull_bar": "isBull and rng >= 2 * A[1] and body >= 0.6 * rng",
    "big_bear_bar": "isBear and rng >= 2 * A[1] and body >= 0.6 * rng",
    "bull_engulfing": "bullEng", "bear_engulfing": "bearEng",
    "bull_harami": "bullHar", "bear_harami": "bearHar", "bull_harami_cross": "f_dn(1) and harUp and body <= 0.1 * rng",
    "piercing_line": "f_dn(1) and bigRed1 and isBull and open <= close[1] and close > (open[1] + close[1]) / 2 and close < open[1]",
    "dark_cloud_cover": "f_up(1) and bigGrn1 and isBear and open >= close[1] and close < (open[1] + close[1]) / 2 and close > open[1]",
    "tweezer_bottom": "f_dn(1) and isBear[1] and isBull and math.abs(low - low[1]) <= 0.05 * A and rng[1] >= 0.5 * A[1]",
    "tweezer_top": "f_up(1) and isBull[1] and isBear and math.abs(high - high[1]) <= 0.05 * A and rng[1] >= 0.5 * A[1]",
    "bull_kicker": "isBear[1] and body[1] >= 0.6 * rng[1] and isBull and open > open[1] and body >= 0.6 * rng",
    "outside_bar_up": "high > high[1] and low < low[1] and close > high[1]",
    "outside_bar_down": "high > high[1] and low < low[1] and close < low[1]",
    "inside_bar": "ins", "inside_bar_break_up": "ins[1] and close > high[2]", "inside_bar_break_down": "ins[1] and close < low[2]",
    "nr7_break_up": "nr7[1] and close > high[1]",
    "morning_star": "mStar", "evening_star": "eStar", "morning_doji_star": "mStar and body[1] <= 0.1 * rng[1]",
    "evening_doji_star": "eStar and body[1] <= 0.1 * rng[1]",
    "three_white_soldiers": "tws", "three_black_crows": "tbc",
    "three_inside_up": "bullHar[1] and isBull and close > open[2]", "three_inside_down": "bearHar[1] and isBear and close < open[2]",
    "three_outside_up": "bullEng[1] and close > close[1]", "three_outside_down": "bearEng[1] and close < close[1]",
    "bull_three_line_strike": "tbc[1] and isBull and open <= close[1] and close >= open[3]",
    "bear_three_line_strike": "tws[1] and isBear and open >= close[1] and close <= open[3]",
    "rising_three": "isBull[4] and body[4] >= A[4] and body[4] >= 0.6 * rng[4] and small3 and isBull and close > close[4]",
    "falling_three": "isBear[4] and body[4] >= A[4] and body[4] >= 0.6 * rng[4] and small3 and isBear and close < close[4]",
    "rsi_os_30": "rsi14 < 30 and rsi14[1] >= 30", "rsi_up_30": "rsi14 > 30 and rsi14[1] <= 30",
    "rsi_ob_70": "rsi14 > 70 and rsi14[1] <= 70", "rsi_dn_70": "rsi14 < 70 and rsi14[1] >= 70",
    "rsi2_10": "rsi2 < 10 and rsi2[1] >= 10", "rsi2_connors": "rsi2 < 10 and rsi2[1] >= 10 and close > sma200",
    "macd_up": "macdUp", "macd_up_below0": "macdUp and macdL < 0 and sigL < 0", "macd_zero_up": "macdL > 0 and macdL[1] <= 0",
    "macd_down": "macdL < sigL and macdL[1] >= sigL[1]", "macd_hist_turn": "hist < 0 and hist > hist[1] and hist[1] <= hist[2]",
    "ema_9_21_up": "e9 > e21 and e9[1] <= e21[1]", "ema_9_21_down": "e9 < e21 and e9[1] >= e21[1]",
    "golden_cross": "sma50 > sma200 and sma50[1] <= sma200[1]", "death_cross": "sma50 < sma200 and sma50[1] >= sma200[1]",
    "ema200_reclaim": "close > e200 and close[1] <= e200[1]", "ema200_lose": "close < e200 and close[1] >= e200[1]",
    "bb_below": "close < bbL and close[1] >= bbL[1]", "bb_reentry": "close > bbL and close[1] <= bbL[1]",
    "bb_above": "close > bbU and close[1] <= bbU[1]", "bb_squeeze_up": "bw[1] <= 1.1 * ta.lowest(bw, 120)[1] and close > bbU",
    "keltner_up": "close > kcU and close[1] <= kcU[1]", "keltner_below": "close < kcL and close[1] >= kcL[1]",
    "ttm_squeeze": "sq[1] and not sq and close > e20",
    "stoch_up": "stK > stD and stK[1] <= stD[1] and stK[1] < 20", "stoch_down": "stK < stD and stK[1] >= stD[1] and stK[1] > 80",
    "stochrsi_up": "srK > srD and srK[1] <= srD[1] and srK[1] < 0.2", "willr_up": "wr > -80 and wr[1] <= -80",
    "cci_up": "cciV > -100 and cciV[1] <= -100", "cci_break": "cciV > 100 and cciV[1] <= 100",
    "mfi_os": "mf < 20 and mf[1] >= 20", "mfi_ob": "mf > 80 and mf[1] <= 80",
    "adx_di_up": "diP > diM and diP[1] <= diM[1] and adxV > 20", "holy_grail": "adxV > 30 and diP > diM and low <= e20 and close > e20",
    "donchian20": "don20 and not don20[1]", "donchian55": "don55 and not don55[1]", "donchian20_down": "dd20 and not dd20[1]",
    "obv_lead": "obvLead and not obvLead[1]", "obv_confirm": "obvConf and not obvConf[1]",
    "vol_spike_bull": "rvol >= 3 and isBull and body >= 0.5 * rng", "vol_spike_bear": "rvol >= 3 and isBear and body >= 0.5 * rng",
    "vwap_reclaim": "close > vw and close[1] <= vw[1]", "vwap_lose": "close < vw and close[1] >= vw[1]",
    "ha_green": "hg and not hg[1] and not hg[2] and not hg[3]", "ha_red": "not hg and hg[1] and hg[2] and hg[3]",
    "rally_24h": "ret > 2.5 * avgAbs and ret[1] <= 2.5 * avgAbs[1]", "drop_24h": "ret < -2.5 * avgAbs and ret[1] >= -2.5 * avgAbs[1]",
    "five_green": "g5 and not g5[1]", "five_red": "r5 and not r5[1]",
    "stretch_ema20": "close < e20 - 2.5 * A and close[1] >= e20[1] - 2.5 * A[1]", "zscore_m2": "zs < -2 and zs[1] >= -2",
}
HELPERS = """    A = ta.atr(14)
    body = math.abs(close - open)
    rng = high - low
    upw = high - math.max(open, close)
    loww = math.min(open, close) - low
    isBull = close > open
    isBear = close < open
    big = rng >= 0.5 * A
    ham = loww >= 2 * body and upw <= 0.1 * rng and body >= 0.05 * rng and big
    inv = upw >= 2 * body and loww <= 0.1 * rng and body >= 0.05 * rng and big
    doji = body <= 0.1 * rng and big
    ins = high < high[1] and low > low[1]
    nr7 = rng <= ta.lowest(rng, 7)
    engUp = isBear[1] and isBull and close >= open[1] and open <= close[1] and body > body[1]
    engDn = isBull[1] and isBear and close <= open[1] and open >= close[1] and body > body[1]
    bullEng = f_dn(1) and engUp
    bearEng = f_up(1) and engDn
    bigRed1 = isBear[1] and body[1] >= 0.6 * rng[1] and body[1] >= 0.75 * A[1]
    bigGrn1 = isBull[1] and body[1] >= 0.6 * rng[1] and body[1] >= 0.75 * A[1]
    harUp = bigRed1 and math.max(open, close) <= open[1] and math.min(open, close) >= close[1] and body <= 0.5 * body[1]
    harDn = bigGrn1 and math.max(open, close) <= close[1] and math.min(open, close) >= open[1] and body <= 0.5 * body[1]
    bullHar = f_dn(1) and harUp and isBull
    bearHar = f_up(1) and harDn and isBear
    bigRed2 = isBear[2] and body[2] >= 0.6 * rng[2] and body[2] >= 0.75 * A[2]
    bigGrn2 = isBull[2] and body[2] >= 0.6 * rng[2] and body[2] >= 0.75 * A[2]
    mStar = f_dn(2) and bigRed2 and body[1] <= 0.3 * body[2] and isBull and close > (open[2] + close[2]) / 2
    eStar = f_up(2) and bigGrn2 and body[1] <= 0.3 * body[2] and isBear and close < (open[2] + close[2]) / 2
    sold = isBull and body >= 0.6 * rng and body >= 0.5 * A and upw <= 0.3 * body
    crow = isBear and body >= 0.6 * rng and body >= 0.5 * A
    tws = sold and sold[1] and sold[2] and close > close[1] and close[1] > close[2] and open >= open[1] and open <= close[1] and open[1] >= open[2] and open[1] <= close[2]
    tbc = crow and crow[1] and crow[2] and close < close[1] and close[1] < close[2] and open <= open[1] and open >= close[1] and open[1] <= open[2] and open[1] >= close[2]
    small3 = body[1] <= 0.5 * body[4] and high[1] <= high[4] and low[1] >= low[4] and body[2] <= 0.5 * body[4] and high[2] <= high[4] and low[2] >= low[4] and body[3] <= 0.5 * body[4] and high[3] <= high[4] and low[3] >= low[4]
    g5 = isBull and isBull[1] and isBull[2] and isBull[3] and isBull[4]
    r5 = isBear and isBear[1] and isBear[2] and isBear[3] and isBear[4]
    rsi14 = ta.rsi(close, 14)
    rsi2 = ta.rsi(close, 2)
    sma50 = ta.sma(close, 50)
    sma200 = ta.sma(close, 200)
    e9 = ta.ema(close, 9)
    e20 = ta.ema(close, 20)
    e21 = ta.ema(close, 21)
    e200 = ta.ema(close, 200)
    macdL = ta.ema(close, 12) - ta.ema(close, 26)
    sigL = ta.ema(macdL, 9)
    hist = macdL - sigL
    macdUp = macdL > sigL and macdL[1] <= sigL[1]
    bbB = ta.sma(close, 20)
    bbD = ta.stdev(close, 20)
    bbU = bbB + 2 * bbD
    bbL = bbB - 2 * bbD
    bw = (bbU - bbL) / bbB
    kcU = e20 + 2 * A
    kcL = e20 - 2 * A
    sq = bbU < kcU and bbL > kcL
    stK = ta.sma(ta.stoch(close, high, low, 14), 3)
    stD = ta.sma(stK, 3)
    srs = (rsi14 - ta.lowest(rsi14, 14)) / (ta.highest(rsi14, 14) - ta.lowest(rsi14, 14))
    srK = ta.sma(srs, 3)
    srD = ta.sma(srK, 3)
    wr = -100 * (ta.highest(high, 14) - close) / (ta.highest(high, 14) - ta.lowest(low, 14))
    cciV = ta.cci(hlc3, 20)
    mf = ta.mfi(hlc3, 14)
    [diP, diM, adxV] = ta.dmi(14, 14)
    don20 = close > ta.highest(high, 20)[1]
    don55 = close > ta.highest(high, 55)[1]
    dd20 = close < ta.lowest(low, 20)[1]
    ob = ta.obv
    obvHi = ob >= ta.highest(ob, 20)[1]
    cHi = close >= ta.highest(close, 20)[1]
    obvLead = obvHi and not cHi
    obvConf = obvHi and cHi
    rvol = volume / ta.sma(volume, 20)[1]
    vw = math.sum(hlc3 * volume, bd) / math.sum(volume, bd)
    haC = (open + high + low + close) / 4
    var float haO = na
    haO := na(haO[1]) ? (open + close) / 2 : (haO[1] + haC[1]) / 2
    hg = haC > haO
    ret = close / close[bd] - 1
    avgAbs = ta.sma(math.abs(ret), math.min(30 * bd, 4500))
    zs = (close - sma50) / ta.stdev(close, 50)
"""


def num(x, d=6):
    if x is None or x != x:
        return "na"
    s = f"{x:.{d}f}".rstrip("0").rstrip(".")
    s = s if s not in ("", "-", "-0") else "0"
    return s if "." in s else s + ".0"                     # always a float literal (Pine types arrays by their values)


def load_models():
    ms = []
    for tf in ORDER:
        p = os.path.join(HERE, "models", f"{tf}.json")
        if os.path.exists(p):
            with open(p) as fh:
                m = json.load(fh)
            if m["agents"]:
                ms.append(m)
    return ms


def test_line(m):
    c = m["backtest"]["metrics"]["C"]
    a = m["backtest"]["metrics"]["all"]
    return (f"all {a['avg_r']:+.2f}R x {a['n']} · test {c['avg_r']:+.2f}R x {c['n']}", a["avg_r"] > 0 and c["avg_r"] > 0 and c["n"] >= 15)


def build(models, strategy):
    union = sorted({a["signal"] for m in models for a in m["agents"]})
    missing = [s for s in union if s not in SNIP]
    if missing:
        raise SystemExit(f"no Pine translation for: {missing}")
    sidx = {s: k for k, s in enumerate(union)}
    labels = {a["signal"]: a["label"] for m in models for a in m["agents"]}
    L = []
    w = L.append
    nm = len(models)
    nu = len(union)
    title = "ULTRON · AI trade council · all timeframes" + (" (strategy)" if strategy else "")
    w("// Generated by ultron/tv/build_pine.py from the trained per-timeframe models. Educational, not advice.")
    w("// Councils: " + ", ".join(f"{m['tf']} (data {m['data_from']} to {m['data_end']})" for m in models))
    w("//@version=5")
    common = 'shorttitle="ULTRON", overlay=true, max_labels_count=500, max_lines_count=500, max_bars_back=5000'
    if strategy:
        w(f'strategy("{title}", {common}, pyramiding=0, initial_capital=1000, default_qty_type=strategy.fixed, '
          'commission_type=strategy.commission.percent, commission_value=0.2, slippage=2)')
    else:
        w(f'indicator("{title}", {common})')
    w("")
    w("// ═════════ settings (the trained values are the defaults)")
    w('gA = "Account & risk"')
    w('iAccount = strategy.equity' if strategy else 'iAccount = input.float(1000, "Account size ($)", minval=10, group=gA)')
    w('iRiskMaj = input.float(0.60, "Risk per trade: BTC, ETH, SOL (%)", minval=0.05, maxval=5, step=0.05, group=gA)')
    w('iRiskMem = input.float(0.30, "Risk per trade: meme coins (%)", minval=0.05, maxval=5, step=0.05, group=gA)')
    w('gF = "Your exchange fees"')
    w('iMaker = input.float(0.20, "Maker fee per side (%)", minval=0, step=0.01, group=gF, tooltip="NDAX 0.20 · Kraken Pro entry tier 0.40 · Coinbase Advanced 0.60")')
    w('iTaker = input.float(0.20, "Taker fee per side (%)", minval=0, step=0.01, group=gF, tooltip="NDAX 0.20 · Kraken Pro entry tier 0.80 · Coinbase Advanced 1.20")')
    w('gB = "Brain"')
    w('iNearest = input.bool(true, "On untrained timeframes, use the nearest trained council", group=gB)')
    w('iOther = input.bool(false, "Also run on markets it was not trained on", group=gB)')
    w('iOnlyPassed = input.bool(true, "Only trade timeframes that passed the untouched test", group=gB, tooltip="On: timeframes whose council lost money in testing, or had too few test trades, stay flat. Off: trade them anyway (not recommended).")')
    w('iExtra = input.float(0.0, "Extra caution: raise the minimum edge by (R)", step=0.01, group=gB)')
    w('iGate = input.string("Trained", "Volatility filter", options=["Trained", "LOUD only", "LOUD or NORMAL", "Off"], group=gB)')
    w('iCostMax = input.float(0.33, "Max fee cost (R)", minval=0.05, step=0.01, group=gB)')
    w('iStopMult = input.float(1.0, "Stop distance (x the trained stop)", minval=0.25, step=0.05, group=gB, tooltip="Trained stop: 4x ATR on 1h and slower; wider on 5m-30m so fees stay small next to the stop.")')
    w('iTargetR = input.float(2.0, "Target (R)", minval=0.5, step=0.25, group=gB)')
    w('iOrderBars = input.int(3, "Limit order valid (bars)", minval=1, group=gB)')
    w('iHoldX = input.float(1.0, "Max hold (x the trained hold)", minval=0.1, step=0.1, group=gB, tooltip="Trained hold: 96 bars on 1h and slower; longer on 5m-30m (about 4 days in every case).")')
    w('gS = "Agents by signal (switch any off)"')
    for s in union:
        w(f'u_{s} = input.bool(true, "{labels[s]}", group=gS)')
    w('gD = "Display"')
    w('iTable = input.bool(true, "Show the council table", group=gD)')
    w('iTablePos = input.string("Top right", "Table position", options=["Top right", "Top left", "Bottom right", "Bottom left"], group=gD)')
    w('iTableSize = input.string("Small", "Table text", options=["Tiny", "Small", "Normal"], group=gD)')
    w('iPast = input.bool(true, "Label past buys and sells", group=gD)')
    w('iLines = input.bool(true, "Draw entry, stop and target", group=gD)')
    w('iGateBg = input.bool(true, "Tint the background in LOUD periods", group=gD)')
    w('iMsg = input.string("Readable", "Alert message", options=["Readable", "JSON (for bots and webhooks)"], group=gD)')
    w('cBuy = input.color(color.new(#1F5BFF, 0), "Buy", group=gD, inline="c")')
    w('cStop = input.color(color.new(#E2474D, 0), "Stop", group=gD, inline="c")')
    w('cTarget = input.color(color.new(#0E9F63, 0), "Target", group=gD, inline="c")')
    w('cLoud = input.color(color.new(#1F5BFF, 93), "LOUD tint", group=gD, inline="c")')
    w("")
    w("// ═════════ which council: the chart's timeframe, or the nearest trained one")
    w("tfSec = timeframe.in_seconds()")
    secs = [SEC[m["tf"]] for m in models]
    w("exact = " + " or ".join(f"tfSec == {s}" for s in secs))
    w("mi = " + "".join(f"tfSec < {int(math.sqrt(secs[k] * secs[k + 1]))} ? {k} : " for k in range(nm - 1)) + str(nm - 1))
    w("htfStr = " + "".join(f'mi == {k} ? "{HTF[m["tf"]]}" : ' for k, m in enumerate(models[:-1])) + f'"{HTF[models[-1]["tf"]]}"')
    w("bdChart = math.max(1, math.round(86400 / tfSec))")
    w("bdHtf = " + "".join(f"mi == {k} ? {max(1, round(86400 / HTF_SEC[HTF[m['tf']]]))} : " for k, m in enumerate(models[:-1]))
      + str(max(1, round(86400 / HTF_SEC[HTF[models[-1]["tf"]]]))))
    w('mName = ' + "".join(f'mi == {k} ? "{m["tf"]}" : ' for k, m in enumerate(models[:-1])) + f'"{models[-1]["tf"]}"')
    tl = [test_line(m) for m in models]
    w('mTest = ' + "".join(f'mi == {k} ? "{tl[k][0]}" : ' for k in range(nm - 1)) + f'"{tl[-1][0]}"')
    w('mPassed = ' + "".join(f'mi == {k} ? {"true" if tl[k][1] else "false"} : ' for k in range(nm - 1)) + ("true" if tl[-1][1] else "false"))
    w("")
    w("// ═════════ trained constants (all councils; mi picks one)")
    offs, flat = [], []
    for m in models:
        offs.append(len(flat))
        flat += m["agents"]
    arr = lambda xs, d=5: "array.from(" + ", ".join(num(x, d) for x in xs) + ")"            # noqa: E731
    w(f"var int[] M_OFF = array.from({', '.join(map(str, offs))})")
    w(f"var int[] M_N = array.from({', '.join(str(len(m['agents'])) for m in models)})")
    w(f"var string[] A_NAME = array.from({', '.join(chr(34) + a['name'] + chr(34) for a in flat)})")
    w(f"var int[] A_SIG = array.from({', '.join(str(sidx[a['signal']]) for a in flat)})")
    w(f"var bool[] A_HTF = array.from({', '.join('true' if a['htf'] else 'false' for a in flat)})")
    w(f"var int[] A_VAR = array.from({', '.join(str(VAR[a['variant']]) for a in flat)})")
    w(f"var bool[] A_MAJ = array.from({', '.join('true' if a['group'] == 'majors' else 'false' for a in flat)})")
    for key, pre in (("bull", "B"), ("bear", "F"), ("na", "N")):
        w(f"var float[] A_M{pre} = {arr([a['edges'][key][0] for a in flat])}")
        w(f"var float[] A_S{pre} = {arr([a['edges'][key][1] for a in flat])}")
    P = [m["params"] for m in models]
    X = [m.get("exit", {"stop_chart": 4.0, "stop_htf": 4.0, "hold": 96}) for m in models]
    w(f"var float[] P_SC = {arr([x['stop_chart'] for x in X], 3)}")
    w(f"var float[] P_SH = {arr([x['stop_htf'] for x in X], 3)}")
    w(f"var int[] P_HOLD = array.from({', '.join(str(int(x['hold'])) for x in X)})")
    w(f"var float[] P_THETA = {arr([p['theta'] for p in P], 4)}")
    w(f"var float[] P_Z = {arr([p['z'] for p in P], 4)}")
    w(f"var float[] P_SIZEA = {arr([p['size_a'] for p in P], 4)}")
    w(f"var float[] P_LOUDM = {arr([p['loud_mult'] for p in P], 4)}")
    w(f"var int[] P_GATE = array.from({', '.join(str({'loud_only': 1, 'no_quiet': 2, 'learned': 0}[p['gate_rule']]) for p in P)})")
    w(f"var bool[] P_WKND = array.from({', '.join('true' if p['weekend_off'] else 'false' for p in P)})")
    w(f"var bool[] P_BEARMEME = array.from({', '.join('true' if p['regime_rule'] == 'memes_off_in_bear' else 'false' for p in P)})")
    G = [m["gate"] for m in models]
    w(f"var float[] G_MU = {arr([x for g in G for x in g['mean']], 8)}")
    w(f"var float[] G_SD = {arr([x for g in G for x in g['std']], 8)}")
    w(f"var float[] G_WL = {arr([x for g in G for x in g['w_loud']], 8)}")
    w(f"var float[] G_WQ = {arr([x for g in G for x in g['w_quiet']], 8)}")
    w(f"var float[] G_TL = {arr([g['t_loud'] for g in G], 6)}")
    w(f"var float[] G_TQ = {arr([g['t_quiet'] for g in G], 6)}")
    prec = [g["scores"]["C"]["loud_precision"] or g["scores"]["A"]["loud_precision"] for g in G]
    w(f"var string[] G_PREC = array.from({', '.join(chr(34) + (f'{p:.0f}%' if p is not None else 'n/a') + chr(34) for p in prec)})")
    w("useOn = array.from(" + ", ".join(f"u_{s}" for s in union) + ")")
    w("")
    w("// ═════════ market")
    w('base = syminfo.basecurrency')
    w('isMajor = base == "BTC" or base == "ETH" or base == "SOL"')
    w('isMeme = base == "DOGE" or base == "SHIB" or base == "PEPE" or base == "BONK" or base == "WIF" or base == "FLOKI"')
    w('useMajor = isMajor or (not isMeme and iOther)')
    w('active = (isMajor or isMeme or iOther) and (exact or iNearest) and (mPassed or not iOnlyPassed)')
    w('slip = useMajor ? 0.0002 : 0.001')
    w("")
    w(f"// ═════════ the {nu} signals the councils use (same formulas on the chart and on the higher timeframe)")
    w("f_dn(k) => close[k + 1] < close[k + 6]")
    w("f_up(k) => close[k + 1] > close[k + 6]")
    w("f_all(bd) =>")
    w(HELPERS.rstrip("\n"))
    for s in union:
        w(f"    s_{s} = {SNIP[s]}")
    w("    [" + ", ".join(f"s_{s}" for s in union) + ", A]")
    w("[" + ", ".join(f"c_{s}" for s in union) + ", atrC] = f_all(bdChart)")
    w("[" + ", ".join(f"h_{s}" for s in union) + ", atrH] = request.security(syminfo.tickerid, htfStr, f_all(bdHtf), lookahead=barmerge.lookahead_off)")
    w("sigC = array.from(" + ", ".join(f"c_{s}" for s in union) + ")")
    w("sigH = array.from(" + ", ".join(f"h_{s}" for s in union) + ")")
    w("// the chart bar that closes a higher-timeframe bar: higher-timeframe values are final here")
    w("isHtfEnd = time_close == time_close(htfStr)")
    w("var int htfCount = 0")
    w("if isHtfEnd")
    w("    htfCount += 1")
    w("")
    w("// ═════════ trend, Bitcoin regime, weekend")
    w("up1 = ta.ema(close, 21) > ta.ema(close, 50) and close > ta.ema(close, 200)")
    w("f_uph() => close > ta.ema(close, 50) and ta.ema(close, 21) > ta.ema(close, 50)")
    w("upHnow = request.security(syminfo.tickerid, htfStr, f_uph(), lookahead=barmerge.lookahead_off)")
    w("var bool upHdone = false")
    w("upH = isHtfEnd ? upHnow : upHdone")
    w("if isHtfEnd")
    w("    upHdone := upHnow")
    w("upTrend = up1 and upH")
    w("f_btc() =>")
    w("    s200 = ta.sma(close, 200)")
    w("    r = na(s200) ? na : close > s200 ? 1.0 : 0.0")
    w("    r[1]")
    w('btcState = request.security("COINBASE:BTCUSD", "D", f_btc(), lookahead=barmerge.lookahead_on)')
    w('dwMT = dayofweek(time_close, "America/Edmonton")')
    w("weekendMT = dwMT == dayofweek.saturday or dwMT == dayofweek.sunday")
    w("")
    w("// ═════════ the volatility gate (this timeframe's trained logistic model)")
    w("lg(x) => math.log(math.max(1e-6, x))")
    w("lr = nz(math.log(close / close[1]))")
    w("rms(k) => math.sqrt(math.sum(lr * lr, k) / k)")
    w("bbw = 4 * ta.stdev(close, 20) / ta.sma(close, 20)")
    w("r12 = (ta.highest(high, 12) - ta.lowest(low, 12)) / close")
    w("r72 = (ta.highest(high, 72) - ta.lowest(low, 72)) / close")
    w('hr = hour(time, "UTC")')
    w('dw = dayofweek(time, "UTC")')
    w("vsd = ta.stdev(volume, 168)")
    w("feat = array.from(1.0, lg(atrC / ta.sma(atrC, 168)), lg(bbw / ta.sma(bbw, 168)), "
      "lg((math.sum(volume, 6) / 6 + 1e-12) / (ta.sma(volume, 168) + 1e-12)), lg(rms(24) / rms(168)), lg(r12 / ta.sma(r12, 168)), "
      "math.min(6.0, math.abs(close - close[12]) / atrC), math.min(6.0, (high - low) / atrC), "
      "math.sin(2 * math.pi * hr / 24), math.cos(2 * math.pi * hr / 24), dw == dayofweek.saturday or dw == dayofweek.sunday ? 1.0 : 0.0, "
      "lg(rms(6) / rms(168)), lg(r72 / ta.sma(r72, 168)), "
      "math.max(-4.0, math.min(4.0, (ta.sma(volume, 24) - ta.sma(volume, 168)) / (vsd > 0 ? vsd : 1e-12))))")
    w("zl = 0.0")
    w("zq = 0.0")
    w("bad = bar_index < 248")
    w("gOff = mi * 14")
    w("for k = 0 to 13")
    w("    x = array.get(feat, k)")
    w("    if na(x)")
    w("        bad := true")
    w("    else")
    w("        zz = (x - array.get(G_MU, gOff + k)) / array.get(G_SD, gOff + k)")
    w("        zl += zz * array.get(G_WL, gOff + k)")
    w("        zq += zz * array.get(G_WQ, gOff + k)")
    w("pLoud = 1 / (1 + math.exp(-zl))")
    w("pQuiet = 1 / (1 + math.exp(-zq))")
    w('gate = bad ? "U" : pLoud >= array.get(G_TL, mi) ? "L" : pQuiet >= array.get(G_TQ, mi) ? "Q" : "N"')
    w("gRule = array.get(P_GATE, mi)")
    w('gateOk = gate == "U" ? false : iGate == "Off" ? true : iGate == "LOUD only" ? gate == "L" : iGate == "LOUD or NORMAL" ? gate != "Q" : '
      '(gRule == 1 ? gate == "L" : gRule == 2 ? gate != "Q" : true)')
    w("")
    w("// ═════════ the council: every enabled agent of this timeframe that fired asks the brain")
    w(f"var int[] lastC = array.new_int({nu}, -100000)")
    w(f"var int[] lastH = array.new_int({nu}, -100000)")
    w(f"keepC = array.new_bool({nu}, false)")
    w(f"keepH = array.new_bool({nu}, false)")
    w(f"for k = 0 to {nu - 1}")
    w("    if array.get(sigC, k) and bar_index >= 250 and bar_index - array.get(lastC, k) >= 12")
    w("        array.set(keepC, k, true)")
    w("        array.set(lastC, k, bar_index)")
    w("    if isHtfEnd and array.get(sigH, k) and htfCount - array.get(lastH, k) >= 3")
    w("        array.set(keepH, k, true)")
    w("        array.set(lastH, k, htfCount)")
    w('loud = gate == "L"')
    w("theta = array.get(P_THETA, mi) + iExtra")
    w("zc = array.get(P_Z, mi)")
    w("off = array.get(M_OFF, mi)")
    w("nA = array.get(M_N, mi)")
    w("bestK = -1")
    w("bestScore = -1e9")
    w("bestM = 0.0")
    w("bestStop = 0.0")
    w("bestCost = 0.0")
    w("firing = 0")
    w("entryPx = close * 0.999")
    w("for j = 0 to nA - 1")
    w("    k = off + j")
    w("    s = array.get(A_SIG, k)")
    w("    onH = array.get(A_HTF, k)")
    w("    fired = onH ? array.get(keepH, s) : array.get(keepC, s)")
    w("    v = array.get(A_VAR, k)")
    w("    cond = v == 0 or (v == 1 and loud) or (v == 2 and upTrend) or (v == 3 and loud and upTrend)")
    w("    if active and bar_index >= 250 and array.get(useOn, s) and array.get(A_MAJ, k) == useMajor and fired and cond")
    w("        firing += 1")
    w("        m = na(btcState) ? array.get(A_MN, k) : btcState == 1.0 ? array.get(A_MB, k) : array.get(A_MF, k)")
    w("        se = na(btcState) ? array.get(A_SN, k) : btcState == 1.0 ? array.get(A_SB, k) : array.get(A_SF, k)")
    w("        a = onH ? atrH : atrC")
    w("        stopD = iStopMult * (onH ? array.get(P_SH, mi) : array.get(P_SC, mi)) * a")
    w("        cost = ((iMaker + iTaker) / 100 + 2 * slip) / (stopD / entryPx)")
    w("        score = m - zc * se")
    w("        ruleOk = not (array.get(P_WKND, mi) and useMajor and weekendMT) and not (array.get(P_BEARMEME, mi) and not useMajor and btcState == 0.0)")
    w("        if gateOk and ruleOk and not na(a) and a > 0 and cost <= iCostMax and score >= theta and score > bestScore")
    w("            bestScore := score")
    w("            bestK := k")
    w("            bestM := m")
    w("            bestStop := stopD")
    w("            bestCost := cost")
    w("")
    w("// ═════════ one plan per chart: limit entry, stop, target, time limit")
    w("var float pEntry = na")
    w("var float pStop = na")
    w("var float pTarget = na")
    w("var int pBar = na")
    w("var int pFill = na")
    w('var string pAgent = ""')
    w("var float pQty = 0.0")
    w("buyNow = false")
    w('sellMsg = ""')
    w("riskPct = useMajor ? iRiskMaj : iRiskMem")
    w("busy = not na(pEntry)")
    w("holdBars = math.max(1, math.round(iHoldX * array.get(P_HOLD, mi)))")
    w("if barstate.isconfirmed and bestK >= 0 and not busy")
    w("    buyNow := true")
    w("    sz = math.max(0.5, math.min(1.5, 1 + array.get(P_SIZEA, mi) * bestM)) * (bestCost > 0.20 ? 0.5 : 1.0) * (loud ? array.get(P_LOUDM, mi) : 1.0)")
    w("    pEntry := entryPx")
    w("    pStop := entryPx - bestStop")
    w("    pTarget := entryPx + iTargetR * bestStop")
    w("    pBar := bar_index")
    w("    pFill := na")
    w("    pAgent := array.get(A_NAME, bestK)")
    w("    pQty := math.min(iAccount * riskPct / 100 * sz / bestStop, iAccount / entryPx)")
    if strategy:
        w('    strategy.entry("ULTRON", strategy.long, qty=pQty, limit=pEntry, comment=pAgent)')
        w('    strategy.exit("EXIT", "ULTRON", stop=pStop, limit=pTarget)')
    w("    if iLines")
    w("        line.new(bar_index, pEntry, bar_index + 20, pEntry, color=cBuy, style=line.style_dashed)")
    w("        line.new(bar_index, pStop, bar_index + 20, pStop, color=cStop, style=line.style_dashed)")
    w("        line.new(bar_index, pTarget, bar_index + 20, pTarget, color=cTarget, style=line.style_dashed)")
    w("    if iPast")
    w('        label.new(bar_index, low, "BUY\\n" + pAgent, style=label.style_label_up, color=cBuy, textcolor=color.white, size=size.small)')
    w("else if busy and barstate.isconfirmed and bar_index > pBar")
    if strategy:
        w("    if na(pFill) and strategy.position_size > 0")
        w("        pFill := bar_index")
        w("    if na(pFill) and bar_index - pBar >= iOrderBars")
        w('        strategy.cancel("ULTRON")')
        w('        sellMsg := "CANCEL"')
        w("    else if not na(pFill)")
        w("        if bar_index - pFill >= holdBars")
        w('            strategy.close("ULTRON", comment="time")')
        w('            sellMsg := "TIME"')
        w("        else if strategy.position_size == 0")
        w('            sellMsg := high >= pTarget ? "TARGET" : "STOP"')
    else:
        w("    if na(pFill)")
        w("        if low <= pEntry")
        w("            pFill := bar_index")
        w("        else if bar_index - pBar >= iOrderBars")
        w('            sellMsg := "CANCEL"')
        w('    if not na(pFill) and sellMsg == ""')
        w("        if low <= pStop")
        w('            sellMsg := "STOP"')
        w("        else if high >= pTarget")
        w('            sellMsg := "TARGET"')
        w("        else if bar_index - pFill >= holdBars")
        w('            sellMsg := "TIME"')
    w('    if sellMsg != ""')
    w('        if iPast and sellMsg != "CANCEL"')
    w('            label.new(bar_index, high, "SELL\\n" + sellMsg, style=label.style_label_down, color=sellMsg == "TARGET" ? cTarget : cStop, '
      'textcolor=color.white, size=size.small)')
    w("        pEntry := na")
    w("        pStop := na")
    w("        pTarget := na")
    w("        pFill := na")
    w("")
    w('// ═════════ alerts: create ONE alert → condition ULTRON → "Any alert() function call"')
    w("if buyNow")
    w('    msgB = iMsg == "Readable" ? "ULTRON BUY " + syminfo.ticker + " (" + mName + ") · limit " + str.tostring(pEntry, format.mintick) + '
      '" · stop " + str.tostring(pStop, format.mintick) + " · sell " + str.tostring(pTarget, format.mintick) + " · size " + '
      'str.tostring(pQty, "#.####") + " · agent " + pAgent : '
      '\'{"ultron":"BUY","symbol":"\' + syminfo.ticker + \'","tf":"\' + mName + \'","agent":"\' + pAgent + \'","entry":\' + '
      'str.tostring(pEntry, format.mintick) + \',"stop":\' + str.tostring(pStop, format.mintick) + \',"target":\' + '
      'str.tostring(pTarget, format.mintick) + \',"qty":\' + str.tostring(pQty, "#.########") + \',"edge_r":\' + '
      'str.tostring(bestM, "#.###") + \'}\'')
    w("    alert(msgB, alert.freq_once_per_bar_close)")
    w('if sellMsg == "STOP" or sellMsg == "TARGET" or sellMsg == "TIME"')
    w('    why = sellMsg == "TARGET" ? "target reached" : sellMsg == "STOP" ? "stop-loss hit" : "time limit reached"')
    w('    msgS = iMsg == "Readable" ? "ULTRON SELL " + syminfo.ticker + " now · " + why + " · price " + str.tostring(close, format.mintick) : '
      '\'{"ultron":"SELL","symbol":"\' + syminfo.ticker + \'","reason":"\' + sellMsg + \'","price":\' + str.tostring(close, format.mintick) + \'}\'')
    w("    alert(msgS, alert.freq_once_per_bar_close)")
    if not strategy:
        w('alertcondition(buyNow, "ULTRON BUY", "ULTRON: BUY {{ticker}} at {{close}} (see chart for entry, stop, target)")')
        w('alertcondition(sellMsg == "STOP" or sellMsg == "TARGET" or sellMsg == "TIME", "ULTRON SELL", "ULTRON: SELL {{ticker}} at {{close}}")')
    w("")
    w("// ═════════ chart")
    w('bgcolor(iGateBg and active and gate == "L" ? cLoud : na)')
    w('plotshape(buyNow and not iPast, "Council buy", shape.triangleup, location.belowbar, cBuy, size=size.tiny)')
    w('posT = iTablePos == "Top right" ? position.top_right : iTablePos == "Top left" ? position.top_left : iTablePos == "Bottom right" ? '
      'position.bottom_right : position.bottom_left')
    w('tsz = iTableSize == "Tiny" ? size.tiny : iTableSize == "Normal" ? size.normal : size.small')
    w("var table T = table.new(posT, 2, 11, bgcolor=color.new(color.white, 0), frame_color=color.new(#D9E0EB, 0), frame_width=1, "
      "border_color=color.new(#E9EEF5, 0), border_width=1)")
    w("cell(r, a, b, col) =>")
    w("    table.cell(T, 0, r, a, text_color=color.new(#56657C, 0), text_size=tsz, text_halign=text.align_left)")
    w("    table.cell(T, 1, r, b, text_color=col, text_size=tsz, text_halign=text.align_left)")
    w("ink = color.new(#0A1426, 0)")
    w("if barstate.islast and iTable")
    w('    table.cell(T, 0, 0, "ULTRON", text_color=color.white, bgcolor=cBuy, text_size=tsz)')
    w('    table.cell(T, 1, 0, "AI TRADE COUNCIL", text_color=color.white, bgcolor=cBuy, text_size=tsz)')
    w('    cell(1, "Council", mName + (exact ? " (trained)" : " (nearest, untested here)"), ink)')
    w('    cell(2, "Backtest", mTest + (mPassed ? "" : " · caution"), mPassed ? ink : cStop)')
    w("    if not active")
    w('        cell(3, "Status", not (isMajor or isMeme or iOther) ? "Not trained on " + base : not mPassed and iOnlyPassed ? '
      '"Flat: no reliable edge on this timeframe in testing" : "Untrained timeframe", cStop)')
    w("    else")
    w('        gTxt = gate == "L" ? "LOUD (big move likely)" : gate == "Q" ? "QUIET" : gate == "N" ? "NORMAL" : "warming up"')
    w('        cell(3, "Volatility", gTxt + " · LOUD right " + array.get(G_PREC, mi), gate == "L" ? cBuy : ink)')
    w('        cell(4, "Trend chart / higher", (up1 ? "up" : "no") + " / " + (upH ? "up" : "no"), ink)')
    w('        cell(5, "Bitcoin regime", na(btcState) ? "n/a" : btcState == 1.0 ? "above 200-day" : "below 200-day", ink)')
    w('        cell(6, "Agents firing now", str.tostring(firing) + " of " + str.tostring(nA), ink)')
    w('        verdict = not na(pEntry) ? (na(pFill) ? "BUY ORDER WAITING" : "IN TRADE") : "WAIT"')
    w('        cell(7, "Decision", verdict, not na(pEntry) ? cBuy : color.new(#56657C, 0))')
    w('        cell(8, "Plan", na(pEntry) ? "—" : "buy " + str.tostring(pEntry, format.mintick) + " · stop " + str.tostring(pStop, format.mintick) + '
      '" · sell " + str.tostring(pTarget, format.mintick), ink)')
    w('        cell(9, "Agent / size", na(pEntry) ? "—" : pAgent + " · " + str.tostring(pQty, "#.####") + " " + base, ink)')
    w('    cell(10, "Not advice", "paper-test before real money", color.new(#97A3B6, 0))')
    return "\n".join(L) + "\n"


def results_md(models):
    """Per-timeframe results table, generated from the model files (README section between the RESULTS markers)."""
    out = ["| Chart | Agents | Test since Dec 2025 (untouched) | Validation 2025 | Development | All: trades · avg R · return · max DD | LOUD precision (test) | Status |",
           "|---|---|---|---|---|---|---|---|"]
    for m in models:
        b = m["backtest"]["metrics"]
        f = lambda k: f"{b[k]['avg_r']:+.3f}R × {b[k]['n']}"            # noqa: E731
        a = b["all"]
        p = m["gate"]["scores"]["C"]["loud_precision"]
        out.append(f"| {m['tf']} | {len(m['agents'])} | {f('C')} | {f('B')} | {f('dev')} | {a['n']} · {a['avg_r']:+.3f}R · "
                   f"{a['ret']:+.1f}% · {a['mdd']:.1f}% | {p if p is not None else 'n/a'}% | "
                   f"{'trades' if test_line(m)[1] else '**flat by default**'} |")
    return "\n".join(out)


def main():
    models = load_models()
    if not models:
        raise SystemExit("no models in ultron/tv/models")
    readme = os.path.join(HERE, "README.md")
    if os.path.exists(readme):
        with open(readme) as fh:
            txt = fh.read()
        a, b = "<!-- RESULTS -->", "<!-- /RESULTS -->"
        if a in txt and b in txt:
            txt = txt[:txt.index(a) + len(a)] + "\n" + results_md(models) + "\n" + txt[txt.index(b):]
            with open(readme, "w") as fh:
                fh.write(txt)
            print("README results table updated")
    for strategy, name in ((False, "ULTRON_indicator.pine"), (True, "ULTRON_strategy.pine")):
        src = build(models, strategy)
        with open(os.path.join(HERE, name), "w") as fh:
            fh.write(src)
        print(f"wrote {name}: {len(src.splitlines())} lines, {len(src):,} chars; councils {[m['tf'] for m in models]}")


if __name__ == "__main__":
    main()
