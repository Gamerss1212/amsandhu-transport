# Knowledge base: candlesticks

One entry per `### `. Read with `python3 scripts/know.py <name>`, which adds Jarvus's own measured result
(`references/kb-measured.md`) to entries that have an `id`. "Measured" numbers come only from that file.

### Candlestick basics
aka: candle, candles, candlestick, ohlc, how to read candles, wick, body, shadow
What: one candle = one period's Open, High, Low, Close. Body = open→close (green if close > open, red if below). Wicks (shadows) = the high and low beyond the body.
Read it: the close matters most (who won the period). Long wicks = rejected prices. Big bodies = one side in control. Context (trend, level, volume, timeframe) decides meaning more than the shape.
Trap: a pattern is only "done" when the candle closes; intrabar shapes change. Crypto trades 24/7, so the gaps many classic patterns need are rare.

### Candle timeframes
aka: timeframe, 1m 5m 15m 1h 4h daily, which timeframe, multi timeframe candles
What: the same market drawn with 1-minute to 1-week candles. Higher timeframes carry more weight; lower ones show the entry.
Use: bias from daily/4h, setup on 1h/15m, trigger on 5m. A 1h pattern against a daily trend is weak.
Jarvus: decisions use completed 1h candles plus the 4h and daily trend.

### Wicks and rejection
aka: long wick, shadow, rejection wick, tail, pin
What: a long wick shows price went there and was pushed back. Lower wick at support = buyers defended; upper wick at resistance = sellers defended.
Trap: in crypto many wicks are stop-runs/liquidations; a wick through a level that closes back inside is a sweep, not a breakdown.

### Hammer
id: hammer · aka: hammer candle, bullish pin bar, pin bar bottom
What: small body near the top, lower wick at least 2× the body, little or no upper wick, after a decline.
Read it: sellers pushed price down, buyers pushed it back. A possible bottom, not a confirmed one.
Use: only at support or after a sweep of a low; wait for the next candle to close above the hammer's high; stop under the wick.

### Inverted hammer
id: inverted_hammer · aka: inverted hammer candle
What: small body near the bottom, long upper wick (≥ 2× body), after a decline.
Read it: buyers tried higher and failed, but sellers are tiring. Needs a strong green confirmation candle.

### Hanging man
id: hanging_man · aka: hanging man candle
What: hammer shape after a rise.
Read it: buyers had to defend a dip; a warning, confirmed only if the next candle closes below its body.

### Shooting star
id: shooting_star · aka: shooting star candle, bearish pin bar, pin bar top
What: small body near the low, long upper wick (≥ 2× body), after a rise.
Read it: buyers pushed up and were rejected. Spot traders use it to take profit or not buy, not to short.

### Doji
aka: doji candle, indecision candle
What: open ≈ close (tiny body). Indecision.
Read it: means little alone; after a long run or at a level it warns the move is tiring. Variants: dragonfly, gravestone, long-legged, four-price.

### Doji after a drop
id: doji_after_drop · aka: doji at bottom
What: a doji after a 5-bar decline. Possible exhaustion of sellers; needs a green confirmation close.

### Doji after a rise
id: doji_after_rise · aka: doji at top
What: a doji after a 5-bar rise. Possible exhaustion of buyers.

### Dragonfly doji
id: dragonfly_doji · aka: dragonfly
What: open, close and high at the top, long lower wick. Strong rejection of lower prices; bullish at support.

### Gravestone doji
id: gravestone_doji · aka: gravestone
What: open, close and low at the bottom, long upper wick. Rejection of higher prices; bearish at resistance.

### Long-legged doji
id: long_legged_doji · aka: long legged doji, rickshaw man
What: tiny body in the middle, long wicks both sides. Big two-way fight; often comes before a large move either way.

### Four-price doji
aka: four price doji
What: open = high = low = close. Almost no trading; seen in illiquid coins. Means the market is dead, not a signal.

### Spinning top
id: spinning_top · aka: spinning top candle
What: small body, wicks on both sides longer than the body. Indecision; meaningful only at a level or after a run.

### Bullish marubozu
id: bull_marubozu · aka: marubozu, white marubozu, green marubozu
What: a big green candle with almost no wicks. Buyers controlled the whole period. Continuation more often than reversal; chasing it buys at the extreme.

### Bearish marubozu
id: bear_marubozu · aka: black marubozu, red marubozu
What: a big red candle with almost no wicks. Sellers controlled the whole period.

### Bullish belt hold
id: bull_belt_hold · aka: belt hold
What: after a decline, a big green candle that opens at its low and closes near its high.

### Big green candle
id: big_bull_bar · aka: momentum ignition, expansion candle, wide range bar, elephant bar
What: a candle at least 2× normal size (ATR) closing strong. Momentum traders follow it; mean-reverters fade it.
Jarvus: playbook-level momentum entries need the volatility gate LOUD and the 1h/4h trend up.

### Big red candle
id: big_bear_bar · aka: capitulation candle, flush, liquidation candle
What: a candle at least 2× normal size closing weak. Often liquidations. Buying it is catching a falling knife unless a reclaim follows.

### Bullish engulfing
id: bull_engulfing · aka: engulfing, bullish engulfing pattern
What: after a decline, a red candle followed by a green candle whose body covers the red body.
Read it: buyers overpowered the prior sellers. Best at support or after a sweep; stop under the pattern low.

### Bearish engulfing
id: bear_engulfing · aka: bearish engulfing pattern
What: after a rise, a green candle followed by a red one whose body covers it. A take-profit/avoid signal for spot traders.

### Bullish harami
id: bull_harami · aka: harami, inside candle bullish
What: after a decline, a big red candle followed by a small candle whose body sits inside the red body. Selling pressure paused; weaker than engulfing; needs confirmation.

### Bearish harami
id: bear_harami · aka: bearish harami pattern
What: after a rise, a big green candle followed by a small body inside it. Buying paused.

### Bullish harami cross
id: bull_harami_cross · aka: harami cross
What: a bullish harami whose second candle is a doji. Stronger pause signal than a plain harami.

### Piercing line
id: piercing_line · aka: piercing pattern
What: after a decline, a big red candle then a green one that opens at/below the red close and closes above the red body's midpoint (not above its open).

### Dark cloud cover
id: dark_cloud_cover · aka: dark cloud
What: after a rise, a big green candle then a red one that opens at/above its close and closes below its midpoint.

### Tweezer bottom
id: tweezer_bottom · aka: tweezers, tweezer bottoms
What: two candles with (almost) the same low after a decline, the first red, the second green. A level defended twice.

### Tweezer top
id: tweezer_top · aka: tweezer tops
What: two candles with the same high after a rise, green then red. A level rejected twice.

### Bullish kicker
id: bull_kicker · aka: kicker, kicking pattern
What: a strong red candle followed by a strong green one that opens above the red's open (a gap). Needs gaps, so it is almost absent on 24/7 crypto charts; seen on stocks and CME futures.

### Outside bar up
id: outside_bar_up · aka: outside bar, outside reversal, key reversal
What: a candle whose range covers the prior candle and closes above the prior high.

### Outside bar down
id: outside_bar_down · aka: bearish outside bar
What: a candle whose range covers the prior one and closes below the prior low.

### Inside bar
id: inside_bar · aka: inside day, harami bar, mother bar
What: a candle entirely within the prior candle's range. Compression: a bigger move often follows, direction unknown.

### Inside bar breakout up
id: inside_bar_break_up · aka: inside bar breakout
What: after an inside bar, a close above the mother bar's high. Stop under the mother bar's low or mid.

### Inside bar breakdown
id: inside_bar_break_down · aka: inside bar breakdown
What: after an inside bar, a close below the mother bar's low.

### NR7 breakout
id: nr7_break_up · aka: nr7, nr4, narrow range 7, narrow range breakout
What: the narrowest candle of the last 7 (NR7), then a close above its high. Volatility contraction → expansion idea (Crabel).

### Morning star
id: morning_star · aka: morning star pattern
What: three candles after a decline: a big red, a small-bodied candle, then a green that closes above the red's midpoint. A classic bottom pattern.

### Evening star
id: evening_star · aka: evening star pattern
What: three candles after a rise: a big green, a small body, then a red closing below the green's midpoint.

### Morning doji star
id: morning_doji_star · aka: doji star bottom
What: a morning star whose middle candle is a doji.

### Evening doji star
id: evening_doji_star · aka: doji star top
What: an evening star whose middle candle is a doji.

### Abandoned baby
aka: abandoned baby bottom, abandoned baby top, island doji
What: a doji that gaps away from the candles on both sides (a one-candle island). Requires gaps, so it is essentially absent on 24/7 crypto; not measured.

### Three white soldiers
id: three_white_soldiers · aka: 3 white soldiers
What: three strong green candles in a row, each closing higher and opening inside the prior body. Shows steady buying; late in a move it can mark exhaustion.

### Three black crows
id: three_black_crows · aka: 3 black crows
What: three strong red candles in a row, each closing lower. Steady selling.

### Advance block
aka: advance block, deliberation, stalled pattern
What: three green candles with shrinking bodies and growing upper wicks. Buying is tiring. Not measured.

### Three inside up
id: three_inside_up · aka: three inside up pattern
What: a bullish harami followed by a candle closing above the first candle's open (the harami, confirmed).

### Three inside down
id: three_inside_down · aka: three inside down pattern
What: a bearish harami followed by a close below the first candle's open.

### Three outside up
id: three_outside_up · aka: three outside up pattern
What: a bullish engulfing followed by a higher close (the engulfing, confirmed).

### Three outside down
id: three_outside_down · aka: three outside down pattern
What: a bearish engulfing followed by a lower close.

### Bullish three-line strike
id: bull_three_line_strike · aka: three line strike
What: three black crows, then one big green candle that wipes them out (closes above the first crow's open). Rare.

### Bearish three-line strike
id: bear_three_line_strike · aka: bearish three line strike
What: three white soldiers, then one red candle that closes below the first soldier's open. Rare.

### Rising three methods
id: rising_three · aka: rising three, mat hold
What: a big green candle, three small candles drifting inside its range, then a green close above it. A continuation pattern (a tiny bull flag).

### Falling three methods
id: falling_three · aka: falling three
What: a big red candle, three small candles inside its range, then a red close below it. Continuation down.

### Rare gap-based patterns
aka: tasuki gap, upside gap two crows, on neck, in neck, thrusting, separating lines, stick sandwich, homing pigeon, ladder bottom, concealing baby swallow, unique three river, tri-star, side by side white lines
What: the long tail of Japanese patterns (Nison, Bulkowski). Most need opening gaps or exact open/close relationships that 24/7 crypto rarely produces, so they fire a handful of times. Jarvus did not measure them; treat them as curiosities, not signals.

### Heikin-Ashi candles
aka: heikin ashi, ha candles
What: smoothed candles: HA close = average of O/H/L/C; HA open = midpoint of the previous HA body. Trends show as runs of one colour with no opposite wick.
Trap: HA prices are not real prices; never place orders at HA levels. See also "Heikin-Ashi turns green".

### Renko, Kagi, Point & Figure, range bars
aka: renko, kagi, point and figure, p&f, range bars, line break
What: charts built from price movement instead of time (a new brick/column only after a set move). They hide noise and time.
Trap: backtests on Renko often cheat by using brick prices you could not have traded. Not measured.

### Candle patterns: what the evidence says
aka: do candlestick patterns work, candle pattern win rate, are candlestick patterns reliable
What: an academic test on Dow stocks (Marshall, Young & Rose, 2006) found candlestick strategies added no value; Bulkowski's catalogue shows big differences between patterns. Jarvus measured 45 crypto candle patterns itself (`python3 scripts/know.py measured candles`, full table `references/kb-measured.md`): only the big green candle on 4h beat random entries and made money in both halves.
Use: patterns are entry triggers at a level, inside a plan with a stop and a cost check — never a reason to trade by themselves.
