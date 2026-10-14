# Requirements matrix — Trading AI 1.7.0

Status meanings:
* **DONE**: implemented and exercised by a test or by the self-test.
* **PARTIAL**: implemented, with a limitation stated in the same row.
* **REQUIRES CONNECTION**: the interface exists, but it needs a credential, paid dataset or service this build does not have.
* **NOT DONE**: not built.

How it was verified:
* **Unit tests**: 204 tests (`backend/tests`), also run on real Windows 11 by `.github/workflows/windows.yml`.
* **Self-test**: `START_TRADING_AI.exe --selftest` runs 34 steps over HTTP and WebSocket against the real server (1.7.0: 34 of 34 from source; the Wine and Windows results are in `VERIFICATION_REPORT.md`).
* **Real-data run**: the dashboard and API were exercised on live Coinbase, Kraken and Yahoo data.

The exe has been tested under Wine on Linux and on a real Windows 11 virtual machine (GitHub runner), **not on a physical Windows PC**.

## Launch and packaging

| Requirement | Status | Evidence / limitation |
|---|---|---|
| One launcher `START_TRADING_AI.exe`, no command prompt, npm or Python for the user | DONE | PyInstaller one-folder build (`packaging/trading_ai.spec`); Python, libraries and the compiled dashboard are inside `_internal/`. |
| Starts backend on 127.0.0.1, auto-selects a free port from 8000 | DONE | `launcher.free_port`; never binds 0.0.0.0. |
| Starts DB, trading engine, agents, WebSocket, risk, frontend; opens the browser | DONE | 20 start-up checks shown on `/health` (including market discovery, the learned-safeguard regression replay, the master agent and its 100 agents, and the assistant). |
| Single instance (a second double-click opens the running dashboard) | DONE | OS file lock + `/api/system/ping` probe; verified under Wine. |
| Clean stop (console close, Ctrl+C, Shut down button) with state saved | DONE | Windows console handler + `/api/system/shutdown`; bots, risk state and a DB backup are saved. |
| Code signing | NOT DONE | Unsigned: SmartScreen may warn on first run. |

## Full automation

| Requirement | Status | Evidence / limitation |
|---|---|---|
| Runs by itself after the double-click (no setup, no clicks) | DONE | The master agent is on by default (paper only). It trains each of the 100 agents with STANDARD research on its own market (at most 2 jobs at once), chooses versions on validation data, gives trading permission only to versions that pass every gate, and runs each permitted agent's execution loop, which buys and sells by itself with no per-trade approval. While no version passes it stays in cash and keeps retraining weekly. Tests: `test_master.py`, `test_autopilot.py`, `test_learning.py`, and self-test steps. |
| Owner keeps control | DONE | Start System turns everything on (the program does this by itself when it opens) and Stop turns everything off. An agent loop the owner stops is never restarted by the master. EMERGENCY STOP removes every agent's permission (self-test step), and nothing automatic re-arms it. |
| Fully automated real-money trading | NOT DONE (by design) | The master runs paper only. Live trading needs the owner's separate arming, as required. |
| Start with Windows | DONE | Optional checkbox: adds the program to this Windows user's Run list (no administrator rights needed). |

## Owner's master prompt, revision 13 (docs/specs/)

The two owner documents are stored unchanged: `docs/specs/AI_Trading_System_Master_Prompt.md` (revision 13) and
`docs/specs/Backtested_Working_Strategies.md`. `scripts/import_master_prompt.py` imports the registry from the first.

| Requirement (section) | Status | Evidence / limitation |
|---|---|---|
| Install the strategies that work, leave the ones that don't | DONE | Backtested_Working_Strategies.md lists **0 qualifying strategies**, so no strategy is installed as tradeable. Every card is installed in the catalog with its true state: 30 of 124 can run here and are tested automatically; 94 are blocked with a reason code (49 PRODUCT_UNSUPPORTED, 36 INSUFFICIENT_DATA, 3 PERMISSION_MISSING, 2 FUNDING_UNFAVORABLE, 2 BORROW_UNAVAILABLE, 1 RELATIONSHIP_BROKEN, 1 rules incomplete). |
| 124-card catalog, 98 sources, 212-entry research index, one registry for every agent (5C, 5I) | DONE | Imported verbatim (ST001-ST080 re-import identically to before). Each card shows evidence labels, sources with access labels (A, P, M, B, K, D), implementation, reason code, lifecycle state and research state. The 212 index entries are discovery records (stage "discovered", DATA_BLOCKED: they need a point-in-time stock universe). Test: `test_catalog_has_all_124_cards_98_sources_and_212_index_entries_mapped`. |
| New cards this software can run (ST082, ST083, ST121, ST122, ST123) | DONE | ST082 residual momentum and ST083 52-week-high distance (portfolio templates on seven large US stocks, survivorship-biased, capped at RESEARCH FURTHER), ST123 multi-horizon crypto channel ensemble (portfolio template), ST121 intraday noise-band momentum and ST122 activity-filtered opening-range breakout (new single-market generators). Look-ahead tests cut the data at several points and check no earlier signal changes. |
| Automatic tests of every runnable card on real data | DONE | `scripts/catalog_batch.py` (103 runs) and `scripts/catalog_report.py` write `docs/CATALOG_BACKTEST_REPORT.md`: 86 REJECT, 17 RESEARCH FURTHER, 0 PAPER TEST. ST082 and ST083 passed every gate including the Deflated Sharpe ratio but are capped at RESEARCH FURTHER because their universe is today's seven large US stocks (survivorship bias), so they may not trade. ST121 and ST122 were rejected (the free intraday history gives them very few trades; ST122's activity filter fired on no test day). |
| Owner's batches recorded as rejected evidence (revisions 11-13) | DONE | Batch 01 (48 configurations), Batch 02 (36) and Batch 03 (6): 0 positive after base costs, validation not opened. Shown per card and in a "Your batches" tab, separate from this installation's tests; not re-run here. |
| Research states (revision 12) | DONE | DATA_BLOCKED, RULES_INCOMPLETE, IMPLEMENTED_RESEARCH_ONLY, TEST_COMPLETE, REJECTED_UNDER_TEST, VALIDATION_PENDING (DISCOVERED for index entries), computed from the mapping and the research ledger. |
| No backtest button, test forms or manual training (2, 6) | DONE | Removed from the interface: the Strategy lab form, the catalog's Backtest and Add-paper-bot buttons, job cancel. Removed routes: POST /api/research, POST /api/catalog/{id}/research, POST /api/portfolio-bots, POST /api/research/jobs/{id}/cancel. The research evidence stays visible read-only. Self-test checks the route is gone. |
| Entries blocked until a strategy qualifies; safe idle in cash (revision 12, 5F) | DONE | Deterministic risk check "strategy qualified" (reason code STRATEGY_NOT_QUALIFIED) on every strategy order; the bot and portfolio-bot loops also abstain early and may still exit. Qualified = latest finished research run on the same market and timeframe has verdict PAPER TEST and the autopilot has not retired it. The PROBATION tier is removed and old probation bots retire. Tests: `test_entries_wait_in_cash_until_a_strategy_qualifies`, `test_a_bot_whose_strategy_says_buy_waits_until_the_strategy_qualifies`, `test_risk_service_blocks_unqualified_entries_but_never_exits`, `test_unqualified_portfolio_bot_buys_nothing`. |
| Day-trading operating mode: entry window, entry cutoff, flattening deadline, crypto maximum hold (4) | DONE | `engine/daytrade.py` declares the rules per calendar with its timezone: stocks and ETFs (New York) enter from 09:35 until 30 min before the close and are flat 10 min before it (early closes included); CME futures enter until 16:15 and are flat by 16:45; forex enters until 16:30 and is flat by 16:50; crypto (UTC) holds at most 24 hours and opens nothing from 23:00 to the 00:00 daily cutoff. The SAME rules run in the backtester (every research run is stamped intraday) and in paper decisions; a sweep every 30 s closes positions past a deadline even without new bars, and when a market is shut it keeps the position and records an incident. Daily-bar methods and monthly portfolios produce no trades under these rules and stay research-only; results tested before 1.4.0 no longer qualify. Tests: `test_daytrade.py`. Limitation: CME and forex holiday hours are approximated by NYSE holidays; venue maintenance windows are not modelled. |
| Three pages with the specified names (2, 8) | DONE | AI Trading System · AI Supercomputer — Agent Activity · Brokers & Accounts. |
| Start System, Pause New Entries, Stop, Emergency Stop (2, 8) | DONE | Start System is what the program does when it opens; the button shows it running. Pause New Entries blocks new exposure but lets exits through and survives a restart. Flatten All closes paper positions through the risk service. |
| Visual design and page 1 composition (8A) | PARTIAL | Design tokens applied everywhere. Page 1 follows the written composition: slim top bar (pages, PAPER badge, account, clock, connection, system state), a pausable market strip with real changes and freshness, a KPI strip (equity, net P&L, exposure, drawdown, agent availability, trading readiness), engine summary beside the chart (5:7), equity and drawdown, measured decision activity (abstention, signal disagreement, latency), confirmed fills, and a team agent strip. The video itself is not available to this build, so the layout follows the specification's description of it, not its frames. No light theme. |
| 320 trading agents A001-A320 with a Supercomputer Brain (3, 4) | REPLACED in 1.5.0 | Replaced by the master agent and 100 agents (next section). As built in 1.4.1: | `engine/fleet.py`: 320 agents with stable ids in the specification's groups; the brain (a separate coordinating service) assigns each agent one distinct instrument with a versioned, persisted ownership plan, keeps positions with their owner, and reassigns agents of groups with no access (options, rates, specialty) to spare crypto pairs while keeping the gap visible. Agents run in a bounded pool of 8 workers with fault isolation; bot decisions run inside the owning agent's job. Budgets are zero until a strategy qualifies on that market, and their sum stays within the gross-exposure limit; the risk check "agent budget" enforces them. One order authority per account re-reads positions plus working orders inside its lock, so capital is reserved atomically (concurrency test: 16 simultaneous agents, exactly the allowed 5 orders pass). Online run (1.4.1): all 320 agents had a distinct market and none was blocked. The 96 equities agents each watch a real US stock or ETF (68 large caps and ETFs were added for them, each checked to return data). Forex and futures have only 5 and 10 observable markets, so their other 49 agents, like the options, rates and specialty agents, watch spare crypto pairs; page 2 shows them as reassigned and keeps those coverage gaps visible. A full cycle took about 6 s once data was cached (30 s on the first one, while new stocks fetched their first prices). Offline (DEMO data) far fewer agents have a market. Agents are deterministic code, not language models. |
| 50 shared capabilities C01-C50 (4) | DONE | Each capability is mapped to the code that does it, with its live state, on page 2 (Support services). Five are shown blocked because their feed or product is not connected: C16 news, C27 spread (no bid/ask feed), C29 borrowing, C30 funding, C31 event calendar. Not counted as trading agents. |
| Global stock, crypto and meme-coin coverage across chains and venues (3) | PARTIAL | `market/discovery.py` lists every Coinbase product and Kraken pair once a day (online run: 842 and 1,460; 403 Coinbase USD pairs paper-tradable) and takes one shared price snapshot per venue each minute; delisted pairs are kept and marked. Coverage is shown with its denominator (pairs listed by the connected providers, not every market). Meme coins: a small seed list tags pairs by theme, marked unverified (a ticker is not an identity). Not covered, and listed as such: stocks beyond the curated list, options, bonds, on-chain tokens, DEXs, launchpads and other exchanges. |
| Equity and drawdown chart; session report; exports (8) | DONE | Equity recorded every 60 s (1D/1W/1M/1Y); session report with a JSON export labelled paper or live. |
| Attribution by strategy, market and costs | DONE | Net P&L, fees and slippage against the decision price, per strategy and per market. |
| Page 2: brain, network, agent grid, drawers, filters (8, 8A) | DONE | 1.5.0: master agent core with what it is doing, plan and cycle metrics; a Learning tab (lessons, mistakes, regression runs, replay button); agent drawers with role, permission and its reason, versions with their training numbers, mistakes, and a shadow check. Since 1.4.0: market map (sessions, venue health, what cannot be observed); network of every agent by team, where a dot pulses only when that agent received new data; virtualized, searchable agent grid with filters (team, state, asset class, meme coins) and grouping (team, asset class, venue, job); an agent drawer with assignment, data, budget, catalog access, positions, decisions, errors, dependencies, tools and assignment history. |
| Page 3 Brokers & Accounts (8, 9, 5B) | DONE | Capability matrix, market coverage, discovery coverage with meme pairs, and Add Funds, which only opens each broker's official website (Kraken, Coinbase, Alpaca, Interactive Brokers Canada, OANDA Canada). No card or bank details are collected and a deposit never raises the trading allocation. |
| Speaking assistant and voice tools (10, 11) | PARTIAL | Answers from verified state; British English browser voice with volume; quiet hours (only critical announcements are spoken); each announcement shows its state (queued, speaking, spoken, shown without speech and why, expired, interrupted, failed); measured event-to-speech delay; "that bot" and "the bitcoin bot" resolve to a bot; it can pause a bot and pause or resume new entries; money and live commands refused. Not built: cloud voice or WebRTC. |

## 1.5.0: master agent, 100 trading agents, continuous learning (owner's instruction of 2026-10-13)

| Requirement | Status | Evidence / limitation |
|---|---|---|
| Research credible, evidence-backed strategies for crypto and stocks; compare performance, drawdowns, liquidity, fees, slippage, failure modes; cite sources | DONE | `docs/STRATEGY_RESEARCH.md`: 24 sources (every link was returned by a web search), a family-by-family comparison, the lessons on replication and overfitting, and how each was mapped to an agent role. Secondary figures are marked as secondary. |
| Inspect the old architecture; keep a recoverable backup before replacing it | DONE | `docs/BACKUP_AND_RESTORE.md`: the 1.4.1 download stays in `downloads/`, the 1.4.1 commit is `a3c3952`, and 1.5.0 copies an older database before migrating it (test `test_upgrading_an_older_database_keeps_a_recoverable_copy_first`). |
| Exactly 100 trading agents, each with an assigned role | DONE | `engine/master.py`: A001-A100 in 8 roles (crypto majors, liquid crypto trend, crypto mean reversion, ETF intraday momentum, stock breakouts, stock mean reversion, forex session momentum, index futures breakouts). One distinct instrument per agent. Online, all 100 had a market (test with a fake listing of 120 pairs; training run on real data). |
| Train and validate each agent with documented datasets, objectives, out-of-sample evaluation | DONE | Each candidate is researched on the agent's own data (provider, bar count, date range and SHA-256 recorded). Parameters are fitted on 60%, the candidate is chosen on the next 20% (never on the test), and the last 20% is held out; walk-forward, Monte Carlo, 2x/3x cost stress, Deflated Sharpe and PBO apply. Results: `docs/AGENT_TRAINING_REPORT.md`. Test `test_version_is_chosen_on_validation_never_on_the_test_segment`. |
| No duplicate orders, no conflicting positions, no uncontrolled aggregate exposure | DONE | One owner per instrument; only the owner may open (test `test_only_the_owning_agent_may_open_a_position`). One order authority with atomic capital reservation (16-thread test). Duplicate and order-rate checks in the risk service. Budgets sum within the gross-exposure limit. |
| Agents buy and sell automatically, without per-trade permission | DONE (paper) | A permitted agent's loop sends paper orders by itself (test `test_an_agent_with_a_validated_version_trades_automatically_in_paper`). Real money is not enabled: that needs the owner's separate arming and a verified broker account. |
| Explicit portfolio, position and loss limits plus an emergency stop, tested before execution | DONE | Risk service limits (order, position, gross, leverage, asset class, correlated exposure, open positions, liquidity, daily/weekly loss locks, drawdown). Per-agent daily loss limit of 0.5% of equity (test `test_daily_loss_limit_stops_the_agents_entries_and_two_breaches_roll_back`). The emergency stop removes every permission (test, and a self-test step). |
| Backtest individually and as a combined portfolio across bull, bear, sideways and volatile markets, with all costs | DONE | `docs/PORTFOLIO_BACKTEST_REPORT.md`: a walk-forward of the master's whole selection process for every agent, combined into one portfolio, by regime, including fees, spread, slippage and funding. Limits are stated in the report. |
| Prevent look-ahead and leakage; walk-forward; held-out data; paper before live | DONE | Signals are causal and fill at the next bar. Selection never sees the test segment. Walk-forward folds trade only unseen data. Regime labels use the previous day's data. Paper only: live stays off. |
| Test terminal, software, integrations, order handling, recovery, hardware thermal; report passed / failed / not performed | DONE (thermal of a physical PC NOT PERFORMED here) | `docs/VERIFICATION_REPORT.md`. A real `kill -9` recovery check passed 14 of 14; the suite, build and self-test passed on real Windows 11. The thermal check itself (`hardware.py`) is built and ran on Windows 11, but that machine is a VM with no sensors; your PC's result needs your run. |
| Master agent controls assignments, capital, portfolio risk, permissions, monitoring, emergency shutdown | DONE | `engine/master.py` (see its docstring). The deterministic risk service and the emergency stop sit above it, and no agent can change them. |
| Continuous learning: record each mistake, find its root cause, share the lesson, add persistent safeguards and regression tests | DONE | `engine/learning.py`: 14 root causes. The first mistake of a cause becomes a lesson whose safeguard applies to all agents. Safeguards only block or shrink entries. Every stored scenario is replayed at start-up (a failure stops start-up), per new lesson and hourly. Tests: `test_learning.py` (12). |
| Validate learned changes by backtest and paper before promotion; version history; automatic rollback | DONE (paper) | A new version needs a PAPER TEST verdict, then must beat the active version on bars it was not trained on (shadow) before promotion. Rollback happens on a paper loss above 2% of equity, 2 daily-limit breaches in 7 days, results below validation, or a failed re-validation. "Live" promotion is not enabled (real money stays off). |
| Track learning improvements and repeated failures with evidence | DONE | Mistakes per 100 decisions, this week vs last week; repeats per lesson; regression pass counts (`/api/learning`, the Learning tab). Three repeats in 24 hours suspend the agent. This aims to prevent repeats; it cannot guarantee them away. |
| Agents never override the master's safety controls | DONE | Entries need the master's permission and the risk service. Safeguards cannot raise a quantity (property test over 3,000 random contexts). Agents have no route to change limits, re-arm, or turn on live trading. |

## Stack

| Requirement | Status | Evidence / limitation |
|---|---|---|
| Python + FastAPI backend | DONE | `backend/tradingai/api/server.py` |
| React + TypeScript frontend | DONE | `frontend/` (Vite build, strict TypeScript) |
| WebSockets for live updates | DONE | `/ws`: catch-up of missed events on reconnect. |
| SQLite (transactions, migrations) | DONE | WAL, synchronous=FULL, schema v4 (adds the discovered-instrument inventory). |
| DuckDB + Parquet market store | DONE | Partitioned by provider/symbol/timeframe/year/month; provenance hashes stored. |

## Markets and data

| Requirement | Status | Evidence / limitation |
|---|---|---|
| Crypto | DONE | Coinbase and Kraken public candles (real-time completed bars). Paper trading only via the paper broker. |
| Stocks / ETFs | DONE | Yahoo chart data; daily bars become available at the NYSE close (early closes included). Yahoo intraday history is limited by Yahoo. |
| Forex | PARTIAL | Yahoo reference mid prices only: no dealer bid/ask. FX financing/swap is not modelled. |
| Indices | PARTIAL | Reference only (SPX, NDX, DJI, RUT); not tradable, by design. |
| Futures | PARTIAL | Yahoo continuous series with multipliers and quarterly roll windows for equity-index futures. No per-contract-month data, so rolls are approximated (positions flat in the roll window). |
| Funding rates, order book, on-chain, economic calendar, news | REQUIRES CONNECTION | The features, agents and strategy templates that need these are marked UNAVAILABLE and abstain. No news or economic-calendar feed is connected and none is fabricated. |
| Data quality (gaps, bad ticks, timestamps, staleness) and provenance | DONE | `data/quality.py`; quality score on every series; SHA-256 per dataset. |
| Corporate actions | PARTIAL | Uses Yahoo adjusted closes, labelled as adjusted. No separate split/dividend ledger. |
| Market calendars | DONE | NYSE holidays and early closes, CME, FX sessions, 24/7 crypto. |
| Offline / DEMO data | DONE | Deterministic synthetic DEMO instruments, labelled SIMULATED everywhere they appear. |

## Strategies, indicators, regimes, agents, ML

| Requirement | Status | Evidence / limitation |
|---|---|---|
| Hundreds of strategy templates | DONE | 1,502 templates from 106 generators with filters and exits. 26 near-duplicate templates were pruned. 1,487 can run; 15 need data that is not connected. |
| Hundreds of indicators / features | DONE | 226 registered features (123 distinct functions), all tested to use only past data. 19 need external data. |
| Regime detection | DONE | Trend / volatility / character rules, a 2-state HMM and CUSUM change points. The HMM probability is labelled "uncalibrated". |
| Multi-timeframe analysis | DONE | Each decision also evaluates completed higher-timeframe bars (agent T11). |
| 100+ AI agents | DONE | 102 agents in 10 groups. 15 vote; the rest advise, veto or report. 20 need data that is not connected and say so. |
| Ensemble without double counting | DONE | Votes are averaged within each information cluster first. |
| Confidence / probabilities | DONE (by design) | No probability is shown unless a calibrated model passes evaluation. None has passed, so none is shown. |
| Machine learning | PARTIAL | Logistic regression, boosted stumps, Platt calibration, triple-barrier labels and purged walk-forward exist in `ml/`. On real BTC data no model beat the base rate (AUC 0.51), so ML is not used in live decisions and has no page. |

## Research engine (automatic; results read-only)

| Requirement | Status | Evidence / limitation |
|---|---|---|
| Chronological train / validation / test, out-of-sample | DONE | 60/20/20 split; parameters are chosen on train only. |
| Walk-forward | DONE | 3, 5 or 8 folds by depth. |
| Monte Carlo | DONE | Trade reshuffle, stationary bootstrap, cost shocks, missed fills. |
| Parameter stability, regime tests, cost stress (1.25×–3×), capacity | DONE | Capacity runs at DEEP depth only and needs volume data. |
| Multiple-testing protection, Deflated Sharpe, PBO | DONE | Every run is recorded in the ledger and counted as a trial; PSR, DSR, Newey-West t, bootstrap interval and PBO (CSCV). |
| Realistic costs | DONE | Fees, spread, volatility- and size-based slippage, participation cap and partial fills, futures multiplier, FX conversion. Cost-model defaults are labelled assumptions. |
| Backtest vs paper vs live comparison | DONE | `/api/research/compare`. The live column stays empty until live trading has happened. |
| Verdicts can never recommend live trading | DONE | The only verdicts are REJECT, RESEARCH FURTHER and PAPER TEST; fewer than 10 test trades means REJECT. |

## Trading, risk, execution, brokers

| Requirement | Status | Evidence / limitation |
|---|---|---|
| Paper trading | DONE | Decimal ledger, idempotent orders, spot vs margin accounting, partial fills; ledger-balance tests. |
| Shadow trading | DONE | Full pipeline; orders are recorded and never sent (test). |
| Live trading with explicit activation | PARTIAL | Arming requires: a live connection, every readiness check passing (including "adapter verified by an acceptance test"), caps, and the typed acknowledgement. No adapter has passed a live acceptance test, so **live arming is locked in this build**. Live never resumes by itself after a restart. |
| Broker integrations | REQUIRES CONNECTION | Alpaca, OANDA, Kraken and IBKR adapters were written from the brokers' documentation and are marked UNVERIFIED. Coinbase Advanced needs ES256 signing, which this build does not include. Credentials go into the DPAPI vault. |
| Broker eligibility, jurisdiction, permissions | DONE (by design) | Product permission comes from the broker's reported capabilities. The software cannot override a broker's rules. Withdrawal permission is never requested. |
| Deterministic risk the AI cannot bypass | DONE | Order size, position, gross exposure, leverage, asset class, correlated cluster, open positions, liquidity, stale data, duplicate orders, order rate, fat-finger price and quantity, account/environment match, known market, contract multiplier, market open, reconciliation. Reduce-only claims are verified against positions. Each check has a test. |
| Daily / weekly loss and drawdown locks; kill switch | DONE | Locks persist across restarts; re-arming needs the typed phrase; raising a limit needs a typed phrase. |
| Execution algorithms | PARTIAL | TWAP, VWAP, POV and limit-with-timeout exist and are tested. Bots currently send market orders; the algorithms are not yet selectable per bot. |
| Portfolio optimization | PARTIAL | Ledoit-Wolf, inverse volatility, risk parity, minimum variance, HRP and mean-variance exist and are tested. Bots are sized per trade from the risk budget; the optimizer does not yet allocate across bots. |
| Audit log | DONE | Hash-chained; verified at every start and in the self-test. |
| Crash recovery | DONE | Uncertain orders are resolved by asking the broker. Paper and shadow bots resume; live does not. The kill switch survives restarts (test). |
| Reconciliation | DONE (paper) / PARTIAL (live) | Paper: positions rebuilt from fills vs stored positions, plus a ledger check, at start-up and every 5 minutes. Live: compared against the broker, but never exercised because live is locked. |
| Clock sync check | DONE | Measured from data-provider Date headers (1-second resolution). |

## Pages

| Requirement | Status | Evidence / limitation |
|---|---|---|
| Exactly three pages | DONE | AI Trading System, Master Agent — 100 Agents, Brokers & Accounts. Details open in drawers and dialogs. |
| AI Trading System | DONE | Market strip; KPI strip; engine summary; candlestick chart with fills; equity and drawdown; decision activity; execution stream; team agent strip; Start System / Stop; Pause New Entries; Flatten All; paper/shadow mode; master agent card; agent execution loops (no hand-made bots); positions; session report; regime and agents; risk meters with limits in a settings drawer; strategy catalog; read-only research evidence. |
| Brokers & Accounts | DONE | Account and balances; paper balance setting; connections (vault, test, remove); capability matrix; Add Funds; market and discovery coverage; live readiness and arming; orders and fills; reconciliation. |
| Master Agent — 100 Agents | DONE | Master agent and its 100 agents (network by role, agent grid, drawers, learning, C01-C50 support services); decision feed with agent votes, conflicts, vetoes, risk checks, execution and audit trail; live event stream; system health; research ledger; signal agent functions. |
| SIMULATED labels | DONE | Paper balances, DEMO prices and backtests on simulated data are labelled on every page. |
| Works at phone width | DONE | No horizontal scrolling at 390 px (checked in Chromium). |

## Known gaps

1. Not tested on a physical Windows PC; tested under Wine and on a Windows 11 virtual machine.
2. No broker adapter is verified against a real account, so live trading cannot be armed.
3. No news, economic-calendar, funding, order-book or on-chain feeds are connected.
4. Machine-learning models and the portfolio optimizer are not used in live decisions.
5. Execution algorithms are not selectable per bot.
6. Futures use continuous series; there is no per-contract roll data.
7. FX financing is not modelled.
8. The program is not code-signed.
9. No GPU acceleration.
10. 94 of the 124 catalog templates cannot run here (see the catalog for each reason code). When 1.5.0 was built, none of the 100 agents' versions passed every research gate on real data (`AGENT_TRAINING_REPORT.md`), so no paper trade is opened until one does.
11. The assistant uses browser speech; no cloud voice provider is connected.
12. Free data limits the history: Yahoo keeps about 60 days of 15-minute bars and about 2 years of hourly bars, so 15-minute agents have few test trades. Options, bonds and more forex pairs or futures contracts cannot be observed here, so no agent covers them.
13. Coverage stops at Coinbase, Kraken and the curated Yahoo list; meme-coin tags are unverified.
14. The page layout follows the specification's written description of the reference video; the video itself was not available.
15. The temperature of your own PC has not been measured: the test machines are virtual machines with no sensors. Run `CHECK_COMPUTER_TEMPERATURE.bat` on your PC (`VERIFICATION_REPORT.md`). Many PCs expose only a motherboard thermal zone, or none, to Windows; the report then says so.

## 1.5.1: Windows 11 and thermal check (owner's request of 2026-10-13)

| Requirement | Status | How it was verified |
|---|---|---|
| Runs on Windows 11 | DONE | Built and self-tested natively on a Windows 11 (build 26100) GitHub runner, and under Wine. `START_HERE.txt` explains SmartScreen, Smart App Control (the program is unsigned) and Defender. Not tested on a physical PC. |
| Check for errors in the thermal (temperature) | DONE (your PC's result NOT PERFORMED here) | `CHECK_COMPUTER_TEMPERATURE.bat` and the page 3 button run 1 minute idle, a load on every logical CPU (1 to 30 minutes, default 5), then 1 minute of cool-down, sampling Windows performance counters every 5 seconds. Verdicts: PASS, PASS (no temperature sensor), WARNING, FAIL, STOPPED. Tests: `tests/test_hardware.py` (12). Real-Windows run: PASS (no sensor) on a VM. |
| Never overheats the PC through the check | DONE | The load stops at once at 95 °C; Ctrl+C or Stop also stops it. Tested with a simulated 96 °C sensor: stopped in under 5 seconds. |
| Monitors while running, protects the PC | DONE | The program reads the temperature every 30 seconds; at 85 °C or when Windows limits the CPU, it pauses new training jobs and records the event. Trading rules and risk checks are not changed. Test: training pauses and resumes. |
| No invented temperatures | DONE | A PC that reports no sensor is reported as such. Readings outside 5-130 °C are dropped as sensor faults. |

## 1.6.0: JARVIS voice assistant, internet, small accounts (owner's request of 2026-10-14)

| Requirement | Status | How it was verified |
|---|---|---|
| Set up `adewaskar/jarvis` with the Trading AI | DONE (voice not tested) | Copied into `jarvis/` with its licence (MIT) and a list of changes (`jarvis/TRADING_AI_CHANGES.md`). `npm ci`, `tsc`, `vite build` and lint pass; the same build is a step of the Windows CI workflow. The microphone, voice and 3D screen need a real Chrome window and a Claude Code login, so they were not run here. |
| JARVIS can read the Trading AI | DONE | Nine read-only tools (`jarvis/bridge/trading.mjs`). Run against a live Trading AI: all nine returned real data. |
| JARVIS cannot trade or change anything | DONE | A separate read-only token: the server accepts it only for GET on 18 information pages and refuses it on every write, on connections, brokers, credentials and the audit chain (`tests/test_readonly_link.py`, 3 tests, and a self-test step). JARVIS has no tool that acts. |
| Internet access for JARVIS | DONE | Claude Code's web search and web fetch are allowed by default in JARVIS. Web text is treated as data; it cannot give orders because nothing JARVIS can reach acts. |
| Works with any amount of money | DONE (as before) | Paper balance from $100 up; at $100 the limits allow $10 per order, $25 per position and a $3 daily loss. |
| "$100 becomes $300K" | NOT PROMISED, by design | `CAN_100_DOLLARS_BECOME_300K.md`: the maths (3,000 times the money) and the measured results (0 of 100 agents passed the gate; the portfolio test was negative after costs). No software can promise this. |
| Bot rewrites and deploys its own live logic | NOT DONE, by design | Improvements are made by a person with tests, never by the bot unattended. |

## 1.7.0: only stocks, crypto and meme coins; JARVIS controls the system by voice (owner's request of 2026-10-14)

| Requirement | Status | How it was verified |
|---|---|---|
| Remove every market except stocks, crypto and meme coins | DONE | Forex and futures are gone from the instrument universe; options and bonds rows are gone from coverage. The risk service denies an entry in any market other than US stocks and crypto (`market supported` check; exits stay allowed so an old position can be closed). ETFs and indices remain only as price references (stock agents compare with SPY); they cannot be ordered or assigned. `tests/test_market_policy.py` (11 tests). Engine code for futures and forex calendars stays dormant and unreachable. |
| Meme coins as their own group | DONE | 15 agents (A041-A055): 8 momentum, 7 mean reversion, on Coinbase meme pairs (16 were online when checked on 2026-10-14). The other crypto agents never take a meme coin. Tested with 15 meme pairs: each meme agent got one, no crypto agent did. |
| Exactly 100 agents | DONE | 40 crypto, 15 meme, 45 US stocks (11 new stock agents A090-A100 for intraday momentum). The new agents are untrained. |
| JARVIS controls everything, like the master | DONE within the safety rules | `engine/jarvis_link.py`: pause and Stop run at once; Start, resume, a temperature test and a paper balance wait for the owner's Approve on page 1; orders, limits, live trading, brokers, credentials and the emergency stop do not exist for JARVIS. `tests/test_jarvis_commands.py` (23 tests), a self-test step, a live run of JARVIS's tools, and the page-1 card checked in Chromium. |
| JARVIS knows everything about stocks, crypto and meme coins | PARTIAL, honestly | It reads the program's markets, agents, roles and results and searches the web. No system knows everything; it is told to look things up and say when it does not know. |
