# Verification report — Trading AI 1.5.0

Every line below is a check that was actually run, with its real result. A check that could not be run is listed as
**NOT PERFORMED**, with the reason. Nothing here is a statement about future returns.

Machine: a cloud Linux VM with 4 vCPUs (Intel Xeon, 2.8 GHz). The Windows program was built and run under Wine. It has
**not** been run on a physical Windows PC.

## Summary

| Area | Result |
|---|---|
| Unit and integration tests (`backend/tests`) | PASSED: 155 of 155. |
| Self-test of the program from source (offline, over HTTP and WebSocket) | PASSED: 31 of 31 steps. |
| Self-test of the built Windows exe under Wine | PASSED: 31 of 31 steps under Wine, in a fresh data folder, offline (`selftest.log` in the download). The agent probe ran the full decision pipeline on A004's market. The 155 tests also passed inside the build. |
| Crash recovery: real SIGKILL during training, then restart | PASSED: 14 of 14 checks (`scripts/kill_restart_check.py`). After the kill, the program restarted READY in paper mode with every start-up check passing, an intact database and audit chain, all 100 agents on the same markets, and 2 interrupted research runs marked failed (not left running). Reconciliation was clean. |
| Paper round trip on a live BTC price through the real order path | PASSED: buy and sell both FILLED. Slippage 1.3 bp each side against the live quote, fee 0.20 per order on a 50 USD order. Reconciliation clean, paper ledger invariant holds. |
| Soak on live data, run 1 (20 minutes) | FAILED, then fixed: 20 missed agent deadlines and a 2.7 s cycle every 5 minutes; "fresh data" flapped between 51 and 45. Causes and fixes are below. |
| Soak on live data, runs 2 and 3 after the fixes (15 minutes each) | Run 2 showed the freshness fix working (stable at 51), but a start-up burst still missed 21 deadlines and some cycles took up to 12 s, because jobs still waited on the network. After moving price refreshes to their own thread, **run 3 PASSED** (15.3 minutes): 0 missed deadlines, 0 agent errors, cycles 20–47 ms (92 cycles), fresh data steady at 51 (the other 49 agents' US markets were closed), memory 110–117 MB, CPU 3–6% of one core after start-up. Reconciliation, audit chain and paper round trip (1.15 bp slippage) all passed. |
| Agent training on real data (2 passes, 300 research runs each) | Completed. 0 of 100 agents passed the research gate, so none may trade (details below). |
| Walk-forward portfolio backtest by market regime | Completed: `PORTFOLIO_BACKTEST_REPORT.md`. Results are below. |
| Data integrations (Coinbase, Kraken, Yahoo Finance public data) | PASSED. Coinbase listed 842 pairs and Kraken 1,460. All 100 agents received real history (Coinbase for crypto, Yahoo for stocks, ETFs, FX and futures). |
| Broker integrations with real accounts (Alpaca, OANDA, Kraken, IBKR, Coinbase) | NOT PERFORMED: no account credentials exist in this environment, by design (credentials are never pasted into chat). The adapters stay UNVERIFIED, so live trading cannot be armed. Offline tests cover order handling, duplicate prevention, uncertain submissions, reduce-only exits and the live-mode refusal. |
| Hardware thermal behaviour | NOT PERFORMED: the build machine is a cloud VM with no temperature sensors (`/sys/class/thermal` is empty and there is no hwmon). Check it on your PC with a monitoring tool such as HWiNFO while the program trains (training is the heaviest load: at most 2 research jobs at once). Measured load here, with no training running: 3–6% of one CPU core, about 115 MB of memory. |
| Live (real-money) execution | NOT PERFORMED, by design. Real-money orders stay disabled until you arm them separately with a verified broker account. |

## What the tests cover

Tests that exist and pass (`backend/tests`):

- **Master agent (`test_master.py`).**
  - Exactly 100 agents in 8 roles, and every candidate template is runnable on its bar size.
  - One owner per instrument; assignment is stable.
  - A restart before the first price snapshot moves no agent. Small rank changes move no agent. A delisted pair is
    replaced.
  - Training is bounded to 2 jobs at once, and a job with no usable result is not resubmitted every cycle.
  - The candidate is chosen on validation data, never on the held-out test.
  - A rejected version keeps the agent in cash.
  - Shadow promotion only when the new version beats the active one; rollback restores the previous version only if it
    still validates, otherwise it suspends the agent. After a rollback, a new version must first make money in shadow.
  - Rollback on a paper loss above 2% of equity and on results below validation.
  - Daily loss limit, and two breaches roll the version back.
  - The emergency stop and Stop remove every permission.
  - A permitted agent trades by itself in paper; only the owning agent may open a position.
  - The owner cannot create bots by hand.
  - The shadow probe sends nothing.
  - A version trained on one market is never used on another.
  - A slow agent job is never doubled.
  - Crash and restart restore agents, versions, positions and lessons.
  - The 16-thread order-authority race, agent budgets, and market discovery.
- **Learning (`test_learning.py`).**
  - Every one of the 14 root causes has a scenario, and its safeguard changes the outcome only when its lesson exists.
  - A risk denial becomes a lesson shared by all agents. Exits are never mistakes.
  - The order authority reports denials.
  - Safeguards never raise a quantity (3,000 random cases).
  - Three repeats in 24 hours suspend the agent. Execution errors start a cooldown.
  - Closed trades that lose more than 1.5 times their planned risk become lessons.
  - Weekly mistake-rate metrics are computed.
  - Lessons persist and are replayed at every start, and a safeguard that stops working fails the start-up check.
  - The old database is copied before an upgrade.
- **System switch (`test_autopilot.py`):** paper only; Stop, Start and the kill switch are respected; lifetime counts
  survive a restart; old bots are removed only when flat.
- **Safety, day trading, backtest golden tests, catalog, packaging:** the existing suites, all passing.

## Problems found during this work, and what was done

| # | Problem found | Fix | Proof |
|---|---|---|---|
| 1 | Once any agent had a validated version, **every restart failed**: the master read the system switch before it was created at start-up. | The start-up order was fixed and the check made robust. | `test_a_crash_and_restart_restores_agents_versions_positions_and_lessons`; the kill-and-restart check. |
| 2 | **Agents were moved to other markets on every restart.** Before the first price snapshot every coin ranked at zero, so crypto agents were moved onto alphabetical pairs and back a minute later. One restart moved 36 agents. | Agents keep their pair while the ranking is unknown, and while it stays among the 3x most liquid of their group. New pairs are taken only from a known ranking. | 3 tests: restart before the snapshot, fresh start, rank changes. |
| 3 | A version stayed attached to the agent, not to the market it was trained on, so after a move it could have traded a market it never saw. | Versions are retired when the market changes, and permission is refused if a version's dataset is a different market. | `test_a_version_trained_on_one_market_is_never_used_on_another`. |
| 4 | **Research runs cut off by a crash stayed "RUNNING" forever.** | They are marked failed at start-up and retried. | Kill check: 2 interrupted runs marked failed. |
| 5 | The day-trading sweep **skipped a position past its deadline while an order was still working** (for example, a partly filled entry). It surfaced as an intermittent test failure. | The sweep cancels that order, then closes the position. | `test_sweep_cancels_a_working_order_and_still_closes_on_time`. |
| 6 | A finished training job without a usable result (for example, too few bars) was **resubmitted every 10 seconds**. | Such a job is not retried for 12 hours; the other candidates still produce a version. | `test_a_finished_job_without_a_usable_result_is_not_resubmitted_every_cycle`. |
| 7 | Training windows were too short: with 5,000 hourly bars, 256 of 300 runs could not reach 30 held-out test trades. | The master trains on the longest history the engine accepts (20,000 hourly bars). No gate was changed, and earlier trials stay charged. | `AGENT_TRAINING_REPORT.md`: 131 of 300 runs now reach 30 test trades. |
| 8 | Soak run 1: every 5 minutes all stock, FX and futures agents refreshed prices from the rate-limited provider in the same cycle. That caused a 2.7 s cycle and once 20 missed deadlines. A late job could be followed by a second job for the same agent. | First, refreshes were spread across the window (soak run 2 still missed 21 deadlines at start-up). Then the real fix: one data thread refreshes prices at the provider's pace, and agent jobs only read its cache. An agent with an unfinished job is skipped, never doubled. | `test_monitoring_jobs_never_wait_on_the_network_when_the_data_refresher_runs`, `test_a_slow_agent_job_is_never_doubled_and_refreshes_are_spread`; soak run 3: 0 missed deadlines, cycles 20–47 ms. |
| 9 | Soak run 1: "fresh data" flapped between 51 and 45 because the freshness window (12 minutes) was shorter than a 15-minute bar's normal age. | Freshness is judged against two of the agent's own bars, the same rule as the stale-data safeguard. | Soak runs 2 and 3: fresh data steady at 51 for the whole run. |
| 10 | Offline, the master queued training for markets with no stored data, wasting jobs. | Offline, only markets with stored or DEMO data are trained. | `test_training_submits_documented_research_per_candidate_with_bounded_jobs`. |
| 11 | The master's counts (promoted, rolled back, rejected) reset to zero on restart. | They are read from the database. | `test_lifetime_counts_come_from_the_database_and_survive_a_restart`. |
| 12 | Page 1 role cards had overflowing badges, and a stat label was cut off. | The layout was fixed and checked in Chromium at 1500 px and 390 px (no horizontal scroll). | Screenshots taken during the check. |

## Training result (what the agents learned)

Full tables: `AGENT_TRAINING_REPORT.md`.

**No agent passed the research gate, so none may trade, even in paper.**

| Measure | Result |
|---|---|
| Research runs on real data | 300 (3 candidates for each of 100 agents) |
| Runs with at least 30 held-out test trades | 131 |
| Runs with a positive held-out Sharpe | 59 |
| Highest Deflated Sharpe | 0.20 (0.95 required) |
| Runs that lose money at 2x costs | 264 |
| Verdicts | REJECT 297, RESEARCH FURTHER 3, PAPER TEST 0 |

## Portfolio result (walk-forward, every traded day out of sample)

Full tables: `PORTFOLIO_BACKTEST_REPORT.md`. The period is 2025-01-25 to 2026-10-13 (627 days), with all costs included.

| Variant | Total return | Max drawdown | Sharpe (annualised) |
|---|---|---|---|
| ALL: every agent trades every fold with its chosen candidate | −33.1% | 33.1% | −7.83 |
| GATED: skips folds whose candidate lost money in its own validation window | −3.7% | 3.7% | −3.72 |
| For comparison: SPY buy and hold | +32.4% | — | — |
| For comparison: BTC buy and hold | −22.0% | — | — |

- Results were negative in every market regime: bull, bear, sideways and volatile, for both the stock and the crypto
  benchmark.
- Before costs, the agents made 233,101 in total across their sleeves. Costs were 2,070,241 (8.9 times as much):
  - fees 1,081,851;
  - slippage 761,092;
  - spread 227,298.
- 19 of 100 agents had a positive out-of-sample result; the best was +4.7% (WMT, mean reversion). With 100 agents tested,
  a handful of positive results is expected by chance alone.

## Live-trading readiness

**Not ready, and not enabled.**

1. No strategy version has passed the research gate. The system correctly stays in cash.
2. No broker account is connected or verified.
3. Real money needs your separate, explicit arming step. Nothing in this release turns it on.
4. The exe has not been tested on a physical Windows PC, and thermal behaviour has not been measured.
