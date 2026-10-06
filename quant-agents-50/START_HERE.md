# Start here: QuantAgents-50 (version 0.6.0)

A 25-agent research and **paper-trading** system. It decides once a day, after the market
closes, using real prices. It **never places real orders**: real money stays locked until you
approve Phase 8 yourself in `docs/STATUS.md`.

## What it does

- **Every weekday after the close:**
  - downloads fresh daily prices (free, no account or API key needed);
  - checks the data for gaps, stale prices and unadjusted splits;
  - lets 25 agents vote;
  - sizes any trade under strict risk limits;
  - records everything in a paper account that started at 10,000 CAD.
- **A watchdog** stops trading if anything goes stale. Only you can restart it.
- **The research tools** test strategies honestly. So far no strategy has beaten simply
  holding the same funds. See `docs/research/grid-2026-10-06.md`: 7,668 backtests.

## Windows (about 10 minutes)

1. **Install Python 3.11 or newer** from python.org. On the first install screen, tick
   **"Add python.exe to PATH"**.
2. **Unzip** this folder somewhere simple, for example `C:\QuantAgents-50`.
3. **Double-click `setup.bat`.** It installs everything into a private `.venv` folder, checks
   the install, runs all 433 tests and shows a demo. It ends with "Setup finished."
4. **Optional:** open `config\my_universe.yaml` in Notepad and change the symbols. The
   default is 8 US-listed ETFs.
   - Toronto listings end in `.TO` (for example `XIC.TO`).
   - Crypto from Kraken is written `BTC-USD.KRAKEN`.
   - Keep stocks and crypto in separate configs: crypto trades on weekends.
5. **Double-click `daily.bat` once.** You should see `--- cycle (exit 0)` and
   `Watchdog: all clear.`
6. **Double-click `status.bat`** any time to see the account, the kill switch, the last
   decision and your progress toward 30 paper days.
7. **Schedule `daily.bat`** in Task Scheduler for weekdays at 3:30 PM Mountain Time. Steps are
   in `docs/schedule.md`.

## macOS / Linux

Same steps, using `bash setup.sh`, `bash daily.sh` and `bash status.sh`. Schedule `daily.sh`
with cron (see `docs/schedule.md`).

## Useful commands

Run these from the folder, after `setup` (Windows: `.venv\Scripts\python -m quantagents ...`).

| Command | What it does |
|---|---|
| `python -m quantagents doctor` | Checks the install, the config and the folders |
| `python -m quantagents status` | One-screen dashboard |
| `python -m quantagents killswitch engage --reason "my stop"` | Stops all new trading now |
| `python -m quantagents killswitch reset --confirm I_REVIEWED_THE_HALT` | Resumes after a stop (only you can) |
| `python -m quantagents demo` | One decision cycle on fake data |
| `python -m quantagents research --universe us=data/prices.csv --noise 20` | The full research grid on your data |

## Where things are

| Path | What is there |
|---|---|
| `docs/STATUS.md` | What is built, every test result, your approvals |
| `docs/schedule.md` | The daily schedule and how to stop and resume |
| `docs/research/` | Every strategy test, failures included, and the trial log |
| `config/my_universe.yaml` | Your symbols (created by setup) |
| `state/`, `runs/`, `data/` | Your paper account, decision logs and price store (created as it runs) |

## Honest limits

- The free price data is "survivorship-biased" and "not point-in-time": funds that closed are
  missing, and history can be restated. Every result says so.
- Paper results are not real results. Real fills, taxes and your own decisions will differ.
- No strategy here has passed the promotion tests. "No edge found" is the honest result so far.
- Not financial advice.
