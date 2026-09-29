# Pre-registration: knowledge-pack formalizations

Written 2026-09-29 05:51 UTC, before any of these rules was run on market data.

## Design (frozen)

- **Search budget:** one configuration per hypothesis. No parameter was chosen by looking at results; none will be changed after.
- **Data:** the batch evaluation's free datasets. Memecoins: Coinbase 5-minute bars for DOGE, SHIB, PEPE, BONK, WIF, FLOKI (and BTC-USD, SOL-USD as references), resampled to 15 minutes where the rule says so.
- **Protocol:** the library's standard one (VALIDATION_METHODOLOGY.md): chronological 60/20/20 split with a one-day embargo, 4 walk-forward folds, three cost levels, Holm correction across every test run, deflated Sharpe for the best.
- **Rejection criteria:** a rule is rejected if its realistic-cost expectancy on the untouched test segment is not above zero, or if it has fewer than 20 test trades (inconclusive).
- **Known bias:** the six memecoins are exchange-listed survivors, so results overstate what the on-chain launch universe offers.

## Rules

### STRAT-158 Range-boundary breakout retest (pack ST004)

Markets: stock, crypto; timeframe 5m

```
long entry: since(cross_above(close, highest(high,48)[1])) >= 2 and since(cross_above(close, highest(high,48)[1])) <= 12 and low <= valuewhen(cross_above(close, highest(high,48)[1]), highest(high,48)[1]) + 0.1*atr(14) and close > valuewhen(cross_above(close, highest(high,48)[1]), highest(high,48)[1]) and close > open
short entry: since(cross_below(close, lowest(low,48)[1])) >= 2 and since(cross_below(close, lowest(low,48)[1])) <= 12 and high >= valuewhen(cross_below(close, lowest(low,48)[1]), lowest(low,48)[1]) - 0.1*atr(14) and close < valuewhen(cross_below(close, lowest(low,48)[1]), lowest(low,48)[1]) and close < open
stop: type=level, long=valuewhen(cross_above(close, highest(high,48)[1]), highest(high,48)[1]) - 0.5*atr(14), short=valuewhen(cross_below(close, lowest(low,48)[1]), lowest(low,48)[1]) + 0.5*atr(14)
target: type=r, r=2.0
max trades/day: 2; flat before the session end; risk 0.5% per trade
```

### STRAT-159 Volatility-normalized time-series momentum (pack ST009)

Markets: stock, crypto; timeframe 15m

```
long entry: cross_above(log(close/close[48]) / (realized_vol(48).per_bar * sqrt(48)), 1)
short entry: cross_below(log(close/close[48]) / (realized_vol(48).per_bar * sqrt(48)), -1)
stop: type=atr, mult=3.0, n=14
long exit: close < close[48]
short exit: close > close[48]
time stop: 96 bars
max trades/day: 2; flat before the session end; risk 0.5% per trade
```

### STRAT-160 RSI extreme recovery (pack ST023)

Markets: stock, crypto; timeframe 15m

```
long entry: cross_above(rsi(close,14), 30)
short entry: cross_below(rsi(close,14), 70)
stop: type=atr, mult=2.5, n=14
long exit: rsi(close,14) > 50
short exit: rsi(close,14) < 50
time stop: 48 bars
max trades/day: 3; flat before the session end; risk 0.5% per trade
```

### STRAT-161 FOMC post-announcement drift (pack ST045)

Markets: stock; timeframe 5m; instruments SPY, QQQ

```
long entry: event("fomc") == 1 and tod() == 870 and close - valuewhen(tod() == 835, close) > 3*atr(14)
short entry: event("fomc") == 1 and tod() == 870 and close - valuewhen(tod() == 835, close) < -3*atr(14)
stop: type=atr, mult=3.0, n=14
max trades/day: 1; flat before the session end; risk 0.5% per trade
```

### STRAT-162 Liquidity sweep then structure shift (pack ST098)

Markets: stock, crypto; timeframe 5m

```
long entry: cross_above(close, swings(3).high) and within(low < swings(3).low and close > swings(3).low, 12)
short entry: cross_below(close, swings(3).low) and within(high > swings(3).high and close < swings(3).high, 12)
stop: type=level, long=lowest(low,12) - 0.2*atr(14), short=highest(high,12) + 0.2*atr(14)
target: type=r, r=2.0
max trades/day: 2; flat before the session end; risk 0.5% per trade
```

### STRAT-163 Order-block retest (pack ST099)

Markets: stock, crypto; timeframe 5m

```
long entry: since(close - open > 1.5*atr(14) and close > highest(high,10)[1] and close[1] < open[1]) >= 3 and since(close - open > 1.5*atr(14) and close > highest(high,10)[1] and close[1] < open[1]) <= 30 and low <= valuewhen(close - open > 1.5*atr(14) and close > highest(high,10)[1] and close[1] < open[1], high[1]) and close > valuewhen(close - open > 1.5*atr(14) and close > highest(high,10)[1] and close[1] < open[1], high[1]) and close > open
short entry: since(open - close > 1.5*atr(14) and close < lowest(low,10)[1] and close[1] > open[1]) >= 3 and since(open - close > 1.5*atr(14) and close < lowest(low,10)[1] and close[1] > open[1]) <= 30 and high >= valuewhen(open - close > 1.5*atr(14) and close < lowest(low,10)[1] and close[1] > open[1], low[1]) and close < valuewhen(open - close > 1.5*atr(14) and close < lowest(low,10)[1] and close[1] > open[1], low[1]) and close < open
stop: type=level, long=valuewhen(close - open > 1.5*atr(14) and close > highest(high,10)[1] and close[1] < open[1], low[1]) - 0.1*atr(14), short=valuewhen(open - close > 1.5*atr(14) and close < lowest(low,10)[1] and close[1] > open[1], high[1]) + 0.1*atr(14)
target: type=r, r=2.0
max trades/day: 2; flat before the session end; risk 0.5% per trade
```

### STRAT-164 Memecoin breadth-led momentum (pack ST181)

Markets: crypto; timeframe 15m; instruments DOGE-USD, SHIB-USD, PEPE-USD, BONK-USD, WIF-USD, FLOKI-USD

```
long entry: cross_above((iff(sym("DOGE-USD", close > ema(close,20)), 1, 0) + iff(sym("SHIB-USD", close > ema(close,20)), 1, 0) + iff(sym("PEPE-USD", close > ema(close,20)), 1, 0) + iff(sym("BONK-USD", close > ema(close,20)), 1, 0) + iff(sym("WIF-USD", close > ema(close,20)), 1, 0) + iff(sym("FLOKI-USD", close > ema(close,20)), 1, 0)), 3.5) and close > ema(close,20)
stop: type=atr, mult=3.0, n=14
target: type=r, r=2.0
max trades/day: 2; flat before the session end; risk 0.5% per trade
```

### STRAT-165 Memecoin leader pullback (pack ST182)

Markets: crypto; timeframe 15m; instruments DOGE-USD

```
long entry: close > ema(close,50) and low <= ema(close,20) and close > ema(close,20) and close > open and (iff(sym("DOGE-USD", close > ema(close,20)), 1, 0) + iff(sym("SHIB-USD", close > ema(close,20)), 1, 0) + iff(sym("PEPE-USD", close > ema(close,20)), 1, 0) + iff(sym("BONK-USD", close > ema(close,20)), 1, 0) + iff(sym("WIF-USD", close > ema(close,20)), 1, 0) + iff(sym("FLOKI-USD", close > ema(close,20)), 1, 0)) >= 4
stop: type=atr, mult=3.0, n=14
target: type=r, r=2.0
max trades/day: 2; flat before the session end; risk 0.5% per trade
```

### STRAT-166 Memecoin laggard catch-up breakout (pack ST183)

Markets: crypto; timeframe 15m; instruments SHIB-USD, PEPE-USD, BONK-USD, WIF-USD, FLOKI-USD

```
long entry: roc(close,24) < sym("DOGE-USD", roc(close,24)) and cross_above(close, donchian(20).upper[1]) and (iff(sym("DOGE-USD", close > ema(close,20)), 1, 0) + iff(sym("SHIB-USD", close > ema(close,20)), 1, 0) + iff(sym("PEPE-USD", close > ema(close,20)), 1, 0) + iff(sym("BONK-USD", close > ema(close,20)), 1, 0) + iff(sym("WIF-USD", close > ema(close,20)), 1, 0) + iff(sym("FLOKI-USD", close > ema(close,20)), 1, 0)) >= 4
stop: type=atr, mult=3.0, n=14
target: type=r, r=2.0
max trades/day: 2; flat before the session end; risk 0.5% per trade
```

### STRAT-167 Memecoin leader-to-follower transmission (pack ST186)

Markets: crypto; timeframe 5m; instruments SHIB-USD, PEPE-USD, BONK-USD, WIF-USD, FLOKI-USD

```
long entry: sym("DOGE-USD", zscore(roc(close,3), 96)) > 2 and zscore(roc(close,3), 96) < 1
stop: type=atr, mult=2.0, n=14
time stop: 8 bars
max trades/day: 3; flat before the session end; risk 0.5% per trade
```

### STRAT-168 Bitcoin risk-on memecoin participation (pack ST222)

Markets: crypto; timeframe 15m; instruments DOGE-USD, SHIB-USD, PEPE-USD, BONK-USD, WIF-USD, FLOKI-USD

```
long entry: sym("BTC-USD", cross_above(close, ema(close,96))) and (iff(sym("DOGE-USD", close > ema(close,20)), 1, 0) + iff(sym("SHIB-USD", close > ema(close,20)), 1, 0) + iff(sym("PEPE-USD", close > ema(close,20)), 1, 0) + iff(sym("BONK-USD", close > ema(close,20)), 1, 0) + iff(sym("WIF-USD", close > ema(close,20)), 1, 0) + iff(sym("FLOKI-USD", close > ema(close,20)), 1, 0)) >= 3
stop: type=atr, mult=3.0, n=14
target: type=r, r=2.0
max trades/day: 2; flat before the session end; risk 0.5% per trade
```

### STRAT-169 Selloff-resilient memecoin rebound (pack ST223)

Markets: crypto; timeframe 15m; instruments DOGE-USD, SHIB-USD, PEPE-USD, BONK-USD, WIF-USD, FLOKI-USD

```
long entry: sym("BTC-USD", since(low <= lowest(low,96))) >= 8 and sym("BTC-USD", since(low <= lowest(low,96))) <= 24 and roc(close,48) > sym("BTC-USD", roc(close,48)) and cross_above(close, highest(high,8)[1])
stop: type=atr, mult=3.0, n=14
target: type=r, r=2.0
max trades/day: 2; flat before the session end; risk 0.5% per trade
```

### STRAT-170 Memecoin residual reversion vs bitcoin (pack ST224)

Markets: crypto; timeframe 15m; instruments DOGE-USD, SHIB-USD, PEPE-USD, BONK-USD, WIF-USD, FLOKI-USD

```
long entry: cross_above(spread_z(close, sym("BTC-USD", close), 96), -2)
stop: type=atr, mult=2.5, n=14
long exit: spread_z(close, sym("BTC-USD", close), 96) > 0
time stop: 96 bars
max trades/day: 2; flat before the session end; risk 0.5% per trade
```

### STRAT-171 Memecoin volatility contraction release (pack ST225)

Markets: crypto; timeframe 15m; instruments DOGE-USD, SHIB-USD, PEPE-USD, BONK-USD, WIF-USD, FLOKI-USD

```
long entry: squeeze(20).on[1] == 1 and squeeze(20).on == 0 and close > donchian(20).upper[1] and sym("BTC-USD", natr(14) < 1.5*sma(natr(14),96))
stop: type=atr, mult=3.0, n=14
target: type=r, r=2.0
max trades/day: 2; flat before the session end; risk 0.5% per trade
```

### STRAT-172 Memecoin session-handover continuation (pack ST227)

Markets: crypto; timeframe 15m; instruments DOGE-USD, SHIB-USD, PEPE-USD, BONK-USD, WIF-USD, FLOKI-USD

```
long entry: (time_between("07:00", "07:30") or time_between("13:30", "14:00")) and rvol_tod(14) > 1.5 and cross_above(close, highest(high,8)[1])
stop: type=atr, mult=3.0, n=14
target: type=r, r=2.0
max trades/day: 2; flat before the session end; risk 0.5% per trade
```

### STRAT-173 Memecoin liquidation-aftershock reclaim (pack ST229)

Markets: crypto; timeframe 15m; instruments DOGE-USD, SHIB-USD, PEPE-USD, BONK-USD, WIF-USD, FLOKI-USD

```
long entry: since(sym("BTC-USD", zscore(roc(close,4), 96) < -2.5)) <= 16 and cross_above(close, valuewhen(sym("BTC-USD", zscore(roc(close,4), 96) < -2.5), open))
stop: type=atr, mult=3.0, n=14
target: type=r, r=2.0
max trades/day: 1; flat before the session end; risk 0.5% per trade
```

### STRAT-174 Memecoin native-price range breakout (pack ST233)

Markets: crypto; timeframe 15m; instruments BONK-USD, WIF-USD

```
long entry: close / sym("SOL-USD", close) > highest(close / sym("SOL-USD", close), 48)[1] and close > ema(close,20)
stop: type=atr, mult=3.0, n=14
target: type=r, r=2.0
max trades/day: 2; flat before the session end; risk 0.5% per trade
```

### STRAT-175 Two-stage compression breakout (pack ST234)

Markets: crypto; timeframe 5m; instruments DOGE-USD, SHIB-USD, PEPE-USD, BONK-USD, WIF-USD, FLOKI-USD

```
long entry: (highest(high,12)-lowest(low,12))[1] < 0.5*(highest(high,48)-lowest(low,48))[1] and (highest(high,48)-lowest(low,48))[1] < 0.7*(highest(high,192)-lowest(low,192))[1] and close > highest(high,12)[1]
stop: type=atr, mult=3.0, n=14
target: type=r, r=2.0
max trades/day: 2; flat before the session end; risk 0.5% per trade
```

### STRAT-176 Selloff-range midpoint acceptance (pack ST239)

Markets: crypto; timeframe 15m; instruments DOGE-USD, SHIB-USD, PEPE-USD, BONK-USD, WIF-USD, FLOKI-USD

```
long entry: since(low <= lowest(low,96)) <= 48 and persist(low > (highest(high,96)+lowest(low,96))/2, 4) and not persist(low > (highest(high,96)+lowest(low,96))/2, 5)
stop: type=level, long=(highest(high,96)+lowest(low,96))/2 - 0.5*atr(14)
target: type=level, long=highest(high,96)
max trades/day: 1; flat before the session end; risk 0.5% per trade
```

### STRAT-177 Memecoin relative-momentum leader (pack ST271)

Markets: crypto; timeframe 15m; instruments DOGE-USD, SHIB-USD, PEPE-USD, BONK-USD, WIF-USD, FLOKI-USD

```
long entry: roc(close,24) >= max(max(max(sym("DOGE-USD", roc(close,24)), sym("SHIB-USD", roc(close,24))), max(sym("PEPE-USD", roc(close,24)), sym("BONK-USD", roc(close,24)))), max(sym("WIF-USD", roc(close,24)), sym("FLOKI-USD", roc(close,24)))) and not (roc(close,24)[1] >= max(max(max(sym("DOGE-USD", roc(close,24)), sym("SHIB-USD", roc(close,24))), max(sym("PEPE-USD", roc(close,24)), sym("BONK-USD", roc(close,24)))), max(sym("WIF-USD", roc(close,24)), sym("FLOKI-USD", roc(close,24))))[1]) and close > ema(close,20)
stop: type=atr, mult=3.0, n=14
long exit: roc(close,24) < max(max(max(sym("DOGE-USD", roc(close,24)), sym("SHIB-USD", roc(close,24))), max(sym("PEPE-USD", roc(close,24)), sym("BONK-USD", roc(close,24)))), max(sym("WIF-USD", roc(close,24)), sym("FLOKI-USD", roc(close,24))))
max trades/day: 2; flat before the session end; risk 0.5% per trade
```

