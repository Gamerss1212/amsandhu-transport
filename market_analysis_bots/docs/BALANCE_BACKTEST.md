# Does it work with any balance?

The full system (brain arm) replayed on 400 random 10-day windows with 60 bots each, at several starting balances, with order sizes modelled as the engine places them: venue minimum orders, whole shares for stocks unless fractional, the cash a spot account has, 20 open positions at most. Fee level: venue. Generated 2026-09-30 21:00 UTC.

* **before**: 20 fixed capital slots, whole shares only.
* **after**: adaptive slots (at least $25 each), fractional US shares ($1 minimum, as Alpaca offers), entries capped at 5% of the market's recent dollar volume.

| Balance | Version | Trades per window | Refused as too small | Refused, no cash | Capped by liquidity | Mean return | Windows positive |
|---|---|---|---|---|---|---|---|
| $100 | before | 0.06 | 4.71 | 0.00 | 0.00 | -0.0003% | 1.2% |
| $100 | after | 3.83 | 0.77 | 0.01 | 0.00 | -0.0775% | 7.2% |
| $1,000 | before | 0.79 | 3.95 | 0.00 | 0.00 | -0.0002% | 9.0% |
| $1,000 | after | 4.29 | 0.31 | 0.00 | 0.00 | -0.0098% | 13.0% |
| $10,000 | before | 3.13 | 1.47 | 0.00 | 0.00 | -0.0079% | 12.5% |
| $10,000 | after | 4.51 | 0.02 | 0.00 | 0.00 | -0.0116% | 12.5% |
| $100,000 | before | 4.54 | 0.00 | 0.00 | 0.00 | -0.0120% | 12.5% |
| $100,000 | after | 4.54 | 0.00 | 0.00 | 0.00 | -0.0124% | 12.2% |
| $10,000,000 | before | 4.54 | 0.00 | 0.00 | 0.00 | -0.0124% | 12.2% |
| $10,000,000 | after | 4.54 | 0.00 | 0.00 | 0.76 | -0.0105% | 14.2% |

Returns are percentages of the starting balance; they are simulations of past data, not a forecast.

## What this shows

* **The problem was real.** With the old rule (20 fixed capital slots), a $100 account sized each trade from a $5
  slot: about 99% of the trades the brain approved were refused as below the exchange's minimum order, so it
  placed 0.06 trades per 10 days. At $1,000 it was 0.79; at $10,000, 3.13 (stocks need whole shares).
* **The fix** is in the engine: an account uses fewer, larger slots when it is small (at least $25 each; all 20
  from $500 up), the AI's paper account may buy fractions of US shares ($1 minimum, as US brokers like Alpaca
  allow), and an entry is capped at 5% of the market's recent volume so a huge balance cannot buy more than the
  market trades. From $100 to $100,000 the AI now places 3.8 to 4.5 trades per window with almost nothing refused
  as too small; at $10,000,000 the volume cap trims about 0.8 orders per window.
* **Returns are not the point.** They are tiny and negative at the fee level used (each bot's own exchange),
  as in the system backtest: the average approved trade is slightly negative after fees. Nothing here says the
  AI makes money at any balance.

### Two ways to fix small balances, compared (400 windows, same bots, paired)

| Balance | Adaptive slots (shipped) | Raise small orders to the venue minimum | Difference (paired, 95% interval) |
|---|---|---|---|
| $100 | -0.0775% | -0.0223% | +0.0552% [+0.0359, +0.0764] for the second |
| $1,000 | -0.0098% | -0.0098% | 0 |
| $100,000 | -0.0124% | -0.0124% | 0 |

At $100 the second approach loses less, and the difference is not noise. It is not a better method, though:
raising an order above the size its risk rule allows bets more than the rule says, and it loses less only because
it bets *less* in total (the slots stay tiny) while the average trade is negative. When the average trade is
negative, smaller bets always look better. The shipped rule never takes more risk than the rule allows, so that
is the one used. The honest reading: at $100 the result is dominated by fees and minimum order sizes, whatever
the sizing rule.

## At each fee level (the goal calculator's inputs)

The same replay ("after" engine, 400 windows of 10 days, 2026-06-09 to 2026-09-30) at every fee level the app
offers, generated 2026-10-01 by `tools/balance_backtest.py --fee-profile <level> --versions after` and collected by
`tools/extract_projection_inputs.py` into `results/projection_inputs.json`. Mean return per 10-day window, with a
bootstrap 95% interval:

| Balance | Each bot's own exchange | Coinbase | Kraken Pro | NDAX | Low-fee (0.10%/0.08%) |
|---|---|---|---|---|---|
| $100 | -0.078% [-0.103, -0.054] | -0.074% [-0.099, -0.051] | -0.024% [-0.057, +0.008] | +0.074% [+0.007, +0.145] | +0.116% [+0.020, +0.218] |
| $1,000 | -0.010% [-0.014, -0.006] | -0.009% [-0.013, -0.005] | -0.000% [-0.006, +0.006] | +0.015% [+0.003, +0.027] | +0.022% [+0.005, +0.040] |
| $10,000 | -0.012% [-0.016, -0.007] | -0.011% [-0.015, -0.007] | -0.002% [-0.009, +0.004] | +0.013% [+0.001, +0.025] | +0.020% [+0.003, +0.038] |
| $100,000 | -0.012% [-0.017, -0.008] | -0.012% [-0.016, -0.007] | -0.003% [-0.009, +0.003] | +0.011% [-0.000, +0.024] | +0.023% [+0.008, +0.039] |
| $10,000,000 | -0.011% [-0.015, -0.007] | -0.010% [-0.014, -0.006] | -0.008% [-0.013, -0.004] | -0.007% [-0.013, -0.001] | -0.003% [-0.009, +0.003] |
| trades per window | 3.8 to 4.5 | 3.6 to 4.3 | 4.6 to 5.1 | 8.8 to 9.1 | 13.1 to 13.4 |

**How to read it.** Lower fees let the brain approve more trades (13 per window at 0.10% instead of 4 at each
exchange's own fees) and move the average from slightly negative to slightly positive. Do not read the positive
cells as an edge:

* the amounts are tiny: +0.074% per 10 days on $100 is about 7 cents;
* the intervals are too narrow. The 400 windows start on only about 100 different days of one three-month period,
  so they overlap heavily; there are roughly ten independent 10-day stretches in it, not 400;
* another sample of the same period at NDAX fees (the brain experiments, `BRAIN_EXPERIMENTS.md`) gave the current
  brain -0.004% and -0.010% per window at $10,000, the opposite sign. Results this close to zero flip with the
  sample;
* at $10,000,000 the 5% volume cap trims the larger orders and every fee level is slightly negative.

So: at a low-fee exchange the system is about break-even, at each exchange's own fees it loses slowly, and at no
fee level does it show a reliable profit. The goal calculator replays exactly these window results, so what it
shows can never be better than this table.

