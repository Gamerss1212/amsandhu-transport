<!-- The Jarvus Terminal's indicator registry and rule language (generated from its code). The strategy rules in strategy-scoreboard.md are written in it. -->

# Indicators and rule functions

Generated from the code registry (`python -m mab.docs`), so it always matches the engine.

All indicators update once per **completed** bar and use only that bar and earlier ones. Tests check this for every indicator (values computed on a truncated history must equal the full-history values). Order-flow indicators use only recorded venue data and are never estimated silently; `est_delta` is an explicitly labelled estimate.

Warm-up: *first* = bars before the first value; *stable* = bars after which the value no longer depends on where the history started (recursive smoothers). Session-based indicators need whole sessions (column *sessions*).

| Indicator | Category | Parameters (defaults) | Outputs | Inputs | Formula | Warm-up first / stable | Sessions | Missing data |
|---|---|---|---|---|---|---|---|---|
| `sma` | trend | n=20 | value | any series | mean(x[i-n+1..i]) | 19 / 20 | - | None until warm; a None input resets rolling windows |
| `ema` | trend | n=20 | value | any series | e[i] = e[i-1] + a*(x[i]-e[i-1]), a = 2/(n+1); seeded with SMA of first n values | 19 / 100 | - | None until warm; a None input resets rolling windows |
| `wma` | trend | n=20 | value | any series | sum(k*x[i-n+k]) / (n(n+1)/2), k = 1..n | 19 / 20 | - | None until warm; a None input resets rolling windows |
| `rma` | trend | n=14 | value | any series | Wilder smoothing: r[i] = r[i-1] + (x[i]-r[i-1])/n | 13 / 140 | - | None until warm; a None input resets rolling windows |
| `hma` | trend | n=21 | value | any series | WMA(2*WMA(x,n/2) - WMA(x,n), sqrt(n)) | 25 / 25 | - | None until warm; a None input resets rolling windows |
| `dema` | trend | n=21 | value | any series | 2*EMA(x,n) - EMA(EMA(x,n),n) | 42 / 210 | - | None until warm; a None input resets rolling windows |
| `tema` | trend | n=21 | value | any series | 3*E1 - 3*E2 + E3 of nested EMAs | 63 / 315 | - | None until warm; a None input resets rolling windows |
| `kama` | trend | n=10, fast=2, slow=30 | value | any series | Kaufman: sc = (ER*(2/(fast+1)-2/(slow+1)) + 2/(slow+1))^2; k[i] = k[i-1] + sc*(x-k[i-1]) | 10 / 300 | - | None until warm; a None input resets rolling windows |
| `macd` | trend | fast=12, slow=26, signal=9 | line, signal, hist | any series | line = EMA(x,fast) - EMA(x,slow); signal = EMA(line,signal); hist = line - signal | 33 / 175 | - | None until warm; a None input resets rolling windows |
| `adx` | trend | n=14 | adx, plus_di, minus_di | high, low, close | +DM/-DM (Wilder), DI = 100*RMA(DM,n)/ATR(n), DX = 100*|+DI - -DI|/(+DI + -DI), ADX = RMA(DX,n) | 28 / 280 | - | None until warm; a None input resets rolling windows |
| `supertrend` | trend | n=10, mult=3.0 | line, dir | high, low, close | basic bands = hl2 -/+ mult*ATR(n); final bands ratchet; dir = +1 while close stays above the final lower band, -1 while below the final upper band | 10 / 100 | - | None until warm; a None input resets rolling windows |
| `ichimoku` | trend | conv=9, base=26, span_b=52 | conv, base, span_a, span_b, lag_close | high, low, close | conv = mid(HH,LL over conv); base = mid over base; span_a = (conv+base)/2 and span_b = mid over span_b, both as computed `base` bars AGO (the cloud drawn over bar i); lag_close = close `base` bars ago (the causal form of the Chikou comparison) | 77 / 78 | - | None until warm; a None input resets rolling windows Chikou span plotted backwards is not used: comparing close with lag_close is the same test, causally. |
| `psar` | trend | step=0.02, max_step=0.2 | value, dir | high, low | Wilder's Parabolic SAR; the SAR for bar i uses bars up to i-1 and is never revised | 2 / 2 | - | None until warm; a None input resets rolling windows |
| `aroon` | trend | n=25 | up, down, osc | high, low | up = 100*(n - bars since n-bar high)/n; down likewise for the low; osc = up - down | 25 / 26 | - | None until warm; a None input resets rolling windows |
| `vortex` | trend | n=14 | plus, minus | high, low, close | VM+ = |H - L[-1]|, VM- = |L - H[-1]|; VI+ = sum(VM+,n)/sum(TR,n) | 14 / 15 | - | None until warm; a None input resets rolling windows |
| `linreg` | trend | n=20 | value, slope, r2 | any series | least-squares line through the last n values: value at the current bar, slope per bar, R^2 | 19 / 20 | - | None until warm; a None input resets rolling windows |
| `trix` | trend | n=15 | value | any series | 100 * 1-bar % change of EMA(EMA(EMA(x,n))) | 45 / 225 | - | None until warm; a None input resets rolling windows |
| `heikin_ashi` | trend | - | open, high, low, close | open, high, low, close | ha_close = ohlc4; ha_open = (ha_open[-1] + ha_close[-1])/2 (seed (o+c)/2); ha_high/low = extremes | 0 / 20 | - | None until warm; a None input resets rolling windows |
| `rsi` | momentum | n=14 | value | any series | Wilder: RS = RMA(gains,n)/RMA(losses,n); RSI = 100 - 100/(1+RS) (100 when losses are 0) | 14 / 140 | - | None until warm; a None input resets rolling windows |
| `stoch` | momentum | k=14, smooth=3, d=3 | k, d | high, low, close | raw = 100*(close - LL(k))/(HH(k) - LL(k)); %K = SMA(raw, smooth); %D = SMA(%K, d) | 17 / 20 | - | None until warm; a None input resets rolling windows |
| `stochrsi` | momentum | rsi_n=14, n=14, smooth=3, d=3 | k, d | any series | stochastic formula applied to RSI(rsi_n) over n bars, smoothed | 34 / 160 | - | None until warm; a None input resets rolling windows |
| `cci` | momentum | n=20 | value | high, low, close | tp = hlc3; CCI = (tp - SMA(tp,n)) / (0.015 * mean |tp - SMA(tp,n)|) | 19 / 20 | - | None until warm; a None input resets rolling windows |
| `roc` | momentum | n=12 | value | any series | 100 * (x / x[n bars ago] - 1) | 12 / 12 | - | None until warm; a None input resets rolling windows |
| `willr` | momentum | n=14 | value | high, low, close | -100 * (HH(n) - close) / (HH(n) - LL(n)) | 13 / 14 | - | None until warm; a None input resets rolling windows |
| `uo` | momentum | p1=7, p2=14, p3=28 | value | high, low, close | Ultimate Oscillator: BP = close - min(low, prev close); weighted 4:2:1 average of BP/TR sums | 28 / 29 | - | None until warm; a None input resets rolling windows |
| `ao` | momentum | - | value | high, low | Awesome Oscillator: SMA(hl2,5) - SMA(hl2,34) | 33 / 34 | - | None until warm; a None input resets rolling windows |
| `connors_rsi` | momentum | rsi_n=3, streak_n=2, rank_n=100 | value | close | mean of RSI(close,rsi_n), RSI(streak,streak_n) and the percent rank of the 1-bar return over rank_n | 100 / 101 | - | None until warm; a None input resets rolling windows |
| `atr` | volatility | n=14 | value | high, low, close | RMA(true range, n); TR = max(H-L, |H-C[-1]|, |L-C[-1]|) | 13 / 140 | - | None until warm; a None input resets rolling windows |
| `natr` | volatility | n=14 | value | high, low, close | 100 * ATR(n) / close | 13 / 140 | - | None until warm; a None input resets rolling windows |
| `bb` | volatility | n=20, mult=2.0 | mid, upper, lower, width, pctb | any series | mid = SMA(x,n); sd = population stdev(x,n); upper/lower = mid +/- mult*sd; width = (upper-lower)/mid; pctb = (x - lower)/(upper - lower) | 19 / 20 | - | None until warm; a None input resets rolling windows |
| `kc` | volatility | n=20, mult=2.0, atr_n=10 | mid, upper, lower | high, low, close | mid = EMA(close,n); bands = mid +/- mult*ATR(atr_n) | 20 / 100 | - | None until warm; a None input resets rolling windows |
| `donchian` | volatility | n=20 | upper, lower, mid | high, low | upper = highest high of the last n bars INCLUDING the current bar; lower likewise; use donchian(n).upper[1] for the channel of the n bars before the current one | 19 / 20 | - | None until warm; a None input resets rolling windows |
| `squeeze` | volatility | n=20, bb_mult=2.0, kc_mult=1.5 | on, mom | high, low, close | on = 1 while BB(n,bb_mult) sits inside KC(n,kc_mult, ATR n); mom = linreg value of close - mean(mid(HH,LL), SMA(close)) over n | 40 / 200 | - | None until warm; a None input resets rolling windows |
| `realized_vol` | volatility | n=30 | value, per_bar | close | per_bar = sample stdev of log returns over n bars; value = per_bar * sqrt(bars per year) (stocks: 252 sessions x 390 minutes; crypto: 365 x 1440 minutes) | 30 / 31 | - | None until warm; a None input resets rolling windows |
| `chop` | volatility | n=14 | value | high, low, close | 100 * log10(sum(TR,n) / (HH(n) - LL(n))) / log10(n) | 14 / 15 | - | None until warm; a None input resets rolling windows |
| `er` | volatility | n=10 | value | any series | Kaufman efficiency ratio: |x - x[n]| / sum(|x[k] - x[k-1]|, n) | 10 / 11 | - | None until warm; a None input resets rolling windows |
| `vwap` | volume | - | value, sd, upper1, lower1, upper2, lower2 | high, low, close, volume, session | session-anchored: cumsum(hlc3*v)/cumsum(v) from the session's first bar; sd = sqrt(cumsum(v*tp^2)/cumsum(v) - vwap^2); bands at +/-1 and +/-2 sd | 0 / 0 | 0 | None outside the session; zero cumulative volume gives the bar's typical price |
| `obv` | volume | - | value | close, volume | cumulative +v on up closes, -v on down closes, 0 unchanged; starts at 0 | 0 / 0 | - | cumulative from the first bar in the buffer, so only its changes (not its level) are comparable |
| `ad` | volume | - | value | high, low, close, volume | Chaikin A/D: cumsum(((C-L)-(H-C))/(H-L) * V); 0 when H == L | 0 / 0 | - | cumulative from the buffer start: compare changes, not levels |
| `cmf` | volume | n=20 | value | high, low, close, volume | sum(MFM*V,n)/sum(V,n), MFM = ((C-L)-(H-C))/(H-L) | 19 / 20 | - | None until warm; a None input resets rolling windows |
| `mfi` | volume | n=14 | value | high, low, close, volume | tp = hlc3; raw flow = tp*v; MFI = 100 - 100/(1 + sum(pos flow,n)/sum(neg flow,n)) | 14 / 15 | - | None until warm; a None input resets rolling windows |
| `force` | volume | n=13 | value | close, volume | EMA((close - close[-1]) * volume, n) | 13 / 65 | - | None until warm; a None input resets rolling windows |
| `rvol` | volume | n=20 | value | volume | volume / mean volume of the PREVIOUS n bars (the current bar is excluded from its own baseline) | 20 / 21 | - | None until warm; a None input resets rolling windows |
| `rvol_tod` | volume | days=10 | value | volume, session | volume / mean volume of the bar at the same position in the previous `days` sessions | 0 / 0 | 10 | None until `days` earlier sessions contain a bar at the same position |
| `volume_profile` | volume | bins=40, va=0.7 | poc, vah, val, dev_poc | high, low, volume, session | each bar's volume spread evenly over its [low, high] in `bins` price bins per session; POC = fullest bin; value area grows from the POC to `va` of volume. poc/vah/val are the PREVIOUS session's; dev_poc is the developing POC of the current session through the current bar | 0 / 0 | 1 | approximated from OHLCV bars, not trade-level volume at price; None for the first session Bar-based approximation. A trade-level profile needs tick data (see data requirements). |
| `session` | structure | - | open, high, low, prev_open, prev_high, prev_low, prev_close, gap | open, high, low, close, session | current session's open and running high/low through the current bar; previous session's OHLC; gap = session open / previous close - 1 | 0 / 0 | 1 | prev_* and gap are None during the first session in the buffer |
| `opening_range` | structure | minutes=30 | high, low, mid, done | high, low, session | high/low of the session's bars that open within the first `minutes`; published from the bar that completes the range and held for the rest of the session; done = 1 once published | 0 / 0 | 0 | None before the range completes (no look-ahead); crypto sessions start 00:00 UTC |
| `window_range` | structure | start=0, end=480 | high, low, done | high, low | high/low of the current day's bars opening between local minute `start` and `end` (minutes after local midnight: New York for stocks, UTC for crypto); published once the window has closed | 0 / 0 | 1 | None until the window closes each day |
| `pivots` | structure | kind=classic | p, r1, r2, r3, s1, s2, s3 | high, low, close, session | from the previous session's H, L, C. classic: P=(H+L+C)/3, R1=2P-L, S1=2P-H, R2=P+(H-L), S2=P-(H-L), R3=H+2(P-L), S3=L-2(H-P). camarilla: C +/- (H-L)*1.1/12, /6, /4. fibonacci: P +/- 0.382, 0.618, 1.0 x (H-L). woodie: P=(H+L+2C)/4, R1=2P-L, S1=2P-H, R2=P+H-L, S2=P-(H-L) | 0 / 0 | 1 | None during the first session in the buffer |
| `swings` | structure | n=3 | high, low, high_prev, low_prev, high_prev2, low_prev2, age_high, age_low | high, low | a swing high at bar j has a high greater than the n bars on each side; it becomes KNOWN at bar j+n (confirmation delay) and is published from then on. high/low = latest confirmed swing prices; *_prev and *_prev2 = the one and two before (for higher-high / pattern tests); age = bars since the swing bar | 6 / 7 | - | None until enough swings are confirmed Never repaints: a swing is published only once confirmed. |
| `fvg` | structure | - | bull_top, bull_bottom, bear_top, bear_bottom | high, low | three-bar fair value gap known at bar i: bullish when low[i] > high[i-2] (gap = high[i-2]..low[i]); bearish when high[i] < low[i-2]. The most recent gap of each side is held until price trades back through it | 2 / 3 | - | None until warm; a None input resets rolling windows |
| `candle` | pattern | - | bull_engulf, bear_engulf, hammer, shooting_star, doji, inside, outside, morning_star, evening_star, three_soldiers, three_crows, marubozu_up, marubozu_down, ibs, range | open, high, low, close | bull_engulf: prior bar bearish, current bullish, current body covers prior body and is larger. hammer: range > 0, body >= 5% of range, lower wick >= 2x body, upper wick <= 25% of range (shooting star mirrored). doji: body <= 10% of range. inside: H < H[-1] and L > L[-1]; outside: H > H[-1] and L < L[-1]. morning_star: bar -2 bearish with body >= 60% of its range, bar -1 body <= 30% of bar -2 body, current bullish closing above bar -2's body midpoint (no gap requirement, since crypto trades continuously). three_soldiers: 3 bullish bars, rising closes, each opening inside the prior body, upper wicks <= 25% of range. marubozu: body >= 90% of range. ibs = (C-L)/(H-L). Each flag is 1.0 or 0.0 | 2 / 3 | - | None until warm; a None input resets rolling windows |
| `nr` | pattern | n=7 | value | high, low | 1.0 when the current bar's range (H-L) is the smallest of the last n bars (NR4 / NR7), else 0.0 | 6 / 7 | - | None until warm; a None input resets rolling windows |
| `orderflow` | orderflow | - | delta, cvd, imbalance, trades | buy_vol, sell_vol, n_trades (recorded from the venue's trade feed) | from venue trade prints aggregated per bar by aggressor side: delta = buy volume - sell volume; cvd = session cumulative delta; imbalance = delta / (buy + sell); trades = print count | 0 / 0 | 0 | None for bars without recorded prints. Never estimated from OHLCV; see est_delta for a labelled estimate |
| `book` | orderflow | - | spread_bps, imbalance, bid_depth, ask_depth | bid, ask, bid_depth, ask_depth (recorded snapshots) | from the order-book snapshot taken at bar close: spread_bps = 1e4*(ask-bid)/mid; imbalance = (bid_depth - ask_depth)/(bid_depth + ask_depth) over the recorded levels | 0 / 0 | - | None for bars without a recorded snapshot; never estimated |
| `est_delta` | orderflow | - | value | high, low, close, volume | ESTIMATE, not order flow: close-location value x volume = ((C-L)-(H-C))/(H-L) * V. Labelled so it is never mistaken for measured aggressor volume | 0 / 0 | - | None until warm; a None input resets rolling windows |
| `fisher` | momentum | n=10 | value, signal | high, low | Ehlers: x = 0.33*2*((hl2 - LL(n))/(HH(n) - LL(n)) - 0.5) + 0.67*x[-1], clipped to +/-0.999; fish = 0.5*ln((1+x)/(1-x)) + 0.5*fish[-1]; signal = fish one bar ago | 10 / 100 | - | None until warm; a None input resets rolling windows |
| `mass_index` | volatility | ema_n=9, sum_n=25 | value | high, low | Dorsey: sum over sum_n bars of EMA(H-L, ema_n) / EMA(EMA(H-L, ema_n), ema_n) | 43 / 115 | - | None until warm; a None input resets rolling windows |
| `td_setup` | pattern | lookback=4 | buy, sell | close | DeMark setup counts: buy = consecutive bars with close < close `lookback` bars earlier (resets otherwise); sell = consecutive bars with close > close `lookback` bars earlier | 4 / 13 | - | None until warm; a None input resets rolling windows |
| `streak` | pattern | - | value | close | signed count of consecutive higher (+) or lower (-) closes; 0 on an unchanged close | 1 / 2 | - | None until warm; a None input resets rolling windows |
| `variance_ratio` | statistical | n=120, k=5 | value | close | Lo-MacKinlay style: var of k-bar log returns / (k * var of 1-bar log returns), both over the last n bars; >1 trending, <1 mean-reverting | 125 / 126 | - | None until warm; a None input resets rolling windows |
| `autocorr` | statistical | n=60, lag=1 | value | close | Pearson autocorrelation of 1-bar returns at `lag` over the last n bars | 62 / 63 | - | None until warm; a None input resets rolling windows |
| `tod_return` | statistical | days=20, k=6 | mean, t | close, session | for the bar at position p of the session: mean (and t-statistic) of the k-bar return that started at the same position p on each of the previous `days` sessions. Uses only sessions already finished | 0 / 0 | 20 | None until `days` earlier sessions have that position |
| `premarket` | structure | - | high, low, last, volume, done | high, low, close, volume (extended hours) | stocks with extended-hours bars: high, low, last price and volume of the bars before the regular open on the same local date; published from the session's first bar | 0 / 0 | 0 | None when the series has no pre-market bars (subscribe with extended hours) |
| `weekend` | structure | fri_close_hour=21, reopen_hour=23 | high, low, fri_close, gap | high, low, close | crypto: high/low of Saturday-Sunday UTC, published from Monday 00:00 UTC for the week; fri_close = close of the bar ending at Friday `fri_close_hour`:00 UTC (a proxy for the CME bitcoin futures close), published from Sunday `reopen_hour`:00 UTC; gap = price at that reopen / fri_close - 1 | 0 / 0 | 3 | None until the first full weekend in the buffer |

## Rule functions

| Function | Meaning |
|---|---|
| `abs` | absolute value |
| `avwap` | VWAP anchored at every bar where cond is true (inclusive); None before the first anchor |
| `bar_in_session` | 0 for the session's first bar; -1 outside the session |
| `beta` | rolling OLS slope of x on y over n bars |
| `ceil_to` | x rounded up to a multiple of step |
| `change` | x - x[n] |
| `corr` | rolling Pearson correlation of x and y over n bars |
| `count` | number of the last n bars on which cond was true |
| `cross_above` | a crosses above b on this bar: a > b now and a <= b on the previous bar |
| `cross_below` | a crosses below b on this bar: a < b now and a >= b on the previous bar |
| `days_to_month_end` | calendar days from the session day to the last day of its month |
| `dom` | day of month |
| `dow` | weekday of the session, Monday = 0 |
| `event` | event("fomc"|"cpi"|"earnings"): 1 on sessions with that scheduled event; None if the event calendar is not loaded (the rule then cannot trigger) |
| `falling` | x fell on each of the last n bars |
| `floor_to` | x rounded down to a multiple of step (round-number levels) |
| `highest` | highest value of x over the last n bars (inclusive) |
| `hour` | local hour of the bar's open |
| `iff` | b if cond else c |
| `is_opex` | 1 on the third Friday of the month (standard US monthly options expiration) |
| `log` | natural log |
| `lowest` | lowest value of x over the last n bars (inclusive) |
| `max` | larger of two values |
| `mean` | mean of x over the last n bars |
| `median` | median of x over the last n bars |
| `min` | smaller of two values |
| `minutes_since_open` | minutes from the session open to this bar's open |
| `minutes_to_close` | minutes from this bar's close to the session close |
| `month` | month 1-12 |
| `on` | on("SPY", "1d", expr): another instrument and timeframe |
| `pct` | x / x[n] - 1 |
| `pctrank` | percent of the previous n values below x |
| `persist` | cond has been true on each of the last n bars (including this one) |
| `pre_holiday` | 1 on the last trading session before an exchange holiday (weekday closure); stocks only |
| `rising` | x rose on each of the last n bars |
| `rs` | relative strength: (x/x[n]) / (y/y[n]) - 1 |
| `sign` | -1, 0 or 1 |
| `since` | bars since cond was last true (0 = this bar); None if never in the buffer |
| `spread_z` | z-score of log(x) - beta*log(y), beta re-estimated over n bars |
| `sqrt` | square root |
| `std` | sample standard deviation over n bars |
| `sum` | sum of x over the last n bars |
| `sym` | sym("SPY", expr) or sym("okx:BTC-USDT-SWAP", expr): expr on another instrument, same timeframe |
| `tf` | tf("1h", expr): expr on this instrument's 1h bars, aligned to completed bars |
| `time_between` | time_between("09:45", "15:30"): bar opens at or after the first and before the second local time |
| `tod` | minutes after local midnight at the bar's open (New York for stocks, UTC for crypto) |
| `valuewhen` | value of x on the most recent bar where cond was true |
| `within` | cond was true on at least one of the last n bars (including this one) |
| `zscore` | (x - mean(x,n)) / std(x,n) |

## Rule language

Rule language: the text a strategy definition uses for entries, filters and exits.

    cross_above(ema(close,9), ema(close,21)) and close > vwap() and rvol(20) > 1.5
    persist(close > tf("1h", ema(close,50)), 3) or rsi(close,2) < 5
    close > opening_range(15).high + 0.1 * atr(14)

Grammar (lowest to highest precedence): `or`, `and`, `not`, comparisons (> < >= <= == !=),
+ -, * /, unary minus, postfix `.output` and `[k]` (value k bars ago), primaries (numbers,
"strings", price sources, function and indicator calls, parentheses). `$name` is replaced by a
strategy or bot parameter before parsing.

Every expression evaluates to a Series aligned with the base Frame (or a scalar). Truth values
are 1.0 / 0.0, and None means "unknown" (an input is warming up or missing). Logic is
three-valued: `False and None` is False, `True and None` is None; a rule that is None never
triggers an order and is reported as unknown.

Multi-timeframe and multi-instrument values use tf("1h", expr), sym("SPY", expr) and
on("okx:BTC-USDT-SWAP", "1h", expr). The other series is aligned to the base bar by taking the
last bar that had COMPLETED by the time the base bar completed, so no value from a still-open
higher-timeframe bar is ever used.
