# 12-1 cross-sectional momentum on US sectors (A12 family)

Status: **pre-registered** in `docs/research/preregistration.md`, run once on 2026-10-06 with
`python -m quantagents validate --strategy xs_mom --data <csv>`.

## 1. Hypothesis and economic reason

Sectors with the best returns from 12 months ago to 1 month ago keep outperforming for a
few months (Jegadeesh-Titman 1993; Moskowitz-Grinblatt 1999 for industries). The cause is
slow diffusion of information. The trend-filter variant steps aside when the market is
below its 200-day average, to avoid momentum crashes (Daniel-Moskowitz 2016).

## 2. Data used and its limits

data/sectors.csv (hash 96aa159115e7): XLB XLE XLF XLI XLK XLP XLU XLV XLY, 1998-12-22 to 2026-10-05 (trading from 2000-01-04).

Yahoo daily bars, adjusted for splits and dividends. Downloaded 2026-10-06 into the
append-only store and exported with `quantagents data export`.
- **Caveats:** survivorship-biased (upper bound only) and not point-in-time.
- **Survivorship:** every ETF used still exists today, so funds that closed are missing.
- **Data drift:** Yahoo restates history, so a later download may hash differently.
- **Costs:** 0.15% one way (10 bp fee + 5 bp slippage), fills at the next open.
- **Engine:** vectorized A43.

## 3. Variants tried and trial count

2: xsmom_12_1 (primary), xsmom_12_1_trend. 2 trials charged. The grid was fixed before the run. Every row is in `docs/research/trials.md`.

## 4. A44 table, A39 findings and the 2x-cost result (tool output, verbatim)

```
Backtest: xsmom_12_1 (2000-01-04 to 2026-10-05)
Costs: 0.15% per unit traded (fees + slippage), fills at the next open
Total return +1158.28% | CAGR +9.95% | volatility 18.74%
Sharpe 0.60 | max drawdown 44.88% | avg daily turnover 0.020 | invested on 100% of days

A44 validation: xsmom_12_1 -> FAIL
----------------------------------
[PASS] observations: 6727 days (need 252)
[PASS] newey_west_t: t = 3.56 (need 3)
[PASS] psr: PSR = 0.999 (need 0.95)
[PASS] dsr: DSR = 0.995 after 2 trial(s) (need 0.95)
[FAIL] pbo: PBO = 0.93 (need <= 0.2)
[PASS] sharpe_at_2x_costs: Sharpe at 2x costs = 0.56 (need > 0)
[PASS] spa: Hansen SPA p = 0.000 over 2 variant(s) vs cash (White RC form 0.000; need <= 0.05)
[PASS] walk_forward: 23 folds: mean out-of-sample Sharpe 0.90, OOS/IS 1.17 (need > 0 and >= 0.5)
Sharpe 0.60 (95% bootstrap interval 0.26 to 1.00)
Walk-forward folds (best in-sample variant, then the next unseen year):
  days 756-1007: xsmom_12_1 in-sample Sharpe -0.10 -> out-of-sample 1.35
  days 1008-1259: xsmom_12_1_trend in-sample Sharpe 0.55 -> out-of-sample 0.61
  days 1260-1511: xsmom_12_1_trend in-sample Sharpe 0.85 -> out-of-sample 1.65
  days 1512-1763: xsmom_12_1_trend in-sample Sharpe 1.36 -> out-of-sample 0.06
  days 1764-2015: xsmom_12_1 in-sample Sharpe 0.79 -> out-of-sample 0.80
  days 2016-2267: xsmom_12_1_trend in-sample Sharpe 0.88 -> out-of-sample 0.75
  days 2268-2519: xsmom_12_1_trend in-sample Sharpe 0.52 -> out-of-sample 1.90
  days 2520-2771: xsmom_12_1_trend in-sample Sharpe 1.10 -> out-of-sample 0.41
  days 2772-3023: xsmom_12_1_trend in-sample Sharpe 0.89 -> out-of-sample -0.21
  days 3024-3275: xsmom_12_1 in-sample Sharpe 0.77 -> out-of-sample 1.02
  days 3276-3527: xsmom_12_1 in-sample Sharpe 0.63 -> out-of-sample 2.42
  days 3528-3779: xsmom_12_1 in-sample Sharpe 0.94 -> out-of-sample 0.95
  days 3780-4031: xsmom_12_1 in-sample Sharpe 1.46 -> out-of-sample -0.28
  days 4032-4283: xsmom_12_1 in-sample Sharpe 0.89 -> out-of-sample 1.19
  days 4284-4535: xsmom_12_1 in-sample Sharpe 0.53 -> out-of-sample 1.71
  days 4536-4787: xsmom_12_1 in-sample Sharpe 0.67 -> out-of-sample -0.35
  days 4788-5039: xsmom_12_1 in-sample Sharpe 0.53 -> out-of-sample 2.28
  days 5040-5291: xsmom_12_1 in-sample Sharpe 0.76 -> out-of-sample 0.54
  days 5292-5543: xsmom_12_1 in-sample Sharpe 0.49 -> out-of-sample 1.23
  days 5544-5795: xsmom_12_1_trend in-sample Sharpe 0.94 -> out-of-sample -0.09
  days 5796-6047: xsmom_12_1 in-sample Sharpe 0.66 -> out-of-sample 0.68
  days 6048-6299: xsmom_12_1 in-sample Sharpe 0.78 -> out-of-sample 1.33
  days 6300-6551: xsmom_12_1 in-sample Sharpe 0.76 -> out-of-sample 0.79
By market volatility (trailing 63 days; descriptive only):
  low vol   2222 days: +3.2% a year, Sharpe 0.24
  mid vol   2221 days: +16.5% a year, Sharpe 1.04
  high vol  2221 days: +13.5% a year, Sharpe 0.54
Note: 2 variant(s) run now; 2 trial(s) charged to this family (every variant ever run on real data counts).

A39 red team: xsmom_12_1 -> PASS
--------------------------------
Tests: future_perturbation, determinism, bounds, time_shift
No findings.
```

## 5. Verdict

**FAIL.** Every check passes except PBO (0.93, limit 0.20).

- **Return and risk:** Sharpe 0.60 against 0.58 for equal-weight buy-and-hold of the 9
  sectors. Return +9.95% a year against +9.33%. Max drawdown 44.9% against 52.2%. That is
  barely different from just holding all the sectors.
- **What would change it:** a clear margin over buy-and-hold on new data, not just over cash.
