"""Families: candlestick patterns; chart/structure patterns; volume & money flow; time-of-day & calendar; events."""
from lib import BOTH, CRYPTO, STOCK, st, variant

C = "candlestick"
CEV = [("SRC-088", "origin", "candlestick definitions (book)"), ("SRC-045", "contrary", "no value vs random trading on DJIA stocks")]
st("engulfing_at_swing", "Engulfing candle at a 10-bar extreme", C, "reversal candle", mech="a full-body reversal at a local extreme",
   logic="reversal", anchor="10-bar low/high",
   hyp="A bullish engulfing bar whose low is the lowest of 10 bars signals a local reversal.",
   entry={"long": "candle().bull_engulf == 1 and low <= lowest(low,10)", "short": "candle().bear_engulf == 1 and high >= highest(high,10)"},
   stop={"type": "level", "long": "low", "short": "high", "buffer_atr": 0.1, "n": 14}, target={"type": "r", "r": 2.0}, max_bars=24,
   ev=CEV, research="incompletely sourced")
st("pin_bar_at_level", "Hammer / shooting star at prior-session level", C, "rejection candle", mech="long rejection wick at a known level",
   logic="reversal", anchor="prior-session low/high",
   hyp="A hammer whose low tests yesterday's low (within 0.2 ATR) shows rejection of lower prices.",
   entry={"long": "candle().hammer == 1 and abs(low - session().prev_low) < 0.2*atr(14)",
          "short": "candle().shooting_star == 1 and abs(high - session().prev_high) < 0.2*atr(14)"},
   stop={"type": "level", "long": "low", "short": "high", "buffer_atr": 0.1, "n": 14}, target={"type": "r", "r": 2.0}, max_bars=24,
   ev=CEV, research="incompletely sourced")
variant("doji_at_level", "pin_bar_at_level", "Doji at prior-session level", "doji instead of hammer")
st("morning_star", "Morning star / evening star", C, "three-bar reversal", mech="selling climax, indecision, then demand",
   logic="reversal", anchor="three-bar pattern",
   hyp="A strong bearish bar, a small indecision bar and a bullish close above the first bar's midpoint mark a turn.",
   entry={"long": "candle().morning_star == 1 and close < ema(close,50)", "short": "candle().evening_star == 1 and close > ema(close,50)"},
   stop={"type": "level", "long": "lowest(low,3)", "short": "highest(high,3)", "buffer_atr": 0.1, "n": 14}, target={"type": "r", "r": 2.0},
   max_bars=24, ev=CEV, research="incompletely sourced")
st("three_soldiers", "Three white soldiers / three black crows continuation", C, "continuation pattern", mech="three strong same-direction closes show sustained demand",
   logic="continuation", anchor="three-bar pattern",
   hyp="Three rising bullish bars opening inside the prior body and closing near highs continue the move.",
   entry={"long": "candle().three_soldiers == 1", "short": "candle().three_crows == 1"},
   stop={"type": "level", "long": "low[2]", "short": "high[2]"}, target={"type": "r", "r": 1.5}, max_bars=12, ev=CEV, research="incompletely sourced")
st("outside_bar_reversal", "Outside-bar reversal", C, "range engulfing", mech="a bar engulfing the prior range and closing strong reverses a down-move",
   logic="reversal", anchor="outside bar after a decline",
   hyp="After a 5-bar decline, an outside bar closing in its top quarter reverses the move.",
   entry={"long": "candle().outside == 1 and close > high - 0.25*(high - low) and close[1] < close[6]",
          "short": "candle().outside == 1 and close < low + 0.25*(high - low) and close[1] > close[6]"},
   stop={"type": "level", "long": "low", "short": "high"}, target={"type": "r", "r": 1.5}, max_bars=12, ev=CEV, research="hypothesis")

S = "market_structure"
st("break_of_structure", "Break of structure after a higher low", S, "swing structure", mech="a close above the last swing high after a higher low confirms an up-trend",
   logic="continuation", anchor="confirmed swing points",
   hyp="Once a higher swing low is in place, a close above the most recent swing high starts the next leg.",
   entry={"long": "swings(3).low > swings(3).low_prev and cross_above(close, swings(3).high)",
          "short": "swings(3).high < swings(3).high_prev and cross_below(close, swings(3).low)"},
   stop={"type": "level", "long": "swings(3).low", "short": "swings(3).high", "buffer_atr": 0.1, "n": 14}, target={"type": "r", "r": 2.0},
   research="hypothesis", notes="Swings are published only after confirmation (3 bars), so no repainting.")
variant("change_of_character", "break_of_structure", "Change of character", "first break against the prior trend")
st("double_bottom", "Double bottom / double top", S, "chart pattern", mech="two failed tests of the same level followed by a neckline break",
   logic="reversal", anchor="last two swing lows + intervening swing high",
   hyp="Two swing lows within 0.3 ATR of each other followed by a close above the swing high between them complete a double bottom.",
   entry={"long": "abs(swings(3).low - swings(3).low_prev) < 0.3*atr(14) and cross_above(close, swings(3).high)",
          "short": "abs(swings(3).high - swings(3).high_prev) < 0.3*atr(14) and cross_below(close, swings(3).low)"},
   stop={"type": "level", "long": "min(swings(3).low, swings(3).low_prev)", "short": "max(swings(3).high, swings(3).high_prev)"},
   target={"type": "r", "r": 2.0}, ev=[("SRC-044", "origin", "algorithmic chart-pattern definitions"), ("SRC-089", "origin", "")],
   research="incompletely sourced")
st("head_and_shoulders", "Head-and-shoulders breakdown", S, "chart pattern", mech="a failed higher high between two lower peaks, then neckline break",
   logic="reversal", anchor="three confirmed swing highs",
   hyp="A head at least 0.5 ATR above two shoulders that are within 1 ATR of each other, then a close below the latest swing low, reverses the trend.",
   entry={"short": "swings(3).high_prev > swings(3).high + 0.5*atr(14) and swings(3).high_prev > swings(3).high_prev2 + 0.5*atr(14) and abs(swings(3).high - swings(3).high_prev2) < atr(14) and cross_below(close, swings(3).low)",
          "long": "swings(3).low_prev < swings(3).low - 0.5*atr(14) and swings(3).low_prev < swings(3).low_prev2 - 0.5*atr(14) and abs(swings(3).low - swings(3).low_prev2) < atr(14) and cross_above(close, swings(3).high)"},
   stop={"type": "level", "long": "swings(3).low", "short": "swings(3).high", "buffer_atr": 0.2, "n": 14}, target={"type": "r", "r": 2.0},
   ev=[("SRC-044", "origin", "kernel-regression pattern definitions"), ("SRC-089", "origin", "")], research="incompletely sourced")
st("bull_flag", "Flag after an impulse", S, "chart pattern", mech="shallow, low-volume consolidation after an impulse is a pause, not a reversal",
   logic="continuation", anchor="5-bar impulse + 6-bar consolidation",
   hyp="After a 5-bar move of more than 3 ATR, a 6-bar consolidation under half that size on falling volume breaks out in the impulse direction.",
   entry={"long": "change(close,11)[6] > 3*atr(14) and highest(high,6) - lowest(low,6) < 0.5*change(close,5)[6] and mean(volume,6) < mean(volume,5)[6] and close > highest(high,6)[1]",
          "short": "change(close,11)[6] < -3*atr(14) and highest(high,6) - lowest(low,6) < -0.5*change(close,5)[6] and mean(volume,6) < mean(volume,5)[6] and close < lowest(low,6)[1]"},
   stop={"type": "level", "long": "lowest(low,6)", "short": "highest(high,6)"}, target={"type": "r", "r": 2.0},
   ev=[("SRC-089", "origin", "flags (book)")], research="incompletely sourced")
st("triangle_breakout", "Converging-range (triangle) breakout", S, "chart pattern", mech="converging highs and lows compress then resolve",
   logic="breakout", anchor="20-bar regression slopes of highs and lows",
   hyp="With highs trending down and lows trending up over 20 bars, a close outside the 20-bar range resolves the triangle.",
   entry={"long": "linreg(high,20).slope < 0 and linreg(low,20).slope > 0 and close > highest(high,20)[1]",
          "short": "linreg(high,20).slope < 0 and linreg(low,20).slope > 0 and close < lowest(low,20)[1]"},
   stop={"type": "level", "long": "lowest(low,5)", "short": "highest(high,5)"}, target={"type": "r", "r": 2.0}, research="hypothesis")
st("fvg_fill_continuation", "Fair-value-gap fill continuation", S, "imbalance", mech="price returns to an inefficient three-bar gap, then resumes",
   logic="continuation (pullback)", anchor="latest bullish/bearish FVG",
   hyp="In an uptrend, the first return into a bullish fair-value gap that closes above its bottom resumes the trend.",
   entry={"long": "close > ema(close,50) and low <= fvg().bull_top and close > fvg().bull_bottom and close > open",
          "short": "close < ema(close,50) and high >= fvg().bear_bottom and close < fvg().bear_top and close < open"},
   stop={"type": "level", "long": "fvg().bull_bottom", "short": "fvg().bear_top", "buffer_atr": 0.2, "n": 14}, target={"type": "r", "r": 2.0},
   research="hypothesis")
st("fib_retracement", "Fibonacci 50-61.8% retracement entry", S, "retracement", mech="traders watch fixed retracement ratios of the last swing",
   logic="continuation (pullback)", anchor="last swing low -> swing high",
   hyp="In an up-leg, a pullback into 50-61.8% of the latest swing that closes bullish resumes the trend.",
   entry={"long": "swings(3).high > swings(3).low and close < swings(3).high - 0.5*(swings(3).high - swings(3).low) and low > swings(3).high - 0.618*(swings(3).high - swings(3).low) - 0.1*atr(14) and close > open",
          "short": "swings(3).high > swings(3).low and close > swings(3).low + 0.5*(swings(3).high - swings(3).low) and high < swings(3).low + 0.618*(swings(3).high - swings(3).low) + 0.1*atr(14) and close < open"},
   stop={"type": "level", "long": "swings(3).low", "short": "swings(3).high"}, target={"type": "r", "r": 2.0}, research="hypothesis")
st("range_box_reversion", "Choppy-regime range trading", S, "range", mech="in choppy regimes, range extremes hold",
   logic="reversal", anchor="20-bar range + Choppiness Index",
   hyp="When the Choppiness Index is above 61.8, buy near the 20-bar low and sell near the 20-bar high.",
   entry={"long": "chop(14) > 61.8 and low <= lowest(low,20)[1] + 0.1*atr(14) and close > open",
          "short": "chop(14) > 61.8 and high >= highest(high,20)[1] - 0.1*atr(14) and close < open"},
   stop={"type": "atr", "mult": 1.0, "n": 14}, target={"type": "level", "long": "(highest(high,20) + lowest(low,20))/2", "short": "(highest(high,20) + lowest(low,20))/2"},
   research="hypothesis")
st("trendline_break", "Swing trendline break", S, "trendline", mech="a line through the last two lower swing highs is a visible resistance",
   logic="breakout", anchor="line through two confirmed swing highs",
   hyp="When price closes above the line connecting the last two descending swing highs (projected to now), the down-trend has broken.",
   entry={"long": "swings(3).high < swings(3).high_prev and swings(3).low < swings(3).low_prev and cross_above(close, swings(3).high)",
          "short": "swings(3).low > swings(3).low_prev and swings(3).high > swings(3).high_prev and cross_below(close, swings(3).low)"},
   stop={"type": "atr", "mult": 1.5, "n": 14}, target={"type": "r", "r": 2.0}, research="hypothesis",
   notes="Implemented as the break of the latest lower swing high in a down-trend (a horizontal proxy of the trendline); break_of_structure instead requires a higher low (continuation).")

W = "volume"
st("rvol_session_high", "Relative-volume new session high", W, "volume surge", mech="unusual same-time-of-day volume marks news/attention flow",
   logic="continuation", anchor="rvol vs same time of day",
   hyp="A new session high on at least three times the usual volume for that time of day continues.",
   entry={"long": "rvol_tod(10) > 3 and cross_above(close, session().high[1])", "short": "rvol_tod(10) > 3 and cross_below(close, session().low[1])"},
   stop={"type": "atr", "mult": 1.5, "n": 14}, trail={"type": "atr", "mult": 2.5, "n": 14, "activate_r": 1.0}, mtd=2,
   ev=[("SRC-002", "mechanism", "stocks in play")], research="hypothesis")
st("volume_climax_reversal", "Volume-climax reversal", W, "climax", mech="capitulation volume with a rejection wick exhausts sellers",
   logic="reversal", anchor="rvol > 4 + long lower wick at session low",
   hyp="A bar at the session low with 4x volume and a lower wick over 60% of its range marks capitulation.",
   entry={"long": "rvol(20) > 4 and low <= session().low and min(open, close) - low > 0.6*(high - low)",
          "short": "rvol(20) > 4 and high >= session().high and high - max(open, close) > 0.6*(high - low)"},
   stop={"type": "level", "long": "low", "short": "high", "buffer_atr": 0.1, "n": 14}, target={"type": "level", "long": "vwap()", "short": "vwap()"},
   research="hypothesis")
st("obv_divergence", "On-balance-volume divergence", W, "volume divergence", mech="volume flow leads price (Granville)",
   logic="reversal", anchor="OBV vs price over 20 bars",
   hyp="A new 20-bar price low without a new 20-bar OBV low shows accumulation; buy on the next up close.",
   entry={"long": "low <= lowest(low,20) and obv() > lowest(obv(),20)[1] and close > open",
          "short": "high >= highest(high,20) and obv() < highest(obv(),20)[1] and close < open"},
   stop={"type": "atr", "mult": 1.5, "n": 14}, target={"type": "r", "r": 2.0}, ev=[("SRC-086", "origin", "OBV (book)")],
   research="incompletely sourced")
variant("ad_divergence", "obv_divergence", "Accumulation/distribution divergence", "Chaikin A/D line instead of OBV")
variant("obv_leads_breakout", "obv_divergence", "OBV-led breakout", "OBV at a 50-bar high before price")
st("mfi_reversal", "Money Flow Index extreme reversal", W, "volume-weighted oscillator", mech="volume-weighted oversold readings revert",
   logic="reversal", anchor="MFI(14)",
   hyp="MFI crossing back above 20 after being below it reverts upward.",
   entry={"long": "cross_above(mfi(14), 20)", "short": "cross_below(mfi(14), 80)"},
   stop={"type": "atr", "mult": 1.5, "n": 14}, target={"type": "r", "r": 1.5}, research="hypothesis",
   distinct="Uses price x volume; rsi2_pullback uses price only.")
st("cmf_trend_confirm", "Chaikin Money Flow trend confirmation", W, "money flow", mech="closes near bar highs on volume indicate accumulation",
   logic="continuation", anchor="CMF(20)",
   hyp="CMF crossing above +0.1 with price above EMA(50) confirms accumulation in an up-trend.",
   entry={"long": "cross_above(cmf(20), 0.1) and close > ema(close,50)", "short": "cross_below(cmf(20), -0.1) and close < ema(close,50)"},
   stop={"type": "atr", "mult": 2.0, "n": 14}, exit={"long": "cmf(20) < 0", "short": "cmf(20) > 0"}, research="hypothesis")
variant("est_delta_trend", "cmf_trend_confirm", "Estimated-delta trend (labelled estimate)", "close-location x volume estimate")
st("force_index_pullback", "Force-index pullback (Elder)", W, "volume-weighted pullback", mech="short-term selling pressure inside an up-trend",
   logic="continuation (pullback)", anchor="EMA(2) of force index, EMA(13)",
   hyp="With the 13-bar EMA rising, a negative 2-bar force index marks a pullback to buy.",
   entry={"long": "force(2) < 0 and ema(close,13) > ema(close,13)[1] and close > ema(close,50)",
          "short": "force(2) > 0 and ema(close,13) < ema(close,13)[1] and close < ema(close,50)"},
   stop={"type": "atr", "mult": 1.5, "n": 14}, target={"type": "r", "r": 1.5}, ev=[("SRC-076", "origin", "Force Index (book)")],
   research="incompletely sourced")
variant("elder_ray_pullback", "force_index_pullback", "Elder-ray bull-power pullback", "bull power (high - EMA13) instead of force index")
st("volume_dryup_breakout", "Volume dry-up then breakout", W, "volume contraction", mech="quiet volume in a tight range precedes a volume-backed breakout",
   logic="breakout", anchor="5-bar volume vs average",
   hyp="After five bars with under 60% of normal volume in a narrowing range, a breakout on twice normal volume continues.",
   entry={"long": "mean(volume,5)[1] < 0.6*mean(volume,50)[1] and rvol(20) > 2 and close > highest(high,5)[1]",
          "short": "mean(volume,5)[1] < 0.6*mean(volume,50)[1] and rvol(20) > 2 and close < lowest(low,5)[1]"},
   stop={"type": "level", "long": "lowest(low,5)", "short": "highest(high,5)"}, target={"type": "r", "r": 2.0}, research="hypothesis")
st("elder_impulse", "Elder impulse system turn", W, "named system", mech="agreement of trend (EMA13) and momentum (MACD histogram) slopes",
   logic="continuation", anchor="EMA13 slope + MACD-histogram slope",
   hyp="The first bar where both the 13-EMA and the MACD histogram rise ('green') after a non-green bar starts a buyable impulse; exit on red.",
   entry={"long": "ema(close,13) > ema(close,13)[1] and macd(close,12,26,9).hist > macd(close,12,26,9).hist[1] and not (ema(close,13)[1] > ema(close,13)[2] and macd(close,12,26,9).hist[1] > macd(close,12,26,9).hist[2])",
          "short": "ema(close,13) < ema(close,13)[1] and macd(close,12,26,9).hist < macd(close,12,26,9).hist[1] and not (ema(close,13)[1] < ema(close,13)[2] and macd(close,12,26,9).hist[1] < macd(close,12,26,9).hist[2])"},
   stop={"type": "atr", "mult": 1.5, "n": 14},
   exit={"long": "ema(close,13) < ema(close,13)[1] and macd(close,12,26,9).hist < macd(close,12,26,9).hist[1]",
         "short": "ema(close,13) > ema(close,13)[1] and macd(close,12,26,9).hist > macd(close,12,26,9).hist[1]"},
   ev=[("SRC-076", "context", "Elder's methods")], research="hypothesis",
   notes="The impulse system appears in Elder's later book 'Come into My Trading Room', which was not verified here.")

T = "time_of_day"
st("intraday_momentum_last_half_hour", "Intraday momentum: first half-hour predicts the last", T, "intraday momentum",
   mech="late-day trading by informed/hedging participants continues the morning's direction", logic="continuation",
   anchor="return from prior close to 10:00 ET",
   hyp="At 15:30 ET, take a position in the direction of the return from the prior close to 10:00 ET; exit at the close.",
   markets=STOCK, tf="5m", instruments=["SPY", "QQQ", "IWM", "DIA"],
   entry={"long": "tod() == 925 and valuewhen(minutes_since_open() == 25, close) / session().prev_close - 1 > 0",
          "short": "tod() == 925 and valuewhen(minutes_since_open() == 25, close) / session().prev_close - 1 < 0"},
   stop={"type": "atr", "mult": 3.0, "n": 14}, mtd=1, session={"entry_start": "15:25", "entry_end": "15:40", "flat_minutes_before_close": 5},
   ev=[("SRC-004", "direct", "SPY 1993-2013; 11 ETFs"), ("SRC-031", "mechanism", "same pattern in Bitcoin")],
   research="sourced", notes="Exit is 5 minutes before the close (platform rule), so the last 5 minutes of the paper's window are not captured.")
variant("crypto_intraday_momentum", "intraday_momentum_last_half_hour", "Bitcoin first-half-hour -> last-half-hour", "market: crypto, UTC day", ev=[("SRC-031", "direct", "")])
st("tod_seasonality", "Same-time-of-day return persistence", T, "intraday seasonality", mech="returns at the same half-hour recur across days",
   logic="continuation", anchor="mean 30-minute return at this time over 20 sessions",
   hyp="Hold for 30 minutes when the average return of this half-hour over the last 20 sessions is significantly positive (t > 2).",
   tf="5m", entry={"long": "tod_return(20,6).t > 2", "short": "tod_return(20,6).t < -2"},
   stop={"type": "atr", "mult": 2.0, "n": 14}, max_bars=6, mtd=4,
   ev=[("SRC-005", "direct", "cross-sectional half-hour continuation; time-series use here is an adaptation")], research="incompletely sourced")
variant("crypto_hour_seasonality", "tod_seasonality", "Crypto hour-of-day seasonality", "market: crypto, 1-hour buckets")
st("turn_of_month", "Turn-of-the-month intraday long", T, "calendar", mech="month-end/start flows lift equities",
   logic="calendar bias", anchor="last day and first 3 days of the month",
   hyp="Hold SPY long from the first bar's close to the close on the last trading day of the month and the first three days of the next.",
   markets=STOCK, tf="5m", direction="long", instruments=["SPY", "QQQ", "IWM"],
   entry={"long": "bar_in_session() == 0 and (dom() <= 3 or days_to_month_end() <= 2)"},
   stop={"type": "atr", "mult": 4.0, "n": 14}, mtd=1, session={"flat_minutes_before_close": 5},
   ev=[("SRC-009", "direct", "daily close-to-close monthly effect; intraday-only here")], research="incompletely sourced")
st("pre_holiday", "Pre-holiday session long", T, "calendar", mech="positive returns before market holidays",
   logic="calendar bias", anchor="session before an exchange holiday",
   hyp="Hold the index long intraday on the last session before a market holiday.", markets=STOCK, tf="5m", direction="long",
   entry={"long": "bar_in_session() == 0 and pre_holiday() == 1"}, stop={"type": "atr", "mult": 4.0, "n": 14}, mtd=1,
   session={"flat_minutes_before_close": 5}, ev=[("SRC-010", "direct", "daily pre-holiday returns 1963-1982")], research="incompletely sourced")
st("opex_pinning", "Option-expiration pinning reversion", T, "calendar", mech="hedging flows pin optionable stocks near strikes on expiration day",
   logic="reversal", anchor="nearest $5 strike on the third Friday",
   hyp="On monthly expiration Fridays after 13:00, fade moves more than 0.5% away from the nearest $5 strike back toward it.",
   markets=STOCK, tf="5m",
   entry={"short": "is_opex() == 1 and tod() >= 780 and close > (floor_to(close,5) + 2.5) and close / (floor_to(close,5) + 5) - 1 > -0.001 and close < open",
          "long": "is_opex() == 1 and tod() >= 780 and close < (floor_to(close,5) + 2.5) and close / floor_to(close,5) - 1 < 0.001 and close > open"},
   stop={"type": "atr", "mult": 1.5, "n": 14}, target={"type": "r", "r": 1.0}, mtd=1,
   ev=[("SRC-011", "mechanism", "closing prices cluster at strikes on expiration dates")], research="incompletely sourced",
   notes="Uses $5 strike spacing as an approximation; real strikes vary by stock and price.")
st("lunch_reversal", "Lunchtime reversal of the morning trend", T, "time-of-day", mech="morning trend participants take profits during the lunch lull",
   logic="reversal", anchor="11:30-13:30 ET",
   hyp="Between 11:30 and 13:30, fade a morning trend of more than 0.7% when a reversal bar closes back through the 20-bar EMA.",
   markets=STOCK, tf="5m",
   entry={"short": "time_between(\"11:30\", \"13:30\") and close / session().open - 1 > 0.007 and cross_below(close, ema(close,20))",
          "long": "time_between(\"11:30\", \"13:30\") and close / session().open - 1 < -0.007 and cross_above(close, ema(close,20))"},
   stop={"type": "level", "long": "session().low", "short": "session().high"}, target={"type": "level", "long": "vwap()", "short": "vwap()"},
   mtd=1, research="hypothesis")

E = "scheduled_events"
st("fomc_pre_announcement", "Pre-FOMC announcement drift (intraday part)", E, "central bank", mech="equities rise ahead of scheduled FOMC announcements",
   logic="event bias", anchor="FOMC announcement days (14:00 ET)",
   hyp="On FOMC announcement days, hold the index long from the first bar's close until 13:55 ET, before the 14:00 statement.",
   markets=STOCK, tf="5m", direction="long", instruments=["SPY", "QQQ"], data=("bars", "events:fomc"),
   entry={"long": "bar_in_session() == 0 and event(\"fomc\") == 1"}, exit={"long": "tod() >= 830"},
   stop={"type": "atr", "mult": 4.0, "n": 14}, mtd=1, session={"flat_minutes_before_close": 5},
   ev=[("SRC-006", "direct", "24-hour pre-announcement window; only the same-day part is traded"), ("SRC-100", "context", "FOMC dates")],
   research="incompletely sourced")
variant("fomc_crypto", "fomc_pre_announcement", "Pre-FOMC bitcoin drift", "market: crypto", ev=[("SRC-030", "mechanism", "FOMC days change BTC intraday predictability")])
st("macro_announcement_day_long", "Macro-announcement-day long (CPI)", E, "macro releases", mech="announcement-day risk premium",
   logic="event bias", anchor="CPI release days",
   hyp="On CPI release days, hold the index long from the first bar's close to the close.",
   markets=STOCK, tf="5m", direction="long", instruments=["SPY", "QQQ"], data=("bars", "events:cpi"),
   entry={"long": "bar_in_session() == 0 and event(\"cpi\") == 1"}, stop={"type": "atr", "mult": 4.0, "n": 14}, mtd=1,
   session={"flat_minutes_before_close": 5},
   ev=[("SRC-012", "direct", "daily announcement-day excess returns 1958-2009"), ("SRC-101", "context", "CPI dates")],
   research="incompletely sourced")
variant("cpi_day_orb", "macro_announcement_day_long", "CPI-day opening-range breakout", "ORB only on CPI days")
st("earnings_day_orb", "Earnings-day opening-range breakout", E, "earnings", mech="earnings days concentrate information and attention",
   logic="breakout", anchor="first 15-minute range on earnings days",
   hyp="On the session after a company reports, trade the 15-minute opening-range breakout in the gap's direction.",
   markets=STOCK, tf="5m", data=("bars", "events:earnings"),
   entry={"long": "event(\"earnings\") == 1 and session().gap > 0 and cross_above(close, opening_range(15).high)",
          "short": "event(\"earnings\") == 1 and session().gap < 0 and cross_below(close, opening_range(15).low)"},
   stop={"type": "level", "long": "opening_range(15).low", "short": "opening_range(15).high"}, mtd=1,
   ev=[("SRC-013", "mechanism", "post-earnings drift (multi-day)"), ("SRC-002", "mechanism", "stocks in play")], research="hypothesis",
   notes="Needs an earnings calendar; without it the event rule is unknown and the bot never trades (reported as data unavailable).")
variant("pead_first_day", "earnings_day_orb", "Post-earnings first-day continuation", "VWAP hold instead of ORB")
