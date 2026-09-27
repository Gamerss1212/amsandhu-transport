"""Families: opening range & initial balance; gaps & overnight; session levels & reference prices."""
from lib import BOTH, CRYPTO, STOCK, STK, st, variant

F = "opening_range"

st("orb_first_candle", "5-minute opening-range breakout in the first candle's direction", F, "opening range",
   mech="the first 5 minutes' direction carries information about the rest of the session", logic="continuation",
   anchor="first 5-minute candle",
   hyp="Trade in the direction of the first 5-minute candle from the second candle's open; stop at the first candle's opposite extreme; target 10R or the close.",
   markets=STOCK, tf="5m", instruments=["QQQ", "SPY"],
   entry={"long": "bar_in_session() == 0 and close > open", "short": "bar_in_session() == 0 and close < open"},
   stop={"type": "level", "long": "opening_range(5).low", "short": "opening_range(5).high"},
   target={"type": "r", "r": 10.0}, mtd=1, session={"flat_minutes_before_close": 5},
   ev=[("SRC-001", "direct", "QQQ 2016-2023: ~24% hit rate, ~+0.13R/trade before costs"),
       ("SRC-003", "contrary", "independent replication: gross +0.131R, net of 2.5-4 point costs ~0R on 5 indices")],
   research="sourced", fail=["edge approximately equal to round-trip costs (SRC-003)", "low hit rate: long losing streaks"],
   distinct="Direction is decided by the first candle itself (no breakout trigger), unlike orb_breakout.")

st("orb_breakout", "Opening-range breakout on a closing basis", F, "opening range",
   mech="acceptance of prices outside the opening auction's range", logic="breakout", anchor="first 15-minute range",
   hyp="A close beyond the first 15 minutes' range signals one side has won the opening auction; stop at the range midpoint.",
   tf="5m", params={"m": 15},
   entry={"long": "cross_above(close, opening_range($m).high)", "short": "cross_below(close, opening_range($m).low)"},
   stop={"type": "level", "long": "opening_range($m).mid", "short": "opening_range($m).mid"},
   target={"type": "r", "r": 2.0}, mtd=1,
   session={"stock": dict(STK, entry_end="12:00"), "crypto": {"entry_end": "12:00"}},
   ev=[("SRC-070", "origin", "opening range breakouts (book; rules not read here)"),
       ("SRC-002", "mechanism", "5-minute ORB across US stocks"), ("SRC-040", "mechanism", "trading-range breaks")],
   research="incompletely sourced", fail=["false breakouts on range days", "late entries after wide ranges"])
variant("orb_breakout_30", "orb_breakout", "30-minute opening-range breakout", "range length 30 minutes", params={"m": 30})
variant("orb_breakout_60", "orb_breakout", "60-minute opening-range breakout", "range length 60 minutes", params={"m": 60})
variant("crypto_utc_open_range", "orb_breakout", "UTC-day opening-range breakout (crypto)", "market: crypto, range = first hour after 00:00 UTC",
        params={"m": 60}, markets=["crypto"])
variant("orb_vwap_confirm", "orb_breakout", "ORB with VWAP confirmation", "adds price-above-VWAP filter",
        definition_patch={"filters": ["close > vwap()"]})
variant("orb_width_filter", "orb_breakout", "ORB only after a narrow opening range", "adds range-width < 0.35 x daily ATR filter")

st("orb_stocks_in_play", "Stocks-in-play 5-minute ORB with ATR stop", F, "opening range",
   mech="attention/news days (abnormal opening volume) produce more persistent intraday moves", logic="breakout",
   anchor="first 5-minute range + opening relative volume",
   hyp="Only when the first 5-minute bar trades at least twice its usual volume, place a stop order at that bar's high (up candle) or low (down candle); stop 10% of the 14-day ATR; exit at the close.",
   markets=STOCK, tf="5m",
   entry={"long": "bar_in_session() == 0 and close > open and rvol_tod(14) > 2",
          "short": "bar_in_session() == 0 and close < open and rvol_tod(14) > 2"},
   order={"type": "stop", "long": "opening_range(5).high", "short": "opening_range(5).low", "ttl_bars": 70},
   stop={"type": "level", "long": "opening_range(5).high - 0.1*tf(\"1d\", atr(14))",
         "short": "opening_range(5).low + 0.1*tf(\"1d\", atr(14))"},
   mtd=1, session={"flat_minutes_before_close": 5},
   ev=[("SRC-002", "direct", "cross-sectional top relative-volume stocks; this is a single-instrument adaptation")],
   research="incompletely sourced",
   fail=["single-stock threshold is not the paper's cross-sectional ranking", "needs many symbols to find in-play days"])

st("orb_failed_breakout_fade", "Failed opening-range breakout fade", F, "opening range",
   mech="trapped breakout traders exit when price re-enters the range", logic="reversal (failed breakout)",
   anchor="15-minute opening range",
   hyp="A breakout above the opening range that closes back inside within three bars traps buyers; short back toward the range low.",
   tf="5m",
   entry={"short": "within(cross_above(close, opening_range(15).high), 3) and cross_below(close, opening_range(15).high)",
          "long": "within(cross_below(close, opening_range(15).low), 3) and cross_above(close, opening_range(15).low)"},
   stop={"type": "level", "long": "session().low", "short": "session().high", "buffer_atr": 0.1, "n": 14},
   target={"type": "level", "long": "opening_range(15).high", "short": "opening_range(15).low"}, mtd=1,
   ev=[("SRC-043", "mechanism", "reversals at levels where take-profit orders cluster (FX)")], research="hypothesis")

st("orb_retest", "Opening-range breakout retest", F, "opening range",
   mech="broken resistance acting as support on the first retest", logic="continuation (retest)",
   anchor="15-minute opening range",
   hyp="After a breakout above the opening range, the first pullback that holds the old range high offers a lower-risk entry than the breakout itself.",
   tf="5m",
   entry={"long": "since(cross_above(close, opening_range(15).high)) >= 2 and since(cross_above(close, opening_range(15).high)) <= 12 and low <= opening_range(15).high + 0.1*atr(14) and close > opening_range(15).high and close > open",
          "short": "since(cross_below(close, opening_range(15).low)) >= 2 and since(cross_below(close, opening_range(15).low)) <= 12 and high >= opening_range(15).low - 0.1*atr(14) and close < opening_range(15).low and close < open"},
   stop={"type": "level", "long": "opening_range(15).mid", "short": "opening_range(15).mid"},
   target={"type": "r", "r": 2.0}, mtd=1, research="hypothesis")

st("ib_narrow_extension", "Narrow initial-balance range extension", F, "initial balance",
   mech="Market Profile: a narrow first-hour range is more likely to be extended", logic="breakout",
   anchor="first-hour range relative to daily ATR",
   hyp="If the first hour's range is under half the 14-day ATR, a close beyond it tends to extend by about one more range.",
   markets=STOCK, tf="5m",
   entry={"long": "cross_above(close, opening_range(60).high) and opening_range(60).high - opening_range(60).low < 0.5*tf(\"1d\", atr(14))",
          "short": "cross_below(close, opening_range(60).low) and opening_range(60).high - opening_range(60).low < 0.5*tf(\"1d\", atr(14))"},
   stop={"type": "level", "long": "opening_range(60).mid", "short": "opening_range(60).mid"},
   target={"type": "level", "long": "opening_range(60).high + (opening_range(60).high - opening_range(60).low)",
           "short": "opening_range(60).low - (opening_range(60).high - opening_range(60).low)"}, mtd=1,
   ev=[("SRC-078", "origin", "initial balance and range extension (book)")], research="incompletely sourced",
   distinct="Conditions on initial-balance width relative to daily volatility; orb_breakout does not.")

st("ib_double_extension_fade", "Initial-balance double-extension fade", F, "initial balance",
   mech="auction exhaustion after price extends twice the initial balance", logic="reversal",
   anchor="first-hour range",
   hyp="Once price has travelled a full initial-balance range beyond it, the move is extended; a reversal bar there fades back to the initial balance edge.",
   markets=STOCK, tf="5m",
   entry={"short": "high > opening_range(60).high + (opening_range(60).high - opening_range(60).low) and close < open and close < low[1]",
          "long": "low < opening_range(60).low - (opening_range(60).high - opening_range(60).low) and close > open and close > high[1]"},
   stop={"type": "level", "long": "session().low", "short": "session().high", "buffer_atr": 0.1, "n": 14},
   target={"type": "level", "long": "opening_range(60).low", "short": "opening_range(60).high"}, mtd=1,
   ev=[("SRC-078", "context", "range extension concept")], research="hypothesis")

st("opening_drive", "Opening-drive continuation", F, "open type",
   mech="a one-directional open (Market Profile 'open-drive') shows conviction", logic="continuation",
   anchor="first 15-minute range and close location",
   hyp="If the first 15 minutes cover at least 0.3 daily ATR and close in the top 20% of their range, the drive tends to continue.",
   markets=STOCK, tf="5m",
   entry={"long": "bar_in_session() == 2 and opening_range(15).high - opening_range(15).low > 0.3*tf(\"1d\", atr(14)) and close > opening_range(15).high - 0.2*(opening_range(15).high - opening_range(15).low)",
          "short": "bar_in_session() == 2 and opening_range(15).high - opening_range(15).low > 0.3*tf(\"1d\", atr(14)) and close < opening_range(15).low + 0.2*(opening_range(15).high - opening_range(15).low)"},
   stop={"type": "level", "long": "opening_range(15).low", "short": "opening_range(15).high"}, mtd=1,
   session={"flat_minutes_before_close": 5},
   ev=[("SRC-078", "origin", "open types (open-drive)")], research="incompletely sourced")
variant("first_pullback_after_drive", "opening_drive", "First pullback after an opening drive", "entry on the first EMA(9) pullback instead of the 15-minute close")

st("open_rejection_reverse", "Open outside prior range, rejected back inside", F, "open type",
   mech="failed auction above/below yesterday's range", logic="reversal",
   anchor="prior-session high/low",
   hyp="An open above yesterday's high that falls back below it within the first hour is a rejected auction; short toward yesterday's close.",
   markets=STOCK, tf="5m",
   entry={"short": "session().open > session().prev_high and cross_below(close, session().prev_high) and minutes_since_open() <= 60",
          "long": "session().open < session().prev_low and cross_above(close, session().prev_low) and minutes_since_open() <= 60"},
   stop={"type": "level", "long": "session().low", "short": "session().high", "buffer_atr": 0.1, "n": 14},
   target={"type": "level", "long": "session().prev_close", "short": "session().prev_close"}, mtd=1,
   session={"flat_minutes_before_close": 5},
   ev=[("SRC-078", "origin", "open-rejection-reverse type")], research="incompletely sourced")

st("session_range_breakout_crypto", "Asia-range breakout at the London open (crypto)", F, "session range",
   mech="liquidity and volatility step up when a new regional session opens", logic="breakout",
   anchor="00:00-07:00 UTC range",
   hyp="The quiet Asia-hours range is broken with follow-through once European traders arrive (07:00-11:00 UTC).",
   markets=CRYPTO, tf="15m",
   entry={"long": "cross_above(close, window_range(0,420).high) and time_between(\"07:00\", \"11:00\")",
          "short": "cross_below(close, window_range(0,420).low) and time_between(\"07:00\", \"11:00\")"},
   stop={"type": "level", "long": "(window_range(0,420).high + window_range(0,420).low)/2",
         "short": "(window_range(0,420).high + window_range(0,420).low)/2"},
   target={"type": "r", "r": 1.5}, mtd=1,
   ev=[("SRC-032", "mechanism", "Bitcoin volatility highest around major stock-market opens")], research="hypothesis")
variant("crypto_london_ny_breakout", "session_range_breakout_crypto", "London-range breakout at the New York open", "range 07:00-13:30 UTC, trade 13:30-17:00 UTC")
variant("crypto_us_open_breakout", "session_range_breakout_crypto", "US-open breakout (crypto)", "range 12:00-13:30 UTC, trade from 13:30")

st("open_volatility_breakout", "Open +/- volatility breakout (Crabel stretch / Williams)", F, "volatility breakout",
   mech="a move of a typical daily 'stretch' away from the open rarely reverses the same day", logic="breakout",
   anchor="session open +/- 10-day average stretch",
   hyp="Place a buy stop at the open plus the 10-day average of min(high-open, open-low) and a sell stop the same distance below (one-cancels-other).",
   markets=BOTH, tf="5m", params={"k": 1.0},
   entry={"long": "bar_in_session() == 0", "short": "bar_in_session() == 0"},
   order={"type": "oco", "long": "session().open + $k*tf(\"1d\", mean(min(high - open, open - low), 10))",
          "short": "session().open - $k*tf(\"1d\", mean(min(high - open, open - low), 10))", "ttl_bars": 60},
   stop={"type": "atr", "mult": 1.5, "n": 14}, mtd=1,
   ev=[("SRC-070", "origin", "stretch-based opening range breakouts (book)"),
       ("SRC-081", "origin", "volatility breakouts from the open (book)")], research="incompletely sourced")
variant("williams_range_breakout", "open_volatility_breakout", "Open +/- k x prior day's range (Williams)", "volatility measure: previous day's range")

# ------------------------------------------------------------------ gaps & overnight
G = "gaps"

st("gap_and_go", "Gap-and-go continuation", G, "opening gap", mech="news-driven gaps with volume continue",
   logic="continuation", anchor="gap vs prior close + first 5-minute bar",
   hyp="A gap of at least 1% whose first 5-minute bar closes in the gap's direction on at least 1.5x usual volume continues past that bar's extreme.",
   markets=STOCK, tf="5m",
   entry={"long": "bar_in_session() == 0 and session().gap > 0.01 and close > open and rvol_tod(14) > 1.5",
          "short": "bar_in_session() == 0 and session().gap < -0.01 and close < open and rvol_tod(14) > 1.5"},
   order={"type": "stop", "long": "opening_range(5).high", "short": "opening_range(5).low", "ttl_bars": 12},
   stop={"type": "level", "long": "opening_range(5).low", "short": "opening_range(5).high"},
   target={"type": "r", "r": 2.0}, mtd=1, session={"flat_minutes_before_close": 5},
   ev=[("SRC-077", "origin", "gap setups (book; rules not read here)"), ("SRC-002", "mechanism", "stocks in play")],
   research="incompletely sourced")
variant("gap_premarket_volume", "gap_and_go", "Gap-and-go with pre-market volume filter", "adds pre-market volume threshold (extended-hours data)")

st("gap_fade_to_close", "Moderate-gap fade to the prior close", G, "opening gap", mech="partial reversal of overnight moves during the session",
   logic="reversal", anchor="prior close",
   hyp="Gaps of 0.3-1.5% whose first 5-minute bar moves against the gap tend to fill toward the prior close.",
   markets=STOCK, tf="5m",
   entry={"short": "bar_in_session() == 0 and session().gap > 0.003 and session().gap < 0.015 and close < open",
          "long": "bar_in_session() == 0 and session().gap < -0.003 and session().gap > -0.015 and close > open"},
   stop={"type": "level", "long": "session().low", "short": "session().high", "buffer_atr": 0.2, "n": 14},
   target={"type": "level", "long": "session().prev_close", "short": "session().prev_close"}, mtd=1,
   session={"flat_minutes_before_close": 5},
   ev=[("SRC-007", "mechanism", "cross-period (overnight vs intraday) reversal"), ("SRC-073", "mechanism", "intraday mean reversion of gaps")],
   research="incompletely sourced")
variant("overnight_intraday_reversal", "gap_fade_to_close", "Large-gap intraday reversal", "gap threshold in units of return volatility")
variant("prior_close_magnet", "gap_fade_to_close", "Early-session reversion to prior close", "trigger after the first 30 minutes instead of the first bar")

st("buy_on_gap", "Buy-on-gap (Chan)", G, "opening gap", mech="liquidity-driven gap-downs below the prior low in uptrending stocks mean-revert intraday",
   logic="reversal", anchor="prior low, 20-day MA, 90-day return volatility",
   hyp="Buy when the open is more than one standard deviation of daily returns below the prior low while above the 20-day average; exit at the close.",
   markets=STOCK, tf="5m", direction="long",
   entry={"long": "bar_in_session() == 0 and session().open < session().prev_low * (1 - tf(\"1d\", std(pct(close,1), 90))) and session().open > tf(\"1d\", sma(close,20))"},
   stop={"type": "pct", "pct": 4.0}, mtd=1, session={"flat_minutes_before_close": 5},
   ev=[("SRC-073", "direct", "portfolio of the 10 lowest-return qualifying stocks; single-stock adaptation here")],
   research="incompletely sourced", fail=["rare signals on any one stock", "gap-downs on real news keep falling"])

st("gap_hold_continuation", "Gap holds above prior high, then new session high", G, "opening gap",
   mech="an unfilled gap above the prior high shows demand absorbing early selling", logic="continuation",
   anchor="prior high + session high",
   hyp="If a gap-up stock pulls back but never trades below yesterday's high, the next new session high after 10:00 continues the move.",
   markets=STOCK, tf="5m",
   entry={"long": "session().gap > 0.005 and session().low > session().prev_high and cross_above(close, session().high[1]) and minutes_since_open() >= 30",
          "short": "session().gap < -0.005 and session().high < session().prev_low and cross_below(close, session().low[1]) and minutes_since_open() >= 30"},
   stop={"type": "level", "long": "session().prev_high", "short": "session().prev_low", "buffer_atr": 0.1, "n": 14},
   target={"type": "r", "r": 2.0}, mtd=1, research="hypothesis",
   distinct="Requires the gap to hold the prior-day extreme and triggers on a later new high; gap_and_go triggers on the first bar.")

st("premarket_high_break", "Pre-market high breakout", G, "extended hours", mech="the pre-market extreme is a visible reference where stops and breakout orders cluster",
   logic="breakout", anchor="pre-market high/low",
   hyp="After the open, a close above the pre-market high with above-normal volume continues.",
   markets=STOCK, tf="5m", data=("bars", "extended_hours"),
   entry={"long": "cross_above(close, premarket().high) and rvol_tod(14) > 1.2",
          "short": "cross_below(close, premarket().low) and rvol_tod(14) > 1.2"},
   stop={"type": "level", "long": "vwap()", "short": "vwap()", "buffer_atr": 0.2, "n": 14},
   target={"type": "r", "r": 2.0}, mtd=1,
   ev=[("SRC-043", "mechanism", "stop orders cluster beyond visible levels")], research="hypothesis",
   notes="Needs bots subscribed with extended_hours=true (Yahoo pre/post-market bars).")

st("ssr_day_bounce", "Short-sale-restriction day bounce", G, "regulatory", mech="SEC Rule 201 restricts short selling the day after a 10% drop, reducing selling pressure",
   logic="reversal", anchor="prior-day return <= -10%",
   hyp="The day after a stock falls 10% or more, short sales are restricted to upticks; a break above the first 30 minutes' high tends to squeeze.",
   markets=STOCK, tf="5m", direction="long",
   entry={"long": "session().prev_close / tf(\"1d\", close[1]) - 1 <= -0.10 and cross_above(close, opening_range(30).high)"},
   stop={"type": "level", "long": "opening_range(30).low"}, target={"type": "r", "r": 2.0}, mtd=1,
   research="hypothesis", notes="No source for the rule or its profitability was verified in this session.")

# ------------------------------------------------------------------ session levels & reference prices
L = "reference_levels"

st("prior_day_breakout", "Prior-day high/low breakout", L, "prior session", mech="stop orders resting beyond yesterday's extremes accelerate breakouts",
   logic="breakout", anchor="prior-session high/low",
   hyp="A close beyond yesterday's high with above-normal volume triggers resting buy stops and continues.",
   tf="5m",
   entry={"long": "cross_above(close, session().prev_high) and rvol(20) > 1.2",
          "short": "cross_below(close, session().prev_low) and rvol(20) > 1.2"},
   stop={"type": "level", "long": "session().prev_high", "short": "session().prev_low", "buffer_atr": 0.5, "n": 14},
   target={"type": "r", "r": 2.0}, mtd=1,
   ev=[("SRC-043", "mechanism", "stop-loss clustering beyond levels"), ("SRC-040", "mechanism", "trading-range breaks")],
   research="incompletely sourced")
variant("weekly_breakout", "prior_day_breakout", "Prior 5-session high/low breakout", "level: prior 5 sessions' extreme")

st("prior_day_rejection", "Prior-day extreme rejection", L, "prior session", mech="take-profit orders cluster at yesterday's extremes",
   logic="reversal", anchor="prior-session high/low",
   hyp="Price that trades above yesterday's high but closes back below it has been rejected; short toward VWAP.",
   tf="5m",
   entry={"short": "high > session().prev_high and close < session().prev_high and close[1] < session().prev_high",
          "long": "low < session().prev_low and close > session().prev_low and close[1] > session().prev_low"},
   stop={"type": "level", "long": "low", "short": "high", "buffer_atr": 0.2, "n": 14},
   target={"type": "level", "long": "vwap()", "short": "vwap()"}, mtd=1,
   ev=[("SRC-043", "mechanism", "take-profit clustering at levels")], research="hypothesis")

st("turtle_soup", "Turtle Soup (failed 20-bar breakdown)", L, "N-bar extreme", mech="failed new extremes trap breakout traders",
   logic="reversal (failed breakout)", anchor="20-bar low with the previous low >= 4 bars old",
   hyp="When price makes a new 20-bar low but the prior 20-bar low was at least four bars earlier and price closes back above it, breakout sellers are trapped.",
   tf="5m",
   entry={"long": "low < lowest(low,20)[1] and since(low <= lowest(low,20))[1] >= 4 and close > lowest(low,20)[1]",
          "short": "high > highest(high,20)[1] and since(high >= highest(high,20))[1] >= 4 and close < highest(high,20)[1]"},
   stop={"type": "level", "long": "low", "short": "high", "buffer_atr": 0.1, "n": 14},
   target={"type": "r", "r": 2.0}, max_bars=24,
   ev=[("SRC-071", "origin", "Turtle Soup (daily, book; rules not read here)")], research="incompletely sourced")
variant("liquidity_sweep_reversal", "turtle_soup", "Swing-low liquidity sweep reversal", "reference: last confirmed swing low instead of the 20-bar low",
        definition_patch={"entry": {"long": "low < swings(3).low and close > swings(3).low"}})

st("pivot_bounce", "Floor-pivot support bounce", L, "pivot points", mech="widely watched calculated levels attract resting orders",
   logic="reversal", anchor="classic pivots from the prior session",
   hyp="A bar that trades through S1 and closes back above it with a bullish body finds support; target the pivot.",
   tf="5m",
   entry={"long": "low <= pivots(\"classic\").s1 and close > pivots(\"classic\").s1 and close > open",
          "short": "high >= pivots(\"classic\").r1 and close < pivots(\"classic\").r1 and close < open"},
   stop={"type": "level", "long": "low", "short": "high", "buffer_atr": 0.25, "n": 14},
   target={"type": "level", "long": "pivots(\"classic\").p", "short": "pivots(\"classic\").p"}, mtd=2,
   research="hypothesis")
variant("camarilla_h3_fade", "pivot_bounce", "Camarilla H3/L3 fade", "levels from the Camarilla formula")
variant("fibonacci_pivot_bounce", "pivot_bounce", "Fibonacci pivot bounce", "levels from the Fibonacci pivot formula")

st("pivot_breakout", "Floor-pivot resistance breakout", L, "pivot points", mech="breaking a watched level triggers stops",
   logic="breakout", anchor="R1/S1",
   hyp="A close above R1 with price above the pivot and VWAP continues toward R2.",
   tf="5m",
   entry={"long": "cross_above(close, pivots(\"classic\").r1) and close > vwap()",
          "short": "cross_below(close, pivots(\"classic\").s1) and close < vwap()"},
   stop={"type": "level", "long": "pivots(\"classic\").p", "short": "pivots(\"classic\").p"},
   target={"type": "level", "long": "pivots(\"classic\").r2", "short": "pivots(\"classic\").s2"}, mtd=1, research="hypothesis")
variant("camarilla_h4_breakout", "pivot_breakout", "Camarilla H4/L4 breakout", "levels from the Camarilla formula")

st("round_number_breakout", "Round-number breakout acceleration", L, "round numbers",
   mech="stop-loss orders cluster just beyond round numbers, so crossing them accelerates the move", logic="breakout",
   anchor="price multiples of a round step", params={"step": 1000},
   hyp="A close through a round-number level (e.g. every $1,000 in BTC) triggers clustered stops and continues.",
   tf="5m", markets=BOTH,
   entry={"long": "floor_to(close, $step) > floor_to(close[1], $step)", "short": "floor_to(close, $step) < floor_to(close[1], $step)"},
   stop={"type": "level", "long": "floor_to(close, $step)", "short": "ceil_to(close, $step)", "buffer_atr": 0.5, "n": 14},
   target={"type": "r", "r": 2.0}, mtd=2,
   ev=[("SRC-043", "mechanism", "stop-loss clustering at round numbers (FX dealer data)")], research="incompletely sourced",
   notes="The round step is a bot parameter (e.g. 1000 for BTC, 100 for ETH, 5 for SPY).")

st("round_number_reversal", "Round-number rejection", L, "round numbers",
   mech="take-profit orders cluster at round numbers, so trends pause or reverse there", logic="reversal",
   anchor="nearest round number", params={"step": 1000},
   hyp="A bar that pokes through a round number and closes back on the near side with a rejection wick reverses.",
   tf="5m",
   entry={"short": "high >= ceil_to(close[1], $step) and close < ceil_to(close[1], $step) and high - max(open, close) > 0.5*(high - low)",
          "long": "low <= floor_to(close[1], $step) and close > floor_to(close[1], $step) and min(open, close) - low > 0.5*(high - low)"},
   stop={"type": "level", "long": "low", "short": "high", "buffer_atr": 0.2, "n": 14},
   target={"type": "r", "r": 1.5}, mtd=2,
   ev=[("SRC-043", "mechanism", "take-profit clustering at round numbers")], research="incompletely sourced")

st("session_open_magnet", "Reversion to the session open", L, "session open",
   mech="the opening price is the day's reference for trapped inventory", logic="reversal",
   anchor="session open",
   hyp="Mid-session, when price is more than half a daily ATR from the open and RSI(14) is stretched, it tends to rotate back toward the open.",
   tf="5m",
   entry={"short": "close - session().open > 0.5*tf(\"1d\", atr(14)) and rsi(close,14) > 70 and minutes_since_open() >= 90",
          "long": "session().open - close > 0.5*tf(\"1d\", atr(14)) and rsi(close,14) < 30 and minutes_since_open() >= 90"},
   stop={"type": "atr", "mult": 1.5, "n": 14}, target={"type": "level", "long": "session().open", "short": "session().open"},
   mtd=1, research="hypothesis")

st("late_day_high_breakout", "Late-session new high breakout", L, "time-conditioned breakout",
   mech="late-day breakouts are joined by end-of-day positioning", logic="breakout",
   anchor="session high after 15:00 ET",
   hyp="A new session high after 15:00 with price above VWAP carries into the close.",
   markets=STOCK, tf="5m",
   entry={"long": "cross_above(close, session().high[1]) and tod() >= 900 and close > vwap()",
          "short": "cross_below(close, session().low[1]) and tod() >= 900 and close < vwap()"},
   stop={"type": "level", "long": "vwap()", "short": "vwap()"}, mtd=1,
   session={"entry_start": "15:00", "entry_end": "15:45", "flat_minutes_before_close": 5}, research="hypothesis")

st("midday_range_breakout", "Midday-range breakout", L, "session range", mech="the lunch lull compresses ranges before afternoon participation returns",
   logic="breakout", anchor="11:30-13:30 ET range",
   hyp="A close beyond the 11:30-13:30 range after 13:30 starts the afternoon move.",
   markets=STOCK, tf="5m",
   entry={"long": "cross_above(close, window_range(690,810).high) and tod() >= 810",
          "short": "cross_below(close, window_range(690,810).low) and tod() >= 810"},
   stop={"type": "level", "long": "(window_range(690,810).high + window_range(690,810).low)/2",
         "short": "(window_range(690,810).high + window_range(690,810).low)/2"},
   target={"type": "r", "r": 2.0}, mtd=1, session={"entry_start": "13:30", "entry_end": "15:15", "flat_minutes_before_close": 5},
   research="hypothesis")

st("ten_am_reversal", "Ten o'clock reversal", L, "time-conditioned reversal",
   mech="opening-order flow is exhausted about 30 minutes in", logic="reversal", anchor="first 30 minutes' direction",
   hyp="If the first 30 minutes moved strongly one way, a reversal bar between 10:00 and 10:30 marks the day's first swing extreme.",
   markets=STOCK, tf="5m",
   entry={"short": "time_between(\"10:00\", \"10:30\") and valuewhen(minutes_since_open() == 25, close) / session().open - 1 > 0.004 and close < low[1]",
          "long": "time_between(\"10:00\", \"10:30\") and valuewhen(minutes_since_open() == 25, close) / session().open - 1 < -0.004 and close > high[1]"},
   stop={"type": "level", "long": "session().low", "short": "session().high", "buffer_atr": 0.1, "n": 14},
   target={"type": "level", "long": "vwap()", "short": "vwap()"}, mtd=1, research="hypothesis")
