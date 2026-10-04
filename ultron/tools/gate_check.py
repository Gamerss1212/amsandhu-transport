#!/usr/bin/env python3
"""How the Jarvus Terminal's volatility gate (LOUD / NORMAL / QUIET) relates to ULTRON's trades: every crypto
walk-forward trade of the 1h and 4h councils (market entry, NDAX fees), split by the gate's reading at the hour the
bot decides, for train+validation and for the untouched test.

  python3 ultron/tools/gate_check.py <hourly dir with the trainer caches>

It is why the terminal's brain keeps its QUIET veto for ULTRON (1 trade in 391 falls in a QUIET hour) but not its
LOUD size cut (LOUD-hour trades are ULTRON's best; its stops already widen with volatility): mab/brain.py.
"""
import argparse, json, os, pickle, sys
from datetime import datetime, timezone
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, "ultron", "tools")); sys.path.insert(0, os.path.join(REPO, "market_analysis_bots"))
import export_terminal as X
from export_terminal import F, T
import backtest_all as B
from mab.volgate import VolGate, Bars, HORIZON
H1 = sys.argv[1]
ns = argparse.Namespace(h1=H1, m5=None, mkt=None)
hourly = B.bars("1h", ns)
vg = VolGate()
gbars = {}
def gate(sym, t_close):
    if sym not in gbars:
        t, o, h, l, c, v = hourly[sym]
        gbars[sym] = (Bars([int(x) for x in t], o.tolist(), h.tolist(), l.tolist(), c.tolist(), v.tolist(), HORIZON["crypto"]),
                      {int(x): k for k, x in enumerate(t)})
    b, idx = gbars[sym]
    i = idx.get(t_close - 3_600_000)          # the hourly bar that has just closed at decision time
    return vg.read(b, i, "crypto")["state"] if i is not None else "NA"
out = {}
for council in ("1h", "4h"):
    tf = X.TFKEY[council]
    m = json.load(open(B.model_file(tf)))
    events, defs, _, first_t = pickle.load(open(os.path.join(H1, X.CACHE[council]), "rb"))
    d0 = datetime.fromtimestamp((first_t + 365 * F.DAY) / 1000, timezone.utc)
    T.WF_START = max(T.ms(2022, 1, 1), int(datetime(d0.year, ((d0.month - 1) // 3) * 3 + 1, 1, tzinfo=timezone.utc).timestamp() * 1000))
    res = T.simulate(events, defs, m["params"], record=True)
    data = B.bars(tf, ns)
    ex = m.get("exit", {"hold": 96}); size = F.TFS[tf][0]
    ev_of = {(e[0], e[1], e[2]): e for e in events}
    preps = {}
    for x in res["trades"]:
        e = ev_of[(x["t"], x["cid"], x["coin"])]; sym = x["coin"]
        if sym not in preps:
            t, o, h, l, c, v = data[sym]; A = B.pg.atr(h, l, c)
            preps[sym] = ({"coin": sym, "t": t.tolist(), "o": o.tolist(), "h": h.tolist(), "l": l.tolist(), "c": c.tolist(),
                           "atr": [None if q != q else float(q) for q in A]}, {int(q): k for k, q in enumerate(t)})
        p, idx = preps[sym]; i = idx[int(x["t"]) - size]
        lim = p["c"][i] * 0.999
        px = next((p["o"][j] if p["o"][j] <= lim else lim) for j in range(i + 1, i + 4) if p["o"][j] <= lim or p["l"][j] <= lim)
        stop_atr = e[6] / 100 * px / p["atr"][i]
        kind = "major" if sym in T.MAJORS else "meme"
        tr = F.st.trade_path(p, i, "x", X.COSTS["ndax"], kind, entry="taker", stop_atr=stop_atr, rung=None, target_r=2.0,
                             tp1_bars=0, horizon=int(ex["hold"]))
        if not tr:
            continue
        g = gate(sym, int(x["t"]))          # x["t"] is the bar's close time (= open + size)
        key = f"{council} {'majors' if kind == 'major' else 'memes'}"
        out.setdefault(key, {}).setdefault(g, {"all": [], "test": []})
        out[key][g]["all"].append(float(tr["r"]))
        if x["period"] == "C":
            out[key][g]["test"].append(float(tr["r"]))
def s(r): return f"{len(r):4d} trades  {sum(r)/len(r):+.3f}R  win {100*sum(q>0 for q in r)/len(r):.0f}%" if r else "   0 trades"
for k, d in sorted(out.items()):
    for g, v in sorted(d.items()):
        dev = list(v["all"])
        for r in v["test"]:
            dev.remove(r)
        print(f"{k:13s} gate {g:7s} train+validation: {s(dev)}   test: {s(v['test'])}")
