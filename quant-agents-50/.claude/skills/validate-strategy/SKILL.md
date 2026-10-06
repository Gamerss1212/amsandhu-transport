---
name: validate-strategy
description: Use when a strategy, signal or parameter set is proposed, changed or about to be promoted, or when anyone says a backtest "works".
argument-hint: "[strategy family, e.g. tsmom]"
---

# Validate strategy $0

## Steps

1. Count trials. Every variant ever run for this family is a trial (spec section 63). Add them to the trial log in `docs/research/trials.md`.
2. Run `python -m quantagents validate --strategy $0`. Add `--data <csv>` for real data.
3. Read the A44 checks and the A39 red-team findings. A critical red-team finding blocks the strategy.
4. Write `docs/research/$0.md` with these parts, in order:
   - hypothesis and economic reason (spec section 26)
   - data used and its limits (survivorship, point-in-time, synthetic or real)
   - every variant tried and the trial count
   - the A44 table, the A39 findings, and the 2x-cost result
   - verdict: PASS or FAIL, and what evidence would change it
5. On FAIL: say so plainly and stop. Do not tune the same family again in this session.

Results on synthetic data are labelled "synthetic" and never count as evidence for real markets.
