"""Batch evaluation of every implemented strategy (writes strategies/results/).

    python strategies/src/run_evaluation.py [--cache DIR] [--workers 3]

Data (free sources, downloaded once and cached): Coinbase 5-minute bars for BTC-USD, ETH-USD,
SOL-USD (120 days), 1-minute BTC-USD (14 days), ETH-BTC and USDT-USD (60 days), OKX BTC-USDT and
BTC-USDT-SWAP 5-minute (30 days); Yahoo 5-minute bars (60 days) for SPY, QQQ, NVDA, AAPL, TSLA,
IWM and ^VIX, plus their 1-hour and daily bars. Crypto 15m/1h/4h/1d bars are aggregated from 5m.
"""

import argparse
import json
import math
import os
import pickle
import sys
import time
from multiprocessing import Pool

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
MAB = os.path.join(os.path.dirname(ROOT), "market_analysis_bots")
sys.path.insert(0, MAB)

from mab import evaluate as EV, metrics as M  # noqa: E402
from mab.clock import tf_ms  # noqa: E402
from mab.frame import Frame  # noqa: E402
from mab.models import Bar  # noqa: E402

CRYPTO_SYMS = ["BTC-USD", "ETH-USD", "SOL-USD"]
MEME_SYMS = ["DOGE-USD", "SHIB-USD", "PEPE-USD", "BONK-USD", "WIF-USD", "FLOKI-USD"]
STOCK_SYMS = ["SPY", "QQQ", "NVDA", "AAPL", "TSLA"]
PINNED = {"crypto_pair_ratio_reversion": [("coinbase", "ETH-BTC")], "stablecoin_peg_reversion": [("coinbase", "USDT-USD")],
          "perp_basis_reversion": [("okx", "BTC-USDT-SWAP")], "perp_volume_lead": [("okx", "BTC-USDT")],
          "coinbase_premium": [("coinbase", "BTC-USD")], "mtf_momentum_alignment": [("okx", "BTC-USDT")],
          "lead_lag_catch_up": [("coinbase", "ETH-USD"), ("coinbase", "SOL-USD")]}
# cost scenarios: (label, venue used for fees, multiplier)
CRYPTO_COSTS = [("gross", "okx", 0.0), ("low_fee_venue", "okx", 1.0), ("retail_kraken", "kraken", 1.0)]
STOCK_COSTS = [("gross", "yahoo", 0.0), ("base", "yahoo", 1.0), ("stress_2x", "yahoo", 2.0)]


# ------------------------------------------------------------------ data
def download(cache, refresh_crypto=False):
    """Fetch every dataset that is not in the cache yet (so a new instrument does not re-download the rest).
    refresh_crypto re-fetches all Coinbase 5-minute series so that cross-instrument rules see aligned history."""
    from mab.data.adapters import Coinbase, OKX, Yahoo
    from mab.net import Http
    os.makedirs(cache, exist_ok=True)
    path = os.path.join(cache, "eval_data.pkl")
    data = {}
    if os.path.exists(path):
        with open(path, "rb") as fh:
            data = pickle.load(fh)
        if refresh_crypto:
            for k in [k for k in data if k[0] == "coinbase" and k[2] == "5m"]:
                del data[k]
        if all(("coinbase", s, "5m") in data for s in CRYPTO_SYMS + MEME_SYMS):
            return data
    http = Http(limits={"api.exchange.coinbase.com": (2.0, 3), "query1.finance.yahoo.com": (1.0, 2), "www.okx.com": (3.0, 5)})
    cb, okx, yh = Coinbase(http), OKX(http), Yahoo(http)

    def page(ad, sym, tf, days, step_back):
        need = int(days * 86_400_000 / tf_ms(tf))
        out, end = {}, None
        while len(out) < need:
            try:
                batch = ad.bars(sym, tf, limit=300, end_ms=end)
            except Exception as e:
                print("download error", sym, tf, e)
                break
            if not batch:
                break
            for b in batch:
                out[b.event_time] = b
            oldest = min(b.event_time for b in batch)
            if end is not None and oldest >= end:
                break
            end = oldest if step_back == "okx" else oldest - 1
        return [out[k] for k in sorted(out)]

    def need(k):
        return k not in data or not data[k]
    for s in CRYPTO_SYMS + MEME_SYMS:
        if need(("coinbase", s, "5m")):
            data[("coinbase", s, "5m")] = page(cb, s, "5m", 120, "cb")
            print("coinbase", s, len(data[("coinbase", s, "5m")]), flush=True)
    if need(("coinbase", "BTC-USD", "1m")):
        data[("coinbase", "BTC-USD", "1m")] = page(cb, "BTC-USD", "1m", 14, "cb")
    for s in ("ETH-BTC", "USDT-USD"):
        if need(("coinbase", s, "5m")):
            data[("coinbase", s, "5m")] = page(cb, s, "5m", 60, "cb")
    for s in ("BTC-USDT", "BTC-USDT-SWAP"):
        if need(("okx", s, "5m")):
            data[("okx", s, "5m")] = page(okx, s, "5m", 30, "okx")
            print("okx", s, len(data[("okx", s, "5m")]))
    for s in STOCK_SYMS + ["IWM", "^VIX"]:
        for tf in ("5m", "1h", "1d"):
            if need(("yahoo", s, tf)):
                try:
                    data[("yahoo", s, tf)] = yh.bars(s, tf, limit=10 ** 6)
                except Exception as e:
                    print("yahoo error", s, tf, e)
        print("yahoo", s, len(data.get(("yahoo", s, "5m"), [])))
    with open(path, "wb") as fh:
        pickle.dump(data, fh)
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
    now = max(out) if out else 0
    return [out[k] for k in sorted(out) if k + step <= now + step and k != now] if out else []


DATA = {}
FRAMES = {}


def frame(venue, sym, tf):
    key = (venue, sym, tf)
    if key in FRAMES:
        return FRAMES[key]
    bars = DATA.get(key)
    if bars is None and venue != "yahoo":
        base = DATA.get((venue, sym, "5m"))
        if base and tf_ms(tf) > tf_ms("5m"):
            bars = resample(base, tf)
    if bars is None and venue == "yahoo" and tf == "15m":
        base = DATA.get((venue, sym, "5m"))
        bars = None if not base else [b for b in resample_session(base)]
    if not bars:
        FRAMES[key] = None
        return None
    at = "stock" if venue == "yahoo" else "crypto"
    FRAMES[key] = Frame(venue, sym, tf, at, bars)
    return FRAMES[key]


def resample_session(bars):
    return resample(bars, "15m")


def resolver(venue, sym, tf):
    return frame(venue, sym, tf)


# ------------------------------------------------------------------ jobs
def jobs_for(strats):
    jobs = []
    for s in strats:
        d = s["definition"]
        targets = []
        if s["key"] in PINNED:
            targets = PINNED[s["key"]]
        else:
            if "crypto" in s["markets"]:
                insts = [x for x in (s.get("instruments") or []) if x in CRYPTO_SYMS + MEME_SYMS]
                targets += [("coinbase", x) for x in (insts or CRYPTO_SYMS)]
            if "stock" in s["markets"]:
                insts = [x for x in (s.get("instruments") or []) if x in STOCK_SYMS]
                targets += [("yahoo", x) for x in (insts or STOCK_SYMS)]
        if d["timeframe"] == "1m":
            targets = [t for t in targets if t == ("coinbase", "BTC-USD")] or [("coinbase", "BTC-USD")]
        for venue, sym in targets:
            jobs.append((s["id"], s["key"], d, venue, sym))
    return jobs


def init_worker(cache):
    global DATA
    with open(os.path.join(cache, "eval_data.pkl"), "rb") as fh:
        DATA.update(pickle.load(fh))


def work(job):
    sid, key, d, venue, sym = job
    tf = d["timeframe"]
    f = frame(venue, sym, tf)
    if f is None or f.n < 500:
        return {"id": sid, "instrument": sym, "venue": venue, "error": f"no data for {venue}:{sym} {tf}"}
    from mab.runtime import load_events
    events = load_events({})
    params = {}
    dp = d.get("params") or {}
    if "step" in dp:
        params["step"] = {"BTC-USD": 1000, "ETH-USD": 100, "SOL-USD": 10}.get(sym, 5)
    at = "stock" if venue == "yahoo" else "crypto"
    costs = STOCK_COSTS if at == "stock" else CRYPTO_COSTS
    can_short = True if at == "stock" or sym.endswith("SWAP") else False
    out = {"id": sid, "key": key, "instrument": sym, "venue": venue, "tf": tf, "bars": f.n,
           "dataset": f"{venue}:{sym} {tf} {time.strftime('%Y-%m-%d', time.gmtime(f.t[0] / 1000))}.."
                      f"{time.strftime('%Y-%m-%d', time.gmtime(f.t[-1] / 1000))}", "runs": {}}
    t0 = time.time()
    try:
        from mab.strategy import compile_strategy, evaluate as eval_rules
        c = compile_strategy(d, params, at)
        pre = (c, eval_rules(c, f, resolver, events))
        for label, fee_venue, mult in costs:
            r = EV.run_one(d, f, fee_venue, mult, resolver, events, at, params, can_short=can_short, pre=pre)
            out["runs"][label] = r
    except Exception as e:
        out["error"] = f"{type(e).__name__}: {e}"
    out["seconds"] = round(time.time() - t0, 1)
    return out


# ------------------------------------------------------------------ analysis
def analyse(cat, results, n_workers, started):
    strategies = {s["id"]: s for s in cat["strategies"]}
    tests = {}
    rows = []
    for res in results:
        if res.get("error") or not res.get("runs"):
            continue
        for label, r in res["runs"].items():
            if label == "gross":
                continue
            rs_trval = r["segments"]["train"]["r"] + r["segments"]["validation"]["r"]
            t, p = EV.t_p(rs_trval)
            k = f"{res['id']}|{res['instrument']}|{label}"
            tests[k] = p
            rows.append((k, res, label, r, t, p))
    holm = M.holm(tests, 0.05)
    # candidates: net expectancy > 0 on train AND validation, at least 30 trades, at the realistic cost level
    real = {"retail_kraken", "base"}
    cands = []
    for k, res, label, r, t, p in rows:
        tr, va = r["segments"]["train"]["metrics"], r["segments"]["validation"]["metrics"]
        if label in real and (tr["trades"] or 0) + (va["trades"] or 0) >= 30 and (tr["expectancy_r"] or -1) > 0 \
                and (va["expectancy_r"] or -1) > 0:
            cands.append((k, res, label, r))
    # deflated Sharpe for the best train+validation Sharpe among all realistic-cost runs
    sharpes = []
    for k, res, label, r, t, p in rows:
        if label in real:
            m = r["segments"]["validation"]["metrics"]
            if m.get("sharpe") is not None:
                sharpes.append(m["sharpe"])
    per = {}
    for k, res, label, r, t, p in rows:
        per.setdefault(res["id"], []).append({
            "instrument": res["instrument"], "venue": res["venue"], "tf": res["tf"], "dataset": res["dataset"], "cost": label,
            "train": r["segments"]["train"]["metrics"], "validation": r["segments"]["validation"]["metrics"],
            "test": r["segments"]["test"]["metrics"], "full": r["full"]["metrics"], "gross_full":
                res["runs"].get("gross", {}).get("full", {}).get("metrics"),
            "folds_positive": sum(1 for fo in r["folds"] if (fo["net_return"] or 0) > 0), "folds": len(r["folds"]),
            "t_trainval": t, "p_trainval": p, "holm": holm.get(k), "candidate": any(c[0] == k for c in cands)})
    summary = {}
    for sid, lst in per.items():
        s = strategies[sid]
        cand = [x for x in lst if x["candidate"]]
        status = "out-of-sample tested" if cand else "backtested"
        results_rows = []
        for x in lst:
            for seg in ("train", "validation", "test"):
                results_rows.append({"period": seg, "instrument": x["instrument"], "tf": x["tf"], "dataset": x["dataset"],
                                     "cost_mult": x["cost"], "metrics": x[seg], "p_value": x["p_trainval"] if seg != "test" else None,
                                     "note": ("candidate: test segment unseen during selection" if x["candidate"] and seg == "test" else "")})
        real_rows = [x for x in lst if x["cost"] in real]
        best = max(real_rows, key=lambda x: (x["full"]["expectancy_r"] or -9)) if real_rows else None
        summary[sid] = {"status": status, "name": s["name"], "runs": lst, "results": results_rows,
                        "best_realistic": None if not best else {"instrument": best["instrument"], "expectancy_r": best["full"]["expectancy_r"],
                                                                 "trades": best["full"]["trades"], "net_return": best["full"]["net_return"],
                                                                 "test_expectancy_r": best["test"]["expectancy_r"],
                                                                 "gross_expectancy_r": (best["gross_full"] or {}).get("expectancy_r")},
                        "candidates": [{"instrument": x["instrument"], "cost": x["cost"], "test": x["test"]} for x in cand]}
    n_trials = len(tests)
    ranking = []
    for sid, sm in summary.items():
        for x in sm["runs"]:
            if x["cost"] in real and x["full"]["trades"]:
                ranking.append({"id": sid, "name": sm["name"], "instrument": x["instrument"], "cost": x["cost"],
                                "trades": x["full"]["trades"], "expectancy_r": x["full"]["expectancy_r"],
                                "win_rate": x["full"]["win_rate"], "net_return": x["full"]["net_return"],
                                "sharpe": x["full"]["sharpe"], "max_dd": x["full"]["max_drawdown"],
                                "gross_expectancy_r": (x["gross_full"] or {}).get("expectancy_r"),
                                "folds_positive": f"{x['folds_positive']}/{x['folds']}",
                                "test_expectancy_r": x["test"]["expectancy_r"], "test_trades": x["test"]["trades"],
                                "holm_significant": bool((x["holm"] or {}).get("significant")), "candidate": x["candidate"]})
    ranking.sort(key=lambda r: (r["candidate"], r["expectancy_r"] or -9), reverse=True)
    dsr = None
    if sharpes:
        best_sr = max(sharpes) / math.sqrt(252)
        var = (sum((s / math.sqrt(252)) ** 2 for s in sharpes) / len(sharpes)) - (sum(s / math.sqrt(252) for s in sharpes) / len(sharpes)) ** 2
        dsr = M.deflated_sharpe(best_sr, 40, len(sharpes), max(var, 1e-12))
    return {"generated": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()), "code_version": EV.code_version(),
            "runtime_minutes": round((time.time() - started) / 60, 1), "workers": n_workers,
            "hypothesis_tests": n_trials, "holm_significant": sum(1 for v in holm.values() if v["significant"]),
            "candidates": len(cands), "deflated_sharpe_best_validation": dsr, "strategies": summary, "ranking": ranking}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", default=os.environ.get("MAB_EVAL_CACHE", os.path.join(ROOT, ".cache")))
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--only", default=None)
    ap.add_argument("--refresh-crypto", action="store_true")
    ap.add_argument("--download-only", action="store_true")
    a = ap.parse_args()
    started = time.time()
    download(a.cache, a.refresh_crypto)
    if a.download_only:
        return
    with open(os.path.join(ROOT, "catalog.json")) as fh:
        cat = json.load(fh)
    strats = [s for s in cat["strategies"] if s["implementation_status"] == "implemented"
              and not (set(s["data"]) & {"trades", "book"})]
    if a.only:
        strats = [s for s in strats if s["key"] in a.only.split(",")]
    jobs = jobs_for(strats)
    print(f"{len(jobs)} jobs for {len(strats)} strategies")
    with Pool(a.workers, initializer=init_worker, initargs=(a.cache,)) as pool:
        results = []
        for i, r in enumerate(pool.imap_unordered(work, jobs, chunksize=1), 1):
            results.append(r)
            if i % 20 == 0:
                print(f"{i}/{len(jobs)} done ({(time.time() - started) / 60:.1f} min)", flush=True)
    os.makedirs(os.path.join(ROOT, "results"), exist_ok=True)
    errors = [r for r in results if r.get("error")]
    summary = analyse(cat, results, a.workers, started)
    summary["errors"] = [{"id": r["id"], "instrument": r["instrument"], "error": r["error"]} for r in errors]
    summary["not_evaluated"] = [{"id": s["id"], "reason": "needs recorded order-flow data (live only)"}
                                for s in cat["strategies"] if s["implementation_status"] == "implemented"
                                and set(s["data"]) & {"trades", "book"}]
    exp = {"experiment_id": EV.experiment_id({"code": summary["code_version"], "jobs": len(jobs), "t": summary["generated"]}),
           "protocol": "fixed parameters; chronological 60/20/20 with 1-day embargo; 4 walk-forward folds; 3 cost levels; Holm across all runs",
           "code_version": summary["code_version"], "generated": summary["generated"], "jobs": len(jobs), "seed": None}
    summary["experiment"] = exp
    with open(os.path.join(ROOT, "results", "evaluation_summary.json"), "w") as fh:
        json.dump(summary, fh, default=str)
    with open(os.path.join(ROOT, "results", "experiments.jsonl"), "a") as fh:
        fh.write(json.dumps(exp) + "\n")
    print(json.dumps({k: summary[k] for k in ("hypothesis_tests", "holm_significant", "candidates", "deflated_sharpe_best_validation",
                                              "runtime_minutes")}, indent=1), f"errors: {len(errors)}")


if __name__ == "__main__":
    main()
