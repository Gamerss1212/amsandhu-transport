# Agent training report (100 agents)

Generated 2026-10-13 04:45 UTC by `scripts/train_agents.py`, using the app's own research engine on real market data. The run took 21 minutes.

## Method

- **Datasets.** Each agent trains on its own market and bar size, using up to 20,000 hourly or 6,000 15-minute bars.
  - The data comes from public sources: Coinbase for crypto, Yahoo Finance for stocks, ETFs, FX and futures.
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
| Index and sector ETFs: intraday momentum | 15 |
| Large US stocks: breakouts | 17 |
| Large US stocks: mean reversion | 17 |
| Forex: session momentum | 5 |
| Equity-index futures: opening breakouts | 6 |

## Why the gate said no

- 131 of 300 runs had at least 30 trades in the held-out test.
- 59 of 300 runs had a positive Sharpe in the held-out test.
- The highest Deflated Sharpe of any run was 0.20; at least 0.95 is required.
- Reasons, counted per run (a run can have several):

  - edge not proven (any of: Deflated Sharpe below 0.95, test loss, walk-forward, PBO, placebo or best-trades check failed): 300
  - loses money at 2x modelled costs: 264
  - fewer than 30 trades in the held-out test: 169
  - one contract is larger than the sized position: 3

Most of these strategies trade often. After fees, spread and slippage, what remains is too small, or too unstable, to tell apart from luck. That matches the published evidence summarised in STRATEGY_RESEARCH.md. The software reports this; it does not lower the bar to make trades happen.

## Earlier pass (kept on record)

A first pass on 2026-10-13 04:12 UTC used shorter windows (5,000 hourly or 2,000 15-minute bars). Its results were:

- Run verdicts: REJECT: 297, RESEARCH FURTHER: 3.
- Versions: rejected: 100.
- Most runs had fewer than 30 trades in the held-out test, so they could never pass.

The master now trains on the longest history the engine accepts. The first pass's trials stay in the ledger, so this pass faces a stricter Deflated Sharpe hurdle, not a looser one. No gate was changed.

## Every agent

The "chosen" row is the candidate the master picked by validation Sharpe. The test columns are the held-out last 20%. Test return and max drawdown are on the backtest's own capital (1% risk per trade).

| Agent | Market (bar) | Data | Chosen | Val. Sharpe | Test Sharpe | Test return | Test max DD | Test trades | WF OOS Sharpe | DSR | PBO | Verdict | Version |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| A001 | COINBASE:BTC-USD (1h) | coinbase 19994 bars 2024-07-01 to 2026-10-13 | ema_cross.adx.flip | -7.35 | -5.28 | -31.1% | 32.4% | 86 | -6.48 | 0.00 | 0.35 | REJECT | v2 rejected |
| A002 | COINBASE:ETH-USD (1h) | coinbase 19994 bars 2024-07-01 to 2026-10-13 | donchian_breakout.none.trail | -3.21 | -1.55 | -11.3% | 16.6% | 48 | -2.42 | 0.00 | - | REJECT | v2 rejected |
| A003 | COINBASE:SOL-USD (1h) | coinbase 19994 bars 2024-07-01 to 2026-10-13 | tsmom.none.trail | -4.29 | -6.35 | -22.9% | 24.2% | 58 | -5.62 | 0.00 | 0.12 | REJECT | v2 rejected |
| A004 | COINBASE:ZEC-USD (1h) | coinbase 19994 bars 2024-07-01 to 2026-10-13 | tsmom.none.trail | -1.03 | 1.62 | 9.4% | 15.0% | 59 | -0.91 | 0.02 | 0.09 | REJECT | v2 rejected |
| A005 | COINBASE:XRP-USD (1h) | coinbase 19994 bars 2024-07-01 to 2026-10-13 | donchian_breakout.none.trail | -1.92 | -0.74 | -4.5% | 8.5% | 31 | -1.63 | 0.00 | - | REJECT | v2 rejected |
| A006 | COINBASE:NEAR-USD (1h) | coinbase 19993 bars 2024-07-01 to 2026-10-13 | donchian_breakout.none.trail | -3.43 | -1.24 | -6.6% | 13.1% | 46 | -1.80 | 0.00 | - | REJECT | v2 rejected |
| A007 | COINBASE:HYPE-USD (1h) | coinbase 5980 bars 2026-02-05 to 2026-10-13 | ema_cross.adx.flip | -2.17 | -3.45 | -6.6% | 7.7% | 28 | -2.80 | 0.00 | 0.72 | REJECT | v2 rejected |
| A008 | COINBASE:SUI-USD (1h) | coinbase 19994 bars 2024-07-01 to 2026-10-13 | donchian_breakout.none.trail | -1.09 | -3.10 | -13.5% | 16.0% | 39 | -2.47 | 0.00 | - | REJECT | v2 rejected |
| A009 | COINBASE:STRK-USD (1h) | coinbase 19719 bars 2024-07-01 to 2026-10-13 | tsmom.none.trail | -2.64 | -3.10 | -17.4% | 20.2% | 74 | -2.29 | 0.00 | 0.00 | REJECT | v2 rejected |
| A010 | COINBASE:QNT-USD (1h) | coinbase 19993 bars 2024-07-01 to 2026-10-13 | tsmom.none.trail | -4.05 | -5.59 | -17.6% | 18.1% | 62 | -5.69 | 0.00 | 0.00 | REJECT | v2 rejected |
| A011 | COINBASE:ADA-USD (1h) | coinbase 19994 bars 2024-07-01 to 2026-10-13 | donchian_breakout.none.trail | -2.76 | -2.22 | -8.7% | 9.5% | 32 | -3.06 | 0.00 | - | REJECT | v2 rejected |
| A012 | COINBASE:PUMP-USD (1h) | coinbase 10901 bars 2025-07-15 to 2026-10-13 | donchian_breakout.none.trail | -4.24 | -1.43 | -4.0% | 6.0% | 29 | -3.01 | 0.00 | - | REJECT | v2 rejected |
| A013 | COINBASE:XLM-USD (1h) | coinbase 19994 bars 2024-07-01 to 2026-10-13 | donchian_breakout.none.trail | -3.40 | -0.60 | -3.6% | 10.9% | 33 | -2.54 | 0.00 | - | REJECT | v2 rejected |
| A014 | COINBASE:ONDO-USD (1h) | coinbase 19994 bars 2024-07-01 to 2026-10-13 | donchian_breakout.none.trail | -5.20 | -1.49 | -7.1% | 10.7% | 35 | -3.08 | 0.00 | - | REJECT | v2 rejected |
| A015 | COINBASE:UNI-USD (1h) | coinbase 19994 bars 2024-07-01 to 2026-10-13 | tsmom.none.trail | -5.12 | -2.46 | -12.3% | 12.8% | 64 | -3.57 | 0.00 | 0.00 | REJECT | v2 rejected |
| A016 | COINBASE:LINK-USD (1h) | coinbase 19994 bars 2024-07-01 to 2026-10-13 | donchian_breakout.none.trail | -3.68 | -2.78 | -12.0% | 14.2% | 40 | -2.56 | 0.00 | - | REJECT | v2 rejected |
| A017 | COINBASE:ENA-USD (1h) | coinbase 11858 bars 2025-06-05 to 2026-10-13 | ema_cross.adx.flip | -4.34 | 0.31 | 0.9% | 10.4% | 56 | -2.86 | 0.00 | 0.52 | REJECT | v2 rejected |
| A018 | COINBASE:DOGE-USD (1h) | coinbase 19994 bars 2024-07-01 to 2026-10-13 | donchian_breakout.none.trail | -2.97 | -4.80 | -18.9% | 20.6% | 33 | -3.71 | 0.00 | - | REJECT | v2 rejected |
| A019 | COINBASE:TAO-USD (1h) | coinbase 14377 bars 2025-02-20 to 2026-10-13 | donchian_breakout.none.trail | -1.02 | -1.39 | -4.7% | 7.1% | 24 | -1.83 | 0.00 | - | REJECT | v2 rejected |
| A020 | COINBASE:LTC-USD (1h) | coinbase 19994 bars 2024-07-01 to 2026-10-13 | donchian_breakout.none.trail | -5.64 | -2.94 | -14.1% | 15.3% | 38 | -3.96 | 0.00 | - | REJECT | v2 rejected |
| A021 | COINBASE:ZRO-USD (1h) | coinbase 19992 bars 2024-07-01 to 2026-10-13 | tsmom.none.trail | -3.41 | -3.44 | -14.8% | 19.4% | 80 | -3.97 | 0.00 | 0.09 | REJECT | v2 rejected |
| A022 | COINBASE:AVAX-USD (1h) | coinbase 19994 bars 2024-07-01 to 2026-10-13 | donchian_breakout.none.trail | -3.47 | -5.82 | -17.3% | 17.3% | 25 | -3.28 | 0.00 | - | REJECT | v2 rejected |
| A023 | COINBASE:HBAR-USD (1h) | coinbase 19993 bars 2024-07-01 to 2026-10-13 | donchian_breakout.none.trail | -3.28 | -0.77 | -4.1% | 10.8% | 24 | -2.51 | 0.00 | - | REJECT | v2 rejected |
| A024 | COINBASE:W-USD (1h) | coinbase 11204 bars 2025-07-02 to 2026-10-13 | donchian_breakout.none.trail | -3.96 | -1.62 | -3.7% | 5.6% | 27 | -3.96 | 0.00 | - | REJECT | v2 rejected |
| A025 | COINBASE:RENDER-USD (1h) | coinbase 19994 bars 2024-07-01 to 2026-10-13 | donchian_breakout.none.trail | -3.89 | -0.89 | -4.5% | 8.6% | 39 | -2.60 | 0.00 | - | REJECT | v2 rejected |
| A026 | COINBASE:VVV-USD (1h) | coinbase 14767 bars 2025-01-28 to 2026-10-13 | zscore_reversion.none.atr_bracket | -1.36 | -1.99 | -6.3% | 8.2% | 24 | -1.91 | 0.00 | 0.17 | REJECT | v2 rejected |
| A027 | COINBASE:GTC-USD (1h) | coinbase 16550 bars 2024-07-01 to 2026-10-13 | bollinger_reversion.adx.time | -2.96 | -4.10 | -3.7% | 3.7% | 25 | -4.16 | 0.00 | 0.32 | REJECT | v2 rejected |
| A028 | COINBASE:TIA-USD (1h) | coinbase 19994 bars 2024-07-01 to 2026-10-13 | zscore_reversion.none.atr_bracket | -4.15 | -1.35 | -4.0% | 6.6% | 19 | -3.96 | 0.00 | 0.01 | REJECT | v2 rejected |
| A029 | COINBASE:FET-USD (1h) | coinbase 19993 bars 2024-07-01 to 2026-10-13 | zscore_reversion.none.atr_bracket | -2.77 | -5.13 | -18.6% | 19.6% | 30 | -4.23 | 0.00 | 0.25 | REJECT | v2 rejected |
| A030 | COINBASE:AERO-USD (1h) | coinbase 19994 bars 2024-07-01 to 2026-10-13 | zscore_reversion.none.atr_bracket | -2.75 | -4.00 | -12.2% | 12.2% | 18 | -2.61 | 0.00 | 0.12 | REJECT | v2 rejected |
| A031 | COINBASE:STX-USD (1h) | coinbase 19992 bars 2024-07-01 to 2026-10-13 | bollinger_reversion.adx.time | -3.69 | -4.92 | -7.9% | 8.0% | 22 | -3.64 | 0.00 | 0.03 | REJECT | v2 rejected |
| A032 | COINBASE:FIL-USD (1h) | coinbase 19993 bars 2024-07-01 to 2026-10-13 | zscore_reversion.none.atr_bracket | -2.31 | -3.28 | -7.3% | 8.2% | 15 | -2.86 | 0.00 | 0.00 | REJECT | v2 rejected |
| A033 | COINBASE:ICP-USD (1h) | coinbase 19983 bars 2024-07-01 to 2026-10-13 | bollinger_reversion.adx.time | -2.95 | -3.56 | -9.2% | 10.1% | 22 | -3.93 | 0.00 | 0.00 | REJECT | v2 rejected |
| A034 | COINBASE:USELESS-USD (1h) | coinbase 10034 bars 2025-08-20 to 2026-10-13 | zscore_reversion.none.atr_bracket | -0.11 | -1.30 | -2.2% | 3.2% | 8 | -0.76 | 0.00 | 0.00 | REJECT | v2 rejected |
| A035 | COINBASE:AAVE-USD (1h) | coinbase 19994 bars 2024-07-01 to 2026-10-13 | zscore_reversion.none.atr_bracket | -3.48 | -5.65 | -20.5% | 20.5% | 26 | -5.22 | 0.00 | 0.56 | REJECT | v2 rejected |
| A036 | COINBASE:LIGHTER-USD (1h) | coinbase 6475 bars 2026-01-15 to 2026-10-13 | zscore_reversion.none.atr_bracket | -0.12 | -4.41 | -2.5% | 2.5% | 2 | -2.17 | 0.00 | 0.50 | REJECT | v2 rejected |
| A037 | COINBASE:INJ-USD (1h) | coinbase 19994 bars 2024-07-01 to 2026-10-13 | bollinger_reversion.adx.time | -3.80 | -2.79 | -6.7% | 7.9% | 15 | -4.16 | 0.00 | 0.02 | REJECT | v2 rejected |
| A038 | COINBASE:RSR-USD (1h) | coinbase 12886 bars 2025-04-22 to 2026-10-13 | zscore_reversion.none.atr_bracket | -3.19 | -3.80 | -1.9% | 1.9% | 14 | -3.71 | 0.00 | 0.63 | REJECT | v2 rejected |
| A039 | COINBASE:PYTH-USD (1h) | coinbase 14364 bars 2025-02-20 to 2026-10-13 | bollinger_reversion.adx.time | -0.60 | -2.77 | -2.8% | 2.9% | 11 | -3.05 | 0.00 | 0.00 | REJECT | v2 rejected |
| A040 | COINBASE:PEPE-USD (1h) | coinbase 16753 bars 2024-11-13 to 2026-10-13 | zscore_reversion.none.atr_bracket | -2.60 | -5.04 | -13.2% | 13.2% | 18 | -3.23 | 0.00 | 0.31 | REJECT | v2 rejected |
| A041 | US:SPY (15m) | yahoo 1041 bars 2026-08-17 to 2026-10-12 | orb.none.time | -3.67 | -1.70 | -0.2% | 0.5% | 5 | -0.32 | 0.00 | - | REJECT | v2 rejected |
| A042 | US:QQQ (15m) | yahoo 1041 bars 2026-08-17 to 2026-10-12 | orb.none.time | 3.00 | -0.90 | -0.1% | 0.8% | 4 | 0.74 | 0.00 | - | REJECT | v2 rejected |
| A043 | US:IWM (15m) | yahoo 1041 bars 2026-08-17 to 2026-10-12 | noise_band_momentum.none.time | -5.63 | -0.59 | -0.1% | 0.6% | 4 | -3.18 | 0.01 | - | REJECT | v2 rejected |
| A044 | US:DIA (15m) | yahoo 1041 bars 2026-08-17 to 2026-10-12 | noise_band_momentum.none.time | -0.50 | 6.29 | 0.5% | 0.4% | 5 | -0.97 | 0.10 | - | REJECT | v2 rejected |
| A045 | US:XLK (15m) | yahoo 1041 bars 2026-08-17 to 2026-10-12 | orb.none.time | -0.15 | -8.53 | -1.5% | 1.5% | 5 | 0.43 | 0.00 | - | REJECT | v2 rejected |
| A046 | US:XLF (15m) | yahoo 1041 bars 2026-08-17 to 2026-10-12 | orb.none.time | 0.40 | 7.43 | 0.8% | 0.3% | 4 | 3.58 | 0.03 | - | REJECT | v2 rejected |
| A047 | US:XLE (15m) | yahoo 1041 bars 2026-08-17 to 2026-10-12 | noise_band_momentum.none.time | -9.81 | 0.56 | 0.1% | 1.0% | 9 | -2.23 | 0.01 | - | REJECT | v2 rejected |
| A048 | US:XLV (15m) | yahoo 1041 bars 2026-08-17 to 2026-10-12 | orb.none.time | 1.64 | -0.60 | -0.1% | 1.6% | 4 | -1.35 | 0.00 | - | REJECT | v2 rejected |
| A049 | US:XLY (15m) | yahoo 1041 bars 2026-08-17 to 2026-10-12 | noise_band_momentum.none.time | -0.71 | -1.23 | -0.2% | 0.8% | 7 | -1.43 | 0.00 | - | REJECT | v2 rejected |
| A050 | US:XLI (15m) | yahoo 1041 bars 2026-08-17 to 2026-10-12 | orb.none.time | -12.22 | -4.97 | -1.0% | 1.4% | 5 | -4.47 | 0.00 | - | REJECT | v2 rejected |
| A051 | US:SMH (15m) | yahoo 1041 bars 2026-08-17 to 2026-10-12 | noise_band_momentum.none.time | 4.25 | -4.79 | -0.9% | 1.1% | 2 | -1.05 | 0.00 | - | REJECT | v2 rejected |
| A052 | US:XBI (15m) | yahoo 1041 bars 2026-08-17 to 2026-10-12 | orb.none.time | 2.13 | 0.38 | 0.0% | 0.4% | 2 | -0.14 | 0.00 | - | REJECT | v2 rejected |
| A053 | US:KRE (15m) | yahoo 1041 bars 2026-08-17 to 2026-10-12 | orb.none.time | -4.38 | -8.46 | -1.2% | 1.2% | 3 | -5.65 | 0.00 | - | REJECT | v2 rejected |
| A054 | US:GLD (15m) | yahoo 1041 bars 2026-08-17 to 2026-10-12 | noise_band_momentum.none.time | -6.12 | -3.96 | -0.4% | 0.7% | 2 | -4.83 | 0.00 | - | REJECT | v2 rejected |
| A055 | US:TLT (15m) | yahoo 1041 bars 2026-08-17 to 2026-10-12 | noise_band_momentum.none.time | -5.17 | -1.01 | -0.2% | 1.1% | 7 | -1.70 | 0.00 | - | REJECT | v2 rejected |
| A056 | US:AAPL (15m) | yahoo 1041 bars 2026-08-17 to 2026-10-12 | orb.relvol.time | 4.01 | 0.70 | 0.1% | 0.7% | 2 | -0.79 | 0.00 | - | REJECT | v2 rejected |
| A057 | US:MSFT (15m) | yahoo 1041 bars 2026-08-17 to 2026-10-12 | vol_breakout.none.atr_bracket | -0.38 | -5.35 | -1.4% | 2.1% | 5 | -0.13 | 0.00 | - | REJECT | v2 rejected |
| A058 | US:NVDA (15m) | yahoo 1041 bars 2026-08-17 to 2026-10-12 | orb.relvol.time | 3.65 | -4.07 | -0.6% | 1.2% | 3 | -5.12 | 0.00 | - | REJECT | v2 rejected |
| A059 | US:AMZN (15m) | yahoo 1041 bars 2026-08-17 to 2026-10-12 | orb.relvol.time | 1.30 | 9.63 | 2.2% | 0.5% | 4 | 2.06 | 0.08 | - | REJECT | v2 rejected |
| A060 | US:TSLA (15m) | yahoo 1041 bars 2026-08-17 to 2026-10-12 | vol_breakout.none.atr_bracket | -5.96 | 5.41 | 2.0% | 1.1% | 4 | -3.98 | 0.01 | - | REJECT | v2 rejected |
| A061 | US:META (15m) | yahoo 1041 bars 2026-08-17 to 2026-10-12 | active_orb.none.time | 10.68 | - | 0.0% | -0.0% | 0 | 6.69 | 0.00 | 0.50 | REJECT | v2 rejected |
| A062 | US:GOOGL (15m) | yahoo 1041 bars 2026-08-17 to 2026-10-12 | orb.relvol.time | 2.50 | -5.04 | -0.6% | 0.9% | 3 | -4.06 | 0.00 | - | REJECT | v2 rejected |
| A063 | US:AMD (15m) | yahoo 1041 bars 2026-08-17 to 2026-10-12 | active_orb.none.time | 4.62 | - | 0.0% | -0.0% | 0 | 0.12 | 0.00 | 0.86 | REJECT | v2 rejected |
| A064 | US:NFLX (15m) | yahoo 1041 bars 2026-08-17 to 2026-10-12 | orb.relvol.time | -5.35 | 5.64 | 1.4% | 0.8% | 2 | 3.60 | 0.02 | - | REJECT | v2 rejected |
| A065 | US:AVGO (15m) | yahoo 1041 bars 2026-08-17 to 2026-10-12 | orb.relvol.time | -1.77 | 6.41 | 2.3% | 1.0% | 3 | 1.71 | 0.02 | - | REJECT | v2 rejected |
| A066 | US:PLTR (15m) | yahoo 1041 bars 2026-08-17 to 2026-10-12 | vol_breakout.none.atr_bracket | -4.90 | -6.38 | -1.9% | 2.3% | 4 | -3.47 | 0.00 | - | REJECT | v2 rejected |
| A067 | US:COIN (15m) | yahoo 1041 bars 2026-08-17 to 2026-10-12 | vol_breakout.none.atr_bracket | -7.70 | -9.28 | -3.3% | 4.5% | 5 | -5.38 | 0.00 | - | REJECT | v2 rejected |
| A068 | US:UBER (15m) | yahoo 1041 bars 2026-08-17 to 2026-10-12 | orb.relvol.time | -5.78 | 4.27 | 0.8% | 0.7% | 2 | 0.29 | 0.01 | - | REJECT | v2 rejected |
| A069 | US:ORCL (15m) | yahoo 1041 bars 2026-08-17 to 2026-10-12 | orb.relvol.time | 0.92 | -13.47 | -3.1% | 3.2% | 3 | -1.40 | 0.00 | - | REJECT | v2 rejected |
| A070 | US:CRM (15m) | yahoo 1041 bars 2026-08-17 to 2026-10-12 | vol_breakout.none.atr_bracket | -3.80 | -5.61 | -0.8% | 0.8% | 1 | -4.25 | 0.00 | - | REJECT | v2 rejected |
| A071 | US:ADBE (15m) | yahoo 1041 bars 2026-08-17 to 2026-10-12 | orb.relvol.time | 4.34 | -1.46 | -0.2% | 0.9% | 1 | 2.44 | 0.00 | - | REJECT | v2 rejected |
| A072 | US:INTC (15m) | yahoo 1041 bars 2026-08-17 to 2026-10-12 | active_orb.none.time | -1.66 | - | 0.0% | -0.0% | 0 | 2.70 | 0.00 | 0.08 | REJECT | v2 rejected |
| A073 | US:JPM (1h) | yahoo 3476 bars 2024-10-14 to 2026-10-12 | zscore_reversion.none.atr_bracket | -0.80 | 2.71 | 3.8% | 1.1% | 12 | 0.77 | 0.05 | 0.08 | RESEARCH FURTHER | v2 rejected |
| A074 | US:XOM (1h) | yahoo 3476 bars 2024-10-14 to 2026-10-12 | zscore_reversion.none.atr_bracket | 1.64 | -0.48 | -0.7% | 2.3% | 28 | -0.14 | 0.00 | 0.36 | REJECT | v2 rejected |
| A075 | US:BRK-B (1h) | yahoo 3476 bars 2024-10-14 to 2026-10-12 | rsi2_reversion.none.time | -1.81 | -1.90 | -2.9% | 4.6% | 36 | -1.46 | 0.00 | 0.20 | REJECT | v2 rejected |
| A076 | US:LLY (1h) | yahoo 3476 bars 2024-10-14 to 2026-10-12 | zscore_reversion.none.atr_bracket | -1.38 | - | 0.0% | -0.0% | 0 | -1.32 | 0.00 | 0.30 | REJECT | v2 rejected |
| A077 | US:V (1h) | yahoo 3476 bars 2024-10-14 to 2026-10-12 | rsi2_reversion.none.time | 0.30 | -1.39 | -2.9% | 4.4% | 45 | -1.18 | 0.00 | 0.42 | REJECT | v2 rejected |
| A078 | US:MA (1h) | yahoo 3476 bars 2024-10-14 to 2026-10-12 | zscore_reversion.none.atr_bracket | 0.25 | 0.09 | 0.1% | 1.2% | 8 | -0.82 | 0.00 | 0.23 | REJECT | v2 rejected |
| A079 | US:UNH (1h) | yahoo 3476 bars 2024-10-14 to 2026-10-12 | rsi2_reversion.none.time | 0.09 | -0.63 | -1.2% | 2.7% | 42 | -1.21 | 0.00 | 0.59 | REJECT | v2 rejected |
| A080 | US:COST (1h) | yahoo 3477 bars 2024-10-14 to 2026-10-12 | zscore_reversion.none.atr_bracket | -0.39 | -1.22 | -2.0% | 2.9% | 26 | 0.58 | 0.00 | 0.08 | REJECT | v2 rejected |
| A081 | US:WMT (1h) | yahoo 3477 bars 2024-10-14 to 2026-10-12 | zscore_reversion.none.atr_bracket | 2.97 | 0.46 | 0.8% | 2.5% | 35 | 1.26 | 0.00 | 0.11 | RESEARCH FURTHER | v2 rejected |
| A082 | US:HD (1h) | yahoo 3476 bars 2024-10-14 to 2026-10-12 | zscore_reversion.none.atr_bracket | -1.26 | -2.38 | -2.9% | 2.9% | 11 | -1.09 | 0.00 | 0.58 | REJECT | v2 rejected |
| A083 | US:PG (1h) | yahoo 3476 bars 2024-10-14 to 2026-10-12 | rsi2_reversion.none.time | -1.97 | 1.16 | 1.6% | 1.4% | 25 | -1.82 | 0.00 | 0.12 | REJECT | v2 rejected |
| A084 | US:JNJ (1h) | yahoo 3476 bars 2024-10-14 to 2026-10-12 | zscore_reversion.none.atr_bracket | 0.24 | 0.07 | 0.1% | 2.0% | 29 | -0.17 | 0.00 | 0.36 | REJECT | v2 rejected |
| A085 | US:KO (1h) | yahoo 3476 bars 2024-10-14 to 2026-10-12 | rsi2_reversion.none.time | -0.11 | -0.41 | -0.6% | 1.7% | 25 | -1.18 | 0.00 | 0.10 | REJECT | v2 rejected |
| A086 | US:PEP (1h) | yahoo 3477 bars 2024-10-14 to 2026-10-12 | zscore_reversion.none.atr_bracket | -3.04 | -0.73 | -1.3% | 3.4% | 37 | -1.54 | 0.00 | 0.91 | REJECT | v2 rejected |
| A087 | US:MRK (1h) | yahoo 3476 bars 2024-10-14 to 2026-10-12 | zscore_reversion.none.atr_bracket | 0.93 | 2.92 | 3.7% | 0.6% | 14 | 1.15 | 0.06 | 0.44 | RESEARCH FURTHER | v2 rejected |
| A088 | US:CVX (1h) | yahoo 3476 bars 2024-10-14 to 2026-10-12 | rsi2_reversion.none.time | 3.41 | 0.07 | 0.1% | 3.2% | 29 | 1.04 | 0.00 | 0.02 | REJECT | v2 rejected |
| A089 | US:BAC (1h) | yahoo 3476 bars 2024-10-14 to 2026-10-12 | rsi2_reversion.none.time | 0.08 | -1.26 | -2.2% | 5.6% | 22 | -0.55 | 0.00 | 0.07 | REJECT | v2 rejected |
| A090 | FX:EURUSD (1h) | yahoo 12293 bars 2024-10-14 to 2026-10-13 | tsmom.none.trail | 0.54 | -1.37 | -14.6% | 18.0% | 199 | -0.17 | 0.00 | 0.71 | REJECT | v2 rejected |
| A091 | FX:GBPUSD (1h) | yahoo 12295 bars 2024-10-14 to 2026-10-13 | london_open_momentum.none.time | 0.46 | -0.10 | -1.7% | 10.3% | 103 | 0.24 | 0.03 | - | REJECT | v2 rejected |
| A092 | FX:USDJPY (1h) | yahoo 12226 bars 2024-10-14 to 2026-10-13 | london_open_momentum.none.time | 1.03 | -0.82 | -8.1% | 9.3% | 103 | 0.26 | 0.00 | - | REJECT | v2 rejected |
| A093 | FX:USDCAD (1h) | yahoo 12358 bars 2024-10-14 to 2026-10-13 | tsmom.none.trail | 0.78 | 0.56 | 3.7% | 7.7% | 71 | 0.16 | 0.01 | 0.15 | REJECT | v2 rejected |
| A094 | FX:AUDUSD (1h) | yahoo 12357 bars 2024-10-14 to 2026-10-13 | london_open_momentum.none.time | 0.13 | 0.25 | 2.8% | 8.5% | 103 | -0.34 | 0.06 | - | REJECT | v2 rejected |
| A095 | CME:ES (15m) | yahoo 3684 bars 2026-08-16 to 2026-10-13 | initial_balance_breakout.none.time | 3.70 | 2.19 | 1.3% | 1.8% | 9 | 1.55 | 0.01 | - | REJECT | v2 rejected |
| A096 | CME:MES (15m) | yahoo 3683 bars 2026-08-16 to 2026-10-13 | initial_balance_breakout.none.time | 3.35 | 1.47 | 1.0% | 2.3% | 9 | 1.43 | 0.00 | - | REJECT | v2 rejected |
| A097 | CME:NQ (15m) | yahoo 3684 bars 2026-08-16 to 2026-10-13 | orb.none.time | - | - | 0.0% | -0.0% | 0 | 0.00 | 0.00 | - | REJECT | v2 rejected |
| A098 | CME:MNQ (15m) | yahoo 3683 bars 2026-08-16 to 2026-10-13 | overnight_range_breakout.none.time | 2.80 | -0.53 | -0.2% | 1.0% | 1 | 0.06 | 0.00 | - | REJECT | v2 rejected |
| A099 | CBOT:YM (15m) | yahoo 3684 bars 2026-08-16 to 2026-10-13 | overnight_range_breakout.none.time | 4.95 | 4.58 | 1.6% | 0.5% | 1 | 1.47 | 0.04 | - | REJECT | v2 rejected |
| A100 | CME:RTY (15m) | yahoo 3683 bars 2026-08-16 to 2026-10-13 | orb.none.time | 0.39 | -0.13 | -0.1% | 1.8% | 9 | 1.29 | 0.00 | - | REJECT | v2 rejected |

## Dataset fingerprints

| Agent | Market | SHA-256 (first 16) |
|---|---|---|
| A001 | COINBASE:BTC-USD 1h | `d6a48805a3c2a4a2` |
| A002 | COINBASE:ETH-USD 1h | `901f787a5875db59` |
| A003 | COINBASE:SOL-USD 1h | `853827c8d4e4ea19` |
| A004 | COINBASE:ZEC-USD 1h | `69e2c48daa2d61be` |
| A005 | COINBASE:XRP-USD 1h | `72fd8c13d355a66b` |
| A006 | COINBASE:NEAR-USD 1h | `4e4030632f005910` |
| A007 | COINBASE:HYPE-USD 1h | `a81cae3f166e33a3` |
| A008 | COINBASE:SUI-USD 1h | `3926f1c6fb46ecac` |
| A009 | COINBASE:STRK-USD 1h | `61473e23ded75a29` |
| A010 | COINBASE:QNT-USD 1h | `94497445509afa85` |
| A011 | COINBASE:ADA-USD 1h | `36b116503fa330a2` |
| A012 | COINBASE:PUMP-USD 1h | `cb8d24bdf4508b2a` |
| A013 | COINBASE:XLM-USD 1h | `515019ccfa70a889` |
| A014 | COINBASE:ONDO-USD 1h | `0288a8ba8cbbff4e` |
| A015 | COINBASE:UNI-USD 1h | `291b29b8a1680217` |
| A016 | COINBASE:LINK-USD 1h | `0590e35d1d5e36d0` |
| A017 | COINBASE:ENA-USD 1h | `9a7ddcd8014842bf` |
| A018 | COINBASE:DOGE-USD 1h | `3604e9775fe10e18` |
| A019 | COINBASE:TAO-USD 1h | `7c8f5d3ee0e336bd` |
| A020 | COINBASE:LTC-USD 1h | `1d9a077d0d3c4b52` |
| A021 | COINBASE:ZRO-USD 1h | `723e56c4fbcbd7b0` |
| A022 | COINBASE:AVAX-USD 1h | `479c78d47564ddf5` |
| A023 | COINBASE:HBAR-USD 1h | `cc96a6bbe0c35c0b` |
| A024 | COINBASE:W-USD 1h | `2c7e451b5655992e` |
| A025 | COINBASE:RENDER-USD 1h | `56acfc20cc5e0bc0` |
| A026 | COINBASE:VVV-USD 1h | `ab2a8d6d996c9ffb` |
| A027 | COINBASE:GTC-USD 1h | `acd3d9ccc9e1369b` |
| A028 | COINBASE:TIA-USD 1h | `cedd664a9fdf87d0` |
| A029 | COINBASE:FET-USD 1h | `6d47a18f37496268` |
| A030 | COINBASE:AERO-USD 1h | `6435c471d2007fa7` |
| A031 | COINBASE:STX-USD 1h | `09b4ca3a8857123c` |
| A032 | COINBASE:FIL-USD 1h | `8a41698baaa0bc1a` |
| A033 | COINBASE:ICP-USD 1h | `d5a045ab27497fb9` |
| A034 | COINBASE:USELESS-USD 1h | `891acc3150413727` |
| A035 | COINBASE:AAVE-USD 1h | `fc739d61b5ab276a` |
| A036 | COINBASE:LIGHTER-USD 1h | `ef4f373b82aca4b6` |
| A037 | COINBASE:INJ-USD 1h | `e70507853b9c86fe` |
| A038 | COINBASE:RSR-USD 1h | `6a72609c3dc7a9f8` |
| A039 | COINBASE:PYTH-USD 1h | `969f3d908e66b586` |
| A040 | COINBASE:PEPE-USD 1h | `3b6bf0bdb5f5653f` |
| A041 | US:SPY 15m | `dca01e1b4ebad69b` |
| A042 | US:QQQ 15m | `090a859c8dc0770c` |
| A043 | US:IWM 15m | `37cfb8a60b1a4a08` |
| A044 | US:DIA 15m | `c8f4e8deffbd9022` |
| A045 | US:XLK 15m | `396673ba38e56621` |
| A046 | US:XLF 15m | `e8a2d9c724432a9c` |
| A047 | US:XLE 15m | `84a5de2ac529b6fb` |
| A048 | US:XLV 15m | `9f00d327e09d52fd` |
| A049 | US:XLY 15m | `5768480a80486f75` |
| A050 | US:XLI 15m | `4fa6fdeaaf2459ec` |
| A051 | US:SMH 15m | `d20c05b2e0ff3b0d` |
| A052 | US:XBI 15m | `5db54af79b740e20` |
| A053 | US:KRE 15m | `7ebbda01735a4ac4` |
| A054 | US:GLD 15m | `fd47d06bc1a4f39d` |
| A055 | US:TLT 15m | `cbc3370579f6c7c8` |
| A056 | US:AAPL 15m | `340918adffd68b36` |
| A057 | US:MSFT 15m | `b2300e460014c291` |
| A058 | US:NVDA 15m | `1b6cb0723b399562` |
| A059 | US:AMZN 15m | `dda8845565c416d4` |
| A060 | US:TSLA 15m | `dbd1fcc4a91f440b` |
| A061 | US:META 15m | `76f6eb6c119800c1` |
| A062 | US:GOOGL 15m | `c693d07471e0f889` |
| A063 | US:AMD 15m | `ebfaf26999892cce` |
| A064 | US:NFLX 15m | `bccf8321f7579dc1` |
| A065 | US:AVGO 15m | `7b8522cbf5ca9d50` |
| A066 | US:PLTR 15m | `e3cd322787a0e6f4` |
| A067 | US:COIN 15m | `898888fc2b9f8995` |
| A068 | US:UBER 15m | `d616848405542a6c` |
| A069 | US:ORCL 15m | `97c4531125b84424` |
| A070 | US:CRM 15m | `56811cb9c5525e44` |
| A071 | US:ADBE 15m | `3a174d1ed7657374` |
| A072 | US:INTC 15m | `5ac4b63d4b225511` |
| A073 | US:JPM 1h | `c5c88040d1296f2e` |
| A074 | US:XOM 1h | `668e2b75a407bf59` |
| A075 | US:BRK-B 1h | `0e3d24aba3ef53d5` |
| A076 | US:LLY 1h | `b19d55e6c72773a4` |
| A077 | US:V 1h | `e2477ae2fb4825bb` |
| A078 | US:MA 1h | `e07c1c2499ecfc11` |
| A079 | US:UNH 1h | `12c3749f4afa8759` |
| A080 | US:COST 1h | `0b1252b2c8ce4798` |
| A081 | US:WMT 1h | `f47350202ccdb495` |
| A082 | US:HD 1h | `221ed311beeb9322` |
| A083 | US:PG 1h | `e66769973243bda6` |
| A084 | US:JNJ 1h | `cbdb9a4ba310c60e` |
| A085 | US:KO 1h | `679112dd9ef37c5f` |
| A086 | US:PEP 1h | `f89f3ca602c699ba` |
| A087 | US:MRK 1h | `a79b20b8661ba049` |
| A088 | US:CVX 1h | `a5cfd7fbdff80413` |
| A089 | US:BAC 1h | `14edafe29993ccc9` |
| A090 | FX:EURUSD 1h | `a94b2eb2deb0e080` |
| A091 | FX:GBPUSD 1h | `55d7dc529d050331` |
| A092 | FX:USDJPY 1h | `c113dd88badd623b` |
| A093 | FX:USDCAD 1h | `6813b6ef1afb0e82` |
| A094 | FX:AUDUSD 1h | `f38dec7dbd76a0d4` |
| A095 | CME:ES 15m | `31baae1d537af755` |
| A096 | CME:MES 15m | `55b0a61967652e6d` |
| A097 | CME:NQ 15m | `443a102a03a6b0ff` |
| A098 | CME:MNQ 15m | `0845ae9c7d57c2d1` |
| A099 | CBOT:YM 15m | `137cf6352fcdda92` |
| A100 | CME:RTY 15m | `c030b3912c0ec895` |

## Reading this honestly

- These are backtests on past data under stated cost assumptions. They are not a forecast and not a promise of returns.
- An agent that is rejected stays in cash. That is the intended result when the evidence is not strong enough.
- Data windows are short for 15-minute bars (the free provider keeps about 60 days), so those agents have few test trades. Most of them cannot pass the 30-trade minimum.
- The app retrains every agent on fresh data every 7 days. A newer version must first beat the active one in shadow on bars it was not trained on.
