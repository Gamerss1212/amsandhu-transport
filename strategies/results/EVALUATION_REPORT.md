# Evaluation report

Generated 2026-09-29 06:16 UTC (code b3b93ac, experiment EXP-818800ed63). Protocol: VALIDATION_METHODOLOGY.md (fixed parameters, chronological 60/20/20 with a one-day embargo, 4 walk-forward folds, three cost levels, Holm across every test). All numbers are after costs unless marked gross.

## Headline

- Strategies evaluated: 143 on 917 strategy-instrument pairs; 1,834 cost-level runs, each split into train, validation, test, 4 folds and the full period: **14,672 backtests** (plus 917 gross runs).
- Hypothesis tests counted: 1,834. **Significant after Holm correction: 0.**
- Deflated Sharpe ratio of the best validation Sharpe: 0.000 (about 0 means the best result is what luck alone would produce with this many tries).
- Crypto at Kraken retail fees (0.40% maker / 0.80% taker): 0 of 353 runs profitable. At a low-fee venue (0.10% taker): 14 of 353.
- Stocks with base costs: 102 of 564 runs profitable with 20+ trades.
- Gross (before any cost) 383 realistic-cost runs had a positive edge: costs remove most of them.
- Candidates (positive on train AND validation, 30+ trades, realistic costs): 49 runs from 34 strategies. On the untouched test segment 8 of 49 stayed positive; average expectancy +0.056R (full period) vs -0.218R (test).

## Top 25 runs at realistic costs

| Strategy | Instrument | Trades | R/trade | Gross R | Win % | Net return | Folds + | Test R (trades) | Holm |
|---|---|---|---|---|---|---|---|---|---|
| STRAT-137 Ornstein-Uhlenbeck reversion with half-life filter | TSLA | 49 | +0.279 | +0.292 | 53% | +6.97% | 4/4 | +0.460 (17) | no |
| STRAT-069 Mass Index reversal bulge (Dorsey) | TSLA | 59 | +0.237 | +0.256 | 54% | +6.98% | 4/4 | +0.466 (12) | no |
| STRAT-054 Reversion to the prior point of control | QQQ | 52 | +0.219 | +0.304 | 44% | +3.86% | 3/4 | -0.402 (10) | no |
| STRAT-107 Beta-adjusted residual reversion | NVDA | 79 | +0.197 | +0.264 | 57% | +7.18% | 3/4 | +0.287 (18) | no |
| STRAT-162 Liquidity sweep then structure shift | NVDA | 62 | +0.180 | +0.199 | 47% | +5.81% | 3/4 | -0.218 (11) | no |
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
| STRAT-162 Liquidity sweep then structure shift | SPY | 53 | +0.045 | +0.120 | 51% | +2.06% | 4/4 | -0.005 (11) | no |

## Knowledge-pack formalizations (core)

| Strategy | Pack id | Best instrument | Trades | R/trade (full) | Gross R | Test R (trades) | Candidate |
|---|---|---|---|---|---|---|---|
| STRAT-158 Range-boundary breakout retest | ST004 | TSLA | 70 | +0.026 | +0.067 | -0.850 (14) | yes |
| STRAT-159 Volatility-normalized time-series momentum | ST009 | TSLA | 29 | +0.077 | +0.089 | -0.022 (7) | no |
| STRAT-160 RSI extreme recovery | ST023 | AAPL | 35 | +0.167 | +0.188 | +0.061 (6) | no |
| STRAT-161 FOMC post-announcement drift | ST045 | SPY | 1 | -1.075 | -1.009 | -1.075 (1) | no |
| STRAT-162 Liquidity sweep then structure shift | ST098 | NVDA | 62 | +0.180 | +0.199 | -0.218 (11) | yes |
| STRAT-163 Order-block retest | ST099 | NVDA | 12 | +0.392 | +0.417 | -0.039 (3) | no |

## Knowledge-pack memecoin hypotheses (six Coinbase-listed memecoins, 120 days)

| Strategy | Pack id | Best instrument | Trades | R/trade (full) | Gross R | Test R (trades) | Candidate |
|---|---|---|---|---|---|---|---|
| STRAT-164 Memecoin breadth-led momentum | ST181 | WIF-USD | 188 | -1.037 | -0.029 | -0.709 (70) | no |
| STRAT-165 Memecoin leader pullback | ST182 | DOGE-USD | 170 | -1.806 | -0.179 | -1.208 (33) | no |
| STRAT-166 Memecoin laggard catch-up breakout | ST183 | BONK-USD | 32 | -0.558 | +0.351 | -0.568 (9) | no |
| STRAT-167 Memecoin leader-to-follower transmission | ST186 | FLOKI-USD | 138 | -2.451 | -0.090 | -2.625 (60) | no |
| STRAT-168 Bitcoin risk-on memecoin participation | ST222 | BONK-USD | 125 | -1.097 | -0.135 | -0.874 (30) | no |
| STRAT-169 Selloff-resilient memecoin rebound | ST223 | BONK-USD | 22 | -0.762 | +0.046 | -0.234 (3) | no |
| STRAT-170 Memecoin residual reversion vs bitcoin | ST224 | BONK-USD | 57 | -0.886 | +0.352 | -1.282 (13) | no |
| STRAT-171 Memecoin volatility contraction release | ST225 | FLOKI-USD | 16 | -0.461 | +0.581 | -0.474 (14) | no |
| STRAT-172 Memecoin session-handover continuation | ST227 | BONK-USD | 5 | -0.484 | +0.200 | -1.532 (1) | no |
| STRAT-173 Memecoin liquidation-aftershock reclaim | ST229 | BONK-USD | 63 | -0.913 | -0.033 | -0.503 (14) | no |
| STRAT-174 Memecoin native-price range breakout | ST233 | WIF-USD | 116 | -1.026 | -0.081 | -0.773 (54) | no |
| STRAT-175 Two-stage compression breakout | ST234 | FLOKI-USD | 377 | -1.779 | -0.014 | -2.197 (84) | no |
| STRAT-176 Selloff-range midpoint acceptance | ST239 | BONK-USD | 47 | -1.281 | +0.112 | -1.307 (8) | no |
| STRAT-177 Memecoin relative-momentum leader | ST271 | BONK-USD | 199 | -1.049 | -0.040 | -0.768 (44) | no |

## Reading

The stock sample is 60 days and the crypto sample 120 days, so each candidate's test segment holds 10-25 trades: single results are noisy. The pattern across all runs is the finding: some rules have a gross edge, costs remove most of it, and nothing survives correction for the number of ideas tested. Memecoin results use exchange-listed survivors and are biased upward relative to newly launched tokens.

