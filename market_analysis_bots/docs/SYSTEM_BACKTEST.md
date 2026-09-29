# Full-system backtest

Generated 2026-09-29 06:25 UTC by `tools/system_backtest.py`. **1,000 runs x 3 arms = 3,000 simulations** of the whole fleet: each run replays 60 randomly chosen bots over a random 10-day window between 2026-06-07 and 2026-09-29 (13,092 candidate trades from 281 bots), with per-venue fees and slippage, account sizing (0.5% of a 1/20 slot per trade), at most 40 open positions and a 3% daily loss halt. The brain's starting knowledge comes only from the training segment that precedes these windows.

| Arm | What runs | Mean return per window | Median | 5th-95th percentile | Windows positive | Mean max drawdown | Trades per window | Win rate | Avg R |
|---|---|---|---|---|---|---|---|---|---|
| none | every signal, full size | -12.348% | -3.395% | -30.56% to -0.18% | 0% | 12.36% | 131 | 9.4% | -3.562 |
| gates | cost + volatility gates | -0.119% | +0.000% | -0.66% to +0.00% | 6% | 0.17% | 39 | 40.0% | -0.128 |
| brain | gates + learned brain | -0.022% | +0.000% | -0.19% to +0.05% | 9% | 0.05% | 6 | 38.2% | -0.131 |

## Does the brain help? (paired: same window, same bots)

| Comparison | Mean difference in return | 95% bootstrap interval | Windows where the first is better |
|---|---|---|---|
| gates vs none | +12.230% | +11.460% to +13.048% | 98% |
| brain vs none | +12.327% | +11.555% to +13.125% | 98% |
| brain vs gates only | +0.097% | +0.084% to +0.112% | 29% |
| drawdown: none minus brain | +12.318% | +11.526% to +13.115% | 98% (brain shallower) |

## What the blocked trades would have made

Counted across all runs (a trade blocked in several runs counts each time).

| Veto reason | Blocked trades | Their average result |
|---|---|---|
| cost | 179,552 | -2.208R |
| learned | 13,508 | -0.187R |
| benched | 19,029 | -0.128R |
| quiet | 5,527 | -0.200R |

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
