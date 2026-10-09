# Trading AI

A local trading research, paper-trading and (owner-armed) live-trading system for crypto, stocks, ETFs, forex,
indices and futures. It runs entirely on your computer behind `http://127.0.0.1:<port>`. The Windows release is one
folder: double-click `START_TRADING_AI.exe`, the local server starts, and the browser opens the dashboard.

It starts in **PAPER** mode and runs by itself: the Autopilot researches strategies, starts paper bots for the ones
that pass, watches them and retires the ones that fall short. It stays in paper. Nothing shown as real is invented: every number comes from a calculation
on real market data, an authenticated broker connection, or clearly labelled simulated (DEMO) data.

Beginners: read [`docs/START_HERE.txt`](docs/START_HERE.txt). What is done and what is not:
[`docs/REQUIREMENTS_MATRIX.md`](docs/REQUIREMENTS_MATRIX.md).

## Architecture

```
START_TRADING_AI.exe (launcher.py)
 ├─ single instance (OS file lock + /api/system/ping), free port from 8000 on 127.0.0.1, opens the browser
 └─ App (app.py): start-up checks → recovery → trading loop thread → research worker pool
     ├─ storage    SQLite (WAL, migrations, hash-chained audit log)  ·  DuckDB + Parquet market store  ·  DPAPI vault
     ├─ data       Coinbase / Kraken / Yahoo / DEMO providers, completed bars only, quality checks, provenance hashes
     ├─ market     41 instruments, NYSE/CME/FX/crypto calendars, futures specs and roll windows
     ├─ features   226 causal features (123 functions), regime detection (rules + HMM + CUSUM)
     ├─ strategies 1,418 templates (1,403 runnable): 101 generators × filters × exits, near-duplicates pruned
     ├─ agents     102 agents in 10 groups; ensemble averages by information cluster; vetoes; no fake probabilities
     ├─ autopilot  on by default, paper only: screens → full tests → starts bots → reviews → retires (engine/autopilot.py)
     ├─ engine     orchestrator: data → features → regime → strategy → agents (incl. higher timeframe) → sizing → risk → OMS
     ├─ risk       deterministic checks (approve / shrink / deny), loss and drawdown locks, kill switch, typed phrases
     ├─ execution  OMS with deterministic client ids, query-before-resend, UNKNOWN state, shadow mode; algos (TWAP/VWAP/POV)
     ├─ brokers    paper broker (Decimal ledger) · Alpaca / OANDA / Kraken / IBKR adapters (UNVERIFIED) · Coinbase (REQUIRES CONNECTION)
     ├─ research   chronological train/validation/test, walk-forward, Monte Carlo, cost stress, PSR/DSR/PBO, ledger
     ├─ portfolio  Ledoit-Wolf, inverse vol, risk parity, min variance, HRP, mean-variance
     └─ api        FastAPI REST + one WebSocket; Host / token / Origin guard; serves the compiled React dashboard
frontend/          React + TypeScript + Vite: Command Center · Broker & Money · Live Intelligence
packaging/         PyInstaller spec, Windows build script (runs under Wine on Linux), icon, version info
```

## Run from source

```bash
python -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
cd frontend && npm ci && npm run build && cd ..
cd backend && ../.venv/bin/python -m tradingai.launcher            # add --offline to use stored + DEMO data only
../.venv/bin/python -m pytest -q tests                              # 64 tests
../.venv/bin/python -m tradingai.launcher --selftest --offline      # end-to-end test over HTTP and WebSocket
```

Frontend development with hot reload: start the backend on port 8000, then `cd frontend && npm run dev`.

## Build the Windows folder

`packaging/build_windows.sh` runs the tests, builds the dashboard, checks the strategy-library cache, runs PyInstaller
with a Windows Python under Wine, copies the documents, runs the built exe's `--selftest` in a fresh folder and zips
`release/TradingAI/`. On Windows run the PyInstaller command from the script header natively.

## Where things are written

Beside the exe (or `TRADING_AI_HOME`): `data/app.sqlite3` (orders, fills, positions, ledger, decisions, audit,
experiments), `data/market/` (Parquet), `data/secrets/` (DPAPI-encrypted credentials), `data/backups/`,
`logs/trading-ai.log` (JSON lines, secrets redacted).

## Safety rules built into the code

* Paper by default. Live needs a verified LIVE connection, all readiness checks, caps and the typed acknowledgement
  `I UNDERSTAND THIS TRADES REAL MONEY`; it never resumes by itself after a restart.
* The risk service is plain deterministic code. Agents cannot loosen limits; raising one needs `RAISE MY RISK LIMITS`.
* Credentials go into the vault, are masked everywhere, and are never logged. Withdrawal permission is never requested.
* External text (news, provider messages) is data, never an instruction.
* A backtest can recommend PAPER TEST at most. Every backtest is recorded and counted as a trial.
