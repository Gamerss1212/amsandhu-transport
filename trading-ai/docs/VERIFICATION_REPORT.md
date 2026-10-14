# Verification report — Trading AI 1.9.1

Every line below is a check that was actually run, with its real result. A check that could not be run is listed as
**NOT PERFORMED**, with the reason. Nothing here is a statement about future returns.

Machines: a cloud Linux VM with 4 vCPUs (Intel Xeon, 2.8 GHz), where the Windows program was built and run under Wine;
and a **real Windows 11 machine** (GitHub Actions `windows-2025` runner: Windows 11, build 26100, AMD EPYC 7763, 4
logical CPUs). That runner is a virtual machine. The program has **not** been run on a physical Windows PC: the
temperature of your own computer can only be measured by running the thermal check on it.

## Summary

| Area | Result |
|---|---|
| Unit and integration tests (`backend/tests`) | PASSED: 205 of 205 on Linux (1.7.0). On real Windows 11 the suite passed for 1.5.1 (167 tests, next rows); the same workflow runs on every push. |
| Real Windows 11: tests, native build, exe self-test, thermal check (measured on 1.5.1) | PASSED on the second run. Workflow `.github/workflows/windows.yml` (run 38478862548): all tests, a native PyInstaller build, the built exe's 32-step self-test (all passed, including "computer temperature sensors read": "Windows 11: sensors via windows-pdh"), then the exe's thermal check (below). The first run FAILED, which found two Windows-only problems (rows 13 and 15 below). |
| Thermal check on that Windows 11 VM (1 minute of full load) | RESULT: PASS (no temperature sensor). Windows reported no temperature: the `Thermal Zone Information` counter set exists but has no instances on a VM, so the report says "not reported" and shows no temperature figure. What it did measure: CPU busy 99% on all 4 logical CPUs, CPU speed 133% of nominal with no drop, no passive limit or throttle reasons reported, work rate 287 → 262 per second (−12%, below the 30% warning level). The check ran 3 minutes in all (1 idle, 1 load, 1 cool-down). This proves the load test, the Windows counters and the report work on real Windows 11. It says nothing about the heat of any physical PC. |
| Self-test of the program from source (offline, over HTTP and WebSocket) | PASSED: 34 of 34 steps (1.9.0). |
| Self-test of the built Windows exe under Wine | PASSED: 34 of 34 steps under Wine (1.9.0), in a fresh data folder, offline (`selftest.log` in the download). The agent probe ran the full decision pipeline on A004's market. The tests also passed inside the build (209). Under Wine the temperature counters do not exist, so that run shows "no temperature reported". |
| Crash recovery: real SIGKILL during training, then restart | PASSED: 14 of 14 checks (`scripts/kill_restart_check.py`). After the kill, the program restarted READY in paper mode with every start-up check passing, an intact database and audit chain, all 100 agents on the same markets, and 2 interrupted research runs marked failed (not left running). Reconciliation was clean. |
| Paper round trip on a live BTC price through the real order path | PASSED: buy and sell both FILLED. Slippage 1.3 bp each side against the live quote, fee 0.20 per order on a 50 USD order. Reconciliation clean, paper ledger invariant holds. |
| Soak on live data, run 1 (20 minutes) | FAILED, then fixed: 20 missed agent deadlines and a 2.7 s cycle every 5 minutes; "fresh data" flapped between 51 and 45. Causes and fixes are below. |
| Soak on live data, runs 2 and 3 after the fixes (15 minutes each) | Run 2 showed the freshness fix working (stable at 51), but a start-up burst still missed 21 deadlines and some cycles took up to 12 s, because jobs still waited on the network. After moving price refreshes to their own thread, **run 3 PASSED** (15.3 minutes): 0 missed deadlines, 0 agent errors, cycles 20–47 ms (92 cycles), fresh data steady at 51 (the other 49 agents' US markets were closed), memory 110–117 MB, CPU 3–6% of one core after start-up. Reconciliation, audit chain and paper round trip (1.15 bp slippage) all passed. |
| Agent training on real data (2 passes, 300 research runs each) | Completed. 0 of 100 agents passed the research gate, so none may trade (details below). |
| Walk-forward portfolio backtest by market regime | Completed: `PORTFOLIO_BACKTEST_REPORT.md`. Results are below. |
| Data integrations (Coinbase, Kraken, Yahoo Finance public data) | PASSED. Coinbase listed 842 pairs and Kraken 1,460. All 100 agents received real history (Coinbase for crypto, Yahoo for stocks, ETFs, FX and futures). |
| Broker integrations with real accounts (Alpaca, OANDA, Kraken, IBKR, Coinbase) | NOT PERFORMED: no account credentials exist in this environment, by design (credentials are never pasted into chat). The adapters stay UNVERIFIED, so live trading cannot be armed. Offline tests cover order handling, duplicate prevention, uncertain submissions, reduce-only exits and the live-mode refusal. |
| Hardware thermal behaviour of a physical PC | NOT PERFORMED here: the build machine and the Windows test machine are virtual machines with no temperature sensors, and no physical PC is reachable from this environment. **Use the built-in check on your PC**: double-click `CHECK_COMPUTER_TEMPERATURE.bat` (or press "Run thermal check" on page 3). It runs every CPU core at full load, reads Windows' own sensors, stops at 95 °C and writes a report to `thermal-reports`. While the program runs, it also reads the temperature every 30 seconds and pauses training when the PC is hot. Measured load of the program itself, with no training running: 3–6% of one CPU core, about 115 MB of memory. |
| JARVIS voice assistant, read-only link to the Trading AI (1.6.0) | PASSED where it could be run. JARVIS installs, type-checks (`tsc`), builds (`vite`) and lints. Its nine trading tools were run against a live Trading AI started from source: all nine returned real data; a request for `/api/connections`, a path-traversal path and a bad agent id were refused by JARVIS's own allowlist; and the server itself answered **401** to a write (POST) and to `/api/connections` when given the read-only token. 3 new tests and a new self-test step cover the server side. **NOT PERFORMED:** voice, the microphone, the camera and the 3D screen (they need a real Chrome window and a Claude Code login), and a run of JARVIS on Windows (the CI workflow builds it there, but does not talk to it). |
| Small account ($100) | CHECKED in the code, not in live trading: at $100 the risk limits allow at most $10 per order, $25 per position and a $3 loss per day. No agent is allowed to trade yet, so there are no small-account trades to measure. |
| Turning $100 into $300,000 | NOT PROMISED and not tested as a goal: it needs 3,000 times the money. `CAN_100_DOLLARS_BECOME_300K.md` shows the maths and the negative measured results. |
| Market removal (1.7.0): only US stocks, crypto and meme coins | PASSED: 11 tests. The universe has no forex or futures; ETFs and indices are price references that cannot be traded; the risk service denies entries in etf, fx, future, index and option markets and still allows closing an old position; the coverage page lists only crypto and US stocks; the roster is 40 crypto, 15 meme and 45 stock agents. Live check on 2026-10-14: Coinbase listed 16 meme-coin USD pairs. |
| JARVIS voice control (1.7.0) | PASSED where it could be run: 24 tests, a self-test step, and a live run against the Trading AI started from source: all 11 read tools returned real data; `pause_entries` ran at once; `start_system` and `set_paper_balance` waited; JARVIS's own token could not approve them (401); `arm_live` was refused (403); after the owner approved, the system started and the paper balance became 100.00. The page-1 approval card was opened in Chromium and Reject cleared it. NOT PERFORMED: voice, microphone and a JARVIS session with a Claude login. |
| JARVIS spoken alerts and command IDs (1.7.0) | PASSED where it could be run: with a live Trading AI, an owner Emergency Stop produced the announcement "Emergency stop engaged. All bots are stopped..." in JARVIS's relay within seconds (the backlog before it was skipped). A simulated lost reply was reported as "Outcome UNKNOWN". A repeated command ID returned the first outcome (test). NOT PERFORMED: hearing it spoken (needs a browser with audio and a Claude login). |
| JARVIS screen and two pages (1.8.0) | PASSED in Chromium: the trading page, the Agents overlay and the Brokers page render with no browser errors and no sideways scrolling at 1600 px and 390 px; positions, trades and P&L shown were the paper broker's own records on DEMO (simulated) markets in a test folder. |
| Training all 100 agents of the current roster (1.9.0) | Completed on real data on 2026-10-14 (26 minutes, 300 runs: 3 candidates for each agent, including the 15 meme-coin and 11 new stock agents). 0 of 100 passed the gate: 297 REJECT, 3 RESEARCH FURTHER. 139 runs reached 30 test trades, 49 had a positive held-out Sharpe, the best Deflated Sharpe was 0.28 (0.95 required), 275 lose money at 2x costs. Details: `AGENT_TRAINING_REPORT.md`. The portfolio report still describes the earlier roster. |
| JARVIS self-editing, ask-first, voice and greeting (1.9.1) | PASSED with a real Claude session and the real bridge: he edited his own screen file (backup taken, no card), his code check passed, and "undo that" restored the file byte for byte. A file outside his folder showed the "May I?" card: Deny left no file, Allow created it. Asked to raise the Trading AI's daily loss limit, he refused and `risk/service.py` was unchanged; a code-level block now refuses any change aimed at the Trading AI folder (10 of 10 sample calls classified right). In Chromium with a stand-in microphone and speaker: he powered on by himself, spoke the greeting with the test folder's real paper balance, took a spoken command, showed the card (in the screen's own colour), and spoke the answer after Y. No page errors. **Found and fixed:** the bundled Claude engine (agent SDK 0.3.220) was too old for the model and every question failed; now 0.3.287. The greeting was skipped when the Trading AI was not running. NOT PERFORMED: real speakers and microphone, and a run on your PC. |
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
| 13 | **Real Windows only: a test failed because of 32-bit integers.** On Windows, numpy's default integer is 32-bit, so `np.arange(n) * 3_600_000` in test data overflowed and produced bar times that were not increasing. | The test data builders use 64-bit integers. The program code was checked: it only uses `arange` for indexes, and the demo data already used 64-bit. | First real-Windows run failed at `test_crypto_backtest_respects_the_24_hour_hold`; the second run passed. |
| 14 | **Wine only: the exe aborted** when reading temperatures, because Wine does not implement one Windows performance-counter call (`PdhGetFormattedCounterArrayW`). | Single counters use the call Wine has; the thermal-zone list is skipped under Wine and reported as not available there. Real Windows uses the full path. | Wine self-test 32 of 32; real Windows run read the same counters. |
| 15 | **Thermal check: a 1-second test load could warn about a falling work rate** (noise, seen on the Windows runner). | The work-rate comparison is only made over a load of 30 seconds or more; a real check runs at least 60 seconds. | `test_a_falling_work_rate_is_judged_only_over_a_long_enough_load`; the second Windows run passed. |

## Training result (what the agents learned)

Full tables: `AGENT_TRAINING_REPORT.md`.

**No agent passed the research gate, so none may trade, even in paper.**

| Measure | Result |
|---|---|
| Research runs on real data | 300 (3 candidates for each of 100 agents; current roster, 2026-10-14) |
| Runs with at least 30 held-out test trades | 139 |
| Runs with a positive held-out Sharpe | 49 |
| Highest Deflated Sharpe | 0.28 (0.95 required) |
| Runs that lose money at 2x costs | 275 |
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
4. The exe has run on a real Windows 11 virtual machine and under Wine, but not on a physical PC, and the thermal behaviour of your computer has not been measured until you run the thermal check on it.
