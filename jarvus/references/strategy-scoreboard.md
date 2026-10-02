# Strategy scoreboard: every strategy the Terminal could test, its exact rules, and what it measured

Source: the Jarvus Terminal's batch evaluation (generated 2026-09-29 06:16 UTC; swing set 2026-09-29 22:01 UTC). 146 strategies with executable rules, 932 strategy-market pairs, 1834 + 30 hypothesis tests. **Significant after Holm correction: 0 and 0.** Read every positive number below as a lead to test, not an edge.

**How it was measured** (`terminal-evidence.md` has the full protocol): parameters fixed before any data was seen; crypto = Coinbase 5-minute bars, about 120 days to late Sept 2026 (BTC, ETH, SOL; 1-minute BTC for 14 days; memecoins DOGE, SHIB, PEPE, BONK, FLOKI, WIF); stocks = Yahoo 5-minute bars, 60 days (SPY, QQQ, NVDA, AAPL, TSLA); swing set = Coinbase hourly, up to 5.5 years. Chronological 60/20/20 split with a one-day embargo, 4 walk-forward folds. Risk 0.5% per trade on fixed capital.

**Columns** (R per trade over the full period, number of trades in brackets): `gross` = no costs at all · `low` = a low-fee crypto venue (0.08% maker / 0.10% taker) · `retail` = Kraken Pro entry tier (0.40% / 0.80%) · for stocks `net` = commission-free broker with spread and regulatory fees, `2x slip` = slippage doubled · `folds` = walk-forward folds with a positive net result · `test` = the untouched last 20%, shown only for candidates (positive on train AND validation with 30+ trades), because the protocol looks at it once and only for them.

**NDAX (0.20% flat) and other fee levels:** net R is linear in the fee for the same trades, so estimate `R(fee) = low + (retail - low) x (taker - 0.10%) / 0.70%` (NDAX: low + 0.14 x (retail - low)). `scripts/decide.py --strategy <id or name>` does this for you. Coinbase Advanced's entry tier (1.20% taker) is worse than the retail column.

**The rule language** (`rule-language.md`): `ema(close,21)`, `vwap()`, `atr(14)`, `rsi(close,2)`, `cross_above(a,b)`, `highest(high,20)[1]` (the previous bar's value), `session_high()`, `or_high(15)` (opening range), `pdh()` (prior day high) and so on, evaluated on completed bars only.

## Contents

- [candlestick](#candlestick) (5)
- [cross asset](#cross-asset) (5)
- [crypto structure](#crypto-structure) (6)
- [gaps](#gaps) (6)
- [market profile](#market-profile) (5)
- [market structure](#market-structure) (11)
- [mean reversion](#mean-reversion) (10)
- [memecoin](#memecoin) (14)
- [momentum](#momentum) (5)
- [named systems](#named-systems) (4)
- [opening range](#opening-range) (11)
- [reference levels](#reference-levels) (11)
- [scheduled events](#scheduled-events) (4)
- [statistical](#statistical) (3)
- [swing](#swing) (3)
- [time of day](#time-of-day) (6)
- [trend following](#trend-following) (18)
- [volatility](#volatility) (5)
- [volume](#volume) (8)
- [vwap](#vwap) (6)

## The best runs at realistic costs (picked from every tested pair, so optimistic by construction)

| Strategy | Market | Trades | Net R | Gross R | Folds + | Test R (trades) |
|---|---|---|---|---|---|---|
| STRAT-018 5-minute opening-range breakout in the first candle's direction | QQQ | 60 | +0.34 | +0.44 | 2/4 | — |
| STRAT-137 Ornstein-Uhlenbeck reversion with half-life filter | TSLA | 49 | +0.28 | +0.29 | 4/4 | +0.46 (17) |
| STRAT-069 Mass Index reversal bulge (Dorsey) | TSLA | 59 | +0.24 | +0.26 | 4/4 | +0.47 (12) |
| STRAT-035 Prior-day high/low breakout | AAPL | 31 | +0.22 | +0.26 | 2/4 | — |
| STRAT-054 Reversion to the prior point of control | QQQ | 52 | +0.22 | +0.30 | 3/4 | -0.40 (10) |
| STRAT-071 Bollinger squeeze breakout | TSLA | 38 | +0.22 | +0.26 | 3/4 | — |
| STRAT-107 Beta-adjusted residual reversion | NVDA | 79 | +0.20 | +0.26 | 3/4 | +0.29 (18) |
| STRAT-162 Liquidity sweep then structure shift | NVDA | 62 | +0.18 | +0.20 | 3/4 | -0.22 (11) |
| STRAT-059 Momentum ignition (ROC shock) | TSLA | 80 | +0.18 | +0.21 | 3/4 | +0.08 (19) |
| STRAT-012 Regression-slope trend with R-squared filter | TSLA | 56 | +0.17 | +0.20 | 3/4 | -0.41 (10) |
| STRAT-077 Morning star / evening star | AAPL | 44 | +0.17 | +0.29 | 3/4 | — |
| STRAT-160 RSI extreme recovery | AAPL | 35 | +0.17 | +0.19 | 3/4 | — |
| STRAT-074 Range-expansion bar continuation | AAPL | 49 | +0.14 | +0.20 | 2/4 | — |
| STRAT-107 Beta-adjusted residual reversion | AAPL | 85 | +0.14 | +0.23 | 2/4 | — |
| STRAT-092 Money Flow Index extreme reversal | TSLA | 70 | +0.13 | +0.18 | 3/4 | — |
| STRAT-057 CCI +100 trend entry (Lambert) | AAPL | 120 | +0.13 | +0.17 | 2/4 | -0.05 (24) |
| STRAT-160 RSI extreme recovery | QQQ | 38 | +0.12 | +0.15 | 3/4 | — |
| STRAT-007 Supertrend direction flip | AAPL | 77 | +0.11 | +0.15 | 3/4 | +0.18 (14) |
| STRAT-039 Floor-pivot resistance breakout | AAPL | 39 | +0.11 | +0.12 | 2/4 | — |
| STRAT-006 Directional-movement crossover (Wilder DMI) | NVDA | 81 | +0.10 | +0.14 | 2/4 | -0.27 (17) |
| STRAT-015 Aroon trend emergence | AAPL | 89 | +0.10 | +0.15 | 2/4 | — |
| STRAT-006 Directional-movement crossover (Wilder DMI) | AAPL | 68 | +0.10 | +0.15 | 1/4 | -0.14 (15) |
| STRAT-037 Turtle Soup (failed 20-bar breakdown) | AAPL | 87 | +0.10 | +0.25 | 3/4 | -0.03 (18) |
| STRAT-091 On-balance-volume divergence | QQQ | 104 | +0.09 | +0.14 | 1/4 | +0.35 (16) |
| STRAT-409 Swing memecoin 48-hour breakout retest (4 ATR, 3R, 96h, limit entry) | BONK-USD | 113 | +0.09 | +0.26 | 2/4 | — |
| STRAT-021 Failed opening-range breakout fade | QQQ | 32 | +0.09 | +0.20 | 2/4 | — |
| STRAT-038 Floor-pivot support bounce | TSLA | 56 | +0.09 | +0.14 | 2/4 | — |
| STRAT-047 VWAP 2-sigma band reversion | AAPL | 94 | +0.09 | +0.17 | 3/4 | — |
| STRAT-059 Momentum ignition (ROC shock) | AAPL | 72 | +0.09 | +0.16 | 1/4 | -0.44 (20) |
| STRAT-059 Momentum ignition (ROC shock) | NVDA | 67 | +0.09 | +0.19 | 3/4 | -0.21 (12) |

Crypto rows in that table are rare because at retail fees almost nothing on crypto is positive: 2 crypto pairs were positive at Kraken retail fees with 20+ trades. At the low-fee level: 18. Gross (before any cost): 154. Fees, not ideas, decide crypto day trading.

## candlestick

### STRAT-075 Engulfing candle at a 10-bar extreme
*5m · both · stock, crypto* — a full-body reversal at a local extreme

Rules: entry long: `candle().bull_engulf == 1 and low <= lowest(low,10)` · entry short: `candle().bear_engulf == 1 and high >= highest(high,10)` · stop: level long `low`, short `high` + 0.1 ATR buffer · target: 2.0R · time stop: 24 bars · max 2 trades/day

| Crypto | gross | low | retail | folds | test |
|---|---|---|---|---|---|
| BTC-USD | -0.16 (196) | -1.81 (196) | -9.00 (196) | 0/4 | — |
| ETH-USD | -0.01 (172) | -1.29 (172) | -8.70 (172) | 0/4 | — |
| SOL-USD | +0.05 (197) | -1.29 (197) | -5.61 (197) | 0/4 | — |

| Stock | gross | net | 2x slip | folds | test |
|---|---|---|---|---|---|
| AAPL | -0.12 (47) | -0.22 (47) | -0.29 (47) | 2/4 | — |
| NVDA | -0.09 (50) | -0.15 (50) | -0.20 (50) | 2/4 | — |
| QQQ | +0.06 (59) | -0.07 (59) | -0.16 (59) | 2/4 | — |
| SPY | -0.14 (64) | -0.53 (64) | -0.71 (64) | 0/4 | — |
| TSLA | -0.17 (53) | -0.22 (53) | -0.31 (53) | 2/4 | — |

### STRAT-076 Hammer / shooting star at prior-session level
*5m · both · stock, crypto* — long rejection wick at a known level

Rules: entry long: `candle().hammer == 1 and abs(low - session().prev_low) < 0.2*atr(14)` · entry short: `candle().shooting_star == 1 and abs(high - session().prev_high) < 0.2*atr(14)` · stop: level long `low`, short `high` + 0.1 ATR buffer · target: 2.0R · time stop: 24 bars · max 2 trades/day

| Crypto | gross | low | retail | folds | test |
|---|---|---|---|---|---|
| BTC-USD | -0.54 (16) | -2.37 (16) | -9.00 (16) | 0/4 | — |
| ETH-USD | +0.50 (16) | -0.60 (16) | -6.25 (16) | 0/4 | — |
| SOL-USD | +0.16 (21) | -1.44 (21) | -6.72 (21) | 0/4 | — |

| Stock | gross | net | 2x slip | folds | test |
|---|---|---|---|---|---|
| AAPL | +0.11 (8) | +0.05 (8) | -0.00 (8) | 0/4 | — |
| NVDA | -0.68 (9) | -0.77 (9) | -0.85 (9) | 1/4 | — |
| QQQ | -0.40 (7) | -0.51 (7) | -0.61 (7) | 1/4 | — |
| SPY | -0.74 (10) | -0.99 (10) | -1.16 (10) | 1/4 | — |
| TSLA | -0.35 (11) | -0.43 (11) | -0.51 (11) | 0/4 | — |

### STRAT-077 Morning star / evening star
*5m · both · stock, crypto* — selling climax, indecision, then demand

Rules: entry long: `candle().morning_star == 1 and close < ema(close,50)` · entry short: `candle().evening_star == 1 and close > ema(close,50)` · stop: level long `lowest(low,3)`, short `highest(high,3)` + 0.1 ATR buffer · target: 2.0R · time stop: 24 bars · max 2 trades/day

| Crypto | gross | low | retail | folds | test |
|---|---|---|---|---|---|
| BTC-USD | -0.08 (165) | -1.50 (165) | -9.00 (165) | 0/4 | — |
| ETH-USD | +0.06 (155) | -1.04 (155) | -7.64 (155) | 0/4 | — |
| SOL-USD | -0.06 (149) | -1.13 (149) | -4.98 (149) | 0/4 | — |

| Stock | gross | net | 2x slip | folds | test |
|---|---|---|---|---|---|
| AAPL | +0.29 (44) | +0.17 (44) | -0.01 (43) | 3/4 | — |
| NVDA | -0.06 (47) | -0.12 (47) | -0.17 (47) | 1/4 | — |
| QQQ | +0.02 (52) | -0.15 (52) | -0.25 (52) | 2/4 | — |
| SPY | -0.01 (58) | -0.21 (58) | -0.48 (58) | 1/4 | — |
| TSLA | +0.09 (42) | +0.02 (42) | -0.02 (40) | 3/4 | — |

### STRAT-078 Three white soldiers / three black crows continuation
*5m · both · stock, crypto* — three strong same-direction closes show sustained demand

Rules: entry long: `candle().three_soldiers == 1` · entry short: `candle().three_crows == 1` · stop: level long `low[2]`, short `high[2]` · target: 1.5R · time stop: 12 bars · max 2 trades/day

| Crypto | gross | low | retail | folds | test |
|---|---|---|---|---|---|
| BTC-USD | -0.06 (177) | -1.18 (177) | -7.94 (177) | 0/4 | — |
| ETH-USD | +0.09 (125) | -0.70 (125) | -5.49 (125) | 0/4 | — |
| SOL-USD | +0.11 (191) | -0.63 (191) | -3.29 (191) | 0/4 | — |

| Stock | gross | net | 2x slip | folds | test |
|---|---|---|---|---|---|
| AAPL | +0.13 (35) | +0.00 (35) | -0.05 (35) | 2/4 | — |
| NVDA | -0.11 (51) | -0.15 (51) | -0.18 (51) | 1/4 | — |
| QQQ | -0.29 (37) | -0.38 (37) | -0.52 (37) | 0/4 | — |
| SPY | -0.14 (39) | -0.31 (39) | -0.45 (39) | 0/4 | — |
| TSLA | +0.01 (36) | -0.04 (36) | -0.07 (36) | 1/4 | — |

### STRAT-079 Outside-bar reversal
*5m · both · stock, crypto* — a bar engulfing the prior range and closing strong reverses a down-move

Rules: entry long: `candle().outside == 1 and close > high - 0.25*(high - low) and close[1] < close[6]` · entry short: `candle().outside == 1 and close < low + 0.25*(high - low) and close[1] > close[6]` · stop: level long `low`, short `high` · target: 1.5R · time stop: 12 bars · max 2 trades/day

| Crypto | gross | low | retail | folds | test |
|---|---|---|---|---|---|
| BTC-USD | -0.07 (240) | -1.81 (240) | -9.00 (240) | 0/4 | — |
| ETH-USD | -0.02 (240) | -1.34 (240) | -9.00 (240) | 0/4 | — |
| SOL-USD | -0.08 (234) | -1.34 (234) | -5.78 (234) | 0/4 | — |

| Stock | gross | net | 2x slip | folds | test |
|---|---|---|---|---|---|
| AAPL | -0.07 (90) | -0.14 (90) | -0.20 (89) | 0/4 | — |
| NVDA | -0.14 (101) | -0.22 (101) | -0.27 (101) | 1/4 | — |
| QQQ | -0.12 (105) | -0.30 (104) | -0.48 (104) | 0/4 | — |
| SPY | -0.21 (100) | -0.47 (100) | -0.63 (98) | 0/4 | — |
| TSLA | +0.03 (92) | -0.01 (92) | -0.05 (92) | 2/4 | — |

## cross asset

### STRAT-106 Intraday relative strength vs the index
*5m · both · stock* — stocks leading the market on the day attract flows

Rules: entry long: `close / session().open - sym($bench, close / session().open) > 0.01 and close > vwap() and minutes_since_open() >= 60` · entry short: `close / session().open - sym($bench, close / session().open) < -0.01 and close < vwap() and minutes_since_open() >= 60` · stop: level long `vwap()`, short `vwap()` + 0.3 ATR buffer · max 1 trades/day

| Stock | gross | net | 2x slip | folds | test |
|---|---|---|---|---|---|
| AAPL | -0.27 (34) | -0.31 (34) | -0.34 (34) | 0/4 | — |
| NVDA | -0.12 (45) | -0.16 (45) | -0.19 (45) | 1/4 | — |
| QQQ | -0.32 (4) | -0.35 (4) | -0.37 (4) | 1/4 | — |
| SPY | — | — | — | 0/4 | — |
| TSLA | -0.14 (49) | -0.18 (49) | -0.21 (49) | 2/4 | — |

### STRAT-107 Beta-adjusted residual reversion
*5m · both · stock* — idiosyncratic deviations from the market revert

Rules: entry long: `spread_z(close, sym($bench, close), 60) < -2` · entry short: `spread_z(close, sym($bench, close), 60) > 2` · stop: 2.0x ATR(14) · exit long: `spread_z(close, sym($bench, close), 60) > 0` · exit short: `spread_z(close, sym($bench, close), 60) < 0` · time stop: 24 bars · max 2 trades/day

| Stock | gross | net | 2x slip | folds | test |
|---|---|---|---|---|---|
| AAPL | +0.23 (84) | +0.14 (85) | +0.09 (85) | 2/4 | — |
| NVDA | +0.26 (79) | +0.20 (79) | +0.15 (79) | 3/4 | +0.29 (18) |
| QQQ | +0.16 (85) | +0.05 (85) | -0.09 (87) | 2/4 | — |
| SPY | +0.25 (1) | +0.16 (1) | +0.07 (1) | 1/4 | — |
| TSLA | +0.04 (80) | +0.01 (81) | -0.01 (81) | 3/4 | — |

### STRAT-108 ETH/BTC ratio reversion
*15m · both · crypto* — relative mispricing between close substitutes reverts

Rules: entry long: `zscore(log(close), 200) < -2` · entry short: `zscore(log(close), 200) > 2` · stop: 2.5x ATR(14) · exit long: `zscore(log(close), 200) > 0` · exit short: `zscore(log(close), 200) < 0` · max 2 trades/day

| Crypto | gross | low | retail | folds | test |
|---|---|---|---|---|---|
| ETH-BTC | +0.39 (45) | -0.78 (46) | -4.70 (46) | 0/4 | — |

### STRAT-109 Leader-to-laggard catch-up
*5m · both · crypto* — information reaches the leading asset first and diffuses slowly

Rules: entry long: `sym($lead, pct(close,3)) > 0.01 and pct(close,3) < 0.5*sym($lead, pct(close,3))` · entry short: `sym($lead, pct(close,3)) < -0.01 and pct(close,3) > 0.5*sym($lead, pct(close,3))` · stop: 1.5x ATR(14) · time stop: 6 bars · max 2 trades/day

| Crypto | gross | low | retail | folds | test |
|---|---|---|---|---|---|
| ETH-USD | -0.32 (3) | -0.64 (3) | -2.65 (3) | 0/4 | — |
| SOL-USD | +0.66 (4) | +0.09 (4) | -2.13 (4) | 0/4 | — |

### STRAT-110 VIX-spike capitulation buy
*5m · long · stock* — fear spikes overshoot

Rules: entry long: `sym("^VIX", close) / sym("^VIX", session().prev_close) - 1 > 0.10 and cross_above(close, vwap().lower2)` · stop: level long `session().low` + 0.2 ATR buffer · target: level long `vwap()` · max 1 trades/day

| Stock | gross | net | 2x slip | folds | test |
|---|---|---|---|---|---|
| QQQ | -0.27 (5) | -0.35 (5) | -0.43 (5) | 1/4 | — |
| SPY | +0.29 (5) | +0.14 (5) | -0.00 (5) | 1/4 | — |

## crypto structure

### STRAT-111 Perpetual-spot basis reversion
*5m · both · crypto* — perpetual prices are tied to spot by funding; extreme basis mean-reverts

Rules: entry long: `zscore(close / sym("okx:BTC-USDT", close) - 1, 288) < -2.5` · entry short: `zscore(close / sym("okx:BTC-USDT", close) - 1, 288) > 2.5` · stop: 2.0x ATR(14) · exit long: `zscore(close / sym("okx:BTC-USDT", close) - 1, 288) > 0` · exit short: `zscore(close / sym("okx:BTC-USDT", close) - 1, 288) < 0` · max 2 trades/day

| Crypto | gross | low | retail | folds | test |
|---|---|---|---|---|---|
| BTC-USDT-SWAP | -0.24 (52) | -1.46 (52) | -8.81 (52) | 0/4 | — |

### STRAT-112 US-venue premium momentum
*5m · long · crypto* — US demand shows up first as a Coinbase premium

Rules: entry long: `zscore(close / sym("okx:BTC-USDT", close) - 1, 288) > 2` · stop: 2.0x ATR(14) · time stop: 24 bars · max 2 trades/day

| Crypto | gross | low | retail | folds | test |
|---|---|---|---|---|---|
| BTC-USD | +0.37 (40) | -0.53 (40) | -6.08 (40) | 0/4 | — |

### STRAT-113 Weekend (CME-hours) gap fill
*15m · both · crypto* — price tends to revisit the level where the regulated futures market closed on Friday

Rules: entry long: `dow() == 0 and weekend(21,23).gap < -0.01 and close < weekend(21,23).fri_close and close > open` · entry short: `dow() == 0 and weekend(21,23).gap > 0.01 and close > weekend(21,23).fri_close and close < open` · stop: 2.0x ATR(14) · target: level long `weekend(21,23).fri_close`, short `weekend(21,23).fri_close` · max 1 trades/day

| Crypto | gross | low | retail | folds | test |
|---|---|---|---|---|---|
| BTC-USD | -1.00 (1) | -1.25 (1) | -2.86 (1) | 0/4 | — |

### STRAT-114 Monday breakout of the weekend range
*15m · both · crypto* — thin weekend ranges are broken when institutional flow returns

Rules: entry long: `dow() == 0 and cross_above(close, weekend(21,23).high)` · entry short: `dow() == 0 and cross_below(close, weekend(21,23).low)` · stop: level long `(weekend(21,23).high + weekend(21,23).low)/2`, short `(weekend(21,23).high + weekend(21,23).low)/2` · target: 2.0R · max 1 trades/day

| Crypto | gross | low | retail | folds | test |
|---|---|---|---|---|---|
| BTC-USD | +0.26 (10) | +0.08 (10) | -0.99 (10) | 1/4 | — |
| ETH-USD | -0.08 (11) | -0.21 (11) | -1.00 (11) | 0/4 | — |
| SOL-USD | -0.17 (9) | -0.42 (9) | -0.98 (9) | 0/4 | — |

### STRAT-115 Stablecoin peg reversion
*5m · long · crypto* — redemption arbitrage pulls fully-backed stablecoins back to $1

Rules: entry long: `close < 0.998` · stop: 1.0% · target: level long `0.9995` · max 2 trades/day

| Crypto | gross | low | retail | folds | test |
|---|---|---|---|---|---|
| USDT-USD | — | — | — | 0/4 | — |

### STRAT-116 Derivatives-led volume spike fade
*5m · both · crypto* — moves driven by leveraged perp volume without spot volume are fragile

Rules: entry long: `zscore(sym("okx:BTC-USDT-SWAP", volume) / max(volume, 1e-9), 288) > 3 and pct(close,3) < -0.005` · entry short: `zscore(sym("okx:BTC-USDT-SWAP", volume) / max(volume, 1e-9), 288) > 3 and pct(close,3) > 0.005` · stop: 1.5x ATR(14) · time stop: 6 bars · max 2 trades/day

| Crypto | gross | low | retail | folds | test |
|---|---|---|---|---|---|
| BTC-USDT | — | — | — | 0/4 | — |

## gaps

### STRAT-029 Gap-and-go continuation
*5m · both · stock* — news-driven gaps with volume continue

Rules: entry long: `bar_in_session() == 0 and session().gap > 0.01 and close > open and rvol_tod(14) > 1.5` · entry short: `bar_in_session() == 0 and session().gap < -0.01 and close < open and rvol_tod(14) > 1.5` · order: stop long `opening_range(5).high` short `opening_range(5).low`, expires after 12 bars · stop: level long `opening_range(5).low`, short `opening_range(5).high` · target: 2.0R · max 1 trades/day

| Stock | gross | net | 2x slip | folds | test |
|---|---|---|---|---|---|
| AAPL | -1.00 (1) | -1.01 (1) | -1.02 (1) | 0/4 | — |
| NVDA | -0.40 (2) | -0.42 (2) | -0.44 (2) | 1/4 | — |
| QQQ | — | — | — | 0/4 | — |
| SPY | — | — | — | 0/4 | — |
| TSLA | +0.76 (4) | +0.74 (4) | +0.73 (4) | 2/4 | — |

### STRAT-030 Moderate-gap fade to the prior close
*5m · both · stock* — partial reversal of overnight moves during the session

Rules: entry long: `bar_in_session() == 0 and session().gap < -0.003 and session().gap > -0.015 and close > open` · entry short: `bar_in_session() == 0 and session().gap > 0.003 and session().gap < 0.015 and close < open` · stop: level long `session().low`, short `session().high` + 0.2 ATR buffer · target: level long `session().prev_close`, short `session().prev_close` · max 1 trades/day

| Stock | gross | net | 2x slip | folds | test |
|---|---|---|---|---|---|
| AAPL | -0.18 (15) | -0.21 (15) | -0.31 (15) | 2/4 | — |
| NVDA | +0.56 (16) | +0.53 (16) | +0.50 (16) | 3/4 | — |
| QQQ | +1.15 (16) | +1.04 (16) | +0.93 (16) | 3/4 | — |
| SPY | -0.89 (13) | -1.00 (13) | -1.09 (13) | 0/4 | — |
| TSLA | +0.05 (18) | +0.02 (18) | -0.01 (18) | 2/4 | — |

### STRAT-031 Buy-on-gap (Chan)
*5m · long · stock* — liquidity-driven gap-downs below the prior low in uptrending stocks mean-revert intraday

Rules: entry long: `bar_in_session() == 0 and session().open < session().prev_low * (1 - tf("1d", std(pct(close,1), 90))) and session().open > tf("1d", sma(close,20))` · stop: 4.0% · max 1 trades/day

| Stock | gross | net | 2x slip | folds | test |
|---|---|---|---|---|---|
| AAPL | — | — | — | 0/4 | — |
| NVDA | — | — | — | 0/4 | — |
| QQQ | — | — | — | 0/4 | — |
| SPY | — | — | — | 0/4 | — |
| TSLA | — | — | — | 0/4 | — |

### STRAT-032 Gap holds above prior high, then new session high
*5m · both · stock* — an unfilled gap above the prior high shows demand absorbing early selling

Rules: entry long: `session().gap > 0.005 and session().low > session().prev_high and cross_above(close, session().high[1]) and minutes_since_open() >= 30` · entry short: `session().gap < -0.005 and session().high < session().prev_low and cross_below(close, session().low[1]) and minutes_since_open() >= 30` · stop: level long `session().prev_high`, short `session().prev_low` + 0.1 ATR buffer · target: 2.0R · max 1 trades/day

| Stock | gross | net | 2x slip | folds | test |
|---|---|---|---|---|---|
| AAPL | +0.10 (3) | +0.09 (3) | +0.07 (3) | 2/4 | — |
| NVDA | -0.05 (5) | -0.06 (5) | -0.06 (5) | 2/4 | — |
| QQQ | +0.11 (10) | +0.09 (10) | +0.07 (10) | 3/4 | — |
| SPY | -0.03 (4) | -0.06 (4) | -0.10 (4) | 1/4 | — |
| TSLA | -0.07 (4) | -0.07 (4) | -0.08 (4) | 0/4 | — |

### STRAT-033 Pre-market high breakout
*5m · both · stock* — the pre-market extreme is a visible reference where stops and breakout orders cluster

Rules: entry long: `cross_above(close, premarket().high) and rvol_tod(14) > 1.2` · entry short: `cross_below(close, premarket().low) and rvol_tod(14) > 1.2` · stop: level long `vwap()`, short `vwap()` + 0.2 ATR buffer · target: 2.0R · max 1 trades/day

| Stock | gross | net | 2x slip | folds | test |
|---|---|---|---|---|---|
| AAPL | — | — | — | 0/4 | — |
| NVDA | — | — | — | 0/4 | — |
| QQQ | — | — | — | 0/4 | — |
| SPY | — | — | — | 0/4 | — |
| TSLA | — | — | — | 0/4 | — |

### STRAT-034 Short-sale-restriction day bounce
*5m · long · stock* — SEC Rule 201 restricts short selling the day after a 10% drop, reducing selling pressure

Rules: entry long: `session().prev_close / tf("1d", close[1]) - 1 <= -0.10 and cross_above(close, opening_range(30).high)` · stop: level long `opening_range(30).low` · target: 2.0R · max 1 trades/day

| Stock | gross | net | 2x slip | folds | test |
|---|---|---|---|---|---|
| AAPL | — | — | — | 0/4 | — |
| NVDA | — | — | — | 0/4 | — |
| QQQ | — | — | — | 0/4 | — |
| SPY | — | — | — | 0/4 | — |
| TSLA | — | — | — | 0/4 | — |

## market profile

### STRAT-052 Market Profile 80% rule
*5m · both · stock* — an open outside yesterday's value that is accepted back inside tends to traverse the value area

Rules: entry long: `session().open < volume_profile(40,0.7).val and persist(close > volume_profile(40,0.7).val, 6)` · entry short: `session().open > volume_profile(40,0.7).vah and persist(close < volume_profile(40,0.7).vah, 6)` · stop: level long `volume_profile(40,0.7).val`, short `volume_profile(40,0.7).vah` + 0.5 ATR buffer · target: level long `volume_profile(40,0.7).vah`, short `volume_profile(40,0.7).val` · max 1 trades/day

| Stock | gross | net | 2x slip | folds | test |
|---|---|---|---|---|---|
| AAPL | -0.47 (14) | -0.51 (14) | -0.55 (14) | 1/4 | — |
| NVDA | +0.32 (14) | +0.19 (14) | +0.09 (14) | 2/4 | — |
| QQQ | -0.17 (21) | -0.25 (21) | -0.28 (21) | 1/4 | — |
| SPY | -0.17 (15) | -0.29 (15) | -0.39 (15) | 1/4 | — |
| TSLA | -0.39 (17) | -0.42 (17) | -0.45 (17) | 0/4 | — |

### STRAT-053 Value-area breakout with acceptance
*5m · both · stock, crypto* — acceptance of prices outside prior value starts a new value area

Rules: entry long: `session().open < volume_profile(40,0.7).vah and persist(close > volume_profile(40,0.7).vah, 6) and not persist(close > volume_profile(40,0.7).vah, 7)` · entry short: `session().open > volume_profile(40,0.7).val and persist(close < volume_profile(40,0.7).val, 6) and not persist(close < volume_profile(40,0.7).val, 7)` · stop: level long `volume_profile(40,0.7).vah`, short `volume_profile(40,0.7).val` + 0.25 ATR buffer · target: level long `volume_profile(40,0.7).vah + (volume_profile(40,0.7).vah - volume_profile(40,0.7).val)`, short `volume_profile(40,0.7).val - (volume_profile(40,0.7).vah - volume_profile(40,0.7).val)` · max 1 trades/day

| Crypto | gross | low | retail | folds | test |
|---|---|---|---|---|---|
| BTC-USD | -0.06 (58) | -1.33 (58) | -9.00 (58) | 0/4 | — |
| ETH-USD | -0.34 (51) | -1.49 (51) | -8.36 (51) | 0/4 | — |
| SOL-USD | -0.10 (48) | -1.12 (48) | -4.66 (48) | 0/4 | — |

| Stock | gross | net | 2x slip | folds | test |
|---|---|---|---|---|---|
| AAPL | +0.02 (23) | -0.09 (23) | -0.17 (23) | 2/4 | — |
| NVDA | -0.18 (24) | -0.24 (24) | -0.29 (24) | 2/4 | — |
| QQQ | -0.19 (15) | -0.26 (15) | -0.33 (15) | 1/4 | — |
| SPY | -0.48 (20) | -0.65 (20) | -0.78 (20) | 0/4 | — |
| TSLA | +0.06 (27) | +0.01 (27) | +0.02 (27) | 1/4 | — |

### STRAT-054 Reversion to the prior point of control
*5m · both · stock, crypto* — the prior session's most traded price attracts price when momentum fades

Rules: entry long: `volume_profile(40,0.7).poc - close > atr(14) * 3 and cross_above(rsi(close,14), 35)` · entry short: `close - volume_profile(40,0.7).poc > atr(14) * 3 and cross_below(rsi(close,14), 65)` · stop: 1.5x ATR(14) · target: level long `volume_profile(40,0.7).poc`, short `volume_profile(40,0.7).poc` · max 1 trades/day

| Crypto | gross | low | retail | folds | test |
|---|---|---|---|---|---|
| BTC-USD | +0.10 (72) | -1.10 (72) | -7.91 (72) | 0/4 | — |
| ETH-USD | -0.00 (74) | -0.80 (74) | -5.65 (74) | 0/4 | — |
| SOL-USD | +0.42 (74) | -1.01 (74) | -5.19 (74) | 0/4 | — |

| Stock | gross | net | 2x slip | folds | test |
|---|---|---|---|---|---|
| AAPL | -0.01 (48) | -0.06 (48) | -0.13 (48) | 2/4 | — |
| NVDA | +0.06 (48) | -0.03 (48) | -0.11 (48) | 1/4 | — |
| QQQ | +0.30 (52) | +0.22 (52) | +0.14 (52) | 3/4 | -0.40 (10) |
| SPY | -0.37 (54) | -0.52 (54) | -0.74 (54) | 0/4 | — |
| TSLA | -0.09 (47) | -0.12 (47) | -0.16 (47) | 0/4 | — |

### STRAT-055 Developing POC migration (trend day)
*5m · both · stock, crypto* — value moving with price indicates a trend day

Rules: entry long: `volume_profile(40,0.7).dev_poc > volume_profile(40,0.7).dev_poc[12] and close > volume_profile(40,0.7).dev_poc and close > vwap() and minutes_since_open() >= 120` · entry short: `volume_profile(40,0.7).dev_poc < volume_profile(40,0.7).dev_poc[12] and close < volume_profile(40,0.7).dev_poc and close < vwap() and minutes_since_open() >= 120` · stop: level long `volume_profile(40,0.7).dev_poc`, short `volume_profile(40,0.7).dev_poc` + 0.3 ATR buffer · max 1 trades/day

| Crypto | gross | low | retail | folds | test |
|---|---|---|---|---|---|
| BTC-USD | +0.77 (116) | -0.90 (116) | -9.00 (116) | 0/4 | — |
| ETH-USD | +0.27 (119) | -1.11 (119) | -9.00 (119) | 0/4 | — |
| SOL-USD | +0.05 (112) | -1.29 (112) | -5.97 (112) | 0/4 | — |

| Stock | gross | net | 2x slip | folds | test |
|---|---|---|---|---|---|
| AAPL | -0.36 (59) | -0.48 (59) | -0.59 (59) | 0/4 | — |
| NVDA | -0.17 (58) | -0.26 (58) | -0.34 (58) | 2/4 | — |
| QQQ | +0.19 (60) | -0.00 (60) | -0.16 (60) | 2/4 | — |
| SPY | -0.06 (60) | -0.28 (60) | -0.45 (60) | 1/4 | — |
| TSLA | -0.03 (58) | -0.12 (58) | -0.21 (58) | 0/4 | — |

### STRAT-056 Trend-day identification and hold
*5m · both · stock* — Market Profile trend days close near their extreme

Rules: entry long: `tod() >= 660 and close > session().high - 0.1*(session().high - session().low) and count(close > vwap(), 18) >= 16 and session().high > opening_range(60).high` · entry short: `tod() >= 660 and close < session().low + 0.1*(session().high - session().low) and count(close < vwap(), 18) >= 16 and session().low < opening_range(60).low` · stop: level long `vwap()`, short `vwap()` · max 1 trades/day

| Stock | gross | net | 2x slip | folds | test |
|---|---|---|---|---|---|
| AAPL | -0.14 (44) | -0.18 (44) | -0.21 (44) | 0/4 | — |
| NVDA | -0.04 (46) | -0.07 (46) | -0.09 (46) | 1/4 | — |
| QQQ | -0.21 (45) | -0.27 (45) | -0.32 (45) | 1/4 | — |
| SPY | +0.14 (41) | +0.03 (41) | -0.06 (41) | 3/4 | — |
| TSLA | -0.15 (38) | -0.17 (38) | -0.19 (38) | 1/4 | — |

## market structure

### STRAT-080 Break of structure after a higher low
*5m · both · stock, crypto* — a close above the last swing high after a higher low confirms an up-trend

Rules: entry long: `swings(3).low > swings(3).low_prev and cross_above(close, swings(3).high)` · entry short: `swings(3).high < swings(3).high_prev and cross_below(close, swings(3).low)` · stop: level long `swings(3).low`, short `swings(3).high` + 0.1 ATR buffer · target: 2.0R · max 2 trades/day

| Crypto | gross | low | retail | folds | test |
|---|---|---|---|---|---|
| BTC-USD | -0.10 (234) | -0.88 (234) | -5.67 (234) | 0/4 | — |
| ETH-USD | +0.07 (234) | -0.49 (234) | -3.81 (234) | 0/4 | — |
| SOL-USD | -0.04 (231) | -0.68 (230) | -2.95 (230) | 0/4 | — |

| Stock | gross | net | 2x slip | folds | test |
|---|---|---|---|---|---|
| AAPL | -0.09 (76) | -0.13 (76) | -0.17 (76) | 2/4 | — |
| NVDA | -0.04 (86) | -0.10 (86) | -0.09 (86) | 2/4 | -0.64 (20) |
| QQQ | -0.23 (78) | -0.28 (78) | -0.33 (78) | 0/4 | — |
| SPY | -0.09 (75) | -0.15 (75) | -0.21 (75) | 0/4 | — |
| TSLA | -0.01 (79) | -0.04 (79) | -0.09 (79) | 1/4 | — |

### STRAT-081 Double bottom / double top
*5m · both · stock, crypto* — two failed tests of the same level followed by a neckline break

Rules: entry long: `abs(swings(3).low - swings(3).low_prev) < 0.3*atr(14) and cross_above(close, swings(3).high)` · entry short: `abs(swings(3).high - swings(3).high_prev) < 0.3*atr(14) and cross_below(close, swings(3).low)` · stop: level long `min(swings(3).low, swings(3).low_prev)`, short `max(swings(3).high, swings(3).high_prev)` · target: 2.0R · max 2 trades/day

| Crypto | gross | low | retail | folds | test |
|---|---|---|---|---|---|
| BTC-USD | +0.06 (163) | -0.65 (163) | -4.95 (163) | 0/4 | — |
| ETH-USD | -0.10 (164) | -0.59 (164) | -3.62 (164) | 0/4 | — |
| SOL-USD | +0.01 (142) | -0.67 (140) | -3.06 (140) | 0/4 | — |

| Stock | gross | net | 2x slip | folds | test |
|---|---|---|---|---|---|
| AAPL | +0.02 (36) | -0.01 (36) | -0.05 (36) | 2/4 | — |
| NVDA | -0.04 (40) | -0.07 (40) | -0.10 (40) | 2/4 | -0.49 (8) |
| QQQ | -0.12 (37) | -0.17 (37) | -0.22 (37) | 1/4 | — |
| SPY | +0.02 (44) | -0.07 (44) | -0.14 (44) | 2/4 | — |
| TSLA | -0.08 (45) | -0.10 (45) | -0.12 (45) | 2/4 | — |

### STRAT-082 Head-and-shoulders breakdown
*5m · both · stock, crypto* — a failed higher high between two lower peaks, then neckline break

Rules: entry long: `swings(3).low_prev < swings(3).low - 0.5*atr(14) and swings(3).low_prev < swings(3).low_prev2 - 0.5*atr(14) and abs(swings(3).low - swings(3).low_prev2) < atr(14) and cross_above(close, swings(3).high)` · entry short: `swings(3).high_prev > swings(3).high + 0.5*atr(14) and swings(3).high_prev > swings(3).high_prev2 + 0.5*atr(14) and abs(swings(3).high - swings(3).high_prev2) < atr(14) and cross_below(close, swings(3).low)` · stop: level long `swings(3).low`, short `swings(3).high` + 0.2 ATR buffer · target: 2.0R · max 2 trades/day

| Crypto | gross | low | retail | folds | test |
|---|---|---|---|---|---|
| BTC-USD | +0.23 (73) | -0.51 (73) | -5.04 (73) | 0/4 | — |
| ETH-USD | -0.03 (89) | -0.58 (89) | -4.00 (89) | 0/4 | — |
| SOL-USD | -0.01 (72) | -0.69 (69) | -2.87 (69) | 0/4 | — |

| Stock | gross | net | 2x slip | folds | test |
|---|---|---|---|---|---|
| AAPL | +0.07 (18) | +0.03 (18) | -0.01 (18) | 1/4 | — |
| NVDA | +0.30 (19) | +0.28 (19) | +0.25 (19) | 1/4 | — |
| QQQ | -0.20 (16) | -0.26 (16) | -0.32 (16) | 2/4 | — |
| SPY | -0.25 (14) | -0.32 (14) | -0.38 (14) | 0/4 | — |
| TSLA | -0.15 (14) | -0.18 (14) | -0.21 (14) | 1/4 | — |

### STRAT-083 Flag after an impulse
*5m · both · stock, crypto* — shallow, low-volume consolidation after an impulse is a pause, not a reversal

Rules: entry long: `change(close,11)[6] > 3*atr(14) and highest(high,6) - lowest(low,6) < 0.5*change(close,5)[6] and mean(volume,6) < mean(volume,5)[6] and close > highest(high,6)[1]` · entry short: `change(close,11)[6] < -3*atr(14) and highest(high,6) - lowest(low,6) < -0.5*change(close,5)[6] and mean(volume,6) < mean(volume,5)[6] and close < lowest(low,6)[1]` · stop: level long `lowest(low,6)`, short `highest(high,6)` · target: 2.0R · max 2 trades/day

| Crypto | gross | low | retail | folds | test |
|---|---|---|---|---|---|
| BTC-USD | +0.00 (3) | -1.02 (3) | -7.31 (3) | 0/4 | — |
| ETH-USD | +0.20 (5) | -0.35 (5) | -3.61 (5) | 0/4 | — |
| SOL-USD | -1.00 (2) | -2.77 (2) | -9.00 (2) | 0/4 | — |

| Stock | gross | net | 2x slip | folds | test |
|---|---|---|---|---|---|
| AAPL | -0.01 (3) | -0.05 (3) | -0.09 (3) | 0/4 | — |
| NVDA | -0.88 (6) | -0.91 (6) | -0.94 (6) | 0/4 | — |
| QQQ | +0.11 (8) | +0.07 (8) | +0.03 (8) | 3/4 | — |
| SPY | +0.57 (7) | +0.41 (7) | +0.32 (7) | 3/4 | — |
| TSLA | +0.13 (5) | +0.10 (5) | +0.08 (5) | 1/4 | — |

### STRAT-084 Converging-range (triangle) breakout
*5m · both · stock, crypto* — converging highs and lows compress then resolve

Rules: entry long: `linreg(high,20).slope < 0 and linreg(low,20).slope > 0 and close > highest(high,20)[1]` · entry short: `linreg(high,20).slope < 0 and linreg(low,20).slope > 0 and close < lowest(low,20)[1]` · stop: level long `lowest(low,5)`, short `highest(high,5)` · target: 2.0R · max 2 trades/day

| Crypto | gross | low | retail | folds | test |
|---|---|---|---|---|---|
| BTC-USD | -0.15 (12) | -0.79 (12) | -4.74 (12) | 0/4 | — |
| ETH-USD | -0.83 (10) | -1.32 (10) | -4.46 (10) | 0/4 | — |
| SOL-USD | +0.23 (6) | -0.31 (6) | -2.42 (6) | 0/4 | — |

| Stock | gross | net | 2x slip | folds | test |
|---|---|---|---|---|---|
| AAPL | +0.75 (3) | +0.71 (3) | +0.68 (3) | 2/4 | — |
| NVDA | -0.91 (2) | -0.94 (2) | -0.97 (2) | 0/4 | — |
| QQQ | -0.45 (2) | -0.51 (2) | -0.56 (2) | 0/4 | — |
| SPY | -0.07 (2) | -0.16 (2) | -0.25 (2) | 1/4 | — |
| TSLA | -0.26 (8) | -0.28 (8) | -0.31 (8) | 1/4 | — |

### STRAT-085 Fair-value-gap fill continuation
*5m · both · stock, crypto* — price returns to an inefficient three-bar gap, then resumes

Rules: entry long: `close > ema(close,50) and low <= fvg().bull_top and close > fvg().bull_bottom and close > open` · entry short: `close < ema(close,50) and high >= fvg().bear_bottom and close < fvg().bear_top and close < open` · stop: level long `fvg().bull_bottom`, short `fvg().bear_top` + 0.2 ATR buffer · target: 2.0R · max 2 trades/day

| Crypto | gross | low | retail | folds | test |
|---|---|---|---|---|---|
| BTC-USD | -0.18 (244) | -1.49 (244) | -9.00 (244) | 0/4 | — |
| ETH-USD | -0.13 (243) | -1.18 (242) | -7.39 (242) | 0/4 | — |
| SOL-USD | -0.12 (241) | -1.27 (241) | -4.90 (241) | 0/4 | — |

| Stock | gross | net | 2x slip | folds | test |
|---|---|---|---|---|---|
| AAPL | -0.02 (100) | -0.06 (100) | -0.18 (100) | 0/4 | — |
| NVDA | +0.06 (98) | +0.08 (97) | +0.06 (97) | 2/4 | -0.35 (19) |
| QQQ | -0.11 (93) | -0.18 (93) | -0.25 (92) | 1/4 | — |
| SPY | +0.10 (93) | -0.01 (92) | -0.18 (90) | 3/4 | -0.25 (17) |
| TSLA | -0.12 (100) | -0.17 (100) | -0.20 (100) | 2/4 | — |

### STRAT-086 Fibonacci 50-61.8% retracement entry
*5m · both · stock, crypto* — traders watch fixed retracement ratios of the last swing

Rules: entry long: `swings(3).high > swings(3).low and close < swings(3).high - 0.5*(swings(3).high - swings(3).low) and low > swings(3).high - 0.618*(swings(3).high - swings(3).low) - 0.1*atr(14) and close > open` · entry short: `swings(3).high > swings(3).low and close > swings(3).low + 0.5*(swings(3).high - swings(3).low) and high < swings(3).low + 0.618*(swings(3).high - swings(3).low) + 0.1*atr(14) and close < open` · stop: level long `swings(3).low`, short `swings(3).high` · target: 2.0R · max 2 trades/day

| Crypto | gross | low | retail | folds | test |
|---|---|---|---|---|---|
| BTC-USD | +0.13 (181) | -1.04 (181) | -7.89 (181) | 0/4 | — |
| ETH-USD | -0.02 (188) | -0.82 (188) | -5.77 (188) | 0/4 | — |
| SOL-USD | +0.10 (153) | -0.72 (152) | -3.27 (152) | 0/4 | — |

| Stock | gross | net | 2x slip | folds | test |
|---|---|---|---|---|---|
| AAPL | +0.04 (39) | -0.06 (39) | -0.12 (38) | 2/4 | — |
| NVDA | -0.04 (44) | -0.15 (44) | -0.26 (44) | 1/4 | — |
| QQQ | +0.08 (42) | +0.00 (42) | -0.07 (42) | 2/4 | — |
| SPY | -0.07 (37) | -0.28 (37) | -0.48 (37) | 1/4 | — |
| TSLA | -0.25 (43) | -0.29 (43) | -0.32 (43) | 1/4 | — |

### STRAT-087 Choppy-regime range trading
*5m · both · stock, crypto* — in choppy regimes, range extremes hold

Rules: entry long: `chop(14) > 61.8 and low <= lowest(low,20)[1] + 0.1*atr(14) and close > open` · entry short: `chop(14) > 61.8 and high >= highest(high,20)[1] - 0.1*atr(14) and close < open` · stop: 1.0x ATR(14) · target: level long `(highest(high,20) + lowest(low,20))/2`, short `(highest(high,20) + lowest(low,20))/2` · max 2 trades/day

| Crypto | gross | low | retail | folds | test |
|---|---|---|---|---|---|
| BTC-USD | -0.21 (70) | -2.11 (71) | -9.00 (71) | 0/4 | — |
| ETH-USD | +0.07 (70) | -1.22 (70) | -8.62 (70) | 0/4 | — |
| SOL-USD | +0.14 (71) | -2.00 (72) | -8.98 (72) | 0/4 | — |

| Stock | gross | net | 2x slip | folds | test |
|---|---|---|---|---|---|
| AAPL | -0.18 (14) | -0.37 (14) | -0.47 (14) | 1/4 | — |
| NVDA | -0.07 (16) | -0.22 (16) | -0.36 (16) | 0/4 | — |
| QQQ | +0.01 (22) | -0.16 (22) | -0.22 (21) | 0/4 | — |
| SPY | +0.00 (27) | -0.33 (28) | -0.69 (28) | 1/4 | — |
| TSLA | -0.31 (21) | -0.46 (20) | -0.58 (20) | 1/4 | — |

### STRAT-088 Swing trendline break
*5m · both · stock, crypto* — a line through the last two lower swing highs is a visible resistance

Rules: entry long: `swings(3).high < swings(3).high_prev and swings(3).low < swings(3).low_prev and cross_above(close, swings(3).high)` · entry short: `swings(3).low > swings(3).low_prev and swings(3).high > swings(3).high_prev and cross_below(close, swings(3).low)` · stop: 1.5x ATR(14) · target: 2.0R · max 2 trades/day

| Crypto | gross | low | retail | folds | test |
|---|---|---|---|---|---|
| BTC-USD | +0.15 (219) | -1.18 (219) | -8.96 (219) | 0/4 | — |
| ETH-USD | +0.06 (220) | -0.90 (220) | -6.67 (220) | 0/4 | — |
| SOL-USD | -0.08 (224) | -1.44 (225) | -6.09 (225) | 0/4 | — |

| Stock | gross | net | 2x slip | folds | test |
|---|---|---|---|---|---|
| AAPL | +0.07 (52) | -0.04 (52) | -0.09 (52) | 2/4 | — |
| NVDA | +0.09 (50) | +0.05 (50) | -0.01 (50) | 4/4 | — |
| QQQ | -0.10 (67) | -0.23 (68) | -0.33 (68) | 1/4 | — |
| SPY | +0.13 (55) | -0.06 (55) | -0.22 (56) | 1/4 | — |
| TSLA | -0.03 (59) | -0.06 (59) | -0.11 (60) | 3/4 | — |

### STRAT-162 Liquidity sweep then structure shift
*5m · both · stock, crypto* — stops below a swing low are taken, then buyers regain control by breaking the last swing high

Rules: entry long: `cross_above(close, swings(3).high) and within(low < swings(3).low and close > swings(3).low, 12)` · entry short: `cross_below(close, swings(3).low) and within(high > swings(3).high and close < swings(3).high, 12)` · stop: level long `lowest(low,12) - 0.2*atr(14)`, short `highest(high,12) + 0.2*atr(14)` · target: 2.0R · max 2 trades/day

| Crypto | gross | low | retail | folds | test |
|---|---|---|---|---|---|
| BTC-USD | +0.03 (223) | -0.61 (223) | -4.33 (223) | 0/4 | — |
| ETH-USD | +0.11 (219) | -0.34 (218) | -2.89 (218) | 0/4 | — |
| SOL-USD | +0.06 (221) | -0.47 (220) | -2.31 (220) | 0/4 | — |

| Stock | gross | net | 2x slip | folds | test |
|---|---|---|---|---|---|
| AAPL | +0.13 (55) | +0.05 (55) | +0.02 (55) | 2/4 | — |
| NVDA | +0.20 (62) | +0.18 (62) | +0.17 (61) | 3/4 | -0.22 (11) |
| QQQ | -0.03 (54) | -0.07 (54) | -0.10 (54) | 2/4 | — |
| SPY | +0.12 (54) | +0.04 (53) | -0.05 (53) | 4/4 | -0.01 (11) |
| TSLA | -0.11 (53) | -0.13 (53) | -0.15 (53) | 1/4 | — |

### STRAT-163 Order-block retest
*5m · both · stock, crypto* — the last opposite candle before a displacement marks where large orders entered; price revisits it

Rules: entry long: `since(close - open > 1.5*atr(14) and close > highest(high,10)[1] and close[1] < open[1]) >= 3 and since(close - open > 1.5*atr(14) and close > highest(high,10)[1] and close[1] < open[1]) <= 30 and low <= valuewhen(close - open > 1.5*atr(14) and close > highest(high,10)[1] and close[1] < open[1], high[1]) and close > valuewhen(close - open > 1.5*atr(14) and close > highest(high,10)[1] and close[1] < open[1], high[1]) and close > open` · entry short: `since(open - close > 1.5*atr(14) and close < lowest(low,10)[1] and close[1] > open[1]) >= 3 and since(open - close > 1.5*atr(14) and close < lowest(low,10)[1] and close[1] > open[1]) <= 30 and high >= valuewhen(open - close > 1.5*atr(14) and close < lowest(low,10)[1] and close[1] > open[1], low[1]) and close < valuewhen(open - close > 1.5*atr(14) and close < lowest(low,10)[1] and close[1] > open[1], low[1]) and close < open` · stop: level long `valuewhen(close - open > 1.5*atr(14) and close > highest(high,10)[1] and close[1] < open[1], low[1]) - 0.1*atr(14)`, short `valuewhen(open - close > 1.5*atr(14) and close < lowest(low,10)[1] and close[1] > open[1], high[1]) + 0.1*atr(14)` · target: 2.0R · max 2 trades/day

| Crypto | gross | low | retail | folds | test |
|---|---|---|---|---|---|
| BTC-USD | +0.02 (82) | -1.46 (81) | -9.00 (81) | 0/4 | — |
| ETH-USD | -0.10 (77) | -1.20 (77) | -7.95 (77) | 0/4 | — |
| SOL-USD | -0.09 (66) | -1.47 (66) | -5.29 (66) | 0/4 | — |

| Stock | gross | net | 2x slip | folds | test |
|---|---|---|---|---|---|
| AAPL | +0.02 (18) | -0.05 (18) | -0.11 (18) | 0/4 | — |
| NVDA | +0.42 (12) | +0.39 (12) | +0.37 (12) | 3/4 | — |
| QQQ | +0.03 (16) | -0.07 (16) | -0.14 (16) | 2/4 | — |
| SPY | -0.05 (18) | -0.16 (18) | -0.25 (18) | 1/4 | — |
| TSLA | -0.19 (17) | -0.23 (17) | -0.27 (17) | 1/4 | — |

## mean reversion

### STRAT-062 RSI(2) pullback in an uptrend (Connors)
*5m · both · stock, crypto* — short pullbacks inside a longer uptrend revert

Rules: entry long: `rsi(close,2) < 5 and close > sma(close,200)` · entry short: `rsi(close,2) > 95 and close < sma(close,200)` · stop: 3.0x ATR(14) · exit long: `close > sma(close,5)` · exit short: `close < sma(close,5)` · time stop: 20 bars · max 3 trades/day

| Crypto | gross | low | retail | folds | test |
|---|---|---|---|---|---|
| BTC-USD | +0.03 (275) | -0.69 (275) | -5.30 (275) | 0/4 | — |
| ETH-USD | +0.04 (267) | -0.50 (267) | -3.84 (267) | 0/4 | — |
| SOL-USD | +0.03 (255) | -0.64 (255) | -3.12 (255) | 0/4 | — |

| Stock | gross | net | 2x slip | folds | test |
|---|---|---|---|---|---|
| AAPL | -0.04 (109) | -0.07 (109) | -0.11 (109) | 1/4 | — |
| NVDA | +0.05 (93) | +0.03 (93) | -0.00 (93) | 2/4 | — |
| QQQ | -0.00 (83) | -0.07 (83) | -0.12 (84) | 2/4 | — |
| SPY | -0.09 (94) | -0.18 (94) | -0.28 (94) | 0/4 | — |
| TSLA | -0.03 (95) | -0.06 (95) | -0.08 (95) | 0/4 | — |

### STRAT-063 Bollinger Band re-entry fade
*5m · both · stock, crypto* — closes back inside the band after a 2-sd excursion revert to the mean

Rules: entry long: `close[1] < bb(close,20,2).lower[1] and close > bb(close,20,2).lower` · entry short: `close[1] > bb(close,20,2).upper[1] and close < bb(close,20,2).upper` · stop: 1.5x ATR(14) · target: level long `bb(close,20,2).mid`, short `bb(close,20,2).mid` · max 2 trades/day

| Crypto | gross | low | retail | folds | test |
|---|---|---|---|---|---|
| BTC-USD | -0.05 (243) | -1.37 (243) | -9.00 (243) | 0/4 | — |
| ETH-USD | -0.07 (243) | -1.01 (243) | -6.44 (243) | 0/4 | — |
| SOL-USD | +0.11 (242) | -1.24 (242) | -5.61 (242) | 0/4 | — |

| Stock | gross | net | 2x slip | folds | test |
|---|---|---|---|---|---|
| AAPL | +0.02 (116) | +0.01 (115) | -0.07 (115) | 2/4 | — |
| NVDA | -0.00 (111) | -0.03 (112) | -0.09 (112) | 2/4 | — |
| QQQ | +0.07 (110) | -0.05 (110) | -0.22 (112) | 2/4 | — |
| SPY | -0.14 (114) | -0.29 (114) | -0.46 (116) | 1/4 | — |
| TSLA | -0.06 (112) | -0.12 (112) | -0.19 (112) | 0/4 | — |

### STRAT-064 Internal bar strength reversal
*5m · both · stock, crypto* — closes at the very bottom of a bar's range tend to be followed by bounces

Rules: entry long: `candle().ibs < 0.15 and close > sma(close,200)` · entry short: `candle().ibs > 0.85 and close < sma(close,200)` · stop: 2.0x ATR(14) · exit long: `candle().ibs > 0.7` · exit short: `candle().ibs < 0.3` · time stop: 5 bars · max 2 trades/day

| Crypto | gross | low | retail | folds | test |
|---|---|---|---|---|---|
| BTC-USD | +0.02 (233) | -1.03 (233) | -7.60 (233) | 0/4 | — |
| ETH-USD | +0.00 (239) | -0.72 (239) | -5.29 (239) | 0/4 | — |
| SOL-USD | -0.01 (226) | -0.99 (226) | -4.66 (226) | 0/4 | — |

| Stock | gross | net | 2x slip | folds | test |
|---|---|---|---|---|---|
| AAPL | -0.03 (116) | -0.07 (116) | -0.11 (116) | 0/4 | — |
| NVDA | -0.01 (116) | -0.04 (116) | -0.07 (116) | 1/4 | — |
| QQQ | -0.05 (115) | -0.12 (115) | -0.20 (115) | 0/4 | — |
| SPY | -0.07 (116) | -0.18 (116) | -0.30 (116) | 0/4 | — |
| TSLA | -0.04 (116) | -0.07 (116) | -0.10 (116) | 1/4 | — |

### STRAT-065 Consecutive down closes reversion
*5m · both · stock, crypto* — runs of same-direction closes exhaust short-term order flow

Rules: entry long: `streak() <= -4 and close > ema(close,200)` · entry short: `streak() >= 4 and close < ema(close,200)` · stop: 2.0x ATR(14) · exit long: `streak() > 0` · exit short: `streak() < 0` · time stop: 10 bars · max 2 trades/day

| Crypto | gross | low | retail | folds | test |
|---|---|---|---|---|---|
| BTC-USD | +0.03 (186) | -1.00 (186) | -7.58 (186) | 0/4 | — |
| ETH-USD | +0.01 (191) | -0.75 (191) | -5.50 (191) | 0/4 | — |
| SOL-USD | +0.02 (174) | -0.94 (174) | -4.53 (174) | 0/4 | — |

| Stock | gross | net | 2x slip | folds | test |
|---|---|---|---|---|---|
| AAPL | -0.06 (84) | -0.12 (85) | -0.19 (85) | 0/4 | — |
| NVDA | -0.05 (83) | -0.09 (83) | -0.13 (83) | 0/4 | — |
| QQQ | -0.06 (75) | -0.14 (75) | -0.22 (75) | 1/4 | — |
| SPY | -0.09 (77) | -0.23 (77) | -0.39 (78) | 0/4 | — |
| TSLA | -0.05 (80) | -0.08 (80) | -0.12 (80) | 1/4 | — |

### STRAT-066 TD Sequential setup-9 exhaustion
*5m · both · stock, crypto* — nine closes against the close 4 bars earlier marks exhaustion

Rules: entry long: `td_setup(4).buy == 9` · entry short: `td_setup(4).sell == 9` · stop: level long `lowest(low,9)`, short `highest(high,9)` + 0.25 ATR buffer · target: 1.5R · time stop: 12 bars · max 2 trades/day

| Crypto | gross | low | retail | folds | test |
|---|---|---|---|---|---|
| BTC-USD | -0.20 (227) | -2.67 (227) | -9.00 (227) | 0/4 | — |
| ETH-USD | -0.08 (230) | -1.78 (230) | -9.00 (230) | 0/4 | — |
| SOL-USD | +0.00 (236) | -1.66 (236) | -7.28 (236) | 0/4 | — |

| Stock | gross | net | 2x slip | folds | test |
|---|---|---|---|---|---|
| AAPL | -0.24 (93) | -0.34 (93) | -0.46 (93) | 0/4 | — |
| NVDA | -0.13 (101) | -0.22 (101) | -0.29 (101) | 0/4 | — |
| QQQ | -0.08 (103) | -0.36 (103) | -0.56 (103) | 1/4 | — |
| SPY | -0.08 (104) | -0.50 (104) | -0.79 (104) | 1/4 | — |
| TSLA | +0.01 (91) | -0.15 (91) | -0.23 (91) | 2/4 | — |

### STRAT-067 Regression-channel reversion
*5m · both · stock, crypto* — deviations from a fitted trend line revert while the trend holds

Rules: entry long: `close < linreg(close,100).value - 2*std(close - linreg(close,100).value, 100) and linreg(close,100).slope >= 0` · entry short: `close > linreg(close,100).value + 2*std(close - linreg(close,100).value, 100) and linreg(close,100).slope <= 0` · stop: 2.0x ATR(14) · target: level long `linreg(close,100).value`, short `linreg(close,100).value` · max 2 trades/day

| Crypto | gross | low | retail | folds | test |
|---|---|---|---|---|---|
| BTC-USD | +0.10 (139) | -0.94 (141) | -6.95 (141) | 0/4 | — |
| ETH-USD | +0.01 (137) | -0.61 (137) | -4.26 (137) | 0/4 | — |
| SOL-USD | -0.08 (133) | -0.90 (139) | -3.98 (139) | 0/4 | — |

| Stock | gross | net | 2x slip | folds | test |
|---|---|---|---|---|---|
| AAPL | -0.33 (39) | -0.34 (39) | -0.38 (39) | 1/4 | — |
| NVDA | +0.10 (32) | +0.07 (32) | +0.01 (32) | 3/4 | — |
| QQQ | +0.10 (27) | +0.03 (27) | -0.20 (28) | 3/4 | — |
| SPY | +0.08 (37) | -0.10 (39) | -0.20 (39) | 1/4 | — |
| TSLA | -0.21 (43) | -0.24 (43) | -0.28 (44) | 1/4 | — |

### STRAT-068 Volatility-shock bar reversal
*5m · both · stock, crypto* — panic bars overshoot fair value and partially retrace

Rules: entry long: `high - low > 3*atr(14)[1] and close < low + 0.25*(high - low)` · entry short: `high - low > 3*atr(14)[1] and close > high - 0.25*(high - low)` · stop: 1.5x ATR(14) · target: level long `(high + low)/2`, short `(high + low)/2` · time stop: 6 bars · max 2 trades/day

| Crypto | gross | low | retail | folds | test |
|---|---|---|---|---|---|
| BTC-USD | -0.01 (122) | -1.49 (122) | -9.00 (122) | 0/4 | — |
| ETH-USD | +0.08 (120) | -0.85 (120) | -6.00 (120) | 0/4 | — |
| SOL-USD | +0.02 (90) | -0.94 (90) | -4.42 (90) | 0/4 | — |

| Stock | gross | net | 2x slip | folds | test |
|---|---|---|---|---|---|
| AAPL | -0.31 (46) | -0.36 (46) | -0.41 (46) | 0/4 | — |
| NVDA | -0.07 (47) | -0.18 (47) | -0.21 (47) | 0/4 | — |
| QQQ | -0.06 (42) | -0.14 (42) | -0.32 (42) | 0/4 | — |
| SPY | -0.18 (19) | -0.37 (19) | -0.51 (19) | 1/4 | — |
| TSLA | -0.06 (49) | -0.12 (49) | -0.15 (49) | 1/4 | — |

### STRAT-069 Mass Index reversal bulge (Dorsey)
*5m · both · stock, crypto* — range expansion then contraction marks trend exhaustion

Rules: entry long: `within(mass_index(9,25) > 27, 10) and cross_below(mass_index(9,25), 26.5) and ema(close,9) < ema(close,9)[5]` · entry short: `within(mass_index(9,25) > 27, 10) and cross_below(mass_index(9,25), 26.5) and ema(close,9) > ema(close,9)[5]` · stop: 2.0x ATR(14) · target: 1.5R · max 2 trades/day

| Crypto | gross | low | retail | folds | test |
|---|---|---|---|---|---|
| BTC-USD | -0.00 (113) | -0.75 (113) | -5.04 (113) | 0/4 | — |
| ETH-USD | +0.06 (126) | -0.47 (126) | -3.52 (126) | 0/4 | — |
| SOL-USD | +0.03 (89) | -0.68 (89) | -2.88 (89) | 0/4 | — |

| Stock | gross | net | 2x slip | folds | test |
|---|---|---|---|---|---|
| AAPL | +0.02 (57) | -0.07 (57) | -0.12 (57) | 1/4 | — |
| NVDA | -0.18 (57) | -0.23 (57) | -0.26 (57) | 1/4 | — |
| QQQ | +0.08 (57) | -0.03 (57) | -0.16 (57) | 1/4 | -0.34 (12) |
| SPY | -0.20 (49) | -0.30 (49) | -0.47 (49) | 0/4 | — |
| TSLA | +0.26 (59) | +0.24 (59) | +0.21 (59) | 4/4 | +0.47 (12) |

### STRAT-070 RSI bullish/bearish divergence
*5m · both · stock, crypto* — momentum failing to confirm a new price extreme

Rules: entry long: `low <= lowest(low,20) and rsi(close,14) > valuewhen(low <= lowest(low,20), rsi(close,14))[5] and close > open` · entry short: `high >= highest(high,20) and rsi(close,14) < valuewhen(high >= highest(high,20), rsi(close,14))[5] and close < open` · stop: 1.5x ATR(14) · target: 2.0R · max 2 trades/day

| Crypto | gross | low | retail | folds | test |
|---|---|---|---|---|---|
| BTC-USD | +0.12 (236) | -1.17 (236) | -9.00 (236) | 0/4 | — |
| ETH-USD | -0.07 (236) | -1.07 (236) | -6.81 (236) | 0/4 | — |
| SOL-USD | -0.08 (238) | -1.41 (238) | -5.92 (238) | 0/4 | — |

| Stock | gross | net | 2x slip | folds | test |
|---|---|---|---|---|---|
| AAPL | +0.15 (88) | +0.06 (88) | -0.01 (89) | 2/4 | — |
| NVDA | -0.07 (94) | -0.15 (94) | -0.20 (94) | 1/4 | — |
| QQQ | +0.11 (88) | +0.03 (87) | -0.09 (86) | 2/4 | — |
| SPY | -0.08 (91) | -0.25 (91) | -0.53 (91) | 1/4 | — |
| TSLA | -0.06 (103) | -0.10 (103) | -0.20 (105) | 2/4 | — |

### STRAT-160 RSI extreme recovery
*15m · both · stock, crypto* — an oversold/overbought reading that starts to normalize signals exhaustion of the move

Rules: entry long: `cross_above(rsi(close,14), 30)` · entry short: `cross_below(rsi(close,14), 70)` · stop: 2.5x ATR(14) · exit long: `rsi(close,14) > 50` · exit short: `rsi(close,14) < 50` · time stop: 48 bars · max 3 trades/day

| Crypto | gross | low | retail | folds | test |
|---|---|---|---|---|---|
| BTC-USD | +0.04 (108) | -0.32 (109) | -2.59 (109) | 0/4 | — |
| ETH-USD | +0.07 (93) | -0.18 (94) | -1.74 (94) | 0/4 | — |
| SOL-USD | +0.02 (96) | -0.33 (97) | -1.64 (97) | 0/4 | — |

| Stock | gross | net | 2x slip | folds | test |
|---|---|---|---|---|---|
| AAPL | +0.19 (35) | +0.17 (35) | +0.15 (35) | 3/4 | — |
| NVDA | +0.03 (39) | +0.01 (39) | -0.00 (39) | 2/4 | — |
| QQQ | +0.15 (38) | +0.12 (38) | +0.09 (38) | 3/4 | — |
| SPY | -0.04 (35) | -0.11 (35) | -0.17 (35) | 2/4 | — |
| TSLA | +0.01 (42) | -0.00 (42) | -0.01 (42) | 1/4 | — |

## memecoin

### STRAT-164 Memecoin breadth-led momentum
*15m · long · crypto* — when most memecoins trend together, attention is flowing into the whole theme

Rules: entry long: `cross_above((iff(sym("DOGE-USD", close > ema(close,20)), 1, 0) + iff(sym("SHIB-USD", close > ema(close,20)), 1, 0) + iff(sym("PEPE-USD", close > ema(close,20)), 1, 0) + iff(sym("BONK-USD", close > ema(close,20)), 1, 0) + iff(sym("WIF-USD", close > ema(close,20)), 1, 0) + iff(sym("FLOKI-USD", close > ema(close,20)), 1, 0)), 3.5) and close > ema(close,20)` · stop: 3.0x ATR(14) · target: 2.0R · max 2 trades/day

| Crypto | gross | low | retail | folds | test |
|---|---|---|---|---|---|
| BONK-USD | -0.11 (202) | -0.31 (203) | -1.07 (203) | 0/4 | — |
| DOGE-USD | -0.05 (213) | -0.42 (216) | -1.70 (216) | 0/4 | — |
| FLOKI-USD | -0.17 (164) | -0.44 (164) | -1.33 (164) | 0/4 | — |
| PEPE-USD | -0.12 (203) | -0.34 (205) | -1.16 (205) | 0/4 | — |
| SHIB-USD | -0.07 (205) | -0.43 (211) | -1.53 (211) | 0/4 | — |
| WIF-USD | -0.03 (187) | -0.25 (188) | -1.04 (188) | 0/4 | — |

### STRAT-165 Memecoin leader pullback
*15m · long · crypto* — the theme leader's orderly pullbacks get bought while the theme stays strong

Rules: entry long: `close > ema(close,50) and low <= ema(close,20) and close > ema(close,20) and close > open and (iff(sym("DOGE-USD", close > ema(close,20)), 1, 0) + iff(sym("SHIB-USD", close > ema(close,20)), 1, 0) + iff(sym("PEPE-USD", close > ema(close,20)), 1, 0) + iff(sym("BONK-USD", close > ema(close,20)), 1, 0) + iff(sym("WIF-USD", close > ema(close,20)), 1, 0) + iff(sym("FLOKI-USD", close > ema(close,20)), 1, 0)) >= 4` · stop: 3.0x ATR(14) · target: 2.0R · max 2 trades/day

| Crypto | gross | low | retail | folds | test |
|---|---|---|---|---|---|
| DOGE-USD | -0.18 (171) | -0.52 (170) | -1.81 (170) | 0/4 | — |

### STRAT-166 Memecoin laggard catch-up breakout
*15m · long · crypto* — laggards in a strong theme catch up once they break out

Rules: entry long: `roc(close,24) < sym("DOGE-USD", roc(close,24)) and cross_above(close, donchian(20).upper[1]) and (iff(sym("DOGE-USD", close > ema(close,20)), 1, 0) + iff(sym("SHIB-USD", close > ema(close,20)), 1, 0) + iff(sym("PEPE-USD", close > ema(close,20)), 1, 0) + iff(sym("BONK-USD", close > ema(close,20)), 1, 0) + iff(sym("WIF-USD", close > ema(close,20)), 1, 0) + iff(sym("FLOKI-USD", close > ema(close,20)), 1, 0)) >= 4` · stop: 3.0x ATR(14) · target: 2.0R · max 2 trades/day

| Crypto | gross | low | retail | folds | test |
|---|---|---|---|---|---|
| BONK-USD | +0.35 (32) | +0.18 (32) | -0.56 (32) | 0/4 | — |
| FLOKI-USD | -0.04 (46) | -0.25 (46) | -1.07 (46) | 0/4 | — |
| PEPE-USD | +0.26 (42) | +0.08 (42) | -0.67 (42) | 0/4 | — |
| SHIB-USD | +0.10 (72) | -0.18 (72) | -1.23 (72) | 0/4 | — |
| WIF-USD | -0.03 (45) | -0.28 (45) | -1.02 (45) | 0/4 | — |

### STRAT-167 Memecoin leader-to-follower transmission
*5m · long · crypto* — a shock in the leading memecoin reaches smaller ones with a delay

Rules: entry long: `sym("DOGE-USD", zscore(roc(close,3), 96)) > 2 and zscore(roc(close,3), 96) < 1` · stop: 2.0x ATR(14) · time stop: 8 bars · max 3 trades/day

| Crypto | gross | low | retail | folds | test |
|---|---|---|---|---|---|
| BONK-USD | +0.13 (193) | -0.47 (194) | -2.54 (194) | 0/4 | — |
| FLOKI-USD | -0.09 (138) | -0.60 (138) | -2.45 (138) | 0/4 | — |
| PEPE-USD | +0.00 (172) | -0.65 (173) | -2.88 (173) | 0/4 | — |
| SHIB-USD | +0.06 (200) | -0.76 (200) | -3.65 (200) | 0/4 | — |
| WIF-USD | -0.01 (158) | -0.55 (159) | -2.58 (159) | 0/4 | — |

### STRAT-168 Bitcoin risk-on memecoin participation
*15m · long · crypto* — when bitcoin turns up, speculative risk appetite spills into memecoins

Rules: entry long: `sym("BTC-USD", cross_above(close, ema(close,96))) and (iff(sym("DOGE-USD", close > ema(close,20)), 1, 0) + iff(sym("SHIB-USD", close > ema(close,20)), 1, 0) + iff(sym("PEPE-USD", close > ema(close,20)), 1, 0) + iff(sym("BONK-USD", close > ema(close,20)), 1, 0) + iff(sym("WIF-USD", close > ema(close,20)), 1, 0) + iff(sym("FLOKI-USD", close > ema(close,20)), 1, 0)) >= 3` · stop: 3.0x ATR(14) · target: 2.0R · max 2 trades/day

| Crypto | gross | low | retail | folds | test |
|---|---|---|---|---|---|
| BONK-USD | -0.14 (122) | -0.34 (125) | -1.10 (125) | 0/4 | — |
| DOGE-USD | -0.18 (122) | -0.51 (124) | -1.78 (124) | 0/4 | — |
| FLOKI-USD | -0.27 (96) | -0.52 (97) | -1.41 (97) | 0/4 | — |
| PEPE-USD | -0.14 (120) | -0.36 (120) | -1.18 (120) | 0/4 | — |
| SHIB-USD | -0.08 (117) | -0.40 (121) | -1.48 (121) | 0/4 | — |
| WIF-USD | -0.07 (115) | -0.32 (117) | -1.15 (117) | 0/4 | — |

### STRAT-169 Selloff-resilient memecoin rebound
*15m · long · crypto* — tokens that held up during a market selloff lead the rebound

Rules: entry long: `sym("BTC-USD", since(low <= lowest(low,96))) >= 8 and sym("BTC-USD", since(low <= lowest(low,96))) <= 24 and roc(close,48) > sym("BTC-USD", roc(close,48)) and cross_above(close, highest(high,8)[1])` · stop: 3.0x ATR(14) · target: 2.0R · max 2 trades/day

| Crypto | gross | low | retail | folds | test |
|---|---|---|---|---|---|
| BONK-USD | +0.05 (22) | -0.11 (22) | -0.76 (22) | 0/4 | — |
| DOGE-USD | -0.25 (36) | -0.54 (36) | -1.70 (36) | 0/4 | — |
| FLOKI-USD | +0.02 (22) | -0.19 (22) | -1.03 (22) | 0/4 | — |
| PEPE-USD | +0.07 (33) | -0.24 (33) | -1.07 (33) | 0/4 | — |
| SHIB-USD | -0.15 (24) | -0.49 (25) | -1.56 (25) | 0/4 | — |
| WIF-USD | -0.17 (35) | -0.39 (35) | -1.15 (35) | 0/4 | — |

### STRAT-170 Memecoin residual reversion vs bitcoin
*15m · long · crypto* — a memecoin's move unexplained by bitcoin tends to partly reverse

Rules: entry long: `cross_above(spread_z(close, sym("BTC-USD", close), 96), -2)` · stop: 2.5x ATR(14) · exit long: `spread_z(close, sym("BTC-USD", close), 96) > 0` · time stop: 96 bars · max 2 trades/day

| Crypto | gross | low | retail | folds | test |
|---|---|---|---|---|---|
| BONK-USD | +0.35 (57) | +0.10 (57) | -0.89 (57) | 0/4 | — |
| DOGE-USD | -0.04 (58) | -0.49 (58) | -2.01 (58) | 0/4 | — |
| FLOKI-USD | -0.33 (43) | -0.64 (43) | -1.80 (43) | 0/4 | — |
| PEPE-USD | +0.08 (57) | -0.18 (57) | -1.16 (57) | 0/4 | — |
| SHIB-USD | -0.32 (58) | -0.68 (60) | -1.99 (60) | 0/4 | — |
| WIF-USD | +0.39 (46) | -0.26 (46) | -1.33 (46) | 0/4 | — |

### STRAT-171 Memecoin volatility contraction release
*15m · long · crypto* — compressed memecoin ranges resolve in large moves; a calm BTC keeps the move token-driven

Rules: entry long: `squeeze(20).on[1] == 1 and squeeze(20).on == 0 and close > donchian(20).upper[1] and sym("BTC-USD", natr(14) < 1.5*sma(natr(14),96))` · stop: 3.0x ATR(14) · target: 2.0R · max 2 trades/day

| Crypto | gross | low | retail | folds | test |
|---|---|---|---|---|---|
| BONK-USD | -0.13 (39) | -0.32 (39) | -1.06 (39) | 0/4 | — |
| DOGE-USD | +0.12 (56) | -0.26 (56) | -1.46 (56) | 0/4 | — |
| FLOKI-USD | +0.58 (16) | +0.39 (16) | -0.46 (16) | 0/4 | — |
| PEPE-USD | +0.07 (39) | -0.13 (39) | -0.95 (39) | 0/4 | — |
| SHIB-USD | +0.12 (41) | -0.24 (42) | -1.33 (42) | 0/4 | — |
| WIF-USD | +0.00 (25) | -0.16 (25) | -0.82 (25) | 0/4 | — |

### STRAT-172 Memecoin session-handover continuation
*15m · long · crypto* — new regional traders arriving at the London and New York opens push existing moves

Rules: entry long: `(time_between("07:00", "07:30") or time_between("13:30", "14:00")) and rvol_tod(14) > 1.5 and cross_above(close, highest(high,8)[1])` · stop: 3.0x ATR(14) · target: 2.0R · max 2 trades/day

| Crypto | gross | low | retail | folds | test |
|---|---|---|---|---|---|
| BONK-USD | +0.20 (5) | +0.11 (5) | -0.48 (5) | 1/4 | — |
| DOGE-USD | -0.86 (6) | -1.12 (6) | -2.13 (6) | 0/4 | — |
| FLOKI-USD | +0.07 (14) | -0.11 (14) | -0.85 (14) | 1/4 | — |
| PEPE-USD | -0.12 (12) | -0.29 (12) | -0.99 (12) | 0/4 | — |
| SHIB-USD | +0.33 (10) | +0.09 (10) | -0.96 (10) | 0/4 | — |
| WIF-USD | +0.35 (13) | +0.10 (13) | -0.62 (13) | 1/4 | — |

### STRAT-173 Memecoin liquidation-aftershock reclaim
*15m · long · crypto* — forced selling during a bitcoin shock overshoots in memecoins, which recover once they reclaim the pre-shock level

Rules: entry long: `since(sym("BTC-USD", zscore(roc(close,4), 96) < -2.5)) <= 16 and cross_above(close, valuewhen(sym("BTC-USD", zscore(roc(close,4), 96) < -2.5), open))` · stop: 3.0x ATR(14) · target: 2.0R · max 1 trades/day

| Crypto | gross | low | retail | folds | test |
|---|---|---|---|---|---|
| BONK-USD | -0.03 (63) | -0.25 (63) | -0.91 (63) | 0/4 | — |
| DOGE-USD | -0.13 (63) | -0.39 (63) | -1.43 (63) | 0/4 | — |
| FLOKI-USD | -0.04 (51) | -0.29 (52) | -1.06 (52) | 0/4 | — |
| PEPE-USD | -0.14 (61) | -0.34 (61) | -1.02 (61) | 0/4 | — |
| SHIB-USD | +0.14 (62) | -0.18 (62) | -1.11 (62) | 0/4 | — |
| WIF-USD | -0.17 (55) | -0.35 (55) | -1.06 (55) | 0/4 | — |

### STRAT-174 Memecoin native-price range breakout
*15m · long · crypto* — Solana memecoins priced in SOL show whether demand is token-specific rather than a SOL move

Rules: entry long: `close / sym("SOL-USD", close) > highest(close / sym("SOL-USD", close), 48)[1] and close > ema(close,20)` · stop: 3.0x ATR(14) · target: 2.0R · max 2 trades/day

| Crypto | gross | low | retail | folds | test |
|---|---|---|---|---|---|
| BONK-USD | -0.21 (118) | -0.43 (120) | -1.14 (120) | 0/4 | — |
| WIF-USD | -0.08 (115) | -0.28 (116) | -1.03 (116) | 0/4 | — |

### STRAT-175 Two-stage compression breakout
*5m · long · crypto* — a tight range inside a tight range stores energy; the break of the inner range starts the move

Rules: entry long: `(highest(high,12)-lowest(low,12))[1] < 0.5*(highest(high,48)-lowest(low,48))[1] and (highest(high,48)-lowest(low,48))[1] < 0.7*(highest(high,192)-lowest(low,192))[1] and close > highest(high,12)[1]` · stop: 3.0x ATR(14) · target: 2.0R · max 2 trades/day

| Crypto | gross | low | retail | folds | test |
|---|---|---|---|---|---|
| BONK-USD | +0.02 (257) | -0.41 (255) | -1.83 (255) | 0/4 | — |
| DOGE-USD | -0.12 (233) | -0.95 (234) | -3.64 (234) | 0/4 | — |
| FLOKI-USD | -0.01 (377) | -0.44 (377) | -1.78 (377) | 0/4 | — |
| PEPE-USD | -0.07 (237) | -0.54 (240) | -1.99 (240) | 0/4 | — |
| SHIB-USD | -0.05 (251) | -0.67 (254) | -2.61 (254) | 0/4 | — |
| WIF-USD | -0.13 (330) | -0.55 (333) | -1.86 (333) | 0/4 | — |

### STRAT-176 Selloff-range midpoint acceptance
*15m · long · crypto* — after a selloff, holding above the range midpoint shows sellers are done

Rules: entry long: `since(low <= lowest(low,96)) <= 48 and persist(low > (highest(high,96)+lowest(low,96))/2, 4) and not persist(low > (highest(high,96)+lowest(low,96))/2, 5)` · stop: level long `(highest(high,96)+lowest(low,96))/2 - 0.5*atr(14)` · target: level long `highest(high,96)` · max 1 trades/day

| Crypto | gross | low | retail | folds | test |
|---|---|---|---|---|---|
| BONK-USD | +0.11 (47) | -0.21 (47) | -1.28 (47) | 0/4 | — |
| DOGE-USD | -0.50 (41) | -1.01 (41) | -2.94 (41) | 0/4 | — |
| FLOKI-USD | +0.50 (76) | -0.28 (77) | -1.94 (77) | 0/4 | — |
| PEPE-USD | -0.23 (58) | -0.63 (58) | -2.08 (58) | 0/4 | — |
| SHIB-USD | -0.27 (46) | -0.78 (46) | -2.59 (46) | 0/4 | — |
| WIF-USD | -0.40 (75) | -0.68 (75) | -1.69 (75) | 0/4 | — |

### STRAT-177 Memecoin relative-momentum leader
*15m · long · crypto* — the memecoin with the strongest recent return keeps attracting attention

Rules: entry long: `roc(close,24) >= max(max(max(sym("DOGE-USD", roc(close,24)), sym("SHIB-USD", roc(close,24))), max(sym("PEPE-USD", roc(close,24)), sym("BONK-USD", roc(close,24)))), max(sym("WIF-USD", roc(close,24)), sym("FLOKI-USD", roc(close,24)))) and not (roc(close,24)[1] >= max(max(max(sym("DOGE-USD", roc(close,24)), sym("SHIB-USD", roc(close,24))), max(sym("PEPE-USD", roc(close,24)), sym("BONK-USD", roc(close,24)))), max(sym("WIF-USD", roc(close,24)), sym("FLOKI-USD", roc(close,24))))[1]) and close > ema(close,20)` · stop: 3.0x ATR(14) · exit long: `roc(close,24) < max(max(max(sym("DOGE-USD", roc(close,24)), sym("SHIB-USD", roc(close,24))), max(sym("PEPE-USD", roc(close,24)), sym("BONK-USD", roc(close,24)))), max(sym("WIF-USD", roc(close,24)), sym("FLOKI-USD", roc(close,24))))` · max 2 trades/day

| Crypto | gross | low | retail | folds | test |
|---|---|---|---|---|---|
| BONK-USD | -0.04 (199) | -0.25 (199) | -1.05 (199) | 0/4 | — |
| DOGE-USD | -0.07 (134) | -0.43 (134) | -1.81 (134) | 0/4 | — |
| FLOKI-USD | -0.06 (153) | -0.32 (153) | -1.30 (153) | 0/4 | — |
| PEPE-USD | -0.03 (183) | -0.26 (183) | -1.17 (183) | 0/4 | — |
| SHIB-USD | -0.06 (159) | -0.37 (159) | -1.58 (159) | 0/4 | — |
| WIF-USD | -0.10 (192) | -0.33 (192) | -1.23 (192) | 0/4 | — |

## momentum

### STRAT-057 CCI +100 trend entry (Lambert)
*5m · both · stock, crypto* — price moving well above its statistical mean starts a cyclical up-move

Rules: entry long: `cross_above(cci(20), 100)` · entry short: `cross_below(cci(20), -100)` · stop: 2.0x ATR(14) · exit long: `cross_below(cci(20), 100)` · exit short: `cross_above(cci(20), -100)` · max 2 trades/day

| Crypto | gross | low | retail | folds | test |
|---|---|---|---|---|---|
| BTC-USD | -0.06 (244) | -1.11 (244) | -7.80 (244) | 0/4 | — |
| ETH-USD | -0.01 (244) | -0.74 (244) | -5.40 (244) | 0/4 | — |
| SOL-USD | +0.02 (244) | -0.96 (244) | -4.72 (244) | 0/4 | — |

| Stock | gross | net | 2x slip | folds | test |
|---|---|---|---|---|---|
| AAPL | +0.17 (120) | +0.13 (120) | +0.09 (120) | 2/4 | -0.05 (24) |
| NVDA | +0.06 (120) | +0.02 (120) | -0.01 (120) | 3/4 | -0.18 (25) |
| QQQ | +0.02 (120) | -0.05 (120) | -0.12 (120) | 1/4 | — |
| SPY | +0.04 (120) | -0.09 (120) | -0.21 (120) | 1/4 | — |
| TSLA | -0.03 (120) | -0.06 (120) | -0.09 (120) | 1/4 | — |

### STRAT-058 Stochastic pop (momentum thrust)
*5m · both · stock, crypto* — an overbought reading after a quiet period is strength, not weakness

Rules: entry long: `cross_above(stoch(14,3,3).k, 80) and adx(14).adx < 20` · entry short: `cross_below(stoch(14,3,3).k, 20) and adx(14).adx < 20` · stop: 1.5x ATR(14) · exit long: `stoch(14,3,3).k < 70` · exit short: `stoch(14,3,3).k > 30` · max 2 trades/day

| Crypto | gross | low | retail | folds | test |
|---|---|---|---|---|---|
| BTC-USD | -0.02 (234) | -1.51 (234) | -9.00 (234) | 0/4 | — |
| ETH-USD | +0.09 (234) | -1.01 (234) | -7.99 (234) | 0/4 | — |
| SOL-USD | -0.07 (229) | -1.55 (229) | -6.70 (229) | 0/4 | — |

| Stock | gross | net | 2x slip | folds | test |
|---|---|---|---|---|---|
| AAPL | +0.17 (76) | +0.08 (76) | -0.02 (76) | 2/4 | — |
| NVDA | +0.05 (73) | -0.02 (73) | -0.10 (73) | 2/4 | -0.27 (14) |
| QQQ | -0.12 (81) | -0.26 (81) | -0.40 (81) | 0/4 | — |
| SPY | -0.27 (68) | -0.47 (68) | -0.69 (68) | 0/4 | — |
| TSLA | -0.15 (83) | -0.20 (83) | -0.24 (83) | 1/4 | — |

### STRAT-059 Momentum ignition (ROC shock)
*5m · both · stock, crypto* — unusually large short-horizon returns attract momentum followers

Rules: entry long: `zscore(roc(close,5), 100) > 2 and close > vwap()` · entry short: `zscore(roc(close,5), 100) < -2 and close < vwap()` · stop: 1.5x ATR(14) · trail: 2.0x ATR after +0.5R · time stop: 12 bars · max 2 trades/day

| Crypto | gross | low | retail | folds | test |
|---|---|---|---|---|---|
| BTC-USD | -0.03 (208) | -1.37 (209) | -9.00 (209) | 0/4 | — |
| ETH-USD | +0.03 (209) | -0.94 (210) | -7.00 (210) | 0/4 | — |
| SOL-USD | +0.19 (202) | -1.28 (205) | -5.84 (205) | 0/4 | — |

| Stock | gross | net | 2x slip | folds | test |
|---|---|---|---|---|---|
| AAPL | +0.16 (72) | +0.09 (72) | +0.03 (72) | 1/4 | -0.44 (20) |
| NVDA | +0.19 (67) | +0.09 (67) | +0.04 (67) | 3/4 | -0.21 (12) |
| QQQ | -0.07 (64) | -0.16 (64) | -0.32 (65) | 1/4 | — |
| SPY | +0.08 (70) | -0.21 (72) | -0.37 (72) | 1/4 | — |
| TSLA | +0.21 (80) | +0.18 (80) | +0.14 (80) | 3/4 | +0.08 (19) |

### STRAT-060 Awesome Oscillator saucer
*5m · both · stock, crypto* — a brief dip in momentum above zero precedes the next thrust

Rules: entry long: `ao() > 0 and ao()[1] < ao()[2] and ao()[2] < ao()[3] and ao() > ao()[1]` · entry short: `ao() < 0 and ao()[1] > ao()[2] and ao()[2] > ao()[3] and ao() < ao()[1]` · stop: 1.5x ATR(14) · target: 1.5R · max 2 trades/day

| Crypto | gross | low | retail | folds | test |
|---|---|---|---|---|---|
| BTC-USD | -0.07 (241) | -1.47 (241) | -9.00 (241) | 0/4 | — |
| ETH-USD | +0.01 (242) | -0.98 (242) | -6.83 (242) | 0/4 | — |
| SOL-USD | -0.17 (242) | -1.58 (242) | -6.35 (242) | 0/4 | — |

| Stock | gross | net | 2x slip | folds | test |
|---|---|---|---|---|---|
| AAPL | -0.18 (101) | -0.24 (102) | -0.30 (100) | 0/4 | — |
| NVDA | +0.06 (102) | -0.08 (102) | -0.13 (101) | 2/4 | — |
| QQQ | +0.13 (96) | +0.04 (96) | -0.07 (96) | 3/4 | — |
| SPY | +0.08 (107) | -0.06 (107) | -0.24 (108) | 0/4 | — |
| TSLA | +0.01 (102) | -0.04 (103) | -0.08 (104) | 2/4 | — |

### STRAT-061 Momentum Pinball (Raschke)
*5m · both · stock* — short-term oversold daily momentum resolves by a first-hour breakout

Rules: entry long: `tf("1d", rsi(roc(close,1),3)) < 30 and cross_above(close, opening_range(60).high)` · entry short: `tf("1d", rsi(roc(close,1),3)) > 70 and cross_below(close, opening_range(60).low)` · stop: level long `opening_range(60).low`, short `opening_range(60).high` · max 1 trades/day

| Stock | gross | net | 2x slip | folds | test |
|---|---|---|---|---|---|
| AAPL | +0.22 (3) | +0.20 (3) | +0.18 (3) | 2/4 | — |
| NVDA | +0.40 (6) | +0.38 (6) | +0.37 (6) | 3/4 | — |
| QQQ | -0.15 (5) | -0.18 (5) | -0.20 (5) | 1/4 | — |
| SPY | -0.48 (9) | -0.52 (9) | -0.56 (9) | 1/4 | — |
| TSLA | +0.22 (5) | +0.21 (5) | +0.20 (5) | 2/4 | — |

## named systems

### STRAT-152 Triple Screen (Elder)
*5m · both · stock, crypto* — trade the higher-timeframe tide, enter on lower-timeframe waves

Rules: entry long: `tf("1h", macd(close,12,26,9).hist > macd(close,12,26,9).hist[1]) == 1 and force(2) < 0` · entry short: `tf("1h", macd(close,12,26,9).hist < macd(close,12,26,9).hist[1]) == 1 and force(2) > 0` · order: stop long `high` short `low`, expires after 2 bars · stop: level long `lowest(low,3)`, short `highest(high,3)` · target: 2.0R · max 2 trades/day

| Crypto | gross | low | retail | folds | test |
|---|---|---|---|---|---|
| BTC-USD | -0.09 (240) | -1.94 (240) | -9.00 (240) | 0/4 | — |
| ETH-USD | -0.21 (242) | -1.58 (242) | -9.00 (242) | 0/4 | — |
| SOL-USD | -0.20 (242) | -1.54 (242) | -5.29 (242) | 0/4 | — |

| Stock | gross | net | 2x slip | folds | test |
|---|---|---|---|---|---|
| AAPL | -0.13 (108) | -0.32 (108) | -0.39 (108) | 1/4 | — |
| NVDA | -0.08 (114) | -0.21 (113) | -0.29 (112) | 2/4 | — |
| QQQ | -0.02 (113) | -0.19 (113) | -0.35 (112) | 2/4 | — |
| SPY | -0.03 (115) | -0.26 (113) | -0.46 (109) | 1/4 | — |
| TSLA | -0.21 (113) | -0.30 (113) | -0.35 (112) | 0/4 | — |

### STRAT-153 Holy Grail (Raschke)
*5m · both · stock, crypto* — first pullback to the 20-EMA in a strong trend

Rules: entry long: `adx(14).adx > 30 and adx(14).adx > adx(14).adx[1] and adx(14).plus_di > adx(14).minus_di and low <= ema(close,20)` · entry short: `adx(14).adx > 30 and adx(14).adx > adx(14).adx[1] and adx(14).minus_di > adx(14).plus_di and high >= ema(close,20)` · order: stop long `high` short `low`, expires after 3 bars · stop: level long `low`, short `high` + 0.1 ATR buffer · target: 2.0R · max 2 trades/day

| Crypto | gross | low | retail | folds | test |
|---|---|---|---|---|---|
| BTC-USD | -0.24 (29) | -1.50 (29) | -8.12 (29) | 0/4 | — |
| ETH-USD | -0.38 (31) | -1.38 (31) | -7.64 (31) | 0/4 | — |
| SOL-USD | +0.08 (15) | -1.14 (15) | -4.13 (15) | 0/4 | — |

| Stock | gross | net | 2x slip | folds | test |
|---|---|---|---|---|---|
| AAPL | -0.03 (3) | -0.17 (3) | -1.29 (3) | 1/4 | — |
| NVDA | +0.14 (6) | +0.10 (6) | +0.07 (6) | 1/4 | — |
| QQQ | -1.01 (2) | -1.07 (2) | -1.12 (2) | 0/4 | — |
| SPY | +0.47 (2) | -1.17 (2) | -1.26 (2) | 0/4 | — |
| TSLA | -0.31 (4) | -0.35 (4) | -0.38 (4) | 1/4 | — |

### STRAT-154 The Anti (Raschke)
*5m · both · stock, crypto* — a counter-move against a slow stochastic trend that fails

Rules: entry long: `stoch(7,10,10).d > stoch(7,10,10).d[1] and stoch(7,10,10).k[1] < stoch(7,10,10).k[2] and stoch(7,10,10).k > stoch(7,10,10).k[1]` · entry short: `stoch(7,10,10).d < stoch(7,10,10).d[1] and stoch(7,10,10).k[1] > stoch(7,10,10).k[2] and stoch(7,10,10).k < stoch(7,10,10).k[1]` · stop: 1.5x ATR(14) · target: 1.5R · time stop: 12 bars · max 2 trades/day

| Crypto | gross | low | retail | folds | test |
|---|---|---|---|---|---|
| BTC-USD | -0.07 (244) | -1.41 (244) | -9.00 (244) | 0/4 | — |
| ETH-USD | -0.02 (244) | -0.97 (244) | -6.70 (244) | 0/4 | — |
| SOL-USD | -0.02 (244) | -1.40 (244) | -6.01 (244) | 0/4 | — |

| Stock | gross | net | 2x slip | folds | test |
|---|---|---|---|---|---|
| AAPL | +0.08 (118) | +0.02 (118) | -0.10 (118) | 3/4 | -0.24 (24) |
| NVDA | -0.12 (119) | -0.18 (119) | -0.22 (119) | 0/4 | — |
| QQQ | -0.16 (113) | -0.29 (113) | -0.40 (114) | 2/4 | — |
| SPY | -0.09 (115) | -0.28 (114) | -0.42 (114) | 0/4 | — |
| TSLA | +0.01 (118) | -0.02 (118) | -0.04 (117) | 2/4 | -0.48 (25) |

### STRAT-155 80-20s (Raschke)
*5m · both · stock, crypto* — a bar that opened at its top and closed at its bottom often reverses the next bar

Rules: entry long: `open[1] > low[1] + 0.8*(high[1] - low[1]) and close[1] < low[1] + 0.2*(high[1] - low[1]) and low < low[1] and close > low[1]` · entry short: `open[1] < low[1] + 0.2*(high[1] - low[1]) and close[1] > low[1] + 0.8*(high[1] - low[1]) and high > high[1] and close < high[1]` · stop: level long `low`, short `high` · target: 1.5R · time stop: 12 bars · max 2 trades/day

| Crypto | gross | low | retail | folds | test |
|---|---|---|---|---|---|
| BTC-USD | -0.06 (244) | -2.96 (244) | -9.00 (244) | 0/4 | — |
| ETH-USD | -0.25 (244) | -2.57 (244) | -9.00 (244) | 0/4 | — |
| SOL-USD | -0.05 (244) | -1.94 (244) | -8.12 (244) | 0/4 | — |

| Stock | gross | net | 2x slip | folds | test |
|---|---|---|---|---|---|
| AAPL | -0.17 (120) | -0.26 (120) | -0.37 (120) | 0/4 | — |
| NVDA | -0.10 (117) | -0.23 (117) | -0.35 (117) | 1/4 | — |
| QQQ | -0.22 (120) | -0.38 (120) | -0.56 (120) | 0/4 | — |
| SPY | -0.28 (120) | -0.70 (120) | -0.95 (120) | 0/4 | — |
| TSLA | -0.15 (120) | -0.27 (120) | -0.33 (120) | 0/4 | — |

## opening range

### STRAT-018 5-minute opening-range breakout in the first candle's direction
*5m · both · stock* — the first 5 minutes' direction carries information about the rest of the session

Rules: entry long: `bar_in_session() == 0 and close > open` · entry short: `bar_in_session() == 0 and close < open` · stop: level long `opening_range(5).low`, short `opening_range(5).high` · target: 10.0R · max 1 trades/day

| Stock | gross | net | 2x slip | folds | test |
|---|---|---|---|---|---|
| QQQ | +0.44 (60) | +0.34 (60) | +0.24 (60) | 2/4 | — |
| SPY | -0.07 (59) | -0.28 (59) | -0.45 (59) | 2/4 | — |

### STRAT-019 Opening-range breakout on a closing basis
*5m · both · stock, crypto* — acceptance of prices outside the opening auction's range

Rules: entry long: `cross_above(close, opening_range($m).high)` · entry short: `cross_below(close, opening_range($m).low)` · stop: level long `opening_range($m).mid`, short `opening_range($m).mid` · target: 2.0R · max 1 trades/day

| Crypto | gross | low | retail | folds | test |
|---|---|---|---|---|---|
| BTC-USD | -0.19 (107) | -1.61 (107) | -9.00 (107) | 0/4 | — |
| ETH-USD | -0.15 (106) | -1.14 (106) | -7.28 (106) | 0/4 | — |
| SOL-USD | -0.29 (106) | -1.40 (106) | -5.21 (106) | 0/4 | — |

| Stock | gross | net | 2x slip | folds | test |
|---|---|---|---|---|---|
| AAPL | +0.09 (55) | +0.07 (55) | +0.05 (55) | 1/4 | -0.18 (10) |
| NVDA | +0.00 (58) | -0.02 (58) | -0.04 (58) | 2/4 | — |
| QQQ | -0.12 (60) | -0.17 (60) | -0.31 (60) | 2/4 | — |
| SPY | +0.22 (59) | -0.02 (59) | -0.15 (59) | 1/4 | — |
| TSLA | -0.02 (49) | -0.04 (49) | -0.05 (49) | 2/4 | -0.92 (9) |

### STRAT-020 Stocks-in-play 5-minute ORB with ATR stop
*5m · both · stock* — attention/news days (abnormal opening volume) produce more persistent intraday moves

Rules: entry long: `bar_in_session() == 0 and close > open and rvol_tod(14) > 2` · entry short: `bar_in_session() == 0 and close < open and rvol_tod(14) > 2` · order: stop long `opening_range(5).high` short `opening_range(5).low`, expires after 70 bars · stop: level long `opening_range(5).high - 0.1*tf("1d", atr(14))`, short `opening_range(5).low + 0.1*tf("1d", atr(14))` · max 1 trades/day

| Stock | gross | net | 2x slip | folds | test |
|---|---|---|---|---|---|
| AAPL | -1.01 (3) | -1.09 (3) | -1.15 (3) | 0/4 | — |
| NVDA | -1.01 (1) | -1.07 (1) | -1.13 (1) | 0/4 | — |
| QQQ | — | — | — | 0/4 | — |
| SPY | -1.03 (1) | -1.23 (1) | -1.36 (1) | 0/4 | — |
| TSLA | -1.01 (3) | -1.05 (3) | -1.09 (3) | 0/4 | — |

### STRAT-021 Failed opening-range breakout fade
*5m · both · stock, crypto* — trapped breakout traders exit when price re-enters the range

Rules: entry long: `within(cross_below(close, opening_range(15).low), 3) and cross_above(close, opening_range(15).low)` · entry short: `within(cross_above(close, opening_range(15).high), 3) and cross_below(close, opening_range(15).high)` · stop: level long `session().low`, short `session().high` + 0.1 ATR buffer · target: level long `opening_range(15).high`, short `opening_range(15).low` · max 1 trades/day

| Crypto | gross | low | retail | folds | test |
|---|---|---|---|---|---|
| BTC-USD | +0.03 (86) | -1.06 (86) | -7.14 (86) | 0/4 | — |
| ETH-USD | +0.18 (95) | -0.52 (95) | -5.09 (95) | 0/4 | — |
| SOL-USD | -0.00 (91) | -0.87 (91) | -3.71 (91) | 0/4 | — |

| Stock | gross | net | 2x slip | folds | test |
|---|---|---|---|---|---|
| AAPL | -0.23 (28) | -0.29 (28) | -0.35 (28) | 1/4 | — |
| NVDA | -0.42 (33) | -0.47 (33) | -0.51 (33) | 1/4 | — |
| QQQ | +0.20 (32) | +0.09 (32) | -0.01 (32) | 2/4 | — |
| SPY | +0.08 (36) | -0.06 (36) | -0.18 (36) | 2/4 | — |
| TSLA | +0.01 (29) | -0.04 (29) | -0.08 (29) | 2/4 | — |

### STRAT-022 Opening-range breakout retest
*5m · both · stock, crypto* — broken resistance acting as support on the first retest

Rules: entry long: `since(cross_above(close, opening_range(15).high)) >= 2 and since(cross_above(close, opening_range(15).high)) <= 12 and low <= opening_range(15).high + 0.1*atr(14) and close > opening_range(15).high and close > open` · entry short: `since(cross_below(close, opening_range(15).low)) >= 2 and since(cross_below(close, opening_range(15).low)) <= 12 and high >= opening_range(15).low - 0.1*atr(14) and close < opening_range(15).low and close < open` · stop: level long `opening_range(15).mid`, short `opening_range(15).mid` · target: 2.0R · max 1 trades/day

| Crypto | gross | low | retail | folds | test |
|---|---|---|---|---|---|
| BTC-USD | -0.42 (72) | -1.68 (72) | -9.00 (72) | 0/4 | — |
| ETH-USD | -0.17 (69) | -1.18 (69) | -7.15 (69) | 0/4 | — |
| SOL-USD | -0.57 (70) | -1.58 (70) | -5.09 (70) | 0/4 | — |

| Stock | gross | net | 2x slip | folds | test |
|---|---|---|---|---|---|
| AAPL | +0.19 (25) | +0.16 (25) | +0.13 (25) | 3/4 | — |
| NVDA | +0.12 (28) | +0.09 (28) | +0.06 (28) | 3/4 | — |
| QQQ | -0.04 (32) | -0.10 (32) | -0.16 (32) | 1/4 | — |
| SPY | -0.06 (35) | -0.17 (35) | -0.35 (35) | 1/4 | — |
| TSLA | -0.18 (20) | -0.20 (20) | -0.21 (20) | 1/4 | — |

### STRAT-023 Narrow initial-balance range extension
*5m · both · stock* — Market Profile: a narrow first-hour range is more likely to be extended

Rules: entry long: `cross_above(close, opening_range(60).high) and opening_range(60).high - opening_range(60).low < 0.5*tf("1d", atr(14))` · entry short: `cross_below(close, opening_range(60).low) and opening_range(60).high - opening_range(60).low < 0.5*tf("1d", atr(14))` · stop: level long `opening_range(60).mid`, short `opening_range(60).mid` · target: level long `opening_range(60).high + (opening_range(60).high - opening_range(60).low)`, short `opening_range(60).low - (opening_range(60).high - opening_range(60).low)` · max 1 trades/day

| Stock | gross | net | 2x slip | folds | test |
|---|---|---|---|---|---|
| AAPL | -0.13 (18) | -0.16 (18) | -0.19 (18) | 2/4 | — |
| NVDA | +0.14 (21) | +0.12 (21) | +0.09 (21) | 1/4 | — |
| QQQ | -0.35 (34) | -0.41 (34) | -0.46 (34) | 0/4 | — |
| SPY | -0.08 (41) | -0.18 (41) | -0.28 (41) | 1/4 | — |
| TSLA | -0.31 (14) | -0.33 (14) | -0.35 (14) | 0/4 | — |

### STRAT-024 Initial-balance double-extension fade
*5m · both · stock* — auction exhaustion after price extends twice the initial balance

Rules: entry long: `low < opening_range(60).low - (opening_range(60).high - opening_range(60).low) and close > open and close > high[1]` · entry short: `high > opening_range(60).high + (opening_range(60).high - opening_range(60).low) and close < open and close < low[1]` · stop: level long `session().low`, short `session().high` + 0.1 ATR buffer · target: level long `opening_range(60).low`, short `opening_range(60).high` · max 1 trades/day

| Stock | gross | net | 2x slip | folds | test |
|---|---|---|---|---|---|
| AAPL | -0.11 (3) | -0.20 (3) | -0.28 (3) | 1/4 | — |
| NVDA | -0.47 (6) | -0.51 (6) | -0.56 (6) | 1/4 | — |
| QQQ | +0.67 (7) | +0.44 (7) | +0.25 (7) | 2/4 | — |
| SPY | -0.18 (10) | -0.40 (10) | -0.57 (10) | 1/4 | — |
| TSLA | +0.42 (2) | +0.34 (2) | +0.26 (2) | 1/4 | — |

### STRAT-025 Opening-drive continuation
*5m · both · stock* — a one-directional open (Market Profile 'open-drive') shows conviction

Rules: entry long: `bar_in_session() == 2 and opening_range(15).high - opening_range(15).low > 0.3*tf("1d", atr(14)) and close > opening_range(15).high - 0.2*(opening_range(15).high - opening_range(15).low)` · entry short: `bar_in_session() == 2 and opening_range(15).high - opening_range(15).low > 0.3*tf("1d", atr(14)) and close < opening_range(15).low + 0.2*(opening_range(15).high - opening_range(15).low)` · stop: level long `opening_range(15).low`, short `opening_range(15).high` · max 1 trades/day

| Stock | gross | net | 2x slip | folds | test |
|---|---|---|---|---|---|
| AAPL | +0.39 (21) | +0.37 (21) | +0.35 (21) | 3/4 | — |
| NVDA | +0.35 (22) | +0.33 (22) | +0.31 (22) | 3/4 | — |
| QQQ | +0.14 (16) | +0.09 (16) | +0.05 (16) | 2/4 | — |
| SPY | -0.22 (9) | -0.29 (9) | -0.35 (9) | 0/4 | — |
| TSLA | -0.01 (25) | -0.02 (25) | -0.03 (25) | 2/4 | — |

### STRAT-026 Open outside prior range, rejected back inside
*5m · both · stock* — failed auction above/below yesterday's range

Rules: entry long: `session().open < session().prev_low and cross_above(close, session().prev_low) and minutes_since_open() <= 60` · entry short: `session().open > session().prev_high and cross_below(close, session().prev_high) and minutes_since_open() <= 60` · stop: level long `session().low`, short `session().high` + 0.1 ATR buffer · target: level long `session().prev_close`, short `session().prev_close` · max 1 trades/day

| Stock | gross | net | 2x slip | folds | test |
|---|---|---|---|---|---|
| AAPL | +0.06 (5) | +0.04 (5) | +0.03 (5) | 2/4 | — |
| NVDA | +0.10 (5) | +0.09 (5) | +0.07 (5) | 2/4 | — |
| QQQ | -0.15 (12) | -0.19 (12) | -0.22 (12) | 1/4 | — |
| SPY | +0.25 (5) | +0.18 (5) | +0.12 (5) | 1/4 | — |
| TSLA | -0.67 (12) | -0.69 (12) | -0.70 (12) | 0/4 | — |

### STRAT-027 Asia-range breakout at the London open (crypto)
*15m · both · crypto* — liquidity and volatility step up when a new regional session opens

Rules: entry long: `cross_above(close, window_range(0,420).high) and time_between("07:00", "11:00")` · entry short: `cross_below(close, window_range(0,420).low) and time_between("07:00", "11:00")` · stop: level long `(window_range(0,420).high + window_range(0,420).low)/2`, short `(window_range(0,420).high + window_range(0,420).low)/2` · target: 1.5R · max 1 trades/day

| Crypto | gross | low | retail | folds | test |
|---|---|---|---|---|---|
| BTC-USD | +0.10 (34) | -0.23 (34) | -2.25 (34) | 0/4 | — |
| ETH-USD | +0.10 (40) | -0.19 (40) | -1.95 (40) | 0/4 | — |
| SOL-USD | +0.49 (33) | +0.22 (33) | -0.95 (33) | 0/4 | — |

### STRAT-028 Open +/- volatility breakout (Crabel stretch / Williams)
*5m · both · stock, crypto* — a move of a typical daily 'stretch' away from the open rarely reverses the same day

Rules: entry long: `bar_in_session() == 0` · entry short: `bar_in_session() == 0` · order: oco long `session().open + $k*tf("1d", mean(min(high - open, open - low), 10))` short `session().open - $k*tf("1d", mean(min(high - open, open - low), 10))`, expires after 60 bars · stop: 1.5x ATR(14) · max 1 trades/day

| Crypto | gross | low | retail | folds | test |
|---|---|---|---|---|---|
| BTC-USD | -0.44 (66) | -1.65 (66) | -9.00 (66) | 0/4 | — |
| ETH-USD | -0.08 (67) | -1.06 (67) | -6.90 (67) | 0/4 | — |
| SOL-USD | +0.27 (75) | -2.03 (75) | -7.07 (75) | 0/4 | — |

| Stock | gross | net | 2x slip | folds | test |
|---|---|---|---|---|---|
| AAPL | -0.10 (55) | -0.20 (55) | -0.31 (55) | 0/4 | — |
| NVDA | +0.14 (59) | -0.08 (59) | -0.13 (59) | 1/4 | — |
| QQQ | -0.33 (58) | -0.61 (58) | -0.82 (58) | 1/4 | — |
| SPY | -0.08 (59) | -0.45 (59) | -0.62 (59) | 1/4 | — |
| TSLA | -0.10 (58) | -0.15 (58) | -0.19 (58) | 2/4 | — |

## reference levels

### STRAT-035 Prior-day high/low breakout
*5m · both · stock, crypto* — stop orders resting beyond yesterday's extremes accelerate breakouts

Rules: entry long: `cross_above(close, session().prev_high) and rvol(20) > 1.2` · entry short: `cross_below(close, session().prev_low) and rvol(20) > 1.2` · stop: level long `session().prev_high`, short `session().prev_low` + 0.5 ATR buffer · target: 2.0R · max 1 trades/day

| Crypto | gross | low | retail | folds | test |
|---|---|---|---|---|---|
| BTC-USD | +0.36 (58) | -0.91 (58) | -8.28 (58) | 0/4 | — |
| ETH-USD | -0.26 (51) | -1.10 (51) | -6.24 (51) | 0/4 | — |
| SOL-USD | +0.01 (54) | -1.03 (54) | -4.62 (54) | 0/4 | — |

| Stock | gross | net | 2x slip | folds | test |
|---|---|---|---|---|---|
| AAPL | +0.26 (31) | +0.22 (31) | +0.18 (31) | 2/4 | — |
| NVDA | +0.24 (28) | +0.10 (28) | +0.08 (28) | 2/4 | — |
| QQQ | -0.01 (32) | -0.17 (32) | -0.23 (32) | 2/4 | — |
| SPY | +0.19 (29) | +0.00 (29) | -0.26 (29) | 1/4 | — |
| TSLA | +0.10 (40) | -0.01 (40) | -0.04 (40) | 2/4 | -0.34 (10) |

### STRAT-036 Prior-day extreme rejection
*5m · both · stock, crypto* — take-profit orders cluster at yesterday's extremes

Rules: entry long: `low < session().prev_low and close > session().prev_low and close[1] > session().prev_low` · entry short: `high > session().prev_high and close < session().prev_high and close[1] < session().prev_high` · stop: level long `low`, short `high` + 0.2 ATR buffer · target: level long `vwap()`, short `vwap()` · max 1 trades/day

| Crypto | gross | low | retail | folds | test |
|---|---|---|---|---|---|
| BTC-USD | -0.26 (44) | -1.38 (44) | -8.22 (44) | 0/4 | — |
| ETH-USD | +0.75 (41) | -0.71 (41) | -9.00 (41) | 0/4 | — |
| SOL-USD | -0.23 (50) | -1.51 (50) | -6.03 (50) | 0/4 | — |

| Stock | gross | net | 2x slip | folds | test |
|---|---|---|---|---|---|
| AAPL | -0.20 (32) | -0.31 (32) | -0.40 (32) | 2/4 | — |
| NVDA | +0.06 (32) | -0.04 (32) | -0.13 (32) | 2/4 | — |
| QQQ | -0.16 (33) | -0.39 (33) | -0.55 (33) | 0/4 | — |
| SPY | -0.49 (28) | -0.85 (28) | -1.10 (28) | 0/4 | — |
| TSLA | -0.61 (30) | -0.67 (30) | -0.72 (30) | 1/4 | — |

### STRAT-037 Turtle Soup (failed 20-bar breakdown)
*5m · both · stock, crypto* — failed new extremes trap breakout traders

Rules: entry long: `low < lowest(low,20)[1] and since(low <= lowest(low,20))[1] >= 4 and close > lowest(low,20)[1]` · entry short: `high > highest(high,20)[1] and since(high >= highest(high,20))[1] >= 4 and close < highest(high,20)[1]` · stop: level long `low`, short `high` + 0.1 ATR buffer · target: 2.0R · time stop: 24 bars · max 2 trades/day

| Crypto | gross | low | retail | folds | test |
|---|---|---|---|---|---|
| BTC-USD | -0.04 (228) | -3.00 (228) | -9.00 (228) | 0/4 | — |
| ETH-USD | +0.08 (233) | -1.88 (233) | -9.00 (233) | 0/4 | — |
| SOL-USD | -0.14 (213) | -1.78 (212) | -7.50 (212) | 0/4 | — |

| Stock | gross | net | 2x slip | folds | test |
|---|---|---|---|---|---|
| AAPL | +0.25 (88) | +0.10 (87) | -0.04 (87) | 3/4 | -0.03 (18) |
| NVDA | +0.00 (83) | -0.12 (83) | -0.23 (83) | 1/4 | — |
| QQQ | -0.32 (81) | -0.60 (80) | -0.81 (79) | 0/4 | — |
| SPY | -0.13 (78) | -0.60 (78) | -0.87 (78) | 0/4 | — |
| TSLA | -0.14 (87) | -0.28 (87) | -0.43 (87) | 0/4 | — |

### STRAT-038 Floor-pivot support bounce
*5m · both · stock, crypto* — widely watched calculated levels attract resting orders

Rules: entry long: `low <= pivots("classic").s1 and close > pivots("classic").s1 and close > open` · entry short: `high >= pivots("classic").r1 and close < pivots("classic").r1 and close < open` · stop: level long `low`, short `high` + 0.25 ATR buffer · target: level long `pivots("classic").p`, short `pivots("classic").p` · max 2 trades/day

| Crypto | gross | low | retail | folds | test |
|---|---|---|---|---|---|
| BTC-USD | -0.39 (65) | -1.53 (65) | -8.59 (65) | 0/4 | — |
| ETH-USD | +0.14 (68) | -0.58 (68) | -4.93 (68) | 0/4 | — |
| SOL-USD | +0.15 (70) | -0.89 (70) | -4.23 (70) | 0/4 | — |

| Stock | gross | net | 2x slip | folds | test |
|---|---|---|---|---|---|
| AAPL | +0.08 (53) | -0.02 (53) | -0.11 (53) | 2/4 | — |
| NVDA | +0.06 (50) | +0.01 (50) | -0.04 (50) | 2/4 | — |
| QQQ | +0.14 (48) | +0.02 (48) | -0.08 (48) | 3/4 | — |
| SPY | +0.07 (61) | -0.17 (61) | -0.37 (61) | 2/4 | — |
| TSLA | +0.14 (56) | +0.09 (56) | +0.04 (56) | 2/4 | — |

### STRAT-039 Floor-pivot resistance breakout
*5m · both · stock, crypto* — breaking a watched level triggers stops

Rules: entry long: `cross_above(close, pivots("classic").r1) and close > vwap()` · entry short: `cross_below(close, pivots("classic").s1) and close < vwap()` · stop: level long `pivots("classic").p`, short `pivots("classic").p` · target: level long `pivots("classic").r2`, short `pivots("classic").s2` · max 1 trades/day

| Crypto | gross | low | retail | folds | test |
|---|---|---|---|---|---|
| BTC-USD | +0.12 (50) | -0.07 (50) | -1.19 (50) | 0/4 | — |
| ETH-USD | -0.03 (49) | -0.19 (49) | -1.15 (49) | 0/4 | — |
| SOL-USD | +0.09 (47) | -0.07 (47) | -0.68 (47) | 0/4 | — |

| Stock | gross | net | 2x slip | folds | test |
|---|---|---|---|---|---|
| AAPL | +0.12 (39) | +0.11 (39) | +0.09 (39) | 2/4 | — |
| NVDA | -0.01 (41) | -0.02 (41) | -0.03 (41) | 1/4 | — |
| QQQ | -0.06 (36) | -0.09 (36) | -0.11 (36) | 1/4 | — |
| SPY | +0.01 (41) | -0.03 (41) | -0.07 (41) | 1/4 | — |
| TSLA | +0.02 (48) | +0.01 (48) | +0.00 (48) | 3/4 | -0.11 (9) |

### STRAT-040 Round-number breakout acceleration
*5m · both · stock, crypto* — stop-loss orders cluster just beyond round numbers, so crossing them accelerates the move

Rules: entry long: `floor_to(close, $step) > floor_to(close[1], $step)` · entry short: `floor_to(close, $step) < floor_to(close[1], $step)` · stop: level long `floor_to(close, $step)`, short `ceil_to(close, $step)` + 0.5 ATR buffer · target: 2.0R · max 2 trades/day

| Crypto | gross | low | retail | folds | test |
|---|---|---|---|---|---|
| BTC-USD | +0.00 (228) | -1.80 (227) | -9.00 (227) | 0/4 | — |
| ETH-USD | +0.10 (130) | -0.85 (130) | -6.46 (130) | 0/4 | — |
| SOL-USD | +0.38 (50) | -0.56 (50) | -4.09 (50) | 0/4 | — |

| Stock | gross | net | 2x slip | folds | test |
|---|---|---|---|---|---|
| AAPL | -0.21 (94) | -0.28 (94) | -0.34 (94) | 1/4 | — |
| NVDA | -0.20 (89) | -0.28 (89) | -0.32 (89) | 0/4 | — |
| QQQ | -0.00 (102) | -0.15 (101) | -0.31 (100) | 2/4 | — |
| SPY | +0.22 (89) | +0.07 (88) | -0.02 (88) | 2/4 | — |
| TSLA | +0.06 (107) | +0.03 (107) | -0.03 (107) | 3/4 | -0.35 (21) |

### STRAT-041 Round-number rejection
*5m · both · stock, crypto* — take-profit orders cluster at round numbers, so trends pause or reverse there

Rules: entry long: `low <= floor_to(close[1], $step) and close > floor_to(close[1], $step) and min(open, close) - low > 0.5*(high - low)` · entry short: `high >= ceil_to(close[1], $step) and close < ceil_to(close[1], $step) and high - max(open, close) > 0.5*(high - low)` · stop: level long `low`, short `high` + 0.2 ATR buffer · target: 1.5R · max 2 trades/day

| Crypto | gross | low | retail | folds | test |
|---|---|---|---|---|---|
| BTC-USD | -0.03 (170) | -1.62 (170) | -9.00 (170) | 0/4 | — |
| ETH-USD | -0.13 (69) | -1.37 (69) | -7.91 (69) | 0/4 | — |
| SOL-USD | -0.14 (22) | -0.95 (22) | -4.38 (22) | 0/4 | — |

| Stock | gross | net | 2x slip | folds | test |
|---|---|---|---|---|---|
| AAPL | -0.07 (67) | -0.21 (67) | -0.31 (67) | 1/4 | — |
| NVDA | -0.30 (55) | -0.41 (55) | -0.46 (55) | 0/4 | — |
| QQQ | -0.16 (83) | -0.47 (83) | -0.76 (83) | 0/4 | — |
| SPY | -0.22 (64) | -0.42 (64) | -0.61 (63) | 0/4 | — |
| TSLA | +0.11 (92) | +0.08 (92) | +0.03 (92) | 3/4 | -0.41 (16) |

### STRAT-042 Reversion to the session open
*5m · both · stock, crypto* — the opening price is the day's reference for trapped inventory

Rules: entry long: `session().open - close > 0.5*tf("1d", atr(14)) and rsi(close,14) < 30 and minutes_since_open() >= 90` · entry short: `close - session().open > 0.5*tf("1d", atr(14)) and rsi(close,14) > 70 and minutes_since_open() >= 90` · stop: 1.5x ATR(14) · target: level long `session().open`, short `session().open` · max 1 trades/day

| Crypto | gross | low | retail | folds | test |
|---|---|---|---|---|---|
| BTC-USD | -0.27 (33) | -1.06 (33) | -6.04 (33) | 0/4 | — |
| ETH-USD | +0.19 (33) | -0.34 (33) | -3.65 (33) | 0/4 | — |
| SOL-USD | +0.11 (33) | -0.76 (33) | -3.92 (33) | 0/4 | — |

| Stock | gross | net | 2x slip | folds | test |
|---|---|---|---|---|---|
| AAPL | +0.61 (20) | +0.56 (20) | +0.50 (20) | 4/4 | — |
| NVDA | -0.56 (20) | -0.60 (20) | -0.64 (20) | 0/4 | — |
| QQQ | +0.75 (14) | +0.66 (14) | +0.44 (14) | 3/4 | — |
| SPY | +0.44 (17) | +0.29 (17) | +0.15 (17) | 3/4 | — |
| TSLA | -0.49 (20) | -0.52 (20) | -0.64 (20) | 0/4 | — |

### STRAT-043 Late-session new high breakout
*5m · both · stock* — late-day breakouts are joined by end-of-day positioning

Rules: entry long: `cross_above(close, session().high[1]) and tod() >= 900 and close > vwap()` · entry short: `cross_below(close, session().low[1]) and tod() >= 900 and close < vwap()` · stop: level long `vwap()`, short `vwap()` · max 1 trades/day

| Stock | gross | net | 2x slip | folds | test |
|---|---|---|---|---|---|
| AAPL | -0.12 (13) | -0.14 (13) | -0.17 (13) | 0/4 | — |
| NVDA | -0.22 (7) | -0.24 (7) | -0.26 (7) | 0/4 | — |
| QQQ | -0.13 (12) | -0.17 (12) | -0.21 (12) | 0/4 | — |
| SPY | -0.15 (13) | -0.20 (13) | -0.24 (13) | 0/4 | — |
| TSLA | -0.22 (12) | -0.23 (12) | -0.24 (12) | 0/4 | — |

### STRAT-044 Midday-range breakout
*5m · both · stock* — the lunch lull compresses ranges before afternoon participation returns

Rules: entry long: `cross_above(close, window_range(690,810).high) and tod() >= 810` · entry short: `cross_below(close, window_range(690,810).low) and tod() >= 810` · stop: level long `(window_range(690,810).high + window_range(690,810).low)/2`, short `(window_range(690,810).high + window_range(690,810).low)/2` · target: 2.0R · max 1 trades/day

| Stock | gross | net | 2x slip | folds | test |
|---|---|---|---|---|---|
| AAPL | -0.11 (40) | -0.19 (40) | -0.28 (40) | 0/4 | — |
| NVDA | -0.12 (33) | -0.16 (33) | -0.19 (33) | 1/4 | — |
| QQQ | -0.16 (36) | -0.26 (36) | -0.32 (36) | 1/4 | — |
| SPY | -0.10 (39) | -0.23 (39) | -0.33 (39) | 1/4 | — |
| TSLA | -0.23 (40) | -0.25 (40) | -0.28 (40) | 0/4 | — |

### STRAT-045 Ten o'clock reversal
*5m · both · stock* — opening-order flow is exhausted about 30 minutes in

Rules: entry long: `time_between("10:00", "10:30") and valuewhen(minutes_since_open() == 25, close) / session().open - 1 < -0.004 and close > high[1]` · entry short: `time_between("10:00", "10:30") and valuewhen(minutes_since_open() == 25, close) / session().open - 1 > 0.004 and close < low[1]` · stop: level long `session().low`, short `session().high` + 0.1 ATR buffer · target: level long `vwap()`, short `vwap()` · max 1 trades/day

| Stock | gross | net | 2x slip | folds | test |
|---|---|---|---|---|---|
| AAPL | -0.14 (24) | -0.18 (24) | -0.21 (24) | 1/4 | — |
| NVDA | +0.14 (25) | +0.06 (25) | +0.03 (25) | 2/4 | — |
| QQQ | -0.07 (14) | -0.13 (14) | -0.19 (14) | 2/4 | — |
| SPY | — | — | — | 0/4 | — |
| TSLA | -0.07 (29) | -0.10 (29) | -0.12 (29) | 1/4 | — |

## scheduled events

### STRAT-103 Pre-FOMC announcement drift (intraday part)
*5m · long · stock* — equities rise ahead of scheduled FOMC announcements

Rules: entry long: `bar_in_session() == 0 and event("fomc") == 1` · stop: 4.0x ATR(14) · exit long: `tod() >= 830` · max 1 trades/day

| Stock | gross | net | 2x slip | folds | test |
|---|---|---|---|---|---|
| QQQ | -0.31 (2) | -0.35 (2) | -0.40 (2) | 1/4 | — |
| SPY | -0.36 (2) | -0.43 (2) | -0.50 (2) | 1/4 | — |

### STRAT-104 Macro-announcement-day long (CPI)
*5m · long · stock* — announcement-day risk premium

Rules: entry long: `bar_in_session() == 0 and event("cpi") == 1` · stop: 4.0x ATR(14) · max 1 trades/day

| Stock | gross | net | 2x slip | folds | test |
|---|---|---|---|---|---|
| QQQ | +0.11 (3) | +0.08 (3) | +0.05 (3) | 1/4 | — |
| SPY | +0.10 (3) | +0.05 (3) | +0.00 (3) | 1/4 | — |

### STRAT-105 Earnings-day opening-range breakout
*5m · both · stock* — earnings days concentrate information and attention

Rules: entry long: `event("earnings") == 1 and session().gap > 0 and cross_above(close, opening_range(15).high)` · entry short: `event("earnings") == 1 and session().gap < 0 and cross_below(close, opening_range(15).low)` · stop: level long `opening_range(15).low`, short `opening_range(15).high` · max 1 trades/day

| Stock | gross | net | 2x slip | folds | test |
|---|---|---|---|---|---|
| AAPL | — | — | — | 0/4 | — |
| NVDA | — | — | — | 0/4 | — |
| QQQ | — | — | — | 0/4 | — |
| SPY | — | — | — | 0/4 | — |
| TSLA | — | — | — | 0/4 | — |

### STRAT-161 FOMC post-announcement drift
*5m · both · stock* — the first 30 minutes after the FOMC statement set the direction for the rest of the session

Rules: entry long: `event("fomc") == 1 and tod() == 870 and close - valuewhen(tod() == 835, close) > 3*atr(14)` · entry short: `event("fomc") == 1 and tod() == 870 and close - valuewhen(tod() == 835, close) < -3*atr(14)` · stop: 3.0x ATR(14) · max 1 trades/day

| Stock | gross | net | 2x slip | folds | test |
|---|---|---|---|---|---|
| QQQ | — | — | — | 0/4 | — |
| SPY | -1.01 (1) | -1.07 (1) | -1.14 (1) | 0/4 | — |

## statistical

### STRAT-135 Variance-ratio regime switch
*5m · both · stock, crypto* — markets alternate between trending (VR>1) and mean-reverting (VR<1) states

Rules: entry long: `(variance_ratio(120,5) > 1.2 and close > donchian(20).upper[1]) or (variance_ratio(120,5) < 0.8 and cross_above(close, bb(close,20,2).lower))` · entry short: `(variance_ratio(120,5) > 1.2 and close < donchian(20).lower[1]) or (variance_ratio(120,5) < 0.8 and cross_below(close, bb(close,20,2).upper))` · stop: 2.0x ATR(14) · target: 1.5R · time stop: 24 bars · max 2 trades/day

| Crypto | gross | low | retail | folds | test |
|---|---|---|---|---|---|
| BTC-USD | -0.12 (206) | -1.13 (206) | -7.24 (206) | 0/4 | — |
| ETH-USD | +0.07 (205) | -0.63 (205) | -4.92 (205) | 0/4 | — |
| SOL-USD | -0.05 (198) | -1.00 (200) | -4.46 (200) | 0/4 | — |

| Stock | gross | net | 2x slip | folds | test |
|---|---|---|---|---|---|
| AAPL | +0.14 (64) | +0.07 (64) | +0.01 (64) | 2/4 | — |
| NVDA | -0.10 (82) | -0.15 (82) | -0.19 (84) | 1/4 | — |
| QQQ | +0.09 (73) | +0.02 (73) | -0.07 (73) | 3/4 | — |
| SPY | +0.07 (81) | -0.04 (82) | -0.20 (82) | 1/4 | — |
| TSLA | -0.06 (102) | -0.08 (102) | -0.10 (102) | 0/4 | — |

### STRAT-136 Autocorrelation-signed follow/fade
*5m · both · stock, crypto* — the sign of recent return autocorrelation persists

Rules: entry long: `(autocorr(60,1) > 0.1 and close > close[1]) or (autocorr(60,1) < -0.1 and close < close[1])` · entry short: `(autocorr(60,1) > 0.1 and close < close[1]) or (autocorr(60,1) < -0.1 and close > close[1])` · stop: 1.5x ATR(14) · time stop: 2 bars · max 10 trades/day

| Crypto | gross | low | retail | folds | test |
|---|---|---|---|---|---|
| BTC-USD | +0.01 (1214) | -1.38 (1214) | -9.00 (1214) | 0/4 | — |
| ETH-USD | +0.03 (1220) | -0.97 (1220) | -7.28 (1220) | 0/4 | — |
| SOL-USD | +0.02 (1220) | -1.33 (1220) | -6.22 (1220) | 0/4 | — |

| Stock | gross | net | 2x slip | folds | test |
|---|---|---|---|---|---|
| AAPL | -0.03 (491) | -0.09 (492) | -0.16 (493) | 0/4 | — |
| NVDA | +0.04 (486) | -0.01 (486) | -0.06 (486) | 2/4 | — |
| QQQ | -0.02 (448) | -0.13 (450) | -0.23 (451) | 0/4 | — |
| SPY | -0.03 (448) | -0.21 (448) | -0.38 (449) | 0/4 | — |
| TSLA | +0.00 (522) | -0.04 (522) | -0.07 (522) | 1/4 | — |

### STRAT-137 Ornstein-Uhlenbeck reversion with half-life filter
*5m · both · stock, crypto* — fast-mean-reverting deviations revert within their half-life

Rules: entry long: `zscore(close,100) < -2 and beta(close - mean(close,100), close[1] - mean(close,100)[1], 100) < 0.966` · entry short: `zscore(close,100) > 2 and beta(close - mean(close,100), close[1] - mean(close,100)[1], 100) < 0.966` · stop: 2.0x ATR(14) · target: level long `mean(close,100)`, short `mean(close,100)` · time stop: 20 bars · max 2 trades/day

| Crypto | gross | low | retail | folds | test |
|---|---|---|---|---|---|
| BTC-USD | -0.11 (154) | -1.13 (156) | -7.18 (156) | 0/4 | — |
| ETH-USD | +0.14 (153) | -0.53 (153) | -4.64 (153) | 0/4 | — |
| SOL-USD | +0.01 (150) | -1.04 (152) | -4.40 (152) | 0/4 | — |

| Stock | gross | net | 2x slip | folds | test |
|---|---|---|---|---|---|
| AAPL | +0.02 (53) | -0.05 (53) | -0.09 (53) | 2/4 | — |
| NVDA | -0.27 (48) | -0.30 (48) | -0.35 (48) | 0/4 | — |
| QQQ | -0.07 (53) | -0.12 (53) | -0.18 (53) | 1/4 | — |
| SPY | +0.01 (46) | -0.10 (46) | -0.21 (46) | 1/4 | — |
| TSLA | +0.29 (49) | +0.28 (49) | +0.26 (49) | 4/4 | +0.46 (17) |

## swing

### STRAT-407 Swing RSI(2) dip in an uptrend (4 ATR, 3R, 96h, limit entry)
*1h · long · crypto* — short-term oversold dips inside an uptrend tend to recover over the next days

Rules: entry long: `rsi(close,2) < 10 and close > ema(close,200)` · order: limit long `close * 0.999`, expires after 3 bars · stop: 4.0x ATR(14) · target: 3.0R · time stop: 96 bars · max 3 trades/day

| Crypto | gross | low | retail | folds | test |
|---|---|---|---|---|---|
| BTC-USD | +0.14 (308) | +0.07 (308) | -0.30 (308) | 0/4 | — |
| ETH-USD | +0.04 (296) | -0.02 (296) | -0.30 (296) | 0/4 | — |
| SOL-USD | +0.23 (276) | +0.18 (276) | -0.01 (276) | 2/4 | — |

### STRAT-408 Swing memecoin 24-hour breakout (4 ATR, 2R, 96h, limit entry)
*1h · long · crypto* — memecoin breakouts to new daily highs in an uptrend tend to continue for days

Rules: entry long: `close > highest(high,24)[1] and close > ema(close,200)` · order: limit long `close * 0.999`, expires after 3 bars · stop: 4.0x ATR(14) · target: 2.0R · time stop: 96 bars · max 3 trades/day

| Crypto | gross | low | retail | folds | test |
|---|---|---|---|---|---|
| BONK-USD | +0.17 (180) | +0.13 (180) | -0.00 (180) | 2/4 | — |
| DOGE-USD | +0.04 (353) | -0.02 (353) | -0.23 (353) | 1/4 | — |
| FLOKI-USD | +0.04 (122) | -0.02 (122) | -0.20 (122) | 1/4 | — |
| PEPE-USD | +0.11 (120) | +0.06 (120) | -0.10 (120) | 2/4 | — |
| SHIB-USD | +0.10 (315) | +0.04 (315) | -0.16 (315) | 1/4 | — |
| WIF-USD | +0.06 (122) | +0.02 (122) | -0.13 (122) | 0/4 | — |

### STRAT-409 Swing memecoin 48-hour breakout retest (4 ATR, 3R, 96h, limit entry)
*1h · long · crypto* — a broken 48-hour high that holds on the first pullback marks demand

Rules: entry long: `since(close > highest(high,48)[1]) >= 1 and since(close > highest(high,48)[1]) <= 12 and low <= valuewhen(close > highest(high,48)[1], highest(high,48)[1]) * 1.002 and close > valuewhen(close > highest(high,48)[1], highest(high,48)[1]) and close > ema(close,200)` · order: limit long `close * 0.999`, expires after 3 bars · stop: 4.0x ATR(14) · target: 3.0R · time stop: 96 bars · max 3 trades/day

| Crypto | gross | low | retail | folds | test |
|---|---|---|---|---|---|
| BONK-USD | +0.26 (113) | +0.22 (113) | +0.09 (113) | 2/4 | — |
| DOGE-USD | +0.18 (223) | +0.12 (223) | -0.09 (223) | 1/4 | — |
| FLOKI-USD | +0.25 (67) | +0.20 (67) | +0.03 (67) | 2/4 | — |
| PEPE-USD | -0.16 (82) | -0.21 (82) | -0.37 (82) | 0/4 | — |
| SHIB-USD | +0.15 (200) | +0.10 (200) | -0.10 (200) | 1/4 | — |
| WIF-USD | -0.09 (74) | -0.14 (74) | -0.28 (74) | 1/4 | — |

## time of day

### STRAT-097 Intraday momentum: first half-hour predicts the last
*5m · both · stock* — late-day trading by informed/hedging participants continues the morning's direction

Rules: entry long: `tod() == 925 and valuewhen(minutes_since_open() == 25, close) / session().prev_close - 1 > 0` · entry short: `tod() == 925 and valuewhen(minutes_since_open() == 25, close) / session().prev_close - 1 < 0` · stop: 3.0x ATR(14) · max 1 trades/day

| Stock | gross | net | 2x slip | folds | test |
|---|---|---|---|---|---|
| QQQ | +0.11 (59) | +0.03 (59) | -0.06 (59) | 2/4 | — |
| SPY | -0.05 (59) | -0.17 (59) | -0.30 (59) | 1/4 | — |

### STRAT-098 Same-time-of-day return persistence
*5m · both · stock, crypto* — returns at the same half-hour recur across days

Rules: entry long: `tod_return(20,6).t > 2` · entry short: `tod_return(20,6).t < -2` · stop: 2.0x ATR(14) · time stop: 6 bars · max 4 trades/day

| Crypto | gross | low | retail | folds | test |
|---|---|---|---|---|---|
| BTC-USD | -0.03 (276) | -1.12 (276) | -8.07 (276) | 0/4 | — |
| ETH-USD | -0.02 (333) | -0.80 (333) | -5.76 (333) | 0/4 | — |
| SOL-USD | +0.00 (306) | -1.01 (307) | -4.74 (307) | 0/4 | — |

| Stock | gross | net | 2x slip | folds | test |
|---|---|---|---|---|---|
| AAPL | -0.02 (63) | -0.08 (63) | -0.14 (63) | 1/4 | — |
| NVDA | -0.07 (56) | -0.12 (56) | -0.16 (56) | 0/4 | — |
| QQQ | -0.03 (88) | -0.14 (88) | -0.26 (89) | 0/4 | — |
| SPY | -0.04 (89) | -0.23 (90) | -0.40 (90) | 0/4 | — |
| TSLA | +0.02 (89) | -0.01 (89) | -0.05 (89) | 2/4 | -0.18 (28) |

### STRAT-099 Turn-of-the-month intraday long
*5m · long · stock* — month-end/start flows lift equities

Rules: entry long: `bar_in_session() == 0 and (dom() <= 3 or days_to_month_end() <= 2)` · stop: 4.0x ATR(14) · max 1 trades/day

| Stock | gross | net | 2x slip | folds | test |
|---|---|---|---|---|---|
| QQQ | +0.68 (8) | +0.65 (8) | +0.62 (8) | 2/4 | — |
| SPY | +0.42 (8) | +0.37 (8) | +0.32 (8) | 2/4 | — |

### STRAT-100 Pre-holiday session long
*5m · long · stock* — positive returns before market holidays

Rules: entry long: `bar_in_session() == 0 and pre_holiday() == 1` · stop: 4.0x ATR(14) · max 1 trades/day

| Stock | gross | net | 2x slip | folds | test |
|---|---|---|---|---|---|
| AAPL | -1.00 (1) | -1.03 (1) | -1.06 (1) | 0/4 | — |
| NVDA | -1.00 (1) | -1.02 (1) | -1.03 (1) | 0/4 | — |
| QQQ | -1.01 (1) | -1.07 (1) | -1.13 (1) | 0/4 | — |
| SPY | -1.01 (1) | -1.11 (1) | -1.21 (1) | 0/4 | — |
| TSLA | -0.45 (1) | -0.46 (1) | -0.47 (1) | 0/4 | — |

### STRAT-101 Option-expiration pinning reversion
*5m · both · stock* — hedging flows pin optionable stocks near strikes on expiration day

Rules: entry long: `is_opex() == 1 and tod() >= 780 and close < (floor_to(close,5) + 2.5) and close / floor_to(close,5) - 1 < 0.001 and close > open` · entry short: `is_opex() == 1 and tod() >= 780 and close > (floor_to(close,5) + 2.5) and close / (floor_to(close,5) + 5) - 1 > -0.001 and close < open` · stop: 1.5x ATR(14) · target: 1.0R · max 1 trades/day

| Stock | gross | net | 2x slip | folds | test |
|---|---|---|---|---|---|
| AAPL | +0.32 (3) | +0.29 (3) | +0.25 (3) | 2/4 | — |
| NVDA | -0.34 (3) | -0.40 (3) | -0.46 (3) | 1/4 | — |
| QQQ | -0.02 (2) | -0.14 (2) | -0.26 (2) | 1/4 | — |
| SPY | +0.31 (3) | +0.23 (3) | -0.66 (3) | 2/4 | — |
| TSLA | -1.01 (2) | -1.05 (2) | -1.10 (2) | 0/4 | — |

### STRAT-102 Lunchtime reversal of the morning trend
*5m · both · stock* — morning trend participants take profits during the lunch lull

Rules: entry long: `time_between("11:30", "13:30") and close / session().open - 1 < -0.007 and cross_above(close, ema(close,20))` · entry short: `time_between("11:30", "13:30") and close / session().open - 1 > 0.007 and cross_below(close, ema(close,20))` · stop: level long `session().low`, short `session().high` · target: level long `vwap()`, short `vwap()` · max 1 trades/day

| Stock | gross | net | 2x slip | folds | test |
|---|---|---|---|---|---|
| AAPL | +0.00 (23) | -0.03 (23) | -0.07 (23) | 3/4 | — |
| NVDA | +0.07 (24) | +0.08 (24) | +0.05 (24) | 1/4 | — |
| QQQ | +0.21 (10) | +0.17 (10) | +0.13 (10) | 3/4 | — |
| SPY | -0.09 (2) | -0.15 (2) | -0.21 (2) | 0/4 | — |
| TSLA | -0.03 (30) | -0.05 (30) | -0.06 (30) | 3/4 | — |

## trend following

### STRAT-001 EMA 9/21 crossover with session-VWAP filter
*1m · long · stock, crypto* — short-horizon trend persistence after a fast/slow average crossover, taken only on the side of the session's volume-weighted average price

Rules: entry long: `cross_above(ema(close,$fast), ema(close,$slow))` · filters: `close > vwap()` · stop: 2.0x ATR(14) · target: 2.0R · exit long: `cross_below(ema(close,$fast), ema(close,$slow))` · max 20 trades/day

| Crypto | gross | low | retail | folds | test |
|---|---|---|---|---|---|
| BTC-USD | -0.04 (232) | -2.92 (234) | -9.00 (234) | 0/4 | — |

### STRAT-002 Aligned EMA ribbon pullback
*5m · both · stock, crypto* — buy weakness inside an established trend (trend defined by stacked averages)

Rules: entry long: `ema(close,8) > ema(close,21) and ema(close,21) > ema(close,55) and low <= ema(close,21) and close > ema(close,21) and close > open` · entry short: `ema(close,8) < ema(close,21) and ema(close,21) < ema(close,55) and high >= ema(close,21) and close < ema(close,21) and close < open` · stop: level long `ema(close,55)`, short `ema(close,55)` + 0.25 ATR buffer · target: 2.0R · max 3 trades/day

| Crypto | gross | low | retail | folds | test |
|---|---|---|---|---|---|
| BTC-USD | -0.08 (330) | -1.52 (330) | -9.00 (330) | 0/4 | — |
| ETH-USD | -0.01 (326) | -1.19 (325) | -7.98 (325) | 0/4 | — |
| SOL-USD | -0.00 (332) | -1.20 (330) | -5.05 (330) | 0/4 | — |

| Stock | gross | net | 2x slip | folds | test |
|---|---|---|---|---|---|
| AAPL | -0.08 (107) | -0.16 (107) | -0.25 (108) | 1/4 | — |
| NVDA | -0.07 (102) | -0.13 (101) | -0.20 (99) | 2/4 | — |
| QQQ | +0.04 (96) | -0.09 (93) | -0.21 (93) | 3/4 | — |
| SPY | +0.02 (91) | -0.14 (89) | -0.29 (89) | 2/4 | — |
| TSLA | -0.05 (103) | -0.12 (103) | -0.16 (103) | 2/4 | — |

### STRAT-003 MACD signal-line crossover
*5m · both · stock, crypto* — change in the slope of smoothed momentum

Rules: entry long: `cross_above(macd(close,12,26,9).line, macd(close,12,26,9).signal) and macd(close,12,26,9).line > 0` · entry short: `cross_below(macd(close,12,26,9).line, macd(close,12,26,9).signal) and macd(close,12,26,9).line < 0` · stop: 2.0x ATR(14) · target: 2.0R · exit long: `cross_below(macd(close,12,26,9).line, macd(close,12,26,9).signal)` · exit short: `cross_above(macd(close,12,26,9).line, macd(close,12,26,9).signal)` · max 2 trades/day

| Crypto | gross | low | retail | folds | test |
|---|---|---|---|---|---|
| BTC-USD | +0.01 (219) | -1.09 (219) | -7.85 (219) | 0/4 | — |
| ETH-USD | -0.10 (224) | -0.89 (224) | -5.71 (224) | 0/4 | — |
| SOL-USD | -0.09 (224) | -1.06 (225) | -4.74 (225) | 0/4 | — |

| Stock | gross | net | 2x slip | folds | test |
|---|---|---|---|---|---|
| AAPL | +0.09 (74) | +0.05 (74) | +0.00 (74) | 2/4 | — |
| NVDA | -0.02 (91) | -0.09 (91) | -0.13 (91) | 1/4 | — |
| QQQ | -0.13 (89) | -0.22 (89) | -0.31 (89) | 0/4 | — |
| SPY | -0.04 (87) | -0.18 (87) | -0.37 (87) | 0/4 | — |
| TSLA | -0.04 (86) | -0.07 (86) | -0.10 (86) | 0/4 | — |

### STRAT-004 MACD histogram turn below zero
*5m · both · stock, crypto* — deceleration of downside momentum before the price trend turns

Rules: entry long: `macd(close,12,26,9).hist < 0 and macd(close,12,26,9).hist > macd(close,12,26,9).hist[1] and macd(close,12,26,9).hist[1] <= macd(close,12,26,9).hist[2] and close > ema(close,200)` · entry short: `macd(close,12,26,9).hist > 0 and macd(close,12,26,9).hist < macd(close,12,26,9).hist[1] and macd(close,12,26,9).hist[1] >= macd(close,12,26,9).hist[2] and close < ema(close,200)` · stop: 1.5x ATR(14) · target: 1.5R · time stop: 24 bars · max 2 trades/day

| Crypto | gross | low | retail | folds | test |
|---|---|---|---|---|---|
| BTC-USD | -0.18 (217) | -1.53 (217) | -9.00 (217) | 0/4 | — |
| ETH-USD | -0.06 (219) | -1.01 (219) | -6.68 (219) | 0/4 | — |
| SOL-USD | -0.04 (215) | -1.35 (217) | -5.86 (217) | 0/4 | — |

| Stock | gross | net | 2x slip | folds | test |
|---|---|---|---|---|---|
| AAPL | -0.16 (111) | -0.24 (111) | -0.33 (111) | 1/4 | — |
| NVDA | -0.01 (113) | -0.07 (113) | -0.14 (114) | 2/4 | — |
| QQQ | +0.17 (111) | -0.07 (111) | -0.19 (112) | 1/4 | — |
| SPY | +0.13 (111) | -0.02 (111) | -0.24 (112) | 3/4 | — |
| TSLA | -0.04 (109) | -0.09 (110) | -0.13 (110) | 2/4 | — |

### STRAT-005 ADX trend-strength breakout
*5m · both · stock, crypto* — onset of a trend measured by rising directional strength

Rules: entry long: `cross_above(adx(14).adx, 20) and adx(14).plus_di > adx(14).minus_di` · entry short: `cross_above(adx(14).adx, 20) and adx(14).minus_di > adx(14).plus_di` · stop: 2.0x ATR(14) · trail: 3.0x ATR after +1.0R · max 2 trades/day

| Crypto | gross | low | retail | folds | test |
|---|---|---|---|---|---|
| BTC-USD | -0.07 (207) | -1.25 (207) | -8.41 (207) | 0/4 | — |
| ETH-USD | +0.12 (202) | -0.76 (202) | -5.85 (202) | 0/4 | — |
| SOL-USD | +0.26 (209) | -1.01 (210) | -4.85 (210) | 0/4 | — |

| Stock | gross | net | 2x slip | folds | test |
|---|---|---|---|---|---|
| AAPL | +0.06 (57) | -0.00 (57) | -0.07 (57) | 2/4 | -0.07 (12) |
| NVDA | +0.07 (54) | +0.01 (54) | -0.05 (54) | 3/4 | — |
| QQQ | -0.39 (59) | -0.51 (59) | -0.59 (59) | 0/4 | — |
| SPY | -0.12 (56) | -0.33 (58) | -0.49 (58) | 1/4 | — |
| TSLA | +0.01 (56) | -0.07 (57) | -0.10 (57) | 1/4 | — |

### STRAT-006 Directional-movement crossover (Wilder DMI)
*5m · both · stock, crypto* — +DI/-DI crossover marks a shift in which side is making new extremes

Rules: entry long: `cross_above(adx(14).plus_di, adx(14).minus_di) and adx(14).adx > 20` · entry short: `cross_above(adx(14).minus_di, adx(14).plus_di) and adx(14).adx > 20` · stop: 2.0x ATR(14) · exit long: `cross_above(adx(14).minus_di, adx(14).plus_di)` · exit short: `cross_above(adx(14).plus_di, adx(14).minus_di)` · max 2 trades/day

| Crypto | gross | low | retail | folds | test |
|---|---|---|---|---|---|
| BTC-USD | -0.10 (237) | -1.14 (237) | -7.70 (237) | 0/4 | — |
| ETH-USD | -0.00 (238) | -0.73 (238) | -5.33 (238) | 0/4 | — |
| SOL-USD | +0.01 (237) | -0.96 (238) | -4.57 (238) | 0/4 | — |

| Stock | gross | net | 2x slip | folds | test |
|---|---|---|---|---|---|
| AAPL | +0.15 (68) | +0.10 (68) | +0.05 (68) | 1/4 | -0.14 (15) |
| NVDA | +0.14 (81) | +0.10 (81) | +0.07 (81) | 2/4 | -0.27 (17) |
| QQQ | +0.10 (74) | +0.01 (74) | -0.06 (74) | 3/4 | — |
| SPY | +0.06 (72) | -0.05 (72) | -0.17 (72) | 1/4 | -0.34 (13) |
| TSLA | -0.06 (62) | -0.09 (62) | -0.12 (62) | 1/4 | — |

### STRAT-007 Supertrend direction flip
*5m · both · stock, crypto* — volatility-scaled trailing band flip marks trend change

Rules: entry long: `supertrend(10,3).dir > 0 and supertrend(10,3).dir[1] < 0` · entry short: `supertrend(10,3).dir < 0 and supertrend(10,3).dir[1] > 0` · stop: level long `supertrend(10,3).line`, short `supertrend(10,3).line` · trail: level long `supertrend(10,3).line`, short `supertrend(10,3).line` · max 2 trades/day

| Crypto | gross | low | retail | folds | test |
|---|---|---|---|---|---|
| BTC-USD | +0.08 (241) | -0.57 (241) | -4.46 (241) | 0/4 | — |
| ETH-USD | +0.07 (238) | -0.39 (238) | -3.18 (238) | 0/4 | — |
| SOL-USD | +0.21 (241) | -0.42 (241) | -2.33 (241) | 0/4 | — |

| Stock | gross | net | 2x slip | folds | test |
|---|---|---|---|---|---|
| AAPL | +0.15 (77) | +0.11 (77) | +0.06 (77) | 3/4 | +0.18 (14) |
| NVDA | +0.06 (80) | +0.03 (80) | +0.00 (80) | 1/4 | -0.33 (16) |
| QQQ | -0.12 (81) | -0.18 (81) | -0.23 (81) | 1/4 | — |
| SPY | +0.01 (75) | -0.09 (75) | -0.18 (75) | 1/4 | — |
| TSLA | -0.20 (73) | -0.22 (73) | -0.24 (73) | 0/4 | — |

### STRAT-008 Parabolic SAR reversal
*5m · both · stock, crypto* — accelerating trailing stop reversal

Rules: entry long: `psar(0.02,0.2).dir > 0 and psar(0.02,0.2).dir[1] < 0` · entry short: `psar(0.02,0.2).dir < 0 and psar(0.02,0.2).dir[1] > 0` · stop: level long `psar(0.02,0.2).value`, short `psar(0.02,0.2).value` · trail: level long `psar(0.02,0.2).value`, short `psar(0.02,0.2).value` · max 2 trades/day

| Crypto | gross | low | retail | folds | test |
|---|---|---|---|---|---|
| BTC-USD | -0.08 (244) | -1.07 (244) | -7.14 (244) | 0/4 | — |
| ETH-USD | +0.10 (244) | -0.73 (244) | -5.59 (244) | 0/4 | — |
| SOL-USD | -0.09 (244) | -1.04 (244) | -4.11 (244) | 0/4 | — |

| Stock | gross | net | 2x slip | folds | test |
|---|---|---|---|---|---|
| AAPL | +0.12 (118) | +0.05 (118) | -0.02 (118) | 2/4 | -0.09 (24) |
| NVDA | +0.12 (119) | +0.07 (119) | +0.01 (119) | 2/4 | -0.18 (25) |
| QQQ | -0.00 (118) | -0.14 (118) | -0.23 (118) | 2/4 | — |
| SPY | -0.08 (119) | -0.26 (119) | -0.40 (119) | 1/4 | — |
| TSLA | +0.01 (120) | -0.05 (120) | -0.11 (120) | 0/4 | — |

### STRAT-009 Ichimoku Tenkan/Kijun cross above the cloud
*5m · both · stock, crypto* — short/medium midpoint crossover confirmed by cloud position

Rules: entry long: `cross_above(ichimoku(9,26,52).conv, ichimoku(9,26,52).base) and close > max(ichimoku(9,26,52).span_a, ichimoku(9,26,52).span_b) and close > ichimoku(9,26,52).lag_close` · entry short: `cross_below(ichimoku(9,26,52).conv, ichimoku(9,26,52).base) and close < min(ichimoku(9,26,52).span_a, ichimoku(9,26,52).span_b) and close < ichimoku(9,26,52).lag_close` · stop: level long `ichimoku(9,26,52).base`, short `ichimoku(9,26,52).base` + 0.25 ATR buffer · target: 2.0R · max 2 trades/day

| Crypto | gross | low | retail | folds | test |
|---|---|---|---|---|---|
| BTC-USD | +0.08 (195) | -1.28 (195) | -9.00 (195) | 0/4 | — |
| ETH-USD | +0.13 (192) | -1.38 (193) | -9.00 (193) | 0/4 | — |
| SOL-USD | +0.06 (195) | -1.19 (193) | -5.17 (193) | 0/4 | — |

| Stock | gross | net | 2x slip | folds | test |
|---|---|---|---|---|---|
| AAPL | -0.12 (59) | -0.18 (59) | -0.23 (59) | 1/4 | — |
| NVDA | -0.14 (61) | -0.18 (61) | -0.22 (61) | 2/4 | — |
| QQQ | -0.05 (63) | -0.26 (64) | -0.42 (63) | 1/4 | — |
| SPY | -0.02 (53) | -0.44 (56) | -0.44 (56) | 1/4 | — |
| TSLA | -0.13 (61) | -0.18 (61) | -0.48 (61) | 2/4 | — |

### STRAT-010 Ichimoku cloud breakout
*5m · both · stock, crypto* — price leaving the equilibrium (cloud) zone

Rules: entry long: `cross_above(close, max(ichimoku(9,26,52).span_a, ichimoku(9,26,52).span_b))` · entry short: `cross_below(close, min(ichimoku(9,26,52).span_a, ichimoku(9,26,52).span_b))` · stop: 2.0x ATR(14) · target: 2.0R · max 2 trades/day

| Crypto | gross | low | retail | folds | test |
|---|---|---|---|---|---|
| BTC-USD | -0.11 (243) | -1.13 (243) | -7.19 (243) | 0/4 | — |
| ETH-USD | -0.11 (242) | -0.85 (242) | -5.37 (242) | 0/4 | — |
| SOL-USD | -0.18 (243) | -1.34 (243) | -4.95 (243) | 0/4 | — |

| Stock | gross | net | 2x slip | folds | test |
|---|---|---|---|---|---|
| AAPL | -0.19 (79) | -0.24 (79) | -0.31 (80) | 0/4 | — |
| NVDA | -0.03 (84) | -0.07 (84) | -0.10 (85) | 1/4 | — |
| QQQ | -0.04 (76) | -0.17 (77) | -0.22 (78) | 2/4 | — |
| SPY | +0.12 (76) | -0.04 (78) | -0.23 (78) | 1/4 | — |
| TSLA | -0.01 (78) | -0.03 (78) | -0.08 (79) | 3/4 | — |

### STRAT-011 Donchian channel breakout (intraday Turtle)
*5m · both · stock, crypto* — new N-bar extremes precede continuation (trading-range break)

Rules: entry long: `close > donchian(20).upper[1]` · entry short: `close < donchian(20).lower[1]` · stop: 2.0x ATR(20) · exit long: `close < donchian(10).lower[1]` · exit short: `close > donchian(10).upper[1]` · max 2 trades/day

| Crypto | gross | low | retail | folds | test |
|---|---|---|---|---|---|
| BTC-USD | -0.15 (242) | -1.25 (242) | -8.12 (242) | 0/4 | — |
| ETH-USD | -0.09 (243) | -0.89 (243) | -5.82 (243) | 0/4 | — |
| SOL-USD | +0.06 (243) | -1.10 (243) | -4.92 (243) | 0/4 | — |

| Stock | gross | net | 2x slip | folds | test |
|---|---|---|---|---|---|
| AAPL | +0.02 (118) | -0.03 (118) | -0.08 (118) | 1/4 | — |
| NVDA | +0.12 (113) | +0.08 (113) | +0.04 (113) | 2/4 | — |
| QQQ | -0.12 (114) | -0.21 (114) | -0.31 (114) | 1/4 | — |
| SPY | +0.14 (113) | -0.01 (113) | -0.14 (113) | 3/4 | — |
| TSLA | +0.03 (113) | +0.00 (113) | -0.03 (113) | 3/4 | -0.61 (23) |

### STRAT-012 Regression-slope trend with R-squared filter
*5m · both · stock, crypto* — persistent drift measured by a least-squares slope with a goodness-of-fit filter

Rules: entry long: `linreg(close,50).slope > 0 and linreg(close,50).r2 > 0.6 and linreg(close,50).r2[1] <= 0.6` · entry short: `linreg(close,50).slope < 0 and linreg(close,50).r2 > 0.6 and linreg(close,50).r2[1] <= 0.6` · stop: 2.0x ATR(14) · exit long: `linreg(close,50).slope < 0` · exit short: `linreg(close,50).slope > 0` · max 2 trades/day

| Crypto | gross | low | retail | folds | test |
|---|---|---|---|---|---|
| BTC-USD | +0.04 (201) | -1.04 (201) | -7.74 (201) | 0/4 | — |
| ETH-USD | -0.07 (189) | -0.80 (189) | -5.33 (189) | 0/4 | — |
| SOL-USD | +0.19 (187) | -1.06 (191) | -4.77 (191) | 0/4 | — |

| Stock | gross | net | 2x slip | folds | test |
|---|---|---|---|---|---|
| AAPL | -0.22 (63) | -0.29 (63) | -0.36 (63) | 1/4 | — |
| NVDA | -0.16 (66) | -0.18 (66) | -0.24 (66) | 1/4 | — |
| QQQ | -0.15 (66) | -0.25 (66) | -0.33 (66) | 1/4 | — |
| SPY | +0.02 (61) | -0.11 (61) | -0.26 (61) | 2/4 | — |
| TSLA | +0.20 (56) | +0.17 (56) | +0.13 (56) | 3/4 | -0.41 (10) |

### STRAT-013 Kaufman adaptive-average cross in efficient markets
*5m · both · stock, crypto* — adaptive smoothing: fast when price moves efficiently, slow in noise

Rules: entry long: `cross_above(close, kama(close,10,2,30)) and er(close,10) > 0.3` · entry short: `cross_below(close, kama(close,10,2,30)) and er(close,10) > 0.3` · stop: 2.0x ATR(14) · exit long: `cross_below(close, kama(close,10,2,30))` · exit short: `cross_above(close, kama(close,10,2,30))` · max 2 trades/day

| Crypto | gross | low | retail | folds | test |
|---|---|---|---|---|---|
| BTC-USD | +0.14 (230) | -0.97 (230) | -7.98 (230) | 0/4 | — |
| ETH-USD | +0.01 (236) | -0.75 (236) | -5.55 (236) | 0/4 | — |
| SOL-USD | -0.07 (228) | -1.02 (228) | -4.65 (228) | 0/4 | — |

| Stock | gross | net | 2x slip | folds | test |
|---|---|---|---|---|---|
| AAPL | +0.03 (81) | -0.02 (81) | -0.07 (81) | 2/4 | — |
| NVDA | -0.17 (88) | -0.21 (88) | -0.25 (88) | 1/4 | — |
| QQQ | +0.14 (87) | +0.05 (87) | -0.03 (87) | 2/4 | +0.09 (20) |
| SPY | -0.12 (85) | -0.26 (85) | -0.39 (85) | 1/4 | — |
| TSLA | +0.01 (82) | -0.02 (82) | -0.05 (82) | 2/4 | — |

### STRAT-014 Heikin-Ashi trend run
*5m · both · stock, crypto* — consecutive smoothed candles without counter-trend wicks mark strong one-sided flow

Rules: entry long: `persist(heikin_ashi().close > heikin_ashi().open and heikin_ashi().low >= heikin_ashi().open, 3)` · entry short: `persist(heikin_ashi().close < heikin_ashi().open and heikin_ashi().high <= heikin_ashi().open, 3)` · stop: 1.5x ATR(14) · exit long: `heikin_ashi().close < heikin_ashi().open` · exit short: `heikin_ashi().close > heikin_ashi().open` · max 2 trades/day

| Crypto | gross | low | retail | folds | test |
|---|---|---|---|---|---|
| BTC-USD | -0.06 (244) | -1.45 (244) | -9.00 (244) | 0/4 | — |
| ETH-USD | -0.07 (243) | -1.06 (243) | -7.36 (243) | 0/4 | — |
| SOL-USD | -0.00 (242) | -1.36 (242) | -6.19 (242) | 0/4 | — |

| Stock | gross | net | 2x slip | folds | test |
|---|---|---|---|---|---|
| AAPL | +0.11 (119) | +0.04 (119) | -0.02 (119) | 2/4 | — |
| NVDA | +0.06 (119) | +0.01 (119) | -0.03 (119) | 2/4 | — |
| QQQ | +0.08 (119) | -0.03 (119) | -0.12 (119) | 2/4 | — |
| SPY | +0.23 (119) | +0.03 (119) | -0.13 (119) | 1/4 | — |
| TSLA | -0.00 (120) | -0.04 (120) | -0.08 (120) | 1/4 | — |

### STRAT-015 Aroon trend emergence
*5m · both · stock, crypto* — recency of the latest high vs latest low

Rules: entry long: `cross_above(aroon(25).up, aroon(25).down) and aroon(25).up > 70` · entry short: `cross_above(aroon(25).down, aroon(25).up) and aroon(25).down > 70` · stop: 2.0x ATR(14) · target: 2.0R · max 2 trades/day

| Crypto | gross | low | retail | folds | test |
|---|---|---|---|---|---|
| BTC-USD | -0.05 (239) | -1.17 (239) | -7.59 (239) | 0/4 | — |
| ETH-USD | -0.13 (242) | -0.90 (242) | -5.41 (242) | 0/4 | — |
| SOL-USD | -0.13 (243) | -1.30 (243) | -4.94 (243) | 0/4 | — |

| Stock | gross | net | 2x slip | folds | test |
|---|---|---|---|---|---|
| AAPL | +0.15 (89) | +0.10 (89) | +0.06 (89) | 2/4 | — |
| NVDA | -0.01 (91) | -0.04 (91) | -0.07 (91) | 3/4 | -0.45 (17) |
| QQQ | -0.20 (94) | -0.31 (94) | -0.47 (95) | 1/4 | — |
| SPY | +0.04 (89) | -0.07 (91) | -0.18 (89) | 1/4 | — |
| TSLA | -0.18 (88) | -0.23 (88) | -0.27 (89) | 1/4 | — |

### STRAT-016 Multi-horizon momentum alignment breakout
*5m · both · crypto* — agreement of momentum across 15m/1h/4h before a local breakout

Rules: entry long: `tf("15m", roc(close,8)) > 0 and tf("1h", roc(close,6)) > 0 and tf("4h", roc(close,6)) > 0 and close > highest(high,12)[1]` · entry short: `tf("15m", roc(close,8)) < 0 and tf("1h", roc(close,6)) < 0 and tf("4h", roc(close,6)) < 0 and close < lowest(low,12)[1]` · stop: 2.0x ATR(14) · target: 2.0R · max 2 trades/day

| Crypto | gross | low | retail | folds | test |
|---|---|---|---|---|---|
| BTC-USDT | -0.19 (43) | -1.55 (43) | -9.00 (43) | 0/4 | — |

### STRAT-017 Previous-day return sign (intraday time-series momentum)
*1h · both · crypto* — persistence of the sign of recent returns

Rules: entry long: `bar_in_session() == 0 and pct(close,24) > 0` · entry short: `bar_in_session() == 0 and pct(close,24) < 0` · stop: 2.5x ATR(24) · max 1 trades/day

| Crypto | gross | low | retail | folds | test |
|---|---|---|---|---|---|
| BTC-USD | +0.26 (61) | +0.08 (61) | -1.05 (61) | 0/4 | — |
| ETH-USD | +0.28 (63) | +0.14 (63) | -0.69 (63) | 0/4 | — |
| SOL-USD | +0.24 (62) | +0.00 (62) | -0.72 (62) | 0/4 | — |

### STRAT-159 Volatility-normalized time-series momentum
*15m · both · stock, crypto* — returns scaled by their own volatility persist over short horizons

Rules: entry long: `cross_above(log(close/close[48]) / (realized_vol(48).per_bar * sqrt(48)), 1)` · entry short: `cross_below(log(close/close[48]) / (realized_vol(48).per_bar * sqrt(48)), -1)` · stop: 3.0x ATR(14) · exit long: `close < close[48]` · exit short: `close > close[48]` · time stop: 96 bars · max 2 trades/day

| Crypto | gross | low | retail | folds | test |
|---|---|---|---|---|---|
| BTC-USD | +0.20 (96) | -0.19 (96) | -2.64 (96) | 0/4 | — |
| ETH-USD | +0.37 (98) | +0.08 (98) | -1.68 (98) | 0/4 | — |
| SOL-USD | +0.39 (92) | -0.02 (95) | -1.36 (95) | 0/4 | — |

| Stock | gross | net | 2x slip | folds | test |
|---|---|---|---|---|---|
| AAPL | -0.31 (39) | -0.33 (39) | -0.35 (39) | 0/4 | — |
| NVDA | +0.07 (34) | +0.05 (34) | +0.04 (34) | 3/4 | — |
| QQQ | -0.20 (27) | -0.23 (27) | -0.26 (27) | 0/4 | — |
| SPY | +0.05 (30) | -0.00 (30) | -0.05 (30) | 2/4 | — |
| TSLA | +0.09 (29) | +0.08 (29) | +0.07 (29) | 3/4 | — |

## volatility

### STRAT-071 Bollinger squeeze breakout
*5m · both · stock, crypto* — volatility compression precedes expansion

Rules: entry long: `within(bb(close,20,2).width <= 1.1*lowest(bb(close,20,2).width, 120), 6) and cross_above(close, bb(close,20,2).upper)` · entry short: `within(bb(close,20,2).width <= 1.1*lowest(bb(close,20,2).width, 120), 6) and cross_below(close, bb(close,20,2).lower)` · stop: level long `bb(close,20,2).mid`, short `bb(close,20,2).mid` · target: 2.0R · max 2 trades/day

| Crypto | gross | low | retail | folds | test |
|---|---|---|---|---|---|
| BTC-USD | -0.07 (145) | -1.49 (145) | -9.00 (145) | 0/4 | — |
| ETH-USD | -0.07 (146) | -1.17 (145) | -7.57 (145) | 0/4 | — |
| SOL-USD | +0.01 (144) | -1.21 (142) | -5.26 (142) | 0/4 | — |

| Stock | gross | net | 2x slip | folds | test |
|---|---|---|---|---|---|
| AAPL | -0.04 (37) | -0.12 (37) | -0.31 (37) | 1/4 | — |
| NVDA | +0.00 (42) | -0.08 (42) | -0.14 (42) | 2/4 | — |
| QQQ | -0.11 (31) | -0.23 (31) | -0.36 (31) | 1/4 | — |
| SPY | -0.10 (36) | -0.28 (36) | -0.40 (36) | 1/4 | — |
| TSLA | +0.26 (38) | +0.22 (38) | +0.19 (38) | 3/4 | — |

### STRAT-072 NR7 breakout bracket (Crabel)
*5m · both · stock, crypto* — the narrowest bar of seven precedes range expansion

Rules: entry long: `nr(7) == 1` · entry short: `nr(7) == 1` · order: oco long `high` short `low`, expires after 3 bars · stop: 1.0x ATR(14) · target: 2.0R · max 2 trades/day

| Crypto | gross | low | retail | folds | test |
|---|---|---|---|---|---|
| BTC-USD | +0.14 (244) | -1.96 (244) | -9.00 (244) | 0/4 | — |
| ETH-USD | +0.01 (244) | -1.47 (244) | -9.00 (244) | 0/4 | — |
| SOL-USD | +0.03 (244) | -2.55 (244) | -9.00 (244) | 0/4 | — |

| Stock | gross | net | 2x slip | folds | test |
|---|---|---|---|---|---|
| AAPL | -0.03 (119) | -0.19 (120) | -0.23 (120) | 0/4 | — |
| NVDA | -0.03 (117) | -0.10 (117) | -0.17 (118) | 0/4 | — |
| QQQ | +0.13 (119) | -0.08 (119) | -0.40 (119) | 1/4 | — |
| SPY | -0.17 (119) | -0.47 (119) | -0.94 (120) | 0/4 | — |
| TSLA | +0.02 (116) | -0.04 (116) | -0.11 (116) | 2/4 | — |

### STRAT-073 Keltner channel breakout
*5m · both · stock, crypto* — closes beyond an ATR band signal directional expansion

Rules: entry long: `cross_above(close, kc(20,2,10).upper)` · entry short: `cross_below(close, kc(20,2,10).lower)` · stop: level long `kc(20,2,10).mid`, short `kc(20,2,10).mid` · exit long: `close < kc(20,2,10).mid` · exit short: `close > kc(20,2,10).mid` · max 2 trades/day

| Crypto | gross | low | retail | folds | test |
|---|---|---|---|---|---|
| BTC-USD | +0.03 (237) | -0.88 (237) | -6.59 (237) | 0/4 | — |
| ETH-USD | -0.05 (228) | -0.68 (228) | -4.67 (228) | 0/4 | — |
| SOL-USD | +0.08 (227) | -0.66 (227) | -3.35 (227) | 0/4 | — |

| Stock | gross | net | 2x slip | folds | test |
|---|---|---|---|---|---|
| AAPL | +0.05 (91) | +0.01 (91) | -0.04 (91) | 1/4 | -0.28 (16) |
| NVDA | +0.09 (89) | +0.06 (89) | +0.03 (89) | 3/4 | -0.09 (17) |
| QQQ | -0.06 (92) | -0.12 (92) | -0.17 (92) | 0/4 | — |
| SPY | +0.04 (93) | -0.06 (93) | -0.14 (93) | 2/4 | — |
| TSLA | -0.11 (85) | -0.14 (85) | -0.16 (85) | 1/4 | — |

### STRAT-074 Range-expansion bar continuation
*5m · both · stock, crypto* — an unusually wide bar closing at its extreme shows urgent one-sided demand

Rules: entry long: `high - low > 2*atr(20)[1] and close > high - 0.2*(high - low) and rvol(20) > 1.5` · entry short: `high - low > 2*atr(20)[1] and close < low + 0.2*(high - low) and rvol(20) > 1.5` · stop: level long `(high + low)/2`, short `(high + low)/2` · target: 1.5R · time stop: 6 bars · max 2 trades/day

| Crypto | gross | low | retail | folds | test |
|---|---|---|---|---|---|
| BTC-USD | -0.01 (211) | -1.68 (211) | -9.00 (211) | 0/4 | — |
| ETH-USD | -0.09 (209) | -1.37 (209) | -8.98 (209) | 0/4 | — |
| SOL-USD | -0.04 (199) | -1.33 (199) | -5.81 (199) | 0/4 | — |

| Stock | gross | net | 2x slip | folds | test |
|---|---|---|---|---|---|
| AAPL | +0.20 (49) | +0.14 (49) | +0.01 (49) | 2/4 | — |
| NVDA | +0.05 (57) | +0.01 (55) | -0.27 (55) | 2/4 | -0.58 (10) |
| QQQ | -0.19 (55) | -0.32 (54) | -0.43 (54) | 0/4 | — |
| SPY | -0.20 (41) | -0.39 (41) | -0.66 (41) | 1/4 | — |
| TSLA | +0.04 (68) | +0.01 (68) | -0.02 (68) | 2/4 | — |

### STRAT-158 Range-boundary breakout retest
*5m · both · stock, crypto* — a broken range boundary is defended on the first retest

Rules: entry long: `since(cross_above(close, highest(high,48)[1])) >= 2 and since(cross_above(close, highest(high,48)[1])) <= 12 and low <= valuewhen(cross_above(close, highest(high,48)[1]), highest(high,48)[1]) + 0.1*atr(14) and close > valuewhen(cross_above(close, highest(high,48)[1]), highest(high,48)[1]) and close > open` · entry short: `since(cross_below(close, lowest(low,48)[1])) >= 2 and since(cross_below(close, lowest(low,48)[1])) <= 12 and high >= valuewhen(cross_below(close, lowest(low,48)[1]), lowest(low,48)[1]) - 0.1*atr(14) and close < valuewhen(cross_below(close, lowest(low,48)[1]), lowest(low,48)[1]) and close < open` · stop: level long `valuewhen(cross_above(close, highest(high,48)[1]), highest(high,48)[1]) - 0.5*atr(14)`, short `valuewhen(cross_below(close, lowest(low,48)[1]), lowest(low,48)[1]) + 0.5*atr(14)` · target: 2.0R · max 2 trades/day

| Crypto | gross | low | retail | folds | test |
|---|---|---|---|---|---|
| BTC-USD | -0.18 (190) | -2.15 (187) | -9.00 (187) | 0/4 | — |
| ETH-USD | +0.03 (180) | -1.58 (180) | -9.00 (180) | 0/4 | — |
| SOL-USD | -0.20 (198) | -1.63 (196) | -6.55 (196) | 0/4 | — |

| Stock | gross | net | 2x slip | folds | test |
|---|---|---|---|---|---|
| AAPL | -0.18 (68) | -0.28 (67) | -0.40 (67) | 1/4 | — |
| NVDA | +0.01 (61) | -0.10 (61) | -0.15 (61) | 2/4 | — |
| QQQ | -0.08 (59) | -0.29 (59) | -0.38 (59) | 1/4 | — |
| SPY | +0.03 (71) | -0.14 (71) | -0.40 (71) | 1/4 | — |
| TSLA | +0.07 (70) | +0.03 (70) | -0.11 (69) | 2/4 | -0.85 (14) |

## volume

### STRAT-089 Relative-volume new session high
*5m · both · stock, crypto* — unusual same-time-of-day volume marks news/attention flow

Rules: entry long: `rvol_tod(10) > 3 and cross_above(close, session().high[1])` · entry short: `rvol_tod(10) > 3 and cross_below(close, session().low[1])` · stop: 1.5x ATR(14) · trail: 2.5x ATR after +1.0R · max 2 trades/day

| Crypto | gross | low | retail | folds | test |
|---|---|---|---|---|---|
| BTC-USD | +0.17 (78) | -0.77 (78) | -6.65 (78) | 0/4 | — |
| ETH-USD | -0.31 (95) | -1.04 (95) | -5.59 (95) | 0/4 | — |
| SOL-USD | -0.05 (94) | -1.26 (96) | -5.32 (96) | 0/4 | — |

| Stock | gross | net | 2x slip | folds | test |
|---|---|---|---|---|---|
| AAPL | -0.66 (9) | -0.71 (9) | -0.76 (9) | 0/4 | — |
| NVDA | +1.36 (3) | +1.32 (3) | +1.28 (3) | 1/4 | — |
| QQQ | -0.01 (7) | -0.14 (7) | -0.47 (7) | 1/4 | — |
| SPY | +0.23 (10) | -0.02 (10) | -0.51 (10) | 1/4 | — |
| TSLA | +0.62 (5) | +0.10 (6) | +0.05 (6) | 1/4 | — |

### STRAT-090 Volume-climax reversal
*5m · both · stock, crypto* — capitulation volume with a rejection wick exhausts sellers

Rules: entry long: `rvol(20) > 4 and low <= session().low and min(open, close) - low > 0.6*(high - low)` · entry short: `rvol(20) > 4 and high >= session().high and high - max(open, close) > 0.6*(high - low)` · stop: level long `low`, short `high` + 0.1 ATR buffer · target: level long `vwap()`, short `vwap()` · max 2 trades/day

| Crypto | gross | low | retail | folds | test |
|---|---|---|---|---|---|
| BTC-USD | +0.24 (23) | -0.57 (23) | -5.24 (23) | 0/4 | — |
| ETH-USD | +0.42 (28) | -0.32 (28) | -4.55 (28) | 0/4 | — |
| SOL-USD | +0.10 (32) | -0.79 (32) | -3.79 (32) | 0/4 | — |

| Stock | gross | net | 2x slip | folds | test |
|---|---|---|---|---|---|
| AAPL | +0.18 (14) | +0.14 (14) | +0.10 (14) | 2/4 | — |
| NVDA | -0.26 (10) | -0.30 (10) | -0.33 (10) | 1/4 | — |
| QQQ | +0.00 (9) | -0.12 (9) | -0.22 (9) | 1/4 | — |
| SPY | +1.07 (3) | +0.89 (3) | +0.72 (3) | 1/4 | — |
| TSLA | -0.72 (12) | -0.74 (12) | -0.76 (12) | 0/4 | — |

### STRAT-091 On-balance-volume divergence
*5m · both · stock, crypto* — volume flow leads price (Granville)

Rules: entry long: `low <= lowest(low,20) and obv() > lowest(obv(),20)[1] and close > open` · entry short: `high >= highest(high,20) and obv() < highest(obv(),20)[1] and close < open` · stop: 1.5x ATR(14) · target: 2.0R · max 2 trades/day

| Crypto | gross | low | retail | folds | test |
|---|---|---|---|---|---|
| BTC-USD | -0.01 (243) | -1.34 (243) | -9.00 (243) | 0/4 | — |
| ETH-USD | -0.05 (241) | -1.07 (241) | -6.98 (241) | 0/4 | — |
| SOL-USD | -0.05 (243) | -1.44 (243) | -6.00 (243) | 0/4 | — |

| Stock | gross | net | 2x slip | folds | test |
|---|---|---|---|---|---|
| AAPL | -0.01 (102) | -0.09 (101) | -0.17 (102) | 2/4 | — |
| NVDA | -0.05 (110) | -0.09 (111) | -0.17 (111) | 2/4 | — |
| QQQ | +0.14 (105) | +0.09 (104) | +0.02 (103) | 1/4 | +0.35 (16) |
| SPY | -0.04 (110) | -0.17 (110) | -0.39 (109) | 2/4 | — |
| TSLA | +0.03 (108) | +0.01 (108) | -0.08 (109) | 2/4 | — |

### STRAT-092 Money Flow Index extreme reversal
*5m · both · stock, crypto* — volume-weighted oversold readings revert

Rules: entry long: `cross_above(mfi(14), 20)` · entry short: `cross_below(mfi(14), 80)` · stop: 1.5x ATR(14) · target: 1.5R · max 2 trades/day

| Crypto | gross | low | retail | folds | test |
|---|---|---|---|---|---|
| BTC-USD | +0.03 (228) | -1.29 (228) | -9.00 (228) | 0/4 | — |
| ETH-USD | -0.15 (231) | -1.10 (231) | -6.75 (231) | 0/4 | — |
| SOL-USD | +0.12 (232) | -1.22 (233) | -5.59 (233) | 0/4 | — |

| Stock | gross | net | 2x slip | folds | test |
|---|---|---|---|---|---|
| AAPL | +0.18 (85) | +0.06 (85) | +0.03 (85) | 1/4 | — |
| NVDA | +0.02 (80) | -0.01 (80) | -0.10 (79) | 1/4 | — |
| QQQ | -0.06 (82) | -0.15 (82) | -0.31 (82) | 1/4 | — |
| SPY | -0.31 (87) | -0.46 (87) | -0.63 (87) | 0/4 | — |
| TSLA | +0.18 (70) | +0.13 (70) | +0.02 (71) | 3/4 | — |

### STRAT-093 Chaikin Money Flow trend confirmation
*5m · both · stock, crypto* — closes near bar highs on volume indicate accumulation

Rules: entry long: `cross_above(cmf(20), 0.1) and close > ema(close,50)` · entry short: `cross_below(cmf(20), -0.1) and close < ema(close,50)` · stop: 2.0x ATR(14) · exit long: `cmf(20) < 0` · exit short: `cmf(20) > 0` · max 2 trades/day

| Crypto | gross | low | retail | folds | test |
|---|---|---|---|---|---|
| BTC-USD | -0.15 (239) | -1.26 (240) | -8.17 (240) | 0/4 | — |
| ETH-USD | -0.12 (239) | -0.92 (239) | -5.91 (239) | 0/4 | — |
| SOL-USD | -0.02 (243) | -1.08 (243) | -4.89 (243) | 0/4 | — |

| Stock | gross | net | 2x slip | folds | test |
|---|---|---|---|---|---|
| AAPL | -0.04 (104) | -0.09 (104) | -0.15 (104) | 1/4 | — |
| NVDA | +0.07 (103) | +0.03 (103) | -0.02 (103) | 2/4 | — |
| QQQ | -0.18 (105) | -0.26 (105) | -0.35 (105) | 0/4 | — |
| SPY | -0.18 (101) | -0.32 (101) | -0.45 (101) | 1/4 | — |
| TSLA | -0.18 (109) | -0.21 (109) | -0.26 (109) | 0/4 | — |

### STRAT-094 Force-index pullback (Elder)
*5m · both · stock, crypto* — short-term selling pressure inside an up-trend

Rules: entry long: `force(2) < 0 and ema(close,13) > ema(close,13)[1] and close > ema(close,50)` · entry short: `force(2) > 0 and ema(close,13) < ema(close,13)[1] and close < ema(close,50)` · stop: 1.5x ATR(14) · target: 1.5R · max 2 trades/day

| Crypto | gross | low | retail | folds | test |
|---|---|---|---|---|---|
| BTC-USD | -0.16 (243) | -1.49 (243) | -9.00 (243) | 0/4 | — |
| ETH-USD | -0.04 (244) | -1.03 (244) | -6.72 (244) | 0/4 | — |
| SOL-USD | -0.04 (243) | -1.40 (243) | -5.97 (243) | 0/4 | — |

| Stock | gross | net | 2x slip | folds | test |
|---|---|---|---|---|---|
| AAPL | -0.00 (115) | -0.04 (115) | -0.12 (115) | 3/4 | — |
| NVDA | +0.03 (117) | -0.01 (116) | -0.06 (116) | 2/4 | — |
| QQQ | -0.05 (113) | -0.16 (113) | -0.26 (113) | 1/4 | — |
| SPY | +0.12 (119) | -0.05 (117) | -0.20 (117) | 1/4 | — |
| TSLA | +0.10 (118) | +0.08 (118) | +0.07 (118) | 2/4 | — |

### STRAT-095 Volume dry-up then breakout
*5m · both · stock, crypto* — quiet volume in a tight range precedes a volume-backed breakout

Rules: entry long: `mean(volume,5)[1] < 0.6*mean(volume,50)[1] and rvol(20) > 2 and close > highest(high,5)[1]` · entry short: `mean(volume,5)[1] < 0.6*mean(volume,50)[1] and rvol(20) > 2 and close < lowest(low,5)[1]` · stop: level long `lowest(low,5)`, short `highest(high,5)` · target: 2.0R · max 2 trades/day

| Crypto | gross | low | retail | folds | test |
|---|---|---|---|---|---|
| BTC-USD | -0.24 (119) | -1.21 (119) | -6.96 (119) | 0/4 | — |
| ETH-USD | +0.11 (124) | -0.53 (124) | -4.39 (124) | 0/4 | — |
| SOL-USD | -0.08 (141) | -0.78 (140) | -3.40 (140) | 0/4 | — |

| Stock | gross | net | 2x slip | folds | test |
|---|---|---|---|---|---|
| AAPL | -0.13 (8) | -0.18 (8) | -0.23 (8) | 1/4 | — |
| NVDA | -0.34 (13) | -0.39 (13) | -0.43 (13) | 2/4 | — |
| QQQ | +0.00 (27) | -0.09 (27) | -0.17 (27) | 1/4 | — |
| SPY | +0.67 (13) | +0.56 (13) | +0.28 (13) | 4/4 | — |
| TSLA | -0.00 (8) | -0.04 (8) | -0.08 (8) | 2/4 | — |

### STRAT-096 Elder impulse system turn
*5m · both · stock, crypto* — agreement of trend (EMA13) and momentum (MACD histogram) slopes

Rules: entry long: `ema(close,13) > ema(close,13)[1] and macd(close,12,26,9).hist > macd(close,12,26,9).hist[1] and not (ema(close,13)[1] > ema(close,13)[2] and macd(close,12,26,9).hist[1] > macd(close,12,26,9).hist[2])` · entry short: `ema(close,13) < ema(close,13)[1] and macd(close,12,26,9).hist < macd(close,12,26,9).hist[1] and not (ema(close,13)[1] < ema(close,13)[2] and macd(close,12,26,9).hist[1] < macd(close,12,26,9).hist[2])` · stop: 1.5x ATR(14) · exit long: `ema(close,13) < ema(close,13)[1] and macd(close,12,26,9).hist < macd(close,12,26,9).hist[1]` · exit short: `ema(close,13) > ema(close,13)[1] and macd(close,12,26,9).hist > macd(close,12,26,9).hist[1]` · max 2 trades/day

| Crypto | gross | low | retail | folds | test |
|---|---|---|---|---|---|
| BTC-USD | -0.04 (244) | -1.42 (244) | -9.00 (244) | 0/4 | — |
| ETH-USD | -0.08 (244) | -1.04 (244) | -7.08 (244) | 0/4 | — |
| SOL-USD | +0.07 (244) | -1.33 (244) | -6.21 (244) | 0/4 | — |

| Stock | gross | net | 2x slip | folds | test |
|---|---|---|---|---|---|
| AAPL | +0.12 (120) | +0.04 (120) | -0.02 (120) | 2/4 | -0.28 (24) |
| NVDA | +0.01 (119) | -0.03 (119) | -0.07 (119) | 3/4 | — |
| QQQ | -0.09 (119) | -0.19 (119) | -0.29 (119) | 1/4 | — |
| SPY | +0.07 (120) | -0.10 (120) | -0.33 (120) | 1/4 | — |
| TSLA | +0.09 (120) | +0.05 (120) | +0.01 (120) | 2/4 | — |

## vwap

### STRAT-046 VWAP pullback in a trending session
*5m · both · stock, crypto* — VWAP as the average cost of the day's participants acts as support in trends

Rules: entry long: `persist(close > vwap(), 6)[1] and vwap() > vwap()[6] and low <= vwap() and close > vwap() and close > open` · entry short: `persist(close < vwap(), 6)[1] and vwap() < vwap()[6] and high >= vwap() and close < vwap() and close < open` · stop: level long `vwap()`, short `vwap()` + 0.5 ATR buffer · target: 2.0R · max 2 trades/day

| Crypto | gross | low | retail | folds | test |
|---|---|---|---|---|---|
| BTC-USD | -0.07 (139) | -1.87 (139) | -9.00 (139) | 0/4 | — |
| ETH-USD | -0.06 (125) | -1.42 (125) | -9.00 (125) | 0/4 | — |
| SOL-USD | -0.19 (127) | -1.63 (125) | -6.39 (125) | 0/4 | — |

| Stock | gross | net | 2x slip | folds | test |
|---|---|---|---|---|---|
| AAPL | +0.09 (46) | -0.10 (46) | -0.22 (46) | 1/4 | — |
| NVDA | -0.34 (45) | -0.41 (45) | -0.47 (45) | 0/4 | — |
| QQQ | -0.01 (49) | -0.26 (49) | -0.35 (49) | 2/4 | — |
| SPY | -0.08 (51) | -0.35 (50) | -0.55 (49) | 1/4 | — |
| TSLA | -0.01 (43) | -0.05 (43) | -0.16 (43) | 1/4 | — |

### STRAT-047 VWAP 2-sigma band reversion
*5m · both · stock, crypto* — intraday overextension from the volume-weighted mean reverts

Rules: entry long: `cross_above(close, vwap().lower2)` · entry short: `cross_below(close, vwap().upper2)` · stop: level long `session().low`, short `session().high` + 0.25 ATR buffer · target: level long `vwap()`, short `vwap()` · max 2 trades/day

| Crypto | gross | low | retail | folds | test |
|---|---|---|---|---|---|
| BTC-USD | +0.05 (218) | -1.78 (218) | -9.00 (218) | 0/4 | — |
| ETH-USD | +0.09 (217) | -1.20 (217) | -8.70 (217) | 0/4 | — |
| SOL-USD | +0.12 (216) | -1.32 (216) | -5.76 (216) | 0/4 | — |

| Stock | gross | net | 2x slip | folds | test |
|---|---|---|---|---|---|
| AAPL | +0.17 (94) | +0.09 (94) | -0.00 (94) | 3/4 | — |
| NVDA | -0.07 (100) | -0.13 (100) | -0.19 (99) | 2/4 | — |
| QQQ | -0.15 (107) | -0.28 (106) | -0.40 (106) | 0/4 | — |
| SPY | -0.07 (106) | -0.32 (105) | -0.52 (105) | 0/4 | — |
| TSLA | -0.03 (96) | -0.08 (96) | -0.12 (96) | 2/4 | — |

### STRAT-048 VWAP 1-sigma band breakout with volume
*5m · both · stock, crypto* — acceptance above the upper band with volume signals trend day

Rules: entry long: `cross_above(close, vwap().upper1) and rvol(20) > 1.5 and vwap() > vwap()[6] and minutes_since_open() >= 60` · entry short: `cross_below(close, vwap().lower1) and rvol(20) > 1.5 and vwap() < vwap()[6] and minutes_since_open() >= 60` · stop: level long `vwap()`, short `vwap()` · trail: level long `vwap()`, short `vwap()` · max 1 trades/day

| Crypto | gross | low | retail | folds | test |
|---|---|---|---|---|---|
| BTC-USD | +0.12 (101) | -0.81 (101) | -6.43 (101) | 0/4 | — |
| ETH-USD | +0.57 (102) | -0.17 (102) | -4.57 (102) | 0/4 | — |
| SOL-USD | +0.21 (90) | -0.80 (90) | -4.02 (90) | 0/4 | — |

| Stock | gross | net | 2x slip | folds | test |
|---|---|---|---|---|---|
| AAPL | -0.42 (18) | -0.47 (18) | -0.52 (18) | 1/4 | — |
| NVDA | -0.12 (21) | -0.16 (21) | -0.21 (21) | 0/4 | — |
| QQQ | -0.21 (16) | -0.31 (16) | -0.39 (16) | 0/4 | — |
| SPY | -0.30 (19) | -0.43 (19) | -0.55 (19) | 1/4 | — |
| TSLA | +0.21 (12) | +0.16 (12) | +0.11 (12) | 2/4 | — |

### STRAT-049 VWAP reclaim after a sustained move below
*5m · both · stock, crypto* — shift of control when price regains the day's average cost

Rules: entry long: `persist(close < vwap(), 6)[1] and cross_above(close, vwap())` · entry short: `persist(close > vwap(), 6)[1] and cross_below(close, vwap())` · stop: level long `session().low`, short `session().high` · target: level long `vwap().upper1`, short `vwap().lower1` · max 2 trades/day

| Crypto | gross | low | retail | folds | test |
|---|---|---|---|---|---|
| BTC-USD | +0.03 (213) | -0.80 (212) | -6.26 (212) | 0/4 | — |
| ETH-USD | +0.15 (210) | -0.56 (210) | -4.69 (210) | 0/4 | — |
| SOL-USD | -0.15 (207) | -0.57 (201) | -3.13 (201) | 0/4 | — |

| Stock | gross | net | 2x slip | folds | test |
|---|---|---|---|---|---|
| AAPL | -0.11 (77) | -0.15 (77) | -0.18 (77) | 1/4 | — |
| NVDA | +0.04 (73) | +0.03 (73) | -0.00 (73) | 3/4 | +0.14 (12) |
| QQQ | +0.04 (89) | -0.03 (89) | -0.09 (89) | 2/4 | — |
| SPY | -0.29 (92) | -0.38 (88) | -0.48 (87) | 0/4 | — |
| TSLA | +0.10 (68) | +0.08 (68) | +0.06 (68) | 3/4 | -0.15 (16) |

### STRAT-050 Anchored VWAP from the last swing low
*5m · both · stock, crypto* — the average cost of buyers since the last swing low is defended

Rules: entry long: `low <= avwap(swings(5).low != swings(5).low[1]) and close > avwap(swings(5).low != swings(5).low[1]) and close > open and close > ema(close,50)` · entry short: `high >= avwap(swings(5).high != swings(5).high[1]) and close < avwap(swings(5).high != swings(5).high[1]) and close < open and close < ema(close,50)` · stop: 1.5x ATR(14) · target: 2.0R · max 2 trades/day

| Crypto | gross | low | retail | folds | test |
|---|---|---|---|---|---|
| BTC-USD | -0.15 (244) | -1.49 (244) | -9.00 (244) | 0/4 | — |
| ETH-USD | -0.03 (244) | -1.02 (244) | -6.83 (244) | 0/4 | — |
| SOL-USD | -0.07 (244) | -1.57 (244) | -6.27 (244) | 0/4 | — |

| Stock | gross | net | 2x slip | folds | test |
|---|---|---|---|---|---|
| AAPL | +0.07 (115) | +0.03 (115) | -0.01 (115) | 2/4 | — |
| NVDA | +0.12 (112) | +0.05 (112) | -0.02 (113) | 3/4 | -0.19 (22) |
| QQQ | -0.02 (110) | -0.15 (110) | -0.22 (110) | 1/4 | — |
| SPY | +0.10 (111) | -0.15 (110) | -0.36 (112) | 1/4 | — |
| TSLA | +0.12 (111) | +0.04 (112) | -0.01 (112) | 2/4 | -0.35 (23) |

### STRAT-051 Anchored VWAP from a volume shock
*5m · both · stock, crypto* — a climactic-volume bar marks where a large participant traded; its AVWAP is their break-even

Rules: entry long: `cross_above(close, avwap(rvol(20) > 4))` · entry short: `cross_below(close, avwap(rvol(20) > 4))` · stop: 1.5x ATR(14) · target: 2.0R · max 2 trades/day

| Crypto | gross | low | retail | folds | test |
|---|---|---|---|---|---|
| BTC-USD | -0.05 (244) | -1.40 (244) | -9.00 (244) | 0/4 | — |
| ETH-USD | -0.14 (244) | -1.09 (244) | -6.67 (244) | 0/4 | — |
| SOL-USD | -0.19 (244) | -1.52 (244) | -6.00 (244) | 0/4 | — |

| Stock | gross | net | 2x slip | folds | test |
|---|---|---|---|---|---|
| AAPL | -0.04 (98) | -0.09 (99) | -0.17 (100) | 2/4 | — |
| NVDA | +0.04 (103) | +0.03 (103) | -0.06 (103) | 1/4 | — |
| QQQ | -0.03 (104) | -0.16 (104) | -0.33 (104) | 1/4 | — |
| SPY | +0.08 (96) | -0.16 (98) | -0.31 (100) | 2/4 | — |
| TSLA | -0.02 (100) | -0.07 (100) | -0.13 (100) | 1/4 | — |

## Implemented but not batch-tested

Rules exist but they need data a backtest cannot get (live order flow), so they were only observed on paper.

- **STRAT-125 Order-book imbalance momentum** (order flow, 1m): entry long: `book().imbalance > 0.3 and orderflow().imbalance > 0.2` · entry short: `book().imbalance < -0.3 and orderflow().imbalance < -0.2` · stop: 1.5x ATR(14) · time stop: 3 bars · max 20 trades/day
- **STRAT-126 Aggressor-flow persistence** (order flow, 5m): entry long: `sum(orderflow().delta, 3) / sum(volume, 3) > 0.25` · entry short: `sum(orderflow().delta, 3) / sum(volume, 3) < -0.25` · stop: 1.5x ATR(14) · time stop: 2 bars · max 20 trades/day
- **STRAT-127 Cumulative-delta divergence** (order flow, 5m): entry long: `low <= lowest(low,20) and orderflow().cvd > lowest(orderflow().cvd,20)[1] and close > open` · entry short: `high >= highest(high,20) and orderflow().cvd < highest(orderflow().cvd,20)[1] and close < open` · stop: 1.5x ATR(14) · target: 1.5R · max 2 trades/day
- **STRAT-128 Absorption of aggressive selling** (order flow, 5m): entry long: `orderflow().imbalance < -0.4 and close > high - 0.3*(high - low)` · entry short: `orderflow().imbalance > 0.4 and close < low + 0.3*(high - low)` · stop: level long `low`, short `high` + 0.1 ATR buffer · target: 1.5R · time stop: 6 bars · max 2 trades/day

