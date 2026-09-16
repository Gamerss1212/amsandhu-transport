# Worked Examples

Five complete interactions, produced with the bundled scripts on live data taken
on 2026-09-16 around 20:50 UTC (an FOMC decision day; the decision printed at
18:00 UTC). The numbers are real for that moment and stale the moment you read
them. What to copy is the *shape* of each answer: what was checked, in what order,
how the verdict was reached, and how uncertainty was stated.

## Contents

1. Analyze mode: "what do you think of BTC right now?"
2. Plan mode: "give me a long setup on BTC for tomorrow"
3. Alt request: "should I long SOL here?"
4. Scanner flag evaluation: the DOGE sweep
5. Coach mode: the user is on tilt
6. Teach mode: "explain funding rates like I'm new"

---

## 1. Analyze mode: "what do you think of BTC right now?"

**What Claude ran**

```bash
python3 scripts/fetch_ohlcv.py --symbol BTCUSDT --interval 1d  --limit 250 --out /tmp/btc_1d.csv
python3 scripts/fetch_ohlcv.py --symbol BTCUSDT --interval 4h  --limit 300 --out /tmp/btc_4h.csv
python3 scripts/fetch_ohlcv.py --symbol BTCUSDT --interval 15m --limit 600 --out /tmp/btc_15m.csv
python3 scripts/snapshot.py /tmp/btc_1d.csv /tmp/btc_4h.csv /tmp/btc_15m.csv
python3 scripts/fetch_ohlcv.py --symbol BTCUSDT --derivs
```

Binance was geo-blocked (HTTP 451); candles came from Coinbase and Kraken,
derivatives from OKX. Claude says so in the header because the funding level on
OKX is not identical to Binance's.

**What Claude wrote**

> **BTC/USD · 2026-09-16 20:50 UTC · data: Coinbase/Kraken candles (live), OKX perps**
>
> Today was FOMC day; the decision printed at 18:00 UTC and the 16:00-20:00 4H
> candle is the whipsaw: up close, body only 18% of its range, wicks 460 above and
> 780 below, on 1.9x volume. Since then the 15m volume has collapsed (RVOL 0.27).
> This is the post-event lull, which is a bad time to initiate anything.
>
> **1D**: bull regime by the EMAs (21 > 50 > 200; price 75,967 is above the 200 EMA at
> 72,207) but the swing sequence has turned: the last daily swing low at 76,030 is
> being tested from below right now, with the daily candle still open. If today
> closes under 76,030 that is a change of character on the daily, not yet a
> reversal. Daily ATR 2,240 (2.9%).
>
> **4H**: range. Last 10 days span 74,891 to 80,541; price sits at the 19th
> percentile of it. Equal highs at 79,786 (liquidity above) and equal lows around
> 76,425 that were just broken through. RSI 40, MACD histogram turning up off the
> FOMC low. 4H ATR 890.
>
> **15m**: range 74,912 to 76,500 since the London open, price mid-upper. Equal highs
> at 76,003 sit right overhead and equal lows at 75,372 below: liquidity on both
> sides within one ATR. Bullish RSI divergence on the last two 15m lows. Session VWAP
> 75,734, price above it by half an ATR.
>
> **Positioning (OKX)**: funding +0.009% per 8h (neutral), OI +2.0% over 24h (stable),
> long/short account ratio 1.72 (63% of accounts long, mildly crowded), perp basis
> slightly negative. Nothing extreme; no squeeze fuel either way.
>
> **Regime**: volatile chop today (FOMC), likely range into the Asia session.
>
> **Scenario map for the next 24h**
> - Bull (~40%): holds today's low 74,957 through Asia, sweeps the 76,003/76,030
>   equal highs at London or New York open and keeps going. First target 76,475
>   (today's high), then 78,242 (PDH). Needs volume; a sweep that closes back
>   below 76,000 is the bear trigger instead.
> - Bear (~35%): loses 74,891 (PDL and the 4H swing low) on a 4H close. Then the 1D
>   50 EMA at 73,555 and the 1D 200 EMA at 72,207 are the magnets. A daily close
>   below 76,030 tonight raises this case.
> - Chop (~25%): 74,900 to 76,500 through Asia with no resolution until the London
>   open at 07:00 UTC.
> - Deciding levels: 76,475 above, 74,891 below. Between them is noise for a day
>   trader tonight.
>
> **Verdict: WAIT.** Post-FOMC volume is dead, price is between two liquidity pools,
> and the daily structure is being decided at the close. The trades will come at
> the London open, most likely as a sweep of one side of the Asia range.
> Confidence in the WAIT: high. Confidence in the lean: low, slightly bullish
> because of the bull EMA stack and the 15m divergence, offset by the daily swing
> low being tested.
>
> This is analysis and education, not financial advice; crypto is volatile and
> leveraged positions can lose more than the margin posted.

Notes on the shape: every level traces to the snapshot output; the data sources
and their limitations are named; the regime is stated; the answer to "what do you
think" is a scenario map with a deciding level, and the verdict is WAIT with the
reasons and the time at which that changes.

## 2. Plan mode: "give me a long setup on BTC for tomorrow"

Same data. The user has said: 10,000 account, 1% risk, trades perps on OKX.

> **BTC/USDT · 15m · plan for 2026-09-17 London/NY sessions · data as of 09-16 20:50 UTC**
>
> HTF bias      : 1D bull EMA stack but swing low 76,030 under test · 4H range 74,891-80,541, price in the lower fifth
> Regime        : post-FOMC chop tonight; expect the Asia range to be swept at London (07:00 UTC)
> Setup         : Liquidity sweep reversal (playbook 4), long side
> Grade         : B (aligned with the 1D EMA regime, but the 1D swing sequence is weakening) -> risk 0.5%
> Verdict       : LONG (conditional)
>
> Trigger       : price wicks below 74,891 (PDL = 4H swing low) and a 15m candle CLOSES back above 74,891 on RVOL > 1.5. No close back above = no trade.
> Entry         : market on that close, expected ~75,000-75,100
> Stop          : 74,560  (sweep wick assumed to ~74,690 = 0.5 ATR under the level, minus a 0.3 ATR buffer; 15m ATR 410) = ~0.6%
> Invalidation  : a 15m close below 74,690 after the reclaim means the sweep was a real breakdown toward the 1D 50 EMA (73,555)
> Targets       : T1 75,585 (today's open / PDC, ~1.3R, take half) · T2 76,030 (equal highs / daily swing low retest, ~2.3R) · T3 76,475 (today's high, ~3.3R, runner)
> Size          : risk 0.5% = 50 → 50 / 490 = 0.102 BTC ≈ 7,650 notional ≈ 0.77x of account (isolated, ~3x leverage setting is plenty)
> R:R           : ~2.2R net to T2 after 0.14R of costs
> Time stop     : if T1 is not hit within 8 candles (2h), exit at market
>
> Context       : funding neutral, OI stable, L/S 1.72; no tier-1 data on 09-17 (next: NFP 10-02 12:30 UTC); funding settles 08:00 UTC
> Confidence    : low-medium. Pro: sweep-and-reclaim of a PDL in a bull EMA regime is the highest R:R setup in the book. Con: the daily may close below its swing low tonight, which would make this a counter-trend bounce; a sweep at London can also be the first leg of a trend day down.
> What kills it : no sweep (price rallies from here: then wait for the retest of 76,030 as playbook 3 instead) · daily close < 76,030 AND 4H close < 74,891 before London (then the bias is short and this plan is void) · funding flipping strongly negative overnight (shorts crowding into the level makes the squeeze bigger but the reclaim must be cleaner)
>
> Plan B (if price sweeps the highs instead): the mirror. Sweep of 76,475 that closes back below on the 15m → short, stop 0.3 ATR above the wick, targets 75,585 then 74,891. Same size logic.

```bash
python3 scripts/position_size.py --account 10000 --risk-pct 0.5 --entry 75050 --stop 74560 --target 75585 --target 76030 --target 76475 --leverage 3
python3 scripts/journal.py add --symbol BTCUSDT --playbook 4-sweep-reversal --grade B --entry 75050 --stop 74560 --target 76030 --risk-pct 0.5 --account 10000 --planned yes --notes "London-open sweep of PDL 74891; conditional on 15m reclaim close with RVOL>1.5"
```

Notes on the shape: the plan is conditional on a trigger that has not printed;
the stop is derived from the level, a sweep allowance, and an ATR buffer; the size
is computed, not felt; the plan states its own weaknesses and a Plan B; the journal
row is written before the trade.

## 3. Alt request: "should I long SOL here?"

Scanner line for SOL at 20:51 UTC: price 98.49, **HTF downtrend**, mixed stack,
**LTF downtrend**, 15m ATR 0.75%, RVOL 0.83, funding +0.004%, OI +3.3% in 24h,
long/short ratio 2.22 (69% of accounts long), basis −0.05% (perp at a discount).

> **SOL/USDT · 2026-09-16 20:51 UTC · data: Coinbase/Kraken, OKX perps**
>
> No. Not here, and not because of SOL's own chart alone.
>
> - **BTC first**: BTC is in post-FOMC chop at the low end of its 4H range with its
>   daily swing low under test. Alts carry 1.5-3x BTC's move; a SOL long is a
>   leveraged bet that BTC holds 74,891 tonight, which is the very thing we are
>   waiting to see.
> - **SOL's structure**: 4H downtrend (lower highs, lower lows) and 15m downtrend.
>   There is no higher low to buy against. A long here is a counter-trend trade
>   with no structural location.
> - **Positioning**: 69% of accounts long and OI rising 3% while price falls. That
>   is new shorts pressing into a long-heavy crowd; the perp discount confirms the
>   shorts are aggressive. The crowded side is *long*, which makes any further BTC
>   weakness a long-liquidation cascade in SOL, not a bounce.
>
> **Verdict: NO TRADE (long).** What would make a SOL long valid: BTC reclaiming
> 76,030 on a 4H close, and SOL printing a 1H higher low after sweeping its own
> session low with a reclaim (playbook 4). Then the target would be the last 4H
> lower high, and the size 0.5% because it is an alt. If BTC loses 74,891 instead,
> SOL is a short candidate on the first bounce into its 15m 21 EMA, not a long.
>
> Confidence: high that a long here is a C setup. No view on direction beyond
> "follows BTC with more beta".

## 4. Scanner flag evaluation: the DOGE sweep

`scan.py` flagged DOGE on the 4H: "SWEEP OF LOWS at 0.0784: last closed candle
wicked below and closed back above (playbook 4 long candidate)", plus a bearish
RSI divergence on the 4H, a bullish one on the 15m, and 83% of accounts long with
OI flat.

> A flag is a reason to look, not a signal. Looking:
>
> - The sweep happened on the FOMC candle. News spikes do not respect liquidity
>   pools the way organic sweeps do; the reclaim tells us less than usual.
> - 83% of accounts long is an extreme crowd on the long side. A reclaim that
>   everyone is already positioned for has less fuel than one that traps shorts.
> - The 4H bearish RSI divergence into the prior high says momentum was already
>   fading before the sweep.
> - DOGE's beta to BTC is 4-6x. With BTC undecided, the DOGE reclaim is a BTC bet
>   in disguise.
>
> Verdict: WAIT. If the sweep is real, DOGE will print a 15m higher low above
> 0.0784 in the next few hours without BTC breaking 74,891; that is the entry, with
> the stop under the 4H wick and 0.25% risk (meme sizing). Chasing the reclaim
> candle itself, on FOMC volume, with a long-crowded book, is the trade the
> scanner is *not* recommending.

## 5. Coach mode: the user is on tilt

User: "got stopped twice on BTC already today, both times it wicked me by like 50
bucks then went my way. going to 10x the next one to make it back, thoughts?"

> Two stops is −2R; the daily limit is 3R, so there is one normal trade left
> today, not a 10x trade. At 10x with the same stop distance the next loss is
> roughly 10% of the account, and today would take weeks to recover instead of a
> day.
>
> The more useful thing you said is "wicked me by 50 bucks then went my way".
> Twice. On BTC today the 15m ATR is about 410. A stop 50 away from the level is
> inside the noise; the sweep of the level *is* the setup, and the stop was where
> the setup starts, not where it fails. That is a placement problem, not bad luck,
> and it is fixable in five minutes: stop = level, minus the typical sweep
> distance (about half an ATR, ~200), minus a buffer (0.3 ATR, ~120). Smaller size
> to keep the risk at 1%, and the same trade idea would have been in profit twice
> today.
>
> Take 30 minutes off the screen. If a planned setup is still there at 21:30 UTC
> and the daily loss is under 3R, we size it at 0.5% with the corrected stop.
> Which level were the two stops at?

Notes on the shape: the coaching answer contains the technical fix. It is short,
specific, and ends with a question that pulls the user back into analysis.

## 6. Teach mode: "explain funding rates like I'm new"

> A perpetual swap is a futures contract that never expires. Without an expiry,
> nothing forces its price to match the real (spot) price, so exchanges add a
> payment between traders to do the job. That payment is the funding rate.
>
> Every 8 hours (00:00, 08:00, 16:00 UTC on most exchanges), if the perp is trading
> above spot, everyone who is long pays everyone who is short a small percentage
> of their position. That makes being long slightly expensive and being short
> slightly rewarding, which nudges the perp back toward spot. If the perp is below
> spot, shorts pay longs instead.
>
> Why a day trader cares: the sign and size of funding tell you which side the
> crowd is on and how badly they want to be there.
>
> - Around +0.01% per 8h is normal. Ignore it.
> - +0.05% and up means longs are paying a lot to stay long: the crowd is long and
>   leveraged. Trends can keep going like that for days, but when a dip comes, the
>   leveraged longs get liquidated together and the dip becomes a cascade.
> - Negative funding means shorts are paying. If price then holds a level, those
>   shorts get squeezed and the rally is fast.
>
> The rule: funding never tells you *when*. It tells you which direction the
> violent move will be if a level breaks. Use it as a filter on your trade
> (do not join a crowded side without a good reason), never as a signal by itself.
>
> Right now BTC funding is about +0.009% per 8h on OKX: neutral. Nobody is crowded.
> That is the boring, healthy state.
