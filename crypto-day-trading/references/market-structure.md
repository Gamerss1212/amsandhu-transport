# Market Structure

How to read a crypto chart without indicators. Everything else in this skill sits on
top of this file.

## Contents

1. Swings and trend
2. Break of structure vs change of character
3. Ranges
4. Support and resistance that actually matters
5. Liquidity, equal highs/lows, stop hunts
6. Order blocks and fair value gaps (imbalance)
7. Multi-timeframe analysis
8. The crypto clock: sessions, closes, settlement
9. Candle patterns worth knowing
10. A worked read

---

## 1. Swings and trend

A **swing high** is a candle whose high is higher than the N candles on each side of
it (N = 2 or 3 for intraday work). A **swing low** is the mirror. `scripts/snapshot.py`
marks them automatically; on a chart you can eyeball them.

Trend is defined by the sequence of swings, nothing else:

- **Uptrend**: higher highs (HH) and higher lows (HL). The higher lows are what
  matter. Buyers are stepping in earlier each time.
- **Downtrend**: lower highs (LH) and lower lows (LL). The lower highs matter.
- **Range**: swings overlap. Price is bouncing between a ceiling and a floor.

Why this matters for expectancy: in an uptrend, buying pullbacks to a higher low has
a structural reason to work (the people who bought the last low are defending it).
Buying because "RSI is oversold" in a downtrend has no such reason.

The most recent swing low in an uptrend is the **trend-defining low**. Lose it and
the uptrend is, by definition, over on that timeframe.

## 2. Break of structure vs change of character

- **Break of structure (BOS)**: price takes out the previous swing high in an
  uptrend (or swing low in a downtrend). Trend continuation. Expect a pullback after
  a BOS; the pullback is the trade, not the breakout candle.
- **Change of character (CHoCH)**: price takes out the most recent higher low in an
  uptrend (or lower high in a downtrend). First warning the trend may be shifting.
  One CHoCH does not make a reversal; it makes the next swing decisive.

The sequence that produces the highest-quality reversals: CHoCH, then a failed
attempt to make a new high (a lower high), then a break of the low that the failed
attempt made. That is three confirmations. Traders who short the first CHoCH get
chopped up in what turns out to be a deeper pullback.

Use candle **closes**, not wicks, to confirm a break on the timeframe you are
trading. Wicks through a level that close back inside are the opposite signal
(see liquidity, below).

## 3. Ranges

Crypto spends most of its time ranging. A range is confirmed when price has touched
both a ceiling and a floor at least twice and the swings in between overlap.

Inside a range:

- The **edges** are where the trades are. The **middle** is where the losses are.
- The first test of an edge usually holds. Each subsequent test weakens it; by the
  third or fourth touch, a breakout is more likely than a rejection because the
  stops resting beyond the edge have grown.
- The range's **midpoint** (equilibrium) is where price gravitates after a failed
  breakout. It is the natural target for a fade from an edge.
- **Deviation**: price pokes outside the range and closes back in within a candle or
  two. That is a failed breakout and it often runs to the opposite edge. High
  quality signal.

Range height in ATR terms tells you if it is tradeable: a range that is 1 ATR tall
cannot fit a stop plus a 2R target. Skip it or drop to a lower timeframe.

## 4. Support and resistance that actually matters

Rank levels. Not all lines are equal. In rough order of how much attention the
market pays:

1. **Prior day high and low (PDH / PDL)** and the **daily open**. Every algorithm and
   every desk has these on screen.
2. **Weekly high/low and open**, **monthly open**. Bigger version of the same thing.
3. **Range highs and lows** on the 4H and 1D.
4. **Swing highs/lows** on the timeframe you trade, especially ones that produced a
   strong move away (the move proves someone big was there).
5. **Round numbers** (60,000; 3,000; 150). Retail limit orders cluster there.
6. **Prior session high/low** (Asia, London, New York).
7. **High-volume nodes**: price areas where lots of volume traded (a volume profile
   shows these; without one, look for where price consolidated longest).
8. **The 200 EMA and the session VWAP** (dynamic levels; see `indicators.md`).

A level that has been tested and held is useful. A level that has been tested many
times is fragile. A level that price blew through on volume and has not returned
to is now the opposite kind of level (old resistance becomes support) and is a
strong retest candidate.

Draw levels as **zones**, not lines. Use the candle bodies and the wick extremes to
define the zone. The width of the zone should be about 0.25-0.5 ATR on the timeframe.

## 5. Liquidity, equal highs/lows, stop hunts

The single most useful idea in this file.

Every stop-loss order is a market order waiting to happen. Traders who bought
support put stops just below it. Traders who shorted resistance put stops just
above it. Where stops cluster there is **liquidity**: a pool of forced orders that
large players can trade into.

Where stops cluster:

- Just beyond **equal highs** or **equal lows** (two or more swings at nearly the same
  price). These are magnets. Expect price to run through them before reversing.
- Just beyond obvious **trendlines** everyone can see.
- Just beyond the **PDH / PDL** and range edges.
- Just beyond a **big round number**.

A **liquidity sweep** (stop hunt, "wick") is when price spikes through one of these
pools, triggers the stops, and then closes back inside. The tell is the close: a
candle that pierces equal lows and closes back above them means sellers were
absorbed. That is one of the highest-probability reversal signals in crypto because
it is mechanical: the forced sellers are exhausted and the buyers who absorbed them
are now in profit and defending.

Practical rules:

- Do not place a stop exactly at an obvious level. Put it beyond where the sweep
  would go (roughly 0.3-0.5 ATR past the level) or accept a smaller position.
- Do not buy the first touch of equal lows. Wait for the sweep and reclaim.
- If price sweeps a level and does **not** reclaim within a couple of candles, it
  was a real breakout, not a sweep. Do not fade it.

## 6. Order blocks and fair value gaps (imbalance)

These come from "smart money concepts" and the evidence for them is anecdotal
rather than rigorous. Treat them as a way to find **where a strong move started**,
which is a sensible place to expect a reaction, and nothing more mystical.

- **Order block**: the last opposite-colored candle (or small cluster) before an
  impulsive move that broke structure. A bullish order block is the last red candle
  before a strong rally that made a BOS. When price returns to it, buyers who
  started the rally may defend. Use the candle body, not the wick, as the zone.
- **Fair value gap (FVG)** / imbalance: a three-candle sequence where the first
  candle's high and the third candle's low do not overlap (for a bullish gap). Price
  moved so fast that it left a hole. Price often returns to fill part of the gap
  before continuing. The 50% of the gap is a common reaction point.

Use them only **with** trend and only as zones for a pullback entry. An order block
against the HTF trend is just a candle.

## 7. Multi-timeframe analysis

The most reliable edge available to a discretionary day trader is trading in the
direction of the higher timeframe. It is boring and it works.

| Role | Timeframes | Question |
|---|---|---|
| Bias | 1D, 4H | Which direction should I be looking? Or is it a range (then trade edges)? |
| Setup | 1H, 15m | Is price at a location that makes sense (pullback to value, range edge, post-sweep)? |
| Trigger | 5m, 1m | Has the lower timeframe confirmed the turn (CHoCH, reclaim, engulfing candle)? |

Rules:

- **Alignment**: bias, setup, and trigger all point the same way. That is an A setup.
- **Counter-trend**: bias says down, but a 15m sweep-and-reclaim at a 4H level says
  up. That is a B setup: smaller size, faster target (the first LTF resistance),
  tighter management.
- **Conflict without a reason**: bias says down, 15m just looks "oversold". No
  trade.
- When the higher timeframe is a range, the bias is "fade the edges, and expect the
  breakout to fail the first time".

Do the top-down read every single time. Write one line per timeframe. It takes
sixty seconds and prevents most bad trades.

## 8. The crypto clock: sessions, closes, settlement

Crypto trades 24/7 but volume and behavior are not uniform.

Times below are UTC during **US summer time** (mid-March to early November). In
US winter time every New York-linked time (data releases, equities open/close,
FOMC, CME hours) is **one hour later in UTC**; London-linked times move one hour
later from late October to late March. `scripts/events.py` does the conversion.

| UTC | What happens |
|---|---|
| 00:00 | Daily candle close and open (Binance/most exchanges). Funding settlement on most perps. Frequently the day's high or low is set within an hour of it. |
| 00:00-07:00 | **Asia session.** Usually lower volume, ranging, sets the "Asia range" that London often breaks. |
| 07:00-08:00 | London open. First real directional attempt of the day. Often sweeps the Asia high or low. |
| 08:00 | Funding settlement. Deribit options expiry (daily 08:00, monthly last Friday). |
| 12:30-13:30 | US economic data releases (CPI, NFP at 12:30 UTC; FOMC decision at 18:00 UTC). |
| 13:30 | **US equities open.** The highest-impact hour of the crypto day. Volume, volatility, and the correlation with Nasdaq all spike. |
| 13:30-16:00 | London / New York overlap. Best liquidity, best trends, best breakouts. |
| 16:00 | Funding settlement. London close. |
| 20:00-21:00 | US equities close. Volume dries up fast afterwards. |
| 21:00 Fri to 22:00 Sun (22:00 / 23:00 in US winter) | **CME closed.** Bitcoin CME futures gap forms; weekend moves are thin and often retrace ("gap fill") early in the week. |

Weekends: lower liquidity, larger wicks, more stop hunts, less follow-through.
Reduce size or skip. Sunday night into Monday (the CME reopen at 22:00 UTC Sunday in summer, 23:00 in winter)
frequently produces a sharp move.

Funding settlement (00/08/16 UTC): if funding is extreme, expect positioning to
shift in the hour before settlement as traders close to avoid paying it.

## 9. Candle patterns worth knowing

Only a few, and only **at a level**. A pattern in the middle of nowhere is noise.

- **Engulfing**: candle body fully covers the previous candle's body in the opposite
  direction. At a level, it is a clean trigger.
- **Pin bar / long wick rejection**: a wick at least twice the body, pointing into a
  level. This is the candle form of a liquidity sweep.
- **Inside bar**: candle entirely inside the previous one. Compression; trade the
  break of the mother bar in the trend direction.
- **Doji at a level after an extended move**: indecision; wait for the next candle.
- **Three consecutive expanding candles into a level** (climax): exhaustion is
  likely. Do not chase the third candle.

## 10. A worked read

BTC, 2026-09-14 09:40 UTC (illustrative numbers).

- **1D**: HH/HL uptrend since late August. Last daily swing low 61,800. Price 64,900,
  above the 200 EMA (58,300) and 21 EMA (63,700). Bias: up.
- **4H**: pulled back from 66,400 (HH) to 63,900 and bounced. HL confirmed at 63,900
  if 4H closes above 65,100 (the last 4H lower high). Currently 64,900: unconfirmed.
- **1H**: range 63,900-65,100 for 14 hours. Equal highs at 65,080/65,110: stops
  stacked above.
- **15m**: swept 63,900 at 08:05 UTC during London open (wick to 63,760), closed back
  above 63,950 on 2.1x average volume. Since then HL at 64,300.
- **Context**: funding +0.008% (neutral), OI flat, London session, US open in 3h50m,
  no tier-1 data today.

Read: the London-open sweep of the range low plus reclaim is a bullish liquidity
sweep inside an HTF uptrend. The equal highs at 65,100 are the obvious target and
the obvious liquidity, so expect price to run them. A long above 64,300 (the
post-sweep HL) with a stop under the sweep wick at 63,700 (~1.9% or 0.9 ATR) targets
65,100 first (1.3R) and the 4H HH at 66,400 second (3.5R). The plan is a B+ setup:
aligned bias, structural location, confirmed trigger; the one weakness is that the
first target is only 1.3R, so the plan must scale rather than take full profit at
65,100. Confidence: medium. What kills it: a 15m close below 64,300 turns the reclaim
into a lower high inside the range.
