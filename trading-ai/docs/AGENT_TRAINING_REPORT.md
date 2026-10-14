# Agent training report (100 agents)

Generated 2026-10-14 05:09 UTC by `scripts/train_agents.py`, using the app's own research engine on real market data. The run took 26 minutes.

## Method

- **Datasets.** Each agent trains on its own market and bar size, using up to 20,000 hourly or 6,000 15-minute bars.
  - The data comes from public sources: Coinbase for crypto and meme coins, Yahoo Finance for US stocks.
  - The provider, bar count, date range and SHA-256 of every dataset are listed below and stored in the research ledger.
- **Objective.** Each of the role's 3 candidate templates gets one STANDARD research run.
  - Parameters are fitted on the first 60% of the bars (TRAIN), using the Sharpe ratio net of modelled costs.
  - The master chooses the candidate with the best VALIDATION Sharpe (the next 20%).
  - The last 20% is a held-out TEST that is never used for any choice.
  - Walk-forward refits are judged out of sample.
- **Costs.** Fees, spread, slippage and funding are taken from the app's cost model for each market. Day-trading rules apply: entries only inside session windows, and every position is flat before the close or the 24-hour crypto limit.
- **Gate.** A version may trade (in paper only) only if its research verdict is PAPER TEST. That verdict requires all of the following:
  - at least 30 test trades;
  - Deflated Sharpe ≥ 0.95, charged for every trial run in the strategy family so far;
  - PBO ≤ 0.2;
  - a walk-forward ratio ≥ 0.5;
  - 2x-cost survival;
  - a placebo percentile ≥ 95.

  Anything else is recorded as a rejected version, and the agent stays in cash.
- **Multiple testing.** Trials are charged per family, in a fixed order (A001 to A100). Later agents in a crowded family therefore face a stricter Deflated Sharpe hurdle. This is deliberate.

## Results

- Agents: 100; with a market: 100; research runs completed: 300.
- Run verdicts: REJECT: 297, RESEARCH FURTHER: 3.
- Agent versions after training: rejected: 100. "active" means the agent may trade in paper; "rejected" and "no version" mean it stays in cash.

| Role | rejected |
|---|---|
| Crypto majors: trend | 3 |
| Liquid crypto: trend | 22 |
| Liquid crypto: mean reversion | 15 |
| Large US stocks: breakouts | 17 |
| Large US stocks: mean reversion | 17 |
| Large US stocks: intraday momentum | 11 |
| Meme coins: momentum | 8 |
| Meme coins: mean reversion | 7 |

## Why the gate said no

- 139 of 300 runs had at least 30 trades in the held-out test.
- 49 of 300 runs had a positive Sharpe in the held-out test.
- The highest Deflated Sharpe of any run was 0.28; at least 0.95 is required.
- Reasons, counted per run (a run can have several):

  - edge not proven (any of: Deflated Sharpe below 0.95, test loss, walk-forward, PBO, placebo or best-trades check failed): 300
  - loses money at 2x modelled costs: 275
  - fewer than 30 trades in the held-out test: 161

Most of these strategies trade often. After fees, spread and slippage, what remains is too small, or too unstable, to tell apart from luck. That matches the published evidence summarised in STRATEGY_RESEARCH.md. The software reports this; it does not lower the bar to make trades happen.

## Every agent

The "chosen" row is the candidate the master picked by validation Sharpe. The test columns are the held-out last 20%. Test return and max drawdown are on the backtest's own capital (1% risk per trade).

| Agent | Market (bar) | Data | Chosen | Val. Sharpe | Test Sharpe | Test return | Test max DD | Test trades | WF OOS Sharpe | DSR | PBO | Verdict | Version |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| A001 | COINBASE:BTC-USD (1h) | coinbase 19994 bars 2024-07-02 to 2026-10-14 | ema_cross.adx.flip | -7.35 | -5.28 | -31.1% | 32.4% | 86 | -6.43 | 0.00 | 0.28 | REJECT | v1 rejected |
| A002 | COINBASE:ETH-USD (1h) | coinbase 19994 bars 2024-07-02 to 2026-10-14 | donchian_breakout.none.trail | -3.21 | -1.55 | -11.3% | 16.6% | 48 | -2.40 | 0.02 | - | REJECT | v1 rejected |
| A003 | COINBASE:SOL-USD (1h) | coinbase 19994 bars 2024-07-02 to 2026-10-14 | tsmom.none.trail | -4.29 | -6.35 | -22.9% | 24.2% | 58 | -5.58 | 0.00 | 0.12 | REJECT | v1 rejected |
| A004 | COINBASE:ZEC-USD (1h) | coinbase 19994 bars 2024-07-02 to 2026-10-14 | donchian_breakout.none.trail | -1.78 | 1.39 | 8.0% | 9.0% | 46 | -0.56 | 0.23 | - | REJECT | v1 rejected |
| A005 | COINBASE:XRP-USD (1h) | coinbase 19994 bars 2024-07-02 to 2026-10-14 | donchian_breakout.none.trail | -1.92 | -0.74 | -4.5% | 8.5% | 31 | -1.62 | 0.01 | - | REJECT | v1 rejected |
| A006 | COINBASE:NEAR-USD (1h) | coinbase 19993 bars 2024-07-02 to 2026-10-14 | donchian_breakout.none.trail | -3.43 | -1.24 | -6.6% | 13.1% | 46 | -1.73 | 0.00 | - | REJECT | v1 rejected |
| A007 | COINBASE:QNT-USD (1h) | coinbase 19993 bars 2024-07-02 to 2026-10-14 | tsmom.none.trail | -3.83 | -5.59 | -17.6% | 18.1% | 62 | -5.77 | 0.00 | 0.00 | REJECT | v1 rejected |
| A008 | COINBASE:HYPE-USD (1h) | coinbase 6004 bars 2026-02-05 to 2026-10-14 | donchian_breakout.none.trail | -1.86 | -6.41 | -10.1% | 10.5% | 21 | -2.33 | 0.00 | - | REJECT | v1 rejected |
| A009 | COINBASE:SUI-USD (1h) | coinbase 19994 bars 2024-07-02 to 2026-10-14 | donchian_breakout.none.trail | -1.09 | -3.10 | -13.5% | 16.0% | 39 | -2.37 | 0.00 | - | REJECT | v1 rejected |
| A010 | COINBASE:ADA-USD (1h) | coinbase 19994 bars 2024-07-02 to 2026-10-14 | donchian_breakout.none.trail | -2.76 | -2.22 | -8.7% | 9.5% | 32 | -3.03 | 0.00 | - | REJECT | v1 rejected |
| A011 | COINBASE:INJ-USD (1h) | coinbase 19994 bars 2024-07-02 to 2026-10-14 | donchian_breakout.none.trail | -2.95 | -1.99 | -10.0% | 14.7% | 45 | -2.90 | 0.00 | - | REJECT | v1 rejected |
| A012 | COINBASE:UNI-USD (1h) | coinbase 19994 bars 2024-07-02 to 2026-10-14 | tsmom.none.trail | -5.01 | -2.46 | -12.3% | 12.8% | 64 | -3.45 | 0.00 | 0.00 | REJECT | v1 rejected |
| A013 | COINBASE:STRK-USD (1h) | coinbase 19719 bars 2024-07-02 to 2026-10-14 | tsmom.none.trail | -2.77 | -3.47 | -19.5% | 22.2% | 72 | -3.20 | 0.00 | 0.00 | REJECT | v1 rejected |
| A014 | COINBASE:LINK-USD (1h) | coinbase 19994 bars 2024-07-02 to 2026-10-14 | donchian_breakout.none.trail | -3.68 | -2.78 | -12.0% | 14.2% | 40 | -2.58 | 0.00 | - | REJECT | v1 rejected |
| A015 | COINBASE:TAO-USD (1h) | coinbase 14401 bars 2025-02-20 to 2026-10-14 | donchian_breakout.none.trail | -1.26 | -1.26 | -4.3% | 7.0% | 23 | -1.91 | 0.00 | - | REJECT | v1 rejected |
| A016 | COINBASE:BAT-USD (1h) | coinbase 19985 bars 2024-07-02 to 2026-10-14 | donchian_breakout.none.trail | -3.00 | -1.14 | -4.4% | 10.0% | 34 | -2.70 | 0.00 | - | REJECT | v1 rejected |
| A017 | COINBASE:XLM-USD (1h) | coinbase 19994 bars 2024-07-02 to 2026-10-14 | donchian_breakout.none.trail | -3.40 | -0.60 | -3.6% | 10.9% | 33 | -2.43 | 0.00 | - | REJECT | v1 rejected |
| A018 | COINBASE:VVV-USD (1h) | coinbase 14791 bars 2025-01-28 to 2026-10-14 | ema_cross.adx.flip | 1.40 | -3.60 | -13.2% | 13.5% | 65 | -1.76 | 0.00 | 0.33 | REJECT | v1 rejected |
| A019 | COINBASE:LTC-USD (1h) | coinbase 19994 bars 2024-07-02 to 2026-10-14 | donchian_breakout.none.trail | -5.95 | -2.94 | -14.1% | 15.3% | 38 | -3.90 | 0.00 | - | REJECT | v1 rejected |
| A020 | COINBASE:ONDO-USD (1h) | coinbase 19994 bars 2024-07-02 to 2026-10-14 | donchian_breakout.none.trail | -5.20 | -1.47 | -7.0% | 10.7% | 35 | -3.02 | 0.00 | - | REJECT | v1 rejected |
| A021 | COINBASE:ENA-USD (1h) | coinbase 11882 bars 2025-06-05 to 2026-10-14 | ema_cross.adx.flip | -4.45 | 0.31 | 0.9% | 10.4% | 56 | -2.87 | 0.00 | 0.52 | REJECT | v1 rejected |
| A022 | COINBASE:PUMP-USD (1h) | coinbase 10925 bars 2025-07-15 to 2026-10-14 | donchian_breakout.none.trail | -4.67 | -1.64 | -4.5% | 6.0% | 29 | -2.84 | 0.00 | - | REJECT | v1 rejected |
| A023 | COINBASE:HBAR-USD (1h) | coinbase 19993 bars 2024-07-02 to 2026-10-14 | donchian_breakout.none.trail | -3.28 | -0.77 | -4.1% | 10.8% | 24 | -2.71 | 0.00 | - | REJECT | v1 rejected |
| A024 | COINBASE:USELESS-USD (1h) | coinbase 10058 bars 2025-08-20 to 2026-10-14 | ema_cross.adx.flip | -1.58 | 0.30 | 0.6% | 5.4% | 37 | -1.37 | 0.00 | 0.81 | REJECT | v1 rejected |
| A025 | COINBASE:S-USD (1h) | coinbase 11426 bars 2025-06-24 to 2026-10-14 | donchian_breakout.none.trail | -2.42 | 0.73 | 2.1% | 4.9% | 24 | -1.77 | 0.02 | - | REJECT | v1 rejected |
| A026 | COINBASE:RENDER-USD (1h) | coinbase 19994 bars 2024-07-02 to 2026-10-14 | bollinger_reversion.adx.time | -3.20 | -2.93 | -8.5% | 10.1% | 26 | -3.12 | 0.00 | 0.00 | REJECT | v1 rejected |
| A027 | COINBASE:AERO-USD (1h) | coinbase 19994 bars 2024-07-02 to 2026-10-14 | zscore_reversion.none.atr_bracket | -2.75 | -4.00 | -12.2% | 12.2% | 18 | -2.61 | 0.00 | 0.13 | REJECT | v1 rejected |
| A028 | COINBASE:AVAX-USD (1h) | coinbase 19994 bars 2024-07-02 to 2026-10-14 | zscore_reversion.none.atr_bracket | -3.46 | -2.91 | -14.3% | 18.2% | 43 | -3.54 | 0.00 | 0.01 | REJECT | v1 rejected |
| A029 | COINBASE:FIL-USD (1h) | coinbase 19993 bars 2024-07-02 to 2026-10-14 | zscore_reversion.none.atr_bracket | -2.31 | -3.28 | -7.3% | 8.2% | 15 | -2.83 | 0.00 | 0.00 | REJECT | v1 rejected |
| A030 | COINBASE:OP-USD (1h) | coinbase 19903 bars 2024-07-02 to 2026-10-14 | zscore_reversion.none.atr_bracket | -3.28 | -3.30 | -7.8% | 8.7% | 30 | -3.81 | 0.00 | 0.00 | REJECT | v1 rejected |
| A031 | COINBASE:FET-USD (1h) | coinbase 19993 bars 2024-07-02 to 2026-10-14 | zscore_reversion.none.atr_bracket | -2.77 | -5.10 | -18.7% | 19.6% | 31 | -4.38 | 0.00 | 0.23 | REJECT | v1 rejected |
| A032 | COINBASE:AMP-USD (1h) | coinbase 19853 bars 2024-07-02 to 2026-10-14 | bollinger_reversion.adx.time | -3.94 | 0.25 | 1.2% | 7.5% | 30 | -2.45 | 0.00 | 0.25 | REJECT | v1 rejected |
| A033 | COINBASE:STX-USD (1h) | coinbase 19992 bars 2024-07-02 to 2026-10-14 | bollinger_reversion.adx.time | -3.84 | -4.85 | -7.7% | 7.9% | 22 | -3.70 | 0.00 | 0.02 | REJECT | v1 rejected |
| A034 | COINBASE:SD-USD (1h) | coinbase 18247 bars 2024-07-30 to 2026-10-14 | zscore_reversion.none.atr_bracket | 0.07 | -4.00 | -1.0% | 1.0% | 22 | -1.36 | 0.00 | 0.01 | REJECT | v1 rejected |
| A035 | COINBASE:DOT-USD (1h) | coinbase 19994 bars 2024-07-02 to 2026-10-14 | zscore_reversion.none.atr_bracket | -3.94 | -5.46 | -20.7% | 21.7% | 31 | -4.34 | 0.00 | 0.00 | REJECT | v1 rejected |
| A036 | COINBASE:LIGHTER-USD (1h) | coinbase 6499 bars 2026-01-15 to 2026-10-14 | zscore_reversion.none.atr_bracket | -0.12 | -4.40 | -2.5% | 2.5% | 2 | -2.04 | 0.00 | 0.47 | REJECT | v1 rejected |
| A037 | COINBASE:ZRO-USD (1h) | coinbase 19992 bars 2024-07-02 to 2026-10-14 | zscore_reversion.none.atr_bracket | -2.71 | -3.10 | -5.4% | 6.8% | 15 | -4.17 | 0.00 | 0.06 | REJECT | v1 rejected |
| A038 | COINBASE:MON-USD (1h) | coinbase 7762 bars 2025-11-24 to 2026-10-14 | zscore_reversion.none.atr_bracket | -1.93 | -4.48 | -5.3% | 5.5% | 6 | -4.64 | 0.00 | 0.00 | REJECT | v1 rejected |
| A039 | COINBASE:AAVE-USD (1h) | coinbase 19994 bars 2024-07-02 to 2026-10-14 | zscore_reversion.none.atr_bracket | -3.45 | -5.53 | -19.9% | 20.1% | 25 | -5.13 | 0.00 | 0.55 | REJECT | v1 rejected |
| A040 | COINBASE:ICP-USD (1h) | coinbase 19983 bars 2024-07-02 to 2026-10-14 | bollinger_reversion.adx.time | -2.98 | -3.51 | -9.0% | 10.1% | 21 | -3.92 | 0.00 | 0.00 | REJECT | v1 rejected |
| A041 | COINBASE:DOGE-USD (1h) | coinbase 19994 bars 2024-07-02 to 2026-10-14 | donchian_breakout.none.trail | -2.63 | -5.39 | -20.3% | 21.0% | 32 | -3.59 | 0.00 | - | REJECT | v1 rejected |
| A042 | COINBASE:TRUMP-USD (1h) | coinbase 15100 bars 2025-01-21 to 2026-10-14 | donchian_breakout.none.trail | -4.56 | 0.12 | 0.3% | 9.2% | 24 | -1.92 | 0.01 | - | REJECT | v1 rejected |
| A043 | COINBASE:PENGU-USD (1h) | coinbase 14569 bars 2025-02-13 to 2026-10-14 | donchian_breakout.none.trail | -2.42 | -1.04 | -4.3% | 10.5% | 28 | -2.12 | 0.00 | - | REJECT | v1 rejected |
| A044 | COINBASE:PEPE-USD (1h) | coinbase 16777 bars 2024-11-13 to 2026-10-14 | donchian_breakout.none.trail | -3.04 | -0.94 | -4.9% | 10.1% | 29 | -1.38 | 0.00 | - | REJECT | v1 rejected |
| A045 | COINBASE:BONK-USD (1h) | coinbase 19994 bars 2024-07-02 to 2026-10-14 | donchian_breakout.none.trail | -3.01 | -1.57 | -6.9% | 8.6% | 28 | -2.30 | 0.00 | - | REJECT | v1 rejected |
| A046 | COINBASE:FARTCOIN-USD (1h) | coinbase 11714 bars 2025-06-12 to 2026-10-14 | tsmom.none.trail | -1.57 | -3.28 | -6.2% | 6.7% | 22 | -2.44 | 0.00 | 0.02 | REJECT | v1 rejected |
| A047 | COINBASE:GIGA-USD (1h) | coinbase 15797 bars 2024-12-11 to 2026-10-14 | donchian_breakout.none.trail | -2.06 | -3.33 | -9.2% | 9.2% | 22 | -2.28 | 0.00 | - | REJECT | v1 rejected |
| A048 | COINBASE:SHIB-USD (1h) | coinbase 19994 bars 2024-07-02 to 2026-10-14 | tsmom.none.trail | -3.83 | -1.74 | -11.0% | 13.7% | 78 | -3.98 | 0.00 | 0.05 | REJECT | v1 rejected |
| A049 | COINBASE:SPX-USD (1h) | coinbase 9576 bars 2025-09-09 to 2026-10-14 | zscore_reversion.none.atr_bracket | -2.56 | -1.33 | -2.2% | 3.6% | 11 | -2.42 | 0.00 | 0.00 | REJECT | v1 rejected |
| A050 | COINBASE:WIF-USD (1h) | coinbase 16714 bars 2024-11-13 to 2026-10-14 | zscore_reversion.none.atr_bracket | -3.04 | -3.84 | -6.6% | 6.8% | 17 | -2.81 | 0.00 | 0.00 | REJECT | v1 rejected |
| A051 | COINBASE:FLOKI-USD (1h) | coinbase 16355 bars 2024-11-21 to 2026-10-14 | zscore_reversion.none.atr_bracket | -3.88 | -3.37 | -1.4% | 1.5% | 20 | -2.77 | 0.00 | 0.00 | REJECT | v1 rejected |
| A052 | COINBASE:MOODENG-USD (1h) | coinbase 16263 bars 2024-12-04 to 2026-10-14 | zscore_reversion.none.atr_bracket | -3.88 | -2.95 | -1.8% | 1.8% | 16 | -2.85 | 0.00 | 0.00 | REJECT | v1 rejected |
| A053 | COINBASE:POPCAT-USD (1h) | coinbase 14510 bars 2025-02-13 to 2026-10-14 | zscore_reversion.none.atr_bracket | -3.58 | -4.16 | -3.1% | 3.6% | 18 | -3.95 | 0.00 | 0.15 | REJECT | v1 rejected |
| A054 | COINBASE:TURBO-USD (1h) | coinbase 16077 bars 2024-12-11 to 2026-10-14 | bollinger_reversion.adx.time | -2.15 | -3.56 | -0.8% | 1.0% | 17 | -4.47 | 0.00 | 0.02 | REJECT | v1 rejected |
| A055 | COINBASE:PNUT-USD (1h) | coinbase 14854 bars 2025-01-14 to 2026-10-14 | zscore_reversion.none.atr_bracket | -3.81 | -3.06 | -1.4% | 1.5% | 19 | -3.08 | 0.00 | 0.04 | REJECT | v1 rejected |
| A056 | US:AAPL (15m) | yahoo 1067 bars 2026-08-17 to 2026-10-13 | orb.relvol.time | 3.96 | 0.69 | 0.1% | 0.7% | 2 | 0.26 | 0.01 | - | REJECT | v1 rejected |
| A057 | US:MSFT (15m) | yahoo 1067 bars 2026-08-17 to 2026-10-13 | vol_breakout.none.atr_bracket | -0.37 | -7.53 | -2.1% | 2.1% | 6 | -0.16 | 0.00 | - | REJECT | v1 rejected |
| A058 | US:NVDA (15m) | yahoo 1067 bars 2026-08-17 to 2026-10-13 | orb.relvol.time | -0.06 | -7.12 | -1.2% | 1.9% | 3 | -4.28 | 0.00 | - | REJECT | v1 rejected |
| A059 | US:AMZN (15m) | yahoo 1067 bars 2026-08-17 to 2026-10-13 | orb.relvol.time | 0.04 | 5.94 | 1.6% | 0.7% | 5 | 0.60 | 0.06 | - | REJECT | v1 rejected |
| A060 | US:TSLA (15m) | yahoo 1067 bars 2026-08-17 to 2026-10-13 | orb.relvol.time | -7.89 | -7.32 | -1.2% | 1.3% | 3 | -6.50 | 0.00 | - | REJECT | v1 rejected |
| A061 | US:META (15m) | yahoo 1067 bars 2026-08-17 to 2026-10-13 | active_orb.none.time | 5.23 | - | 0.0% | -0.0% | 0 | 6.80 | 0.00 | 0.50 | REJECT | v1 rejected |
| A062 | US:GOOGL (15m) | yahoo 1067 bars 2026-08-17 to 2026-10-13 | orb.relvol.time | 2.26 | -4.98 | -0.6% | 0.9% | 3 | -3.20 | 0.00 | - | REJECT | v1 rejected |
| A063 | US:AMD (15m) | yahoo 1067 bars 2026-08-17 to 2026-10-13 | orb.relvol.time | 0.04 | -3.26 | -0.8% | 2.3% | 4 | -2.97 | 0.00 | - | REJECT | v1 rejected |
| A064 | US:NFLX (15m) | yahoo 1067 bars 2026-08-17 to 2026-10-13 | orb.relvol.time | -6.65 | 5.58 | 1.4% | 0.8% | 2 | 1.81 | 0.05 | - | REJECT | v1 rejected |
| A065 | US:AVGO (15m) | yahoo 1067 bars 2026-08-17 to 2026-10-13 | vol_breakout.none.atr_bracket | -4.61 | 9.06 | 3.1% | 0.9% | 5 | 1.45 | 0.11 | - | REJECT | v1 rejected |
| A066 | US:PLTR (15m) | yahoo 1067 bars 2026-08-17 to 2026-10-13 | vol_breakout.none.atr_bracket | -6.03 | -6.30 | -1.9% | 2.3% | 4 | -2.52 | 0.00 | - | REJECT | v1 rejected |
| A067 | US:COIN (15m) | yahoo 1067 bars 2026-08-17 to 2026-10-13 | vol_breakout.none.atr_bracket | -10.24 | -11.08 | -3.3% | 3.4% | 5 | -3.79 | 0.00 | - | REJECT | v1 rejected |
| A068 | US:UBER (15m) | yahoo 1067 bars 2026-08-17 to 2026-10-13 | orb.relvol.time | -5.72 | 4.22 | 0.8% | 0.7% | 2 | -0.27 | 0.02 | - | REJECT | v1 rejected |
| A069 | US:ORCL (15m) | yahoo 1067 bars 2026-08-17 to 2026-10-13 | orb.relvol.time | 1.65 | -13.17 | -2.7% | 3.1% | 4 | -0.95 | 0.00 | - | REJECT | v1 rejected |
| A070 | US:CRM (15m) | yahoo 1067 bars 2026-08-17 to 2026-10-13 | vol_breakout.none.atr_bracket | -3.70 | -8.70 | -1.9% | 1.9% | 2 | -7.09 | 0.00 | - | REJECT | v1 rejected |
| A071 | US:ADBE (15m) | yahoo 1067 bars 2026-08-17 to 2026-10-13 | orb.relvol.time | 4.30 | -1.45 | -0.2% | 0.9% | 1 | 2.37 | 0.00 | - | REJECT | v1 rejected |
| A072 | US:INTC (15m) | yahoo 1067 bars 2026-08-17 to 2026-10-13 | vol_breakout.none.atr_bracket | -5.72 | -0.65 | -0.3% | 2.0% | 4 | -0.14 | 0.00 | - | REJECT | v1 rejected |
| A073 | US:JPM (1h) | yahoo 3476 bars 2024-10-15 to 2026-10-13 | zscore_reversion.none.atr_bracket | -0.80 | 2.71 | 3.8% | 1.1% | 12 | 0.88 | 0.08 | 0.06 | RESEARCH FURTHER | v1 rejected |
| A074 | US:XOM (1h) | yahoo 3476 bars 2024-10-15 to 2026-10-13 | zscore_reversion.none.atr_bracket | 0.45 | -0.70 | -0.9% | 2.6% | 20 | -0.07 | 0.00 | 0.50 | REJECT | v1 rejected |
| A075 | US:BRK-B (1h) | yahoo 3476 bars 2024-10-15 to 2026-10-13 | rsi2_reversion.none.time | -1.67 | -1.90 | -2.9% | 4.6% | 36 | -1.43 | 0.00 | 0.19 | REJECT | v1 rejected |
| A076 | US:LLY (1h) | yahoo 3476 bars 2024-10-15 to 2026-10-13 | zscore_reversion.none.atr_bracket | -1.38 | - | 0.0% | -0.0% | 0 | -1.32 | 0.00 | 0.26 | REJECT | v1 rejected |
| A077 | US:V (1h) | yahoo 3476 bars 2024-10-15 to 2026-10-13 | rsi2_reversion.none.time | 0.25 | -1.48 | -3.1% | 4.4% | 44 | -1.16 | 0.00 | 0.40 | REJECT | v1 rejected |
| A078 | US:MA (1h) | yahoo 3476 bars 2024-10-15 to 2026-10-13 | zscore_reversion.none.atr_bracket | 0.25 | 0.10 | 0.1% | 1.2% | 8 | -0.88 | 0.00 | 0.25 | REJECT | v1 rejected |
| A079 | US:UNH (1h) | yahoo 3476 bars 2024-10-15 to 2026-10-13 | rsi2_reversion.none.time | 0.06 | -0.81 | -1.5% | 2.7% | 42 | -0.96 | 0.00 | 0.59 | REJECT | v1 rejected |
| A080 | US:COST (1h) | yahoo 3477 bars 2024-10-15 to 2026-10-13 | zscore_reversion.none.atr_bracket | -0.39 | -1.22 | -2.0% | 2.9% | 26 | 0.54 | 0.00 | 0.06 | REJECT | v1 rejected |
| A081 | US:WMT (1h) | yahoo 3477 bars 2024-10-15 to 2026-10-13 | zscore_reversion.none.atr_bracket | 2.94 | 0.49 | 0.9% | 2.5% | 34 | 1.46 | 0.00 | 0.10 | RESEARCH FURTHER | v1 rejected |
| A082 | US:HD (1h) | yahoo 3476 bars 2024-10-15 to 2026-10-13 | zscore_reversion.none.atr_bracket | -1.14 | -2.10 | -4.2% | 5.7% | 24 | -1.19 | 0.00 | 0.54 | REJECT | v1 rejected |
| A083 | US:PG (1h) | yahoo 3476 bars 2024-10-15 to 2026-10-13 | rsi2_reversion.none.time | -1.97 | 1.15 | 1.6% | 1.4% | 25 | -1.69 | 0.01 | 0.11 | REJECT | v1 rejected |
| A084 | US:JNJ (1h) | yahoo 3476 bars 2024-10-15 to 2026-10-13 | zscore_reversion.none.atr_bracket | 0.25 | -0.52 | -1.0% | 2.9% | 30 | -0.35 | 0.00 | 0.50 | REJECT | v1 rejected |
| A085 | US:KO (1h) | yahoo 3476 bars 2024-10-15 to 2026-10-13 | zscore_reversion.none.atr_bracket | -0.27 | -1.89 | -2.6% | 2.9% | 14 | -0.74 | 0.00 | 0.86 | REJECT | v1 rejected |
| A086 | US:PEP (1h) | yahoo 3477 bars 2024-10-15 to 2026-10-13 | zscore_reversion.none.atr_bracket | -0.23 | -2.70 | -5.1% | 5.1% | 29 | -1.70 | 0.00 | 0.86 | REJECT | v1 rejected |
| A087 | US:MRK (1h) | yahoo 3476 bars 2024-10-15 to 2026-10-13 | zscore_reversion.none.atr_bracket | 0.93 | 2.92 | 3.7% | 0.6% | 14 | 1.15 | 0.08 | 0.50 | RESEARCH FURTHER | v1 rejected |
| A088 | US:CVX (1h) | yahoo 3476 bars 2024-10-15 to 2026-10-13 | rsi2_reversion.none.time | 3.41 | 0.07 | 0.1% | 3.2% | 29 | 0.96 | 0.00 | 0.02 | REJECT | v1 rejected |
| A089 | US:BAC (1h) | yahoo 3476 bars 2024-10-15 to 2026-10-13 | rsi2_reversion.none.time | 0.13 | -1.26 | -2.2% | 5.6% | 22 | -0.36 | 0.00 | 0.05 | REJECT | v1 rejected |
| A090 | US:QCOM (15m) | yahoo 1067 bars 2026-08-17 to 2026-10-13 | noise_band_momentum.none.time | 4.21 | -0.13 | -0.0% | 1.0% | 4 | 0.07 | 0.14 | - | REJECT | v1 rejected |
| A091 | US:PYPL (15m) | yahoo 1067 bars 2026-08-17 to 2026-10-13 | orb.none.time | 4.76 | 2.54 | 0.6% | 0.9% | 5 | 0.54 | 0.01 | - | REJECT | v1 rejected |
| A092 | US:BA (15m) | yahoo 1067 bars 2026-08-17 to 2026-10-13 | noise_band_momentum.none.time | -5.11 | -10.54 | -1.1% | 1.2% | 4 | -5.55 | 0.00 | - | REJECT | v1 rejected |
| A093 | US:DIS (15m) | yahoo 1067 bars 2026-08-17 to 2026-10-13 | orb.none.time | -7.32 | 10.97 | 2.9% | 0.6% | 6 | -0.98 | 0.19 | - | REJECT | v1 rejected |
| A094 | US:ABBV (15m) | yahoo 1067 bars 2026-08-17 to 2026-10-13 | noise_band_momentum.none.time | -1.18 | 5.62 | 2.0% | 1.1% | 9 | -1.18 | 0.19 | - | REJECT | v1 rejected |
| A095 | US:MCD (15m) | yahoo 1067 bars 2026-08-17 to 2026-10-13 | noise_band_momentum.none.time | -2.16 | 4.76 | 1.0% | 0.4% | 2 | -0.66 | 0.12 | - | REJECT | v1 rejected |
| A096 | US:GS (15m) | yahoo 1067 bars 2026-08-17 to 2026-10-13 | orb.none.time | 3.50 | 7.55 | 0.9% | 0.3% | 2 | 1.68 | 0.03 | - | REJECT | v1 rejected |
| A097 | US:CAT (15m) | yahoo 1067 bars 2026-08-17 to 2026-10-13 | orb.none.time | 0.22 | -0.70 | -0.1% | 0.7% | 1 | -0.48 | 0.00 | - | REJECT | v1 rejected |
| A098 | US:HON (15m) | yahoo 1067 bars 2026-08-17 to 2026-10-13 | orb.none.time | 1.77 | -7.44 | -1.2% | 1.2% | 2 | -3.77 | 0.00 | - | REJECT | v1 rejected |
| A099 | US:IBM (15m) | yahoo 1067 bars 2026-08-17 to 2026-10-13 | noise_band_momentum.none.time | -7.81 | -6.90 | -2.5% | 3.3% | 8 | -4.04 | 0.00 | - | REJECT | v1 rejected |
| A100 | US:TXN (15m) | yahoo 1067 bars 2026-08-17 to 2026-10-13 | noise_band_momentum.none.time | -0.66 | -3.76 | -1.7% | 3.7% | 7 | -3.60 | 0.00 | - | REJECT | v1 rejected |

## Dataset fingerprints

| Agent | Market | SHA-256 (first 16) |
|---|---|---|
| A001 | COINBASE:BTC-USD 1h | `610fffcba70c4987` |
| A002 | COINBASE:ETH-USD 1h | `f8c49d6c820c33af` |
| A003 | COINBASE:SOL-USD 1h | `86c6934021d0a0ee` |
| A004 | COINBASE:ZEC-USD 1h | `5c67fd9bdca7e43f` |
| A005 | COINBASE:XRP-USD 1h | `529e0d4f24770093` |
| A006 | COINBASE:NEAR-USD 1h | `6957e623dd109321` |
| A007 | COINBASE:QNT-USD 1h | `b69e80927b49b34c` |
| A008 | COINBASE:HYPE-USD 1h | `e592e1b4c2021570` |
| A009 | COINBASE:SUI-USD 1h | `4b8a9a6e037720c9` |
| A010 | COINBASE:ADA-USD 1h | `48ce958c0054a3dd` |
| A011 | COINBASE:INJ-USD 1h | `7117f34c34e7349d` |
| A012 | COINBASE:UNI-USD 1h | `bbe9b056459d222f` |
| A013 | COINBASE:STRK-USD 1h | `e8c71df4f88afcd5` |
| A014 | COINBASE:LINK-USD 1h | `69beebfb14ef600d` |
| A015 | COINBASE:TAO-USD 1h | `b95ed905275290c7` |
| A016 | COINBASE:BAT-USD 1h | `3edf098b32ab0057` |
| A017 | COINBASE:XLM-USD 1h | `2c0556b4170e2005` |
| A018 | COINBASE:VVV-USD 1h | `8436edf7a0d618b9` |
| A019 | COINBASE:LTC-USD 1h | `a243541b57fd1e33` |
| A020 | COINBASE:ONDO-USD 1h | `ef650b24248cd171` |
| A021 | COINBASE:ENA-USD 1h | `b20562e23ece8af2` |
| A022 | COINBASE:PUMP-USD 1h | `2c1909f408e4bf48` |
| A023 | COINBASE:HBAR-USD 1h | `34938ae76bf34fe1` |
| A024 | COINBASE:USELESS-USD 1h | `981c33d46f92328f` |
| A025 | COINBASE:S-USD 1h | `a9f5bea1740250a2` |
| A026 | COINBASE:RENDER-USD 1h | `92c3131f559418b8` |
| A027 | COINBASE:AERO-USD 1h | `2feb3f517489364b` |
| A028 | COINBASE:AVAX-USD 1h | `942f0c3a066ad039` |
| A029 | COINBASE:FIL-USD 1h | `53f098a9405972e7` |
| A030 | COINBASE:OP-USD 1h | `95047774dd48ee8b` |
| A031 | COINBASE:FET-USD 1h | `2148856a9b45e476` |
| A032 | COINBASE:AMP-USD 1h | `483bdb8fbf71c777` |
| A033 | COINBASE:STX-USD 1h | `566ce6b72a91225d` |
| A034 | COINBASE:SD-USD 1h | `cffeaf2d5b0dd4ad` |
| A035 | COINBASE:DOT-USD 1h | `04a9ebbb753cc8ba` |
| A036 | COINBASE:LIGHTER-USD 1h | `93bf63a66e0cdc3e` |
| A037 | COINBASE:ZRO-USD 1h | `9fbd7caa8d3a661e` |
| A038 | COINBASE:MON-USD 1h | `5643a70ab412074b` |
| A039 | COINBASE:AAVE-USD 1h | `b3f30ca5f3937a07` |
| A040 | COINBASE:ICP-USD 1h | `5b3ac0356316ab29` |
| A041 | COINBASE:DOGE-USD 1h | `8afa66021c6114b1` |
| A042 | COINBASE:TRUMP-USD 1h | `322b9405a82ca3ee` |
| A043 | COINBASE:PENGU-USD 1h | `f44bc5982a8a50d8` |
| A044 | COINBASE:PEPE-USD 1h | `e24a5076cd3b6893` |
| A045 | COINBASE:BONK-USD 1h | `4082151e7f983fe5` |
| A046 | COINBASE:FARTCOIN-USD 1h | `e832c6eca7de7465` |
| A047 | COINBASE:GIGA-USD 1h | `3b6f29742629d40e` |
| A048 | COINBASE:SHIB-USD 1h | `3a0d29c8042a6336` |
| A049 | COINBASE:SPX-USD 1h | `41df0504bd10e138` |
| A050 | COINBASE:WIF-USD 1h | `fb2da18eee91612c` |
| A051 | COINBASE:FLOKI-USD 1h | `ad9137c7debc19eb` |
| A052 | COINBASE:MOODENG-USD 1h | `a60429e466d9e65f` |
| A053 | COINBASE:POPCAT-USD 1h | `61c3ca3e437c7460` |
| A054 | COINBASE:TURBO-USD 1h | `55d6afbc8f2b1661` |
| A055 | COINBASE:PNUT-USD 1h | `2d7bfd6f679ce7d5` |
| A056 | US:AAPL 15m | `c73a2ce48b2aa014` |
| A057 | US:MSFT 15m | `908ff47790d98550` |
| A058 | US:NVDA 15m | `28ef5ef2ebb5245d` |
| A059 | US:AMZN 15m | `758a1a693632e0e7` |
| A060 | US:TSLA 15m | `0588215838ce9d78` |
| A061 | US:META 15m | `bf6ce2ea679d2023` |
| A062 | US:GOOGL 15m | `eb7cf0ffc64af8f5` |
| A063 | US:AMD 15m | `4701127e1d555ff7` |
| A064 | US:NFLX 15m | `6530b2aace199b9c` |
| A065 | US:AVGO 15m | `e853b0a916dfb281` |
| A066 | US:PLTR 15m | `684423bce253522c` |
| A067 | US:COIN 15m | `610b861cc0c12cbd` |
| A068 | US:UBER 15m | `bda70c5d979933aa` |
| A069 | US:ORCL 15m | `6d9581cd20dc776c` |
| A070 | US:CRM 15m | `e57d407d3382a14d` |
| A071 | US:ADBE 15m | `7ca228308f80c816` |
| A072 | US:INTC 15m | `083436038da8bd5f` |
| A073 | US:JPM 1h | `afc95e063ef3976f` |
| A074 | US:XOM 1h | `c3a0ce9c22f45239` |
| A075 | US:BRK-B 1h | `21edc488d4804079` |
| A076 | US:LLY 1h | `c41aec0ff0025ca9` |
| A077 | US:V 1h | `c535ed76c5603da0` |
| A078 | US:MA 1h | `47aa4be17901c9bf` |
| A079 | US:UNH 1h | `2b2e9b2c4a447086` |
| A080 | US:COST 1h | `7c013ad7668881e1` |
| A081 | US:WMT 1h | `cd6ea59024249cfa` |
| A082 | US:HD 1h | `993b28de3ef488b9` |
| A083 | US:PG 1h | `5f1826f0f8a4a297` |
| A084 | US:JNJ 1h | `9016077c373b0ac9` |
| A085 | US:KO 1h | `5c33802cc5a1355f` |
| A086 | US:PEP 1h | `980c8218021e0962` |
| A087 | US:MRK 1h | `8d86d6b7525e3e35` |
| A088 | US:CVX 1h | `9e41cfc761c9f5f0` |
| A089 | US:BAC 1h | `d57804b21d2cf4bf` |
| A090 | US:QCOM 15m | `81acc55b781237e0` |
| A091 | US:PYPL 15m | `ed07922c74433a85` |
| A092 | US:BA 15m | `3e6d9482047e4606` |
| A093 | US:DIS 15m | `4c4aa866f09ed112` |
| A094 | US:ABBV 15m | `9e8389e3cf50b6bb` |
| A095 | US:MCD 15m | `b82319a1d024194b` |
| A096 | US:GS 15m | `8a542ef8643ccb90` |
| A097 | US:CAT 15m | `b8155a907336675e` |
| A098 | US:HON 15m | `d4bbd1b8d83e70ec` |
| A099 | US:IBM 15m | `61343cae6d1c5565` |
| A100 | US:TXN 15m | `e23686e4ee951ec4` |

## Reading this honestly

- These are backtests on past data under stated cost assumptions. They are not a forecast and not a promise of returns.
- An agent that is rejected stays in cash. That is the intended result when the evidence is not strong enough.
- Data windows are short for 15-minute bars (the free provider keeps about 60 days), so those agents have few test trades. Most of them cannot pass the 30-trade minimum.
- The app retrains every agent on fresh data every 7 days. A newer version must first beat the active one in shadow on bars it was not trained on.
