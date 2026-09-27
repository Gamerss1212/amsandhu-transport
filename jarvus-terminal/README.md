# Jarvus Terminal

A local trading terminal that scans **every liquid crypto market and the most active US
stocks**, runs **95 strategies against each of them at once**, ranks what is most likely to
move, builds a costed plan, and **grades its own predictions** so the confidence it shows
you is measured rather than claimed.

It has **seven trading bots that run themselves**, a **Brain** of 120 agents that votes on
every trade they consider, and a **Learn trading** tab: a course plus an encyclopedia of
every strategy with its measured results on crypto and stocks. Press **Run bots** once and
the bots scan, backtest, buy, manage and sell on their own, around the clock, with
practice money at live prices. See **The bots** and **The Brain**, below.

```
python3 run.py
```

That is the whole install. Python 3.8+ and an internet connection. No pip, no node,
no API keys, no account.

### Other ways to start it

| You have | Do this |
|---|---|
| **Windows, no Python** | Double-click `JarvusTerminal.exe`. It opens the app in your browser and keeps a console window open. Closing that window stops Jarvus. |
| Windows with Python | Double-click `Jarvus Terminal.bat` |
| Mac | Double-click `Jarvus Terminal.command`. The first time, right-click it and choose **Open**. |
| Linux | `./jarvus-terminal.sh` |

**About the Windows warning.** The exe is not code-signed, because signing costs money
and needs a registered company. So the first time you run it, Windows SmartScreen will say
*"Windows protected your PC"*. Click **More info**, then **Run anyway**. Some antivirus
programs also flag any unsigned exe built with PyInstaller. If yours deletes it, use the
`.bat` launcher with Python installed from python.org. It runs the same code.

The exe keeps its data (database, settings, cached candles) in a `data` folder next to
itself, so move the exe and its `data` folder together. To add your own strategies to
the exe, make a `strategies` folder next to it and drop `.py` files in.

**Rebuilding the exe yourself** (on Windows, with Python 3.8+):

```
pip install pyinstaller
pyinstaller --noconfirm jarvus.spec
```

The result is `dist\JarvusTerminal.exe`.

---

## Start here: what this can and cannot do

You will get more out of this if these four things are clear before you open it.

**It cannot tell you which way a market will go.** Direction on short horizons is close
to unforecastable. A 77-feature model trained on 67,585 hours of Bitcoin data reached
AUC 0.513 on direction, where 0.500 is a coin flip. The same model asking "will the next
twelve hours be a big move" reached 0.716. So this app forecasts **movement**, not
direction, because that is the question that has an answer.

**Most strategies are worse than not thinking.** This is not an opinion, it is what the
Research tab measured on your own data. A control that buys every twelfth bar with no
analysis at all returned **+0.189R** out of sample over 12 markets, because the period
was a bull market and everything long made money. Of 64 real strategies, **13 beat it.**
The other 51 were measuring the weather. That is why every ranking here is by *excess
over the control* rather than by raw return.

**The bots trade practice money, not your money.** They are fully automatic: nobody
has to press anything after Run. Every fill uses the live price, the real fee for your fee
tier and realistic slippage, so their record is a fair preview of what real money would
have done. There is no connection to a real exchange account. The reason is in the
numbers: taken on their own, the strategies here lose money after fees, and the filter
that makes the bots positive in testing has not yet been proven forward on your screen.
Let the practice record reach the readiness bar first. See **Real money**, below.

**Nobody can promise you profits, and anything that does is selling something.** What
this gives you is a way to look at 1,700 markets in six seconds, a measured opinion about
which are about to move, a plan whose loss is defined before you enter, and an honest
scoreboard. That is a real edge over trading on vibes. It is not a money printer.

---

## The bots

Open the app, stay on the **Bots** tab, press **Run bots**. That is the whole job.

| Bot | Playbook |
|---|---|
| **Trend Rider** | Buys pullbacks and continuations in markets already trending up, when two of its 19 trend strategies agree. |
| **Breakout Hunter** | Waits for a market to coil or start moving hard (LOUD or COILED only), then buys the break when two of its 17 breakout strategies fire. |
| **Dip Buyer** | Buys sharp oversold dips in markets whose bigger trend is not down, including the Connors high-win-rate rules. |
| **Momentum** | Buys when momentum turns up and two of its 10 momentum strategies agree. |
| **Smart Money** | Liquidity sweeps, order blocks, fair-value gaps, candlestick reversals, flags and volume absorption. |
| **Day Trader** | Trades the daily rhythm: opening-range breakouts, VWAP reclaims and pullbacks, gap-and-go, prior-day level reclaims and pivot bounces. |
| **Swarm Captain** | Only trades when three different strategy families agree at once. |

Each bot has its own share of the practice money (default $10,000 split seven ways) and
its own record, so you can see which playbooks earn their keep.

**What happens without you**

* **Every 5 minutes** they scan every liquid market (about 1,700), analyse the top 40,
  and run all 66 strategies on each: 2,680 checks per scan. Each bot picks out the
  setups that match its playbook.
* **Before any trade** the bot backtests the strategies that fired on *that coin's last
  1,500 hours*, using the exact exits it will trade with, and buys only if they made at
  least **+0.15R per trade over 12+ trades there and beat random buying**. Each buy is
  logged with its reason, e.g. *"supertrend_adx made +0.74R per trade over 17 trades
  (71% winners) vs random buying at +0.48R."*
* **Every 15 seconds** they check every open trade against the live price and sell at
  the stop (4 x ATR below entry), the target (2R) or the time limit (96 hours).
* **After every closed trade** they learn: a strategy that keeps losing for them is
  benched, a coin that keeps losing is avoided, and a bot on a losing run cuts its own
  risk to a half or a quarter. Learning only ever makes them more careful.
* **Every 24 hours** they re-run the full research backtest in the background, so the
  strategy weights keep up with the market.
* **They survive restarts.** If the app or the computer restarts, the bots resume on
  their own and pick up every open trade where they left it.

**Safety rails, all on by default:** 1% of the bot's money at risk per trade, at most 3
open trades per bot and 2 bots per coin, 6 new trades per bot per day, a 4% daily loss
limit per bot, a 12-hour cooling-off after 4 losses in a row, a fee gate that refuses any
trade where fees would eat more than 20% of the risk, and a hard ceiling of 3% risk per
trade that no setting can exceed.

**Why these defaults.** Every one comes from a walk-forward test on 15 markets x 3,300
hours, where each decision could only see data from before it:

| What was tested | Result |
|---|---|
| Taking every strategy signal | Lost money after fees in every exit style tried. No better than buying at random. |
| Holding 24 hours or less (true day trading) | Lost money even with the filter. Fees and forced exits cut the winners. |
| Holding up to 4 days, 4 x ATR stop, 2R target | The best of seven exit styles tested. |
| The bots' full rule (fee gate + recent edge on that coin + beats random), 10bps slippage | **+0.22R per trade over 675 trades.** Positive in all three test windows: +0.15R while prices fell (random buying: -0.26R), +0.27R and +0.19R while they rose (random: +0.21R and +0.17R). |

**Read that last row carefully.** The rule beat random buying in every window, clearly
when the market fell and narrowly when it rose. **Its edge came mostly from volatile small
coins (+0.30R per trade); on BTC, ETH and SOL-type majors it made only +0.07R** and lost
money in the latest window. It is one 75-day period on 15 markets that were picked while
they were busy, which likely flatters the small coins. In money terms, +0.22R on a trade
risking $16.67 is about $3.70. It is a real, measured edge, not a money printer. The
practice record on the Bots tab is how you find out whether it holds from here.

---

## Stocks

The app trades the 40 most liquid US stocks and ETFs as well as crypto (edit
`STOCK_WATCHLIST` in `config.py`; any Yahoo ticker works). Data comes from Yahoo Finance's
public chart API, with no key and no account.

* **Market hours.** Stocks are only bought during the regular session, 9:30 to 16:00 New
  York time. A stop resting overnight fills at the next open if the stock gaps through it,
  which is how it fills in real life.
* **Costs.** Most brokers charge no commission on US stocks, so the practice broker
  charges half a basis point for regulatory fees plus liquidity-scaled slippage. That is
  roughly fifty times cheaper than a crypto taker trade, and it matters: see lesson 6 in
  Learn trading.
* **Day trading or not.** Stock trades are held up to four days by default. Measured on
  30 stocks over two years, the same entries closed by the bell like a true day trade
  were break-even at best even with no commission (random entries: -0.01R; best
  strategy: +0.01R), while holding up to four days let the best strategies reach
  +0.07R to +0.13R per trade. The day-trade exit is still available: tick *Stocks: out
  by the close* in Bot settings on the Bots tab.
* **Research** runs separately for crypto and stocks, each with its own costs, and the
  bots use the latest weights for each.

---

## The Brain

The bots already require every trade to pass a backtest on that market. The Brain is a
second opinion that looks at everything at once.

**120 agents.** One per strategy (95), reading how strongly its pattern is present, and 25
context agents reading what strategies do not: volatility and whether it is expanding or
compressing, trend on three horizons, how stretched price is, momentum, volume, fees as a
share of the risk, time of day, weekends, the overnight gap, price against session VWAP,
how many strategies and families agree, the verification backtest's measured edge on that
market, and what the leader is doing (Bitcoin for crypto, the S&P 500 for stocks).

**One coordinator.** A ridge regression per market type turns the 120 readings into a
single prediction: the trade's expected result in R, after fees. It was trained on every
hourly bar of the study where any strategy fired, each one recorded with every agent's
reading and how a trade taken there actually ended. It is deliberately simple. With a few
hundred thousand noisy examples, a model that can bend into any shape memorises the
noise, and a regularised linear model can only learn "this agent tends to help, that one
tends to hurt, by this much", which is what can be learned reliably here. Every prediction
comes with its reasons, agent by agent.

**How it is used.** In the default *veto* mode, a setup that has passed its bot's backtest
is only traded if the Brain also predicts a profit. Every vote, with its reasons, appears on
the Brain tab. Switch the Brain to *rank only* or *off* there.

**It keeps learning.** Every trade the bots close nudges the weights of the agents that
were active in it toward what really happened. The learned weights are saved beside the
app and survive restarts.

**What it measured.** Trained on the first 60% of each market's history (45 markets,
about 190,000 moments), judged on the last 40%, which it never saw:

| Unseen test period | Moments | Win rate | Avg per trade |
|---|---|---|---|
| Crypto: the bots' backtest rule alone | 2,782 | 46.6% | +0.18R |
| **Crypto: the rule, minus the Brain's most pessimistic 20%** | **1,010** | **55.5%** | **+0.39R** |
| Stocks: the bots' backtest rule alone | 25,675 | 49.1% | -0.00R |
| Stocks: the rule, minus the Brain's vetoes | no cut-off helped | | |

On crypto the Brain learned something small but real (correlation with the outcome
+0.06 on unseen data), mostly how to recognise the trades most likely to lose, and vetoing
them roughly doubled the rule's average result. The 20% cut-off was chosen on a separate
validation period, not on the test. These are overlapping hourly moments rather than
separate trades, the test period was a rising market, and the veto cuts trading to about
a third, so read it as "a real improvement in selection", not as a promise.

On stocks it showed no skill at all (correlation -0.002). So it **abstains on stocks**: it
never blocks or reorders a stock trade. More agents and more data do not create an edge
where the market does not offer one.

---

## What it does

**Scans everything.** One pass discovers ~1,700 crypto markets across OKX spot, OKX perps
and Coinbase, plus 40 of the most liquid US stocks and ETFs from Yahoo Finance (no key),
filters to those clearing a liquidity floor, collapses the same asset listed on several
venues, and ranks what is left. The top 40 crypto markets and the top 15 stocks get the
full analysis. Stocks are ranked only against other stocks, so crypto's bigger daily
swings never crowd them out.

**Runs 95 strategies on every market, concurrently.** 97 strategy checks (95 plus two
controls) × 55 markets is **over 5,300 independent evaluations per scan**, and the Brain's
120 agents then read every setup that survives. That is what "analyses thousands of
possibilities" means here: a real count of real evaluations.

**Refuses to double-count.** Ninety-five opinions are worthless added up, because a dozen
of these strategies are different spellings of "price is above a rising average". Votes
are grouped into families first, each family gets one weighted say, and agreement across
*different* families is the only kind counted.

**Weights each vote by what it has actually earned.** A research run backtests every
strategy against every market over deep history, splits the period in two, and judges each
strategy only on the half it was not built on — minus the control. Strategies that beat
the control get more say. Strategies that did not get **zero**, market by market.

**Costs every idea before recommending it.** Cost in R is the round trip divided by the
stop distance. Above 33% of your risk budget the trade is refused. Change the fee tier in
the header and watch plans appear and vanish; that one control moves results more than any
indicator.

**Reads real news.** Five public RSS desks, matched to the assets on screen by ticker and
by name, with words that historically precede violent repricing flagged.

**Grades itself.** Every scan writes its claims to SQLite *before* the outcome is known,
with the threshold that will later decide whether each claim was right.

---

## Indicators

Thirty-six indicators, implemented from their formulas and computed locally from exchange
candles. Supertrend, Ichimoku, ADX/DMI, Keltner, Bollinger, TTM squeeze, Stochastic,
Stochastic RSI, RSI, MACD, CCI, Williams %R, MFI, CMF, OBV, Force Index, Elder Ray,
Parabolic SAR, Donchian, Aroon, Vortex, TRIX, ROC, Awesome Oscillator, Ultimate
Oscillator, Choppiness, ATR, VWAP with standard-deviation bands, HMA, DEMA, TEMA, WMA,
SMA, EMA, linear-regression channel, ZigZag, pivot points and Fibonacci levels.

Pick up to four to overlay on the Detail chart from Settings.

**On "any TradingView indicator":** the standard library above is the real thing, same
formulas. What cannot be imported is somebody's closed-source Pine script, because that
code is not public. If you have the Pine source, these are the building blocks to port it
with, and `engine/strategies/custom/` is where it goes.

---

## Strategies

Ninety-five built-in strategies plus two controls, in seven families: trend (19),
breakout (17), price action and structure (16), mean reversion (15), momentum (10),
**session (10)** and volume (8).

The newest 31 are the setups professional day traders are known for:

* **Session:** opening-range breakout and its retest, VWAP reclaim, VWAP trend-day
  pullback, gap-and-go, gap-down reclaim, first-hour momentum, prior-day-low reclaim
  (turtle soup), floor-trader pivot bounce, inside-day breakout. These read a session
  table that knows each bar's trading day: the opening range (the first hour of a stock
  session, 00:00-08:00 UTC on crypto), running VWAP, the overnight gap and yesterday's
  high, low and close. It works on stocks' 9:30-16:00 sessions and crypto's 24-hour day
  alike, and never looks ahead.
* **Price action:** bullish engulfing, hammer, morning star, three white soldiers,
  outside-bar reversal, bull flag, the Fibonacci golden pocket, pin bar at the 21/50 EMA.
* **Quant classics:** Larry Connors' high-win-rate rules: IBS, Double 7s, Connors RSI,
  cumulative RSI(2), three lower lows.
* **Trend and momentum:** Kaufman's adaptive average, Heikin-Ashi flips, MACD zero-line
  cross, +DI/-DI cross, Keltner breakout, the 9/21 EMA cross.
* **Volume:** selling-climax reversal, anchored-VWAP bounce.

Every one of them was measured on crypto and on stocks before shipping; the results are in
the Learn trading tab.

Turn any of them off on the Swarm tab. **Add your own by dropping a `.py` file in
`engine/strategies/custom/`** — there is a commented worked example in that folder. A
strategy is about fifteen lines:

```python
from engine.strategies import Ctx, Signal, strategy

@strategy("my_setup", "breakout", "Supertrend up and a squeeze just released")
def my_setup(c: Ctx):
    line, direction = c.ind("supertrend", period=10, multiplier=3.0)
    if c.last(direction) != 1:
        return None
    return Signal(direction="long", strength=0.75,
                  reason="squeeze released with the trend",
                  stop_hint=c.last(line))
```

It is picked up on the next run, appears in the swarm, and gets backtested and weighted
alongside everything else.

---

## The self-learning loop

Two loops run, and both mean "change how much to believe something" rather than "invent an
edge".

**Calibration.** The volatility gate emits a score, which is arbitrary until proven. Every
score is written down before the outcome, graded when its horizon passes, and turned into a
reliability curve: of the times this app said 0.8, how often did a big move follow? After
enough samples it shows that measured rate instead of its own raw score.

**Weighting.** A research run measures all 67 strategies on all markets out of sample and
sets each strategy's voting weight from the result, minus the control. Re-run it monthly:
edges decay, regimes change, and a weight from last quarter is a claim about last quarter.

**What will never be learned is direction**, and the Learning tab proves it by leaving the
direction row visible. Expect roughly 50%. That number is the honesty check, not a target.

---

## Automation

The bots (above) are the automation most people want: they scan, trade, manage and learn
on their own. Running them also fires your alert rules and grades predictions, so there is
nothing else to switch on.

The older scheduler on the Alerts tab is still there if you want scanning and alerts
without any trading. While it runs the app rescans every market, fires any alert rule
that matches, marks open Portfolio positions to market, closes anything through its stop
or target, and grades predictions whose horizon has passed.

Alert rules combine heat, gate state, consensus, family agreement, verdict, cost and
volume, each with a cooldown so a market sitting just over a threshold does not fire
every cycle.

Neither the scheduler nor the bots ever touch a real exchange account.

---

## Real money

The Portfolio tab is paper trading with **real prices, real fees, real slippage and real
position sizing**, so the record it produces is a fair prediction of what real money would
have done. A 2R target pays about 1.85R once fees are charged, and the book shows you that
rather than the number the plan hoped for.

`readiness()` then answers the only question that matters, with six checks that must all
pass:

| Check | Why |
|---|---|
| At least 50 closed trades | Under 50 the expectancy is noise. A losing system routinely shows a profit over 20. |
| Positive expectancy after fees | Fees are already included. If it is negative, size is not the problem. |
| Profit factor above 1.2 | Below this the edge is inside the noise band and a normal losing streak erases it. |
| Max drawdown under 20% | Assume the real one is worse, because paper does not panic. |
| Average win larger than average loss | Otherwise you are relying on a high hit rate, which does not survive a bad week. |
| Fees under a third of gross profit | If fees eat a third, the venue is the problem and a better fee tier beats a better strategy. |

The Bots tab runs the same six checks on everything the bots have closed.

When all six pass, going live is a matter of placing the orders yourself from the plan the
app prints, at a quarter of the size the maths allows, because live execution and live
emotions are both worse than paper. Keeping a human at the point where money moves is the
feature, not the limitation.

---

## Customising it

Everything below is in the Settings drawer and persists to both the browser and the server.

- **Theme** light, dark or match system. **Accent** blue, violet, aqua or magenta — each
  checked against the LOUD orange for colour-vision deficiency in both themes. Green was
  offered and dropped because it failed the check.
- **Density** compact, normal or roomy. **Text size** 12 to 18px.
- **Columns** choose from 16, reorder them, and the table follows.
- **Panels** hide the tiles, the explainer, the how-to card or the sparklines.
- **Filters** search, minimum heat, gate state, verdict, minimum volume; sort by any
  column; **save the whole combination as a named view** and switch between them.
- **Chart indicators** pick up to four of the 36 to overlay.
- **Risk model** stop width in ATR and target in R.
- **Strategies** enable or disable any of the 67 on the Swarm tab.

---

## The screens

| Tab | What it is for |
|---|---|
| **Bots** | The Run button, seven bot cards with what each is doing right now, open trades with live P&L, the activity feed, what they have learned, and the readiness checks. |
| **Brain** | The 120 agents and how much the coordinator trusts each, its results on data it never saw, and every vote it casts with its reasons. |
| **Learn trading** | A nine-lesson course built from this app's own measurements, and an encyclopedia of all 95 strategies with their results on crypto, stocks and stock day trades. |
| **Markets** | Every liquid market ranked by heat, with family agreement, consensus, cost and verdict. |
| **Detail** | TradingView chart, local price and volume with your indicator overlays, why the gate reads what it does, the costed plan, every strategy that fired and its weight. |
| **Swarm** | The whole grid, plus the strategy roster with on/off switches. |
| **Research** | Run the backtest grid; leaderboard ranked by excess over the control. |
| **Portfolio** | Paper books with real accounting, equity curve, and the readiness gate. |
| **Alerts** | Rules, fired alerts, and the automation switch. |
| **News** | Live headlines with hot-word flags. |
| **Calibration** | The reliability curve and the direction reality check. |

---

## Commands

```
python3 run.py                    # the dashboard (default)
python3 run.py --port 9000        # a different port
python3 run.py scan -n 20         # one scan, printed here
python3 run.py resolve            # grade predictions past their horizon
python3 run.py learn              # measured calibration as JSON
python3 run.py selftest           # verify the install (83 checks)
```

Environment overrides: `JARVUS_PORT`, `JARVUS_DEEP_N`, `JARVUS_FEE_TIER`, `JARVUS_ACCOUNT`,
`JARVUS_MIN_VOL`, `JARVUS_DB`, `JARVUS_DATA` (the data folder). Everything else is in `config.py`.

---

## Layout

```
jarvus-terminal/
├── run.py / server.py / config.py / selftest.py
├── desktop.py          entry point for the Windows exe
├── jarvus.spec         PyInstaller recipe for the exe
├── Jarvus Terminal.bat / Jarvus Terminal.command / jarvus-terminal.sh   launchers
├── engine/
│   ├── universe.py     market discovery and the cheap pre-rank
│   ├── marketdata.py   candles across venues; deep paged history, disk-cached
│   ├── volgate.py      the volatility gate
│   ├── indicators.py   36 indicators and the catalog
│   ├── strategies/     registry, the session table, 95 built-ins, 2 controls, your custom folder
│   ├── swarm.py        every strategy × every market, concurrently, family-grouped
│   ├── backtest.py     walk-forward grid, control-relative weighting
│   ├── research.py     research runs, persistence, the weights the swarm uses
│   ├── analysis.py     structure, levels, confluence, the cost gate, the plan
│   ├── portfolio.py    paper books with real accounting and the readiness gate
│   ├── automation.py   scheduler and alert rules
│   ├── bots.py         the seven self-running bots: scan, verify, trade, manage, learn
│   ├── brain.py        the 120 agents and the coordinator; brain_weights.json ships trained
│   ├── stocks.py       US stocks from Yahoo Finance: quotes, candles, the market clock
│   ├── broker.py       practice-money fills at live prices, liquidity-scaled slippage
│   ├── learn.py        resolution, calibration, reliability
│   ├── news.py / store.py / scanner.py / http.py
└── web/                the dashboard; no frameworks, inline SVG charts
```

Every chart is hand-written inline SVG so the no-install promise holds all the way to the
browser. Price and volume are separate plots rather than a dual axis, because sliding two
unrelated scales against each other invents a correlation the data does not contain.

---

## Honest limits

- **Direction is not forecastable** on these horizons. The app is built around that.
- **The gate is a heuristic**, not the trained model whose numbers are quoted above. Its
  real accuracy is whatever your Learning tab measures.
- **Backtests flatter.** Fills are pessimistic and fees are charged, but the sample is one
  market regime, and 67 strategies tested at once means the best-looking one is partly luck.
- **Small samples lie.** Under 20 graded predictions the app refuses calibrated
  probabilities; under 50 journaled trades your expectancy is noise.
- **Wide stops mean small positions.** A market moving 9% an hour needs a stop far enough
  away to survive, which makes the position small. That is correct, not a bug.

Educational research tool, not financial advice. It looks and plans; you decide and click.
Crypto is volatile and most retail day traders lose money.
