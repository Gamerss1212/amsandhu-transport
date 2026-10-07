# Build status

Updated: 2026-10-07 (release 0.9.0: slim download; the owner switches real money on and off from the page; it is OFF; the 30-day paper run is next)

## Where things stand

- **The 25-agent core is built.** All 25 run in every cycle at `phase: 4` (the default in `config/default.yaml`).
- The other 25 roster agents are **parked** (`core: false` in `config/agents.yaml`): optional, built later only if they earn it.
- New signal agents A13 and A15 are in **shadow**: sealed and scored by A35, no vote until the owner promotes them.
- Mode: **paper**. Autonomy level: **1**. Live trading: **not approved**.
- **Real money: built, OFF.** The owner asked for it on 2026-10-06. It is a crypto-only mirror for Kraken (`docs/REAL_MONEY.md`). It sends nothing until the owner opens all 11 gates, including a dated approval row below. It was tested against a fake exchange and real Kraken prices, never a real account.
- **Simple to run:** `QuantAgents.bat` (Windows) or `bash QuantAgents.sh` installs on the first run, then opens the app in the web browser (a page on this computer only, `http://127.0.0.1:8765`).
- Tests: 503, all gates green, 97% coverage overall, 100% branch coverage on risk.
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
| 8 | Micro-live (owner approval) | Code built 2026-10-06 at the owner's request, **switched off**. Needs the owner's approval row and 10 more gates (`docs/REAL_MONEY.md`). Its preconditions are not met: no strategy has passed A44. |
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
| `setup.bat` carried on after a crash (Windows crash exit codes are negative; `if errorlevel 1` misses them) | Any non-zero exit stops setup |
| With numpy 1.26 (the oldest supported) the type check failed on one line | Clean on numpy 1.26.4, 2.4.6 and 2.5.3 |
| One test expected `/` in a path; Windows prints `\` | The test works on both |

**Where the download was tested** (unzipped from the release, then `setup`):

| System | Python | numpy | Result |
|---|---|---|---|
| Linux | 3.11, 3.12, 3.13 | 2.4 and 2.5 (newest) | all gates green |
| Linux | 3.11 | 1.26.4 (oldest supported) | all gates green |
| Windows (Wine) | 3.11 | 1.26.4 | `setup.bat`: all gates green (433 passed, 1 skipped by design), demo OK; `daily.bat` with live data and `status.bat` OK |

- Wine (the Windows layer used for testing here) cannot run numpy 2.x: it lacks one C library
  function (`crealf`) that real Windows has. So the Windows test used numpy 1.26.4.
- On a real PC, setup installs the newest numpy. That version passes every gate on Linux.

**New**
- `setup`, `daily` and `status` scripts for Windows and macOS/Linux.
- The `status` dashboard and the `doctor` install check.
- `daily` reads its symbols from the config.
- `START_HERE.md`.
- The release builder: `python scripts/make_release.py`.

## Release 0.7.0 (2026-10-06): one-click menu, real money built but off

**Simple to run**
- `QuantAgents.bat` (Windows) and `QuantAgents.sh` (macOS/Linux):
  - the first run installs everything (setup, all gates, a demo);
  - after that, every double-click opens the menu.
- The menu (`quantagents menu`) has 13 numbered choices:
  - run today and show the dashboard;
  - turn the automatic daily run on or off (Windows Task Scheduler or cron);
  - stop all trading, and resume with the reset phrase;
  - edit the symbols;
  - three real-money choices (what is still needed, a preview, a test order);
  - check the install;
  - bring an account over from an older folder.
- The menu cannot raise a limit or switch on real money. Every choice runs an ordinary
  command.

**Real money (Phase 8), switched off.** `src/quantagents/execution/live.py`, `quantagents live check | sync [--dry-run] | test-order`.
- **What it is:** a mirror. The paper cycle still decides; the mirror copies the paper
  portfolio's weights to Kraken, scaled to `live.budget` (default 0).
- **Gates, all 11 required:**
  - the owner's dated "Approve Phase 8 micro-live" row in this file;
  - in the config: `execution_mode` live, `autonomy_level` 3, `live_trading_approved`;
  - in `.env`: the approval phrase and the exchange keys;
  - a budget above 0;
  - crypto on one exchange (Kraken), with ccxt installed;
  - the kill switch armed;
  - a paper cycle at most 4 days old that was not halted.
- **Safety in code:**
  - reconciles with the exchange first; a break engages the kill switch;
  - sells first, and only what the mirror bought;
  - limit orders at most 0.5% past the bid/ask and at most `max_order_value`; whatever is
    unfilled is cancelled;
  - buys need free cash and a price within A49's 5% band;
  - any error engages the kill switch;
  - one run at a time: a lock file stops a menu click and a scheduled run from both buying;
  - keys are scrubbed from every message;
  - there is no withdrawal or transfer code (a test checks).
- **Alerts** (optional, Telegram): every fill, every halt, and any loss limit at 75% or more.
- **Separate files:** paper and live state never mix. The live ledger is
  `state/live_ledger.json`.
- **`.env` is read at start-up** (values never printed). Tests never read it, and they clear
  every live variable.

**Tested**
- 42 new automated tests (live mirror, menu, schedule, run locks) on a fake exchange.
  - **Scenarios covered:** reconciliation breaks, partial fills, timeouts, crash recovery,
    price band, cash cap, secret scrubbing, a failed test order, an unreachable exchange.
- **Real Kraken market data** (public prices, minimum sizes, precision) with a fake account:
  - the preview, a buy run and an idempotent second run all worked;
  - the test order rested 20% under the bid and was cancelled.
- **A clean install from the zip on Linux** (`bash QuantAgents.sh`, Python 3.11, numpy 2.x):
  - setup and all gates passed (472 passed, 1 skipped by design);
  - then, from the menu: a live-data daily run (fetch, export, cycle and watchdog, all exit 0),
    the dashboard, the real-money check (8 of 11 gates closed, as expected), the preview
    (refused, as expected), and stop then resume.
- **Windows under Wine** (Python 3.11, numpy 1.26.4):
  - every gate green (472 passed, 1 skipped by design), and again for the changed test files
    after the run locks were added;
  - `QuantAgents.bat` opened the menu; dashboard, real-money check, stop and resume worked;
  - its first-run branch calls setup and stops cleanly on a failed or crashed setup.
  - Wine's `schtasks` is a stub, so the automatic schedule could not be created there. The
    menu now counts a task as ON only when Windows lists it by name.

**Not tested** (said plainly):
- a real exchange account, because no keys were shared;
- Windows Task Scheduler on a real PC.

**Review round (2026-10-07): found and fixed before the download was built**

| Problem | Fix |
|---|---|
| Crypto names like `BTC-CAD.KRAKEN` ran into the next column of the cycle report | Columns size to the longest name (a test fails without the fix) |
| The dashboard never compared the paper account with simply holding | A scoreboard line: paper vs holding the same symbols in equal parts since the first paper day (no fees) |
| A failed scheduled run was silent until someone looked | With Telegram set up, every daily run sends one line: OK with the day's result, or FAILED and which step |
| Updating meant copying files by hand, and two copies could both trade (two mirrors would both buy on Kraken) | `import-from` (menu 12) copies the account, then engages the old folder's kill switch and turns its task off; a folder already moved cannot be imported twice; approvals are not copied |
| Two folders with the same name shared one scheduled task (turning one on replaced the other) | Task names carry a code from the full path |
| Windows tasks made by `schtasks` skip runs on battery and never catch up a missed time | The task is made from XML: runs on battery, catches up after sleep, never two at once. If Windows refuses it, the plain task is made and the menu says what it lacks |
| Setup checked the demo settings, not yours (a confusing warning on first install) | Your settings file is created first and checked |
| No backup of the account files | After each daily run, `state/backups/<date>/` (the newest 30 days) |
| "Task already off" relied on English error text from Windows (wrong on a French or other-language Windows) | The menu asks Task Scheduler whether the task exists before deleting it |

- **Checked on live data:** a crypto folder (BTC-CAD and ETH-CAD on Kraken) ran a full day.
  - Data health was 100 and every agent ran.
  - The result was no trade: only one team agreed, and two are needed.
- **Kraken gives only the last 720 daily candles** (about 2 years). Every agent had enough
  history.
- **Fresh install from the zip on Python 3.13** (`bash QuantAgents.sh`):
  - every gate green (483 passed, 1 skipped by design);
  - the account was brought over from an earlier test folder, and that folder was stopped;
  - a live-data day continued the imported account (paper day 2);
  - the scoreboard read: paper +0.00% vs holding the same 8 ETFs +0.38%, so paper is behind.
- **Windows under Wine:**
  - the changed test files pass;
  - menu choice 12 imported an account from a quoted Windows path (`"C:\..."`) and engaged the
    old folder's kill switch.
- **Not tested on a real PC:** the XML task (Wine has no working Task Scheduler). The menu
  falls back to the plain task if Windows refuses it.

## Release 0.8.0 (2026-10-07): the local web app

The owner said the system was not easy to run and asked for "a local host site". So
`QuantAgents.bat` / `QuantAgents.sh` now open QuantAgents in the web browser. The text menu
still exists (`quantagents menu`).

**What it is**
- `src/quantagents/webapp.py` (Python's own web server, no new packages) and
  `src/quantagents/web/` (one page).
- Boxes:
  - **Today:** run today, with the live output.
  - **Paper account:** tiles, the scoreboard, and a chart of paper vs holding, with a table
    view.
  - **Last decision:** each symbol and why there was no trade.
  - **Automatic daily run:** ON and OFF.
  - **Stop or resume:** STOP, and resume with the phrase.
  - **Your symbols:** ready-made lists or your own.
  - **Real money:** the 11 gates, check, preview and test order.
  - **Tools:** install check, bring an account over, close the app.
- **No new powers.** Every button runs an ordinary `quantagents` command.
  - It cannot raise a limit, switch on real money or show a key.
  - The test order still needs every gate, plus a typed YES.
- **Symbols are saved carefully:**
  - only `universe` (and, for crypto, the unit size) changes;
  - every other setting is kept;
  - a file that would not load is never written;
  - stocks and crypto cannot be mixed;
  - a completely different list is refused once the folder has a paper account.
- **Double-clicking twice** opens the running app instead of starting a second one.
- **Two folders** each get their own address (8765, 8766...).

**Safety (tested)**
- It listens on 127.0.0.1 only.
- It refuses a request whose host name is not this app (DNS rebinding).
- Every request needs a random key that only the app's own page knows. A button press from
  another site's page is refused (Origin check).
- Strict Content-Security-Policy: no outside scripts, and the page cannot be framed (no
  hidden clicks).
- One job at a time. **STOP** always works, even while a job runs.
- A command that crashes still ends its job, and shows the error.

**Checked**
- 12 automated tests (`tests/test_webapp.py`).
- A real browser (Chromium):
  - light, dark and phone width, with no sideways scrolling and no page errors;
  - clicks on every main button: a live-data day, stop, a wrong and then the right resume
    phrase, a refused crypto switch, a bad symbol, the preview, and the test order without
    YES.
- Windows under Wine: `QuantAgents.bat` started the app, the page data loaded, the install
  check ran from a button, and "Close the app" stopped it.
- Fresh install from the zip (Linux, Python 3.11): every gate green (495 passed, 1 skipped by
  design). Then `bash QuantAgents.sh` opened the app, and the first button press created the
  paper account on live prices. The other buttons behaved as above.
- Not checked: opening the browser on a real Windows PC (Wine has no browser).
  `QuantAgents.bat` always prints the address, so it can be typed in by hand.

## Release 0.9.0 (2026-10-07): only what is needed, and real money from the page

The owner asked to "organize the final" (too much random stuff) and to make real money usable.

**A slim download**
- The owner's zip now holds 94 files instead of 184:
  - the program and its settings;
  - the start scripts (`QuantAgents`, `setup`, `daily`);
  - three guides (`START_HERE`, `REAL_MONEY`, `schedule`);
  - a short `docs/STATUS.md` for the owner's own approvals.
- Left out: tests, the spec, research logs, Claude Code files and developer tools.
  `make_release.py --full` still builds the developer copy.
- Setup in the slim copy skips the developer tests and their tools, so it installs faster.
- `status.bat` / `status.sh` are gone: the page shows the same.
- Old zips were removed from `downloads/` (they stay in git history).

**Real money from the page** (`execution/arming.py`)
- **Step 1: Save keys.**
  - The Kraken key and secret go into `.env`; other lines are kept.
  - The keys are never shown again or sent back to the page. On macOS/Linux the file is made
    private.
- **Step 2: Switch real money ON.**
  - Needs saved keys, a crypto-on-Kraken folder, a budget above 0 and at most 1,000
    (micro-live), the owner's name, and the approval phrase typed exactly.
  - Every check runs before any file changes. Then it writes the live settings, the phrase in
    `.env`, and the dated row in `docs/STATUS.md`.
  - No risk limit is touched.
- **Switch real money OFF** works at any time, even while a job runs. It removes the live
  settings and the phrase; the keys stay saved.
- **The gates did not change.** Orders still need a fresh paper day that A49 did not halt,
  the kill switch armed, and reconciliation with Kraken.
- The gate hints now point to the page instead of to files.

**Checked**
- 7 new tests; all 503 pass and every gate is green.
- In a real browser, the whole flow worked:
  - keys saved and hidden, the input boxes cleared;
  - a wrong phrase refused;
  - switched ON: the row, the settings and the phrase were written;
  - the preview waited for a paper day;
  - switched OFF: back to paper.
- A fresh install from the slim zip on Linux (Python 3.12) passed the install check, then ran a
  live-data paper day from the page.
- Under Wine, `setup.bat` from the slim zip skipped the tests, passed the install check and
  ran the demo.

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

1. **Owner:** unzip `QuantAgents-50-v0.9.0.zip` and double-click `QuantAgents.bat`. Your
   browser opens the app.
   - Press **Run today's paper day**, then **Turn ON** for the automatic daily run.
   - Let it paper-trade for 30 trading days; the page shows progress and the scoreboard.
2. **Owner (optional):** decide the PBO question in the Phase 2 results.
3. **Real money is your decision.** It needs:
   - a separate crypto folder;
   - 30 paper days;
   - the steps in `docs/REAL_MONEY.md`: save keys, then switch on in the Real money box.

   No strategy has passed validation yet, so the honest expectation is "no edge".
4. After 30 clean paper days, Phase 4 scoring has real data to score.
