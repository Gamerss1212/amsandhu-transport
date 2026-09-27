# Evaluation report

Generated 2026-09-27 21:20 UTC (code 64c9981, experiment EXP-9162a9d000). Protocol: VALIDATION_METHODOLOGY.md. All numbers are after costs unless marked gross.

## Headline

- Strategies evaluated: 123 (the 4 order-flow strategies need recorded live data and were not backtested).
- Hypothesis tests counted: 1608 (strategy x instrument x cost level).
- **Significant after Holm correction: 0.** No strategy shows an edge that survives testing this many ideas.
- Deflated Sharpe ratio of the best validation Sharpe: 0.000 (probability the best result beats luck; ~0 means it does not).
- Crypto at Kraken retail fees (0.40% maker / 0.80% taker): **0 of 265 runs profitable.**
- Stocks with base costs: 93 of 512 runs profitable with 20+ trades.
- Candidates (positive on train AND validation, 30+ trades, realistic costs): 46 runs from 32 strategies. On the untouched test segment 8 of 46 stayed positive; average expectancy fell from +0.054R (full period) to -0.209R (test).

Reading: with 60 days of stock data and ~120 days of crypto data, a candidate's test segment has only 10-25 trades, so single results are noisy. The pattern across all runs (gross edges exist in some rules, costs remove most of them, nothing survives multiple testing) is the finding.

## Top 25 runs at realistic costs (ranked per RANKING_METHODOLOGY.md)

| Strategy | Instrument | Trades | R/trade | Gross R | Win % | Net return | Folds + | Test R (trades) | Holm |
|---|---|---|---|---|---|---|---|---|---|
| STRAT-137 Ornstein-Uhlenbeck reversion with half-life filter | TSLA | 49 | +0.279 | +0.292 | 53% | +6.97% | 4/4 | +0.460 (17) | no |
| STRAT-069 Mass Index reversal bulge (Dorsey) | TSLA | 59 | +0.237 | +0.256 | 54% | +6.98% | 4/4 | +0.466 (12) | no |
| STRAT-054 Reversion to the prior point of control | QQQ | 52 | +0.219 | +0.304 | 44% | +3.86% | 3/4 | -0.402 (10) | no |
| STRAT-107 Beta-adjusted residual reversion | NVDA | 79 | +0.197 | +0.264 | 57% | +7.18% | 3/4 | +0.287 (18) | no |
| STRAT-059 Momentum ignition (ROC shock) | TSLA | 80 | +0.177 | +0.214 | 45% | +6.89% | 3/4 | +0.083 (19) | no |
| STRAT-012 Regression-slope trend with R-squared filter | TSLA | 56 | +0.173 | +0.203 | 50% | +4.81% | 3/4 | -0.415 (10) | no |
| STRAT-057 CCI +100 trend entry (Lambert) | AAPL | 120 | +0.129 | +0.173 | 37% | +6.94% | 2/4 | -0.052 (24) | no |
| STRAT-007 Supertrend direction flip | AAPL | 77 | +0.106 | +0.148 | 44% | +4.08% | 3/4 | +0.179 (14) | no |
| STRAT-006 Directional-movement crossover (Wilder DMI) | NVDA | 81 | +0.105 | +0.141 | 33% | +4.92% | 2/4 | -0.267 (17) | no |
| STRAT-006 Directional-movement crossover (Wilder DMI) | AAPL | 68 | +0.098 | +0.147 | 34% | +2.28% | 1/4 | -0.135 (15) | no |
| STRAT-037 Turtle Soup (failed 20-bar breakdown) | AAPL | 87 | +0.096 | +0.251 | 41% | +1.24% | 3/4 | -0.025 (18) | no |
| STRAT-091 On-balance-volume divergence | QQQ | 104 | +0.092 | +0.144 | 41% | +1.98% | 1/4 | +0.350 (16) | no |
| STRAT-059 Momentum ignition (ROC shock) | AAPL | 72 | +0.089 | +0.160 | 38% | +2.00% | 1/4 | -0.440 (20) | no |
| STRAT-059 Momentum ignition (ROC shock) | NVDA | 67 | +0.085 | +0.191 | 39% | +2.15% | 3/4 | -0.213 (12) | no |
| STRAT-041 Round-number rejection | TSLA | 92 | +0.084 | +0.113 | 46% | +1.99% | 3/4 | -0.414 (16) | no |
| STRAT-085 Fair-value-gap fill continuation | NVDA | 97 | +0.081 | +0.063 | 46% | +1.78% | 2/4 | -0.354 (19) | no |
| STRAT-049 VWAP reclaim after a sustained move below | TSLA | 68 | +0.078 | +0.098 | 62% | +2.78% | 3/4 | -0.149 (16) | no |
| STRAT-019 Opening-range breakout on a closing basis | AAPL | 55 | +0.070 | +0.094 | 47% | +1.15% | 1/4 | -0.182 (10) | no |
| STRAT-008 Parabolic SAR reversal | NVDA | 119 | +0.068 | +0.124 | 42% | +3.65% | 2/4 | -0.181 (25) | no |
| STRAT-073 Keltner channel breakout | NVDA | 89 | +0.058 | +0.089 | 43% | +3.64% | 3/4 | -0.085 (17) | no |
| STRAT-013 Kaufman adaptive-average cross in efficient markets | QQQ | 87 | +0.054 | +0.136 | 33% | -0.11% | 2/4 | +0.089 (20) | no |
| STRAT-050 Anchored VWAP from the last swing low | NVDA | 112 | +0.050 | +0.119 | 40% | +2.06% | 3/4 | -0.189 (22) | no |
| STRAT-008 Parabolic SAR reversal | AAPL | 118 | +0.046 | +0.122 | 42% | +5.17% | 2/4 | -0.089 (24) | no |
| STRAT-050 Anchored VWAP from the last swing low | TSLA | 112 | +0.037 | +0.124 | 39% | +1.90% | 2/4 | -0.352 (23) | no |
| STRAT-096 Elder impulse system turn | AAPL | 120 | +0.035 | +0.115 | 29% | -0.76% | 2/4 | -0.283 (24) | no |

Full per-run detail: `evaluation_summary.json` and the workbook's *Evaluation Results* sheet.
