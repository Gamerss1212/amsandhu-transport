"""Search behind references/jarvus-backtest.md section 6 (run from the repository: python3 jarvus/tools/robust.py DATA_PARENT_DIR)."""
import sys, json, itertools, math
sys.path.insert(0, __import__("os").path.join(__import__("os").path.dirname(__import__("os").path.abspath(__file__)), "..", "scripts"))
import system_test as S
from multiprocessing import Pool
SP = sys.argv[1] if len(sys.argv) > 1 else "."   # folder holding jbt-data/ (made by system_test.py --download)
ALL = ["trend_pullback", "breakout_retest", "sweep_reclaim", "orb", "rsi2"]
jobs = []
for g in ("majors", "memes"):
    for mg, mv in (("half1R+2R", {}), ("one exit 2R", {"rung": None})):
        for st, hz in itertools.product((3.0, 4.0, 5.0), (48, 96, 144)):
            jobs.append((f"LOUD | {mg} | stop {st:g}xATR | {hz}h", g, "ndax", dict(setups=ALL, gate="loud_only", tp1_bars=0, stop_atr=st, horizon=hz, **mv)))
    jobs.append(("CONTROL random entries | LOUD | half1R+2R 96h", g, "ndax", dict(setups=["benchmark"], gate="loud_only", tp1_bars=0)))
    jobs.append(("CONTROL random entries | LOUD | half1R+2R 96h | no engine", g, "ndax", dict(setups=["benchmark"], gate="loud_only", tp1_bars=0, engine=False)))
    jobs.append(("CONTROL random entries | gate as written | 96h | no engine", g, "ndax", dict(setups=["benchmark"], tp1_bars=0, engine=False)))
    jobs.append(("setups | LOUD | 96h | no engine", g, "ndax", dict(setups=ALL, gate="loud_only", tp1_bars=0, engine=False)))
    jobs.append(("setups | LOUD | 96h | no regime/BTC rules", g, "ndax", dict(setups=ALL, gate="loud_only", tp1_bars=0, regime=False, btc_first=False)))
with Pool(4, initializer=S._init, initargs=(SP + "/jbt-data",)) as pool:
    res = pool.map(S.run_one, jobs, chunksize=1)
json.dump(res, open(SP + "/robust.json", "w"), indent=1, default=str)
def pa(r, k): return r.get("periods", {}).get(k, {})
for g in ("majors", "memes"):
    print(f"\n== {g} ndax")
    for r in [x for x in res if x["group"] == g]:
        print(f"  {r['name'][:58]:58} n {r['trades']:4} all {r.get('avg_r', 0):+.3f} t {r.get('t_stat')}  A {pa(r,'A').get('avg_r', float('nan')):+.3f} ({pa(r,'A').get('n',0)})"
              f"  B {pa(r,'B').get('avg_r', float('nan')):+.3f} ({pa(r,'B').get('n',0)})  C {pa(r,'C').get('avg_r', float('nan')):+.3f} ({pa(r,'C').get('n',0)})  ret {r['return_pct']:+.1f}% dd {r.get('max_dd_pct',0):.1f}%")
