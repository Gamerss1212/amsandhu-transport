#!/usr/bin/env python3
"""Self-test for the crypto-day-trading scripts. Run after installing:  python3 scripts/selftest.py

Checks the indicator math against hand-computed values, the sizing formula, the
statistics, the backtest engine on synthetic candles with a known outcome, the
journal round trip, event-time conversions, and that the snapshot runs on
synthetic data. No network needed.
"""

from __future__ import annotations

import csv
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import indicators as ind  # noqa: E402
import events  # noqa: E402
from position_size import compute  # noqa: E402
from tradestats import summarize  # noqa: E402
import backtest  # noqa: E402
import snapshot  # noqa: E402

FAILS = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(("ok   " if cond else "FAIL ") + name + (f"  ({detail})" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def close(a, b, tol=1e-6):
    return a is not None and b is not None and abs(a - b) <= tol * max(1.0, abs(b))


# ------------------------------------------------------------- indicators ---
print("== indicators ==")
const = [100.0] * 30
check("EMA of a constant series is the constant", all(close(v, 100.0) for v in ind.ema(const, 9)[8:]))
check("SMA of 1..10 over 5 ends at 8.0", close(ind.sma([float(i) for i in range(1, 11)], 5)[-1], 8.0))
# EMA hand computation: period 3 on [1,2,3,4,5]: seed sma(1,2,3)=2; k=0.5; 4 -> 3.0; 5 -> 4.0
e3 = ind.ema([1.0, 2.0, 3.0, 4.0, 5.0], 3)
check("EMA(3) hand-computed values", e3[2] == 2.0 and close(e3[3], 3.0) and close(e3[4], 4.0), str(e3))
rising = [float(i) for i in range(1, 40)]
check("RSI of a monotonically rising series is 100", close(ind.rsi(rising, 14)[-1], 100.0))
check("RSI of a monotonically falling series is 0", close(ind.rsi(list(reversed(rising)), 14)[-1], 0.0))
# alternating +1/-1 changes: avg gain == avg loss -> RSI 50
alt = [100.0 + (i % 2) for i in range(40)]
rsi_alt = ind.rsi(alt, 14)
check("RSI of symmetric alternating series oscillates tightly around 50",
      abs((rsi_alt[-1] + rsi_alt[-2]) / 2 - 50.0) < 0.5 and abs(rsi_alt[-1] - 50.0) < 5, str(rsi_alt[-2:]))
h = [11.0] * 20; l = [9.0] * 20; c = [10.0] * 20
check("ATR of constant 2-point ranges is 2", close(ind.atr(h, l, c, 14)[-1], 2.0))
mid, up, lo, w = ind.bollinger(const, 20, 2.0)
check("Bollinger on a constant has zero width", close(w[-1], 0.0) and close(up[-1], 100.0))
# swing detection on a zigzag: highs at 5 and 15, lows at 10
z_h = [10, 11, 12, 13, 14, 15, 14, 13, 12, 11, 10, 11, 12, 13, 14, 15, 14, 13, 12, 11, 10.0]
z_l = [x - 1 for x in z_h]
sh, sl = ind.swing_points(z_h, z_l, 3)
check("swing highs found at the zigzag peaks", sh == [5, 15], str(sh))
check("swing low found at the zigzag trough", sl == [10], str(sl))
check("equal_levels groups 100.0/100.1 and leaves 105 alone", ind.equal_levels([100.0, 100.1, 105.0], 0.2) == [100.05])
rv = ind.relative_volume([10.0] * 20 + [30.0], 20)
check("relative volume 30 vs avg 10 is 3.0", close(rv[-1], 3.0))
flags = [i % 5 == 0 for i in range(10)]
vw = ind.vwap([10.0] * 10, [10.0] * 10, [10.0] * 10, [1.0] * 10, flags)
check("VWAP of flat price is the price", all(close(v, 10.0) for v in vw))

# ---------------------------------------------------------------- sizing ---
print("== position sizing ==")
r = compute(10000, 1.0, 64200, 63550, [65600], fee_pct=0.0, slippage_pct=0.0)
check("units = risk / stop distance", close(r["units"], 100 / 650))
check("direction inferred long", r["direction"] == "long")
check("target R computed (rounded to 2 dp)", r["targets"][0]["gross_r"] == round(1400 / 650, 2), str(r["targets"][0]))
r2 = compute(1000, 5.0, 76000, 75800, [76300], 0.05, 0.02, leverage=20)
check("reckless case raises 20x, >2% and <2R warnings", len(r2["warnings"]) >= 3, str(r2["warnings"]))
r3 = compute(10000, 1.0, 100, 98, [105], 0.0, 0.0, leverage=60)
check("liquidation-before-stop warning at 60x with a 2% stop", any("LIQUIDATION" in w for w in r3["warnings"]), str(r3["warnings"]))
try:
    compute(10000, 1.0, 100, 100, None, 0.0, 0.0)
    check("entry == stop rejected", False)
except ValueError:
    check("entry == stop rejected", True)

# ------------------------------------------------------------- statistics ---
print("== statistics ==")
s = summarize([2.0, -1.0, -1.0, 2.0, -1.0])
check("win rate 40%", s["win_rate_pct"] == 40.0)
check("expectancy (2*2 - 3)/5 = 0.2", close(s["expectancy_r"], 0.2))
check("profit factor 4/3", close(s["profit_factor"], 1.33, 1e-2))
check("max drawdown 2R (after +2, two -1s)", close(s["max_drawdown_r"], 2.0))
check("longest losing streak 2", s["max_loss_streak"] == 2)
check("small-sample warning present", s["sample_warning"] is not None)

# --------------------------------------------------------------- backtest ---
print("== backtest engine ==")
# Build 260 candles: flat-ish uptrend so EMAs stack bullish, then a pullback that touches the EMA21,
# then an up candle closing above EMA9, then a rally that hits 2R.
base = datetime(2026, 1, 1, tzinfo=timezone.utc)
ts, o, hh, ll, cc, vv = [], [], [], [], [], []
price = 100.0
for i in range(260):
    if i < 230:
        price += 0.20
        op, cl = price - 0.1, price + 0.1
        lo_, hi_ = op - 0.15, cl + 0.15
    else:
        op, cl, lo_, hi_ = price, price, price - 0.2, price + 0.2
    ts.append(base + timedelta(minutes=15 * i)); o.append(op); cc.append(cl); hh.append(hi_); ll.append(lo_); vv.append(100.0)
d = {"ts": ts, "open": o, "high": hh, "low": ll, "close": cc, "volume": vv}
ctx = backtest.precompute(d, 2.0)
e21_229 = ctx["ema21"][229]
# candle 230: pullback whose low touches EMA21 (setup candle); candle 231: up close above EMA9 (trigger)
d["low"][230] = e21_229 - 0.05; d["open"][230] = cc[229]; d["close"][230] = e21_229 + 0.05; d["high"][230] = cc[229] + 0.05
d["open"][231] = d["close"][230]; d["close"][231] = cc[229] + 0.6; d["high"][231] = d["close"][231] + 0.1; d["low"][231] = d["open"][231] - 0.05
ctx = backtest.precompute(d, 2.0)
sig = backtest.ema_pullback(231, d, ctx)
check("ema_pullback emits a long signal on the constructed pullback", sig is not None and sig["direction"] == "long", str(sig))
if sig:
    d["open"][232] = d["close"][231]  # fill exactly at the signal close so the strategy's 2R target is 2R from entry
    entry = d["open"][232]
    risk = entry - sig["stop"]
    # make the following candles rally through the target without touching the stop
    for j in range(232, 260):
        d["open"][j] = entry + (j - 232) * risk * 0.5
        d["close"][j] = d["open"][j] + risk * 0.5
        d["high"][j] = d["close"][j] + 0.01
        d["low"][j] = d["open"][j] - 0.01
    trades = backtest.run(d, backtest.ema_pullback, ctx, fee_pct=0.0, slip_pct=0.0, max_bars=48, start=200)
    check("one trade taken", len(trades) == 1, str(len(trades)))
    if trades:
        check("trade exits at target for ~+2R", trades[0]["reason"] == "target" and close(trades[0]["r_multiple"], 2.0, 0.02), str(trades[0]))
    # now force the stop to be hit first on the entry candle: pessimistic rule says stop wins
    d2 = {k: list(v) for k, v in d.items()}
    d2["low"][232] = sig["stop"] - 1.0
    d2["high"][232] = sig["target"] + 1.0
    trades2 = backtest.run(d2, backtest.ema_pullback, ctx, 0.0, 0.0, 48, start=200)
    check("stop wins when both stop and target touch in one candle", trades2 and trades2[0]["reason"] == "stop" and close(trades2[0]["r_multiple"], -1.0, 1e-6), str(trades2[:1]))

# ---------------------------------------------------------------- journal ---
print("== journal ==")
with tempfile.TemporaryDirectory() as td:
    jp = os.path.join(td, "t.csv")
    env = dict(os.environ, CRYPTO_JOURNAL=jp)
    py = sys.executable
    subprocess.run([py, os.path.join(HERE, "journal.py"), "init"], env=env, check=True, capture_output=True)
    out = subprocess.run([py, os.path.join(HERE, "journal.py"), "add", "--symbol", "BTC", "--playbook", "1-trend-pullback",
                          "--entry", "100", "--stop", "98", "--target", "105", "--account", "10000"], env=env, capture_output=True, text=True)
    check("journal add succeeds", out.returncode == 0 and "logged trade #1" in out.stdout, out.stdout + out.stderr)
    out = subprocess.run([py, os.path.join(HERE, "journal.py"), "close", "--id", "1", "--exit", "104", "--fees-r", "0"], env=env, capture_output=True, text=True)
    check("journal close computes +2.00R", "+2.00R" in out.stdout, out.stdout + out.stderr)
    out = subprocess.run([py, os.path.join(HERE, "journal_stats.py"), jp], capture_output=True, text=True)
    check("journal_stats runs on the journal", out.returncode == 0 and "trades 1" in out.stdout, out.stdout[-300:] + out.stderr[-300:])
    with open(jp) as fh:
        row = list(csv.DictReader(fh))[0]
    check("size stored from account and stop", close(float(row["size"]), 50.0))

# ---------------------------------------------------------------- symbols ---
print("== symbol parsing ==")
from fetch_ohlcv import parse_symbol
check("BTCUSDT -> BTC/USDT", parse_symbol("BTCUSDT") == ("BTC", "USDT"))
check("btc -> BTC/USDT", parse_symbol("btc") == ("BTC", "USDT"))
check("ETH-USD -> ETH/USD", parse_symbol("ETH-USD") == ("ETH", "USD"))
check("SOL/USDC -> SOL/USDC", parse_symbol("SOL/USDC") == ("SOL", "USDC"))
check("ETHBTC -> ETH/BTC", parse_symbol("ETHBTC") == ("ETH", "BTC"))
check("1000PEPEUSDT keeps its base", parse_symbol("1000PEPEUSDT") == ("1000PEPE", "USDT"))

# ---------------------------------------------------------------- events ---
print("== events / DST ==")
from datetime import date
check("US DST on 2026-09-16", events.us_dst(date(2026, 9, 16)))
check("US standard time on 2026-12-10", not events.us_dst(date(2026, 12, 10)))
check("US DST boundary: 2026-03-08 is DST, 2026-03-07 is not", events.us_dst(date(2026, 3, 8)) and not events.us_dst(date(2026, 3, 7)))
check("US DST ends 2026-11-01", not events.us_dst(date(2026, 11, 1)) and events.us_dst(date(2026, 10, 31)))
check("UK BST boundaries 2026 (Mar 29 - Oct 25)", events.uk_dst(date(2026, 3, 29)) and not events.uk_dst(date(2026, 3, 28)) and not events.uk_dst(date(2026, 10, 25)))
ev = {e[1][:4] + e[0].strftime("%Y-%m-%d"): e[0] for e in events.tier1_events(2026)}
check("FOMC 2026-09-16 decision at 18:00 UTC", ev["FOMC2026-09-16"].strftime("%H:%M") == "18:00")
check("FOMC 2026-12-09 decision at 19:00 UTC (winter)", ev["FOMC2026-12-09"].strftime("%H:%M") == "19:00")
check("CPI 2026-10-14 at 12:30 UTC", ev["US C2026-10-14"].strftime("%H:%M") == "12:30")
check("CPI 2026-01-13 at 13:30 UTC (winter)", ev["US C2026-01-13"].strftime("%H:%M") == "13:30")
t1 = events.next_tier1(datetime(2026, 9, 16, 17, 45, tzinfo=timezone.utc))
check("15 min before FOMC is inside the no-trade window", t1["inside_no_trade_window"])
t1b = events.next_tier1(datetime(2026, 9, 16, 19, 0, tzinfo=timezone.utc))
check("60 min after FOMC is outside the window", not t1b["inside_no_trade_window"])

# --------------------------------------------------------------- snapshot ---
print("== snapshot ==")
snap = snapshot.analyze(d, 3, now=ts[-1] + timedelta(minutes=15))
check("snapshot runs on synthetic 15m data", snap["timeframe"] == "15m" and snap["atr14"] is not None)
check("snapshot detects bullish EMA stack on an uptrend", snap["ema_stack"].startswith("bullish"), snap["ema_stack"])
check("snapshot produces levels sorted by distance", len(snap["levels_by_distance"]) > 3 and
      abs(snap["levels_by_distance"][0]["distance_pct"]) <= abs(snap["levels_by_distance"][-1]["distance_pct"]))
check("snapshot flags is a list", isinstance(snap["flags"], list))
ck = snapshot.clock(datetime(2026, 9, 16, 17, 45, tzinfo=timezone.utc))
check("clock reports US open 13:30 UTC in summer", ck["us_open_utc"] == "13:30")
ck2 = snapshot.clock(datetime(2026, 12, 10, 12, 0, tzinfo=timezone.utc))
check("clock reports US open 14:30 UTC in winter", ck2["us_open_utc"] == "14:30")
check("clock: CME closed on Saturday", snapshot.clock(datetime(2026, 9, 19, 12, 0, tzinfo=timezone.utc))["cme_closed"])
check("clock: CME open on Wednesday", not ck["cme_closed"])

print()
if FAILS:
    print(f"{len(FAILS)} FAILED: {FAILS}")
    sys.exit(1)
print("all checks passed")
