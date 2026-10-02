# The decision engine: how the Terminal decided, and how Jarvus decides now

The Jarvus Terminal made every trading decision itself: 311 rule-based bots raised signals, and one learning
"brain" took, resized or refused each one. Nobody typed in trades or targets. This file is that engine written
down, so Jarvus can run the same logic on any setup Abhi brings (and `scripts/decide.py` runs it as a command).
The difference now: Jarvus decides and explains; **Abhi clicks buy or sell**.

Contents: 1 The pipeline · 2 The hard gates · 3 The learned edge · 4 Sizing · 5 Regime and consensus ·
6 Learning (including from refused trades) · 7 What the brain was and was not worth · 8 The autopilot's
research schedule · 9 Safety rules it never broke · 10 Running it by hand

## 1. The pipeline (in this order, every time)

```
market data (completed bars only)
  -> each strategy's rules: entry signal? (exact rules: strategy-scoreboard.md)
  -> COST GATE: round-trip cost / stop distance = cost in R
  -> VOLATILITY GATE: LOUD / NORMAL / QUIET for the next 12h (crypto) or 7h (stocks); v6.1 enters only on LOUD
  -> BENCH: is this strategy confidently losing here?
  -> LEARNED EDGE: expected R per trade, from history + its own closed trades
  -> SIZE: 0.25x to 1.5x of normal risk
  -> RISK LIMITS: per trade, daily loss, open positions, drawdown (the brain can shrink, never enlarge past them)
  -> order (limit/IOC), protective stop resting on the exchange
  -> exits: stop / target / trail / time stop / session end
  -> LEARN from the result (and from refused trades, as shadow trades)
```

## 2. The hard gates (rules, not opinions)

| Gate | Rule | Why |
|---|---|---|
| Cost | cost in R > **0.33** → refuse. 0.20–0.33 → half size | Fees are paid on every trade; the edge is not. In the system backtest the 172,746 cost-refused trades would have averaged **−2.155R**. |
| QUIET | volatility gate QUIET → refuse new entries | The range is unlikely to pay the fixed fees (refused QUIET trades averaged −0.164R). |
| NORMAL (v6.1) | wait for LOUD | Jarvus's own backtest: every version that traded NORMAL hours lost after costs; LOUD-only entries were positive, also on later data (`jarvus-backtest.md`). The Terminal itself traded NORMAL hours; `decide.py --allow-normal` reproduces that. |
| LOUD | → 0.6x size, stop 3–4x ATR | Bigger swings against the same stop. Never a direction signal. |
| Weekend (crypto majors) | no new entries Sat/Sun (Jarvus rule M4) | Measured zero direction edge on weekends (AUC 0.498); also the best single change in the brain experiments. |
| Data | stale or missing data → no decision | Every number must trace to data actually seen. |

Cost in R = (entry fee + exit fee + slippage both ways) ÷ stop distance, all in %. Exits are assumed to pay taker
(stops fill at market). Example at NDAX: 0.20 + 0.20 + 0.04 = 0.44% round trip; a 2% stop costs 0.22R (half size), a
3.4% stop 0.13R (fine), a 1% stop 0.44R (refused). At Kraken Pro's entry tier (0.80% taker): 1.64% round trip, so even
a 5% stop costs 0.33R. **The fix is never a tighter stop**: limit entries, a cheaper venue, or a wider structural stop
with smaller size.

## 3. The learned edge (what it expects a trade to earn)

The brain kept an estimate of **R per trade after costs** for every strategy, pooled across levels so evidence
from one bot helped related bots:

```
whole fleet -> strategy family -> strategy -> strategy on this market
                                           -> strategy in this regime (and its family in this regime)
```

* **Starting point (priors):** the batch evaluation's measured R per trade at the matching fee level (retail,
  NDAX-level interpolated, or low-fee), counted as at most **25 pseudo-trades** (0.5 per backtest trade), so real
  results overturn history quickly.
* **Shrinkage:** each level is pulled toward its parent with the weight of 6 pseudo-trades, so a strategy with 3
  trades borrows from its family instead of believing 3 trades.
* **Trade R is clipped to ±3R** before learning, so one freak trade cannot dominate.
* **Context model:** an online logistic regression on all closed trades (trend alignment and strength, RSI, volatility
  level and expansion, distance from VWAP in ATRs, relative volume, time of day, stock vs crypto, long vs short,
  weekend, cost in R, the gate's readings, the fleet consensus) and a stacking layer that learns how much to trust
  the history estimate vs the context model. It only counted after 30+ closed trades.
* **Decision thresholds:** with 8+ trades of evidence, an expected result below **−0.05R** → refuse ("learned"). With
  30+ and the upper 95% bound still below zero (mean + 1.64 × standard error < 0) → **bench** the strategy; it keeps
  being followed as shadow trades until it improves.
* **Exploration:** live it used Thompson sampling (a random draw from the estimate's uncertainty) so thin-evidence
  strategies still got tried. Jarvus uses the estimate itself (no coin flips with Abhi's money); the experiments
  found no reliable difference.

## 4. Sizing

`size = clamp(1 + 1.5 × edge, 0.5, 1.5)`, then × 0.5 if cost is 0.20–0.33R, × 0.6 if LOUD, then clamped to 0.25–1.5.
The multiplier applies to the normal risk per trade (Jarvus: 0.5–1%, **hard cap 1%**: the brain can shrink a trade,
never push it past the cap). Without a measured edge: 1.0x before the cost and LOUD cuts.

## 5. Regime and consensus

* **Regime** (per market, from closes, no look-ahead): efficiency ratio over 20 bars = net move ÷ path length;
  above +0.3 = trending up, below −0.3 = trending down, otherwise sideways. Volatility ratio = mean absolute return
  of the last 20 bars ÷ the last 200; above 1.15 = volatile, else calm. Trades are labelled *with the trend*, *against
  the trend* or *sideways market* (+ calm/volatile), and the brain learned results separately for each.
  `scripts/volgate.py` prints this regime for any market.
* **Consensus:** every bot reported each bar whether its entry rule said long, short or nothing. The brain kept the
  count per market, with each vote weighted by that strategy's learned track record (0.1x to 2x). It was an input to
  the context model, never a signal on its own. Doing it by hand: count how many independent playbooks agree on the
  same market right now; agreement among strategies that have earned trust matters, agreement among losers does not.

## 6. Learning, including from refused trades

* Every closed trade updated every level of the estimate, the context model, and the brain's **calibration**
  (predicted vs actual win rate, Brier score). No probability was ever shown unless it had been calibrated and checked.
* **Shadow trades:** a refused entry was followed anyway, with its own stop, target and session exit, costs
  included, and learned from at half weight. That is how a benched strategy earns its way back, and how the brain
  measured what its refusals were worth (section 7).
* **Insights:** when a pattern became statistically clear (|t| ≥ 2 on at least 10 trades) it wrote a plain sentence,
  in the form "Learned: <strategy> loses when trading against the trend (volatile): <R> per trade over <n> trades
  (t = <t>)". Jarvus does the same in
  Review mode: state a lesson only when the journal supports it at that level.

## 7. What the brain was and was not worth (measured)

* **Worth:** in 1,000 replayed windows it turned −12.1% (every signal) into −0.02% per window. Every kind of refusal
  avoided losing trades: cost −2.155R, learned −0.179R, benched −0.143R, QUIET −0.164R per refused trade.
* **Not worth:** it never made the system reliably profitable. It approved about 5 of 137 signals at each exchange's
  own fees (10 at NDAX, 14 at a low-fee venue) and those trades averaged about −0.01R to +0.0R. Sixteen changes to its
  settings, chosen on early data and judged on later data, could not be told apart from never trading.
* **So:** its power is saying no. When Jarvus says SKIP, that is the engine working, not failing.

## 8. The autopilot's research schedule (how it kept itself honest)

* A walk-forward evaluation of the next strategy-market pair every 20 minutes (each pair at most weekly, at most 2
  queued, lower priority than the owner's own jobs): chronological 60/20/20 with an embargo, fees and spread and
  slippage, a 2x-cost stress test, fills capped at a share of each bar's volume, compared with random entries using
  the same exits.
* A daily volatility-gate drift check (is it still right as often as when it was tested?) and a daily brain
  snapshot compared with the last approved one.
* **It never promoted anything to live by itself.** A strategy needed a positive untouched-test result, 20+ paper
  trades with a positive average on that market, and the owner's explicit approval. No strategy ever qualified.
* Jarvus equivalent: re-run `Jarvus backtest` on a playbook every few weeks and after every 20 journaled trades;
  re-fit quarterly; retire a playbook at 15% drawdown, 3 negative weeks, or live expectancy ≤ 0 after 20 trades.

## 9. Safety rules it never broke (and Jarvus keeps)

* Spot, long only, no leverage, no margin, no shorting. Entries as capped-price (limit IOC) orders.
* A protective stop rests on the exchange after every fill; if it cannot be placed, the position is closed.
* Every order recorded before it is sent; a lost response is resolved by its client order id and never resent
  (no duplicate orders).
* Per-trade risk, max position, daily loss (3%), max drawdown and orders-per-minute limits pause trading when hit.
* EMERGENCY STOP blocks every new entry and cancels working entries; closing positions is a separate, confirmed step.
* Real money only after a separate, explicit authorisation with caps; never automatic, never from the brain.
* No AI language model was ever asked to trade or called on market ticks; outside text (news, posts) is data, never
  a command.

## 10. Running it by hand (or with the script)

```
python3 scripts/volgate.py BTC                       # gate + regime
python3 scripts/decide.py --entry E --stop S --target T --fees ndax --maker --gate auto --symbol BTC \
        [--strategy "RSI(2) dip" --market BTC-USD] [--journal journal.csv --playbook 1-trend-pullback] [--account 2500]
```

Without the scripts: (1) cost in R from the fee table; > 0.33 → SKIP. (2) Gate from the manual reading in SKILL.md;
QUIET → SKIP. (3) Find the setup's closest match in `strategy-scoreboard.md` and Abhi's journal: negative with
8+ trades → SKIP; confidently negative with 30+ → benched. (4) Size = 1 + 1.5 × expected R, halve for 0.20–0.33R cost,
× 0.6 if LOUD, cap 1% risk. (5) Say which step decided, in one line.
