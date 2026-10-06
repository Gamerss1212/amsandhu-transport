# Phase 9: Controlled scaling (owner approval at every step)

**Spec sections to read:** 65, 68, 69, 76.

## Rules (spec section 65)

- Raise size at most 2x per step, with at least 30 days between steps. The owner writes an approval row in STATUS for each step.
- Promote only when live Sharpe sits inside the backtest's 95% interval, live-vs-backtest divergence is under 1 standard deviation, drawdown is under 50% of the allowance, and A49 recorded zero breaches.
- Demote automatically when drawdown exceeds 1.5x the backtest's 95th percentile, live Sharpe stays below the interval for 60 days, slippage exceeds 2x the model, or any reconciliation fails.

## Claude does

- Builds the automatic demotion checks and the monthly review report.
- Builds the weekly agent league table and the monthly roster review (section 17).

## Acceptance

- [ ] Every step approved in writing, monitored and reversible
