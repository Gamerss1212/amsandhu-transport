# Knowledge base: chart patterns, price structure, levels, SMC/ICT, Wyckoff, Elliott, Fibonacci, harmonics

One entry per `### `. `python3 scripts/know.py <name>` prints one entry plus Jarvus's measured result when it has an `id`.

### Support and resistance
aka: support, resistance, s/r, levels, key levels, sr flip, role reversal
What: prices where buying (support) or selling (resistance) showed up before: prior swing highs/lows, range edges, round numbers, prior-day high/low, high-volume nodes.
Use: buy near support with a stop just beyond it; after a clean break, old resistance often becomes support (flip).
Trap: levels are zones, not lines; crypto often sweeps them (wick through, close back) before reversing.

### Trendlines and channels
aka: trendline, trend line, channel, ascending channel, descending channel, parallel channel
What: a line through two or more swing lows (uptrend) or highs (downtrend); a channel adds a parallel line on the other side.
Trap: trendlines are subjective (two traders draw two lines). Breaks are frequently false. Jarvus measures structure with swing points instead.

### Market structure (HH/HL, LH/LL)
aka: market structure, higher highs higher lows, lower highs lower lows, swing structure, trend structure
What: uptrend = higher highs and higher lows; downtrend = lower highs and lower lows; range = neither.
Use: trade with the structure of the higher timeframe; a broken structure is the first warning of a trend change.

### Break of structure (BOS)
id: bos_up · aka: bos, break of structure
What: in an uptrend (HH/HL), a close above the last swing high: continuation.

### Change of character (CHoCH)
id: choch_up · aka: choch, change of character, mss, market structure shift
What: in a downtrend (LH/LL), the first close above the last lower high: the first sign the trend may be turning up. Unconfirmed until a higher low forms.

### Change of character down
id: choch_down · aka: bearish choch, bearish mss
What: in an uptrend, the first close below the last higher low. For spot: protect profits / stop buying.

### Double bottom
id: double_bottom · aka: w bottom, double bottom pattern
What: two similar lows with a peak (neckline) between; confirmed by a close above the neckline. Classic target = neckline + (neckline − low).

### Double top
id: double_top · aka: m top, double top pattern
What: two similar highs with a trough between; confirmed by a close below the neckline.

### Triple top and bottom
aka: triple top, triple bottom
What: like double tops/bottoms with a third test. Rarer; same neckline logic. Not measured separately.

### Inverse head and shoulders
id: inverse_hs · aka: inverse head and shoulders, ihs, inverted head and shoulders
What: three lows, the middle (head) lowest, shoulders similar; confirmed by a close above the neckline.

### Head and shoulders top
id: hs_top · aka: head and shoulders, h&s, hns
What: three highs, the middle highest; confirmed by a close below the neckline. Spot reading: sell/avoid.

### Ascending triangle
id: asc_triangle · aka: ascending triangle, flat top triangle
What: flat highs with rising lows; buyers pressing a fixed supply. Breakout = close above the flat top.

### Descending triangle
id: desc_triangle · aka: descending triangle, flat bottom triangle
What: flat lows with falling highs; breakdown = close below the flat bottom.

### Symmetrical triangle
id: sym_triangle_up · aka: symmetrical triangle, symmetric triangle, coil
What: falling highs and rising lows converging; breakout direction is not known in advance.

### Falling wedge
id: falling_wedge · aka: falling wedge, descending wedge
What: highs and lows both falling, converging; traditionally bullish on an upside break.

### Rising wedge
id: rising_wedge · aka: rising wedge, ascending wedge
What: highs and lows both rising, converging; traditionally bearish on a downside break.

### Broadening formation
aka: broadening wedge, megaphone, expanding triangle
What: higher highs and lower lows at once: volatility expanding, no control. Not measured.

### Bull flag
id: bull_flag · aka: flag, bull flag, high tight flag, pennant
What: a sharp rise (pole), a short tight pause drifting sideways/down (flag) or converging (pennant), then a break up. Classic target = pole length added to the breakout.

### Bear flag
id: bear_flag · aka: bear flag, bear pennant
What: a sharp drop, a short pause, then a break down.

### Cup and handle
aka: cup and handle, cup with handle, rounding bottom, saucer
What: a rounded U-shaped base, a small pullback (handle), then a breakout over the rim (O'Neil). Slow, multi-week pattern; hard to define mechanically. Not measured by Jarvus.

### Rectangle / range
aka: rectangle, range, trading range, box, consolidation, sideways
What: price bouncing between a flat top and bottom. Inside: fade the edges with tight risk; outside: trade the confirmed break or the failed break (sweep).
Jarvus: range-edge fades are in the strategy encyclopedia; the volatility gate decides whether a range is worth trading at all.

### Measured move
aka: measured move, abcd, ab=cd
What: the idea that a second leg tends to equal the first. Used for targets, not entries. No evidence it beats a fixed R target.

### V-reversal and island reversal
aka: v bottom, v reversal, spike reversal, island reversal
What: a sharp reversal with no base, often after liquidations. Hard to trade in real time; you only know it afterwards.

### Gaps and CME gaps
aka: gap, cme gap, gap fill, weekend gap
What: crypto spot trades 24/7, so true gaps appear on CME Bitcoin futures (historically closed on weekends). "CME gaps always fill" is folklore: many fill, some take months, and the claim is easy to cherry-pick.

### Fair value gap (FVG)
id: fvg_retest · aka: fvg, fair value gap, imbalance, inefficiency, liquidity void
What: a 3-candle move where candle 3's low is above candle 1's high (bullish); the gap is said to be "rebalanced" later. Entry idea: first return into the gap that holds.

### Order block
id: ob_retest · aka: order block, ob, bullish order block, institutional candle
What: in ICT/SMC terms, the last opposite candle before a strong move that breaks structure; price returning to it is the entry idea.
Trap: the definition is loose; almost any chart can be annotated after the fact.

### Breaker and mitigation blocks
aka: breaker block, breaker, mitigation block, rejection block, propulsion block
What: ICT variants of the order block (a failed order block that flips role, etc.). Same caveat: discretionary, not measured.

### Liquidity, sweeps and stop hunts
aka: liquidity, liquidity grab, liquidity sweep, stop hunt, equal highs, equal lows, buy side liquidity, sell side liquidity, inducement, judas swing, turtle soup
What: stops cluster beyond obvious highs/lows (equal highs/lows, prior-day high/low). Price often runs them, then reverses. Turtle soup (Connors/Raschke) = fade a new 20-bar low that fails.
Jarvus: P4 sweep reclaim and the prior-day-low sweep are measured versions.

### Prior-day low sweep
id: pdl_sweep · aka: pdl, previous day low, pdl sweep, sweep of yesterday's low
What: price trades below yesterday's low, then closes back above it.

### Prior-day high breakout
id: pdh_break · aka: pdh, previous day high, pdh breakout
What: the first close above yesterday's high that day.

### Prior-day high rejection
id: pdh_reject · aka: pdh sweep, failed breakout above yesterday's high
What: price trades above yesterday's high and closes back below it.

### Premium, discount and OTE
aka: premium, discount, ote, optimal trade entry, equilibrium
What: ICT terms: above the 50% of a range = premium (sell zone), below = discount (buy zone); OTE = the 62–79% retracement. A Fibonacci retracement by another name.

### ICT concepts
aka: ict, inner circle trader, smc, smart money concepts, smart money, kill zone, killzone, silver bullet, power of 3, po3, amd, accumulation manipulation distribution, market maker model
What: a popular discretionary vocabulary (Michael Huddleston): liquidity, FVGs, order blocks, kill zones (session windows), "Power of 3" (accumulate, manipulate/sweep, distribute).
Evidence: no audited track record; Jarvus measured the mechanical parts (FVG retest, order-block retest, BOS/CHoCH, sweeps): see their entries. Kill zones overlap with the session effect Jarvus already uses.

### Wyckoff method
aka: wyckoff, accumulation, distribution, spring, upthrust, utad, composite man, wyckoff schematic
What: phases of a range: accumulation (selling climax, test, spring = false break down, sign of strength, markup) and distribution (buying climax, upthrust = false break up, markdown).
Use: a spring is a sweep-and-reclaim of the range low; an upthrust is the reverse. Phase labels are only clear in hindsight.

### Elliott wave
aka: elliott, elliott wave, wave count, impulse wave, abc correction, wave 3
What: markets move in 5-wave impulses and 3-wave corrections (Elliott, 1930s). Wave 3 is "never the shortest".
Trap: counts are subjective and get re-labelled after the fact; not testable as written. Not measured.

### Fibonacci retracement
id: fib_618 · aka: fibonacci, fib, fibs, golden ratio, 0.618, 61.8, 0.5 retracement, golden pocket
What: retracement levels 23.6/38.2/50/61.8/78.6% of a swing; "golden pocket" = 61.8–65%.
Trap: with five levels, price is always near one. Use only with another reason (prior level, trend).

### Fibonacci extensions
aka: fib extension, 1.618, 1.272, fibonacci targets
What: projected targets beyond a swing (127.2%, 161.8%). Targets, not signals.

### Harmonic patterns
aka: harmonic, harmonics, gartley, bat pattern, butterfly pattern, crab pattern, shark pattern, cypher, xabcd
What: XABCD shapes with Fibonacci-ratio legs (Gartley 1935; Carney). Entry at the "potential reversal zone" D.
Trap: many ratio tolerances = many chances to fit noise. Not measured.

### Floor pivot points
id: pivot_s1 · aka: pivot points, pivots, floor pivots, s1, s2, r1, r2, camarilla, woodie pivots, fibonacci pivots
What: P = (yesterday's high + low + close)/3; R1 = 2P − low; S1 = 2P − high. Camarilla/Woodie/Fib are variants.
Use: intraday reference levels; meaning comes from reactions, not the formula.

### Pivot R1 rejection
id: pivot_r1_reject · aka: r1 rejection
What: price trades above R1 and closes back below it.

### RSI bullish divergence
id: rsi_bull_div · aka: bullish divergence, positive divergence, hidden divergence
What: price makes a lower low while RSI makes a higher low: momentum fading on the way down. Hidden divergence = the reverse in a trend (continuation).
Trap: divergences can repeat several times before a turn.

### RSI bearish divergence
id: rsi_bear_div · aka: bearish divergence, negative divergence
What: price makes a higher high while RSI makes a lower high.

### Supply and demand zones
aka: supply zone, demand zone, supply and demand, rally base rally, drop base drop
What: the base (small candles) before a sharp move away; price returning to it is the entry idea. Close cousin of order blocks; discretionary. Not measured.

### Round numbers
aka: round number, psychological level, big figure, 100k
What: prices like $100,000 BTC attract orders and attention; expect reactions and sweeps around them.

### Dow theory
aka: dow theory, primary trend, secondary trend
What: trends have primary/secondary/minor moves; a trend persists until clear reversal signals; volume should confirm. The root of modern trend-following.

### Chart patterns: what the evidence says
aka: do chart patterns work, chart pattern win rate, pattern reliability
What: Bulkowski's catalogues report pattern statistics on stocks; Lo, Mamaysky & Wang (2000) found some patterns carry modest information. Jarvus measured 24 crypto chart-pattern and structure signals: none both beat random entries and made money after fees in both halves (`references/kb-measured.md`).
