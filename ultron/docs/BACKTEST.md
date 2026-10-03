# Ultron: training and backtest report

Generated 2026-10-03 04:28 UTC by `ultron/tools/train.py` in 7.6 minutes.
1953 candidate agents (1,075,687 historical signals, every one traded with Ultron's exits at NDAX fees).
R = profit or loss in units of the amount risked, after fees and slippage. Paper results, not a forecast.

## How it was tested

- **Walk-forward.** Every quarter from January 2022 the brain chose its 50 agents using only signals that had
  already finished, then traded the next three months on a fresh decision for every signal. No trade below
  was made by an agent chosen with knowledge of that trade.
- **Three periods.** Development (2022-01-01 to 2025-03-19) tuned the brain's settings; validation
  (2025-03-20 to 2025-12-22) had to agree before a change was kept; **test (from 2025-12-23) was never used to
  choose anything.**
- Account: $10,000 paper, risk per trade 0.6% (BTC/ETH/SOL) or 0.3% (memes) x the brain's size, compounding.

## Result (final settings)

| Period | Trades | Avg R | t | Win | Return | Max drawdown |
|---|---|---|---|---|---|---|
| Development | 152 | +0.190 | 2.06 | 51% | +23.43% | 4.18% |
| Validation | 62 | +0.131 | 0.83 | 44% | +5.93% | 3.36% |
| **Test (untouched)** | 33 | +0.286 | 1.35 | 52% | +3.27% | 4.68% |
| All | 247 | +0.188 | 2.53 | 49% | +35.04% | 7.19% |

Decisions: 247 signals taken, 3,303 refused.

## Extreme tests

| Test | Trades | Avg R | t | Win | Return | Max drawdown |
|---|---|---|---|---|---|---|
| NDAX fees x2 | 247 | +0.114 | 1.53 | 47% | +18.26% | 10.12% |
| Kraken Pro entry-tier fees | 241 | +0.079 | 1.05 | 46% | +12.78% | 11.42% |
| slippage x3 | 245 | +0.148 | 1.98 | 48% | +26.41% | 7.96% |

**200 random 90-day windows** (fresh account each): median +0.95%, 10th percentile -1.94%, 90th +6.66%, best +10.47%, worst -3.09%; positive in 122 of 200; 0 had no trade; 15.5 trades per window.

**2,000 bootstrap reshuffles** of the walk-forward trades: final return 5th / 50th / 95th percentile +11.9% / +34.8% / +63.5%; ended below the start in 0.5%; max drawdown median 5.8%, 95th percentile 9.8%.

## The improvement loop

100 proposals, each one setting changed at a time; kept only if development improved and validation did not get worse.

| # | Change | Dev trades | Dev avg R | Dev return | Val avg R | Val return | Kept |
|---|---|---|---|---|---|---|---|
| 0 | start (defaults) | 292 | -0.014 | -5.63% | -0.019 | -1.03% | yes |
| 1 | theta = 0.0 | 310 | +0.020 | +0.63% | -0.019 | -1.03% | yes |
| 2 | theta = -0.05 | 314 | +0.026 | +1.89% | -0.019 | -1.03% | yes |
| 3 | max_open = 1 | 201 | +0.004 | -1.17% | +0.022 | -0.35% |  |
| 4 | z = 2.0 | 305 | +0.009 | -0.57% | -0.025 | -1.16% |  |
| 5 | max_per_signal = 4 | 311 | +0.035 | +2.83% | +0.014 | +0.32% | yes |
| 6 | loud_mult = 1.0 | 311 | +0.035 | +7.82% | +0.014 | +1.32% | yes |
| 7 | max_per_signal = 2 | 314 | +0.027 | +5.04% | -0.019 | -0.65% |  |
| 8 | z = 0.0 | 319 | +0.024 | +6.30% | +0.015 | +1.34% |  |
| 9 | max_meme_open = 3 | 315 | +0.042 | +9.28% | +0.037 | +2.37% | yes |
| 10 | max_per_signal = 2 | 318 | +0.041 | +7.96% | +0.028 | +1.53% |  |
| 11 | weekend_off = False | 328 | +0.039 | +8.92% | +0.011 | +1.18% |  |
| 12 | theta = 0.08 | 280 | +0.004 | +2.36% | +0.032 | +2.15% |  |
| 13 | theta = 0.03 | 306 | +0.030 | +6.54% | +0.037 | +2.37% |  |
| 14 | variants = loud_only | 187 | +0.112 | +16.69% | -0.011 | -0.61% |  |
| 15 | sel_z = 0.5 | 283 | +0.002 | +1.58% | +0.034 | +1.61% |  |
| 16 | z = 2.0 | 307 | +0.021 | +5.30% | +0.032 | +2.23% |  |
| 17 | shrink = 10.0 | 314 | +0.037 | +8.66% | +0.037 | +2.35% |  |
| 18 | max_per_signal = 1 | 334 | +0.014 | +4.75% | +0.134 | +7.02% |  |
| 19 | max_meme_open = 1 | 261 | +0.025 | +6.49% | +0.099 | +2.61% |  |
| 20 | max_open = 1 | 194 | -0.034 | -1.06% | +0.130 | +1.56% |  |
| 21 | theta = 0.05 | 298 | +0.008 | +2.24% | +0.037 | +2.37% |  |
| 22 | sel_min_n = 80 | 422 | +0.017 | +3.01% | +0.057 | +3.04% |  |
| 23 | shrink = 40.0 | 314 | +0.046 | +9.69% | +0.037 | +2.41% |  |
| 24 | sel_z = 0.0 | 276 | +0.033 | +8.73% | +0.133 | +4.90% | yes |
| 25 | sel_min_n = 150 | 525 | +0.007 | -1.77% | +0.042 | +4.19% |  |
| 26 | z = 2.0 | 258 | +0.026 | +7.29% | +0.149 | +5.14% |  |
| 27 | size_a = 2.0 | 276 | +0.030 | +7.73% | +0.133 | +5.65% |  |
| 28 | max_open = 1 | 180 | -0.023 | -1.10% | -0.127 | -1.51% |  |
| 29 | max_meme_open = 1 | 230 | +0.029 | +8.00% | +0.032 | +1.27% |  |
| 30 | max_meme_open = 2 | 273 | +0.023 | +7.90% | +0.097 | +3.44% |  |
| 31 | theta = 0.05 | 257 | +0.021 | +5.20% | +0.150 | +5.28% |  |
| 32 | weekend_off = False | 280 | +0.024 | +8.31% | +0.124 | +4.06% |  |
| 33 | z = 0.0 | 284 | +0.027 | +8.00% | +0.130 | +4.89% |  |
| 34 | max_open = 2 | 244 | +0.023 | +8.84% | +0.080 | +3.43% |  |
| 35 | evidence = since_selected | 207 | +0.011 | +4.99% | -0.030 | +0.29% |  |
| 36 | max_per_signal = 1 | 313 | -0.040 | -3.46% | +0.064 | +4.28% |  |
| 37 | variants = loud_only | 193 | +0.109 | +16.16% | +0.022 | +0.71% |  |
| 38 | theta = 0.03 | 263 | +0.031 | +7.03% | +0.150 | +5.28% |  |
| 39 | size_a = 0.0 | 276 | +0.033 | +5.62% | +0.133 | +3.78% |  |
| 40 | max_open = 4 | 285 | +0.042 | +10.55% | +0.103 | +4.14% |  |
| 41 | gate_rule = loud_only | 204 | +0.101 | +16.94% | +0.021 | +0.04% |  |
| 42 | theta = 0.08 | 247 | -0.009 | +1.11% | +0.073 | +2.90% |  |
| 43 | shrink = 10.0 | 275 | +0.045 | +10.78% | +0.133 | +4.88% | yes |
| 44 | theta = 0.18 | 217 | +0.034 | +4.16% | +0.168 | +7.31% |  |
| 45 | max_open = 1 | 180 | +0.004 | +1.99% | -0.127 | -1.54% |  |
| 46 | weekend_off = False | 279 | +0.033 | +9.36% | +0.124 | +4.01% |  |
| 47 | max_open = 2 | 242 | +0.043 | +11.93% | +0.080 | +3.39% |  |
| 48 | max_per_signal = 2 | 276 | +0.037 | +9.86% | +0.109 | +4.78% |  |
| 49 | size_a = 0.0 | 275 | +0.045 | +7.55% | +0.133 | +3.78% |  |
| 50 | z = 2.0 | 252 | +0.032 | +6.95% | +0.067 | +2.68% |  |
| 51 | sel_z = 0.5 | 283 | -0.001 | +0.95% | +0.034 | +1.58% |  |
| 52 | size_a = 2.0 | 275 | +0.043 | +10.10% | +0.133 | +5.61% |  |
| 53 | sel_min_n = 20 | 230 | +0.044 | +8.89% | -0.097 | -2.42% |  |
| 54 | theta = 0.12 | 237 | -0.003 | +0.80% | +0.151 | +6.88% |  |
| 55 | shrink = 40.0 | 278 | +0.043 | +10.82% | +0.117 | +4.53% |  |
| 56 | max_meme_open = 2 | 272 | +0.036 | +9.92% | +0.097 | +3.40% |  |
| 57 | z = 1.5 | 264 | +0.051 | +11.14% | +0.150 | +5.24% | yes |
| 58 | weekend_off = False | 270 | +0.027 | +7.78% | +0.124 | +4.01% |  |
| 59 | size_a = 2.0 | 264 | +0.049 | +10.74% | +0.150 | +6.02% |  |
| 60 | shrink = 20.0 | 276 | +0.052 | +12.56% | +0.150 | +5.27% | yes |
| 61 | z = 0.5 | 281 | +0.029 | +8.06% | +0.130 | +4.89% |  |
| 62 | variants = loud_only | 193 | +0.109 | +16.15% | +0.021 | +0.73% |  |
| 63 | sel_window_days = 365 | 404 | -0.105 | -22.03% | -0.184 | -10.54% |  |
| 64 | theta = 0.05 | 243 | -0.017 | -0.37% | +0.067 | +2.69% |  |
| 65 | z = 0.0 | 284 | +0.027 | +8.00% | +0.130 | +4.89% |  |
| 66 | sel_window_days = 730 | 304 | -0.018 | -1.83% | +0.018 | +1.70% |  |
| 67 | size_a = 0.0 | 276 | +0.052 | +8.97% | +0.150 | +4.12% |  |
| 68 | sel_min_n = 150 | 509 | +0.015 | -1.12% | +0.025 | +3.74% |  |
| 69 | theta = 0.0 | 256 | +0.027 | +7.12% | +0.150 | +5.27% |  |
| 70 | shrink = 80.0 | 277 | +0.063 | +13.81% | +0.133 | +4.81% |  |
| 71 | max_per_signal = 2 | 275 | +0.061 | +14.83% | +0.125 | +5.17% | yes |
| 72 | theta = 0.03 | 248 | +0.015 | +6.01% | +0.048 | +2.81% |  |
| 73 | size_a = 2.0 | 275 | +0.058 | +14.17% | +0.125 | +5.63% |  |
| 74 | gate_rule = loud_only | 206 | +0.102 | +17.81% | -0.013 | -0.56% |  |
| 75 | evidence = since_selected | 189 | +0.044 | +8.02% | -0.042 | +0.43% |  |
| 76 | z = 0.0 | 285 | +0.011 | +5.96% | +0.106 | +4.76% |  |
| 77 | variants = loudtrend | 152 | +0.191 | +21.73% | +0.131 | +5.02% | yes |
| 78 | theta = 0.05 | 149 | +0.185 | +21.39% | +0.131 | +5.02% |  |
| 79 | sel_z = 1.0 | 148 | +0.185 | +19.73% | +0.136 | +4.66% |  |
| 80 | max_per_signal = 4 | 152 | +0.190 | +21.84% | +0.103 | +4.28% |  |
| 81 | variants = loud_only | 192 | +0.117 | +16.91% | -0.016 | -0.55% |  |
| 82 | sel_window_days = 730 | 156 | +0.171 | +18.21% | +0.187 | +5.90% |  |
| 83 | gate_rule = learned | 152 | +0.191 | +21.73% | +0.131 | +5.02% |  |
| 84 | max_open = 4 | 160 | +0.206 | +23.04% | +0.122 | +4.51% |  |
| 85 | sel_min_n = 80 | 115 | +0.169 | +12.75% | +0.247 | +7.93% |  |
| 86 | z = 2.0 | 152 | +0.176 | +20.92% | +0.131 | +5.02% |  |
| 87 | sel_z = 0.5 | 149 | +0.171 | +18.65% | +0.107 | +4.03% |  |
| 88 | theta = 0.08 | 147 | +0.205 | +22.61% | +0.121 | +4.35% |  |
| 89 | z = 0.5 | 152 | +0.192 | +21.36% | +0.138 | +5.14% |  |
| 90 | theta = 0.0 | 152 | +0.176 | +20.54% | +0.131 | +5.02% |  |
| 91 | size_a = 2.0 | 152 | +0.190 | +23.43% | +0.131 | +5.93% | yes |
| 92 | theta = 0.08 | 147 | +0.203 | +24.34% | +0.121 | +5.06% |  |
| 93 | size_a = 1.0 | 152 | +0.191 | +21.73% | +0.131 | +5.02% |  |
| 94 | max_per_signal = 4 | 152 | +0.188 | +23.48% | +0.103 | +5.08% |  |
| 95 | shrink = 80.0 | 152 | +0.189 | +23.12% | +0.131 | +5.84% |  |
| 96 | sel_min_n = 20 | 166 | +0.194 | +26.64% | +0.122 | +3.62% |  |
| 97 | loud_mult = 0.6 | 152 | +0.191 | +13.72% | +0.131 | +3.56% |  |
| 98 | shrink = 40.0 | 152 | +0.189 | +23.25% | +0.131 | +5.93% |  |
| 99 | variants = loud_only | 192 | +0.116 | +17.90% | -0.016 | -0.41% |  |
| 100 | variants = all | 275 | +0.058 | +14.17% | +0.125 | +5.63% |  |

Final settings: `{"theta": -0.05, "z": 1.5, "shrink": 20.0, "size_a": 2.0, "gate_rule": "no_quiet", "loud_mult": 1.0, "weekend_off": true, "regime_rule": "memes_off_in_bear", "max_open": 3, "max_major_open": 1, "max_meme_open": 3, "risk_major": 0.006, "risk_meme": 0.003, "daily_stop_r": -3.0, "loss_streak": 3, "sel_z": 0.0, "sel_min_n": 40, "max_per_signal": 2, "n_agents": 50, "variants": "loudtrend", "sel_window_days": 0, "evidence": "all"}`

## The 50 agents in the live model (the last quarter's choice; history = all their signals to the end)

| Agent | Signal | Group | Candles | When | Signals | Avg R (all history) | Win | Walk-forward trades | Walk-forward avg R |
|---|---|---|---|---|---|---|---|---|---|
| ORION | Volume spike on a green candle | majors | 4h | big moves in uptrends | 42 | +0.650 | 86% | 0 | — |
| VEGA | Inside bar breakdown | majors | 1h | big moves in uptrends | 63 | +0.583 | 71% | 1 | -1.220 |
| NOVA | Big green candle (momentum ignition) | majors | 4h | big moves in uptrends | 81 | +0.552 | 74% | 1 | +1.904 |
| ATLAS | P6 opening range breakout (Jarvus) | majors | 1h | big moves in uptrends | 57 | +0.521 | 63% | 2 | +0.360 |
| LYRA | NR7 breakout up | memes | 4h | big moves in uptrends | 58 | +0.505 | 52% | 1 | +1.962 |
| TITAN | MFI above 80 | majors | 4h | big moves in uptrends | 51 | +0.504 | 71% | 1 | -1.044 |
| AEGIS | Break of structure up (trend continuation) | majors | 4h | big moves in uptrends | 55 | +0.496 | 69% | 0 | — |
| HELIOS | Big 24h rally (momentum) | majors | 1h | big moves in uptrends | 95 | +0.488 | 61% | 10 | -0.132 |
| SIRIUS | Close above the upper Bollinger band | majors | 4h | big moves in uptrends | 68 | +0.481 | 69% | 3 | +1.038 |
| KEPLER | Five green candles in a row | memes | 4h | big moves in uptrends | 56 | +0.476 | 55% | 0 | — |
| POLARIS | Breakout confirmed by OBV | majors | 4h | big moves in uptrends | 88 | +0.464 | 68% | 1 | +0.216 |
| RIGEL | Inside bar | majors | 1h | big moves in uptrends | 177 | +0.451 | 68% | 8 | +0.353 |
| CYGNUS | Big 24h rally (momentum) | majors | 4h | big moves in uptrends | 77 | +0.445 | 69% | 0 | — |
| DRACO | Prior-day high breakout | majors | 4h | big moves in uptrends | 93 | +0.440 | 66% | 6 | +0.255 |
| PULSAR | Spinning top | majors | 1h | big moves in uptrends | 138 | +0.439 | 69% | 6 | +0.517 |
| QUASAR | Shooting star | memes | 4h | big moves in uptrends | 41 | +0.438 | 49% | 0 | — |
| ZENITH | Donchian 20 breakout | majors | 4h | big moves in uptrends | 100 | +0.437 | 66% | 1 | -0.690 |
| AURORA | Hanging man | memes | 1h | big moves in uptrends | 79 | +0.428 | 54% | 2 | +0.420 |
| BOREAS | Floor pivot R1 rejection | memes | 4h | big moves in uptrends | 140 | +0.423 | 54% | 11 | +0.312 |
| CALYPSO | RSI(2) below 10 | majors | 1h | big moves in uptrends | 101 | +0.417 | 70% | 4 | +0.571 |
| CASSINI | RSI(2) below 10 above the 200 SMA (Connors) | majors | 1h | big moves in uptrends | 101 | +0.417 | 70% | 0 | — |
| CEPHEUS | Stochastic RSI bullish cross below 0.2 | majors | 1h | big moves in uptrends | 128 | +0.415 | 62% | 1 | +0.881 |
| ELARA | RSI bearish divergence | majors | 1h | big moves in uptrends | 92 | +0.410 | 63% | 2 | -0.590 |
| EOS | RSI(2) dip (Jarvus) | majors | 1h | big moves in uptrends | 102 | +0.408 | 70% | 0 | — |
| GAIA | CCI above +100 (momentum) | majors | 4h | big moves in uptrends | 46 | +0.405 | 65% | 0 | — |
| HALO | Hammer | memes | 1h | big moves in uptrends | 70 | +0.398 | 56% | 0 | — |
| HERMES | Doji after a rise | memes | 4h | big moves in uptrends | 89 | +0.395 | 54% | 4 | +0.186 |
| HYDRA | Big green candle (momentum ignition) | majors | 1h | big moves in uptrends | 90 | +0.391 | 53% | 2 | +0.553 |
| HYPERION | Keltner channel breakout | majors | 4h | big moves in uptrends | 55 | +0.385 | 64% | 0 | — |
| ICARUS | Five green candles in a row | majors | 1h | big moves in uptrends | 68 | +0.384 | 57% | 0 | — |
| JUNO | MACD crosses below signal | majors | 1h | big moves in uptrends | 127 | +0.383 | 65% | 1 | +0.111 |
| MIRA | Doji after a rise | majors | 1h | big moves in uptrends | 100 | +0.381 | 66% | 2 | -0.337 |
| NYX | Donchian 55 breakout (turtle) | majors | 4h | big moves in uptrends | 100 | +0.381 | 64% | 0 | — |
| OBERON | Outside bar, down close | memes | 1h | big moves in uptrends | 127 | +0.379 | 55% | 4 | +0.070 |
| PALLAS | Donchian 55 breakout (turtle) | majors | 1h | big moves in uptrends | 117 | +0.379 | 56% | 5 | +1.637 |
| PHOEBE | Bearish engulfing | majors | 1h | big moves in uptrends | 81 | +0.377 | 65% | 1 | +1.926 |
| RHEA | MFI above 80 | memes | 4h | big moves in uptrends | 112 | +0.371 | 49% | 8 | -0.331 |
| SELENE | Prior-day high breakout | majors | 1h | big moves in uptrends | 79 | +0.364 | 56% | 0 | — |
| SPICA | EMA 9/21 bearish cross | majors | 1h | big moves in uptrends | 41 | +0.359 | 66% | 0 | — |
| TALOS | NR7 breakout up | majors | 1h | big moves in uptrends | 104 | +0.359 | 59% | 3 | +0.569 |
| TETHYS | OBV new high before price | majors | 1h | big moves in uptrends | 59 | +0.358 | 59% | 0 | — |
| THEIA | MACD histogram turns up | majors | 1h | big moves in uptrends | 113 | +0.356 | 62% | 1 | +1.875 |
| TRITON | Heikin-Ashi turns green | majors | 1h | big moves in uptrends | 104 | +0.356 | 66% | 0 | — |
| VESTA | RSI bearish divergence | memes | 1h | big moves in uptrends | 164 | +0.354 | 51% | 5 | -0.482 |
| ZEPHYR | Loss of the 24h VWAP | majors | 1h | big moves in uptrends | 81 | +0.353 | 73% | 2 | +0.208 |
| ARGUS | Three outside down | memes | 4h | big moves in uptrends | 42 | +0.351 | 45% | 0 | — |
| ALTAIR | OBV new high before price | memes | 1h | big moves in uptrends | 100 | +0.351 | 53% | 2 | -1.115 |
| DENEB | Heikin-Ashi turns red | majors | 1h | big moves in uptrends | 161 | +0.350 | 62% | 3 | -0.784 |
| ANTARES | Doji after a drop | majors | 1h | big moves in uptrends | 66 | +0.350 | 68% | 0 | — |
| CASTOR | Break of structure up (trend continuation) | memes | 4h | big moves in uptrends | 76 | +0.347 | 54% | 0 | — |

## What this does not show

- Real fills: limit orders may fill less often or at worse prices live; the stops assume no gaps beyond the bar.
- The future: 2022-2026 contained a bear market, a recovery and a bull run; other markets may differ.
- The selection of signals, exits and coins was informed by earlier research on this same history, so even the
  walk-forward is somewhat optimistic. Paper-trade it before trusting it with money.
