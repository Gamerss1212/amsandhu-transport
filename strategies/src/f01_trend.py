"""Family: trend following (moving averages, MACD, directional movement, trailing bands, channels)."""
from lib import BOTH, CRYPTO, STOCK, st, variant

F = "trend_following"

st("ema_cross_vwap", "EMA 9/21 crossover with session-VWAP filter", F, "moving-average crossover",
   mech="short-horizon trend persistence after a fast/slow average crossover, taken only on the side of the session's volume-weighted average price",
   logic="continuation", anchor="EMA pair + session VWAP",
   hyp="When a fast average crosses a slow one, recent returns have been persistently positive; requiring price above VWAP keeps only moves that buyers since the open are winning.",
   markets=BOTH, tf="1m", direction="long", params={"fast": 9, "slow": 21},
   entry={"long": "cross_above(ema(close,$fast), ema(close,$slow))"}, filters=["close > vwap()"],
   stop={"type": "atr", "mult": 2.0, "n": 14}, target={"type": "r", "r": 2.0},
   exit={"long": "cross_below(ema(close,$fast), ema(close,$slow))"}, mtd=20,
   session={"flat_minutes_before_close": 5},
   ev=[("SRC-040", "mechanism", "moving-average rules on daily DJIA data, before costs"),
       ("SRC-033", "mechanism", "moving-average rules on high-frequency Bitcoin"),
       ("SRC-041", "contrary", "data-snooping adjustment weakens technical-rule evidence")],
   research="incompletely sourced",
   fail=["whipsaw in ranging sessions", "1-minute signals are small relative to fees at retail crypto tiers"],
   notes="Stage 1 pilot strategy. The VWAP filter and 1-minute timeframe are this platform's choices, not a source's.")

variant("ema_cross_plain", "ema_cross_vwap", "EMA crossover without VWAP filter", "filter removed", tf="5m")
variant("sma_cross_20_50", "ema_cross_vwap", "SMA 20/50 crossover", "average type and periods",
        definition_patch={"entry": {"long": "cross_above(sma(close,20), sma(close,50))"},
                          "exit": {"long": "cross_below(sma(close,20), sma(close,50))"}})
variant("hma_slope_turn", "ema_cross_vwap", "Hull MA slope turn", "same template: slope sign change of a low-lag average",
        definition_patch={"entry": {"long": "cross_above(hma(close,21), hma(close,21)[1])"}})
variant("rsi_50_cross", "ema_cross_vwap", "RSI centreline (50) cross", "same template with an oscillator in place of the average pair",
        definition_patch={"entry": {"long": "cross_above(rsi(close,14), 50)"}})

st("ema_ribbon_pullback", "Aligned EMA ribbon pullback", F, "pullback in trend",
   mech="buy weakness inside an established trend (trend defined by stacked averages)", logic="continuation (pullback)",
   anchor="EMA 8/21/55",
   hyp="With the 8, 21 and 55-period averages stacked in trend order, a dip to the 21 that closes back in the trend direction resumes the trend more often than it reverses it.",
   entry={"long": "ema(close,8) > ema(close,21) and ema(close,21) > ema(close,55) and low <= ema(close,21) and close > ema(close,21) and close > open",
          "short": "ema(close,8) < ema(close,21) and ema(close,21) < ema(close,55) and high >= ema(close,21) and close < ema(close,21) and close < open"},
   stop={"type": "level", "long": "ema(close,55)", "short": "ema(close,55)", "buffer_atr": 0.25, "n": 14},
   target={"type": "r", "r": 2.0}, mtd=3,
   fail=["late in trends pullbacks become reversals", "stacked averages lag at turning points"])

variant("supertrend_pullback", "ema_ribbon_pullback", "Supertrend pullback", "pullback reference changed to the Supertrend line",
        definition_patch={"entry": {"long": "supertrend(10,3).dir > 0 and low <= supertrend(10,3).line + 0.3*atr(14) and close > open"}})
variant("kijun_bounce", "ema_ribbon_pullback", "Ichimoku base-line bounce", "pullback reference changed to the Kijun-sen")
variant("mtf_trend_pullback", "elder_triple_screen", "Higher-timeframe trend, lower-timeframe RSI pullback", "Triple Screen template with RSI as the second screen",
        definition_patch={"entry": {"long": "tf(\"1h\", close > ema(close,50)) and cross_above(rsi(close,14), 40)"}})

st("macd_signal_cross", "MACD signal-line crossover", F, "momentum oscillator crossover",
   mech="change in the slope of smoothed momentum", logic="continuation", anchor="MACD(12,26,9)",
   hyp="A MACD line crossing its signal line marks acceleration in the direction of the cross; filtered by the zero line to trade with the prevailing momentum.",
   entry={"long": "cross_above(macd(close,12,26,9).line, macd(close,12,26,9).signal) and macd(close,12,26,9).line > 0",
          "short": "cross_below(macd(close,12,26,9).line, macd(close,12,26,9).signal) and macd(close,12,26,9).line < 0"},
   stop={"type": "atr", "mult": 2.0, "n": 14}, target={"type": "r", "r": 2.0},
   exit={"long": "cross_below(macd(close,12,26,9).line, macd(close,12,26,9).signal)",
         "short": "cross_above(macd(close,12,26,9).line, macd(close,12,26,9).signal)"},
   ev=[("SRC-087", "origin", "MACD by its inventor")], research="incompletely sourced",
   fail=["lagging in choppy markets"])
variant("macd_zero_cross", "macd_signal_cross", "MACD zero-line cross", "trigger moved to the zero line")
variant("trix_signal_cross", "macd_signal_cross", "TRIX signal cross", "triple-smoothed momentum in the same template")

st("macd_hist_turn", "MACD histogram turn below zero", F, "momentum shift",
   mech="deceleration of downside momentum before the price trend turns", logic="early reversal into trend",
   anchor="MACD histogram",
   hyp="A histogram that stops falling while still negative shows sellers losing momentum; with the longer trend up, the turn often precedes the next leg.",
   entry={"long": "macd(close,12,26,9).hist < 0 and macd(close,12,26,9).hist > macd(close,12,26,9).hist[1] and macd(close,12,26,9).hist[1] <= macd(close,12,26,9).hist[2] and close > ema(close,200)",
          "short": "macd(close,12,26,9).hist > 0 and macd(close,12,26,9).hist < macd(close,12,26,9).hist[1] and macd(close,12,26,9).hist[1] >= macd(close,12,26,9).hist[2] and close < ema(close,200)"},
   stop={"type": "atr", "mult": 1.5, "n": 14}, target={"type": "r", "r": 1.5}, max_bars=24,
   ev=[("SRC-087", "origin", "MACD histogram")], research="hypothesis", fail=["frequent false turns"])

st("adx_trend_start", "ADX trend-strength breakout", F, "directional movement",
   mech="onset of a trend measured by rising directional strength", logic="continuation", anchor="ADX/DMI(14)",
   hyp="When ADX rises through 20 with the positive directional indicator on top, a new trend is starting and tends to extend.",
   entry={"long": "cross_above(adx(14).adx, 20) and adx(14).plus_di > adx(14).minus_di",
          "short": "cross_above(adx(14).adx, 20) and adx(14).minus_di > adx(14).plus_di"},
   stop={"type": "atr", "mult": 2.0, "n": 14}, trail={"type": "atr", "mult": 3.0, "n": 14, "activate_r": 1.0},
   ev=[("SRC-074", "origin", "ADX/DMI definitions")], research="incompletely sourced",
   fail=["ADX lags: much of the move may be over when it crosses"])

st("dmi_cross", "Directional-movement crossover (Wilder DMI)", F, "directional movement",
   mech="+DI/-DI crossover marks a shift in which side is making new extremes", logic="continuation", anchor="DMI(14)",
   hyp="A +DI/-DI crossover while ADX shows a trend exists identifies the side controlling new highs/lows.",
   entry={"long": "cross_above(adx(14).plus_di, adx(14).minus_di) and adx(14).adx > 20",
          "short": "cross_above(adx(14).minus_di, adx(14).plus_di) and adx(14).adx > 20"},
   stop={"type": "atr", "mult": 2.0, "n": 14}, exit={"long": "cross_above(adx(14).minus_di, adx(14).plus_di)",
                                                    "short": "cross_above(adx(14).plus_di, adx(14).minus_di)"},
   ev=[("SRC-074", "origin", "DMI system")], research="incompletely sourced")
variant("vortex_cross", "dmi_cross", "Vortex indicator crossover", "same template with VI+/VI-")

st("supertrend_flip", "Supertrend direction flip", F, "ATR trailing band",
   mech="volatility-scaled trailing band flip marks trend change", logic="continuation", anchor="Supertrend(10,3)",
   hyp="When price closes through an ATR-scaled trailing band, the previous trend has failed and a new one is more likely.",
   entry={"long": "supertrend(10,3).dir > 0 and supertrend(10,3).dir[1] < 0",
          "short": "supertrend(10,3).dir < 0 and supertrend(10,3).dir[1] > 0"},
   stop={"type": "level", "long": "supertrend(10,3).line", "short": "supertrend(10,3).line"},
   trail={"type": "level", "long": "supertrend(10,3).line", "short": "supertrend(10,3).line"},
   research="hypothesis", fail=["whipsaw", "wide stops after volatile flips"])

st("psar_flip", "Parabolic SAR reversal", F, "stop-and-reverse", mech="accelerating trailing stop reversal",
   logic="continuation", anchor="PSAR(0.02,0.2)",
   hyp="Wilder's stop-and-reverse keeps the trader in the market on the side of the latest breakout of an accelerating stop.",
   entry={"long": "psar(0.02,0.2).dir > 0 and psar(0.02,0.2).dir[1] < 0",
          "short": "psar(0.02,0.2).dir < 0 and psar(0.02,0.2).dir[1] > 0"},
   stop={"type": "level", "long": "psar(0.02,0.2).value", "short": "psar(0.02,0.2).value"},
   trail={"type": "level", "long": "psar(0.02,0.2).value", "short": "psar(0.02,0.2).value"},
   ev=[("SRC-074", "origin", "Parabolic SAR")], research="incompletely sourced", fail=["always in the market: loses in ranges"])

st("ichimoku_tk_cross", "Ichimoku Tenkan/Kijun cross above the cloud", F, "Ichimoku", mech="short/medium midpoint crossover confirmed by cloud position",
   logic="continuation", anchor="Ichimoku(9,26,52)",
   hyp="A conversion/base-line cross on the cloud's trend side, with price above where it was 26 bars ago, aligns three horizons of trend.",
   entry={"long": "cross_above(ichimoku(9,26,52).conv, ichimoku(9,26,52).base) and close > max(ichimoku(9,26,52).span_a, ichimoku(9,26,52).span_b) and close > ichimoku(9,26,52).lag_close",
          "short": "cross_below(ichimoku(9,26,52).conv, ichimoku(9,26,52).base) and close < min(ichimoku(9,26,52).span_a, ichimoku(9,26,52).span_b) and close < ichimoku(9,26,52).lag_close"},
   stop={"type": "level", "long": "ichimoku(9,26,52).base", "short": "ichimoku(9,26,52).base", "buffer_atr": 0.25, "n": 14},
   target={"type": "r", "r": 2.0}, research="hypothesis", fail=["long warm-up (78 bars)", "lag"])

st("ichimoku_cloud_break", "Ichimoku cloud breakout", F, "Ichimoku", mech="price leaving the equilibrium (cloud) zone",
   logic="breakout", anchor="Ichimoku cloud",
   hyp="A close through the whole cloud after being inside or below it signals the market has left its equilibrium zone.",
   entry={"long": "cross_above(close, max(ichimoku(9,26,52).span_a, ichimoku(9,26,52).span_b))",
          "short": "cross_below(close, min(ichimoku(9,26,52).span_a, ichimoku(9,26,52).span_b))"},
   stop={"type": "atr", "mult": 2.0, "n": 14}, target={"type": "r", "r": 2.0}, research="hypothesis")

st("donchian_breakout", "Donchian channel breakout (intraday Turtle)", F, "channel breakout",
   mech="new N-bar extremes precede continuation (trading-range break)", logic="breakout", anchor="20-bar high/low",
   hyp="A close beyond the prior 20-bar range means the market accepted prices outside its recent range; exit on a 10-bar opposite extreme.",
   entry={"long": "close > donchian(20).upper[1]", "short": "close < donchian(20).lower[1]"},
   stop={"type": "atr", "mult": 2.0, "n": 20},
   exit={"long": "close < donchian(10).lower[1]", "short": "close > donchian(10).upper[1]"},
   ev=[("SRC-090", "origin", "Turtle 20/10 channel rules on daily futures"),
       ("SRC-040", "mechanism", "trading-range-break rules, daily DJIA"), ("SRC-033", "mechanism", "range break-outs tested on Bitcoin")],
   research="incompletely sourced", fail=["false breakouts in ranges", "intraday ranges are narrow relative to costs"])

st("linreg_trend_quality", "Regression-slope trend with R-squared filter", F, "statistical trend",
   mech="persistent drift measured by a least-squares slope with a goodness-of-fit filter", logic="continuation",
   anchor="linreg(close,50)",
   hyp="When the 50-bar regression slope is positive and the fit is tight (R^2 > 0.6), price is trending smoothly and tends to continue.",
   entry={"long": "linreg(close,50).slope > 0 and linreg(close,50).r2 > 0.6 and linreg(close,50).r2[1] <= 0.6",
          "short": "linreg(close,50).slope < 0 and linreg(close,50).r2 > 0.6 and linreg(close,50).r2[1] <= 0.6"},
   stop={"type": "atr", "mult": 2.0, "n": 14}, exit={"long": "linreg(close,50).slope < 0", "short": "linreg(close,50).slope > 0"},
   research="hypothesis")

st("kama_efficiency_cross", "Kaufman adaptive-average cross in efficient markets", F, "adaptive average",
   mech="adaptive smoothing: fast when price moves efficiently, slow in noise", logic="continuation", anchor="KAMA(10,2,30), ER(10)",
   hyp="Price crossing an adaptive average while the efficiency ratio is high marks a directional (not noisy) move.",
   entry={"long": "cross_above(close, kama(close,10,2,30)) and er(close,10) > 0.3",
          "short": "cross_below(close, kama(close,10,2,30)) and er(close,10) > 0.3"},
   stop={"type": "atr", "mult": 2.0, "n": 14}, exit={"long": "cross_below(close, kama(close,10,2,30))",
                                                    "short": "cross_above(close, kama(close,10,2,30))"},
   ev=[("SRC-082", "origin", "KAMA and efficiency ratio")], research="incompletely sourced")

st("heikin_ashi_trend", "Heikin-Ashi trend run", F, "smoothed candles",
   mech="consecutive smoothed candles without counter-trend wicks mark strong one-sided flow", logic="continuation",
   anchor="Heikin-Ashi",
   hyp="Three bullish Heikin-Ashi candles with no lower shadow show uninterrupted buying; exit at the first bearish candle.",
   entry={"long": "persist(heikin_ashi().close > heikin_ashi().open and heikin_ashi().low >= heikin_ashi().open, 3)",
          "short": "persist(heikin_ashi().close < heikin_ashi().open and heikin_ashi().high <= heikin_ashi().open, 3)"},
   stop={"type": "atr", "mult": 1.5, "n": 14},
   exit={"long": "heikin_ashi().close < heikin_ashi().open", "short": "heikin_ashi().close > heikin_ashi().open"},
   research="hypothesis")

st("aroon_trend", "Aroon trend emergence", F, "time-since-extreme",
   mech="recency of the latest high vs latest low", logic="continuation", anchor="Aroon(25)",
   hyp="When the most recent 25-bar high is much more recent than the most recent low (Aroon-up > 70 crossing Aroon-down), an uptrend is emerging.",
   entry={"long": "cross_above(aroon(25).up, aroon(25).down) and aroon(25).up > 70",
          "short": "cross_above(aroon(25).down, aroon(25).up) and aroon(25).down > 70"},
   stop={"type": "atr", "mult": 2.0, "n": 14}, target={"type": "r", "r": 2.0},
   ev=[("SRC-083", "origin", "Aroon")], research="incompletely sourced")

st("mtf_momentum_alignment", "Multi-horizon momentum alignment breakout", F, "multi-timeframe",
   mech="agreement of momentum across 15m/1h/4h before a local breakout", logic="continuation", anchor="ROC on 3 horizons",
   hyp="A breakout on the trading timeframe works better when 15-minute, 1-hour and 4-hour momentum all point the same way.",
   tf="5m",
   entry={"long": "tf(\"15m\", roc(close,8)) > 0 and tf(\"1h\", roc(close,6)) > 0 and tf(\"4h\", roc(close,6)) > 0 and close > highest(high,12)[1]",
          "short": "tf(\"15m\", roc(close,8)) < 0 and tf(\"1h\", roc(close,6)) < 0 and tf(\"4h\", roc(close,6)) < 0 and close < lowest(low,12)[1]"},
   stop={"type": "atr", "mult": 2.0, "n": 14}, target={"type": "r", "r": 2.0}, markets=CRYPTO,
   ev=[("SRC-047", "mechanism", "time-series momentum at 1-12 month horizons (not intraday)")], research="hypothesis",
   notes="Crypto only: Yahoo does not publish 4h bars.")

st("trend_return_sign", "Previous-day return sign (intraday time-series momentum)", F, "time-series momentum",
   mech="persistence of the sign of recent returns", logic="continuation", anchor="24h return",
   hyp="Trade today's session in the direction of the last 24 hours' return, sized to a volatility stop.",
   tf="1h", markets=CRYPTO,
   entry={"long": "bar_in_session() == 0 and pct(close,24) > 0", "short": "bar_in_session() == 0 and pct(close,24) < 0"},
   stop={"type": "atr", "mult": 2.5, "n": 24}, mtd=1,
   ev=[("SRC-047", "mechanism", "monthly-horizon time-series momentum in futures"),
       ("SRC-030", "mechanism", "intraday momentum and reversal both present in Bitcoin")], research="hypothesis")
