# Build status

Updated: 2026-10-06 (kit v0.5.0 + Phase 1: real data and the event-driven backtester)

## Where things stand

- **The 25-agent core is built.** All 25 run in every cycle at `phase: 4` (the default in `config/default.yaml`).
- The other 25 roster agents are **parked** (`core: false` in `config/agents.yaml`): optional, built later only if they earn it.
- New signal agents A13 and A15 are in **shadow**: sealed and scored by A35, no vote until the owner promotes them.
- Mode: **paper**. Autonomy level: **1**. Live trading: **not approved**.
- Tests: 369, all gates green, 99% line coverage overall, 100% branch coverage on risk.
- **Phase 1 passed** (2026-10-06): real data store, free data sources, split check, event-driven backtester, benchmark, leakage tests.
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
| 0 | Setup on the owner's PC | Checked in the build environment (all gates green); still to do on the owner's PC |
| 1 | Data and backtester | **Passed** 2026-10-06 (see Phase 1 results below) |
| 2 | First signals and validation | Built; strategy library and trial log to grow |
| 3 | Risk, execution, paper | Built; chaos tests, watchdog and 30 paper days to do |
| 4 | Context, aggregation, scoring | Built (core complete); 60+ real paper days to score agents |
| 5-7 | Parked agents (optional) | Not planned |
| 8 | Micro-live (owner approval) | Locked |
| 9 | Controlled scaling (owner approval) | Locked |

## Phase 1 results (2026-10-06, real data)

Benchmark: buy-and-hold total return worked out three ways from one stored snapshot (Yahoo,
downloaded 2026-10-06). Pass = every route within 10 bp (0.1%) a year.

| Symbol | Period | Dividends | Adjusted close | Raw close + dividends (gap) | A43 backtester (gap) | Result |
|---|---|---|---|---|---|---|
| SPY | 2000-01-03 to 2026-10-05 | 108 | +752.33% | +752.99% (+0.31 bp/yr) | +763.65% from day-2 open (0.00 bp/yr) | PASS |
| QQQ | 2000-01-03 to 2026-10-05 | 90 | +848.14% | +848.14% (+0.00 bp/yr) | +876.48% from day-2 open (0.00 bp/yr) | PASS |
| XIC.TO | 2001-02-22 to 2026-10-05 | 103 | +734.09% | +740.88% (+3.45 bp/yr) | +740.71% from day-2 open (0.00 bp/yr) | PASS |
| VFV.TO | 2012-11-08 to 2026-10-05 | 55 | +868.83% | +868.37% (-0.40 bp/yr) | +876.34% from day-2 open (0.00 bp/yr) | PASS |

- The backtester route starts at the open after the first day (A43 never fills at the signal's
  close), so it is compared with the adjusted return from that same open.
- XIC's worst single year (2003) differs by 55 bp: one dividend date or amount in Yahoo's data
  probably disagrees with its adjusted close. Over 25 years it averages 3.45 bp a year (passes).
- Engine cross-check on real data (SPY+QQQ, tsmom_126, 2001-2026): vectorized CAGR +8.71%,
  event-driven +8.66%. Both logged in `docs/research/trials.md` as trials. Not validated: no A44 run.
- All free data is labelled "survivorship-biased: upper bound only" and "not point-in-time".

## Human approvals

| Date | Decision | Owner |
|---|---|---|
| (none yet) | | |

## Open issues

- Most results so far are on synthetic data and prove nothing about real markets. Real-data runs so far are engine checks only.
- The default config universe is the synthetic SYN_A..SYN_F. To paper-trade real symbols, put them in `universe.symbols` (or `[]` for every symbol in the file). `cycle` now says so when nothing can trade.
- Export stocks and crypto to separate CSVs: crypto trades on weekends, so a mixed file has gaps that make A02 block the stocks.
- On the synthetic data the full chain rarely says GO: two teams must agree and the edge must beat 1.5x costs. That is by design.
- With only 4 voting agents, the 25% per-agent cap forces equal weights. A35's weights start to matter at 5+ voters.
- A09 works from daily bars. Its high-low spread proxy is shown for information only; replace it with real quotes when an L1 feed exists.

## Next step

- Owner: on your PC, install Python 3.11+, Git and Claude Code, then `python -m pip install -e ".[dev,data]"` and `python scripts/check.py`.
- Build: Phase 2 (trial log, strategy library on real data, A44 additions) and Phase 3 (chaos tests, watchdog, daily schedule).
