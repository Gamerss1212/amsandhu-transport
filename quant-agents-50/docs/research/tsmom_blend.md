# Time-series momentum, 1/3/12-month blend (A11 family)

Status: **pre-registered** in `docs/research/preregistration.md`, run once on 2026-10-06 with
`python -m quantagents validate --strategy tsmom_blend --data <csv>`.

## 1. Hypothesis and economic reason

Assets that have risen over the last 1, 3 and 12 months tend to keep rising for a while.
Investors under-react to news, then chase it, and hedgers pay trend followers for insurance
(Moskowitz-Ooi-Pedersen 2012; Hurst-Ooi-Pedersen 2017). Long-only form: weight each asset by
the share of its three lookbacks that are positive. Vol-scaled form: cap each asset's risk at
10% a year.

## 2. Data used and its limits

data/multi_asset.csv (hash 19e95947f2a0): SPY EFA EEM TLT IEF GLD DBC VNQ, 2006-02-06 to 2026-10-05 (trading from 2007-02-20 after a 260-day warm-up).

Yahoo daily bars, adjusted for splits and dividends. Downloaded 2026-10-06 into the
append-only store and exported with `quantagents data export`.
- **Caveats:** survivorship-biased (upper bound only) and not point-in-time.
- **Survivorship:** every ETF used still exists today, so funds that closed are missing.
- **Data drift:** Yahoo restates history, so a later download may hash differently.
- **Costs:** 0.15% one way (10 bp fee + 5 bp slippage), fills at the next open.
- **Engine:** vectorized A43.

## 3. Variants tried and trial count

2: tsmom_blend_vt10 (primary), tsmom_blend_raw. 2 trials charged. The grid was fixed before the run. Every row is in `docs/research/trials.md`.

## 4. A44 table, A39 findings and the 2x-cost result (tool output, verbatim)

```
Backtest: tsmom_blend_vt10 (2007-02-20 to 2026-10-05)
Costs: 0.15% per unit traded (fees + slippage), fills at the next open
Total return +63.79% | CAGR +2.55% | volatility 4.06%
Sharpe 0.64 | max drawdown 7.83% | avg daily turnover 0.010 | invested on 100% of days

A44 validation: tsmom_blend_vt10 -> FAIL
----------------------------------------
[PASS] observations: 4937 days (need 252)
[PASS] newey_west_t: t = 3.01 (need 3)
[PASS] psr: PSR = 0.997 (need 0.95)
[PASS] dsr: DSR = 0.989 after 2 trial(s) (need 0.95)
[FAIL] pbo: PBO = 0.92 (need <= 0.2)
[PASS] sharpe_at_2x_costs: Sharpe at 2x costs = 0.55 (need > 0)
[PASS] spa: Hansen SPA p = 0.002 over 2 variant(s) vs cash (White RC form 0.002; need <= 0.05)
[PASS] walk_forward: 16 folds: mean out-of-sample Sharpe 0.52, OOS/IS 1.00 (need > 0 and >= 0.5)
Sharpe 0.64 (95% bootstrap interval 0.26 to 1.04)
Walk-forward folds (best in-sample variant, then the next unseen year):
  days 756-1007: tsmom_blend_vt10 in-sample Sharpe 0.86 -> out-of-sample 1.33
  days 1008-1259: tsmom_blend_vt10 in-sample Sharpe 0.81 -> out-of-sample 1.01
  days 1260-1511: tsmom_blend_vt10 in-sample Sharpe 1.08 -> out-of-sample -0.11
  days 1512-1763: tsmom_blend_vt10 in-sample Sharpe 0.83 -> out-of-sample -0.02
  days 1764-2015: tsmom_blend_vt10 in-sample Sharpe 0.33 -> out-of-sample 0.79
  days 2016-2267: tsmom_blend_vt10 in-sample Sharpe 0.21 -> out-of-sample -1.09
  days 2268-2519: tsmom_blend_vt10 in-sample Sharpe -0.08 -> out-of-sample 0.91
  days 2520-2771: tsmom_blend_vt10 in-sample Sharpe 0.23 -> out-of-sample 1.22
  days 2772-3023: tsmom_blend_vt10 in-sample Sharpe 0.47 -> out-of-sample -0.98
  days 3024-3275: tsmom_blend_vt10 in-sample Sharpe 0.45 -> out-of-sample 1.27
  days 3276-3527: tsmom_blend_vt10 in-sample Sharpe 0.58 -> out-of-sample 0.97
  days 3528-3779: tsmom_blend_raw in-sample Sharpe 0.65 -> out-of-sample 0.58
  days 3780-4031: tsmom_blend_raw in-sample Sharpe 1.02 -> out-of-sample -1.03
  days 4032-4283: tsmom_blend_raw in-sample Sharpe 0.44 -> out-of-sample 0.59
  days 4284-4535: tsmom_blend_vt10 in-sample Sharpe 0.10 -> out-of-sample 0.99
  days 4536-4787: tsmom_blend_vt10 in-sample Sharpe 0.36 -> out-of-sample 1.91
By market volatility (trailing 63 days; descriptive only):
  low vol   1625 days: +2.4% a year, Sharpe 0.57
  mid vol   1624 days: +2.1% a year, Sharpe 0.52
  high vol  1625 days: +3.5% a year, Sharpe 0.90
Note: 2 variant(s) run now; 2 trial(s) charged to this family (every variant ever run on real data counts).

A39 red team: tsmom_blend_vt10 -> PASS
--------------------------------------
Tests: future_perturbation, determinism, bounds, time_shift
No findings.
```

## 5. Verdict

**FAIL.** Every check passes except PBO (0.92, limit 0.20).

- **Return and risk:** Sharpe 0.64, against 0.58 for equal-weight buy-and-hold of the same 8
  ETFs. Max drawdown 7.8% against 37.2%. The return is much lower: +2.55% a year against
  +6.69%, because the book runs at about 4% volatility.
- **Why PBO fails:** the two variants have almost the same Sharpe over the full sample.
  When the sample is split in halves, whichever wins one half tends to lose the other. With
  only 2 near-twin variants, PBO measures that coin flip. It is not a measure of the
  family's edge. The rule fixed in advance still says FAIL.
- **What would change it:** a PBO computed on a pre-registered grid where the variants really
  differ (this needs the owner's decision on the rule), or out-of-sample evidence. The 30
  paper days of Phase 3 are a start.
