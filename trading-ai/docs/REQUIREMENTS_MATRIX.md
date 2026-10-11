# Requirements matrix — Trading AI 1.3.0

Status meanings:
* **DONE**: implemented and exercised by a test or by the self-test.
* **PARTIAL**: implemented, with a limitation stated in the same row.
* **REQUIRES CONNECTION**: the interface exists, but it needs a credential, paid dataset or service this build does not have.
* **NOT DONE**: not built.

How it was verified:
* **Unit tests**: 98 tests (`backend/tests`).
* **Self-test**: `START_TRADING_AI.exe --selftest` runs 23 steps over HTTP and WebSocket against the real server. It passed on the built Windows exe under Wine.
* **Real-data run**: the dashboard and API were exercised on live Coinbase, Kraken and Yahoo data.

The exe has been tested under Wine on Linux, **not on a physical Windows PC**.

## Launch and packaging

| Requirement | Status | Evidence / limitation |
|---|---|---|
| One launcher `START_TRADING_AI.exe`, no command prompt, npm or Python for the user | DONE | PyInstaller one-folder build (`packaging/trading_ai.spec`); Python, libraries and the compiled dashboard are inside `_internal/`. |
| Starts backend on 127.0.0.1, auto-selects a free port from 8000 | DONE | `launcher.free_port`; never binds 0.0.0.0. |
| Starts DB, trading engine, agents, WebSocket, risk, frontend; opens the browser | DONE | 17 start-up checks shown on `/health` (including the autopilot and the assistant). |
| Single instance (a second double-click opens the running dashboard) | DONE | OS file lock + `/api/system/ping` probe; verified under Wine. |
| Clean stop (console close, Ctrl+C, Shut down button) with state saved | DONE | Windows console handler + `/api/system/shutdown`; bots, risk state and a DB backup are saved. |
| Code signing | NOT DONE | Unsigned: SmartScreen may warn on first run. |

## Full automation

| Requirement | Status | Evidence / limitation |
|---|---|---|
| Runs by itself after the double-click (no setup, no clicks) | DONE | The Autopilot is on by default. It screens strategies with FAST research and confirms the promising ones with STANDARD research (rate-limited, one job at a time). It starts paper bots only for strategies that QUALIFIED (passed every gate), monitors them, and retires those whose paper results fall short or whose re-test on newer data fails. While nothing qualifies it stays in cash and keeps researching (revision 13). Covered by tests (`test_autopilot.py`) and self-test steps. |
| Owner keeps control | DONE | Start System turns everything on (the program does this by itself when it opens) and Stop turns everything off. A bot the owner stops is never restarted by the autopilot. EMERGENCY STOP blocks the autopilot, and the autopilot never re-arms. |
| Fully automated real-money trading | NOT DONE (by design) | The autopilot is paper-only. Live trading needs the owner's separate arming, as required. |
| Start with Windows | DONE | Optional checkbox: adds the program to this Windows user's Run list (no administrator rights needed). |

## Owner's master prompt, revision 13 (docs/specs/)

The two owner documents are stored unchanged: `docs/specs/AI_Trading_System_Master_Prompt.md` (revision 13) and
`docs/specs/Backtested_Working_Strategies.md`. `scripts/import_master_prompt.py` imports the registry from the first.

| Requirement (section) | Status | Evidence / limitation |
|---|---|---|
| Install the strategies that work, leave the ones that don't | DONE | Backtested_Working_Strategies.md lists **0 qualifying strategies**, so no strategy is installed as tradeable. Every card is installed in the catalog with its true state: 30 of 124 can run here and are tested automatically; 94 are blocked with a reason code (49 PRODUCT_UNSUPPORTED, 36 INSUFFICIENT_DATA, 3 PERMISSION_MISSING, 2 FUNDING_UNFAVORABLE, 2 BORROW_UNAVAILABLE, 1 RELATIONSHIP_BROKEN, 1 rules incomplete). |
| 124-card catalog, 98 sources, 212-entry research index, one registry for every agent (5C, 5I) | DONE | Imported verbatim (ST001-ST080 re-import identically to before). Each card shows evidence labels, sources with access labels (A, P, M, B, K, D), implementation, reason code, lifecycle state and research state. The 212 index entries are discovery records (stage "discovered", DATA_BLOCKED: they need a point-in-time stock universe). Test: `test_catalog_has_all_124_cards_98_sources_and_212_index_entries_mapped`. |
| New cards this software can run (ST082, ST083, ST121, ST122, ST123) | DONE | ST082 residual momentum and ST083 52-week-high distance (portfolio templates on seven large US stocks, survivorship-biased, capped at RESEARCH FURTHER), ST123 multi-horizon crypto channel ensemble (portfolio template), ST121 intraday noise-band momentum and ST122 activity-filtered opening-range breakout (new single-market generators). Look-ahead tests cut the data at several points and check no earlier signal changes. |
| Owner's batches recorded as rejected evidence (revisions 11-13) | DONE | Batch 01 (48 configurations), Batch 02 (36) and Batch 03 (6): 0 positive after base costs, validation not opened. Shown per card and in a "Your batches" tab, separate from this installation's tests; not re-run here. |
| Research states (revision 12) | DONE | DATA_BLOCKED, RULES_INCOMPLETE, IMPLEMENTED_RESEARCH_ONLY, TEST_COMPLETE, REJECTED_UNDER_TEST, VALIDATION_PENDING (DISCOVERED for index entries), computed from the mapping and the research ledger. |
| No backtest button, test forms or manual training (2, 6) | DONE | Removed from the interface: the Strategy lab form, the catalog's Backtest and Add-paper-bot buttons, job cancel. Removed routes: POST /api/research, POST /api/catalog/{id}/research, POST /api/portfolio-bots, POST /api/research/jobs/{id}/cancel. The research evidence stays visible read-only. Self-test checks the route is gone. |
| Entries blocked until a strategy qualifies; safe idle in cash (revision 12, 5F) | DONE | Deterministic risk check "strategy qualified" (reason code STRATEGY_NOT_QUALIFIED) on every strategy order; the bot and portfolio-bot loops also abstain early and may still exit. Qualified = latest finished research run on the same market and timeframe has verdict PAPER TEST and the autopilot has not retired it. The PROBATION tier is removed and old probation bots retire. Tests: `test_entries_wait_in_cash_until_a_strategy_qualifies`, `test_a_bot_whose_strategy_says_buy_waits_until_the_strategy_qualifies`, `test_risk_service_blocks_unqualified_entries_but_never_exits`, `test_unqualified_portfolio_bot_buys_nothing`. |
| Same decision code in research and live; intraday flat by the close (4, 5F) | PARTIAL | The new intraday generators and the ST022 first-half-hour generator now take the session close from the New York clock, not from later bars (they used to look at the session's last bar, which a live bot cannot know; ST022 also held overnight in research). Early closes and other exchanges are not modelled; other strategies do not yet declare entry windows and flattening deadlines. |
| Three pages with the specified names (2, 8) | DONE | AI Trading System · AI Supercomputer — Agent Activity · Brokers & Accounts. |
| Start System, Pause New Entries, Stop, Emergency Stop (2, 8) | DONE | Start System is what the program does when it opens; the button shows it running. Pause New Entries blocks new exposure but lets exits through and survives a restart. Flatten All closes paper positions through the risk service. |
| Colour palette (8A) | PARTIAL | The specified design tokens (midnight navy, cyan, violet, teal, magenta, gold, coral) are applied across the pages and charts. **The video-based layout is not built**: no core/vortex view, node network, KPI strip or 5:7 split. The video file is not available to this build. |
| 320 independent trading agents A001-A320 with a Supercomputer Brain (3, 4) | NOT DONE | The system runs up to six single-market paper bots plus two portfolio bots chosen by the autopilot, with 102 agents advising each decision. No 320 independent trading workers, market partitions, ownership leases or capital reservations per agent exist. Page 2 shows the real counts, not 320. |
| 50 shared capabilities C01-C50 (4) | PARTIAL | Page 2 lists the 25 roles of the previous revision with their real state; the revision 13 list of 50 capabilities is not mapped one by one. |
| Global stock, crypto and meme-coin coverage across chains and venues (3) | NOT DONE | 55 instruments from Coinbase, Kraken and Yahoo. No exchange-wide discovery, no on-chain data, no DEX or launchpad adapters, no meme-coin taxonomy. |
| Equity and drawdown chart; session report; exports (8) | DONE | Equity recorded every 60 s (1D/1W/1M/1Y); session report with a JSON export labelled paper or live. |
| Attribution by strategy, market and costs | DONE | Net P&L, fees and slippage against the decision price, per strategy and per market. |
| Page 2 detail drawers and filters (8) | PARTIAL | 25 roles with state and latest result; no per-agent drawer, team/asset filters or network view. |
| Page 3 Brokers & Accounts (8, 9, 5B) | DONE / NOT DONE | Capability matrix and market coverage. **Add Funds is not built.** |
| Speaking assistant and voice tools (10, 11) | PARTIAL | Answers from verified state; explains that the system waits in cash while nothing qualifies; British English browser voice; proactive events with expiry and de-duplication; pause new entries is its only control; money and live commands refused. Not built: cloud voice or WebRTC, quiet hours, volume, announcement lifecycle, latency measurements, "that bot" references. |

## Stack

| Requirement | Status | Evidence / limitation |
|---|---|---|
| Python + FastAPI backend | DONE | `backend/tradingai/api/server.py` |
| React + TypeScript frontend | DONE | `frontend/` (Vite build, strict TypeScript) |
| WebSockets for live updates | DONE | `/ws`: catch-up of missed events on reconnect. |
| SQLite (transactions, migrations) | DONE | WAL, synchronous=FULL, schema v2. |
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
| Hundreds of strategy templates | DONE | 1,418 templates: 101 generators × 6 filters × 4 exits. 26 near-duplicate templates were pruned. 1,403 can run; 15 need data that is not connected. |
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
| Exactly three pages | DONE | AI Trading System, AI Supercomputer — Agent Activity, Brokers & Accounts (the names in the specification). Details open in drawers and dialogs. |
| AI Trading System | DONE | Candlestick chart with fills; Start System / Stop; Pause New Entries; Flatten All; paper/shadow mode; autopilot; bots; positions; equity chart and session report; profit and loss; regime and agents; risk meters and editable limits; strategy catalog; read-only research evidence. |
| Brokers & Accounts | DONE | Account and balances; paper balance setting; connections (vault, test, remove); capability matrix; market coverage; live readiness and arming; orders and fills; reconciliation. |
| AI Supercomputer — Agent Activity | DONE | Decision feed with agent votes, conflicts, vetoes, risk checks, execution and audit trail; live event stream; the 25 roles; system health; research ledger; agent roster. |
| SIMULATED labels | DONE | Paper balances, DEMO prices and backtests on simulated data are labelled on every page. |
| Works at phone width | DONE | No horizontal scrolling at 390 px (checked in Chromium). |

## Known gaps

1. Not tested on a physical Windows PC; tested only under Wine.
2. No broker adapter is verified against a real account, so live trading cannot be armed.
3. No news, economic-calendar, funding, order-book or on-chain feeds are connected.
4. Machine-learning models and the portfolio optimizer are not used in live decisions.
5. Execution algorithms are not selectable per bot.
6. Futures use continuous series; there is no per-contract roll data.
7. FX financing is not modelled.
8. The program is not code-signed.
9. No GPU acceleration.
10. 94 of the 124 catalog templates cannot run here (see the catalog for each reason code); 0 strategies qualify, so no trade is opened until one does.
11. The assistant uses browser speech; no cloud voice provider is connected.
12. Add Funds is not built.
13. Revision 13's 320-agent fleet, global and meme-coin coverage and video-based layout are not built (see the revision 13 table).
