"""Swing structures selected by the swing lab (results/SWING_LAB.md).

The lab tried 8 hourly setups x 48 exit structures and entry types on 5.5 years of crypto and 3 years
of stock data, chose each setup's structure on the TRAIN period only, required it to stay positive on
VALIDATION, and measured it once on the untouched TEST period (the volatility gate's). These three were
the only crypto setups positive on test after costs, and only at a low-fee exchange (0.10% taker);
at NDAX-level fees (0.20%) they were about break-even and at retail fees (0.80-1.20%) they lose. None
passed the Holm correction. They are here because they are the best-evidenced structures available,
not because they are proven: the brain judges them at the fees the owner actually pays.

The structure the lab picked everywhere is the one the cost arithmetic points to: a wide stop (4 x ATR),
a 2-3R target, holds of up to 96 hourly bars, and a limit entry 0.1% under the signal close (maker fee,
unfilled after 3 bars = no trade). Frozen exactly as selected; nothing was tuned after the test.
"""
from lib import CRYPTO, st
from pack import MEMES

OVERNIGHT = {"hold_overnight": True}
MAKER = {"type": "limit", "long": "close * 0.999", "ttl_bars": 3}
WIDE = {"type": "atr", "mult": 4.0, "n": 14}
NOTE = ("Selected by the swing lab on 2021-2025 train data (results/SWING_LAB.md). Untouched test period: positive "
        "only at a low-fee exchange (0.10% taker), about break-even at 0.20%, negative at retail fees; not significant "
        "after correction. Holds overnight and through weekends.")
FAIL = ["fees above about 0.2% per side remove the edge", "a long-only swing loses in a falling market",
        "limit entries miss the strongest moves (unfilled)"]
BO48 = "close > highest(high,48)[1]"

st("swing_rsi2_dip", "Swing RSI(2) dip in an uptrend (4 ATR, 3R, 96h, limit entry)", "swing", "hourly pullback",
   mech="short-term oversold dips inside an uptrend tend to recover over the next days",
   logic="mean reversion within trend", anchor="RSI(2) and the 200-hour EMA",
   hyp="On hourly bars, buy with a limit 0.1% under the close when RSI(2) < 10 and the close is above the 200-hour "
       "EMA; stop 4 ATR(14) below the fill, target 3R, exit after 96 bars.",
   markets=CRYPTO, tf="1h", entry={"long": "rsi(close,2) < 10 and close > ema(close,200)"}, order=MAKER, stop=WIDE,
   target={"type": "r", "r": 3.0}, max_bars=96, session=OVERNIGHT, mtd=3, ev=[("SRC-072", "mechanism", "RSI(2) dips in an uptrend")],
   research="hypothesis", fail=FAIL, notes=NOTE, instruments=["BTC-USD", "ETH-USD", "SOL-USD"],
   distinct="Hourly bars, 4 ATR stop, 96-bar hold and a maker entry (rsi2_pullback is intraday with a tight stop).")

st("swing_meme_breakout", "Swing memecoin 24-hour breakout (4 ATR, 2R, 96h, limit entry)", "swing", "hourly breakout",
   mech="memecoin breakouts to new daily highs in an uptrend tend to continue for days",
   logic="continuation", anchor="prior 24-hour high and the 200-hour EMA",
   hyp="On hourly bars, buy with a limit 0.1% under the close when the close is above the prior 24-hour high and "
       "above the 200-hour EMA; stop 4 ATR(14) below the fill, target 2R, exit after 96 bars.",
   markets=CRYPTO, tf="1h", entry={"long": "close > highest(high,24)[1] and close > ema(close,200)"}, order=MAKER,
   stop=WIDE, target={"type": "r", "r": 2.0}, max_bars=96, session=OVERNIGHT, mtd=3,
   ev=[("SRC-090", "mechanism", "channel breakouts (Donchian)")], research="hypothesis", fail=FAIL, notes=NOTE,
   instruments=list(MEMES), distinct="Hourly memecoin breakout with a wide stop and multi-day hold.")

st("swing_meme_retest", "Swing memecoin 48-hour breakout retest (4 ATR, 3R, 96h, limit entry)", "swing", "hourly breakout retest",
   mech="a broken 48-hour high that holds on the first pullback marks demand", logic="continuation (retest)",
   anchor="48-hour high frozen at the breakout bar",
   hyp="On hourly bars, 1-12 bars after a close above the prior 48-hour high, buy with a limit 0.1% under the close "
       "when the bar dips to within 0.2% of that level and closes above it, above the 200-hour EMA; stop 4 ATR(14), "
       "target 3R, exit after 96 bars.",
   markets=CRYPTO, tf="1h",
   entry={"long": f"since({BO48}) >= 1 and since({BO48}) <= 12 and low <= valuewhen({BO48}, highest(high,48)[1]) * 1.002 "
                  f"and close > valuewhen({BO48}, highest(high,48)[1]) and close > ema(close,200)"},
   order=MAKER, stop=WIDE, target={"type": "r", "r": 3.0}, max_bars=96, session=OVERNIGHT, mtd=3,
   ev=[("SRC-090", "mechanism", "channel breakouts (Donchian)")], research="hypothesis", fail=FAIL, notes=NOTE,
   instruments=list(MEMES), distinct="Hourly, memecoins, frozen breakout level, wide stop (range_breakout_retest is 5-minute).")
