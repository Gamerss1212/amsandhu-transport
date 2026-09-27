# Market analysis bots (paper trading)

A platform that runs up to 250 independently configured, rule-based bots on shared live market data, with a
paper-trading engine, a portfolio risk layer, storage, monitoring, a dashboard and a command line. It runs on your own
computer with Python 3.11+ and needs no paid data or packages. It is also built into **Jarvus Terminal** (Fleet and
Library tabs), so on Windows you can just run `JarvusTerminal.exe`.

**Real-money trading is not available.** No code in this package can submit an order to a real broker or exchange
(`mab.broker.LiveBroker` refuses every call). Adding it would be a separate, explicitly authorised change.

## Quick start (source)

```
cd market_analysis_bots
python -m mab init                     # creates config/fleet.json (from the example) and the database
python -m mab start --stage 10         # 10 bots; --stage 50, or no --stage for all 250
# dashboard: http://127.0.0.1:8765/
```

Other commands: `status`, `inspect BOT-012`, `pause`, `resume`, `emergency-stop`, `clear-emergency`,
`balance [show|set|deposit|withdraw] AMOUNT`, `test-order BOT-001`, `replay BOT-012`, `recover`, `backup`,
`bots`, `dashboard` (for a fleet running in another window), `secret set NAME`, `stop`.

## How it works

```
venues (Coinbase, Kraken, OKX, Yahoo) -> data hub (one poll per series, quality checks) -> shared Frames
   -> each bot: rules evaluated on completed bars -> TradeManager decision -> order intent
   -> portfolio risk check -> paper broker (order-book walk / synthetic stock fill) -> fills
   -> account (customizable balance, time-weighted return) -> SQLite storage -> health, dashboard
```

| Part | Module | Notes |
|---|---|---|
| Venue adapters | `mab/data/adapters.py` | completed bars only; aggressor side normalised; forming bars dropped |
| HTTP client | `mab/net.py` | per-host token buckets, bounded retries with jitter, Retry-After, circuit breaker, counters |
| Data quality | `mab/data/quality.py` | schema, impossible prices, future stamps, duplicates, revisions, late bars, gaps, jumps, stale |
| Ingestion hub | `mab/data/hub.py` | shared series, coalesced polling, bounded workers (backpressure), gap backfill, order-flow capture |
| Calendars | `mab/clock.py` | NYSE and TSX holidays/early closes from rules; New York DST; crypto UTC day |
| Indicators | `mab/indicators.py` | 65 causal indicators, documented in `docs/INDICATORS.md` |
| Rule language | `mab/expr.py` | AND/OR/NOT, crossovers, persistence, lags, multi-timeframe and multi-instrument alignment |
| Strategy runtime | `mab/strategy.py` | one TradeManager for backtest, replay and live; stops before targets; bracket orders |
| Risk | `mab/risk.py` | exposure caps, concentration, conflicting positions, duplicates, rate limits, loss limits, kill switch |
| Paper broker | `mab/broker.py` | latency, book-walk slippage, partial fills (IOC), fees, rejections; stock fills labelled synthetic |
| Account | `mab/account.py` | set the balance to any amount at any time (deposit / withdraw / set), running or stopped; open trades are never closed for it; performance is time-weighted |
| Fleet Brain | `mab/brain.py` | the coordinator every bot is connected to; see below |
| Storage | `mab/storage.py` | SQLite WAL; signals, intents, risk decisions, orders, fills, trades, health, events; retention; backups |
| Runtime | `mab/runtime.py` | bot isolation, auto-disable after repeated errors, restart recovery, control queue, health cycle |
| Dashboard | `mab/dashboard.py`, `mab/dashboard.html` | header stats, stat tape, wallet, candles and live order book, #1 bot streak, 3D hive-mind swarm, P&L, analytics, execution log, per-bot rule explanations |
| Secrets | `mab/secrets_store.py` | Windows DPAPI / keyring / owner-only file; hidden prompt; log redaction |
| Evaluation | `mab/backtest.py`, `mab/evaluate.py`, `mab/metrics.py` | walk-forward, embargo, costs, Holm, deflated Sharpe |

## Fleet Brain (self-learning, local)

Every bot reports its signal state each bar; before any paper entry is sent the brain decides on its own to approve,
resize (0.5x-1.5x), veto, or bench the bot. It combines a hierarchical Bayesian estimate of the result per trade
after costs (fleet -> strategy family -> strategy -> strategy on this instrument / in this market regime), a shared
context model trained on every bot's closed trades, and a stacking layer that learns how much to trust each part.
Priors come from the batch evaluation, priced like each bot's venue (retail fees vs a low-fee venue). Vetoed entries
are followed as shadow trades and learned from at half weight, so a benched strategy can earn its way back and the
value of the vetoes is measured. Insights are written in plain language when a pattern is statistically clear.
No AI service is called; nothing leaves the computer. `brain.mode` in the config: `active` (default), `advisory`
(learns and scores, never blocks), `off`. The brain cannot create an edge the markets do not give: its calibration,
high- vs low-score results and the average result of vetoed trades are on the dashboard so its value can be judged.

## Bots

`bots/registry.json` (generated by `bots/generate.py` from the strategy catalog): 250 bots, one strategy on one
instrument each, covering all 127 implemented strategies; `bots/coverage.json` maps strategies to bots. Stage tags
(`1`, `10`, `50`, `250`) select the staged roll-out.

## Tests

`python -m pytest tests -q` (85 tests: indicator references, look-ahead checks for every indicator, rule language,
restart, stale/duplicate/out-of-order data, network failure and circuit breaker, paper-broker partial fills and
rejections, balance changes and TWR, risk breaches, storage failure and corrupt state, calendars).

## Costs and data (all free)
Crypto market data: Coinbase, Kraken, OKX public APIs. Stocks: Yahoo Finance chart API (unofficial; bars only, no
quotes or trade prints, regular-hours 5-minute history limited to 60 days). Fees used in paper trading are the
venues' published base tiers (see `mab/costs.py` and the strategy source register).
