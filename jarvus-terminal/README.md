# Jarvus Terminal

A local day-trading terminal that scans **every liquid crypto market**, ranks them by
how likely they are to make a big move, builds a costed plan for the ones that
qualify, pulls live news, and **grades its own predictions** so the confidence it
shows you is measured rather than asserted.

```
python3 run.py
```

That is the whole install. Python 3.8+ and an internet connection. No pip, no
node, no API keys, no account.

---

## What it actually does

**Scans everything.** One pass discovers ~1,700 markets across OKX spot, OKX perps
and Coinbase, filters to those that clear a liquidity floor, collapses the same
asset listed on several venues, and ranks what is left. The full sweep takes about
six seconds.

**Ranks by what is forecastable.** The headline list answers "which markets are
about to blow" — and it answers it with a volatility forecast, not a direction call.
That distinction is the design:

> Direction on short horizons is close to unforecastable. A 77-feature model trained
> on 67,585 hours of Bitcoin data reached AUC 0.513 on direction, where 0.500 is a
> coin flip. The same model asking "will the next 12 hours be a big move" reached
> 0.716, and "will it go dead" reached 0.747.

Volatility clusters — loud hours follow loud hours, and compression resolves into
expansion. Direction does not cluster that way. So the app ranks by expected
*movement*, tells you which of two mechanisms is driving it, and refuses to tell you
which way. That is the honest version of the question.

**Costs every idea before recommending it.** Cost in R is the round trip divided by
the stop distance. At retail fees it decides more outcomes than setup selection
does, so it is checked early rather than buried: above 33% of the risk budget, the
trade is refused outright. Switch the fee tier in the header and watch plans appear
and disappear — that single control moves results more than any indicator.

**Reads real news.** Five public RSS desks, parsed with the standard library,
matched to the assets on screen by ticker and by name. Words that have historically
preceded violent repricing are flagged as worth reading, never as a signal.

**Grades itself.** This is the part most trading software does not do.

---

## The self-learning loop

Every scan writes its claims to SQLite **before the outcome is known**, including the
threshold that will later decide whether each claim was right. After the horizon
passes, a resolver fetches what actually happened and scores them.

That ordering is the entire point. A system that records what it thought only after
seeing what happened cannot be held to account, and almost all trading software is
built that way: a signal appears, scrolls off the screen, and nobody ever checks.

The Learning tab then shows a reliability curve — of the times this app said 0.8, how
often did a big move follow? Once there are enough graded samples it stops showing its
own raw score and starts showing that measured rate instead. It learns how much to
believe itself.

**What it will not learn** is how to predict direction, and the same tab proves it.
The direction row sits there reporting how often predictions finished up. Expect
roughly 50%. That number is the honesty check, not a target.

```
python3 run.py resolve     # grade everything past its horizon
python3 run.py learn       # print what has been measured so far
```

---

## The screens

| Tab | What it is for |
|---|---|
| **Markets** | Every liquid market ranked by heat, with state, trend, cost and verdict. Click any row. |
| **Detail** | TradingView chart, locally computed price and volume, why the gate reads what it does, the costed plan, the confluence count, structure and levels, news naming that asset. |
| **News** | Live headlines with hot-word flags and per-source health. |
| **Learning** | The reliability curve, per-state hit rates, and the direction reality check. |
| **Journal** | Log a plan before the order, close it after, see expectancy in R. |

---

## Reading the heat score

Heat blends three measurements, and the Detail tab breaks any reading into its parts:

- **Energy** — how far the market actually travels per bar right now, as a share of
  price. Log-scaled, because crypto hourly ATR spans two orders of magnitude and a
  linear scale stops telling the fast markets apart.
- **Expansion** — it is speeding up: ATR rising against its own average, realised
  volatility rising, volume surging, bars widening.
- **Compression** — it is wound tight: bands at multi-day narrows, volume drained.

A market can be hot by being fast, by accelerating, or by coiling. Those imply
different trades, so they are reported separately rather than averaged away.

**The gate is a transparent heuristic, not the trained model**, so it does not inherit
that model's accuracy and the app never claims it does. What it claims is whatever the
Learning tab has measured on your own data.

---

## Commands

```
python3 run.py                    # the dashboard (default)
python3 run.py --port 9000        # a different port
python3 run.py scan -n 20         # one scan, printed in the terminal
python3 run.py resolve            # grade predictions past their horizon
python3 run.py learn              # measured calibration as JSON
python3 run.py selftest           # verify the install (37 checks)
```

Environment overrides: `JARVUS_PORT`, `JARVUS_DEEP_N`, `JARVUS_FEE_TIER`,
`JARVUS_ACCOUNT`, `JARVUS_MIN_VOL`, `JARVUS_DB`. Everything else lives in
`config.py`, which is safe to edit.

---

## Layout

```
jarvus-terminal/
├── run.py              launcher and CLI
├── server.py           stdlib HTTP server + JSON API
├── config.py           every tunable in one file
├── selftest.py         37 checks, offline where possible
├── engine/
│   ├── universe.py     market discovery and the cheap pre-rank
│   ├── marketdata.py   candles across venues, concurrent, closed bars only
│   ├── volgate.py      the volatility gate
│   ├── analysis.py     structure, levels, confluence, the cost gate, the plan
│   ├── news.py         RSS aggregation and symbol matching
│   ├── store.py        SQLite: predictions, outcomes, journal
│   ├── learn.py        resolution, calibration, reliability
│   ├── scanner.py      the orchestrator
│   ├── indicators.py   EMA, ATR, RSI, Bollinger, swings, VWAP
│   └── http.py         cached, timing-out, never-raising HTTP
└── web/                the dashboard (no frameworks, inline SVG charts)
```

Every chart is inline SVG written by hand, which keeps the no-install promise all the
way to the browser. The palette was validated for colour-vision deficiency with the
`dataviz` validator in both light and dark; state is never carried by colour alone.

---

## Honest limits

- **It cannot predict direction.** Nothing can, on these horizons. The app is built
  around that fact rather than against it.
- **The gate is a heuristic.** Its real accuracy is whatever your Learning tab says
  after enough samples, which is why the tab exists.
- **A BUY is not a forecast.** It means the structural boxes are ticked and the cost
  gate passed. Every plan carries a stop that defines the loss in advance.
- **Small samples lie.** Under 20 graded predictions the app refuses to show
  calibrated probabilities; under 50 journaled trades your expectancy is noise.
- **Wide stops mean small positions.** A market moving 9% an hour needs a stop far
  enough away to survive, which makes the position small. That is correct, not a bug.
- **TradingView** is embedded through their official widget. If your network blocks
  it the box collapses and the locally computed chart carries on.

Educational research tool, not financial advice. It looks and plans; you decide and
click. Crypto is volatile and most retail day traders lose money.
