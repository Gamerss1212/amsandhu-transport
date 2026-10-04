#!/usr/bin/env python3
"""Train one ULTRON council per chart timeframe (5m, 15m, 30m, 1h, 2h, 4h, 1D) for the TradingView indicator.

For each timeframe, on that timeframe's own bars (Coinbase, UTC-aligned, built from 5m or 1h candles):
  gate     the 14-feature logistic volatility gate refit on this timeframe (LOUD = next 12 bars' range in the top
           third of the last 720 bars' finished 12-bar ranges)
  trend    EMA21 > EMA50 and close > EMA200 on the chart, and the previous completed higher-timeframe bar
           (close > EMA50 and EMA21 > EMA50); Bitcoin regime = previous completed UTC day above its 200-day average
  agents   every Pine-portable signal x {majors, memes} x {LOUD, LOUD + uptrend}; exits: limit 0.1% under the close
           (3 bars), stop 4x ATR(14), one exit at 2R, 96 bars (charts faster than 1h: scaled, see exit_profile),
           NDAX fees + slippage
  brain    train.py's walk-forward (quarterly re-selection of up to 25 agents from finished signals only, learning
           as signals finish) + an improvement loop; development / validation / untouched test as in train.py
These are exactly the formulas build_pine.py writes into Pine (request.security(..., [1], lookahead_on) for the
higher timeframe and Bitcoin, the chart's own bars for everything else).

  python3 ultron/tools/train_tf.py --h1 <dir with *_1h.csv> --m5 <dir with *_5m.csv> [--tfs 5m,15m,...] [--iters 30]
"""

from __future__ import annotations

import argparse
import json
import math
import os
import pickle
import sys
import time
from datetime import datetime, timezone
from multiprocessing import Pool

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(os.path.dirname(ROOT), "jarvus", "scripts"))
sys.path.insert(0, os.path.join(ROOT, "core"))
sys.path.insert(0, os.path.join(ROOT, "tv"))
sys.path.insert(0, HERE)
import pine_gate as pg  # noqa: E402
import signals as sg  # noqa: E402
import system_test as st  # noqa: E402
import train as T  # noqa: E402
from brain import Brain  # noqa: E402
from snapshot import load_csv  # noqa: E402

MIN = 60_000
DAY = 86_400_000
# tf: (bar ms, source file, higher timeframe multiplier label for Pine, how to bucket the higher timeframe)
TFS = {"5m": (5 * MIN, "5m", "15"), "15m": (15 * MIN, "5m", "60"), "30m": (30 * MIN, "5m", "120"),
       "1h": (60 * MIN, "1h", "240"), "2h": (120 * MIN, "1h", "480"), "4h": (240 * MIN, "1h", "D"), "1D": (DAY, "1h", "W"),
       "1Dm": (DAY, "mkt", "W")}                                       # 1Dm = daily council for stocks, ETFs, forex
st.FEES.setdefault("markets", (0.0005, 0.0005))                         # stocks/ETFs/forex: 0.05% per side (spread + fees)
HTF_MS = {"15": 15 * MIN, "60": 60 * MIN, "120": 120 * MIN, "240": 240 * MIN, "480": 480 * MIN, "D": DAY, "W": 7 * DAY}
SIGNALS = sorted(s for s in T.TV_SIGNALS if s not in sg.PLAYBOOK)
EXITS = "scaled"                                                       # --exits: "scaled" or "fixed" (4x ATR, 96 bars)


def exit_profile(tf):
    """Charts faster than 1h: stop and hold scaled to the 1-hour structure, so the fee stays a small share of the stop.
    ATR grows roughly with the square root of time, so stop x sqrt(1h / tf) and hold x (1h / tf) bars."""
    size, _, htf = TFS[tf]
    if EXITS == "fixed":
        return 4.0, 4.0, 96
    sc = max(1.0, math.sqrt(3_600_000 / size))
    sh = max(1.0, math.sqrt(3_600_000 / HTF_MS[htf]))
    return round(4.0 * sc, 3), round(4.0 * sh, 3), int(round(96 * sc * sc))
COINS = T.MAJORS + T.MEMES
MKT_DIR = None                                                         # --mkt: <NAME>_1d.csv from download_markets.py


def symbols(tf, mkt_dir):
    if tf == "1Dm":
        return sorted(f[:-7] for f in os.listdir(mkt_dir) if f.endswith("_1d.csv"))
    return COINS


def bucket(t_ms, size_ms, weekly=False):
    return (t_ms // DAY + 3) // 7 if weekly else t_ms // size_ms        # weeks start Monday 00:00 UTC


def load(path):
    d = load_csv(path)
    t = np.array([int(x.timestamp() * 1000) for x in d["ts"]], dtype=np.int64)
    return t, *(np.array(d[k], float) for k in ("open", "high", "low", "close", "volume"))


def aggregate(t, o, h, l, c, v, size_ms, weekly=False):
    k = bucket(t, size_ms, weekly)
    br = np.flatnonzero(np.diff(k)) + 1
    s = np.concatenate([[0], br])
    e = np.concatenate([br, [len(t)]]) - 1
    bt = (k[s] * 7 - 3) * DAY if weekly else k[s] * size_ms
    out = (bt, o[s], np.maximum.reduceat(h, s), np.minimum.reduceat(l, s), c[e], np.add.reduceat(v, s))
    return tuple(x[:-1] for x in out)                                   # drop the last (possibly unfinished) bar


def ema_first(x, n):
    """Pine ta.ema: seeded with the first value."""
    out = np.empty(len(x))
    a = 2 / (n + 1)
    e = x[0]
    for i, xv in enumerate(x):
        e = xv if i == 0 else a * xv + (1 - a) * e
        out[i] = e
    return out


def btc_bull_by_day(h1_dir):
    t, o, h, l, c, v = load(os.path.join(h1_dir, "BTC_1h.csv"))
    dt, _, _, _, dc, _ = aggregate(t, o, h, l, c, v, DAY)
    out = {}
    for i in range(len(dc)):
        if i >= 199:
            out[int(dt[i] // DAY)] = bool(dc[i] > dc[i - 199:i + 1].mean())
    return out


def build_coin(job):
    tf, coin, h1_dir, m5_dir, gate_model, bull_day, exits, mkt_dir = job
    market = tf == "1Dm"
    global EXITS
    EXITS = exits
    size, src, htf = TFS[tf]
    stop_c, stop_h, hold = exit_profile(tf)
    path = os.path.join(mkt_dir, f"{coin}_1d.csv") if market else os.path.join(m5_dir if src == "5m" else h1_dir, f"{coin}_{src}.csv")
    if not os.path.exists(path):
        return coin, [], None
    t, o, h, l, c, v = load(path)
    if not market and (src == "5m" and tf != "5m" or src == "1h" and tf != "1h"):
        t, o, h, l, c, v = aggregate(t, o, h, l, c, v, size)
    n = len(c)
    if n < 600:
        return coin, [], None
    if gate_model is None:                                              # pass 1: features for fitting the gate
        return coin, None, (t, o, h, l, c, v)
    gate = pg.states(t, o, h, l, c, v, gate_model)
    e21, e50, e200 = ema_first(c, 21), ema_first(c, 50), ema_first(c, 200)
    up1 = (e21 > e50) & (c > e200)
    weekly = htf == "W"
    ht, _, _, _, hc, _ = aggregate(t, o, h, l, c, v, HTF_MS[htf], weekly)
    h21, h50 = ema_first(hc, 21), ema_first(hc, 50)
    hup = (hc > h50) & (h21 > h50)
    hk = bucket(ht, HTF_MS[htf], weekly)
    hmap = dict(zip(hk.tolist(), hup.tolist()))
    bk = bucket(t, HTF_MS[htf], weekly)
    # the chart bar that closes a higher-timeframe bar (TradingView: time_close == time_close(htf))
    nxt = (np.append(bk[1:], bk[-1] + 1) != bk)
    ends = np.array([(int(k) * 7 - 3 + 7) * DAY if weekly else (int(k) + 1) * HTF_MS[htf] for k in bk])
    is_end = nxt if market else (t + size == ends) & nxt                # markets: the week's last trading day
    # higher-timeframe trend: the bar that just closed (on its last chart bar), otherwise the previous completed one
    upH = np.array([hmap.get(int(k) if e else int(k) - 1, False) for k, e in zip(bk, is_end)])
    if market:                                                         # markets: own close vs its 200-day average, previous day
        sma = np.full(n, np.nan)
        sma[199:] = np.convolve(c, np.ones(200) / 200, "valid")
        prev = np.concatenate([[np.nan], (c > sma).astype(float)[:-1]])
        prev[:200] = np.nan
        bull = [None if x != x else bool(x) for x in prev]
    else:
        bull = [bull_day.get(int(x // DAY) - 1) for x in t]             # previous completed UTC day
    A = pg.atr(h, l, c)
    bars_day = max(1, int(DAY // size))
    S, _, _ = sg.vector_signals(t, o, h, l, c, v, bars_day)
    group, kind = ("markets", "major") if market else ("majors", "major") if coin in T.MAJORS else ("memes", "meme")
    fees = st.FEES["markets" if market else "ndax"]
    p = {"coin": coin, "t": t.tolist(), "o": o.tolist(), "h": h.tolist(), "l": l.tolist(), "c": c.tolist(),
         "atr": [None if x != x else float(x) for x in A]}
    allvars = size >= 120 * MIN                                        # 2h and slower: NORMAL periods too
    out = []

    def emit(j, i, sid, key, stop_atr):
        """signal at bar j (chart bar i decides) -> one event per matching condition."""
        if not p["atr"][i] or not (0.5 <= stop_atr <= 60):
            return
        g = gate[i]
        if g == "U" or (not allvars and g != "L"):
            return
        tr = st.trade_path(p, int(i), "x", fees, kind, entry="maker", stop_atr=stop_atr, rung=None, target_r=2.0,
                           tp1_bars=0, horizon=hold)
        if tr is None:
            return
        t_dec = int(t[i]) + size
        upj = bool(up1[i] and upH[i])
        base = (t_dec, None, coin, tr["t_exit"] - T.HOUR + size, float(tr["r"]), float(tr["rt_cost_r"]), float(tr["stop_pct"]),
                g, bull[i], upj, False if market else T.mt_weekend(t_dec), float(c[i]))
        loud = g == "L"
        for var, ok in (("any", allvars), ("loud", loud), ("trend", allvars and upj), ("loudtrend", loud and upj)):
            if ok:
                out.append(base[:1] + (f"{sid}|{group}|{key}|{var}",) + base[2:])

    for sid in SIGNALS:                                                # signals on the chart's own bars
        m = S.get(sid)
        if m is None or (sid in ("rally_24h", "drop_24h") and 30 * bars_day > 4500):
            continue                                                   # Pine keeps at most ~5,000 bars of history
        last = -10 ** 9
        for j in np.flatnonzero(m):
            if j < 250 or j - last < 12 or j >= n - 3:
                continue
            last = j
            emit(j, j, sid, tf, stop_c)
    # signals on the higher timeframe's bars, acted on at the chart bar that closes that bar
    hv = aggregate(t, o, h, l, c, v, HTF_MS[htf], weekly)[5]
    _, ho, hh, hl, _, _ = aggregate(t, o, h, l, c, v, HTF_MS[htf], weekly)
    hbd = max(1, int(DAY // HTF_MS[htf]))
    SH, _, _ = sg.vector_signals(ht, ho, hh, hl, hc, hv, hbd)
    AH = pg.atr(hh, hl, hc)
    end_of = {int(k): i for i, (k, e) in enumerate(zip(bk.tolist(), is_end.tolist())) if e}
    for sid in SIGNALS:
        m = SH.get(sid)
        if m is None or (sid in ("rally_24h", "drop_24h") and 30 * hbd > 4500):
            continue
        last = -10 ** 9
        for jh in np.flatnonzero(m):
            if jh < 60 or jh - last < 3 or AH[jh] != AH[jh]:
                continue
            last = jh
            i = end_of.get(int(hk[jh]))                                # decide when the higher-timeframe bar closes
            if i is None or i < 250 or i >= n - 3 or not p["atr"][i]:
                continue
            emit(jh, i, sid, tf + "+", round(stop_h * float(AH[jh]) / p["atr"][i], 3))
    return coin, out, None


def train_tf(tf, a, bull_day, base_params, log):
    t0 = time.time()
    stop_c, stop_h, hold = exit_profile(tf)
    tag = "" if (stop_c, stop_h, hold) == (4.0, 4.0, 96) else f"_x{stop_c:g}_{hold}"
    cache = os.path.join(a.cache, f"ultron_tf_{tf}{tag}.pkl")
    if os.path.exists(cache):
        with open(cache, "rb") as fh:
            events, defs, gate_model, first_t = pickle.load(fh)
    else:
        with Pool(a.workers) as pool:
            raw = pool.map(build_coin, [(tf, c, a.h1, a.m5, None, None, EXITS, a.mkt) for c in symbols(tf, a.mkt)])
        data = [x[2] for x in raw if x[2] is not None]
        first_t = min(int(d[0][0]) for d in data)
        bd = max(1, int(DAY // TFS[tf][0]))
        gate_model = pg.fit(data, T.B_START, T.C_START, window=min(720, max(120, 30 * bd)))
        with Pool(a.workers) as pool:
            got = pool.map(build_coin, [(tf, c, a.h1, a.m5, gate_model, bull_day, EXITS, a.mkt) for c in symbols(tf, a.mkt)])
        events = sorted((e for _, evs, _ in got for e in evs), key=lambda e: (e[0], e[1], e[2]))
        defs = {}
        for e in events:
            if e[1] not in defs:
                sid, group, tf_, var = e[1].split("|")
                name, side, fam, rule = sg.DEFS[sid]
                defs[e[1]] = {"signal": sid, "group": group, "tf": tf_, "htf": tf_.endswith("+"), "variant": var, "family": fam,
                              "label": name, "side": side, "rule": rule}
        with open(cache, "wb") as fh:
            pickle.dump((events, defs, gate_model, first_t), fh)
    # walk-forward starts once a year of history exists (quarter-aligned)
    d0 = datetime.fromtimestamp((first_t + 365 * DAY) / 1000, timezone.utc)
    q0 = datetime(d0.year, ((d0.month - 1) // 3) * 3 + 1, 1, tzinfo=timezone.utc)
    T.WF_START = max(T.ms(2022, 1, 1), int(q0.timestamp() * 1000))
    log(f"[{tf}] {len(defs)} candidates, {len(events):,} LOUD signals, walk-forward from {datetime.fromtimestamp(T.WF_START / 1000, timezone.utc):%Y-%m-%d}, "
        f"gate LOUD precision A/B/C {gate_model['scores']['A']['loud_precision']}/{gate_model['scores']['B']['loud_precision']}/"
        f"{gate_model['scores']['C']['loud_precision']}% ({time.time() - t0:.0f}s)")
    it_log = []
    params = T.improve(events, defs, a.iters, it_log, base_params)
    final = T.simulate(events, defs, params, record=True)
    if tf == "1Dm":                                                    # market costs, not NDAX
        stress = {"fees x2": T.simulate(events, defs, params, adj=lambda e: 0.1 / e[6])["metrics"],
                  "slippage x3": T.simulate(events, defs, params, adj=lambda e: 0.08 / e[6])["metrics"]}
    else:
        stress = T.stress(events, defs, params)
    win = T.windows(final["trades"], T.WF_START, events[-1][0]) if final["trades"] else None
    boot = T.bootstrap(final["trades"]) if final["trades"] else {}
    brain = final["brain"]
    chosen = final["selected"][-1][1] if final["selected"] else []
    cst = final["cstat"]
    chosen = sorted(chosen, key=lambda c: -(cst[c][1] / cst[c][0]))
    agents = []
    for rank, cid in enumerate(chosen):
        d = defs[cid]
        ev = {"agent": cid, "fam": d["family"], "group": d["group"], "gate": "L"}
        edges = {}
        for key, b in (("bull", True), ("bear", False), ("na", None)):
            m, se, _ = brain.estimate(dict(ev, bull=b))
            edges[key] = [round(m, 5), round(se, 5)]
        agents.append({"id": cid, "name": T.NAMES[rank], "signal": d["signal"], "label": d["label"], "group": d["group"],
                       "htf": d["htf"], "variant": d["variant"], "family": d["family"], "signals": cst[cid][0],
                       "avg_r": round(cst[cid][1] / cst[cid][0], 4), "edges": edges})
    model = {"tf": "1D" if tf == "1Dm" else tf, "market": tf == "1Dm", "symbols": symbols(tf, a.mkt) if tf == "1Dm" else COINS,
             "htf": TFS[tf][2], "trained": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
             "data_from": datetime.fromtimestamp(first_t / 1000, timezone.utc).strftime("%Y-%m-%d"),
             "data_end": datetime.fromtimestamp(events[-1][0] / 1000, timezone.utc).strftime("%Y-%m-%d") if events else None,
             "walk_forward_from": datetime.fromtimestamp(T.WF_START / 1000, timezone.utc).strftime("%Y-%m-%d"),
             "exit": {"stop_chart": stop_c, "stop_htf": stop_h, "hold": hold},
             "params": params, "gate": gate_model, "agents": agents,
             "backtest": {"metrics": final["metrics"], "decisions": final["decisions"], "stress": {k: v["all"] for k, v in stress.items()},
                          "windows": win, "bootstrap": boot, "iterations": len(it_log) - 1,
                          "kept": sum(1 for x in it_log if x["kept"]) - 1}}
    out_dir = a.out or os.path.join(ROOT, "tv", "models")
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, f"{'1D_markets' if tf == '1Dm' else tf}.json"), "w") as fh:
        json.dump(model, fh, separators=(",", ":"))
    m = final["metrics"]
    log(f"[{tf}] agents {len(agents)} · dev {T.fmt(m['dev'])} | B {T.fmt(m['B'])} | C {T.fmt(m['C'])} | all {T.fmt(m['all'])} "
        f"({time.time() - t0:.0f}s)")
    return model


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--h1", required=True)
    ap.add_argument("--m5", required=True)
    ap.add_argument("--tfs", default="1h,2h,4h,1D,5m,15m,30m")
    ap.add_argument("--iters", type=int, default=150)
    ap.add_argument("--exits", choices=["scaled", "fixed"], default="scaled")
    ap.add_argument("--mkt", default=None, help="dir with <NAME>_1d.csv (download_markets.py) for the 1Dm markets council")
    ap.add_argument("--out", default=None, help="write models here instead of ultron/tv/models")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--cache", default=None)
    a = ap.parse_args()
    a.cache = a.cache or a.h1
    global EXITS
    EXITS = a.exits
    with open(os.path.join(ROOT, "tv", "tv_model.json")) as fh:
        base = dict(json.load(fh)["params"], gate_rule="loud_only", variants="all")
    base["n_agents"] = 25
    bull_day = btc_bull_by_day(a.h1)

    def log(msg):
        print(f"{datetime.now():%H:%M:%S} {msg}", flush=True)
    for tf in a.tfs.split(","):
        train_tf(tf, a, bull_day, base, log)


if __name__ == "__main__":
    main()
