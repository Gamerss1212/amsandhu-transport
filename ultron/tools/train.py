#!/usr/bin/env python3
"""Train and backtest Ultron: 50 agents chosen from 532 candidates, one learned brain, walk-forward.

Data: Coinbase hourly candles, BTC ETH SOL (majors) and DOGE SHIB PEPE BONK WIF FLOKI (memes), Dec 2020 onward.

1. Candidates: every measured signal (133) x {majors, memes} x {1h, 4h candles} x {any time, big-move (LOUD) periods,
   uptrends, big moves in uptrends}, plus Jarvus's 1h playbooks.
   Each signal is traded with the same exits: limit 0.1% under the close (3 bars to fill), stop 4x ATR of its
   timeframe, one exit at 2R, 96 hours, NDAX fees + slippage. Every outcome is in R after costs.
2. Walk-forward: at the start of every quarter from 2022, the brain picks the 50 agents with the best
   lower-confidence-bound R using ONLY signals that had finished before that day, then trades the quarter,
   learning from every signal as it finishes. Nothing it trades was used to choose it.
3. Improvement loop: up to 100 one-change-at-a-time proposals to the brain's settings. A change is kept only if
   it improves the development period (2022 to 2025-03-19) AND does not hurt validation (2025-03-20 to 12-22).
   The test period (from 2025-12-23) is never used to choose anything.
4. Extreme tests on the final settings: fees x2, Kraken fees, slippage x3, 200 random 90-day windows,
   2,000 bootstrap reshuffles of the trades.
5. Exports the live model: the 50 agents chosen on all data up to today and everything the brain learned.

  python3 ultron/tools/train.py --data <dir with *_1h.csv> [--iters 100] [--workers 4]
"""

from __future__ import annotations

import argparse
import heapq
import json
import math
import os
import pickle
import random
import sys
import time
from datetime import datetime, timedelta, timezone
from multiprocessing import Pool

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
REPO = os.path.dirname(ROOT)
sys.path.insert(0, os.path.join(REPO, "jarvus", "scripts"))
sys.path.insert(0, os.path.join(ROOT, "core"))
import events as evmod  # noqa: E402
import signals as sg  # noqa: E402
import system_test as st  # noqa: E402
from brain import DEFAULT_PARAMS, Book, Brain  # noqa: E402
from snapshot import load_csv  # noqa: E402

HOUR = 3_600_000
DAY = 24 * HOUR
MAJORS, MEMES = st.MAJORS, st.MEMES


def ms(y, m, d):
    return int(datetime(y, m, d, tzinfo=timezone.utc).timestamp() * 1000)


WF_START, B_START, C_START = ms(2022, 1, 1), ms(2025, 3, 20), ms(2025, 12, 23)
# signals that the TradingView indicator reproduces exactly (pure OHLCV + standard ta.* functions)
TV_SIGNALS = {k for k, v in sg.DEFS.items() if v[2] == "candle"} | {
    "rsi_os_30", "rsi_up_30", "rsi_ob_70", "rsi_dn_70", "rsi2_10", "rsi2_connors", "macd_up", "macd_up_below0", "macd_zero_up",
    "macd_down", "macd_hist_turn", "ema_9_21_up", "ema_9_21_down", "golden_cross", "death_cross", "ema200_reclaim", "ema200_lose",
    "bb_below", "bb_reentry", "bb_above", "bb_squeeze_up", "keltner_up", "keltner_below", "ttm_squeeze", "stoch_up", "stoch_down",
    "stochrsi_up", "willr_up", "cci_up", "cci_break", "mfi_os", "mfi_ob", "adx_di_up", "holy_grail", "donchian20", "donchian55",
    "donchian20_down", "obv_lead", "obv_confirm", "vol_spike_bull", "vol_spike_bear", "vwap_reclaim", "vwap_lose", "ha_green",
    "ha_red", "rally_24h", "drop_24h", "five_green", "five_red", "stretch_ema20", "zscore_m2"}
NAMES = ["ORION", "VEGA", "NOVA", "ATLAS", "LYRA", "TITAN", "AEGIS", "HELIOS", "SIRIUS", "KEPLER", "POLARIS", "RIGEL",
         "CYGNUS", "DRACO", "PULSAR", "QUASAR", "ZENITH", "AURORA", "BOREAS", "CALYPSO", "CASSINI", "CEPHEUS", "ELARA",
         "EOS", "GAIA", "HALO", "HERMES", "HYDRA", "HYPERION", "ICARUS", "JUNO", "MIRA", "NYX", "OBERON", "PALLAS",
         "PHOEBE", "RHEA", "SELENE", "SPICA", "TALOS", "TETHYS", "THEIA", "TRITON", "VESTA", "ZEPHYR", "ARGUS", "ALTAIR",
         "DENEB", "ANTARES", "CASTOR", "POLLUX", "IOTA", "SIGMA", "OMEGA", "KAPPA"]


# ------------------------------------------------------------------ 1. candidate events
def mt_weekend(t_ms):
    dt = datetime.fromtimestamp(t_ms / 1000, timezone.utc)
    dt = dt - timedelta(hours=6 if evmod.us_dst(dt.date()) else 7)
    return dt.weekday() >= 5


def build_coin(job):
    data_dir, coin, btc_bull, gate_model, allowed = job
    p = st.prepare((data_dir, coin))
    d = load_csv(os.path.join(data_dir, f"{coin}_1h.csv"))
    n = len(p["c"])
    t = np.array(p["t"], dtype=np.int64)
    o, h, l, c = (np.array(p[k], float) for k in ("o", "h", "l", "c"))
    v = np.array(d["volume"][:n], float)
    group, kind = ("majors", "major") if coin in MAJORS else ("memes", "meme")
    gate = p["gate"]
    if gate_model is not None:                               # TradingView mode: the Pine-computable gate
        sys.path.insert(0, os.path.join(ROOT, "tv"))
        import pine_gate
        gate = list(pine_gate.states(t, o, h, l, c, v, gate_model))
    S1, _ = sg.all_signals(t, o, h, l, c, v, 24)
    s4, e4 = sg.bars4h_index(t)
    t4, o4, c4 = t[s4], o[s4], c[e4]
    h4 = np.array([h[a:b + 1].max() for a, b in zip(s4, e4)])
    l4 = np.array([l[a:b + 1].min() for a, b in zip(s4, e4)])
    v4 = np.array([v[a:b + 1].sum() for a, b in zip(s4, e4)])
    S4, A4 = sg.all_signals(t4, o4, h4, l4, c4, v4, 6)
    for sid, name in sg.PLAYBOOK.items():
        m = np.zeros(n, bool)
        m[[i for i in p["sig"].get(name, []) if i < n]] = True
        S1[sid] = m
    if allowed is not None:
        S1 = {k: v_ for k, v_ in S1.items() if k in allowed}
        S4 = {k: v_ for k, v_ in S4.items() if k in allowed}
    memo = {}

    def trade(i, stop_atr):
        key = (i, stop_atr)
        if key not in memo:
            memo[key] = st.trade_path(p, i, "x", st.FEES["ndax"], kind, entry="maker", stop_atr=stop_atr, rung=None,
                                      target_r=2.0, tp1_bars=0, horizon=96)
        return memo[key]

    out = []
    for tf, S, gap, j0 in (("1h", S1, 12, 210), ("4h", S4, 3, 60)):
        for sid, mask in S.items():
            if tf == "4h" and sid in sg.PLAYBOOK:
                continue
            cid = f"{sid}|{group}|{tf}"
            last = -10 ** 9
            for j in np.flatnonzero(mask):
                if j < j0 or j - last < gap:
                    continue
                i = int(j) if tf == "1h" else int(e4[j])
                if i >= n - 3 or not p["atr"][i]:
                    continue
                last = j
                stop_atr = 4.0 if tf == "1h" else round(4.0 * float(A4[j]) / p["atr"][i], 2)
                if not (0.5 <= stop_atr <= 40):
                    continue
                tr = trade(i, stop_atr)
                if tr is None:
                    continue
                t_dec = int(t[i]) + HOUR
                loud, up = gate[i] == "L", bool(p["up1"][i] and p["trend4"][i])
                base = (t_dec, None, coin, tr["t_exit"], float(tr["r"]), float(tr["rt_cost_r"]), float(tr["stop_pct"]),
                        gate[i], btc_bull.get(int(t[i])), up, mt_weekend(t_dec), float(c[i]))
                for var, ok in (("any", True), ("loud", loud), ("trend", up), ("loudtrend", loud and up)):
                    if ok:
                        out.append(base[:1] + (f"{cid}|{var}",) + base[2:])
    return coin, out


def build_events(data_dir, workers, cache, gate_model=None, allowed=None):
    if os.path.exists(cache):
        with open(cache, "rb") as fh:
            return pickle.load(fh)
    btc = st.prepare((data_dir, "BTC"))
    btc_bull = {int(tt): b for tt, b in zip(btc["t"], btc["bull"])}
    coins = [c for c in MAJORS + MEMES if os.path.exists(os.path.join(data_dir, f"{c}_1h.csv"))]
    with Pool(workers) as pool:
        got = pool.map(build_coin, [(data_dir, c, btc_bull, gate_model, allowed) for c in coins])
    events = sorted((e for _, evs in got for e in evs), key=lambda e: (e[0], e[1], e[2]))
    defs = {}
    for e in events:
        cid = e[1]
        if cid not in defs:
            sid, group, tf, var = cid.split("|")
            name, side, fam, rule = sg.DEFS[sid]
            defs[cid] = {"signal": sid, "group": group, "tf": tf, "variant": var, "family": fam, "label": name, "side": side,
                         "rule": rule}
    with open(cache, "wb") as fh:
        pickle.dump((events, defs, coins), fh)
    return events, defs, coins


# ------------------------------------------------------------------ 2. the walk-forward simulation
def quarters(t0, t1):
    out, d = [], datetime.fromtimestamp(t0 / 1000, timezone.utc)
    while True:
        q = int(d.timestamp() * 1000)
        if q > t1:
            return out
        out.append(q)
        d = d.replace(year=d.year + (d.month + 3 > 12), month=(d.month + 2) % 12 + 1)


def period(t):
    return "dev" if t < B_START else "B" if t < C_START else "C"


def ev_dict(e, defs):
    d = defs[e[1]]
    return {"agent": e[1], "fam": d["family"], "group": d["group"], "gate": e[7], "bull": e[8], "cost_r": e[5],
            "weekend": e[10], "coin": e[2]}


def simulate(events, defs, params, adj=None, record=False, t_end=None):
    """Replay every candidate signal in time order. Returns metrics (and the trades if record)."""
    brain = Brain(params)
    P = brain.p
    book = Book(P)
    q_list = quarters(WF_START, t_end or events[-1][0])
    qi, selected = 0, set()
    cstat = {}                                   # cid -> [n, s, s2] of completed signals (raw R after costs)
    chist = {}                                   # cid -> list of (t_exit, r) in completion order (windowed selection)
    since = {}                                   # agent -> when it was first chosen (evidence = "since_selected")
    win_ms = P["sel_window_days"] * DAY
    comp = []                                    # (t_exit, k)
    opn = []                                     # (t_exit, seq, coin, group, risk_amt, r, rec)
    eq, peak, mdd = 10_000.0, 10_000.0, 0.0
    trades, decisions, seq = [], {"taken": 0, "refused": 0}, 0
    sel_hist = []
    k, N = 0, len(events)
    r_of = (lambda e: e[4]) if adj is None else (lambda e: e[4] - adj(e))
    while k < N:
        t = events[k][0]
        batch = []
        while k < N and events[k][0] == t:
            batch.append(k)
            k += 1
        while comp and comp[0][0] <= t:
            _, j = heapq.heappop(comp)
            e = events[j]
            r = r_of(e)
            fresh = P["evidence"] == "all" or (e[1] in since and e[0] >= since[e[1]])
            brain.learn(ev_dict(e, defs), r, agent_level=fresh)
            if win_ms:
                chist.setdefault(e[1], []).append((e[3], r))
            s = cstat.get(e[1])
            if s is None:
                cstat[e[1]] = [1, r, r * r]
            else:
                s[0] += 1
                s[1] += r
                s[2] += r * r
        while opn and opn[0][0] <= t:
            te, _, coin, group, risk_amt, r, rec = heapq.heappop(opn)
            eq += risk_amt * r
            peak = max(peak, eq)
            mdd = max(mdd, 1 - eq / peak)
            book.closed(coin, r * rec["size"], (te - 6 * HOUR) // DAY)
            rec["eq_after"] = eq
        while qi < len(q_list) and t >= q_list[qi]:
            if win_ms:
                lo = q_list[qi] - win_ms
                stats = {}
                for c, hist in chist.items():
                    rs = [r for te, r in hist if te >= lo]
                    if len(rs) >= 2:
                        m_ = sum(rs) / len(rs)
                        stats[c] = (len(rs), m_, math.sqrt(max(1e-9, sum(x * x for x in rs) / len(rs) - m_ * m_)))
            else:
                stats = {c: (s[0], s[1] / s[0], math.sqrt(max(1e-9, s[2] / s[0] - (s[1] / s[0]) ** 2))) for c, s in cstat.items()}
            selected = set(brain.select(stats, defs))
            for c in selected:
                since.setdefault(c, q_list[qi])
            sel_hist.append((q_list[qi], sorted(selected)))
            qi += 1
        if t >= WF_START and selected:
            best = {}
            for j in batch:
                e = events[j]
                if e[1] not in selected:
                    continue
                ed = ev_dict(e, defs)
                take, size, why, m, se = brain.decide(ed)
                if not take:
                    decisions["refused"] += 1
                    continue
                score = m - P["z"] * se
                if e[2] not in best or score > best[e[2]][0]:
                    best[e[2]] = (score, j, size, m)
            for coin, (score, j, size, m) in sorted(best.items(), key=lambda kv: -kv[1][0]):
                e = events[j]
                group = defs[e[1]]["group"]
                ok, _ = book.can_open(coin, group, (t - 6 * HOUR) // DAY)
                if not ok:
                    decisions["refused"] += 1
                    continue
                decisions["taken"] += 1
                risk_pct = (P["risk_major"] if group == "majors" else P["risk_meme"]) * size
                risk_amt = eq * risk_pct
                notional = risk_amt / (e[6] / 100)
                if notional > eq:
                    risk_amt *= eq / notional
                r = r_of(e)
                rec = {"t": t, "t_exit": e[3], "cid": e[1], "coin": coin, "r": r, "size": size, "risk_pct": risk_amt / eq,
                       "m": m, "period": period(t), "eq_before": eq}
                trades.append(rec)
                book.opened(coin, group)
                seq += 1
                heapq.heappush(opn, (e[3], seq, coin, group, risk_amt, r, rec))
        for j in batch:
            heapq.heappush(comp, (events[j][3], j))
    while opn:
        te, _, coin, group, risk_amt, r, rec = heapq.heappop(opn)
        eq += risk_amt * r
        peak = max(peak, eq)
        mdd = max(mdd, 1 - eq / peak)
        rec["eq_after"] = eq
    res = {"metrics": metrics(trades), "decisions": decisions, "end_equity": eq, "mdd": mdd * 100}
    if record:
        res.update(trades=trades, brain=brain, selected=sel_hist, cstat=cstat)
    return res


def metrics(trades):
    out = {}
    for per in ("dev", "B", "C", "all"):
        tr = [x for x in trades if per == "all" or x["period"] == per]
        if not tr:
            out[per] = {"n": 0, "avg_r": 0.0, "win": 0.0, "ret": 0.0, "mdd": 0.0, "score": -1e9}
            continue
        rs = [x["r"] for x in tr]
        ret_fr = [x["risk_pct"] * x["r"] for x in tr]             # account fraction made per trade
        eq, peak, mdd = 1.0, 1.0, 0.0
        for f in ret_fr:
            eq *= 1 + f
            peak = max(peak, eq)
            mdd = max(mdd, 1 - eq / peak)
        n = len(rs)
        mean = sum(rs) / n
        sd = math.sqrt(max(1e-12, sum((r - mean) ** 2 for r in rs) / max(1, n - 1)))
        ret = (eq - 1) * 100
        out[per] = {"n": n, "avg_r": round(mean, 4), "t": round(mean / (sd / math.sqrt(n)), 2) if n > 2 else 0.0,
                    "win": round(sum(r > 0 for r in rs) / n * 100, 1), "ret": round(ret, 2), "mdd": round(mdd * 100, 2),
                    "score": (ret - 0.5 * mdd * 100) if n >= 30 else -1e9}
    return out


# ------------------------------------------------------------------ 3. the improvement loop
SPACE = {"theta": [-0.05, 0.0, 0.03, 0.05, 0.08, 0.12, 0.18], "z": [0.0, 0.5, 1.0, 1.5, 2.0],
         "shrink": [5.0, 10.0, 20.0, 40.0, 80.0], "size_a": [0.0, 1.0, 2.0],
         "gate_rule": ["learned", "no_quiet", "loud_only"], "loud_mult": [0.6, 1.0], "weekend_off": [True, False],
         "regime_rule": ["learned", "memes_off_in_bear"], "max_open": [1, 2, 3, 4], "max_meme_open": [1, 2, 3],
         "sel_z": [0.0, 0.5, 1.0, 1.5], "sel_min_n": [20, 40, 80, 150], "max_per_signal": [1, 2, 4],
         "variants": ["all", "loud_only", "loudtrend"], "sel_window_days": [0, 365, 730], "evidence": ["all", "since_selected"]}


def improve(events, defs, iters, log, base_params=None):
    best_p = dict(DEFAULT_PARAMS, **(base_params or {}))
    base = simulate(events, defs, best_p)
    best_dev, best_b = base["metrics"]["dev"]["score"], base["metrics"]["B"]["score"]
    log.append({"iter": 0, "change": "start (defaults)", "dev": base["metrics"]["dev"], "B": base["metrics"]["B"],
                "kept": True})
    print(f"start: dev {fmt(base['metrics']['dev'])} | B {fmt(base['metrics']['B'])}", flush=True)
    rng = random.Random(20261003)
    props = [(k, v) for k, vs in SPACE.items() for v in vs]
    tried = set()
    it = 0
    while it < iters:
        cand = [pv for pv in props if best_p[pv[0]] != pv[1] and (pv, tuple(sorted(best_p.items()))) not in tried]
        if not cand:
            break
        k, v = rng.choice(cand)
        tried.add(((k, v), tuple(sorted(best_p.items()))))
        it += 1
        trial = dict(best_p, **{k: v})
        res = simulate(events, defs, trial)
        dev, b = res["metrics"]["dev"]["score"], res["metrics"]["B"]["score"]
        keep = dev > best_dev + 0.25 and b >= best_b - 0.5
        log.append({"iter": it, "change": f"{k} = {v}", "dev": res["metrics"]["dev"], "B": res["metrics"]["B"], "kept": keep})
        print(f"{it:3d} {k}={v!s:<10} dev {fmt(res['metrics']['dev'])} | B {fmt(res['metrics']['B'])} {'KEEP' if keep else ''}",
              flush=True)
        if keep:
            best_p, best_dev, best_b = trial, dev, b
    return best_p


def fmt(m):
    return f"n {m['n']:4d} R {m['avg_r']:+.3f} ret {m['ret']:+6.2f}% dd {m['mdd']:5.2f}%"


# ------------------------------------------------------------------ 4. extreme tests
def stress(events, defs, params):
    def fees2(e):
        return 0.4 / e[6]

    def kraken(e):
        return 0.8 / e[6]

    def slip3(e):
        return (0.08 if e[2] in MAJORS else 0.4) / e[6]

    out = {}
    for name, fn in (("NDAX fees x2", fees2), ("Kraken Pro entry-tier fees", kraken), ("slippage x3", slip3)):
        out[name] = simulate(events, defs, params, adj=fn)["metrics"]
    return out


def windows(trades, t0, t1, n=200, days=90):
    rng = random.Random(7)
    rets = []
    for _ in range(n):
        s = t0 + rng.random() * (t1 - t0 - days * DAY)
        tr = [x for x in trades if s <= x["t"] < s + days * DAY]
        eq = 1.0
        for x in tr:
            eq *= 1 + x["risk_pct"] * x["r"]
        rets.append(((eq - 1) * 100, len(tr)))
    r = sorted(x[0] for x in rets)
    return {"n": n, "days": days, "median": r[n // 2], "p10": r[n // 10], "p90": r[9 * n // 10], "best": r[-1], "worst": r[0],
            "positive": sum(x > 0 for x in r), "flat": sum(1 for x in rets if x[1] == 0), "avg": sum(r) / n,
            "avg_trades": sum(x[1] for x in rets) / n}


def bootstrap(trades, n=2000):
    rng = random.Random(11)
    fr = [x["risk_pct"] * x["r"] for x in trades]
    if not fr:
        return {}
    finals, dds = [], []
    for _ in range(n):
        eq, peak, mdd = 1.0, 1.0, 0.0
        for _ in range(len(fr)):
            eq *= 1 + fr[rng.randrange(len(fr))]
            peak = max(peak, eq)
            mdd = max(mdd, 1 - eq / peak)
        finals.append((eq - 1) * 100)
        dds.append(mdd * 100)
    finals.sort()
    dds.sort()
    return {"n": n, "ret_p5": finals[n // 20], "ret_p50": finals[n // 2], "ret_p95": finals[19 * n // 20],
            "loss_share": sum(x < 0 for x in finals) / n * 100, "dd_p50": dds[n // 2], "dd_p95": dds[19 * n // 20]}


# ------------------------------------------------------------------ 5. live model export
def export(events, defs, params, final, path):
    """The live model continues exactly where the walk-forward stopped: the last quarter's 50 agents and
    everything the brain had learned by the end of the data."""
    brain = final["brain"]
    chosen = sorted(final["selected"][-1][1], key=lambda c: -(final["cstat"][c][1] / final["cstat"][c][0]))
    taken = {}
    for x in final["trades"]:
        taken.setdefault(x["cid"], []).append(x["r"])
    recent = {}
    for e in events:
        if e[1] in chosen:
            recent.setdefault(e[1], []).append(e[4])
    agents = []
    for rank, cid in enumerate(chosen):
        n, sr, s2 = final["cstat"][cid]
        mean = sr / n
        rs = recent.get(cid, [])
        cum, spark = 0.0, []
        for r in rs[-40:]:
            cum += r
            spark.append(round(cum, 2))
        d = defs[cid]
        tk = taken.get(cid, [])
        agents.append({"id": cid, "name": NAMES[rank], "signal": d["signal"], "label": d["label"], "group": d["group"],
                       "tf": d["tf"], "variant": d["variant"], "family": d["family"], "rule": d["rule"], "signals": n,
                       "avg_r": round(mean, 4), "win": round(sum(r > 0 for r in rs) / max(1, len(rs)) * 100, 1),
                       "walk_forward_trades": len(tk), "walk_forward_avg_r": round(sum(tk) / len(tk), 4) if tk else None,
                       "spark": spark})
    model = {"version": 1, "trained": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
             "data_end": datetime.fromtimestamp(events[-1][0] / 1000, timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
             "params": params, "agents": agents,
             "stats": {"|".join(map(str, k)): [round(v[0], 3), round(v[1], 4), round(v[2], 4)] for k, v in brain.stats.items()},
             "exits": "limit 0.1% under the close (3 bars), stop 4x ATR of the timeframe, one exit at 2R, 96h, NDAX fees"}
    with open(path, "w") as fh:
        json.dump(model, fh, separators=(",", ":"))
    return model


# ------------------------------------------------------------------ report
def report(path, final, stress_res, win, boot, log, params, model, n_cand, n_events, secs):
    m = final["metrics"]
    row = lambda k, x: (f"| {k} | {x['n']} | {x['avg_r']:+.3f} | {x.get('t', 0)} | {x['win']:.0f}% | {x['ret']:+.2f}% | "  # noqa: E731
                        f"{x['mdd']:.2f}% |")
    L = ["# Ultron: training and backtest report", "",
         f"Generated {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())} by `ultron/tools/train.py` in {secs / 60:.1f} minutes.",
         f"{n_cand} candidate agents ({n_events:,} historical signals, every one traded with Ultron's exits at NDAX fees).",
         "R = profit or loss in units of the amount risked, after fees and slippage. Paper results, not a forecast.", "",
         "## How it was tested", "",
         "- **Walk-forward.** Every quarter from January 2022 the brain chose its 50 agents using only signals that had",
         "  already finished, then traded the next three months on a fresh decision for every signal. No trade below",
         "  was made by an agent chosen with knowledge of that trade.",
         "- **Three periods.** Development (2022-01-01 to 2025-03-19) tuned the brain's settings; validation",
         "  (2025-03-20 to 2025-12-22) had to agree before a change was kept; **test (from 2025-12-23) was never used to",
         "  choose anything.**",
         "- Account: $10,000 paper, risk per trade 0.6% (BTC/ETH/SOL) or 0.3% (memes) x the brain's size, compounding.", "",
         "## Result (final settings)", "", "| Period | Trades | Avg R | t | Win | Return | Max drawdown |",
         "|---|---|---|---|---|---|---|", row("Development", m["dev"]), row("Validation", m["B"]), row("**Test (untouched)**", m["C"]),
         row("All", m["all"]), "",
         f"Decisions: {final['decisions']['taken']:,} signals taken, {final['decisions']['refused']:,} refused.", "",
         "## Extreme tests", "", "| Test | Trades | Avg R | t | Win | Return | Max drawdown |", "|---|---|---|---|---|---|---|"]
    for k, x in stress_res.items():
        L.append(row(k, x["all"]))
    L += ["", f"**{win['n']} random {win['days']}-day windows** (fresh account each): median {win['median']:+.2f}%, "
          f"10th percentile {win['p10']:+.2f}%, 90th {win['p90']:+.2f}%, best {win['best']:+.2f}%, worst {win['worst']:+.2f}%; "
          f"positive in {win['positive']} of {win['n']}; {win['flat']} had no trade; {win['avg_trades']:.1f} trades per window.", ""]
    if boot:
        L += [f"**{boot['n']:,} bootstrap reshuffles** of the walk-forward trades: final return 5th / 50th / 95th "
              f"percentile {boot['ret_p5']:+.1f}% / {boot['ret_p50']:+.1f}% / {boot['ret_p95']:+.1f}%; ended below the start "
              f"in {boot['loss_share']:.1f}%; max drawdown median {boot['dd_p50']:.1f}%, 95th percentile {boot['dd_p95']:.1f}%.", ""]
    L += ["## The improvement loop", "",
          f"{len(log) - 1} proposals, each one setting changed at a time; kept only if development improved and validation "
          "did not get worse.", "", "| # | Change | Dev trades | Dev avg R | Dev return | Val avg R | Val return | Kept |",
          "|---|---|---|---|---|---|---|---|"]
    for x in log:
        L.append(f"| {x['iter']} | {x['change']} | {x['dev']['n']} | {x['dev']['avg_r']:+.3f} | {x['dev']['ret']:+.2f}% | "
                 f"{x['B']['avg_r']:+.3f} | {x['B']['ret']:+.2f}% | {'yes' if x['kept'] else ''} |")
    L += ["", "Final settings: `" + json.dumps(params) + "`", "",
          "## The 50 agents in the live model (the last quarter's choice; history = all their signals to the end)", "",
          "| Agent | Signal | Group | Candles | When | Signals | Avg R (all history) | Win | Walk-forward trades | Walk-forward avg R |",
          "|---|---|---|---|---|---|---|---|---|---|"]
    for a in model["agents"]:
        wf = f"{a['walk_forward_avg_r']:+.3f}" if a["walk_forward_avg_r"] is not None else "—"
        when = {"any": "any time", "loud": "big-move periods", "trend": "uptrends", "loudtrend": "big moves in uptrends"}[a["variant"]]
        L.append(f"| {a['name']} | {a['label']} | {a['group']} | {a['tf']} | {when} | {a['signals']} | {a['avg_r']:+.3f} | {a['win']:.0f}% | "
                 f"{a['walk_forward_trades']} | {wf} |")
    L += ["", "## What this does not show", "",
          "- Real fills: limit orders may fill less often or at worse prices live; the stops assume no gaps beyond the bar.",
          "- The future: 2022-2026 contained a bear market, a recovery and a bull run; other markets may differ.",
          "- The selection of signals, exits and coins was informed by earlier research on this same history, so even the",
          "  walk-forward is somewhat optimistic. Paper-trade it before trusting it with money.", ""]
    with open(path, "w") as fh:
        fh.write("\n".join(L))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--iters", type=int, default=100)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--cache", default=None)
    ap.add_argument("--tv", action="store_true", help="TradingView build: Pine gate, Pine-portable signals, 25 agents")
    a = ap.parse_args()
    t0 = time.time()
    gate_model, allowed, base = None, None, {}
    out_model, out_bt, out_md = (os.path.join(ROOT, "assets", "ultron_model.json"), os.path.join(ROOT, "assets", "ultron_backtest.json"),
                                 os.path.join(ROOT, "docs", "BACKTEST.md"))
    if a.tv:
        with open(os.path.join(ROOT, "tv", "pine_gate_model.json")) as fh:
            gate_model = json.load(fh)
        allowed = TV_SIGNALS
        base = {"n_agents": 25}
        out_model, out_bt, out_md = (os.path.join(ROOT, "tv", "tv_model.json"), os.path.join(ROOT, "tv", "tv_backtest.json"),
                                     os.path.join(ROOT, "tv", "BACKTEST.md"))
    cache = a.cache or os.path.join(a.data, "ultron_tv_events.pkl" if a.tv else "ultron_events.pkl")
    events, defs, coins = build_events(a.data, a.workers, cache, gate_model, allowed)
    print(f"{len(defs)} candidates, {len(events):,} signals, coins {coins} ({time.time() - t0:.0f}s)", flush=True)
    log = []
    params = improve(events, defs, a.iters, log, base)
    final = simulate(events, defs, params, record=True)
    print("final:", {k: fmt(v) for k, v in final["metrics"].items()}, flush=True)
    stress_res = stress(events, defs, params)
    t_lo = max(WF_START, min(x["t"] for x in final["trades"])) if final["trades"] else WF_START
    win = windows(final["trades"], t_lo, events[-1][0])
    boot = bootstrap(final["trades"])
    os.makedirs(os.path.join(ROOT, "assets"), exist_ok=True)
    os.makedirs(os.path.join(ROOT, "docs"), exist_ok=True)
    model = export(events, defs, params, final, out_model)
    if a.tv:
        model["gate"] = gate_model
        with open(out_model, "w") as fh:
            json.dump(model, fh, separators=(",", ":"))
    report(out_md, final, stress_res, win, boot, log, params, model, len(defs), len(events), time.time() - t0)
    summary = {"metrics": final["metrics"], "decisions": final["decisions"], "stress": {k: v["all"] for k, v in stress_res.items()},
               "windows": win, "bootstrap": boot, "params": params, "iterations": len(log) - 1,
               "kept": sum(1 for x in log if x["kept"]) - 1}
    with open(out_bt, "w") as fh:
        json.dump(summary, fh, indent=1)
    print("done", round(time.time() - t0), "s", flush=True)


if __name__ == "__main__":
    main()
