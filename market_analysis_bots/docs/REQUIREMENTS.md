# Requirements: day-trading research library and market-analysis bot platform

Version 1.0, 2026-09-27. Owner: the user (Canada). Author: Claude.

This document fixes what will be built, how success is measured, and what is out of
scope, **before** any strategy is evaluated. Thresholds here are not relaxed later to
claim success; if one is missed, the report says so.

## 1. Answers received and provisional assumptions

| Topic | Answer | Provisional assumption where the answer was open |
|---|---|---|
| Jurisdiction and markets | Canada; US stocks and crypto; "an unlimited number of markets" | Universe is configuration-driven with **no hard-coded cap**. Practical capacity is bounded by public API rate limits and the host CPU, and is measured (Stage 3/4), not assumed. |
| Data and budget | Free software, free data | $0/month. Only public, key-free endpoints. No paid feed is assumed anywhere. |
| Hosting | The user's Windows PC, when on | Bots run while the process runs. Nothing runs when the PC is off. Restart recovery is required. |
| Scope and paper account | Customisable paper balance, changeable at any time; wants real brokers and real money | Analysis **and** paper trading. Paper balance adjustable at any time via deposits/withdrawals recorded as cash flows (never counted as returns). Default $10,000, 0.5% risk per trade, 3% daily loss limit, 15% drawdown halt, 10 concurrent positions. |
| Real money | Requested | **Not enabled.** Real-money order submission stays disabled in code. See section 7. |
| Timeframes | Not specified | 1m, 5m, 15m, 1h bars; tick/trade and order-book streams for crypto where a strategy needs them. |
| Operating system | Windows | Code is standard-library Python 3.11+ so it runs on Windows, macOS and Linux. Built and tested here on Linux (4 vCPU, 15 GB RAM); Windows is not directly tested in this environment. |

## 2. Initial supported universe (measured availability, 2026-09-27)

Probed from this environment; each row was an actual HTTP request.

| Venue / source | Instruments | Data available free | Not available |
|---|---|---|---|
| Yahoo Finance chart API | US-listed stocks and ETFs (any ticker) | Bars: 1m (last ~7 days per request, ~30 days total), 2m/5m/15m (60 days), 1h (730 days), 1d (decades); pre/post-market bars | NBBO quotes, trade prints, order book, borrow availability, official corporate-action feed |
| Coinbase Exchange public REST + WebSocket | Crypto spot (USD, USDC, USDT quotes) | 1m-1d candles (300 per request, pageable), recent trades, level-2 book snapshots, live trade and book streams | Historical order books |
| Kraken public REST | Crypto spot (~670 USD pairs) | OHLC (720 most recent bars per interval), recent trades, depth | Deep intraday history, historical books |
| OKX public REST | Crypto spot and perpetual swaps | 1m candles with deep paged history, trades, books (400 levels), funding-rate history, open interest | Historical order books beyond recent |
| Deribit public API | BTC/ETH implied-volatility index (DVOL) | Hourly history | Options chains are not used in v1 |
| Nasdaq public calendar | US earnings dates | Daily calendar | Historical revisions |

**Excluded, with reasons**

* Binance (HTTP 451) and Bybit (HTTP 403): blocked from this network.
* Alpaca and Polygon (HTTP 401): require keys and, for useful stock data, paid plans.
* SEC EDGAR (HTTP 403): requires a declared User-Agent contact. Filing-driven strategies are
  specified but blocked until the user supplies a contact string in local settings.
* Stock order-flow, quote-imbalance and spread strategies: no free quote or trade data. Specified,
  marked `blocked` with the exact missing dependency.
* Options, futures on regulated exchanges, forex, bonds: out of scope for v1.

**Sessions.** US equities: regular session 09:30-16:00 America/New_York from an explicit
exchange calendar (weekends, NYSE holidays, early closes), with DST handled through the
calendar, not fixed UTC offsets. Crypto: trades 24/7; the platform's crypto "trading day"
is the UTC calendar day, and day-trading strategies on crypto close positions at 23:55 UTC
or after their declared maximum holding time, whichever is first.

## 3. Deliverables

* **Package A, `strategies/`:** `day_trading_strategies.xlsx`, machine-readable strategy
  definitions, source register, taxonomy and duplicate-review notes, validation methodology,
  evaluation results, ranking methodology.
* **Package B, `market_analysis_bots/`:** runnable platform, bot configurations and registry,
  data adapters, replay and paper-trading, dashboard, risk configuration, dependency files,
  secret-free example configuration, operating instructions, tests and actual test results.

Packages are linked only through stable strategy IDs (`STRAT-###`) and version strings.

## 4. Acceptance criteria

### Package A

| ID | Criterion | Measured by |
|---|---|---|
| A1 | Target of 300 distinct strategies; if fewer can be specified honestly, the verified count plus a separate backlog | Automated count; duplicate-review log |
| A2 | Every strategy ID unique and stable (`STRAT-001`...) | Automated check |
| A3 | Every required field present for every strategy (identity, data, rules, risk, evidence, four status fields) | Automated schema check, 100% required |
| A4 | Variants (parameter, ticker or timeframe changes) stored under a parent, never counted as strategies | Automated check that variants have `parent` and are excluded from the count |
| A5 | Every cited source has a URL (or bibliographic reference for print-only works), access date and a note of what it supports; no source is cited that was not actually located | Automated check plus manual verification log |
| A6 | No strategy labelled "proven"; evaluation status reflects actual runs only | Automated check against the evaluation results file |
| A7 | Workbook opens and contains Index, Catalog, Sources, Evaluation and Implementation sheets | Automated load test with openpyxl |

### Package B

| ID | Criterion | Measured by |
|---|---|---|
| B1 | At least 250 bot configurations when supported, each with a stated purpose, strategy ID and version, universe, timeframe, parameters and risk settings | Registry validator |
| B2 | Registry matches the configuration files one-to-one; every strategy reference resolves | Automated check |
| B3 | Shared ingestion: at most one data request per (source, instrument, timeframe) per refresh, however many bots use it | Request counter in tests and soak test |
| B4 | Risk controls enforced outside strategy code and not bypassable by bot configuration | Automated tests that attempt bypasses |
| B5 | Real-money order submission disabled in code | Automated test |
| B6 | Each bot exposes: data received, last evaluation time, decision, reasons (indicator values, thresholds, rule outcomes), strategy and config version | Dashboard/API inspection test |
| B7 | Failure scenarios pass: network interruption, stale data, duplicate and out-of-order events, restart, corrupt state, invalid config, storage failure, risk-limit breach | Automated tests, labelled synthetic where synthetic |

### Stage gates (declared before testing)

| Stage | Bots | Pass thresholds |
|---|---|---|
| 1 | 1 | Live data ingested; features and a decision record produced for every completed bar for 30 minutes; at least one paper order path exercised (live or, if no signal occurs, a labelled synthetic event); state survives a restart; dashboard shows the bot. Zero unhandled exceptions. |
| 2 | ~10, at least 5 strategy families | Shared data verified (B3); portfolio risk blocks a conflicting or duplicate intent (test); recovery test passes; 30-minute live run with zero unhandled exceptions. |
| 3 | ~50 | Over a 30-minute live run: p95 time from data arrival to decision under 5 s; HTTP 429 responses under 1% of requests; storage growth reported per hour and under 100 MB/hour. |
| 4 | at least 250 | Soak test of at least 2 hours on live feeds (the longest this session can support): at least 95% of scheduled evaluations completed; every bot emits a health record at least once per evaluation cycle; no cross-bot state corruption; peak memory under 2 GB; errors, recoveries and gaps reported in full. |

A configuration file is not a running bot, a replay is not live operation, and a successful
startup is not proof of continuous operation. Reports keep those counts separate.

## 5. Costs

| Item | Cost |
|---|---|
| Market data | $0 (public endpoints only) |
| Software | $0 (Python standard library; `openpyxl` only to build the workbook) |
| Hosting | The user's PC; electricity only. Optional always-on VPS for 24/7 crypto: roughly $10-40/month (not selected) |

## 6. Dependencies

* Python 3.11 or newer.
* `openpyxl==3.1.5` for generating and checking the workbook (Package A tooling only).
* Network access to the endpoints in section 2.

## 7. Real money: current position

Order submission to real brokers is **disabled in code** and will stay disabled in this
build. Two independent reasons: the user's own specification requires a separate, explicit
authorisation step, and this development session's safety controls blocked real-money order
code earlier. What is delivered instead:

* a broker interface with the paper engine as its only enabled implementation;
* secure local credential storage (OS-protected on Windows) so keys are never pasted into
  chat, committed, or logged;
* written requirements for the separate authorisation step (section 8).

## 8. Unresolved decisions

1. **Real-money execution.** Needs: explicit written authorisation in a separate step; a
   broker chosen that serves Canadian residents with an API (e.g. Interactive Brokers for
   stocks; Kraken for crypto); read-only keys first; a paper-versus-live reconciliation
   period; the development environment's permission to write order-submission code.
2. **Paid data** for stock quotes/trades (unlocks stock order-flow and spread strategies and
   longer minute history).
3. **Always-on hosting** for 24/7 crypto coverage.
4. **SEC EDGAR contact string** for filing-driven strategies.
5. **Tax and regulatory questions** (Canadian brokers, margin rules, reporting) are the
   user's to confirm with a professional; nothing here is tax or legal advice.
