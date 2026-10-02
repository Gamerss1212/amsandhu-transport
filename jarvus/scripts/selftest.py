#!/usr/bin/env python3
"""Self-test for the Jarvus scripts (v6: also the Terminal's gate, decision engine and goal calculator). Run after installing:  python3 scripts/selftest.py

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
import ladder  # noqa: E402

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

# ------------------------------------------------------------- confluence ---
print("== confluence ==")
import confluence
_snap_now = ts[-1] + timedelta(minutes=15)
_s = snapshot.analyze(d, 3, now=_snap_now)
_px = _s["price"]
_res = confluence.score(_s, _s, {"funding_rate_8h_pct": 0.01}, "long", datetime(2026, 9, 17, 14, 0, tzinfo=timezone.utc),
                        entry=_px, stop=_px * 0.97, target=_px + 2.5 * _px * 0.03, gate="LOUD", fees="ndax")
check("confluence scores the eleven SKILL.md factors (0 = volatility gate)", len(_res["rows"]) == 11 and _res["max"] == 11
      and 0 <= _res["score"] <= 11)
check("a 3% stop at NDAX (0.15R of costs) earns the reward and stop-quality points",
      all(r["points"] == 1 for r in _res["rows"] if r["factor"] in (0, 9, 10)) and not _res["blocked"],
      str([r for r in _res["rows"] if r["factor"] in (9, 10)]))
_tight = confluence.score(_s, _s, {}, "long", datetime(2026, 9, 17, 14, 0, tzinfo=timezone.utc),
                          entry=_px, stop=_px * 0.99, target=_px * 1.03, gate="LOUD", fees="ndax")
check("a 1% stop at NDAX (0.44R of costs) is blocked by the cost gate, whatever the score",
      _tight["blocked"] and _tight["grade"] == "skip" and next(r for r in _tight["rows"] if r["factor"] == 10)["points"] == 0,
      str(_tight["blocked"]))
check("Kraken Pro's entry tier makes the same 3% stop a NO (1.64% round trip = 0.55R)",
      confluence.score(_s, _s, {}, "long", datetime(2026, 9, 17, 14, 0, tzinfo=timezone.utc), entry=_px, stop=_px * 0.97,
                       target=_px * 1.075, gate="LOUD", fees="kraken")["blocked"] is not None)
check("v6.1: a NORMAL gate means wait for LOUD",
      confluence.score(_s, _s, {}, "long", datetime(2026, 9, 17, 14, 0, tzinfo=timezone.utc), entry=_px, stop=_px * 0.97,
                       target=_px * 1.075, gate="NORMAL")["blocked"] == "volatility gate NORMAL: wait for LOUD")
check("a QUIET gate blocks whatever the score",
      confluence.score(_s, _s, {}, "long", datetime(2026, 9, 17, 14, 0, tzinfo=timezone.utc), entry=_px, stop=_px * 0.97,
                       target=_px * 1.075, gate="QUIET")["grade"] == "skip")
check("confluence awards the session point at 14:00 UTC on a weekday", next(r for r in _res["rows"] if r["factor"] == 7)["points"] == 1)
_res2 = confluence.score(_s, _s, {"funding_rate_8h_pct": 0.01}, "long", datetime(2026, 9, 16, 17, 50, tzinfo=timezone.utc))
check("confluence denies the calendar point 10 min before FOMC", next(r for r in _res2["rows"] if r["factor"] == 8)["points"] == 0)
check("confluence grade is skip without a plan", _res2["grade"] == "skip")

# ------------------------------------------------------------------ ladder ---
print("== ladder / 80% engine ==")
import ladder as L

check("parse_ladder sorts rungs by R", [r["r"] for r in L.parse_ladder("1.0:0.3,0.25:0.5")] == [0.25, 1.0])
try:
    L.parse_ladder("0.5:0.7,1.0:0.7")
    check("parse_ladder rejects fractions summing above the whole position", False)
except SystemExit:
    check("parse_ladder rejects fractions summing above the whole position", True)

# A steadily rising series: every trade should reach a low rung and bank exactly it.
_n = 900
_rise = {"ts": [], "open": [], "high": [], "low": [], "close": [], "volume": []}
_p = 100.0
for _i in range(_n):
    _rise["ts"].append(base + timedelta(hours=_i))
    _o = _p; _p *= 1.004; _c = _p
    _rise["open"].append(_o); _rise["close"].append(_c)
    _rise["high"].append(max(_o, _c) * 1.0005); _rise["low"].append(min(_o, _c) * 0.9995)
    _rise["volume"].append(100.0)
_rx = L._ctx(_rise)
_t = L.simulate(_rise, L.SETUPS["benchmark"], _rx, stop_atr=4.0, target_r=2.0,
                rungs=L.parse_ladder("0.25:1.0"), horizon=96, fee_bps=0.0, slip_bps=0.0, breakeven=True)
check("sell-everything-at-0.25R banks ~+0.25R on a rising series",
      len(_t) > 5 and all(abs(x["r"] - 0.25) < 0.02 for x in _t), str(_t[:2]))
check("that ladder reports ladder_complete, not target", all(x["reason"] == "ladder_complete" for x in _t))

# Stop-wins-on-tie: a bar spanning both the stop and the rung must resolve as the stop.
# benchmark fires on i % 12 == 0, so the first signal at or past bar 205 is 216;
# its entry bar is 217, and that is the bar made wide enough to span both sides.
_tie = {k: list(v) for k, v in _rise.items()}
_tie["high"][217] = _tie["open"][217] * 1.5        # far above every rung
_tie["low"][217] = _tie["open"][217] * 0.5         # far below the stop
_t2 = L.simulate(_tie, L.SETUPS["benchmark"], L._ctx(_tie), stop_atr=4.0, target_r=2.0,
                 rungs=L.parse_ladder("0.25:0.5"), horizon=96, fee_bps=0.0, slip_bps=0.0,
                 breakeven=True, start=210, end=230)
check("a bar touching both stop and rung resolves as the stop, at -1R",
      bool(_t2) and _t2[0]["reason"] == "stop" and abs(_t2[0]["r"] + 1.0) < 1e-6, str(_t2[:1]))

# The central claim of Part 26: a lower first rung mechanically raises the green rate.
_rw = {"ts": [], "open": [], "high": [], "low": [], "close": [], "volume": []}
_p = 100.0; _seed = 12345
for _i in range(4000):
    _seed = (1103515245 * _seed + 12345) % (2 ** 31)      # deterministic LCG, no drift
    _step = ((_seed / (2 ** 31)) - 0.5) * 0.02
    _o = _p; _p *= (1 + _step); _c = _p
    _rw["ts"].append(base + timedelta(hours=_i))
    _rw["open"].append(_o); _rw["close"].append(_c)
    _rw["high"].append(max(_o, _c) * 1.002); _rw["low"].append(min(_o, _c) * 0.998)
    _rw["volume"].append(100.0)
_rwx = L._ctx(_rw)
_greens = {}
for _spec in ("1.0:0.5", "0.5:0.5", "0.25:0.5"):
    _tr = L.simulate(_rw, L.SETUPS["benchmark"], _rwx, stop_atr=4.0, target_r=2.0,
                     rungs=L.parse_ladder(_spec), horizon=96, fee_bps=0.0, slip_bps=0.0, breakeven=True)
    _greens[_spec] = L.stats(_tr)["green_rate_pct"]
check("a lower first rung raises the green rate on entries with no edge (Part 26's claim)",
      _greens["0.25:0.5"] > _greens["0.5:0.5"] > _greens["1.0:0.5"], str(_greens))
check("and it does so on random-walk data, i.e. with no edge present at all",
      _greens["0.25:0.5"] > 65, str(_greens))

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

# ------------------------------------------------- the Terminal, built in (v6) ---
print("== volatility gate (trained model) ==")
import math as _m  # noqa: E402
import random as _r  # noqa: E402
import volgate as vg  # noqa: E402
_g = vg.VolGate()
check("gate model loads for crypto and stocks", _g.model.get("crypto", {}).get("kind") == "gbm" and _g.model.get("stock", {}).get("kind") == "logit")
_rng = _r.Random(3)
_t0 = 1_780_000_000_000 - (1_780_000_000_000 % 3_600_000)
_rows, _p = [], 100.0
for _k in range(500):
    _vol = 0.004 * (2.5 if (_k // 60) % 3 == 0 else 1.0)
    _o = _p
    _p = _p * _m.exp(_rng.gauss(0, _vol))
    _rows.append([_t0 + _k * 3_600_000, _o, max(_o, _p) * (1 + abs(_rng.gauss(0, _vol / 2))),
                  min(_o, _p) * (1 - abs(_rng.gauss(0, _vol / 2))), _p, _rng.uniform(50, 150)])
_t, _o, _h, _l, _c, _v = (list(x) for x in zip(*_rows))
_rd = _g.read(vg.Bars(_t, _o, _h, _l, _c, _v, 12), 499, "crypto")
check("gate reproduces the Terminal's reading on a fixed series (NORMAL 0.2179 / 0.4391)",
      _rd["state"] == "NORMAL" and _rd["p_loud"] == 0.2179 and _rd["p_quiet"] == 0.4391, str(_rd)[:200])
check("gate attaches tested evidence (observed rate and hours) to the reading",
      _rd["evidence"]["loud"]["n"] > 1000 and 0 < _rd["evidence"]["loud"]["observed_rate"] < 1)
check("gate refuses to read with too little history", vg.read_rows(_g, _rows[:100], "crypto")["state"] == "UNKNOWN")
check("regime: a straight rise is 'up'", vg.regime([100.0 + i for i in range(260)])["trend"] == "up")
check("regime: a zigzag is 'sideways'", vg.regime([100.0 + (i % 2) for i in range(260)])["trend"] == "sideways")

print("== decision engine (the Terminal's brain) ==")
import decide as dc  # noqa: E402
_c1 = dc.cost_r(100.0, 98.0, False, "ndax", 0.02)
check("NDAX round trip 0.44% on a 2% stop = 0.22R", close(_c1["cost_r"], 0.22, 1e-6), str(_c1))
check("cost above 0.33R is refused", dc.decide(dc.cost_r(100.0, 99.5, False, "kraken", 0.02), "LOUD", None)["kind"] == "cost")
check("QUIET is refused", dc.decide(dc.cost_r(100.0, 96.0, True, "ndax", 0.02), "QUIET", None)["kind"] == "quiet")
check("v6.1: NORMAL waits for LOUD", dc.decide(dc.cost_r(100.0, 96.0, True, "ndax", 0.02), "NORMAL", None)["kind"] == "not_loud")
check("--allow-normal restores the Terminal's rule (NORMAL trades)", dc.decide(dc.cost_r(100.0, 96.0, True, "ndax", 0.02), "NORMAL", None, True)["action"] == "TAKE")
check("0.20-0.33R cost halves the size", dc.decide(_c1, "NORMAL", None, True)["size"] == 0.5)
check("LOUD with fine costs = 0.6x", dc.decide(dc.cost_r(100.0, 96.0, True, "ndax", 0.02), "LOUD", None)["size"] == 0.6)
_neg = dc.estimate({"mean": -0.4, "trades": 200}, [])
check("history counts as at most 25 pseudo-trades", _neg["evidence"] == 25.0)
check("a measured negative edge is refused", dc.decide(dc.cost_r(100.0, 96.0, True, "ndax", 0.02), "LOUD", _neg)["kind"] == "learned")
_own = dc.estimate({"mean": -0.4, "trades": 200}, [1.0] * 40)
check("his own trades overturn history (40 wins at +1R beat 25 pseudo-trades at -0.4R)", _own["mean"] > 0.4, str(_own))
_pos = dc.decide(dc.cost_r(100.0, 96.0, True, "ndax", 0.02), "LOUD", {"mean": 0.2, "sd": 0.1, "evidence": 30, "own_trades": 5})
check("a positive edge sizes up (1.3x), then LOUD's 0.6x", _pos["action"] == "RESIZE" and close(_pos["size"], 0.78, 1e-6), str(_pos))
_pr = dc.strategy_prior("STRAT-407", "SOL-USD", "ndax")
check("scoreboard lookup interpolates NDAX between low-fee and retail runs",
      _pr and _pr["mean"] is not None and abs(_pr["mean"] - (0.183 + (-0.011 - 0.183) * (0.002 - 0.001) / 0.007)) < 0.02, str(_pr)[:200])

print("== system test (Jarvus backtested) ==")
import system_test as stt  # noqa: E402
_t0 = int(datetime(2026, 1, 12, 0, 0, tzinfo=timezone.utc).timestamp() * 1000)    # a Monday in US winter time
_n = 245
_d = {"ts": [datetime.fromtimestamp((_t0 + k * 3_600_000) / 1000, timezone.utc) for k in range(_n)],
      "open": [100.0] * _n, "high": [100.2] * _n, "low": [99.8] * _n, "close": [100.0] * _n, "volume": [100.0] * _n}
_base = 216                                          # 2026-01-21 00:00 UTC
for _h, (_hi, _cl, _v) in {13: (100.5, 100.1, 100.0), 14: (101.0, 100.8, 300.0), 15: (101.4, 101.2, 300.0)}.items():
    _d["high"][_base + _h], _d["close"][_base + _h], _d["volume"][_base + _h] = _hi, _cl, _v
_x = ladder._ctx(_d)
_fixed = [k for k in range(_base, _n) if ladder.s_orb(k, _d, _x) == "long"]
_legacy = [k for k in range(_base, _n) if stt.s_orb_legacy(k, _d, _x) == "long"]
check("ORB fixed: in US winter the open range is the 14:00 UTC bar (break at 15:00)", _fixed == [_base + 15], str(_fixed))
check("ORB before the fix fired inside the opening hour itself (14:00)", _legacy == [_base + 14], str(_legacy))

_H = 3_600_000
_mon = int(datetime(2026, 1, 12, 15, 0, tzinfo=timezone.utc).timestamp() * 1000)
_sat = int(datetime(2026, 1, 17, 15, 0, tzinfo=timezone.utc).timestamp() * 1000)
_btc = {"t": [_mon - _H, _sat - _H], "bull": [True, True], "trend4": [True, True]}


def _cd(t, gate="L", rt=0.1, r=-1.0, coin="BTC", kind="major", setup="breakout_retest", hold=2):
    return {"coin": coin, "kind": kind, "setup": setup, "t_dec": t, "t_exit": t + hold * _H, "gate": gate, "up1": True,
            "trend4": True, "rt_cost_r": rt, "r": r, "gross_r": r + 0.1, "cost_r": 0.1, "risk": 2.0, "entry": 100.0}


_rules61 = dict(stt.DEFAULT_RULES, **stt.V61)
_tk, _sk, _, _ = stt.simulate([_cd(_sat)], _btc, _rules61)
check("system test: no new majors trade at the weekend (M4)", not _tk and "weekend (M4)" in _sk)
_tk, _sk, _, _ = stt.simulate([_cd(_mon, gate="N")], _btc, _rules61)
check("system test: v6.1 waits when the gate is NORMAL", not _tk and "gate not LOUD" in _sk)
_tk, _sk, _, _ = stt.simulate([_cd(_mon, gate="N")], _btc, stt.DEFAULT_RULES)
check("system test: v6 as written traded NORMAL hours", len(_tk) == 1)
_tk, _sk, _, _ = stt.simulate([_cd(_mon, rt=0.4)], _btc, _rules61)
check("system test: cost above 0.33R is refused", not _tk and "cost > 0.33R" in _sk)
_seq = [_cd(_mon + k * 3 * _H, coin=c) for k, c in enumerate(["BTC", "ETH", "SOL", "BTC"])]
_tk, _sk, _, _ = stt.simulate(_seq, _btc, dict(_rules61, engine=False))
check("system test: majors stop for the day after 2 trades (the 3rd and 4th signals are refused)", len(_tk) == 2, str(_sk))
_tk, _, _, _eq = stt.simulate([_cd(_mon, r=2.0)], _btc, _rules61)
check("system test: a LOUD trade risks 0.6% and a +2R result adds 1.2%", abs(_eq - 10_120.0) < 1e-6, str(_eq))

print("== jarvus.py (one-call card) ==")
import jarvus as jv  # noqa: E402
_t0 = int(datetime(2026, 9, 1, tzinfo=timezone.utc).timestamp() * 1000)
_rows = [[_t0 + k * 3_600_000, 100 + k * 0.05, 100.3 + k * 0.05, 99.8 + k * 0.05, 100.1 + k * 0.05, 100.0] for k in range(420)]
_an = jv.analyse_rows(_rows)
check("jarvus.py reads a steady rise as 1h and 4h uptrends", _an["up1"] and _an["up4"])
_r = {"sym": "BTC-USD", "meme": False, "close": 85000.0, "gate": "NORMAL", "up1": True, "up4": True, "setups": [],
      "entry": 84915.0, "stop": 81500.0, "target": 91745.0, "stop_pct": 4.0, "cost_r": 0.11, "risk_pct": 0.6,
      "risk_amt": 6.0, "units": 0.00176, "notional": 149.0, "verdict": "WAIT", "why": ["gate NORMAL: trade only on LOUD"],
      "mt": datetime(2026, 10, 1, 21, 0), "bar": "02:00"}
_card = jv.card(_r, "ndax")
check("the card is at most 5 short lines with the verdict on line 3", len(_card.splitlines()) <= 5 and "Verdict: WAIT" in _card.splitlines()[2])
check("the card shows stop, 2R target, 96h and the cost in R", all(k in _card for k in ("4×ATR", "2R", "96h", "0.11R")))
_s = jv.short(_r)
check("the short reply for WAIT is one line with no buy levels", len(_s.splitlines()) == 1 and "WAIT" in _s and "Buy" not in _s, _s)
check("the short reply never forecasts a direction", "direction unknown" in _s and not any(w in _s.lower() for w in (" up", " down", "bull", "bear")), _s)
_b = jv.short(dict(_r, verdict="BUY", gate="LOUD"))
check("the short reply for BUY gives buy, sell (2R), stop, size and the 96h exit time",
      all(k in _b for k in ("Buy 84,915", "Sell 91,745", "Stop 81,500", "Size $149", "out by Mon 21:00")) and len(_b.splitlines()) == 3, _b)
check("prices under $0.001 print without scientific notation", jv.px(3.8e-06) == "0.0000038", jv.px(3.8e-06))

print("== goal calculator ==")
import goal as gl  # noqa: E402
import json as _j  # noqa: E402
_inp = _j.load(open(gl.INPUTS))
_gr = gl.project(_inp, "ndax", 100, 90, 300_000)
check("$100 -> $300K in 90 days needs +9.30% every day", close(_gr["goal"]["per_day_pct"], 9.3037, 1e-3), str(_gr["goal"]))
check("none of 5,000 measured paths reach it", _gr["goal"]["share_reaching"] == 0.0)
check("the measured middle outcome stays near $100", 95 < _gr["median"] < 106, str(_gr["median"]))
check("all five fee levels are bundled", set(_inp["profiles"]) == {"venue", "coinbase", "kraken", "ndax", "low_fee"})

print()
if FAILS:
    print(f"{len(FAILS)} FAILED: {FAILS}")
    sys.exit(1)
print("all checks passed")
