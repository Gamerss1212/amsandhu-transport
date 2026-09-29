# Stock, crypto, and memecoin research pack

Version 2.0.0 • Source review: September 28–29, 2026 UTC

**320 records: 302 trading hypotheses and 18 supporting model, execution, or risk-filter entries, across 33 families.** The expansion contains 200 memecoin-specific records, including 197 hypotheses, plus twenty additional stock setups. Related variants are labeled, not presented as independent proven edges. No strategy has been backtested in this task; performance fields remain null.

Also included: 100 feature definitions, 77 source references with review depth, 100 future software acceptance-test specifications, 104 glossary terms, 20 screening rules, versioned data contracts, and a software integration prompt. Nineteen executed synthetic calculator tests are separate from the unexecuted software acceptance specifications.

## Start here

- `Memecoin_Trading_Handbook.md`: launch mechanics, identity, authorities, holders, manipulation, execution, research evidence, and concrete experiments.
- `Day_Trading_Handbook.md`: stock/crypto foundations, market structure, testing, and engineering.
- `strategy_catalog.json`: authoritative structured catalogue. `Strategy_Catalogue.md` is its readable rendering.
- `Software_Integration_Prompt.md`: hand this to your coding assistant with the full pack.
- `source_registry.json` and `Sources.md`: what each source supports and what it does not.
- `feature_dictionary.json`, `data_contracts.json`, and `strategy_catalog.schema.json`: implementation contracts.
- `memecoin_screening_rules.json` and `universe_discovery_spec.json`: discovery and eligibility specifications, not live scans or a complete census.
- `acceptance_tests.json`: future implementation tests. `glossary.json`: terminology.
- `research_math.py`, `test_research_math.py`, and `synthetic_examples.json`: offline educational arithmetic and synthetic verification, not a trading engine.
- `knowledge_base.jsonl`: retrieval import; avoid duplicate ingestion of its derived Markdown views.
- `catalogue_counts.json`, `validation_notes.md`, `research_session.json`, and `manifest.json`: counts, limitations, timing transparency, and integrity.

## Import rules

Preserve stable IDs, source provenance, null performance, parent relationships, and `counts_as_trading_hypothesis`. Never turn unknown values into safe/zero or a scanner score into an unvalidated probability. Sources establish mechanics and context; they do not endorse the exact authored rules. Many numerical parameters intentionally remain unset until preregistration.

No broker, wallet, exchange, live scan, model training, market backtest, or complete token census is connected or claimed. Every new token cannot be enumerated permanently: collect versioned supported universes and report coverage limits. No asset is trade-ready. Live execution remains disabled.

Run the calculator checks from this folder with `python -m unittest test_research_math.py`. Run `python research_math.py` for the clearly labeled examples. These use simplified continuous-unit arithmetic, not protocol-specific integer rounding or an actual execution adapter.
