# The Strategy Encyclopedia

Every serious trading strategy family, written in one consistent format so Claude
can recognize what a user is describing, explain it, evaluate it against current
conditions, and test it. Strategies are numbered for reference. The seven core
playbooks in `playbooks.md` are the curated subset that fits crypto day trading
best; everything else here is context, alternatives, and the things a user will
ask about.

## Contents

- Part 0. Read this first: the truth about win rates
- Part 1. How to use this file and the confluence scoring system
- Part 2. The High-Probability Program (the honest path to a high win rate)
- Part 3. Trend-following and momentum (strategies 1-16)
- Part 4. Mean reversion and range (17-32)
- Part 5. Breakout (33-44)
- Part 6. Liquidity, order flow, and "smart money" concepts (45-60)
- Part 7. Derivatives and positioning (61-70)
- Part 8. Time and session based (71-80)
- Part 9. Cross-asset and relative value (81-90)
- Part 10. News, catalysts, and events (91-98)
- Part 11. Scalping and micro-structure (99-105)
- Part 12. Classic indicator systems and named methodologies (106-130)
- Part 13. Chart, candle, and volume-profile pattern catalog (131-145)
- Part 14. Quantitative and systematic approaches (146-155)
- Part 15. Management overlays: sizing, pyramiding, trailing, exits (156-165)
- Part 16. Strategies that lose, and why (166-175)
- Part 17. Choosing: a decision table by regime, session, and skill level

**Volume II — the rest of the field**

- Part 18. Options and volatility strategies (176-195)
- Part 19. DeFi-native and on-chain (196-215)
- Part 20. Portfolio, allocation and systematic capital (216-232)
- Part 21. Execution algorithms and cost strategies (233-245)
- Part 22. Seasonality, calendar and cycle (246-258)
- Part 23. Sentiment, alt-data and flow (259-272)
- Part 24. Arbitrage and market-neutral (273-288)
- Part 25. Remaining named systems and completions (289-320)
- **Part 26. The 80% experiment — what a high win rate is actually made of (measured)**

Format for every entry:

```
### N. Name
Family · Timeframes · Best regime · Typical profile (win rate / average R, from retail-scale backtests; verify)
Thesis: why it should work at all
Rules: context / entry / stop / target / management
Fails when: the conditions that break it
Crypto notes: what changes on a 24/7 leveraged market
Test: the mechanical version to backtest, and what to log
```

---

## Part 0. Read this first: the truth about win rates

Users ask for "an 85% win rate strategy". Here is what that request actually
means and how to answer it honestly.

**Win rate is a dial, not a goal.** Any strategy's win rate can be pushed up by
taking profit closer and putting the stop further away. A strategy that targets
0.3R with a 3R stop wins about 85-90% of the time and loses money, because the
one loss erases ten wins. A strategy that targets 3R with a 1R stop wins about
30-35% of the time and makes money. The trade-off is nearly mechanical.

| Target / stop | Typical win rate | Expectancy per trade (before costs) |
|---|---|---|
| 0.25R / 1R | 80-88% | roughly zero to slightly negative |
| 0.5R / 1R | 65-72% | roughly zero |
| 1R / 1R | 48-55% | slightly positive with a real edge |
| 2R / 1R | 36-45% | +0.1 to +0.35R with a real edge |
| 3R / 1R | 28-35% | +0.1 to +0.4R with a real edge |

The lines sit near zero because markets are close to efficient on short horizons.
A **real edge** moves every row up by a few points of win rate or a few tenths of
an R. That is what selectivity, structure, positioning data, and session timing
buy. They do not buy 85% on 2R targets. Nothing does.

**This is no longer just an argument — it has been measured.** On 78,000 hourly
candles of BTC, ETH and SOL, an 80% win rate was successfully built: sell half the
position at +0.25R and move the stop to breakeven, and **79.5% of trades close
green**. The same exit rules applied to *deliberately random entries* produce
**78.6%**. The win rate is manufactured entirely by the exit ladder, and it is worth
**+0.012R gross and negative at every retail fee tier**. The configuration that
actually made money won only 51% of the time. Part 26 has the full tables, the
out-of-sample split, and the code to reproduce it. Read it before quoting any win
rate, including your own.

**What a documented high-win-rate day trader actually does:**

1. Takes only A-grade confluence setups (see Part 1), which raises the base win
   rate of a 2R setup from ~40% toward 50-55%.
2. Scales out a third to a half at ~1R, which converts many would-be losers into
   small winners or scratches. Measured by "trades closed above zero", the rate
   climbs toward 60-70%.
3. Moves the stop to breakeven after the partial, which turns further would-be
   losers into scratches. Counted as non-losers, 70%+ is reachable.
4. Never trades into events, on weekends, or against the higher timeframe.
5. Trades 1-3 times a day, not 20.

Measured honestly (every trade, R-weighted, including scratches as zero), that
trader's win rate is 50-60% and their average win is 1.3-1.8R. Their expectancy
is roughly +0.3 to +0.5R per trade. That is elite. It compounds an account
several times a year at 1% risk with modest drawdowns. Nobody with a verified
track record does materially better than that over hundreds of trades.

**How to say this to the user:** "85% is achievable only by making the targets
tiny and the stops huge, which loses money. The version of 'high win rate' that
actually pays is 55-65% of trades closing green with winners bigger than losers.
Here is the program that gets there." Then give Part 2.

## Part 1. How to use this file and the confluence scoring system

### Using the encyclopedia

- **User names a strategy** ("what about turtle soup?"): find it, explain the thesis
  and rules, then evaluate it against *today's* regime and the user's timeframe,
  and say which core playbook it maps to.
- **User describes a setup without naming it**: match the description to an entry,
  name it, and show the rules they are missing (usually the stop and the
  skip-when).
- **User wants "the best strategy"**: there is none; use Part 17's decision table
  to pick by regime, session, and experience, then Part 2 to filter.
- **User wants to test one**: the "Test" line gives the mechanical rules;
  `scripts/backtest.py` shows how to add a strategy function.

### The confluence scoring system

Every candidate trade gets scored before the plan card is written. Ten factors,
one point each; alts and memes need one point more at every grade.

| # | Factor | Point if |
|---|---|---|
| 1 | HTF bias | 1D and 4H trend agree with the trade direction (or HTF is a range and the trade is at its edge) |
| 2 | EMA regime | Price on the correct side of the 200 EMA on the setup timeframe and the 21/50 stack agrees |
| 3 | Location | Entry is at a tier-1 level or value zone (PDH/PDL, range edge, 21 EMA, VWAP, order block, sweep of equal highs/lows), not mid-range |
| 4 | Trigger | A closed candle confirms (reclaim, engulfing, CHoCH), not an anticipation |
| 5 | Volume | RVOL ≥ 1.5 on the trigger, or absorption/CVD confirms |
| 6 | Positioning | Funding and OI are not crowded in the trade direction; ideally crowded against it |
| 7 | Session | London/NY overlap or the first 90 minutes of NY; not late US, not Asia (unless the setup is Asia-specific), not weekend |
| 8 | Calendar | No tier-1 event within 30 minutes before or after; no token unlock inside 72h for alts |
| 9 | Reward | Net R:R to T2 ≥ 2 with no major level between entry and T1 |
| 10 | Stop quality | Stop beyond the invalidation with an ATR buffer, ≥ 0.5 ATR from entry, liquidation ≥ 3x the stop away |

- **9-10: A+** full risk (1%). These come a few times a week across three pairs.
- **8: A** full risk.
- **7: B** half risk, take T1 in full.
- **6 or below: skip.** Write what would add the missing points and wait.

`scripts/confluence.py` computes the mechanical subset of these from a snapshot
and derivatives JSON; factors 3, 4 and 9 still need a human or Claude reading the
chart.

## Part 2. The High-Probability Program

The closest honest answer to "give me the highest win rate". It is a filter, a
management rule, and a schedule, layered on the core playbooks.

**Filter**
- Trade only A and A+ confluence scores.
- Trade only playbooks 1, 3, 4, and 7 (pullback, breakout-retest, sweep reversal,
  VWAP reclaim). Range fades and funding fades stay off the list until 100
  journaled trades.
- BTC and ETH only for the first 100 trades. Alts add beta and wicks, which cost
  win rate.
- One session: the first three hours of New York (13:30-16:30 UTC in US summer).
  It has the most volume, the cleanest trends, and the fewest stop hunts per
  hour of screen time.

**Management**
- Partial: sell half at 1R (or at the first level, if closer).
- Stop to breakeven plus fees once the partial fills.
- Runner to 2R+ or trailed behind the last 5m higher low.
- Time stop: if 1R is not reached within 8 candles of the trigger timeframe, exit
  at market. Trades that do not work quickly usually do not work.
- Hard cap: 3 trades per day, stop at −2R or +3R for the day.

**Schedule**
- Pre-session routine (`assets/daily-routine.md`) every day. No plan, no trade.
- Journal every trade with the confluence score. After 50 trades, check: do 9-10
  scores beat 7-8 scores? If not, the scoring is being fudged.

**Expected profile after 100 trades** (if executed): 55-65% of trades closed
green including scratches, average win 1.4R, average loss 0.9R, expectancy
+0.35R, max drawdown 6-9R. That is a professional result. Promising more would
be dishonest.

---

## Part 3. Trend-following and momentum

### 1. Trend pullback to the 21 EMA
Trend · 5m-4H · Trend days, HTF trend · ~45-55% / 1.8R
Thesis: in a trend, the people who bought the last leg defend the average price of it; the 21 EMA approximates that.
Rules: context: 21 > 50 > 200 EMA, price made a HH; entry: price touches the 21 EMA and a trigger-timeframe candle closes back above the 9 EMA; stop: below the pullback low minus 0.3 ATR; target: prior high (T1), measured move (T2); management: half at T1, stop to BE, trail the rest.
Fails when: the pullback is the first leg of a reversal (retraces > 70%), or the trend is mature (many legs, RSI divergence, hot funding).
Crypto notes: works best on BTC/ETH in the London/NY overlap; on alts require BTC to be flat or aligned.
Test: `backtest.py --strategy ema_pullback`. Log the number of legs since the trend started.

### 2. Moving-average crossover with trend filter
Trend · 15m-4H · Strong trends · ~35-45% / 2R (lots of whipsaw in ranges)
Thesis: a fast average crossing a slow one captures a change in momentum.
Rules: context: price above the 200 EMA (longs only); entry: 9 EMA closes above 21 EMA after being below, ADX > 20 or Bollinger width expanding; stop: below the last swing low; target: trail on a 21 EMA close; management: none until trail.
Fails when: the market ranges; crossovers whipsaw repeatedly and the losses stack.
Crypto notes: crossovers on the 15m in Asia session are mostly noise. Use as a regime signal, not an entry.
Test: crossover long above the 200 EMA, exit on reverse cross. Compare with and without the ADX filter.

### 3. Break of structure, higher-low entry
Trend · 5m-1H · Emerging trends · ~45-50% / 2R
Thesis: after a BOS, the first higher low is where new-trend buyers show their hand; entering there has a clear invalidation.
Rules: context: price closes above the last swing high (BOS) on volume; entry: the first pullback forms a higher low above the broken level and a 5m candle closes above the pullback's last lower high (CHoCH up on the micro); stop: below the higher low; target: 2R or the next HTF level; management: standard.
Fails when: the BOS was a sweep (wick with a close back inside); the higher low forms *below* the broken level (failed retest).
Crypto notes: excellent after a cascade reset when OI has dropped 10%+.
Test: define swings with n=3, BOS = close above prior swing high, entry on next swing low confirmation.

### 4. Momentum ignition (expansion candle continuation)
Momentum · 1m-15m · Trend days, post-news · ~40-50% / 1.5-2R
Thesis: an unusually large candle on volume signals an imbalance that usually extends before it mean-reverts.
Rules: context: a candle with range ≥ 2 ATR and RVOL ≥ 3 in the HTF direction; entry: on the first small pullback (1-3 candles) that does not retrace more than 50% of the ignition candle, on a close back in the direction; stop: below the 50% of the ignition candle; target: 1x the ignition candle's range from the pullback low (T1), 2x (T2); management: fast; partial at T1.
Fails when: the ignition candle was the climax of a move (third expansion candle in a row, into an HTF level); when it was a news spike that reverses.
Crypto notes: liquidation cascades create ignition candles that *reverse*; check whether OI dropped sharply on the candle (cascade) or rose (new positioning).
Test: ignition = range/ATR ≥ 2 and RVOL ≥ 3; entry next candle close if pullback < 50%.

### 5. Donchian channel breakout (intraday turtle)
Trend · 15m-4H · Trending markets · ~30-40% / 2.5R+
Thesis: a new N-period high means the path of least resistance is up; the original Turtle system.
Rules: context: 20-period Donchian channel; entry: close above the 20-period high; stop: 2 ATR below entry, or the 10-period low; target: none; exit on a close below the 10-period low; management: pyramid at each 0.5 ATR of progress (classic), or do not (simpler).
Fails when: ranges (the majority of the time); win rate is low and drawdowns are long. Needs discipline.
Crypto notes: the classic system was for daily bars; on intraday crypto, filter with the 4H trend and the session (breakouts during Asia fail more).
Test: breakout of 20-bar high, exit on 10-bar low. Compare with the 4H 200 EMA filter.

### 6. Supertrend / ATR trailing stop system
Trend · 15m-4H · Trends · ~40% / 2R
Thesis: an ATR-based trailing line flips when price crosses it; it keeps you in trends and out of the worst of the chop.
Rules: context: Supertrend(10, 3) on the setup timeframe agrees with the 4H direction; entry: on the flip, or better, on the first pullback to the line after the flip; stop: the line itself; target: trail until the line flips.
Fails when: choppy ranges flip the line repeatedly.
Crypto notes: use multiplier 3-4 on crypto; 2 is too tight for the wicks.
Test: enter on flip, exit on opposite flip; then test "enter on first retest of line".

### 7. Ichimoku trend entry
Trend · 1H-1D · Established trends · ~40-45% / 2R
Thesis: the cloud (Senkou spans) represents equilibrium; price above a rising cloud with the Tenkan above the Kijun is a trend with support underneath.
Rules: context: price above the cloud, cloud green and rising, Chikou above price 26 periods ago; entry: pullback to the Kijun-sen (26) or the top of the cloud with a bullish close; stop: below the cloud; target: measured move or trail on a Kijun cross.
Fails when: price is inside the cloud (no trade zone); cloud flat.
Crypto notes: many crypto traders use doubled settings (20/60/120/30) for 24/7 markets. Either works; consistency matters more.
Test: entry on Kijun touch + close above, above the cloud; exit on close below the Kijun.

### 8. Parabolic SAR trail
Trend · 15m-1H · Strong trends · ~35% / 2R
Thesis: an accelerating stop that captures parabolic legs.
Rules: use only as an exit for a runner in a trend (SAR step 0.02, max 0.2); as an entry it whipsaws.
Fails when: anything other than a persistent trend.
Crypto notes: crypto's parabolic phases are where it shines: hold the runner until SAR flips.
Test: compare runner exits: SAR vs 21 EMA close vs 5m swing low trail.

### 9. ADX trend-strength filter (Raschke's Holy Grail)
Trend · 15m-1H · Strong trends · ~50-55% / 1.5R
Thesis: ADX(14) > 30 and rising marks a genuine trend; the first pullback to the 20 EMA in such a trend is a high-probability continuation. Linda Raschke's "Holy Grail".
Rules: context: ADX > 30 and rising; entry: price pulls back to the 20 EMA; buy stop above the high of the pullback candle; stop: below the pullback low; target: the prior high (T1), then trail; management: if the first attempt fails, re-enter once on the next test.
Fails when: ADX is falling (trend maturing) or below 20.
Crypto notes: one of the best-behaved trend entries on BTC 15m during NY hours.
Test: needs an ADX implementation; add to indicators.py if the user wants it.

### 10. Stair-step continuation (5m HH/HL within the 1H trend)
Trend · 1m-15m · Trend days · ~50% / 1.5R
Thesis: trend days advance in steps: impulse, shallow pullback, impulse. Each higher low is an entry with the stop below it.
Rules: context: 1H trend, day classified as a trend day (price on one side of VWAP, RVOL up); entry: buy the break of the last 5m lower high after a 2-5 candle pullback; stop: below the pullback low; target: the last high (T1), 1x the last impulse (T2).
Fails when: the pullback exceeds 3 ATR (5m) or breaks the 5m 21 EMA on volume: the step structure is broken.
Crypto notes: trend days are ~25% of days; identify them by 11:00 UTC (London) or 14:30 UTC (NY).
Test: count the number of successful steps per trend day; the third and later steps have lower win rates.

### 11. Measured-move / three-push continuation
Trend · 15m-4H · Trends · ~45% / 2R
Thesis: trends often produce legs of similar length (AB = CD); the third push frequently completes the move and exhausts.
Rules: context: two clear impulse legs of similar size separated by a pullback; entry: at the start of the third leg (the pullback's higher low confirmed); stop: below the pullback; target: the projected measured move (length of leg 1 from the pullback low); management: take most at the target because three-push completions often reverse.
Fails when: leg 2 was much shorter than leg 1 (momentum already fading).
Crypto notes: the measured move projection is also where liquidation clusters tend to sit; check the heatmap.
Test: leg detection with swings n=3; compare 1x projection vs 0.618x.

### 12. Flag / pennant continuation
Trend · 5m-1H · Trend days · ~45-50% / 2R
Thesis: a sharp move (the pole) followed by a tight, low-volume, counter-drift consolidation (the flag) usually resolves in the pole's direction.
Rules: context: pole of ≥ 2 ATR on volume, flag of 3-15 candles with declining volume, drifting against the pole; entry: close beyond the flag boundary in the pole direction with RVOL > 1.2; stop: beyond the opposite flag boundary (or the flag midpoint for a tighter version); target: the pole length projected from the breakout (T2), half of it (T1).
Fails when: the flag retraces more than 50% of the pole; volume rises during the flag (distribution, not rest); the flag lasts longer than the pole took to form.
Crypto notes: bull flags on the 15m during NY hours are among the most reliable continuation patterns on BTC; bear flags in downtrends equally.
Test: define pole and flag mechanically (range compression ratio); measure by flag depth.

### 13. Trend-day identification and opening drive
Trend · 5m-15m · Trend days · ~50% / 2R (on trend days; the skill is in identification)
Thesis: on a trend day, the best trade is to get in early and hold; the skill is recognizing the day.
Rules: signs by 30-60 minutes after the session open: opening range > 40% of daily ATR and one-directional; price never returns to VWAP; RVOL ≥ 1.5 on directional candles; gap from the prior close not filled; HTF breakout context. Entry: first pullback that holds VWAP or the 9 EMA; stop: below VWAP; target: 1.5-2 daily ATR from the open, or hold to the last hour.
Fails when: the "trend day" was an event spike; when the day is a range day (the majority).
Crypto notes: the 00:00 UTC open and the NY open both produce opening drives. FOMC/CPI days are trend days *after* the release, not before.
Test: label days as trend/range post hoc; check the identification rules' hit rate at 60 minutes in.

### 14. Anchored VWAP pullback
Trend · 15m-4H · Trends from a clear origin · ~50% / 2R
Thesis: VWAP anchored to the swing low that started the trend is the average cost of everyone who bought since; pullbacks to it are defended.
Rules: context: anchor to a major swing low (or high for shorts) or a catalyst candle; entry: first touch of the AVWAP with a rejection close; stop: below the AVWAP by 0.5 ATR; target: the trend high (T1), new high (T2).
Fails when: price closes below the AVWAP on volume (the trend's average buyer is underwater; expect liquidation).
Crypto notes: anchor to the post-cascade low or the ETF/news candle; it is uncanny how often it holds the first time and breaks the third.
Test: AVWAP from the last swing low of ≥ 3 ATR; entry on first touch + bullish close.

### 15. Heikin-Ashi trend riding
Trend · 15m-4H · Trends · ~40% / 2R
Thesis: Heikin-Ashi candles smooth noise; a run of same-colored candles without opposite wicks shows a strong trend.
Rules: entry: after a color flip when the second HA candle has no lower wick (longs); stop: below the last real-candle swing low; exit: on the first HA candle of the opposite color with a wick.
Fails when: chop produces alternating colors. HA candles hide the real price, so stops must be set on real candles.
Crypto notes: useful for holding runners without being shaken out; not for entries.
Test: entry on 2 consecutive wickless HA candles; exit on opposite color.

### 16. Time-series momentum (intraday)
Trend · 1H-1D · Trending regimes · ~50% / 1.2R
Thesis: assets that have risen over the last N hours/days tend to keep rising over the next short window; the academically documented momentum effect, weaker intraday.
Rules: entry: if the 24h return is above +X% (X ~ 1 daily ATR) and the 4H is trending, buy pullbacks (playbook 1) only in that direction; skip all counter-trend setups.
Fails when: momentum crashes (sharp reversals after extended runs), which are more frequent in crypto than in equities.
Crypto notes: more useful as a *filter* on the other playbooks than as a standalone entry.
Test: 24h return sign as a filter on ema_pullback; compare expectancy with and without.

## Part 4. Mean reversion and range

### 17. Range edge fade
Range · 15m-4H · Range days · ~45% / 1.5R
Thesis: a confirmed range means both sides have defended; the edges are where the defenders are.
Rules: (playbook 2) context: ≥ 2 touches each side, range ≥ 2.5 ATR; entry: rejection candle at the edge; stop: beyond the edge plus sweep allowance; target: midpoint (T1), opposite edge (T2).
Fails when: the fourth+ test; breakout context (squeeze, volume rising into the edge); session open within 30 min.
Crypto notes: Asia-session ranges are the most reliable to fade; NY ranges break more often.
Test: mechanical range = 60-candle high/low with ≥ 2 touches within 0.25 ATR of each; entry on close back inside after a touch.

### 18. Bollinger band reversal
Range · 15m-4H · Range days · ~45-50% / 1.2R
Thesis: a close outside 2σ is statistically rare; a close back inside signals the excursion has ended.
Rules: context: bands not expanding (bandwidth flat), no band walk; entry: close outside, then close back inside; stop: beyond the extreme plus 0.3 ATR; target: the middle band (20 SMA) or 1.5R, whichever is farther but realistic.
Fails when: band walks (strong trends): price closes outside repeatedly. The EMA stack filter avoids most of these.
Crypto notes: the bundled `range_fade` strategy is this, with a trend filter and a minimum R:R.
Test: `backtest.py --strategy range_fade`.

### 19. Keltner channel fade
Range · 15m-1H · Ranges · ~45% / 1.2R
Thesis: Keltner channels (EMA ± ATR multiple) adapt to volatility; a poke outside the 2.5 ATR channel with a rejection tends to revert to the EMA.
Rules: same as 18 with Keltner(20, 2.5); the channel is smoother, so fewer signals and slightly better quality.
Fails when: trend days.
Crypto notes: the "TTM squeeze" (Bollinger inside Keltner) is the compression signal that precedes breakouts; see 35.
Test: compare Keltner and Bollinger fades over the same period.

### 20. RSI(2) extreme mean reversion (Connors)
Range · 1H-1D · Ranges and pullbacks in uptrends · ~60-65% / 0.8R
Thesis: a two-period RSI below 10 marks a short-term washout; in an uptrend (above the 200 SMA) it usually bounces within a few bars. Larry Connors' equity system, adapted.
Rules: context: price above the 200 EMA; entry: RSI(2) < 10 at the close; stop: none in the original (use 2 ATR in crypto); target: close above the 5-period SMA, or RSI(2) > 70.
Fails when: crashes; the "no stop" original is unacceptable on leverage.
Crypto notes: works on the 4H for BTC in bull regimes; on the 15m it is noise.
Test: RSI(2) < 10 above the 200 EMA, exit on close > 5 SMA; add a 2 ATR stop and see how much it costs.

### 21. VWAP standard-deviation band fade
Range · 1m-15m · Range days · ~50% / 1R
Thesis: on a range day price oscillates around VWAP; the 2σ VWAP band is the statistical edge of the day's distribution.
Rules: context: VWAP flat, day classified as range; entry: touch of the 2σ band with a rejection close; stop: beyond the 3σ band; target: VWAP (T1), the opposite 1σ band (T2).
Fails when: the day turns into a trend day (VWAP starts sloping, price holds outside the 1σ band).
Crypto notes: excellent in the Asia session and on weekends *at reduced size*; terrible in the first hour of NY.
Test: needs VWAP bands (add to indicators.py: rolling std of price around VWAP).

### 22. Stretch from the 20 EMA reversal
Range · 5m-1H · Any, at extremes · ~50% / 1R
Thesis: price more than N ATR from its 20 EMA is a rubber band; it snaps back toward the mean more often than it keeps stretching.
Rules: context: distance from the 20 EMA ≥ 2.5 ATR; entry: first rejection candle (pin bar or engulfing) against the move; stop: beyond the extreme plus 0.5 ATR; target: the 20 EMA.
Fails when: news; liquidation cascades (the stretch keeps stretching). Wait for the candle close.
Crypto notes: the snapshot's "STRETCHED" flag is this condition; it is a reason not to chase before it is a reason to fade.
Test: stretch ≥ 2.5 ATR + rejection close; target the EMA.

### 23. Failed breakout / deviation (Wyckoff spring and upthrust)
Range · 15m-4H · Ranges · ~50-55% / 2R
Thesis: a break of the range edge that closes back inside within one to three candles traps breakout traders; their stops fuel the move to the other side. Wyckoff called the bullish version a spring and the bearish an upthrust.
Rules: context: established range; entry: close back inside after the deviation; stop: beyond the deviation extreme; target: the range midpoint (T1), the opposite edge (T2).
Fails when: the "deviation" holds outside for more than three candles (real breakout).
Crypto notes: the single most common profitable pattern in crypto ranges; it is playbook 4 at range edges.
Test: deviation = close outside then close inside within 3 candles; measure follow-through to the midpoint.

### 24. Double top / double bottom with neckline
Reversal · 15m-4H · Ranges, trend ends · ~45% / 2R
Thesis: two failures at the same level show exhaustion; the break of the neckline (the swing between the two tests) confirms.
Rules: entry: close below the neckline (short) or on the retest of the neckline from below; stop: above the second top; target: the pattern height projected from the neckline.
Fails when: the two tops are equal highs (liquidity) and the "second top" is actually a sweep that then reverses back up. Wait for the neckline break.
Crypto notes: equal highs in crypto are more often swept than respected; the sweep-then-neckline-break version is the reliable one.
Test: tops within 0.25 ATR; neckline break close; target = height.

### 25. Head and shoulders / inverse
Reversal · 1H-1D · Trend ends · ~45% / 2R
Thesis: a higher high (head) that fails and is followed by a lower high (right shoulder) is a change of character; the neckline break confirms.
Rules: entry: neckline break close, or the retest; stop: above the right shoulder; target: head-to-neckline distance projected.
Fails when: the pattern is drawn onto noise; requires the left shoulder, head, and right shoulder to each be clear swings on the timeframe.
Crypto notes: the right-shoulder area is often a sweep of the left shoulder's high; enter after that sweep fails.
Test: swing-based detection is complex; treat as discretionary and log it.

### 26. Asia range reversion
Range · 5m-15m · Asia session · ~50% / 1R
Thesis: the Asia session (00:00-07:00 UTC) usually ranges; fades of its edges toward its midpoint work until London arrives.
Rules: context: after 02:00 UTC, range established; entry: rejection at the Asia high/low; stop: beyond by 0.3 ATR; target: the Asia midpoint; exit everything by 06:45 UTC.
Fails when: Asia trends (it does about a quarter of the time, usually continuing a strong US session).
Crypto notes: reduced size; liquidity is thin and wicks are wide.
Test: Asia range = 00:00-04:00 UTC high/low; fade touches after 04:00; flat by 07:00.

### 27. Gap fill (CME and exchange gaps)
Range · 1H-1D · Post-weekend · ~60-65% / 0.8R
Thesis: CME Bitcoin futures gaps (from the Friday close to the Sunday open) fill most of the time, often within days.
Rules: context: a CME gap exists (spot moved over the weekend); entry: when price begins moving toward the gap during Monday's session with a structural trigger (playbook 1 or 7); stop: structural; target: the gap's far edge.
Fails when: the gap is a breakaway gap on news; when the fill takes weeks.
Crypto notes: gap fills are a *bias*, not a timing signal. Pair with a real trigger.
Test: log gap size, fill time, and whether the fill happened within 3 days.

### 28. Floor pivot bounce / rejection
Range · 5m-1H · Ranges · ~45% / 1.2R
Thesis: classic floor-trader pivots (P = (H+L+C)/3, R1/S1 etc. from the prior day) are widely watched and act as intraday levels.
Rules: entry: rejection candle at S1 (long) / R1 (short) when the day is a range day; stop: beyond S2/R2 minus buffer; target: the pivot.
Fails when: trend days (price goes through R1 to R2 to R3).
Crypto notes: PDH/PDL and the daily open matter more than pivots in crypto; use pivots as a secondary confluence.
Test: compute pivots from the prior UTC day; log reactions at each level.

### 29. Fibonacci retracement confluence pullback
Range/Trend · 15m-4H · Pullbacks in trends · ~45-50% / 2R
Thesis: the 0.5-0.618 retracement of an impulse (the "golden pocket") is where trend pullbacks tend to end, partly because so many traders watch it.
Rules: context: HTF trend; entry: pullback into 0.5-0.618 of the last leg that coincides with another level (21 EMA, order block, PDL) and a trigger candle; stop: below 0.786; target: the leg's high (T1), 1.272 extension (T2).
Fails when: no confluence (Fibonacci alone is weak); deep pullbacks past 0.786 are usually reversals.
Crypto notes: crypto pullbacks are deep; 0.618-0.786 is more typical than 0.382-0.5.
Test: entry on 0.618 touch with 21 EMA within 0.3 ATR; compare against random levels to check the edge is real.

### 30. Round-number reversal
Range · 5m-1H · Any · ~45% / 1.5R
Thesis: 10,000-multiples on BTC, 100s on ETH, 10s and 100s on alts attract limit orders and stops; first touches often reject, but they are also swept.
Rules: entry: only after a sweep-and-reclaim of the round number (playbook 4 rules); never on the first touch alone; stop and target per playbook 4.
Fails when: momentum is strong (round numbers break cleanly on trend days).
Crypto notes: ETH 3,000, BTC 100,000: these are also options strikes with large open interest, adding gamma effects around expiry.
Test: log sweeps vs holds at round numbers.

### 31. Overbought/oversold RSI in a range
Range · 15m-4H · Confirmed ranges · ~50% / 1R
Thesis: inside a range, RSI(14) > 70 / < 30 flags an edge test; useful only with the range context.
Rules: context: range confirmed; entry: RSI extreme *at the range edge* with a rejection candle; stop and target as 17.
Fails when: trends (RSI stays > 70 for hours).
Crypto notes: adjust the bands to the regime (see indicators.md).
Test: RSI extreme + range edge within 0.3 ATR + rejection close.

### 32. Grid trading in a range
Range · any · Confirmed, wide ranges · ~80-90% of individual orders win / negative tail
Thesis: place buy orders at intervals below price and sell orders above; capture oscillations.
Rules: define the range and grid spacing from ATR; total exposure at the bottom of the grid must be a position you are comfortable holding through a breakdown.
Fails when: price leaves the range. A grid is short volatility; the one breakdown can erase months of grid profits. Only viable with a hard stop on the whole grid and small notional.
Crypto notes: exchange grid bots are popular and mostly lose on the first trend; see Part 16.
Test: simulate on a ranging month, then on the month it broke.

## Part 5. Breakout

### 33. Breakout and retest
Breakout · 5m-4H · Compression into trend · ~45% / 2.5R
Thesis: (playbook 3) the retest of a broken level is where breakout buyers defend and late shorts cover.
Rules: context: consolidation or squeeze, breakout close on RVOL ≥ 1.5 and rising OI; entry: retest holds (wick into the level, close above) within a handful of candles; stop: below the retest low minus 0.3 ATR; target: breakout candle high (T1), measured move (T2).
Fails when: no retest; retest low inside the range by > 0.5 ATR; breakout into an HTF level < 2R away.
Crypto notes: breakouts in the Asia session without volume are the ones to fade, not buy.
Test: level = 60-candle high; break close; retest within 12 candles.

### 34. Opening range breakout (ORB)
Breakout · 5m-15m · NY/London open · ~45% / 1.8R
Thesis: (playbook 6) the first 15-30 minutes of a major session define the day's initial balance; the break of it with volume tends to extend.
Rules: OR = first 15 min high/low; entry: 5m close outside with RVOL ≥ 1.5, in the HTF direction; stop: opposite side of the OR (or midpoint if wide); target: 1 OR height (T1), PDH/PDL (T2).
Fails when: OR > 1.5 ATR (move already happened); tier-1 data in the first hour; break against both the HTF and the prior session.
Crypto notes: use the 13:30 UTC (summer) NY equities open, not 00:00 UTC, for the primary ORB; the 00:00 open produces its own but with thinner participation.
Test: OR 15 min; break close; exit at OR height or stop; count second-break failures.

### 35. Bollinger / Keltner squeeze breakout (TTM squeeze)
Breakout · 15m-4H · Compression · ~45% / 2R
Thesis: when Bollinger bands contract inside the Keltner channel, volatility is at a cycle low; the expansion that follows is directional.
Rules: context: bandwidth at a 100-candle low (the snapshot's SQUEEZE flag), or Bollinger inside Keltner; entry: first close outside the Bollinger band in the HTF direction with RVOL ≥ 1.5, or the retest of the band; stop: the middle band; target: 2R, or trail while the bands expand.
Fails when: the first break is a fake (frequent); the retest entry (33) avoids most of these.
Crypto notes: squeezes on the 4H resolve with 3-5% moves on BTC; on alts, 10%+.
Test: bandwidth percentile ≤ 10 then close outside band; measure the follow-through.

### 36. Inside bar / NR7 breakout
Breakout · 15m-4H · Compression in trend · ~45% / 2R
Thesis: an inside bar (or the narrowest range of the last 7, NR7) is one-bar compression; the break of the mother bar in the trend direction continues.
Rules: context: HTF trend; entry: stop order beyond the mother bar's high (longs) with the trend; stop: the mother bar's low (or midpoint for large mother bars); target: 2R or the next level.
Fails when: inside bars in the middle of ranges (both sides break).
Crypto notes: on the 4H and 1D, an inside bar after a big candle is one of the cleanest continuation signals in crypto.
Test: inside bar detection; entry on break; compare with/without the 4H trend filter.

### 37. Triangle / wedge breakout
Breakout · 15m-4H · Consolidation · ~40-45% / 2R
Thesis: converging swings show a shrinking auction; the resolution is directional.
Rules: context: at least two lower highs and two higher lows (symmetrical), or flat top with higher lows (ascending, bullish bias); entry: close beyond the boundary with RVOL ≥ 1.5, or the retest; stop: inside the pattern beyond the last swing; target: the pattern's widest height projected.
Fails when: late in the pattern (past 75% of the apex) breakouts lose force; a wedge *against* the trend often reverses (rising wedge in an uptrend is bearish).
Crypto notes: descending triangles in crypto break *up* nearly as often as down, because the flat bottom is equal lows (liquidity) that gets swept before the real move. Wait for the close.
Test: discretionary; log pattern age at breakout.

### 38. Asia range breakout at London open
Breakout · 5m-15m · London open · ~40% first break / 55% second · 1.5R
Thesis: London brings the first real volume; it breaks the Asia range. The first break often fails (see 79); the second, or the retest, is better.
Rules: context: Asia range defined; entry: 15m close outside the Asia range after 07:00 UTC with RVOL ≥ 1.5, ideally after a first fake break the other way; stop: Asia midpoint; target: 1 Asia range height (T1), PDH/PDL (T2).
Fails when: Asia range > 1 ATR (already trended); tier-1 UK/EU data at 07:00-09:00.
Crypto notes: the sweep of the Asia low then break of the Asia high (a "London Judas swing") is the highest-quality version.
Test: Asia = 00:00-07:00 range; first break vs second break follow-through.

### 39. Prior day high/low break and hold
Breakout · 15m-1H · Trend days · ~45% / 2R
Thesis: PDH/PDL are the most-watched levels; a close beyond that holds on the retest signals the day's direction.
Rules: entry: 15m close beyond PDH with RVOL ≥ 1.5, then a hold above on the next candle, or the retest; stop: below PDH by 0.5 ATR; target: 1 daily ATR from PDH, or the next HTF level.
Fails when: the break is a sweep (close back below within 2 candles): that is the playbook-4 short instead.
Crypto notes: PDH/PDL breaks during Asia are usually sweeps; during NY, usually real.
Test: PDH break close; hold = next candle low > PDH; follow-through to +1 ATR.

### 40. Volume-confirmed breakout (RVOL threshold)
Breakout · 5m-1H · Any · improves any breakout's win rate by 5-10 points
Thesis: breakouts without participation fail; RVOL ≥ 2 on the breakout candle is the simplest filter.
Rules: overlay on 33-39: require RVOL ≥ 1.5 (minimum) or ≥ 2 (better) on the breakout candle, and rising OI where available.
Fails when: the volume is a single liquidation candle (check OI drop).
Crypto notes: use volume from the venue you trade; aggregated volume includes wash-traded venues.
Test: compare breakout follow-through by RVOL bucket.

### 41. Intraday cup-and-handle / consolidation continuation
Breakout · 15m-1H · Trend pauses · ~45% / 2R
Thesis: a rounded base after a strong leg with a small pullback (handle) at the rim shows sellers exhausted; the rim break continues.
Rules: entry: close above the rim after the handle, RVOL ≥ 1.5; stop: below the handle low; target: cup depth projected.
Fails when: the handle retraces > 50% of the cup; the cup is V-shaped (that is a double-top risk).
Crypto notes: common on alts during narrative rotations.
Test: discretionary; log.

### 42. Darvas box
Breakout · 1H-1D · Trends · ~40% / 2R
Thesis: price forms boxes (consolidations); buy the break of the box top in an uptrend, stop below the box.
Rules: box = 3+ candles without a new high, then 3+ without a new low; entry: close above the box top; stop: box bottom; target: box height projected, then trail box by box.
Fails when: ranges; boxes stack sideways.
Crypto notes: works on the 4H for trending alts.
Test: box detection; entry on break.

### 43. Momentum breakout of the day's high with VWAP support
Breakout · 5m · Trend days · ~50% / 1.5R
Thesis: on a trend day, each new high of day with VWAP below and rising is a continuation entry with a clear stop.
Rules: context: trend day identified (13); entry: 5m close above HOD with RVOL ≥ 1.3; stop: below the last 5m higher low (not VWAP, too far); target: 1 ATR (5m) × 3, or the next level.
Fails when: late in the session (after 19:00 UTC) or after 3+ HOD breaks (exhaustion).
Crypto notes: watch OI: if it falls on the HOD break, it is short covering and the move is weaker.
Test: HOD break count per trend day vs follow-through.

### 44. Failed-break-then-break (the second attempt)
Breakout · 5m-1H · Ranges resolving · ~55% / 2R
Thesis: the first break of a level traps; the second, after the trap has flushed, has fewer opposing stops left and better odds.
Rules: context: a level was broken and reversed (a sweep); entry: the second close beyond the same level, with the first-break wick as the stop reference; stop: below the pullback low after the first break; target: measured move.
Fails when: the second break is also a sweep (happens in chop). Three failures = leave it alone.
Crypto notes: the "two attempts" pattern at PDH/PDL is one of the most consistent intraday edges in BTC.
Test: first break failure then second break close; follow-through vs first-break trades.

## Part 6. Liquidity, order flow, and "smart money" concepts

The terminology here comes from the "ICT" / smart money concepts community and
from institutional order-flow trading. The mechanisms are real (stop clusters,
forced flow, absorption); the mysticism is not. Every entry below is described
by its mechanism.

### 45. Liquidity sweep reversal (stop hunt)
Liquidity · 5m-4H · Any, at pools · ~40% / 2.8R
Thesis: (playbook 4) stops beyond equal highs/lows, PDH/PDL, and range edges are forced orders; a spike through them that closes back inside means the forced flow was absorbed.
Rules: entry: close back inside within 1-3 candles, on elevated volume, ideally with a micro CHoCH; stop: beyond the wick plus 0.2-0.3 ATR; target: the nearest opposing structure (T1), the opposite pool (T2).
Fails when: no close back inside; news spikes; sweeps *with* the HTF trend at no HTF level.
Crypto notes: the highest-R:R setup in crypto and the one most beginners misuse (they buy the first touch).
Test: pool = equal lows within 0.15 ATR; sweep = low < pool − 0.05 ATR and close > pool.

### 46. Turtle soup (Connors and Raschke)
Liquidity · 15m-4H · Ranges · ~50% / 1.5R
Thesis: a break of the 20-period Donchian low that fails (price closes back above within a candle or two) traps breakout sellers; the original "turtle soup" fades the turtle breakout.
Rules: context: the prior 20-period low was at least 3 candles ago; entry: price breaks it by ≥ 0.1 ATR then trades back above; buy stop 1 tick above the old low; stop: below the new low; target: 1.5-2R or the 20-period midpoint.
Fails when: trend days (the break follows through).
Crypto notes: identical mechanism to 45 with a mechanical definition; good for backtesting.
Test: 20-bar low break then close back above within 2 bars.

### 47. Order block retest
Liquidity · 5m-4H · Trends · ~45% / 2.2R
Thesis: the last opposing candle before an impulsive BOS marks where a large participant started; a return to it is often defended.
Rules: context: an impulsive move that broke structure; identify the last down candle (for a bullish OB) before it, use its body; entry: first return to the OB with a rejection close on the trigger timeframe; stop: below the OB by 0.3 ATR; target: the impulse high (T1), extension (T2).
Fails when: the OB is against the HTF trend; the OB has already been tested (second tests are weaker); the return comes on strong volume (it will trade through).
Crypto notes: OBs that coincide with a 0.618 retracement and the 21 EMA are the ones worth taking.
Test: OB = last opposite-colored candle before a 3-ATR move that closed above the prior swing high; entry on first touch + bullish close.

### 48. Fair value gap (imbalance) fill entry
Liquidity · 5m-1H · Trends · ~45% / 2R
Thesis: a three-candle gap (candle 1 high < candle 3 low) shows price moved without two-sided trade; the gap tends to be partially filled, and the 50% of it is a common reaction level.
Rules: context: FVG created by an impulse with the HTF trend; entry: return to the 50% of the gap with a rejection; stop: beyond the gap's far edge; target: the impulse high.
Fails when: the gap is fully traded through on volume (it was a "breakaway" gap); gaps against the trend.
Crypto notes: cascades leave huge FVGs that fill days later; intraday, the 5m and 15m FVGs are the tradeable ones.
Test: FVG detection; entry at 50% fill with close in trend direction.

### 49. Breaker block
Liquidity · 15m-4H · Trend reversals · ~45% / 2R
Thesis: an order block that failed (price traded through it) flips polarity; its retest from the other side is a continuation of the new direction.
Rules: context: a bullish OB that broke down; entry: price returns to the failed OB from below and rejects; stop: above the OB; target: the low that the breakdown made, then beyond.
Fails when: the "failure" was a sweep and price is coming back through.
Crypto notes: functionally the same as old-support-becomes-resistance; the name is new.
Test: as 47 with polarity flipped.

### 50. Session-open manipulation ("Judas swing")
Liquidity · 5m-15m · London/NY open · ~45% / 2.5R
Thesis: the first move after a major session open often runs stops on one side of the pre-session range before the real move goes the other way.
Rules: context: HTF bias known; at the open, price sweeps the pre-session high/low *against* the bias; entry: close back inside plus a 5m CHoCH in the bias direction; stop: beyond the sweep; target: the opposite side of the pre-session range (T1), PDH/PDL (T2).
Fails when: the move at the open is *with* the bias (no manipulation, just a trend start): then use 34 instead.
Crypto notes: the 13:30 UTC (summer) NY open sweep of the London high/low is the textbook version.
Test: sweep of the pre-open 4h range within 30 min of the open, then close back inside.

### 51. Accumulation / manipulation / distribution (intraday "power of three")
Liquidity · 15m-1H · Any · framework, not an entry
Thesis: a session or day often unfolds as a range (accumulation), a fake move (manipulation) that sweeps one side, then the real move (distribution/expansion). It is a narrative that organizes 38, 45, and 50.
Rules: identify the accumulation range; wait for the manipulation sweep; enter on the reclaim (45/50); target the expansion toward the opposite liquidity.
Fails when: applied to every candle; it is a *sometimes* pattern, roughly a third of sessions.
Crypto notes: the daily version (Asia = accumulation, London = manipulation, NY = expansion) is common enough to plan around.
Test: label sessions post hoc; measure how often the pattern appeared.

### 52. Equal highs / lows as targets
Liquidity · any · Any · improves target selection
Thesis: liquidity pools attract price; the best T2 is usually the nearest pool in the trade direction, not an arbitrary 2R.
Rules: overlay: set T2 at the nearest equal highs/lows, PDH/PDL, or liquidation cluster; take most of the position *before* price reaches it (the pool is usually swept, then reverses).
Fails when: the pool is < 1.5R away (then the trade is not worth it).
Crypto notes: the snapshot lists equal highs/lows; use them.
Test: compare fixed-2R targets vs pool targets on the same entries.

### 53. Liquidation cluster magnet
Liquidity · 15m-4H · Leveraged markets · ~50% direction-of-magnet / 1.5R
Thesis: heatmaps of estimated liquidation levels show where forced orders wait; price is drawn to large clusters, and reverses after consuming them.
Rules: context: a large cluster within 1-2 ATR; entry: trade *toward* the cluster with a structural trigger (playbooks 1/3/7), take profit at the cluster; then watch for the post-cascade reversal (55).
Fails when: the cluster is estimated from stale positioning; when a bigger cluster sits just beyond (price runs both).
Crypto notes: requires Coinglass/Hyblock-style data; without it, equal highs/lows are the proxy.
Test: log cluster size and whether price reached it within 24h.

### 54. CVD divergence / absorption reversal
Order flow · 1m-15m · Any, at levels · ~50% / 1.5R
Thesis: when aggressive buying (rising CVD) fails to lift price at a level, passive sellers are absorbing; the buyers will give up and price reverses.
Rules: context: price at resistance; CVD makes a higher high while price does not (or price makes a higher high while CVD does not); entry: rejection close; stop: above the high; target: the last swing low.
Fails when: absorption is followed by the absorber pulling orders (the wall vanishes and price breaks); use the candle close, not the CVD alone.
Crypto notes: needs a footprint/CVD tool; spot CVD vs perp CVD divergence (spot buying while perps sell) is a strong bullish read.
Test: requires trade-level data; not in the bundled scripts.

### 55. Post-liquidation cascade reversal
Liquidity · 5m-1H · After cascades · ~50% / 2R
Thesis: a cascade is forced selling with no regard for price; once it exhausts (OI has dropped sharply, the last spike has no follow-through), the book is thin on the other side and the bounce is violent.
Rules: context: a candle with range ≥ 3 ATR, OI drop ≥ 3-5% in the hour, liquidation totals spiking; entry: not the wick; wait for a 5m higher low above the cascade low and a close above the cascade candle's midpoint; stop: below the higher low; target: 50% of the cascade candle (T1), the pre-cascade level (T2).
Fails when: the cascade is the first of several (funding still extreme, OI still high); a second leg follows.
Crypto notes: the most reliable "buy the dip" in crypto, and the most dangerous if entered early. The OI reset is the tell.
Test: cascade = range ≥ 3 ATR down + volume ≥ 4x; entry on first 5m HL above the low.

### 56. Stop-run reversal at session highs/lows
Liquidity · 5m-15m · Any · ~45% / 2R
Thesis: the high/low of the prior session (Asia, London) holds stops; a run through it that fails is a sweep.
Rules: same as 45 with session highs/lows as the pools.
Fails when: the run continues (a trend session).
Crypto notes: the London high swept at the NY open is 50.
Test: as 45 with session pools.

### 57. Delta divergence continuation
Order flow · 1m-5m · Trends · ~50% / 1.5R
Thesis: in a trend, a pullback on *negative* delta that fails to push price down shows sellers are being absorbed by trend buyers; the trend resumes.
Rules: context: trend; pullback with CVD falling but price holding a level; entry: close back above the pullback's last high; stop: below the pullback; target: new high.
Fails when: the absorber is exhausted (price finally breaks).
Crypto notes: needs order flow tooling.
Test: not in the bundled scripts.

### 58. Order-book imbalance scalp
Order flow · seconds-1m · Liquid pairs · ~55% / 0.7R (fee-sensitive)
Thesis: persistent bid/ask depth imbalance predicts the next tick's direction slightly.
Rules: only with maker orders and a venue with rebates; the edge is smaller than taker fees.
Fails when: retail pays taker fees; walls are spoofed.
Crypto notes: this is what market-making firms do with colocated infrastructure; retail cannot compete. Listed so Claude can explain why.
Test: not viable without L2 data and a fee edge.

### 59. Spoofed wall fade
Order flow · 1m-5m · Any · discretionary
Thesis: a large visible wall that repeatedly reappears and pulls is a manipulator's tool; the *pull* of the wall often precedes the move in its direction (the spoofer wanted to buy lower).
Rules: do not trade off the wall's presence; note it, and trade the structural setup that forms when it is pulled.
Fails when: the wall is real (it gets eaten): then the move goes through.
Crypto notes: common on mid-cap alts.
Test: discretionary.

### 60. Absorption at a level on high volume
Order flow · 5m-15m · Any · ~50% / 1.5R
Thesis: a very high-volume candle at a level with a small body and close inside the range means the aggressive side was fully absorbed; expect a move against the aggressors.
Rules: context: RVOL ≥ 3 candle at a level with body < 30% of range; entry: next candle close against the wick direction; stop: beyond the absorption candle's extreme; target: 1.5-2R.
Fails when: news; the candle was the start of a cascade (check OI).
Crypto notes: the snapshot reports body-percent and wicks for the last closed candle.
Test: RVOL ≥ 3 + body < 30% + at a level; follow-through.

## Part 7. Derivatives and positioning

### 61. Funding extreme fade
Positioning · 1H-4H · Any, at HTF levels · ~45% / 2.2R
Thesis: (playbook 5) extreme funding means a crowded, leveraged side; at a structural level with a rejection, the crowd's liquidations become the fuel for the reversal.
Rules: context: funding beyond ±0.05% (BTC/ETH) with OI elevated, price at an HTF level; entry: a playbook 2 or 4 trigger at the level; stop: beyond the level plus 0.5 ATR; target: the first liquidation cluster (T1), the level where funding started rising (T2).
Fails when: funding has been extreme for days in a trend; OI is already falling.
Crypto notes: alts run hotter; ±0.1% is the alt equivalent.
Test: funding percentile ≥ 95 + level + rejection; log the funding at entry.

### 62. OI-price divergence
Positioning · 1H-4H · Trends maturing · ~45% / 2R
Thesis: rising OI with falling (or flat) price means new shorts are pressing (or longs are trapped); the side that is growing will be squeezed if price turns.
Rules: context: OI up ≥ 5% over 24h while price is flat or down at support; entry: a playbook 4 sweep-reclaim at the support; stop: below the sweep; target: the level where OI began rising.
Fails when: price breaks support: then the growing shorts were right and the longs cascade.
Crypto notes: compare OI in coin terms; dollar OI moves with price.
Test: OI change + price change quadrant at entry; expectancy by quadrant.

### 63. Long/short ratio contrarian
Positioning · 4H-1D · Extremes · weak standalone
Thesis: when a large majority of accounts are on one side, the minority (usually larger accounts) tends to be right.
Rules: use as a confluence point (factor 6) when the ratio is extreme (> 3 or < 0.5), never as a trigger.
Fails when: used alone; retail can be right for days.
Crypto notes: the "top trader" ratios on Binance/OKX are more informative than the all-accounts ratio.
Test: ratio bucket vs next-24h return.

### 64. Post-cascade OI reset long
Positioning · 15m-4H · After liquidations · ~50% / 2R
Thesis: a ≥ 10% OI drop flushes leverage; trends that begin afterwards are on cleaner footing.
Rules: as 55, with the OI drop as the required context.
Fails when: the drop is partial and funding is still hot.
Crypto notes: the best "regime reset" signal available for free.
Test: OI drop ≥ 10% in 24h; performance of playbook 1 longs in the following 48h.

### 65. Basis and cash-and-carry
Positioning · days-months · Contango · ~risk-free-ish, not day trading
Thesis: buy spot, short the dated future (or perp) to capture the basis/funding with no directional risk.
Rules: annualized basis > funding cost + fees + risk premium; hedge fully; manage margin on the short leg through spikes.
Fails when: exchange risk; a short squeeze margins out the short leg before the spot gain is realized; basis goes negative (then reverse it).
Crypto notes: the professional way to "earn 10-20%" in bull markets; retail versions on exchanges ("dual investment", "earn") carry hidden risks. Explain, do not recommend as day trading.
Test: log basis and funding daily.

### 66. Funding arbitrage (perp vs perp)
Positioning · hours-days · Funding dislocations · low R, low risk
Thesis: long the perp with negative funding, short the same perp on a venue with positive funding; collect both.
Rules: only when the spread in funding exceeds fees and the two venues' prices track; monitor both margins.
Fails when: one venue's price dislocates (depeg, outage) and one leg is liquidated.
Crypto notes: the classic "delta neutral farming"; profitable for bots, marginal for hand trading.
Test: log funding spreads between venues.

### 67. Options expiry pin and release
Positioning · 1H-4H · Monthly expiry (last Friday 08:00 UTC) · ~50% / 1.5R
Thesis: large options open interest at a strike creates hedging flow that pins price near "max pain" into expiry; after expiry the pin releases.
Rules: context: monthly expiry within 24h, max pain within 2% of price; entry: fade moves away from max pain into expiry (playbook 2 rules), then trade the release direction after 08:00 UTC with a structural trigger.
Fails when: a macro event coincides; when open interest is small relative to spot volume.
Crypto notes: Deribit publishes max pain; the effect is real on the biggest expiries (quarterly) and faint on small ones.
Test: distance to max pain 24h before expiry vs at expiry.

### 68. Short-squeeze setup checklist
Positioning · 1H-4H · Crowded shorts · ~45% / 2.5R
Thesis: crowded shorts (negative funding, rising OI on falling price, high short ratio) plus a held level plus a catalyst = a squeeze.
Rules: require: funding ≤ −0.02%, OI rising, price holding a 4H level for ≥ 3 candles, then a 15m close above the last lower high; stop: below the held level; target: the level where the shorts entered (where OI started rising), often 3R+.
Fails when: the level breaks (the shorts were right).
Crypto notes: alts squeeze 20-50% in hours; size for the wick.
Test: checklist score at entry vs outcome.

### 69. Long-squeeze (cascade) anticipation
Positioning · 1H-4H · Crowded longs · ~45% / 2.5R
Thesis: the mirror of 68: hot funding, rising OI, price failing at resistance, first lower high.
Rules: mirror of 68; stop above the resistance; target the liquidation clusters below.
Fails when: the breakout is real.
Crypto notes: the pre-cascade tell is often a sharp OI spike with price flat.
Test: mirror of 68.

### 70. Spot-perp divergence (spot premium/discount)
Positioning · 15m-4H · Any · confluence
Thesis: when spot leads (spot premium, spot CVD rising while perp CVD falls), real buyers are present and dips are bought; when perps lead (perp premium, basis rising fast), the move is leveraged and fragile.
Rules: use basis sign and magnitude as factor 6; a spot-led move gets full size on pullbacks; a perp-led move gets half and faster targets.
Fails when: used as a trigger.
Crypto notes: `fetch_ohlcv.py --derivs` reports basis.
Test: basis at entry vs outcome for playbook 1 longs.

## Part 8. Time and session based

### 71. New York open range break
Session · 5m-15m · NY open · see 34.

### 72. London open sweep and reverse
Session · 5m-15m · 07:00-09:00 UTC · ~45% / 2R
Thesis: London's first move sweeps the Asia high or low; the reversal after the sweep sets the London direction.
Rules: see 38 (second version) and 50.
Fails when: London continues Asia's trend without a sweep.
Crypto notes: less reliable than the NY version because volume is lower.
Test: as 38.

### 73. Daily close (00:00 UTC) reversal and open drive
Session · 5m-15m · 23:30-01:00 UTC · ~45% / 1.5R
Thesis: the daily candle close and funding settlement at 00:00 UTC concentrate flow; the first 30-60 minutes of the new day often set a high or low that holds for hours.
Rules: context: the last hour of the day; entry: a sweep of the day's high/low in the final 30 minutes with a close back inside (fade), or the first pullback of the new day's opening drive; stop: beyond the sweep; target: the daily open (T1), the day's midpoint (T2).
Fails when: US session momentum carries through (trend days).
Crypto notes: the 00:00 UTC open is crypto-specific; there is no equivalent in equities.
Test: reaction after 00:00 UTC vs the last hour's direction.

### 74. Funding settlement drift
Session · 5m-15m · 30 min before 00/08/16 UTC · weak / 0.5R
Thesis: when funding is extreme, some traders close positions before settlement to avoid paying; a small drift against the crowded side appears in the last 30 minutes.
Rules: only with funding ≥ 0.05%; fade small moves into settlement; flat at settlement.
Fails when: funding is normal (no effect).
Crypto notes: too small to trade alone after fees; useful to know when placing stops near settlement.
Test: 30-min pre-settlement return by funding bucket.

### 75. Weekend range and Monday resolution
Session · 1H-4H · Weekends · ~50% / 1.5R
Thesis: weekend moves happen on thin books and are often retraced when Monday's volume arrives; the weekend range is a box that Monday breaks.
Rules: context: define the Friday-close-to-Sunday range; entry: Monday London or NY break of the weekend range with volume (33 rules), or the fade of a weekend deviation on Sunday night with the CME reopen; stop: structural; target: PDH/PDL of Friday.
Fails when: weekend news creates a real gap.
Crypto notes: avoid initiating on Saturday afternoon UTC through Sunday afternoon; the wicks are cruel.
Test: weekend range break follow-through Monday.

### 76. CME reopen gap play
Session · 1H-4H · Sunday 22:00 UTC (summer) · ~60% fill / 1R
Thesis: see 27; the reopen sets the gap.
Rules: trade toward the gap fill with a structural trigger on Monday; fade the first 30 minutes after the reopen only if a clear sweep prints.
Fails when: breakaway gaps.
Crypto notes: the gap size matters: gaps > 3% fill more slowly.
Test: log.

### 77. Overlap trend hour (13:30-16:00 UTC summer)
Session · 5m-15m · London/NY overlap · best hours for 1, 10, 13, 43
Thesis: the overlap has the most volume and the highest share of trend hours; trend playbooks perform best here.
Rules: schedule trend playbooks for these hours; range playbooks for Asia; avoid the 16:00-17:00 lull and the post-20:00 drain.
Fails when: tier-1 data lands inside the window (then it is chop until the retrace).
Crypto notes: the single most valuable schedule rule for a part-time trader.
Test: expectancy of each playbook by hour of day from the journal.

### 78. Late US session fade
Session · 5m-15m · 19:00-22:00 UTC · ~50% / 1R
Thesis: after the US equities close, volume drains; the last impulse of the US session frequently retraces into the Asia open.
Rules: context: a strong directional US session; entry: after 20:00 UTC, a 15m CHoCH against the day's direction near the day's extreme; stop: beyond the extreme; target: VWAP.
Fails when: trend days that continue into Asia (a third of the time).
Crypto notes: small size; thin books.
Test: post-20:00 mean reversion by US-session return.

### 79. First-break failure at London
Session · 5m-15m · London open · see 38 and 44.

### 80. Day-of-week tendencies
Session · 1D · Statistical · weak, unstable
Thesis: various studies find Monday and weekend effects in crypto; they change year to year.
Rules: do not trade on them; check the user's journal by weekday instead.
Fails when: the effect flips (it does).
Crypto notes: the only robust weekday fact is lower weekend liquidity.
Test: journal expectancy by weekday.

## Part 9. Cross-asset and relative value

### 81. BTC-lead alt follow (lag trade)
Relative · 1m-15m · Any · ~50% / 1.5R
Thesis: BTC moves first; liquid alts follow within seconds to minutes. A BTC sweep-reclaim is an alt entry a candle or two later.
Rules: context: BTC prints a playbook 4/7 trigger; entry: the alt's own reclaim of its equivalent level within 1-3 candles; stop: below the alt's sweep; target: the alt's opposite pool.
Fails when: the alt has its own overhang (unlock, listing dump); BTC's move was a fake.
Crypto notes: the lag has shortened; in 2026 it is often under a minute on majors. Mid-caps still lag minutes.
Test: alt return in the 15 minutes after a BTC trigger.

### 82. Relative strength rotation (alt/BTC pairs)
Relative · 4H-1D · Alt seasons · ~50% / 2R
Thesis: alts that make higher lows against BTC while BTC chops are being accumulated; they lead when BTC moves.
Rules: rank alts by 7-day performance vs BTC and by their ALT/BTC chart structure; trade long setups only on the top quartile; short setups only on the bottom quartile.
Fails when: BTC trends hard (all alts fall regardless).
Crypto notes: `scan.py` shows each pair's trend and stack; compare them.
Test: RS quartile at entry vs outcome.

### 83. ETH/BTC regime switch
Relative · 1D · Regime · filter
Thesis: rising ETH/BTC marks risk appetite within crypto (alts work); falling ETH/BTC marks BTC-only regimes (alts bleed).
Rules: alt longs only when ETH/BTC is above its 21-day EMA; otherwise BTC/ETH only.
Fails when: ETH-specific news distorts it.
Crypto notes: also watch TOTAL2 and TOTAL3 (market cap ex-BTC, ex-BTC-ETH).
Test: alt playbook expectancy by ETH/BTC regime.

### 84. Nasdaq open correlation trade
Relative · 5m-15m · US open · ~50% / 1.5R
Thesis: at the US equities open, crypto follows Nasdaq futures direction for the first 30-60 minutes on most days.
Rules: context: NQ gapping/opening with a clear direction; entry: BTC's own ORB (34) in that direction only; skip ORBs against NQ.
Fails when: crypto-specific news; correlation breakdowns (happen for weeks at a time).
Crypto notes: check the 30-day correlation before trusting it; it swings between 0.2 and 0.8.
Test: BTC ORB outcome conditional on NQ first-30-min direction.

### 85. DXY inverse
Relative · 1H-1D · Macro days · filter
Thesis: a strong dollar is a headwind for BTC.
Rules: on days DXY breaks out, downgrade BTC longs one grade.
Fails when: crypto-specific drivers dominate.
Test: BTC return on DXY ±0.5% days.

### 86. Stablecoin premium / Kimchi premium
Relative · 1H-1D · Regional demand · signal
Thesis: a persistent premium on Korean exchanges (Kimchi premium) or a USDT premium in specific fiat markets signals retail demand; extremes mark tops.
Rules: use as sentiment context; a Kimchi premium > 5% in a rally is a late-cycle warning.
Fails when: capital controls distort it structurally.
Test: log.

### 87. Pairs trade (long strong / short weak)
Relative · 1H-1D · Any · ~55% / 1R, lower volatility
Thesis: long the relatively strong alt, short the weak one in the same sector; profit from the spread with less BTC exposure.
Rules: pick pairs in the same narrative; equal notional; stop on the spread, not on each leg.
Fails when: a listing or unlock hits one leg; funding costs on the short leg.
Crypto notes: the SOL/ETH spread and sector pairs are common.
Test: spread z-score entries and exits.

### 88. BTC dominance rotation
Relative · 1D · Regime · filter
Thesis: BTC.D rising = BTC-only regime; falling with BTC steady = alt season.
Rules: alt exposure scales with the BTC.D trend.
Test: alt performance by BTC.D trend.

### 89. Stablecoin supply and exchange reserves
Relative · 1D-1W · Macro context · filter
Thesis: growing stablecoin supply = dry powder; growing exchange stablecoin reserves = buying power on exchanges.
Rules: background bias only.
Test: not intraday.

### 90. Gold / rates / real-yield correlation
Relative · 1D · Macro · weak
Thesis: BTC sometimes trades with gold (store of value narrative) and sometimes against real yields.
Rules: do not lean on either intraday.
Test: rolling correlations.

## Part 10. News, catalysts, and events

### 91. Tier-1 release: straddle-then-fade the first move
Event · 1m-15m · CPI/FOMC/NFP · ~50% / 1.5R
Thesis: the first move after a release is often driven by headline algorithms and is reversed once the details are read (especially FOMC: the statement move reverses during the presser about half the time).
Rules: flat 30 minutes before; do not trade the first 5-15 minutes; entry: the first 5m CHoCH against the initial spike at a pre-marked level with a close back inside; stop: beyond the spike extreme; target: the pre-release price (T1).
Fails when: the release is a genuine surprise and the move is a trend day (then use 13 after the retrace).
Crypto notes: CPI at 12:30 UTC summer / 13:30 winter; FOMC 18:00 / 19:00 with the presser 30 minutes later. `scripts/events.py` has the dates.
Test: log spike size, reversal size, and time to reversal per event.

### 92. Exchange listing pump fade
Event · 5m-1H · Listing announcements · ~55% / 1.5R
Thesis: listing announcements (Binance, Coinbase, Upbit) spike the token 10-50%; most of the spike is retraced within hours to days as early holders sell into the new liquidity.
Rules: do not chase; entry: after the spike, a 15m lower high and a close below the 15m 21 EMA (short, on venues where it can be borrowed/perped), or wait for the retrace to the pre-announcement level for a long only if it holds.
Fails when: the listing coincides with a real catalyst (product launch); when the token is illiquid (no borrow).
Crypto notes: Upbit listings on Korean-favored tokens are the most violent; Coinbase listings the most reliably faded.
Test: log spike and 24h/72h retrace per listing.

### 93. Token unlock short
Event · 4H-1D · Unlocks > 1-2% of supply · ~55% / 1.5R
Thesis: unlocked tokens get sold; price often weakens into the unlock and for a few days after.
Rules: context: large unlock in 1-3 days; entry: short on a 4H lower high, or skip longs; stop: above the last 4H swing high; target: the prior 4H swing low; cover before the unlock if the token has already dropped 15%+ (priced in).
Fails when: the unlock is to a party that does not sell (treasury, locked staking); when "sell the unlock" is crowded and the token squeezes.
Crypto notes: check the recipient of the unlock, not just the size.
Test: return from T-3 days to T+3 days across unlocks by size.

### 94. Exploit / hack crash bounce
Event · 5m-1H · Protocol exploits · ~40% / 2R (dangerous)
Thesis: after a hack headline, the token crashes on panic; if the protocol is solvent, part of the crash retraces within hours.
Rules: no trade in the first 30-60 minutes; entry: only after the team confirms the scope and a 15m higher low prints; stop: below the panic low; target: 50% retrace.
Fails when: the hack is existential (bridge drains, treasury losses).
Crypto notes: most beginners buy the first bounce; it is usually sold again.
Test: log.

### 95. ETF flow reaction
Event · 1H-4H · Daily ETF flow reports · filter
Thesis: large net inflows/outflows into BTC/ETH ETFs (reported after the US close) tilt the next US session.
Rules: use as factor 1-2 confluence for next-day NY-session trades in the flow direction.
Fails when: the flow is already priced (price moved during the US session).
Test: next-day NY session return by flow decile.

### 96. Buy the rumor, sell the news
Event · 4H-1D · Scheduled catalysts (upgrades, launches) · ~55% / 1.5R
Thesis: anticipation drives price into a known event; the event itself has no buyers left.
Rules: entry: short on the first 4H lower high after the event, or take profit on longs before the event; stop: above the event high; target: the pre-run-up level.
Fails when: the event surprises to the upside.
Crypto notes: ETH upgrades, Bitcoin halvings, and mainnet launches all show this pattern historically.
Test: return from T-7 to T and T to T+7 across events.

### 97. Regulatory headline reflex
Event · 5m-1H · Regulatory news · ~45% / 1.5R
Thesis: regulatory headlines cause sharp, often overdone moves that partially retrace once lawyers read the document.
Rules: as 91: no trade in the first 15 minutes; fade at a level with a CHoCH.
Fails when: the action is enforcement against a specific exchange or token (structural).
Test: log.

### 98. Macro regime days (equities crash, VIX spike)
Event · 1H-4H · Risk-off days · filter
Thesis: on risk-off equity days crypto trades as high-beta risk; correlations go to 1 and crypto levels stop mattering.
Rules: on VIX spikes / equity gaps down: BTC shorts on bounces into VWAP with the Nasdaq as the guide; no alt longs.
Fails when: crypto-specific bid (rare).
Test: BTC return on S&P −2% days.

## Part 11. Scalping and micro-structure

### 99. 1-minute VWAP scalp
Scalp · 1m · Liquid pairs, active hours · ~55% / 0.8R (fee-sensitive)
Thesis: on the 1m, price oscillates around VWAP; buy the first pullback to VWAP in the direction of the 15m trend, target the last 1m high.
Rules: context: 15m trend, NY hours; entry: 1m close back above VWAP after a touch; stop: 1 ATR (1m) below VWAP; target: last high, then out; max hold 10 minutes.
Fails when: fees. On a 0.15% stop, a 0.1% round trip is two-thirds of 1R. Only viable with maker fees or fee rebates.
Crypto notes: most "scalping" videos ignore fees; run the numbers with `position_size.py --fee-pct 0.05` before believing any scalp.
Test: expectancy with realistic fees.

### 100. Tape / time-and-sales momentum scalp
Scalp · seconds · Liquid pairs · ~55% / 0.7R
Thesis: bursts of large aggressive prints in one direction at a level precede a short move.
Rules: requires a tape/footprint tool; entry on the burst, exit within a minute.
Fails when: fees and latency; spoofing.
Crypto notes: professional territory; explain, do not encourage.
Test: not with bundled tools.

### 101. Spread capture / market making
Scalp · continuous · Any · retail cannot
Thesis: post bids and asks, earn the spread and maker rebates.
Rules: inventory management, quote skewing, latency; a full-time engineering problem.
Fails when: adverse selection (you get filled only when you are wrong) and toxic flow.
Crypto notes: firms with colocation do this; retail bots lose to them.
Test: n/a.

### 102. Momentum burst on the 1m with 5m confirmation
Scalp · 1m-5m · Trend days · ~50% / 1R
Thesis: in a trend day, 1m breakouts of micro-consolidations in the trend direction extend for a few minutes.
Rules: context: 5m and 15m trend; entry: 1m close above a 5-10 candle consolidation with RVOL ≥ 2; stop: below the consolidation; target: 1R fast.
Fails when: range days; fees.
Test: as 4 on the 1m.

### 103. Level-to-level scalp
Scalp · 1m-5m · Clear levels · ~55% / 1R
Thesis: trade from one tier-1 level to the next when they are ≥ 1 ATR (5m) apart; enter on a rejection at one, exit at the other.
Rules: entry: rejection candle at PDL/VWAP/OR edge; stop: 0.5 ATR beyond; target: the next level; no runner.
Fails when: the levels are too close for fees; chop between levels.
Crypto notes: the most fee-efficient scalp because targets are defined by structure, not by ticks.
Test: log level pairs and outcomes.

### 104. Grid / DCA bots on perps
Scalp · continuous · Ranges · see 32 and Part 16.

### 105. Latency / cross-exchange arbitrage
Scalp · milliseconds · Dislocations · bots only
Thesis: the same asset briefly trades at different prices on different venues.
Rules: buy on the cheap venue, sell on the expensive one; requires pre-funded balances on both and sub-second execution.
Fails when: withdrawal delays, fees, and the fact that faster bots already took it.
Crypto notes: retail cannot compete; explain why the "arbitrage bot" they were sold does not work.
Test: n/a.

## Part 12. Classic indicator systems and named methodologies

### 106. MACD histogram reversal
Indicator · 15m-4H · Trends (for pullback timing) · ~45% / 1.5R
Thesis: the histogram shrinking toward zero during a pullback shows selling losing steam; the first histogram uptick in a trend is a pullback entry.
Rules: context: HTF trend; entry: first histogram bar higher than the previous after a pullback, at a level; stop: below the pullback low; target: prior high.
Fails when: used in ranges; the histogram flips constantly.
Test: histogram uptick + 21 EMA within 0.5 ATR.

### 107. RSI divergence reversal
Indicator · 1H-4H · Trend ends · ~45% / 2R (as confirmation)
Thesis: price makes a higher high while RSI makes a lower high: momentum is fading. Not an entry; a warning that makes a subsequent structural trigger (CHoCH, sweep) more credible.
Rules: divergence + CHoCH + level = entry; divergence alone = nothing.
Fails when: traded alone (trends can carry divergence for many legs).
Crypto notes: the snapshot flags divergences on the last two swings.
Test: CHoCH trades with vs without prior divergence.

### 108. Stochastic cross in trend (Lane)
Indicator · 15m-1H · Trends · ~50% / 1.2R
Thesis: in an uptrend, a stochastic (14,3,3) cross up from below 20 times the pullback end.
Rules: context: HTF trend; entry: %K crosses %D from below 20 at a level; stop: below the pullback; target: prior high.
Fails when: ranges; overbought/oversold reading in trends.
Test: cross + 21 EMA proximity.

### 109. Williams %R and CCI extremes
Indicator · 15m-1H · Ranges · ~45% / 1R
Thesis: bounded oscillators at extremes at range edges.
Rules: as 31 with a different oscillator.
Fails when: trends.
Test: as 31.

### 110. Elder's Triple Screen
Methodology · 1H/15m/5m · Any · framework
Thesis: use three timeframes: the tide (trend on the highest, e.g. weekly MACD histogram slope), the wave (oscillator pullback on the middle), the ripple (entry trigger on the lowest). Alexander Elder.
Rules: trade only in the tide's direction; enter when the wave oscillator pulls back; trigger on the ripple's breakout.
Fails when: the tide is flat.
Crypto notes: the skill's HTF/setup/trigger structure is Triple Screen.
Test: the skill's workflow *is* the test.

### 111. Elder Impulse System
Indicator · 15m-4H · Trends · filter
Thesis: color each candle by the 13 EMA slope and MACD histogram slope: both up = green (buy allowed), both down = red (sell allowed), mixed = blue (no new positions).
Rules: use as permission: no longs on red candles, no shorts on green.
Fails when: used as a trigger.
Test: playbook 1 with vs without the Impulse filter.

### 112. Larry Williams patterns (Oops, smash day, outside day)
Methodology · 1D (adapted to 4H) · Any · ~50% / 1.5R
Thesis: specific bar patterns: "Oops" (gap open beyond the prior extreme that reverses back through it), "smash day" (a bar that closes below the prior low then the next bar reverses), naked closes.
Rules: entry on the reversal through the prior bar's extreme; stop at the pattern bar's extreme; target 1-2R within a few bars.
Fails when: applied without the trend context Williams used.
Crypto notes: crypto has no gaps except CME; the "smash day" translates to 4H bars well.
Test: smash-day pattern on 4H.

### 113. Raschke's 80-20s
Methodology · 1D/4H · Any · ~50% / 1.2R
Thesis: a bar that opens in the top 20% of its range and closes in the bottom 20% (or vice versa) shows a full-range reversal; the next bar often continues that reversal briefly.
Rules: entry on the next bar's break of the pattern bar's extreme; stop at the opposite extreme; target 1R.
Fails when: the bar was a news bar.
Test: 80-20 detection on 4H.

### 114. Al Brooks price action: second entries
Methodology · 5m · Any · ~55% / 1R
Thesis: the first pullback signal in a trend often fails; the *second* signal (a "second entry") at the same area has a materially higher win rate because the first failure trapped the early traders.
Rules: in a bull trend, after a pullback, the first bull bar close is entry 1; if price makes another leg down and prints another bull bar, that is entry 2: take it; stop below the second leg; target: the trend high, or a measured move.
Fails when: the second entry is below the 20 EMA on the 5m (the trend is over).
Crypto notes: the two-attempts principle (44) is the same insight applied to breakouts.
Test: first vs second entry outcomes on 5m pullbacks.

### 115. Al Brooks: wedge reversal and three pushes
Methodology · 5m-1H · Trend ends · ~45% / 2R
Thesis: three pushes with diminishing momentum forming a wedge, then a break of the wedge's trendline, mark a reversal or at least a two-legged pullback.
Rules: entry on the break of the wedge with a close; stop beyond the third push; target: the start of the wedge.
Fails when: the wedge is with the trend on a trend day (it becomes a continuation).
Test: discretionary; log.

### 116. Al Brooks: trading range rules
Methodology · 5m-15m · Ranges · framework
Thesis: in a trading range, buy low, sell high, scalp; most breakout attempts fail; the range's middle is a no-trade zone; expect two-legged moves.
Rules: fade edges with limit orders; take 1R; do not chase breakouts until the second attempt.
Fails when: the range is actually a flag in a strong trend.
Test: the range playbooks.

### 117. Wyckoff schematics (accumulation / distribution)
Methodology · 1H-1D · Range-to-trend transitions · framework
Thesis: ranges have phases: preliminary support, selling climax, automatic rally, secondary test, spring (23), sign of strength, last point of support, then markup. The mirror for distribution.
Rules: the tradeable moments: the spring (sweep of the range low with a reclaim), the last point of support (higher low after the sign of strength) as a playbook-1 entry, and the upthrust (sweep of the range high) in distribution.
Fails when: the schematic is imposed on noise; the phases must be visible.
Crypto notes: intraday accumulation ranges before NY session breakouts are common; the spring is the highest-quality entry in the whole framework.
Test: log springs vs first-touch entries at range lows.

### 118. Volume Spread Analysis (VSA)
Methodology · 15m-4H · Any · framework
Thesis: read each bar by its spread (range), close position, and volume relative to recent bars: "no demand" (narrow spread, low volume up bar in a downtrend), "stopping volume" (wide spread down bar on huge volume closing off the low), "upthrust" (wide spread up bar closing near the low on high volume).
Rules: stopping volume at support + a subsequent no-supply bar = long; upthrust at resistance = short; always with structure.
Fails when: read bar by bar without context.
Crypto notes: 60 (absorption) is VSA's stopping volume.
Test: log the bar types at reversal points.

### 119. Supply and demand zones (Seiden)
Methodology · 15m-4H · Trends · ~45% / 2R
Thesis: zones where price left quickly (drop-base-rally, rally-base-drop) mark unfilled institutional orders; the first return fills them.
Rules: mark the base (the consolidation before the impulse); entry: limit at the zone's proximal edge with the stop beyond the distal edge; target: the opposite zone; only fresh (untested) zones; only with the trend.
Fails when: the zone has been tested; the impulse was news.
Crypto notes: functionally the order block (47) with a wider zone; the "fresh zone only" rule is the important part.
Test: fresh vs tested zone outcomes.

### 120. Market profile / volume profile (POC, value area, initial balance)
Methodology · 15m-1D · Any · framework
Thesis: the day's traded-volume-at-price distribution shows where the market agreed on value (the value area, 70% of volume) and where it did not; the point of control (POC) is the fairest price; the initial balance (first hour) frames the day.
Rules: range day: fade the value area edges toward the POC; trend day: price accepts outside value (closes there); naked (untested) POCs from prior days are magnets; the initial balance extension direction sets the day type.
Fails when: the profile is read without volume data from a serious venue.
Crypto notes: TradingView's session volume profile works on Binance/Coinbase data; the developing value area is the day-trader's best map of "where is fair".
Test: reaction at prior-day POC and value-area edges.

### 121. Elliott wave (intraday)
Methodology · 15m-4H · Trends · discretionary, low reliability
Thesis: trends unfold in five waves, corrections in three; wave 3 is the strongest, wave 5 often diverges; corrections retrace 0.382-0.618.
Rules: the actionable version: after a clear impulse (wave 1) and a correction (wave 2) that holds above the wave 1 start, enter for wave 3 (a playbook 1/3 entry); take profit into wave 5 on divergence.
Fails when: counts are ambiguous (usually); traders re-count until it fits.
Crypto notes: use the wave-3 idea as a narrative for measured moves; do not trade the count.
Test: not mechanically testable in a useful way.

### 122. Harmonic patterns (Gartley, Bat, Butterfly, Crab)
Methodology · 15m-4H · Reversals · ~40-50% / 1.5R
Thesis: specific Fibonacci ratio combinations between swings define completion zones (the "D" point) where reversals cluster.
Rules: enter at D with a rejection candle; stop beyond D by a small buffer; targets at the 0.382 and 0.618 retracements of the CD leg.
Fails when: the pattern is drawn to fit; the ratio tolerance is wide.
Crypto notes: the D point often coincides with a sweep of a level; if so, trade it as 45 and ignore the ratios.
Test: discretionary.

### 123. Renko / range bars
Methodology · n/a · Trends · filter
Thesis: bars built by price movement (not time) filter noise and make trends and reversals cleaner to see.
Rules: use a brick size of ~0.5 ATR (15m); a trend is a run of same-colored bricks; a reversal is two opposite bricks; combine with a real-time chart for stops.
Fails when: the brick size is too small (noise) or too large (lag).
Test: brick reversal system vs candle system.

### 124. Pivot-based systems (Camarilla, Woodie)
Indicator · 5m-1H · Ranges · ~45% / 1R
Thesis: alternative pivot formulas; Camarilla's H3/L3 (fade) and H4/L4 (breakout) levels are the most used.
Rules: fade H3/L3 with a rejection; go with a break of H4/L4.
Fails when: trend days blow through.
Test: as 28.

### 125. Chaikin Money Flow / OBV divergence
Indicator · 1H-4H · Trend ends · confirmation
Thesis: volume-weighted accumulation indicators diverging from price warn of exhaustion.
Rules: use as a confluence point with a structural trigger.
Fails when: used alone.
Test: as 107.

### 126. Hull / TEMA / DEMA moving averages
Indicator · 15m-1H · Trends · variants of 1-2
Thesis: lower-lag averages for faster trend signals.
Rules: substitute in 1 and 2; expect more signals and more whipsaw.
Test: compare with EMA versions.

### 127. Schaff Trend Cycle / stochastic RSI
Indicator · 15m-1H · Any · variants of 108
Thesis: faster oscillators.
Rules: as 108.
Test: as 108.

### 128. Guppy multiple moving averages (GMMA)
Indicator · 1H-1D · Trends · filter
Thesis: two groups of EMAs (short-term traders, long-term investors); compression and expansion between them show trend health.
Rules: trend when both groups are separated and aligned; no trade when compressed and tangled.
Test: playbook 1 with GMMA alignment filter.

### 129. Fibonacci extensions and time zones
Indicator · 15m-4H · Targets · target selection
Thesis: 1.272 and 1.618 extensions of the pullback are common targets; time zones are not useful.
Rules: use extensions as T2 candidates when no structural level exists.
Test: extension hit rate.

### 130. Gann levels, astro, and numerology
Indicator · any · n/a · no edge
Thesis: none that survives testing.
Rules: when a user asks, say so kindly and redirect to structure.
Test: they fail.

## Part 13. Chart, candle, and volume-profile pattern catalog

Patterns are context, not signals. Each one below is only worth acting on at a
level and with a close that confirms.

### 131. Engulfing (bullish / bearish)
Candle · any · at levels · trigger quality: high
A body that fully covers the previous body in the opposite direction. At a level after a pullback, it is a clean trigger; mid-range it is noise.

### 132. Pin bar / hammer / shooting star
Candle · any · at levels · trigger quality: high
Wick ≥ 2x body, pointing into the level. The candle form of a sweep. Enter on the close or on the break of the pin's body; stop beyond the wick.

### 133. Doji and spinning tops
Candle · any · after extended moves · trigger quality: low
Indecision. Wait for the next candle. A doji at a level after three expansion candles is a warning; alone it is nothing.

### 134. Inside bar / mother bar
Candle · 15m-1D · compression · see 36.

### 135. Three white soldiers / three black crows
Candle · 1H-1D · trend starts · trigger quality: medium
Three consecutive expanding candles with small wicks after a base: momentum ignition on a higher timeframe. Do not chase the third; buy the first pullback.

### 136. Morning star / evening star
Candle · 1H-1D · reversals at levels · trigger quality: medium
A big candle, a small-bodied candle (the star), and a big opposite candle. It is a two-candle-delayed engulfing; treat it as 131.

### 137. Tweezer tops / bottoms
Candle · 15m-4H · equal extremes · trigger quality: medium
Two candles with matching highs (or lows). Equal highs on a two-candle scale: expect the sweep before the reversal (45).

### 138. Marubozu
Candle · any · trend days · continuation
A candle with no wicks. Strong control by one side; on a trend day, buy the first pullback into its body.

### 139. Flags, pennants, wedges, triangles
Chart · see 12, 37.

### 140. Double / triple tops and bottoms, head and shoulders
Chart · see 24, 25.

### 141. Rounded bottom / cup
Chart · see 41.

### 142. Broadening formation (megaphone)
Chart · 15m-4H · volatile chop · fade the edges at reduced size
Expanding swings: each high higher, each low lower. Chop with growing amplitude; a sign of a two-sided, news-driven market. Fade the third or fourth touch with a tight stop, or stand aside.

### 143. Rectangle (box)
Chart · see 17, 42.

### 144. Volume profile: POC, value area high/low, high/low volume nodes
Profile · see 120.
High-volume nodes are agreement (price slows there); low-volume nodes are rejection (price moves through fast). Trade from a low-volume node toward the next high-volume node.

### 145. Naked POC and single prints
Profile · 1H-1D · magnets
Untested prior-day POCs and single-print areas (fast moves that left thin profile) attract price; use them as targets and as confluence for entries.

## Part 14. Quantitative and systematic approaches

### 146. Volatility breakout (Larry Williams)
Quant · 1D/4H · Any · ~45% / 1.5R
Thesis: buy when price exceeds the open by a fraction (e.g., 0.5-0.7) of the prior bar's range; the day is "already trending".
Rules: entry: open + k × prior range; stop: open; exit: close of the bar.
Fails when: ranges; the bar closes back at the open.
Crypto notes: on the 4H, k = 0.6 of the prior 4H range is a reasonable start.
Test: mechanical; easy to add to backtest.py.

### 147. Mean-reversion z-score
Quant · 1H-4H · Ranges · ~55% / 0.8R
Thesis: the z-score of price vs its 20-period mean beyond ±2 reverts.
Rules: entry at |z| ≥ 2 with the EMA stack flat; exit at z = 0; stop at |z| = 3.5.
Fails when: trends.
Test: mechanical.

### 148. Cross-sectional momentum (rank alts, buy leaders)
Quant · 1D · Alt seasons · ~50% / 1.5R
Thesis: the top-decile 7-day performers outperform the bottom decile over the next few days (until they do not).
Rules: rebalance daily; long the top decile, short the bottom (or BTC-hedge).
Fails when: momentum crashes.
Test: needs a universe of alt data.

### 149. Statistical arbitrage on the funding/basis curve
Quant · hours-days · Dislocations · low risk, low R
See 65-66. Bots.

### 150. Regime classification (HMM / volatility clustering)
Quant · 1H-1D · Any · framework
Thesis: classify the market into regimes (low-vol range, high-vol trend, crisis) with a simple rule set or a hidden Markov model, and switch playbooks by regime.
Rules: the skill's regime table (`regimes-and-cycles.md`) is the rule-based version.
Fails when: regimes change faster than the classifier updates.
Test: label days, measure playbook expectancy by label.

### 151. Machine learning signal models
Quant · any · Any · usually overfit
Thesis: train a classifier on features (returns, volume, funding) to predict direction.
Rules: if attempted: walk-forward validation, no lookahead, features that are causally sensible, transaction costs in the objective, and a baseline of "always predict flat".
Fails when: nearly always in retail hands, because the signal-to-noise ratio on short horizons is tiny and the model learns noise.
Crypto notes: the honest answer to "can AI predict crypto": not on intraday horizons with public data.
Test: out-of-sample Brier score vs the flat baseline.

### 152. Kelly and volatility-targeted sizing
Quant · overlay · Any · see risk-management.md
Thesis: size positions so that portfolio volatility is constant; scale down in high-ATR regimes.
Rules: risk per trade in ATR units is constant; dollar size scales inversely with ATR.
Test: compare fixed-fractional vs volatility-targeted equity curves.

### 153. Ensemble of playbooks by regime
Quant · overlay · Any · the skill's design
Thesis: no single strategy works in every regime; a small set of uncorrelated strategies, each gated by regime, smooths the equity curve.
Rules: the seven playbooks plus the regime table.
Test: correlation of playbook returns.

### 154. Monte Carlo drawdown estimation
Quant · overlay · Any · essential
Thesis: shuffle the journal's R outcomes thousands of times to estimate the drawdowns a strategy can produce even if its expectancy is real.
Rules: if the 95th-percentile drawdown from the shuffle exceeds what the user can stomach, reduce risk per trade.
Test: easy to add to journal_stats.py; recommended for users with 50+ trades.

### 155. Walk-forward optimization
Quant · overlay · Any · essential for any parameterized system
See `journal-and-backtesting.md`.

## Part 15. Management overlays: sizing, pyramiding, trailing, exits

### 156. Fixed fractional (1%) sizing
The default. Risk a fixed % of current equity on every trade; size from the stop.

### 157. Fixed ratio / anti-martingale
Increase risk only after equity grows by a set amount; never after losses. Compounds winners, protects during losing streaks.

### 158. Pyramiding (adding to winners)
Add a second unit only after the first is at ≥ 1R with the stop at breakeven, at the next structural entry (a new higher low), with the total risk still ≤ 1R. Never add to losers.

### 159. Scaling out
Half at 1R or the first level; stop to breakeven; rest to T2 or trailed. The default for 2R+ setups.

### 160. Trailing methods
ATR chandelier (highest high − 3 ATR), swing-low trail (below each new higher low on the trigger timeframe), EMA trail (close below the 21 EMA), Parabolic SAR for parabolic legs. Pick one per playbook and journal it.

### 161. Time stops
Exit if the trade has not reached 1R within N candles (8 on the trigger timeframe is a good default). Dead trades become losers.

### 162. Breakeven rules
Move the stop to breakeven plus fees only after T1 or after a new higher low forms above entry. Moving it immediately turns winners into scratches.

### 163. Daily / weekly loss limits and circuit breakers
−3R day, −6R week, three consecutive losses: stop. After +3R, consider stopping. Mechanical.

### 164. Equity-curve trading
Reduce risk when the equity curve is below its own 20-trade moving average; restore when above. Cuts drawdowns; costs a little upside.

### 165. Correlation budgeting
Count correlated positions (BTC + ETH + SOL longs) as one; cap total open risk at 3R.

## Part 16. Strategies that lose, and why

### 166. Martingale / doubling down
Doubling size after each loss to "guarantee" recovery. Guarantees ruin instead: the losing streak that exceeds the bankroll arrives with certainty given enough trades. Every DCA-on-perps bot is a martingale.

### 167. Averaging down on leverage
Adding to a losing leveraged position. Converts a defined 1R loss into an undefined one and moves the liquidation price closer with every add.

### 168. Grid bots without a global stop
Short volatility with unlimited downside. Profitable for months, then one trend erases it (32).

### 169. Signal groups and paid calls
The caller's incentives are subscriptions and referral fees, not the follower's P&L. Calls with no stop, no size, and no track record. If the calls were profitable at scale, the caller would not need subscribers.

### 170. 50-100x scalping
The stop distance that leverage permits is inside the noise; fees are most of 1R; liquidation is one wick away. Structurally negative expectancy.

### 171. Indicator-only systems in all regimes
"Buy when RSI < 30" without regime or structure. Loses in trends, and trends are where the big losses are.

### 172. Trading the news candle
Entering in the first minutes after a release. The spread is wide, the book is thin, the algorithms are faster, and the first move reverses half the time.

### 173. Revenge trading and "making it back"
The next trade after a loss is taken with worse selection and bigger size. The daily limit exists for this.

### 174. Holding day trades into swing trades ("it will come back")
A 15m setup that is now a 3-day hold has no plan, no stop that matters, and usually funding costs.

### 175. Predicting instead of reacting
Entering because "it has to bounce here" without a trigger. The market does not have to do anything. Every playbook waits for the close that proves it.

## Part 17. Choosing: a decision table

### By regime (identify it first; `regimes-and-cycles.md`)

| Regime | Primary | Secondary | Avoid |
|---|---|---|---|
| Trend day | 1, 10, 13, 43, 14 | 3, 12, 36, 39 | 17, 18, 21, 26 |
| Range day | 17, 23, 45, 21 | 18, 28, 31, 46 | 5, 34, 43 |
| Volatile chop / post-news | 45 (large R only), 55, 91 | 22, 60 | everything else |
| Compression | wait; then 33, 35, 36 | 38, 34 | 17, 18 (targets too small) |
| Post-cascade | 55, 64, 3 | 47, 48 | shorts for the next session |

### By session (UTC, US summer)

| Session | Best | Notes |
|---|---|---|
| Asia 00:00-07:00 | 26, 21, 73 | small size; ranges; 00:00 open drive occasionally |
| London 07:00-13:00 | 38, 50, 72, 44 | first break often fails; second break or sweep-reclaim |
| Overlap 13:30-16:00 | 1, 10, 13, 34, 43, 45, 50 | the best hours; trend playbooks |
| NY afternoon 16:00-20:00 | 1, 7 (VWAP), 39 | slower; watch for the 16:00 lull |
| Late US 20:00-24:00 | 78 | thin; mostly stand aside |
| Weekend | 75 (Sunday night), stand aside | thin; wicks |

### By experience

| Level | Trade only | Add after |
|---|---|---|
| First 50 trades | 1 on BTC, NY session, spot | journal shows positive expectancy |
| 50-150 trades | + 45 or 33, + ETH | per-playbook stats hold |
| 150+ trades | + 17/23 in ranges, + 61 at levels, + one alt | drawdown < 10R over the sample |
| Systematic inclination | 5, 18, 46, 146, 147 via backtest.py | walk-forward results hold |

### By what the user asked for

| They want | Give them |
|---|---|
| "highest win rate" | **Part 26 first** (the measured 80% and what it is made of), then Parts 0 and 2; then 1, 7, 44, 114 with 1R partials |
| "options / covered calls / straddles" | Part 18; say what is reachable from a spot account and what is not |
| "yield / LP / staking / airdrops" | Part 19, and the question "what risk is this yield paying me for?" |
| "what do I do with the rest of my money" | Part 20 — and DCA (216) is the benchmark active trading must beat |
| "how do I actually improve" | Part 21 — fee tier, stop width and venue move results more than any setup change |
| "is this seasonal pattern real" | Part 22, then strategy 320 (multiple comparisons) |
| "what has a genuinely high win rate" | Part 24 — arbitrage and market making, and why retail cannot run most of it |
| "biggest R" | 45, 55, 68, 69, 3 |
| "something mechanical to test" | 1 (ema_pullback), 18 (range_fade), 46, 146, 147 |
| "how institutions trade" | 120, 54, 65, 101, and the honest note that most institutional edge is execution and cost, not signals |
| "smart money / ICT" | 45, 47, 48, 49, 50, 51 explained by mechanism |
| "scalping" | 99, 103 with the fee math; then the suggestion to trade the 15m instead |
| "bots / grids / DCA" | 32, 166-168, 65-66 |
| "alt that will pump" | Part 9 (82, 81) and `altcoins-and-memecoins.md`; no names |

---

# Volume II — the rest of the field (176-320)

Parts 3-17 cover what a spot crypto day trader actually uses. Volume II covers
everything else a user might name, so Jarvus can recognise it, explain it, and say
honestly whether it is reachable from a Canadian spot account. Many of these are
**not** day trading and several are **not available** without derivatives, size, or
infrastructure Abhi does not have. Each entry says so in its Crypto notes line.

The format is unchanged: Family · Timeframes · Best regime · Typical profile ·
Thesis · Rules · Fails when · Crypto notes · Test.

## Part 18. Options and volatility strategies (176-195)

Crypto options live mainly on Deribit (BTC/ETH, and increasingly SOL), with smaller
books on OKX and Bybit. **Canadian retail access is limited and none of this is spot.**
Jarvus's honest use for options is (a) reading what the options market implies about
volatility, which feeds the volatility gate, and (b) explaining these when asked.

### 176. Covered call (selling calls against spot held)
Options · weeks · Range/mild-up · ~70-80% of calls expire worthless / capped upside
Thesis: sell someone the right to buy your coin higher than it is now; keep the premium if it does not get there. Converts a flat market into income and lowers your effective cost basis.
Rules: hold the spot; sell a call 10-30% out of the money, 7-30 days out; roll or let it expire; if assigned, you sold your coin at a price you chose in advance.
Fails when: a violent rally — you capped the upside that pays for all the flat months. This is the whole risk and it is the one people forget.
Crypto notes: the only options strategy that makes sense against a spot stack, and the only one in this part Abhi could plausibly use if he had Deribit access. Implied vol in crypto is high, so premium is rich. Selling calls into a strong uptrend is how people miss the move.
Test: log every call sold, its premium, and the spot's price at expiry; compare with simply holding.

### 177. Cash-secured put (getting paid to bid lower)
Options · weeks · Range/accumulation · ~70-80% expire worthless
Thesis: you want to buy the dip anyway, so sell someone the right to sell it to you at your bid, and collect a premium for waiting.
Rules: hold the cash; sell a put at the level you would happily buy; if assigned you own the coin at strike minus premium.
Fails when: a crash far below the strike — you are long at your strike while price is much lower. Only sell puts at a price you genuinely want to own.
Crypto notes: the synthetic version of a resting limit bid that pays you. Same risk as the limit bid plus the premium as compensation.
Test: compare with just resting the limit order.

### 178. The wheel (put, assignment, covered call, repeat)
Options · weeks-months · Range · income, capped
Thesis: 177 then 176 in a loop: sell puts until assigned, then sell calls until called away, then repeat.
Rules: only on an asset you want to hold; size so assignment is affordable in full.
Fails when: the asset trends hard in either direction — you buy the whole way down and cap the whole way up.
Crypto notes: popular content, mediocre in a market with crypto's trend magnitude.
Test: simulate over a full cycle, not one quarter.

### 179. Protective put (insurance on a spot stack)
Options · weeks-months · Any, pre-event · cost drag
Thesis: buy the right to sell at a floor; your downside below it is capped for the premium paid.
Rules: buy a put 10-20% below spot across an event you fear; treat the premium as an insurance bill.
Fails when: nothing happens, repeatedly. Persistent hedging is a large drag; crypto implied vol is expensive.
Crypto notes: rational before a known binary (a court ruling, an unlock cliff) and irrational as a standing policy.
Test: price the annual drag before adopting it.

### 180. Collar (protective put funded by a covered call)
Options · weeks-months · Uncertain · low cost, capped both ways
Thesis: sell the upside you do not need to pay for the downside you fear.
Rules: buy the put, sell the call, ideally for zero net premium.
Fails when: the rally you sold away.
Crypto notes: how a treasury protects a large position through a volatile quarter.
Test: compare to holding and to selling a portion outright.

### 181. Long straddle / strangle (buying volatility)
Options · days-weeks · Pre-breakout, pre-event · ~30-40% win / large R
Thesis: buy both a call and a put; profit if price moves far enough either way to cover both premiums. A pure bet on **magnitude, not direction** — exactly what the volatility gate forecasts.
Rules: buy before the expansion (compression, squeeze, pre-catalyst); size for the full premium as the max loss; exit on the expansion, not at expiry.
Fails when: implied volatility is already high (you overpay), or price sits still and theta bleeds you daily.
Crypto notes: the conceptual cousin of the QUIET/LOUD gate. If the gate says LOUD and options are cheap, this is the instrument that expresses it. Abhi cannot trade it on spot; the honest spot translation is "widen the stop, expect follow-through, do not fade".
Test: compare realised 12h range against the implied move priced by the straddle.

### 182. Short straddle / strangle (selling volatility)
Options · days-weeks · Range/post-event · ~70-80% win / unlimited risk
Thesis: sell both sides, keep the premium if price stays inside the range.
Rules: define the max loss with wings (see 183) or do not do it.
Fails when: any large move. Naked short volatility in crypto has bankrupted funds, not just retail.
Crypto notes: the classic "high win rate that eventually loses everything" — the exact shape of the 85% trap in Part 0. Excellent teaching example.
Test: simulate through a March 2020 or a cascade week.

### 183. Iron condor / iron butterfly
Options · weeks · Range · ~65-80% win / defined risk
Thesis: 182 with bought wings that cap the disaster; income if price stays in a band.
Rules: define the band from the expected move, not hope; manage at 50% of max profit.
Fails when: crypto leaves the band, which it does more than equities do.
Crypto notes: designed for index-like assets; crypto's fat tails make the band wider and the premium thinner than it looks.
Test: log the band vs realised range.

### 184. Calendar / diagonal spread
Options · weeks · Compression before expansion · defined risk
Thesis: sell a near-dated option, buy a longer-dated one; profit from the near one decaying faster.
Rules: works best when near-term implied vol is high relative to longer-term.
Fails when: a big move immediately.
Crypto notes: requires a real term structure; Deribit has one.
Test: term-structure slope vs outcome.

### 185. Risk reversal (sell a put, buy a call)
Options · weeks · Bullish · leveraged directional
Thesis: finance upside exposure by selling downside.
Rules: only at a level you would buy; the short put is a real obligation.
Fails when: a crash; you are long at the strike with a worthless call.
Crypto notes: the skew (puts vs calls priced) is itself a sentiment read: heavy put skew marks fear, and extremes have contrarian value.
Test: log 25-delta skew vs forward returns.

### 186. Gamma scalping
Options · intraday · High realised vol · market-neutral-ish
Thesis: hold long options (long gamma), hedge the delta repeatedly in spot; if realised volatility exceeds what you paid in implied, the hedging profits exceed the theta bill.
Rules: continuous rehedging, tight execution costs.
Fails when: realised vol comes in below implied, or hedging costs eat it.
Crypto notes: a real professional strategy and a real reason market makers care about the volatility forecast. Out of reach at retail cost levels.
Test: realised vs implied volatility spread over time.

### 187. Volatility risk premium harvesting
Options · systematic · Any · small positive with tail risk
Thesis: implied volatility exceeds subsequent realised volatility most of the time, so systematically selling volatility is positive-expectancy with a fat left tail.
Rules: sell defined-risk structures, size for the tail, never scale up after good months.
Fails when: the tail. It always eventually arrives.
Crypto notes: the premium is larger in crypto than equities, and so is the tail.
Test: implied minus realised, distribution of the difference.

### 188. Dispersion / correlation trading
Options · weeks · Any · institutional
Thesis: trade the difference between index volatility and the volatility of its members.
Crypto notes: no true crypto index option market at retail. Listed for completeness.

### 189. Max-pain / gamma pin
Options · around expiry · Expiry days · see strategy 67
Thesis: dealer hedging around large open interest strikes pins price into expiry.
Crypto notes: real on large Deribit expiries; useful as *context* for a spot day trade.
Test: distance to max pain 24h before vs at expiry.

### 190. Implied-volatility rank as a regime filter
Options · overlay · Any · filter
Thesis: IV rank (where current implied sits in its yearly range) tells you whether to be a buyer or seller of volatility, and warns of regime change.
Rules: high IV rank favours selling premium and fading extension; low IV rank favours buying premium and expecting expansion.
Crypto notes: **usable by Abhi without trading options at all** — Deribit's DVOL index is public. Low DVOL plus a Bollinger squeeze is a strong QUIET-to-LOUD transition signal.
Test: DVOL percentile vs realised 12h range, straight into the volatility gate.

### 191. Skew as a sentiment gauge
Options · overlay · Any · context
Thesis: when puts are much more expensive than equidistant calls, the market is paying up for protection.
Crypto notes: extremes in skew mark fear/greed better than most social sentiment measures, and it is free to read.
Test: 25-delta skew percentile vs forward 7-day returns.

### 192. Term-structure (contango/backwardation in vol)
Options · overlay · Any · context
Thesis: near-dated implied above long-dated (backwardation) signals acute stress; the reverse is calm.
Crypto notes: a genuine regime read; pairs with the volatility gate.
Test: slope vs subsequent realised vol.

### 193. Binary / exotic options
Options · any · Any · avoid
Thesis: fixed payout if a condition is met.
Crypto notes: overwhelmingly offered by unregulated venues with negative expected value by construction. Treat as gambling and say so.

### 194. Options-implied expected move as a target-setter
Options · overlay · Any · target selection
Thesis: the at-the-money straddle price implies the market's expected move to expiry; targets beyond it are ambitious, targets well inside it are conservative.
Crypto notes: **free and useful on spot.** If the implied daily move is 2.5% and your 2R target requires 6%, the plan is unrealistic. This is a better reality check than ATR alone on event days.
Test: implied move vs realised move by day type.

### 195. Volatility targeting on a spot book
Options-adjacent · overlay · Any · risk management
Thesis: scale position size inversely to forecast volatility so the portfolio's risk is constant rather than the position's notional.
Rules: size = risk budget ÷ (ATR-based stop); this is already how Jarvus sizes, and the LOUD gate's 0.6x multiplier is its explicit form.
Crypto notes: the single most transferable idea from institutional volatility trading into a retail spot account.
Test: constant-notional vs constant-risk equity curves on the journal.

## Part 19. DeFi-native and on-chain strategies (196-215)

On-chain strategies have a different risk profile from trading: smart-contract risk,
oracle risk, and total-loss outcomes that no stop protects against. Jarvus explains
them and is honest that "yield" is usually a payment for a risk that has not yet
shown up.

### 196. Liquidity provision (constant-product AMM)
DeFi · weeks-months · Range · fee income vs impermanent loss
Thesis: deposit two assets into a pool, earn a share of trading fees.
Rules: fees must exceed impermanent loss (the value lost relative to just holding, when the pair's ratio moves).
Fails when: one asset trends hard. IL at a 2x price move is about 5.7%; at 4x, about 20%.
Crypto notes: an LP position is structurally **short volatility** — the same shape as 182. Stablecoin pairs have minimal IL and minimal fees; volatile pairs have the reverse.
Test: compare the LP position against simply holding both assets (this is the only comparison that matters and it is the one dashboards hide).

### 197. Concentrated liquidity (Uniswap v3 style)
DeFi · days-weeks · Range · higher fees, higher IL
Thesis: provide liquidity only within a price band for far higher fee capture per dollar.
Rules: choose the band like a range trade; rebalance when price leaves it.
Fails when: price leaves the band — you are now 100% in the losing asset and earning nothing.
Crypto notes: this is an **actively managed range trade with extra steps**, and it should be evaluated with the range-trading rules in Part 4, not as passive income.
Test: fees earned vs IL vs holding, per rebalance cycle.

### 198. Stablecoin yield / lending
DeFi · any · Any · low single-digit to teens
Thesis: lend stablecoins to borrowers for interest.
Fails when: the protocol is exploited, the stablecoin depegs, or utilisation spikes and you cannot withdraw.
Crypto notes: yields above roughly the risk-free rate plus a few points are paying you for a risk. Ask what the risk is; there always is one.
Test: not applicable; due-diligence question, not a backtest.

### 199. Leveraged staking / looping
DeFi · weeks · Stable rates · positive carry, liquidation risk
Thesis: stake, borrow against it, stake again, repeat, to multiply a yield.
Fails when: the collateral asset depegs from what you borrowed (the classic stETH/ETH event), or rates invert.
Crypto notes: a leveraged carry trade wearing a yield costume. Every loop tightens the liquidation band.
Test: stress-test the collateral ratio at a 10% depeg.

### 200. Delta-neutral basis farming
DeFi/CeFi · weeks · Contango · see strategies 65-66
Thesis: long spot, short perp, collect funding.
Crypto notes: the honest "market-neutral yield" in crypto. Requires perps, which Abhi does not use. Risks are venue and margin-management, not direction.

### 201. Liquidation hunting / keeper bots
DeFi · continuous · Volatile · bots only
Thesis: be the one who liquidates undercollateralised positions and take the bonus.
Crypto notes: competitive, gas-war driven, infrastructure required.

### 202. MEV: arbitrage, sandwiching, backrunning
DeFi · milliseconds · Any · bots only; some of it predatory
Thesis: order-flow extraction from the mempool.
Crypto notes: sandwich attacks harm ordinary users and Jarvus does not help build them. Explain the mechanism so Abhi can **defend** against it (private RPC, MEV-protected transactions, tight slippage), which is what the meme-sleeve execution rules already require.
Test: n/a.

### 203. Airdrop farming
On-chain · months · Any · lottery-shaped
Thesis: use protocols early in the hope of a retroactive token distribution.
Fails when: no airdrop, sybil filters, or the token launches and dumps.
Crypto notes: costs are real and immediate (gas, capital lock-up, time); the payoff is speculative and taxable. Treat as a lottery ticket budget, not a strategy.
Test: log costs against realised distributions.

### 204. Governance and vote-incentive capture
DeFi · weeks · Any · niche
Thesis: hold governance tokens, sell your voting power to protocols bidding for emissions.
Crypto notes: real yields, real lock-ups, real token-price risk.

### 205. New-pool sniping
On-chain · seconds-minutes · Any · overwhelmingly negative
Thesis: buy at launch before the crowd.
Crypto notes: the meme-sleeve hard-fail list exists precisely because this is where losses come from. 94% of Solana meme traders lost money over 90 days. The filter, not the speed, is the edge.

### 206. Cross-chain and bridge arbitrage
On-chain · minutes · Dislocations · bots
Thesis: same asset, different price across chains.
Fails when: bridge risk, which has produced some of the largest losses in the industry.

### 207. NFT floor trading
On-chain · days · Any · illiquid
Thesis: buy near the floor, sell higher.
Crypto notes: far thinner liquidity than tokens, wash-trading in reported volume, and a wide spread. Not day trading.

### 208. Real-world-asset and tokenised-treasury yield
DeFi · months · Any · low, real
Thesis: on-chain exposure to short-term government debt.
Crypto notes: the closest thing to a genuine risk-free rate on-chain, and a legitimate parking place for idle stablecoins if custody/regulatory questions are satisfied.

### 209. Restaking
DeFi · months · Any · yield with correlated risk
Thesis: reuse staked capital to secure additional services for extra yield.
Fails when: slashing conditions across multiple services correlate.
Crypto notes: stacked risks for stacked yields; the risks are not independent.

### 210. Perp DEX funding-rate farming
DeFi · days · Extremes · see 66
Crypto notes: same as CeFi funding arbitrage with extra smart-contract risk.

### 211. Oracle-latency arbitrage
DeFi · seconds · Any · bots
Thesis: trade against a protocol that prices off a lagging oracle.
Crypto notes: has been the mechanism in several exploits; the line between arbitrage and attack is a legal one. Jarvus does not help design these.

### 212. Whale-wallet copy trading
On-chain · minutes-days · Any · weak
Thesis: mirror wallets with good records.
Fails when: the wallet is hedged elsewhere, is the exit liquidity's counterparty, or the record is selection bias from the thousands of wallets you did not follow.
Crypto notes: the tooling (GMGN, Cielo, Nansen) is genuinely useful as **confirmation**, which is exactly how the meme sleeve scores it — 10 of 100 points, never a trigger.

### 213. Exchange-flow trading
On-chain · hours-days · Any · background bias
Thesis: large inflows to exchanges precede selling; outflows precede holding.
Crypto notes: slow, noisy, and best used as backdrop. Already in `crypto-market-data.md`.

### 214. Miner-flow and hash-ribbon signals
On-chain · weeks-months · Cycle turns · slow
Thesis: miner capitulation (hash rate falling then recovering) has historically marked cycle lows.
Crypto notes: a small sample of cycle events — perhaps five observations. Interesting, not statistically strong. Say the sample size out loud.
Test: count the observations before believing the backtest.

### 215. Stablecoin depeg trading
On-chain · hours · Stress · asymmetric, dangerous
Thesis: buy a depegged stablecoin below par expecting recovery.
Fails when: the depeg is terminal. This is picking up a coin that may be worth zero.
Crypto notes: the distinction between a liquidity depeg and a solvency depeg is the entire trade, and it is not knowable in the first hours.

## Part 20. Portfolio, allocation and systematic capital (216-232)

Not day trading. These are how the rest of the account should behave while the day
trading happens, and several of them beat day trading outright for most people.

### 216. Dollar-cost averaging into majors
Allocation · months-years · Any · beats most active trading
Thesis: buy a fixed amount on a fixed schedule; you accumulate more when prices are low without needing to time anything.
Fails when: the asset goes to zero, or you stop during the drawdown (which is when it does its work).
Crypto notes: given that 97% of day traders past 300 days lose money, DCA into BTC/ETH is the honest benchmark every active strategy should be compared against. Jarvus should name it when Abhi's journal is negative over 50+ trades.
Test: compare the journal's total R, converted to dollars, against DCA over the same window.

### 217. Value averaging
Allocation · months · Any · slightly better than DCA, more work
Thesis: target a portfolio value path; invest more when behind, less (or sell) when ahead.
Fails when: the required buy in a deep drawdown exceeds available cash.
Test: simulate against DCA over a full cycle.

### 218. Fixed-weight rebalancing
Allocation · months · Range-bound relative moves · harvests volatility
Thesis: hold fixed percentages (e.g. 60 BTC / 30 ETH / 10 SOL); rebalance periodically, which mechanically sells what rose and buys what fell.
Fails when: one asset trends far above the others — rebalancing sells the winner.
Crypto notes: a genuine, free "rebalancing bonus" in high-volatility, low-correlation assets. Crypto assets are highly correlated, which shrinks it.
Test: rebalanced vs buy-and-hold over 3 years.

### 219. Core-satellite
Allocation · ongoing · Any · the structure Jarvus implicitly assumes
Thesis: a large passive core (BTC/ETH, self-custodied) plus a small active satellite (the day-trading and meme sleeves).
Crypto notes: this is the correct home for everything in this skill. The day-trading account should be a satellite sized so that losing it entirely changes nothing important.

### 220. Risk parity
Allocation · months · Any · institutional
Thesis: weight positions by inverse volatility so each contributes equal risk.
Crypto notes: all crypto assets share one dominant risk factor (BTC), so the diversification is mostly illusory.

### 221. Volatility targeting on the portfolio
Allocation · ongoing · Any · genuinely useful
Thesis: scale total exposure so portfolio volatility is constant; de-risk automatically in turbulent regimes.
Crypto notes: this is the portfolio-level version of the volatility gate, and the evidence for it is stronger than for most signals.
Test: constant-vol vs constant-notional equity curves.

### 222. Trend-following allocation (time-series momentum on the stack)
Allocation · weeks · Trends · the best-evidenced systematic strategy
Thesis: hold the asset when it is above a long moving average (e.g. the 200-day), move to cash when below.
Fails when: whipsaw ranges around the average.
Crypto notes: has historically cut crypto's worst drawdowns substantially at the cost of some upside and some whipsaws. One of the very few rules with decades of cross-asset evidence behind it.
Test: 200-day filter on BTC since 2015: compare CAGR and max drawdown against holding.

### 223. Cross-sectional momentum across a basket
Allocation · weeks · Alt seasons · see 148
### 224. Equal-weight vs market-cap weight
Allocation · months · Any · structural choice
Crypto notes: equal weight over-weights small caps and their risks; cap weight concentrates in BTC.

### 225. The barbell
Allocation · ongoing · Any · robust
Thesis: most of the capital in the safest thing, a small slice in maximum-convexity bets, nothing in the middle.
Crypto notes: cash/treasuries plus a small high-risk sleeve. Maps cleanly onto the majors/meme split, and explains why the meme sleeve is capped at survival size.

### 226. Kelly and fractional Kelly
Sizing · ongoing · Any · see risk-management.md
Crypto notes: requires knowing your edge, which requires 50+ logged trades. Quarter-Kelly is a ceiling, not a target.

### 227. Anti-martingale / pyramiding into strength
Sizing · ongoing · Trends · see 158
### 228. Equity-curve trading
Sizing · ongoing · Any · see 164
### 229. Drawdown-triggered de-risking
Sizing · ongoing · Any · the drawdown protocol in risk-management.md
### 230. Monte Carlo position sizing
Sizing · overlay · Any · see 154
Thesis: shuffle the journal's R outcomes to estimate the drawdown distribution, then size so the 95th-percentile drawdown is survivable.

### 231. Tax-aware trading and lot selection
Ops · ongoing · Any · real money
Thesis: in Canada, frequent trading may be treated as business income rather than capital gains; every disposition is a taxable event and crypto-to-crypto counts.
Crypto notes: Jarvus is not a tax advisor and says so, but it should flag that high trade frequency has a tax consequence and that records must be kept per trade. The journal doubles as that record.

### 232. Custody and counterparty allocation
Ops · ongoing · Any · survival
Thesis: exchange balances are unsecured claims on a company. Keep only active trading capital there.
Crypto notes: already a hard rule in `risk-management.md`; repeated here because it has cost more people more money than any strategy on this list.

## Part 21. Execution algorithms and cost strategies (233-245)

For a retail spot trader, **execution is the largest controllable edge**. The v5
measurement is unambiguous: 19 of 21 positive configurations needed maker pricing.
This part is therefore more valuable to Abhi than most of the signal parts.

### 233. Maker-only (post-only) entries
Execution · any · Any · the single biggest retail improvement
Thesis: pay the maker fee instead of the taker fee by resting a limit order.
Rules: place the limit at the level the plan named; accept that some fills are missed.
Crypto notes: on Kraken Pro this is 16bps vs 26bps; on Coinbase Advanced and MEXC the maker fee can be **zero**. In the measured tables, that difference is the whole difference between a live edge and a dead one.
Test: re-run any journal at maker vs taker fees. The gap will be larger than any setup change.

### 234. Limit-at-level vs market-on-confirmation
Execution · any · Any · trade-off
Thesis: resting at the level gets a better price and a worse fill rate; entering on the confirmed close gets a worse price and a higher win rate.
Crypto notes: the measured cost table decides this. At 4x ATR stops the price difference matters less than the fee difference, so favour the limit.
Test: log both, compare realised R.

### 235. TWAP / VWAP execution
Execution · minutes-hours · Large size · institutional
Thesis: split an order over time to reduce impact.
Crypto notes: only relevant if the order is a meaningful share of the book — which, for a meme with a $50k pool, a retail order can be. The meme rules already cap size at 1% of the pool.

### 236. Iceberg orders
Execution · any · Large size · hides size
### 237. Scaling in across a zone
Execution · any · Wide levels · see execution-and-order-types.md
### 238. Slippage budgeting
Execution · any · Any · essential on alts
Thesis: set a maximum acceptable slippage and skip the trade if the book cannot fill you inside it.
Crypto notes: the meme sleeve's "round-trip > 8% = no trade" gate is exactly this.

### 239. Venue selection and fee-tier laddering
Execution · ongoing · Any · large, boring, effective
Thesis: the same strategy is profitable on one venue and not on another. Volume tiers lower fees.
Crypto notes: the fee table in the Jarvus core is the most actionable table in the whole system.

### 240. Rebate capture
Execution · continuous · Any · professional
### 241. Order-type selection for stops (stop-market vs stop-limit)
Execution · any · Any · stop-market, always
Thesis: a stop-limit that does not fill leaves the position open in the exact scenario the stop existed for.
### 242. Time-of-day liquidity selection
Execution · any · Any · free improvement
Thesis: trade when the book is deepest; spreads and slippage are session-dependent.
Crypto notes: 7:30-10:00 AM MT is both the best liquidity and the best structure window. Two reasons for one rule.
### 243. Partial-fill and rounding management
Execution · any · Any · operational
Thesis: round size down to the exchange step; confirm the stop covers the filled size, not the intended size.
### 244. Cross-venue best execution
Execution · any · Any · marginal at retail
### 245. Cost-aware strategy selection
Execution · overlay · Any · **the v5 core insight**
Thesis: choose the strategy whose natural stop distance makes its cost in R acceptable at your fee tier, rather than choosing a strategy and then discovering the cost.
Crypto notes: this reverses the usual order of operations and it is the most important idea in the Jarvus evidence layer. Cost in R = round-trip cost % ÷ stop distance %. Pick the stop width first.
Test: the cost table. Run it for your venue before choosing a timeframe.

## Part 22. Seasonality, calendar and cycle (246-258)

Treat every entry here as a hypothesis with a multiple-comparisons problem attached.
With 24 hours, 7 weekdays and 12 months on the menu, some will look significant by
chance. The measured example in the Jarvus core (the "22:00 UTC" claim that tested at
Sharpe 0.09) is the cautionary tale.

### 246. Hour-of-day effects
Seasonality · intraday · Any · mostly noise
Crypto notes: measured — hour 22 UTC positive, hour 23 the worst of the day, the pair cancels. With 24 tests you need roughly t = 2.9 to clear chance. Do not trade these without that bar.

### 247. Day-of-week effects
Seasonality · daily · Any · unstable, except weekends
Crypto notes: the one robust finding is **lower weekend liquidity**, and the measured direction AUC on weekends was 0.498 on 16,224 bars — literally no edge. That is now a hard rule in Jarvus, and it is the only day-of-week rule that earned it.

### 248. Month-of-year / "Uptober" / "Sell in May"
Seasonality · monthly · Any · small samples
Crypto notes: BTC has roughly 15 years of monthly data, so each calendar month has ~15 observations. That is far too few to support a trading rule. Say the sample size.

### 249. Turn-of-month effects
Seasonality · daily · Any · weak
### 250. Halving cycle positioning
Cycle · years · Cycle · 4 observations
Thesis: BTC's supply issuance halves roughly every four years and price has historically risen into and after it.
Crypto notes: **four observations.** Anyone quoting this as statistics is misusing the word. As a narrative that influences other participants' behaviour, it has some reflexive force; as evidence, it has almost none.

### 251. The four-year cycle phase model
Cycle · months-years · Cycle · framework, not a signal
Crypto notes: covered in `regimes-and-cycles.md`. Useful for setting the backdrop (which playbooks are live), useless for timing.

### 252. Pi cycle top / rainbow chart / stock-to-flow
Cycle · months · Cycle · overfit to a handful of events
Thesis: various indicator crossovers that "called" prior cycle tops.
Crypto notes: stock-to-flow in particular failed badly out of sample after being widely promoted. A model fitted to three cycle tops that then misses the fourth is the textbook overfitting lesson — use it as one.
Test: ask what the model predicted *before* each event, not after.

### 253. MVRV, NUPL, SOPR and on-chain valuation bands
Cycle · weeks-months · Cycle extremes · slow context
Thesis: aggregate unrealised profit/loss across holders marks euphoria and capitulation zones.
Crypto notes: genuinely informative at multi-month extremes, useless intraday, and the thresholds drift as the holder base changes.

### 254. Realised price and cost-basis bands
Cycle · months · Cycle lows · context
### 255. Funding/basis as a cycle-phase gauge
Cycle · weeks · Late cycle · see 65
Thesis: persistently high annualised basis marks leverage-driven late-cycle conditions.
### 256. Post-event drift (halvings, ETF approvals, listings)
Event · days-weeks · Any · see 96
### 257. Tax-loss selling and year-end flows
Seasonality · December · Any · weak
### 258. Options expiry calendar effects
Seasonality · monthly/quarterly · Expiry · see 67, 189

## Part 23. Sentiment, alt-data and flow (259-272)

The trust ranking in the Jarvus core places most of this near the bottom on purpose:
it is easy to fake, easy to misread, and often already in the price.

### 259. Fear and Greed Index
Sentiment · daily · Extremes · weak contrarian
Thesis: extreme fear marks lows, extreme greed marks tops.
Crypto notes: it is largely a *function of recent price and volatility*, so it is a lagging restatement of the chart. At true extremes it has some contrarian value on a multi-week horizon; intraday, none.
Test: index bucket vs forward returns at several horizons.

### 260. Social volume and mention spikes
Sentiment · hours · Any · lags leg one
Crypto notes: a token trending on feeds has already made its first move. Useful as a "what is alive today" filter, exactly as the meme sleeve uses it.

### 261. Google Trends
Sentiment · weeks · Cycle extremes · coincident
Crypto notes: peaks with price, does not lead it.

### 262. Funding as sentiment
Sentiment · hours · Any · see Part 7
Crypto notes: the best-quality sentiment measure available free, because it is a *paid* position rather than an opinion.

### 263. Long/short ratios
Sentiment · hours · Extremes · weak
### 264. Open interest as commitment
Sentiment · hours · Any · see 62
### 265. Perp premium / spot-led vs perp-led moves
Flow · hours · Any · genuinely useful; see 70
Thesis: spot-led moves are more durable than perp-led ones.
Crypto notes: one of the higher-quality free reads in crypto, and directly relevant to a spot trader.

### 266. Stablecoin printing as liquidity
Flow · weeks · Any · slow backdrop
### 267. ETF flows
Flow · daily · Any · see 95
Crypto notes: now a major, reported, daily flow variable for BTC and ETH that did not exist in earlier cycles. Worth watching; already in the core.

### 268. Coinbase premium / regional premia
Flow · hours · Any · context
Thesis: a persistent premium on a US venue suggests US institutional bid; the Korean (Kimchi) premium suggests retail demand there.
Crypto notes: free to read and occasionally informative at extremes.

### 269. Whale alerts and large transfers
Flow · minutes · Any · mostly noise
### 270. Insider and team-wallet monitoring
Flow · any · Alts · a hard-fail input, not a signal
Crypto notes: the meme sleeve treats dev selling and LP withdrawal as instant NO. That is the correct use.

### 271. News sentiment models and LLM headline scoring
Alt-data · minutes · Events · fast-decaying
Crypto notes: by the time a headline is scored and traded, the algorithms have moved. The measured edge in published work shrinks to nothing after realistic latency and fees.

### 272. Order-flow imbalance
Flow · seconds · Any · real but out of reach
Crypto notes: genuinely predicts returns at roughly a **3-second** horizon with 1-second order-book data. Real, documented, and not reachable from a laptop on a spot account. Worth knowing so Abhi can recognise that "order flow" content aimed at retail is not this.

## Part 24. Arbitrage and market-neutral (273-288)

Arbitrage is where the genuinely high win rates in finance actually live — and almost
all of it requires speed, capital on multiple venues, or borrow that retail does not
have. When Abhi asks "what has a real 90% win rate", this part is the honest answer,
together with the reason he cannot run most of it.

### 273. Cross-exchange spot arbitrage
Arb · seconds · Dislocations · very high hit rate, tiny edge, bot-only
Thesis: same coin, two venues, different prices.
Fails when: withdrawal delays, fees, and the fact that faster participants already took it. The price difference you can see on two charts is usually smaller than the round-trip cost.
Crypto notes: requires pre-funded balances on both venues, which is itself an exchange-risk decision.

### 274. Triangular arbitrage
Arb · seconds · Any · bot-only
Thesis: BTC→ETH→USDT→BTC ends with more than you started.
Crypto notes: exchanges' own market makers close these in milliseconds.

### 275. Cash-and-carry / basis capture
Arb · weeks-months · Contango · high hit rate, real
Thesis: see strategy 65. Long spot, short the dated future, capture the basis.
Crypto notes: the most legitimate "high win rate" trade in crypto. Needs derivatives and margin management. Not available to Abhi as configured, and the honest note is that its risk is venue failure, not direction.

### 276. Funding-rate arbitrage across venues
Arb · days · Dislocations · see 66
### 277. Perp-spot convergence at settlement
Arb · hours · Any · thin
### 278. Statistical arbitrage / pairs trading
Market-neutral · hours-days · Any · see 87
Thesis: trade the spread between two correlated assets when it deviates from its mean.
Crypto notes: works on spot in a limited way (rotate between two majors rather than shorting one), and that rotation version *is* available to Abhi. Long the relatively strong major, hold less of the weak one.
Test: spread z-score entries; compare against holding both equally.

### 279. Index arbitrage
Arb · seconds · Any · institutional
### 280. ETF creation/redemption arbitrage
Arb · daily · Any · authorised participants only
Crypto notes: worth understanding because it is the mechanism that keeps spot BTC ETFs near NAV, and because ETF flows are now a daily variable in the crypto tape.

### 281. Volatility arbitrage
Arb · days · Any · see 186-187
### 282. Latency arbitrage
Arb · microseconds · Any · infrastructure
### 283. Market making with inventory management
Market-neutral · continuous · Any · the real high-win-rate business
Thesis: quote both sides, earn the spread and rebates, manage inventory skew.
Crypto notes: this is what a genuine 90%+ "win rate" looks like in practice — thousands of tiny wins, a few large adverse-selection losses, and an operation rather than a strategy. Explaining this is often the most useful answer to "how do professionals win".

### 284. Grid trading as a market-making proxy
Market-neutral · continuous · Ranges · see 32 and Part 16
Crypto notes: a grid is retail market making without inventory management or a stop. The individual orders win most of the time, which is exactly why it feels good until the trend arrives.

### 285. Delta-neutral yield stacking
Market-neutral · weeks · Any · see 200
### 286. Convertible / structured product arbitrage
Arb · months · Any · institutional
### 287. Liquidation-cascade liquidity provision
Market-neutral · minutes · Cascades · dangerous, real
Thesis: rest bids far below the market to be filled by forced sellers during a cascade.
Crypto notes: the spot version is a resting limit ladder into a liquidation cluster, which a patient spot trader *can* do. It is the disciplined form of "buy the wick". Size it as a position you are content to hold, because you will be filled exactly when everything is worst.
Test: log resting-ladder fills against the subsequent 24h.

### 288. Insurance-fund and ADL awareness
Ops · any · Stress · defensive knowledge
Crypto notes: on the biggest days, profitable leveraged positions can be force-closed. A reason the spot-only constraint is less of a handicap than it looks.

## Part 25. Remaining named systems and completions (289-320)

### 289. Turtle Trading (the full original system)
Trend · daily · Trends · ~35% / large R
Thesis: Donchian breakouts (20 and 55 day), ATR-based ("N") position sizing, pyramiding at 0.5N, 2N stops, correlated-position limits.
Crypto notes: the sizing and unit-limit rules aged better than the entry. Jarvus's ATR sizing and correlated-position cap are direct descendants.
Test: 55-day breakout on BTC daily with 2N stops.

### 290. Dual momentum (absolute + relative)
Trend · monthly · Any · well-evidenced in equities
Thesis: hold the strongest asset, but only if it also beats cash.
Crypto notes: the "beats cash" filter is what keeps it out of bear markets; a crypto version is "hold BTC only when above the 200-day".

### 291. The 200-day moving average filter
Trend · daily · Any · the single most robust rule on this list
Thesis: be long when above it, in cash when below.
Crypto notes: does not maximise returns; substantially reduces drawdowns and removes the worst stretches. Jarvus already uses price vs the 200-day as a regime gate.
Test: compare CAGR and max drawdown vs holding, over the longest sample available.

### 292. Momentum with a volatility filter
Trend · daily · Any · see 222, 221
### 293. Bollinger Band Squeeze (Bollinger's own rules)
Breakout · any · Compression · see 35
### 294. Keltner/Bollinger "TTM squeeze" (Carter)
Breakout · any · Compression · see 35
### 295. ATR trailing "chandelier exit" (Chuck LeBeau)
Management · any · Trends · see 160
### 296. The "3-bar trailing stop" and swing-based trails
Management · any · Trends · see 160
### 297. Ross hooks and 1-2-3 patterns (Joe Ross)
Price action · any · Trends · ~45% / 2R
Thesis: after a breakout, the first pullback that fails to continue and then resumes (the "hook") is a continuation entry.
Crypto notes: the same structure as break-of-structure plus first higher low (strategy 3).

### 298. Sperandeo's 1-2-3 trend change
Reversal · daily · Trend ends · discretionary
Thesis: trendline break, failed retest, then a break of the prior swing — three confirmations before calling a reversal.
Crypto notes: an excellent discipline against calling tops early; it is the long-form version of "one CHoCH does not make a reversal".

### 299. Dow Theory
Framework · any · Any · the origin of structure trading
Thesis: trends persist until the sequence of highs and lows changes; volume should confirm; movements have primary, secondary and minor degrees.
Crypto notes: everything in `market-structure.md` descends from this.

### 300. Livermore's pivotal points and "line of least resistance"
Framework · any · Trends · classic
Thesis: act when price confirms at a pivotal point, not before; the market's path of least resistance is the trend.
Crypto notes: Livermore's risk rules (never average down, cut losses fast, size up only on proven positions) match this skill's rules almost exactly, a century earlier.

### 301. Point-and-figure charting
Chart · any · Any · noise filter
Thesis: chart price movement only, ignoring time; box sizes and reversal amounts define signals.
Crypto notes: equivalent in spirit to Renko (strategy 123); the vertical count gives mechanical targets.

### 302. Market Profile / TPO (Steidlmayer)
Framework · intraday · Any · see 120
### 303. Auction Market Theory
Framework · intraday · Any · the theory under 120
Thesis: markets move to facilitate trade; price moves away from value until it finds opposing interest, then returns.
Crypto notes: the cleanest mental model for why ranges and value areas behave as they do.

### 304. Order-flow footprint reading
Order flow · intraday · Any · see 54, 57, 60
### 305. Delta divergence and absorption at extremes
Order flow · intraday · At levels · see 54
### 306. Composite operator / Wyckoff cause-and-effect
Framework · any · Any · see 117
### 307. Elliott wave with Fibonacci confluence
Framework · any · Trends · see 121, 129
### 308. Gann angles, squares and time cycles
Framework · any · Any · no evidence
Crypto notes: when asked, say plainly that no rigorous test supports it, and redirect to structure. Do not pretend otherwise to be agreeable.

### 309. Astrological and lunar-cycle trading
Framework · any · Any · no evidence
Crypto notes: the full-moon effect is a classic multiple-comparisons artifact.

### 310. Chart-pattern recognition by machine learning
Quant · any · Any · usually overfit; see 151
### 311. Reinforcement-learning trading agents
Quant · any · Any · overfit, and the reward function is the hard part
Crypto notes: agents trained on historical prices learn the historical regime. The published successes rarely survive walk-forward with costs.

### 312. Genetic-algorithm rule mining
Quant · any · Any · maximal overfitting risk
Thesis: search millions of rule combinations for the best historical performer.
Crypto notes: searching a million rules guarantees that some look brilliant by chance. Without walk-forward and a multiple-comparisons correction, the output is noise with a backtest attached.

### 313. Ensemble and voting models
Quant · any · Any · see 153
### 314. Regime-switching models (HMM, Markov)
Quant · any · Any · see 150
### 315. Hawkes processes and volatility clustering models
Quant · intraday · Any · the mathematics behind the volatility gate
Thesis: events cluster and excite further events; volatility is self-exciting, which is why it is forecastable when direction is not.
Crypto notes: this is the formal reason the Jarvus volatility gate works and the direction model does not. Worth naming when Abhi asks *why* volatility is the predictable part.

### 316. GARCH-family volatility forecasting
Quant · daily · Any · the classical volatility forecast
Thesis: tomorrow's variance is a function of recent variance and recent shocks.
Crypto notes: a simple GARCH(1,1) or even an ATR-vs-30-day-average ratio captures most of the volatility-clustering signal. The manual gate readings in the Jarvus core are a hand-computed version of this.
Test: compare an ATR-ratio gate against the model's gate on the same bars.

### 317. Realised-volatility estimators (Parkinson, Garman-Klass, Yang-Zhang)
Quant · any · Any · better vol measurement from OHLC
Thesis: estimators that use the high, low, open and close extract more volatility information per bar than close-to-close does.
Crypto notes: a genuine, cheap improvement to the volatility gate for anyone extending these scripts.

### 318. Triple-barrier labelling and meta-labelling (Lopez de Prado)
Quant · any · Any · methodology, not a strategy
Thesis: label outcomes by which of three barriers (profit, stop, time) is hit first; then train a second model to decide *whether to take* the primary model's signal.
Crypto notes: the v5 engine already uses triple-barrier labelling. Meta-labelling is the formal version of what the confluence score does by hand — a filter on an existing signal.

### 319. Purged and embargoed cross-validation
Quant · any · Any · methodology
Thesis: standard cross-validation leaks in time series; purging and embargoing removes overlapping information between train and test.
Crypto notes: this is why the v5 numbers are trustworthy and most published crypto backtests are not.

### 320. Deflated Sharpe and the multiple-comparisons problem
Quant · any · Any · methodology, and the most important item in Volume II
Thesis: if you test many strategies, the best one looks good by chance; the Sharpe ratio must be deflated by the number of trials.
Crypto notes: this single idea invalidates most strategy content that exists. Jarvus should apply it out loud whenever it reports a backtest: how many variants were tried before this one looked good?
Test: it is the test. Ask it of every result in this file, including the ones measured in Part 26.

## Part 26. The 80% experiment — what a high win rate is actually made of

Part 0 argues from theory that win rate is a dial rather than an edge. In September
2026 that argument was **measured**, because an argument is not evidence.

### What was run

`scripts/ladder.py` on **78,000 hourly candles** — BTC, ETH and SOL, 2023-10-01 to
2026-09-18, 26,000 bars each. Five real setups plus one deliberately worthless
control. Stop 4x ATR, final target 2R, 96-bar time limit. Fills are pessimistic:
entry at the next bar's open plus slippage, and **if a bar touches both the stop and a
profit rung, the stop is taken**. Every fill pays a fee, so a three-exit ladder pays
three fees.

The control matters most. `benchmark` goes long **every twelfth bar regardless of
anything** — no trend filter, no level, no trigger, no volume. It is an entry with no
edge by construction. If the ladder produces the same win rate on the control as on a
real setup, then the win rate belongs to the exit rules, not to the analysis.

### Result A — where the 80% comes from (gross, zero fees)

| Ladder | ORB green % | ORB E(R) | **Random entries green %** | Random E(R) |
|---|---|---|---|---|
| single exit at +2R | 38.7% | −0.005 | **44.1%** | +0.065 |
| sell half at +1R | 51.2% | **+0.050** | **50.9%** | +0.030 |
| sell half at +0.5R | 65.1% | +0.013 | **65.9%** | +0.018 |
| sell half at +0.33R | 75.2% | +0.017 | **73.9%** | +0.009 |
| **sell half at +0.25R** | **79.5%** | +0.012 | **78.6%** | +0.005 |
| sell half at +0.2R | 82.9% | +0.015 | **82.1%** | +0.004 |
| sell 85% at +0.15R | 87.2% | +0.007 | **86.3%** | −0.003 |

Every ladder moves the stop to breakeven once the first rung fills.

**An 80% win rate is real, reachable and reproducible.** Sell half the position at
+0.25R, move the stop to breakeven, let the rest run: 79.5% of 669 trades closed
green. Push the rung to +0.2R and it is 82.9%. There is no trick and no curve fit.

**And it has nothing to do with the setup.** Random entries produce 78.6% on the same
ladder. The entire win rate is manufactured by the exit rules. A trader running this
could truthfully advertise "79% win rate" while having no edge whatsoever — which is
precisely what a great deal of trading education is.

Note what it costs even before fees: the +1R ladder earns **+0.050R** per trade, while
the 80% ladder earns **+0.012R**. Buying the win rate up from 51% to 80% cost roughly
**three quarters of the expectancy** in a frictionless world.

### Result B — what it costs once fees exist (ORB)

Basis points are **one side**; a plain entry-and-exit pays twice this, and a laddered
exit pays more because each rung is another fill.

| Venue / tier | Half at +1R | | Half at +0.25R (the 80% ladder) | |
|---|---|---|---|---|
| | green % | E(R) | green % | E(R) |
| gross (no fees) | 51.2% | +0.050 | 79.5% | +0.012 |
| maker ~0-10bps (Coinbase Adv, MEXC) | 51.0% | **+0.019** | 79.7% | −0.018 |
| Binance / OKX spot 20bps | 51.0% | −0.011 | 79.5% | −0.053 |
| good maker tier 30bps | 50.6% | −0.044 | 78.3% | −0.077 |
| NDAX 40bps | 50.5% | −0.077 | 74.9% | −0.112 |
| Kraken Pro taker 52bps | 50.7% | −0.111 | **68.3%** | −0.147 |

Three things to take from this table.

1. **Exactly one configuration in it makes money**: the +1R ladder at maker pricing,
   +0.019R per trade. That is consistent with the wider v5 finding that 19 of 21
   positive configurations required maker fees.
2. **The 80% ladder is negative at every real fee tier**, and it is more negative than
   the lower-win-rate ladder at every single tier. The high win rate is not merely
   unhelpful; it is actively worse, because the extra rungs mean extra fills and the
   +0.25R it banks is barely larger than the fee it pays to bank it.
3. **At retail taker fees the 80% is not even 80% any more.** It falls to 68.3%,
   because a +0.25R partial minus two fees no longer closes green. The vanity metric
   cannot be bought at retail pricing either.

### Result C — the part that should change how you read any backtest

First 60% of trades against the last 40%, gross:

| Setup | Ladder | In-sample green % | In-sample E | Out-of-sample green % | Out-of-sample E |
|---|---|---|---|---|---|
| ORB | half at 1R | 51.7% | +0.074 | 50.5% | **+0.012** |
| ORB | half at 0.25R | 78.3% | +0.007 | **81.3%** | +0.020 |
| Trend pullback | half at 1R | 53.5% | +0.101 | 45.2% | **−0.079** |
| RSI-2 | half at 1R | 56.2% | +0.119 | 48.7% | **−0.021** |
| Random | half at 1R | 52.6% | +0.068 | 48.4% | **−0.027** |
| Random | half at 0.25R | 79.8% | +0.029 | 76.9% | **−0.031** |

**The win rate replicates almost perfectly out of sample. The expectancy mostly does
not.** 78.3% became 81.3%; 79.8% became 76.9%. Meanwhile three of the four positive
in-sample expectancies turned negative.

That contrast is the most useful thing in this file. A number that is produced by
mechanics is stable, because mechanics do not decay. A number that is produced by an
edge is fragile, because edges decay and because some of what looked like edge was
never there. **So stability is not evidence of quality — and a strategy advertised on
its win rate is advertised on the one statistic that would look identical if it had no
edge at all.**

### How Jarvus uses this

When a high win rate is requested, do not refuse and do not lecture. Build it, then
show what it is made of:

- The 80% ladder is **real** and Jarvus can produce it on demand: sell half at +0.25R,
  stop to breakeven, runner to 2R. Measured at 79.5%.
- It is worth **+0.012R gross and negative at every retail fee tier**, and random
  entries score 78.6% on the same rules.
- The configuration that actually made money was **half at +1R at maker pricing**, at
  a 51% win rate and +0.019R — a *lower* win rate and the only positive cell in the
  table.
- Therefore the honest target is **expectancy after costs**, and the honest levers are
  **fee tier, stop width and selectivity** — in that order, because that is the order
  the measurements rank them in.

Re-run it on any data at any fee tier:

```bash
python3 scripts/ladder.py data/BTC_1h.csv data/ETH_1h.csv --sweep --fee-bps 5
python3 scripts/experiment_80.py data/BTC_1h.csv data/ETH_1h.csv data/SOL_1h.csv
```

### The caveat this file applies to itself (strategy 320)

Roughly 100 configurations were examined here — six setups by seventeen ladders by
several fee tiers. With that many trials, the best-looking cell is partly luck, and
the single positive result (+0.019R) is not large enough to survive a deflated Sharpe
correction with confidence. The honest reading is not "ORB at maker fees is the
answer". It is: **no configuration tested here produced a convincing edge, the one that
came closest needed maker pricing, and the high-win-rate configurations were the worst
of them.** Treat that as the finding.
