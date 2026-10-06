# Connors RSI(2) reversion on US index ETFs (A16 family)

Status: **pre-registered** in `docs/research/preregistration.md`, run once on 2026-10-06 with
`python -m quantagents validate --strategy rsi2 --data <csv>`.

## 1. Hypothesis and economic reason

In an uptrend (price above its 200-day average), sharp 2-3 day sell-offs in broad index
ETFs tend to bounce within days. The cause is liquidity provision and over-reaction
(Connors-Alvarez 2009).

## 2. Data used and its limits

data/us_index.csv (hash 3f82863350f9): SPY QQQ IWM DIA, 2000-05-26 to 2026-10-05 (trading from 2001-06-08).

Yahoo daily bars, adjusted for splits and dividends. Downloaded 2026-10-06 into the
append-only store and exported with `quantagents data export`.
- **Caveats:** survivorship-biased (upper bound only) and not point-in-time.
- **Survivorship:** every ETF used still exists today, so funds that closed are missing.
- **Data drift:** Yahoo restates history, so a later download may hash differently.
- **Costs:** 0.15% one way (10 bp fee + 5 bp slippage), fills at the next open.
- **Engine:** vectorized A43.

## 3. Variants tried and trial count

2: rsi2_10 (primary), rsi2_5. 2 trials charged. The grid was fixed before the run. Every row is in `docs/research/trials.md`.

## 4. A44 table, A39 findings and the 2x-cost result (tool output, verbatim)

```
Backtest: rsi2_10 (2001-06-08 to 2026-10-05)
Costs: 0.15% per unit traded (fees + slippage), fills at the next open
Total return +27.32% | CAGR +0.96% | volatility 5.68%
Sharpe 0.20 | max drawdown 16.03% | avg daily turnover 0.063 | invested on 21% of days

A44 validation: rsi2_10 -> FAIL
-------------------------------
[PASS] observations: 6367 days (need 252)
[FAIL] newey_west_t: t = 1.26 (need 3)
[FAIL] psr: PSR = 0.837 (need 0.95)
[FAIL] dsr: DSR = 0.679 after 2 trial(s) (need 0.95)
[FAIL] pbo: PBO = 0.92 (need <= 0.2)
[FAIL] sharpe_at_2x_costs: Sharpe at 2x costs = -0.22 (need > 0)
[FAIL] spa: Hansen SPA p = 0.130 over 2 variant(s) vs cash (White RC form 0.130; need <= 0.05)
[PASS] walk_forward: 22 folds: mean out-of-sample Sharpe 0.20, OOS/IS 0.64 (need > 0 and >= 0.5)
Sharpe 0.20 (95% bootstrap interval -0.09 to 0.60)
Walk-forward folds (best in-sample variant, then the next unseen year):
  days 756-1007: rsi2_5 in-sample Sharpe 0.91 -> out-of-sample -0.23
  days 1008-1259: rsi2_5 in-sample Sharpe 0.88 -> out-of-sample -0.48
  days 1260-1511: rsi2_5 in-sample Sharpe 0.35 -> out-of-sample 0.25
  days 1512-1763: rsi2_10 in-sample Sharpe -0.10 -> out-of-sample -0.58
  days 1764-2015: rsi2_10 in-sample Sharpe -0.04 -> out-of-sample -1.11
  days 2016-2267: rsi2_5 in-sample Sharpe 0.13 -> out-of-sample 1.27
  days 2268-2519: rsi2_5 in-sample Sharpe 0.65 -> out-of-sample -0.08
  days 2520-2771: rsi2_5 in-sample Sharpe 0.54 -> out-of-sample -0.86
  days 2772-3023: rsi2_10 in-sample Sharpe 0.08 -> out-of-sample 1.55
  days 3024-3275: rsi2_10 in-sample Sharpe -0.08 -> out-of-sample 0.54
  days 3276-3527: rsi2_10 in-sample Sharpe -0.02 -> out-of-sample 0.89
  days 3528-3779: rsi2_5 in-sample Sharpe 1.03 -> out-of-sample -0.33
  days 3780-4031: rsi2_5 in-sample Sharpe 0.42 -> out-of-sample 0.39
  days 4032-4283: rsi2_5 in-sample Sharpe 0.54 -> out-of-sample 0.33
  days 4284-4535: rsi2_5 in-sample Sharpe 0.19 -> out-of-sample -0.27
  days 4536-4787: rsi2_5 in-sample Sharpe 0.15 -> out-of-sample -0.59
  days 4788-5039: rsi2_5 in-sample Sharpe -0.19 -> out-of-sample 1.95
  days 5040-5291: rsi2_5 in-sample Sharpe 0.08 -> out-of-sample 0.08
  days 5292-5543: rsi2_5 in-sample Sharpe 0.17 -> out-of-sample 0.10
  days 5544-5795: rsi2_5 in-sample Sharpe 0.80 -> out-of-sample -0.32
  days 5796-6047: rsi2_10 in-sample Sharpe 0.06 -> out-of-sample 0.90
  days 6048-6299: rsi2_10 in-sample Sharpe 0.49 -> out-of-sample 1.08
By market volatility (trailing 63 days; descriptive only):
  low vol   2102 days: -1.3% a year, Sharpe -0.26
  mid vol   2101 days: +3.7% a year, Sharpe 0.56
  high vol  2101 days: +1.0% a year, Sharpe 0.19
Note: 2 variant(s) run now; 2 trial(s) charged to this family (every variant ever run on real data counts).

A39 red team: rsi2_10 -> PASS
-----------------------------
Tests: future_perturbation, determinism, bounds, time_shift
No findings.
```

## 5. Verdict

**FAIL. No edge found after costs.**

- **Results:** Sharpe 0.20, t 1.26, SPA p 0.13, and Sharpe at 2x costs is -0.22. It was
  invested on only 21% of days, for +0.96% a year.
- **Why:** the short-term bounce exists in the papers before costs. At 0.15% one way, with
  trades every few days, most of it is paid away.
- **What would change it:** much cheaper execution (maker fees, which needs intraday data
  and limit orders), or a test on assets with larger bounces. Neither is in scope for
  Phase 2.
