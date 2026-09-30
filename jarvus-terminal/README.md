# Jarvus

A trading research and paper-trading terminal: **311 bots** running **150 strategies** on crypto and
US/Canadian stocks, a **brain** that checks every trade they want to make, a research engine that
keeps testing them, and live visibility into everything they do. **One button starts it all.**

**Money:** the bots trade **simulated (paper) money** at live market prices. **Real money is off**
and stays off until you connect a live account, authorise live trading separately with your own caps,
and type a confirmation for each live bot. See [docs/LIVE_REQUIREMENTS.md](docs/LIVE_REQUIREMENTS.md)
for what live use still needs.

## Start

| You have | Do this |
|---|---|
| **Windows, no Python** | Double-click `JarvusTerminal.exe`. It opens the app in your browser; keep its window open (closing it stops Jarvus). |
| Windows with Python | Double-click `Jarvus Terminal.bat` |
| Mac | Double-click `Jarvus Terminal.command` (first time: right-click, **Open**) |
| Linux / any | `python3 run.py` (Python 3.9+; no pip needed) |

1. The first time, create your **owner account** on the page that opens (stored as a salted scrypt hash).
2. On **Command Center**, press **▶ START AUTOPILOT**. That's it.

The exe is not code-signed: if Windows SmartScreen says "Windows protected your PC", click
**More info → Run anyway**.

## What the one button does

**START AUTOPILOT** starts the bot engine if it is stopped and then, by itself, with no further input:

* all 311 bots load their markets (crypto from Coinbase, Kraken and OKX public data; stocks from
  Yahoo) and evaluate their strategy on every closed bar;
* entries go to the **brain** (cost gate, volatility gate, learned edge, bench and size) which
  approves, resizes or refuses each one; approved trades fill on the **simulated research account**;
* stops, targets, trailing stops and time exits are managed automatically;
* research runs on a schedule: a walk-forward evaluation of the next strategy/market pair every
  20 minutes (each pair at most weekly), a daily volatility-gate drift check and a daily brain
  snapshot compared with the approved brain. Results are recorded; **nothing is promoted to live by
  itself**;
* it keeps running, and it resumes whenever Jarvus opens, until you press **■ STOP AUTOPILOT**
  (the bots then stop opening trades; open positions are still managed to their exits).

It never overrides an **EMERGENCY STOP** and never touches real money. The demo workspace has its
own autopilot (24 bots on synthetic markets).

## The three pages

| Page | What it is for |
|---|---|
| **Command Center** | The AUTOPILOT button and its live status; account equity, buying power, allocated capital, realised/unrealised P&L, exposure and daily drawdown; the candlestick chart (timeframes, volume, EMA/VWAP/Bollinger, markers for real fills coloured by mode); building and starting your own bot (strategy, market, mode, account, allocation, risk limits, readiness checks); bot cards with **PAUSE NEW ENTRIES**, **STOP** (keep protective orders or close) and details; equity and drawdown charts; recent trades; alerts. |
| **Connections** | Every account: the simulated paper account, Alpaca paper/live, Kraken Pro, NDAX. Identity, environment, status, permissions, buying power, last sync, supported assets; connect / test / sync / reconnect / disconnect; **Add funds** opens the provider's own funding page (Jarvus never moves money or simulates a deposit); the separate **live-trading authorisation**; the AI research assistant's key and budget; news feeds. |
| **Live Intelligence** | Decision feed (live) with the full lifecycle of each decision: market update → signal (every rule condition) → brain → risk checks → order → broker acknowledgement → fills (fees, slippage) → position → exit; scanner with watchlists; bot status; orders, fills, positions and exposure; side-by-side comparison (backtest vs research vs paper vs demo vs live, never mixed); searchable history with CSV/JSON export; research jobs and model registry; service health (queue, latencies, data age, CPU, memory, this computer's hardware). |

**Modes are labelled everywhere:** `DEMO` (synthetic market, simulated money), `PAPER` (simulated money
at live prices), `PAPER · RESEARCH` (the autopilot fleet's own simulated account), `LIVE` (real money),
`BACKTEST` (measured on history, not traded). Simulated figures are never shown as real ones.

**EMERGENCY STOP** (top bar) blocks every new entry at once and tries to cancel working entry orders,
reporting each result. Closing positions is a separate, confirmed step ("CLOSE ALL").

## What was measured (and what it means)

In plain words: **no strategy here has been shown to make money after retail costs**. At each bot's own
exchange's fees the whole system averages slightly below zero per 10-day window; at a low-fee exchange
about break-even. 143 strategies on 917 strategy-market pairs: none is significant after correcting for
the number of ideas tried. The volatility gate is the one part with real predictive skill: when it flags
LOUD on crypto it is right 76% of the time (base rate 31%), and it predicts the size of a move, not its
direction. Details are on Live Intelligence → Research & models, and in `../market_analysis_bots/results`.

The autopilot's scheduled evaluations keep measuring: each walk-forward test splits the data
chronologically (60/20/20 with an embargo), charges fees, spread and slippage (and a 2x-cost stress
test), limits fills to a share of each bar's volume, and compares against random entries with the same
exits. This is educational research and paper-trading software, not financial advice. Nothing here is
a promise.

## Setup details

* **Configuration:** environment variables, all optional; see [`.env.example`](.env.example) (port,
  data folder, research workers and per-job time/memory limits, how many bot engines may run).
* **Data:** `data/` beside the program: `app.db` (accounts, sessions, workspaces) and one folder per
  workspace with its database (`mab.db`), backups and logs. Database changes are versioned migrations
  applied automatically at start (a backup is taken first).
* **Credentials:** an encrypted vault in `%APPDATA%\mab` (Windows; key protected by DPAPI for your
  Windows user) or `~/.config/mab` (key in the system keyring, or an owner-only file). Credentials are
  never shown again, never sent to the page, never logged, never in exports. Paper and live
  credentials are separate connections.
* **Network:** the app listens on `127.0.0.1` only. Every change needs the session cookie, a CSRF token
  and the app's header; foreign Host and Origin headers are refused.
* **AI research assistant (optional):** add an Anthropic API key under Connections. It uses the
  `claude-opus-5-5` model through the official `anthropic` SDK (bundled in the exe; `pip install
  anthropic` when running from source), only when you press a button, within daily request and token
  budgets. Server-side model fallback on refusals is enabled (`fallbacks: "default"`). It can summarise
  the log, explain a decision, draft strategy ideas (compiled, validated and registered as untested
  research versions) and summarise headlines. It cannot place, change or cancel orders; log text and
  headlines are passed to it as untrusted data.
* **Hardware:** research runs in separate worker processes on this computer's CPU cores with time and
  memory limits. No GPU and no remote compute are used; the Health tab shows what this computer has.

## Checks and tests

```
python3 run.py selftest                      # the install, offline (also: JarvusTerminal.exe selftest)
python3 -m pytest jarvus-terminal/tests      # app server: sign-in, CSRF, isolation, secrets, autopilot, stream
python3 -m pytest market_analysis_bots/tests # engine: risk limits, duplicate orders, restarts, partial fills,
                                             # stale data, rejections, emergency controls, providers, research
```

Run the pytest commands from the repository root (pytest is needed for them; the app itself needs no
packages).

## For developers

* [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md): processes, database, execution, risk, research, streams.
* `server.py`: the page, JSON API and live event stream; `engine/auth.py` (accounts, sessions,
  workspaces); `engine/supervisor.py` (one bot-engine process per workspace, autostart, research
  pool); `engine/library.py` (strategy library and measured results).
* `web/`: `index.html`, `app.css`, `js/` (ES modules, no build step), `vendor/` (TradingView
  Lightweight Charts, Apache-2.0, with its licence).
* Engine, brain, execution, providers and research: `../market_analysis_bots/mab`; strategy library:
  `../strategies`.
