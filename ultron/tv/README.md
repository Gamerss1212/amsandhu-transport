# ULTRON 25 for TradingView

A semi-automatic AI trading council inside TradingView. 25 trained agents watch your chart, one trained brain
decides, and TradingView shows you (and alerts you) where to buy, where to sell and where the stop goes.
You place the orders. Paper-test it first.

## Install (2 minutes)

1. Open TradingView (website or the TradingView Desktop app) and a **1-hour chart** of a Coinbase pair:
   `COINBASE:BTCUSD`, `ETHUSD`, `SOLUSD`, `DOGEUSD`, `SHIBUSD`, `PEPEUSD`, `BONKUSD`, `WIFUSD` or `FLOKIUSD`.
2. Open **Pine Editor** (bottom of the chart), delete what is there, paste all of `ULTRON_25_indicator.pine`,
   click **Save**, then **Add to chart**.
3. Optional: paste `ULTRON_25_strategy.pine` as a second script and open **Strategy Tester** to see how the
   same rules did on that chart, after the commission you set.

## What you see

- **Blue background** = the volatility gate says LOUD (a big move is likely in the next 12 hours, direction
  unknown). In testing, LOUD calls were right about 80% of the time against a 32% base rate.
- **BUY label + three dashed lines** = the council approved a signal: blue = limit buy, red = stop-loss,
  green = target (sell). **SELL label** = the target or the stop was reached, or the 96 hours ran out.
- **The table** = gate, 1h/4h trend, Bitcoin regime, how many agents are firing, the council's verdict and the
  full plan with position size.

## Alerts (so it tells you without watching)

1. Click **Alert** (clock icon) → Condition: **ULTRON 25** → **Any alert() function call** → Create.
2. Turn on **Notify in app** to get it on your phone through the free TradingView mobile app.
3. Paid TradingView plans can also send a **Webhook**. Pointing it at `https://ntfy.sh/<your private topic>` sends the
   same message to the free ntfy phone app, or to any bot. Set "Alert message" to JSON in the indicator's settings
   for bots.

## Customise everything (Settings → Inputs)

- Account size and risk per trade (majors and memes separately).
- Your exchange's maker/taker fees (NDAX, Kraken, Coinbase values are in the tooltips).
- The brain: minimum learned edge, caution, volatility filter (LOUD only / LOUD or NORMAL / off), max fee cost,
  stop distance, target, how long the limit order waits, max hold.
- Switch any of the 25 agents on or off.
- Display: table on/off, position and size, past signals, plan lines, LOUD tint, colours, alert message style.
  Changing the brain settings away from the trained defaults means the backtest below no longer applies.

## How it was trained and tested (honest numbers)

- 1,420 candidate agents (every Pine-portable signal × BTC/ETH/SOL or memes × 1h or 4h × condition) on Coinbase
  hourly data, Dec 2020 to Oct 2026, each traded with the same exits after NDAX fees and slippage.
- **Walk-forward:** every quarter from 2022 the brain chose its 25 agents using only signals that had already
  finished, then traded the next quarter. 100 one-at-a-time improvements were tried; 9 kept because they helped
  development (2022 – Mar 2025) without hurting validation (Mar – Dec 2025). The test period (since Dec 2025) was
  never used to choose anything.

| Period | Trades | Avg R | Return ($10k paper) | Max drawdown |
|---|---|---|---|---|
| Development 2022 – Mar 2025 | 232 | +0.151 | +30.3% | 6.1% |
| Validation Mar – Dec 2025 | 60 | +0.068 | +3.1% | 5.7% |
| **Test since Dec 2025 (untouched)** | 68 | +0.105 | +5.1% | 7.1% |
| All | 360 | +0.128 | +41.2% | 8.3% |

- Harder costs: fees ×2 +17.4% (avg +0.054R); Kraken entry-tier fees +9.7% (+0.014R, barely positive);
  slippage ×3 +25.8%.
- 200 random 90-day windows: median +1.6%, positive in 141; 2,000 reshuffles: 90% of outcomes between +12.9% and
  +76.8%, 95th-percentile drawdown 12.5%.
- Full report: `BACKTEST.md`. Most of the edge comes from the volatility gate plus the uptrend filter; the candle
  and indicator agents are the triggers.

## Limits

- 1-hour charts and the nine coins it was trained on (other markets only if you allow it, untested).
- The indicator uses the snapshot of what the brain learned up to the training date; retrain with
  `python3 ultron/tools/train.py --data <hourly data> --tv` and `python3 ultron/tv/build_pine.py` to refresh it.
- One plan per chart; the cross-market limits of the backtest (one BTC/ETH/SOL trade at a time, daily loss stop)
  are yours to keep.
- Past results after costs, not a forecast, not financial advice.
