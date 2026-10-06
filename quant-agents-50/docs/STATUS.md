# Build status

Updated: 2026-10-05 (kit v0.5.0: the 25-agent core)

## Where things stand

- **The 25-agent core is built.** All 25 run in every cycle at `phase: 4` (the default in `config/default.yaml`).
- The other 25 roster agents are **parked** (`core: false` in `config/agents.yaml`): optional, built later only if they earn it.
- New signal agents A13 and A15 are in **shadow**: sealed and scored by A35, no vote until the owner promotes them.
- Mode: **paper**. Autonomy level: **1**. Live trading: **not approved**.
- Tests: 308, all gates green, 99% line coverage overall, 100% branch coverage on risk.
- An independent review found 8 defects in the new agents (1 high, 3 medium, 4 low). All are fixed and covered by regression tests.

## The 25-agent core

| Team | Core agents |
|---|---|
| Data and integrity | A01 market data, A02 data quality, A03 features, A05 ledger |
| Market context | A06 regime, A07 transitions, A08 volatility, A09 liquidity |
| Signals | A11 trend, A12 cross-sectional momentum, A16 reversion, A23 calendar; A13 breakout and A15 exhaustion (shadow) |
| Scoring and review | A35 scorekeeper, A39 red team, A40 no-trade |
| Research | A43 backtester, A44 statistics, A45 stress |
| Command, risk, execution | A46 orchestrator, A47 aggregator, A48 sizing, A49 risk governor, A50 paper broker |

## Phases

| Phase | Goal | Status |
|---|---|---|
| 0 | Setup on the owner's PC | Not started: run `/phase 0` |
| 1 | Data and backtester | Built; real data and a benchmark check to do |
| 2 | First signals and validation | Built; strategy library and trial log to grow |
| 3 | Risk, execution, paper | Built; chaos tests, watchdog and 30 paper days to do |
| 4 | Context, aggregation, scoring | Built (core complete); 60+ real paper days to score agents |
| 5-7 | Parked agents (optional) | Not planned |
| 8 | Micro-live (owner approval) | Locked |
| 9 | Controlled scaling (owner approval) | Locked |

## Human approvals

| Date | Decision | Owner |
|---|---|---|
| (none yet) | | |

## Open issues

- Results so far are on synthetic data and prove nothing about real markets.
- On the synthetic data the full chain rarely says GO: two teams must agree and the edge must beat 1.5x costs. That is by design.
- With only 4 voting agents, the 25% per-agent cap forces equal weights. A35's weights start to matter at 5+ voters.
- A09 works from daily bars. Its high-low spread proxy is shown for information only; replace it with real quotes when an L1 feed exists.

## Next step

Owner: install Python 3.11+, Git and Claude Code, open this folder in a terminal, run `claude`, then type `/phase 0`.
