# Portfolio backtest report (walk-forward, by market regime)

Generated 2026-10-13 05:07 UTC by `scripts/portfolio_backtest.py`, using the app's own backtester and cost model on real market data. The run took 4 minutes. 100 agents had enough history to test.

## Method

- **No look-ahead.** Each agent's history is walked forward in 6 folds after the first 30%.
  - Before each fold, the 3 candidates of the agent's role are fitted on the first 75% of the history so far.
  - The best candidate is chosen on the remaining 25% (validation).
  - That choice then trades the next fold, which it has never seen.
  - Signals are computed causally, and orders fill at the next bar.
- **Costs.** Every backtest includes the app's cost model for its market: fees, spread, slippage and funding.
  - Funding is zero for spot crypto, because the agents hold no perpetual futures.
  - FX swap is not modelled. FX positions are always closed before the daily rollover, under the intraday rules.
  - Futures are flat in roll windows.
- **Intraday rules** apply in every backtest: entry windows, flat before the close, and a 24-hour maximum hold for crypto.
- **Portfolio.** Each agent is a sleeve with equal capital, rebalanced daily among the sleeves that have out-of-sample data that day.
  - Inside its sleeve, an agent risks 1% of the sleeve per trade (stop-based exits) or targets 15% volatility (signal exits).
  - Day returns are compounded from bar returns, by UTC day.
- **ALL** trades every fold with the chosen candidate.
- **GATED** skips a fold when the chosen candidate lost money in its own validation window, or traded fewer than 3 times there. This uses in-sample information only.
- **Regimes.** Each day is labelled from a benchmark's daily closes up to the previous day:
  - **volatile**: 20-day volatility is above 1.5 times its one-year median;
  - **bull** or **bear**: the 20-day move is beyond half of one 20-day standard deviation;
  - **sideways**: everything else.
  - Benchmarks: BTC for crypto, SPY for stocks, ETFs and index futures, EUR/USD for FX.

## Combined portfolio (all agents with out-of-sample data)

Out-of-sample period: 2025-01-25 to 2026-10-13.

| Variant | Days | Total return | Sharpe (ann., 365 d) | Max drawdown | Up days | Worst day |
|---|---|---|---|---|---|---|
| ALL | 627 | -33.1% | -7.83 | 33.1% | 20% | -0.75% |
| GATED | 627 | -3.7% | -3.72 | 3.7% | 25% | -0.15% |

For comparison, buy and hold over the same dates: SPY +32.4% (2025-01-27 to 2026-10-12); BTC-USD -22.0% (2025-01-25 to 2026-10-12).

Trading costs over all sleeves: 2,070,241 (fees 1,081,851, spread 227,298, slippage 761,092, funding 0), against gross trading P&L of 233,101. All amounts are in account currency, on each sleeve's own 100,000 of backtest capital.

**Costs were 8.9 times the gross trading profit.** Before costs the agents made a little money in total; after costs they lost it. This is the main reason the research gate rejects every version.

**Combined ALL, by US equity regime (SPY)**

| Regime | Days | Return over those days | Mean per day | Sharpe (ann.) | Up days | Worst day |
|---|---|---|---|---|---|---|
| bull | 270 | -15.4% | -6.2 bp | -9.60 | 23% | -0.45% |
| bear | 56 | -3.9% | -7.2 bp | -12.19 | 7% | -0.49% |
| sideways | 207 | -12.4% | -6.4 bp | -8.97 | 21% | -0.75% |
| volatile | 94 | -6.0% | -6.5 bp | -4.65 | 20% | -0.67% |

**Combined ALL, by crypto regime (BTC)**

| Regime | Days | Return over those days | Mean per day | Sharpe (ann.) | Up days | Worst day |
|---|---|---|---|---|---|---|
| bull | 187 | -10.8% | -6.1 bp | -6.15 | 22% | -0.65% |
| bear | 145 | -7.3% | -5.2 bp | -9.02 | 17% | -0.75% |
| sideways | 241 | -15.6% | -7.0 bp | -9.02 | 22% | -0.45% |
| volatile | 54 | -4.1% | -7.8 bp | -8.84 | 15% | -0.67% |

**Combined GATED, by US equity regime (SPY)**

| Regime | Days | Return over those days | Mean per day | Sharpe (ann.) | Up days | Worst day |
|---|---|---|---|---|---|---|
| bull | 270 | -1.4% | -0.5 bp | -2.84 | 31% | -0.14% |
| bear | 56 | -0.2% | -0.3 bp | -1.90 | 25% | -0.09% |
| sideways | 207 | -1.6% | -0.8 bp | -4.89 | 23% | -0.15% |
| volatile | 94 | -0.7% | -0.7 bp | -5.27 | 12% | -0.09% |

## Each role, by its own market's regime

### Crypto majors: trend (3 agents, benchmark COINBASE:BTC-USD)

ALL: 585 days, -62.5%, Sharpe -5.72, max drawdown 62.5%. GATED: +0.0%, Sharpe -, max drawdown 0.0%.

**ALL by regime**

| Regime | Days | Return over those days | Mean per day | Sharpe (ann.) | Up days | Worst day |
|---|---|---|---|---|---|---|
| bull | 179 | -28.8% | -18.8 bp | -6.46 | 16% | -1.91% |
| bear | 121 | -12.2% | -10.7 bp | -6.35 | 14% | -1.19% |
| sideways | 234 | -34.6% | -17.9 bp | -5.20 | 15% | -1.65% |
| volatile | 51 | -8.3% | -16.9 bp | -7.05 | 14% | -1.37% |

### Liquid crypto: trend (22 agents, benchmark COINBASE:BTC-USD)

ALL: 588 days, -39.5%, Sharpe -5.96, max drawdown 39.6%. GATED: -3.8%, Sharpe -3.90, max drawdown 3.8%.

**ALL by regime**

| Regime | Days | Return over those days | Mean per day | Sharpe (ann.) | Up days | Worst day |
|---|---|---|---|---|---|---|
| bull | 179 | -13.5% | -8.0 bp | -4.93 | 24% | -0.93% |
| bear | 122 | -7.0% | -5.9 bp | -5.79 | 23% | -0.67% |
| sideways | 234 | -20.4% | -9.7 bp | -6.60 | 17% | -1.13% |
| volatile | 53 | -5.6% | -10.8 bp | -8.23 | 13% | -0.90% |

### Liquid crypto: mean reversion (15 agents, benchmark COINBASE:BTC-USD)

ALL: 627 days, -32.6%, Sharpe -7.46, max drawdown 32.6%. GATED: -1.1%, Sharpe -1.86, max drawdown 1.3%.

**ALL by regime**

| Regime | Days | Return over those days | Mean per day | Sharpe (ann.) | Up days | Worst day |
|---|---|---|---|---|---|---|
| bull | 187 | -11.5% | -6.5 bp | -8.15 | 16% | -1.08% |
| bear | 145 | -8.9% | -6.4 bp | -7.04 | 21% | -1.03% |
| sideways | 241 | -13.9% | -6.2 bp | -7.36 | 20% | -0.80% |
| volatile | 54 | -3.0% | -5.6 bp | -6.73 | 15% | -0.97% |

### Index and sector ETFs: intraday momentum (15 agents, benchmark US:SPY)

ALL: 28 days, -0.3%, Sharpe -3.15, max drawdown 0.5%. GATED: -0.3%, Sharpe -5.34, max drawdown 0.4%.

**ALL by regime**

| Regime | Days | Return over those days | Mean per day | Sharpe (ann.) | Up days | Worst day |
|---|---|---|---|---|---|---|
| bull | 5 | +0.0% | +0.4 bp | 1.91 | 20% | -0.02% |
| bear | 6 | -0.1% | -1.1 bp | -10.11 | 17% | -0.04% |
| sideways | 17 | -0.3% | -1.5 bp | -3.57 | 29% | -0.18% |

### Large US stocks: breakouts (17 agents, benchmark US:SPY)

ALL: 28 days, -0.2%, Sharpe -1.50, max drawdown 0.6%. GATED: -0.3%, Sharpe -7.17, max drawdown 0.3%.

**ALL by regime**

| Regime | Days | Return over those days | Mean per day | Sharpe (ann.) | Up days | Worst day |
|---|---|---|---|---|---|---|
| bull | 5 | -0.1% | -2.7 bp | -28.03 | 0% | -0.05% |
| bear | 6 | +0.0% | +0.4 bp | 1.16 | 50% | -0.11% |
| sideways | 17 | -0.1% | -0.6 bp | -0.96 | 35% | -0.13% |

### Large US stocks: mean reversion (17 agents, benchmark US:SPY)

ALL: 351 days, -5.2%, Sharpe -3.58, max drawdown 6.2%. GATED: -1.5%, Sharpe -1.71, max drawdown 2.1%.

**ALL by regime**

| Regime | Days | Return over those days | Mean per day | Sharpe (ann.) | Up days | Worst day |
|---|---|---|---|---|---|---|
| bull | 169 | -3.0% | -1.8 bp | -4.39 | 43% | -0.31% |
| bear | 30 | -1.0% | -3.3 bp | -5.80 | 40% | -0.33% |
| sideways | 133 | -1.0% | -0.8 bp | -1.86 | 45% | -0.30% |
| volatile | 19 | -0.3% | -1.6 bp | -3.77 | 42% | -0.19% |

### Forex: session momentum (5 agents, benchmark FX:EURUSD)

ALL: 417 days, -11.9%, Sharpe -1.23, max drawdown 14.5%. GATED: -13.6%, Sharpe -1.71, max drawdown 15.7%.

**ALL by regime**

| Regime | Days | Return over those days | Mean per day | Sharpe (ann.) | Up days | Worst day |
|---|---|---|---|---|---|---|
| bull | 140 | -5.7% | -4.1 bp | -2.00 | 39% | -1.37% |
| bear | 139 | -9.7% | -7.3 bp | -3.27 | 32% | -1.12% |
| sideways | 138 | +3.6% | +2.7 bp | 0.97 | 41% | -1.41% |

### Equity-index futures: opening breakouts (6 agents, benchmark US:SPY)

ALL: 35 days, -0.7%, Sharpe -1.74, max drawdown 1.7%. GATED: -0.1%, Sharpe -0.65, max drawdown 0.5%.

**ALL by regime**

| Regime | Days | Return over those days | Mean per day | Sharpe (ann.) | Up days | Worst day |
|---|---|---|---|---|---|---|
| bull | 7 | -0.4% | -5.0 bp | -2.97 | 57% | -0.65% |
| bear | 7 | -0.2% | -2.4 bp | -7.22 | 0% | -0.17% |
| sideways | 21 | -0.2% | -1.1 bp | -0.83 | 19% | -0.46% |

## Every agent (out of sample)

| Agent | Market | Candidates chosen across folds | OOS days | OOS return | Sharpe | Max DD | Trades | Costs / gross P&L | Folds traded when gated | GATED return |
|---|---|---|---|---|---|---|---|---|---|---|
| A001 | COINBASE:BTC-USD | donchian_breakout, tsmom | 585 | -74.7% | -6.38 | 74.7% | 221 | gross loss | 0/6 | +0.0% |
| A002 | COINBASE:ETH-USD | donchian_breakout, tsmom | 585 | -54.1% | -2.76 | 54.2% | 229 | 473% | 0/6 | +0.0% |
| A003 | COINBASE:SOL-USD | ema_cross, tsmom | 585 | -55.6% | -4.08 | 55.9% | 275 | 891% | 0/6 | +0.0% |
| A004 | COINBASE:ZEC-USD | donchian_breakout, tsmom | 585 | -19.4% | -1.02 | 25.6% | 177 | 158% | 2/6 | -8.1% |
| A005 | COINBASE:XRP-USD | donchian_breakout, ema_cross | 585 | -31.9% | -1.96 | 34.2% | 159 | 312% | 0/6 | +0.0% |
| A006 | COINBASE:NEAR-USD | donchian_breakout, tsmom | 585 | -28.3% | -1.67 | 32.8% | 182 | 219% | 0/6 | +0.0% |
| A007 | COINBASE:HYPE-USD | donchian_breakout, ema_cross | 176 | -18.9% | -2.99 | 18.9% | 91 | 290% | 2/6 | -5.2% |
| A008 | COINBASE:SUI-USD | donchian_breakout, tsmom | 585 | -35.4% | -2.99 | 37.3% | 129 | gross loss | 2/6 | -18.1% |
| A009 | COINBASE:STRK-USD | donchian_breakout, tsmom | 588 | -45.6% | -3.14 | 47.3% | 207 | 583% | 0/6 | +0.0% |
| A010 | COINBASE:QNT-USD | donchian_breakout, tsmom | 585 | -42.3% | -3.55 | 48.0% | 170 | 719% | 0/6 | +0.0% |
| A011 | COINBASE:ADA-USD | donchian_breakout, ema_cross | 585 | -35.4% | -2.71 | 35.9% | 168 | 786% | 0/6 | +0.0% |
| A012 | COINBASE:PUMP-USD | donchian_breakout, ema_cross, tsmom | 319 | -30.7% | -3.00 | 31.4% | 181 | 700% | 0/6 | +0.0% |
| A013 | COINBASE:XLM-USD | donchian_breakout, tsmom | 585 | -38.7% | -2.86 | 40.7% | 151 | 523% | 1/6 | -13.7% |
| A014 | COINBASE:ONDO-USD | donchian_breakout, ema_cross | 585 | -44.5% | -3.63 | 45.7% | 162 | gross loss | 0/6 | +0.0% |
| A015 | COINBASE:UNI-USD | donchian_breakout, ema_cross, tsmom | 585 | -45.4% | -3.50 | 45.6% | 184 | 97284% | 0/6 | +0.0% |
| A016 | COINBASE:LINK-USD | donchian_breakout | 585 | -34.0% | -2.42 | 34.7% | 150 | 373% | 0/6 | +0.0% |
| A017 | COINBASE:ENA-USD | donchian_breakout, ema_cross, tsmom | 347 | -30.1% | -3.22 | 34.0% | 115 | 4691% | 0/6 | +0.0% |
| A018 | COINBASE:DOGE-USD | donchian_breakout, ema_cross | 585 | -43.1% | -3.39 | 45.0% | 128 | gross loss | 0/6 | +0.0% |
| A019 | COINBASE:TAO-USD | donchian_breakout, ema_cross, tsmom | 421 | -29.5% | -2.73 | 30.9% | 144 | 623% | 1/6 | -13.4% |
| A020 | COINBASE:LTC-USD | donchian_breakout, tsmom | 585 | -54.3% | -4.71 | 54.8% | 155 | gross loss | 1/6 | -11.4% |
| A021 | COINBASE:ZRO-USD | donchian_breakout, tsmom | 585 | -35.0% | -3.21 | 38.6% | 131 | 559% | 0/6 | +0.0% |
| A022 | COINBASE:AVAX-USD | donchian_breakout, ema_cross | 585 | -44.6% | -3.60 | 46.4% | 150 | gross loss | 0/6 | +0.0% |
| A023 | COINBASE:HBAR-USD | donchian_breakout | 585 | -34.4% | -2.34 | 38.8% | 135 | 517% | 0/6 | +0.0% |
| A024 | COINBASE:W-USD | donchian_breakout, tsmom | 329 | -24.0% | -5.14 | 25.2% | 91 | 1485% | 0/6 | +0.0% |
| A025 | COINBASE:RENDER-USD | donchian_breakout, ema_cross, tsmom | 585 | -45.6% | -3.64 | 47.0% | 219 | 504% | 0/6 | +0.0% |
| A026 | COINBASE:VVV-USD | zscore_reversion | 439 | -17.6% | -2.11 | 17.6% | 76 | 365% | 1/6 | -2.6% |
| A027 | COINBASE:GTC-USD | bollinger_reversion, zscore_reversion | 627 | -12.0% | -3.90 | 12.0% | 70 | gross loss | 0/6 | +0.0% |
| A028 | COINBASE:TIA-USD | bollinger_reversion, zscore_reversion | 585 | -38.8% | -4.70 | 39.2% | 80 | gross loss | 0/6 | +0.0% |
| A029 | COINBASE:FET-USD | bollinger_reversion, zscore_reversion | 585 | -39.5% | -4.09 | 40.0% | 81 | gross loss | 0/6 | +0.0% |
| A030 | COINBASE:AERO-USD | bollinger_reversion, zscore_reversion | 585 | -31.7% | -3.30 | 31.7% | 53 | gross loss | 1/6 | -1.8% |
| A031 | COINBASE:STX-USD | bollinger_reversion, zscore_reversion | 585 | -29.3% | -3.98 | 29.4% | 74 | gross loss | 0/6 | +0.0% |
| A032 | COINBASE:FIL-USD | bollinger_reversion, zscore_reversion | 585 | -27.2% | -2.85 | 27.2% | 70 | 603% | 1/6 | -7.9% |
| A033 | COINBASE:ICP-USD | bollinger_reversion, zscore_reversion | 585 | -36.4% | -3.82 | 36.5% | 73 | gross loss | 0/6 | +0.0% |
| A034 | COINBASE:USELESS-USD | bollinger_reversion, zscore_reversion | 294 | -11.0% | -2.08 | 12.9% | 37 | 513% | 3/6 | -3.5% |
| A035 | COINBASE:AAVE-USD | bollinger_reversion, zscore_reversion | 585 | -45.0% | -4.39 | 45.3% | 95 | gross loss | 0/6 | +0.0% |
| A036 | COINBASE:LIGHTER-USD | bollinger_reversion, rsi2_reversion, zscore_reversion | 191 | -9.9% | -3.50 | 10.2% | 31 | 451% | 0/6 | +0.0% |
| A037 | COINBASE:INJ-USD | bollinger_reversion, zscore_reversion | 585 | -34.8% | -3.48 | 36.3% | 86 | gross loss | 0/6 | +0.0% |
| A038 | COINBASE:RSR-USD | bollinger_reversion, zscore_reversion | 379 | -12.0% | -3.08 | 12.0% | 66 | gross loss | 0/6 | +0.0% |
| A039 | COINBASE:PYTH-USD | bollinger_reversion, zscore_reversion | 421 | -15.5% | -3.49 | 15.5% | 50 | gross loss | 0/6 | +0.0% |
| A040 | COINBASE:PEPE-USD | bollinger_reversion, zscore_reversion | 490 | -34.6% | -3.77 | 34.6% | 80 | gross loss | 0/6 | +0.0% |
| A041 | US:SPY | first_hour_momentum, noise_band_momentum, orb | 28 | -0.0% | 0.02 | 1.1% | 12 | 100% | 1/6 | +0.4% |
| A042 | US:QQQ | first_hour_momentum, noise_band_momentum, orb | 28 | +0.7% | 1.41 | 1.3% | 11 | 42% | 2/6 | -0.9% |
| A043 | US:IWM | first_hour_momentum, noise_band_momentum | 28 | -0.8% | -7.14 | 0.8% | 5 | gross loss | 0/6 | +0.0% |
| A044 | US:DIA | first_hour_momentum, orb | 28 | +0.3% | 2.49 | 0.1% | 2 | 19% | 1/6 | +0.3% |
| A045 | US:XLK | first_hour_momentum, noise_band_momentum, orb | 28 | -2.2% | -5.30 | 2.3% | 10 | gross loss | 2/6 | -2.0% |
| A046 | US:XLF | first_hour_momentum, noise_band_momentum, orb | 28 | +1.4% | 4.73 | 0.1% | 6 | 16% | 0/6 | +0.0% |
| A047 | US:XLE | first_hour_momentum, noise_band_momentum, orb | 28 | -2.0% | -6.42 | 2.2% | 8 | gross loss | 1/6 | -0.7% |
| A048 | US:XLV | first_hour_momentum, noise_band_momentum, orb | 28 | -0.8% | -3.05 | 1.1% | 7 | gross loss | 3/6 | -0.8% |
| A049 | US:XLY | first_hour_momentum, noise_band_momentum, orb | 28 | -0.7% | -2.26 | 1.5% | 5 | gross loss | 0/6 | +0.0% |
| A050 | US:XLI | first_hour_momentum | 28 | +0.0% | - | 0.0% | 0 | - | 0/6 | +0.0% |
| A051 | US:SMH | first_hour_momentum, noise_band_momentum | 28 | -0.8% | -3.17 | 1.2% | 4 | gross loss | 2/6 | -0.8% |
| A052 | US:XBI | first_hour_momentum, orb | 28 | +0.4% | 1.53 | 0.5% | 4 | 36% | 1/6 | -0.1% |
| A053 | US:KRE | first_hour_momentum | 28 | +0.0% | - | 0.0% | 0 | - | 0/6 | +0.0% |
| A054 | US:GLD | first_hour_momentum | 28 | +0.0% | - | 0.0% | 0 | - | 0/6 | +0.0% |
| A055 | US:TLT | first_hour_momentum, orb | 28 | +0.1% | 0.95 | 0.4% | 4 | 48% | 0/6 | +0.0% |
| A056 | US:AAPL | active_orb, orb, vol_breakout | 28 | +0.3% | 0.76 | 1.0% | 9 | 68% | 0/6 | +0.0% |
| A057 | US:MSFT | active_orb, orb, vol_breakout | 28 | -3.0% | -5.49 | 4.0% | 11 | gross loss | 0/6 | +0.0% |
| A058 | US:NVDA | active_orb, orb, vol_breakout | 28 | -1.5% | -4.72 | 1.5% | 8 | gross loss | 3/6 | -0.6% |
| A059 | US:AMZN | active_orb, orb | 28 | -0.5% | -4.03 | 0.5% | 2 | gross loss | 0/6 | +0.0% |
| A060 | US:TSLA | active_orb, vol_breakout | 28 | +1.1% | 1.75 | 1.4% | 5 | 26% | 0/6 | +0.0% |
| A061 | US:META | active_orb, orb, vol_breakout | 28 | +0.5% | 0.59 | 2.3% | 6 | 49% | 0/6 | +0.0% |
| A062 | US:GOOGL | active_orb, vol_breakout | 28 | -1.8% | -4.45 | 2.1% | 8 | gross loss | 3/6 | -1.9% |
| A063 | US:AMD | active_orb, orb, vol_breakout | 28 | -0.2% | -0.35 | 1.5% | 8 | 128% | 0/6 | +0.0% |
| A064 | US:NFLX | active_orb, orb, vol_breakout | 28 | +0.1% | 0.22 | 1.3% | 9 | 84% | 1/6 | -0.9% |
| A065 | US:AVGO | active_orb, orb, vol_breakout | 28 | -0.7% | -4.85 | 0.7% | 2 | gross loss | 1/6 | -0.2% |
| A066 | US:PLTR | active_orb, vol_breakout | 28 | -0.1% | -1.05 | 0.2% | 2 | 161% | 0/6 | +0.0% |
| A067 | US:COIN | active_orb, orb | 28 | +1.6% | 2.68 | 1.1% | 7 | 23% | 0/6 | +0.0% |
| A068 | US:UBER | active_orb, orb, vol_breakout | 28 | +1.3% | 2.33 | 1.1% | 3 | 18% | 0/6 | +0.0% |
| A069 | US:ORCL | active_orb, orb, vol_breakout | 28 | -3.2% | -4.03 | 5.0% | 10 | gross loss | 1/6 | -1.5% |
| A070 | US:CRM | active_orb | 28 | +0.0% | - | 0.0% | 0 | - | 0/6 | +0.0% |
| A071 | US:ADBE | active_orb, orb | 28 | +0.6% | 2.73 | 0.2% | 2 | 21% | 1/6 | -0.2% |
| A072 | US:INTC | active_orb, orb, vol_breakout | 28 | +1.6% | 3.10 | 0.6% | 9 | 28% | 0/6 | +0.0% |
| A073 | US:JPM | rsi2_reversion, zscore_reversion | 351 | +4.0% | 1.14 | 3.3% | 59 | 51% | 4/6 | +5.6% |
| A074 | US:XOM | ibs_reversion, rsi2_reversion, zscore_reversion | 351 | -0.3% | -0.03 | 3.8% | 168 | 102% | 4/6 | +0.9% |
| A075 | US:BRK-B | rsi2_reversion, zscore_reversion | 351 | -9.7% | -1.81 | 12.5% | 147 | 690% | 1/6 | -2.4% |
| A076 | US:LLY | rsi2_reversion, zscore_reversion | 351 | -4.6% | -1.40 | 6.6% | 58 | gross loss | 1/6 | -0.6% |
| A077 | US:V | ibs_reversion, rsi2_reversion, zscore_reversion | 351 | -6.6% | -1.41 | 8.8% | 124 | 457% | 2/6 | -2.8% |
| A078 | US:MA | ibs_reversion, rsi2_reversion, zscore_reversion | 351 | -13.4% | -2.86 | 14.7% | 105 | gross loss | 1/6 | -5.3% |
| A079 | US:UNH | rsi2_reversion, zscore_reversion | 351 | -8.7% | -1.69 | 9.1% | 129 | gross loss | 2/6 | +0.1% |
| A080 | US:COST | rsi2_reversion, zscore_reversion | 351 | -3.6% | -0.87 | 5.5% | 61 | 543% | 6/6 | -3.6% |
| A081 | US:WMT | zscore_reversion | 351 | +4.7% | 1.29 | 3.2% | 69 | 50% | 4/6 | +0.4% |
| A082 | US:HD | ibs_reversion, rsi2_reversion, zscore_reversion | 351 | -13.4% | -2.67 | 14.9% | 119 | gross loss | 2/6 | -2.5% |
| A083 | US:PG | ibs_reversion, rsi2_reversion, zscore_reversion | 351 | -5.4% | -1.16 | 9.9% | 100 | 372% | 2/6 | -0.9% |
| A084 | US:JNJ | ibs_reversion, rsi2_reversion, zscore_reversion | 351 | -8.1% | -1.58 | 9.6% | 150 | 401% | 4/6 | -6.4% |
| A085 | US:KO | rsi2_reversion, zscore_reversion | 351 | -7.2% | -1.74 | 8.9% | 99 | 8402% | 3/6 | -7.1% |
| A086 | US:PEP | ibs_reversion, rsi2_reversion, zscore_reversion | 351 | -12.5% | -2.68 | 16.1% | 123 | gross loss | 2/6 | -0.5% |
| A087 | US:MRK | rsi2_reversion, zscore_reversion | 351 | +2.6% | 0.72 | 4.4% | 64 | 62% | 4/6 | +1.2% |
| A088 | US:CVX | ibs_reversion, rsi2_reversion, zscore_reversion | 351 | +2.7% | 0.69 | 3.0% | 100 | 71% | 4/6 | +4.7% |
| A089 | US:BAC | rsi2_reversion, zscore_reversion | 351 | -6.9% | -1.69 | 8.8% | 71 | gross loss | 4/6 | -5.6% |
| A090 | FX:EURUSD | london_open_momentum, ny_overlap_continuation, tsmom | 416 | -24.0% | -1.47 | 25.9% | 524 | gross loss | 5/6 | -21.4% |
| A091 | FX:GBPUSD | london_open_momentum, tsmom | 416 | +1.9% | 0.18 | 11.6% | 316 | 88% | 5/6 | -4.7% |
| A092 | FX:USDJPY | london_open_momentum, ny_overlap_continuation, tsmom | 416 | +0.7% | 0.12 | 13.3% | 519 | 96% | 6/6 | +0.7% |
| A093 | FX:USDCAD | london_open_momentum, tsmom | 416 | -19.5% | -1.32 | 26.6% | 455 | 817% | 4/6 | -14.9% |
| A094 | FX:AUDUSD | london_open_momentum, tsmom | 417 | -19.2% | -0.95 | 25.9% | 551 | 254% | 5/6 | -28.1% |
| A095 | CME:ES | initial_balance_breakout, orb, overnight_range_breakout | 35 | -0.9% | -1.54 | 2.4% | 16 | gross loss | 2/6 | -0.5% |
| A096 | CME:MES | initial_balance_breakout, orb, overnight_range_breakout | 35 | -1.0% | -1.56 | 2.7% | 16 | gross loss | 2/6 | -0.6% |
| A097 | CME:NQ | orb | 35 | +0.0% | - | 0.0% | 0 | - | 0/6 | +0.0% |
| A098 | CME:MNQ | initial_balance_breakout, orb, overnight_range_breakout | 35 | -2.1% | -1.62 | 5.5% | 16 | gross loss | 1/6 | +0.0% |
| A099 | CBOT:YM | initial_balance_breakout, overnight_range_breakout | 35 | -0.4% | -0.89 | 1.6% | 15 | gross loss | 2/6 | -0.5% |
| A100 | CME:RTY | initial_balance_breakout, orb, overnight_range_breakout | 35 | -0.2% | -0.19 | 2.0% | 17 | 140% | 1/6 | +1.0% |

## Reading this honestly

- This is a backtest of past data under stated assumptions. It is not a forecast and not a promise of returns.
- Live fills can be worse than the cost model, especially for small coins and at the open.
- The 15-minute agents have only about 60 days of data, so their numbers rest on few trades.
- Regime labels are a reporting device. A short window may contain few days of a given regime, and the day counts are shown so the sample size is visible. Days the benchmark did not trade (weekends, holidays) take the previous trading day's label.
- The live system is stricter than ALL. An agent trades only after its own research run passes every gate (PAPER TEST), and in paper only.
