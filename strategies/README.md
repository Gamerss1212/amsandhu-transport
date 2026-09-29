# Strategy library

Generated 2026-09-29. 409 distinct strategies after duplicate review (target was 300), 66 documented variants that are not counted, 147 sources. 259 of the distinct strategies are blocked: they are real, distinct hypotheses (most from the research knowledge pack, see PACK_IMPORT.md) that need data this software does not have.

| Status | Count |
|---|---|
| Implemented (runs on the bot platform) | 150 |
| Blocked (needs data or engine features that are missing) | 259 |
| Specified only | 0 |
| Research: sourced | 3 |
| Research: incompletely sourced | 67 |
| Research: hypothesis | 339 |
| Evaluation: untested | 263 |
| Evaluation: backtested | 112 |
| Evaluation: out-of-sample tested | 34 |
| Evaluation: paper observed | 0 |

No strategy here is labelled proven. Statuses are separate on purpose: a strategy can be sourced yet untested, or backtested yet a hypothesis.

## How strategies are counted

The distinctness rule (DUPLICATE_REVIEW.md) counts a strategy only if it differs in market hypothesis, signal construction, reference level, direction logic or required data. Changing a period, threshold, ticker, timeframe, or swapping one indicator for another in the same template makes a *variant*, listed under its parent and not counted. Applying that rule honestly produced the count above; BACKLOG.md lists the variants and the ideas rejected or not yet specified. Knowledge-pack records that describe a strategy already here were mapped to it, not counted again (PACK_IMPORT.md).

## Files

- `catalog.json` - every field of every strategy (machine-readable), plus variants
- `definitions/STRAT-###.json` - one executable definition per strategy (the bot platform loads these)
- `day_trading_strategies.xlsx` - index, full catalog, source register, evaluation results, implementation status
- `sources.json`, `SOURCE_REGISTER.md` - verified sources with links and access dates
- `TAXONOMY.md`, `DUPLICATE_REVIEW.md`, `BACKLOG.md`, `VALIDATION_METHODOLOGY.md`, `RANKING_METHODOLOGY.md`
- `src/` - the authoring sources and this build script (`python strategies/src/build.py`)

