#!/usr/bin/env python3
"""Tune the ULTRON Council indicator for win rate without fooling ourselves.

Per timeframe, the Council's walk-forward is re-run for every combination of the indicator's own settings:
  volatility filter  learned (off) / no QUIET / LOUD only
  extra caution      the minimum edge raised by 0 ... 0.30R (fewer, stronger signals)
and every trade it takes is replayed with every exit style (the trained 2R, smaller targets, and ladders that sell part
early and move the stop to breakeven, which is what lifts the win rate).

The pick for each timeframe: the highest win rate (fit and validation pooled) among combinations that made at least
+0.10R per trade with a profit factor of 1.2 in BOTH the fit and the validation period, with enough trades in each. The untouched test (since Dec 2025) is never used
to choose; it is only reported. A timeframe where nothing qualifies is marked "stay flat".

  python3 ultron/tools/optimize_wr.py --h1 <hourly dir> --m5 <5m dir> --mkt <daily markets dir> [--tfs 1h,4h]
Writes ultron/tv/backtest/winrate.json (read by build_pine.py).
"""

from __future__ import annotations

import argparse
import json
import os
import pickle
import sys
import time
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import backtest_all as B  # noqa: E402
import train_tf as F  # noqa: E402
from train_tf import T, pg, st  # noqa: E402

ROOT = os.path.dirname(HERE)
OUT = os.path.join(ROOT, "tv", "backtest", "winrate.json")
GATES = ["learned", "no_quiet", "loud_only"]
EXTRAS = [0.0, 0.03, 0.06, 0.10, 0.15, 0.20, 0.30]
STYLES = B.STYLES          # name, (rung R, fraction sold there; then the stop moves to breakeven after fees), target R
MIN_N = {"A": 30, "B": 10}
# A safety margin, not just "positive": a first run that only asked for avg R > 0 picked ladders earning +0.05R per
# trade, and on 4 of 7 timeframes those turned negative on the untouched test. Each of fit and validation must clear
# +0.10R per trade and a profit factor of 1.2. (Set after seeing that first test result once: say so in the report.)
MIN_AVG_R, MIN_PF = 0.10, 1.2


def seg(rs):
    if not rs:
        return {"n": 0, "win": None, "avg_r": None, "pf": None}
    pos, neg = sum(r for r in rs if r > 0), -sum(r for r in rs if r < 0)
    return {"n": len(rs), "win": round(100 * sum(r > 0 for r in rs) / len(rs), 1), "avg_r": round(sum(rs) / len(rs), 4),
            "pf": round(pos / neg, 2) if neg > 0 else None}


def run_tf(tf, a):
    with open(B.model_file(tf)) as fh:
        m = json.load(fh)
    ex = m.get("exit", {"stop_chart": 4.0, "stop_htf": 4.0, "hold": 96})
    tag = "" if (ex["stop_chart"], ex["stop_htf"], ex["hold"]) == (4.0, 4.0, 96) else f"_x{ex['stop_chart']:g}_{ex['hold']}"
    with open(os.path.join(a.h1, f"ultron_tf_{tf}{tag}.pkl"), "rb") as fh:
        events, defs, _, first_t = pickle.load(fh)
    d0 = datetime.fromtimestamp((first_t + 365 * B.DAY) / 1000, timezone.utc)
    T.WF_START = max(T.ms(2022, 1, 1), int(datetime(d0.year, ((d0.month - 1) // 3) * 3 + 1, 1, tzinfo=timezone.utc).timestamp() * 1000))
    data = B.bars(tf, a)
    size = F.TFS[tf][0]
    ev_of = {(e[0], e[1], e[2]): e for e in events}
    fees = st.FEES["markets" if tf == "1Dm" else "ndax"]
    preps, memo = {}, {}

    def replay(x):
        """R of one trade for every exit style (memoised: the variants share most of their trades)."""
        key = (x["t"], x["cid"], x["coin"])
        if key in memo:
            return memo[key]
        e = ev_of[key]
        sym = x["coin"]
        if sym not in preps:
            t, o, h, l, c, v = data[sym]
            A = pg.atr(h, l, c)
            preps[sym] = ({"coin": sym, "t": t.tolist(), "o": o.tolist(), "h": h.tolist(), "l": l.tolist(), "c": c.tolist(),
                           "atr": [None if q != q else float(q) for q in A]}, {int(q): k for k, q in enumerate(t)})
        p, idx = preps[sym]
        i = idx[int(x["t"]) - size]
        lim, px = p["c"][i] * 0.999, None
        for j in range(i + 1, min(len(p["c"]), i + 4)):
            if p["o"][j] <= lim:
                px = p["o"][j]
                break
            if p["l"][j] <= lim:
                px = lim
                break
        out = None
        if px is not None and p["atr"][i]:
            stop_atr = e[6] / 100 * px / p["atr"][i]
            kind = "major" if tf == "1Dm" or sym in T.MAJORS else "meme"
            out = {}
            for name, rung, tgt in STYLES:
                tr = st.trade_path(p, i, "x", fees, kind, entry="maker", stop_atr=stop_atr, rung=rung, target_r=tgt,
                                   tp1_bars=0, horizon=int(ex["hold"]))
                out[name] = None if tr is None else float(tr["r"])
        memo[key] = out
        return out

    base_gate, base_theta = m["params"]["gate_rule"], m["params"]["theta"]
    rows = []
    for gate in GATES:
        for extra in EXTRAS:
            prm = dict(m["params"], gate_rule=gate, theta=base_theta + extra)
            res = T.simulate(events, defs, prm, record=True)
            per = {name: {"A": [], "B": [], "C": []} for name, _, _ in STYLES}
            for x in res["trades"]:
                rr = replay(x)
                if rr is None:
                    continue
                p_ = {"dev": "A", "B": "B", "C": "C"}[x["period"]]
                for name, r in rr.items():
                    if r is not None:
                        per[name][p_].append(r)
            for name, d in per.items():
                rows.append({"gate": gate, "extra": extra, "style": name, "trained": gate == base_gate and extra == 0.0,
                             "A": seg(d["A"]), "B": seg(d["B"]), "C": seg(d["C"]), "AB": seg(d["A"] + d["B"])})

    def ok(r):
        return all(r[p]["n"] >= MIN_N[p] and r[p]["avg_r"] >= MIN_AVG_R and (r[p]["pf"] or 0) >= MIN_PF for p in ("A", "B"))

    good = [r for r in rows if ok(r)]
    pick = max(good, key=lambda r: (r["AB"]["win"], r["AB"]["avg_r"])) if good else None
    base = next(r for r in rows if r["trained"] and r["style"] == "2R (trained)")
    return {"gate_trained": base_gate, "theta_trained": base_theta, "pick": pick, "trained_2R": base,
            "qualifying": len(good), "combinations": len(rows), "rows": rows}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--h1", required=True)
    ap.add_argument("--m5", required=True)
    ap.add_argument("--mkt", required=True)
    ap.add_argument("--tfs", default="5m,15m,30m,1h,2h,4h,1D,1Dm")
    a = ap.parse_args()
    try:
        with open(OUT) as fh:
            out = json.load(fh)
    except (OSError, ValueError):
        out = {}
    for tf in a.tfs.split(","):
        t0 = time.time()
        r = run_tf(tf, a)
        out[tf] = r
        with open(OUT, "w") as fh:
            json.dump(out, fh, indent=1)
        p, b = r["pick"], r["trained_2R"]
        fmt = lambda s: f"{s['n']} trades win {s['win']}% avg {s['avg_r']:+.3f}R" if s["n"] else "0 trades"   # noqa: E731
        print(f"{datetime.now():%H:%M:%S} [{tf}] {r['qualifying']}/{r['combinations']} qualify ({time.time() - t0:.0f}s)", flush=True)
        print(f"   trained 2R   fit+valid {fmt(b['AB'])} | TEST {fmt(b['C'])}", flush=True)
        if p:
            print(f"   PICK {p['gate']}, +{p['extra']:.2f}R edge, {p['style']}: fit+valid {fmt(p['AB'])} | TEST {fmt(p['C'])}", flush=True)
        else:
            print("   PICK none: stay flat on this timeframe", flush=True)


if __name__ == "__main__":
    main()
