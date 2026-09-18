# Probability and Prediction

The user will ask "where is BTC going?" and "will SOL pump?". This file is how to
answer those questions truthfully and still be useful. It is the difference between
a fortune teller and a professional.

## Contents

1. Why nobody predicts the next candle
2. What can be estimated
3. Speaking in scenarios, not points
4. Expected value: the only reason to take a trade
5. Base rates worth knowing (rough, verify with the backtester)
6. Updating a view as evidence arrives
7. Calibrating confidence language
8. Answering "what will the price be tomorrow?"
9. Keeping a forecast log

---

## 1. Why nobody predicts the next candle

- **Noise dominates short horizons.** On a 5-minute or 15-minute chart, the expected
  move over the next few candles is close to zero and the standard deviation is
  large. Any directional edge is a few percentage points of probability at best.
- **Fat tails.** Crypto returns have far more extreme moves than a normal
  distribution predicts. A "3-sigma" day happens several times a year. Models that
  assume tidy distributions get liquidated.
- **Reflexivity.** Widely known patterns get traded, which changes them. A level
  everyone sees becomes a liquidity pool, not a support.
- **Regime change.** The relationships (correlations, session behaviors, funding
  norms) drift. What worked in a trending quarter loses in a ranging one.
- **Selection bias in what the user has seen.** Screenshots of calls that worked
  circulate; the ones that failed do not. "This indicator predicted the top" is a
  survivorship story.

The consequence: any confident directional claim about the next hour or day is
unjustified. Saying so is not weakness; it is the first sign of competence.

## 2. What can be estimated

Useful, defensible statements about the future:

- **Volatility**: ATR gives a realistic range for the next N candles. "BTC moves
  about 2,200 a day lately; a 1,500 move by tomorrow would be ordinary."
- **Conditional tendencies**: given a specific structure (a sweep and reclaim of
  equal lows in an uptrend), the frequency of a follow-through move to the next
  level is meaningfully above 50% in most backtests. Still not a certainty.
- **Positioning asymmetry**: with funding extreme and OI high, the *size* of a
  move against the crowd, if one starts, is larger than usual. The direction is
  still not known; the payoff shape is.
- **Time-of-day effects**: volume, volatility, and the probability of a breakout
  are demonstrably higher in the London/New York overlap than in Asia.
- **Event volatility**: a CPI print will move price sharply. The direction is
  unknown until the number is out.

Each of these is about **shape** (how far, how fast, how asymmetric), not about
**direction**. Trading edges come from combining a small directional tilt with a
favorable shape (a 2R+ target against a defined stop).

## 3. Speaking in scenarios, not points

Never give one number. Give a map:

```
BTC · 4H · 2026-09-16 21:00 UTC · price 76,050

Bull case (~40%): holds the 74,900 daily low and reclaims 76,600 (4H 21 EMA / today's high).
  Then the 78,250 PDH is the first magnet, 79,600-79,800 equal highs the second.
Bear case (~35%): loses 74,900 on a 4H close. Then 73,500 (4H 50 EMA) and the 72,200 1D 200 EMA.
Chop (~25%): stays 74,900-76,600 into the US open tomorrow. No trade until it leaves.
Deciding level: 76,600 above, 74,900 below. Everything between is noise for a day trader.
What changes the odds: a 4H close above 76,600 on rising OI moves the bull case to ~55%;
  funding flipping strongly positive without price progress moves the bear case up.
```

The probabilities are rough and they should be. Their job is to communicate lean
and uncertainty, and to force the analyst to admit the chop case exists.

## 4. Expected value: the only reason to take a trade

```
EV (in R) = p_win × R_target − (1 − p_win) × 1 − costs_in_R
```

- A sweep-reversal long with a 2.8R target and an honest 38% win rate:
  0.38 × 2.8 − 0.62 × 1 − 0.1 = **+0.34R**. Take it.
- A "sure thing" breakout chase with a 0.9R target and a generous 60% win rate:
  0.60 × 0.9 − 0.40 × 1 − 0.15 = **−0.01R**. Skip it, however good it feels.

The user's intuition about p_win is almost always too high. The journal's actual
win rate per playbook is the number to use. Until there are 50 trades, use the
conservative end of the ranges in `playbooks.md` (35-50%).

## 5. Base rates worth knowing (rough, verify with the backtester)

These are approximate tendencies widely observed in BTC/ETH over recent years. They
are inputs to a prior, not facts. Run `scripts/backtest.py` or check the journal
before leaning on any of them.

- Most days are **range days**. Trend days (close near the high or low with a wide
  range) are the minority, roughly a quarter to a third of days. Default to range
  tactics until the market proves a trend day is underway.
- The **day's high or low is frequently set in the first few hours** after the
  00:00 UTC open or around the London/New York opens. Once both a London and New
  York attempt in one direction have failed, the other extreme tends to hold.
- The **first breakout of the Asia range** during London fails and reverses more
  often than it follows through. Waiting for the retest costs some winners and
  avoids many losers.
- **Equal highs/lows get swept** before a reversal far more often than they hold on
  the first touch.
- **Funding extremes persist** in trends. Fading them without a structural rejection
  is a losing base rate.
- **Weekend moves retrace** at a higher rate than weekday moves (thin books, CME gap
  fill tendency).
- **Round-number levels** (10k multiples on BTC, 100s on ETH) see more wicks and
  more reversals than random levels, because retail orders cluster there.
- **After a liquidation cascade**, the first sharp bounce is usually sold, and the
  durable low comes after a retest or a higher low, not at the cascade wick.

## 6. Updating a view as evidence arrives

Think in a simple Bayesian loop:

1. **Prior** from the higher timeframe. In a 1D uptrend, the prior for "the next
   4H swing resolves up" might be ~55%.
2. **Evidence** from the setup timeframe. A sweep of the 1H equal lows that closes
   back inside on 2x volume is evidence for the up case; maybe it lifts the
   probability to ~60-65%.
3. **Disconfirming evidence** counts too. OI rising while price fails to make
   progress, or CVD diverging, pulls it back down.
4. **Decision** = probability × payoff, not probability alone. 60% with a 2.5R
   target is a great trade. 60% with a 0.8R target is not.
5. **Invalidation** is the pre-committed point where the evidence has proven the
   view wrong, and the stop is there. Do not "update" a stop wider because the
   view feels right.

## 7. Calibrating confidence language

Use these words consistently so the user learns what they mean:

| Word | Rough probability the trade direction is right on this horizon | When to use |
|---|---|---|
| **low** | 35-45% | B setup, counter-trend, thin data, weekend |
| **medium** | 45-55% | aligned bias and location but an ordinary trigger |
| **high** | 55-65% | A setup: HTF alignment, structural location, confirmed trigger, positioning tailwind |

Nothing above "high". A day trader with a true 65% win rate on 2R setups would
compound absurdly; claiming more is a sign the analysis is wrong. Note that a
"low" confidence 3R sweep-reversal trade can still have positive expectancy and
be worth taking at reduced size.

Words to avoid: "will", "guaranteed", "definitely", "can't lose", "free money",
"about to". Words to use: "leans", "favors", "if X then Y", "the odds tilt",
"the payoff is asymmetric", "unknown until".

## 8. Answering "what will the price be tomorrow?"

Give a cone, then the lean, then the caveat.

> BTC is 76,050 and has been moving about 2,200 a day (14-day ATR). So by this time
> tomorrow, something between 73,900 and 78,200 is the ordinary outcome, and a move
> beyond that would need a catalyst. Structure leans slightly up on the daily
> (higher lows since late August) but the 4H is mid-range, so I would call it
> 55/45 up over that window, which is close to a coin flip. The useful question is
> not where it will be but what to do at 74,900 and at 76,600, and the plan for
> both is [...].

If the user pushes for a single number, give the current price. It is the best
unbiased point forecast for a short horizon, and saying so teaches something.

## 9. Keeping a forecast log

If the user wants to get better at reading markets, have them log every stated
probability and what happened. Over 50+ forecasts, compare: of the calls made at
"60%", did about 60% resolve that way? Consistently higher means underconfidence;
consistently lower (the common case) means overconfidence, and the fix is to
shade every probability toward 50% until the log says otherwise.

A simple score: for each forecast, (probability − outcome)² where outcome is 1 or
0. Average it. Lower is better; 0.25 is what pure coin-flipping scores. A day
trader who beats 0.24 on directional calls is doing well.
