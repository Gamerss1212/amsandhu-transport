# Research grid pre-registration (written 2026-10-06, before the grid's first real-data run)

This file, the grid in `src/quantagents/backtest/grid.py` and the runner in
`src/quantagents/research.py` were committed **before** the grid was run on real data. Nothing
below changes after a result is seen. Whatever the result is, it gets reported.

## What gets run

| Universe | File (hash) | Symbols | Start | Periods a year |
|---|---|---|---|---|
| multi_asset | data/multi_asset.csv (19e95947f2a0) | SPY EFA EEM TLT IEF GLD DBC VNQ | 2006-02-06 | 252 |
| sectors | data/sectors.csv (96aa159115e7) | XLB XLE XLF XLI XLK XLP XLU XLV XLY | 1998-12-22 | 252 |
| us_index | data/us_index.csv (3f82863350f9) | SPY QQQ IWM DIA | 2000-05-26 | 252 |
| crypto | data/crypto.csv (51cdd990d23b) | BTC-USD ETH-USD | 2017-11-09 | 365 |

- **Data:** Yahoo daily bars, adjusted for splits and dividends, from the append-only store.
  Caveats: survivorship-biased (upper bound only) and not point-in-time.
- **Grid:** 87 variants of 11 published families (table in `grid.py`). The benchmark is
  equal-weight buy-and-hold of the same universe.
- **Each variant on each universe:**
  - on the real data at the config's costs (0.15% one way);
  - again at 2x costs (0.30%, roughly what a retail crypto taker order really costs);
  - on 20 noise panels (block bootstrap, mean block 20 days, seeds 1-20).
- **Total:** 87 x 4 x (1 + 1 + 20) = **7,656 backtests**, plus 3 per finalist (an
  event-driven re-test and two time-shift runs).
- **Engine:** vectorized A43, next-open fills, holdings drift with prices, 260-day warm-up.
- **Trials charged:** 348 real-data trials (87 variants x 4 universes). Every one is logged in
  `docs/research/trials.md`.

## Selection rule (fixed in advance)

The finalist of each universe is the variant with the **highest full-sample Sharpe at 1x
costs**, excluding the benchmark.

## Pass rule (fixed in advance)

A finalist passes only if **all six** checks pass:

1. **A44 validation PASS.** That means all of:
   - Newey-West t ≥ 3
   - PSR ≥ 0.95, and DSR ≥ 0.95 charged with all 348 trials
   - PBO ≤ 0.20 across its universe's 87 variants
   - Sharpe at 2x costs > 0
   - Hansen SPA vs cash p ≤ 0.05
   - walk-forward out-of-sample Sharpe > 0, with OOS/IS ≥ 0.5
   - at least 252 days
2. **Beats buy-and-hold:** Hansen SPA on excess returns over buy-and-hold, p ≤ 0.05.
3. **FDR discovery:** its excess over buy-and-hold survives Benjamini-Hochberg at q = 0.10,
   across the 86 non-benchmark variants.
4. **Noise control:** its best-minus-buy-and-hold Sharpe beats every one of the 20 noise
   panels (empirical p ≤ 0.05).
5. **A39 red team PASS:** future perturbation, determinism, bounds and time shift.
6. **Event-driven re-test agrees:** Sharpe > 0 and within 0.10 of the vectorized Sharpe.

## Disclosures

- The Phase 2 results were seen before this grid was designed. Five of the families are in
  the grid; all five failed in Phase 2.
- Parameter ranges come from the papers and common practice, not from those results.
- Since Phase 2 the engine was corrected: holdings now drift with prices, and crypto uses
  365-day years. So Phase 2 numbers and grid numbers are not directly comparable.
- The noise control destroys trends longer than about a month, but keeps shorter behaviour. For
  short-term rules (RSI(2)) it is therefore a weaker null.
- A PASS would mean one historical sample cleared every check. It would not promise future
  returns. A FAIL means no edge was shown at the required confidence: a valid result.
