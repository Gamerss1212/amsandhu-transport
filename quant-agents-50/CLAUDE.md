# QuantAgents-50: instructions for Claude Code

A quant research and paper-trading platform: a complete 25-agent core (spec section 93) plus 25
parked roster agents, built from the spec in `docs/SPEC.md`. The owner is a beginner: explain
decisions in plain words, short lines, bullets.

Current phase, progress and human approvals (loaded every session):
@docs/STATUS.md

## Non-negotiable rules (spec section 2)

1. Paper trading only until the human approves Phase 8 in `docs/STATUS.md`. No live broker code before that.
2. Never read, write, print or commit secrets. Keys live in `.env`, which only the human edits. Use `os.environ`.
3. A49 (`src/quantagents/risk/`) is deterministic code. No LLM or ML inside. Its checks may only shrink or reject orders.
4. Never raise a risk limit, the autonomy level, the execution mode or `live_trading_approved`. Only the human changes those.
5. LLMs never do arithmetic, sizing, P&L or risk math. Code does.
6. Never fabricate data, results or performance. "No edge found" is a valid, reportable result.
7. Never keep tuning a strategy until it passes. Every variant tried counts as a trial (spec section 63).
8. No look-ahead: agents only receive a `MarketView` that ends at the as-of date.
9. Anyone can say stop; only the full chain can say go. Stop signals can only reduce risk.

## Commands

- Install: `python -m pip install -e ".[dev]"`
- All quality gates: `python scripts/check.py` (ruff, format, mypy strict, pytest, 100% risk coverage)
- Fast gates while editing: `python scripts/check.py --fast`; one file: `python -m pytest tests/test_agents.py -q`
- Demo cycle: `python -m quantagents demo`; many days: `python -m quantagents simulate --days 120`
- Roster: `python -m quantagents agents --core`; strategy stress: `python -m quantagents stress --strategy tsmom`
- Research: `python -m quantagents validate --strategy tsmom` (A43 backtest + A44 statistics + A39 red team)
- Research grid: `python -m quantagents research --universe NAME=CSV --noise 20 --jobs 4` (87 pre-registered variants, noise controls; never edit the grid after a run without a new pre-registration)
- Paper day: `python -m quantagents cycle --data data/prices.csv`; kill switch: `python -m quantagents killswitch status`
- Real data (Phase 1): `python -m quantagents data fetch --yahoo SPY`, `data list`, `data benchmark --symbol SPY`, `data export --out data/us.csv`
- Daily paper run (Phase 3): `python -m quantagents --config config/my_universe.yaml daily --yahoo SPY ...`; watchdog: `python -m quantagents watchdog --data data/prices.csv`

## How to work

- One phase at a time. `/phase N` loads `docs/phases/phase-N.md`. Do not start phase N+1 until phase N passes its acceptance tests.
- Plan before any change bigger than a small fix: list the files you will touch and the tests you will add, then wait for "go".
- Write tests first for risk logic, sizing, order validation and reconciliation.
- The 25-agent core is built. Parked agents (`core: false`) are optional: `/new-agent A17` builds one in shadow.
- Never promote a shadow agent yourself. Show the owner A35's scorecard; only the owner changes `state`.
- Before every commit run `/verify`. Never commit with a failing gate.
- Small commits with clear messages. Update `docs/STATUS.md` at the end of every session.
- Unsure about anything that touches money: stop and ask. Never guess silently.
- Subagents: `risk-reviewer` after touching risk, execution or sizing; `red-team` for any strategy or signal;
  `spec-checker` before closing a phase; `test-writer` for new modules.

## Project map

- `src/quantagents/schemas.py`: every message between agents (spec section 81). Change schemas carefully.
- `src/quantagents/config.py` + `config/default.yaml`: all limits. The YAML must match the code defaults (a test checks).
- `config/agents.yaml`: the roster (team, tier, phase, state, core, implementation).
- `src/quantagents/orchestrator.py`: A46, the 15-step cycle (spec section 12).
- `src/quantagents/agents/`: one module per agent, `aNN_role.py`.
- `src/quantagents/aggregation.py`: pooling and GO rules (spec section 13).
- `src/quantagents/agents/a06_regime.py`, `a07_transition.py`, `a09_liquidity.py`: market context (risk-reducing only).
- `src/quantagents/agents/a35_scorekeeper.py`: scoring, calibration, weights. `a45_stress.py`: stress tests.
- `src/quantagents/regime_models.py`: mixture, sticky HMM filter, change-point detection.
- `src/quantagents/simulate.py`: day-by-day paper simulation of the full cycle.
- `src/quantagents/risk/`: A49 governor and kill switch. Edits ask the human first.
- `src/quantagents/execution/paper.py`: A05 ledger, A50 paper broker, reconciliation.
- `src/quantagents/backtest/`, `src/quantagents/validation/`: A43, A44, A39 (research only, never trade).
- `tests/`: one test file per area. `tests/helpers.py` has builders for fake data and messages.

## Reading the spec

`docs/SPEC.md` is long. Never read it all at once. Find a section, then read only that part:
`grep -n "^### 48\." docs/SPEC.md`. Phase prompts list the sections they need.

## Code style

- Python 3.11+, fully typed (mypy strict), pydantic models for messages, numpy for math. No pandas in the core.
- Pure functions where possible; agents are deterministic given their inputs.
- Docstrings in plain English: what it does and why. Cite the spec section.
- A hook formats Python after every edit and shows remaining lint errors. Fix them right away.

## Talking to the owner

- Start by saying what you will do. End with what changed, how to check it, and the next step.
- Bold headers, short bullets, no unexplained jargon. Define a term the first time you use it.
- Say plainly when something failed or when no edge was found.
