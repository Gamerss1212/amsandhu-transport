# Indicators

Indicators are transformations of price and volume. They cannot know anything price
does not already know. Their job is to make certain facts easy to see at a glance:
trend, momentum, volatility, and participation. Use at most one from each category,
and always after reading structure.

## Contents

1. Trend: moving averages
2. Value: VWAP
3. Momentum: RSI and MACD
4. Volatility: ATR and Bollinger Bands
5. Participation: volume, relative volume, CVD
6. Combining them: the four-question model
7. What indicators cannot do
8. Quick settings table

---

## 1. Trend: moving averages

Use **exponential** moving averages (EMA); they weight recent price more and lag
less than simple ones.

Standard set for crypto day trading: **9, 21, 50, 200** on each timeframe.

How to read them:

- **Price relative to the 200 EMA** on the 4H and 1D: above is a bull regime, below
  is a bear regime. The 200 is where the biggest institutional and algorithmic
  mean-reversion interest lives. Trades toward the 200 from far away have a
  tailwind; trades away from it near it are prone to snapping back.
- **The 21 EMA** is the "value" line on the setup timeframe. In a healthy trend,
  pullbacks find support at or near the 21 EMA and bounce. When price is far above
  the 21 (more than ~2 ATR), it is stretched and chasing is dangerous.
- **The 9 EMA** is a short-term momentum line. On the trigger timeframe, a close back
  across the 9 after a pullback is a simple trigger.
- **Slope** matters more than crosses. A flat 50 EMA with price crossing it back and
  forth means range, not trend. Rising 21 above rising 50 above rising 200 is a
  clean stack, and clean stacks are where trend playbooks work.
- **Crosses** (9 over 21, 50 over 200 "golden cross") are lagging and mostly
  useless for entries. Use them for regime awareness only.

## 2. Value: VWAP

**Volume weighted average price**, anchored to the start of the session (00:00 UTC
for a daily VWAP). It is the average price paid by everyone today, weighted by size.
Institutions benchmark execution against it, so it is a real level, not a derived one.

- **Price above rising VWAP**: buyers are in control today. Pullbacks to VWAP are
  buyable in a trend.
- **Price below falling VWAP**: sellers in control. Rallies to VWAP are sellable.
- **VWAP reclaim**: price loses VWAP, then closes back above it with volume. The
  people who sold the breakdown are now trapped. Strong intraday long trigger.
- **VWAP rejection**: price rallies into VWAP from below and prints a wick. Strong
  intraday short trigger in a down day.
- **Standard deviation bands** (1 and 2 sigma) around VWAP: the 2 sigma band is a
  common mean-reversion point on range days and a "do not chase" line on trend days.

Anchored VWAP from a significant swing low or high (rather than the session) shows
the average cost of everyone who bought since that low. When price returns to it,
the crowd is at breakeven and tends to defend.

## 3. Momentum: RSI and MACD

**RSI (14)** measures the speed of recent gains against losses on a 0-100 scale.

- **In a range**: above 70 is overbought and below 30 is oversold, and fading these
  at range edges works reasonably.
- **In a trend**: overbought is not a sell signal. In a strong uptrend, RSI lives
  between 40 and 80 and "oversold" is 40. In a strong downtrend it lives between 20
  and 60. Adjust the bands to the regime or RSI will bleed you.
- **RSI 50** acts as the momentum trendline. Holding above 50 on pullbacks confirms
  the uptrend.
- **Divergence** is the useful part. Price makes a higher high but RSI makes a lower
  high: momentum is fading. That is not an entry, it is a warning to tighten
  targets and to look for a structural reversal signal (CHoCH, sweep). Divergences
  on the 1H and 4H are far more reliable than on the 5m.

**MACD (12, 26, 9)** is the difference between two EMAs and its own average.

- The **histogram** shrinking toward zero shows a pullback losing steam; flipping
  sign confirms momentum change. Useful to time the pullback entry in a trend.
- Signal-line crosses lag price badly. Do not trade them directly.
- MACD divergence works like RSI divergence and is slightly slower.

Pick one of these two. They tell you the same thing.

## 4. Volatility: ATR and Bollinger Bands

**ATR (14)**, average true range, is the average candle range including gaps. It is
the most practically useful indicator in this file because it sizes everything:

- **Stop buffer**: place stops beyond the invalidation level by 0.3-0.5 ATR (setup
  timeframe) so a normal wick does not take you out.
- **Sanity check**: a stop smaller than ~0.5 ATR of the timeframe is inside the
  noise. Widen the stop or drop to a lower timeframe.
- **Targets**: a day trade rarely captures more than 1.5-2.5 daily ATRs of movement.
  If the 2R target requires 3 daily ATRs, the plan is unrealistic.
- **Regime**: ATR expanding after a contraction means a new trend leg. ATR at
  multi-week lows means a big move is coming and the direction is unknown.

**Bollinger Bands (20, 2)** are a 20-period SMA with bands two standard deviations
away.

- **Squeeze**: bands at their narrowest in 50-100 candles. Volatility compression.
  Expect expansion; trade the breakout with confirmation (volume, close outside),
  not the first poke.
- **Band walk**: price riding the upper band for many candles is a strong trend.
  Do not fade it. It ends when price closes back inside the band and then fails to
  retake it.
- **Mean reversion**: in a confirmed range, a close outside the band followed by a
  close back inside is a fade signal toward the middle band.

## 5. Participation: volume, relative volume, CVD

**Volume** confirms or denies price. A breakout on below-average volume is suspect.
A sweep on very high volume that closes back inside is absorption.

- **Relative volume (RVOL)**: current candle volume divided by the average of the
  same candle position over recent days, or simply divided by the 20-candle average.
  Breakouts want RVOL above 1.5. `scripts/snapshot.py` reports it.
- **Climax volume**: the largest volume in a long time at the end of an extended
  move usually marks exhaustion, not continuation.
- **Volume dry-up** during a pullback in a trend is healthy: sellers are not
  pressing.

**Cumulative volume delta (CVD)** sums (market buys minus market sells). It shows
who is aggressive.

- Price making a new high while CVD does not: buyers are being absorbed by passive
  sellers (limit orders). Bearish divergence, and more reliable than RSI divergence
  because it is measuring actual orders.
- Price flat while CVD rises steeply: aggressive buyers are being absorbed. Someone
  big is selling into them. Bearish.
- Price sweeping lows while CVD makes a much lower low, then price reclaims: the
  sellers were exhausted into the sweep. Bullish.

CVD needs trade-level data; the bundled scripts do not fetch it. Exchanges and
charting platforms show it. If unavailable, use plain volume and say so.

## 6. Combining them: the four-question model

Choose one indicator per question, and no more:

| Question | Pick one |
|---|---|
| Which way is the trend on the setup timeframe? | EMA stack (21/50/200) |
| Is price at value or stretched? | VWAP, or distance from 21 EMA in ATR |
| Is momentum confirming or diverging? | RSI **or** MACD |
| How big are stops and targets? | ATR |
| Is anyone participating? | RVOL, CVD if available |

A trade needs the first, second, and fourth answered favorably. The third and fifth
are quality filters that move a setup from B to A or from B to "skip".

## 7. What indicators cannot do

- They cannot predict. They describe the recent past.
- They cannot make a counter-trend trade a good trade. RSI at 20 in a downtrend is
  what a downtrend looks like.
- They cannot replace a stop. "RSI is oversold, so it will bounce" is not an
  invalidation.
- More of them does not add information; they are all derived from the same
  price series and will mostly agree with each other, which feels like confirmation
  and is not.

## 8. Quick settings table

| Indicator | Setting | Timeframes | Use |
|---|---|---|---|
| EMA | 9, 21, 50, 200 | all | trend, value, regime |
| VWAP | session (00:00 UTC), plus anchored to key swing | 1m-1H | intraday value, reclaim/reject triggers |
| RSI | 14 | 15m-4H | divergence, regime-adjusted OB/OS |
| MACD | 12, 26, 9 | 15m-4H | pullback exhaustion via histogram |
| ATR | 14 | setup timeframe and 1D | stop buffer, target realism, sizing |
| Bollinger | 20, 2 | 15m-4H | squeeze, band walk, range fades |
| RVOL | 20-candle average | trigger timeframe | breakout validation |
