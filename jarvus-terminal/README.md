# Jarvus

One window for a fleet of **311 trading bots** and the **brain** that checks every trade they want to
make. The bots run **150 strategies** on crypto and US/Canadian stocks with **paper money** at live
prices, start by themselves and decide everything on their own. **Real money is off** until you
connect a broker, set your limits and type an acknowledgement in the app.

```
python3 run.py
```

Python 3.9+ and an internet connection. No pip, no API keys needed for paper trading.

| You have | Do this |
|---|---|
| **Windows, no Python** | Double-click `JarvusTerminal.exe`. It opens the app in your browser and keeps a console window open; closing that window stops Jarvus and the bots. |
| Windows with Python | Double-click `Jarvus Terminal.bat` |
| Mac | Double-click `Jarvus Terminal.command` (the first time: right-click, **Open**) |
| Linux | `./jarvus-terminal.sh` |

**About the Windows warning.** The exe is not code-signed, so Windows SmartScreen may say "Windows
protected your PC". Click **More info**, then **Run anyway**.

## The seven pages

| Page | What it shows |
|---|---|
| **Command** | The live view: paper wallet (set the balance to any amount, any time), price chart and order book, the #1 bot, the hive of all 296 bots around the brain, P&L, recent trades and the execution log of every brain decision. |
| **Bots** | Every bot, its state and last decision. Click one to see the exact rules, indicator values and checks behind what it did; disable or enable it. |
| **Brain** | How every entry is decided (cost gate → volatility gate → learned score → bench and size), live gate readings for every market, what refused trades would have made, what it has learned, calibration and its own insights. |
| **Strategies** | The library: 409 strategies (150 the bots run, 259 research-only), with exact rules, sources, how each fails and its measured results after costs. |
| **Results** | Everything measured: whole-system simulations at each fee level, the swing lab (5.5 years of hourly data), 14,672 strategy backtests with a correction for how many ideas were tried, and the volatility gate's accuracy. |
| **Live money** | Connect Kraken, NDAX or Alpaca; see which bots have earned real money; arm or disarm real-money trading. |
| **Settings** | Your exchange's fees, paper balance, autopilot (start/stop the bots), pause, emergency stop, system health, data feeds and alerts. |

## How the bots decide

Each bot runs one strategy on one market: exact entry rules, a stop, a target or exit rule, a time
limit and its own sizing. Before any entry, the **brain** checks it:

1. **Cost gate.** Fees and spread as a share of the stop ("cost in R"). Above 0.33R the trade is
   refused; 0.20-0.33R trades at half size. This single rule is why most signals are refused at
   retail crypto fees: a tight stop plus a 0.8% taker fee costs more than the setup is worth.
2. **Volatility gate.** A model trained on 5 years of hourly data forecasts whether the next hours
   will be LOUD or QUIET. QUIET: no new trades. LOUD: 0.6x size. It says how much, never which way.
3. **Learned score.** Expected R per trade from each strategy's tested history, updated with every
   closed paper trade, by market and market regime. A negative edge is refused.
4. **Bench and size.** Bots that keep losing are benched until their shadow trades recover.

Every refused trade is followed to its exit as a "shadow", so the brain learns from what it blocked.
Everything is local statistics: no AI service, no per-tick model calls.

**Your fees (Settings).** Fees decide most results, so tell Jarvus which exchange you trade crypto on
(Coinbase, Kraken, NDAX, a low-fee exchange, or each bot's own). Paper fills, the cost gate and the
brain's starting knowledge then use those fees; the brain keeps what it learns at each fee level apart.
A limit (maker) entry is counted at the maker fee.

**Swing bots.** The swing lab tested 8 hourly setups with 48 exit structures each on 5.5 years of data.
The oldest data picked the same shape almost everywhere: a 4 x ATR stop, a 2-3R target, holds of up to
96 hours and a limit entry, because that is what keeps fees small next to the risk. Three setups stayed
positive on the untouched recent data at a low-fee exchange (not significant after correction); they
run as 15 swing bots that hold through the night.

## What was measured (and what it means)

From the Results page, in plain words:

* **Whole software, 1,000 runs x 3 versions at each of 4 fee levels** (60 random bots, random 10-day
  windows, real sizing, the brain starting only with what it learned before those windows). Average
  result per window with the full brain: **-0.020%** at each bot's own exchange's fees, **-0.012%** at
  Kraken's, **+0.001%** at NDAX's (0.20%), **+0.006%** at a low-fee exchange (0.10%). Trading every
  signal instead loses 3.5% to 12% per window. The brain cuts losses by refusing trades whose costs
  exceed their edge and by sizing; at low fees it reaches about break-even. **No version makes
  meaningful money**, and the average trade is still negative at every fee level.
* **Swing lab** (5.5 years of hourly data, 8 setups x 48 exit structures): nothing survives retail
  fees; three setups stay slightly positive on the untouched recent data at a low-fee exchange; none
  is significant after correction.
* **Strategies:** 143 strategies on 917 strategy-market pairs, 1,834 hypothesis tests. **None is
  significant after correcting for the number of ideas tried.** At Kraken retail fees, 0 of 353
  crypto runs were profitable; at a low-fee venue 14 of 353; stocks 102 of 564.
* **Volatility gate:** when it flags LOUD on crypto it is right 76% of the time (base rate 31%), on
  5.8% of hours. It predicts size of move, not direction.

This is an educational research and paper-trading tool, not financial advice, and no result above
is a promise.

## Real money (off by default)

1. **Live money → Step 1:** paste an API key and secret for Kraken Pro, NDAX or Alpaca (create the
   key **without withdrawal permission**). Jarvus saves them encrypted for your Windows user (DPAPI),
   never shows them again, never logs them, and tests the connection.
2. **Step 2:** choose the broker, your limits (per trade, total, daily loss, in the broker's
   currency) and type **I UNDERSTAND THIS TRADES REAL MONEY**. The bots must be running.
3. A bot trades real money only after it has **earned it**: positive on train, validation and the
   untouched test at its venue's costs, and at least 20 paper trades with a positive average. The
   check runs before every order. You can tick "allow bots with no track record" (not recommended).

What is enforced whatever a strategy says: spot only, long only, no leverage; capped-price entries;
a protective stop **resting on the exchange** after every fill (if it cannot be placed, the position
is sold at once); a lost response is resolved by the order's client id, never by resending; a
daily-loss breach, a failed reconciliation or an unexpected broker error **disarms** live trading.
Emergency stop also disarms. **Disarm now** always works, even with the bots stopped.

## Autopilot

The bots start with Jarvus and restart by themselves within a minute if they ever stop (up to 5
times an hour). Only **Settings → Stop bots** turns them off; **Start bots** turns them back on.
Updates to Jarvus keep what the brain has learned and the paper account.

## Where things are

* Your data (the bots' database, autopilot state): `data/` beside the program.
* Broker keys: Windows DPAPI-encrypted store in `%APPDATA%\mab\secrets.json` (Windows); elsewhere the
  OS keyring or an owner-only file.
* The app listens on `http://127.0.0.1:8787` only (this computer). Every change must come from the
  app's own page (Host and Origin checks plus an app header).

`python3 run.py selftest` checks the install offline (library, bots, models, every route, the
protections, paper balance and broker validation).

## For developers

* `server.py`: the app's page and API; fleet data is proxied from the running fleet or read from its
  database when stopped.
* `engine/fleet.py`: starts and watches the fleet process (autopilot), commands, brokers, results.
* `web/`: `index.html`, `app.css`, `app.js` (no framework, no build step).
* The bots, brain, gates, brokers and live executor live in `../market_analysis_bots/mab`; the
  strategy library in `../strategies`.
