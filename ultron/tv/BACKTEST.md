# Ultron: training and backtest report

Generated 2026-10-03 04:43 UTC by `ultron/tools/train.py` in 6.6 minutes.
1420 candidate agents (814,522 historical signals, every one traded with Ultron's exits at NDAX fees).
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
| Development | 232 | +0.151 | 1.99 | 48% | +30.33% | 6.06% |
| Validation | 60 | +0.068 | 0.43 | 40% | +3.10% | 5.72% |
| **Test (untouched)** | 68 | +0.105 | 0.77 | 46% | +5.10% | 7.06% |
| All | 360 | +0.128 | 2.1 | 46% | +41.22% | 8.33% |

Decisions: 360 signals taken, 3,368 refused.

## Extreme tests

| Test | Trades | Avg R | t | Win | Return | Max drawdown |
|---|---|---|---|---|---|---|
| NDAX fees x2 | 346 | +0.054 | 0.89 | 46% | +17.35% | 10.17% |
| Kraken Pro entry-tier fees | 321 | +0.014 | 0.22 | 44% | +9.70% | 7.81% |
| slippage x3 | 345 | +0.075 | 1.2 | 45% | +25.76% | 9.89% |

**200 random 90-day windows** (fresh account each): median +1.59%, 10th percentile -1.67%, 90th +6.20%, best +10.00%, worst -5.92%; positive in 141 of 200; 0 had no trade; 18.1 trades per window.

**2,000 bootstrap reshuffles** of the walk-forward trades: final return 5th / 50th / 95th percentile +12.9% / +41.6% / +76.8%; ended below the start in 0.7%; max drawdown median 6.9%, 95th percentile 12.5%.

## The improvement loop

100 proposals, each one setting changed at a time; kept only if development improved and validation did not get worse.

| # | Change | Dev trades | Dev avg R | Dev return | Val avg R | Val return | Kept |
|---|---|---|---|---|---|---|---|
| 0 | start (defaults) | 260 | +0.002 | +1.29% | +0.014 | +0.10% | yes |
| 1 | theta = 0.0 | 270 | +0.001 | +0.90% | +0.014 | +0.10% |  |
| 2 | theta = -0.05 | 272 | +0.009 | +3.57% | +0.014 | +0.10% | yes |
| 3 | max_open = 1 | 195 | -0.050 | -1.06% | -0.075 | -1.34% |  |
| 4 | z = 2.0 | 263 | +0.021 | +4.40% | +0.016 | +0.11% | yes |
| 5 | sel_min_n = 150 | 427 | -0.004 | -6.21% | +0.102 | +3.87% |  |
| 6 | loud_mult = 1.0 | 262 | +0.022 | +9.27% | +0.035 | +2.07% | yes |
| 7 | max_per_signal = 4 | 247 | +0.024 | +10.11% | -0.005 | -0.23% |  |
| 8 | z = 0.0 | 271 | +0.014 | +9.03% | -0.035 | -0.79% |  |
| 9 | max_meme_open = 3 | 267 | +0.036 | +11.97% | -0.008 | -0.34% |  |
| 10 | sel_window_days = 365 | 332 | +0.040 | +10.12% | -0.162 | -6.97% |  |
| 11 | regime_rule = learned | 347 | +0.019 | +10.21% | +0.065 | +3.00% |  |
| 12 | theta = 0.08 | 205 | -0.019 | +0.75% | +0.052 | +2.94% |  |
| 13 | theta = 0.03 | 235 | +0.008 | +5.61% | +0.035 | +2.07% |  |
| 14 | sel_window_days = 730 | 280 | -0.012 | -1.11% | -0.012 | -0.74% |  |
| 15 | size_a = 2.0 | 262 | +0.022 | +10.13% | +0.035 | +2.03% | yes |
| 16 | z = 0.5 | 271 | +0.016 | +10.20% | +0.014 | +1.45% |  |
| 17 | z = 1.5 | 270 | +0.006 | +8.24% | +0.036 | +2.05% |  |
| 18 | variants = loud_only | 187 | +0.053 | +13.01% | -0.006 | +0.96% |  |
| 19 | theta = 0.08 | 205 | -0.019 | -0.12% | +0.052 | +2.99% |  |
| 20 | gate_rule = loud_only | 194 | +0.098 | +21.68% | +0.034 | +1.95% | yes |
| 21 | variants = loudtrend | 146 | +0.068 | +9.02% | +0.024 | +1.03% |  |
| 22 | sel_min_n = 150 | 186 | +0.103 | +13.42% | +0.125 | +5.17% |  |
| 23 | z = 1.5 | 199 | +0.082 | +19.48% | +0.034 | +1.97% |  |
| 24 | size_a = 1.0 | 194 | +0.098 | +19.01% | +0.034 | +1.98% |  |
| 25 | max_open = 1 | 130 | +0.024 | +9.73% | -0.118 | -2.00% |  |
| 26 | max_meme_open = 1 | 161 | +0.110 | +21.02% | +0.067 | +2.35% |  |
| 27 | max_meme_open = 3 | 198 | +0.114 | +23.86% | -0.007 | +0.62% |  |
| 28 | theta = 0.05 | 169 | +0.114 | +18.25% | +0.078 | +3.61% |  |
| 29 | shrink = 5.0 | 185 | +0.091 | +19.40% | +0.034 | +1.95% |  |
| 30 | z = 0.0 | 201 | +0.077 | +18.14% | +0.011 | +1.37% |  |
| 31 | max_open = 2 | 176 | +0.078 | +17.37% | +0.010 | +0.19% |  |
| 32 | max_per_signal = 1 | 200 | +0.133 | +23.57% | +0.067 | +1.32% |  |
| 33 | variants = loud_only | 187 | +0.053 | +13.01% | -0.006 | +0.96% |  |
| 34 | theta = 0.03 | 173 | +0.105 | +19.00% | +0.034 | +1.95% |  |
| 35 | gate_rule = learned | 262 | +0.022 | +10.13% | +0.035 | +2.03% |  |
| 36 | max_open = 4 | 194 | +0.098 | +21.68% | +0.034 | +1.95% |  |
| 37 | loud_mult = 0.6 | 194 | +0.097 | +12.57% | +0.013 | +0.90% |  |
| 38 | theta = 0.08 | 156 | +0.080 | +14.14% | +0.078 | +3.61% |  |
| 39 | shrink = 40.0 | 195 | +0.094 | +20.79% | +0.034 | +1.95% |  |
| 40 | theta = 0.18 | 131 | +0.146 | +16.34% | +0.074 | +3.09% |  |
| 41 | sel_z = 0.0 | 186 | +0.087 | +16.31% | +0.075 | +3.65% |  |
| 42 | regime_rule = learned | 224 | +0.131 | +27.47% | +0.065 | +2.84% | yes |
| 43 | weekend_off = False | 227 | +0.131 | +27.57% | +0.068 | +3.08% |  |
| 44 | sel_min_n = 80 | 217 | +0.116 | +18.95% | +0.044 | +1.72% |  |
| 45 | shrink = 80.0 | 224 | +0.119 | +24.29% | +0.065 | +2.84% |  |
| 46 | z = 1.0 | 241 | +0.122 | +27.15% | +0.044 | +2.26% |  |
| 47 | sel_window_days = 730 | 247 | +0.128 | +22.02% | +0.034 | +0.46% |  |
| 48 | max_open = 4 | 224 | +0.131 | +27.47% | +0.065 | +2.84% |  |
| 49 | sel_min_n = 20 | 221 | +0.101 | +19.76% | +0.181 | +5.18% |  |
| 50 | shrink = 5.0 | 209 | +0.100 | +21.74% | +0.065 | +2.84% |  |
| 51 | shrink = 10.0 | 216 | +0.118 | +25.11% | +0.065 | +2.84% |  |
| 52 | max_open = 1 | 139 | +0.033 | +8.53% | -0.109 | -2.00% |  |
| 53 | z = 0.0 | 255 | +0.127 | +26.77% | +0.044 | +2.26% |  |
| 54 | size_a = 0.0 | 224 | +0.130 | +17.55% | +0.045 | +1.58% |  |
| 55 | z = 1.5 | 235 | +0.139 | +28.47% | +0.066 | +2.86% | yes |
| 56 | shrink = 10.0 | 228 | +0.150 | +29.80% | +0.066 | +2.86% | yes |
| 57 | z = 0.5 | 243 | +0.138 | +27.33% | +0.044 | +2.26% |  |
| 58 | variants = loud_only | 215 | +0.089 | +18.37% | +0.048 | +2.38% |  |
| 59 | sel_window_days = 365 | 245 | +0.086 | +13.99% | +0.023 | +1.10% |  |
| 60 | theta = 0.05 | 208 | +0.095 | +21.26% | +0.066 | +2.86% |  |
| 61 | z = 0.0 | 252 | +0.123 | +26.22% | +0.044 | +2.26% |  |
| 62 | sel_window_days = 730 | 252 | +0.145 | +25.26% | +0.057 | +1.10% |  |
| 63 | size_a = 0.0 | 228 | +0.149 | +19.27% | +0.066 | +1.93% |  |
| 64 | sel_min_n = 150 | 196 | +0.121 | +15.97% | +0.210 | +8.27% |  |
| 65 | theta = 0.0 | 221 | +0.133 | +28.21% | +0.066 | +2.86% |  |
| 66 | shrink = 80.0 | 239 | +0.129 | +25.90% | +0.065 | +2.84% |  |
| 67 | max_per_signal = 4 | 222 | +0.146 | +29.31% | +0.043 | +0.77% |  |
| 68 | sel_min_n = 80 | 227 | +0.086 | +15.91% | +0.068 | +2.41% |  |
| 69 | theta = 0.03 | 216 | +0.116 | +24.51% | +0.066 | +2.86% |  |
| 70 | sel_min_n = 20 | 227 | +0.098 | +19.41% | +0.181 | +5.18% |  |
| 71 | shrink = 40.0 | 240 | +0.133 | +27.54% | +0.066 | +2.86% |  |
| 72 | size_a = 1.0 | 228 | +0.150 | +26.70% | +0.066 | +2.97% |  |
| 73 | sel_z = 0.0 | 235 | +0.154 | +27.66% | +0.138 | +5.19% |  |
| 74 | theta = 0.18 | 167 | +0.083 | +13.68% | +0.112 | +4.81% |  |
| 75 | evidence = since_selected | 157 | +0.104 | +12.75% | +0.049 | +1.89% |  |
| 76 | max_meme_open = 3 | 232 | +0.163 | +32.13% | +0.026 | +1.52% |  |
| 77 | theta = 0.12 | 187 | +0.068 | +14.71% | +0.109 | +4.54% |  |
| 78 | max_meme_open = 1 | 185 | +0.138 | +24.98% | +0.107 | +3.25% |  |
| 79 | max_per_signal = 1 | 236 | +0.175 | +31.84% | +0.067 | +1.38% |  |
| 80 | loud_mult = 0.6 | 228 | +0.149 | +17.03% | +0.066 | +1.74% |  |
| 81 | regime_rule = memes_off_in_bear | 195 | +0.099 | +21.47% | +0.034 | +1.97% |  |
| 82 | gate_rule = learned | 359 | +0.033 | +14.68% | +0.066 | +2.94% |  |
| 83 | max_open = 4 | 228 | +0.150 | +29.80% | +0.066 | +2.86% |  |
| 84 | weekend_off = False | 232 | +0.151 | +30.33% | +0.068 | +3.10% | yes |
| 85 | gate_rule = learned | 369 | +0.021 | +9.57% | +0.030 | +0.95% |  |
| 86 | theta = 0.18 | 169 | +0.093 | +15.51% | +0.119 | +5.31% |  |
| 87 | shrink = 20.0 | 239 | +0.139 | +29.01% | +0.068 | +3.10% |  |
| 88 | theta = 0.03 | 219 | +0.108 | +23.00% | +0.068 | +3.10% |  |
| 89 | max_meme_open = 1 | 189 | +0.140 | +25.80% | +0.108 | +3.49% |  |
| 90 | theta = 0.12 | 188 | +0.075 | +16.11% | +0.116 | +5.03% |  |
| 91 | weekend_off = True | 228 | +0.150 | +29.80% | +0.066 | +2.86% |  |
| 92 | evidence = since_selected | 160 | +0.110 | +14.00% | +0.058 | +2.37% |  |
| 93 | z = 2.0 | 219 | +0.115 | +24.57% | +0.068 | +3.08% |  |
| 94 | regime_rule = memes_off_in_bear | 199 | +0.100 | +21.96% | +0.038 | +2.20% |  |
| 95 | shrink = 40.0 | 244 | +0.133 | +28.14% | +0.068 | +3.10% |  |
| 96 | z = 1.0 | 242 | +0.129 | +27.59% | +0.047 | +2.50% |  |
| 97 | variants = loud_only | 217 | +0.080 | +16.45% | +0.051 | +2.62% |  |
| 98 | max_meme_open = 3 | 236 | +0.163 | +32.66% | +0.021 | +1.28% |  |
| 99 | sel_z = 0.5 | 232 | +0.167 | +30.48% | +0.089 | +3.59% |  |
| 100 | z = 0.0 | 256 | +0.123 | +26.73% | +0.047 | +2.50% |  |

Final settings: `{"theta": -0.05, "z": 1.5, "shrink": 10.0, "size_a": 2.0, "gate_rule": "loud_only", "loud_mult": 1.0, "weekend_off": false, "regime_rule": "learned", "max_open": 3, "max_major_open": 1, "max_meme_open": 2, "risk_major": 0.006, "risk_meme": 0.003, "daily_stop_r": -3.0, "loss_streak": 3, "sel_z": 1.0, "sel_min_n": 40, "max_per_signal": 2, "n_agents": 25, "variants": "all", "sel_window_days": 0, "evidence": "all"}`

## The 50 agents in the live model (the last quarter's choice; history = all their signals to the end)

| Agent | Signal | Group | Candles | When | Signals | Avg R (all history) | Win | Walk-forward trades | Walk-forward avg R |
|---|---|---|---|---|---|---|---|---|---|
| ORION | Volume spike on a green candle | majors | 4h | big moves in uptrends | 47 | +0.539 | 83% | 0 | — |
| VEGA | Hanging man | memes | 1h | big moves in uptrends | 62 | +0.499 | 55% | 0 | — |
| NOVA | Hammer | memes | 1h | big moves in uptrends | 63 | +0.485 | 56% | 1 | -0.496 |
| ATLAS | Big green candle (momentum ignition) | majors | 4h | big moves in uptrends | 90 | +0.477 | 72% | 2 | +1.065 |
| LYRA | Spinning top | majors | 1h | big moves in uptrends | 131 | +0.477 | 69% | 14 | +0.799 |
| TITAN | Five green candles in a row | memes | 4h | big moves in uptrends | 54 | +0.468 | 54% | 0 | — |
| AEGIS | Five green candles in a row | memes | 4h | big-move periods | 63 | +0.459 | 56% | 5 | +0.283 |
| HELIOS | Shooting star | majors | 1h | big-move periods | 51 | +0.449 | 63% | 0 | — |
| SIRIUS | MFI above 80 | majors | 4h | big moves in uptrends | 51 | +0.445 | 72% | 1 | -1.062 |
| KEPLER | Volume spike on a green candle | majors | 4h | big-move periods | 65 | +0.444 | 74% | 1 | +1.879 |
| POLARIS | Close above the upper Bollinger band | majors | 4h | big-move periods | 88 | +0.438 | 70% | 3 | +0.093 |
| RIGEL | Doji after a drop | majors | 1h | big moves in uptrends | 56 | +0.437 | 71% | 4 | +0.436 |
| CYGNUS | Close above the upper Bollinger band | majors | 4h | big moves in uptrends | 74 | +0.431 | 69% | 0 | — |
| DRACO | MFI above 80 | majors | 4h | big-move periods | 55 | +0.428 | 73% | 0 | — |
| PULSAR | Bearish engulfing | majors | 1h | big moves in uptrends | 89 | +0.426 | 66% | 1 | +1.898 |
| QUASAR | Big green candle (momentum ignition) | majors | 4h | big-move periods | 117 | +0.424 | 70% | 5 | -0.301 |
| ZENITH | Outside bar, up close | majors | 1h | big moves in uptrends | 80 | +0.423 | 61% | 0 | — |
| AURORA | Inside bar breakdown | majors | 1h | big moves in uptrends | 72 | +0.420 | 67% | 5 | +0.100 |
| BOREAS | OBV new high before price | majors | 1h | big moves in uptrends | 61 | +0.412 | 62% | 0 | — |
| CALYPSO | Doji after a rise | majors | 1h | big moves in uptrends | 85 | +0.404 | 67% | 1 | +0.132 |
| CASSINI | Inside bar | majors | 1h | big moves in uptrends | 148 | +0.398 | 64% | 3 | +1.895 |
| CEPHEUS | Breakout confirmed by OBV | majors | 4h | big moves in uptrends | 102 | +0.378 | 67% | 0 | — |
| ELARA | Breakout confirmed by OBV | majors | 4h | big-move periods | 115 | +0.377 | 69% | 0 | — |
| EOS | Donchian 20 breakout | majors | 4h | big-move periods | 125 | +0.365 | 64% | 1 | -0.037 |
| GAIA | Donchian 20 breakout | majors | 4h | big moves in uptrends | 110 | +0.351 | 62% | 0 | — |

## What this does not show

- Real fills: limit orders may fill less often or at worse prices live; the stops assume no gaps beyond the bar.
- The future: 2022-2026 contained a bear market, a recovery and a bull run; other markets may differ.
- The selection of signals, exits and coins was informed by earlier research on this same history, so even the
  walk-forward is somewhat optimistic. Paper-trade it before trusting it with money.
