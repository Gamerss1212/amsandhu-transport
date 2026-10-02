#!/usr/bin/env python3
"""Backtest Jarvus itself: the whole rulebook in SKILL.md, mechanized, on years of hourly crypto data.

What is simulated, bar by bar, in time order, across several coins at once (one account):
  * the playbooks as Jarvus's scripts define them (ladder.py): P1 trend pullback, P3 breakout retest,
    P4 sweep reclaim, P6 opening-range breakout, RSI(2) dip, plus an every-12th-bar control with no edge;
  * the trained volatility gate (volgate.py): QUIET = no trade, LOUD = 0.6x size;
  * rule M4 (no new majors trades at the weekend), rule M0 (trend setups only when the 1h and 4h trends are
    up; in a bear regime, BTC below its 200-day average, majors take only reversion setups at half size and
    memes are off), BTC first for memes (no meme longs while BTC's 4h trend is down), the meme dead zone
    (7 PM - midnight MT);
  * the cost gate and the decision engine (decide.py): cost > 0.33R skip, 0.20-0.33R half size, the learned
    edge per playbook from Jarvus's own closed trades (refused trades followed as shadow trades at half
    weight, so a benched playbook can recover);
  * the risk rules: 1% risk (0.5% for P4 and memes), the engine's multiplier, daily -3R cap, 3 losses in a
    row ends the day, at most 2 majors trades a day, one majors position at a time (BTC/ETH/SOL count as
    one), at most 2 meme positions, weekly -6R cap, the drawdown protocol (-5R from the peak = half risk,
    -10R = a week off) and no leverage;
  * management as the Signal Card says: limit (maker) entry 0.1% under the signal close, valid 3 bars;
    stop 4x ATR; half at +1R (stop to entry + fees), the rest at +2R; exit if +1R is not reached within 8
    bars, otherwise a 96-bar limit. Stops fill at the stop (or the open if the bar gapped through it) as taker
    with slippage; targets are resting limits (maker). Stop and target in one bar: the stop is assumed first.

Every rule can be switched off or changed, so each one's contribution is measured (ablation). Results are
split into three periods because the gate and the rules were designed on part of this history:
A = design (before 2025-03-20), B = validation (2025-03-20 to 2025-12-22), C = test (from 2025-12-23: the
volatility gate never saw it). A change is only worth adopting if it helps on B and C, not just A.

  python3 system_test.py --data DIR --download                 # fetch Coinbase hourly history (no keys)
  python3 system_test.py --data DIR --battery --out results.json --md report.md --workers 4
  python3 system_test.py --data DIR --group majors --fees ndax  # one run with the rules as written

Standard library only. Educational, not advice: a replay of history, not a forecast.
"""

from __future__ import annotations

import argparse
import csv
import heapq
import json
import math
import os
import pickle
import random
import sys
import time
from datetime import datetime, timedelta, timezone
from multiprocessing import Pool

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import events  # noqa: E402
import ladder  # noqa: E402
import volgate  # noqa: E402
from snapshot import load_csv  # noqa: E402

MAJORS = ["BTC", "ETH", "SOL"]
MEMES = ["DOGE", "SHIB", "PEPE", "BONK", "WIF", "FLOKI"]
FEES = {"ndax": (0.0020, 0.0020), "kraken": (0.0040, 0.0080), "kraken10k": (0.0022, 0.0038),
        "low": (0.0008, 0.0010), "coinbase": (0.0060, 0.0120)}
SLIP = {"major": 0.0002, "meme": 0.0010}          # per side, an assumption (spread + impact for a small order)
PERIOD_B = datetime(2025, 3, 20, tzinfo=timezone.utc)
PERIOD_C = datetime(2025, 12, 23, tzinfo=timezone.utc)
SETUPS = ["trend_pullback", "breakout_retest", "sweep_reclaim", "orb_legacy", "rsi2"]   # v6 as written used the old ORB
TREND_SETUPS = {"trend_pullback", "breakout_retest", "orb", "orb_legacy"}
REVERSION_SETUPS = {"sweep_reclaim", "rsi2"}
HOUR = 3_600_000


# ------------------------------------------------------------------ setups not in ladder.py
def s_orb_legacy(i, d, x):
    """P6 as ladder.py had it before Oct 2026: the 13:00 UTC bar all year (an hour early in US winter time).
    Kept only to measure the fix."""
    if i < 205:
        return None
    ts = d["ts"][i]
    if ts.hour < 14 or ts.hour > 18:
        return None
    j = i
    while j > 0 and d["ts"][j].hour > 13 and d["ts"][j].date() == ts.date():
        j -= 1
    if d["ts"][j].hour != 13 or d["ts"][j].date() != ts.date() or i <= j:
        return None
    or_high = d["high"][j]
    if d["close"][i] <= or_high or any(d["close"][k] > or_high for k in range(j + 1, i)):
        return None
    rv = x["rvol"][i]
    if rv is None or rv < 1.2:
        return None
    e200 = x["ema200"][i]
    return "long" if (e200 is not None and d["close"][i] > e200) else None


SETUP_FN = dict(ladder.SETUPS, orb_legacy=s_orb_legacy)
PREP_VERSION = 2                                  # bump when a setup or the gate changes: rebuilds caches


# ------------------------------------------------------------------ data
def download(data_dir: str, coins, hours: int = 50_400) -> None:
    from fetch_ohlcv import fetch_coinbase, iso
    os.makedirs(data_dir, exist_ok=True)
    for c in coins:
        path = os.path.join(data_dir, f"{c}_1h.csv")
        if os.path.exists(path):
            continue
        rows = fetch_coinbase(c, "USD", "1h", hours)
        with open(path, "w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["timestamp_utc", "open", "high", "low", "close", "volume"])
            for r in rows:
                w.writerow([iso(r[0])] + r[1:])
        print(f"{c}: {len(rows)} hourly bars", flush=True)


def _ema(vals, n):
    out, e, k = [None] * len(vals), None, 2 / (n + 1)
    for i, v in enumerate(vals):
        if v is None:
            continue
        e = v if e is None else e + k * (v - e)
        out[i] = e if i >= n - 1 else None
    return out


def prepare(args):
    """Per coin: candles, indicators, the gate reading at every bar, 4h and daily trend flags, signals. Cached."""
    data_dir, coin = args
    cache = os.path.join(data_dir, f"{coin}_prep.pkl")
    src = os.path.join(data_dir, f"{coin}_1h.csv")
    if os.path.exists(cache) and os.path.getmtime(cache) >= os.path.getmtime(src):
        with open(cache, "rb") as fh:
            got = pickle.load(fh)
        if got.get("version") == PREP_VERSION:
            return got
    d = load_csv(src)
    x = ladder._ctx(d)
    n = len(d["close"])
    t = [int(ts.timestamp() * 1000) for ts in d["ts"]]
    gate = volgate.VolGate()
    b = volgate.Bars(t, d["open"], d["high"], d["low"], d["close"], d["volume"], volgate.HORIZON["crypto"])
    gstate = []
    for i in range(n):
        r = gate.read(b, i, "crypto") if i >= 200 else {"state": "UNKNOWN"}
        gstate.append(r["state"][0])                                   # L / N / Q / U
    # 4h trend (last completed 4h bar): close > EMA50 and EMA21 > EMA50
    buckets, order = {}, []
    for i in range(n):
        k = t[i] // (4 * HOUR)
        if k not in buckets:
            buckets[k] = [i, i]
            order.append(k)
        buckets[k][1] = i
    c4 = [d["close"][buckets[k][1]] for k in order]
    e21, e50 = _ema(c4, 21), _ema(c4, 50)
    up4 = {}
    for idx, k in enumerate(order):
        up4[k] = bool(e21[idx] and e50[idx] and c4[idx] > e50[idx] and e21[idx] > e50[idx])
    # daily: close > SMA200
    dkeys, dclose = [], []
    for i in range(n):
        k = t[i] // (24 * HOUR)
        if not dkeys or dkeys[-1] != k:
            dkeys.append(k)
            dclose.append(d["close"][i])
        else:
            dclose[-1] = d["close"][i]
    bull_d = {}
    for idx, k in enumerate(dkeys):
        w = dclose[max(0, idx - 199):idx + 1]
        bull_d[k] = (len(w) >= 200 and dclose[idx] > sum(w) / len(w))
    trend4, bull = [], []
    for i in range(n):
        dec = t[i] + HOUR                                              # decision at the bar's close
        k4 = dec // (4 * HOUR) - 1                                     # last 4h bar completed by then
        trend4.append(up4.get(k4, False))
        kd = dec // (24 * HOUR) - 1
        bull.append(bull_d.get(kd, None))
    up1 = [bool(x["ema21"][i] and x["ema50"][i] and x["ema200"][i] and x["ema21"][i] > x["ema50"][i]
                and d["close"][i] > x["ema200"][i]) for i in range(n)]
    sig = {}
    for name, fn in list(SETUP_FN.items()):
        sig[name] = [i for i in range(205, n - 2) if fn(i, d, x) == "long"]
    out = {"version": PREP_VERSION, "coin": coin, "t": t, "o": d["open"], "h": d["high"], "l": d["low"], "c": d["close"],
           "atr": x["atr"], "gate": gstate, "trend4": trend4, "up1": up1, "bull": bull, "sig": sig}
    with open(cache, "wb") as fh:
        pickle.dump(out, fh)
    return out


# ------------------------------------------------------------------ one trade's path
def trade_path(p, i, setup, fees, kind, *, entry="maker", stop_atr=4.0, rung=(1.0, 0.5), target_r=2.0,
               tp1_bars=8, horizon=96):
    """Fill, exits and R of one signal. Returns None if a limit entry never fills."""
    mk, tk = fees
    slip = SLIP[kind]
    o, h, l, c, n = p["o"], p["h"], p["l"], p["c"], len(p["c"])
    a = p["atr"][i]
    if not a or i + 2 >= n:
        return None
    if entry == "maker":
        lim, fill_j, px = c[i] * 0.999, None, None
        for j in range(i + 1, min(n, i + 4)):
            if o[j] <= lim:
                fill_j, px = j, o[j]
                break
            if l[j] <= lim:
                fill_j, px = j, lim
                break
        if fill_j is None:
            return None
        efee = mk
    else:
        fill_j, px, efee = i + 1, o[i + 1] * (1 + slip), tk
    stop = px - stop_atr * a
    risk = px - stop
    if risk <= 0:
        return None
    be = px * (1 + efee + tk) + px * slip                         # entry + fees (and the exit's slippage)
    rr, rfrac = (rung if rung else (None, 0.0))
    t1 = px + rr * risk if rr else None
    t2 = px + target_r * risk
    remaining, gross, cost, moved = 1.0, 0.0, efee * px, False
    exit_j, reason = None, None
    last = min(n - 1, fill_j + horizon)
    for j in range(fill_j, last + 1):
        if l[j] <= stop:                                           # pessimistic: the stop first
            f = (min(o[j], stop) if j > fill_j else stop) * (1 - 2 * slip)
            gross += remaining * (f - px)
            cost += remaining * f * tk
            exit_j, reason, remaining = j, ("breakeven" if moved else "stop"), 0.0
            break
        if t1 is not None and not moved and h[j] >= t1:
            gross += rfrac * (t1 - px)
            cost += rfrac * t1 * mk
            remaining -= rfrac
            moved, stop = True, max(stop, be)
        if h[j] >= t2:
            gross += remaining * (t2 - px)
            cost += remaining * t2 * mk
            exit_j, reason, remaining = j, "target", 0.0
            break
        if (tp1_bars and not moved and t1 is not None and j - fill_j + 1 >= tp1_bars) or j == last:
            f = c[j] * (1 - slip)
            gross += remaining * (f - px)
            cost += remaining * f * tk
            exit_j, reason, remaining = j, ("time_tp1" if not moved and j < last else "time"), 0.0
            break
    if exit_j is None:
        return None
    return {"coin": p["coin"], "setup": setup, "i": i, "t_dec": p["t"][i] + HOUR, "t_fill": p["t"][fill_j],
            "t_exit": p["t"][exit_j] + HOUR, "entry": px, "risk": risk, "stop_pct": risk / px * 100,
            "gross_r": gross / risk, "cost_r": cost / risk + (slip * 2 if entry == "taker" else slip),
            "r": (gross - cost) / risk, "reason": reason,
            "rt_cost_r": ((efee + tk) * px + 2 * slip * px) / risk}


# ------------------------------------------------------------------ the account
DEFAULT_RULES = {"gate": "on", "weekend": True, "regime": True, "btc_first": True, "dead_zone": True,
                 "cost_gate": True, "engine": True, "caps": True, "drawdown": True, "setups": SETUPS,
                 "entry": "maker", "stop_atr": 4.0, "rung": (1.0, 0.5), "target_r": 2.0, "tp1_bars": 8,
                 "horizon": 96, "risk_major": 0.01, "risk_meme": 0.005, "start": None, "end": None}


def candidates(preps, coins, fees, rules):
    out = []
    for coin in coins:
        p = preps[coin]
        kind = "major" if coin in MAJORS else "meme"
        for s in rules["setups"]:
            for i in p["sig"].get(s, []):
                tp = trade_path(p, i, s, fees, kind, entry=rules["entry"], stop_atr=rules["stop_atr"], rung=rules["rung"],
                                target_r=rules["target_r"], tp1_bars=rules["tp1_bars"], horizon=rules["horizon"])
                if tp is None:
                    continue
                tp.update(kind=kind, gate=p["gate"][i], trend4=p["trend4"][i], up1=p["up1"][i])
                out.append(tp)
    out.sort(key=lambda r: (r["t_dec"], r["coin"], r["setup"]))
    return out


def mt_hour(ms):
    dt = datetime.fromtimestamp(ms / 1000, timezone.utc)
    return (dt - timedelta(hours=6 if events.us_dst(dt.date()) else 7)).hour


def simulate(cands, btc, rules, equity0=10_000.0):
    """Replay the candidates through every Jarvus rule, in time order, on one account."""
    btc_t = btc["t"]
    btc_idx = {t + HOUR: k for k, t in enumerate(btc_t)}

    def btc_state(t_dec):
        k = btc_idx.get(t_dec)
        if k is None:
            return None, None
        return btc["bull"][k], btc["trend4"][k]

    eq, peak_eq = equity0, equity0
    r_cum, r_peak, pause_until, half_mode = 0.0, 0.0, 0, False
    open_q = []                                  # (t_exit, seq, trade)
    open_by_coin, open_majors, open_memes = {}, 0, 0
    day_key, day_r, day_losses_streak, day_major_trades = None, 0.0, 0, 0
    week_key, week_r = None, 0.0
    learn = {}                                   # setup|kind -> [sum_w, sum_wr, sum_wr2]
    pending_learn = []                           # (t_exit, key, r, weight)
    taken, skips, seq = [], {}, 0
    curve = [(cands[0]["t_dec"] if cands else 0, eq)]

    def skip(why):
        skips[why] = skips.get(why, 0) + 1

    def settle(until):
        nonlocal eq, peak_eq, r_cum, r_peak, open_majors, open_memes, day_r, day_losses_streak, week_r, pause_until, half_mode
        while open_q and open_q[0][0] <= until:
            te, _, tr = heapq.heappop(open_q)
            pnl = tr["risk_amt"] * tr["r"]
            eq += pnl
            curve.append((te, eq))
            peak_eq = max(peak_eq, eq)
            r_cum += tr["r"] * tr["size"]
            if r_cum > r_peak:
                r_peak, half_mode = r_cum, False
            if rules["drawdown"]:
                if r_peak - r_cum >= 10 and pause_until < te:
                    pause_until, half_mode = te + 7 * 24 * HOUR, True
                    r_peak = r_cum                                   # restart the count after the break
                elif r_peak - r_cum >= 5:
                    half_mode = True
            open_by_coin.pop(tr["coin"], None)
            if tr["kind"] == "major":
                open_majors -= 1
            else:
                open_memes -= 1
            dk = (te - 6 * HOUR) // (24 * HOUR)
            if dk == day_key:
                day_r += tr["r"] * tr["size"]
                day_losses_streak = day_losses_streak + 1 if tr["r"] < 0 else 0
            wk = (te - 6 * HOUR) // (7 * 24 * HOUR)
            if wk == week_key:
                week_r += tr["r"] * tr["size"]
        while pending_learn and pending_learn[0][0] <= until:
            _, key, r, w = heapq.heappop(pending_learn)
            s = learn.setdefault(key, [0.0, 0.0, 0.0])
            r = max(-3.0, min(3.0, r))
            s[0] += w
            s[1] += w * r
            s[2] += w * r * r

    for cd in cands:
        t = cd["t_dec"]
        if rules["start"] and t < rules["start"]:
            continue
        if rules["end"] and t >= rules["end"]:
            break
        settle(t)
        dk = (t - 6 * HOUR) // (24 * HOUR)
        if dk != day_key:
            day_key, day_r, day_losses_streak, day_major_trades = dk, 0.0, 0, 0
        wk = (t - 6 * HOUR) // (7 * 24 * HOUR)
        if wk != week_key:
            week_key, week_r = wk, 0.0
        kind, setup = cd["kind"], cd["setup"]
        size = 1.0
        dt = datetime.fromtimestamp(t / 1000, timezone.utc)
        if cd["coin"] in open_by_coin:
            skip("already in this coin")
            continue
        if rules["weekend"] and kind == "major" and dt.weekday() >= 5:
            skip("weekend (M4)")
            continue
        g = cd["gate"]
        if rules["gate"] != "off":
            if g == "Q":
                skip("gate QUIET")
                continue
            if rules["gate"] == "loud_only" and g != "L":
                skip("gate not LOUD")
                continue
            if g == "L":
                size *= 0.6
        bull, btc4 = btc_state(t)
        if rules["regime"]:
            if setup in TREND_SETUPS and not (cd["up1"] and cd["trend4"]):
                skip("trend setup without 1h+4h uptrend (M0)")
                continue
            if bull is False:
                if kind == "meme":
                    skip("bear regime: memes off")
                    continue
                if setup not in REVERSION_SETUPS:
                    skip("bear regime: only reversion setups")
                    continue
                size *= 0.5
        if rules["btc_first"] and kind == "meme" and btc4 is False:
            skip("BTC 4h trend down (BTC first)")
            continue
        if rules["dead_zone"] and kind == "meme" and 19 <= mt_hour(t) <= 23:
            skip("meme dead zone 7 PM-midnight MT")
            continue
        if rules["cost_gate"]:
            if cd["rt_cost_r"] > 0.33:
                skip("cost > 0.33R")
                continue
            if cd["rt_cost_r"] > 0.20:
                size *= 0.5
        key = f"{setup}|{kind}"
        shadow = False
        if rules["engine"]:
            s = learn.get(key)
            if s and s[0] > 0:
                n_eff, mean = s[0], s[1] / s[0]
                var = max(0.05, s[2] / s[0] - mean * mean) if n_eff >= 5 else 1.0
                sd = math.sqrt(var / n_eff)
                if n_eff >= 30 and mean + 1.64 * sd < 0:
                    skip("engine: benched")
                    shadow = True
                elif n_eff >= 8 and mean < -0.05:
                    skip("engine: negative learned edge")
                    shadow = True
                elif n_eff >= 8:
                    size *= max(0.5, min(1.5, 1 + 1.5 * mean))
        if shadow:
            heapq.heappush(pending_learn, (cd["t_exit"], key, cd["r"], 0.5))
            continue
        if rules["caps"]:
            if pause_until > t:
                skip("drawdown break (-10R)")
                continue
            if day_r <= -3:
                skip("daily -3R cap")
                continue
            if day_losses_streak >= 3:
                skip("3 losses in a row")
                continue
            if week_r <= -6:
                skip("weekly -6R cap")
                continue
            if kind == "major" and (open_majors >= 1 or day_major_trades >= 2):
                skip("majors: one position / 2 trades a day")
                continue
            if kind == "meme" and open_memes >= 2:
                skip("memes: 2 positions max")
                continue
        base = rules["risk_meme"] if kind == "meme" else rules["risk_major"]
        if setup == "sweep_reclaim":
            base = min(base, 0.005)
        if half_mode and rules["drawdown"]:
            size *= 0.5
        risk_pct = min(base * size, 0.01 if kind == "major" else 0.005)
        risk_amt = eq * risk_pct
        notional = risk_amt / (cd["risk"] / cd["entry"])
        if notional > eq:                                          # spot: no leverage
            risk_amt *= eq / notional
        tr = dict(cd, size=risk_amt / (eq * (rules["risk_meme"] if kind == "meme" else rules["risk_major"])),
                  risk_amt=risk_amt, risk_pct=risk_amt / eq)
        seq += 1
        heapq.heappush(open_q, (cd["t_exit"], seq, tr))
        heapq.heappush(pending_learn, (cd["t_exit"], key, cd["r"], 1.0))
        open_by_coin[cd["coin"]] = True
        if kind == "major":
            open_majors += 1
            day_major_trades += 1
        else:
            open_memes += 1
        taken.append(tr)
    settle(float("inf"))
    return taken, skips, curve, eq


def summarize(taken, skips, curve, eq, equity0=10_000.0, span=None):
    rs = [t["r"] for t in taken]
    n = len(rs)
    out = {"trades": n, "skips": dict(sorted(skips.items(), key=lambda kv: -kv[1])), "end_equity": round(eq, 2),
           "return_pct": round((eq / equity0 - 1) * 100, 2)}
    if n:
        wins = [r for r in rs if r > 0]
        losses = [r for r in rs if r <= 0]
        out.update(win_rate=round(len(wins) / n, 3), avg_r=round(sum(rs) / n, 4), sum_r=round(sum(rs), 2),
                   pf=round(sum(wins) / -sum(losses), 3) if losses and sum(losses) < 0 else None,
                   avg_cost_r=round(sum(t["cost_r"] for t in taken) / n, 4),
                   avg_gross_r=round(sum(t["gross_r"] for t in taken) / n, 4),
                   t_stat=round((sum(rs) / n) / (math.sqrt(max(1e-12, sum((r - sum(rs) / n) ** 2 for r in rs) / max(1, n - 1))) / math.sqrt(n)), 2) if n > 2 else None)
        peak, mdd = curve[0][1], 0.0
        for _, v in curve:
            peak = max(peak, v)
            mdd = max(mdd, 1 - v / peak)
        out["max_dd_pct"] = round(mdd * 100, 2)
        by = {}
        for tr in taken:
            b = by.setdefault(tr["setup"], [])
            b.append(tr["r"])
        out["by_setup"] = {k: {"n": len(v), "avg_r": round(sum(v) / len(v), 4)} for k, v in sorted(by.items())}
        per = {"A": [], "B": [], "C": []}
        for tr in taken:
            dt = datetime.fromtimestamp(tr["t_dec"] / 1000, timezone.utc)
            per["A" if dt < PERIOD_B else "B" if dt < PERIOD_C else "C"].append(tr)
        out["periods"] = {}
        for k, v in per.items():
            if v:
                out["periods"][k] = {"n": len(v), "avg_r": round(sum(x["r"] for x in v) / len(v), 4),
                                     "sum_r": round(sum(x["r"] for x in v), 2),
                                     "pnl": round(sum(x["risk_amt"] * x["r"] for x in v), 2)}
    if span:
        days = max(1.0, (span[1] - span[0]) / (24 * HOUR))
        out["trades_per_month"] = round(n / days * 30.4, 2)
        out["days"] = round(days)
    return out


# ------------------------------------------------------------------ battery
_G = {}


def _init(data_dir):
    coins = [c for c in MAJORS + MEMES if os.path.exists(os.path.join(data_dir, f"{c}_1h.csv"))]
    _G["preps"] = {c: prepare((data_dir, c)) for c in coins}
    _G["cands"] = {}


def _cands(group, fee, rules):
    coins = [c for c in (MAJORS if group == "majors" else MEMES if group == "memes" else MAJORS + MEMES) if c in _G["preps"]]
    key = (group, fee, rules["entry"], rules["stop_atr"], tuple(rules["rung"] or ()), rules["target_r"],
           rules["tp1_bars"], rules["horizon"], tuple(rules["setups"]))
    if key not in _G["cands"]:
        _G["cands"][key] = candidates(_G["preps"], coins, FEES[fee], rules)
    return _G["cands"][key]


def run_one(job):
    name, group, fee, over = job
    rules = dict(DEFAULT_RULES, **over)
    cands = _cands(group, fee, rules)
    taken, skips, curve, eq = simulate(cands, _G["preps"]["BTC"], rules)
    span = (rules["start"] or (cands[0]["t_dec"] if cands else 0), rules["end"] or (cands[-1]["t_dec"] if cands else 1))
    s = summarize(taken, skips, curve, eq, span=span)
    s.update(name=name, group=group, fees=fee, candidates=len(cands))
    return s


# v6.1: what the backtest supported (chosen on period A, checked on B and C; see references/jarvus-backtest.md)
V61 = {"setups": ["trend_pullback", "breakout_retest", "sweep_reclaim", "orb", "rsi2"], "gate": "loud_only",
       "tp1_bars": 0, "rung": None}

VARIANTS = {
    "jarvus_v6 (as written)": {},
    "no volatility gate": {"gate": "off"},
    "trade only when the gate says LOUD": {"gate": "loud_only"},
    "no weekend rule": {"weekend": False},
    "no trend/regime rule (M0)": {"regime": False},
    "no BTC-first rule": {"btc_first": False},
    "no meme dead zone": {"dead_zone": False},
    "no cost gate": {"cost_gate": False},
    "no decision engine (no learning)": {"engine": False},
    "no risk caps or drawdown protocol": {"caps": False, "drawdown": False},
    "taker entries (market orders)": {"entry": "taker"},
    "stop 2x ATR": {"stop_atr": 2.0},
    "stop 3x ATR": {"stop_atr": 3.0},
    "no 8-bar time stop (96h only)": {"tp1_bars": 0},
    "one exit at 2R (no half at 1R)": {"rung": None},
    "target 3R": {"target_r": 3.0},
    "80% Mode (half at +0.25R)": {"rung": (0.25, 0.5)},
    "only P1 trend pullback": {"setups": ["trend_pullback"]},
    "only P3 breakout retest": {"setups": ["breakout_retest"]},
    "only P4 sweep reclaim": {"setups": ["sweep_reclaim"]},
    "only P6 ORB (before the fix: 13:00 UTC all year)": {"setups": ["orb_legacy"]},
    "only P6 ORB (fixed: the US open's hour)": {"setups": ["orb"]},
    "only RSI(2) dip": {"setups": ["rsi2"]},
    "control: every 12th bar, all rules": {"setups": ["benchmark"]},
    "control: every 12th bar, no rules": {"setups": ["benchmark"], "gate": "off", "weekend": False, "regime": False,
                                          "btc_first": False, "dead_zone": False, "cost_gate": False, "engine": False,
                                          "caps": False, "drawdown": False},
}


def battery(data_dir, groups, fees, windows, workers, extra=None, window_versions=None):
    jobs = [(name, g, f, over) for g in groups for f in fees for name, over in (extra or VARIANTS).items()]
    window_versions = window_versions or {"": {}}
    rng = random.Random(20261002)
    preps_t = {}
    with open(os.path.join(data_dir, "BTC_1h.csv")) as fh:
        rows = list(csv.reader(fh))
        t_first = int(datetime.strptime(rows[1][0], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp() * 1000)
        t_last = int(datetime.strptime(rows[-1][0], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp() * 1000)
    lo = t_first + 300 * 24 * HOUR                               # the 200-day trend and the gate need history
    for g in groups:
        for k in range(windows):
            s = lo + rng.randrange(int((t_last - lo - 90 * 24 * HOUR) // HOUR)) * HOUR
            for vname, vover in window_versions.items():
                jobs.append((f"window {k + 1:03d}{vname}", g, "ndax", dict(vover, start=s, end=s + 90 * 24 * HOUR)))
    with Pool(workers, initializer=_init, initargs=(data_dir,)) as pool:
        res = pool.map(run_one, jobs, chunksize=1)
    return res


def fmt_row(r):
    p = r.get("periods", {})
    pc = lambda k: f"{p[k]['avg_r']:+.3f} ({p[k]['n']})" if k in p else "—"  # noqa: E731
    return (f"| {r['name']} | {r['trades']} | {r.get('win_rate', 0) * 100:.0f}% | {r.get('avg_r', 0):+.3f} | "
            f"{r.get('t_stat') if r.get('t_stat') is not None else '—'} | {r['return_pct']:+.1f}% | {r.get('max_dd_pct', 0):.1f}% | "
            f"{pc('A')} | {pc('B')} | {pc('C')} |")


def report(res, path):
    L = ["# Jarvus backtest report", "", f"Generated {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())} by `scripts/system_test.py`. "
         f"{len(res)} backtests. R = profit or loss in units of the risk taken, after fees and slippage. Periods: A design "
         "(before 2025-03-20), B validation (to 2025-12-22), C test (from 2025-12-23; the gate never saw it).", ""]
    for g in sorted({r["group"] for r in res}):
        for f in sorted({r["fees"] for r in res if r["group"] == g and not r["name"].startswith("window")}):
            rows = [r for r in res if r["group"] == g and r["fees"] == f and not r["name"].startswith("window")]
            if not rows:
                continue
            L += [f"## {g}, {f} fees", "", "| Variant | Trades | Win | Avg R | t | Return | Max DD | A avg R (n) | B avg R (n) | C avg R (n) |",
                  "|---|---|---|---|---|---|---|---|---|---|"] + [fmt_row(r) for r in rows] + [""]
        for tag in sorted({r["name"][10:] for r in res if r["group"] == g and r["name"].startswith("window")}):
            wins = [r for r in res if r["group"] == g and r["name"].startswith("window") and r["name"][10:] == tag]
            rets = sorted(r["return_pct"] for r in wins)
            L += [f"## {g}: {len(wins)} random 90-day windows ({tag.strip(' |') or 'rules as written'}, NDAX fees, fresh account each time)", "",
                  f"Return per window: median {rets[len(rets) // 2]:+.2f}%, 10th percentile {rets[len(rets) // 10]:+.2f}%, "
                  f"90th {rets[(9 * len(rets)) // 10]:+.2f}%, best {rets[-1]:+.2f}%, worst {rets[0]:+.2f}%; "
                  f"positive in {sum(1 for x in rets if x > 0)} of {len(rets)}; average trades per window "
                  f"{sum(r['trades'] for r in wins) / len(wins):.1f}; average return {sum(rets) / len(rets):+.2f}%; "
                  f"windows with no trade {sum(1 for r in wins if not r['trades'])}; of the windows that traded, "
                  f"{sum(1 for r in wins if r['trades'] and r['return_pct'] > 0)} up and "
                  f"{sum(1 for r in wins if r['trades'] and r['return_pct'] <= 0)} flat or down.", ""]
    with open(path, "w") as fh:
        fh.write("\n".join(L) + "\n")


def main():
    ap = argparse.ArgumentParser(description="Backtest Jarvus's whole rulebook on hourly crypto history.")
    ap.add_argument("--data", required=True)
    ap.add_argument("--download", action="store_true")
    ap.add_argument("--battery", action="store_true", help="every rule switched off one at a time, x groups x fees, + windows")
    ap.add_argument("--compare", action="store_true", help="v6 as written vs v6.1, x groups x fees, + windows for both")
    ap.add_argument("--version", default="v6.1", choices=["v6", "v6.1"], help="rules for a single run")
    ap.add_argument("--group", default="majors", choices=["majors", "memes", "all"])
    ap.add_argument("--fees", default="ndax", choices=sorted(FEES))
    ap.add_argument("--windows", type=int, default=100)
    ap.add_argument("--groups", default="majors,memes")
    ap.add_argument("--fee-levels", default="ndax,kraken,low")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--out")
    ap.add_argument("--md")
    a = ap.parse_args()
    if a.download:
        download(a.data, MAJORS + MEMES)
    coins = [c for c in MAJORS + MEMES if os.path.exists(os.path.join(a.data, f"{c}_1h.csv"))]
    t0 = time.time()
    with Pool(min(a.workers, len(coins))) as pool:
        pool.map(prepare, [(a.data, c) for c in coins])
    print(f"prepared {len(coins)} coins in {time.time() - t0:.0f}s", flush=True)
    if a.compare:
        res = battery(a.data, a.groups.split(","), a.fee_levels.split(","), a.windows, a.workers,
                      extra={"jarvus_v6 (as written)": {}, "jarvus_v6.1 (backtest-supported)": V61},
                      window_versions={" | v6 as written": {}, " | v6.1": V61})
    elif a.battery:
        res = battery(a.data, a.groups.split(","), a.fee_levels.split(","), a.windows, a.workers)
    else:
        _init(a.data)
        res = [run_one((f"jarvus_{a.version}", a.group, a.fees, V61 if a.version == "v6.1" else {}))]
    if a.out:
        with open(a.out, "w") as fh:
            json.dump(res, fh, indent=1, default=str)
    if a.md:
        report(res, a.md)
    for r in res[:60]:
        print(fmt_row(r).replace("|", " ").strip(), f"[{r['group']}, {r['fees']}]")
    print(f"{len(res)} backtests in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
