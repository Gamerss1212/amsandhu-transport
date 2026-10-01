"""The strategy library and every measured result shipped with this build (read-only).

    library()              the catalog: strategies, families, implementation and evaluation status
    strategy(id)           one strategy with its rules, sources and measured runs
    results()              digest of the measurements: strategy runs, full-system runs, swing lab, volatility gate
    evaluation(id)         a strategy's measured runs (train / validation / untouched test, per cost level)
"""

from __future__ import annotations

import gzip
import json
import os
import sys

import config

HERE = os.path.dirname(os.path.abspath(__file__))
if getattr(sys, "frozen", False):
    PAYLOAD = config.BUNDLE_DIR
else:
    PAYLOAD = os.path.dirname(os.path.dirname(HERE))
MAB_DIR = os.path.join(PAYLOAD, "market_analysis_bots")
if MAB_DIR not in sys.path:
    sys.path.insert(0, MAB_DIR)

CATALOG = os.path.join(PAYLOAD, "strategies", "catalog.json")
REGISTRY = os.path.join(MAB_DIR, "bots", "registry.json")
_catalog = None
_evaluation = None


def catalog() -> dict:
    global _catalog
    if _catalog is None:
        with open(CATALOG, encoding="utf-8") as fh:
            _catalog = json.load(fh)
        with open(os.path.join(os.path.dirname(CATALOG), "sources.json"), encoding="utf-8") as fh:
            _catalog["_sources"] = {s["id"]: s for s in json.load(fh)}
    return _catalog


def library() -> dict:
    c = catalog()
    rows = []
    for s in c["strategies"]:
        ev = s.get("evaluation") or {}
        best = ev.get("best_realistic") or {}
        rows.append({"id": s["id"], "name": s["name"], "family": s["family"], "markets": s["markets"],
                     "tf": s["timeframe"], "research": s["research_status"], "impl": s["implementation_status"],
                     "eval": s["evaluation_status"], "best_r": best.get("expectancy_r"), "best_inst": best.get("instrument"),
                     "gross_r": best.get("gross_expectancy_r"), "trades": best.get("trades"),
                     "variants": len(s.get("variants") or [])})
    return {"counts": c["counts"], "generated": c.get("generated"), "strategies": rows}


def strategy(sid: str) -> dict:
    c = catalog()
    s = next((x for x in c["strategies"] if x["id"] == sid), None)
    if s is None:
        return {"error": "unknown strategy"}
    out = dict(s)
    out["sources"] = [dict(c["_sources"].get(e["source"], {"id": e["source"]}), relation=e["relation"], note=e["note"])
                      for e in s.get("evidence", [])]
    out["variant_rows"] = [v for v in c.get("variants", []) if v.get("parent_id") == sid]
    return out


# ------------------------------------------------------------------ results (what was measured)
_results = None


_projection = None


def projection_inputs() -> dict:
    """Measured per-window returns of the whole system by fee level and starting balance (goal calculator input)."""
    global _projection
    if _projection is None:
        try:
            with open(os.path.join(PAYLOAD, "market_analysis_bots", "results", "projection_inputs.json"), encoding="utf-8") as fh:
                _projection = json.load(fh)
        except (OSError, ValueError):
            _projection = {}
    return _projection


def results() -> dict:
    """Digest of every measurement shipped with this build: strategy runs, full-system runs, volatility gate."""
    global _results
    if _results is not None:
        return _results
    import gzip
    import statistics
    out = {"strategies": None, "system": None, "volgate": None}
    ev_path = os.path.join(PAYLOAD, "strategies", "results", "evaluation_summary.json")
    try:
        if os.path.exists(ev_path):
            with open(ev_path, encoding="utf-8") as fh:
                ev = json.load(fh)
        else:
            with gzip.open(ev_path + ".gz", "rt", encoding="utf-8") as fh:
                ev = json.load(fh)
        runs = [(sid, x) for sid, s in ev["strategies"].items() for x in s["runs"]]

        def prof(xs, n=0):
            return sum(1 for x in xs if (x["full"]["expectancy_r"] or -1) > 0 and (x["full"]["trades"] or 0) >= n)
        by = {c: [x for _, x in runs if x["cost"] == c] for c in ("retail_kraken", "low_fee_venue", "base")}
        cands = [x for _, x in runs if x.get("candidate")]
        tv = [x["test"]["expectancy_r"] for x in cands if x["test"]["expectancy_r"] is not None]
        fv = [x["full"]["expectancy_r"] for x in cands if x["full"]["expectancy_r"] is not None]
        out["strategies"] = {
            "generated": ev.get("generated"), "strategies": len(ev["strategies"]),
            "pairs": len({(sid, x["instrument"]) for sid, x in runs}), "runs": len(runs), "backtests": len(runs) * 8,
            "tests": ev.get("hypothesis_tests"), "holm": ev.get("holm_significant"),
            "dsr": ev.get("deflated_sharpe_best_validation"),
            "crypto_retail": [prof(by["retail_kraken"]), len(by["retail_kraken"])],
            "crypto_low_fee": [prof(by["low_fee_venue"]), len(by["low_fee_venue"])],
            "stocks": [prof(by["base"], 20), len(by["base"])],
            "gross_positive": sum(1 for _, x in runs if x["cost"] in ("retail_kraken", "base")
                                  and ((x.get("gross_full") or {}).get("expectancy_r") or -1) > 0),
            "candidates": len(cands), "candidate_strategies": len({s for s, x in runs if x.get("candidate")}),
            "candidates_test_positive": sum(1 for v in tv if v > 0),
            "candidates_avg_full": statistics.mean(fv) if fv else None,
            "candidates_avg_test": statistics.mean(tv) if tv else None,
            "top": [{k: x.get(k) for k in ("id", "name", "instrument", "trades", "expectancy_r", "gross_expectancy_r",
                                           "win_rate", "test_expectancy_r", "test_trades", "holm_significant")}
                    for x in ev.get("ranking", [])[:15]]}
    except (OSError, ValueError, KeyError) as e:
        out["strategies_error"] = str(e)
    try:
        with open(os.path.join(MAB_DIR, "results", "system_backtest_summary.json"), encoding="utf-8") as fh:
            out["system"] = json.load(fh)
    except (OSError, ValueError):
        pass
    try:
        with open(os.path.join(MAB_DIR, "results", "system_backtest_profiles.json"), encoding="utf-8") as fh:
            prof = json.load(fh)
        from mab.costs import FEE_PROFILE_LABELS
        out["fee_profiles"] = [{"profile": k, "label": FEE_PROFILE_LABELS.get(k, k), "runs": v["runs"],
                                "none": v["arms"]["none"]["return"]["mean"], "gates": v["arms"]["gates"]["return"]["mean"],
                                "brain": v["arms"]["brain"]["return"]["mean"],
                                "brain_positive": v["arms"]["brain"]["return"]["share_positive"],
                                "brain_trades": v["arms"]["brain"]["trades"]["mean"],
                                "brain_avg_r": (v["arms"]["brain"]["avg_r"] or {}).get("mean")}
                               for k, v in prof.items()]
        order = ["venue", "coinbase", "kraken", "ndax", "low_fee"]
        out["fee_profiles"].sort(key=lambda r: order.index(r["profile"]) if r["profile"] in order else 9)
    except (OSError, ValueError, KeyError):
        pass
    try:
        import gzip as _gz
        with _gz.open(os.path.join(PAYLOAD, "strategies", "results", "swing_lab.json.gz"), "rt", encoding="utf-8") as fh:
            lab = json.load(fh)
        rows = []
        for sc, groups in lab["scenarios"].items():
            for g, lst in groups.items():
                for r in lst:
                    if r.get("config"):
                        rows.append({"scenario": sc, "group": g, "setup": r["setup"], "config": r["config"],
                                     "train": r["train"]["mean"], "validation": r["validation"]["mean"],
                                     "test": r["test"]["mean"], "test_n": r["test"]["n"], "test_gross": r["test_gross"]["mean"],
                                     "test_cost": r["test_cost_r"], "survivor": r["survivor"],
                                     "holm": bool(r.get("holm_significant"))})
        out["swing_lab"] = {"generated": lab["generated"], "cuts": lab["cuts"], "configs_per_setup": lab["configs_per_setup"],
                            "rows": rows}
    except (OSError, ValueError, KeyError):
        pass
    try:
        from mab.volgate import MODEL_PATH
        with open(MODEL_PATH, encoding="utf-8") as fh:
            vg = json.load(fh)
        out["volgate"] = {a: {"horizon_hours": m["horizon_hours"], "rows": m["rows"], "period": m["period"],
                              "kind": m.get("kind"), "loud": m["test_loud"], "quiet": m["test_quiet"]}
                          for a, m in vg.items() if a in ("crypto", "stock")}
        out["volgate"]["generated"] = vg.get("generated")
    except (OSError, ValueError, KeyError):
        pass
    _results = out
    return out


def evaluation(sid: str) -> list:
    """Measured runs of one strategy (the batch evaluation plus the swing lab's)."""
    global _evaluation
    if _evaluation is None:
        _evaluation = {}
        base = os.path.join(PAYLOAD, "strategies", "results")
        p = os.path.join(base, "evaluation_summary.json")
        try:
            if os.path.exists(p):
                with open(p, encoding="utf-8") as fh:
                    _evaluation = json.load(fh).get("strategies", {})
            elif os.path.exists(p + ".gz"):
                with gzip.open(p + ".gz", "rt", encoding="utf-8") as fh:
                    _evaluation = json.load(fh).get("strategies", {})
            sw = os.path.join(base, "swing_eval.json")
            if os.path.exists(sw):
                with open(sw, encoding="utf-8") as fh:
                    _evaluation.update(json.load(fh).get("strategies", {}))
        except (OSError, ValueError):
            _evaluation = {}
    return (_evaluation.get(sid) or {}).get("runs", [])


def backtest_summary(sid: str, instrument: str = None, venue: str = None) -> dict:
    """The measured (backtest) result for a strategy on a market at the matching cost level, clearly labelled."""
    cost = "base" if venue == "yahoo" else ("low_fee_venue" if venue in ("okx", "demo") else "retail_kraken")
    runs = [r for r in evaluation(sid) if r.get("cost") == cost]
    same = [r for r in runs if r.get("instrument") == instrument] if instrument else []
    use = same or runs
    if not use:
        return {"label": "BACKTEST", "available": False, "note": "this strategy was not measured at this market's costs"}
    def agg(seg):
        vals = [(r.get(seg) or {}) for r in use]
        tr = sum((v.get("trades") or 0) for v in vals)
        ex = [v.get("expectancy_r") for v in vals if v.get("expectancy_r") is not None]
        return {"trades": tr, "expectancy_r": sum(ex) / len(ex) if ex else None}
    return {"label": "BACKTEST", "available": True, "cost_level": cost, "same_market": bool(same),
            "markets": sorted({r.get("instrument") for r in use}), "runs": len(use),
            "train": agg("train"), "validation": agg("validation"), "test": agg("test"), "full": agg("full"),
            "note": "measured on history after costs; the test segment is the untouched most recent part"}
