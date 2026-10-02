"""Search behind references/jarvus-backtest.md section 6 (run from the repository: python3 jarvus/tools/improve.py DATA_PARENT_DIR)."""
import sys, json, itertools
sys.path.insert(0, __import__("os").path.join(__import__("os").path.dirname(__import__("os").path.abspath(__file__)), "..", "scripts"))
import system_test as S
from multiprocessing import Pool
SP = sys.argv[1] if len(sys.argv) > 1 else "."   # folder holding jbt-data/ (made by system_test.py --download)
SETS = {"all (ORB fixed)": ["trend_pullback", "breakout_retest", "sweep_reclaim", "orb", "rsi2"],
        "P3 + P6": ["breakout_retest", "orb"],
        "P1 + P3 + P6": ["trend_pullback", "breakout_retest", "orb"]}
GATES = {"gate as written": "on", "LOUD only": "loud_only"}
MGMT = {"half 1R + 2R, 8-bar stop": {}, "half 1R + 2R, 96h": {"tp1_bars": 0}, "one exit 2R, 96h": {"rung": None, "tp1_bars": 0}}
jobs = []
for g in ("majors", "memes"):
    for f in ("ndax", "low", "kraken"):
        for (sn, ss), (gn, gv), (mn, mv) in itertools.product(SETS.items(), GATES.items(), MGMT.items()):
            jobs.append((f"{sn} | {gn} | {mn}", g, f, dict(setups=ss, gate=gv, **mv)))
        jobs.append(("jarvus_v6 (as written)", g, f, {}))
with Pool(4, initializer=S._init, initargs=(SP + "/jbt-data",)) as pool:
    res = pool.map(S.run_one, jobs, chunksize=1)
json.dump(res, open(SP + "/improve.json", "w"), indent=1, default=str)
for g in ("majors", "memes"):
    for f in ("ndax", "low", "kraken"):
        rows = [r for r in res if r["group"] == g and r["fees"] == f]
        def pa(r, k): return r.get("periods", {}).get(k, {})
        rows.sort(key=lambda r: -(pa(r, "A").get("avg_r", -9) if pa(r, "A").get("n", 0) >= 50 else -9))
        print(f"\n== {g} {f}  (sorted by period-A avg R, n>=50)")
        for r in rows[:6] + [x for x in rows if x["name"].startswith("jarvus")]:
            print(f"  {r['name'][:60]:60} n {r['trades']:4}  all {r.get('avg_r', 0):+.3f}  A {pa(r,'A').get('avg_r', float('nan')):+.3f} ({pa(r,'A').get('n',0)})"
                  f"  B {pa(r,'B').get('avg_r', float('nan')):+.3f} ({pa(r,'B').get('n',0)})  C {pa(r,'C').get('avg_r', float('nan')):+.3f} ({pa(r,'C').get('n',0)})  ret {r['return_pct']:+.1f}%  dd {r.get('max_dd_pct',0):.1f}%")
