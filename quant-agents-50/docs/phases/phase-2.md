# Phase 2: First signals and validation (13 agents)

**Agents added:** A08, A11, A12, A16, A21, A23, A40, A44 (A21 is not built yet).
**Goal:** a few well-known strategies, each with an honest validation report.
**Spec sections to read:** 13, 38, 39, 41, 60, 61, 63, 64, Appendix A (A1-A3, A6, A9, A16).

## Already in the kit

- A08 volatility, A11 trend, A12 cross-sectional momentum, A16 reversion, A23 calendar, A40 no-trade.
- A44: Newey-West t, PSR, DSR, minimum backtest length, PBO/CSCV, BH-FDR, stationary bootstrap, walk-forward and purged k-fold splits.
- `python -m quantagents validate` runs a family's variants, A44 and the A39 red team.

## Build

1. **Trial log:** every backtest run appends a row to `docs/research/trials.md` (family, parameters, data hash, date, result). A44 uses the count.
2. **Strategy library** (Grade A/B in Appendix A), each as a strategy factory:
   - TSMOM 1/3/12-month blend with volatility scaling
   - 12-1 cross-sectional momentum
   - Faber 10-month moving-average filter
   - RSI(2) reversion on ETFs with a 200-day filter
   - volatility-targeting overlay
3. **A21 Carry:** build it if carry data exists (crypto funding through CCXT, or FX rate differentials). Otherwise leave it registered, idle, and note why in STATUS.
4. **A44 additions:** White's Reality Check or Hansen's SPA (bootstrap), out-of-sample/in-sample Sharpe ratio, results split by volatility regime.
5. Run `/validate-strategy` for each family and keep the notes in `docs/research/`.

## Acceptance (spec section 83)

- [x] Every strategy has a full A44 report with an honest PASS or FAIL (all five: FAIL; see `docs/research/`)
- [x] Every run is in the trial log (`docs/research/trials.md`; the CLI now logs every run itself)
- [x] The A39 red team passes every strategy that is reported (no findings on any of the five)

## Results (2026-10-06)

Pre-registered in `docs/research/preregistration.md`, run once on real data, 0.15% one-way costs.

| Family | Primary variant | Sharpe | Buy-and-hold Sharpe | Failing checks | Verdict |
|---|---|---|---|---|---|
| tsmom_blend | tsmom_blend_vt10 | 0.64 | 0.58 | PBO 0.92 | FAIL |
| faber | faber_10m | 0.64 | 0.58 | PBO 0.91 | FAIL |
| vol_target | vt10_hold | 0.57 | 0.58 | t 2.70, PBO 0.31 | FAIL |
| xs_mom | xsmom_12_1 | 0.60 | 0.58 | PBO 0.93 | FAIL |
| rsi2 | rsi2_10 | 0.20 | 0.58 | t, PSR, DSR, PBO, 2x costs, SPA | FAIL |

A21 carry: not built (see STATUS).
