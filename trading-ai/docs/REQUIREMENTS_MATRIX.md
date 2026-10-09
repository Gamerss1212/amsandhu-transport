# Requirements matrix — Trading AI 1.2.0

Status meanings:
* **DONE**: implemented and exercised by a test or by the self-test.
* **PARTIAL**: implemented, with a limitation stated in the same row.
* **REQUIRES CONNECTION**: the interface exists, but it needs a credential, paid dataset or service this build does not have.
* **NOT DONE**: not built.

How it was verified:
* **Unit tests**: 87 tests (`backend/tests`).
* **Self-test**: `START_TRADING_AI.exe --selftest` runs 22 steps over HTTP and WebSocket against the real server. It passed on the built Windows exe under Wine.
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
| Runs by itself after the double-click (no setup, no clicks) | DONE | The Autopilot is on by default. It screens strategies with FAST research and confirms the promising ones with STANDARD research (rate-limited, one job at a time). It then starts paper bots for strategies that are QUALIFIED (passed every gate) or on PROBATION (strict out-of-sample conditions, labelled as such), monitors them, and retires those whose paper results fall short or whose re-test on newer data fails. Covered by tests (`test_autopilot.py`) and a self-test step. |
| Owner keeps control | DONE | START BOT turns everything on and STOP BOT turns everything off. A bot the owner stops is never restarted by the autopilot. EMERGENCY STOP blocks the autopilot, and the autopilot never re-arms. |
| Fully automated real-money trading | NOT DONE (by design) | The autopilot is paper-only. Live trading needs the owner's separate arming, as required. |
| Start with Windows | DONE | Optional checkbox: adds the program to this Windows user's Run list (no administrator rights needed). |

## Owner's master prompt (docs/specs/AI_Trading_System_Master_Prompt.md)

| Requirement (section) | Status | Evidence / limitation |
|---|---|---|
| 80-template catalog with its source register (5C) | DONE | All 80 cards (ST001-ST080) and 47 sources are loaded from the specification into `strategies/data/`. Each card shows its published evidence label (R/C/H), its sources with access labels, how this software implements it, the lifecycle state and this installation's own backtests (catalog drawer on the AI Trading System page). Test: `test_catalog_has_all_80_cards_and_47_sources_mapped`. |
| Turn templates into executable specifications (5D) | PARTIAL | 25 of 80 templates are runnable here: 10 as multi-asset portfolio templates (ST001, ST001-E, ST004, ST005, ST009, ST010, ST017, ST018, ST040, ST045, ST046) and the rest as single-market generators (three new ones: structure break ST031, sweep and reclaim ST032, failed breakout ST026). The other 55 say what blocks them with a reason code: 25 need data this build does not have (fundamentals, point-in-time membership, order books, news), 23 need products it does not support (options, bonds, dated contracts), and 7 need borrow, funding, account permissions or a tested pair relationship. |
| What "best" and "working" mean (5A) | DONE | Held-out period never used for tuning; benchmark comparison; costs and 2× costs; walk-forward; Deflated Sharpe charged with every trial in the family; PBO; placebo. Verdicts are REJECT, RESEARCH FURTHER or PAPER TEST only. Survivorship-biased templates are capped at RESEARCH FURTHER. |
| Portfolio templates, no look-ahead, next-day execution | DONE | Weights decided at a rebalance close, filled at the next day's close; gross exposure capped at 1. Tests: look-ahead test for every portfolio template, execution and cost test. |
| Backtests of the catalog on real data | DONE | `scripts/catalog_batch.py` then `scripts/catalog_report.py` write `docs/CATALOG_BACKTEST_REPORT.md`. No template reached PAPER TEST; see that report for every number and caveat. |
| Automatic selection and continuous review (5F) | DONE | The autopilot also tests portfolio templates weekly and can run up to two portfolio paper bots (15% of the account if qualified, 10% on probation; only if they beat equal weight held out). Portfolio bots retire at a 15% loss of their allocation or when a re-test fails; every bot is re-validated every 14 days. |
| Reason codes (5F) | DONE | The 14 codes in the specification plus 7 used by this software (ENTRIES_PAUSED, KILL_SWITCH, TRADING_LOCKED, MARKET_CLOSED, RECONCILIATION_REQUIRED, INVALID_ORDER, CONTRACT_TOO_LARGE). Every risk check and research gate maps to one; they appear on orders, decisions, research results and catalog cards. |
| Page 1 controls: Start, Pause New Entries, Stop, Emergency Stop (8) | DONE | Pause New Entries blocks new exposure but lets exits and reduce-only orders through, and survives a restart (test). Flatten All closes paper positions with reduce-only orders through the risk service and reports each instrument's real outcome. |
| Equity and drawdown chart; session report; exports (8) | DONE | Equity is recorded every 60 s (1D/1W/1M/1Y views). The session report lists trades, costs, blocked decisions, incidents, strategy changes and remaining exposure, with a JSON export labelled paper or live. |
| Attribution by strategy, market and costs (role 23) | DONE | Net P&L, fees and slippage against the decision price, per strategy and per market, from the fills ledger. |
| Page 2 Agent Activity: every role and what it is doing (4, 8) | PARTIAL | All 25 roles with implementation, live state (running, waiting for data, idle, blocked...) and latest result; counts of roles, agent functions, running jobs, queue depth, stale feeds and model calls (0: no cloud AI). There is no per-agent detail drawer and no filter by team or asset class yet. |
| Page 3 Brokers & Accounts: capability matrix, market coverage (8, 9, 5B) | DONE / NOT DONE | Capability matrix and a market-coverage card. **Add Funds is not built**: this software does not link to any broker's funding page. |
| Speaking assistant (10) | PARTIAL | On every page. Answers come only from verified system state (no cloud AI). Speech uses the browser's own voices, preferring a British English one; the microphone uses the browser's recognizer where available. Proactive announcements carry an id, category, severity, subject, creation and expiry time and a deduplication key; old ones are not spoken; fills are batched; asking or pressing the microphone stops speech. Not built: a cloud voice API or WebRTC, quiet hours, volume control (browser volume only), the full announcement lifecycle, latency measurements. |
| Voice tools and permissions (11) | PARTIAL | Typed intents answer all eight example questions. Pause New Entries is the only control the assistant may perform; going live, raising capital or leverage, moving money and flattening are refused and sent to the page. Command ids make a retried command a no-op. The transcript lives only in the open page and is not stored. Not built: resolving "that bot" from page context. |

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

## Research engine (Strategy lab)

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
| Exactly three pages | DONE | AI Trading System, Agent Activity, Brokers & Accounts (the names in the specification). Details open in drawers and dialogs. |
| AI Trading System | DONE | Candlestick chart with fills; START/STOP BOT; Pause New Entries; Flatten All; paper/shadow mode; autopilot; bots; positions; equity chart and session report; profit and loss; regime and agents; risk meters and editable limits; strategy catalog; Strategy lab. |
| Brokers & Accounts | DONE | Account and balances; paper balance setting; connections (vault, test, remove); capability matrix; market coverage; live readiness and arming; orders and fills; reconciliation. |
| Agent Activity | DONE | Decision feed with agent votes, conflicts, vetoes, risk checks, execution and audit trail; live event stream; the 25 roles; system health; research ledger; agent roster. |
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
10. 55 of the 80 catalog templates cannot run here (see the catalog for each reason code).
11. The assistant uses browser speech; no cloud voice provider is connected.
12. Add Funds is not built.
