#!/usr/bin/env python3
"""Jarvus in one call: the whole v6.1 rulebook applied by code, printed as a short card (saves Claude tokens).

  python3 jarvus.py card BTC [--account 1000] [--fees ndax]   # the call: BUY/WAIT/NO, and on BUY buy/sell/stop/size
  python3 jarvus.py scan [SOL ETH BTC DOGE BONK]               # the same for each market (default: Jarvus's best 5)
  --why adds the reasons · --full prints the long card (gate, trend, setups, cost in R)

What it checks, in order (references/manual.md has the reasons and the numbers):
  data (Coinbase 1h, last completed bar) -> weekend rule for majors -> volatility gate (LOUD only) ->
  memes: BTC above its 200-day average, BTC 4h trend up, not 7 PM-midnight MT -> trend (1h and 4h up for
  P1/P3/P6) -> a playbook fired in the last 3 completed hours (P1 trend pullback, P3 breakout retest,
  P4 sweep reclaim, P6 ORB, RSI(2) dip) -> cost in R (> 0.33 NO, 0.20-0.33 half size) -> plan:
  limit 0.1% under the close, stop 4x ATR(1h), one exit at 2R, 96h limit, risk 1% x 0.6 (LOUD) for majors,
  0.5% x 0.6 for memes. Spot only. Never a direction forecast. Educational, not advice.
"""

from __future__ import annotations

import argparse
import math
import sys
from datetime import datetime, timedelta, timezone

import os
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import decide  # noqa: E402
import events  # noqa: E402
import ladder  # noqa: E402
import volgate  # noqa: E402
from fetch_ohlcv import fetch_candles, fetch_coinbase  # noqa: E402

MEMES = {"DOGE", "SHIB", "PEPE", "BONK", "WIF", "FLOKI", "FARTCOIN", "TRUMP", "MOG", "POPCAT"}
BEST5 = ["SOL", "ETH", "BTC", "DOGE", "BONK"]
LOUD_RIGHT = {"crypto": "76%"}                    # held-out test precision of a LOUD call (base rate 31%)
TREND = {"trend_pullback": "P1", "breakout_retest": "P3", "orb": "P6"}
REVERSION = {"sweep_reclaim": "P4", "rsi2": "RSI2"}


def _ema(v, n):
    out, e, k = [], None, 2 / (n + 1)
    for x in v:
        e = x if e is None else e + k * (x - e)
        out.append(e)
    return out


def mt_now():
    now = datetime.now(timezone.utc)
    return now - timedelta(hours=6 if events.us_dst(now.date()) else 7)


_BTC = {}


def btc_regime():
    """BTC above its 200-day average (memes allowed) and BTC's 4h trend (cached per run)."""
    if not _BTC:
        try:
            d = fetch_coinbase("BTC", "USD", "1d", 230)[:-1]
            closes = [r[4] for r in d]
            _BTC["bull"] = closes[-1] > sum(closes[-200:]) / 200 if len(closes) >= 200 else None
            _BTC["sma"] = sum(closes[-200:]) / 200 if len(closes) >= 200 else None
        except Exception:                                       # noqa: BLE001
            _BTC["bull"], _BTC["sma"] = None, None
        try:
            _, rows = fetch_candles("BTC-USD", "1h", 420, "coinbase")
            _BTC["up4"] = analyse_rows(rows)["up4"]
        except Exception:                                       # noqa: BLE001
            _BTC["up4"] = None
    return _BTC


def analyse_rows(rows):
    now_ms = datetime.now(timezone.utc).timestamp() * 1000
    if rows and rows[-1][0] + 3_600_000 > now_ms:
        rows = rows[:-1]                                         # the hour is still open
    d = {"ts": [datetime.fromtimestamp(r[0] / 1000, timezone.utc) for r in rows],
         "open": [r[1] for r in rows], "high": [r[2] for r in rows], "low": [r[3] for r in rows],
         "close": [r[4] for r in rows], "volume": [r[5] for r in rows]}
    x = ladder._ctx(d)
    n = len(rows)
    i = n - 1
    up1 = bool(x["ema21"][i] and x["ema50"][i] and x["ema200"][i] and x["ema21"][i] > x["ema50"][i]
               and d["close"][i] > x["ema200"][i])
    c4, last_k = [], None
    for r in rows:
        k = r[0] // (4 * 3_600_000)
        if k != last_k:
            c4.append(r[4])
            last_k = k
        else:
            c4[-1] = r[4]
    c4 = c4[:-1] if (rows[-1][0] + 3_600_000) % (4 * 3_600_000) else c4   # only completed 4h bars
    e21, e50 = _ema(c4, 21), _ema(c4, 50)
    up4 = len(c4) >= 50 and c4[-1] > e50[-1] and e21[-1] > e50[-1]
    fired = []
    for name, fn in ladder.SETUPS.items():
        if name == "benchmark":
            continue
        if any(fn(k, d, x) == "long" for k in range(max(205, n - 3), n)):
            fired.append(name)
    return {"d": d, "x": x, "rows": rows, "up1": up1, "up4": up4, "fired": fired, "close": d["close"][i],
            "atr": x["atr"][i], "t": rows[-1][0]}


def evaluate(sym, account, fees):
    base = sym.upper().replace("-USD", "").replace("USDT", "").replace("/USD", "")
    meme = base in MEMES
    src, rows = fetch_candles(f"{base}-USD", "1h", 420, "coinbase")
    a = analyse_rows(rows)
    g = volgate.read_rows(volgate.VolGate(), rows, "crypto")
    gate = g.get("state", "UNKNOWN")
    close, atr = a["close"], a["atr"]
    entry = close * 0.999
    stop = entry - 4 * atr
    target = entry + 2 * (entry - stop)
    c = decide.cost_r(entry, stop, True, fees, 0.10 if meme else 0.02)
    risk_pct = (0.5 if meme else 1.0) * 0.6
    if c["cost_r"] > 0.20:
        risk_pct *= 0.5
    risk_amt = account * risk_pct / 100
    units = risk_amt / (entry - stop) if entry > stop else 0
    mt = mt_now()
    why, verdict = [], "BUY"
    trend_ok = [s for s in a["fired"] if s in TREND and a["up1"] and a["up4"]]
    rev_ok = [s for s in a["fired"] if s in REVERSION]
    setups = trend_ok + rev_ok
    if not meme and mt.weekday() >= 5:
        verdict, why = "WAIT", why + ["weekend: no new majors trades"]
    if gate != "LOUD":
        verdict, why = "WAIT", why + [f"gate {gate}: trade only on LOUD"]
    if meme:
        b = btc_regime()
        if b.get("bull") is False:
            verdict, why = "NO", why + ["BTC below its 200-day average: memes off"]
        elif b.get("up4") is False:
            verdict, why = ("WAIT" if verdict != "NO" else verdict), why + ["BTC 4h trend down: no meme longs"]
        if 19 <= mt.hour <= 23:
            verdict, why = ("WAIT" if verdict != "NO" else verdict), why + ["7 PM-midnight MT: meme dead zone"]
    if c["cost_r"] > 0.33:
        verdict, why = "NO", why + [f"cost {c['cost_r']:.2f}R > 0.33R at {fees}"]
    if not setups:
        verdict = verdict if verdict != "BUY" else "WAIT"
        why.append("no playbook fired in the last 3 hours" + ("" if a["up1"] and a["up4"] else " (and 1h/4h trend not both up)"))
    return {"sym": f"{base}-USD", "meme": meme, "src": src, "close": close, "gate": gate, "up1": a["up1"], "up4": a["up4"],
            "setups": [TREND.get(s) or REVERSION.get(s) for s in setups], "entry": entry, "stop": stop, "target": target,
            "stop_pct": (entry - stop) / entry * 100, "cost_r": c["cost_r"], "risk_pct": risk_pct, "risk_amt": risk_amt,
            "units": units, "notional": units * entry, "verdict": verdict, "why": why, "mt": mt,
            "bar": datetime.fromtimestamp(a["t"] / 1000, timezone.utc).strftime("%H:%M")}


def px(v):
    if v >= 1000:
        return f"{v:,.0f}"
    if v >= 1:
        return f"{v:,.2f}"
    return f"{v:.{max(2, 3 - math.floor(math.log10(v)))}f}".rstrip("0").rstrip(".") if v > 0 else "0"


def arrow(b):
    return "↑" if b else "↓/↔"


MOVE = {"LOUD": "big move likely", "NORMAL": "normal move", "QUIET": "small move"}


def move(r):
    return MOVE.get(r["gate"], "move size unknown")


def orders(r):
    out = r["mt"] + timedelta(hours=96)
    return (f"Buy {px(r['entry'])} · Sell {px(r['target'])} · Stop {px(r['stop'])} · "
            f"Size ${r['notional']:,.0f} · out by {out:%a %H:%M} MT")


def short(r, why=False, scan=False):
    """Default reply: only the call, the orders and the expected move size (never a direction)."""
    head = f"{r['sym'].split('-')[0]} ${px(r['close'])} → {r['verdict']}"
    tail = f"next 12h: {move(r)}" + ("" if scan else ", direction unknown")
    lines = [f"{head}\n{orders(r)}\n{tail[0].upper() + tail[1:]}" if r["verdict"] == "BUY" else f"{head} · {tail}"]
    if why and r["why"]:
        lines.append("Why: " + "; ".join(r["why"]))
    return "\n".join(lines)


def card(r, fees):
    lines = [f"JARVUS {r['sym']} · {r['mt']:%a %H:%M} MT · Coinbase 1h (bar {r['bar']} UTC) · ${px(r['close'])}",
             f"Gate {r['gate']} (LOUD calls right {LOUD_RIGHT['crypto']} in testing) · trend 1h {arrow(r['up1'])} 4h {arrow(r['up4'])}"
             f" · setups {', '.join(r['setups']) or 'none'}" + (" · meme" if r["meme"] else ""),
             f"Verdict: {r['verdict']}" + (f" — {'; '.join(r['why'])}" if r["why"] else "")]
    tag = "Plan" if r["verdict"] == "BUY" else "Plan if it turns LOUD with a setup"
    lines.append(f"{tag}: limit {px(r['entry'])} · stop {px(r['stop'])} (4×ATR, {r['stop_pct']:.1f}%) · "
                 f"target {px(r['target'])} (2R, one exit) · 96h max")
    lines.append(f"Size: risk {r['risk_pct']:.2f}% = ${r['risk_amt']:.2f} → {r['units']:.6g} {r['sym'].split('-')[0]} "
                 f"(${r['notional']:,.0f}) · cost {r['cost_r']:.2f}R at {fees} (maker in)")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description="Jarvus v6.1 in one call: card or scan.")
    ap.add_argument("cmd", choices=["card", "scan"])
    ap.add_argument("symbols", nargs="*")
    ap.add_argument("--account", type=float, default=1000.0)
    ap.add_argument("--fees", default="ndax", help="ndax | kraken | kraken10k | coinbase | low | <taker %% per side>")
    ap.add_argument("--why", action="store_true", help="add the reasons behind each call")
    ap.add_argument("--full", action="store_true", help="the long card (gate, trend, setups, cost) instead of the short call")
    a = ap.parse_args()
    syms = a.symbols or (BEST5 if a.cmd == "scan" else ["BTC"])
    out = []
    for s in syms:
        try:
            out.append(evaluate(s, a.account, a.fees))
        except SystemExit as e:
            print(f"{s.upper()}: no data ({str(e).strip()[:120]})")
        except Exception as e:                                   # noqa: BLE001
            print(f"{s.upper()}: error {type(e).__name__}: {e}"[:160])
    if not a.full:
        for r in out:
            print(short(r, a.why, a.cmd == "scan"))
        if a.cmd == "scan" and out:
            print("Direction: unknown (not predictable).")
        return 0
    if a.cmd == "card":
        for r in out:
            print(card(r, a.fees))
        return 0
    for r in out:
        print(f"{r['sym']:<9} ${px(r['close']):>12}  gate {r['gate']:<6} 1h {arrow(r['up1']):<3} 4h {arrow(r['up4']):<3} "
              f"setups {','.join(r['setups']) or '-':<8} {r['verdict']:<4} {('; '.join(r['why']))[:70]}")
    if out:
        mt = out[0]["mt"]
        b = btc_regime() if any(r["meme"] for r in out) else {}
        print(f"{mt:%a %H:%M} MT · BUY {sum(r['verdict'] == 'BUY' for r in out)} of {len(out)}"
              + (f" · BTC {'above' if b.get('bull') else 'below'} 200-day" if b.get("bull") is not None else "")
              + " · educational, not advice")
    return 0


if __name__ == "__main__":
    sys.exit(main())
