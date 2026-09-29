"""Backtest the whole software many times (writes results/system_backtest.json and docs/SYSTEM_BACKTEST.md).

    python tools/system_backtest.py --cache DIR [--runs 1000] [--window-days 10] [--bots-per-run 60]

Uses every bot in bots/registry.json, the evaluation datasets (strategies/src/run_evaluation.py cache)
plus the extra instruments the registry needs, the volatility gate model and the batch evaluation
(priors from the TRAIN segment only). Windows are drawn only from the part of each dataset after the
training segment (60% + 1-day embargo), so the brain never starts out knowing the period it trades.
"""

import argparse
import json
import math
import os
import pickle
import random
import sys
import time
from multiprocessing import Pool

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
STRAT = os.path.join(os.path.dirname(ROOT), "strategies")
sys.path.insert(0, os.path.join(STRAT, "src"))

from mab import backtest, sysbacktest as SB  # noqa: E402
from mab.clock import DAY, tf_ms  # noqa: E402
from mab.frame import Frame  # noqa: E402
from mab.models import Bar  # noqa: E402
from mab.volgate import VolGate  # noqa: E402

EXTRA_CRYPTO = ["XRP-USD", "LINK-USD", "AVAX-USD", "LTC-USD"]
EXTRA_STOCKS = ["MSFT", "AMZN", "AMD", "META", "COIN", "SHOP.TO", "RY.TO"]
DATA_MAP = {("kraken", "XXBTZUSD"): ("coinbase", "BTC-USD"), ("kraken", "XETHZUSD"): ("coinbase", "ETH-USD"),
            ("okx", "BTC-USDT"): ("coinbase", "BTC-USD"), ("okx", "ETH-USDT"): ("coinbase", "ETH-USD")}
DATA, FRAMES, HOURLY = {}, {}, {}


def load_data(cache):
    with open(os.path.join(cache, "eval_data.pkl"), "rb") as fh:
        data = pickle.load(fh)
    extra = os.path.join(cache, "extra_data.pkl")
    if os.path.exists(extra):
        with open(extra, "rb") as fh:
            data.update(pickle.load(fh))
        return data
    from mab.data.adapters import Coinbase, Yahoo
    from mab.net import Http
    http = Http(limits={"api.exchange.coinbase.com": (2.0, 3), "query1.finance.yahoo.com": (1.0, 2)})
    cb, yh = Coinbase(http), Yahoo(http)
    add = {}
    for s in EXTRA_CRYPTO:
        out, end = {}, None
        while len(out) < 120 * 288:
            batch = cb.bars(s, "5m", limit=300, end_ms=end)
            if not batch:
                break
            for b in batch:
                out[b.event_time] = b
            oldest = min(b.event_time for b in batch)
            if end is not None and oldest >= end:
                break
            end = oldest - 1
        add[("coinbase", s, "5m")] = [out[k] for k in sorted(out)]
        print("extra", s, len(add[("coinbase", s, "5m")]), flush=True)
    for s in EXTRA_STOCKS:
        for tf in ("5m", "1h", "1d"):
            try:
                add[("yahoo", s, tf)] = yh.bars(s, tf, limit=10 ** 6)
            except Exception as e:
                print("extra error", s, tf, e)
        print("extra", s, len(add.get(("yahoo", s, "5m"), [])), flush=True)
    with open(extra, "wb") as fh:
        pickle.dump(add, fh)
    data.update(add)
    return data


def resample(bars, tf):
    step = tf_ms(tf)
    out = {}
    for b in bars:
        k = b.event_time - b.event_time % step
        o = out.get(k)
        if o is None:
            out[k] = Bar(b.venue, b.instrument, tf, k, b.open, b.high, b.low, b.close, b.volume, b.receipt_time, "resampled")
        else:
            o.high, o.low, o.close, o.volume = max(o.high, b.high), min(o.low, b.low), b.close, o.volume + b.volume
    last = max(out) if out else 0
    return [out[k] for k in sorted(out) if k != last]


def frame(venue, sym, tf):
    key = (venue, sym, tf)
    if key in FRAMES:
        return FRAMES[key]
    bars = DATA.get(key)
    if bars is None:
        base = DATA.get((venue, sym, "5m"))
        if base and tf_ms(tf) > tf_ms("5m"):
            bars = resample(base, tf)
    FRAMES[key] = Frame(venue, sym, tf, "stock" if venue == "yahoo" else "crypto", bars) if bars else None
    return FRAMES[key]


def resolver(venue, sym, tf):
    if ":" in sym:
        venue, sym = sym.split(":", 1)
    return frame(venue, sym, tf)


def init(cache):
    DATA.update(load_data(cache))


def work(job):
    bot, definition, family = job
    try:
        from mab.runtime import load_events
        from mab.strategy import compile_strategy, evaluate as eval_rules
        venue, inst = bot["venue"], bot["instrument"]
        dv, ds = DATA_MAP.get((venue, inst), (venue, inst))
        tf = definition["timeframe"]
        f = frame(dv, ds, tf)
        if f is None or f.n < 500:
            return {"bot": bot["bot_id"], "error": f"no data {dv}:{ds} {tf}"}
        asset = "stock" if venue == "yahoo" else "crypto"
        c = compile_strategy(definition, bot.get("params") or {}, asset)
        rs = eval_rules(c, f, resolver, load_events({}))
        can_short = asset == "stock" or inst.endswith("SWAP")
        res = backtest.run(c, f, venue, cost_mult=1.0, rs=rs, can_short=can_short)
        filler = backtest.filler_for(venue, inst, f.asset_type, 1.0, 0.0)
        key = (dv, ds)
        if key not in HOURLY:
            base = frame(dv, ds, "5m") or f
            HOURLY[key] = SB.hourly_from(base)
        bkey = bot["strategy_id"] + ("@low" if venue == "okx" else "")
        cands = SB.candidates_for(res, f, bkey, bot["bot_id"], inst, venue, family, filler, VolGate(), HOURLY[key])
        span = f.t[-1] - f.t[0]
        cutoff = f.t[0] + int(span * 0.6) + DAY                       # after the training segment + embargo
        return {"bot": bot["bot_id"], "cands": [x.to_dict() for x in cands if x.t_in >= cutoff],
                "all_trades": len(cands), "cutoff": cutoff, "end": f.t[-1]}
    except Exception as e:
        return {"bot": bot["bot_id"], "error": f"{type(e).__name__}: {e}"}


def stats(xs):
    xs = sorted(x for x in xs if x is not None)
    if not xs:
        return None
    n = len(xs)
    mu = sum(xs) / n
    sd = math.sqrt(sum((x - mu) ** 2 for x in xs) / (n - 1)) if n > 1 else 0.0
    q = lambda p: xs[min(n - 1, int(p * n))]  # noqa: E731
    return {"n": n, "mean": mu, "sd": sd, "p05": q(0.05), "median": q(0.5), "p95": q(0.95),
            "share_positive": sum(1 for x in xs if x > 0) / n}


def paired(a, b, rng):
    d = [x - y for x, y in zip(a, b)]
    n = len(d)
    mu = sum(d) / n
    boots = sorted(sum(d[rng.randrange(n)] for _ in range(n)) / n for _ in range(2000))
    return {"mean_diff": mu, "ci95": [boots[50], boots[1949]], "share_better": sum(1 for x in d if x > 0) / n}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", required=True)
    ap.add_argument("--runs", type=int, default=1000)
    ap.add_argument("--window-days", type=int, default=10)
    ap.add_argument("--bots-per-run", type=int, default=60)
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()
    t0 = time.time()
    init(a.cache)
    with open(os.path.join(ROOT, "bots", "registry.json")) as fh:
        bots = json.load(fh)["bots"]
    with open(os.path.join(STRAT, "catalog.json")) as fh:
        cat = {s["id"]: s for s in json.load(fh)["strategies"]}
    jobs = [(b, cat[b["strategy_id"]]["definition"], cat[b["strategy_id"]]["family"]) for b in bots
            if cat.get(b["strategy_id"], {}).get("definition") and not (set(cat[b["strategy_id"]]["data"]) & {"trades", "book"})]
    print(f"{len(jobs)} bots to backtest for candidates", flush=True)
    with Pool(a.workers, initializer=init, initargs=(a.cache,)) as pool:
        res = pool.map(work, jobs, chunksize=2)
    errors = [r for r in res if r.get("error")]
    cands = [SB.Candidate(**c) for r in res if not r.get("error") for c in r["cands"]]
    usable = sorted({c.bot for c in cands})
    print(f"candidates: {len(cands)} from {len(usable)} bots ({len(errors)} bots without data); "
          f"{(time.time() - t0) / 60:.1f} min", flush=True)
    t_start = min(r["cutoff"] for r in res if not r.get("error"))
    t_end = max(r["end"] for r in res if not r.get("error"))
    families = {sid: s["family"] for sid, s in cat.items()}
    ev = os.path.join(STRAT, "results", "evaluation_summary.json")
    priors = ev if os.path.exists(ev) else ev + ".gz"
    runs = SB.sample_runs(cands, usable, t_start, t_end, a.runs, a.window_days, a.bots_per_run, priors, families)
    rng = random.Random(7)
    arms = ("none", "gates", "brain")
    agg = {arm: {k: stats([r[arm][k] for r in runs]) for k in ("return", "max_dd", "trades", "win_rate", "avg_r", "sharpe_daily")}
           for arm in arms}
    cmp_ = {"brain_vs_none": paired([r["brain"]["return"] for r in runs], [r["none"]["return"] for r in runs], rng),
            "gates_vs_none": paired([r["gates"]["return"] for r in runs], [r["none"]["return"] for r in runs], rng),
            "brain_vs_gates": paired([r["brain"]["return"] for r in runs], [r["gates"]["return"] for r in runs], rng),
            "brain_vs_none_drawdown": paired([r["none"]["max_dd"] for r in runs], [r["brain"]["max_dd"] for r in runs], rng)}
    veto = {}
    for r in runs:
        for k, v in r["brain"]["vetoes"].items():
            veto[k] = veto.get(k, 0) + v
    shadow = {}
    for r in runs:
        for k, v in (r["brain"].get("brain", {}).get("shadow_by_kind") or {}).items():
            s = shadow.setdefault(k, [0, 0.0])
            if v["trades"]:
                s[0] += v["trades"]
                s[1] += v["avg_r"] * v["trades"]
    out = {"generated": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()), "runs": len(runs), "simulations": 3 * len(runs),
           "window_days": a.window_days, "bots_per_run": a.bots_per_run, "bots_with_candidates": len(usable),
           "candidates": len(cands), "period": [time.strftime("%Y-%m-%d", time.gmtime(t_start / 1000)),
                                                time.strftime("%Y-%m-%d", time.gmtime(t_end / 1000))],
           "arms": agg, "paired": cmp_, "vetoes_total": veto,
           "vetoed_trades_avg_r": {k: {"trades": v[0], "avg_r": v[1] / v[0] if v[0] else None} for k, v in shadow.items()},
           "errors": [{"bot": e["bot"], "error": e["error"]} for e in errors], "minutes": round((time.time() - t0) / 60, 1),
           "per_run": runs}
    os.makedirs(os.path.join(ROOT, "results"), exist_ok=True)
    with open(os.path.join(ROOT, "results", "system_backtest.json"), "w") as fh:
        json.dump(out, fh, default=str)
    write_report(out)
    print(json.dumps({k: out[k] for k in ("runs", "simulations", "candidates", "minutes")}, indent=1))


def pct(x, d=2):
    return "-" if x is None else f"{100 * x:+.{d}f}%"


def write_report(o):
    A = o["arms"]
    L = ["# Full-system backtest\n", f"Generated {o['generated']} by `tools/system_backtest.py`. **{o['runs']:,} runs x 3 arms = "
         f"{o['simulations']:,} simulations** of the whole fleet: each run replays {o['bots_per_run']} randomly chosen bots over a "
         f"random {o['window_days']}-day window between {o['period'][0]} and {o['period'][1]} ({o['candidates']:,} candidate trades from "
         f"{o['bots_with_candidates']} bots), with per-venue fees and slippage, account sizing (0.5% of a 1/20 slot per trade), at most "
         "40 open positions and a 3% daily loss halt. The brain's starting knowledge comes only from the training segment that precedes "
         "these windows.\n",
         "| Arm | What runs | Mean return per window | Median | 5th-95th percentile | Windows positive | Mean max drawdown | Trades per window | Win rate | Avg R |",
         "|---|---|---|---|---|---|---|---|---|---|"]
    what = {"none": "every signal, full size", "gates": "cost + volatility gates", "brain": "gates + learned brain"}
    for arm in ("none", "gates", "brain"):
        r = A[arm]
        L.append(f"| {arm} | {what[arm]} | {pct(r['return']['mean'], 3)} | {pct(r['return']['median'], 3)} | "
                 f"{pct(r['return']['p05'], 2)} to {pct(r['return']['p95'], 2)} | {100 * r['return']['share_positive']:.0f}% | "
                 f"{100 * r['max_dd']['mean']:.2f}% | {r['trades']['mean']:.0f} | "
                 + (f"{100 * r['win_rate']['mean']:.1f}%" if r['win_rate'] else "-") + " | "
                 + (f"{r['avg_r']['mean']:+.3f}" if r['avg_r'] else "-") + " |")
    P = o["paired"]
    L.append("\n## Does the brain help? (paired: same window, same bots)\n")
    L.append("| Comparison | Mean difference in return | 95% bootstrap interval | Windows where the first is better |")
    L.append("|---|---|---|---|")
    for k, name in (("gates_vs_none", "gates vs none"), ("brain_vs_none", "brain vs none"), ("brain_vs_gates", "brain vs gates only")):
        p = P[k]
        L.append(f"| {name} | {pct(p['mean_diff'], 3)} | {pct(p['ci95'][0], 3)} to {pct(p['ci95'][1], 3)} | {100 * p['share_better']:.0f}% |")
    p = P["brain_vs_none_drawdown"]
    L.append(f"| drawdown: none minus brain | {pct(p['mean_diff'], 3)} | {pct(p['ci95'][0], 3)} to {pct(p['ci95'][1], 3)} | "
             f"{100 * p['share_better']:.0f}% (brain shallower) |")
    L.append("\n## What the blocked trades would have made\n\n| Veto reason | Blocked trades | Their average result |\n|---|---|---|")
    for k, v in o["vetoed_trades_avg_r"].items():
        L.append(f"| {k} | {v['trades']:,} | " + (f"{v['avg_r']:+.3f}R" if v["avg_r"] is not None else "-") + " |")
    L.append("\nA negative average means the vetoes avoided losing trades.\n")
    L.append("## Limits\n\n- Candidate trades come from each bot's own unfiltered backtest: when a trade is vetoed, the bot does not get "
             "the other entries it might have taken while flat.\n- Kraken and OKX bots use Coinbase price history with their own "
             "venue's fees.\n- Consensus between bots is not modelled here (it is live).\n- Paper simulation: fills are modelled, not "
             "real; stock fills have no order book.\n- The windows cover a few weeks of recent history; a different market period can "
             "give a different answer.\n")
    if o["errors"]:
        L.append(f"- {len(o['errors'])} bots had no historical data here and were left out.\n")
    with open(os.path.join(ROOT, "docs", "SYSTEM_BACKTEST.md"), "w") as fh:
        fh.write("\n".join(L))
    print("\n".join(L))


if __name__ == "__main__":
    main()
