# ULTRON for TradingView: AI trade council, all timeframes, crypto and markets

A semi-automatic AI trading council that lives inside TradingView. Each crypto timeframe (5m to 1D) has its own
trained council, and a separate council covers daily charts of 28 stocks, ETFs, forex pairs, gold, silver and oil.
Each council is up to 25 agents plus one learned brain. It watches your chart and decides whether to buy. When it
does, TradingView shows you (and alerts you) the limit buy, the stop and the target. You place the orders.
Paper-test it first. `MARKETS.md` explains how each market behaves and what ULTRON covers.

## Install (2 minutes)

1. In TradingView (website or Desktop app), open either:
   - a Coinbase crypto pair (`COINBASE:BTCUSD`, `ETHUSD`, `SOLUSD`, `DOGEUSD`, `SHIBUSD`, `PEPEUSD`, `BONKUSD`,
     `WIFUSD`, `FLOKIUSD`) on any timeframe, or
   - a **daily** chart of one of the trained markets: SPY, QQQ, IWM, DIA, AAPL, MSFT, NVDA, AMZN, GOOGL, META, TSLA,
     JPM, AMD, NFLX, XIU, RY, TD, ENB, SHOP, CNQ, EURUSD, GBPUSD, USDJPY, USDCAD, AUDUSD, GLD, SLV, USO.
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
| stocks, ETFs, forex, gold, silver, oil: 1D | 1D markets | 1W |
| stocks, ETFs, forex: intraday | none (stays flat and says so) | |

On charts faster than 1h, the trained stop is wider and the hold longer (scaled to the 1-hour structure), so the
fee stays a small share of the stop.

The top line of the table names the council in use and says whether it was trained on this timeframe or is the
nearest one.

## What you see

**Simple view (default):** a small table with the decision ("WAIT · no setup now", "BUY · limit order waiting",
"IN TRADE", or why it is flat), then buy price, stop-loss, target, size, and volatility. Switch off "Simple view" in
Settings → Display to see everything: backtest, trend, regime, agents firing, which agent proposed the trade.

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
- **Fees:** your crypto exchange's maker/taker fees (NDAX, Kraken, Coinbase values are in the tooltips), and
  your stock/forex cost per side.
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

- **Data:**
  - Coinbase candles. Hourly from Dec 2020 to Oct 2026 for 1h, 2h, 4h and 1D. 5-minute from Oct 2023 for 5m, 15m
    and 30m, so those have a shorter history and fewer quarters of walk-forward.
  - Markets council: daily Yahoo Finance candles from 2005 (split-adjusted like TradingView), costed at 0.05% per
    side plus 0.02% slippage.
- **Candidates:** every Pine-portable candle and indicator signal × BTC/ETH/SOL or memes × chart or higher
  timeframe × condition (LOUD, uptrend, both, or any). Every candidate was traded with the same exits, after NDAX
  fees and slippage: limit 0.1% under the close, stop 4×ATR, target 2R, max 96 bars (on 5m–30m: stop 5.7–13.9×ATR,
  hold 192–1,152 bars, about 4 days).
- **Walk-forward:** every quarter, each council re-chose its agents using only signals that had already finished,
  then traded the next quarter. 150 one-at-a-time improvements were tried per council. A change was kept only if
  it helped development without hurting validation (Mar–Dec 2025). The test period (since Dec 2025) was never
  used to choose anything.
- **$10k paper account.** R = average result per trade in units of risk, after costs. A timeframe "passed" if
  its overall average and its untouched-test average are both positive with at least 15 test trades. Others show
  **caution** in the table.

<!-- RESULTS -->
| Chart | Agents | Test since Dec 2025 (untouched) | Validation 2025 | Development | All: trades · avg R · return · max DD | LOUD precision (test) | Status |
|---|---|---|---|---|---|---|---|
| 5m crypto | 25 | -0.029R × 33 | -0.015R × 182 | +0.013R × 37 | 252 · -0.013R · +0.6% · 2.3% | 81.2% | **flat by default** |
| 15m crypto | 25 | -0.195R × 68 | -0.027R × 61 | -0.058R × 55 | 184 · -0.099R · -3.4% · 6.5% | 71.5% | **flat by default** |
| 30m crypto | 25 | -0.090R × 75 | +0.073R × 73 | +0.344R × 61 | 209 · +0.093R · +10.4% · 11.9% | 74.4% | **flat by default** |
| 1h crypto | 25 | +0.154R × 56 | +0.192R × 55 | +0.172R × 158 | 269 · +0.173R · +40.6% · 5.9% | 80.2% | trades |
| 2h crypto | 25 | -0.017R × 65 | +0.264R × 63 | +0.176R × 269 | 397 · +0.159R · +42.2% · 11.0% | 83.1% | **flat by default** |
| 4h crypto | 25 | +0.069R × 22 | +0.330R × 19 | +0.527R × 81 | 122 · +0.414R · +36.5% · 3.4% | 87.3% | trades |
| 1D crypto | 25 | +0.495R × 4 | -0.357R × 14 | +0.532R × 40 | 58 · +0.315R · +14.4% · 6.8% | 29.4% | **flat by default** |
| 1D markets | 25 | +0.431R × 22 | +0.794R × 25 | +0.355R × 134 | 181 · +0.425R · +91.4% · 14.5% | 79.9% | trades |
<!-- /RESULTS -->

- **What this means:** three councils trade by default: **1h crypto** (the steadiest), **4h crypto**, and **1D
  markets** (stocks, ETFs, forex, gold, silver, oil). The others stay flat by default because their untouched test
  lost money or had too few trades. 2h was positive before the extra 50 improvement steps and slightly negative
  after; it was not reverted, because choosing by the test result would make the test meaningless. 5m, 15m and 30m
  found no lasting edge after fees, even with wider exits. Councils marked **flat by default** show their backtest
  and "Flat: no reliable edge on this timeframe in testing" and do not signal buys, unless you switch off "Only
  trade timeframes that passed the untouched test".
- Markets council context: over the same walk-forward (Jan 2022 – Oct 2026), buying and holding SPY returned
  +59.9% (max drawdown 25.4%) and QQQ +84.7% (35.2%). Not like-for-like: the council is long-only across 28 markets,
  risks 0.6% per trade, holds up to 8 positions and does best when markets rise. On forex, tight % stops mean large
  positions; the size is capped at your account size per trade, and your total exposure across charts is yours to
  manage.
- 5m, 15m and 30m only have 5-minute data from Oct 2023, so their walk-forward starts in Jul 2024 and their
  development period is shorter.
- Per-timeframe stress tests (fees ×2, Kraken entry fees, slippage ×3), 200 random 90-day windows and 2,000
  bootstrap reshuffles are stored in `models/<tf>.json` under `backtest`.
- Most of the edge comes from the volatility gate plus trend filters. The candle and indicator agents are the
  triggers. Direction itself is barely predictable; the council does not forecast prices.

## Limits

- Trained on nine Coinbase coins and 28 daily markets. Other symbols run only if you allow it, untested.
- Intraday stock and forex charts have no trained council: free intraday history only goes back about 2 years, too
  short for an honest walk-forward test.
- The scripts hold a snapshot of what each council learned up to its training date. To refresh:
  `python3 ultron/tools/train_tf.py --h1 <hourly data> --m5 <5-minute data>` (add `--mkt <daily data> --tfs 1Dm` for
  the markets council, data from `ultron/tools/download_markets.py`), then `python3 ultron/tv/build_pine.py`
  (it also refreshes the table above). Run `python3 ultron/tv/pine_check.py ultron/tv/*.pine` to compile-check.
- One plan per chart. The cross-market limits of the backtest (one BTC/ETH/SOL trade at a time, daily loss stop)
  are yours to keep.
- Past results after costs. Not a forecast, not financial advice.

`ULTRON_25_indicator.pine` / `ULTRON_25_strategy.pine` are the earlier 1-hour-only version, kept for reference.
