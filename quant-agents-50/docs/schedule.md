# Daily paper-trading schedule (Phase 3)

In paper mode nothing here can place a real order. If you have armed real money yourself
(`docs/REAL_MONEY.md`), each daily run ends with one more step, `live sync`.

## The easy way

Double-click `QuantAgents.bat` (or `bash QuantAgents.sh`). In the **Automatic daily run**
box, press **Turn ON** (or **Turn OFF**).

The app picks the time for you:
- **Stocks and ETFs:** Monday to Friday at 3:30 PM.
- **Crypto:** every day at 7:00 PM.

The times are on this computer's clock, so set it to Alberta time.

**On Windows** the app makes a Task Scheduler task named
`QuantAgents daily (<folder name> <code>)`. The code comes from the folder's full path, so two
folders never share a task. The task:
- also runs on battery power;
- runs as soon as possible after a missed time (computer off or asleep);
- never starts a second copy while one is running.

If the app says Windows refused the full settings, set the two missing ones by hand:
1. Open Task Scheduler and find the task. Open Properties.
2. **Conditions:** untick "Start the task only if the computer is on AC power".
3. **Settings:** tick "Run task as soon as possible after a scheduled start is missed".

**On macOS and Linux** the app adds one cron line.

The rest of this page does the same by hand.

## What runs, and when

| When (Mountain Time) | What | Command |
|---|---|---|
| Weekdays 3:30 PM (after the US close at 2:00 PM MT, once the daily bars are final) | Fetch, export, one paper cycle, watchdog | `daily.bat` (Windows) or `bash daily.sh`; both run `python -m quantagents --config config/my_universe.yaml daily` |
| Weekdays 4:30 PM | A second, independent watchdog | `python scripts/watchdog.py --data data/prices.csv` |

What each part does:
- **daily:**
  - Reads the symbols from `config/my_universe.yaml`. Crypto from an exchange is written
    `BTC-USD.KRAKEN`.
  - Downloads a fresh snapshot of the last 5 years. The append-only store keeps every old one.
  - Writes the CSV and its caveats.
  - Runs the cycle only if there is a trading day the last cycle has not seen, so a holiday
    or a second run the same day is skipped.
  - Then runs the watchdog. Everything is also written to `runs/daily.log`.
  - Only when your config's `execution_mode` is `live`: `live sync` copies the paper portfolio
    to Kraken. It refuses unless every real-money gate is open, and it is skipped after any
    failed step.
- **watchdog:** engages the kill switch if a cycle has not run for more than 2 weekdays, if the
  newest bar is more than 3 weekdays old, or if a state file cannot be read. It never resets
  the switch.
- **To resume after a stop:** read `runs/daily.log`, fix the cause, then
  `python -m quantagents killswitch reset --confirm I_REVIEWED_THE_HALT`.

## Before the first run

1. Run `setup.bat` (Windows) or `bash setup.sh`. It installs everything and runs every
   quality gate; all must be green.
2. `setup.bat` (or `setup.sh`) copies `config/us_etfs.example.yaml` to
   `config/my_universe.yaml`. Set your symbols there. Only the universe changes; every risk
   limit keeps its default.
3. Run `daily.bat` once by hand and read the report. Check that `data health` is 100 and that
   `blocked` is `none`. `status.bat` shows the result on one screen.

## Windows (Task Scheduler)

1. Open Task Scheduler and choose Create Basic Task. Name it `QuantAgents daily`.
2. Trigger: Weekly, Monday to Friday, at 3:30 PM.
3. Action: Start a program.
   - Program: the full path to `daily.bat`, for example `C:\QuantAgents-50\daily.bat`.
   - Start in: the project folder, for example `C:\QuantAgents-50`.
4. Repeat for `QuantAgents watchdog` at 4:30 PM:
   - Program: `C:\QuantAgents-50\.venv\Scripts\python.exe`
   - Arguments: `scripts\watchdog.py --data data/prices.csv`
   - Same Start in folder.
5. In each task's properties, tick "Run whether user is logged on or not". The PC must be on
   at that time.

## macOS / Linux (cron)

`crontab -e`, then (times in your machine's local time; this example is Mountain Time):

```
30 15 * * 1-5  bash ~/quant-agents-50/daily.sh
30 16 * * 1-5  cd ~/quant-agents-50 && .venv/bin/python scripts/watchdog.py --data data/prices.csv
```

## A crypto folder

- Use a second copy of the folder, with `config/crypto.example.yaml` copied to
  `config/my_universe.yaml`.
- Crypto trades every day, and its daily bar ends at midnight UTC (6:00 PM Mountain Time in
  summer, 5:00 PM in winter). So schedule its `daily.bat` for **every day at 7:00 PM MT**,
  not weekdays only.
- Unfinished bars are never used: the downloader drops today's bar until the UTC day is over.

## The 30-day paper run (Phase 3 acceptance)

- 30 trading days with zero A49 breaches and no reconciliation break. This needs real
  calendar time: about six weeks.
- Each day, glance at the end of `runs/daily.log`. Each week, test the kill switch by hand:
  1. `python -m quantagents killswitch engage --reason "weekly test"`
  2. `python -m quantagents killswitch status`
  3. `python -m quantagents killswitch reset --confirm I_REVIEWED_THE_HALT`
- Record the start date, any stops and their causes in `docs/STATUS.md`.
