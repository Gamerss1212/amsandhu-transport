# Playbooks

Seven day-trading setups. Each one has a required context, a trigger, a stop, a
target, an invalidation, and the conditions under which it should be skipped. A
setup qualifies only when every element is present. When Claude cannot honestly
check a box, the verdict is WAIT.

Every playbook assumes the top-down read from `market-structure.md` has been done
and the sizing rules in `risk-management.md` apply.

## Contents

1. Trend pullback to value
2. Range edge fade
3. Breakout and retest
4. Liquidity sweep reversal
5. Funding / OI extreme fade
6. Session open range break
7. VWAP reclaim / rejection
8. Choosing between them
9. Grading a setup A / B / skip

---

## 1. Trend pullback to value

The bread and butter. Highest frequency, moderate win rate, clean risk.

**Context**
- 4H (or 1D) in a confirmed trend: HH/HL for longs. 21 EMA above 50 above 200, all
  sloping the trend's way.
- Price has pulled back to **value**: the 21 EMA on the setup timeframe, the
  session VWAP, a prior breakout level, or the order block / FVG that started the
  last leg. Ideally two of these overlap.
- The pullback is **orderly**: volume declining, no single huge red candle, RSI on
  the setup timeframe holding above 40 (longs).

**Trigger** (trigger timeframe, 5m)
- A CHoCH back in the trend direction: price takes out the most recent 5m lower
  high, or
- An engulfing candle / strong close above the 9 EMA, with RVOL above 1.2.

**Stop**: below the pullback low, minus 0.3-0.5 ATR (15m).

**Targets**: T1 the prior swing high (the HH), take a third to half. T2 a measured
move (the length of the last impulse leg projected from the pullback low) or the
next HTF level.

**Invalidation**: setup-timeframe close below the pullback low. The HL failed.

**Skip when**
- Price is more than 2 ATR from the 21 EMA (chasing, not pulling back).
- The pullback has retraced more than ~70% of the impulse leg (a deep pullback is
  often the first leg of a reversal).
- The pullback is into a tier-1 event.
- The HTF trend is mature (many legs, RSI divergence on the 4H, funding hot). Late
  trend pullbacks fail more often; take only A-grade ones.

## 2. Range edge fade

Crypto ranges more than it trends. Fading edges works when the range is real.

**Context**
- A range on the 1H or 4H with at least two touches of each edge and overlapping
  swings. Range height at least 2.5 ATR (setup timeframe) so a stop and 2R fit.
- No HTF trend pressing on the range (a range in the middle of a 1D uptrend is a
  continuation pause; fade only the lower edge, or skip the upper-edge shorts).
- Not a squeeze (Bollinger width contracting to multi-day lows means breakout risk
  is elevated).

**Trigger**
- Price reaches the edge (within 0.25 ATR) and prints a **rejection**: a pin bar,
  an engulfing candle back into the range, or a sweep of the edge that closes back
  inside. The sweep-and-close is the best version.

**Stop**: beyond the edge, past the sweep wick, plus 0.3 ATR.

**Targets**: T1 the range midpoint (take half). T2 the opposite edge.

**Invalidation**: a setup-timeframe close beyond the edge with follow-through
(the next candle does not come back).

**Skip when**
- It is the fourth or later test of the edge without a decisive rejection.
- Funding is extreme in the direction of the fade (fading resistance while funding
  is deeply negative is fading a short squeeze).
- Volume is expanding into the edge instead of contracting (that is a breakout
  attempt, not exhaustion).
- London or New York open is within 30 minutes; opens break ranges.

## 3. Breakout and retest

Chasing breakouts is a losing habit. Buying the **retest** of a real breakout is
not.

**Context**
- A range or consolidation (see playbook 2) or a Bollinger squeeze.
- HTF bias agrees with the breakout direction, or the HTF is a range and this is
  the range's edge.
- The breakout candle **closed** beyond the level with RVOL above 1.5, and ideally
  OI rose with it (new positions, not short covering).

**Trigger**
- Price returns to the broken level (old resistance, now support) and holds: a 5m
  candle wicks into the level and closes above it, or a 5m CHoCH forms at the level.
- Time filter: the retest should come within a handful of setup-timeframe
  candles. A breakout that drifts sideways for a day has lost its energy.

**Stop**: below the retest low, minus 0.3 ATR. If the retest low is inside the old
range by more than 0.5 ATR, the breakout has failed; do not take it.

**Targets**: T1 the breakout candle's high (or the post-breakout high). T2 the
measured move: the height of the range projected from the breakout level.

**Invalidation**: a setup-timeframe close back inside the range.

**Skip when**
- No retest (price runs without you). Missing a trade costs nothing.
- The breakout was on low volume or occurred during Asia session thin liquidity.
- The breakout runs immediately into an HTF level less than 2R away.
- The breakout is a sweep of equal highs/lows that closed back inside: that is
  playbook 4 in the other direction.

## 4. Liquidity sweep reversal

Lower win rate, high reward, and the most "crypto" of the setups.

**Context**
- An obvious liquidity pool: equal highs/lows, PDH/PDL, a range edge, a well-known
  round number, or a large liquidation cluster.
- Preferably in the direction of the HTF trend (sweeping lows in an uptrend), or at
  an HTF level (sweeping highs into a 4H resistance).
- Often occurs at a session open (London ~07:00, New York ~13:30 UTC, an hour
  later in winter) or around the
  daily close.

**Trigger**
- Price pierces the pool and, within one to three trigger-timeframe candles,
  **closes back** on the original side. Volume on the sweep candle is elevated
  (absorption). A 5m CHoCH after the reclaim is the highest-quality confirmation;
  entering on the reclaim close alone is the aggressive version.

**Stop**: beyond the sweep wick's extreme, plus 0.2-0.3 ATR. Sweeps that get swept
again are usually real breakouts.

**Targets**: T1 the nearest opposing structure (the last swing the other way, or
VWAP). T2 the opposite liquidity pool (the other side of the range, the other equal
highs). Sweeps regularly run from one pool to the other.

**Invalidation**: a close beyond the sweep extreme. It was a breakout.

**Skip when**
- The sweep candle does not close back inside. Waiting for the close is the whole
  edge.
- The sweep is with the HTF trend and against nothing (a sweep of highs in an
  uptrend with no HTF resistance is just a breakout with a wick).
- A tier-1 event caused the spike; news moves do not respect pools.

## 5. Funding / OI extreme fade

A positioning trade. Slower (1H-4H context), fewer signals, and it pairs with
another playbook for the trigger.

**Context**
- Funding at an extreme (BTC/ETH above +0.05% or below −0.03% per 8h; alts hotter)
  **and** OI elevated or rising into a level (the crowd is large and leveraged).
- Price at an HTF level against the crowd: crowded longs into 4H resistance, or
  crowded shorts into 4H support.
- Bonus: RSI or CVD divergence on the 1H, or a liquidation cluster just past the
  level (the squeeze's fuel).

**Trigger**
- A playbook-2 rejection or playbook-4 sweep at the level, on the 15m. The funding
  extreme by itself is never the trigger.

**Stop**: beyond the level plus 0.5 ATR (15m). Squeezes are violent; a tight stop
gets hit by the last spike before the reversal.

**Targets**: T1 the nearest liquidation cluster or swing on the crowded side (where
the liquidations start). T2 the level where the crowd entered (funding started
rising there; often the 4H 21 EMA or VWAP-anchored-to-the-last-swing).

**Invalidation**: a 1H close beyond the level with OI still rising. The crowd was
right and new money is joining.

**Skip when**
- Funding has been extreme for days in a strong trend. Persistence is the norm in
  trends; fade only at levels with a rejection.
- OI is falling (the crowd is already leaving; the squeeze fuel is gone).
- No structural level; "funding is high" in the middle of nowhere is not a trade.

## 6. Session open range break

An intraday breakout playbook keyed to the clock.

**Context**
- Use the **New York open** (13:30 UTC in US summer, 14:30 in winter) primarily;
  London open (07:00 UTC in British summer time, 08:00 in winter) secondary.
- Define the **opening range**: the high and low of the first 15 minutes (three 5m
  candles) after the open. Also mark the Asia session high/low (for London) or the
  London session high/low (for New York).
- HTF bias identifies the preferred direction. Take breaks in both directions only
  if the HTF is a range.

**Trigger**
- A 5m close outside the opening range with RVOL above 1.5, in the direction of
  the bias. Better: the break also takes out the prior session high/low.
- Aggressive: enter on the close. Conservative: enter on the first pullback that
  holds the range edge (which is playbook 3 at small scale).

**Stop**: the opposite side of the opening range, or the midpoint of the range if
the range is wider than 1 ATR (15m).

**Targets**: T1 one opening-range height beyond the break. T2 PDH/PDL or the
nearest HTF level. Session-open moves often run for 60-90 minutes then stall.

**Invalidation**: a 5m close back inside the opening range.

**Skip when**
- The opening range is wider than 1.5 ATR (15m): the move already happened.
- A tier-1 release is within the first hour (CPI days: wait for the release and
  treat the release time, 12:30 UTC in summer, as the open instead).
- The break is against the HTF bias and against the prior session's direction.

## 7. VWAP reclaim / rejection

The cleanest intraday trigger when the day has a direction.

**Context (reclaim, long)**
- HTF bias up or neutral. Price opened above VWAP, lost it during a pullback
  (trapping breakout sellers), and is now pressing back.
- Volume on the loss of VWAP was light; volume on the reclaim attempt is rising.

**Trigger**: a 5m close back above VWAP with RVOL above 1.2, followed by a hold
(the next candle does not close back below). Enter on the hold or on the first
touch of VWAP from above.

**Stop**: below the low made under VWAP, minus 0.3 ATR (5m).

**Targets**: T1 the day's high. T2 VWAP + 2 standard deviations, or PDH.

**Invalidation**: a 5m close back below VWAP after the reclaim.

**Rejection (short)** is the mirror: price below falling VWAP, rallies into it,
prints a rejection wick and closes back below. Stop above the wick. Targets: the
day's low, then VWAP − 2σ or PDL.

**Skip when**
- VWAP is flat and price has crossed it several times already (chop day; range
  playbook or no trade).
- Within 30 minutes of a tier-1 event.
- Late in the US session (after 19:00 UTC) when volume is leaving.

## 8. Choosing between them

| Market state (from the top-down read) | Look for |
|---|---|
| HTF trend, orderly pullback in progress | #1 Trend pullback, #7 VWAP reclaim |
| HTF range, price at an edge | #2 Range fade, #4 Sweep reversal at the edge |
| Squeeze / tight consolidation, volume building | #3 Breakout retest, #6 Session open break |
| Equal highs/lows, PDH/PDL, liquidation clusters nearby | #4 Sweep reversal |
| Funding extreme + OI high at an HTF level | #5 Positioning fade, triggered by #2 or #4 |
| Session open in the next 15 minutes | #6 Open range break |
| Trend day with price above/below VWAP all day | #7 VWAP reclaim / rejection |
| Chop, flat VWAP, no structure, weekend | Nothing. WAIT. |

## 9. Grading a setup A / B / skip

Score the plan honestly before writing the card:

- **A**: HTF bias, setup location, and trigger all aligned. Net R:R ≥ 2.5. Clean
  stop ≥ 0.5 ATR, no level in the way. Session and calendar clear. Full 1% risk.
- **B**: one element is weaker (counter-HTF but at an HTF level; R:R 2.0; slightly
  late trigger; mild funding headwind). Half risk (0.5%) and take T1 in full.
- **Skip**: two or more weak elements, or any hard no-trade condition from
  `SKILL.md`. Write what would upgrade it and wait.

Most days produce zero A setups on a single pair. That is normal. A trader who
takes only A and B setups across three or four pairs finds two to five trades a
day. A trader who takes C setups finds twenty and loses.
