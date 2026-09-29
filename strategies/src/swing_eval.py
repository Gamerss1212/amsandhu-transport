"""Evaluate the swing strategies (f07_swing.py) with the platform's own engine on 5.5 years of hourly data.

    python strategies/src/swing_eval.py --hourly PATH/hourly.pkl [--workers 4]

Writes results/swing_eval.json in the same format as evaluation_summary.json (chronological 60/20/20 with a
one-day embargo per dataset, walk-forward folds, cost levels gross / low-fee / Kraken retail), which the
catalog build, the brain's priors and the live-money eligibility rule read. It also re-runs the swing lab's
simulation for the same rules and prints both, so a difference between the lab and the bots' engine
(fills, indicator warm-up, limit-order handling) is visible rather than assumed away.
"""

import argparse
import json
import os
import pickle
import sys
import time
from multiprocessing import Pool

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(ROOT), "market_analysis_bots"))

import run_evaluation as RE  # noqa: E402

LAB = {"swing_rsi2_dip": ("rsi2_dip", 4.0, 3.0, 96), "swing_meme_breakout": ("breakout", 4.0, 2.0, 96),
       "swing_meme_retest": ("retest", 4.0, 3.0, 96)}


def init(path):
    with open(path, "rb") as fh:
        hourly = pickle.load(fh)
    for (kind, sym), bars in hourly.items():
        if kind == "crypto":
            RE.DATA[("coinbase", sym, "1h")] = bars


def lab_check(job):
    """The swing lab's own simulation of the same rule on the same bars (gross R, maker entry)."""
    import numpy as np
    import swing_lab as L
    sid, key, d, venue, sym = job
    bars = RE.DATA[("coinbase", sym, "1h")]
    t, o, h, l, c, v = L.arrays(bars)
    a = L.atr(h, l, c)
    setup, k, r, hold = LAB[key]
    tr = L.simulate(t, o, h, l, c, a, L.signals(t, o, h, l, c, False)[setup], k, r, hold, "maker")
    return {"trades": int(len(tr["t"])), "gross_r": float(np.mean(tr["gross_r"]))} if tr else {"trades": 0, "gross_r": None}


def run(job):
    out = RE.work(job)
    try:
        out["lab"] = lab_check(job)
    except Exception as e:                                   # noqa: BLE001
        out["lab"] = {"error": str(e)}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hourly", required=True)
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()
    t0 = time.time()
    with open(os.path.join(ROOT, "catalog.json")) as fh:
        cat = json.load(fh)
    swing = [s for s in cat["strategies"] if s["key"] in LAB]
    if len(swing) != len(LAB):
        raise SystemExit("build the catalog first (python strategies/src/build.py)")
    jobs = [(s["id"], s["key"], s["definition"], "coinbase", sym) for s in swing for sym in s["instruments"]]
    with Pool(a.workers, initializer=init, initargs=(a.hourly,)) as pool:
        results = pool.map(run, jobs)
    sub = dict(cat, strategies=swing)
    summary = RE.analyse(sub, results, a.workers, t0)
    summary["protocol"] = ("platform engine on Coinbase hourly bars (up to 5.5 years); chronological 60/20/20 with a "
                           "one-day embargo per dataset; cost levels gross / low_fee_venue (OKX fees) / retail_kraken")
    lab = {(r["id"], r["instrument"]): r.get("lab") for r in results}
    summary["engine_vs_lab"] = []
    for sid, s in summary["strategies"].items():
        for x in s["runs"]:
            if x["cost"] == "retail_kraken":
                g = x.get("gross_full") or {}
                summary["engine_vs_lab"].append({"id": sid, "instrument": x["instrument"], "engine_trades": g.get("trades"),
                                                 "engine_gross_r": g.get("expectancy_r"), "lab": lab.get((sid, x["instrument"]))})
    with open(os.path.join(ROOT, "results", "swing_eval.json"), "w") as fh:
        json.dump(summary, fh, default=str)
    for sid, s in summary["strategies"].items():
        print(sid, s["name"])
        for x in s["runs"]:
            print(f"  {x['instrument']:10s} {x['cost']:14s} full {x['full']['trades']:4d} tr {x['full']['expectancy_r'] or 0:+.3f}R "
                  f"gross {(x.get('gross_full') or {}).get('expectancy_r') or 0:+.3f}R  test {x['test']['trades']:3d} tr "
                  f"{x['test']['expectancy_r'] or 0:+.3f}R  candidate {x['candidate']}")
    for e in summary["engine_vs_lab"]:
        print("engine vs lab", e)
    for r in results:
        if r.get("error"):
            print("error", r["id"], r["instrument"], r["error"])
    print(f"{(time.time() - t0) / 60:.1f} min")


if __name__ == "__main__":
    main()
