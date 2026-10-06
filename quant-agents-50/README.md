# QuantAgents-50

A multi-agent trading research and **paper-trading** platform, built step by step with Claude Code.

## What it is

- **A complete 25-agent core:** all 25 agents are built, tested and wired into one 15-step decision cycle.
- **25 more agents parked:** the full 50-agent roster stays in the spec, as optional extras to build only when they earn it.
- **Safety first:** a deterministic risk governor (A49) checks every order, and real money stays locked behind written owner approval.

## What it is not

- Not a money printer. No system guarantees profit. "No edge found" is a normal, honest result.
- Not live trading. The kit ships with a paper broker only.
- Not financial, legal or tax advice.

## Quick start (about 5 minutes)

You need Python 3.11 or newer.

```bash
python -m venv .venv
# Windows:  .venv\Scripts\activate      macOS/Linux:  source .venv/bin/activate
python -m pip install -e ".[dev]"
python -m quantagents demo
python scripts/check.py
```

- `demo` runs one full decision cycle of all 25 agents on **synthetic** data (fake symbols SYN_A to SYN_F).
- `check.py` runs every quality gate: lint, formatting, strict types, 369 tests, and 100% coverage of the risk code.
- `python -m quantagents simulate --days 120` runs the full cycle day after day on a fresh paper account.

### What to expect

- On the demo day the honest answer is **no trade**. Each symbol shows the rule it failed.
- Over 120 synthetic days the system said GO on 8 days, made 1 round trip and finished at -0.25%.
- That is the design: two teams must agree and the edge must beat 1.5x costs. Doing nothing beats guessing.

## The 25 agents

| Group | Agents |
|---|---|
| Data | A01 market data, A02 data quality, A03 features, A05 ledger |
| Market context | A06 regime, A07 transition alarm, A08 volatility, A09 liquidity |
| Signals (vote) | A11 trend, A12 momentum ranking, A16 short-term reversion, A23 calendar |
| Signals (shadow) | A13 breakouts, A15 trend exhaustion: scored, no vote until you promote them |
| Checks | A35 scorekeeper, A39 red team, A40 no-trade check |
| Research | A43 backtester, A44 statistics, A45 stress tester |
| Command | A46 orchestrator, A47 aggregator, A48 sizing, A49 risk governor, A50 paper broker |

New context and risk agents can only **reduce** risk. If one crashes, the system fails safe (smaller or no new trades).

## Build the rest with Claude Code

1. **Install Claude Code** (needs a paid Claude plan):
   - Windows PowerShell: `irm https://claude.ai/install.ps1 | iex`
   - macOS or Linux: `curl -fsSL https://claude.ai/install.sh | bash`
   - On Windows, also install Git for Windows so Claude Code can use Bash.
2. **Open this folder** in a terminal and run `claude`.
3. **Type `/phase 0`.** Claude reads `CLAUDE.md`, checks your setup, and walks you through it.
4. **One phase at a time:** `/phase 1`, `/phase 2`, and so on. Claude plans, waits for your "go", writes tests first, then code.
5. **After each session:** read the summary, look at the changes, and commit.

### Slash commands in this project

| Command | What it does |
|---|---|
| `/phase N` | Works through `docs/phases/phase-N.md` |
| `/new-agent A17` | Builds one parked roster agent with tests, in shadow mode |
| `/validate-strategy tsmom` | Backtest + statistics + red team, then an honest research note |
| `/verify` | Runs every quality gate (Claude also runs it before each commit) |

### Helper agents Claude uses

- `risk-reviewer`: checks any change to risk, sizing or execution code
- `red-team`: attacks strategies for look-ahead, overfitting and unrealistic costs
- `spec-checker`: checks a phase against its acceptance criteria
- `test-writer`: writes tests before code

## Everyday commands

| Command | Purpose |
|---|---|
| `python -m quantagents demo` | One decision cycle on synthetic data |
| `python -m quantagents data fetch --yahoo SPY QQQ --start 2000-01-01` | Download free daily bars (stocks/ETFs, with dividends and splits) into the append-only store |
| `python -m quantagents data fetch --ccxt kraken:BTC/USD` | Free daily crypto candles (needs `pip install -e ".[data]"`) |
| `python -m quantagents data benchmark --symbol SPY` | Phase 1 check: buy-and-hold total return three ways, within 0.1% a year |
| `python -m quantagents data export --out data/us.csv --symbols SPY QQQ` | Adjusted prices to a CSV, plus a `.meta.json` with each source's caveats |
| `python -m quantagents backtest --data data/us.csv --engine event` | Event-driven backtest: orders, partial fills, impact, 1%-of-ADV cap |
| `python -m quantagents simulate --days 120` | The full cycle day by day, with A35 scorecards and why it did not trade |
| `python -m quantagents agents --core` | The 25-agent core and each agent's state |
| `python -m quantagents stress --strategy tsmom` | A45 Monte Carlo and 2x-cost stress of a strategy |
| `python -m quantagents validate --strategy tsmom` | Backtest every variant, then A44 statistics and the A39 red team |
| `python -m quantagents make-data --out data/prices.csv` | Write synthetic prices to try the paper loop |
| `python -m quantagents cycle --data data/prices.csv` | One paper-trading day (account and A35 memory saved in `state/`) |
| `python -m quantagents killswitch status` | Check, engage or reset the kill switch |
| `python -m quantagents audit` | Verify the tamper-evident audit log |
| `python -m quantagents acb` | Adjusted cost base report (Canada; not tax advice) |

## Safety rails

- **A49 has the last word.** Plain code, no AI inside. It can only shrink or reject orders, and always allows exits.
- **Kill switch.** One command stops new trades. Only a typed phrase resets it.
- **Hooks.** Claude Code is blocked from writing secrets, editing `.env`, or switching on live trading.
- **Approvals.** Edits to risk code, limits and settings always ask you first.
- **No look-ahead.** Agents only see data up to the decision date. A test scrambles the future and checks that all 25 agents give exactly the same answer.
- **Stress before every entry.** A45 shrinks new trades whose bad-day loss would break the daily limit, then re-checks the book.
- **Honest scoring.** A35 only scores a prediction after its horizon has passed and counts overlapping forecasts once. It can only make an agent less confident, never more.
- **Audit trail.** Every cycle is logged in a hash chain, so edits are detectable.

## Project map

| Path | What is there |
|---|---|
| `CLAUDE.md` | Instructions Claude Code reads every session |
| `docs/SPEC.md` | The full spec (v4.1): the 25-agent core (section 93), the 50-agent roster, 406 strategies, 185 indicators |
| `docs/STATUS.md` | Current phase, progress, your approvals |
| `docs/phases/` | One build prompt per phase (0-9) |
| `config/default.yaml` | Every limit and setting |
| `config/agents.yaml` | The roster: 25 core agents and 25 parked |
| `src/quantagents/` | The code (one module per agent in `agents/`) |
| `tests/` | 369 tests |
| `.claude/` | Settings, hooks, skills, subagents and rules for Claude Code |

## Canada notes

- IBKR Canada blocks API orders on Canadian-listed products; US-listed products work.
- Questrade's API trading is for partner developers; retail gets data only.
- Crypto: Kraken and Coinbase are CSA restricted dealers in Canada; NDAX is an investment dealer.
- Re-check these before Phase 8. Rules change.
