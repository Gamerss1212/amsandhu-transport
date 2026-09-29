# Crypto and Stock Day Trading: Software Knowledge Handbook

Research edition 2.0 • Reviewed 28 September 2026 UTC

This handbook and its companion files are a broad public-knowledge foundation for building a trading research system. They are not an exhaustive record of every private strategy, a trained prediction model, a live trading bot, or evidence that any included template is profitable. No historical price dataset was supplied or backtested for this task. All catalogue performance fields are intentionally null.

The catalogue contains 320 records in 33 families, including research strategies, model frameworks, market making and execution methods. A variant is not a newly discovered independent edge. Some carry, futures, options and AMM concepts are adjacent to day trading and may involve longer holding periods. The final pattern entry deliberately groups three subfamilies that need separate implementations.

Sources are keyed as S01–S77 in `source_registry.json` and `Sources.md`. Source coverage ranges from reviewed official search excerpts to selected page passages and paper abstracts; the registry states the depth. Citations support the specified definitions, mechanics or research context. The catalogue's exact proposed rules are original research templates, not exact reproductions of those sources or source-endorsed trading recommendations.

## 1. What a trading system actually needs to know

Day trading generally opens and closes exposure within the same trading day or defined session. A crypto system needs an explicit session convention because trading can continue around the clock. Scalping describes short holding periods, not a unique strategy. Swing trading holds longer; investing has different objectives and evaluation horizons.

A complete strategy specifies the eligible universe, observable information, market regime, signal, entry timing, order type, position size, protective limits, profit or time exits, and conditions under which it must do nothing. An indicator computes a feature. A signal proposes an action. A portfolio rule allocates risk across signals. An execution method implements an already approved action. Confusing these layers makes software impossible to evaluate cleanly.

The system needs five distinct knowledge classes:

1. **Market facts:** contract units, order rules, settlement, sessions and fees. These are venue- and date-dependent.
2. **Mathematical definitions:** returns, volatility, indicators, exposure and performance calculations.
3. **Hypotheses:** proposed reasons a rule might earn returns after costs. Plausibility does not establish an edge.
4. **Empirical results:** actual dataset, code version, sample period, costs, sample size and uncertainty. None are manufactured in this pack.
5. **Operating constraints:** permissions, maximum exposure, stale-data rules, emergency procedures and audit records.

The correct output of a research engine is often “insufficient evidence” or “no trade.” Storing more text in a language model does not create new market observations, private order flow, faster execution, or profitable forecasts.

## 2. Stock and crypto market mechanics

| Area | Stocks and ETFs | Crypto spot and derivatives | Software implication |
|---|---|---|---|
| Identity | Share class, listing, issuer, corporate actions | Token contract, chain, venue symbol, spot or derivative | Never use ticker text alone as a permanent identifier |
| Sessions | Exchange calendars, auctions, holidays, early closes | Often continuous, with maintenance and product-specific sessions | Maintain a versioned venue calendar |
| Price formation | Fragmented trading venues and quote feeds | Separate books and pools with fragmented capital | Record exactly which venue and feed produced each price |
| Long exposure | Shares or fund units | Tokens or contract exposure | Verify quantity units and contract multipliers |
| Short exposure | Borrow, locate, recalls and restrictions | Margin borrow or a derivative where permitted | Verify permissions and actual availability before generating an order |
| Settlement | Often T+1 for covered US securities | Internal venue balances, chain settlement, contract-specific cash flows | Separate economic position, available cash and settled assets |
| Financing | Margin interest, borrow charges | Borrow interest, funding, collateral and conversion costs | Reprice financing and maintain collateral ledgers |
| Extraordinary events | Halts, corporate actions, delisting, auctions | Delisting, chain halt, token migration, depeg, venue outage | Have explicit exceptional states |

NYSE's core stock session is 09:30–16:00 America/New_York, with published holiday and early-close exceptions. Extended sessions differ by venue and broker. A US holiday calendar is not a Canadian exchange calendar. Use timezone-aware calendars instead of fixed UTC offsets. [S04, S09]

US standard settlement for covered securities moved to T+1 in May 2024. Settlement timing does not itself define whether an order is affordable or permitted. Cash-account logic needs settled-cash and broker-specific payment controls; margin accounts need current buying-power and risk checks. [S03]

Spot tokens, linear perpetual contracts, inverse perpetual contracts, dated futures, options and leveraged tokens are different instruments. They cannot share a single unqualified position-size or P&L formula. A stablecoin quote currency is an exposure, not guaranteed cash. A tokenized stock should not automatically inherit the rights, liquidity or session behavior of an exchange-listed share.

US equity shorting must incorporate the broker's locate and borrow processes and applicable short-sale restrictions. Historical borrow availability cannot be assumed from current availability. A profitable hypothetical short is not executable evidence when no borrow existed. [S07, S08]

Corporate-action processing needs effective timestamps and appropriate price/quantity adjustments for splits, dividends, mergers, spin-offs and symbol changes. Store raw prices for execution simulation and an explicitly documented adjusted series for research where appropriate. Never simulate a historical fill at a back-adjusted synthetic price.

## 3. Current rules that must not be hard-coded forever

As of this research date, FINRA's replacement intraday margin framework became effective on 4 June 2026. Brokerage firms have a transition period through 20 October 2027. Under the new framework, the old trade-count PDT designation and USD 25,000 PDT minimum are removed, but a transitioning firm may still operate under old requirements. New-framework margin and broker house requirements still apply. Therefore store the firm's actual adopted regime, effective date and account limits; never infer universal access from the rule change. This is a US broker framework, not a universal Canadian or crypto rule. [S01]

For Canadian use, verify the platform's registration and permitted product scope with the CSA and the applicable provincial regulator, as well as the account's broker terms. The existence of an API or an overseas website does not establish eligibility. Identity, age, residence, account type and product permissions belong in the authorization layer. [S10, S11]

CRA explains that crypto disposals can generate business income or capital gains depending on the facts, including transaction frequency, short holding periods, market knowledge and other circumstances. Crypto-to-crypto exchanges may be dispositions; transfers between wallets you own generally differ. Preserve CAD valuations, fees, acquisition/disposal records and transfer links for tax analysis. Do not hard-code “all trading is capital gains,” “all gains are tax free in a registered account,” or a permanently fixed tax treatment. [S12]

Pump-and-dump coordination is a recognized danger in thinly traded tokens. The bot should not participate in manipulation, wash trading, spoofing, or deceptive promotion. Suspicious price/volume bursts are grounds for investigation or exclusion, not proof of a low-risk opportunity. [S13]

## 4. Data: the first source of hidden errors

Collect data at the resolution the hypothesis requires. OHLCV can support many bar-based prototypes, but it cannot reveal exact trade ordering within a candle, queue position, hidden liquidity, or every price-level interaction. Quotes add spread and executable-side information. L2 adds aggregate depth; L3 can add individual visible order events where available. A trade tape is not the same thing as a quote feed.

Store at least three times: when the market event occurred, when the provider published it if known, and when your system received it. A backtest may use only information available by the simulated decision time. A beautifully aligned dataset that uses revised values or delayed news as though they were instantly known can be worse than no dataset.

Keep raw immutable events. Build a normalized layer with stable instrument IDs, decimal price/quantity rules, UTC timestamps, feed identifiers, sequence numbers, event types, quality flags and source versions. Keep trade corrections, cancellations, exchange status, symbol changes and late-arriving data instead of silently overwriting history.

Required quality checks include duplicate trade IDs, out-of-order events, sequence gaps, stale quotes, negative sizes, crossed books under venue-specific rules, unexpected price scales, timestamp drift, missing sessions, zero-volume bars and unavailable markets. Missing is not automatically zero. Zero activity is not an excuse to invent a trade. Repairs must be recorded.

For order-book feeds, use the documented snapshot-plus-update sequence and recovery rules. When state cannot be reconciled, mark the book invalid, block new risk and obtain a fresh synchronized state. Coinbase documents separate market and user-order streams and a level2 feed; implementing one venue does not establish compatibility with another. [S14, S15]

Point-in-time stock universes should retain delisted and failed companies. Crypto universes should retain dead tokens and historical listings where reliable data exists. Use liquidity measured before selection, not a present-day list of survivors. Record venue coverage gaps and the portion of each universe excluded because reliable data was unavailable.

News requires publication, update and receipt times, issuer mapping, duplicate clustering and source authenticity. SEC EDGAR provides filings and extracted XBRL information; this is a source for issuer facts, not automatically a low-latency event-trading feed. FRED vintage dates help distinguish historical versions of macro series. First release values and actual availability matter. [S42, S43]

Historical data, exchange redistribution rights, news licenses, storage rights and model-training rights can differ. Record the license and permitted use of every dataset. Publicly visible information is not automatically licensed for bulk commercial redistribution or unrestricted training.

## 5. Features and indicators

`feature_dictionary.json` defines the key numerical features with timing and implementation pitfalls. A formula is not a trading recommendation. Parameters such as 14-period RSI, 20-period bands or a 5-minute bar are conventions and research choices; none are universal optimum settings.

Useful categories are price returns, trend, momentum, volatility, liquidity, participation, cross-asset relationships, derivatives positioning and events. Avoid treating several transformations of the same closing prices as independent evidence. Ten correlated indicators do not multiply into a 90% probability of winning.

Choose indicator conventions explicitly: input price, bar interval, session definition, initialization, smoothing, warm-up length, missing data and rounding. An EMA's initialization and recursive history can change its early values. Test consistency between historical computation and the live streaming implementation. [S24, S40]

For multi-timeframe signals, the higher-timeframe candle must be available at the decision time. A 10:05 decision cannot use the completed 10:00–11:00 hourly close. Pivots confirmed with bars to their right become known later than the pivot's plotted timestamp. Retain both the pivot time and the confirmation time. Unconfirmed values, higher-timeframe requests and retrospective plotting can cause live/historical discrepancies. [S38]

VWAP requires an anchor and a definition of eligible volume. Trade-based VWAP and typical-price candle approximations differ. Relative volume should compare like-for-like elapsed session time. Order-flow delta should use documented aggressor direction, not invent buy/sell activity from candle color. Volume profile needs trades at prices or a clearly labeled approximation.

Fundamentals can define event context or a tradable universe, but quarterly accounting ratios rarely explain a sub-second execution decision by themselves. On-chain flows, social sentiment, wallet labels and liquidation heatmaps are noisy proxies with vendor assumptions. They need point-in-time availability and independent predictive testing.

## 6. Strategy taxonomy and evidence

| Family | Hypothesized source of return | Data burden | Main way it fails |
|---|---|---|---|
| Trend and momentum | Persistence of movement or information absorption | Bars, quotes, benchmarks | Choppy or reversing conditions |
| Breakout | Movement after a boundary or volatility change | Bars, frozen levels, quotes | False breaks and expensive entry |
| Mean reversion | Temporary displacement around a stable reference | Bars, quotes, regime/context | The reference changes permanently |
| Relative value | Convergence or lag among linked exposures | Synchronized multi-asset data | Relationship and hedge failure |
| Events | Delayed or excessive response to new public information | Timestamped events and quotes | Event already priced or received too late |
| Order flow | Short-horizon demand/liquidity information | Sequenced trades and depth | Latency, queue error and adverse selection |
| Arbitrage and carry | Executable relative prices or compensation for financing | Every leg, depth, funding, inventory | Frictions, settlement and collateral losses |
| Market making | Spread/fee compensation for supplying liquidity | Book replay and inventory model | Toxic fills and inventory accumulation |
| Machine learning | Predictive structure conditional on observed inputs | Causal labels, features and execution data | Leakage, overfitting and drift |
| Execution methods | Lower cost of implementing an approved order | Quotes, fills and deadlines | Delay, impact and non-completion |
| Pattern formalizations | Proposed recurring price geometry | Causal objective labels | Hindsight and discretionary relabeling |

The accompanying catalogue gives the setup, entry, exit/invalidation, data requirements, candidate regime, parameters to freeze, failure modes, and validation requirements for every template. Implement only a small number at first so that the simulator and accounting can be understood. This is an engineering sequencing judgment, not a profitability ranking.

Some papers establish useful concepts without validating these exact strategies. Lo, Mamaysky and Wang illustrate computational technical-pattern research. Gatev and coauthors study historical pairs trading. Cont and coauthors analyze short-horizon order-book events. Avellaneda and Stoikov study stylized inventory-aware quoting. Makarov and Schoar study crypto segmentation and arbitrage frictions. DeepLOB studies book-based prediction. Different populations, dates, horizons, access and costs prevent simply transferring their conclusions to a new bot. [S28–S33]

Barber and coauthors' study of Taiwan from 1992–2006 finds negative aggregate after-fee day-trader performance and widespread losses. It is evidence against casually assuming easy trading income, not a current universal failure percentage for every market or algorithm. [S34]

Popular labels such as smart money concepts, liquidity sweeps, order blocks, fair-value gaps, Wyckoff phases, Fibonacci ratios, harmonics and Elliott waves must be translated into reproducible rules. A name does not demonstrate institutional intent or causal price prediction. The included pattern templates are explicitly unvalidated hypotheses. Astrology, numerology, guaranteed-profit schemes and unsupported win-rate claims are not evidence-based additions to a trading engine.

## 7. Orders, fills and transaction costs

A market order prioritizes immediate execution under the venue's rules but does not lock a price. A limit order constrains price but may never fill. A stop commonly becomes a market order after its trigger; a stop-limit adds a limit and can remain unfilled during a fast move. Venue rules determine trigger reference, supported order types and session availability. [S02]

Record time-in-force, post-only, reduce-only, stop reference, client order ID, exchange order ID, parent/child links, cumulative fill quantity and actual fees. IOC, FOK, day, GTC, auction and bracket orders are not universally available. OCO and synthetic brackets may have race conditions. Cancel requested is not cancel confirmed. A cancelled remainder does not undo prior partial fills. [S17]

Two accounting conventions are possible:

- **Actual-fill simulation:** bid/ask execution prices already contain spread effects. Deduct explicit fees, financing and any additional modeled price impact only once.
- **Mid-price research approximation:** separately charge spread crossing, expected impact, latency slippage, fees and financing. Clearly label it an approximation.

Do not deduct the same spread or slippage twice. Conversely, “zero commission” does not mean zero trading cost. Maker rebates should only be credited when the actual venue tier and qualifying fill conditions justify them. A posted order is not automatically a maker fill.

Estimate costs by instrument, venue, time of day, order size, volatility, fee tier and order type. Historical fee tiers should reflect past trading activity rather than today's best fee tier. Include partial fills, unfilled orders, minimum charges, currency conversion, borrow, funding, market-data fees and applicable regulatory fees in the correct performance layer.

For passive fills, touching the limit price is not enough to guarantee execution. Model displayed volume ahead, cancellations, hidden-liquidity uncertainty and the order's arrival time. If the necessary data is absent, use pessimistic assumptions and expose the uncertainty. For aggressive fills, consume realistic depth and cap participation. A large order cannot fill entirely at a displayed best price with insufficient size.

If a candle touches both stop and target, OHLC does not reveal which happened first. Use finer data or a documented conservative ambiguity policy; never automatically choose the winning sequence. A strategy evaluated at bar close cannot receive a fill at that same close unless a causally valid execution mechanism and timing support it. TradingView's emulator is useful but not a substitute for a venue-aware fill model. [S37]

## 8. Risk and position sizing

Use an independent deterministic risk engine. Signals and language models may propose actions; they should not change hard account limits, permissions, credentials or accounting records. Define separate limits for per-trade planned loss, total open risk, gross and net exposure, symbol/sector exposure, correlated strategy groups, venue collateral, borrow usage, maximum inventory, daily loss and drawdown.

For a linear instrument, a simple risk sizing approximation is:

`quantity = floor_to_lot((risk_budget - fixed_cost_reserve) / (abs(entry - stop) * multiplier + variable_stress_cost_per_unit))`

Apply notional, liquidity, buying-power and concentration caps afterward. Reject nonpositive denominators, insufficient budget, unknown units or an invalid stop direction. This estimates loss near the stop; gaps, halts and failed execution can cause larger losses. Inverse contracts and options need their own valuation functions.

Illustration only: equity of USD 10,000 and a hypothetical 0.25% planned-risk budget gives USD 25. A USD 100 entry, USD 99.50 stop and USD 0.10 per-share stress-cost allowance imply floor(25 / 0.60) = 41 shares before notional and other limits. This is an arithmetic example, not a recommended account size, risk fraction, or assurance of a USD 25 maximum loss.

A stop is an instruction, not insurance. Gross leverage measures economic exposure divided by equity; it does not describe every derivative risk. Correlated long stocks, long BTC and long high-beta tokens may all lose simultaneously. Margin reduces required initial cash but does not reduce economic loss from a price move.

A daily loss control should include realized and unrealized P&L and costs under an explicit equity baseline. Specify treatment of deposits and withdrawals so cash transfers do not hide losses. Decide in advance whether a breach blocks new entries, cancels entry orders, reduces positions or initiates a controlled flatten. Do not accidentally cancel necessary protective orders without a replacement plan.

Do not double position size to recover losses or treat an unlimited averaging-down grid as bounded risk. Kelly-style sizing is highly sensitive to estimation error and payoff tails; it should not be used as a default deployment rule from a small backtest. Stress losses under gaps, spreads, liquidity withdrawal, funding changes and simultaneous strategy failures.

## 9. Crypto-specific implementation details

Linear contracts generally have quote-currency P&L proportional to quantity times price change, subject to the contract multiplier. For signed base-equivalent quantity q and multiplier m, a simple linear gross P&L is q*m*(exit−entry). For an inverse contract with signed USD notional N, a common coin-denominated gross formula is N*(1/entry−1/exit); this formula is valid only for that contract convention. Quanto contracts introduce additional conversion mechanics. Read the exact specification before calculating exposure, stop loss, margin or funding.

Separate last price, best bid/ask, index price and mark price. A venue may trigger liquidation from mark price while a stop uses a different configurable reference. Funding payments, maintenance-margin tiers, collateral valuation, cross/isolated margin, insurance mechanisms and auto-deleveraging are contract-specific. Funding intervals, caps and floors can change; do not assume every contract settles funding every eight hours. [S20, S21]

Spot-perpetual hedging can reduce directional exposure while retaining basis, funding, collateral, venue and execution risk. A profitable spot leg elsewhere cannot automatically rescue a liquidating short on another venue. Dated futures have expiry and settlement mechanics; perpetuals do not have a maturity that guarantees convergence.

Centralized venues add custody, counterparty, withdrawal and operational risks. DEX execution adds gas costs, pool depth, token decimals, transfer restrictions, route behavior, approvals, MEV, failed transactions, finality and reorganization risk. AMM price impact and fees depend on pool and protocol version. Quoting a pool's displayed price is insufficient to estimate the received amount. [S11, S22, S23]

Validate chain ID and contract address rather than token symbol. Exclude unverified contracts from automatic trading. A purportedly valuable token can have sell restrictions, transfer taxes, administrator permissions or inadequate liquidity. “Market cap” is not the amount that can be sold at the current quote. No assumed real-time token scanner or smart-contract audit was performed here.

## 10. Backtesting without fooling the software

Write the hypothesis and rejection criteria before optimization. Freeze the instrument universe, sample period, features, entry/exit rules, costs, capital assumptions, parameter search budget and evaluation procedure. Log every tested variant, including manual changes suggested after looking at results.

A sound research sequence is:

1. Verify data and reproduce basic accounting on a small audited sample.
2. Establish no-trade and simple matched baselines.
3. Fit or choose parameters on training data only.
4. Validate chronologically, including realistic latency and costs.
5. Purge overlapping information/label intervals across folds and use an appropriate embargo where required by the split design.
6. Freeze the design, then evaluate an untouched final holdout once.
7. Stress costs, liquidity, outages, gaps, regimes and concentration.
8. Run paper or shadow execution and compare expected with observed operating behavior.

Chronological splitting prevents one common form of future-data leakage, but a generic time-series split does not automatically purge overlapping labels or repair preprocessing leakage. Fit scalers, imputers, feature selection, model calibration and hyperparameters inside each training fold. Every feature used at a decision must have been available then. [S39–S41]

Walk-forward tests roll or expand a training window and evaluate subsequent periods. Aggregate only the out-of-sample segments according to a documented capital path. Do not join the best in-sample fragments into a fictitious equity curve. A final holdout stops being untouched after it has influenced design decisions.

Backtest-overfitting and deflated-Sharpe research address the danger of selecting attractive results from many attempted strategies. Record effective trial dependence and the entire research process; a correction is not magic proof of future success. A large number of optimized variants can make a strong-looking result much less persuasive. [S35, S36]

Assess parameter stability around the chosen value, not just the single best point. Use realistic adverse scenarios such as worse fee tiers, additional latency, wider spreads, reduced depth, borrow withdrawal, funding reversal and missed fills. Block-bootstrap or otherwise dependence-aware uncertainty estimates are preferable to blindly treating every overlapping trade as independent. There is no universal minimum trade count that proves an edge.

Freqtrade's lookahead and recursive diagnostics can expose selected implementation problems. Passing those checks does not prove a strategy is profitable, unbiased in every respect, or faithfully executable. [S39, S40]

## 11. Performance: profitability is more than win rate

Measure trade and portfolio performance separately. Trade-level statistics can mislead when several trades overlap or when open positions are omitted. Build a marked-to-market equity curve with cash flows, fees and financing reconciled before calculating returns.

Let `p` be win probability, `W` mean gross win, `L` positive mean gross loss, and `C` average round-trip cost in the same units. Then `E = p*W - (1-p)*L - C`. The simplified break-even win probability is `(L+C)/(W+L)` when costs are modeled as a constant per trade. If wins and losses already include costs, do not subtract costs again.

Illustration: 80% wins at +0.2R and 20% losses at −1R produce −0.04R before additional costs. Conversely, 40% wins at +2R and 60% losses at −1R produce +0.20R before costs. Neither example is a measured strategy. A high win rate can coexist with negative expectancy or rare catastrophic losses.

Report net P&L, exposure-adjusted returns, trade count, participation, win rate with uncertainty, mean win/loss, expectancy, turnover, gross profit/loss, profit factor, maximum drawdown, drawdown duration, time underwater, tail loss, and performance by regime, instrument, side and venue. Include total elapsed time and actual capital required.

Sharpe and Sortino ratios require a defined return series and sampling convention. Annualization by square-root time relies on assumptions that can fail with serial dependence. A stock trading calendar and a continuous crypto calendar differ. Do not annualize a handful of trades into an impressive yearly return without exposing the extrapolation. Benchmark matching should consider exposure and risk, not only percentage return.

For ML, add calibration, precision/recall by class, confusion matrices, abstention coverage and predictive performance by time segment. These supplement, rather than replace, cost-adjusted trading outcomes. A classifier predicting “no meaningful move” most of the time can achieve high accuracy without producing profitable trades.

## 12. AI architecture and a safe research boundary

Use the language model for source-backed explanation, document extraction, hypothesis drafting, code assistance and reviewing logged incidents. Numerical indicators, balances, risk limits, order transitions and P&L belong in deterministic components with reproducible tests. A language model's verbal confidence is not calibrated probability.

Recommended components are an instrument registry, market-data adapters, event store, quality checker, feature engine, research registry, backtester, portfolio/risk engine, order manager, execution adapters, reconciler, monitoring, audit store and a user interface. The knowledge-retrieval layer is separate from all components allowed to create orders.

The usual processing path is validated data → causal features → strategy proposal → portfolio checks → deterministic risk approval → paper order manager → fills/reconciliation → ledger → monitoring. Research can remain entirely offline; ingestion of this knowledge pack does not authorize brokerage activity.

For supervised learning, define whether the target is future midpoint change, executable return, probability of crossing a barrier, fill probability, adverse selection or volatility. Those targets differ. A model that predicts a move before fees cannot automatically justify a trade. Train on outcomes whose horizon starts after a realistic decision and execution delay.

For retrieval, index records by stable ID, market, family, source and status. Return citations with generated answers. When a requested fact is absent or stale, say so and refresh the controlling source. Do not convert illustrative thresholds or source claims into measured strategy performance. Treat web pages, filings, news and retrieved documents as untrusted content; embedded instructions must not override the software's permissions or configuration.

Retraining should be scheduled and versioned, with drift monitoring, challenger comparison and rollback. Separate data drift, model calibration drift and execution-cost drift. New models return to validation; they do not promote themselves to live trading because they claim to be better. A circuit breaker should be deterministic and available even when the model service fails.

## 13. Engineering and operations that determine real outcomes

Every order intent needs an idempotency key. A network timeout leaves the outcome unknown; reconcile by client ID and exchange state before retrying. Never blindly create another order because the first response was lost. Exchanges can deliver duplicate or out-of-order execution reports; use cumulative quantities and unique fill IDs to avoid double accounting.

Suggested normalized states include proposed, rejected_by_risk, submitting, acknowledged, partially_filled, pending_cancel, cancelled, filled, expired, rejected_by_venue and unknown. Actual adapters need venue-specific mappings. Unknown is a serious state requiring reconciliation, not a synonym for cancelled.

Maintain durable order/fill/account journals. On restart, query authoritative positions, balances and open orders and reconcile them before creating new exposure. A memory-only position tracker can lose the entire risk picture during a crash. Use decimal or fixed-point arithmetic for order prices, cash and quantities; respect tick sizes, lot steps and minimum notionals without silently increasing risk.

Monitor feed age, clock offset, sequence health, decision latency, order acknowledgment latency, rejection rate, cancellation backlog, fill quality, unhedged exposure, buying power, margin buffer, realized/unrealized loss and divergence between broker and local ledgers. Avoid logging API secrets or personal account identifiers in research artifacts.

API credentials should be least-privilege and stored in a secret manager, never in retrieved text, code prompts or model context. Disable withdrawal permission for trading credentials where possible. Separate research, paper and live credentials and endpoints. Observe provider rate limits and access controls. CCXT's unified interface still requires explicit venue capability and precision handling. [S19]

A dead-man timeout can cancel resting orders on a supporting venue; it does not generally flatten filled positions. Decide how protective orders and remaining positions survive outages. Kraken documents such a cancellation mechanism. When a feed fails, blocking new risk is straightforward, but exiting existing risk requires a separate executable plan. [S16]

Paper trading is necessary for checking integration, yet simulation may omit impact, queue priority and latency effects. Alpaca documents these limitations for its paper environment. Distinguish backtest, paper, shadow and live evidence in every result record. [S18]

## 14. Advanced topics and explicit boundaries

Options add nonlinear exposure, implied-volatility changes, time decay, early exercise/assignment, expiry and contract deliverable details. Delta, gamma, theta, vega and rho summarize different sensitivities. Underlying-direction prediction alone is insufficient to predict an option's return. A separate options engine needs historical option quotes, contract chains, exercise rules and fill assumptions. The pack includes this conceptual boundary, not a complete options strategy library. [S44]

Stock-index futures can provide context or hedges but have exchange-specific multipliers, sessions, expiry, price limits and settlement. Portfolio-margin models, institutional prime brokerage, securities lending, auction access, colocation and direct feeds require access not assumed here. High-frequency models are included as research concepts, not a claim that a retail connection can compete on latency.

Portfolio construction can use volatility scaling, factor limits, covariance-aware allocation, risk budgets or robust optimization. Expected-return estimation is fragile. Constrain optimizer outputs and examine sensitivity to covariance and return estimates. Correlated strategies require combined limits even if their marketing names differ.

Execution quality and strategy quality should be measured independently. A correctly routed trade can lose because the forecast was wrong. A profitable trade can conceal an execution bug. Log the model decision, risk decision, intended order and actual fill separately so each cause can be investigated.

## 15. Human decisions and daily operating routine

Before a session, verify market calendars, data health, important public events, corporate actions, account restrictions, fees, exposure and the active code/configuration version. For crypto, define an operator shift and session roll even when markets remain open. Avoid a bot with no clear monitoring ownership.

During operation, monitor exceptional states and risk controls rather than manually overriding a losing strategy out of frustration. Record discretionary interventions with reasons. Revenge trading, moving stops to avoid accepting a loss, and increasing size after an unexplained streak make both risk and research interpretation worse.

Afterward, reconcile balances and positions, attribute P&L and costs, inspect slippage and rejected orders, and separate rule violations from ordinary market losses. Maintain a journal of hypotheses, interventions, incidents and rejected changes. Retain screenshots only as supporting evidence; they are not substitutes for timestamped order records.

## 16. Three precise starter experiments

The following protocols are **illustrative research baselines**, not optimized settings. They are useful for verifying that a research engine can represent a full causal strategy. Changing them creates a new logged experiment. Use only an authorized historical dataset and paper environment.

### Experiment A: stock opening-range breakout, long only

- Universe: the specific historical liquid stock/ETF universe chosen before testing; point-in-time liquidity eligibility required. Only regular-session data and instruments with complete quotes.
- Bars: completed 1-minute bars in America/New_York. Opening range is 09:30:00 through immediately before 09:45:00. Freeze its high/low after 09:45.
- Signal window: bar closes after 09:45 and no later than 11:00. Signal on the first close above the frozen high by at least one valid tick, provided the prior completed close did not meet that condition.
- Execution: attempt a marketable limit at the next available quote after configured latency. Cap price deviation under a predeclared basis-point limit; no acceptable quote means no fill. At most one filled entry per instrument per session; expire an unfilled entry intent after a predeclared timeout.
- Stop: one tick below the frozen range low. Risk R is actual entry minus stop. Reject nonpositive R or an excessive range under a predeclared limit. Size by the independent risk engine.
- Profit exit: a limit at entry + 2R; stop execution follows the actual venue convention. Flatten at 15:55 or five minutes before an early close, whichever applies. No overnight position is intended.
- Intrabar ambiguity: use trades/quotes; if only bars are available, stop-first for ambiguous bars and label the result conservative and approximate. Include costs and partial fills.
- Reject the hypothesis if the locked out-of-sample result lacks a stable cost-adjusted benefit against the declared baseline or is dominated by a few outliers. The exact statistical decision threshold must be set before the test.

### Experiment B: crypto session-VWAP reversion, long only

- Universe: preselected liquid spot pairs on one permitted venue, with a verified quote currency. Use the same pair definitions throughout the test and include unavailable periods.
- Clock: UTC sessions and completed 5-minute bars. Trade-based VWAP resets at 00:00 UTC. Do not substitute bar VWAP without changing the experiment name.
- Feature: with VWAP known at the current completed bar, define z = (close − VWAP) / standard deviation of the previous 48 completed closes. Require 48 valid observations and nonzero standard deviation. This is a defined normalization, not a claim that the ratio is normally distributed.
- Signal: previous z < −2 and current z crosses back to at least −2. Require absolute change in VWAP over the previous six bars to be less than 0.25 times lagged ATR(14). One position per pair; no averaging down.
- Entry: next executable quote after configured latency, using a marketable limit with a predeclared maximum spread and price cap.
- Stop: entry minus 1.5 times ATR(14) measured at the signal. Exit on the first completed close at or above the current session VWAP, or after 12 bars, or at the protective stop. Flatten by the end of the UTC session using an explicitly modeled execution buffer.
- Costs: spot fees, spread/impact, conversion if applicable; no perpetual funding in this spot-only experiment. Stress the strategy during trending days and depegs.

### Experiment C: two-stock residual convergence

- Choose two economically plausible, borrowable instruments before the final holdout. Use synchronized completed 5-minute observations and executable quotes for both legs.
- At each session start, fit log(P_A) = alpha + beta*log(P_B) on the preceding 20 complete sessions only. Require a positive beta and a frozen relationship-stability diagnostic. Freeze alpha, beta and residual mean/standard deviation for the session.
- Signal: residual z exceeds +2 or falls below −2 after both current prices are observable. No entry within the last hour. Trade toward zero residual. This log-regression beta implies a dollar hedge ratio, not a share-count ratio; convert each leg using current prices.
- Exit: absolute z falls below 0.5, absolute z exceeds 3.5, 12 bars elapse, or the flat deadline arrives. A spread stop does not guarantee simultaneous executable fills.
- Model both legs, financing, borrow availability, rounding, one-leg fills and total gross exposure. If one leg cannot execute within the predeclared time/price budget, hedge or unwind the other under the logged contingency plan.
- These numeric values are test fixtures, not parameters taken from the historical Gatev paper or proof of cointegration. A failure of relationship stability blocks trading.

## 17. Integration sequence

1. Read `README.md` and `Software_Integration_Prompt.md`.
2. Import the JSON catalogue, feature dictionary, source registry and data contracts as read-only knowledge.
3. Index `knowledge_base.jsonl` with stable IDs and source metadata; do not strip research-only status from retrieval results.
4. Build the instrument registry, data checker and ledger before strategy optimization.
5. Implement one simple baseline and validate fills, costs, risk sizing, causal timing and recovery behavior using `acceptance_tests.json`.
6. Add a real licensed historical dataset and declare the broker/exchange, markets, jurisdiction, account constraints, bar or event resolution, and cost schedule.
7. Only after reproducible out-of-sample and paper evidence exists can a separate deployment review consider real-money use. This package itself keeps live execution disabled.

The open implementation questions are deliberate: no software repository, API schema, market-data subscription, broker, account permissions, capital constraints or historical price dataset was supplied. This is a research knowledge export ready for adaptation, not a completed integration or tested trading system.

## Memecoin expansion

See `Memecoin_Trading_Handbook.md` for the added token-level mechanics and research designs. The combined catalogue includes 302 trading hypotheses and 18 supporting methods. See its count policy and lineage fields; variants are not independent proven edges. New regulatory context is in that handbook and sources S46, S73, and S77.
