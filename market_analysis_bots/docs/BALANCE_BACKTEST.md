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
