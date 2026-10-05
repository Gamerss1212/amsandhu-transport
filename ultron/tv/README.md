# ULTRON for TradingView: two AI indicators, every timeframe

| File | What it is |
|---|---|
| `ULTRON_Radar.pine` | **Indicator 1: ULTRON Radar.** Forecasts whether the next 12 candles will move a lot (LOUD / VERY LOUD) or very little (QUIET / VERY QUIET). It also shows trend, a stop and target, the fee cost and the position size. Works on any chart. |
| `ULTRON_indicator.pine` | **Indicator 2: ULTRON Council.** A trained AI council that says WAIT or BUY, with the limit buy, stop-loss, target(s) and size, and alerts you. |
| `ULTRON_strategy.pine` | Optional: the Council as a TradingView strategy, so the Strategy Tester shows its past trades on your chart. |

Results for both on every timeframe are below. The full report is `BACKTEST_ALL.md`. `HOW_IT_WORKS.md` explains
everything in plain words.

**New in v2.**
- **Council: Mode = High win rate (tested), the default.** Per timeframe it uses the volatility filter, minimum edge
  and exit that won most often while still making at least +0.10R a trade in both the fit and the validation
  period (231 combinations searched; `BACKTEST_ALL.md` section 3). On the untouched test: daily stocks/ETFs/forex
  82% of trades won (+0.30R a trade, 22 trades), 1h crypto 66% (+0.04R, 47), 2h crypto 57% (+0.02R, 42). 4h crypto
  lost on the test and 5m, 15m, 30m and daily crypto had no setup that passed, so those stay flat. Higher win
  rates come from selling part early: they make less per trade than the trained 2R (Mode = Trained) on 1h.
- **Radar: only calls that held up.** A call (LOUD, VERY LOUD, QUIET, VERY QUIET) shows on a timeframe only if it
  was right at least 60% of the time and 15 points above chance in both the fit and the validation period. The
  others are hidden (Calls -> Also show calls that failed). Calls -> Only the strongest shows just VERY LOUD /
  VERY QUIET: fewer calls, right more often (VERY LOUD 82-99% on the untouched test on 5m to 4h crypto and daily
  markets).

## Install (2 minutes each)

1. Open TradingView (website or Desktop app) and any chart.
2. Click **Pine Editor** at the bottom, delete what is there, paste all of `ULTRON_Radar.pine`, then **Save** →
   **Add to chart**.
3. In the Pine Editor click **Open → New indicator**, paste all of `ULTRON_indicator.pine`, then **Save** →
   **Add to chart**.
4. Move one table so they don't overlap: Radar's gear icon → Inputs → Table position → Top left.

The Council trades the markets it was trained on:
- **Crypto:** `COINBASE:BTCUSD`, `ETHUSD`, `SOLUSD`, `DOGEUSD`, `SHIBUSD`, `PEPEUSD`, `BONKUSD`, `WIFUSD`, `FLOKIUSD`.
- **Daily charts:** SPY, QQQ, IWM, DIA, AAPL, MSFT, NVDA, AMZN, GOOGL, META, TSLA, JPM, AMD, NFLX, XIU, RY, TD, ENB,
  SHOP, CNQ, EURUSD, GBPUSD, USDJPY, USDCAD, AUDUSD, GLD, SLV, USO.

The Radar works on anything; outside its training it says "nearest model, untested here".

## ULTRON Radar: is a big move coming?

- **The call:**
  - **VERY LOUD**: dark blue background and a big diamond.
  - **LOUD**: light blue background and a small diamond. A big move is likely in the next 12 candles; direction
    unknown.
  - **QUIET / VERY QUIET**: grey background. A small move is likely, and fees will eat small moves.
  - **NORMAL**: no strong call.
- **The table:**
  - the call;
  - what "big" and "small" mean on this chart right now, in %;
  - **how often this exact call was right on unseen data, next to the chance level**;
  - the typical 12-candle move after this call;
  - trend (this chart and the higher timeframe);
  - where a long stop (4× ATR, wider on fast charts) and a 2R target would be;
  - the fee cost of that stop in R;
  - how much to buy for your risk %.
- A call that tested weak on that timeframe is greyed and marked "weak call here".
- **Alerts:** "ULTRON Radar: VERY LOUD", "LOUD" and "QUIET", or "Any alert() function call".

## ULTRON Council: when to buy

- **The decision** (simple view):
  - WAIT, BUY (limit order waiting), IN TRADE, or why it is flat;
  - then buy price, stop-loss, sell target(s), size and volatility;
  - and **how this exit style did in the backtest on this timeframe** (win rate and average result, overall and on the
    untouched test).
- **On the chart:**
  - **BUY** label with dashed lines: blue = buy, red = stop, green = target, dotted green = first target.
  - **SELL HALF** label when the first target is hit and the stop moves to breakeven.
  - **SELL** label when it ends: target, stop, breakeven or time.
- **Exit style** (Settings → Inputs → Brain): same buys, different sells.
  - The default **Auto** picks, per timeframe, the style with the highest win rate that was profitable in both the
    fit and validation periods. The untouched test was not used to pick.
  - Pick **2R (trained)** for the largest average profit per trade.
  - Pick 1.5R, 1R, 0.5R or a "Half at …" ladder to trade a higher win rate against a smaller profit per trade.
- **Flat by default:** if the chosen exit style lost money, or had fewer than 15 trades, on this timeframe's untouched
  test, the Council stays flat and says why. Where 2R passes but Auto doesn't (4h), the table says so.
- **Alerts:** one alert on the indicator with "Any alert() function call" sends BUY, SELL HALF and SELL messages
  (readable or JSON).

## Results on every timeframe (untouched test = since Dec 2025, never used to choose anything)

<!-- RESULTS -->
**ULTRON Council**: default exit style (Auto) vs the trained 2R exit. Win rate = trades closed in profit after fees.

| Chart | Auto exit picks | Auto: win rate · avg R (all) | Auto: untouched test | 2R: win rate · avg R (all) | 2R: untouched test | Default |
|---|---|---|---|---|---|---|
| 5m crypto | 2R (trained) | 44% · -0.013R | 36% · -0.029R (33) | 44% · -0.013R | 36% · -0.029R (33) | **flat** |
| 15m crypto | Half at 0.5R, rest 1R | 67% · -0.015R | 57% · -0.134R (68) | 36% · -0.099R | 26% · -0.195R (68) | **flat** |
| 30m crypto | Third at 0.5R, rest 2R | 66% · +0.025R | 60% · -0.088R (75) | 42% · +0.093R | 33% · -0.090R (75) | **flat** |
| 1h crypto | Half at 0.5R, rest 2R | 71% · +0.066R | 70% · +0.082R (56) | 49% · +0.173R | 46% · +0.154R (56) | trades |
| 2h crypto | Third at 0.5R, rest 2R | 66% · +0.068R | 55% · -0.041R (65) | 46% · +0.159R | 35% · -0.017R (65) | **flat** |
| 4h crypto | Half at 0.33R, rest 2R | 76% · +0.120R | 68% · -0.005R (22) | 52% · +0.414R | 46% · +0.069R (22) | flat (2R passes: pick it to trade) |
| 1D crypto | 2R (trained) | 52% · +0.315R | 75% · +0.495R (4) | 52% · +0.315R | 75% · +0.495R (4) | **flat** |
| 1D markets | Half at 0.33R, rest 2R | 76% · +0.086R | 86% · +0.193R (22) | 54% · +0.425R | 54% · +0.431R (22) | trades |

**ULTRON Radar**: how often each call came true on the untouched test (number of calls), vs chance.

| Chart | LOUD | VERY LOUD | Chance (big move) | QUIET | VERY QUIET | Chance (small move) | Typical 12-bar move: all / after VERY LOUD |
|---|---|---|---|---|---|---|---|
| 5m crypto | 81% (37,336) | 91% (7,710) | 35% | 66% (40,718) | 74% (12,374) | 34% | 0.90% / 1.72% |
| 15m crypto | 72% (12,834) | 82% (2,695) | 33% | 69% (16,361) | 75% (5,572) | 35% | 1.57% / 2.86% |
| 30m crypto | 74% (5,362) | 92% (1,285) | 33% | 71% (7,429) | 79% (2,152) | 35% | 2.26% / 5.10% |
| 1h crypto | 80% (2,623) | 92% (679) | 32% | 56% (3,620) | 60% (852) | 35% | 3.29% / 7.48% |
| 2h crypto | 83% (1,687) | 94% (420) | 32% | 44% (1,410) | 38% (195) | 35% | 4.79% / 10.31% |
| 4h crypto | 87% (731) | 99% (149) | 33% | 41% (204) | 13% (15) | 38% | 6.95% / 12.69% |
| 1D crypto | 29% (34) | 50% (2) | 30% | 37% (419) | 42% (137) | 40% | 18.26% / 17.55% |
| 1D markets | 80% (204) | 91% (67) | 40% | 77% (87) | 86% (21) | 31% | 7.31% / 23.33% |
<!-- /RESULTS -->

### What this means

- **The Radar is the accurate one.**
  - On crypto 5m to 4h and on daily markets, its LOUD calls came true 72–87% of the time on unseen data, and VERY LOUD
    calls 82–99%, where chance is about a third (40% on daily markets).
  - The typical move after VERY LOUD was about 2–3× the normal move.
  - QUIET calls are strong on 5m–30m and daily markets (66–86%) and weak on 2h, 4h and daily crypto, where they are
    greyed.
  - The Radar is weak on daily crypto altogether.
- **The Council is profitable on 1h crypto and daily markets with the default Auto exit.**
  - On 1h crypto, about 7 in 10 trades closed in profit on unseen data.
  - On daily markets, about 8 in 10 closed in profit on unseen data.
  - 4h crypto passes with the 2R exit (higher profit per trade, about half the trades win) but not with Auto.
  - 5m, 15m, 30m and 2h crypto lost money on unseen data with every exit style, and daily crypto had only 4 test
    trades, so they stay flat by default.
- **Win rate vs profit.**
  - Closer targets win more often but each win is smaller. On 1h crypto, Auto wins 71% of trades at +0.066R on
    average, while 2R wins 49% at +0.173R.
  - Both are positive on unseen data. Pick by what you can stick with.
- Every backtest above re-ran the Council's walk-forward and reproduced the trained model exactly. Then every trade
  was replayed with every exit style. Costs are included: NDAX fees and slippage for crypto, 0.05% per side plus
  slippage for markets.
- Markets context: over the same walk-forward (Jan 2022 – Oct 2026), buying and holding SPY returned +59.9% (max
  drawdown 25.4%). The Council is long-only and does best when markets rise.

## Settings (gear icon → Inputs)

- **Council:**
  - account size;
  - risk per trade (majors/stocks and memes);
  - your fees (crypto maker/taker, stock/forex cost);
  - exit style;
  - only-passed timeframes;
  - nearest council on untrained timeframes;
  - other markets;
  - extra caution;
  - volatility filter;
  - max fee cost;
  - stop distance (× the trained stop);
  - limit-order life;
  - max hold;
  - any agent's signal on or off;
  - display options.
- **Radar:** account size, risk, fees, stop distance, target, lines, table, tints and colours.

Changing the brain settings away from the defaults means the backtest no longer applies exactly.

## How it was trained and tested

- **Data:**
  - Coinbase candles: hourly from Dec 2020 for 1h–1D, 5-minute from Oct 2023 for 5m–30m;
  - Yahoo Finance daily candles from 2005 for 28 stocks, ETFs, forex pairs and commodity ETFs.
- **Radar:**
  - A logistic model on 13 measurements, trained per timeframe on data before 20 Mar 2025.
  - Its LOUD, VERY LOUD, QUIET and VERY QUIET thresholds were set on that period only.
- **Council:**
  - Per timeframe, 700–1,400 candidate agents were tested with the same exits after costs.
  - A quarterly walk-forward chose 25 agents using only finished trades, and the brain learned their edges.
  - 150 one-at-a-time improvements were each kept only if they helped the fit period without hurting validation
    (20 Mar – 22 Dec 2025).
- Regenerate everything:
  - `python3 ultron/tools/train_tf.py ...`
  - `python3 ultron/tools/backtest_all.py --h1 <hourly> --m5 <5m> --mkt <daily markets>`
  - `python3 ultron/tools/report_all.py`
  - `python3 ultron/tv/build_pine.py`
  - `python3 ultron/tv/build_radar.py`
  - `python3 ultron/tv/pine_check.py ultron/tv/*.pine` (TradingView's own compiler: 0 errors required)

## Limits

- Past results after costs, not a forecast and not financial advice. Paper-trade first.
- Neither indicator predicts direction. The Radar forecasts the size of the next move. The Council trades small
  edges with strict risk and cost rules.
- Intraday stock and forex charts have no trained Council: free intraday history is too short for an honest test.
- One plan per chart. The backtest's cross-market limits are yours to keep: a few positions at a time, and a daily
  loss stop.

`ULTRON_25_*.pine` are the earlier 1-hour-only version, kept for reference.
