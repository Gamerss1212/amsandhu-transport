# Can $100 become $300,000?

**No software can promise that, and this one does not.** A program that says it can is not real. This page shows the
arithmetic and the measured results, so you can check them yourself.

## The arithmetic (no forecast, just maths)

$100 to $300,000 is **3,000 times** the money. To get there by compounding, you must earn this *every month*, with no
losing month:

| Time allowed | Return needed every month | Return needed every year |
|---|---|---|
| 1 year | 94.9% | 299,900% |
| 2 years | 39.6% | 5,377% |
| 3 years | 24.9% | 1,342% |
| 5 years | 14.3% | 396% |
| 10 years | 6.9% | 123% |
| 20 years | 3.4% | 49% |

For comparison, steady growth of 2% a month turns $100 into about $328 after 5 years and $1,077 after 10 years.
5% a month (which nobody has shown they can keep up) gives $1,868 and $34,891. These are what-if calculations, not
predictions.

## What this software has actually measured (real data, all costs included)

* The 100 trading agents were trained on real market data. **0 of 100 passed the research gate**, so none is allowed to
  trade, even in paper (`AGENT_TRAINING_REPORT.md`).
* A walk-forward test of the combined portfolio over 627 days came out **negative**: -33.1% if every agent traded,
  -3.7% with the gate that skips losing folds. Buying and holding SPY made +32.4% over the same period
  (`PORTFOLIO_BACKTEST_REPORT.md`).
* Before costs the agents made 233,101; costs (fees, slippage, spread) were 2,070,241, which is 8.9 times as much.
* The earlier research behind the Jarvus skill tested 72 configurations on 7.7 years of Bitcoin data: **none was
  profitable at normal retail taker fees**.

## What a $100 account means in this program

The risk limits are plain code and the AI cannot change them. At $100 they allow at most **$10 per order**, **$25 in one
position**, and a **$3 loss in a day** (10%, 25% and 3% of equity). Fees and minimum order sizes take a larger share of
a small order, so a small account is hurt *more* by costs, not less.

## What the program does do

* Runs with any balance from $100 up, in paper mode, with real prices and real costs. Paper results are simulated.
* Keeps you in cash unless an agent has proved itself on data it never saw. Today none has.
* Shows what it measured, including the losses.

## What would have to be true before real money

1. An agent passes the research gate on its own market.
2. It makes money in **paper** trading for months, after costs.
3. You connect a broker yourself and arm live trading in a separate step. Nothing here turns that on.

Even then, expect small numbers, and expect to be able to lose what you put in. Only risk money you can afford to lose.
