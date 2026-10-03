# ULTRON for TradingView: AI trade council, all timeframes

A semi-automatic AI trading council that lives inside TradingView. Each chart timeframe has its own trained
council: up to 25 agents plus one learned brain. The council watches your chart and decides whether to buy. When
it does, TradingView shows you (and alerts you) the limit buy, the stop and the target. You place the orders.
Paper-test it first.

## Install (2 minutes)

1. In TradingView (website or Desktop app), open a Coinbase pair: `COINBASE:BTCUSD`, `ETHUSD`, `SOLUSD`, `DOGEUSD`,
   `SHIBUSD`, `PEPEUSD`, `BONKUSD`, `WIFUSD` or `FLOKIUSD`. Any timeframe works.
2. Open **Pine Editor**, delete what is there, paste all of `ULTRON_indicator.pine`, then **Save** → **Add to chart**.
3. Optional: paste `ULTRON_strategy.pine` as a second script and open **Strategy Tester** to see the same rules
   traded on that chart, after the fees you set.

## Timeframes

Each trained timeframe has its own council. Its agents and brain were chosen by walk-forward testing on that
timeframe only. Each council also reads one higher timeframe:

| Your chart | Council | Also reads |
|---|---|---|
| 5m | 5m | 15m |
| 15m | 15m | 1h |
| 30m | 30m | 2h |
| 1h | 1h | 4h |
| 2h | 2h | 8h |
| 4h | 4h | 1D |
| 1D | 1D | 1W |
| anything else (1m, 3m, 45m, 3h, 12h, 1W …) | the nearest trained council | (untested on that chart; switch off in settings) |

The top line of the table names the council in use and says whether it was trained on this timeframe or is the
nearest one.

## What you see

- **Blue background** = the volatility gate says LOUD: a big move is likely soon, direction unknown. The table
  shows how often LOUD calls were right on the untouched test.
- **BUY label + three lines** = the council approved a buy. Blue = limit buy, red = stop, green = target.
  **SELL label** = the target or stop was hit, or the max hold ran out.
- **The table** shows the council, its backtest, volatility, chart and higher-timeframe trend, Bitcoin regime,
  agents firing, the decision, the full plan, and the position size for your account.

## Alerts (so it tells you without watching)

1. Click **Alert** → Condition **ULTRON** → **Any alert() function call** → Create.
2. Turn on **Notify in app** to get alerts on your phone through the free TradingView app.
3. Paid plans can also send a **Webhook**, for example to `https://ntfy.sh/<your private topic>` (the free ntfy phone
   app) or a bot. Set **Alert message** to JSON in Settings for bots. Alerts carry no keys or passwords; keep it
   that way.

## Customise everything (Settings → Inputs)

- **Account & risk:** account size, risk per trade for majors and for memes.
- **Fees:** your exchange's maker/taker fees (NDAX, Kraken, Coinbase values are in the tooltips).
- **Brain:**
  - nearest council on untrained timeframes on/off
  - other markets on/off
  - trade only timeframes that passed the untouched test (on by default: a council that lost money in testing,
    or had too few test trades, stays flat and says so in the table)
  - extra caution
  - volatility filter (Trained / LOUD only / LOUD or NORMAL / Off)
  - max fee cost, stop distance, target, limit-order life, max hold
- **Agents:** switch any signal off.
- **Display:** table on/off, position and size, past signals, plan lines, LOUD tint, colours, alert style.

The backtest below only applies to the trained defaults.

## How it was trained and tested (honest numbers)

- **Data:** Coinbase candles. Hourly from Dec 2020 to Oct 2026 for 1h, 2h, 4h and 1D. 5-minute from Oct 2023 for
  5m, 15m and 30m, so those have a shorter history and fewer quarters of walk-forward.
- **Candidates:** every Pine-portable candle and indicator signal × BTC/ETH/SOL or memes × chart or higher
  timeframe × condition (LOUD, uptrend, both, or any). Every candidate was traded with the same exits, after NDAX
  fees and slippage: limit 0.1% under the close, stop 4×ATR, target 2R, max 96 bars.
- **Walk-forward:** every quarter, each council re-chose its agents using only signals that had already finished,
  then traded the next quarter. 100 one-at-a-time improvements were tried per timeframe. A change was kept only if
  it helped development without hurting validation (Mar–Dec 2025). The test period (since Dec 2025) was never
  used to choose anything.
- **$10k paper account.** R = average result per trade in units of risk, after costs. A timeframe "passed" if
  its overall average and its untouched-test average are both positive with at least 15 test trades. Others show
  **caution** in the table.

<!-- RESULTS -->
| Chart | Agents | Test since Dec 2025 (untouched) | Validation 2025 | Development | All: trades · avg R · return · max DD | LOUD precision (test) | Status |
|---|---|---|---|---|---|---|---|
| 15m | 25 | -0.172R × 18 | -0.013R × 31 | -0.193R × 45 | 94 · -0.130R · -2.6% · 2.8% | 71.5% | **caution** |
| 30m | 25 | +0.005R × 128 | +0.119R × 105 | +0.116R × 80 | 313 · +0.072R · +13.1% · 12.1% | 74.4% | passed |
| 1h | 25 | +0.154R × 56 | +0.192R × 55 | +0.172R × 158 | 269 · +0.173R · +40.6% · 5.9% | 80.2% | passed |
| 2h | 25 | +0.030R × 67 | +0.264R × 63 | +0.157R × 286 | 416 · +0.153R · +43.6% · 9.7% | 83.1% | passed |
| 4h | 25 | +0.069R × 22 | +0.330R × 19 | +0.527R × 81 | 122 · +0.414R · +36.5% · 3.4% | 87.3% | passed |
| 1D | 25 | +0.495R × 4 | -0.315R × 11 | +0.660R × 33 | 48 · +0.423R · +13.8% · 5.5% | 29.4% | **caution** |
<!-- /RESULTS -->

- Per-timeframe stress tests (fees ×2, Kraken entry fees, slippage ×3), 200 random 90-day windows and 2,000
  bootstrap reshuffles are stored in `models/<tf>.json` under `backtest`.
- Most of the edge comes from the volatility gate plus trend filters. The candle and indicator agents are the
  triggers. Direction itself is barely predictable; the council does not forecast prices.

## Limits

- Trained on nine Coinbase coins. Other markets run only if you allow it, untested.
- The scripts hold a snapshot of what each council learned up to its training date. To refresh:
  `python3 ultron/tools/train_tf.py --h1 <hourly data> --m5 <5-minute data>` then `python3 ultron/tv/build_pine.py`
  (it also refreshes the table above). Run `python3 ultron/tv/pine_check.py ultron/tv/*.pine` to compile-check.
- One plan per chart. The cross-market limits of the backtest (one BTC/ETH/SOL trade at a time, daily loss stop)
  are yours to keep.
- Past results after costs. Not a forecast, not financial advice.

`ULTRON_25_indicator.pine` / `ULTRON_25_strategy.pine` are the earlier 1-hour-only version, kept for reference.
