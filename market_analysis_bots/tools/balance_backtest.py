"""Does the software work with any balance? The full system replayed at several starting balances.

    python tools/balance_backtest.py --cache DIR [--runs 400] [--fee-profile venue]

Same candidates, windows and bot subsets as tools/system_backtest.py (the brain arm only), but with order sizes
modelled as the engine places them (sysbacktest.run(realistic=True)): risk-based size capped at the slot, venue
minimum orders, whole shares for stocks, the cash a spot account has, 20 open positions at most. Two engine
versions are compared at each balance:

  before   20 fixed capital slots, whole shares only, no liquidity cap
  after    adaptive slots (at least $25 each), fractional US shares ($1 minimum, as Alpaca offers),
           entries capped at 5% of the market's recent dollar volume
  bump     20 slots kept; an order below the venue minimum is raised to it when that is at most 5x its
           risk-based size (and fits the slot and the cash); fractional US shares; the same liquidity cap

Writes results/balance_backtest.json and docs/BALANCE_BACKTEST.md.
"""

import argparse
import importlib.util
import json
import math
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
sys.modules["system_backtest"] = SBT                  # so worker processes can find its functions
spec.loader.exec_module(SBT)
from mab import sysbacktest as SB  # noqa: E402
from mab.clock import DAY  # noqa: E402

BALANCES = [100, 1_000, 10_000, 100_000, 10_000_000]
VERSIONS = {
    "before": {"realistic": True, "max_open": 20},
    "after": {"realistic": True, "max_open": 20, "min_slot": 25.0, "fractional_us": True, "participation": 0.05},
    "bump": {"realistic": True, "max_open": 20, "min_bump": 5.0, "fractional_us": True, "participation": 0.05},
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", required=True)
    ap.add_argument("--runs", type=int, default=400)
    ap.add_argument("--window-days", type=int, default=10)
    ap.add_argument("--bots-per-run", type=int, default=60)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--fee-profile", default="venue")
    a = ap.parse_args()
    t0 = time.time()
    SBT.init(a.cache, a.fee_profile)
    with open(os.path.join(ROOT, "bots", "registry.json")) as fh:
        bots = json.load(fh)["bots"]
    with open(os.path.join(SBT.STRAT, "catalog.json")) as fh:
        cat = {s["id"]: s for s in json.load(fh)["strategies"]}
    jobs = [(b, cat[b["strategy_id"]]["definition"], cat[b["strategy_id"]]["family"]) for b in bots
            if cat.get(b["strategy_id"], {}).get("definition") and not (set(cat[b["strategy_id"]]["data"]) & {"trades", "book"})]
    with Pool(a.workers, initializer=SBT.init, initargs=(a.cache, a.fee_profile)) as pool:
        res = pool.map(SBT.work, jobs, chunksize=2)
    cands = [SB.Candidate(**c) for r in res if not r.get("error") for c in r["cands"]]
    usable = sorted({c.bot for c in cands})
    t_start = min(r["cutoff"] for r in res if not r.get("error"))
    t_end = max(r["end"] for r in res if not r.get("error"))
    families = {sid: s["family"] for sid, s in cat.items()}
    ev = os.path.join(SBT.STRAT, "results", "evaluation_summary.json")
    priors = [ev if os.path.exists(ev) else ev + ".gz", os.path.join(SBT.STRAT, "results", "swing_eval.json")]
    print(f"{len(cands)} candidates from {len(usable)} bots; {(time.time() - t0) / 60:.1f} min", flush=True)

    by_bot = {}
    for c in cands:
        by_bot.setdefault(c.bot, []).append(c)
    rng = random.Random(12345)
    span = t_end - t_start - a.window_days * DAY
    windows = []
    for n in range(a.runs):
        w0 = t_start + (rng.randrange(max(1, span // DAY)) * DAY if span > 0 else 0)
        subset = rng.sample(usable, min(a.bots_per_run, len(usable)))
        windows.append((w0, w0 + a.window_days * DAY, sorted((c for b in subset for c in by_bot.get(b, [])), key=lambda c: c.t_in)))
    out = {"generated": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()), "runs": a.runs, "window_days": a.window_days,
           "bots_per_run": a.bots_per_run, "fee_profile": a.fee_profile, "versions": VERSIONS, "results": {}}
    for bal in BALANCES:
        for name, kw in VERSIONS.items():
            rows = [SB.run(cs, w0, w1, "brain", seed=12345 + n, priors=priors, families=families, capital=float(bal), **kw)
                    for n, (w0, w1, cs) in enumerate(windows)]
            ret = sorted(r["return"] for r in rows)
            k = f"{bal}|{name}"
            out["results"][k] = {
                "balance": bal, "version": name,
                "trades_per_window": sum(r["trades"] for r in rows) / len(rows),
                "return_mean": sum(ret) / len(ret), "return_median": ret[len(ret) // 2],
                "return_p05": ret[int(0.05 * len(ret))], "return_p95": ret[min(len(ret) - 1, int(0.95 * len(ret)))],
                "share_positive": sum(1 for x in ret if x > 0) / len(ret),
                "refused_too_small_per_window": sum(r["skipped_size"] for r in rows) / len(rows),
                "refused_no_cash_per_window": sum(r["skipped_cash"] for r in rows) / len(rows),
                "capped_by_liquidity_per_window": sum(r["capped_liquidity"] for r in rows) / len(rows),
            }
            x = out["results"][k]
            print(f"{bal:>11,} {name:6}  trades/window {x['trades_per_window']:6.2f}  refused-too-small "
                  f"{x['refused_too_small_per_window']:6.2f}  no-cash {x['refused_no_cash_per_window']:5.2f}  liquidity-capped "
                  f"{x['capped_by_liquidity_per_window']:5.2f}  mean {x['return_mean'] * 100:+.4f}%  positive "
                  f"{x['share_positive'] * 100:5.1f}%", flush=True)
    out["minutes"] = round((time.time() - t0) / 60, 1)
    with open(os.path.join(ROOT, "results", "balance_backtest.json"), "w") as fh:
        json.dump(out, fh, indent=1)
    write_report(out)


def write_report(o):
    L = ["# Does it work with any balance?\n",
         f"The full system (brain arm) replayed on {o['runs']} random {o['window_days']}-day windows with "
         f"{o['bots_per_run']} bots each, at several starting balances, with order sizes modelled as the engine places "
         "them: venue minimum orders, whole shares for stocks unless fractional, the cash a spot account has, 20 open "
         f"positions at most. Fee level: {o['fee_profile']}. Generated {o['generated']}.\n",
         "* **before**: 20 fixed capital slots, whole shares only.",
         "* **after**: adaptive slots (at least $25 each), fractional US shares ($1 minimum, as Alpaca offers), "
         "entries capped at 5% of the market's recent dollar volume.\n",
         "| Balance | Version | Trades per window | Refused as too small | Refused, no cash | Capped by liquidity | "
         "Mean return | Windows positive |",
         "|---|---|---|---|---|---|---|---|"]
    for k, x in o["results"].items():
        L.append(f"| ${x['balance']:,} | {x['version']} | {x['trades_per_window']:.2f} | {x['refused_too_small_per_window']:.2f} "
                 f"| {x['refused_no_cash_per_window']:.2f} | {x['capped_by_liquidity_per_window']:.2f} "
                 f"| {x['return_mean'] * 100:+.4f}% | {x['share_positive'] * 100:.1f}% |")
    L.append("\nReturns are percentages of the starting balance; they are simulations of past data, not a forecast.")
    with open(os.path.join(ROOT, "docs", "BALANCE_BACKTEST.md"), "w") as fh:
        fh.write("\n".join(L) + "\n")


if __name__ == "__main__":
    main()
