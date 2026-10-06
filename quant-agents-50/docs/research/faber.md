# Faber 10-month moving-average timing (A11 family)

Status: **pre-registered** in `docs/research/preregistration.md`, run once on 2026-10-06 with
`python -m quantagents validate --strategy faber --data <csv>`.

## 1. Hypothesis and economic reason

Hold an asset only while it is above its 10-month average. This sidesteps the worst of
long bear markets, at the cost of whipsaws (Faber 2007). Same economics as trend following:
under-reaction, then herding.

## 2. Data used and its limits

data/multi_asset.csv (hash 19e95947f2a0): SPY EFA EEM TLT IEF GLD DBC VNQ, trading 2007-02-20 to 2026-10-05.

Yahoo daily bars, adjusted for splits and dividends. Downloaded 2026-10-06 into the
append-only store and exported with `quantagents data export`.
- **Caveats:** survivorship-biased (upper bound only) and not point-in-time.
- **Survivorship:** every ETF used still exists today, so funds that closed are missing.
- **Data drift:** Yahoo restates history, so a later download may hash differently.
- **Costs:** 0.15% one way (10 bp fee + 5 bp slippage), fills at the next open.
- **Engine:** vectorized A43.

## 3. Variants tried and trial count

3: faber_10m (primary), faber_8m, faber_12m. 3 trials charged. The grid was fixed before the run. Every row is in `docs/research/trials.md`.

## 4. A44 table, A39 findings and the 2x-cost result (tool output, verbatim)

```
Backtest: faber_10m (2007-02-20 to 2026-10-05)
Costs: 0.15% per unit traded (fees + slippage), fills at the next open
Total return +138.06% | CAGR +4.53% | volatility 7.37%
Sharpe 0.64 | max drawdown 13.26% | avg daily turnover 0.008 | invested on 99% of days

A44 validation: faber_10m -> FAIL
---------------------------------
[PASS] observations: 4937 days (need 252)
[PASS] newey_west_t: t = 3.16 (need 3)
[PASS] psr: PSR = 0.997 (need 0.95)
[PASS] dsr: DSR = 0.975 after 3 trial(s) (need 0.95)
[FAIL] pbo: PBO = 0.91 (need <= 0.2)
[PASS] sharpe_at_2x_costs: Sharpe at 2x costs = 0.60 (need > 0)
[PASS] spa: Hansen SPA p = 0.002 over 3 variant(s) vs cash (White RC form 0.002; need <= 0.05)
[PASS] walk_forward: 16 folds: mean out-of-sample Sharpe 0.52, OOS/IS 0.85 (need > 0 and >= 0.5)
Sharpe 0.64 (95% bootstrap interval 0.25 to 1.01)
Walk-forward folds (best in-sample variant, then the next unseen year):
  days 756-1007: faber_12m in-sample Sharpe 0.82 -> out-of-sample 0.97
  days 1008-1259: faber_12m in-sample Sharpe 0.70 -> out-of-sample -0.06
  days 1260-1511: faber_8m in-sample Sharpe 0.87 -> out-of-sample -0.47
  days 1512-1763: faber_8m in-sample Sharpe 0.54 -> out-of-sample -0.05
  days 1764-2015: faber_12m in-sample Sharpe 0.14 -> out-of-sample 1.30
  days 2016-2267: faber_12m in-sample Sharpe 0.62 -> out-of-sample -1.56
  days 2268-2519: faber_10m in-sample Sharpe 0.00 -> out-of-sample 0.91
  days 2520-2771: faber_10m in-sample Sharpe 0.34 -> out-of-sample 1.26
  days 2772-3023: faber_8m in-sample Sharpe 0.53 -> out-of-sample -0.30
  days 3024-3275: faber_8m in-sample Sharpe 0.72 -> out-of-sample 1.08
  days 3276-3527: faber_8m in-sample Sharpe 0.81 -> out-of-sample 1.96
  days 3528-3779: faber_8m in-sample Sharpe 1.11 -> out-of-sample 0.64
  days 3780-4031: faber_8m in-sample Sharpe 1.27 -> out-of-sample -0.91
  days 4032-4283: faber_8m in-sample Sharpe 0.77 -> out-of-sample 0.22
  days 4284-4535: faber_12m in-sample Sharpe 0.12 -> out-of-sample 1.30
  days 4536-4787: faber_12m in-sample Sharpe 0.45 -> out-of-sample 2.07
By market volatility (trailing 63 days; descriptive only):
  low vol   1625 days: +4.4% a year, Sharpe 0.74
  mid vol   1624 days: +3.1% a year, Sharpe 0.45
  high vol  1625 days: +6.6% a year, Sharpe 0.75
Note: 3 variant(s) run now; 3 trial(s) charged to this family (every variant ever run on real data counts).

A39 red team: faber_10m -> PASS
-------------------------------
Tests: future_perturbation, determinism, bounds, time_shift
No findings.
```

## 5. Verdict

**FAIL.** Every check passes except PBO (0.91, limit 0.20).

- **Return and risk:** Sharpe 0.64 against 0.58 for buy-and-hold. Max drawdown 13.3% against
  37.2%. Return +4.53% a year against +6.69%.
- **Neighbours:** 8- and 12-month neighbours gave Sharpe 0.67 and 0.66. The result does not
  hinge on the 10-month choice, but PBO cannot tell the three apart (same reason as
  tsmom_blend).
- **What would change it:** the same as tsmom_blend.
