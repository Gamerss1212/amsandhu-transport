# Full-system backtest

Generated 2026-09-29 22:10 UTC by `tools/system_backtest.py`. **1,000 runs x 3 arms = 3,000 simulations** of the whole fleet: each run replays 60 randomly chosen bots over a random 10-day window between 2026-06-07 and 2026-09-29 (13,245 candidate trades from 296 bots), with per-venue fees and slippage, account sizing (0.5% of a 1/20 slot per trade), at most 40 open positions and a 3% daily loss halt. The brain's starting knowledge comes only from the training segment that precedes these windows.

| Arm | What runs | Mean return per window | Median | 5th-95th percentile | Windows positive | Mean max drawdown | Trades per window | Win rate | Avg R |
|---|---|---|---|---|---|---|---|---|---|
| none | every signal, full size | -12.048% | -3.222% | -30.48% to -0.14% | 0% | 12.07% | 133 | 10.8% | -3.390 |
| gates | cost + volatility gates | -0.105% | +0.000% | -0.68% to +0.03% | 8% | 0.16% | 37 | 38.4% | -0.135 |
| brain | gates + learned brain | -0.020% | +0.000% | -0.18% to +0.06% | 13% | 0.05% | 6 | 41.8% | -0.016 |

## Does the brain help? (paired: same window, same bots)

| Comparison | Mean difference in return | 95% bootstrap interval | Windows where the first is better |
|---|---|---|---|
| gates vs none | +11.942% | +11.176% to +12.709% | 98% |
| brain vs none | +12.028% | +11.246% to +12.815% | 98% |
| brain vs gates only | +0.086% | +0.073% to +0.098% | 31% |
| drawdown: none minus brain | +12.024% | +11.245% to +12.724% | 98% (brain shallower) |

## What the blocked trades would have made

Counted across all runs (a trade blocked in several runs counts each time).

| Veto reason | Blocked trades | Their average result |
|---|---|---|
| cost | 172,278 | -2.173R |
| learned | 12,813 | -0.174R |
| benched | 17,506 | -0.123R |
| quiet | 4,919 | -0.209R |

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
