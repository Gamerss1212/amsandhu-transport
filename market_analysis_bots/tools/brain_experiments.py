"""Can the brain be made better? Test changes the honest way: choose on EARLY windows, judge on LATER ones.

    python tools/brain_experiments.py --cache DIR --fee-profile ndax [--windows 150] [--workers 2]

The candidate trades (tools/system_backtest.py) span a few months. Random 10-day windows are drawn separately from
the first 55% of that period (TUNE) and the last 45% (VALIDATE), with the same bot subsets for every variant, so
differences between variants are paired. Variants change one brain setting at a time and then a few combinations.
Selection uses TUNE only; the chosen variant is then judged on VALIDATE against the current brain, with a paired
bootstrap confidence interval. A variant that wins on TUNE and not on VALIDATE was luck and is dropped.

Order sizes are modelled as the shipped engine places them (adaptive slots, fractional US shares, liquidity cap) at
the balance given (default $10,000, where no order is too small, so sizing cannot confound the comparison).
"""

import argparse
import importlib.util
import json
import os
import random
import sys
import time
from multiprocessing import Pool

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
spec = importlib.util.spec_from_file_location("system_backtest", os.path.join(HERE, "system_backtest.py"))
SBT = importlib.util.module_from_spec(spec)
sys.modules["system_backtest"] = SBT
spec.loader.exec_module(SBT)
from mab import sysbacktest as SB  # noqa: E402
from mab.clock import DAY  # noqa: E402

SIZING = {"realistic": True, "max_open": 20, "min_slot": 25.0, "fractional_us": True, "participation": 0.05}
VARIANTS = {
    "current": {},
    "edge>=0": {"brain_opts": {"veto_edge": 0.0}},
    "edge>=0.05": {"brain_opts": {"veto_edge": 0.05}},
    "edge>=0.10": {"brain_opts": {"veto_edge": 0.10}},
    "edge>=0.20": {"brain_opts": {"veto_edge": 0.20}},
    "deterministic": {"brain_opts": {"deterministic": True}},
    "deterministic+edge>=0": {"brain_opts": {"deterministic": True, "veto_edge": 0.0}},
    "deterministic+edge>=0.05": {"brain_opts": {"deterministic": True, "veto_edge": 0.05}},
    "deterministic+edge>=0.10": {"brain_opts": {"deterministic": True, "veto_edge": 0.10}},
    "cost<=0.25": {"brain_opts": {"cost_veto_r": 0.25}},
    "cost<=0.20": {"brain_opts": {"cost_veto_r": 0.20}},
    "cost<=0.15": {"brain_opts": {"cost_veto_r": 0.15}},
    "evidence>=8 to trade": {"brain_opts": {"min_trade_evidence": 8.0}},
    "evidence>=25 to trade": {"brain_opts": {"min_trade_evidence": 25.0}},
    "no weekends (crypto)": {"skip_weekends": True},
    "deterministic+edge>=0.05+cost<=0.25": {"brain_opts": {"deterministic": True, "veto_edge": 0.05, "cost_veto_r": 0.25}},
}

_G = {}


def _init(windows, priors, families, balance):
    _G.update(windows=windows, priors=priors, families=families, balance=balance)


def _run_variant(item):
    name, kw = item
    out = {}
    for part in ("tune", "validate"):
        rows = []
        for n, (w0, w1, cs) in enumerate(_G["windows"][part]):
            r = SB.run(cs, w0, w1, "brain", seed=12345 + n, priors=_G["priors"], families=_G["families"],
                       capital=_G["balance"], **SIZING, **kw)
            rows.append({"ret": r["return"], "trades": r["trades"], "r": r["avg_r"], "dd": r["max_dd"], "wins": r["win_rate"]})
        out[part] = rows
    return name, out


def boot_ci(diff, rng, n=4000):
    m = len(diff)
    xs = sorted(sum(diff[rng.randrange(m)] for _ in range(m)) / m for _ in range(n))
    return xs[int(0.025 * n)], xs[int(0.975 * n)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", required=True)
    ap.add_argument("--fee-profile", default="ndax")
    ap.add_argument("--windows", type=int, default=150)
    ap.add_argument("--window-days", type=int, default=10)
    ap.add_argument("--bots-per-run", type=int, default=60)
    ap.add_argument("--balance", type=float, default=10_000.0)
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    t0 = time.time()
    SBT.init(a.cache, a.fee_profile)
    bots = json.load(open(os.path.join(ROOT, "bots", "registry.json")))["bots"]
    cat = {s["id"]: s for s in json.load(open(os.path.join(SBT.STRAT, "catalog.json")))["strategies"]}
    jobs = [(b, cat[b["strategy_id"]]["definition"], cat[b["strategy_id"]]["family"]) for b in bots
            if cat.get(b["strategy_id"], {}).get("definition") and not (set(cat[b["strategy_id"]]["data"]) & {"trades", "book"})]
    with Pool(3, initializer=SBT.init, initargs=(a.cache, a.fee_profile)) as pool:
        res = pool.map(SBT.work, jobs, chunksize=2)
    cands = [SB.Candidate(**c) for r in res if not r.get("error") for c in r["cands"]]
    usable = sorted({c.bot for c in cands})
    t_start = min(r["cutoff"] for r in res if not r.get("error"))
    t_end = max(r["end"] for r in res if not r.get("error"))
    families = {sid: s["family"] for sid, s in cat.items()}
    ev = os.path.join(SBT.STRAT, "results", "evaluation_summary.json")
    priors = [ev if os.path.exists(ev) else ev + ".gz", os.path.join(SBT.STRAT, "results", "swing_eval.json")]
    by_bot = {}
    for c in cands:
        by_bot.setdefault(c.bot, []).append(c)
    split = t_start + int(0.55 * (t_end - t_start))
    rng = random.Random(4242)
    windows = {"tune": [], "validate": []}
    for part, lo, hi in (("tune", t_start, split - a.window_days * DAY), ("validate", split, t_end - a.window_days * DAY)):
        span_days = max(1, (hi - lo) // DAY)
        for _ in range(a.windows):
            w0 = lo + rng.randrange(span_days) * DAY
            subset = rng.sample(usable, min(a.bots_per_run, len(usable)))
            windows[part].append((w0, w0 + a.window_days * DAY,
                                  sorted((c for b in subset for c in by_bot.get(b, [])), key=lambda c: c.t_in)))
    print(f"{len(cands)} candidates; tune windows start before {time.strftime('%Y-%m-%d', time.gmtime(split / 1000))}, "
          f"validate windows after; {(time.time() - t0) / 60:.1f} min", flush=True)
    results = {}
    with Pool(a.workers, initializer=_init, initargs=(windows, priors, families, a.balance)) as pool:
        for name, out in pool.imap_unordered(_run_variant, list(VARIANTS.items())):
            results[name] = out
            tr = [x["ret"] for x in out["tune"]]
            print(f"  done {name:40} tune mean {sum(tr) / len(tr) * 100:+.4f}%", flush=True)
    rng = random.Random(1)
    rows = []
    base_t = [x["ret"] for x in results["current"]["tune"]]
    base_v = [x["ret"] for x in results["current"]["validate"]]
    for name in VARIANTS:
        t = [x["ret"] for x in results[name]["tune"]]
        v = [x["ret"] for x in results[name]["validate"]]
        dt = [x - y for x, y in zip(t, base_t)]
        dv = [x - y for x, y in zip(v, base_v)]
        lo, hi = boot_ci(dv, rng) if name != "current" else (0.0, 0.0)
        tr_v = sum(x["trades"] for x in results[name]["validate"]) / len(v)
        rv = [x["r"] for x in results[name]["validate"] if x["r"] is not None]
        rows.append({"variant": name, "tune_mean": sum(t) / len(t), "tune_vs_current": sum(dt) / len(dt),
                     "validate_mean": sum(v) / len(v), "validate_vs_current": sum(dv) / len(dv), "validate_ci": [lo, hi],
                     "validate_trades": tr_v, "validate_avg_r": sum(rv) / len(rv) if rv else None,
                     "validate_share_positive": sum(1 for x in v if x > 0) / len(v)})
    rows.sort(key=lambda r: -r["tune_mean"])
    print("\nvariant                                    tune mean   | VALIDATE mean   vs current [95% CI]            trades  avgR   win%")
    for r in rows:
        print(f"{r['variant']:42} {r['tune_mean'] * 100:+.4f}% | {r['validate_mean'] * 100:+.4f}% {r['validate_vs_current'] * 100:+.4f}% "
              f"[{r['validate_ci'][0] * 100:+.4f}, {r['validate_ci'][1] * 100:+.4f}]  {r['validate_trades']:5.1f}  "
              f"{(r['validate_avg_r'] if r['validate_avg_r'] is not None else float('nan')):+.3f}  {r['validate_share_positive'] * 100:4.1f}")
    out = a.out or f"brain_experiments_{a.fee_profile}"
    json.dump({"fee_profile": a.fee_profile, "balance": a.balance, "windows_each": a.windows, "rows": rows,
               "results": results, "generated": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()),
               "minutes": round((time.time() - t0) / 60, 1)},
              open(os.path.join(ROOT, "results", out + ".json"), "w"))


if __name__ == "__main__":
    main()
