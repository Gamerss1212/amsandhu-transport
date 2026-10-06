# Build status

Updated: 2026-10-06 (release 0.6.0: Phases 1-3 built, research grid run, clean-install tested; the 30-day paper run is next)

## Where things stand

- **The 25-agent core is built.** All 25 run in every cycle at `phase: 4` (the default in `config/default.yaml`).
- The other 25 roster agents are **parked** (`core: false` in `config/agents.yaml`): optional, built later only if they earn it.
- New signal agents A13 and A15 are in **shadow**: sealed and scored by A35, no vote until the owner promotes them.
- Mode: **paper**. Autonomy level: **1**. Live trading: **not approved**.
- Tests: 434, all gates green, 99% line coverage overall, 100% branch coverage on risk.
- **Phase 1 passed** (2026-10-06): real data store, free data sources, split check, event-driven backtester, benchmark, leakage tests.
- **Phase 2 done** (2026-10-06): five published strategies tested on real data, pre-registered, run once. **All five FAIL** the promotion bar. No edge strong enough to trade has been found yet.
- **Phase 3 built** (2026-10-06): chaos tests, watchdog, daily run and schedule guide. The 30-day paper run needs calendar time on the owner's PC.
- **Research grid** (2026-10-06): 87 pre-registered variants x 4 universes (US multi-asset ETFs, US sectors, US index ETFs, BTC+ETH). Every variant ran at 1x and 2x costs and on 20 noise panels: **7,668 backtests**. **All four finalists FAIL.** No strategy was shown to beat buy-and-hold. Report: `docs/research/grid-2026-10-06.md`.
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
| 2 | First signals and validation | **Done** 2026-10-06: 5 families, all FAIL (see Phase 2 results) |
| 3 | Risk, execution, paper | Built and tested 2026-10-06; **30 paper days to run** (owner's PC, `docs/schedule.md`) |
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

## Phase 2 results (2026-10-06, real data)

| Family | Universe | Sharpe (buy-and-hold) | Max drawdown (buy-and-hold) | Failing checks | Verdict |
|---|---|---|---|---|---|
| tsmom_blend_vt10 | 8 multi-asset ETFs | 0.64 (0.58) | 7.8% (37.2%) | PBO 0.92 | FAIL |
| faber_10m | 8 multi-asset ETFs | 0.64 (0.58) | 13.3% (37.2%) | PBO 0.91 | FAIL |
| vt10_hold | 8 multi-asset ETFs | 0.57 (0.58) | 23.6% (37.2%) | t 2.70, PBO 0.31 | FAIL |
| xsmom_12_1 | 9 sector SPDRs | 0.60 (0.58) | 44.9% (52.2%) | PBO 0.93 | FAIL |
| rsi2_10 | SPY QQQ IWM DIA | 0.20 (0.58) | 16.0% (54.0%) | t, PSR, DSR, PBO, SPA, 2x costs | FAIL |

**In plain words**
- **No edge proven.** None of the five beats simply holding the same ETFs by a margin the
  tests can trust.
- **Lower drawdowns:** the two trend rules (tsmom_blend, faber) had far smaller drawdowns at a
  similar Sharpe. They also earned less.
- **RSI(2)** loses its edge to trading costs.
- **Why three families fail only on PBO:** each was tested with 2-3 near-twin variants. With so
  few, so similar variants, PBO mostly measures a coin flip between them. That is a
  limitation of the rule, not proof of an edge.
- **Owner decision:** whether PBO should only apply when a family has, say, 10+ variants. Any
  change applies to future families only. These results stay FAIL.

**A21 carry: not built.**
- **Crypto funding rates** belong to perpetual futures, which this kit cannot trade (spot only,
  Canada).
- **FX carry** needs interest-rate data that the store does not have yet.
- A21 stays registered and idle until a carry source exists.

## Phase 3 (2026-10-06)

**Chaos tests:** all pass (`tests/test_chaos.py`).
- **Stale feed:** that symbol is blocked. If the whole feed is stale, A49 halts and fires the
  kill switch.
- **Duplicate fill:** applied once. If the broker double-books a fill, the next cycle sees a
  reconciliation break, halts and fires the kill switch.
- **Broker drops before the open:** reconciliation break, halt and kill switch. Queued orders
  are kept.
- **Broker drops at submit:** nothing is sent, and A46 fires the kill switch.
- **Corrupted kill-switch file** (empty, garbage, half-written, wrong type, or a folder in its
  place): it counts as engaged, and only the reset phrase clears it.

**Real data through the full cycle:** 8 ETFs, as of 2026-10-05.
- Data health 100/100, nothing blocked, all 25 agents ran.
- Decision: no trade. GO: none, 8 reasoned no-trades.
- Across 3,608 sampled days of real history, A02 raised no false split or stale alarms.

**Watchdog and daily run:** built and tested. The guide is in `docs/schedule.md`. It is not
switched on: the owner approves the schedule first.

**30 paper days:** not started. This needs about six weeks of calendar time on the owner's PC.

## Research grid (2026-10-06)

Pre-registered in `docs/research/grid-preregistration.md` (committed before the run). Full report:
`docs/research/grid-2026-10-06.md`, with every variant in the `.csv` next to it.

| Universe | Best of 87 | Sharpe | Buy-and-hold Sharpe | Walk-forward OOS Sharpe (B&H) | Verdict |
|---|---|---|---|---|---|
| multi_asset (8 ETFs) | xsmom_126_0_half | 0.72 | 0.60 | 0.51 (0.87) | FAIL |
| sectors (9 SPDRs) | faber_10m | 0.69 | 0.53 | 0.83 (0.99) | FAIL |
| us_index (SPY QQQ IWM DIA) | vt15_21_hold | 0.68 | 0.58 | 0.61 (0.94) | FAIL |
| crypto (BTC ETH) | sma_50 | 1.22 | 0.72 | 0.25 (0.43) | FAIL |

**In plain words**
- **Nothing beats holding.** 0 of 344 variants beat buy-and-hold after the false-discovery
  check.
- **Picking last period's winner did worse than holding**, in every universe.
- **Luck alone** (noise panels with no trends) produces winners about as good-looking as the
  real ones.
- **Trend and volatility rules** (Faber, trend blend, vol targeting) cut the worst losses
  (drawdowns) a lot. Their risk-adjusted return was similar or slightly better, but too little
  to prove. Outside crypto they earned less than holding.

**Engine fixes in this round**
- **Holdings now drift with prices.** Before, the book was reset to its targets every day for
  free. The two backtest engines now agree within 0.01% a year.
- **Crypto uses 365-day years.**
- **Unfinished crypto bars are dropped** until the UTC day ends.

Phase 2 numbers came from the old engine. Their verdicts (all FAIL) stand.

## Release 0.6.0 (2026-10-06): problems found and fixed

Found by installing the download from scratch on Python 3.11, 3.12 and 3.13 (Linux, and
Windows under Wine), running it on live data, and reviewing the code.

| Problem | Fix |
|---|---|
| A clean install on Python 3.12/3.13 failed the type check (new numpy 2.5 type hints) | Code fixed; ruff and mypy pinned so a new release cannot break a fresh install |
| Kraken `BTC/USD` and Yahoo `BTC-USD` were both stored as `BTC-USD`: the store could switch sources | Exchange data is now `BTC-USD.KRAKEN` |
| Store file names could contain characters Windows forbids | Safe names on every system |
| Each read scanned every snapshot ever stored (slower every day) | A read opens only the one file it needs |
| The daily run downloaded 26 years of history every day | 5 years (enough for every agent) |
| A second research run on the same day overwrote the report | Reports are never overwritten (`-2`, `-3`...) |
| Two universes in one folder shared one paper account (wrong account value) | Refused with a clear message; one folder per universe (`config/crypto.example.yaml` for crypto) |
| Research workers were forked from a multi-threaded process (deadlock risk on Python 3.12+) | Workers start the same way as on Windows ("spawn") |
| `setup.bat` gave up if the Python launcher was broken | It tries the launcher, then `python`, and checks the version |
| The download builder dropped `src/quantagents/data/` and `tests/data/` (caught before release) | Fixed; a test proves every program and test file ships |

**New**
- `setup`, `daily` and `status` scripts for Windows and macOS/Linux.
- The `status` dashboard and the `doctor` install check.
- `daily` reads its symbols from the config.
- `START_HERE.md`.
- The release builder: `python scripts/make_release.py`.

## Human approvals

| Date | Decision | Owner |
|---|---|---|
| (none yet) | | |

## Open issues

- Real-data research so far: Phase 2 (5 families) and the research grid (87 variants x 4 universes): no strategy passes. Synthetic results prove nothing about real markets.
- The default config universe is the synthetic SYN_A..SYN_F. To paper-trade real symbols, put them in `universe.symbols` (or `[]` for every symbol in the file). `cycle` now says so when nothing can trade.
- Export stocks and crypto to separate CSVs: crypto trades on weekends, so a mixed file has gaps that make A02 block the stocks.
- On the synthetic data the full chain rarely says GO: two teams must agree and the edge must beat 1.5x costs. That is by design.
- With only 4 voting agents, the 25% per-agent cap forces equal weights. A35's weights start to matter at 5+ voters.
- A09 works from daily bars. Its high-low spread proxy is shown for information only; replace it with real quotes when an L1 feed exists.

## Next step

1. Owner: unzip `QuantAgents-50-v0.6.0.zip` and follow `START_HERE.md`. On Windows:
   install Python 3.11+, double-click `setup.bat`, then `daily.bat` once, then `status.bat`.
2. Owner: schedule `daily.bat` (`docs/schedule.md`) and let it run for 30 trading days. Check
   `status.bat` now and then.
3. Owner (optional): decide the PBO question in the Phase 2 results.
4. After 30 clean paper days: Phase 4 scoring has real data to score. Phase 8 (real money)
   stays locked until you approve it here.
