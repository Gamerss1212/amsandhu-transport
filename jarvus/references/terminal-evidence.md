# What the Jarvus Terminal measured (Sept–Oct 2026)

The Jarvus Terminal was a Windows/desktop program built for Abhi in Sept 2026: 311 rule-based bots on crypto and
US/Canadian stocks, a learning "brain" that took or refused every trade, a trained volatility gate, a research
engine, paper trading at live prices, and broker connections (real money off). It has been retired; its
knowledge lives in Jarvus now. This file is everything it measured, with how it was measured and what each
number does and does not show. Where these numbers disagree with an older line in Jarvus, **these win** (they
are newer, larger, and priced at fees verified in Sept 2026).

Contents: 1 The short version · 2 How everything was tested · 3 Every strategy, tested · 4 The swing lab ·
5 The whole system, replayed 3,000 times · 6 By fee level · 7 By account size · 8 Can the brain be improved? ·
9 The volatility gate · 10 Live paper running · 11 Fees used everywhere · 12 What none of this shows

## 1. The short version

* **146 strategies, 932 strategy-market pairs, 1,864 hypothesis tests: zero significant after correcting for the
  number of ideas tried** (Holm). The deflated Sharpe of the best result was 0.000: what luck alone produces with
  that many tries.
* **Crypto at retail fees: 0 of 353 runs profitable** (Kraken Pro entry tier, 0.40% maker / 0.80% taker). At a
  low-fee venue (0.10% taker): 14 of 353. Before any costs, 154 crypto pairs had a positive edge with 20+ trades:
  **fees, not ideas, decide crypto day trading.**
* **US stocks (commission-free):** 102 of 564 runs profitable with 20+ trades, but none survived the multiple-testing
  correction, and of the 49 candidates (positive on train AND validation) only 8 stayed positive on the untouched
  test segment (average +0.056R full period vs −0.218R on test).
* **The whole software** (all bots + gates + brain), replayed on 1,000 random 10-day windows: trading every signal
  lost −12.1% per window; the gates cut that to −0.11%; the brain to −0.02% at each exchange's own fees, about
  break-even (+0.002% to +0.007%) at NDAX or low-fee levels. **It never showed a reliable profit.** Its real value
  was refusing trades: it approved about 5 of every 137 signals.
* **The one part with real skill: the volatility gate.** When it flags LOUD on crypto it is right 76% of the time
  (base rate 31%). It predicts how much a market will move, never which way.
* **$100 → $300,000 in 3 months** needs +9.3% every day; the best 10-day window ever measured was +3.42% (at $100,
  NDAX fees). 0 of 5,000 simulations came close. See `any-balance-and-goals.md`.

## 2. How everything was tested (the protocol)

Use the same protocol whenever Abhi asks "does X work" (`Jarvus backtest`, `Jarvus test`).

1. **Parameters fixed before data is seen.** Each strategy's parameters were written down first; the evaluation
   never searched or tuned them. That removes in-sample optimisation, not the selection bias of picking which
   of 146 to trust, which is handled by step 6.
2. **No look-ahead.** Every indicator is causal (tested: values on a truncated history equal values on the full
   history); decisions use completed bars only; higher timeframes align to the last closed bar; swing points are
   published only after confirmation (no repainting).
3. **Same code as live.** Backtests drove the same trade manager the live bots used.
4. **Costs always on.** Crypto at three levels: gross (no costs, to show the raw edge), a low-fee venue
   (0.08%/0.10%), and **retail Kraken (0.40%/0.80%)**. Stocks: commission-free broker plus assumed spreads by
   liquidity tier plus US regulatory sell fees, and a 2x-slippage stress run. Fill model: market orders fill at
   the next bar's open ± half the spread + impact; stops fill at the stop or at the open if the bar gapped through
   it, with twice the normal slippage; when stop and target are both touched inside one bar, the stop wins.
5. **Chronological splits.** Train 60% / validation 20% / test 20% with a one-day embargo after each boundary, plus
   4 consecutive walk-forward folds (the share of positive folds is a stability check). Intraday strategies are
   flat at each session end, so no trade spans a boundary.
6. **Selection and multiple testing.** A pair is a **candidate** only if it was positive on BOTH train and
   validation with 30+ trades at realistic costs. The test segment is looked at once, for candidates only. Every
   (strategy, market, cost level) run is one hypothesis; one-sided t-test on per-trade R over train+validation;
   **Holm-Bonferroni** across all of them; the best validation Sharpe is **deflated** (Bailey & López de Prado 2014).
7. **Sizing for comparability.** Fixed capital, 0.5% risk per trade, no compounding.
8. **Kinds of evidence never mixed:** in-sample, validation, out-of-sample, paper observations, external claims.

**Data:** crypto = Coinbase 5-minute bars, about 120 days to late Sept 2026 (BTC, ETH, SOL; 1-minute BTC for 14 days;
ETH-BTC and USDT-USD 60 days; OKX BTC-USDT spot and perpetual 30 days; memecoins DOGE, SHIB, PEPE, BONK, FLOKI, WIF);
stocks = Yahoo 5-minute bars, 60 days (the free limit) for SPY, QQQ, NVDA, AAPL, TSLA with hourly/daily bars for
higher-timeframe rules. Swing lab: Coinbase hourly up to 5.5 years (9 coins), Yahoo hourly 3 years (6 stocks/ETFs).
Short samples: single results are noisy; the pattern across all runs is the finding.

## 3. Every strategy, tested

Full list with exact rules and every run: `strategy-scoreboard.md`. Untestable ideas: `strategy-library-untested.md`.

| | Result |
|---|---|
| Strategies evaluated | 143 intraday + 3 swing = 146, on 932 strategy-market pairs |
| Backtests | 14,672 (each pair × cost level × train/validation/test/4 folds/full) + gross runs |
| Significant after Holm | **0** (of 1,834 + 30 tests) |
| Crypto, retail Kraken fees | **0 of 353 runs profitable** |
| Crypto, low-fee venue | 14 of 353 |
| Stocks, base costs | 102 of 564 runs profitable with 20+ trades |
| Candidates (train AND validation positive, 30+ trades) | 49 runs from 34 strategies |
| Candidates still positive on the untouched test | **8 of 49**; average +0.056R (full) vs −0.218R (test) |
| Memecoin hypotheses (14, from the knowledge pack, 6 Coinbase memecoins, 120 days) | **all negative** after costs, most by −0.5R to −2.5R per trade; memecoin results use listed survivors, so they are biased upward |

Best runs at realistic costs (a selection, so optimistic; most failed on the test segment):

| Strategy | Market | Trades | R/trade | Gross R | Win % | Folds + | Test R (trades) |
|---|---|---|---|---|---|---|---|
| Ornstein-Uhlenbeck reversion, half-life filter | TSLA | 49 | +0.279 | +0.292 | 53% | 4/4 | +0.460 (17) |
| Mass Index reversal bulge (Dorsey) | TSLA | 59 | +0.237 | +0.256 | 54% | 4/4 | +0.466 (12) |
| Reversion to the prior point of control | QQQ | 52 | +0.219 | +0.304 | 44% | 3/4 | −0.402 (10) |
| Beta-adjusted residual reversion | NVDA | 79 | +0.197 | +0.264 | 57% | 3/4 | +0.287 (18) |
| Liquidity sweep then structure shift | NVDA | 62 | +0.180 | +0.199 | 47% | 3/4 | −0.218 (11) |
| Momentum ignition (ROC shock) | TSLA | 80 | +0.177 | +0.214 | 45% | 3/4 | +0.083 (19) |
| Supertrend direction flip | AAPL | 77 | +0.106 | +0.148 | 44% | 3/4 | +0.179 (14) |
| Turtle Soup (failed 20-bar breakdown) | AAPL | 87 | +0.096 | +0.251 | 41% | 3/4 | −0.025 (18) |
| VWAP reclaim after a sustained move below | TSLA | 68 | +0.078 | +0.098 | 62% | 3/4 | −0.149 (16) |
| Opening-range breakout on a closing basis | AAPL | 55 | +0.070 | +0.094 | 47% | 1/4 | −0.182 (10) |

Every one of those is a stock. On crypto 5-minute bars at retail fees, tight-stop intraday rules lose several R per
trade because a round trip costs more than the stop distance (`strategy-scoreboard.md` shows −5R to −9R rows).

## 4. The swing lab: what survives real costs on hourly data

Eight setups (breakout, RSI-2 dip, pullback, retest, squeeze, momentum, ORB, and "every bar" as the benchmark),
each tried with 48 exit structures and entry types chosen on train only; validation and an untouched test period
(crypto from 2025-12-23, stocks from 2026-03-30). Results are test-period R per trade after costs:

| Fee level | Majors (BTC, ETH, SOL) | Memes | Survivors (positive train, validation AND test) |
|---|---|---|---|
| Coinbase retail (0.60%/1.20%) | −0.46 to −0.83 | −0.28 to −0.63 | none |
| Kraken retail (0.40%/0.80%) | −0.26 to −0.52 | −0.16 to −0.49 | none |
| NDAX (0.20%/0.20%) | −0.23 to +0.00 | −0.32 to +0.006 | memes retest **+0.006** (172 trades) |
| Low-fee (0.08%/0.10%) | −0.15 to +0.08 | −0.27 to +0.06 | majors RSI-2 dip **+0.081** (126), memes breakout +0.029 (318), memes retest +0.056 (172) |
| US stocks, commission-free | +0.08 to +0.56 | — | none (every stock setup was negative on validation) |

* The exit structure every setup chose on train: **stop 4× ATR, target 2–3R, 96-hour time limit, limit (maker)
  entry.** That is swing trading, and it matches v5's finding (wide stops are the only way costs fit).
* Test-period gross R on majors was +0.10 to +0.15 for breakout and RSI-2 dip; the cost was 0.15R at NDAX, 0.41–0.45R
  at Kraken, 0.6–0.7R at Coinbase. Same trades, different venue, opposite result.
* The volatility gate did not rescue any setup here (the "with vol gate" test column was about equal).
* None survived Holm. The three swing strategies that became bots: RSI(2) dip in an uptrend, memecoin 24-hour
  breakout, memecoin 48-hour breakout retest (all 4 ATR / 2–3R / 96h / limit entry; rules in the scoreboard).

## 5. The whole system, replayed (1,000 runs × 3 arms)

Each run: 60 random bots, a random 10-day window between 2026-06-09 and 2026-09-30 (13,104 candidate trades from 296
bots), per-venue fees and slippage, 0.5% of a 1/20 capital slot per trade, at most 40 positions, 3% daily loss
halt. The brain's starting knowledge came only from data before the windows.

| Arm | Mean per window | Windows positive | Max drawdown | Trades per window | Win rate | Avg R |
|---|---|---|---|---|---|---|
| none (every signal, full size) | −12.124% | 0% | 12.15% | 137 | 10.5% | −3.280 |
| gates (cost + volatility) | −0.107% | 8% | 0.15% | 33 | 37.8% | −0.130 |
| brain (gates + learned brain) | −0.018% | 13% | 0.04% | 5 | 40.8% | −0.007 |

Paired: gates vs none +12.0% (97% of windows better); brain vs gates +0.089% [+0.076, +0.102]. What the refused
trades would have made: cost vetoes 172,746 blocked at −2.155R average; learned vetoes 12,049 at −0.179R; benched
16,146 at −0.143R; QUIET 3,464 at −0.164R. **Every kind of refusal avoided losing trades.** Limits: a vetoed bot does
not get the other entries it might have taken while flat; Kraken/OKX bots used Coinbase prices with their own fees.

## 6. The same system at each fee level

| Crypto fees | No brain | Gates only | Full brain | Brain windows positive | Trades per window |
|---|---|---|---|---|---|
| each bot's own exchange (Coinbase 1.20%, Kraken 0.80%, OKX 0.10% taker) | −12.124% | −0.107% | **−0.018%** | 13% | 5 |
| Kraken Pro entry tier (0.40%/0.80%) | −11.421% | −0.098% | **−0.010%** | 16% | 6 |
| NDAX (0.20% flat) | −5.487% | −0.140% | **+0.002%** | 19% | 10 |
| low-fee exchange (0.08%/0.10%) | −3.387% | −0.227% | **+0.007%** | 22% | 14 |

Lower fees let the brain approve more trades and move the average from slightly negative to about zero. Never a
reliable profit.

## 7. By account size ($100 to $10,000,000)

400 windows, brain arm, with order sizes modelled as the engine placed them (venue minimum orders, whole shares
unless fractional, a spot account's cash, 20 positions at most). Mean per 10-day window [bootstrap 95% interval]:

| Balance | Each bot's exchange | Coinbase | Kraken Pro | NDAX | Low-fee |
|---|---|---|---|---|---|
| $100 | −0.078% [−0.103, −0.054] | −0.074% | −0.024% [−0.057, +0.008] | +0.074% [+0.007, +0.145] | +0.116% [+0.020, +0.218] |
| $1,000 | −0.010% | −0.009% | −0.000% | +0.015% [+0.003, +0.027] | +0.022% |
| $10,000 | −0.012% | −0.011% | −0.002% | +0.013% [+0.001, +0.025] | +0.020% |
| $100,000 | −0.012% | −0.012% | −0.003% | +0.011% [−0.000, +0.024] | +0.023% |
| $10,000,000 | −0.011% | −0.010% | −0.008% | −0.007% | −0.003% |
| trades per window | 3.8–4.5 | 3.6–4.3 | 4.6–5.1 | 8.8–9.1 | 13.1–13.4 |

Do not read the positive cells as an edge: +0.074% per 10 days on $100 is about 7 cents; the 400 windows start on
only ~100 different days of one three-month period (about ten independent stretches, so the intervals are too
narrow); another sample of the same period at NDAX fees gave the opposite sign (section 8); at $10M the 5% volume
cap trims orders and every level is slightly negative. **At a low-fee exchange the system is about break-even, at
each exchange's own fees it loses slowly, and at no fee level does it show a reliable profit.**

The account-size fix that was measured: with 20 fixed slots a $100 account sized each trade from a $5 slot and 99% of
approved trades were too small for the exchange (0.06 trades per 10 days). Using fewer, larger slots (at least $25
each) raised that to 3.8. See `any-balance-and-goals.md`.

## 8. Can the brain be made better? (16 changes, chosen early, judged late)

Tune on windows before 2026-08-10, validate after; 150 windows each, paired, NDAX fees, $10,000.

| Variant | Validate mean | vs current [95% CI] | Trades |
|---|---|---|---|
| deterministic + edge ≥ 0.05 + cost ≤ 0.25R | +0.0140% | +0.0244% [+0.0142, +0.0346] | 15.0 |
| deterministic + edge ≥ 0.10 | +0.0125% | +0.0229% | 13.2 |
| no weekend entries (crypto) | +0.0074% | +0.0178% [+0.0079, +0.0273] | 21.4 |
| cost ≤ 0.15R | +0.0063% | +0.0167% | 16.2 |
| **current brain** | **−0.0104%** | reference | 23.0 |

**None was adopted.** Every "better" variant simply traded less and paid fewer fees; against never trading (0.0000%)
every interval includes zero (best: +0.0140% [−0.0060, +0.0340], about $1.40 per 10 days on $10,000); the validation
half holds only about five independent 10-day stretches. The lesson for Jarvus: a stricter filter loses less when
the average trade is negative; that is fee arithmetic, not intelligence. (It is also why the weekend rule M4 and the
cost gate stay.)

## 9. The volatility gate (trained 2026-09-29; `scripts/volgate.py`)

Chronological split: fit 60%, thresholds chosen on the next 20% (lowest that reached 65% precision), measured once
on the last 20%.

| Market | Forecast | Test AUC | Baseline AUC (ATR ratio only) | Flags | Right when it flags | Base rate |
|---|---|---|---|---|---|---|
| crypto, next 12h (299,719 hourly rows: BTC, ETH, SOL, DOGE, SHIB, PEPE, BONK, WIF, FLOKI; 2021-05 → 2026-09; boosted trees) | LOUD | 0.686 | 0.620 | 5.8% of hours | **76.2%** | 30.6% |
| | QUIET | 0.700 | 0.606 | 20.7% | 59.8% | 36.3% |
| stocks, next 7h (26,086 rows: SPY, QQQ, NVDA, AAPL, TSLA, IWM; 2024-04 → 2026-09; logistic) | LOUD | 0.637 | 0.637 | 1.7% | 68.2% | 29.0% |
| | QUIET | 0.647 | 0.639 | 5.4% | 59.2% | 32.9% |

Features (all from completed hourly bars): ATR(14) vs its 7-day mean, Bollinger width vs its 7-day mean, last-6h
volume vs the 7-day hourly mean, realised vol 24h vs 168h and 6h vs 168h, the last 12h and 72h range vs their 7-day
means, |12h return| in ATRs, the last bar's range in ATRs, hour of day, weekend, how big the next hours usually are
when they start at this hour (last 14 days), and 24h volume as a z-score. **Relation to v5's BTC-only gate (AUC 0.72–0.75,
82–85% at a ≥0.8 score on ~2–5% of bars):** both are honest; v5 used a stricter score on BTC alone, the Terminal's gate
is multi-coin with a 65%-precision threshold. Quote the numbers of the gate that produced the reading.

## 10. Live paper running

* **Staged roll-out (27–28 Sept 2026):** 1 → 10 → 50 → 250 bots on live public feeds. 250 bots for 125 minutes:
  3,268 of 3,268 scheduled evaluations, 0 errors, 0 rate-limited requests, decision p95 15 ms, bar close to decision
  p95 4.46 s, peak memory 148 MB. The brain scored 82 entries and **vetoed 79 (96%)**; the 6 paper trades that closed
  all lost: −$376.39, of which **$354.97 was fees (94% of the loss)**.
* **A defect found there and fixed:** resting (stop/limit) entries filled without the brain or the risk check;
  afterwards every resting entry was scored when placed. Lesson for manual trading: a limit or stop entry you leave
  on the book is still a trade decision; run the checks when you place it, not when it fills.
* **Autopilot (1 Oct 2026, 311 bots, 33 markets, NDAX fees):** typical hour: a handful of entry signals, all refused
  as "fees too high for the move"; the gate read NORMAL on every market; most markets sideways and calm. That is what
  the system does most of the time: watch, and refuse.

## 11. Fees used everywhere (base tiers, verified late Sept 2026)

| Venue | Maker | Taker | Round trip (taker both ways) |
|---|---|---|---|
| NDAX | 0.20% | 0.20% | 0.40% |
| Kraken Pro, $0+ 30-day volume | 0.40% | 0.80% | **1.60%** |
| Kraken Pro, $2.5K+ | 0.30% | 0.60% | 1.20% |
| Kraken Pro, $10K+ and $20K assets on platform | 0.22% | 0.38% | 0.76% |
| Coinbase Advanced, entry tier | 0.60% | 1.20% | 2.40% |
| a low-fee venue (OKX-level; not verified for Canadian residents) | 0.08% | 0.10% | 0.20% |
| US stocks via a commission-free broker | 0 | 0 | spread + SEC/FINRA sell fees |

Kraken's simple app (instant buy) charges a flat 1% instead; use Kraken Pro. Older Jarvus text quoted Kraken Pro at
0.16%/0.26% — that schedule is gone; re-check fee pages before relying on any number here.

## 12. What none of this shows

* It does not show that nothing can work: samples were short (60–120 days intraday), the period was one regime, and
  order-flow strategies could not be backtested at all.
* It does not show any strategy will work: the few positive results are what 1,800+ tries produce by chance.
* Paper fills are not real fills; crypto paper fills walked real order books, stock fills were synthetic.
* What it does show, robustly: **costs decide**, wide stops and maker entries are the only structures where costs
  fit, a selective filter loses less, and volatility (not direction) is forecastable.
