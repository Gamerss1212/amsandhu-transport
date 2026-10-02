# Knowledge base: indicators

One entry per `### `. `python3 scripts/know.py <name>` prints one entry plus, for each `id`, Jarvus's measured result.
Indicators are calculations on past prices/volume: they describe, they do not predict. One per job: trend (moving
averages), momentum (RSI or MACD), volatility (ATR, bands), participation (volume, OBV), value (VWAP).

### Moving averages (SMA, EMA)
id: ema_9_21_up, ema_9_21_down · aka: moving average, ma, sma, ema, simple moving average, exponential moving average, ema cross, ma crossover, 9 21 ema, 20 ema, 50 ema
What: average close of the last N bars. SMA weights equally; EMA weights recent bars more (reacts faster). Common: 9/21 (short), 20/50 (swing), 200 (long-term).
Use: trend filter (price above a rising 50/200 = uptrend), dynamic support in trends, crossovers as slow trend signals.
Trap: crossovers lag; in ranges they whipsaw.

### Weighted, Hull and other averages
aka: wma, hma, hull moving average, vwma, dema, tema, kama, alma, smma, rma, lsma, linear regression line
What: variants that reduce lag (Hull, DEMA/TEMA), adapt to volatility (KAMA), weight by volume (VWMA) or fit a regression line (LSMA). Same job as an EMA; none measured as a different edge by Jarvus.

### Golden cross and death cross
id: golden_cross, death_cross · aka: golden cross, death cross, 50 200 cross
What: the 50-period average crossing above (golden) or below (death) the 200. On daily charts a famous long-term trend signal; it lags by weeks.

### 200 EMA / 200-day average
id: ema200_reclaim, ema200_lose · aka: 200 ema, 200 sma, 200 day moving average, 200dma, 200 week moving average, 200wma
What: the long-term trend line. Above it = bull regime, below = bear regime.
Jarvus: memes are only allowed while BTC is above its 200-day average (backtested rule).

### RSI (Relative Strength Index)
id: rsi_os_30, rsi_up_30, rsi_ob_70, rsi_dn_70 · aka: rsi, relative strength index, rsi 14, overbought, oversold, rsi 30 70
What: 0–100 momentum oscillator (Wilder, 1978): average gains vs average losses over 14 bars. Classic: > 70 overbought, < 30 oversold.
Use: in ranges, extremes fade; in trends, RSI stays "overbought" while price keeps rising (40–80 band in uptrends).
Jarvus measured: in crypto, RSI above 70 was followed by BETTER-than-average results on 4h (momentum), so "overbought = sell" did not hold.

### RSI(2) (Connors)
id: rsi2_10, rsi2_connors, p_rsi2 · aka: rsi2, rsi 2, connors rsi, larry connors
What: a 2-period RSI used for short pullbacks: buy when RSI(2) < 10 while price is above the 200-day average, sell on strength (Connors & Alvarez). Built for stocks.

### MACD
id: macd_up, macd_up_below0, macd_zero_up, macd_down, macd_hist_turn · aka: macd, moving average convergence divergence, macd cross, signal line, histogram
What: MACD line = EMA(12) − EMA(26); signal = EMA(9) of MACD; histogram = MACD − signal (Appel). Crosses and zero-line crosses are momentum shifts; divergences warn of fading momentum.
Trap: it is two moving averages, so it lags like them.

### Bollinger Bands
id: bb_below, bb_reentry, bb_above, bb_squeeze_up · aka: bollinger, bollinger bands, bb, %b, bandwidth, band squeeze, bollinger squeeze
What: SMA(20) ± 2 standard deviations (John Bollinger). %B = where price sits in the bands; BandWidth = band width / middle. A squeeze (narrow bands) precedes expansion, direction unknown.
Use: in ranges, closes outside the bands tend to revert; in trends, price "walks the band".

### Keltner Channels
id: keltner_up, keltner_below · aka: keltner, keltner channel, kc
What: EMA(20) ± 2× ATR. Smoother than Bollinger; a close outside signals strong momentum (or a stretch to fade in ranges).

### TTM Squeeze
id: ttm_squeeze · aka: ttm squeeze, squeeze, squeeze momentum, lazybear squeeze
What: Bollinger Bands inside the Keltner Channel = squeeze on (low volatility); when they come back out, the squeeze "fires" (John Carter). Direction from momentum.

### ATR (Average True Range)
id: stretch_ema20 · aka: atr, average true range, true range, volatility, chandelier exit, atr stop
What: average bar range including gaps (Wilder), the unit of volatility. Stops and targets in ATR adapt to the market. Chandelier exit = highest high − 3× ATR (trailing stop).
Jarvus: stop = 4× ATR(1h); the measured signal here is "close stretched 2.5 ATR below the 20 EMA" (a mean-reversion buy).

### Stochastic oscillator
id: stoch_up, stoch_down · aka: stochastic, stoch, stochastics, %k %d, slow stochastic
What: where the close sits in the last 14 bars' range, 0–100 (Lane). < 20 oversold, > 80 overbought; %K/%D crosses as triggers.

### Stochastic RSI
id: stochrsi_up · aka: stoch rsi, stochrsi
What: the stochastic formula applied to RSI (0–1). Very fast and noisy; popular on crypto charts.

### Williams %R
id: willr_up · aka: williams r, williams %r, %r
What: like the stochastic, inverted: 0 to −100; below −80 oversold, above −20 overbought (Larry Williams).

### CCI (Commodity Channel Index)
id: cci_up, cci_break · aka: cci, commodity channel index
What: distance of the typical price from its average in mean-deviation units (Lambert). ±100 are the usual triggers: above +100 = strong momentum, back above −100 = recovery from oversold.

### MFI (Money Flow Index)
id: mfi_os, mfi_ob · aka: mfi, money flow index, volume rsi
What: an RSI that uses price × volume. < 20 oversold, > 80 overbought.

### ADX and DMI
id: adx_di_up, holy_grail · aka: adx, dmi, +di, -di, directional movement, trend strength, holy grail
What: +DI/−DI measure up vs down movement; ADX (0–100) measures trend strength regardless of direction (Wilder). ADX > 25 = trending, < 20 = ranging. Raschke's "Holy Grail": ADX > 30 and a pullback to the 20 EMA.

### Parabolic SAR
id: psar_up, psar_down · aka: parabolic sar, psar, sar, stop and reverse
What: dots that trail price and accelerate in a trend (Wilder); a flip to the other side = trend change / trailing-stop exit. Whipsaws in ranges.

### Supertrend
id: supertrend_up, supertrend_down · aka: supertrend, super trend
What: an ATR band (10, 3) that flips between support below price (uptrend) and resistance above (downtrend). Used as a trailing stop and trend filter.

### Ichimoku Cloud
id: ichi_tk_up, ichi_cloud_up, ichi_cloud_down · aka: ichimoku, ichimoku cloud, kumo, tenkan, kijun, senkou span, chikou, tk cross
What: Tenkan (9) and Kijun (26) midpoints, a cloud of two spans plotted 26 bars ahead, and a lagging line (Hosoda). Above the cloud = bullish regime; TK cross = trigger.
Note: designed for daily stock charts with 6-day weeks; crypto users often use 20/60/120 settings.

### Aroon
id: aroon_up · aka: aroon, aroon oscillator
What: how many bars since the 25-bar high (Aroon up) and low (Aroon down), as 0–100. Up crossing above down = new uptrend.

### Donchian channels
id: donchian20, donchian55, donchian20_down · aka: donchian, donchian channel, turtle trading, turtles, channel breakout, 20 day breakout, 55 day breakout
What: highest high and lowest low of the last N bars. The Turtle Traders (Dennis/Eckhardt, 1980s) bought 20- and 55-day breakouts with ATR-based sizing.

### OBV (On-Balance Volume)
id: obv_lead, obv_confirm · aka: obv, on balance volume, accumulation distribution, a/d line, chaikin money flow, cmf, chaikin oscillator
What: running total of volume, added on up closes and subtracted on down closes (Granville). Rising OBV with flat price = quiet buying. A/D line and Chaikin Money Flow weight volume by where the close sits in the range.

### Volume and relative volume
id: vol_spike_bull, vol_spike_bear · aka: volume, rvol, relative volume, volume spike, high volume, volume confirmation
What: RVOL = volume ÷ its average. Breakouts on high volume are more trusted; spikes on red candles are often liquidations/capitulation.
Trap: crypto exchange volume includes wash trading on some venues; compare the same venue only.

### VWAP
id: vwap_reclaim, vwap_lose · aka: vwap, volume weighted average price, anchored vwap, avwap, vwap bands
What: average price weighted by volume, usually from the session start (or anchored to a chosen candle). Institutions benchmark fills to it; above VWAP = buyers in control for the session.
Jarvus measured a rolling 24h VWAP because crypto has no session open.

### Heikin-Ashi turns
id: ha_green, ha_red · aka: heikin ashi signal, ha flip
What: the first green (red) Heikin-Ashi candle after a run of the other colour: a smoothed trend-change trigger. Lags by design.

### Rate of change and momentum
id: rally_24h, drop_24h · aka: roc, rate of change, momentum indicator, time series momentum, 24h change
What: % change over N bars. Time-series momentum (what went up keeps going up for a while) is one of the best documented effects across markets, including crypto. Jarvus measured "big 24h rally" (momentum) and "big 24h drop" (dip).

### Runs of candles
id: five_green, five_red · aka: consecutive candles, five green candles, winning streak, losing streak
What: N candles in a row of one colour. Momentum traders follow streaks; mean-reverters fade them.

### Z-score
id: zscore_m2 · aka: z score, standard score, standard deviation from mean
What: (price − its 50-bar average) ÷ the 50-bar standard deviation; below −2 = statistically stretched low. A mean-reversion trigger.

### Oscillators Jarvus did not measure
aka: ultimate oscillator, trix, kst, know sure thing, awesome oscillator, accelerator oscillator, fisher transform, elder ray, force index, vortex, choppiness index, chop, coppock curve, dpo, detrended price oscillator, cmo, chande momentum, ppo, tsi, true strength index, rvi, relative vigor, schaff trend cycle, stc, wavetrend, market cipher, kdj, mass index, ulcer index, ehlers
What: more ways to combine price momentum, smoothing and volatility. Most are close relatives of RSI/MACD/stochastics; none adds information the price did not already contain. The choppiness index (high = range) is a regime filter similar to ADX < 20.
Rule: test one mechanically before trusting it (`Jarvus backtest`); never stack five oscillators that say the same thing.

### Trend tools Jarvus did not measure
aka: williams alligator, alligator, gator, fractals, williams fractals, zigzag, linear regression channel, regression channel, envelope, ma envelope, price channel, standard error bands, starc bands
What: more ways to draw trends, swings and bands. ZigZag and fractals mark swing points (Jarvus uses 2-bar fractals for structure); ZigZag repaints, so it cannot be backtested honestly.

### Volatility measures
aka: historical volatility, realized volatility, standard deviation, implied volatility, iv, dvol, volatility index, beta
What: how much price moves. Realized = measured from past returns; implied = priced into options (Deribit DVOL is crypto's VIX). Volatility clusters, which is why Jarvus's volatility gate can forecast it while direction stays unpredictable.

### Which indicator is best
aka: best indicator, most accurate indicator, best indicator for crypto, best indicator for day trading, indicator win rate
What: none predicts direction reliably. Jarvus measured 59 crypto indicator signals (`references/kb-measured.md`): momentum/breakout signals on 4h candles (big green candle, volume spike, RSI above 70, Donchian 55, Keltner breakout) beat random entries and made money in both halves on at least one group; classic "oversold = buy" signals did not.
Use: one trend filter + one trigger + a stop in ATR + a cost check. Jarvus's volatility gate (how much, not which way) is the measured edge.
