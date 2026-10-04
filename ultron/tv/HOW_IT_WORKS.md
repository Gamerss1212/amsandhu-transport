# How the two ULTRON indicators work, in plain English

Both indicators are complex inside but simple to read. This page explains what happens under the hood. The measured
results for every timeframe are in `BACKTEST_ALL.md`.

---

## ULTRON Radar: "Is a big move coming?"

**What it answers.** For the next 12 candles, will the price move a lot (**LOUD**), very little (**QUIET**), or
neither (**NORMAL**)? It does **not** say which direction. Nobody can forecast direction reliably on short timeframes;
in our tests a direction model scored barely better than a coin flip.

**Why that is still valuable.**
- **Fees.** A small move cannot pay for fees, while a big move can. QUIET is when accounts bleed out one fee at a time.
- **Stops.** In a LOUD period, tight stops get hit by noise, so you need a wider stop and a smaller size.
- **Predictability.** Volatility clusters: calm follows calm and storms follow storms. That makes "how much will it
  move" forecastable even though "which way" is not.

**How it decides: 13 measurements on every candle.** Each one compares "now" with "normal" for this market:

| # | Measurement | Plain meaning |
|---|---|---|
| 1 | ATR(14) ÷ its 168-candle average | Are candles bigger than usual right now? |
| 2 | Bollinger Band width ÷ its average | Squeezed (calm, often before a move) or expanding? |
| 3 | Volume of the last 6 candles ÷ normal | Is money suddenly arriving? |
| 4 | Volatility of the last 24 candles ÷ the last 168 | Has the market woken up recently? |
| 5 | High-low range of the last 12 candles ÷ normal | Is the recent swing wide or narrow? |
| 6 | Move of the last 12 candles, in ATRs | Did price just travel far? |
| 7 | Size of this candle, in ATRs | A shock candle? |
| 8–9 | Hour of the day (as a clock position) | Some hours are busier (London/New York open) |
| 10 | Weekend or not | Weekends are usually calmer for crypto |
| 11 | Volatility of the last 6 candles ÷ normal | Very short-term wake-up |
| 12 | Range of the last 72 candles ÷ normal | The bigger picture of the swing |
| 13 | Volume of the last 24 candles vs normal (z-score) | Sustained interest, not one spike |

**The model.**
- A logistic regression, the classic, well-understood kind of AI model. It turns the 13 measurements into one score.
- Each timeframe (5m, 15m, 30m, 1h, 2h, 4h, 1D, and daily stocks/forex) has its own trained model, because a 5-minute
  chart behaves differently from a daily one.
- Thresholds were set on the training data only:
  - LOUD fires on the top 5% of scores.
  - **VERY LOUD** fires on the top 1%.
  - QUIET and VERY QUIET work the same way for calm.

**What "right" means.**
- A LOUD call is right if the next 12 candles' high-to-low range lands in the **top third** of the last month's
  12-candle ranges.
- A QUIET call is right if it lands in the bottom third.
- By pure chance each happens about a third of the time, so 33% is the bar to beat.
- The table shows how often the current call was right on the untouched test (since Dec 2025), and next to it the
  chance level.

**The table.**
- *Next 12 bars*: the call (VERY LOUD / LOUD / NORMAL / QUIET / VERY QUIET).
- *Big / small move*: what "big" and "small" mean on this chart right now, in % (top-third and bottom-third cut-offs).
- *This call in testing*: how often this exact call was right on unseen data, and how many times it was tested.
- *Typical 12-bar move*: the median move after this call, next to the median of all candles.
- *Trend*: the chart's trend (EMA 21/50/200) and the higher timeframe's.
- *Long stop / target*: where a stop (4× ATR, wider on fast charts) and a 2R target would be for a buy now.
- *Fee cost*: your fees as a share of that stop. Above 0.33R, skip the trade.
- *Size*: how much to buy so that hitting the stop loses only your chosen risk %.

**How to use it.**
- VERY LOUD or LOUD: the market is about to move. Look for setups, use wide stops and expect follow-through.
- QUIET: stand aside, because fees will eat small moves.
- Pair it with the Council: the Council's edge was found mostly in LOUD periods with an uptrend on both timeframes.

**Limits.**
- On daily crypto the Radar was weak in testing, and the table says so.
- On markets or timeframes it was not trained on, it uses the nearest model and says "nearest, untested here".

---

## ULTRON Council: "Should I buy now, and where are the stop and target?"

**The agents.** Each timeframe has a council of 25 agents. An agent is one precise rule made of four parts:
- **A signal.** Either a candle pattern (bullish engulfing, hammer, three outside up, inside-bar break…) or an
  indicator event (20-bar Donchian breakout, MACD histogram turning up, OBV confirming a high, Bollinger re-entry…).
- **A market group.** BTC/ETH/SOL, or meme coins, or stocks/ETFs/forex.
- **A condition.** Any time, LOUD only, uptrend only, or LOUD + uptrend.
- **Where it looks.** This chart's candles, or the next higher timeframe's (it acts when that bigger candle closes).

**How the 25 were chosen (walk-forward).**
- Per timeframe, 700–1,400 candidate agents were each traded on years of history with the same exits, after fees.
- Every quarter since 2022, the council re-ranked the candidates using only trades that had already finished at that
  point, kept the best 25 by a cautious score, then traded the next quarter.
- The candidates are ranked by a lower confidence bound, not the average, so a lucky agent with few trades does not
  win a place.
- Then 150 one-at-a-time improvements to the brain's settings were tried. A change was kept only if it helped the fit
  period and did not hurt validation. The test period never chose anything.

**The brain.**
- For every agent it learned two things:
  - **edge**: the average result per trade, in R;
  - **uncertainty**: the standard error, learned separately for "Bitcoin above its 200-day average" and "below".
- A signal is approved only if **edge − z × uncertainty ≥ threshold**. The brain demands more proof from agents it
  knows less about.
- Hard rules on top:
  - Fees must cost less than 0.33R, otherwise the trade is refused; between 0.20 and 0.33R it trades half size.
  - The council's volatility rule (for example LOUD only).
  - No new BTC/ETH/SOL trades at weekends, because the models showed no edge there.
  - Meme coins are off when Bitcoin is below its 200-day average.

**The trade it proposes.**
- **Entry:** a limit buy 0.1% under the close, valid for 3 candles (maker fees are cheaper).
- **Stop:** 4 × ATR. On 5m–30m it is wider (5.7–13.9 × ATR) so fees stay small next to it.
- **Exit:** depends on the **Exit style** you pick (below).
- **Time limit:** 96 candles (about 4 days on fast charts).
- **Size:** your risk % of the account ÷ stop distance, scaled 0.5×–1.5× by the agent's edge, halved when fees are
  costly. It is never more than your account.

**Exit styles: win rate vs profit.** Same buys, different sells:

| Style | What happens | Effect |
|---|---|---|
| 2R (trained) | sell everything at 2× the risk | fewest wins, biggest wins |
| 1.5R / 1R / 0.5R | sell everything at a closer target | more wins, smaller wins |
| Half at 1R, rest 2R | sell half at 1R, move the stop to breakeven, rest at 2R | a middle way |
| Half at 0.5R, rest 2R or 1R | sell half early, stop to breakeven | high win rate; profit depends on the timeframe |

The table shows the measured win rate and average result of the style you picked on your chart's timeframe, both
over the whole backtest and on the untouched test. **Always look at both numbers.** A higher win rate often comes with
a lower average result, because many small wins can be wiped out by the losses.

**"Flat by default".**
- Timeframes whose council lost money or had too few trades on the untouched test do not signal buys unless you
  switch that rule off.
- The table says "Flat: no reliable edge on this timeframe in testing".

---

## Why not a 90% win rate with huge profits?

- **Win rate and payoff trade off.** With the same entries, closer targets win more often but each win is smaller.
  You can buy a high win rate with exit rules. That does not make a strategy more profitable; the tables show
  exactly what each style costs or gains.
- **Accuracy is real for volatility.** The Radar's VERY LOUD calls were right about 9 times in 10 on several
  timeframes in the untouched test. That is the part of the market that is genuinely predictable.
- **Direction stays close to a coin flip.** The Council's edge is real but small (+0.07R to +0.43R per trade on the
  timeframes that passed, depending on the exit style). It comes from trading only when conditions favour it, sizing from the stop and keeping
  fees small, not from "seeing the future".
- **Most day traders lose.** These tools are built to make you slower, smaller and more selective, which is how a
  small edge survives. Paper-trade first.
