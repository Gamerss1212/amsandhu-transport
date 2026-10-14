# Trading AI

A local trading research, paper-trading and (owner-armed) live-trading system for US stocks, crypto and meme coins
(forex, futures, options and bonds were removed in 1.7.0; ETFs and indices remain only as price references). It runs entirely on your computer behind `http://127.0.0.1:<port>`. The Windows release is one
folder: double-click `START_TRADING_AI.exe`, the local server starts, and the browser opens the dashboard.

It starts in **PAPER** mode and runs by itself. One **master agent** runs exactly **100 trading agents** (A001-A100).
Each agent owns one distinct market and has a role: a strategy family, a bar size, and three candidate templates chosen
from the evidence in [`docs/STRATEGY_RESEARCH.md`](docs/STRATEGY_RESEARCH.md).

The master trains each agent on its own market data, chooses a version on validation data, and lets the agent trade
paper automatically only if that version passes every research gate. It promotes better versions through a shadow test,
rolls back versions that fall short, and enforces portfolio, position and daily loss limits plus the emergency stop.
Every mistake is recorded with a root cause, and the lesson becomes a safeguard for all agents, with a regression
replay.

Nothing shown as real is invented: every number comes from a calculation on real market data, an authenticated broker
connection, or clearly labelled simulated (DEMO) data.

Download for Windows 11 or 10 (64-bit): [`downloads/TradingAI-v1.8.0-windows.zip`](../downloads/TradingAI-v1.8.0-windows.zip)
(unzip, double-click `START_TRADING_AI.exe`; `docs/START_HERE.txt` explains the SmartScreen and Smart App Control
messages). To check your computer's temperature under full load, double-click `CHECK_COMPUTER_TEMPERATURE.bat` in the
same folder. `START_JARVIS.bat` opens the optional JARVIS voice assistant ([`docs/JARVIS.md`](docs/JARVIS.md)). The previous 1.7.0, 1.6.0 and 1.5.1 downloads are kept beside it. Can $100 become $300,000? [No, and why.](docs/CAN_100_DOLLARS_BECOME_300K.md)

Beginners: read [`docs/START_HERE.txt`](docs/START_HERE.txt). What is done and what is not:
[`docs/REQUIREMENTS_MATRIX.md`](docs/REQUIREMENTS_MATRIX.md). The owner's specification is in
[`docs/specs/`](docs/specs/AI_Trading_System_Master_Prompt.md) (revision 13, with `Backtested_Working_Strategies.md`); its runnable
strategy templates were tested on real data in
[`docs/CATALOG_BACKTEST_REPORT.md`](docs/CATALOG_BACKTEST_REPORT.md).

Evidence for 1.5.0:

- [`docs/AGENT_TRAINING_REPORT.md`](docs/AGENT_TRAINING_REPORT.md): every agent's training.
- [`docs/PORTFOLIO_BACKTEST_REPORT.md`](docs/PORTFOLIO_BACKTEST_REPORT.md): walk-forward, combined portfolio, by market
  regime.
- [`docs/VERIFICATION_REPORT.md`](docs/VERIFICATION_REPORT.md): what was tested, what passed, failed or could not be run.
- [`docs/BACKUP_AND_RESTORE.md`](docs/BACKUP_AND_RESTORE.md): how to get the 1.4.1 version back.

## Architecture

```
START_TRADING_AI.exe (launcher.py)
 ├─ single instance (OS file lock + /api/system/ping), free port from 8000 on 127.0.0.1, opens the browser
 └─ App (app.py): start-up checks → recovery → trading loop thread → research worker pool
     ├─ storage    SQLite (WAL, migrations, hash-chained audit log)  ·  DuckDB + Parquet market store  ·  DPAPI vault
     ├─ data       Coinbase / Kraken / Yahoo / DEMO providers, completed bars only, quality checks, provenance hashes
     ├─ market     US stocks and crypto (meme coins tagged), ETF/index price references; market policy (market/policy.py);
     │             discovery: every Coinbase product and Kraken pair (daily) + one shared price snapshot per minute
     ├─ features   226 causal features (123 functions), regime detection (rules + HMM + CUSUM)
     ├─ strategies 1,502 templates (1,487 runnable): 106 generators × filters × exits, near-duplicates pruned;
     │             the owner's 124-template catalog (ST001-ST124) and 212-entry research index mapped onto them, with
     │             98 sources, reason codes and the owner's own batch results; entries only once a strategy qualifies
     ├─ agents     102 agents in 10 groups; ensemble averages by information cluster; vetoes; no fake probabilities
     ├─ master     the master agent + 100 trading agents A001-A100 in 8 roles: one owner per instrument, training per
     │             candidate, versions (shadow promotion, rollback), permissions, budgets, daily loss limits, bounded
     │             worker pool, fault isolation (engine/master.py); C01-C50 support services
     ├─ learning   mistakes → root causes → lessons → shared safeguards (block or shrink entries only) → regression
     │             replay at start-up, per lesson and hourly; repeats counted (engine/learning.py)
     ├─ daytrade   intraday rules per calendar: entry window, cutoff, flatten deadline, crypto 24 h hold (engine/daytrade.py)
     ├─ autopilot  the system switch (Start System / Stop) that drives the master, paper only (engine/autopilot.py)
     ├─ assistant  deterministic intents over verified state; "that bot" references; proactive voice events with
     │             quiet hours and lifecycle states; refuses money commands
     ├─ engine     orchestrator: data → features → regime → strategy → agents (incl. higher timeframe) → sizing → risk → OMS
     ├─ risk       deterministic checks (approve / shrink / deny), loss and drawdown locks, kill switch, typed phrases
     ├─ execution  one order authority per account (capital reserved atomically), deterministic client ids,
     │             query-before-resend, UNKNOWN state, shadow mode; algos (TWAP/VWAP/POV)
     ├─ brokers    paper broker (Decimal ledger) · Alpaca / OANDA / Kraken / IBKR adapters (UNVERIFIED) · Coinbase (REQUIRES CONNECTION)
     ├─ research   chronological train/validation/test, walk-forward, Monte Carlo, cost stress, PSR/DSR/PBO, ledger;
     │             portfolio templates (rebalanced, next-day execution, equal-weight benchmark) and portfolio bots
     ├─ portfolio  Ledoit-Wolf, inverse vol, risk parity, min variance, HRP, mean-variance
     └─ api        FastAPI REST + one WebSocket; Host / token / Origin guard; serves the compiled React dashboard
jarvis/            JARVIS voice assistant (adewaskar/jarvis, MIT) with a read-only link to this program
frontend/          React + TypeScript + Vite: two pages, the JARVIS trading panel and Brokers (agents and control room open as overlays)
packaging/         PyInstaller spec, Windows build script (runs under Wine on Linux), icon, version info
```

## Run from source

```bash
python -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
cd frontend && npm ci && npm run build && cd ..
cd backend && ../.venv/bin/python -m tradingai.launcher            # add --offline to use stored + DEMO data only
../.venv/bin/python -m pytest -q tests                              # 205 tests
../.venv/bin/python -m tradingai.launcher --thermal-check --minutes 5   # temperature and throttling under full load
../.venv/bin/python -m tradingai.launcher --selftest --offline      # end-to-end test over HTTP and WebSocket
```

Frontend development with hot reload: start the backend on port 8000, then `cd frontend && npm run dev`.

Train all 100 agents and run the walk-forward portfolio backtest (downloads real data; tens of minutes each):

```bash
.venv/bin/python scripts/train_agents.py /tmp/agents-home        # writes docs/AGENT_TRAINING_REPORT.md
.venv/bin/python scripts/portfolio_backtest.py /tmp/agents-home  # writes docs/PORTFOLIO_BACKTEST_REPORT.md
.venv/bin/python scripts/kill_restart_check.py --offline         # kills the program mid-training and checks recovery
```

Backtest the whole catalog and regenerate its report (about 6 minutes, downloads real data):

```bash
.venv/bin/python scripts/catalog_batch.py /tmp/catalog-home
.venv/bin/python scripts/catalog_report.py /tmp/catalog-home     # writes docs/CATALOG_BACKTEST_REPORT.md
.venv/bin/python scripts/import_master_prompt.py              # re-imports the registry from docs/specs/
```

## Build the Windows folder

`packaging/build_windows.sh` runs the tests, builds the dashboard, checks the strategy-library cache, runs PyInstaller
with a Windows Python under Wine, copies the documents, runs the built exe's `--selftest` in a fresh folder and zips
`release/TradingAI/`. On Windows run the PyInstaller command from the script header natively.

`.github/workflows/windows.yml` does the same on a real Windows machine (GitHub's `windows-2025` runner): the tests,
a native PyInstaller build, the exe's self-test, a thermal check against Windows' own performance counters, and a list
of the counters that machine offers. It runs on every push that changes `trading-ai/`, or by hand from the Actions tab.

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
* No order may open exposure unless it comes from the instrument's owning agent, that agent has the master's
  permission, and its version qualified (PAPER TEST on the same market and timeframe, under the day-trading rules).
  Otherwise the system waits in cash. Exits are always allowed.
* There is no manual backtest route and no hand-made bot: the agents test by themselves.
* Learned safeguards can only block or shrink entries; they never loosen a limit. No agent can change a limit, re-arm
  the emergency stop, turn on live trading or change code.
* Only US stocks and crypto (including meme coins) can be entered: the risk service denies every other market.
* Intraday: stocks are flat 10 minutes before the close, crypto and meme coins are held 24 hours at most. The same rules run in research and in paper trading.
* Add Funds only opens the broker's own website. The program never handles card or bank details.
