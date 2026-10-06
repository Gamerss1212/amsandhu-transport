# Phase 2 pre-registration (written 2026-10-06, before any real-data run of these families)

Everything below was fixed and committed **before** the first real-data run, so the results
cannot have shaped the choices. Each family is run once with `quantagents validate`. The
primary (first) variant is the one reported. The others are neighbours that test whether the
result depends on one parameter. Every variant counts as a trial.

## Pass rule

A family passes only if its primary variant gets **PASS from A44 and from the A39 red team**,
at the config's thresholds (`config/default.yaml`, `validation:`). These are:
- Newey-West t ≥ 3.0
- PSR and DSR ≥ 0.95
- PBO ≤ 0.20
- Sharpe at 2× costs > 0
- Hansen SPA p ≤ 0.05
- walk-forward out-of-sample Sharpe > 0, with OOS/IS ≥ 0.5
- at least 252 days

No threshold, grid, universe or date range changes after a result is seen. A FAIL is reported
as a FAIL. The family is not re-tuned in this phase.

## Costs

The config default is 10 bp fee + 5 bp slippage, so 0.15% one way, paid on every unit traded.
The vectorized A43 engine is used. Fills are at the next open.

## Data

- Source: Yahoo daily bars, adjusted for splits and dividends, downloaded 2026-10-06 into the
  append-only store.
- Caveats: survivorship-biased (upper bound only) and not point-in-time.
- The ETFs used all exist today, which is itself a survivorship bias.
- Each universe starts on the first date when every symbol in it has data. It ends on the
  last completed day.

| Family | Universe | Why this universe |
|---|---|---|
| tsmom_blend | SPY EFA EEM TLT IEF GLD DBC VNQ | multi-asset, as in the trend-following papers |
| faber | SPY EFA EEM TLT IEF GLD DBC VNQ | Faber's paper uses a multi-asset ETF book |
| vol_target | SPY EFA EEM TLT IEF GLD DBC VNQ | overlay on the same multi-asset book |
| xs_mom | XLB XLE XLF XLI XLK XLP XLU XLV XLY | the 9 original sector SPDRs: industry momentum |
| rsi2 | SPY QQQ IWM DIA | liquid US index ETFs, as in Connors-Alvarez |

## Grids (from `src/quantagents/backtest/strategies.py`)

| Family | Primary | Neighbours | Trials |
|---|---|---|---|
| tsmom_blend | tsmom_blend_vt10 (1/3/12-month share positive, 10% vol target per asset, monthly) | tsmom_blend_raw (no vol scaling) | 2 |
| xs_mom | xsmom_12_1 (top third by 12-1 return, monthly) | xsmom_12_1_trend (only when the equal-weight index is above its 200-day average) | 2 |
| faber | faber_10m | faber_8m, faber_12m | 3 |
| rsi2 | rsi2_10 (enter RSI(2) < 10 above the 200-day average, exit close > 5-day average) | rsi2_5 | 2 |
| vol_target | vt10_hold (equal-weight book scaled to 10% a year, monthly, max 1x) | vt15_hold | 2 |

Total: 11 trials on real data.

The benchmark for every family is equal-weight buy-and-hold of the same universe. It is
reported for context and is not a pass condition.

## What the evidence can and cannot say

- A PASS means the primary rule cleared every check on this one historical sample. It does
  **not** promise future returns.
- A FAIL means no edge was shown at the required confidence. That is a valid result.
- The sample covers roughly 2006-2026 (2004 or 1999 onwards for some universes): one market
  history, dominated by a long US bull market.
