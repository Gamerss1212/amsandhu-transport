#!/usr/bin/env python3
"""Backtest both TradingView indicators on every timeframe, from the same data and models they were built from.

ULTRON Radar (the volatility forecast), per timeframe and market group, per period (A = fit, B = validation,
C = untouched test since Dec 2025):
  how often each call was right: LOUD (next 12 bars' range in the top third of the last month), QUIET (bottom
  third), and the stricter VERY LOUD / VERY QUIET tiers (thresholds set on period A only), the AUC, how often each
  call fires, and how big the next 12 bars actually moved after each call.
ULTRON Council, per timeframe:
  re-runs the walk-forward simulation from the cached signals and checks it reproduces the model file, then replays
  every trade it took with different exit styles (same entries, same sizes): 2R, 1.5R, 1R, 0.5R, and "ladders" that
  sell half early and move the stop to breakeven. Win rate = share of trades that closed with a profit after fees.

  python3 ultron/tools/backtest_all.py --h1 <hourly dir> --m5 <5m dir> --mkt <daily markets dir> [--tfs 1h,4h]
Writes ultron/tv/backtest/results.json and adds the VERY LOUD / VERY QUIET thresholds to ultron/tv/models/*.json.
"""

from __future__ import annotations

import argparse
import json
import os
import pickle
import sys
import time
from datetime import datetime, timezone

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import train_tf as F  # noqa: E402
from train_tf import T, pg, st  # noqa: E402

ROOT = os.path.dirname(HERE)
MODELS = os.path.join(ROOT, "tv", "models")
DAY = F.DAY
STYLES = [  # name, rung (sell fraction at R, then stop to breakeven), final target R
    ("2R (trained)", None, 2.0),
    ("1.5R", None, 1.5),
    ("1R", None, 1.0),
    ("0.5R", None, 0.5),
    ("half at 1R, rest 2R", (1.0, 0.5), 2.0),
    ("half at 0.5R, rest 2R", (0.5, 0.5), 2.0),
    ("half at 0.5R, rest 1R", (0.5, 0.5), 1.0),
]


def model_file(tf):
    return os.path.join(MODELS, "1D_markets.json" if tf == "1Dm" else f"{tf}.json")


def period(t):
    return "A" if t < T.B_START else "B" if t < T.C_START else "C"


def bars(tf, a):
    """Per symbol: (t, o, h, l, c, v) arrays for this timeframe, exactly as the trainer built them."""
    out = {}
    for sym in F.symbols(tf, a.mkt):
        coin, _, arr = F.build_coin((tf, sym, a.h1, a.m5, None, None, "scaled", a.mkt))
        if arr is not None:
            out[sym] = arr
    return out


def group_of(tf, sym):
    return "markets" if tf == "1Dm" else "majors" if sym in T.MAJORS else "memes"


# ------------------------------------------------------------------ Radar
def radar(tf, data, m):
    g = m["gate"]
    mu, sd = np.array(g["mean"]), np.array(g["std"])
    wl, wq = np.array(g["w_loud"]), np.array(g["w_quiet"])
    bd = max(1, int(DAY // F.TFS[tf][0]))
    window = min(720, max(120, 30 * bd))
    rows = []
    for sym, (t, o, h, l, c, v) in data.items():
        X = pg.features(t, o, h, l, c, v)
        yl, yq = pg.labels(h, l, c, window)
        n = len(c)
        fwd = np.full(n, np.nan)
        hh, ll = pg.highest(h, pg.H), pg.lowest(l, pg.H)
        fwd[:n - pg.H] = (hh[pg.H:] - ll[pg.H:]) / c[:n - pg.H] * 100
        with np.errstate(invalid="ignore", over="ignore"):
            Z = (X - mu) / sd
            pl = 1 / (1 + np.exp(-(Z @ wl)))
            pq = 1 / (1 + np.exp(-(Z @ wq)))
        ok = ~np.isnan(X).any(axis=1) & ~np.isnan(yl) & ~np.isnan(yq)
        per = np.array([period(x) for x in t])
        rows.append((group_of(tf, sym), per[ok], pl[ok], pq[ok], yl[ok], yq[ok], fwd[ok]))
    G = np.concatenate([np.full(len(r[1]), r[0]) for r in rows])
    PER = np.concatenate([r[1] for r in rows])
    PL, PQ, YL, YQ, FWD = (np.concatenate([r[k] for r in rows]) for k in (2, 3, 4, 5, 6))
    A = PER == "A"
    t_vl = float(np.quantile(PL[A], 0.99))
    t_vq = float(np.quantile(PQ[A], 0.99))
    out = {"window": window, "t_vloud": t_vl, "t_vquiet": t_vq, "rows": {}}
    for grp in sorted(set(G)) + ["all"]:
        for p_ in ("A", "B", "C"):
            sel = (PER == p_) & ((G == grp) if grp != "all" else True)
            if sel.sum() < 50:
                continue
            pl_, pq_, yl_, yq_, f_ = PL[sel], PQ[sel], YL[sel], YQ[sel], FWD[sel]
            L = pl_ >= g["t_loud"]
            Q = (pq_ >= g["t_quiet"]) & ~L
            VL = pl_ >= t_vl
            VQ = (pq_ >= t_vq) & ~L
            N = ~L & ~Q
            pr = lambda m_, y: (round(float(y[m_].mean()) * 100, 1), int(m_.sum())) if m_.any() else (None, 0)   # noqa: E731
            med = lambda m_: round(float(np.median(f_[m_])), 2) if m_.any() else None                          # noqa: E731
            out["rows"][f"{grp}|{p_}"] = {
                "bars": int(sel.sum()), "base_loud": round(float(yl_.mean()) * 100, 1), "base_quiet": round(float(yq_.mean()) * 100, 1),
                "auc_loud": round(pg.auc(pl_, yl_), 3), "auc_quiet": round(pg.auc(pq_, yq_), 3),
                "loud": pr(L, yl_), "very_loud": pr(VL, yl_), "quiet": pr(Q, yq_), "very_quiet": pr(VQ, yq_),
                "loud_share": round(float(L.mean()) * 100, 2), "very_loud_share": round(float(VL.mean()) * 100, 2),
                "quiet_share": round(float(Q.mean()) * 100, 2),
                "move_all": med(np.ones(len(f_), bool)), "move_loud": med(L), "move_very_loud": med(VL), "move_quiet": med(Q),
                "move_normal": med(N)}
    return out


# ------------------------------------------------------------------ Council
def council(tf, data, m, a):
    ex = m.get("exit", {"stop_chart": 4.0, "stop_htf": 4.0, "hold": 96})
    tag = "" if (ex["stop_chart"], ex["stop_htf"], ex["hold"]) == (4.0, 4.0, 96) else f"_x{ex['stop_chart']:g}_{ex['hold']}"
    path = os.path.join(a.h1, f"ultron_tf_{tf}{tag}.pkl")
    with open(path, "rb") as fh:
        events, defs, _, first_t = pickle.load(fh)
    d0 = datetime.fromtimestamp((first_t + 365 * DAY) / 1000, timezone.utc)
    q0 = datetime(d0.year, ((d0.month - 1) // 3) * 3 + 1, 1, tzinfo=timezone.utc)
    T.WF_START = max(T.ms(2022, 1, 1), int(q0.timestamp() * 1000))
    res = T.simulate(events, defs, m["params"], record=True)
    same = all(res["metrics"][k]["n"] == m["backtest"]["metrics"][k]["n"] and
               abs(res["metrics"][k]["avg_r"] - m["backtest"]["metrics"][k]["avg_r"]) < 1e-6 for k in ("dev", "B", "C", "all"))
    trades = res["trades"]
    size = F.TFS[tf][0]
    ev_of = {(e[0], e[1], e[2]): e for e in events}
    fees = st.FEES["markets" if tf == "1Dm" else "ndax"]
    preps = {}
    alt = {s[0]: [] for s in STYLES}
    check = []
    for x in trades:
        e = ev_of[(x["t"], x["cid"], x["coin"])]
        sym = x["coin"]
        if sym not in preps:
            t, o, h, l, c, v = data[sym]
            A = pg.atr(h, l, c)
            preps[sym] = ({"coin": sym, "t": t.tolist(), "o": o.tolist(), "h": h.tolist(), "l": l.tolist(), "c": c.tolist(),
                           "atr": [None if q != q else float(q) for q in A]}, {int(q): k for k, q in enumerate(t)})
        p, idx = preps[sym]
        i = idx[int(x["t"]) - size]
        lim = p["c"][i] * 0.999
        px = None
        for j in range(i + 1, min(len(p["c"]), i + 4)):
            if p["o"][j] <= lim:
                px = p["o"][j]
                break
            if p["l"][j] <= lim:
                px = lim
                break
        stop_atr = e[6] / 100 * px / p["atr"][i]
        kind = "major" if tf == "1Dm" or sym in T.MAJORS else "meme"
        for name, rung, tgt in STYLES:
            tr = st.trade_path(p, i, "x", fees, kind, entry="maker", stop_atr=stop_atr, rung=rung, target_r=tgt, tp1_bars=0,
                               horizon=int(ex["hold"]))
            alt[name].append(dict(x, r=float(tr["r"])))
        check.append(abs(alt[STYLES[0][0]][-1]["r"] - x["r"]) < 1e-6)
    out = {"reproduces_model_file": same, "replay_matches_2R": f"{sum(check)}/{len(check)}", "styles": {}}
    for name, _, _ in STYLES:
        tr = alt[name]
        met = T.metrics(tr)
        for k in ("dev", "B", "C", "all"):
            rs = [y["r"] for y in tr if k == "all" or y["period"] == k]
            pos, neg = sum(r for r in rs if r > 0), -sum(r for r in rs if r < 0)
            met[k]["pf"] = round(pos / neg, 2) if neg > 0 else None
            met[k].pop("score", None)
        out["styles"][name] = met
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--h1", required=True)
    ap.add_argument("--m5", required=True)
    ap.add_argument("--mkt", required=True)
    ap.add_argument("--tfs", default="5m,15m,30m,1h,2h,4h,1D,1Dm")
    a = ap.parse_args()
    os.makedirs(os.path.join(ROOT, "tv", "backtest"), exist_ok=True)
    rpath = os.path.join(ROOT, "tv", "backtest", "results.json")
    try:
        with open(rpath) as fh:
            results = json.load(fh)
    except (OSError, ValueError):
        results = {}
    for tf in a.tfs.split(","):
        t0 = time.time()
        with open(model_file(tf)) as fh:
            m = json.load(fh)
        data = bars(tf, a)
        rd = radar(tf, data, m)
        cn = council(tf, data, m, a)
        results[tf] = {"radar": rd, "council": cn}
        m["gate"]["t_vloud"], m["gate"]["t_vquiet"] = rd["t_vloud"], rd["t_vquiet"]
        m["gate"]["scores_tiers"] = {k: {kk: v[kk] for kk in ("loud", "very_loud", "quiet", "very_quiet", "base_loud", "base_quiet",
                                                             "move_loud", "move_very_loud", "move_quiet", "move_all")}
                                     for k, v in rd["rows"].items() if k.startswith("all|")}
        with open(model_file(tf), "w") as fh:
            json.dump(m, fh, separators=(",", ":"))
        with open(rpath, "w") as fh:
            json.dump(results, fh, indent=1)
        c = rd["rows"].get("all|C", {})
        s0, s2 = cn["styles"]["2R (trained)"]["all"], cn["styles"]["1R"]["all"]
        print(f"{datetime.now():%H:%M:%S} [{tf}] radar test: LOUD {c.get('loud')} VERY LOUD {c.get('very_loud')} QUIET {c.get('quiet')} "
              f"base {c.get('base_loud')}% | council reproduces {cn['reproduces_model_file']} replay {cn['replay_matches_2R']} | "
              f"2R win {s0['win']}% avgR {s0['avg_r']:+.3f} | 1R win {s2['win']}% avgR {s2['avg_r']:+.3f} ({time.time() - t0:.0f}s)",
              flush=True)


if __name__ == "__main__":
    main()
