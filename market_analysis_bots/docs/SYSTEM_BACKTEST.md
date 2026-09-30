# Full-system backtest

Generated 2026-09-30 18:56 UTC by `tools/system_backtest.py`. **1,000 runs x 3 arms = 3,000 simulations** of the whole fleet: each run replays 60 randomly chosen bots over a random 10-day window between 2026-06-09 and 2026-09-30 (13,104 candidate trades from 296 bots), with per-venue fees and slippage, account sizing (0.5% of a 1/20 slot per trade), at most 40 open positions and a 3% daily loss halt. The brain's starting knowledge comes only from the training segment that precedes these windows.

| Arm | What runs | Mean return per window | Median | 5th-95th percentile | Windows positive | Mean max drawdown | Trades per window | Win rate | Avg R |
|---|---|---|---|---|---|---|---|---|---|
| none | every signal, full size | -12.124% | -3.053% | -30.72% to -0.14% | 0% | 12.15% | 137 | 10.5% | -3.280 |
| gates | cost + volatility gates | -0.107% | +0.000% | -0.69% to +0.02% | 8% | 0.15% | 33 | 37.8% | -0.130 |
| brain | gates + learned brain | -0.018% | +0.000% | -0.16% to +0.04% | 13% | 0.04% | 5 | 40.8% | -0.007 |

## Does the brain help? (paired: same window, same bots)

| Comparison | Mean difference in return | 95% bootstrap interval | Windows where the first is better |
|---|---|---|---|
| gates vs none | +12.016% | +11.254% to +12.786% | 97% |
| brain vs none | +12.105% | +11.311% to +12.893% | 97% |
| brain vs gates only | +0.089% | +0.076% to +0.102% | 33% |
| drawdown: none minus brain | +12.107% | +11.315% to +12.825% | 98% (brain shallower) |

## What the blocked trades would have made

Counted across all runs (a trade blocked in several runs counts each time).

| Veto reason | Blocked trades | Their average result |
|---|---|---|
| cost | 172,746 | -2.155R |
| learned | 12,049 | -0.179R |
| benched | 16,146 | -0.143R |
| quiet | 3,464 | -0.164R |

A negative average means the vetoes avoided losing trades.

## Reading

The gates and the brain make the software lose far less than trading every signal, mostly by refusing trades whose costs are larger than their expected edge. They do not turn it into a money maker: the mean window return stays at or below zero in every arm. That matches the strategy tests, where nothing survived the correction for the number of ideas tried.

## Limits

- Candidate trades come from each bot's own unfiltered backtest: when a trade is vetoed, the bot does not get the other entries it might have taken while flat.
- Kraken and OKX bots use Coinbase price history with their own venue's fees.
- Consensus between bots is not modelled here (it is live).
- Paper simulation: fills are modelled, not real; stock fills have no order book.
- The windows cover a few weeks of recent history; a different market period can give a different answer.

- 1 bots had no historical data here and were left out.
