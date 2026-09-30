"""Drift monitoring: is what the bots do now still what they were tested to do?

* Performance drift: for each strategy on each market with enough closed trades (paper, demo or live), the average
  result per trade is compared with its held-out test result at the matching cost level. A z-score below -2 is a
  warning, below -3 an alert. Drift never changes anything by itself: it tells the owner a re-evaluation is due.
* Volatility gate drift runs as a research job (mab.research.worker.gate_drift).
"""

from __future__ import annotations

import json
import math
import time
from typing import Callable, List

MIN_TRADES = 20


def performance(storage, eval_rows: Callable[[str], list], window_days: int = 60, write: bool = True) -> List[dict]:
    since = int(time.time() * 1000) - window_days * 86_400_000
    rows = storage.query(
        "SELECT strategy_id, instrument, venue, mode, COUNT(*) AS n, AVG(r) AS mean, SUM(r*r) AS s2 FROM trades"
        " WHERE r IS NOT NULL AND exit_time >= ? GROUP BY strategy_id, instrument, venue, mode HAVING COUNT(*) >= ?",
        (since, MIN_TRADES))
    out = []
    now = int(time.time() * 1000)
    for r in rows:
        n, mean = r["n"], r["mean"]
        var = max(0.0, (r["s2"] - n * mean * mean) / (n - 1)) if n > 1 else 0.0
        sd = math.sqrt(var)
        cost = "base" if r["venue"] == "yahoo" else ("low_fee_venue" if r["venue"] == "okx" else "retail_kraken")
        ev = [x for x in eval_rows(r["strategy_id"]) if x.get("cost") == cost and x.get("instrument") == r["instrument"]] or \
             [x for x in eval_rows(r["strategy_id"]) if x.get("cost") == cost]
        exp = None
        if ev:
            vals = [x["test"].get("expectancy_r") for x in ev if (x.get("test") or {}).get("expectancy_r") is not None]
            exp = sum(vals) / len(vals) if vals else None
        z = (mean - exp) / (sd / math.sqrt(n)) if (exp is not None and sd > 0) else None
        status = "no reference" if z is None else ("alert" if z < -3 else ("warn" if z < -2 else "ok"))
        rec = {"subject": f"strategy:{r['strategy_id']}:{r['instrument']}:{r['mode']}", "strategy_id": r["strategy_id"],
               "instrument": r["instrument"], "mode": r["mode"], "trades": n, "mean_r": round(mean, 4),
               "expected_r": round(exp, 4) if exp is not None else None, "z": round(z, 2) if z is not None else None,
               "status": status}
        out.append(rec)
        if write:
            storage.write("INSERT INTO drift_reports (ts, subject, metric, value, threshold, status, body) VALUES (?,?,?,?,?,?,?)",
                          (now, rec["subject"], "mean_r_vs_test", mean, exp, status, json.dumps(rec)))
    return out


def latest(storage, limit: int = 200) -> List[dict]:
    rows = storage.query("SELECT d.* FROM drift_reports d JOIN (SELECT subject, metric, MAX(ts) AS m FROM drift_reports"
                         " GROUP BY subject, metric) x ON d.subject = x.subject AND d.metric = x.metric AND d.ts = x.m"
                         " ORDER BY d.ts DESC LIMIT ?", (limit,))
    for r in rows:
        r["body"] = json.loads(r["body"] or "{}")
    return rows
