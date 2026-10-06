---
paths:
  - "src/quantagents/backtest/**"
  - "src/quantagents/validation/**"
  - "src/quantagents/features.py"
  - "docs/research/**"
---

# Research rules (spec sections 56-64)

- Causal only: a value at date t may use data up to t. Add a causality test for every new feature.
- Strategies are built by a factory from the data they run on, so the A39 future-perturbation test can rebuild them.
- Count every variant tried as a trial and log it in `docs/research/trials.md`. More trials need stronger evidence.
- Default promotion bar: Newey-West t at least 3.0, PSR and DSR at least 0.95, PBO at most 0.20, positive Sharpe at 2x costs.
- Report failures as plainly as passes. "No edge found" is a valid result.
- Never tune a strategy until it passes. Never present synthetic-data results as evidence about real markets.
- The vectorized backtester is for screening. Re-test finalists in an event-driven engine before paper trading.
