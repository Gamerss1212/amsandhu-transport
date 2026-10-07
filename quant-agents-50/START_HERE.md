# Start here: QuantAgents-50 (version 0.9.0)

A 25-agent trading system. Once a day, after the market closes, it downloads real prices, lets
the agents decide, and trades in a **paper account**: 10,000 CAD of practice money.
**Real money** (crypto on Kraken) is built in, but stays off until you switch it on.

## Run it

1. **Install Python 3.11 or newer** from python.org. On the first screen, tick
   **"Add python.exe to PATH"**.
2. **Unzip** this folder somewhere simple, for example `C:\QuantAgents-50`.
3. **Double-click `QuantAgents.bat`** (macOS/Linux: `bash QuantAgents.sh`).
   - The first time, it installs itself (5 to 10 minutes, needs the internet).
   - Then your web browser opens QuantAgents at `http://127.0.0.1:8765`. This page lives on
     your own computer; nobody else can open it.
   - Keep the black window open while you use the page.

## Your first day

1. Press **Run today's paper day**. About a minute later the page shows the decision.
2. Press **Turn ON** in **Automatic daily run**. It now runs by itself after each market
   close, even when the page is closed:
   - stocks: Monday to Friday at 3:30 PM;
   - crypto: every day at 7:00 PM.
3. Come back any time to see the **scoreboard**: the paper account against simply holding the
   same symbols.

## The page

| Box | What you do there |
|---|---|
| **Today** | Run today's paper day |
| **Paper account** | Money, positions, scoreboard and chart |
| **Last decision** | What the agents decided, and why not |
| **Automatic daily run** | ON / OFF |
| **Stop or resume** | Red **STOP** button; resuming needs a typed phrase |
| **Your symbols** | A ready-made list, or your own |
| **Real money** | Save Kraken keys, switch ON or OFF, check, preview, test order |
| **Tools** | Install check, bring an account over from an older folder, close the app |

## Real money, in short

Read `docs/REAL_MONEY.md` first. Then:
1. Use a **separate crypto folder** (unzip a second copy, pick **Crypto on Kraken, in CAD**).
2. Let it **paper-trade for 30 days**.
3. In its **Real money** box:
   - save **trade-only Kraken keys** (withdrawals OFF);
   - type a **budget** (start about 100), your **name** and the **approval phrase**;
   - press **Switch real money ON**.
4. Press **Preview real orders** to see what it would do. **Switch real money OFF** goes back
   to paper at any time.

Every safety check stays in force:
- it trades only within your budget, with limit orders;
- it stops everything on any problem;
- it can never withdraw money.

## Updating

Unzip the new version into a new folder and open it. In **Tools**, type the old folder's path
and press **Bring it over**. Your account moves over and the old folder is stopped.

## Files

| Path | What it is |
|---|---|
| `QuantAgents.bat` / `QuantAgents.sh` | Start QuantAgents |
| `daily.bat` / `daily.sh` | One daily run (what the automatic run starts) |
| `docs/REAL_MONEY.md` | How real money works, step by step |
| `docs/schedule.md` | The daily schedule, if you want to set it by hand |
| `docs/STATUS.md` | Your approvals (QuantAgents writes your dated row when you switch real money on) |
| `config/my_universe.yaml` | Your settings (made on the first run) |
| `state/`, `runs/`, `data/` | Your accounts, decision records and prices (made as it runs) |
| `.env` | Your keys, if any (made when you save them; never share it) |

## Honest limits

- No strategy here has beaten simply holding yet. "No edge found" is the honest result so far.
- Free price data misses funds that closed, and old prices can be changed later.
- Paper results are not real results.
- Real money was tested against a fake exchange and real Kraken prices, never a real account.
- Not financial advice.
