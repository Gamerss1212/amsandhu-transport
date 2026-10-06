# Volatility-targeting overlay on equal-weight buy-and-hold (A16 family)

Status: **pre-registered** in `docs/research/preregistration.md`, run once on 2026-10-06 with
`python -m quantagents validate --strategy vol_target --data <csv>`.

## 1. Hypothesis and economic reason

Volatility clusters and is forecastable while returns are not. So scaling exposure down
when recent volatility is high should improve risk-adjusted returns (Moreira-Muir 2017;
Harvey et al. 2018). Book: equal-weight 8 ETFs, scaled to 10% (primary) or 15% annual
volatility, never above 1x.

## 2. Data used and its limits

data/multi_asset.csv (hash 19e95947f2a0), trading 2007-02-20 to 2026-10-05.

Yahoo daily bars, adjusted for splits and dividends. Downloaded 2026-10-06 into the
append-only store and exported with `quantagents data export`.
- **Caveats:** survivorship-biased (upper bound only) and not point-in-time.
- **Survivorship:** every ETF used still exists today, so funds that closed are missing.
- **Data drift:** Yahoo restates history, so a later download may hash differently.
- **Costs:** 0.15% one way (10 bp fee + 5 bp slippage), fills at the next open.
- **Engine:** vectorized A43.

## 3. Variants tried and trial count

2: vt10_hold (primary), vt15_hold. 2 trials charged. The grid was fixed before the run. Every row is in `docs/research/trials.md`.

## 4. A44 table, A39 findings and the 2x-cost result (tool output, verbatim)

```
Backtest: vt10_hold (2007-02-20 to 2026-10-05)
Costs: 0.15% per unit traded (fees + slippage), fills at the next open
Total return +169.31% | CAGR +5.19% | volatility 9.69%
Sharpe 0.57 | max drawdown 23.63% | avg daily turnover 0.002 | invested on 100% of days

A44 validation: vt10_hold -> FAIL
---------------------------------
[PASS] observations: 4937 days (need 252)
[FAIL] newey_west_t: t = 2.70 (need 3)
[PASS] psr: PSR = 0.994 (need 0.95)
[PASS] dsr: DSR = 0.976 after 2 trial(s) (need 0.95)
[FAIL] pbo: PBO = 0.31 (need <= 0.2)
[PASS] sharpe_at_2x_costs: Sharpe at 2x costs = 0.56 (need > 0)
[PASS] spa: Hansen SPA p = 0.004 over 2 variant(s) vs cash (White RC form 0.004; need <= 0.05)
[PASS] walk_forward: 16 folds: mean out-of-sample Sharpe 0.80, OOS/IS 1.41 (need > 0 and >= 0.5)
Sharpe 0.57 (95% bootstrap interval 0.19 to 1.00)
Walk-forward folds (best in-sample variant, then the next unseen year):
  days 756-1007: vt15_hold in-sample Sharpe 0.30 -> out-of-sample 1.61
  days 1008-1259: vt15_hold in-sample Sharpe 0.46 -> out-of-sample 0.76
  days 1260-1511: vt15_hold in-sample Sharpe 1.37 -> out-of-sample 0.54
  days 1512-1763: vt15_hold in-sample Sharpe 0.99 -> out-of-sample 0.21
  days 1764-2015: vt15_hold in-sample Sharpe 0.52 -> out-of-sample 0.63
  days 2016-2267: vt15_hold in-sample Sharpe 0.43 -> out-of-sample -0.91
  days 2268-2519: vt15_hold in-sample Sharpe -0.12 -> out-of-sample 1.63
  days 2520-2771: vt15_hold in-sample Sharpe 0.33 -> out-of-sample 1.32
  days 2772-3023: vt15_hold in-sample Sharpe 0.51 -> out-of-sample 0.34
  days 3024-3275: vt15_hold in-sample Sharpe 1.08 -> out-of-sample 1.73
  days 3276-3527: vt15_hold in-sample Sharpe 1.06 -> out-of-sample 0.51
  days 3528-3779: vt15_hold in-sample Sharpe 0.65 -> out-of-sample 0.70
  days 3780-4031: vt15_hold in-sample Sharpe 0.73 -> out-of-sample -0.62
  days 4032-4283: vt15_hold in-sample Sharpe 0.14 -> out-of-sample 0.90
  days 4284-4535: vt10_hold in-sample Sharpe 0.20 -> out-of-sample 1.54
  days 4536-4787: vt10_hold in-sample Sharpe 0.45 -> out-of-sample 1.92
By market volatility (trailing 63 days; descriptive only):
  low vol   1625 days: +5.0% a year, Sharpe 0.70
  mid vol   1624 days: +3.7% a year, Sharpe 0.39
  high vol  1625 days: +7.9% a year, Sharpe 0.67
Note: 2 variant(s) run now; 2 trial(s) charged to this family (every variant ever run on real data counts).

A39 red team: vt10_hold -> PASS
-------------------------------
Tests: future_perturbation, determinism, bounds, time_shift
No findings.
```

## 5. Verdict

**FAIL.** Newey-West t 2.70 (needs 3.0) and PBO 0.31 (limit 0.20).

- **Return and risk:** Sharpe 0.57 is the same as plain buy-and-hold (0.58). Return was
  +5.19% a year against +6.69%. Max drawdown 23.6% against 37.2%. Here the overlay cut risk
  and return about equally: it did not improve risk-adjusted returns.
- **What would change it:** evidence on a longer or broader sample. Note that capping at 1x
  limits the overlay to scaling down, never up.
