#!/usr/bin/env python3
"""Put the ULTRON councils into the Jarvus Terminal: strategies in strategies/catalog.json, bots in
market_analysis_bots/bots/registry.json, and the councils' measured walk-forward results per market as the terminal
brain's starting evidence (market_analysis_bots/results/ultron_priors.json).

  python3 ultron/tools/export_terminal.py --h1 <hourly dir with the trainer caches>
The evidence comes from re-running each council's walk-forward (the same simulation that wrote its model file).
"""

from __future__ import annotations

import argparse
import json
import os
import pickle
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import train_tf as F  # noqa: E402
from train_tf import T  # noqa: E402

REPO = os.path.dirname(os.path.dirname(HERE))
CATALOG = os.path.join(REPO, "strategies", "catalog.json")
REGISTRY = os.path.join(REPO, "market_analysis_bots", "bots", "registry.json")
PRIORS = os.path.join(REPO, "market_analysis_bots", "results", "ultron_priors.json")
sys.path.insert(0, os.path.join(REPO, "ultron", "core"))
import markets as mk  # noqa: E402

COINS_MAJ = ["BTC", "ETH", "SOL"]
COINS_MEME = ["DOGE", "SHIB", "PEPE", "BONK", "WIF", "FLOKI"]
STRATS = [  # id, council, group, name, timeframe, risk %, order ttl bars, max bars
    ("STRAT-U01", "1h", "majors", "ULTRON council 1h: BTC, ETH, SOL", "1h", 0.6, 3, 96),
    ("STRAT-U02", "1h", "memes", "ULTRON council 1h: meme coins", "1h", 0.3, 3, 96),
    ("STRAT-U03", "4h", "majors", "ULTRON council 4h: BTC, ETH, SOL", "1h", 0.6, 12, 384),
    ("STRAT-U04", "4h", "memes", "ULTRON council 4h: meme coins", "1h", 0.3, 12, 384),
    ("STRAT-U05", "1D", "markets", "ULTRON daily markets council: stocks, ETFs, forex, gold, silver, oil", "1d", 0.6, 3, 96),
]
CACHE = {"1h": "ultron_tf_1h.pkl", "4h": "ultron_tf_4h.pkl", "1D": "ultron_tf_1Dm.pkl"}
MODEL = {"1h": "1h.json", "4h": "4h.json", "1D": "1D_markets.json"}


def instruments(group):
    if group == "majors":
        return [("coinbase", f"{c}-USD", c) for c in COINS_MAJ]
    if group == "memes":
        return [("coinbase", f"{c}-USD", c) for c in COINS_MEME]
    return [("yahoo", mk.YAHOO[s], s) for s in mk.YAHOO]


COSTS = {"ndax": (0.0020, 0.0020), "retail_kraken": (0.0040, 0.0080), "low_fee_venue": (0.0008, 0.0010)}
TFKEY = {"1h": "1h", "4h": "4h", "1D": "1Dm"}


def evidence(council, h1, m5, mkt):
    """Every trade of the council's walk-forward replayed with a MARKET entry (what live trading supports), at each
    fee level. -> ({cost: {symbol: {period: [r...]}}}, model)"""
    import backtest_all as B
    tf = TFKEY[council]
    with open(B.model_file(tf)) as fh:
        m = json.load(fh)
    with open(os.path.join(h1, CACHE[council]), "rb") as fh:
        events, defs, _, first_t = pickle.load(fh)
    d0 = datetime.fromtimestamp((first_t + 365 * F.DAY) / 1000, timezone.utc)
    q0 = datetime(d0.year, ((d0.month - 1) // 3) * 3 + 1, 1, tzinfo=timezone.utc)
    T.WF_START = max(T.ms(2022, 1, 1), int(q0.timestamp() * 1000))
    res = T.simulate(events, defs, m["params"], record=True)
    data = B.bars(tf, argparse.Namespace(h1=h1, m5=m5, mkt=mkt))
    ex = m.get("exit", {"stop_chart": 4.0, "stop_htf": 4.0, "hold": 96})
    size = F.TFS[tf][0]
    ev_of = {(e[0], e[1], e[2]): e for e in events}
    costs = {"base": F.st.FEES["markets"]} if council == "1D" else COSTS
    out = {k: {} for k in costs}
    preps = {}
    for x in res["trades"]:
        e = ev_of[(x["t"], x["cid"], x["coin"])]
        sym = x["coin"]
        if sym not in preps:
            t, o, h, l, c, v = data[sym]
            A = B.pg.atr(h, l, c)
            preps[sym] = ({"coin": sym, "t": t.tolist(), "o": o.tolist(), "h": h.tolist(), "l": l.tolist(), "c": c.tolist(),
                           "atr": [None if q != q else float(q) for q in A]}, {int(q): k for k, q in enumerate(t)})
        p, idx = preps[sym]
        i = idx[int(x["t"]) - size]
        lim = p["c"][i] * 0.999
        px = next((p["o"][j] if p["o"][j] <= lim else lim) for j in range(i + 1, i + 4) if p["o"][j] <= lim or p["l"][j] <= lim)
        stop_atr = e[6] / 100 * px / p["atr"][i]
        kind = "major" if council == "1D" or sym in T.MAJORS else "meme"
        for ck, fees in costs.items():
            tr = F.st.trade_path(p, i, "x", fees, kind, entry="taker", stop_atr=stop_atr, rung=None, target_r=2.0, tp1_bars=0,
                                 horizon=int(ex["hold"]))
            if tr:
                out[ck].setdefault(sym, {"train": [], "validation": [], "test": []})[
                    {"dev": "train", "B": "validation", "C": "test"}[x["period"]]].append(float(tr["r"]))
    return out, m


def seg(rs):
    if not rs:
        return {"trades": 0, "expectancy_r": None, "win_rate": None, "profit_factor": None}
    pos, neg = sum(r for r in rs if r > 0), -sum(r for r in rs if r < 0)
    return {"trades": len(rs), "expectancy_r": round(sum(rs) / len(rs), 4), "win_rate": round(sum(r > 0 for r in rs) / len(rs), 4),
            "profit_factor": round(pos / neg, 3) if neg > 0 else None}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--h1", required=True)
    ap.add_argument("--m5", required=True)
    ap.add_argument("--mkt", required=True)
    a = ap.parse_args()
    with open(CATALOG) as fh:
        cat = json.load(fh)
    with open(REGISTRY) as fh:
        reg = json.load(fh)
    cat["strategies"] = [s for s in cat["strategies"] if not s["id"].startswith("STRAT-U")]
    reg["bots"] = [b for b in reg["bots"] if not b["bot_id"].startswith("BOT-U")]
    priors = {"generated": datetime.now(timezone.utc).strftime("%Y-%m-%d"), "source": "ULTRON council walk-forward", "strategies": {}}
    ev_cache = {}
    nb = 0
    for sid, council, group, name, tf, risk, ttl, max_bars in STRATS:
        if council not in ev_cache:
            ev_cache[council] = evidence(council, a.h1, a.m5, a.mkt)
        ev, m = ev_cache[council]
        d = {"id": sid, "name": name, "family": "ultron", "timeframe": tf, "direction": "long", "version": "1.0.0", "params": {},
             "entry": {"long": f'ultron("{council}") > 0'}, "filters": [],
             "order": {"type": "market"},
             "stop": {"type": "level", "long": f'ultron_stop("{council}")'}, "target": {"type": "r", "r": 2.0},
             "trail": {"type": "none"}, "exit": {}, "max_bars": max_bars, "session": {"hold_overnight": True}, "max_trades_per_day": 3,
             "cooldown_bars": 0, "sizing": {"risk_pct": risk, "max_notional_pct": 100.0}, "data": ["bars"], "engine": "rules"}
        insts = {x[2]: x[1] for x in instruments(group)}
        runs, results, best = [], [], None
        for ck, by in ev.items():
            agg = {"train": [], "validation": [], "test": []}
            for sym, segs in by.items():
                if sym not in insts:
                    continue
                for k in agg:
                    agg[k] += segs[k]
                full = segs["train"] + segs["validation"] + segs["test"]
                runs.append({"instrument": insts[sym], "cost": ck, "candidate": False, "full": seg(full),
                             "train": seg(segs["train"]), "validation": seg(segs["validation"]), "test": seg(segs["test"])})
            full = agg["train"] + agg["validation"] + agg["test"]
            row = {"instrument": "*", "cost": ck, "candidate": True, "full": seg(full), "train": seg(agg["train"]),
                   "validation": seg(agg["validation"]), "test": seg(agg["test"])}
            runs.append(row)
            for per in ("train", "validation", "test"):
                g = row[per]
                results.append({"period": per, "instrument": "all council markets", "tf": council, "cost_mult": ck,
                                "dataset": f"ULTRON walk-forward, market entries, {ck} costs", "p_value": None, "note": "",
                                "metrics": {"trades": g["trades"], "win_rate": g["win_rate"], "expectancy_r": g["expectancy_r"],
                                            "profit_factor": g["profit_factor"], "net_return": None, "sharpe": None, "max_drawdown": None}})
            if ck in ("ndax", "base"):
                best = {"instrument": "all council markets", "expectancy_r": row["full"]["expectancy_r"], "trades": row["full"]["trades"],
                        "net_return": None, "test_expectancy_r": row["test"]["expectancy_r"], "gross_expectancy_r": None}
        evaluation = {"status": "out-of-sample tested", "best_realistic": best or {}, "candidates": [], "results": results,
                      "summary": f"walk-forward 2022-{m['data_end'][:4]} with market entries: see results by fee level"}
        cat["strategies"].append({
            "id": sid, "key": f"ultron_{council.lower()}_{group}", "name": name, "family": "ultron", "subfamily": "trained council",
            "mechanism": "25 trained agents (candle and indicator signals with volatility and trend conditions) chosen by a "
                         "quarterly walk-forward; a learned brain approves only signals whose edge minus caution clears its "
                         "threshold, after fees",
            "logic": "continuation", "anchor": "volatility gate + trend + learned agent edges",
            "hypothesis": "volatility clusters and is forecastable; trend-aligned signals in LOUD periods pay after costs",
            "markets": ["stock"] if group == "markets" else ["crypto"], "timeframe": tf, "definition": d, "data": ["bars"],
            "evidence": [], "references": [], "failure_modes": ["regime change after the training period", "fees above the trained level"],
            "implementation_status": "implemented", "research_status": "sourced", "evaluation_status": "out-of-sample tested",
            "evaluation": evaluation, "live_evidence": None, "blocked": None, "distinct": True, "notes": "ULTRON (see ultron/tv/BACKTEST_ALL.md)",
            "instruments": [x[1] for x in instruments(group)], "variants": [], "warmup_bars": 1700, "spec": {}, "pack_refs": [],
            "parent": None, "subfamily_note": None})
        for venue, inst, sym in instruments(group):
            nb += 1
            reg["bots"].append({"bot_id": f"BOT-U{nb:03d}", "name": f"{name.split(':')[0]} | {inst}", "strategy_id": sid,
                                "venue": venue, "instrument": inst, "enabled": True, "stages": ["1", "10", "50", "250"]})
        priors["strategies"][sid] = {"runs": runs}
    cnt = cat.setdefault("counts", {})
    prev, k = cnt.get("ultron_strategies", 0), len(STRATS)               # idempotent: replace what an earlier export added
    for key in ("counted_strategies", "implemented"):
        cnt[key] = cnt.get(key, 0) - prev + k
    for grp, key in (("research_status", "sourced"), ("evaluation_status", "out-of-sample tested")):
        cnt.setdefault(grp, {})[key] = cnt[grp].get(key, 0) - prev + k
    cnt.setdefault("families", {})["ultron"] = k
    cnt["ultron_strategies"] = k
    for path, obj in ((CATALOG, cat), (REGISTRY, reg)):
        with open(path, "w") as fh:
            json.dump(obj, fh, indent=1, ensure_ascii=False)
    with open(PRIORS, "w") as fh:
        json.dump(priors, fh, indent=1)
    print(f"{len(STRATS)} ULTRON strategies, {nb} bots, {sum(len(v['runs']) for v in priors['strategies'].values())} evaluation rows")
    for sid_, v in priors["strategies"].items():
        print(" ", sid_, "; ".join(f"{r['cost']}: test {r['test']['expectancy_r']}R x {r['test']['trades']}, all {r['full']['expectancy_r']}R x {r['full']['trades']}"
                                  for r in v["runs"] if r["instrument"] == "*"))


if __name__ == "__main__":
    main()
