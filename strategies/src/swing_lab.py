"""Swing lab: which longer-hold setups survive real costs? (writes results/SWING_LAB.md and swing_lab.json.gz)

    python strategies/src/swing_lab.py --hourly PATH/hourly.pkl [--workers 4]

Why this exists. The main evaluation used 60-120 days of 1-5 minute data, where a strategy's stop is
so tight that fees cost more than the whole setup is worth ("cost in R"). This lab asks the question
the cost arithmetic points to: with wider, volatility-sized stops, longer holds and cheaper order
types, is there anything left after costs? It uses 5.5 years of hourly crypto and 3 years of hourly
stocks, the same untouched test period as the volatility gate, and a selection protocol fixed before
the test period is looked at (PREREGISTRATION below).

Setups (all long only, decided at an hourly close, entered after it):
  breakout      close above the prior 24-hour high, in an uptrend (close > EMA 200)
  rsi2_dip      RSI(2) below 10 in an uptrend (buy the dip)
  pullback      EMA 21 > 50 > 200; the bar dips to EMA 21 and closes back above it, up on the bar
  retest       a 48-hour-high breakout in the last 12 hours, pulled back to that level, held it
  squeeze       Bollinger width in its lowest 10% of 90 days, then a close above the upper band
  momentum      once a day: 30-day return positive and close above the 50-day average
  orb           opening-range breakout: first hourly close above the day's first bar high (before hour 8)
  every_bar     benchmark: enter whenever flat (tells whether a setup beats just being long)

Exit structures: stop k x ATR(14) (k in 1.5, 2, 3, 4), target 1.5R / 2R / 3R, time limit 24 or 96 hours.
Entry: taker (next bar open) or maker (limit 0.1% below the signal close, valid 3 bars; unfilled = no trade).
Exits: stop and time exits pay taker fee + slippage; target exits are resting limits (maker fee).
Stop and target in the same bar: the stop is assumed first. Gaps through the stop fill at the open.

PREREGISTRATION (fixed before any test-period number was computed)
  For each fee scenario, market group and setup:
  1. On TRAIN (before the volatility gate's validation start) pick the exit structure and entry type
     with the highest t-statistic of net R per trade among those with at least 60 trades.
  2. It is a candidate only if its mean net R is positive on VALIDATION too.
  3. Candidates are measured once on TEST (the volatility gate's untouched period). Significance:
     one-sided t-test, Holm-corrected across every setup x group tested in that fee scenario.
  A setup is called a survivor only if it is positive on TEST after costs; "significant" only if it
  also passes Holm.
"""

import argparse
import gzip
import json
import math
import os
import pickle
import sys
import time
from multiprocessing import Pool

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
MAB = os.path.join(os.path.dirname(ROOT), "market_analysis_bots")
sys.path.insert(0, MAB)

from mab import volgate as VG  # noqa: E402

GROUPS = {"majors": ["BTC-USD", "ETH-USD", "SOL-USD"],
          "memes": ["DOGE-USD", "SHIB-USD", "PEPE-USD", "BONK-USD", "WIF-USD", "FLOKI-USD"],
          "stocks": ["SPY", "QQQ", "NVDA", "AAPL", "TSLA", "IWM"]}
SETUPS = ["breakout", "rsi2_dip", "pullback", "retest", "squeeze", "momentum", "orb", "every_bar"]
STOPS, TARGETS, HOLDS, ENTRIES = (1.5, 2.0, 3.0, 4.0), (1.5, 2.0, 3.0), (24, 96), ("taker", "maker")
MAKER_OFFSET, MAKER_TTL = 0.001, 3
# one-side fees (taker, maker) and taker slippage per side, by scenario and group
FEES = {"coinbase_retail": (0.012, 0.006), "kraken_retail": (0.008, 0.004), "ndax": (0.002, 0.002), "low_fee": (0.001, 0.0008)}
CRYPTO_SCENARIOS = ["coinbase_retail", "kraken_retail", "ndax", "low_fee"]
STOCK_SCENARIO = "stock_commission_free"
SLIP = {"majors": 0.0002, "memes": 0.0010, "stocks": 0.0002}
MIN_TRAIN_TRADES = 60


# ------------------------------------------------------------------ indicators (causal)
def ema(x, n):
    out = np.empty_like(x)
    a = 2.0 / (n + 1)
    out[0] = x[0]
    for i in range(1, len(x)):
        out[i] = a * x[i] + (1 - a) * out[i - 1]
    out[:n] = np.nan
    return out


def rsi(c, n):
    d = np.diff(c, prepend=c[0])
    up, dn = np.clip(d, 0, None), np.clip(-d, 0, None)
    au, ad = np.empty_like(c), np.empty_like(c)
    au[0], ad[0] = up[0], dn[0]
    for i in range(1, len(c)):
        au[i] = (au[i - 1] * (n - 1) + up[i]) / n
        ad[i] = (ad[i - 1] * (n - 1) + dn[i]) / n
    r = 100 - 100 / (1 + au / np.where(ad == 0, 1e-12, ad))
    r[:n + 5] = np.nan
    return r


def atr(h, l, c, n=14):
    pc = np.r_[c[0], c[:-1]]
    tr = np.maximum(h - l, np.maximum(abs(h - pc), abs(l - pc)))
    out = np.empty_like(c)
    out[0] = tr[0]
    for i in range(1, len(c)):
        out[i] = (out[i - 1] * (n - 1) + tr[i]) / n
    out[:n] = np.nan
    return out


def prior_max(x, n):
    """max of the n bars BEFORE each bar."""
    out = np.full_like(x, np.nan)
    if len(x) > n:
        w = np.lib.stride_tricks.sliding_window_view(x, n)[:-1]
        out[n:] = w.max(axis=1)
    return out


def rolling_pct_rank_low(x, n, q, every=24):
    """True where x[i-1] is within the lowest q of the n values before it (causal; the threshold is
    recomputed every `every` bars from the n bars before that point)."""
    out = np.zeros(len(x), dtype=bool)
    thr = np.inf
    for i in range(n + 1, len(x)):
        if (i - n - 1) % every == 0:
            w = x[i - 1 - n:i - 1]
            w = w[np.isfinite(w)]
            thr = np.quantile(w, q) if len(w) else np.inf
        out[i] = x[i - 1] <= thr
    return out


# ------------------------------------------------------------------ data
def arrays(bars):
    t = np.array([b.event_time for b in bars], dtype=np.int64)
    o, h, l, c = (np.array([getattr(b, k) for b in bars], dtype=float) for k in ("open", "high", "low", "close"))
    v = np.array([b.volume for b in bars], dtype=float)
    return t, o, h, l, c, v


def gate_states(bars, asset):
    """LOUD / NORMAL / QUIET / UNKNOWN at every bar from the shipped volatility gate (causal)."""
    t, o, h, l, c, v = arrays(bars)
    b = VG.Bars(list(t), list(o), list(h), list(l), list(c), list(v), VG.HORIZON[asset])
    g = VG.VolGate()
    code = {"LOUD": 2, "NORMAL": 1, "QUIET": 0, "UNKNOWN": -1}
    return np.array([code[g.read(b, i, asset)["state"]] for i in range(len(bars))], dtype=np.int8)


def signals(t, o, h, l, c, stock):
    e21, e50, e200 = ema(c, 21), ema(c, 50), ema(c, 200)
    up = c > e200
    r2 = rsi(c, 2)
    hh24, hh48 = prior_max(h, 24), prior_max(h, 48)
    sma20 = np.convolve(c, np.ones(20) / 20, mode="full")[:len(c)]
    sd20 = np.array([c[max(0, i - 19):i + 1].std() for i in range(len(c))])
    bbw = np.where(sma20 > 0, 4 * sd20 / sma20, np.nan)
    bbw[:20] = np.nan
    s = {}
    s["breakout"] = (c > hh24) & up
    s["rsi2_dip"] = (r2 < 10) & up
    s["pullback"] = (e21 > e50) & (e50 > e200) & (l <= e21) & (c > e21) & (c > o)
    bo = c > hh48
    level = np.full(len(c), np.nan)
    last, age = np.nan, 99
    for i in range(len(c)):
        if bo[i]:
            last, age = hh48[i], 0
        else:
            age += 1
        level[i] = last if 1 <= age <= 12 else np.nan
    s["retest"] = (l <= level * 1.002) & (c > level) & up
    s["squeeze"] = rolling_pct_rank_low(np.nan_to_num(bbw, nan=np.inf), 90 * (7 if stock else 24), 0.10) & (c > sma20 + 2 * sd20)
    day = t // 86_400_000
    new_day = np.r_[True, day[1:] != day[:-1]]
    last_of_day = np.r_[day[1:] != day[:-1], True]
    n30, n50 = (30 * 7, 50 * 7) if stock else (30 * 24, 50 * 24)
    ret30 = np.full(len(c), np.nan)
    ret30[n30:] = c[n30:] / c[:-n30] - 1
    s["momentum"] = last_of_day & (ret30 > 0) & (c > np.convolve(c, np.ones(n50) / n50, mode="full")[:len(c)])
    s["momentum"][:n50] = False
    orb = np.zeros(len(c), dtype=bool)
    or_high, taken, k = np.nan, False, 0
    for i in range(len(c)):
        if new_day[i]:
            or_high, taken, k = h[i], False, 0
            continue
        k += 1
        if not taken and k <= 8 and c[i] > or_high:
            orb[i], taken = True, True
    s["orb"] = orb
    s["every_bar"] = np.ones(len(c), dtype=bool)
    warm = 200
    for k2 in s:
        s[k2] = np.nan_to_num(s[k2], nan=0).astype(bool)
        s[k2][:warm] = False
    return s


# ------------------------------------------------------------------ simulation
def simulate(t, o, h, l, c, a, sig, k, R, H, entry):
    """Non-overlapping trades for one setup and structure. Returns arrays: t_entry, gross R, cost pieces."""
    n = len(c)
    idx = np.flatnonzero(sig[:n - H - MAKER_TTL - 2])
    if not len(idx):
        return None
    if entry == "taker":
        e = idx + 1
        px = o[e]
    else:
        lim = c[idx] * (1 - MAKER_OFFSET)
        e = np.full(len(idx), -1)
        px = np.full(len(idx), np.nan)
        for j in range(1, MAKER_TTL + 1):
            hit = (e < 0) & (l[idx + j] <= lim)
            e[hit] = idx[hit] + j
            px[hit] = np.minimum(lim[hit], o[idx[hit] + j])
        keep = e >= 0
        idx, e, px = idx[keep], e[keep], px[keep]
    dist = k * a[idx]
    ok = np.isfinite(dist) & (dist > 0) & np.isfinite(px)
    idx, e, px, dist = idx[ok], e[ok], px[ok], dist[ok]
    if not len(idx):
        return None
    stop, tgt = px - dist, px + R * dist
    W = np.arange(H)
    rows = e[:, None] + W[None, :]
    lw, hw, ow, cw = l[rows], h[rows], o[rows], c[rows]
    sh = lw <= stop[:, None]
    th = hw >= tgt[:, None]
    big = H + 1
    fs = np.where(sh.any(1), sh.argmax(1), big)
    ft = np.where(th.any(1), th.argmax(1), big)
    kind = np.where((fs <= ft) & (fs < big), 0, np.where(ft < big, 1, 2))          # 0 stop, 1 target, 2 time
    j = np.where(kind == 0, fs, np.where(kind == 1, ft, H - 1))
    r_ix = np.arange(len(e))
    xo = ow[r_ix, j]
    exit_px = np.where(kind == 0, np.minimum(stop, np.where(j > 0, xo, stop)), np.where(kind == 1, tgt, cw[r_ix, j]))
    exit_bar = e + j
    # one position at a time
    take = np.zeros(len(e), dtype=bool)
    free = -1
    for q in range(len(e)):
        if idx[q] > free:
            take[q] = True
            free = exit_bar[q]
    sel = take
    # compact: entry and exit as multiples of the stop distance (all the cost arithmetic needs)
    return {"t": t[idx[sel]], "gross_r": ((exit_px - px) / dist)[sel].astype(np.float32),
            "e_d": (px / dist)[sel].astype(np.float32), "x_d": (exit_px / dist)[sel].astype(np.float32),
            "kind": kind[sel].astype(np.int8), "sig_i": idx[sel]}


def net_r(tr, group, scenario, entry):
    """(net R per trade, cost in R per trade)."""
    if scenario == STOCK_SCENARIO:
        f_t, f_m = 0.0, 0.0
    else:
        f_t, f_m = FEES[scenario]
    slip = SLIP[group]
    f_in = (f_t + slip) if entry == "taker" else f_m
    f_out = np.where(tr["kind"] == 1, f_m, f_t + slip)
    cost_r = f_in * tr["e_d"] + f_out * tr["x_d"]
    if group == "stocks":
        cost_r = cost_r + 0.00003 * tr["x_d"]                  # US regulatory fees on sales, rounded up
    return (tr["gross_r"] - cost_r).astype(np.float64), cost_r.astype(np.float64)


def stats(x):
    n = len(x)
    if n == 0:
        return {"n": 0, "mean": None, "t": None, "p": None, "win": None, "pf": None}
    m = float(x.mean())
    sd = float(x.std(ddof=1)) if n > 1 else 0.0
    tt = m / (sd / math.sqrt(n)) if sd > 0 else 0.0
    p = 0.5 * math.erfc(tt / math.sqrt(2))                     # one-sided, normal approximation (n is large)
    gains, losses = x[x > 0].sum(), -x[x < 0].sum()
    return {"n": n, "mean": m, "t": tt, "p": p, "win": float((x > 0).mean()), "pf": float(gains / losses) if losses > 0 else None}


# ------------------------------------------------------------------ worker
DATA = {}


def init(path):
    with open(path, "rb") as fh:
        DATA.update(pickle.load(fh))


def prepare(job):
    group, sym, cache_dir = job
    key = ("stock" if group == "stocks" else "crypto", sym)
    bars = DATA.get(key)
    if not bars or len(bars) < 1500:
        return group, sym, None
    asset = "stock" if group == "stocks" else "crypto"
    gpath = os.path.join(cache_dir, f"gate_{sym}.npy")
    if os.path.exists(gpath):
        g = np.load(gpath)
    else:
        g = gate_states(bars, asset)
        np.save(gpath, g)
    t, o, h, l, c, v = arrays(bars)
    a = atr(h, l, c)
    sig = signals(t, o, h, l, c, group == "stocks")
    out = {}
    for s_name, s in sig.items():
        for k in STOPS:
            for R in TARGETS:
                for H in HOLDS:
                    for entry in ENTRIES:
                        tr = simulate(t, o, h, l, c, a, s, k, R, H, entry)
                        if tr is not None:
                            tr["gate"] = g[tr.pop("sig_i")]
                            out[(s_name, k, R, H, entry)] = tr
    return group, sym, out


# ------------------------------------------------------------------ protocol
def cut_times(hourly, asset, horizon):
    """The volatility gate's own validation and test start times (its rows pooled and sorted by time)."""
    T = []
    for (kind, sym), bars in hourly.items():
        if kind != asset:
            continue
        n = len(bars)
        t, o, h, l, c, v = arrays(bars)
        b = VG.Bars(list(t), list(o), list(h), list(l), list(c), list(v), horizon)
        ff = next((i for i in range(n) if VG.features(b, i) is not None), n)
        start = max(ff, 30 * 24 + horizon)            # as in train_volgate.dataset: features and 30 days of labels
        T.extend(int(x) for x in t[min(n, start):max(0, n - horizon)])
    T.sort()
    return T[int(len(T) * 0.6)], T[int(len(T) * 0.8)]


def pooled(res, group, cfg):
    parts = [res[(group, s)].get(cfg) for s in GROUPS[group] if res.get((group, s))]
    parts = [p for p in parts if p is not None]
    if not parts:
        return None
    return {k: np.concatenate([p[k] for p in parts]) for k in parts[0]}


def holm(ps):
    order = sorted(range(len(ps)), key=lambda i: ps[i])
    out, m, running = [False] * len(ps), len(ps), 0.0
    for rank, i in enumerate(order):
        adj = min(1.0, (m - rank) * ps[i])
        running = max(running, adj)
        out[i] = running < 0.05
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hourly", required=True)
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()
    t0 = time.time()
    cache_dir = os.path.join(os.path.dirname(os.path.abspath(a.hourly)), "swinglab_cache")
    os.makedirs(cache_dir, exist_ok=True)
    with open(a.hourly, "rb") as fh:
        hourly = pickle.load(fh)
    cuts = {"crypto": cut_times(hourly, "crypto", VG.HORIZON["crypto"]), "stock": cut_times(hourly, "stock", VG.HORIZON["stock"])}
    jobs = [(g, s, cache_dir) for g, syms in GROUPS.items() for s in syms]
    with Pool(a.workers, initializer=init, initargs=(a.hourly,)) as pool:
        done = pool.map(prepare, jobs)
    res = {(g, s): out for g, s, out in done if out is not None}
    print(f"simulated {len(res)} markets in {(time.time() - t0) / 60:.1f} min", flush=True)
    configs = [(s, k, R, H, e) for s in SETUPS for k in STOPS for R in TARGETS for H in HOLDS for e in ENTRIES]
    report = {"generated": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()), "cuts": {}, "scenarios": {}, "configs_per_setup": len(configs) // len(SETUPS)}
    for asset, (v0, t1) in cuts.items():
        report["cuts"][asset] = [time.strftime("%Y-%m-%d", time.gmtime(v0 / 1000)), time.strftime("%Y-%m-%d", time.gmtime(t1 / 1000))]
    scen_groups = [(sc, g) for sc in CRYPTO_SCENARIOS for g in ("majors", "memes")] + [(STOCK_SCENARIO, "stocks")]
    for scenario, group in scen_groups:
        v0, t1 = cuts["stock" if group == "stocks" else "crypto"]
        rows = []
        for setup in SETUPS:
            best, best_cfg, grid = None, None, []
            for cfg in configs:
                if cfg[0] != setup:
                    continue
                tr = pooled(res, group, cfg)
                if tr is None:
                    continue
                nr, cr = net_r(tr, group, scenario, cfg[4])
                m = tr["t"] < v0
                st = stats(nr[m])
                grid.append({"cfg": cfg[1:], "train": st, "gross_train": float(tr["gross_r"][m].mean()) if m.any() else None,
                             "cost_r": float(cr[m].mean()) if m.any() else None})
                if st["n"] >= MIN_TRAIN_TRADES and (best is None or st["t"] > best["t"]):
                    best, best_cfg = st, cfg
            row = {"setup": setup, "grid_train_top": sorted(grid, key=lambda x: -(x["train"]["t"] or -99))[:5]}
            if best_cfg is not None:
                tr = pooled(res, group, best_cfg)
                nr, cr = net_r(tr, group, scenario, best_cfg[4])
                val = (tr["t"] >= v0) & (tr["t"] < t1)
                test = tr["t"] >= t1
                gated = test & (tr["gate"] != 0)
                wts = np.where(tr["gate"] == 2, 0.6, 1.0)
                row.update({"config": {"stop_atr": best_cfg[1], "target_r": best_cfg[2], "hold_h": best_cfg[3], "entry": best_cfg[4]},
                            "train": best, "validation": stats(nr[val]), "test": stats(nr[test]),
                            "test_gross": stats(tr["gross_r"][test]), "test_cost_r": float(cr[test].mean()) if test.any() else None,
                            "test_gated": stats(nr[gated]),
                            "test_gated_weighted_mean": float((nr[gated] * wts[gated]).sum() / wts[gated].sum()) if gated.any() else None,
                            "test_by_market": {s: stats(net_r(p, group, scenario, best_cfg[4])[0][p["t"] >= t1])
                                               for s in GROUPS[group] if (p := (res.get((group, s)) or {}).get(best_cfg)) is not None}})
                row["candidate"] = bool((row["validation"]["mean"] or -1) > 0)
            rows.append(row)
        tested = [r for r in rows if r.get("candidate") and r["test"]["n"] > 0]
        flags = holm([r["test"]["p"] for r in tested]) if tested else []
        for r, f in zip(tested, flags):
            r["holm_significant"] = bool(f)
        for r in rows:
            r["survivor"] = bool(r.get("candidate") and (r["test"]["mean"] or -1) > 0)
        report["scenarios"].setdefault(scenario, {})[group] = rows
        print(scenario, group, [(r["setup"], round(r["test"]["mean"], 3) if r.get("test") and r["test"]["mean"] is not None else None,
                                 r.get("survivor")) for r in rows], flush=True)
    report["minutes"] = round((time.time() - t0) / 60, 1)
    out = os.path.join(ROOT, "results", "swing_lab.json.gz")
    with gzip.open(out, "wt") as fh:
        json.dump(report, fh, default=lambda x: x.item() if hasattr(x, "item") else str(x))
    write_report(report)


def f(x, d=3):
    return "-" if x is None else f"{x:+.{d}f}"


def write_report(rep):
    L = ["# Swing lab: what survives real costs\n",
         f"Generated {rep['generated']} by `src/swing_lab.py`. Hourly data: 9 cryptos (Coinbase, up to 5.5 years) and 6 US "
         "stocks/ETFs (Yahoo, 3 years). Each setup was tried with "
         f"{rep['configs_per_setup']} exit structures and entry types; the protocol and its preregistration are in the "
         "script's docstring. Test period = the volatility gate's untouched test period "
         f"(crypto from {rep['cuts']['crypto'][1]}, stocks from {rep['cuts']['stock'][1]}); validation from "
         f"{rep['cuts']['crypto'][0]} / {rep['cuts']['stock'][0]}.\n",
         "R = profit or loss in units of the risk taken (entry to stop). Net = after fees and slippage.\n"]
    names = {"coinbase_retail": "Coinbase retail fees (0.60% maker / 1.20% taker)", "kraken_retail": "Kraken retail fees (0.40% / 0.80%)",
             "ndax": "NDAX-level fees (0.20% / 0.20%)", "low_fee": "Low-fee exchange (0.08% / 0.10%)",
             STOCK_SCENARIO: "Stocks, commission-free broker (spread and regulatory fees only)"}
    for sc, groups in rep["scenarios"].items():
        L.append(f"## {names.get(sc, sc)}\n")
        for g, rows in groups.items():
            L.append(f"### {g}\n\n| Setup | Chosen on train (stop, target, hold, entry) | Train R (n) | Validation R (n) | Test R (n) | Test gross R | "
                     "Test cost R | Test with vol gate | Holm | Survivor |\n|---|---|---|---|---|---|---|---|---|---|")
            for r in rows:
                if not r.get("config"):
                    L.append(f"| {r['setup']} | not enough trades | | | | | | | | |")
                    continue
                c = r["config"]
                L.append(f"| {r['setup']} | {c['stop_atr']}xATR, {c['target_r']}R, {c['hold_h']}h, {c['entry']} | "
                         f"{f(r['train']['mean'])} ({r['train']['n']}) | {f(r['validation']['mean'])} ({r['validation']['n']}) | "
                         f"**{f(r['test']['mean'])}** ({r['test']['n']}) | {f(r['test_gross']['mean'])} | {f(r['test_cost_r'])} | "
                         f"{f(r['test_gated_weighted_mean'])} ({r['test_gated']['n']}) | {'yes' if r.get('holm_significant') else 'no'} | "
                         f"{'**yes**' if r['survivor'] else 'no'} |")
            L.append("")
    with open(os.path.join(ROOT, "results", "SWING_LAB.md"), "w") as fh:
        fh.write("\n".join(L))
    print("\n".join(L))


if __name__ == "__main__":
    main()
