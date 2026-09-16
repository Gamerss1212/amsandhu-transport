# Risk Management

This is the file that decides whether the user is still trading in a year. Read it
before any file about entries.

## Contents

1. The one number: risk per trade
2. Position sizing formula and examples
3. R multiples: the language of trading
4. Stop placement
5. Expectancy: the only scoreboard
6. The win-rate vs reward table
7. Daily, weekly, and concurrent risk limits
8. Drawdown math
9. Leverage, margin, and liquidation
10. Fees, funding, and slippage
11. Scaling out and moving stops
12. Kelly and why to use a quarter of it
13. Exchange, custody, and operational risk
14. Sizing checklist

---

## 1. The one number: risk per trade

Risk per trade is the amount of the account lost if the stop is hit. Not the
position size. Not the margin. The loss.

Default: **1% of account equity**. Aggressive but survivable: 0.5% while learning,
never above 2%.

Why: a strategy with a 45% win rate will regularly produce streaks of 6-8 losses.
At 1% each that is an 8% drawdown, recoverable. At 5% each it is a 34% drawdown,
and recovery needs a 52% gain on a strategy that just showed it can lose eight in
a row. The math of ruin is not symmetric.

## 2. Position sizing formula and examples

```
risk_amount      = account_equity × risk_pct
stop_distance    = |entry − stop|
position_units   = risk_amount / stop_distance
position_notional = position_units × entry
leverage_needed  = position_notional / margin_you_choose_to_post
```

`scripts/position_size.py` does this and adds fees.

**Example 1, spot BTC.** Account 10,000. Risk 1% = 100. Entry 64,200, stop 63,550.
Stop distance 650. Units = 100 / 650 = 0.1538 BTC. Notional = 9,877. Almost the
whole account in one spot position; fine on spot, the loss is still only 100 if the
stop holds.

**Example 2, SOL perp, wide stop.** Account 10,000. Risk 1% = 100. Entry 150.0,
stop 144.0 (4% away). Units = 100 / 6 = 16.67 SOL. Notional = 2,500. No leverage
needed at all. Notice that a wider stop simply means a smaller position, not a
bigger loss.

**Example 3, what leverage is for.** Same as Example 1 but the user wants to post
only 2,000 margin. Leverage = 9,877 / 2,000 = ~5x. The risk on the trade is still
100. Leverage changed the margin, not the risk. If instead the user says "I want to
use 20x on 2,000" and works out the size from the leverage (40,000 notional, 0.623
BTC), the same 650-point stop now loses 405, or 4% of the account. Sizing from
leverage instead of from the stop is how accounts die.

**Example 4, stop too tight to fit.** Account 500. Risk 1% = 5. ETH entry 3,200,
stop 3,168 (1%, 32 points). Units = 5 / 32 = 0.156 ETH, notional 500. Fine. But if
the correct structural stop were 3,120 (80 points), units = 0.0625 ETH, notional
200, and the exchange minimum is 0.01 ETH: still fine. If the exchange minimum
notional were 100 and the correctly sized trade were 40, the honest answer is
"this account cannot take this trade at 1% risk". Say that, do not widen the risk.

## 3. R multiples: the language of trading

**1R** is the risk on the trade (the distance from entry to stop, in money). Every
outcome is expressed as a multiple of it.

- A trade that hits a target twice the stop distance away is **+2R**.
- A trade stopped out is **−1R** (slightly worse with fees and slippage).
- A trade closed early at half the target is **+1R**.

Thinking in R strips out account size and coin price and lets the user compare
every trade on one scale. It also kills the "I made 800 dollars" ego trap: +0.4R
on a stupidly oversized trade is a bad trade that happened to pay.

All journal entries, reviews, and expectancy calculations in this skill are in R.

## 4. Stop placement

The stop goes where the trade idea is **provably wrong**, plus a buffer, and nowhere
else.

- **Trend pullback long**: below the higher low that the entry is betting on.
- **Range fade**: beyond the range edge, past where a sweep would go.
- **Breakout retest**: below the retest low.
- **Sweep reversal**: beyond the sweep wick.

Then add a **buffer** of 0.3-0.5 ATR (of the setup timeframe) so an ordinary wick
does not stop you out before the idea plays.

Then **sanity check**:

- Stop distance below 0.5 ATR of the setup timeframe: it is inside noise. Move to a
  lower timeframe for the entry, or widen it and accept a smaller size.
- Stop distance above ~2.5 ATR: the entry is too far from the invalidation. Wait
  for a better location.
- Does the 2R target run into a major level first? If so, the true reward is to
  that level. Recompute R:R to it.

Never widen a stop after entry. Widening converts a defined risk into an undefined
one. The only permitted stop modification is tightening.

## 5. Expectancy: the only scoreboard

```
expectancy (R per trade) = (win_rate × avg_win_R) − (loss_rate × avg_loss_R)
```

A strategy with 40% winners averaging +2.2R and 60% losers averaging −1.0R has
expectancy 0.88 − 0.60 = **+0.28R per trade**. Over 100 trades at 1% risk that is
+28% before compounding. A strategy with 65% winners averaging +0.6R and 35% losers
at −1.0R has 0.39 − 0.35 = **+0.04R**, and once fees are added it is negative.
High win rate is not the same as profitable.

Related metrics (all computed by `scripts/journal_stats.py`):

- **Profit factor** = gross wins / gross losses. Below 1.0 is losing; 1.3-1.8 is a
  solid discretionary day trader; above 2.5 over a large sample is either
  exceptional or a small sample.
- **Max drawdown (R)**: the largest peak-to-trough decline. Tells you the stomach
  required.
- **Average R** and its standard deviation: expectancy and consistency.

Sample size: expectancy measured on fewer than ~50 trades is mostly noise. Treat
the first 100 trades of any new approach as data collection at 0.5% risk.

## 6. The win-rate vs reward table

Breakeven win rate for a given average reward-to-risk (before fees):

| Avg R:R | Breakeven win rate | Comfortable win rate |
|---|---|---|
| 0.5R | 67% | 75%+ |
| 1.0R | 50% | 58%+ |
| 1.5R | 40% | 48%+ |
| 2.0R | 33% | 42%+ |
| 3.0R | 25% | 33%+ |

Day-trading setups in this skill target 2R or better and realistically win 35-50%
of the time. That is a positive-expectancy business. Scalping for 0.5R needs a
75% win rate to survive fees, which almost nobody sustains.

## 7. Daily, weekly, and concurrent risk limits

- **Max daily loss: 3R** (3% at 1% risk). Hit it and the day is over. Not "one
  more". The third loss usually means the read on the day is wrong, and the fourth
  loss is nearly always a tilt trade.
- **Max weekly loss: 6R.** Hit it, stop for the week, review the journal.
- **Max concurrent risk: 3R** across all open positions.
- **Correlated positions count as one.** Long BTC, long ETH, and long SOL at the
  same time is one 3R bet on crypto, not three 1R bets. Size accordingly.
- **After a big win** (3R+ in a day), consider stopping too. Euphoria trades are
  as expensive as tilt trades.

## 8. Drawdown math

Gain required to recover a drawdown:

| Drawdown | Gain to recover |
|---|---|
| 5% | 5.3% |
| 10% | 11.1% |
| 20% | 25% |
| 30% | 43% |
| 50% | 100% |
| 70% | 233% |

This is why risk per trade is capped and why daily limits exist. Below a 20%
drawdown a trader can grind back. Beyond 30% they usually need to change
something fundamental, and beyond 50% the account is effectively a new, smaller
account.

**Drawdown response protocol**: at −5R from equity peak, halve risk per trade to
0.5%. At −10R, stop and do a full review. Resume at 0.5% and return to 1% only after
a new equity high.

## 9. Leverage, margin, and liquidation

- Leverage does not change risk if size comes from the stop. It changes how much
  margin sits on the exchange and where the **liquidation price** is.
- The liquidation price must be **well beyond the stop**. Rule: liquidation
  distance at least 3x stop distance. If the exchange would liquidate before or
  near the stop, leverage is too high.
- **Isolated margin** for day trades so one position cannot drain the account.
  Cross margin only if the user knows exactly why.
- Effective leverage (notional / equity) above ~3-5x on a day trade is a red flag:
  it means either the stop is unrealistically tight or the user is sizing from
  leverage.
- Exchanges reduce max leverage as position size grows (tiered margin). A "100x"
  headline is for tiny positions.

## 10. Fees, funding, and slippage

Taker fees on major exchanges: ~0.04-0.06% per side on perps, 0.05-0.10% on spot
(lower with volume or native-token discounts). Maker fees are lower or zero.

Impact on a day trade: a 0.05% taker fee each way is 0.10% round trip. On a trade
with a 0.8% stop, fees are 12.5% of 1R. On a scalp with a 0.2% stop, fees are half
of 1R. Fees are why tight-stop scalping is a losing game for retail.

- Use **limit (maker) orders** for entries when the setup allows waiting.
- Include fees in every R:R calculation (`position_size.py` does).
- **Funding**: if a perp position is held through settlement, the funding payment
  is a cost (or income). At +0.05% per 8h, holding a long through two settlements
  costs 0.10%, another 12.5% of a 0.8% stop.
- **Slippage** on market orders: small on BTC/ETH during liquid hours, large on
  alts and on weekends. Assume 0.05-0.1% on alts. Stops are market orders when
  triggered, so realized losses run a bit larger than 1R.

## 11. Scaling out and moving stops

A simple, robust management plan for 2R+ setups:

1. Take **one third to one half** at the first logical level or ~1R-1.5R.
2. Move the stop to **breakeven** (entry plus fees) only after T1 is hit, never
   before. Moving to breakeven early converts good trades into scratches.
3. Let the rest run to T2 (2R+) or trail behind each new higher low on the trigger
   timeframe.

Full exits at T1 lower the average win and require a higher win rate. Never
scaling out means giving back many 1.5R winners. The blend above is a reasonable
default; the journal will show whether it suits the user's setups.

## 12. Kelly and why to use a quarter of it

Kelly fraction = win_rate − (loss_rate / avg_R_ratio). With 40% winners at 2.2R:
0.40 − (0.60 / 2.2) = 0.127, or 12.7% of the account per trade for maximum long-run
growth. Full Kelly assumes you know your edge exactly (you do not) and tolerates
drawdowns above 50% (nobody does). Quarter-Kelly, ~3%, is the theoretical ceiling;
the 1% default leaves room for the edge being smaller than the journal claims.

## 13. Exchange, custody, and operational risk

- Keep only active trading capital on any exchange. Everything else in self
  custody (hardware wallet). Exchanges fail.
- Hardware two-factor. API keys with trading permission only, never withdrawal.
  IP whitelist where offered.
- Know the exchange's rules on **auto-deleveraging (ADL)**, insurance funds, and
  maintenance margin. Read the liquidation page once.
- Use **stop orders on the exchange**, not mental stops and not alerts. Crypto
  moves 5% while you are in the shower.
- Have a plan for the exchange going down during a move (it happens on the most
  volatile days). A hedge on a second venue, or smaller size.

## 14. Sizing checklist

Before every entry:

- [ ] Stop is at the invalidation plus buffer, and it is at least 0.5 ATR away
- [ ] Size computed from the stop at 1% (or current drawdown-adjusted) risk
- [ ] 2R target is realistic and does not run through a major level
- [ ] Fees included; net R:R still 2 or better
- [ ] Liquidation price at least 3x the stop distance away
- [ ] Total open risk including this trade ≤ 3R; correlated positions counted as one
- [ ] Daily loss so far < 3R; weekly < 6R
- [ ] Stop order placed on the exchange before or immediately with the entry
