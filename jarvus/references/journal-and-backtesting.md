# Journal and Backtesting

Edge is a statistical claim. It needs data. This file covers what to record, what
to compute, and how to test an idea before risking money on it.

## Contents

1. The journal
2. Metrics that matter
3. Reviewing the journal
4. Backtesting honestly
5. Overfitting and how to avoid it
6. Using scripts/backtest.py
7. Forward testing

---

## 1. The journal

`assets/journal-template.csv` has the columns. The essential fields:

| Field | Why |
|---|---|
| `date_utc`, `time_utc` | Session and time-of-day analysis later |
| `symbol`, `direction` | Per-pair and long/short breakdown |
| `playbook` | The single most useful column: expectancy by setup |
| `grade` (A/B) | Did the user take only quality? Did grading predict outcome? |
| `entry`, `stop`, `target`, `exit` | Reconstructs R |
| `risk_pct`, `size` | Sizing discipline check |
| `r_multiple` | The outcome in R (the script computes it if blank) |
| `fees_r` | Fee drag in R |
| `planned` (yes/no) | Was it in the morning plan? |
| `execution_grade` (1-5) | Process quality regardless of outcome |
| `mistake` | Free text tag: chased, moved stop, early exit, oversized, none |
| `notes` | What was seen, what was felt, screenshot link |

Record the trade **before** the outcome (entry, stop, target, playbook, grade)
and fill in the exit after. Recording after the fact rewrites history.

## 2. Metrics that matter

All produced by `scripts/journal_stats.py`:

- **Trades (n)**: below 50, everything else is provisional.
- **Win rate**: with the average R it determines expectancy; alone it means nothing.
- **Average win (R), average loss (R)**: average loss drifting past −1.1R means
  stops are being moved or slippage is heavy.
- **Expectancy (R/trade)**: the number.
- **Profit factor**: gross win R / gross loss R.
- **Max drawdown (R)** and **longest losing streak**: sets the risk % and the
  stomach requirement.
- **By playbook**: cut the setup with negative expectancy over 20+ trades.
- **By session / hour**: many traders discover they only make money in one session.
- **By grade**: A trades should beat B trades. If not, grading is wrong.
- **Planned vs unplanned**: unplanned trades are almost always net negative. The
  number makes the case.
- **Execution grade vs outcome**: good process with bad outcomes is variance;
  bad process with good outcomes is a future problem.

## 3. Reviewing the journal

Weekly, in this order:

1. Did I follow the rules? Count unplanned trades, moved stops, oversized trades,
   limit breaches. Those are the first thing to fix; nothing else matters until
   they are near zero.
2. What is expectancy and is n large enough to believe it?
3. Which playbook / session / pair is the best and worst? Do more of the best, cut
   the worst.
4. What is the most common mistake tag? Pick one, and only one, to work on next
   week.
5. Re-read the notes on the three biggest losses. Most large losses are not bad
   setups; they are rule breaks.

## 4. Backtesting honestly

A backtest replays a rule set over history to estimate expectancy. Done well it
saves months. Done badly it manufactures confidence.

**Requirements for a meaningful test:**

- **Rules that a machine could follow.** "Buy the pullback when it looks good" is
  not testable. "Buy when 5m closes above the 9 EMA after price touched the 15m 21
  EMA in a 4H uptrend" is.
- **Realistic fills**: entries at the next candle's open after the signal, not at
  the signal candle's close. Stops filled at the stop price minus slippage. Fees
  on both sides.
- **Both stop and target checked within each candle**, and when both are touched
  in the same candle, assume the **stop** hit first (pessimistic).
- **Enough data**: at least several hundred signals across different regimes (a
  trending quarter, a ranging quarter, a crash). One good month proves nothing.
- **Out-of-sample data**: tune the rules on one period, then test on a period the
  rules never saw. If the out-of-sample result collapses, the rules were fitted to
  noise.

**Metrics to report**: n, win rate, avg R, expectancy, profit factor, max drawdown
(R), longest losing streak, and expectancy per regime.

## 5. Overfitting and how to avoid it

Overfitting is tuning parameters until the past looks great. Symptoms:

- Many parameters (more than 3-4) with precise values ("RSI 37, EMA 23").
- Results that change a lot when a parameter moves slightly. A robust rule
  performs similarly with EMA 18, 21, or 25.
- A great in-sample result and a poor out-of-sample result.
- A strategy that only worked in one regime.

Defenses: fewer parameters, round numbers, walk-forward testing (tune on window
1, test on window 2, slide, repeat), and a healthy suspicion of anything above
+0.5R expectancy on a day-trading rule.

## 6. Using scripts/backtest.py

The bundled backtester is deliberately simple: standard-library Python, one CSV
of candles in, a stats table out. It implements two rule sets as examples:

- `ema_pullback`: long-only trend pullback. Trend filter: close above the 200 EMA
  and 21 EMA above 50 EMA. Setup: a candle low touches the 21 EMA. Trigger: next
  candle closes above the 9 EMA. Stop: the setup candle's low minus 0.3 ATR. Target:
  2R (configurable).
- `range_fade`: mean reversion. A candle closes outside the 2σ Bollinger band and
  the next closes back inside; enter toward the middle band; stop beyond the
  extreme plus 0.3 ATR; target the middle band or 2R, whichever is closer.

```bash
python3 scripts/fetch_ohlcv.py --symbol BTCUSDT --interval 15m --limit 1000 --out /tmp/btc15.csv
python3 scripts/backtest.py /tmp/btc15.csv --strategy ema_pullback --target-r 2 --fee-pct 0.05
python3 scripts/backtest.py /tmp/btc15.csv --strategy range_fade --split 0.7
```

`--split 0.7` reports in-sample (first 70%) and out-of-sample (last 30%)
separately. `--json` emits machine-readable results.

The point of the script is to show the user what verification looks like and to
give Claude a concrete tool when the user says "does X work?". Adding a strategy
means adding one function that returns a signal (direction, stop, target) for a
given candle index; the file explains where.

## 7. Forward testing

After a backtest looks acceptable, trade the rules at minimum size (or on paper)
for 30-50 trades in real time. Forward results are always worse than the backtest:
fills, hesitation, and regime change. If forward expectancy is still positive,
scale toward normal risk. If it is not, the backtest was optimistic; find out why
before adding money.
