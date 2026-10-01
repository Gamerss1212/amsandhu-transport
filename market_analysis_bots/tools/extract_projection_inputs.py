"""Collect the per-window returns of tools/balance_backtest.py runs (results/balance_<fee profile>.json) into
results/projection_inputs.json, the measured inputs of the goal calculator (jarvus-terminal/engine/projection.py)."""

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROFILES = ["venue", "coinbase", "kraken", "ndax", "low_fee"]


def main():
    out = {"generated": None, "window_days": None, "runs": None, "period": None, "profiles": {}}
    sysb = os.path.join(ROOT, "results", "system_backtest_summary.json")
    if os.path.exists(sysb):
        out["period"] = json.load(open(sysb))["period"]
    for fp in PROFILES:
        path = os.path.join(ROOT, "results", f"balance_{fp}.json")
        if not os.path.exists(path):
            print("missing", path)
            continue
        d = json.load(open(path))
        out["generated"] = d["generated"]
        out["window_days"], out["runs"] = d["window_days"], d["runs"]
        tiers = {}
        for k, v in d["results"].items():
            bal, ver = k.split("|")
            if ver != "after":
                continue
            tiers[str(int(float(bal)))] = {"returns": [round(x, 6) for x in v["returns"]],
                                           "trades_per_window": round(v["trades_per_window"], 2)}
        out["profiles"][fp] = tiers
        print(fp, {t: (round(sum(x["returns"]) / len(x["returns"]) * 100, 4)) for t, x in tiers.items()})
    with open(os.path.join(ROOT, "results", "projection_inputs.json"), "w") as fh:
        json.dump(out, fh, separators=(",", ":"))
    print("wrote results/projection_inputs.json,", os.path.getsize(os.path.join(ROOT, "results", "projection_inputs.json")), "bytes")


if __name__ == "__main__":
    sys.exit(main())
