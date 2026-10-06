# Daily paper-trading schedule (Phase 3)

Paper trading only. Nothing here can place a real order. The owner approves the schedule
before it is switched on.

## What runs, and when

| When (Mountain Time) | What | Command |
|---|---|---|
| Weekdays 3:30 PM (after the US close at 2:00 PM MT, once the daily bars are final) | Fetch, export, one paper cycle, watchdog | `python -m quantagents --config config/my_universe.yaml daily --yahoo SPY EFA EEM TLT IEF GLD DBC VNQ --out data/prices.csv` |
| Weekdays 4:30 PM | A second, independent watchdog | `python scripts/watchdog.py --data data/prices.csv` |

What each part does:
- **daily:**
  - Downloads a fresh snapshot. The append-only store keeps every old one.
  - Writes the CSV and its caveats.
  - Runs the cycle only if there is a trading day the last cycle has not seen, so a holiday
    or a second run the same day is skipped.
  - Then runs the watchdog. Everything is also written to `runs/daily.log`.
- **watchdog:** engages the kill switch if a cycle has not run for more than 2 weekdays, if the
  newest bar is more than 3 weekdays old, or if a state file cannot be read. It never resets
  the switch.
- **To resume after a stop:** read `runs/daily.log`, fix the cause, then
  `python -m quantagents killswitch reset --confirm I_REVIEWED_THE_HALT`.

## Before the first run

1. `python -m pip install -e ".[dev,data]"` and `python scripts/check.py` (all gates green).
2. Copy `config/us_etfs.example.yaml` to `config/my_universe.yaml` and set your symbols. Only
   the universe changes; every risk limit keeps its default.
3. Run the daily command once by hand and read the report. Check that `data health` is 100 and
   that `blocked` is `none`.

## Windows (Task Scheduler)

1. Open Task Scheduler and choose Create Basic Task. Name it `QuantAgents daily`.
2. Trigger: Weekly, Monday to Friday, at 3:30 PM.
3. Action: Start a program.
   - Program: the full path to `python.exe` in your virtual environment, for example
     `C:\Users\you\quant-agents-50\.venv\Scripts\python.exe`.
   - Arguments: `-m quantagents --config config/my_universe.yaml daily --yahoo SPY EFA EEM TLT IEF GLD DBC VNQ --out data/prices.csv`.
   - Start in: the project folder, for example `C:\Users\you\quant-agents-50`.
4. Repeat for `QuantAgents watchdog` at 4:30 PM:
   - Arguments: `scripts\watchdog.py --data data/prices.csv`.
   - Same Start in folder.
5. In each task's properties, tick "Run whether user is logged on or not". The PC must be on
   at that time.

## macOS / Linux (cron)

`crontab -e`, then (times in your machine's local time; this example is Mountain Time):

```
30 15 * * 1-5  cd ~/quant-agents-50 && .venv/bin/python -m quantagents --config config/my_universe.yaml daily --yahoo SPY EFA EEM TLT IEF GLD DBC VNQ --out data/prices.csv
30 16 * * 1-5  cd ~/quant-agents-50 && .venv/bin/python scripts/watchdog.py --data data/prices.csv
```

## The 30-day paper run (Phase 3 acceptance)

- 30 trading days with zero A49 breaches and no reconciliation break. This needs real
  calendar time: about six weeks.
- Each day, glance at the end of `runs/daily.log`. Each week, test the kill switch by hand:
  1. `python -m quantagents killswitch engage --reason "weekly test"`
  2. `python -m quantagents killswitch status`
  3. `python -m quantagents killswitch reset --confirm I_REVIEWED_THE_HALT`
- Record the start date, any stops and their causes in `docs/STATUS.md`.
