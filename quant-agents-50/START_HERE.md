# Start here: QuantAgents-50 (version 0.7.0)

A 25-agent research and trading system. It decides once a day, after the market closes, using
real prices.

- **It starts in paper trading:** a practice account of 10,000 CAD, no real money.
- **Real money is built in but switched off.** Only you can switch it on, in 8 steps of your
  own. It works for crypto on Kraken only; see `docs/REAL_MONEY.md`.

## The simple way: one file, one menu

### Windows

1. **Install Python 3.11 or newer** from python.org. On the first install screen, tick
   **"Add python.exe to PATH"**.
2. **Unzip** this folder somewhere simple, for example `C:\QuantAgents-50`.
3. **Double-click `QuantAgents.bat`.**
   - The first time, it installs everything (5 to 10 minutes, needs the internet) and checks
     itself.
   - Then it opens the menu. Every later double-click goes straight to the menu.

### macOS / Linux

Same idea: open a terminal in the folder and run `bash QuantAgents.sh`.

### The menu

```
   1  Run today's paper trading day now
   2  Show the full dashboard
   3  Turn the automatic daily run ON
   4  Turn the automatic daily run OFF
   5  STOP all trading now (kill switch)
   6  Resume trading after a stop
   7  Change my symbols (opens the settings file)
   8  Real money: what is still needed
   9  Real money: preview the real orders (sends nothing)
  10  Real money: send a tiny test order (cancelled at once)
  11  Check the install
  12  Bring over my account from an older QuantAgents folder
   0  Quit
```

**Your first day:**
1. Choose **1**: it downloads prices and runs one paper day. You should see `cycle (exit 0)`
   and `Watchdog: all clear.`
2. Choose **3**: the daily run now starts by itself, Monday to Friday at 3:30 PM (crypto
   folders: every day at 7:00 PM).
   - It also runs on battery.
   - If the computer was off or asleep at that time, it runs as soon as you are back.
   - Stay signed in to Windows.
3. Choose **2** any time to see:
   - the account and the kill switch;
   - the last decision and your progress toward 30 paper days;
   - the **scoreboard**: the paper account against simply holding the same symbols.

That is all. You can close the window; the automatic run keeps working without it.

## What it does

- **Every trading day after the close:**
  - downloads fresh daily prices (free, no account or key needed);
  - checks the data for gaps, stale prices and unadjusted splits;
  - lets 25 agents vote;
  - sizes any trade under strict risk limits;
  - records everything in the paper account.
- **A watchdog** stops trading if anything goes stale. Only you can restart it (menu choice 6).
- **The research tools** test strategies honestly. So far no strategy has beaten simply holding
  the same funds (`docs/research/grid-2026-10-06.md`: 7,668 backtests).

## Phone alerts (optional)

Make a Telegram bot with @BotFather, then put `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` in a
`.env` file in this folder (copy `.env.example`). After every daily run your phone gets one
line:
- "Daily run OK: ..." with the day's result;
- "Daily run FAILED: ..." if something broke, so you know the same day.

## Updating to a new version

1. Unzip the new version into a **new** folder, for example `C:\QuantAgents-50-v2`.
2. Double-click its `QuantAgents.bat`.
3. Choose **12** and type the path of your old folder.

It copies your account, decision records, prices, settings and `.env` (never shown). Then:
- the old folder's kill switch is engaged, so it can never trade twice;
- its automatic run is turned off; choose **3** to turn it on in the new folder.

Approvals are not copied: real money needs your dated approval row again (a new version
deserves a fresh look).

## Your symbols

The default is 8 US-listed ETFs. Menu choice **7** opens the settings file
(`config\my_universe.yaml`):
- **Toronto listings** end in `.TO` (for example `XIC.TO`).
- **Crypto from Kraken** is written `BTC-CAD.KRAKEN`.
- **One folder holds one paper account.** For crypto, unzip a second copy into another folder
  (for example `C:\QuantAgents-Crypto`) and copy `config\crypto.example.yaml` over its
  `config\my_universe.yaml`. Crypto trades on weekends; stocks do not.

## Real money

Read `docs/REAL_MONEY.md` before anything else. In short:
- It copies the paper account's decisions onto your Kraken account, scaled to a small budget
  you set.
- Every safety rule is in code. Any problem stops everything.
- It cannot withdraw money.
- It needs 8 steps that only you can do: keys, settings, the approval phrase and your signed
  row in `docs/STATUS.md`.
- Menu choice 8 shows which steps are still missing.
- Paper-trade the crypto folder for 30 days first.

## Still there, for those who like them

| File or command | What it does |
|---|---|
| `setup.bat` / `bash setup.sh` | The install (QuantAgents.bat runs it for you the first time) |
| `daily.bat` / `bash daily.sh` | One daily run (what the automatic run starts) |
| `status.bat` / `bash status.sh` | The dashboard |
| `python -m quantagents --help` | Every command (Windows: `.venv\Scripts\python -m quantagents --help`) |
| `python -m quantagents live check` | The real-money gates, one per line |

## Where things are

| Path | What is there |
|---|---|
| `docs/REAL_MONEY.md` | How real money works and the 8 steps to switch it on |
| `docs/STATUS.md` | What is built, every test result, your approvals |
| `docs/schedule.md` | The daily schedule, by hand, and how to stop and resume |
| `docs/research/` | Every strategy test, failures included, and the trial log |
| `config/my_universe.yaml` | Your settings and symbols (created on the first run) |
| `state/`, `runs/`, `data/` | Your accounts, decision logs and price store (created as it runs) |
| `state/backups/` | A copy of your account files after every daily run (the newest 30 days) |

## Honest limits

- The free price data has two flaws, and every result says so:
  - it is "survivorship-biased": funds that closed are missing;
  - it is "not point-in-time": old prices can be restated later.
- Paper results are not real results. Real fills, fees, taxes and your own decisions will
  differ.
- No strategy here has passed the promotion tests. "No edge found" is the honest result so far.
- The real-money part was tested against a fake exchange, not against a real account.
- Not financial advice.
