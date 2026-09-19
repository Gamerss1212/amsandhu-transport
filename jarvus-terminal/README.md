# Jarvus Terminal

A local trading terminal that scans **every liquid crypto market**, runs **67 strategies
against each of them at once**, ranks what is most likely to move, builds a costed plan,
and **grades its own predictions** so the confidence it shows you is measured rather than
claimed.

```
python3 run.py
```

That is the whole install. Python 3.8+ and an internet connection. No pip, no node,
no API keys, no account.

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

**It will not place orders.** There is no live-trading button and this is deliberate,
for reasons the app's own numbers make plain: the strategies here have no forward-tested
record, and of the configurations tested in this project essentially none were profitable
after retail taker fees. Automating orders on an unproven edge does not make money
faster, it loses it faster with nobody watching. What the app does instead is make paper
trading arithmetically identical to real trading, then tell you honestly when that record
would justify risking money. See **Real money**, below.

**Nobody can promise you profits, and anything that does is selling something.** What
this gives you is a way to look at 1,700 markets in six seconds, a measured opinion about
which are about to move, a plan whose loss is defined before you enter, and an honest
scoreboard. That is a real edge over trading on vibes. It is not a money printer.

---

## What it does

**Scans everything.** One pass discovers ~1,700 markets across OKX spot, OKX perps and
Coinbase, filters to those clearing a liquidity floor, collapses the same asset listed on
several venues, and ranks what is left. About six seconds.

**Runs 67 strategies on every market, concurrently.** 67 strategies × 40 markets is
**2,680 independent evaluations per scan**. That is what "analyses thousands of
possibilities" means here: a real count of real evaluations.

**Refuses to double-count.** Sixty-seven opinions are worthless added up, because a dozen
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

Sixty-four built-in strategies plus two controls, drawn from the families in the
320-strategy encyclopedia: trend (12), mean reversion (10), breakout (10), momentum (8),
volatility (6), volume (6), structure and liquidity (8), composite (4).

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

Turn it on from the Alerts tab and pick an interval. While it runs the app rescans every
market, fires any alert rule that matches, marks open paper positions to market, closes
anything through its stop or target, and grades predictions whose horizon has passed.

Alert rules combine heat, gate state, consensus, family agreement, verdict, cost and
volume, each with a cooldown so a market sitting just over a threshold does not fire
every cycle.

It never sends an order.

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
| **Markets** | Every liquid market ranked by heat, with family agreement, consensus, cost and verdict. |
| **Detail** | TradingView chart, local price and volume with your indicator overlays, why the gate reads what it does, the costed plan, every strategy that fired and its weight. |
| **Swarm** | The whole grid, plus the strategy roster with on/off switches. |
| **Research** | Run the backtest grid; leaderboard ranked by excess over the control. |
| **Portfolio** | Paper books with real accounting, equity curve, and the readiness gate. |
| **Alerts** | Rules, fired alerts, and the automation switch. |
| **News** | Live headlines with hot-word flags. |
| **Learning** | The reliability curve and the direction reality check. |

---

## Commands

```
python3 run.py                    # the dashboard (default)
python3 run.py --port 9000        # a different port
python3 run.py scan -n 20         # one scan, printed here
python3 run.py resolve            # grade predictions past their horizon
python3 run.py learn              # measured calibration as JSON
python3 run.py selftest           # verify the install (68 checks)
```

Environment overrides: `JARVUS_PORT`, `JARVUS_DEEP_N`, `JARVUS_FEE_TIER`, `JARVUS_ACCOUNT`,
`JARVUS_MIN_VOL`, `JARVUS_DB`. Everything else is in `config.py`.

---

## Layout

```
jarvus-terminal/
├── run.py / server.py / config.py / selftest.py
├── engine/
│   ├── universe.py     market discovery and the cheap pre-rank
│   ├── marketdata.py   candles across venues; deep paged history, disk-cached
│   ├── volgate.py      the volatility gate
│   ├── indicators.py   36 indicators and the catalog
│   ├── strategies/     registry, 64 built-ins, 2 controls, and your custom folder
│   ├── swarm.py        every strategy × every market, concurrently, family-grouped
│   ├── backtest.py     walk-forward grid, control-relative weighting
│   ├── research.py     research runs, persistence, the weights the swarm uses
│   ├── analysis.py     structure, levels, confluence, the cost gate, the plan
│   ├── portfolio.py    paper books with real accounting and the readiness gate
│   ├── automation.py   scheduler and alert rules
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
