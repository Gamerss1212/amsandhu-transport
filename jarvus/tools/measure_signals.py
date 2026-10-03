#!/usr/bin/env python3
"""Measure every candle pattern, chart pattern and indicator signal in Jarvus's knowledge base on real data.

Data: Coinbase hourly candles (the files system_test.py downloads), majors BTC ETH SOL and memes DOGE SHIB PEPE
BONK WIF FLOKI, on 1h bars and on 4h bars built from them. For every signal:

  direction test   12-bar forward return of the close after the signal vs the same coin's average bar
                   (excess %), how often it was up vs that coin's base rate, and the move size vs normal
  trade test       buy it with Jarvus's exits: limit 0.1% under the close (3 bars to fill), stop 4x ATR(14),
                   one exit at 2R, 96 hours, NDAX fees (0.20%/side) + slippage, vs the same exits on evenly
                   spaced bars (the benchmark: "buy at random"), early (before 2025-03-20) and late halves,
                   and the volatility-gate LOUD subset (1h gate reading at the signal's close)

A signal that repeats within 12 bars (1h) / 3 bars (4h) of its last counted firing is not counted again.
Roughly 100 signals x 4 groups are tested, so a few will look good by luck: the label "held up" needs the
signal to beat the benchmark in BOTH halves and overall at t >= 2.5.

  python3 tools/measure_signals.py --data <dir with *_1h.csv and *_prep.pkl> [--workers 4]
Writes assets/signal_results.json and references/kb-measured.md.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import pickle
import sys
from datetime import datetime, timezone
from multiprocessing import Pool

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view as swv

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import ladder  # noqa: E402
import system_test as st  # noqa: E402
from snapshot import load_csv  # noqa: E402

MAJORS = ["BTC", "ETH", "SOL"]
MEMES = ["DOGE", "SHIB", "PEPE", "BONK", "WIF", "FLOKI"]
SPLIT = int(datetime(2025, 3, 20, tzinfo=timezone.utc).timestamp() * 1000)
HOUR = 3_600_000
FWD = 12

from signals import DEFS, PLAYBOOK, P, roll, ema, wilder, rsi, atr, cross_up, cross_dn, first_in_run, vector_signals, psar, supertrend, loop_signals, to4h  # noqa: E402,F401


# ------------------------------------------------------------------ data
def load(data_dir, coin):
    d = load_csv(os.path.join(data_dir, f"{coin}_1h.csv"))
    t = np.array([int(x.timestamp() * 1000) for x in d["ts"]], dtype=np.int64)
    arr = [np.array(d[k], float) for k in ("open", "high", "low", "close", "volume")]
    gate = np.array(["U"] * len(t))
    sig = {}
    pk = os.path.join(data_dir, f"{coin}_prep.pkl")
    if os.path.exists(pk):
        with open(pk, "rb") as fh:
            p = pickle.load(fh)
        g = dict(zip(p["t"], p["gate"]))
        gate = np.array([g.get(int(x), "U") for x in t])
        pos = {int(x): k for k, x in enumerate(t)}
        for name in PLAYBOOK.values():
            sig[name] = [pos[p["t"][i]] for i in p["sig"].get(name, []) if p["t"][i] in pos]
    return t, *arr, gate, sig


def measure_coin(job):
    data_dir, coin = job
    kind = "major" if coin in MAJORS else "meme"
    t, o, h, l, c, v, gate, pb = load(data_dir, coin)
    out = {}
    for tf in ("1h", "4h"):
        if tf == "4h":
            t2, o2, h2, l2, c2, v2, g2 = to4h(t, o, h, l, c, v, gate)
            bars_day, gap, horizon, bench_step = 6, 3, 24, 3
        else:
            t2, o2, h2, l2, c2, v2, g2 = t, o, h, l, c, v, gate
            bars_day, gap, horizon, bench_step = 24, 12, 96, 12
        n = len(c2)
        S, A, r14 = vector_signals(t2, o2, h2, l2, c2, v2, bars_day)
        S.update(loop_signals(t2, o2, h2, l2, c2, A, r14, bars_day))
        if tf == "1h":
            for sid, name in PLAYBOOK.items():
                m = np.zeros(n, bool)
                m[[i for i in pb.get(name, []) if i < n]] = True
                S[sid] = m
        p = {"coin": coin, "t": t2.tolist(), "o": o2.tolist(), "h": h2.tolist(), "l": l2.tolist(), "c": c2.tolist(),
             "atr": [None if x != x else float(x) for x in A]}
        memo = {}

        def trade(i):
            if i not in memo:
                tr = st.trade_path(p, i, "x", st.FEES["ndax"], kind, entry="maker", stop_atr=4.0, rung=None,
                                   target_r=2.0, tp1_bars=0, horizon=horizon)
                memo[i] = None if tr is None else tr["r"]
            return memo[i]

        fwd = np.full(n, np.nan)
        fwd[:n - FWD] = c2[FWD:] / c2[:n - FWD] - 1
        valid = np.zeros(n, bool)
        valid[210:n - FWD] = True
        valid &= ~np.isnan(fwd) & ~np.isnan(A)
        base = {"mean": float(np.mean(fwd[valid])), "up": float(np.mean(fwd[valid] > 0)),
                "abs": float(np.mean(np.abs(fwd[valid]))), "n": int(valid.sum())}
        late = t2 >= SPLIT
        bench = {"all": [], "early": [], "late": [], "loud": []}
        for i in range(210, n - FWD, bench_step):
            r = trade(i)
            if r is None:
                continue
            bench["all"].append(r)
            bench["late" if late[i] else "early"].append(r)
            if g2[i] == "L":
                bench["loud"].append(r)
        res = {"base": base, "bench": {k: [len(x), float(np.sum(x))] for k, x in bench.items()}, "sig": {}}
        for sid, m in S.items():
            idx = np.flatnonzero(m & valid)
            kept, last = [], -10 ** 9
            for i in idx:
                if i - last >= gap:
                    kept.append(int(i))
                    last = i
            if not kept:
                res["sig"][sid] = None
                continue
            k = np.array(kept)
            f = fwd[k]
            rs = {"all": [], "early": [], "late": [], "loud": []}
            for i in kept:
                r = trade(i)
                if r is None:
                    continue
                rs["all"].append(r)
                rs["late" if late[i] else "early"].append(r)
                if g2[i] == "L":
                    rs["loud"].append(r)
            res["sig"][sid] = {
                "n": len(kept), "ex": float(np.sum(f - base["mean"])), "ex2": float(np.sum((f - base["mean"]) ** 2)),
                "up": int(np.sum(f > 0)), "absr": float(np.sum(np.abs(f) / base["abs"])),
                "r": {kk: [len(x), float(np.sum(x)), float(np.sum(np.square(x))), int(np.sum(np.array(x) > 0))]
                      for kk, x in rs.items()}}
        out[tf] = res
    return coin, kind, out


# ------------------------------------------------------------------ pooling and labels
def pool(per_coin, coins, tf):
    agg = {}
    for sid in DEFS:
        s = {"n": 0, "ex": 0.0, "ex2": 0.0, "up": 0, "base_up": 0.0, "absr": 0.0,
             "r": {k: [0, 0.0, 0.0, 0] for k in ("all", "early", "late", "loud")},
             "bench": {k: 0.0 for k in ("all", "early", "late", "loud")}}
        for coin in coins:
            res = per_coin.get(coin, {}).get(tf)
            if not res or not res["sig"].get(sid):
                continue
            x = res["sig"][sid]
            s["n"] += x["n"]
            s["ex"] += x["ex"]
            s["ex2"] += x["ex2"]
            s["up"] += x["up"]
            s["base_up"] += res["base"]["up"] * x["n"]
            s["absr"] += x["absr"]
            for k in s["r"]:
                rn, rsum, rsq, rwin = x["r"][k]
                for q, val in enumerate((rn, rsum, rsq, rwin)):
                    s["r"][k][q] += val
                bn, bsum = res["bench"][k]
                s["bench"][k] += rn * (bsum / bn if bn else 0.0)          # benchmark weighted like the signal
        agg[sid] = s
    out = {}
    for sid, s in agg.items():
        if s["n"] == 0:
            out[sid] = None
            continue
        n = s["n"]
        mean_ex = s["ex"] / n
        sd_ex = math.sqrt(max(s["ex2"] / n - mean_ex ** 2, 1e-18))
        row = {"n": n, "ex12": round(mean_ex * 100, 3), "t_dir": round(mean_ex / (sd_ex / math.sqrt(n)), 2),
               "up": round(s["up"] / n * 100, 1), "base_up": round(s["base_up"] / n * 100, 1),
               "move": round(s["absr"] / n, 2)}
        for k in ("all", "early", "late", "loud"):
            rn, rsum, rsq, rwin = s["r"][k]
            if rn:
                mean = rsum / rn
                sd = math.sqrt(max(rsq / rn - mean ** 2, 1e-12))
                row[f"r_{k}"] = round(mean, 3)
                row[f"b_{k}"] = round(s["bench"][k] / rn, 3)
                row[f"n_{k}"] = rn
                if k == "all":
                    row["hit"] = round(rwin / rn * 100, 1)
                    row["t_r"] = round((mean - s["bench"][k] / rn) / (sd / math.sqrt(rn)), 2)
        row["label"] = label(row, DEFS[sid][1])
        out[sid] = row
    return out


def label(r, side):
    if r.get("n_all", 0) < 30:
        return "too few"
    beat_e = r.get("n_early", 0) >= 15 and r["r_early"] > r["b_early"]
    beat_l = r.get("n_late", 0) >= 15 and r["r_late"] > r["b_late"]
    if r["t_r"] >= 2.5 and beat_e and beat_l:
        if r["r_all"] > 0 and r["r_early"] > 0 and r["r_late"] > 0:
            return "held up and made money"
        return "beat random, still lost after fees"
    if r["t_r"] <= -2.5:
        return "worse than random"
    if r["r_all"] > r["b_all"]:
        return "slightly better, not reliable"
    return "no better than random"


def dir_label(r, side):
    if r["n"] < 30:
        return "too few"
    if r["t_dir"] >= 2.5:
        return "rose more than average"
    if r["t_dir"] <= -2.5:
        return "fell more than average"
    return "no reliable direction"


# ------------------------------------------------------------------ report
MARK = {"held up and made money": "✓", "beat random, still lost after fees": "+", "worse than random": "✗",
        "slightly better, not reliable": "~", "no better than random": "·"}


def cell(r):
    if not r:
        return "—"
    if r.get("n_all", 0) < 30:
        return f"n {r['n']}, too few"
    mark = MARK.get(r["label"], "·")
    return f"{mark} {r['r_all']:+.2f} vs {r['b_all']:+.2f}R · 12h {r['ex12']:+.2f}% · n {r['n_all']}"


def report(results, path):
    L = ["# What every candle, pattern and indicator signal actually did (Jarvus measurement)", "",
         "Generated by `tools/measure_signals.py` on Coinbase hourly data (majors BTC ETH SOL; memes DOGE SHIB PEPE BONK",
         "WIF FLOKI; Dec 2020 to Oct 2026, memes from their Coinbase listing). 1h bars and 4h bars built from them.",
         "",
         "Each cell: **buy it with Jarvus's exits** (limit 0.1% under the close, stop 4×ATR, one exit at 2R, 96h,",
         "NDAX fees + slippage) average R per trade **vs buying at random** with the same exits, then the average",
         "12-bar move after the signal compared with an average bar, and the number of trades.",
         "✓ = beat random in both halves (before/after 2025-03-20) and overall at t ≥ 2.5 AND made money in both halves",
         "· + = beat random the same way but still lost money after fees · ~ = better overall, not reliable · · = no better",
         "than random · ✗ = worse than random (t ≤ −2.5).",
         "Caution: 133 signals × 4 groups were tested, and coins move together (BTC/ETH/SOL fire on the same hours), so",
         "t-values are flattering and a few marks are luck. A family that works across groups and timeframes is stronger",
         "evidence than one cell. Fixed exits, no volatility gate, no trend filter: Jarvus's live rules are stricter.",
         "Bearish signals were also bought, to show what buying them did; their 12h move is the sell/avoid reading.",
         "None of this is a forecast. Past results, after costs, on this data only.", ""]
    fam_title = {"candle": "Candlestick patterns", "chart": "Chart patterns and price structure",
                 "indicator": "Indicator signals", "playbook": "Jarvus's own playbooks (1h)"}
    held = []
    for fam in ("candle", "chart", "indicator", "playbook"):
        L += [f"## {fam_title[fam]}", "", "| Signal | Side | Majors 1h | Majors 4h | Memes 1h | Memes 4h |", "|---|---|---|---|---|---|"]
        for sid, (name, side, f, _) in DEFS.items():
            if f != fam:
                continue
            cells = [cell(results[g][tf].get(sid)) for g in ("majors", "memes") for tf in ("1h", "4h")]
            L.append(f"| {name} | {side} | " + " | ".join(cells) + " |")
            for g in ("majors", "memes"):
                for tf in ("1h", "4h"):
                    r = results[g][tf].get(sid)
                    if r and r["label"] == "held up and made money":
                        loud = (f", LOUD-gate subset {r['r_loud']:+.3f} vs {r['b_loud']:+.3f} (n {r['n_loud']})"
                                if r.get("n_loud", 0) >= 20 else "")
                        held.append(f"{name} ({g} {tf}): {r['r_all']:+.3f}R vs random {r['b_all']:+.3f}R, n {r['n_all']}, "
                                    f"t {r['t_r']}, early {r['r_early']:+.3f} vs {r['b_early']:+.3f} (n {r['n_early']}), "
                                    f"late {r['r_late']:+.3f} vs {r['b_late']:+.3f} (n {r['n_late']}){loud}")
        L.append("")
    L += ["## The ones that held up and made money (✓)", ""] + ([f"- {x}" for x in held] or ["- none"]) + [""]
    L += ["## Count by family (cells with 30+ trades)", "", "| Family | cells | ✓ | + | ~ | · | ✗ |", "|---|---|---|---|---|---|---|"]
    for fam in ("candle", "chart", "indicator", "playbook"):
        cnt = {m: 0 for m in MARK.values()}
        tot = 0
        for sid, (_, _, f, _) in DEFS.items():
            if f != fam:
                continue
            for g in ("majors", "memes"):
                for tf in ("1h", "4h"):
                    r = results[g][tf].get(sid)
                    if r and r.get("n_all", 0) >= 30:
                        tot += 1
                        cnt[MARK[r["label"]]] += 1
        L.append(f"| {fam_title[fam]} | {tot} | {cnt['✓']} | {cnt['+']} | {cnt['~']} | {cnt['·']} | {cnt['✗']} |")
    L.append("")
    with open(path, "w") as fh:
        fh.write("\n".join(L))
    return held


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()
    coins = [c for c in MAJORS + MEMES if os.path.exists(os.path.join(a.data, f"{c}_1h.csv"))]
    with Pool(a.workers) as pool_:
        got = pool_.map(measure_coin, [(a.data, c) for c in coins])
    per_coin = {coin: out for coin, _, out in got}
    results = {"majors": {}, "memes": {}}
    for g, cs in (("majors", MAJORS), ("memes", MEMES)):
        for tf in ("1h", "4h"):
            results[g][tf] = pool(per_coin, [c for c in cs if c in per_coin], tf)
    meta = {"generated": datetime.now(timezone.utc).strftime("%Y-%m-%d"), "coins": coins, "fees": "ndax",
            "exits": "limit 0.1% under close, stop 4xATR(14), one exit at 2R, 96h", "split": "2025-03-20",
            "defs": {k: {"name": v[0], "side": v[1], "family": v[2], "rule": v[3]} for k, v in DEFS.items()}}
    with open(os.path.join(ROOT, "assets", "signal_results.json"), "w") as fh:
        json.dump({"meta": meta, "results": results}, fh, separators=(",", ":"))
    held = report(results, os.path.join(ROOT, "references", "kb-measured.md"))
    print(f"{len(DEFS)} signals, {len(coins)} coins. Held up and made money: {len(held)}")
    for x in held:
        print(" ", x)


if __name__ == "__main__":
    main()
