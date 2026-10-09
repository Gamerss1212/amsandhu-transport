Continue developing my existing AI trading software into a dependable, highly automated local application with a master AI coordinator, 25 or 50 specialist agents, exactly three main pages, optional real-money broker connections, and a proactive speaking assistant inspired by JARVIS.

Act as the project's senior software engineer, quantitative research engineer, execution-systems engineer, security engineer, and product designer. Work in the actual repository. Implement functioning software, verify it, fix defects, and deliver a runnable application. A polished mockup, proposal, or collection of disconnected modules is not completion.

1. CONTINUE THE EXISTING PROJECT

Inspect the repository, project instructions, current architecture, dependencies, running services, database, tests, and previous progress before editing. Identify what works, what is incomplete, what is simulated, and what has external dependencies. Preserve useful existing work and user changes.

Determine whether the project already has 25 agents, 50 agents, or another configuration. Report the actual count, preserve functional agents, and map them to responsibilities. If the project is effectively empty, implement 25 logical roles first and support expansion to 50. Do not create fake agents just to reach a number.

Continue the established technology stack unless a concrete limitation justifies a change. Make routine engineering decisions independently. Ask only for missing credentials, account choices, permissions, or decisions that materially block progress. If a service is unavailable, complete everything possible around it and label the exact remaining blocker.

Create a requirement-to-implementation map before making large changes. For each requirement record its existing module, intended change, dependency, verification method, and completion state. Keep the map current as work proceeds. Deliver complete vertical workflows in runnable increments rather than accumulating disconnected features.

Treat this prompt as the product specification. Existing repository security rules, user instructions, and provider constraints still apply. Resolve contradictions explicitly in the implementation notes. Do not disable failing checks, hide exceptions, or remove useful functionality merely to obtain a clean demonstration.

Read current official API documentation before integrating a provider. Record documentation URLs, access dates, relevant versions, account requirements, and limitations. Never invent endpoints, supported order types, account eligibility, market coverage, or API capabilities.

2. MY REQUIRED EXPERIENCE

I want the AI system to handle research, market monitoring, strategy selection, execution within my authorized limits, position management, recordkeeping, and ongoing evaluation automatically.

I do not want to manually run backtests, tune dozens of parameters, supervise individual bots, or approve every ordinary trade. Interpret this as no manual testing workflow and no testing page. Necessary engineering checks and strategy validation should run automatically in the background, with a short readiness explanation when they block something.

Build exactly three top-level pages:
- AI Trading System.
- Agent Activity.
- Brokers & Accounts.

Use drawers, tabs, expandable panels, and dialogs inside those pages for secondary features. The speaking assistant is a persistent interface across the three pages, not a fourth page.

Fully automated means routine operation within an explicitly authorized account, instrument universe, capital allocation, operating mode, and risk budget. It does not mean inventing permissions or bypassing broker authentication. Default to paper mode. Once I deliberately enable live operation and its boundaries, ordinary qualifying trades should run without repeated approval.

I should never have to pretend that a connection, agent, trade, or result exists. Show clear states for disconnected, simulated, delayed, unavailable, and live.

3. MASTER AI AND SYSTEM ARCHITECTURE

Separate the reasoning layer from the execution layer.

The master AI coordinates research and specialist outputs, explains decisions, selects among eligible strategies, and proposes portfolio actions. Deterministic services compute indicators, evaluate implemented rules, enforce risk policies, maintain order state, and communicate with brokers.

The language model must not directly hold trading credentials, invent prices, calculate authoritative balances, or bypass the risk engine. An unavailable model must not disable protective order management.

Use this operational flow:
market data -> quality checks -> features -> strategy signals -> portfolio allocation -> deterministic risk checks -> order management -> broker acknowledgements and fills -> reconciliation -> monitoring and explanation.

Research and learning run on a separate background path. New code, strategies, models, or parameters enter a versioned candidate registry and evaluation process before becoming eligible for execution.

Use typed, versioned messages. Every proposal should include an ID, timestamp, account and mode, instrument and venue, strategy version, data snapshot references, signal expiry, intended direction, proposed exposure, entry and exit conditions, estimated costs, risk impact, and a concise evidence-based explanation.

Support BUY, SELL, HOLD, EXIT, REDUCE, and ABSTAIN where meaningful. Abstaining is a successful outcome when evidence or execution conditions are inadequate.

Reject malformed, stale, unsupported, internally inconsistent, or unauthorized proposals. Store reason codes. Never interpret a model's self-reported confidence as a calibrated probability of profit.

Resolve conflicting signals centrally. Several agents must not independently submit contradictory orders for the same account and instrument. Aggregate exposures and dependencies across strategies and accounts. Correlated indicators or agents do not count as independent confirmation.

Prefer target-position proposals over repeated imperative "buy again" messages. Calculate the required change from reconciled holdings, outstanding orders, reserved exposure, and the approved target. Give each proposal a validity window and portfolio-state version; re-evaluate it if account state changes before execution.

Define three distinct memory stores:
- Operational state: authoritative orders, positions, policies, and connection state.
- Research knowledge: sources, hypotheses, specifications, versions, and evaluation artifacts.
- Conversational memory: user preferences and explanations, with retention controls.

A remembered conversation never overrides current broker state or an accepted risk policy. Use retrieval over versioned evidence rather than stuffing every agent transcript into the master model's context.

Every agent job needs a task contract: objective, input references, permitted tools, required output schema, dependencies, deadline, maximum attempts, cost allowance, cancellation state, and completion evidence. Workers return bounded results or explicit failure states. The coordinator must detect stalled dependencies and repeated handoffs instead of allowing endless loops.

4. AGENT RESPONSIBILITIES

Implement or map the existing agents to these 25 core logical roles:

01. Master coordinator: schedules work, synthesizes findings, and publishes an operating plan.
02. Market-data supervisor: manages feeds, subscriptions, timestamps, and availability.
03. Data-quality analyst: detects gaps, stale quotes, duplicate events, and inconsistent instruments.
04. Regime analyst: identifies trend, range, volatility, liquidity, and uncertain conditions.
05. Trend specialist: evaluates eligible trend-following systems.
06. Momentum specialist: evaluates momentum and relative-strength signals.
07. Mean-reversion specialist: evaluates range and reversion candidates.
08. Breakout specialist: evaluates range breaks and volatility expansion.
09. Market-structure specialist: evaluates explicitly defined swing and structure rules.
10. Volume and order-flow specialist: uses only genuinely available volume and depth data.
11. Statistical-arbitrage specialist: evaluates pairs and spread relationships.
12. Crypto specialist: handles venue structure, funding inputs, and eligible spot instruments.
13. Equity specialist: handles corporate actions, sessions, and equity-specific constraints.
14. FX specialist: handles currency pairs, sessions, rollover, and conversion.
15. Futures and index-products specialist: handles contracts, expiry, multipliers, and eligible index-linked products.
16. News and event analyst: tracks timestamped, attributable events.
17. Strategy researcher: maintains a deduplicated, sourced catalog of candidates.
18. Validation analyst: evaluates candidates automatically and documents uncertainty.
19. Portfolio allocator: proposes exposure within approved constraints.
20. Risk-policy analyst: reviews risk and explains deterministic policy outcomes.
21. Execution analyst: selects supported execution approaches and monitors execution quality.
22. Reconciliation analyst: checks orders, fills, balances, and positions against broker records.
23. Attribution analyst: measures outcomes by strategy, market, costs, and operating regime.
24. Reliability supervisor: monitors failures, resource use, recoveries, and drift.
25. Voice and reporting assistant: explains verified system state and handles authorized commands.

Logical roles can be deterministic workers, statistical models, LLM agents, or hybrid components. Label their implementation honestly. An agent tile alone does not constitute a working agent.

If 50 useful agents already exist, preserve them. Otherwise, additional roles may cover liquidity, spreads, transaction costs, borrowing, funding, calendar events, corporate actions, session calendars, contract rolls, correlation, concentration, exposure stress, candidate deduplication, parameter stability, signal calibration, model drift, data drift, reconciliation anomalies, security monitoring, cost control, storage health, restart recovery, voice intent, alert prioritization, and reporting.

Expansion must have measurable purpose. Agents need bounded queues, deadlines, cancellation, retries with limits, health checks, restricted tools, and shared evidence references. Schedule expensive reasoning only when needed. Do not run 50 continuous LLM conversations for routine arithmetic or each price tick.

For a genuine 50-role configuration, use these optional specialist assignments, subject to the mapping of existing functional agents:
26 liquidity; 27 spread monitoring; 28 transaction-cost estimation; 29 borrowing constraints; 30 funding inputs; 31 event calendar; 32 corporate actions; 33 trading sessions; 34 contract rolls; 35 correlations; 36 concentration; 37 stress scenarios; 38 strategy deduplication; 39 parameter stability; 40 signal calibration; 41 model drift; 42 data drift; 43 reconciliation anomalies; 44 security events; 45 compute and API budgets; 46 storage health; 47 restart recovery; 48 voice intent; 49 alert prioritization; 50 session reporting.

Evaluate whether a separate role improves coverage, reliability, latency, or cost compared with a simpler worker. Merge redundant responsibilities. Show configured roles, running jobs, and active model calls as three different counts.

5. RESEARCH AND STRATEGY LIBRARY

Build a continuously expanding strategy research library. Do not claim to have learned every strategy in existence, discovered private proprietary methods, or established that any method always works.

For each strategy, distinguish:
- Documented idea.
- Precisely specified candidate.
- Implemented candidate.
- Automatically evaluated candidate.
- Paper-eligible strategy.
- Live-eligible strategy within an authorized scope.
- Suspended or retired strategy.

Research these families and their meaningful variations:

Trend: moving-average rules, channel breakouts, Donchian systems, trend pullbacks, volatility-adjusted trends, and time-series momentum.

Momentum: rate of change, cross-sectional strength, relative strength, session momentum, and momentum with liquidity or volatility filters.

Mean reversion: standardized price deviations, Bollinger-type bands, moving-average distance, range reversion, and suitable VWAP deviations.

Breakouts: opening ranges, prior-session levels, consolidation ranges, squeeze expansion, failed breakouts, and objectively defined retests.

Structure: confirmed swings, support and resistance, break-of-structure rules, liquidity-sweep hypotheses, and explicit imbalance definitions. Treat smart-money and similar terminology as hypotheses needing measurable rules.

Volume and order flow: relative volume, trade imbalance, order-book imbalance, volume profiles, and spread-depth interactions. Disable these when the data cannot support them.

Relative value: pairs, cointegration candidates, basket residuals, sector-relative signals, and mean-reverting spreads, with relationship-breakdown controls.

Crypto-specific: eligible spot momentum, basis and funding research, cross-venue discrepancies, and liquidity filters. Research status must not imply that derivatives or cross-venue execution are available.

FX: trend, range, session transitions, macro-event filters, relative currency strength, and rollover-aware execution.

Futures and index-linked instruments: eligible contract momentum, opening ranges, calendar-spread research, expiry-aware signals, and contract-roll handling. Indices themselves are benchmarks; execution requires an eligible tradable product.

Event-driven: earnings and scheduled macro-event reactions where licensed, timestamped data supports the hypothesis.

Statistical and machine-learning methods: calibrated classification, regression, regime models, change detection, and carefully evaluated ensembles.

Portfolio methods: volatility scaling, diversification, correlation-aware allocation, and bounded regime-dependent weighting.

Execution methods: limit-order scheduling, participation controls, TWAP/VWAP-style execution where justified, and implementation-shortfall analysis. Label these as execution methods, not automatic sources of profit.

For every catalog entry, store the source, publication date, originally studied markets and horizons, precise rules, inputs, parameter ranges, costs, failure modes, compute requirements, market eligibility, version, and current evidence status.

A long-horizon study does not establish an edge on five-minute candles. A working implementation does not establish profitability. A variation of the same formula does not become an independent strategy merely by changing its name.

Use primary research, exchange and broker documentation, and reproducible sources. Record uncertainty and contradictory findings. Never label an internet win-rate claim as verified evidence.

Prioritize an initial liquid, data-supported universe rather than scanning every asset at once. Support five-minute and fifteen-minute strategies where evidence and data justify them, while preserving each strategy's native decision and holding horizons. Cross-market support must include correct instrument semantics, not one generic stock formula reused everywhere.

Assign each candidate a stable family ID and rule fingerprint so cosmetic names and small parameter changes do not inflate the strategy count. Record rejected candidates and failed hypotheses to prevent the research agent from repeatedly rediscovering them.

Schedule research in bounded batches. Stop each batch with an evidence register, newly specified candidates, contradictions, and a concrete next action. A request to research broadly must never become an infinite loop that blocks delivery of the working application.

Treat options, on-chain trading, market making, high-frequency execution, and cross-venue arbitrage as capability-gated extensions. Enable an extension only after its distinct data, permissions, execution, and risk requirements are implemented. For on-chain work, a token ticker alone is insufficient identification; chain and contract identity are required.

5A. WHAT "BEST" AND "WORKING" MUST MEAN

Interpret my request as broad coverage of credible systematic methods across accessible public markets, followed by automatic selection for the actual account and current conditions. There is no single best strategy across all assets, horizons, costs, and regimes. Build an expanding evidence catalog; do not represent this initial catalog as every public or proprietary method in existence.

A strategy is "working software" when its implementation behaves according to its specification. It is "currently eligible" only when its data, validation, permissions, execution, and risk conditions pass. Historical research support is a separate label. None of these states guarantees future profits.

Use three evidence labels throughout the catalog:
- R — Research-supported family: the cited authors report empirical evidence in a specified historical sample. This does not certify the proposed implementation, current profitability, or transfer to another market.
- C — Documented construction: the trade, hedge, or portfolio structure is documented by a primary source. Its mechanics do not establish a positive expected net return.
- H — Research hypothesis or adaptation: the concrete proposed rule has not been established by the sources reviewed for this prompt. Keep it in research until the system produces appropriate evidence.

Record source access depth separately: full methods inspected, abstract inspected, or bibliographic record only. If the full method is unavailable, do not pretend the paper has been replicated. R describes what the published study reports; implementation readiness remains unverified.

Every specification below is a starting template. Holding periods are research scopes, not optimized recommendations. Proposed entry, exit, sizing, and suspension rules are engineering requirements unless explicitly identified as an exact source method. A change in timing, asset universe, hedge, parameters, or execution creates a new version requiring its own evaluation.

This catalog contains 80 templates, including related variants and defensive structures. It does not contain 80 independent return sources. Identify shared trend, equity, credit, volatility, liquidity, and funding exposures before combining them. Covered calls, collars, and protective puts may serve portfolio objectives without being standalone alpha strategies.

5B. MARKET COVERAGE AND ADAPTER REQUIREMENTS

Support a market only through verified instruments, data, account permissions, and execution adapters. Make a coverage matrix with separate research, historical-data, live-data, paper-execution, and live-execution status.

| Market | Research scope | Additional implementation requirements |
| --- | --- | --- |
| Global equities | Eligible shares across regions, sectors, and capitalization groups | Point-in-time listings, delistings, dividends, splits, filing timestamps, currencies, trading halts, short availability, and local settlement rules. |
| ETFs, listed REITs, and index products | Equity, sector, country, bond, commodity, and eligible crypto exposures | Product mandate, holdings timing, distributions, tracking differences, premium/discount, leverage/reset mechanics, and underlying trading hours. An index value is not an executable instrument. |
| FX | Eligible spot, forwards, and currency futures | Base/quote conventions, executable bid/ask, actual financing, settlement dates, holidays, dealer-specific volume, and instrument-specific rollover. Do not portray one dealer's volume as global FX volume. |
| Crypto | Eligible spot, dated futures, and perpetual contracts | Venue and chain identity, custody and counterparty exposure, contract collateral, funding timing, outages, delistings, and derivative eligibility. Stablecoin collateral is not assumed equivalent to insured cash. |
| Commodities | Energy, metals, agriculture, livestock, and supported specialty contracts | Delivery specifications, expiry, first-notice dates, units, conversion ratios, seasonality, storage information, inventory release timestamps, and real contract rolls. |
| Rates and sovereign bonds | Cash bonds, rate futures, yield-curve and basis research | Accrued interest, clean/dirty prices, day counts, coupon schedules, duration, DV01, convexity, cheapest-to-deliver dynamics, financing, and settlement. |
| Corporate and emerging-market credit | Eligible bonds, bond funds, and explicitly supported hedging instruments | Tradable quotes, issue-level liquidity, default/recovery assumptions, issuer concentration, spread duration, callability, ratings history, and stale-price detection. |
| Listed options | Eligible equity, ETF, index, and futures options | Full contract identity, multiplier, exercise style, settlement, executable chains, Greeks with model versions, dividends, assignment, expiration, and combination-order support. |
| Specialty markets | Power, emissions, freight, volatility products, and other requested instruments | Research-only until a dedicated product specification, licensed data, account access, and risk model exist. Do not infer support from a similarly named ticker. |

Direct property, private credit, private equity, and other infrequently traded assets need separate workflows; do not present them as continuously executable markets. Prediction markets and other specialized venues require a separate access and product review before inclusion.

5C. INITIAL CATALOG: 80 STRATEGY TEMPLATES

A. CROSS-ASSET TREND, VALUE, AND CARRY

ST001 — Time-series momentum. Evidence R [S01]. Markets: liquid futures and forwards in the studied asset classes; scope: weeks to months. Use each instrument's trailing excess return to determine direction, with bounded volatility scaling. Exit or rebalance when the scheduled signal changes. Require appropriate return and roll series. Main failures: reversals, whipsaws, gaps, and correlated trend exposure.

ST002 — Moving-average trend. Evidence H for the proposed variant. Markets: liquid shares, ETFs, FX, crypto, and futures; scope: days to months. Define a completed-bar price/average or fast/slow crossover, a buffer, and a scheduled exit. Include spreads and turnover. Test each market separately; choppy prices and delayed reversals can repeatedly erode capital.

ST003 — Donchian/channel breakout. Evidence H for the proposed variant. Markets: liquid spot and futures products; scope: days to months. Enter beyond a channel calculated from prior completed bars, excluding the trigger bar. Exit through a separately defined trailing channel or risk rule. Handle gaps and stop slippage; false breaks and correlated signals can dominate results.

ST004 — Relative momentum with an absolute-trend filter. Evidence H for this combination. Markets: diversified eligible ETFs or futures; scope: monthly decisions. Rank assets by trailing strength, then allocate only when the selected asset passes an absolute threshold. Cash is a valid target. Define ties, turnover limits, and exposure caps; rapid rotation and concentration are failure modes.

ST005 — Volatility-managed momentum. Evidence R for volatility management at the studied portfolio level, H for this combination [S03]. Markets: an already specified momentum portfolio. Scale exposure from lagged volatility within fixed caps; rebalance on a defined schedule. Test estimation lag and transaction costs. Low measured volatility must never authorize unlimited leverage or conceal jump risk.

ST006 — Trend pullback continuation. Evidence H. Markets: liquid instruments with a separately defined trend; scope: intraday to several days. Define the trend, allowable retracement, completed-bar trigger, and invalidation before evaluating it. Exit at invalidation, target, or maximum age. Suspended during unclear structure; a reversal cannot be relabeled a pullback after losses.

ST007 — Cross-asset value. Evidence R [S02]. Markets: the asset groups and valuation measures supported by the selected study; scope: months to years. Use asset-specific valuation, normalize within comparable groups, and rebalance gradually. Require point-in-time economic or fundamental data. Cheap assets can become cheaper; macro breaks, financing, and concentration can overwhelm the valuation signal.

ST008 — Diversified carry. Evidence R [S04]. Markets: supported currencies, bonds, commodities, and other separately specified instruments; scope: weeks to months. Estimate carry under explicitly unchanged price/curve conditions, rank comparable exposures, and diversify. Include financing and hedging. Carry is conditional compensation, not locked profit; correlated losses can emerge during funding and liquidity stress.

B. EQUITIES, SECTORS, AND CORPORATE EVENTS

ST009 — Cross-sectional equity momentum. Evidence R [S02, S05]. Markets: liquid equities; scope: monthly formation and multi-month holding variants. Rank lagged total returns using a predefined observation and skip period; buy relative winners and short losers only if permitted. Account for delistings, borrow, and turnover. Momentum can suffer sharp losses around market rebounds.

ST010 — Sector or industry rotation. Evidence H for the proposed implementation. Markets: eligible sector baskets or ETFs; scope: weeks to months. Rank comparable total-return series and rebalance among stronger sectors with concentration caps. Exit when rank or trend conditions fail. Overlapping constituents, changing classifications, index reconstruction, and crowded sector exposure can create misleading diversification.

ST011 — Book-to-market value. Evidence R [S06]. Markets: equities with suitable accounting data; scope: months to years. Rank a precisely defined point-in-time book-to-market measure within the chosen universe and rebalance on schedule. Require publication lags and valid denominators. Financial distress, intangible-heavy businesses, sector bias, and long periods of underperformance require explicit controls.

ST012 — Earnings or free-cash-flow yield value. Evidence H for the chosen definitions and composite. Markets: equities; scope: months to years. Compare timestamped earnings or cash flow with the appropriate price or enterprise-value denominator. Define treatment of negative values and one-off items. Exit on scheduled reranking or invalid data; accounting distortions and value traps can defeat the signal.

ST013 — Quality minus junk. Evidence R [S07]. Markets: equities; scope: months. Build an explicitly versioned quality score using source-supported dimensions, then form a diversified portfolio. Use only data published before selection. Rebalance rather than chase news narratives. Valuation, sector crowding, missing fields, and financing can make a high-quality company an unattractive trade.

ST014 — Operating-profitability factor. Evidence R [S06]. Markets: equities; scope: months. Follow a documented accounting definition and rank stronger versus weaker operating profitability within an eligible universe. Keep reporting delays and rebalance rules explicit. Profitability is distinct from recent price momentum, but concentrated sector exposure and revised accounts can still bias an apparent result.

ST015 — Conservative-investment factor. Evidence R [S06]. Markets: equities; scope: months to years. Define asset-growth or investment intensity from point-in-time accounts and form conservative-versus-aggressive groups. Follow a documented rebalance schedule. Acquisitions, accounting changes, small-company liquidity, and sustained growth-led markets can undermine performance or comparability.

ST016 — Betting against beta. Evidence R [S08]. Markets: instruments supported by the chosen study; scope: monthly portfolio decisions. Estimate beta using lagged data and specify the scaling of low- and high-beta legs. Rebalance with financing and gross-exposure limits. If leverage or shorts are unavailable, treat a long-only adaptation as a different strategy.

ST017 — Long-only low-volatility portfolio. Evidence H for the proposed adaptation; related beta research [S08]. Markets: liquid equities or ETFs; scope: months. Rank lagged risk estimates and construct a constrained portfolio. Define benchmark exposure and rebalance costs. This is not equivalent to betting against beta; concentration, valuation, and rising correlation can offset lower standalone volatility.

ST018 — Short-term reversal. Evidence C for the documented factor construction, H for the executable rule [S09]. Markets: liquid equities; scope: days to weeks. Buy recent relative losers and, where permitted, sell winners using a fixed formation horizon. Enforce spread and news exclusions. Turnover, adverse selection, and distressed-name concentration can consume the apparent gross effect.

ST019 — Post-earnings-announcement drift. Evidence H pending full-method extraction for this implementation; foundational literature located [S10]. Markets: equities; scope: days to months after publication. Define a timestamped earnings-surprise measure and trade only after dissemination. Specify exit age and next-event handling. Revised estimates, instant repricing, borrow costs, and publication-time leakage can invalidate results.

ST020 — Merger arbitrage. Evidence R [S11]. Markets: announced, eligible corporate transactions; scope: weeks to deal resolution. Calculate consideration and deal-specific hedges from verified public terms, then compare spread with an independently specified risk model. Exit on completion, thesis invalidation, or constraints. Deal breaks, competing bids, funding, and uncertain completion times create asymmetric losses.

C. INTRADAY AND MARKET-MICROSTRUCTURE CANDIDATES

ST021 — Opening-range breakout. Evidence R for the cited crude-oil study's specific threshold method, H for generic first-N-minute variants [S12]. Markets: separately evaluated liquid session-based instruments; scope: one session. Freeze an opening range or source-specific threshold, enter on a later executable break, and exit by a defined deadline. Include failed breaks, gaps, and spread expansion.

ST022 — First-half-hour to last-half-hour momentum. Evidence R [S13]. Initial scope: the S&P 500 ETF setting studied by the authors. The opening signal includes the return from the previous close through the first half hour; evaluate a separately defined final-half-hour trade. Do not reinterpret this evidence as prediction of every subsequent five-minute bar.

ST023 — VWAP trend pullback. Evidence H. Markets: instruments with reliable trade-volume data; scope: intraday. In a separately confirmed trend, identify a pullback toward session VWAP and enter only after a predefined resumption trigger. Exit on invalidation or session deadline. VWAP is a reference price, not evidence that price must bounce.

ST024 — VWAP mean reversion. Evidence H. Markets: liquid, reliably measured session instruments; scope: minutes to hours. Fade a standardized deviation only when the specified range regime and liquidity checks pass. Target the moving reference with a time limit. Trend days, scheduled information releases, fragmented volume, and widening spreads can defeat reversion.

ST025 — Prior-session high/low breakout. Evidence H. Markets: session-based equities, FX feeds, and futures; scope: intraday. Fix calendar, prior-session bounds, breakout buffer, and permitted entry times. Exit on failure or deadline. Distinguish overnight from regular-session levels; repeated touches, auction effects, and transaction costs can eliminate a visible chart pattern's value.

ST026 — Failed-breakout reversal. Evidence H. Markets: liquid instruments; scope: intraday to several days. Define a previously known range, a measurable excursion, and a later completed-bar return inside it. Enter only after confirmation, with invalidation outside the excursion. Do not use future bars to select failures; genuine trend continuation is the principal risk.

ST027 — Gap continuation. Evidence H. Markets: session-based equities and futures; scope: intraday. Classify the opening gap using only prior-close and available opening information, then require a defined continuation trigger. Exclude corporate-action artifacts and uncertain event data. Exit on invalidation or time. Opening volatility, auctions, and rapid reversal can dominate results.

ST028 — Gap fade. Evidence H. Markets: separately eligible session instruments; scope: intraday. Require an objective gap size, a non-event or other explicitly justified eligibility condition, and a reversal trigger. Target a predeclared portion of the gap with bounded loss and duration. A gap is not an obligation for the market to return to yesterday's price.

ST029 — Volatility-squeeze expansion. Evidence H. Markets: liquid instruments; scope: minutes to days. Define compression from lagged realized volatility or band width, freeze the breakout level, and trade a subsequent move. Specify false-break and time exits. Do not count Bollinger, ATR, and channel variants as independent evidence; spread and volatility can expand together.

ST030 — Order-book imbalance response. Evidence R for a studied short-horizon predictive relationship, H for a profitable trading rule [S14]. Markets: venues with complete, synchronized depth. Estimate imbalance and evaluate executable responses at measured latency. Exit after a short signal lifetime. Queue position, cancellations, hidden liquidity, fees, and adverse selection are essential.

ST031 — Confirmed market-structure break. Evidence H. Markets: liquid instruments; scope: minutes to days. Define swing confirmation using a fixed number of already completed bars and timestamp when the level becomes known. Trade a later break with explicit invalidation. Repainting pivots or hindsight-selected structure disqualify the implementation.

ST032 — Liquidity sweep and reclaim. Evidence H. Markets: supported liquid instruments; scope: intraday. Define a known level, minimum excursion, reclaim timing, and entry condition. Call inferred stop concentrations a hypothesis unless actual data supports them. Exit on renewed breach or timeout. Do not claim access to other traders' private stops or hidden intentions.

D. STATISTICAL ARBITRAGE AND RELATIVE VALUE

ST033 — Distance-based pairs trading. Evidence R [S15]. Markets: suitable equity pairs; scope: days to months. Select pairs using a past formation window and normalized historical-price distance, then define divergence and convergence rules for the next trading interval. Include both legs' costs and borrow. Structural breaks, common factor exposure, and delistings remain material.

ST034 — Cointegration-based pairs. Evidence H for the exact selection and execution model. Markets: economically plausible tradable pairs; scope: days to months. Estimate a past-window hedge and residual, require relationship diagnostics, and trade bounded deviations. Exit on convergence, timeout, or relationship failure. Correlation alone is insufficient; repeated pair searching creates selection bias.

ST035 — Sector-ETF residual mean reversion. Evidence R for the studied approach [S16]. Markets: equities with appropriate sector proxies; scope: days. Estimate lagged factor exposure, model residual deviations, and form constrained positions. Include hedging, turnover, and borrow. A stock-specific event or changing factor relationship can make an apparently cheap residual rational.

ST036 — PCA residual mean reversion. Evidence R for the studied approach [S16]. Markets: a sufficiently broad liquid equity universe; scope: days. Fit factors using past data, construct residual signals, and rebalance under exposure constraints. Track component and universe changes. Statistical factors, crowding, and transaction costs can shift; published results are not stationary constants.

ST037 — ETF creation/redemption arbitrage. Evidence C [S17]. Markets: eligible ETFs and underlying baskets; scope: execution-dependent. Compare executable basket value with ETF price after all fees, financing, and hedging. Direct creation/redemption requires the relevant authorized-participant access. A retail premium/discount trade is a separate, unhedged or imperfectly hedged hypothesis, not this mechanism.

ST038 — Dual-listed or ADR relative value. Evidence H for the selected pair and rules. Markets: verified equivalent claims; scope: minutes to days. Confirm conversion rights, share ratios, currency hedges, settlement, and simultaneous tradability before comparing executable prices. Exit on convergence or constraints. Nonconvertibility, borrow recalls, taxes, holidays, and transfer delays can preserve discrepancies.

E. FOREIGN EXCHANGE

ST039 — Currency carry. Evidence R [S04, S18]. Markets: eligible currency instruments; scope: weeks to months. Define exposure using tradable forwards or actual broker financing, rather than policy rates alone. Rebalance on schedule with currency and funding caps. Exchange-rate moves, crowded exits, and liquidity shocks can exceed accumulated interest.

ST040 — Cross-sectional currency momentum. Evidence R [S19]. Markets: currencies supported by the chosen data and instruments; scope: months. Rank past currency excess returns and construct permitted winner/loser exposures. Use executable conversions and rollover. Published evidence includes limits to capture; turnover, spreads, funding, and crowded reversals must be measured.

ST041 — Currency valuation or PPP reversion. Evidence H for the proposed valuation measure. Markets: currencies with appropriate economic data; scope: months to years. Specify the valuation model, release lags, and a slow rebalance rule. Structural inflation differences, capital controls, and long-lived misvaluation can overwhelm a simple fair-value estimate.

ST042 — Dollar-carry timing. Evidence H for the proposed timing rule. Markets: explicitly specified currency baskets; scope: weeks to months. Separate dollar exposure from carry ranking, define the state variable and hedge, and evaluate each source of return. Exit by rule or risk limit. A profitable generic carry study does not establish a dollar-timing model.

ST043 — Triangular FX arbitrage. Evidence H for an executable strategy; a conversion identity alone does not establish attainable profit. Scope: one fully specified three-pair cycle. Use simultaneous directional bid/ask quotes, available size, fees, and attainable latency. Execute only with an approved legging policy. Stale prices and incomplete fills can turn a displayed discrepancy into outright currency exposure.

ST044 — FX session-range breakout. Evidence H. Markets: individually evaluated currency feeds; scope: intraday. Define the session in exchange-aware time, freeze a range, and trade subsequent breaks with rollover and news filters. Exit before a specified cutoff. Daylight-saving changes, dealer spread behavior, and overlapping sessions must be part of the rule.

F. CRYPTO SPOT, FUTURES, FUNDING, AND VENUES

ST045 — Crypto time-series momentum. Evidence R for the study's sampled cryptocurrencies and period [S20]. Markets: individually eligible liquid tokens; scope: source-aligned daily or longer research. Use lagged returns and a separately specified execution rule. Require survivorship-aware listings and venue data. The study does not establish identical behavior in every token or on five-minute charts.

ST046 — Crypto cross-sectional momentum. Evidence R [S21]. Markets: point-in-time eligible token universes; scope: periodic ranking. Form exposure from lagged relative returns, with liquidity and concentration limits. Measure shared crypto-market and size exposure. Listings, failed assets, fabricated volume, and unavailable shorting can materially change implementable results.

ST047 — Dated-futures cash-and-carry. Evidence R for the documented crypto carry research [S22]. Markets: eligible spot and matching dated futures. Compare basis with financing, fees, margin, and custody costs; size a contract-correct hedge and manage it to a defined exit or expiry. Interim margin calls, basis widening, venue failure, and settlement mismatches remain possible.

ST048 — Spot/perpetual funding carry. Evidence H for the proposed strategy; related carry research [S22]. Markets: eligible matching spot and perpetual products. Hedge delta and compare expected funding with all holding costs under conservative scenarios. Reassess each funding interval; exit on inversion, hedge failure, or limits. Funding is variable, and perpetual basis need not converge on a known date.

ST049 — Cross-venue crypto arbitrage. Evidence R for observed segmentation and trading discrepancies, not frictionless profits [S23]. Markets: approved venues with pre-positioned inventory where needed. Compare executable buy and sell prices after fees and rebalancing costs. Transfers are not assumed instantaneous. Withdrawal restrictions, collateral differences, counterparty risk, and failed legs can prevent capture.

ST050 — Triangular crypto arbitrage. Evidence H for the executable strategy. Markets: three compatible pairs on an eligible venue. Calculate the complete bid/ask conversion cycle with quantity steps, depth, fees, and residual dust. Cancel or hedge incomplete cycles according to policy. Displayed prices without available size are not actionable arbitrage.

ST051 — Crypto ETF/spot or ETF/futures basis. Evidence H for the executable strategy; ETF access mechanics [S17]. Markets: approved products with understood settlement and holdings. Specify currency, trading-hours, and hedge differences; compare executable prices, not an unverified indicative value. Premiums can persist, shorts may be unavailable, and retail accounts cannot assume creation/redemption rights.

ST052 — Liquidation-pressure response. Evidence H. Markets: derivatives venues with attributable liquidation and open-interest data. Define the event threshold and test continuation and reversion as different variants with fixed exits. Do not use retrospectively completed liquidation maps. Delayed feeds, liquidation clustering, exchange-specific coverage, and mark-price differences can invalidate the signal.

G. COMMODITIES, FUTURES SPREADS, AND RATES

ST053 — Commodity curve carry. Evidence R [S24]. Markets: specified liquid commodity contracts; scope: weeks to months. Rank a precisely defined term-structure measure using actual contracts, with fixed roll and rebalance rules. Distinguish spot moves, carry, and collateral return. Curve shifts, delivery constraints, and contract discontinuities can dominate a simple backwardation score.

ST054 — Inventory-informed commodity relative value. Evidence R for the documented inventory relationship, H for a new signal [S24]. Markets: commodities with reliable physical-inventory data. Combine timestamped inventory measures with a specified price/curve model and bounded exposure. Exit when the model or horizon expires. Releases are delayed and regional inventories may not represent deliverable supply.

ST055 — Commodity calendar spreads. Evidence C [S25]. Markets: eligible expiries of the same commodity. Define the relative-value thesis, trade the permitted near/far contract combination, and exit on target, time, or risk limit. Prefer supported spread orders. Calendar spreads still carry seasonal, liquidity, delivery, and outright price sensitivity when legs are not perfectly matched.

ST056 — Energy crack spreads. Evidence C [S46]. Markets: crude oil and refined-product contracts. Use documented units and a declared refinery-output ratio; trade deviations only under a separately evaluated model. Exit on normalization or invalidation. Regional quality differences, outages, transport, weather, and unequal contract liquidity can overwhelm the theoretical processing margin.

ST057 — Agricultural crush spreads. Evidence C [S47]. Markets: soybeans, meal, and oil or another explicitly modeled processing chain. Convert units correctly and specify the processing ratio before constructing a spread. Trade only a validated valuation or momentum rule. Input/output location, seasonality, crop shocks, and mismatched legs prevent automatic lock-in of an industrial margin.

ST058 — Seasonal commodity spreads. Evidence H. Markets: commodity contracts with a plausible recurring production or demand cycle. Specify the contract-month pair, entry calendar, holding period, and information available at each date. Count each season as dependent evidence where appropriate. Weather shifts, policy changes, sparse observations, and repeated calendar searches can create false patterns.

ST059 — Intercommodity relative value. Evidence H for the model; spread mechanics [S25]. Markets: economically related but nonidentical commodities. Estimate a historically specified hedge, constrain residual risk, and trade deviations with a relationship-break exit. Substitution can change; unit conversion, energy content, geography, and evolving supply chains matter more than a superficially correlated chart.

ST060 — DV01-matched yield-curve steepener/flattener. Evidence C [S26]. Markets: supported government bonds or rate futures. Define which maturity spread should widen or narrow, then size opposing legs by instrument-specific rate sensitivity. Recompute after material changes. Parallel-rate neutrality is approximate; curve twists, convexity, financing, and delivery-option changes remain.

ST061 — Yield-curve butterfly. Evidence H for the proposed implementation. Markets: three defined maturity points. Establish duration or factor-matched wing and belly weights and trade a specified curvature signal. Exit on normalization, deadline, or exposure breach. Hedging a parallel move does not remove slope, convexity, liquidity, or model-estimation risk.

ST062 — Treasury cash/futures basis. Evidence C [S27]. Markets: approved Treasury cash bonds and corresponding futures. Model delivery eligibility, conversion factors, accrued interest, financing, and cheapest-to-deliver behavior. Trade only after executable cash and futures quotes and margin stress pass. Repo repricing, liquidity demands, delivery options, and crowded unwinds can create substantial losses.

H. OPTIONS AND VOLATILITY STRUCTURES

ST063 — Covered call. Evidence C [S28, S29]. Markets: owned eligible underlying shares and properly sized calls. Specify strike selection, expiration, sale timing, and assignment handling; exit or roll under an evaluated rule. Premium reduces some cost but does not remove stock downside. Upside is capped, and early assignment can change dividends and holdings.

ST064 — Cash-secured put. Evidence C [S30]. Markets: eligible underlyings the account can fund upon assignment. Reserve the required cash, sell the defined put, and track expiration or early assignment. A high premium is not free income; a large underlying decline can produce substantial losses. Do not silently convert this into leveraged short-put exposure.

ST065 — Protective put. Evidence C [S31]. Markets: a defined underlying position plus compatible long puts. Specify hedge fraction, strike, tenor, and replacement schedule. Evaluate the insurance objective and ongoing premium cost. Protection depends on coverage and contract terms; gaps between expiries, exercise mechanics, and mismatched settlement can undermine the intended floor.

ST066 — Collar. Evidence C [S32]. Markets: owned underlying, a long put, and a covered short call. Match quantities and define expiration, strikes, and assignment policy. Evaluate downside protection alongside capped upside and costs. A nominally zero-premium collar is not cost-free and can create operational complications when one leg is exercised.

ST067 — Bull call debit spread. Evidence C [S33]. Markets: compatible calls on the same underlying and expiry. Buy the lower strike and sell the higher strike using a supported combination order when possible. Define thesis, exit, and expiration handling. An intact standard spread's payoff is bounded; legging and assignment can create different temporary exposures.

ST068 — Bear put debit spread. Evidence C [S34]. Markets: compatible puts on the same underlying and expiry. Buy the higher strike and sell the lower strike, then manage the complete spread under predefined rules. Evaluate net debit, liquidity, and payoff. A correct bearish direction alone may not cover premium, timing, and execution costs.

ST069 — Defined-risk credit spreads. Evidence C [S35]. Variants: bull put and bear call spreads, recorded separately. Sell one option and buy a farther out-of-the-money option with compatible terms. Require portfolio loss limits and reliable combined execution. Credit collected is not expected profit; gaps, expiration, assignment, and closing liquidity require explicit handling.

ST070 — Iron condor. Evidence C [S36]. Markets: compatible put and call credit spreads. Define wing width, placement, expiry, profit/exit rule, and aggregate Greeks. Measure losses under directional jumps and volatility changes. Four legs increase friction and operational complexity; a high proportion of small gains can coexist with poor overall returns.

ST071 — Long straddle or strangle. Evidence C for the straddle construction [S37], H for each forecasting rule and strangle adaptation. Buy the specified call and put combination before a defined movement or volatility thesis. Exit by thesis, time, or risk budget. Realized movement must overcome premium and costs; time decay and volatility repricing matter.

ST072 — Calendar or diagonal option spreads. Evidence C for the documented calendar [S38], H for the chosen diagonal and timing rules. Specify all expiries, strikes, underlying exposure, and front-leg management. Evaluate term-structure and Greek changes across scenarios. Different expiries introduce path, assignment, and volatility risks that a simple expiration payoff chart does not capture.

ST073 — Dispersion/correlation trading. Evidence H for the proposed implementation. Markets: an eligible index and a sufficiently representative constituent-option basket. Specify which volatility/correlation exposure is sought and hedge aggregate sensitivities. Keep research-only without institutional-quality chains, execution, and risk tools. Single-name jumps, changing weights, discrete dividends, and many-leg costs can defeat the model.

ST074 — Bounded volatility-risk-premium strategy. Evidence H for the proposed trade; variance-premium research provides context only [S39]. Markets: explicitly chosen listed options with bounded exposure. Compare a defensible volatility forecast with executable option pricing, then select a permitted structure and exit rule. Equity-return predictability research does not prove that this short-option strategy earns net profits.

I. BONDS, CREDIT, AND EMERGING-MARKET DEBT

ST075 — Bond carry and roll-down. Evidence C [S40]. Markets: eligible cash bonds or carefully specified substitutes; scope: weeks to months. Estimate coupon/accrual and movement along an assumed unchanged curve, net of financing. Rebalance by schedule and risk. A curve shift, default, call, or liquidity shock can outweigh modeled carry and roll-down.

ST076 — Corporate-credit value. Evidence R [S41]. Markets: bonds with reliable issue-level prices and issuer information. Rank spread compensation relative to a declared fundamental/default-risk model, controlling duration and liquidity. Exit through scheduled reranking or invalidation. Wide spreads can reflect genuine distress; stale marks and trading costs can distort an apparent bargain.

ST077 — Credit momentum. Evidence R for the studied style [S40]. Markets: supported corporate-bond universes; scope: months. Define whether momentum concerns total returns, excess returns, spreads, or linked equity information; evaluate each separately. Rebalance with turnover limits. Sparse trading, price marking, issuer events, and rate exposure can produce misleading signals.

ST078 — Credit carry. Evidence R for the studied style [S41]. Markets: eligible corporate bonds; scope: months. Measure specified spread and carry relative to duration, expected losses, and funding, then diversify issuer exposure. Exit by schedule or risk trigger. Larger yield is not larger assured profit; defaults and correlated liquidity stress can overwhelm accrual.

ST079 — Defensive credit. Evidence R for the studied style [S41]. Markets: eligible corporate bonds; scope: months. Define the quality, maturity, leverage, or risk features used and distinguish them from valuation. Construct a constrained portfolio with an explicit benchmark. Defensive selection can underperform in risk rallies and remains exposed to rate, liquidity, and issuer risk.

ST080 — Emerging-market sovereign bond styles. Evidence R for the source's hard-currency debt research [S42]. Markets: eligible sovereign bonds and supported hedges; scope: months. Specify value, momentum, carry, or defensive variants with country caps. Do not infer local-currency results from hard-currency evidence. Restructuring, capital controls, political events, and sparse quotes require separate modeling.

5D. TURN TEMPLATES INTO PRECISE, EXECUTABLE SPECIFICATIONS

For every template, produce a machine-readable StrategySpec and a concise human-readable strategy card. Required fields:

Identity: strategy_id, family_id, parent_variant_id, version, code_hash, economic_hypothesis, evidence_label, and implementation_state.

Evidence: source_ids, publication_dates, retrieval_dates, access_depth, originally_studied_universe, sample_dates, original_horizon, exact_source_rules_when_available, contradictory_findings, and differences_from_source.

Eligibility: asset_classes, instrument_types, venue_allowlist, jurisdiction/account constraints, minimum_liquidity, data_entitlements, borrow_requirements, derivative_permissions, margin_requirements, and required adapter capabilities.

Data: canonical_identifiers, fields, frequency, event_time, publication_time, ingestion_time, allowed_latency, adjustment_policy, missing_data_policy, warmup, and point_in_time_universe.

Rules: decision_schedule, indicator_definitions, formation_window, holding_horizon, entry_condition, entry_expiry, exit_condition, maximum_age, invalidation_condition, cooldown, order_types, hedge_rules, and all parameter bounds.

Economics: fees, spread, impact, financing, borrow, funding, roll_costs, conversions, assignment/exercise costs, and capacity assumptions. Keep execution costs separate from portfolio management fees or taxes.

Risk: proposed sizing method, scenario losses, gross/net exposure, factor exposures, liquidity limits, leverage eligibility, per-strategy budget, and interactions with the portfolio's accepted limits.

Lifecycle: current readiness, evaluation artifacts, evidence uncertainty, live authorization scope, monitoring requirements, automatic suspension conditions, reinstatement criteria, and last review.

An incomplete card is not executable. Missing values must remain missing, with a reason; do not invent data, source methods, fees, or performance.

Use the following implementation patterns to remove ambiguity. They are proposed research starting points unless explicitly identified as source-native rules:

1. Time-series momentum: define the trailing excess-return interval precisely and use only observations available before the decision. A twelve-month signal is a research starting point informed by the source, not an optimal setting for all instruments. Form direction from the sign, use lagged volatility for bounded sizing, and keep synthetic continuous futures separate from real contract execution.

2. Equity momentum: a candidate can rank returns from twelve months before formation through one month before formation, using a declared total-return convention. Specify rank thresholds, rebalance timing, holding overlaps, neutralization, and missing-history rules. Treat these choices as versioned parameters, not universal best settings. Include delisted companies and contemporaneous index membership.

3. Fundamental portfolios: a fiscal period end is not a publication timestamp. Admit a filing only after its availability time plus any required processing delay. Use the originally available values; later restatements belong to later snapshots. Define sector comparability, winsorization, missing-field treatment, rank calculation, and the effect of corporate reorganizations.

4. Pairs and residuals: define a residual such as log(P_A) minus a fitted intercept and beta times log(P_B). Estimate the relationship on past data and align the hedge with that exact formulation. An example research grid might include entry at |z| = 2, exit at |z| = 0.5, and a failure boundary near |z| = 4; these are unvalidated seeds. Add time and structural-break exits. Never average down without an explicitly bounded rule.

5. Opening-range variants: freeze high/low after a declared opening interval, then evaluate later quotes or completed bars. Five-, fifteen-, or thirty-minute intervals are candidate choices, not the method automatically established by the cited crude-oil paper. Define whether stop, limit, or next-quote execution is modeled. Resolve same-bar stop/target ambiguity conservatively and forbid hindsight fills.

6. Intraday closing momentum: preserve the cited signal's overnight component and local market clock. The first-half-hour signal and final-half-hour trade are separate intervals. Define auctions, half-days, halted sessions, transaction-cost assumptions, and the deadline for flattening. Evaluate any extension to another exchange or asset as a new implementation.

7. VWAP hypotheses: calculate cumulative session trade value divided by cumulative eligible volume using a named feed and session. Define how auctions, odd lots, or missing trades are handled. A standardized deviation needs a backward-looking dispersion estimate and a specified regime rule. Do not use the completed day's volume or VWAP to make an earlier decision.

8. FX carry: express returns in the account's reporting currency. For forwards, include contract maturity, forward points, settlement, and collateral; for rolling spot products, use the broker's actual financing schedule. Weekend or holiday accrual and base/quote direction must be explicit. Central-bank rates are contextual data, not a substitute for actual financing.

9. Crypto basis and funding: a simple dated-contract quote basis is F/S - 1, while a rough annualization multiplies by 365 divided by days to expiry. Label that as a gross quote, not a guaranteed annual yield. Model contract payout, spot financing, fees, collateral, margin, and settlement. For perpetuals, use scenario-based future funding, not one payment multiplied indefinitely.

10. Commodity spreads: store the exact contract months, units, multipliers, conversion ratios, roll policy, and delivery avoidance date. A back-adjusted continuous chart is unsuitable for valuing a currently executable calendar spread. Preserve seasonality without letting future inventory releases, finalized harvest data, or retrospectively selected contract pairs leak into the signal.

11. Rate hedges: for a two-leg first-order hedge, solve signed quantities so their total DV01 is close to the intended target. Use each actual instrument's sensitivity, not equal dollar notionals. For futures, include current delivery characteristics. Test residual slope and curvature exposure, financing changes, and feasible contract rounding before accepting the hedge.

12. Option verticals: for a standard intact debit vertical, expiration maximum loss is net debit times multiplier plus fees; for a standard intact credit vertical, it is strike width minus net credit, times multiplier, plus fees. Verify that contract terms match these assumptions. Model early assignment, physical settlement, pin risk, and legging separately; do not apply the intact-position bound after its legs change.

5E. MARKET ADAPTATION, DISCOVERY, AND SPECIALIZED METHODS

Maintain reusable indicator and feature components for moving averages, MACD, RSI, stochastic measures, Bollinger-style bands, ATR, ADX, rate of change, realized volatility, Donchian channels, VWAP, relative volume, and supported book statistics. An indicator is an input, not a complete strategy or evidence of profitability. Give each its calculation convention, warmup, event timing, and numerical checks.

Translate Ichimoku, harmonic-pattern, Fibonacci, order-block, fair-value-gap, smart-money, and similar named methods into precise, non-repainting hypotheses before admitting them to the registry. Do not label branding, popularity, visual appeal, or an influencer's claimed win rate as evidence. Reject methods that cannot be specified without hindsight.

Track other research domains as an expansion queue: overnight/intraday decomposition, earnings revisions, buybacks and issuance, index reconstitution, auction effects, public macro surprises, capital structure, convertible bonds, inflation-linked bonds, mortgage prepayment, volatility term structure, power, emissions, and freight. Admission requires a sourced hypothesis and a product-specific implementation plan; a list entry alone is not support.

Treat market making as a specialized research extension with inventory-aware quoting, measured queue behavior, adverse-selection estimates, cancellation limits, and a verified venue adapter. A mathematical quoting model is not evidence that a retail system can earn its theoretical spread [S43]. Do not build spoofing, wash trading, manipulative self-trading, or use of confidential information into any strategy.

For on-chain research, additionally require chain-specific settlement/finality, gas and failed-transaction costs, smart-contract and oracle dependencies, token transfer behavior, pool depth, and wallet permission boundaries. DeFi yields, liquidations, or cross-chain transfers must not inherit the safety or performance assumptions of a centralized spot trade.

Use machine learning as a precisely scoped estimation layer: return or risk forecasting, calibrated event probabilities, regime classification, anomaly detection, execution estimates, or portfolio ranking. Preserve the target, horizon, features, label availability, training window, and model version. Research on machine-learning asset pricing does not establish autonomous LLM stock-picking performance [S44].

A neural network, reinforcement learner, ensemble, or LLM is not a separate source of economic edge by name. Compare it with a simpler baseline using the same information and costs. Keep learning outside the live execution path. Do not let an agent rewrite a live strategy or enlarge its capital allowance because a few recent trades were profitable.

Separate portfolio and execution methods from alpha templates. Risk parity, volatility targeting, minimum variance, factor balancing, TWAP, VWAP scheduling, and participation limits can change implementation or risk; none should be displayed as a newly discovered profitable market anomaly.

5F. AUTOMATIC SELECTION AND CONTINUOUS REVIEW

The master coordinator should choose among currently eligible implementations, not whichever strategy has the highest advertised return or latest winning streak. Rank candidates using net expected economics with uncertainty, drawdown and tail behavior, turnover, liquidity, capital efficiency, diversification, operational reliability, and evidence quality.

Make ranking weights explicit, bounded, and versioned. Distinguish estimated probability calibration from the language model's confidence words. A low-evidence candidate cannot obtain a live capital allocation merely by producing an enthusiastic explanation.

Count all searched parameter sets, feature combinations, markets, and strategy variants when evaluating selection bias. Use an appropriate multiple-comparison or selection-adjustment method; the deflated Sharpe ratio is one documented research option with assumptions that must be checked [S45]. Ten similarly constructed variants are not ten independent confirmations.

Background evaluation must distinguish source replication, proposed adaptation, historical evaluation, live shadow observation, paper execution, and authorized live performance. A simulated fill is never labeled a live fill. Use realistic costs and publication timing; retain negative findings. Do not make me run these processes manually or create a fourth page.

Verify the same decision code and instrument semantics across evaluation and operation. Report where a simulator cannot represent queue priority, partial fills, market impact, outages, borrow, funding, or complex options behavior. A technically passing simulator is insufficient when these limitations dominate the strategy.

Monitor evidence at the correct horizon. A monthly strategy should not be retired because it did not trade during one afternoon. A high-frequency strategy with stale depth is ineligible immediately. Define minimum observation requirements and uncertainty by effective independent information, not raw tick count.

Maintain explicit reason codes, including INSUFFICIENT_DATA, SOURCE_METHOD_UNVERIFIED, EDGE_UNCERTAIN, COSTS_TOO_HIGH, CAPACITY_EXCEEDED, REGIME_UNSUITABLE, RELATIONSHIP_BROKEN, BORROW_UNAVAILABLE, FUNDING_UNFAVORABLE, PRODUCT_UNSUPPORTED, PERMISSION_MISSING, STALE_DATA, HEDGE_INCOMPLETE, and PORTFOLIO_LIMIT.

Use a portfolio exposure map before accepting a target. Several strategies can all be long equities, short volatility, long carry, or dependent on one venue even when their names differ. Netting orders does not erase strategy attribution or shared risk. Reserve capital and hedge capacity atomically.

Provide an automatic safe-idle outcome when no method qualifies. Cash is an eligible portfolio state. Fully automated operation must include knowing when not to trade.

5G. STRATEGY VISIBILITY WITHIN MY THREE PAGES

On AI Trading System, add an internal strategy panel showing eligible methods, current selections, market/horizon, evidence label, proposed or allocated capital, net exposure, recent verified outcomes, and why other methods are inactive. Separate published-study evidence from this installation's actual results.

On Agent Activity, show which research or trading agent owns each family, its latest completed job, source references, generated candidate, deterministic checks, and the next scheduled action. The displayed explanation should point to a traceable event, not a fabricated stream of thinking.

On Brokers & Accounts, show the strategy capabilities each connection actually enables: market data, shorting, futures, options, order combinations, margin, or other required features. A connected account does not imply permission for every instrument.

The speaking assistant should explain strategy actions using verified facts: what changed, which rule applied, what risk was accepted, and whether action actually executed. It should be able to say, for example, that a carry strategy is inactive because estimated financing exceeds the observed spread, without inventing numeric certainty.

5H. IMPLEMENTATION PRIORITY AND COMPLETION EVIDENCE

Populate the complete 80-template registry first, but do not run 80 unverified strategies live. Choose the first executable candidates according to available instruments, data, and permissions. A practical research order is liquid directional methods, diversified equity methods, rigorously hedged relative value, then specialist derivatives and institutional-access methods.

The catalog is complete when every template has a stable identity, evidence label, primary-source reference or explicit hypothesis status, native research horizon, dependencies, entry/exit outline, failure conditions, and a current implementation state.

A strategy implementation is complete only when its deterministic rules, data contract, costs, sizing proposal, risk checks, order behavior, attribution, restart behavior, and automatic monitoring are demonstrated. Mark all other entries as research, blocked, or unimplemented.

Completion of this software project does not require proving every catalog entry profitable. It requires a working application that can research, reject, implement, evaluate, and operate eligible methods honestly within the user's authorized scope.

6. AUTOMATIC VALIDATION AND CONTROLLED LEARNING

The system owns this entire workflow. I should not have to operate it.

Separate software correctness, execution correctness, and evidence of trading performance. Passing one does not prove the others.

Automatically check time alignment, indicator warmup, corporate actions where relevant, look-ahead leakage, survivorship effects, fill assumptions, fees, spreads, slippage, borrowing or funding charges, partial fills, latency, rejected orders, trading sessions, and liquidity limits.

Where historical evaluation is available, use chronological evaluation and genuinely held-out periods, track all tried variants, and apply appropriate controls for repeated strategy selection. Use live shadow observation and paper trading to inspect current behavior. Neither historical nor paper results guarantee live results.

Report sample size, period, market, costs, drawdown, net expectancy, exposure, turnover, execution quality, and uncertainty. Do not approve a strategy based only on win rate or a few favorable trades.

Define reproducible promotion criteria before evaluating a candidate. Keep weak, stale, insufficiently observed, or unsupported candidates in research or paper mode. No fixed number of trades or days magically proves an edge.

Make self-learning concrete: collect outcomes, compare predictions with observations, detect deterioration, propose updates, evaluate candidates separately, version them, and replace deployed versions only under the preauthorized promotion policy.

Permit bounded automatic changes inside an approved policy. Changes to capital limits, leverage permissions, allowed products, credentials, or execution code must not silently broaden the existing authorization.

Do not let the live bot rewrite its own execution or risk code. Use controlled releases and reversible migrations. Retain previous working versions and define rollback behavior.

Expose only a compact readiness state by default. Put detailed evidence inside an expandable panel on an existing page.

Keep learning and evaluation information available only as of the decision time. Separate publication time, provider arrival time, and local receipt time for news and revised economic data. Fit transforms and model parameters on the appropriate training portion rather than on the complete evaluation dataset.

Evaluate incremental contribution after fees, turnover, shared exposures, and compute costs. Compare complex models against simple baselines and the option of holding cash. More agents, more indicators, or more trades must earn their place through useful evidence.

Record a reproducibility package for each promoted version: code revision, data identifiers, configuration, model and prompt versions, random seeds where applicable, evaluation splits, assumptions, and a machine-readable result.

Adaptation should have bounded step sizes, minimum evidence requirements, and an explicit reversal policy. A short winning streak must not automatically increase leverage or capital. Deterioration can suspend new entries while existing positions continue under their defined management policy.

Distinguish explainable adaptation from claims of general intelligence. Retrieval of a document, a newly written prompt, and a genuinely trained statistical model are different actions and must be reported separately.

7. EXECUTION AND RISK ENGINE

Use one authoritative order-management service per account, with ownership controls that prevent two application instances from trading the same account simultaneously.

Maintain persistent order states covering intent, submission, acknowledgement, working, partial fill, filled, cancel requested, cancelled, rejected, expired, and unknown outcome. Normalize provider events without discarding their original identifiers.

Use durable intent records, unique client order identifiers where supported, and idempotent handling. If a submission times out, query broker state before retrying. Do not assume exactly-once delivery or submit a duplicate order because an acknowledgement was lost.

Reconcile on startup, reconnect, and regularly during operation. Broker records establish actual executions; local records establish the system's intended actions. Freeze new exposure when discrepancies are unresolved.

Before submitting or modifying exposure, check available balance, reserved funds, position limits, instrument eligibility, quantity increments, minimum notional, tick size, price plausibility, quote freshness, liquidity, spread, expected costs, session status, margin requirements where applicable, and all account-level risk limits.

Account for contract multipliers and conversion into the account's base currency. Reserve risk and capital atomically so simultaneous agents cannot overspend the same budget.

Require an exit policy and a maximum holding policy where applicable. Prefer broker-native protective orders when available. Clearly distinguish native protection from protection that depends on the local application remaining online.

Enforce configurable limits for allocated capital, per-position exposure, aggregate exposure, concentration, correlated exposure, daily loss, drawdown, order frequency, and maximum acceptable slippage. Start with leverage and unrestricted short selling disabled. Present draft limits for deliberate acceptance before live activation; do not invent a suitable personal risk tolerance.

Specify how daily loss is calculated, its timezone, treatment of unrealized losses, and treatment of deposits and withdrawals. A daily rollover or restart must not quietly erase a latched safety stop.

Distinguish these controls:
- Pause new entries: continue monitoring and managing existing positions.
- Cancel entry orders: cancel outstanding opening orders while retaining necessary protection.
- Stop automation: prevent new automated exposure and execute the preselected position-management policy.
- Flatten positions: submit appropriate closing orders and reconcile until the result is known.
- Emergency stop: latch the system against additional exposure and follow the documented emergency policy.

A request is not a completed action. Report outstanding orders and unclosed positions honestly. Closing may be unavailable during outages or market closures.

Use disconnect protection only after inspecting its venue-specific behavior. Some cancel-all mechanisms can also remove protective exits. Order cancellation does not itself close an existing position.

Handle external/manual trades according to a declared ownership policy. Do not unexpectedly liquidate holdings the application does not manage.

Implement a persistent runtime state machine. Keep account mode separate from system state: PAPER/LIVE identifies where orders go; BOOTING, RECONCILING, READY, RUNNING, PAUSED, DEGRADED, HALTED, and SHUTTING_DOWN identify operational readiness. An offline demonstration is a separate clearly labeled data source.

Record every transition with cause, actor or triggering event, timestamp, authorization reference, and the resulting permission to open or reduce exposure. The UI must show backend-confirmed state rather than assuming a button click succeeded.

Give failures a documented scope and severity. A research-worker crash may suspend research; a corrupted order ledger must halt new trading. One failed market feed should disable dependent strategies while unrelated verified feeds may continue within policy.

Represent unknown execution outcomes explicitly. Persist the intent before sending it, retain the provider response or timeout, and reconcile before choosing a retry. Deduplicate execution events by their provider-defined identity and handle cumulative versus incremental fill fields correctly.

Persist capital reservations with the order lifecycle. A cancellation request does not release reserved capital until the relevant outcome is established. Recalculate protection after partial fills without creating unintentional reverse positions.

Protect against simultaneous leaders using a deployment-appropriate lock or lease and a single controlled path to broker submission. A stale worker must lose access to execution when ownership changes. Do not claim a database lock can make external broker operations atomic.

Use available venue-native reduce-only, bracket, or OCO behavior only when supported for that instrument. Otherwise document and test the local emulation and its outage limitations. Never round an order upward beyond its authorized quantity or risk budget just to meet a minimum trade size.

Account for settled funds, borrow availability, trading halts, expiring contracts, price limits, and liquidation constraints when applicable. Stops are execution instructions; do not represent them as guaranteed loss caps unless the actual product contract provides that guarantee.

8. THE THREE PAGES

PAGE 1 — AI TRADING SYSTEM

Make this the main operating dashboard.

Show the master AI's concise operating summary, selected account, prominent PAPER/LIVE status, connection and data freshness, current regime, active strategies, and a plain explanation when the system is waiting.

Include Start, Pause New Entries, Stop, and Emergency Stop controls with clearly different behavior. Place consequential account and capital settings in a drawer.

Show account equity, cash, allocated capital, buying power where relevant, realized and unrealized P&L, fees, drawdown, and open exposure. Distinguish trading performance from deposits and withdrawals. Display instrument currency and base-currency conversion.

Provide useful charts of equity and drawdown plus selected instruments, open positions, pending orders, and a recent decision timeline. Show actual broker fills rather than optimistic animations.

Explain why trades were entered, reduced, exited, skipped, or blocked. Use structured evidence and concise explanations, not fabricated private reasoning transcripts.

Keep advanced strategy evidence, exports, diagnostics, and risk configuration accessible inside this page without adding routes.

PAGE 2 — AGENT ACTIVITY

Show every configured agent and what it is genuinely doing.

For each agent, display its role, implementation type, current state, current task, assigned market, latest input time, latest result, next scheduled action, elapsed time, recent errors, and resource or API cost where measurable.

States should include running, waiting for data, idle, paused, blocked, degraded, failed, and completed. Idle is an honest state.

Provide filters by team, asset class, status, and strategy, plus a searchable event timeline. Explain assignments, handoffs, disagreements, failed jobs, and resolved incidents.

Selecting an agent opens a detail drawer containing its recent jobs, evidence, output summaries, history, dependencies, allowed tools, and health. Restarting an analytics worker must not reset orders or duplicate broker actions.

Show aggregate active-agent counts, queue depth, feed freshness, last reconciliation, model availability, and cost budget. Clearly separate real workloads from demonstration data.

PAGE 3 — BROKERS & ACCOUNTS

Provide real connection flows and a capability matrix for each implemented provider.

Show provider, account identifier in masked form, region, mode, authentication status, last verification, supported products, data entitlements, order types, permissions, balances, and limitations.

Support connect, verify connection, refresh, reauthenticate, disconnect, and revoke locally stored credentials. Explain the state of open positions before disconnecting.

Keep paper and live credentials, endpoints, and execution state separate. Switching the selected dashboard account must not silently switch an active trading session.

The Add Funds action should open the broker's official funding interface or a genuinely supported authenticated funding flow. Do not collect card details or emulate a bank deposit in this application. A deposit must not automatically increase the trading allocation.

Enable live operation only after the account is eligible, connection checks succeed, data is suitable, limits are accepted, and I deliberately activate the chosen scope. Do not require confirmation for every routine trade afterward.

SHARED DESIGN REQUIREMENTS

Use a polished, readable control-room design: restrained dark surfaces, strong typography, clear spacing, accessible contrast, and purposeful color. Reserve prominent warning colors for real operational meaning. Make profit/loss and status understandable without relying on color alone.

Support the desktop as the main workspace and make all essential controls usable on smaller screens. Provide keyboard navigation, visible focus, readable charts, tooltips for unfamiliar metrics, and reduced-motion support.

Every component needs loading, empty, disconnected, error, stale, and healthy states where applicable. Use an explicit dash or "unavailable" for missing values, not a misleading zero. Mark each displayed timestamp and data delay clearly.

Keep the first-run journey inside the three existing pages: open in paper mode, select a data source, optionally connect an AI provider, inspect readiness, and start a paper session. Broker setup and voice setup use drawers. Show advanced options only when useful.

If no cloud AI key is configured, allow whatever deterministic or local-model functionality is genuinely available and clearly identify the missing AI capabilities. Do not display a simulated master brain as if it were connected to a reasoning model.

Provide a concise session report with actual trades, costs, blocked decisions, incidents, strategy changes, and remaining exposure. Exports belong inside existing pages and must label paper versus live records.

9. BROKER INTEGRATIONS AND ELIGIBILITY

Prioritize adapters suited to the existing project and the user's actual access:
- Interactive Brokers for supported securities, futures, currencies, and other permitted products.
- Kraken for eligible crypto spot markets.
- OANDA v20 for eligible accounts and instruments.
- Alpaca as an optional paper environment or supported live integration when account eligibility is verified.

These are integration candidates, not a promise that every provider or product is available to me. Verify Canadian/Alberta availability, account type, age requirements, product permissions, market-data subscriptions, and authentication requirements before offering activation.

Kraken currently lists Canada as ineligible for its derivatives service; recheck current official restrictions at implementation. Do not display restricted products as tradable.

If age or account eligibility blocks live access, retain a useful local simulation, research, and paper experience subject to provider terms. Never bypass identity verification, geographic restrictions, or age requirements.

Define an adapter interface for capabilities, instruments, quotes, balances, positions, orders, cancellations, updates, executions, connection health, and reconciliation. Preserve provider-specific differences instead of assuming universal features.

Check whether each provider has a suitable sandbox or paper environment. If it does not, use a clearly labeled local simulator; never describe simulated fills as exchange fills.

Build one complete end-to-end adapter first, then add others behind the same interface. Finish all integrations that can be completed and tested with available access. Clearly identify adapters that are implemented but not authenticated or independently verified.

Treat reconnect behavior as provider-specific. For example, IBKR TWS distinguishes a restored connection with lost data subscriptions from one with subscriptions maintained; implement the corresponding resubscription behavior. OANDA documents an initial account snapshot followed by updates using the last transaction identifier; preserve that checkpoint through recovery.

For each broker, maintain verified support flags for order modification, client order identifiers, fractional quantities, partial fills, protective orders, cancellation behavior, shorting, account updates, and real-time data. Unknown capability is different from supported capability.

Authentication success alone does not prove trading readiness. Distinguish reachable API, authenticated account, verified data entitlement, valid instrument permissions, reconciled positions, and authorized execution.

Do not promise indefinite unattended operation if the broker requires periodic reauthentication. Detect the approaching or actual interruption, preserve the current position policy, and present the specific required action.

10. JARVIS-INSPIRED SPEAKING ASSISTANT

Build a real conversational assistant connected to system events and authenticated application tools.

The intended voice is calm, articulate, British-sounding, composed, technically fluent, and lightly witty, with concise delivery and a subtle futuristic character. Avoid theatrical constant chatter.

Aim for the JARVIS experience and conversational character. Do not promise an exact movie-voice match from a text instruction. If an appropriately licensed and provider-approved matching voice is available, make it selectable. Otherwise use an available voice with the desired qualities. Follow the selected provider's consent and eligibility requirements for custom voices.

Do not claim to have watched a movie unless you actually accessed and reviewed it. Reference material may guide style; it does not establish technical capability.

After I enable proactive audio, let the assistant speak when meaningful events occur without needing a new message or a Speak button each time.

Separate listening permission, audio playback permission, proactive announcements, and trading authorization. Announcing events must work without requiring the microphone to remain active. Respect browser and OS permissions; explain any initial interaction required.

Support configurable proactive events: session start, meaningful position changes, risk-limit activation, feed or broker failures, recovered connections, important operational decisions, scheduled summaries, and an explicit request for attention.

Use priorities, deduplication, cooldowns, batching, quiet hours, volume controls, mute, and a transcript. Speak about fills only after confirmation. Announce reduced protection or unknown order outcomes urgently, using verified state.

Make the assistant interruptible. If I begin speaking, stop or duck playback, handle the interrupted turn correctly, and avoid hearing its own voice as a new command. Handle microphone failure, provider timeouts, reconnects, session expiration, and text-only fallback.

Provide a persistent compact voice control on all three pages. Show listening, speaking, muted, unavailable, and reconnecting states accurately.

Use a currently documented low-latency voice API and WebRTC where appropriate, or a measured speech-to-text -> language model -> text-to-speech pipeline. Keep the provider replaceable. Verify the current API generation and schemas; do not mix incompatible examples.

Keep permanent model and broker keys on the backend. Use supported short-lived session credentials or server-mediated session setup for the browser.

Build speech from structured application events. Each announcement event needs an event ID, category, severity, subject, factual payload, creation time, expiration time, deduplication key, and references to the underlying records.

Before speaking, verify that the announcement is still current. Suppress an old opportunity alert after its signal expires, combine repetitive fills into a useful summary, and replace superseded connection messages with the current condition.

Maintain an announcement lifecycle: queued, eligible, speaking, interrupted, delivered, superseded, or failed. Critical operational facts should appear in text even when voice is muted or unavailable.

Keep factual content separate from vocal style. The speech generator may simplify phrasing, but it must not change quantities, order states, account mode, or uncertainty. Use deterministic templates for urgent operational alerts if model generation fails.

Measure event-to-announcement delay separately from conversational response latency. Choose realistic targets based on the machine, provider, and network; publish the measurements and timeout behavior instead of claiming cinematic response speed.

11. VOICE TOOLS AND PERMISSIONS

Give the assistant narrow typed tools for verified status, agent activity, positions, recent decisions, risk state, costs, and connection health. Add allowed controls for navigation, pausing new entries, muting, summaries, and other explicitly authorized operations.

Examples it should answer using live tools:
- What are all the bots doing?
- Why did you take that trade?
- Why are you not trading?
- How much did fees cost today?
- Which strategies are under review?
- Pause new entries.
- Show my broker connection.
- Explain my current exposure.

A voice command must go through the same authorization and risk checks as the UI. Do not treat a familiar-sounding speaker as secure authentication.

Changing to live mode, increasing authorized capital or leverage, broadening permissions, or moving money requires the corresponding deliberate authenticated action. Use context-aware confirmation only for consequential or ambiguous commands, not routine status questions.

After a command, distinguish requested, accepted, completed, rejected, and unknown. Do not say "all positions are closed" while closing orders remain unfilled.

Never supply the voice model with API secrets. Send the minimum account information necessary for the response. Provide transcript retention and deletion controls; make raw audio recording opt-in.

Resolve references such as "that bot," "this trade," or "stop it" against the active page and recent conversation. If the target or consequence remains ambiguous, ask one short clarification. Never guess an account, symbol, amount, or destructive action from an unclear transcript.

Use a tool-result acknowledgement protocol: validate intent, authorize the operation, call the backend, receive a structured outcome, and then speak the matching confirmation. Attach a command ID so retries do not repeat a consequential action.

Provide a plain-language explanation policy: lead with the current fact, give the main reason, and identify any required action. For example, say "New entries are paused because the price feed is stale; existing broker-held exits remain active" only when those exits have actually been verified.

Proactive speech permission is revocable immediately. Turning off the microphone must stop input capture; muting speech must stop playback. Either control remains independent of trading state.

12. LOCALHOST, PACKAGING, AND RECOVERY

Run the application locally by default, bound to loopback rather than the public network. Localhost means the application server runs on my computer; broker access, live feeds, and cloud models still require their relevant network connections.

Provide one obvious launcher suitable for the operating system. On Windows, prefer a clearly named executable or Start Trading System.cmd with documented prerequisites. It should start the required services, check readiness, and open the browser.

One launcher does not mean one enormous source file. Keep the internal project modular, maintainable, and packaged cleanly.

Prevent duplicate launches from creating duplicate trading processes. Handle occupied ports, missing dependencies, expired credentials, failed migrations, and already-running services with actionable messages.

Run execution in backend services independent of the browser tab. State plainly that a local computer must remain running and connected for local automation. Never imply that browser audio or trading continues when the relevant host is asleep or off.

Persist orders, decisions, account configuration, evidence, checkpoints, and health incidents. On restart, reconcile before resuming new exposure. Do not replay expired signals.

Support orderly shutdown, health monitoring, bounded automatic restarts, backoff, local logs, recovery checkpoints, and backups. Resume only when previous authorization and operational readiness remain valid; latch unresolved incidents for review.

Provide separate explicit actions to close the dashboard and shut down the trading service. Closing a browser window must not accidentally imply that positions have been closed or that backend trading stopped.

Make installation repeatable with pinned dependencies, a versioned configuration, and an environment check. A launcher should not silently download and execute arbitrary code from unverified locations. Preserve configuration and secrets when upgrading, and report migrations before applying irreversible changes.

If remote/mobile access is later requested, treat that as a separate authenticated deployment requirement. Do not expose the local trading server publicly by changing its bind address and assuming that is sufficient.

13. ENGINEERING QUALITY AND SECURITY

Use a modular architecture suited to the existing codebase. Prefer a dependable local deployment over unnecessary distributed infrastructure.

Keep the database authoritative for durable application state. Use decimal-safe money and quantity handling, UTC internally, exchange calendars, and an explicit display/reporting timezone.

Separate feeds, feature calculations, research jobs, execution, reconciliation, and voice workloads so slow research cannot starve order protection.

Apply bounded concurrency, backpressure, data retention, caching, connection reuse, and sensible refresh intervals. Measure CPU, RAM, event lag, API cost, signal-to-order latency, and voice latency. Publish measured results rather than invented performance claims.

Set configurable API and compute budgets. Reduce optional research or chatter when budgets are reached; keep protective execution and reconciliation working.

Use secure local secret storage, masked credentials, minimum necessary permissions, redacted logs, authenticated local APIs, restricted origins, and protections against unauthorized browser requests to localhost.

Where supported, use trading-only credentials without withdrawal permissions. If a provider cannot separate permissions, disclose the scope and tightly constrain the application tools.

Treat news, research documents, broker error text, retrieved content, and market metadata as untrusted input. They cannot instruct the system to reveal secrets, change its rules, or execute commands.

Keep research sandboxed away from live credentials. Validate generated tool arguments, restrict filesystem and network access by role, pin dependencies, and version model prompts and strategy artifacts.

MARKET-DATA CONTRACT

Maintain canonical instrument identifiers including venue, product type, symbol, quote/base currencies where applicable, expiry, contract multiplier, price tick, quantity step, and current trading status.

Store provider event time and local receipt time separately. Record whether data is real-time, delayed, historical, synthetic, or incomplete. Use monotonic clocks for local durations and define freshness thresholds by strategy requirements.

Distinguish completed bars from developing bars. Resampling and higher-timeframe features must use only data available at the decision time. Warm up indicators explicitly. Do not silently interpolate missing market data into executable signals.

When consuming order books, apply snapshots and incremental updates according to the provider's protocol. Verify sequence continuity or checksums where available; quarantine a desynchronized book and rebuild it before using dependent signals. Kraken's WebSocket v2 documentation describes checksum and precision requirements; follow those exact rules when using that feed.

Preserve decimal precision for prices and sizes. Model bids, asks, trades, mark prices, and index prices as different data fields rather than interchangeable prices.

CORE DOMAIN CONTRACTS

Implement validated schemas for Instrument, MarketSnapshot, StrategySpec, AgentTask, SignalProposal, RiskDecision, OrderIntent, BrokerOrder, Fill, Position, ReconciliationResult, VoiceEvent, and AuditEvent.

Include account/mode scope where relevant, schema version, unique identity, timestamps, source references, and correlation IDs. A RiskDecision must include allowed/rejected status, reason codes, approved quantity, policy version, and expiry. An approved quantity is recalculated if material inputs change.

Use a durable event history and explicit state transitions sufficient to reconstruct an incident. Correlate a market snapshot with the resulting signal, decision, order, fills, position, and spoken explanation.

Provide recorded-event replay for engineering verification in an isolated environment. Replay must use test credentials or simulated adapters and must never route old events to live execution.

OBSERVABILITY AND ACCOUNTING

Expose metrics for job lag, stale feeds, lost events, model errors, order rejection, unmatched fills, reconciliation differences, failed protection, and restart count. Distinguish a healthy process from a healthy trading workflow.

Reconcile realized P&L, unrealized P&L, fees, financing, deposits, withdrawals, and conversions. Label estimates and delayed adjustments. Attribute shared costs consistently and do not double-count the same fill across several agents.

Set limits for logs, transcripts, data caches, and research artifacts. When disk capacity or database integrity is threatened, stop new exposure before losing the ability to record and reconcile it.

Never allow UI refreshes, chart rendering, or voice generation to become prerequisites for order protection. Apply explicit priority to execution monitoring and recovery.

14. IMPLEMENTATION ORDER AND COMPLETION CRITERIA

Work in dependency order:
1. Audit and stabilize the existing repository.
2. Complete persistent state, data flow, deterministic risk, and order lifecycle.
3. Deliver one complete paper workflow with actual event-driven agent activity.
4. Implement the master coordinator, registry, and automatic evaluation.
5. Finish exactly three polished pages.
6. Implement and verify broker adapters and optional live activation controls.
7. Add proactive voice, authenticated tools, interruption handling, and fallback.
8. Verify recovery, packaging, launch behavior, and documentation.

Use meaningful tests for concrete risks. At minimum demonstrate:
- A valid paper signal creates one intended order and correctly tracked fills.
- A risk-blocked or stale signal creates no order.
- A lost acknowledgement does not create duplicate exposure.
- Partial fills and cancellation races preserve consistent positions.
- Reconnection reconciles before new trading.
- Manual or external positions are handled according to the ownership policy.
- No LLM tool can bypass limits or access secrets.
- A model outage leaves protective management available.
- Exactly three top-level pages expose the intended features.
- Agent activity represents backend jobs.
- Proactive speech occurs after enablement, respects mute, and handles interruption.
- The launcher works from a fresh environment with documented prerequisites.

Use simulation or official test environments for verification. Do not spend real money, move funds, or place a live test order merely to prove the implementation works.

Extend the verification with a concise evidence matrix covering these failure scenarios:

| Scenario | Required observable behavior |
| --- | --- |
| Same signal is delivered twice | One intended exposure change; the duplicate is recorded or ignored safely. |
| Two agents compete for the remaining allocation | Atomic reservations prevent combined allocation from exceeding the accepted limit. |
| Broker accepts an order but the reply is lost | State becomes uncertain; reconciliation precedes any retry. |
| A fill arrives during cancellation | Holdings, remaining quantity, and protection reflect the actual fill. |
| Quote stream stops while the app stays online | Dependent new entries stop; UI freshness changes; current position policy continues. |
| An order-book checksum fails | Dependent signals stop until a valid book is rebuilt. |
| A worker crashes with outstanding orders | Order ownership and recovery preserve broker-state reconciliation. |
| The application is launched twice | The second instance cannot become another execution owner. |
| A broker requires login again | Readiness is withdrawn and the required authentication action is shown. |
| AI quota or voice access is exhausted | Optional reasoning or audio degrades; execution protection remains independent. |
| A document contains malicious instructions | It is treated as data and cannot authorize tools or disclose secrets. |
| A voice command is unclear | The assistant requests the missing target or scope before consequential action. |
| An old spoken alert is queued | It expires or is replaced when its underlying state changes. |
| Broker data differs from local holdings | New exposure is blocked within the affected scope until reconciled. |
| A live account receives a deposit | Available cash changes; the authorized allocation does not silently expand. |
| A daily limit trips before restart | Restart preserves the latched limit and its cause. |
| A market closes before flattening finishes | Remaining exposure is reported; completion is not fabricated. |
| No strategy passes current eligibility checks | The system stays idle and explains why without forcing a trade. |

Record the scenario, environment, fixture or provider evidence, expected result, observed result, and pass/fail status. Fix failures in the implementation rather than weakening the scenario. These checks establish specified software behavior, not future investment returns.

Demonstrate the user's complete journeys: launch and start paper automation; inspect an agent and trace its latest decision; connect or diagnose a broker; receive an event-triggered spoken update; interrupt and ask a grounded question; recover safely after a simulated disconnection.

15. DELIVER THE WORKING RESULT

Provide the updated application, the single launcher, concise setup instructions, an environment template without secrets, architecture notes, source register, agent inventory, broker capability matrix, validation evidence, and clear known limitations.

For each major capability, state whether it is implemented, tested locally, verified against a provider test environment, awaiting credentials, or blocked by provider/account access.

Do not call a mock connection production-ready. Do not display fabricated returns, confidence percentages, agent activity, or execution latency. Do not promise guaranteed profits, universal market mastery, perfect prediction, or zero risk.

Maintain a progress file and a runnable checkpoint during long work. If the execution environment limits progress, preserve the exact completed state and concrete remaining tasks rather than making a false completion claim.

Begin by inspecting the existing project, determining its actual agent count, and continuing implementation. Make the experience simple for me while making the underlying system measurable, recoverable, and honest about its limits.

---

RESEARCH NOTES FOR THIS PROMPT

Prepared October 8, 2026 (America/Edmonton). This is a software build specification, not a completed trading system or evidence that any strategy is profitable. The role allocation, architecture, interface, and acceptance criteria are proposed engineering requirements.

Revision 2 adds detailed runtime states, task and data contracts, all 50 optional role assignments, evidence-linked memory, provider-specific recovery, an announcement lifecycle, interface quality requirements, and an observable failure-scenario matrix.

Revision 3, updated October 9, 2026 (UTC), adds 80 strategy templates across nine groups, a market-coverage matrix, separate evidence and implementation labels, twelve detailed specification patterns, automatic selection rules, and a 47-source strategy register. This revision expands the prompt; it does not represent completed strategy implementations or verified live returns.

The request to avoid backtesting work is interpreted as no manual testing tasks or extra testing page; background validation remains automated. The existing repository has not been inspected in this prompt-writing task, so its actual agent count is deliberately left for the implementing assistant to determine.

Primary sources reviewed:

- Anthropic, How we built our multi-agent research system: multi-agent coordination and its cost tradeoffs.
  https://www.anthropic.com/engineering/multi-agent-research-system
- Interactive Brokers, API Solutions: documented trading and account interfaces; product access remains account-dependent.
  https://www.interactivebrokers.com/en/trading/ib-api.php
- Interactive Brokers, Market Data Subscriptions introduction: entitlement requirements for API data.
  https://www.interactivebrokers.com/docs/general/market-data-subscriptions/introduction
- Kraken, API key permissions: separate account, trading, and funding capabilities.
  https://docs.kraken.com/exchange/guides/rest/api-keys
- Kraken, Cancel on Disconnect: cancellation timeout behavior; not position liquidation.
  https://docs.kraken.com/exchange/api-reference/spot-websocket-v1/cancelallordersafter
- Kraken, Derivatives eligibility: current Canada restriction.
  https://support.kraken.com/articles/360023786632-kraken-derivatives-eligibility
- Kraken, Verification requirements: account eligibility including age 18 or older.
  https://support.kraken.com/articles/201352206-verification-level-requirements
- OANDA, v20 introduction: API access requires an eligible v20 account.
  https://developer.oanda.com/rest-live-v20/introduction/
- Alpaca, Paper Trading: simulated execution and differences from live trading.
  https://docs.alpaca.markets/us/docs/paper-trading
- OpenAI, Realtime conversations: audio conversations, tool calls, and interruption handling.
  https://developers.openai.com/api/docs/guides/realtime-conversations
- OpenAI, WebRTC: server-mediated setup and short-lived credentials.
  https://developers.openai.com/api/docs/guides/voice-webrtc
- OpenAI, Custom voices: provider eligibility and voice-consent requirements.
  https://developers.openai.com/api/docs/guides/custom-voices
- MDN, Autoplay guide: browser restrictions on unprompted audio playback.
  https://developer.mozilla.org/en-US/docs/Web/Media/Guides/Autoplay
- MDN, getUserMedia: microphone access permissions.
  https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getUserMedia
- Moskowitz, Ooi, and Pedersen, Time Series Momentum: research on specified markets and longer horizons, not proof of a five-minute trading edge.
  https://www.aqr.com/Insights/Research/Journal-Article/Time-Series-Momentum
- Bailey, Borwein, Lopez de Prado, and Zhu, The Probability of Backtest Overfitting: risk of false discoveries through repeated strategy selection.
  https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf

Provider documentation can change. Reverify current schemas and account availability during implementation. The strategy catalog above is a research scope, not a list of individually verified profitable strategies.

Additional primary sources reviewed for revision 2:

- Kraken, Book checksum (WebSocket v2): synchronized book maintenance and decimal precision.
  https://docs.kraken.com/exchange/guides/websockets/book-checksum-v2
- Interactive Brokers, TWS System Message Codes: different recovery behavior after lost versus maintained data subscriptions.
  https://www.interactivebrokers.com/docs/tws-api/doc/error-handling/system-message-codes
- OANDA, Best Practices: initial account state and updates using the most recent transaction identifier.
  https://developer.oanda.com/rest-live-v20/best-practices/

STRATEGY SOURCE REGISTER — REVISION 3

Reviewed October 9, 2026 (UTC). The codes in section 5 link to the primary sources below. These are research papers, author summaries, official data methods, or regulator/exchange/industry documentation. An asset manager's research is primary author evidence, not an independent certification of performance.

Access labels: A = abstract or author/publisher research summary reviewed; P = paper text or excerpts reviewed, without a full replication audit; M = relevant mechanics or methodology documentation reviewed; B = bibliographic identification only. No study was replicated and no strategy performance was independently computed in this prompt-writing task. The implementing research agent must obtain full methods and exact sample details before claiming replication.

| Code | Primary source | Scope and access |
| --- | --- | --- |
| S01 | [Moskowitz, Ooi, and Pedersen — Time Series Momentum](https://www.aqr.com/Insights/Research/Journal-Article/Time-Series-Momentum) | A; source family and horizon |
| S02 | [Asness, Moskowitz, and Pedersen — Value and Momentum Everywhere](https://www.aqr.com/insights/research/journal-article/value-and-momentum-everywhere) | A; cross-market evidence |
| S03 | [Moreira and Muir — Volatility Managed Portfolios](https://www.nber.org/papers/w22208) | A; portfolio-level evidence |
| S04 | [Koijen, Moskowitz, Pedersen, and Vrugt — Carry](https://www.aqr.com/insights/research/journal-article/carry) | A; conditional carry and risk |
| S05 | [Daniel and Moskowitz — Momentum Crashes](https://www.nber.org/papers/w20439) | A; adverse regimes |
| S06 | [Kenneth French — Fama/French Five Factors construction](https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/Data_Library/f-f_5_factors_2x3.html) | M; factor definitions |
| S07 | [Asness, Frazzini, and Pedersen — Quality Minus Junk](https://www.aqr.com/Insights/Research/Working-Paper/Quality-Minus-Junk) | A; quality family |
| S08 | [Frazzini and Pedersen — Betting Against Beta](https://www.aqr.com/insights/research/journal-article/betting-against-beta) | A; beta-scaled portfolios |
| S09 | [Kenneth French — Data Library, including short-term reversal](https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/data_library.html) | M; published factor datasets |
| S10 | [Bernard and Thomas — Post-Earnings-Announcement Drift: Delayed Price Response or Risk Premium?](https://www.jstor.org/stable/2491062) | B; article identified through publisher issue listing |
| S11 | [Mitchell and Pulvino — Characteristics of Risk and Return in Risk Arbitrage](https://www.aqr.com/Insights/Research/Journal-Article/Characteristics-of-Risk-and-Return-in-Risk-Arbitrage) | A; merger-arbitrage evidence |
| S12 | [Holmberg, Lönnbark, and Lundström — Assessing the Profitability of Intraday Opening Range Breakout Strategies](https://swopec.hhs.se/umnees/abs/umnees0845.htm) | A; crude-oil threshold method |
| S13 | [Gao, Han, Li, and Zhou — Market Intraday Momentum](https://www.sciencedirect.com/science/article/pii/S0304405X18301351) | A; abstract and article excerpts |
| S14 | [Avellaneda, Reed, and Stoikov — Forecasting Prices from Level-I Quotes in the Presence of Hidden Liquidity](https://math.nyu.edu/faculty/avellane/hiddenliquidity.pdf) | P; short-horizon price relationship |
| S15 | [Gatev, Goetzmann, and Rouwenhorst — Pairs Trading: Performance of a Relative-Value Arbitrage Rule](https://academic.oup.com/rfs/article-abstract/19/3/797/1646694) | A; historical distance-based pairs |
| S16 | [Avellaneda and Lee — Statistical Arbitrage in the U.S. Equities Market](https://math.nyu.edu/inmemoriam/avellaneda/AvellanedaLeeStatArb20090616.pdf) | P; ETF/PCA residual methods |
| S17 | [SEC — Exchange-Traded Funds investor bulletin](https://www.sec.gov/investor/alerts/etfs.pdf) | M; creation/redemption access |
| S18 | [Brunnermeier, Nagel, and Pedersen — Carry Trades and Currency Crashes](https://www.nber.org/papers/w14473) | A; currency carry downside |
| S19 | [Menkhoff, Sarno, Schmeling, and Schrimpf — Currency Momentum Strategies](https://www.bis.org/publications/working-paper-366-currency-momentum-strategies) | A; costs and limits to capture |
| S20 | [Liu and Tsyvinski — Risks and Returns of Cryptocurrency](https://www.nber.org/papers/w24877) | A; sampled crypto evidence |
| S21 | [Liu, Tsyvinski, and Wu — Common Risk Factors in Cryptocurrency](https://www.nber.org/papers/w25882) | A; shared crypto factors |
| S22 | [BIS — Crypto Carry](https://www.bis.org/publications/working-paper-1087-crypto-carry) | A; dated-futures basis research |
| S23 | [Makarov and Schoar — Trading and Arbitrage in Cryptocurrency Markets](https://mitsloan.mit.edu/cfi/trading-and-arbitrage-cryptocurrency-markets) | A; venue segmentation |
| S24 | [Gorton, Hayashi, and Rouwenhorst — The Fundamentals of Commodity Futures Returns](https://www.nber.org/papers/w13249) | A; inventory and curve research |
| S25 | [CME Group — Why Smart Money Trades Spreads](https://www.cmegroup.com/education/articles-and-reports/why-smart-money-trades-spreads-a-three-part-series) | M; spread mechanics |
| S26 | [CME Group — Calibrating Treasury Link: DV01-Weighted Spreads](https://www.cmegroup.com/articles/2026/calibrating-treasury-link-dv01-weighted-spreads.html) | M; rate-sensitivity sizing |
| S27 | [CME Group — Beyond the Basis Trade: Spreading Cash and Futures Using Treasury Link](https://www.cmegroup.com/articles/2026/beyond-the-basis-trade-spreading-cash-and-futures-using-treasury-link.html) | M; cash/futures construction |
| S28 | [Options Industry Council — Covered Call](https://www.optionseducation.org/strategies/all-strategies/covered-call-buy-write) | M; position mechanics |
| S29 | [Cboe — BuyWrite Indices Methodology](https://cdn.cboe.com/api/global/us_indices/governance/BXM_Methodology.pdf) | M; index construction, not achieved investor returns |
| S30 | [Options Industry Council — Cash-Secured Put](https://www.optionseducation.org/strategies/all-strategies/cash-secured-put) | M; assignment and funding |
| S31 | [Options Industry Council — Protective Put](https://www.optionseducation.org/strategies/all-strategies/protective-put-married-put) | M; protective structure |
| S32 | [Options Industry Council — Collar](https://www.optionseducation.org/strategies/all-strategies/collar-protective-collar) | M; protective structure |
| S33 | [Options Industry Council — Bull Call Spread](https://www.optionseducation.org/strategies/all-strategies/bull-call-spread-debit-call-spread) | M; standard payoff |
| S34 | [Options Industry Council — Bear Put Spread](https://www.optionseducation.org/strategies/all-strategies/bear-put-spread) | M; standard payoff |
| S35 | [Options Industry Council — The Wheel Strategy and Credit Spreads](https://www.optionseducation.org/news/june-key-takeaways-the-wheel-strategy-and-credit-spreads) | M; credit spread constructions |
| S36 | [Options Industry Council — Short Condor (Iron Condor)](https://www.optionseducation.org/strategies/all-strategies/short-condor) | M; four-leg structure |
| S37 | [Options Industry Council — Long Straddle](https://www.optionseducation.org/strategies/all-strategies/long-straddle) | M; premium and movement |
| S38 | [Options Industry Council — Long Call Calendar Spread](https://www.optionseducation.org/strategies/all-strategies/long-call-calendar-spread-call-horizontal) | M; expiration mismatch |
| S39 | [Bollerslev, Tauchen, and Zhou — Expected Stock Returns and Variance Risk Premia](https://www.federalreserve.gov/econres/feds/expected-stock-returns-and-variance-risk-premia.htm) | A; equity-return research context |
| S40 | [Asvanunt, Brooks, and Richardson — Style Investing in Fixed Income Markets](https://www.aqr.com/-/media/AQR/Documents/Insights/Journal-Article/Style-Investing-in-Fixed-Income-Markets.pdf) | P; fixed-income style overview |
| S41 | [AQR — Systematic Credit Investing](https://www.aqr.com/-/media/AQR/Documents/Insights/White-Papers/Systematic-Credit-Investing.pdf) | P; credit style research |
| S42 | [AQR — Systematic Investing in Emerging Market Debt](https://www.aqr.com/-/media/AQR/Documents/Journal-Articles/AQRJFIFall20SystematicInvestinginEmergingMarketDebt.pdf?sc_lang=en) | P; hard-currency sovereign evidence |
| S43 | [Avellaneda and Stoikov — High-Frequency Trading in a Limit Order Book](https://math.nyu.edu/inmemoriam/avellaneda/HighFrequencyTrading.pdf) | P; theoretical market-making model |
| S44 | [Gu, Kelly, and Xiu — Empirical Asset Pricing via Machine Learning](https://www.nber.org/papers/w25398) | A; statistical model evidence |
| S45 | [Bailey and López de Prado — The Deflated Sharpe Ratio](https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf) | P; selection-bias methodology |
| S46 | [CME Group — Introduction to Crack Spreads](https://www.cmegroup.com/education/articles-and-reports/introduction-to-crack-spreads) | M; refining ratios and units |
| S47 | [CME Group — Soybean Crush Spreads](https://www.cmegroup.com/trading/agricultural/grain-and-oilseed/soybean-crush-spreads.html) | M; processing ratios and units |

The 80 cards intentionally omit promised returns, fixed win rates, and claims of universal superiority. Many sources are historical. Current fees, funding, permissions, contract terms, and market conditions must be verified from current official documentation and actual account data during implementation. Read any inaccessible full paper before claiming to reproduce its exact method.



