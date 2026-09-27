# Duplicate review

## Rule

Two candidates are the same strategy (one becomes a variant) when they differ only in:
- parameter values (periods, thresholds, multipliers), ticker, market or timeframe;
- the choice among interchangeable indicators in the same template (e.g. RSI vs Stochastic vs Williams %R for an oversold reversal);
- exit or order-type details while the entry logic is unchanged;
- the name.

They are distinct when they differ in the market hypothesis, the signal construction, the reference level or anchor, the direction logic (continuation vs reversal), or a required data type (e.g. order flow, cross-asset series, event calendars).

## Automated checks

1. **Exact structure**: every executable rule is parsed, numeric constants are replaced by `#`, and the entry/filter structures plus stop and order types are compared. Identical structures are flagged.
2. **Near duplicates**: within a family, pairs whose indicator/function sets overlap by Jaccard >= 0.75 are flagged for manual review.


## Results

Exact-structure matches: 0


Near-duplicate pairs flagged for manual review: 11

- STRAT-005 ADX trend-strength breakout / STRAT-006 Directional-movement crossover (Wilder DMI) (overlap 1.0): kept separate: anchor 'ADX/DMI(14)' vs 'DMI(14)', logic 'continuation' vs 'continuation'
- STRAT-009 Ichimoku Tenkan/Kijun cross above the cloud / STRAT-010 Ichimoku cloud breakout (overlap 1.0): kept separate: anchor 'Ichimoku(9,26,52)' vs 'Ichimoku cloud', logic 'continuation' vs 'breakout'
- STRAT-020 Stocks-in-play 5-minute ORB with ATR stop / STRAT-025 Opening-drive continuation (overlap 0.8): kept separate: anchor 'first 5-minute range + opening relative volume' vs 'first 15-minute range and close location', logic 'breakout' vs 'continuation'
- STRAT-052 Market Profile 80% rule / STRAT-053 Value-area breakout with acceptance (overlap 1.0): kept separate: anchor 'prior session VAH/VAL' vs 'prior session VAH/VAL', logic 'reversal / rotation' vs 'breakout'
- STRAT-075 Engulfing candle at a 10-bar extreme / STRAT-077 Morning star / evening star (overlap 0.8): kept separate: anchor '10-bar low/high' vs 'three-bar pattern', logic 'reversal' vs 'reversal'
- STRAT-078 Three white soldiers / three black crows continuation / STRAT-079 Outside-bar reversal (overlap 1.0): kept separate: anchor 'three-bar pattern' vs 'outside bar after a decline', logic 'continuation' vs 'reversal'
- STRAT-080 Break of structure after a higher low / STRAT-082 Head-and-shoulders breakdown (overlap 0.8): kept separate: anchor 'confirmed swing points' vs 'three confirmed swing highs', logic 'continuation' vs 'reversal'
- STRAT-080 Break of structure after a higher low / STRAT-088 Swing trendline break (overlap 1.0): kept separate: anchor 'confirmed swing points' vs 'line through two confirmed swing highs', logic 'continuation' vs 'breakout'
- STRAT-082 Head-and-shoulders breakdown / STRAT-088 Swing trendline break (overlap 0.8): kept separate: anchor 'three confirmed swing highs' vs 'line through two confirmed swing highs', logic 'reversal' vs 'breakout'
- STRAT-103 Pre-FOMC announcement drift (intraday part) / STRAT-104 Macro-announcement-day long (CPI) (overlap 0.75): kept separate: anchor 'FOMC announcement days (14:00 ET)' vs 'CPI release days', logic 'event bias' vs 'event bias'
- STRAT-111 Perpetual-spot basis reversion / STRAT-112 US-venue premium momentum (overlap 1.0): kept separate: anchor 'z-score of OKX BTC perp / spot - 1' vs 'Coinbase BTC-USD / OKX BTC-USDT - 1', logic 'reversal' vs 'continuation'

## Variants recorded (not counted): 66

- STRAT-V001 EMA crossover without VWAP filter -> parent STRAT-001: filter removed
- STRAT-V002 SMA 20/50 crossover -> parent STRAT-001: average type and periods
- STRAT-V003 Hull MA slope turn -> parent STRAT-001: same template: slope sign change of a low-lag average
- STRAT-V004 RSI centreline (50) cross -> parent STRAT-001: same template with an oscillator in place of the average pair
- STRAT-V005 Supertrend pullback -> parent STRAT-002: pullback reference changed to the Supertrend line
- STRAT-V006 Ichimoku base-line bounce -> parent STRAT-002: pullback reference changed to the Kijun-sen
- STRAT-V007 Higher-timeframe trend, lower-timeframe RSI pullback -> parent STRAT-152: Triple Screen template with RSI as the second screen
- STRAT-V008 MACD zero-line cross -> parent STRAT-003: trigger moved to the zero line
- STRAT-V009 TRIX signal cross -> parent STRAT-003: triple-smoothed momentum in the same template
- STRAT-V010 Vortex indicator crossover -> parent STRAT-006: same template with VI+/VI-
- STRAT-V011 30-minute opening-range breakout -> parent STRAT-019: range length 30 minutes
- STRAT-V012 60-minute opening-range breakout -> parent STRAT-019: range length 60 minutes
- STRAT-V013 UTC-day opening-range breakout (crypto) -> parent STRAT-019: market: crypto, range = first hour after 00:00 UTC
- STRAT-V014 ORB with VWAP confirmation -> parent STRAT-019: adds price-above-VWAP filter
- STRAT-V015 ORB only after a narrow opening range -> parent STRAT-019: adds range-width < 0.35 x daily ATR filter
- STRAT-V016 First pullback after an opening drive -> parent STRAT-025: entry on the first EMA(9) pullback instead of the 15-minute close
- STRAT-V017 London-range breakout at the New York open -> parent STRAT-027: range 07:00-13:30 UTC, trade 13:30-17:00 UTC
- STRAT-V018 US-open breakout (crypto) -> parent STRAT-027: range 12:00-13:30 UTC, trade from 13:30
- STRAT-V019 Open +/- k x prior day's range (Williams) -> parent STRAT-028: volatility measure: previous day's range
- STRAT-V020 Gap-and-go with pre-market volume filter -> parent STRAT-029: adds pre-market volume threshold (extended-hours data)
- STRAT-V021 Large-gap intraday reversal -> parent STRAT-030: gap threshold in units of return volatility
- STRAT-V022 Early-session reversion to prior close -> parent STRAT-030: trigger after the first 30 minutes instead of the first bar
- STRAT-V023 Prior 5-session high/low breakout -> parent STRAT-035: level: prior 5 sessions' extreme
- STRAT-V024 Swing-low liquidity sweep reversal -> parent STRAT-037: reference: last confirmed swing low instead of the 20-bar low
- STRAT-V025 Camarilla H3/L3 fade -> parent STRAT-038: levels from the Camarilla formula
- STRAT-V026 Fibonacci pivot bounce -> parent STRAT-038: levels from the Fibonacci pivot formula
- STRAT-V027 Camarilla H4/L4 breakout -> parent STRAT-039: levels from the Camarilla formula
- STRAT-V028 First-hour VWAP extension fade -> parent STRAT-047: time window 10:00-11:00 ET only
- STRAT-V029 VWAP-distance z-score reversion -> parent STRAT-047: z-score of close - VWAP instead of VWAP bands
- STRAT-V030 Weekend band reversion (crypto) -> parent STRAT-047: only on Saturday/Sunday UTC
- STRAT-V031 Anchored VWAP from the prior session close -> parent STRAT-050: anchor at the prior session's last bar
- STRAT-V032 RSI(14) 30/70 reversal -> parent STRAT-062: period 14, thresholds 30/70, no trend filter
- STRAT-V033 ConnorsRSI pullback -> parent STRAT-062: ConnorsRSI(3,2,100) < 10
- STRAT-V034 Stochastic oversold cross -> parent STRAT-062: %K/%D cross below 20
- STRAT-V035 StochRSI extreme -> parent STRAT-062: StochRSI %K below 10
- STRAT-V036 Williams %R reversal -> parent STRAT-062: %R below -90 turning up
- STRAT-V037 Fisher transform reversal -> parent STRAT-062: Fisher(10) crossing its signal below -1.5
- STRAT-V038 Keltner channel fade -> parent STRAT-063: Keltner(20,2,10) instead of Bollinger
- STRAT-V039 Z-score reversion to SMA(20) -> parent STRAT-063: z-score < -2 instead of band re-entry
- STRAT-V040 Overextension from EMA(20) fade -> parent STRAT-063: distance > 3 ATR from EMA(20)
- STRAT-V041 Double 7s (7-bar low in uptrend) -> parent STRAT-065: trigger: close at 7-bar low; exit at 7-bar high
- STRAT-V042 30-minute return percentile reversal -> parent STRAT-068: trigger on pctrank of 6-bar return < 5
- STRAT-V043 MACD divergence -> parent STRAT-070: MACD line instead of RSI
- STRAT-V044 Ultimate Oscillator divergence (Williams) -> parent STRAT-070: Ultimate Oscillator with break of divergence high
- STRAT-V045 TTM Squeeze fire (Carter) -> parent STRAT-071: compression = Bollinger inside Keltner; direction from squeeze momentum
- STRAT-V046 Volatility contraction pattern breakout -> parent STRAT-071: successively smaller pullbacks, then breakout
- STRAT-V047 Inside-bar breakout bracket -> parent STRAT-072: trigger: inside bar instead of NR7
- STRAT-V048 NR4 inside-bar bracket -> parent STRAT-072: NR4 and inside bar together
- STRAT-V049 Bollinger band breakout -> parent STRAT-073: Bollinger(20,2) bands
- STRAT-V050 Marubozu continuation -> parent STRAT-074: trigger defined by candle body >= 90% of range
- STRAT-V051 Doji at prior-session level -> parent STRAT-076: doji instead of hammer
- STRAT-V052 Change of character -> parent STRAT-080: first break against the prior trend
- STRAT-V053 Accumulation/distribution divergence -> parent STRAT-091: Chaikin A/D line instead of OBV
- STRAT-V054 OBV-led breakout -> parent STRAT-091: OBV at a 50-bar high before price
- STRAT-V055 Estimated-delta trend (labelled estimate) -> parent STRAT-093: close-location x volume estimate
- STRAT-V056 Elder-ray bull-power pullback -> parent STRAT-094: bull power (high - EMA13) instead of force index
- STRAT-V057 Bitcoin first-half-hour -> last-half-hour -> parent STRAT-097: market: crypto, UTC day
- STRAT-V058 Crypto hour-of-day seasonality -> parent STRAT-098: market: crypto, 1-hour buckets
- STRAT-V059 Pre-FOMC bitcoin drift -> parent STRAT-103: market: crypto
- STRAT-V060 CPI-day opening-range breakout -> parent STRAT-104: ORB only on CPI days
- STRAT-V061 Post-earnings first-day continuation -> parent STRAT-105: VWAP hold instead of ORB
- STRAT-V062 QQQ/SPY spread reversion (one leg) -> parent STRAT-107: pair of ETFs instead of stock vs index
- STRAT-V063 BTC leads COIN/MSTR -> parent STRAT-109: follower: US crypto stocks
- STRAT-V064 SPY leads IWM -> parent STRAT-109: leader SPY, follower small caps
- STRAT-V065 Stablecoin premium signal -> parent STRAT-112: USDT-USD deviation instead of cross-venue premium
- STRAT-V066 Hurst-exponent regime switch -> parent STRAT-135: Hurst exponent instead of variance ratio
