# Strategy library

Generated 2026-09-27. 157 distinct strategies after duplicate review (target was 300; see *Why fewer than 300*), 66 documented variants that are not counted, 70 verified sources.

| Status | Count |
|---|---|
| Implemented (runs on the bot platform) | 127 |
| Blocked (needs data or engine features that are missing) | 30 |
| Specified only | 0 |
| Research: sourced | 3 |
| Research: incompletely sourced | 67 |
| Research: hypothesis | 87 |
| Evaluation: untested | 34 |
| Evaluation: backtested | 91 |
| Evaluation: out-of-sample tested | 32 |
| Evaluation: paper observed | 0 |

No strategy here is labelled proven. Statuses are separate on purpose: a strategy can be sourced yet untested, or backtested yet a hypothesis.

## Why fewer than 300

The distinctness rule (DUPLICATE_REVIEW.md) counts a strategy only if it differs in market hypothesis, signal construction, reference level, direction logic or required data. Changing a period, threshold, ticker, timeframe, or swapping one indicator for another in the same template makes a *variant*, listed under its parent and not counted. Applying that rule honestly produced the count above; BACKLOG.md lists the variants and the ideas rejected or not yet specified.

## Files

- `catalog.json` - every field of every strategy (machine-readable), plus variants
- `definitions/STRAT-###.json` - one executable definition per strategy (the bot platform loads these)
- `day_trading_strategies.xlsx` - index, full catalog, source register, evaluation results, implementation status
- `sources.json`, `SOURCE_REGISTER.md` - verified sources with links and access dates
- `TAXONOMY.md`, `DUPLICATE_REVIEW.md`, `BACKLOG.md`, `VALIDATION_METHODOLOGY.md`, `RANKING_METHODOLOGY.md`
- `src/` - the authoring sources and this build script (`python strategies/src/build.py`)

