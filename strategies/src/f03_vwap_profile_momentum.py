"""Families: VWAP anchors; volume/market profile; momentum & oscillators; mean reversion; volatility."""
from lib import BOTH, CRYPTO, STOCK, st, variant

V = "vwap"
st("vwap_trend_pullback", "VWAP pullback in a trending session", V, "session VWAP", mech="VWAP as the average cost of the day's participants acts as support in trends",
   logic="continuation (pullback)", anchor="session VWAP",
   hyp="After 30 minutes above a rising VWAP, a touch of VWAP that closes back above it with a bullish body resumes the trend.",
   entry={"long": "persist(close > vwap(), 6)[1] and vwap() > vwap()[6] and low <= vwap() and close > vwap() and close > open",
          "short": "persist(close < vwap(), 6)[1] and vwap() < vwap()[6] and high >= vwap() and close < vwap() and close < open"},
   stop={"type": "level", "long": "vwap()", "short": "vwap()", "buffer_atr": 0.5, "n": 14}, target={"type": "r", "r": 2.0},
   mtd=2, research="hypothesis")
st("vwap_band_reversion", "VWAP 2-sigma band reversion", V, "VWAP bands", mech="intraday overextension from the volume-weighted mean reverts",
   logic="reversal", anchor="VWAP +/- 2 sd",
   hyp="A close back inside the 2-standard-deviation VWAP band after trading outside it reverts toward VWAP.",
   entry={"long": "cross_above(close, vwap().lower2)", "short": "cross_below(close, vwap().upper2)"},
   stop={"type": "level", "long": "session().low", "short": "session().high", "buffer_atr": 0.25, "n": 14},
   target={"type": "level", "long": "vwap()", "short": "vwap()"}, mtd=2, research="hypothesis")
variant("first_hour_vwap_fade", "vwap_band_reversion", "First-hour VWAP extension fade", "time window 10:00-11:00 ET only")
variant("vwap_zscore_reversion", "vwap_band_reversion", "VWAP-distance z-score reversion", "z-score of close - VWAP instead of VWAP bands")
variant("weekend_band_reversion", "vwap_band_reversion", "Weekend band reversion (crypto)", "only on Saturday/Sunday UTC")
st("vwap_band_breakout", "VWAP 1-sigma band breakout with volume", V, "VWAP bands", mech="acceptance above the upper band with volume signals trend day",
   logic="breakout", anchor="VWAP + 1 sd",
   hyp="After 10:30, a close above the upper 1-sd band with relative volume above 1.5 and a rising VWAP extends; trail at VWAP.",
   entry={"long": "cross_above(close, vwap().upper1) and rvol(20) > 1.5 and vwap() > vwap()[6] and minutes_since_open() >= 60",
          "short": "cross_below(close, vwap().lower1) and rvol(20) > 1.5 and vwap() < vwap()[6] and minutes_since_open() >= 60"},
   stop={"type": "level", "long": "vwap()", "short": "vwap()"},
   trail={"type": "level", "long": "vwap()", "short": "vwap()"}, mtd=1, research="hypothesis")
st("vwap_reclaim", "VWAP reclaim after a sustained move below", V, "session VWAP", mech="shift of control when price regains the day's average cost",
   logic="reversal", anchor="session VWAP",
   hyp="After 30 minutes below VWAP, the first close back above it flips intraday control to buyers; target the upper band.",
   entry={"long": "persist(close < vwap(), 6)[1] and cross_above(close, vwap())",
          "short": "persist(close > vwap(), 6)[1] and cross_below(close, vwap())"},
   stop={"type": "level", "long": "session().low", "short": "session().high"},
   target={"type": "level", "long": "vwap().upper1", "short": "vwap().lower1"}, mtd=2, research="hypothesis")
st("avwap_swing_support", "Anchored VWAP from the last swing low", V, "anchored VWAP", mech="the average cost of buyers since the last swing low is defended",
   logic="continuation (pullback)", anchor="AVWAP from each newly confirmed swing low",
   hyp="VWAP anchored at the latest confirmed swing low is a support line; a touch that closes back above it resumes the up-leg.",
   entry={"long": "low <= avwap(swings(5).low != swings(5).low[1]) and close > avwap(swings(5).low != swings(5).low[1]) and close > open and close > ema(close,50)",
          "short": "high >= avwap(swings(5).high != swings(5).high[1]) and close < avwap(swings(5).high != swings(5).high[1]) and close < open and close < ema(close,50)"},
   stop={"type": "atr", "mult": 1.5, "n": 14}, target={"type": "r", "r": 2.0}, research="hypothesis",
   notes="Anchored at the bar where the swing is CONFIRMED (n bars after the swing), so it never uses future bars.")
variant("avwap_prior_close", "avwap_swing_support", "Anchored VWAP from the prior session close", "anchor at the prior session's last bar")
st("avwap_volume_event", "Anchored VWAP from a volume shock", V, "anchored VWAP", mech="a climactic-volume bar marks where a large participant traded; its AVWAP is their break-even",
   logic="breakout", anchor="AVWAP from bars with relative volume > 4",
   hyp="Price reclaiming the VWAP anchored at the latest 4x-volume bar shows the event's participants are back in profit.",
   entry={"long": "cross_above(close, avwap(rvol(20) > 4))", "short": "cross_below(close, avwap(rvol(20) > 4))"},
   stop={"type": "atr", "mult": 1.5, "n": 14}, target={"type": "r", "r": 2.0}, research="hypothesis")

P = "market_profile"
st("value_area_80_rule", "Market Profile 80% rule", P, "value area", mech="an open outside yesterday's value that is accepted back inside tends to traverse the value area",
   logic="reversal / rotation", anchor="prior session VAH/VAL",
   hyp="If the session opens below yesterday's value-area low and then holds inside the value area for 30 minutes, it tends to reach the value-area high.",
   markets=STOCK, tf="5m",
   entry={"long": "session().open < volume_profile(40,0.7).val and persist(close > volume_profile(40,0.7).val, 6)",
          "short": "session().open > volume_profile(40,0.7).vah and persist(close < volume_profile(40,0.7).vah, 6)"},
   stop={"type": "level", "long": "volume_profile(40,0.7).val", "short": "volume_profile(40,0.7).vah", "buffer_atr": 0.5, "n": 14},
   target={"type": "level", "long": "volume_profile(40,0.7).vah", "short": "volume_profile(40,0.7).val"}, mtd=1,
   ev=[("SRC-078", "origin", "Market Profile value area")], research="incompletely sourced",
   notes="Value area is approximated from OHLCV bars (not trade-level volume at price).")
st("value_area_acceptance_breakout", "Value-area breakout with acceptance", P, "value area", mech="acceptance of prices outside prior value starts a new value area",
   logic="breakout", anchor="prior session VAH/VAL",
   hyp="After opening inside yesterday's value area, 30 minutes of closes above the value-area high mean acceptance; target one value-area width higher.",
   markets=BOTH, tf="5m",
   entry={"long": "session().open < volume_profile(40,0.7).vah and persist(close > volume_profile(40,0.7).vah, 6) and not persist(close > volume_profile(40,0.7).vah, 7)",
          "short": "session().open > volume_profile(40,0.7).val and persist(close < volume_profile(40,0.7).val, 6) and not persist(close < volume_profile(40,0.7).val, 7)"},
   stop={"type": "level", "long": "volume_profile(40,0.7).vah", "short": "volume_profile(40,0.7).val", "buffer_atr": 0.25, "n": 14},
   target={"type": "level", "long": "volume_profile(40,0.7).vah + (volume_profile(40,0.7).vah - volume_profile(40,0.7).val)",
           "short": "volume_profile(40,0.7).val - (volume_profile(40,0.7).vah - volume_profile(40,0.7).val)"}, mtd=1,
   ev=[("SRC-078", "origin", "value area acceptance")], research="incompletely sourced")
st("poc_magnet", "Reversion to the prior point of control", P, "point of control", mech="the prior session's most traded price attracts price when momentum fades",
   logic="reversal", anchor="prior POC",
   hyp="Mid-session, more than 1 ATR away from yesterday's POC with RSI turning, price rotates back toward the POC.",
   entry={"long": "volume_profile(40,0.7).poc - close > atr(14) * 3 and cross_above(rsi(close,14), 35)",
          "short": "close - volume_profile(40,0.7).poc > atr(14) * 3 and cross_below(rsi(close,14), 65)"},
   stop={"type": "atr", "mult": 1.5, "n": 14}, target={"type": "level", "long": "volume_profile(40,0.7).poc", "short": "volume_profile(40,0.7).poc"},
   mtd=1, research="hypothesis")
st("poc_migration_trend", "Developing POC migration (trend day)", P, "point of control", mech="value moving with price indicates a trend day",
   logic="continuation", anchor="developing POC",
   hyp="When the developing POC has risen over the last hour and price holds above it and VWAP, the session is trending; hold to the close.",
   entry={"long": "volume_profile(40,0.7).dev_poc > volume_profile(40,0.7).dev_poc[12] and close > volume_profile(40,0.7).dev_poc and close > vwap() and minutes_since_open() >= 120",
          "short": "volume_profile(40,0.7).dev_poc < volume_profile(40,0.7).dev_poc[12] and close < volume_profile(40,0.7).dev_poc and close < vwap() and minutes_since_open() >= 120"},
   stop={"type": "level", "long": "volume_profile(40,0.7).dev_poc", "short": "volume_profile(40,0.7).dev_poc", "buffer_atr": 0.3, "n": 14},
   mtd=1, research="hypothesis")
st("trend_day_hold", "Trend-day identification and hold", P, "day type", mech="Market Profile trend days close near their extreme",
   logic="continuation", anchor="range extension + VWAP persistence",
   hyp="After 11:00, if price is in the top 10% of the day's range, has held above VWAP for 90% of bars and extended above the first hour, hold long to the close.",
   markets=STOCK, tf="5m",
   entry={"long": "tod() >= 660 and close > session().high - 0.1*(session().high - session().low) and count(close > vwap(), 18) >= 16 and session().high > opening_range(60).high",
          "short": "tod() >= 660 and close < session().low + 0.1*(session().high - session().low) and count(close < vwap(), 18) >= 16 and session().low < opening_range(60).low"},
   stop={"type": "level", "long": "vwap()", "short": "vwap()"}, mtd=1,
   ev=[("SRC-078", "origin", "day types incl. trend day")], research="incompletely sourced")

M = "momentum"
st("cci_trend_breakout", "CCI +100 trend entry (Lambert)", M, "oscillator thrust", mech="price moving well above its statistical mean starts a cyclical up-move",
   logic="continuation", anchor="CCI(20)",
   hyp="CCI crossing above +100 marks the start of an up-cycle; exit when it falls back below +100.",
   entry={"long": "cross_above(cci(20), 100)", "short": "cross_below(cci(20), -100)"},
   stop={"type": "atr", "mult": 2.0, "n": 14}, exit={"long": "cross_below(cci(20), 100)", "short": "cross_above(cci(20), -100)"},
   ev=[("SRC-079", "origin", "CCI and its +/-100 signals")], research="incompletely sourced")
st("stochastic_pop", "Stochastic pop (momentum thrust)", M, "oscillator thrust", mech="an overbought reading after a quiet period is strength, not weakness",
   logic="continuation", anchor="Stochastic(14,3,3), ADX",
   hyp="When %K pushes above 80 while ADX is still below 20 (a new move out of a range), momentum continues until %K drops below 70.",
   entry={"long": "cross_above(stoch(14,3,3).k, 80) and adx(14).adx < 20", "short": "cross_below(stoch(14,3,3).k, 20) and adx(14).adx < 20"},
   stop={"type": "atr", "mult": 1.5, "n": 14}, exit={"long": "stoch(14,3,3).k < 70", "short": "stoch(14,3,3).k > 30"},
   research="hypothesis")
st("roc_ignition", "Momentum ignition (ROC shock)", M, "return shock", mech="unusually large short-horizon returns attract momentum followers",
   logic="continuation", anchor="5-bar ROC vs its 100-bar dispersion",
   hyp="A 5-bar return more than two standard deviations above its recent distribution continues briefly; trail an ATR stop.",
   entry={"long": "zscore(roc(close,5), 100) > 2 and close > vwap()", "short": "zscore(roc(close,5), 100) < -2 and close < vwap()"},
   stop={"type": "atr", "mult": 1.5, "n": 14}, trail={"type": "atr", "mult": 2.0, "n": 14, "activate_r": 0.5}, max_bars=12,
   research="hypothesis")
st("ao_saucer", "Awesome Oscillator saucer", M, "oscillator pattern", mech="a brief dip in momentum above zero precedes the next thrust",
   logic="continuation", anchor="Awesome Oscillator",
   hyp="With AO above zero, two falling AO bars followed by a rising bar mark the end of a pause.",
   entry={"long": "ao() > 0 and ao()[1] < ao()[2] and ao()[2] < ao()[3] and ao() > ao()[1]",
          "short": "ao() < 0 and ao()[1] > ao()[2] and ao()[2] > ao()[3] and ao() < ao()[1]"},
   stop={"type": "atr", "mult": 1.5, "n": 14}, target={"type": "r", "r": 1.5}, research="hypothesis")
st("momentum_pinball", "Momentum Pinball (Raschke)", M, "named setup", mech="short-term oversold daily momentum resolves by a first-hour breakout",
   logic="reversal-to-continuation", anchor="RSI(3) of daily 1-day ROC + first-hour range",
   hyp="When RSI(3) of the daily 1-day rate of change is below 30, buy a break above the first hour's high.",
   markets=STOCK, tf="5m",
   entry={"long": "tf(\"1d\", rsi(roc(close,1),3)) < 30 and cross_above(close, opening_range(60).high)",
          "short": "tf(\"1d\", rsi(roc(close,1),3)) > 70 and cross_below(close, opening_range(60).low)"},
   stop={"type": "level", "long": "opening_range(60).low", "short": "opening_range(60).high"}, mtd=1,
   ev=[("SRC-071", "origin", "Momentum Pinball (book; rules not read here)")], research="incompletely sourced")

R = "mean_reversion"
st("rsi2_pullback", "RSI(2) pullback in an uptrend (Connors)", R, "oscillator extreme", mech="short pullbacks inside a longer uptrend revert",
   logic="reversal (pullback)", anchor="RSI(2), SMA(200), SMA(5)",
   hyp="With price above its 200-bar average, an RSI(2) reading below 5 is a buying opportunity; exit on a close above the 5-bar average.",
   entry={"long": "rsi(close,2) < 5 and close > sma(close,200)", "short": "rsi(close,2) > 95 and close < sma(close,200)"},
   stop={"type": "atr", "mult": 3.0, "n": 14}, exit={"long": "close > sma(close,5)", "short": "close < sma(close,5)"},
   max_bars=20, mtd=3, ev=[("SRC-072", "origin", "2-period RSI strategies on daily bars (book)")], research="incompletely sourced",
   notes="Originally daily bars; intraday use is an adaptation.")
variant("rsi14_30_70", "rsi2_pullback", "RSI(14) 30/70 reversal", "period 14, thresholds 30/70, no trend filter")
variant("connors_rsi_pullback", "rsi2_pullback", "ConnorsRSI pullback", "ConnorsRSI(3,2,100) < 10")
variant("stoch_oversold_cross", "rsi2_pullback", "Stochastic oversold cross", "%K/%D cross below 20")
variant("stochrsi_extreme", "rsi2_pullback", "StochRSI extreme", "StochRSI %K below 10")
variant("williams_r_reversal", "rsi2_pullback", "Williams %R reversal", "%R below -90 turning up")
variant("fisher_reversal", "rsi2_pullback", "Fisher transform reversal", "Fisher(10) crossing its signal below -1.5")
st("bollinger_fade", "Bollinger Band re-entry fade", R, "volatility bands", mech="closes back inside the band after a 2-sd excursion revert to the mean",
   logic="reversal", anchor="BB(20,2)",
   hyp="A close back above the lower band after closing below it reverts toward the 20-bar mean.",
   entry={"long": "close[1] < bb(close,20,2).lower[1] and close > bb(close,20,2).lower",
          "short": "close[1] > bb(close,20,2).upper[1] and close < bb(close,20,2).upper"},
   stop={"type": "atr", "mult": 1.5, "n": 14}, target={"type": "level", "long": "bb(close,20,2).mid", "short": "bb(close,20,2).mid"},
   ev=[("SRC-075", "origin", "Bollinger Bands (book)")], research="incompletely sourced")
variant("keltner_fade", "bollinger_fade", "Keltner channel fade", "Keltner(20,2,10) instead of Bollinger")
variant("zscore_sma_reversion", "bollinger_fade", "Z-score reversion to SMA(20)", "z-score < -2 instead of band re-entry")
variant("ema_overextension_fade", "bollinger_fade", "Overextension from EMA(20) fade", "distance > 3 ATR from EMA(20)")
st("ibs_reversal", "Internal bar strength reversal", R, "bar position", mech="closes at the very bottom of a bar's range tend to be followed by bounces",
   logic="reversal", anchor="IBS",
   hyp="A bar closing in the bottom 15% of its range above the 200-bar average bounces; exit when IBS > 0.7 or after 5 bars.",
   entry={"long": "candle().ibs < 0.15 and close > sma(close,200)", "short": "candle().ibs > 0.85 and close < sma(close,200)"},
   stop={"type": "atr", "mult": 2.0, "n": 14}, exit={"long": "candle().ibs > 0.7", "short": "candle().ibs < 0.3"}, max_bars=5,
   research="hypothesis")
st("down_streak_reversion", "Consecutive down closes reversion", R, "streak", mech="runs of same-direction closes exhaust short-term order flow",
   logic="reversal", anchor="close streak",
   hyp="Four or more consecutive lower closes above the 200-bar EMA bounce; exit on the first higher close.",
   entry={"long": "streak() <= -4 and close > ema(close,200)", "short": "streak() >= 4 and close < ema(close,200)"},
   stop={"type": "atr", "mult": 2.0, "n": 14}, exit={"long": "streak() > 0", "short": "streak() < 0"}, max_bars=10,
   ev=[("SRC-014", "mechanism", "short-term reversal (monthly horizon)")], research="hypothesis")
variant("double_sevens", "down_streak_reversion", "Double 7s (7-bar low in uptrend)", "trigger: close at 7-bar low; exit at 7-bar high", ev=[("SRC-072", "origin", "")])
st("td_setup_exhaustion", "TD Sequential setup-9 exhaustion", R, "count exhaustion", mech="nine closes against the close 4 bars earlier marks exhaustion",
   logic="reversal", anchor="TD setup count",
   hyp="When the buy-setup count reaches 9, the decline is exhausted; buy with a stop under the setup's low.",
   entry={"long": "td_setup(4).buy == 9", "short": "td_setup(4).sell == 9"},
   stop={"type": "level", "long": "lowest(low,9)", "short": "highest(high,9)", "buffer_atr": 0.25, "n": 14},
   target={"type": "r", "r": 1.5}, max_bars=12, ev=[("SRC-080", "origin", "TD Sequential (book)")], research="incompletely sourced")
st("linreg_channel_reversion", "Regression-channel reversion", R, "trend line", mech="deviations from a fitted trend line revert while the trend holds",
   logic="reversal", anchor="linreg(close,100) +/- 2 sd of residual",
   hyp="A close more than two residual standard deviations below the 100-bar regression line reverts toward the line.",
   entry={"long": "close < linreg(close,100).value - 2*std(close - linreg(close,100).value, 100) and linreg(close,100).slope >= 0",
          "short": "close > linreg(close,100).value + 2*std(close - linreg(close,100).value, 100) and linreg(close,100).slope <= 0"},
   stop={"type": "atr", "mult": 2.0, "n": 14}, target={"type": "level", "long": "linreg(close,100).value", "short": "linreg(close,100).value"},
   research="hypothesis")
st("shock_bar_reversal", "Volatility-shock bar reversal", R, "range shock", mech="panic bars overshoot fair value and partially retrace",
   logic="reversal", anchor="bar range vs ATR",
   hyp="A bar whose range exceeds 3 ATR and closes near its extreme retraces part of the move over the next bars.",
   entry={"long": "high - low > 3*atr(14)[1] and close < low + 0.25*(high - low)", "short": "high - low > 3*atr(14)[1] and close > high - 0.25*(high - low)"},
   stop={"type": "atr", "mult": 1.5, "n": 14}, target={"type": "level", "long": "(high + low)/2", "short": "(high + low)/2"}, max_bars=6,
   ev=[("SRC-014", "mechanism", "short-term reversal")], research="hypothesis")
variant("return_percentile_reversal", "shock_bar_reversal", "30-minute return percentile reversal", "trigger on pctrank of 6-bar return < 5")
st("mass_index_bulge", "Mass Index reversal bulge (Dorsey)", R, "range expansion", mech="range expansion then contraction marks trend exhaustion",
   logic="reversal", anchor="Mass Index(9,25)",
   hyp="After the Mass Index rises above 27 and falls back below 26.5, trade against the prevailing 9-EMA direction.",
   entry={"long": "within(mass_index(9,25) > 27, 10) and cross_below(mass_index(9,25), 26.5) and ema(close,9) < ema(close,9)[5]",
          "short": "within(mass_index(9,25) > 27, 10) and cross_below(mass_index(9,25), 26.5) and ema(close,9) > ema(close,9)[5]"},
   stop={"type": "atr", "mult": 2.0, "n": 14}, target={"type": "r", "r": 1.5},
   ev=[("SRC-085", "origin", "Mass Index reversal bulge")], research="incompletely sourced")
st("rsi_divergence", "RSI bullish/bearish divergence", R, "divergence", mech="momentum failing to confirm a new price extreme",
   logic="reversal", anchor="RSI(14) vs price over 20 bars",
   hyp="A new 20-bar low with RSI(14) higher than at the previous 20-bar low shows waning selling; buy on the next up close.",
   entry={"long": "low <= lowest(low,20) and rsi(close,14) > valuewhen(low <= lowest(low,20), rsi(close,14))[5] and close > open",
          "short": "high >= highest(high,20) and rsi(close,14) < valuewhen(high >= highest(high,20), rsi(close,14))[5] and close < open"},
   stop={"type": "atr", "mult": 1.5, "n": 14}, target={"type": "r", "r": 2.0}, research="hypothesis")
variant("macd_divergence", "rsi_divergence", "MACD divergence", "MACD line instead of RSI")
variant("uo_divergence", "rsi_divergence", "Ultimate Oscillator divergence (Williams)", "Ultimate Oscillator with break of divergence high")

X = "volatility"
st("bb_squeeze_breakout", "Bollinger squeeze breakout", X, "compression", mech="volatility compression precedes expansion",
   logic="breakout", anchor="BB width at a 120-bar low",
   hyp="When Bollinger bandwidth is near its 120-bar low, the next close outside the bands starts an expansion move.",
   entry={"long": "within(bb(close,20,2).width <= 1.1*lowest(bb(close,20,2).width, 120), 6) and cross_above(close, bb(close,20,2).upper)",
          "short": "within(bb(close,20,2).width <= 1.1*lowest(bb(close,20,2).width, 120), 6) and cross_below(close, bb(close,20,2).lower)"},
   stop={"type": "level", "long": "bb(close,20,2).mid", "short": "bb(close,20,2).mid"}, target={"type": "r", "r": 2.0},
   ev=[("SRC-075", "origin", "The Squeeze, ch.15-16 (book)")], research="incompletely sourced")
variant("ttm_squeeze_fire", "bb_squeeze_breakout", "TTM Squeeze fire (Carter)", "compression = Bollinger inside Keltner; direction from squeeze momentum", ev=[("SRC-077", "origin", "")])
variant("vcp_breakout", "bb_squeeze_breakout", "Volatility contraction pattern breakout", "successively smaller pullbacks, then breakout")
st("nr7_breakout", "NR7 breakout bracket (Crabel)", X, "narrow range", mech="the narrowest bar of seven precedes range expansion",
   logic="breakout", anchor="NR7 bar high/low",
   hyp="After the narrowest-range bar of the last seven, a bracket (one-cancels-other) at its high and low catches the expansion.",
   entry={"long": "nr(7) == 1", "short": "nr(7) == 1"},
   order={"type": "oco", "long": "high", "short": "low", "ttl_bars": 3},
   stop={"type": "atr", "mult": 1.0, "n": 14}, target={"type": "r", "r": 2.0},
   ev=[("SRC-070", "origin", "narrow-range patterns (book)")], research="incompletely sourced")
variant("inside_bar_breakout", "nr7_breakout", "Inside-bar breakout bracket", "trigger: inside bar instead of NR7")
variant("nr4_inside", "nr7_breakout", "NR4 inside-bar bracket", "NR4 and inside bar together")
st("keltner_breakout", "Keltner channel breakout", X, "volatility bands", mech="closes beyond an ATR band signal directional expansion",
   logic="breakout", anchor="Keltner(20,2,10)",
   hyp="A close above the upper Keltner band continues until price closes back below the midline.",
   entry={"long": "cross_above(close, kc(20,2,10).upper)", "short": "cross_below(close, kc(20,2,10).lower)"},
   stop={"type": "level", "long": "kc(20,2,10).mid", "short": "kc(20,2,10).mid"},
   exit={"long": "close < kc(20,2,10).mid", "short": "close > kc(20,2,10).mid"},
   ev=[("SRC-091", "origin", "Keltner's ten-day moving average rule")], research="incompletely sourced")
variant("bollinger_breakout", "keltner_breakout", "Bollinger band breakout", "Bollinger(20,2) bands")
st("range_expansion_continuation", "Range-expansion bar continuation", X, "expansion", mech="an unusually wide bar closing at its extreme shows urgent one-sided demand",
   logic="continuation", anchor="true range vs ATR(20)",
   hyp="A bar with true range above twice ATR(20) that closes in its top 20% continues over the next few bars.",
   entry={"long": "high - low > 2*atr(20)[1] and close > high - 0.2*(high - low) and rvol(20) > 1.5",
          "short": "high - low > 2*atr(20)[1] and close < low + 0.2*(high - low) and rvol(20) > 1.5"},
   stop={"type": "level", "long": "(high + low)/2", "short": "(high + low)/2"}, target={"type": "r", "r": 1.5}, max_bars=6,
   research="hypothesis", distinct="Continuation after a wide bar; shock_bar_reversal fades wider bars that close at the extreme opposite.")
variant("marubozu_continuation", "range_expansion_continuation", "Marubozu continuation", "trigger defined by candle body >= 90% of range")
