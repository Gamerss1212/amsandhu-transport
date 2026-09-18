# Regimes and Cycles

The same setup has a different win rate depending on the market's regime. A day
trader who does not know the regime is running a strategy blind. This file covers
how to classify the regime and how each playbook's usage changes with it.

## Contents

1. The four intraday regimes
2. Classifying today's regime
3. Playbook adjustments per regime
4. Volatility regimes
5. The larger cycle and why a day trader still cares
6. Regime transitions: where the biggest wins and losses live

---

## 1. The four intraday regimes

| Regime | Signature | Share of days (rough) |
|---|---|---|
| **Trend day** | Opens near one extreme, closes near the other. Pullbacks shallow (to 9/21 EMA), VWAP rising/falling all day, RVOL elevated | ~20-30% |
| **Range day** | Two-sided, returns to VWAP repeatedly, edges reject, low RVOL, Bollinger flat | ~40-50% |
| **Volatile chop** | Big candles both ways, stops hit both sides, VWAP crossed many times, often around news | ~15-20% |
| **Dead / compression** | ATR shrinking, tiny candles, Bollinger squeeze, volume at lows; often weekends and pre-event | ~10-15% |

The percentages vary by asset and period; check them on the user's own market with
a quick look at recent daily candles.

## 2. Classifying today's regime

Do this after the first hour of the London session and again after the first
30 minutes of New York:

- **Opening range vs ATR**: if the first hour's range is already more than
  ~40% of the daily ATR and one-directional, a trend day is likely.
- **VWAP behavior**: price on one side of VWAP all morning with pullbacks holding
  it means trend. Multiple crosses mean range or chop.
- **RVOL**: elevated on directional candles is trend. Elevated on both directions
  is chop. Low everywhere is range or dead.
- **HTF context**: a 4H breakout from a multi-day range raises the odds of a trend
  day. A 4H mid-range raises the odds of a range day.
- **Calendar**: tier-1 event days are chop until the release, then often trend.
  Fridays after the US open, and weekends, lean range/dead.

State the regime explicitly in the analysis ("today reads as a range day so far")
and let it choose the playbook.

## 3. Playbook adjustments per regime

| Playbook | Trend day | Range day | Volatile chop | Dead / compression |
|---|---|---|---|---|
| 1 Trend pullback | Primary. Shallow pullbacks to 9/21 EMA, trail hard | Only at range edges | Avoid; pullbacks become reversals | Wait for the break |
| 2 Range fade | Avoid; edges break | Primary | Wider stops, half size, or skip | Ranges are too small to pay |
| 3 Breakout retest | Primary after the first leg | Fades usually win; retests fail | Avoid | Primary once the squeeze breaks with volume |
| 4 Sweep reversal | Only sweeps *with* the trend | Primary at the edges | Best R:R of any regime but lowest win rate | Rare |
| 5 Funding fade | Only at HTF levels; trend days carry extreme funding | Good at edges | Good after a cascade | Not applicable |
| 6 Open range break | Primary | First break usually fails; wait for the second | Skip | Skip |
| 7 VWAP reclaim | Primary on pullbacks | Reclaims fail; fade VWAP touches instead | Skip | Skip |

Position size: full in the regime the playbook is built for, half in adjacent
regimes, zero in the wrong regime.

## 4. Volatility regimes

ATR relative to its own history:

- **Low and falling** (ATR at multi-week lows, squeeze): expansion is coming.
  Targets must be modest until it does; then the first expansion move is the
  trade.
- **Rising**: trend legs. Widen stop buffers, widen targets, expect follow-through.
- **High and spiking** (post-news, post-cascade): stops are unreliable, slippage
  is large. Halve size or wait an hour.
- **High and falling**: the move is maturing; mean reversion improves.

A useful rule: the stop and target in ATR units stay the same; the *dollar* stop
scales with ATR, so size scales inversely. High-volatility days automatically get
smaller positions, which is exactly right.

## 5. The larger cycle and why a day trader still cares

Bitcoin has had multi-year cycles loosely tied to its halving (2012, 2016, 2020,
2024, next around 2028), with strong years followed by deep drawdowns. Whether
the pattern persists is unknowable, but the cycle phase changes the day-trading
backdrop:

- **Early bull / accumulation**: ranges, boring, funding neutral. Range playbooks.
  Alts dead.
- **Mid bull / expansion**: trend days frequent, dips shallow, funding warm. Trend
  playbooks, long bias, alts start to work.
- **Late bull / euphoria**: extreme funding, vertical alts, cascades every few
  days. Sweep reversals and funding fades pay; chasing kills. Shorts at HTF
  levels start working.
- **Bear / distribution**: lower highs, rallies sold, funding negative, sharp
  squeezes up. Short pullbacks (playbook 1 mirrored) and fade squeezes; longs
  only on capitulation sweeps with tight management.
- **Capitulation**: ATR spikes, OI resets, basis goes negative. The best long
  sweep-reversal setups of the cycle, but sized small because the tails are
  fattest here.

Estimate the phase from the weekly chart (price vs the 50-week and 200-week
moving averages, the sequence of weekly swings) and from funding norms over the
last month. State it as context, not as a forecast.

## 6. Regime transitions: where the biggest wins and losses live

Most large losses happen when a trader keeps applying the old regime's playbook
after the regime has changed: fading a range that has become a trend day, or
buying pullbacks on the day the uptrend breaks.

Signs a regime is changing:

- A range that has held for days breaks on RVOL above 2 and OI rising. Trend
  begins. Stop fading.
- A trend pullback goes deeper than 70% of the last leg, or the 21 EMA fails and
  the 50 EMA is tested on volume. Trend is weakening. Reduce trend-pullback size.
- ATR contracts for several sessions inside a trend. Compression before the next
  leg or a reversal. Wait for the break.
- Funding flips sign and stays flipped. The crowd has switched sides.
- Correlation with equities breaks (crypto moving alone). A crypto-specific driver
  is in play; macro levels stop mattering for a while.

The response to uncertainty about the regime is smaller size and fewer trades,
not a different indicator.
