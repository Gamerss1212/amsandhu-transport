# Requirement matrix: master prompt sections 119-353

Section 350 asks for this table before anything is called finished. It was written on 2026-10-08 by reading the code
and running it, not from memory. Statuses:

- **DONE**: built and covered by an automated test or a recorded run.
- **PARTIAL**: some of it is built; the gap is named.
- **NOT BUILT**: nothing yet.
- **NEEDS EXTERNAL**: cannot be finished truthfully without an outside account, feed or paid data (section 352).
- **DEVIATION**: done differently on purpose; the reason is given.

Code paths: `jarvus-terminal/` (the app) and `market_analysis_bots/mab/` (the engine).

## Round 1 (2026-10-08): what changed

| Section | Change | Evidence |
|---|---|---|
| 121-122 | The Windows build is now one folder: `START_TRADING_AI.exe` + `_internal/`. Writes go to `data/` and `logs/` beside the exe. It starts faster than the old one-file build because nothing unpacks to a temp folder. | `jarvus.spec`; built with PyInstaller 6.22.3 under Wine |
| 269 | App state machine: 12 states, a transition table, impossible moves refused. Real money is reachable only through LIVE_LOCKED, then LIVE_ARMED, then LIVE_RUNNING. | `engine/appstate.py`; `tests/test_appstate.py` (6 tests) |
| 120 | Start-up checks: every database (quick_check), data folder writable, web files present, strategy library loads. A failure puts the app in ERROR and no bot engine starts. | `server.App.run_startup_checks`; test with a corrupted workspace database |
| 270 | `GET /health`: lifecycle, start-up checks, backend, database, strategy engine, market feed, execution, risk, brokers, trading state, live LOCKED/ARMED/RUNNING. No secrets, ids or balances. | `server.system_health`; test checks for secrets |
| 183 | Page 2 is labelled **Broker & Money** (was "Connections"). | `web/js/app.js` |
| 130, 132, 137, 202, 212, 322-324 | Typed instruments (9 market types, multiplier, tick, settlement, units), exact `Decimal` money, P&L with the contract multiplier, size from risk (rounds down; 0 = no trade), FX pips, index reference vs tradable proxy, broker contract check before an order. Versioned specs for 19 futures (ES MES NQ MNQ YM MYM RTY M2K GC MGC SI CL NG 6E 6B 6J 6C ZN ZC). | `mab/instrument_spec.py`, `mab/data/contract_specs.json`; `tests/test_contracts.py` |
| 133-134 | Futures roll schedule (calendar, or earlier on open interest), stitched / difference / ratio continuous series kept apart from the real-contract execution prices, delivery guard (an unknown first notice date blocks). | `mab/futures.py`; golden two-contract test |
| 165, 288 | **Defect found and fixed:** a backtest could report losing more than 100% of a cash account (a real run showed -936%). The account now stops at zero, flags `ruined` and its day, and keeps the plain sum separately as `net_pnl_uncapped`. | `mab/metrics.py`; test |

**Acceptance run (section 283), under Wine on Linux (Windows emulation):**

1. Copied the built folder into an empty one.
2. Started `START_TRADING_AI.exe`: the server came up and every start-up check passed.
3. Opened the session as the browser does. The paper engine started: 357 bots, 142 live market series, real money LOCKED.
4. A real browser (Chromium) rendered Command Center with no page errors.
5. A walk-forward backtest job ran to the end inside the exe on Coinbase BTC-USD data.
6. Shut down from the app's own Shut down action: every process ended.
7. Restarted twice: the same workspace came back, and a paper balance set to 12,345 was still 12,345.

**Not checked:**
- the browser opening by itself (Wine has no browser);
- a real Windows 11 PC;
- the `logs/` file (under Wine the program still has a console, so it prints there instead).

## The matrix

| Sec. | Requirement | Status | Evidence / gap |
|---|---|---|---|
| 119 | Many markets with market-specific engines | PARTIAL | Crypto spot (Coinbase, Kraken, OKX, NDAX) and US/Canadian stocks and ETFs trade on paper. Forex and gold/silver/oil ETFs on daily Yahoo data, paper only. Futures: metadata, P&L, roll and delivery logic now exist, but no futures data feed or broker is wired. Perpetuals: listed (OKX swaps), no funding model. |
| 120 | Local start-up sequence, 127.0.0.1 only | DONE | Binds 127.0.0.1; Host and Origin checks; start-up checks; port fallback; opens the browser once the app answers (`desktop.py`, `engine/launcher.py`) |
| 121 | One user entry point `START_TRADING_AI.exe` | DONE | Built and run under Wine (above) |
| 122 | Portable runtime: FastAPI + React/TS + Vite | DEVIATION | Python standard-library server and plain ES modules, no build step. Same result (one exe, no Python or Node needed); fewer moving parts and no new dependencies. A rewrite would risk the working safety code for no user-visible gain. |
| 123 | Single instance | DONE | Second launch finds the running copy through `/api/version` and opens it; exclusive port on Windows (`tests/test_launcher.py`) |
| 124 | SQLite for state; DuckDB + Parquet for big market data | PARTIAL | SQLite with migrations and WAL. No DuckDB or Parquet: research history is cached JSON, which is fine at today's sizes but not for years of tick data. |
| 125 | Crash-safe storage, reconcile on restart | PARTIAL | WAL, atomic writes, integrity check, backups (`mab/storage.py`). Live reconciliation runs every 5 health cycles and blocks the deployment on a mismatch. There is no single RECONCILIATION_REQUIRED app lock yet; it is per deployment, and now reported in `/health`. |
| 126 | Market intelligence layer (instrument to strategy compatibility) | PARTIAL | Instrument registry plus the new typed `Instrument`. Strategies declare data needs and refuse unavailable data. The new schema is not yet the one the runtime uses. |
| 127 | Stock engine: sessions, auctions, halts, corporate actions, short borrow | PARTIAL | NYSE and TSX sessions, holidays, early closes (`mab/clock.py`); adjusted Yahoo data. No auction or imbalance data, no halt feed, no borrow data (long-only on stocks). Survivorship bias is not removed (no point-in-time universe). |
| 128 | Crypto engine: spot vs perps, venues kept apart, funding | PARTIAL | Venues kept separate (`venue:symbol`); maker and taker fees per venue and fee profile. No funding, mark or index prices, liquidation data, or open interest feed. |
| 129 | Forex engine: OTC dealer quotes vs currency futures | PARTIAL | Yahoo daily FX only, paper; pip math now exists. No dealer bid/ask feed, no rollover financing; currency futures now have specs (6E 6B 6J 6C). NEEDS EXTERNAL: a dealer API such as OANDA. |
| 130-131 | Index reference vs tradable proxy; index internals | PARTIAL | `INDEX_REFERENCES` and `InstrumentBook.proxies`. No breadth or internals feed. |
| 132 | Futures P&L with the multiplier | DONE (library) | `instrument_spec.pnl`, golden tests (ES, MES, CL, ZN). Not yet used by the paper engine, which has no futures. |
| 133 | Roll engine; signal series separate from execution series | DONE (library) | `mab/futures.py`, golden test |
| 134 | Delivery safety | DONE (library) | `delivery_guard`; unknown first notice blocks |
| 135 | Futures market groups metadata | PARTIAL | 19 contracts with versioned specs; agriculture marked inactive (no data or broker) |
| 136 | Market calendar service, UTC inside | PARTIAL | UTC milliseconds throughout; NYSE holidays from rules; crypto 24/7. No futures, CME maintenance or FX session calendars. |
| 137 | Universal instrument schema | PARTIAL | Built (`Instrument`, `InstrumentBook`); runtime adoption pending |
| 138-140 | Cost, slippage and impact models; capacity | PARTIAL | Fees per venue and fee profile, spread and slippage by liquidity tier, stops pay 2x slippage, participation cap 5% (`mab/costs.py`). No order-book or empirical slippage model, no capacity estimate. |
| 141 | 350+ distinct strategy templates | PARTIAL | 414 catalogued with sources (147 sources). 155 executable, 259 blocked for missing data, said plainly. 197 of the 414 are memecoin rules, so structural variety is lower than the count suggests. |
| 142 | Formal strategy contract per strategy | PARTIAL | Catalog entries carry hypothesis, data needs, warmup, rules, status and sources. The lifecycle methods are one shared TradeManager, not per-strategy classes. |
| 143-154 | Family coverage (trend, momentum, reversion, breakout, VWAP, stat-arb, order flow, volatility, crypto, FX, futures, cross-market) | PARTIAL | Families present: trend 18, opening range 11, VWAP 6, reversion 10, order flow 14 (most blocked: no L2 data), cross-asset 12, crypto structure 14, statistical 5. FX-specific and futures-specific families are not built. |
| 155 | 275+ indicators with formulas | PARTIAL | 118 registered with formulas and warmups (`docs/INDICATORS.md`) |
| 156 | AVAILABLE_AT on every feature | PARTIAL | Rules are causal (bar i uses bars up to i), and only closed bars are used. No per-feature available_at timestamp field. |
| 157-160 | Research pipeline, chronological splits, walk-forward, purging | PARTIAL | Train/validation/test splits, folds, random and buy-and-hold baselines, bootstrap intervals (`mab/research/evaluate.py`). Purging and embargo apply only where labels overlap. Shadow and micro-live stages exist only as deployment modes. |
| 161 | Multiple-testing protection | PARTIAL | Trial counts and stated searches in the evaluation reports. No trial ledger across all research and no DSR/PBO in Jarvus (QuantAgents has both). |
| 162-164 | Parameter robustness, Monte Carlo, regime tests | PARTIAL | Full-system backtest replayed many times; brain regimes. No parameter heatmaps. |
| 165 | Full backtest report | PARTIAL | Net and gross, fees, win rate with expectancy, Sharpe, Sortino, Calmar, drawdown, VaR, streaks. Ruin is now reported. No CVaR or time-under-water. |
| 166-167 | Quality score; champion and challenger | PARTIAL | Model registry with versions, approvals and promotions; drift check (`mab/research/registry.py`). No composite quality score. |
| 168 | No unattended self-rewriting of live code | DONE | Research jobs and the assistant can propose; promotion needs the owner; live bots need START LIVE |
| 169-171 | 100+ logical agents, disagreement, orchestrator with risk veto | PARTIAL | Fleet Brain over 357 bots, and ULTRON councils of 25 agents. The brain's veto and resize pass through `mab/risk.py`. Not 100 named agent roles, and correlated evidence is not deduplicated across agents. |
| 172-173 | Non-bypassable risk service; fat-finger checks | DONE | Every intent goes through `RiskManager.check`: duplicate intent, emergency stop, paused, data quality, price freshness, daily loss, fleet and bot order rates, open-position limit, conflicting positions, exposure limits. Then the execution engine's own checks (`tests/test_execution.py`). Not yet: a price-distance check against the last quote at order time in the risk layer itself. |
| 174-175 | Always-visible kill switch; daily loss lock | DONE | EMERGENCY STOP in the top bar on every page; deployment and live daily loss limits; a drawdown triggers the kill switch |
| 176-178 | Arming states; shadow; micro-live | PARTIAL | Live needs the typed acknowledgement, caps and START LIVE per bot; arming is now named in `/health`. Deployment modes: demo, paper, live. No SHADOW mode that sends nothing while comparing to real fills. |
| 179-181 | Broker adapter standard; capability matrix | PARTIAL | One adapter interface (`mab/execution/base.py`) for paper, Alpaca (paper and live), Kraken, NDAX; capabilities stored per connection. NEEDS EXTERNAL: no adapter was tested against a real account in this round (no keys shared). IBKR, OANDA and Coinbase Advanced are not built. |
| 182 | Secure key storage | DONE | Encrypted vault; key protected by Windows DPAPI on Windows, keyring elsewhere; never returned to the page (`tests/test_server.py`) |
| 183-189 | Three pages, explainability, data health | DONE | Command Center, Broker & Money, Live Intelligence; per-decision audit with correlation ids; health panel with p50/p95 latency and HTTP 429 counts |
| 190-192 | Performance, event-driven agents, research profiles | PARTIAL | Research runs in a separate bounded worker pool, never on the trading thread. No FAST/STANDARD/DEEP profiles. |
| 193-194 | Reproducibility; research ledger | PARTIAL | Jobs store spec hash, code version, seed and strategy version; failed jobs are kept |
| 195-198 | ML baselines, calibration, ensembles | PARTIAL | The brain reports Brier score; the volatility gate is evaluated on held-out data. No reliability curves shown in the app. |
| 199-203 | Diversification, portfolio risk, sizing, event risk | PARTIAL | Exposure caps, conflict policy, risk-based sizing; event calendar for scheduled events. No correlation clusters. |
| 204 | LLM output is advisory only | DONE | The assistant has no order tools (`mab/assistant.py`); its ideas are validated and registered for research only (`test_candidates_are_validated_and_only_registered_for_research`); news is wrapped as untrusted data |
| 205 | Manipulation filter | PARTIAL | No strategy in the catalog spoofs, layers or wash-trades. There is no automated filter yet that rejects such ideas from the assistant or a generator. |
| 206-210 | Test suite, golden backtests, leakage tests, execution tests | PARTIAL | 258 automated tests across engine and app; golden money tests added. No golden 10-bar test of the rule engine itself yet. |
| 211-212 | Jurisdiction profile; versioned market rules | PARTIAL | Contract specs are now versioned data. No jurisdiction profile (Canada, the owner's country, is assumed in the docs). |
| 213-214 | Audit log; correlation ids | DONE | Append-only audit table, SSE stream, CSV export |
| 215-218 | Safe shutdown, recovery, stale data, broker disconnects | PARTIAL | Shut down stops engines and keeps open trades recorded; the watchdog restarts a crashed engine; stale data blocks entries; orders unresolved after a timeout block the deployment instead of being resent (`router`). Not tested this round: a kill while a live order is pending. |
| 219 | Order idempotency | DONE | Durable client_order_id per intent |
| 220-221 | Measured latency; execution quality | PARTIAL | Evaluation and data latency p50/p95 measured. No implementation-shortfall report. |
| 222-223 | Data quality score; data requirements | DONE | `mab/data/quality.py`; strategies needing missing data are blocked, never approximated |
| 224-226 | Realistic paper; backtest vs paper vs live; drift | PARTIAL | Paper fills pay fees, spread and slippage with a liquidity cap; drift jobs. No three-way comparison table yet. |
| 227-229 | Data drift, provenance, source grades | PARTIAL | Source register with evidence levels; HTTP provenance on records |
| 230-243 | Research principles, generator, adversarial tests, netting, attribution | PARTIAL | Strategies start as hypothesis or untested; per-deployment attribution. No "remove best trades" or symbol-exclusion tests. |
| 244-250 | Intraday data, multi-timeframe, bars, outliers | PARTIAL | 1m to 1d bars from venues; only closed bars; the quality layer flags bad ticks without deleting them |
| 251-253 | Responsive UI, real progress, cancellable research | DONE | Background jobs report progress and can be cancelled |
| 254-256 | Exports and reports | PARTIAL | Audit CSV export; JSON results. No PDF report. |
| 257-263 | Promotion filters, human review, risk settings, safe defaults, local security | DONE | Paper by default; live needs owner authorisation and caps; session cookie, CSRF token, Host and Origin checks, strict CSP |
| 264-266 | Content security, pinned dependencies, plugins | PARTIAL | CSP, no HTML from APIs; the plugin system is not built |
| 267-268 | Code quality, layout | PARTIAL | Typed where new; existing modules are partly typed; no mypy gate in Jarvus |
| 269-270 | State machine; /health | DONE | This round |
| 271-282 | Benchmarks, caches, network resilience, rate limits, environment isolation, offline mode | PARTIAL | One shared HTTP client with backoff and 429 handling; LIVE banner. Not measured this round: a cold start with no internet. |
| 283 | Localhost acceptance test | DONE (Wine) | See the acceptance run above; real Windows 11 not tested |
| 284 | Broker acceptance per adapter | NEEDS EXTERNAL | Needs the owner's paper or demo accounts; adapters stay EXPERIMENTAL until then |
| 285 | Backtest acceptance (leakage, commission, slippage, partial fill, multiplier, roll, corporate actions, timezones) | PARTIAL | Multiplier, roll, money and ruin are proven by golden tests; commission and partial fills are covered by execution tests; corporate actions are not covered in Jarvus |
| 286-287 | Risk and recovery acceptance | PARTIAL | Bad orders are blocked in tests; a forced kill with a pending order was not run |
| 288 | Research truthfulness | PARTIAL | Labels separate SIMULATED from real; this round fixed the impossible below -100% returns. Continuing check. |
| 289-353 | Build order, benchmarks, honest language, final review | ONGOING | This round did phases A and B first, as section 289 orders |

## Next rounds, in the order section 289 sets

1. **Phase B to C:** make the paper engine and the backtester use `Instrument` and `Decimal` for every fill and
   ledger entry. Add a golden 10-bar test of the rule engine: known entry, exit, fees and exact P&L.
2. **Phase D:** an empirical slippage model from the app's own paper fills; capacity estimate; cost stress at 1.25x,
   1.5x and 2x in every report.
3. **Phase E-F:** an app-level RECONCILIATION_REQUIRED lock; a SHADOW mode (real data, orders recorded but never sent);
   a forced-kill recovery test.
4. **Phase G (needs the owner):** paper or demo accounts for each broker, to run section 284.
5. **Phase J:** one trial ledger across all research, with DSR and PBO (port from QuantAgents), plus "remove best
   trades" and symbol-exclusion tests.
6. **Phase K onwards:** more strategy families (FX sessions, futures) only once the above passes, and only with data
   that exists.
