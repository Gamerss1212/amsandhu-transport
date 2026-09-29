"""Knowledge-pack hypotheses formalized as executable rules (6 core, 14 memecoin).

Every threshold below was fixed (see PREREGISTRATION_PACK.md) before any test was run, with a search
budget of one configuration per hypothesis: nothing here was tuned on results. The pack supplies the
idea, the data needs and the falsification test; the exact rule is this library's own formalization,
so research status is "hypothesis" and the pack sources are cited as context only.

Memecoin rules run on the six memecoins listed on Coinbase (DOGE, SHIB, PEPE, BONK, WIF, FLOKI) using
exchange price bars. They are survivors (tokens that lasted long enough to be listed), so any result
is biased upward relative to the on-chain launch universe the pack describes.
"""
from lib import CRYPTO, STOCK, st
from pack import MEMES, pack_evidence

CRY_DAY = {"flat_minutes_before_close": 5}


def breadth(ema_n=20):
    """Number of the six memecoins closing above their own EMA (0..6)."""
    return "(" + " + ".join(f'iff(sym("{s}", close > ema(close,{ema_n})), 1, 0)' for s in MEMES) + ")"


def meme_max(expr):
    """The largest value of `expr` across the six memecoins (the current one included)."""
    parts = [f'sym("{s}", {expr})' for s in MEMES]
    while len(parts) > 1:
        parts = [f"max({parts[i]}, {parts[i + 1]})" if i + 1 < len(parts) else parts[i] for i in range(0, len(parts), 2)]
    return parts[0]


B = breadth()

# ------------------------------------------------------------------ core (stocks and crypto)
BR = "cross_above(close, highest(high,48)[1])"
BS = "cross_below(close, lowest(low,48)[1])"
st("range_breakout_retest", "Range-boundary breakout retest", "volatility", "breakout retest",
   mech="a broken range boundary is defended on the first retest", logic="continuation (retest)",
   anchor="48-bar range high/low frozen at the breakout bar",
   hyp="After a close beyond the prior 48-bar range, the first pullback within 2-12 bars that holds the frozen boundary (within 0.1 ATR) and closes back beyond it offers entry; stop 0.5 ATR through the boundary; target 2R.",
   tf="5m",
   entry={"long": f"since({BR}) >= 2 and since({BR}) <= 12 and low <= valuewhen({BR}, highest(high,48)[1]) + 0.1*atr(14) and close > valuewhen({BR}, highest(high,48)[1]) and close > open",
          "short": f"since({BS}) >= 2 and since({BS}) <= 12 and high >= valuewhen({BS}, lowest(low,48)[1]) - 0.1*atr(14) and close < valuewhen({BS}, lowest(low,48)[1]) and close < open"},
   stop={"type": "level", "long": f"valuewhen({BR}, highest(high,48)[1]) - 0.5*atr(14)", "short": f"valuewhen({BS}, lowest(low,48)[1]) + 0.5*atr(14)"},
   target={"type": "r", "r": 2.0}, mtd=2, ev=pack_evidence("ST004"), research="hypothesis",
   fail=["retests often fail in ranging sessions", "the boundary is only one of many possible range definitions"],
   distinct="Any 48-bar range, not the opening range (orb_retest).")

st("tsmom_vol_scaled", "Volatility-normalized time-series momentum", "trend_following", "time-series momentum",
   mech="returns scaled by their own volatility persist over short horizons", logic="momentum",
   anchor="48-bar log return in units of its volatility",
   hyp="Enter when the 48-bar (12-hour on 15m) log return crosses one volatility unit in its direction; exit when the return changes sign or after 96 bars; 3-ATR stop.",
   tf="15m",
   entry={"long": "cross_above(log(close/close[48]) / (realized_vol(48).per_bar * sqrt(48)), 1)",
          "short": "cross_below(log(close/close[48]) / (realized_vol(48).per_bar * sqrt(48)), -1)"},
   exit={"long": "close < close[48]", "short": "close > close[48]"},
   stop={"type": "atr", "mult": 3.0, "n": 14}, max_bars=96, mtd=2, ev=pack_evidence("ST009"), research="hypothesis",
   fail=["momentum reverses at news shocks", "volatility estimate lags regime changes"],
   distinct="Volatility-normalized threshold, unlike the previous-day sign rule (trend_return_sign).")

st("rsi_extreme_recovery", "RSI extreme recovery", "mean_reversion", "oscillator recovery",
   mech="an oversold/overbought reading that starts to normalize signals exhaustion of the move", logic="reversal",
   anchor="RSI(14) crossing back through 30 / 70",
   hyp="Buy when RSI(14) crosses back above 30 (sell when it crosses back below 70); exit at RSI 50, after 48 bars, or at a 2.5-ATR stop.",
   tf="15m",
   entry={"long": "cross_above(rsi(close,14), 30)", "short": "cross_below(rsi(close,14), 70)"},
   exit={"long": "rsi(close,14) > 50", "short": "rsi(close,14) < 50"},
   stop={"type": "atr", "mult": 2.5, "n": 14}, max_bars=48, mtd=3, ev=pack_evidence("ST023"), research="hypothesis",
   fail=["strong trends keep RSI extreme", "recovery crosses whipsaw near the threshold"],
   distinct="No trend filter and a recovery trigger, unlike RSI(2) in an uptrend (rsi2_pullback).")

st("fomc_post_reaction", "FOMC post-announcement drift", "scheduled_events", "central bank",
   mech="the first 30 minutes after the FOMC statement set the direction for the rest of the session", logic="event continuation",
   anchor="price at 13:55 ET vs 14:30 ET on FOMC days",
   hyp="On FOMC days, at 14:30 ET enter in the direction of the move since 13:55 ET if it exceeds 3 five-minute ATRs; hold to 5 minutes before the close; 3-ATR stop.",
   markets=STOCK, tf="5m", instruments=["SPY", "QQQ"], data=("bars", "events:fomc"),
   entry={"long": "event(\"fomc\") == 1 and tod() == 870 and close - valuewhen(tod() == 835, close) > 3*atr(14)",
          "short": "event(\"fomc\") == 1 and tod() == 870 and close - valuewhen(tod() == 835, close) < -3*atr(14)"},
   stop={"type": "atr", "mult": 3.0, "n": 14}, mtd=1, session={"flat_minutes_before_close": 5},
   ev=pack_evidence("ST045"), research="hypothesis",
   fail=["about eight events a year: too few trades to judge", "the first move after the statement is often reversed during the press conference"])

SW = "within(low < swings(3).low and close > swings(3).low, 12)"
SH = "within(high > swings(3).high and close < swings(3).high, 12)"
st("sweep_structure_shift", "Liquidity sweep then structure shift", "market_structure", "liquidity",
   mech="stops below a swing low are taken, then buyers regain control by breaking the last swing high", logic="reversal (sweep + shift)",
   anchor="latest confirmed 3-bar swing high/low",
   hyp="Within 12 bars after price trades below the latest swing low and closes back above it, buy the close that breaks the latest swing high; stop 0.2 ATR under the 12-bar low; target 2R (mirror for shorts).",
   tf="5m",
   entry={"long": f"cross_above(close, swings(3).high) and {SW}", "short": f"cross_below(close, swings(3).low) and {SH}"},
   stop={"type": "level", "long": "lowest(low,12) - 0.2*atr(14)", "short": "highest(high,12) + 0.2*atr(14)"},
   target={"type": "r", "r": 2.0}, mtd=2, ev=pack_evidence("ST098"), research="hypothesis",
   fail=["the shift can come after the move is mostly over", "swing definitions change the signal a lot"],
   distinct="Requires both the sweep and a later swing-high break, unlike turtle_soup (sweep reclaim only).")

DL = "close - open > 1.5*atr(14) and close > highest(high,10)[1] and close[1] < open[1]"
DS = "open - close > 1.5*atr(14) and close < lowest(low,10)[1] and close[1] > open[1]"
st("order_block_retest", "Order-block retest", "market_structure", "order block",
   mech="the last opposite candle before a displacement marks where large orders entered; price revisits it", logic="continuation (retest)",
   anchor="last bearish candle before a 1.5-ATR bullish displacement (mirror for shorts)",
   hyp="After a bullish displacement bar (body > 1.5 ATR, new 10-bar high) that follows a bearish candle, buy the first retest 3-30 bars later that touches that candle's high and closes above it; stop 0.1 ATR under its low; target 2R.",
   tf="5m",
   entry={"long": f"since({DL}) >= 3 and since({DL}) <= 30 and low <= valuewhen({DL}, high[1]) and close > valuewhen({DL}, high[1]) and close > open",
          "short": f"since({DS}) >= 3 and since({DS}) <= 30 and high >= valuewhen({DS}, low[1]) and close < valuewhen({DS}, low[1]) and close < open"},
   stop={"type": "level", "long": f"valuewhen({DL}, low[1]) - 0.1*atr(14)", "short": f"valuewhen({DS}, high[1]) + 0.1*atr(14)"},
   target={"type": "r", "r": 2.0}, mtd=2, ev=pack_evidence("ST099"), research="hypothesis",
   fail=["zones are defined after the fact in most teaching material; here they are frozen at the displacement bar",
         "many zones are never revisited"])

# ------------------------------------------------------------------ memecoins (six Coinbase-listed tokens)
MEME_NOTE = "Tested on exchange-listed memecoins (survivors), not on the on-chain launch universe the pack describes."
st("meme_breadth_momentum", "Memecoin breadth-led momentum", "memecoin", "narrative rotation",
   mech="when most memecoins trend together, attention is flowing into the whole theme", logic="momentum (breadth)",
   anchor="count of the six memecoins above their 20-bar EMA",
   hyp="Buy a memecoin when meme breadth rises from 3 or fewer to 4 or more of 6 above their 20-bar EMA while it is itself above that EMA; 3-ATR stop, 2R target.",
   markets=CRYPTO, tf="15m", instruments=MEMES, direction="long",
   entry={"long": f"cross_above({B}, 3.5) and close > ema(close,20)"},
   stop={"type": "atr", "mult": 3.0, "n": 14}, target={"type": "r", "r": 2.0}, mtd=2, session=CRY_DAY,
   ev=pack_evidence("ST181"), research="hypothesis", notes=MEME_NOTE, fail=["breadth flips often in chop"])
st("meme_leader_pullback", "Memecoin leader pullback", "memecoin", "narrative rotation",
   mech="the theme leader's orderly pullbacks get bought while the theme stays strong", logic="continuation (pullback)",
   anchor="DOGE (largest memecoin) and meme breadth",
   hyp="Buy DOGE when it is above its 50-bar EMA, dips to its 20-bar EMA and closes up, while at least 4 of 6 memecoins are above their 20-bar EMA; 3-ATR stop, 2R target.",
   markets=CRYPTO, tf="15m", instruments=["DOGE-USD"], direction="long",
   entry={"long": f"close > ema(close,50) and low <= ema(close,20) and close > ema(close,20) and close > open and {B} >= 4"},
   stop={"type": "atr", "mult": 3.0, "n": 14}, target={"type": "r", "r": 2.0}, mtd=2, session=CRY_DAY,
   ev=pack_evidence("ST182"), research="hypothesis", notes=MEME_NOTE, fail=["a leader change leaves the old leader behind"])
st("meme_laggard_breakout", "Memecoin laggard catch-up breakout", "memecoin", "narrative rotation",
   mech="laggards in a strong theme catch up once they break out", logic="breakout (catch-up)",
   anchor="token's 24-bar return below DOGE's while breadth is high",
   hyp="Buy a memecoin whose 24-bar return trails DOGE's when it closes above its prior 20-bar high while at least 4 of 6 memecoins are above their 20-bar EMA; 3-ATR stop, 2R target.",
   markets=CRYPTO, tf="15m", instruments=["SHIB-USD", "PEPE-USD", "BONK-USD", "WIF-USD", "FLOKI-USD"], direction="long",
   entry={"long": f'roc(close,24) < sym("DOGE-USD", roc(close,24)) and cross_above(close, donchian(20).upper[1]) and {B} >= 4'},
   stop={"type": "atr", "mult": 3.0, "n": 14}, target={"type": "r", "r": 2.0}, mtd=2, session=CRY_DAY,
   ev=pack_evidence("ST183"), research="hypothesis", notes=MEME_NOTE, fail=["laggards often lag for a reason"])
st("meme_leader_follower_lag", "Memecoin leader-to-follower transmission", "memecoin", "narrative rotation",
   mech="a shock in the leading memecoin reaches smaller ones with a delay", logic="lead-lag",
   anchor="DOGE 3-bar return z-score vs the follower's",
   hyp="When DOGE's 3-bar return z-score (96 bars) exceeds 2 while the follower's is below 1, buy the follower; exit after 8 bars; 2-ATR stop.",
   markets=CRYPTO, tf="5m", instruments=["SHIB-USD", "PEPE-USD", "BONK-USD", "WIF-USD", "FLOKI-USD"], direction="long",
   entry={"long": 'sym("DOGE-USD", zscore(roc(close,3), 96)) > 2 and zscore(roc(close,3), 96) < 1'},
   stop={"type": "atr", "mult": 2.0, "n": 14}, max_bars=8, mtd=3, session=CRY_DAY,
   ev=pack_evidence("ST186"), research="hypothesis", notes=MEME_NOTE, fail=["the lag may be too short for bar-close execution"])
st("meme_btc_riskon", "Bitcoin risk-on memecoin participation", "memecoin", "market regime",
   mech="when bitcoin turns up, speculative risk appetite spills into memecoins", logic="regime change",
   anchor="BTC crossing above its 96-bar EMA (one day of 15-minute bars)",
   hyp="Buy a memecoin when BTC closes back above its 96-bar EMA and at least 3 of 6 memecoins are above their 20-bar EMA; 3-ATR stop, 2R target.",
   markets=CRYPTO, tf="15m", instruments=MEMES, direction="long",
   entry={"long": f'sym("BTC-USD", cross_above(close, ema(close,96))) and {B} >= 3'},
   stop={"type": "atr", "mult": 3.0, "n": 14}, target={"type": "r", "r": 2.0}, mtd=2, session=CRY_DAY,
   ev=pack_evidence("ST222"), research="hypothesis", notes=MEME_NOTE, fail=["BTC crosses whipsaw in ranges"])
st("meme_resilient_rebound", "Selloff-resilient memecoin rebound", "memecoin", "market regime",
   mech="tokens that held up during a market selloff lead the rebound", logic="relative strength rebound",
   anchor="BTC 1-day low in the last 24 bars; token beat BTC over 48 bars",
   hyp="After BTC printed a 96-bar low within the last 24 bars but none in the last 8, buy a memecoin whose 48-bar return beats BTC's when it breaks its prior 8-bar high; 3-ATR stop, 2R target.",
   markets=CRYPTO, tf="15m", instruments=MEMES, direction="long",
   entry={"long": 'sym("BTC-USD", since(low <= lowest(low,96))) >= 8 and sym("BTC-USD", since(low <= lowest(low,96))) <= 24 and roc(close,48) > sym("BTC-USD", roc(close,48)) and cross_above(close, highest(high,8)[1])'},
   stop={"type": "atr", "mult": 3.0, "n": 14}, target={"type": "r", "r": 2.0}, mtd=2, session=CRY_DAY,
   ev=pack_evidence("ST223"), research="hypothesis", notes=MEME_NOTE, fail=["a second selloff leg"])
st("meme_residual_reversion", "Memecoin residual reversion vs bitcoin", "memecoin", "market regime",
   mech="a memecoin's move unexplained by bitcoin tends to partly reverse", logic="reversion",
   anchor="z-score of the token-vs-BTC spread over 96 bars",
   hyp="Buy when the token-vs-BTC spread z-score crosses back above -2 from below; exit when it reaches 0; 2.5-ATR stop; 96-bar limit.",
   markets=CRYPTO, tf="15m", instruments=MEMES, direction="long",
   entry={"long": 'cross_above(spread_z(close, sym("BTC-USD", close), 96), -2)'},
   exit={"long": 'spread_z(close, sym("BTC-USD", close), 96) > 0'},
   stop={"type": "atr", "mult": 2.5, "n": 14}, max_bars=96, mtd=2, session=CRY_DAY,
   ev=pack_evidence("ST224"), research="hypothesis", notes=MEME_NOTE, fail=["token-specific news makes the residual permanent"])
st("meme_squeeze_release", "Memecoin volatility contraction release", "memecoin", "market regime",
   mech="compressed memecoin ranges resolve in large moves; a calm BTC keeps the move token-driven", logic="breakout (volatility)",
   anchor="Bollinger/Keltner squeeze ending; BTC normalized ATR below 1.5x its 96-bar mean",
   hyp="Buy when the 20-bar squeeze ends with a close above the prior 20-bar high while BTC's normalized ATR is under 1.5 times its 96-bar average; 3-ATR stop, 2R target.",
   markets=CRYPTO, tf="15m", instruments=MEMES, direction="long",
   entry={"long": 'squeeze(20).on[1] == 1 and squeeze(20).on == 0 and close > donchian(20).upper[1] and sym("BTC-USD", natr(14) < 1.5*sma(natr(14),96))'},
   stop={"type": "atr", "mult": 3.0, "n": 14}, target={"type": "r", "r": 2.0}, mtd=2, session=CRY_DAY,
   ev=pack_evidence("ST225"), research="hypothesis", notes=MEME_NOTE, fail=["squeezes often release downward"])
st("meme_session_handover", "Memecoin session-handover continuation", "memecoin", "market regime",
   mech="new regional traders arriving at the London and New York opens push existing moves", logic="session breakout",
   anchor="07:00 and 13:30 UTC opens; same-time-of-day relative volume",
   hyp="In the first 30 minutes after 07:00 or 13:30 UTC, buy a memecoin that breaks its prior 8-bar high on at least 1.5x its usual volume for that time of day; 3-ATR stop, 2R target.",
   markets=CRYPTO, tf="15m", instruments=MEMES, direction="long",
   entry={"long": '(time_between("07:00", "07:30") or time_between("13:30", "14:00")) and rvol_tod(14) > 1.5 and cross_above(close, highest(high,8)[1])'},
   stop={"type": "atr", "mult": 3.0, "n": 14}, target={"type": "r", "r": 2.0}, mtd=2, session=CRY_DAY,
   ev=pack_evidence("ST227"), research="hypothesis", notes=MEME_NOTE, fail=["session effects in crypto are weak and unstable"])
SHOCK = 'sym("BTC-USD", zscore(roc(close,4), 96) < -2.5)'
st("meme_aftershock_reclaim", "Memecoin liquidation-aftershock reclaim", "memecoin", "market regime",
   mech="forced selling during a bitcoin shock overshoots in memecoins, which recover once they reclaim the pre-shock level", logic="reversal (reclaim)",
   anchor="BTC 4-bar return z-score below -2.5 in the last 16 bars; token open at the shock bar",
   hyp="Within 16 bars of a BTC shock (4-bar return z-score < -2.5), buy a memecoin that closes back above its open at the shock bar; 3-ATR stop, 2R target.",
   markets=CRYPTO, tf="15m", instruments=MEMES, direction="long",
   entry={"long": f"since({SHOCK}) <= 16 and cross_above(close, valuewhen({SHOCK}, open))"},
   stop={"type": "atr", "mult": 3.0, "n": 14}, target={"type": "r", "r": 2.0}, mtd=1, session=CRY_DAY,
   ev=pack_evidence("ST229"), research="hypothesis", notes=MEME_NOTE, fail=["cascades come in waves"])
RATIO = 'close / sym("SOL-USD", close)'
st("meme_native_ratio_breakout", "Memecoin native-price range breakout", "memecoin", "intraday structure",
   mech="Solana memecoins priced in SOL show whether demand is token-specific rather than a SOL move", logic="breakout (ratio)",
   anchor="token/SOL price ratio and its 48-bar high",
   hyp="Buy a Solana memecoin (BONK, WIF) when its SOL-denominated price closes above its prior 48-bar high and the USD price is above its 20-bar EMA; 3-ATR stop, 2R target.",
   markets=CRYPTO, tf="15m", instruments=["BONK-USD", "WIF-USD"], direction="long",
   entry={"long": f"{RATIO} > highest({RATIO}, 48)[1] and close > ema(close,20)"},
   stop={"type": "atr", "mult": 3.0, "n": 14}, target={"type": "r", "r": 2.0}, mtd=2, session=CRY_DAY,
   ev=pack_evidence("ST233"), research="hypothesis", notes=MEME_NOTE, fail=["ratio breakouts can be SOL weakness, not token strength"])
R12, R48, R192 = "(highest(high,12)-lowest(low,12))", "(highest(high,48)-lowest(low,48))", "(highest(high,192)-lowest(low,192))"
st("meme_nested_compression_breakout", "Two-stage compression breakout", "memecoin", "intraday structure",
   mech="a tight range inside a tight range stores energy; the break of the inner range starts the move", logic="breakout (compression)",
   anchor="12-bar range under half the 48-bar range, which is under 0.7 of the 192-bar range",
   hyp="When the 12-bar range is under half the 48-bar range and the 48-bar range is under 0.7 of the 192-bar range, buy the close above the 12-bar high; 3-ATR stop, 2R target.",
   markets=CRYPTO, tf="5m", instruments=MEMES, direction="long",
   entry={"long": f"{R12}[1] < 0.5*{R48}[1] and {R48}[1] < 0.7*{R192}[1] and close > highest(high,12)[1]"},
   stop={"type": "atr", "mult": 3.0, "n": 14}, target={"type": "r", "r": 2.0}, mtd=2, session=CRY_DAY,
   ev=pack_evidence("ST234"), research="hypothesis", notes=MEME_NOTE, fail=["compression can resolve downward"])
st("meme_midpoint_acceptance", "Selloff-range midpoint acceptance", "memecoin", "intraday structure",
   mech="after a selloff, holding above the range midpoint shows sellers are done", logic="reversal (acceptance)",
   anchor="midpoint of the last 96 bars after a fresh 96-bar low",
   hyp="Within 48 bars of a 96-bar low, buy when the last 4 bars' lows all held above the 96-bar range midpoint; stop 0.5 ATR under the midpoint; target the 96-bar high.",
   markets=CRYPTO, tf="15m", instruments=MEMES, direction="long",
   entry={"long": "since(low <= lowest(low,96)) <= 48 and persist(low > (highest(high,96)+lowest(low,96))/2, 4) and not persist(low > (highest(high,96)+lowest(low,96))/2, 5)"},
   stop={"type": "level", "long": "(highest(high,96)+lowest(low,96))/2 - 0.5*atr(14)"},
   target={"type": "level", "long": "highest(high,96)"}, mtd=1, session=CRY_DAY,
   ev=pack_evidence("ST239"), research="hypothesis", notes=MEME_NOTE, fail=["dead-cat bounces"])
st("meme_relative_momentum_leader", "Memecoin relative-momentum leader", "memecoin", "relative value",
   mech="the memecoin with the strongest recent return keeps attracting attention", logic="cross-sectional momentum (long only)",
   anchor="24-bar return rank among the six memecoins",
   hyp="Buy the memecoin with the highest 24-bar return of the six when it becomes the leader and is above its 20-bar EMA; exit when it loses the lead; 3-ATR stop.",
   markets=CRYPTO, tf="15m", instruments=MEMES, direction="long",
   entry={"long": f"roc(close,24) >= {meme_max('roc(close,24)')} and not (roc(close,24)[1] >= {meme_max('roc(close,24)')}[1]) and close > ema(close,20)"},
   exit={"long": f"roc(close,24) < {meme_max('roc(close,24)')}"},
   stop={"type": "atr", "mult": 3.0, "n": 14}, mtd=2, session=CRY_DAY,
   ev=pack_evidence("ST271"), research="hypothesis", notes=MEME_NOTE, fail=["leadership rotates quickly among memecoins"])
