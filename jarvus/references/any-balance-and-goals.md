# Any balance, and "can $X become $Y?"

What the Jarvus Terminal learned about trading accounts from $100 to $10,000,000, and how to answer money goals
honestly. Numbers: `terminal-evidence.md` sections 6–7. Calculator: `scripts/goal.py`.

## 1. Sizing works the same at every balance

Risk per trade is a percentage (0.5–1%, cap 1%), and size = risk ÷ stop distance. What changes with the balance is
whether that size can actually be placed.

| Balance | What goes wrong | What to do |
|---|---|---|
| **$100–$500** | 1% risk = $1–$5. With a 3–4x ATR stop on BTC (about 2–3%) the position is $35–$250: fine. With 20 small positions each would be $5, below many exchange minimums, so trades get refused | **Fewer, larger positions**: at most `balance ÷ $25` open at once (4 at $100, 20 from $500 up). Never raise risk to reach a minimum; if the minimum needs more risk than 1%, skip the trade |
| **$500–$100K** | Nothing structural; fees and discipline decide | Standard rules |
| **$100K+** | Market depth on small coins and memes | Cap any entry at **5% of the market's recent volume** (average of the last 12 bars); split large orders |
| **$10M** | The volume cap binds on most non-major markets | Majors and liquid stocks only; measured: the cap trimmed about 0.8 orders per 10 days at the Terminal's size |

* **Exchange minimums:** Coinbase about $1 per order; Kraken has a per-pair minimum cost (a few dollars) and a
  minimum quantity; NDAX shows its minimum in the order ticket; check before planning a $5 position.
* **US stocks:** many US brokers (Alpaca and others) allow fractional shares with a $1 minimum, so a $100 account can
  size a stock trade properly. Canadian listings (.TO) usually need whole shares: a $300 share in a $100 account cannot
  be sized at 1% risk at all, so skip it.
* **Spot, no leverage:** if the notional at 1% risk exceeds the account, the stop is too tight; widen it and cut size,
  never borrow.
* **Measured effect of the fix:** with 20 fixed slots a $100 account placed 0.06 trades per 10 days (99% of approved
  trades were too small); with `balance ÷ $25` slots, 3.8 (vs 4.5 at $100,000).
* **What a small account cannot fix:** fees are a percentage, so $100 pays the same cost in R as $100,000. The
  measured results per 10 days were about equal across sizes; the $100 row just swings more because each trade is a
  bigger share of the account.

## 2. Balance changes are not profit

Deposits and withdrawals (or a paper balance reset) are not results. Measure performance as a time-weighted return:
chain the returns between cash flows, so adding $1,000 never looks like a 10% gain and withdrawing never looks like a
drawdown. Journal R multiples are already immune to this; prefer them.

## 3. "Turn $100 into $300K in 3 months" and every goal like it

Answer in this order, briefly, without lecturing:

1. **The arithmetic.** Required daily return, compounded every day: `(goal ÷ balance)^(1 ÷ days) − 1`.

   | Goal | Days | Needed every single day |
   |---|---|---|
   | 2x | 90 | +0.77% |
   | 2x | 365 | +0.19% |
   | 10x | 90 | +2.59% |
   | 100x | 90 | +5.25% |
   | **3,000x ($100 → $300K)** | **90** | **+9.30%** |
   | 3,000x | 365 | +2.22% |

2. **What was measured.** `python3 scripts/goal.py 100 300000 90` strings together the real 10-day results of the
   whole Terminal (400 windows, Jun–Sep 2026) 5,000 times: at NDAX fees $100 → middle outcome **$100.45**, 9 in 10
   between $97.62 and $104.39, best of 5,000 $110.28; repeating the single best 10-day window (+3.42%) nine times in
   a row ends at $135. **0 of 5,000 reached $300,000**; the goal needs 42x the best 10 days ever measured, every 10 days.
3. **What would "work" instead, and why not:** all-in bets, leverage, memecoin lottery tickets, signal groups. They
   raise the spread of outcomes, mostly toward zero (94% of 300,000+ Solana meme traders lost over 90 days; 97% of day
   traders past 300 days lost money). Jarvus will not plan them.
4. **The honest aim:** survive, keep costs below 0.20R per trade, journal 100 trades, and see whether Abhi's own
   expectancy is positive. If it is, compounding a real +0.1 to +0.3R edge at 1% risk is how accounts grow; slowly.
   Adding money from income grows a small account far faster than trading can.

Never set a profit target for a trading day or week ("I need $X today" is a Coach-mode trigger). The engine has no
target: it decides trade by trade from costs, the gate and the measured edge.

## 4. `scripts/goal.py`

```
python3 scripts/goal.py 100 300000 90            # balance, goal, days (NDAX fees by default)
python3 scripts/goal.py 1000 2000 365 --fees kraken
python3 scripts/goal.py 25000 --days 180          # no goal: the spread of measured outcomes
```

It picks the nearest measured account size (log distance: $100, $1K, $10K, $100K, $10M), the fee level
(ndax, low_fee, kraken, coinbase, venue), and reports the middle, 5th and 95th percentile, best and worst of 5,000,
share ending up, share losing 10%+, the needed daily return and how many times the best measured window it is.
Always add: a measurement of three months of recent history, not a forecast.
