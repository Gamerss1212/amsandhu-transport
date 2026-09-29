# Validation notes — version 2.0

Completed: UTF-8 JSON and JSONL parsing; unique strategy names and IDs; required strategy field/type checks against the supplied schema's used constraints; family, parent, and source references; exact hypothesis/supporting counts; null performance and research-only statuses; Markdown source-reference resolution; 19 passing synthetic arithmetic tests; example recalculation; generated catalogue and retrieval views; archive and payload hash verification.

The schema check is a direct structural check, not certification by a general-purpose JSON Schema engine. Unique text does not establish statistically independent strategies: lineage marks related variants. The catalogue contains 302 trading hypotheses, 18 supporting records, 200 memecoin-specific records (197 hypotheses), 100 features, 77 sources, 100 acceptance specifications, and 104 glossary terms.

The 19 executed tests cover the offline educational calculator only. The 100 software acceptance scenarios have not been run against the user's software. No historical market backtest, model training, paper trading, live orders, complete token census, or token-by-token security audit was performed. Calculator assumptions exclude protocol-specific rounding, hooks, taxes, virtual reserves, and concurrent changes unless explicitly described.

Source review depth is retained. Not every source was read in full, and no separate all-URL availability audit was conducted. Sources support mechanics and context, not the profitability of authored rules. Protocol deployments, fees, APIs, regulations, and account permissions require renewed verification before implementation.

Timing: the session has a long wall-clock gap. One hour of active research was not independently timed or verified; see research_session.json. Usage quota percentages are unavailable, so neither a 30% nor 10% cap can be certified. Additional research was stopped after the latest usage instruction.
