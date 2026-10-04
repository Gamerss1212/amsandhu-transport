"""The trained ULTRON councils, live: the same rules as the TradingView indicator (ultron/tv/build_pine.py), in Python.

A council = one chart timeframe's 25 agents + its brain constants, exported by ultron/tools/train_tf.py.
evaluate() looks at the newest completed bar of one coin and returns the council's best approved trade, if any:
  volatility gate (logistic, this timeframe) -> agents whose signal fired (chart bars, or the higher-timeframe bar
  that just closed) and whose condition holds (LOUD / uptrend) -> learned edge for the Bitcoin regime ->
  hard rules (fees <= 0.33R, gate rule, weekend majors, memes off in a bear market) -> edge - z x error >= threshold.
Edges are the frozen snapshot from training, exactly what the indicator uses (no live re-training).
"""

from __future__ import annotations

import math

import numpy as np

import pine_gate as pg
import signals as sg

MIN = 60_000
DAY = 86_400_000
SIZE = {"1h": 60 * MIN, "4h": 240 * MIN, "1D": DAY}
HTF_SIZE = {"1h": 240 * MIN, "4h": DAY, "1D": 7 * DAY}


def ema_first(x, n):
    """Pine ta.ema: seeded with the first value."""
    out = np.empty(len(x))
    a = 2 / (n + 1)
    e = x[0]
    for i, xv in enumerate(x):
        e = xv if i == 0 else a * xv + (1 - a) * e
        out[i] = e
    return out


def aggregate(rows, size_ms):
    """Completed hourly rows -> bars of size_ms (UTC-aligned), as the trainer built them: a bucket with a missing hour
    is kept (exchanges skip empty hours); only the last bucket is dropped while it is still open."""
    out, cur, k_cur = [], None, None
    for r in rows:
        k = r[0] // size_ms
        if k != k_cur:
            if cur is not None:
                out.append(cur)
            k_cur, cur = k, [k * size_ms, r[1], r[2], r[3], r[4], r[5]]
        else:
            cur[2], cur[3], cur[4], cur[5] = max(cur[2], r[2]), min(cur[3], r[3]), r[4], cur[5] + r[5]
    if cur is not None and rows and cur[0] + size_ms <= rows[-1][0] + 3_600_000:
        out.append(cur)                                             # the last bucket has ended: complete
    return out


def bars_since(t, i, t_last):
    """Bars between an earlier fire (by its bar time) and bar i: counts bars, not hours, so market charts that skip
    weekends and holidays space signals exactly as the trainer did."""
    if t_last is None or t_last < t[0]:
        return 10 ** 9
    return i - int(np.searchsorted(t, t_last))


def arrays(rows):
    t = np.array([r[0] for r in rows], dtype=np.int64)
    return (t,) + tuple(np.array([r[k] for r in rows], float) for k in (1, 2, 3, 4, 5))


def evaluate(model, coin, rows, htf_rows, bull, weekend, fees, slip, last_fire, group, htf_end=None):
    """rows / htf_rows: completed chart and higher-timeframe bars [t, o, h, l, c, v], oldest first.
    last_fire: dict the caller keeps between calls ({"c|sid": t, "h|sid": t}); updated here.
    Returns (decision dict or None, info dict for the screen)."""
    tf = model["tf"]
    size, hsize = SIZE[tf], HTF_SIZE[tf]
    t, o, h, l, c, v = arrays(rows)
    n = len(c)
    i = n - 1
    bars_day = max(1, DAY // size)
    gm = model["gate"]
    gate = str(pg.states(t, o, h, l, c, v, gm)[i])
    very_loud = False
    if gate == "L" and gm.get("t_vloud"):                               # Radar's VERY LOUD tier (top 1% of scores)
        X = pg.features(t[-400:], o[-400:], h[-400:], l[-400:], c[-400:], v[-400:])[-1]
        z = (X - np.array(gm["mean"])) / np.array(gm["std"])
        very_loud = bool(1 / (1 + np.exp(-(z @ np.array(gm["w_loud"])))) >= gm["t_vloud"])
    up1 = bool(ema_first(c, 21)[i] > ema_first(c, 50)[i] and c[i] > ema_first(c, 200)[i])
    ht, ho, hh, hl, hc, hv = arrays(htf_rows)
    h21, h50 = ema_first(hc, 21), ema_first(hc, 50)
    upH = bool(hc[-1] > h50[-1] and h21[-1] > h50[-1])               # the last completed higher-timeframe bar
    if htf_end is None:                                                 # crypto: the higher bar ends with this one
        htf_end = (int(t[i]) + size) % hsize == 0 and int(ht[-1]) + hsize == int(t[i]) + size
    A = pg.atr(h, l, c)
    atr = float(A[i])
    sigs = {a["signal"] for a in model["agents"]}
    S, _, _ = sg.vector_signals(t, o, h, l, c, v, bars_day)
    fired_c = set()
    for sid in sigs:                                                    # chart signals, at most one per 12 bars
        m = S.get(sid)
        if m is not None and m[i] and bars_since(t, i, last_fire.get("c|" + sid)) >= 12:
            fired_c.add(sid)
            last_fire["c|" + sid] = int(t[i])
    fired_h, AH = set(), float("nan")
    if htf_end:                                                         # higher-timeframe signals, at most one per 3 bars
        SH, _, _ = sg.vector_signals(ht, ho, hh, hl, hc, hv, max(1, DAY // hsize))
        AH = float(pg.atr(hh, hl, hc)[-1])
        for sid in sigs:
            m = SH.get(sid)
            if m is not None and m[-1] and int(ht[-1]) - last_fire.get("h|" + sid, -10 ** 15) >= 3 * hsize:
                fired_h.add(sid)
                last_fire["h|" + sid] = int(ht[-1])
    p = model["params"]
    ex = model.get("exit", {"stop_chart": 4.0, "stop_htf": 4.0, "hold": 96})
    loud = gate == "L"
    upj = up1 and upH
    regime = "na" if bull is None else "bull" if bull else "bear"
    entry = float(c[i]) * 0.999
    best, firing, why, fired_agents = None, 0, "no agent's signal fired on this bar", []
    for a in model["agents"]:
        if a["group"] != group:
            continue
        if a["signal"] not in (fired_h if a["htf"] else fired_c):
            continue
        var = a["variant"]
        if not (var == "any" or (var == "loud" and loud) or (var == "trend" and upj) or (var == "loudtrend" and loud and upj)):
            continue
        firing += 1
        fired_agents.append(a["id"])
        stop = ex["stop_htf"] * AH if a["htf"] else ex["stop_chart"] * atr
        if not stop > 0 or math.isnan(stop):
            continue
        cost = (fees[0] + fees[1] + 2 * slip) / (stop / entry)
        m_, se = a["edges"][regime]
        if cost > 0.33:
            why = "fees too high for this stop"
            continue
        if gate == "U":
            why = "volatility gate warming up"
            continue
        if p["gate_rule"] == "loud_only" and gate != "L":
            why = "waiting for a LOUD (big-move) period"
            continue
        if p["gate_rule"] == "no_quiet" and gate == "Q":
            why = "market too quiet for the fees"
            continue
        if p["weekend_off"] and group == "majors" and weekend:
            why = "weekend: no new BTC/ETH/SOL trades"
            continue
        if p["regime_rule"] == "memes_off_in_bear" and group == "memes" and bull is False:
            why = "Bitcoin below its 200-day average: memes off"
            continue
        score = m_ - p["z"] * se
        if score < p["theta"]:
            why = f"learned edge too small ({m_:+.2f}R)"
            continue
        if best is None or score > best["score"]:
            sz = max(0.5, min(1.5, 1 + p["size_a"] * m_)) * (0.5 if cost > 0.20 else 1.0) * (p["loud_mult"] if loud else 1.0)
            best = {"agent": a, "score": score, "m": m_, "size": sz, "stop_dist": stop, "entry": entry, "cost_r": cost,
                    "hold_ms": int(ex["hold"]) * size, "order_ms": 3 * size, "bar_t": int(t[i]), "t_dec": int(t[i]) + size}
    info = {"tf": tf, "gate": gate, "very_loud": very_loud, "up": up1, "upH": upH, "firing": firing,
            "why": "approved" if best else why,
            "price": float(c[i]), "atr": atr, "fired_agents": fired_agents}
    return best, info


# ---------------------------------------------------------------------------------------------- whole-chart series
def _buckets(t, hsize, weekly):
    return (t // DAY + 3) // 7 if weekly else t // hsize


def series(model, t, o, h, l, c, v, bull_of_bar, weekend_of_bar, fees, slip, group, market=False, fired_log=None, htf=None):
    """The council over every bar of a chart, exactly as the trainer built its signals (train_tf.build_coin): returns
    (approve, stop_dist, edge, agent_name) lists, one entry per bar. approve[i] = 1 where the council's brain approves a
    long entry at the close of bar i. Used by the Jarvus Terminal's rule function ultron(...)."""
    tf = model["tf"]
    size, hsize = SIZE[tf], HTF_SIZE[tf]
    t = np.asarray(t, dtype=np.int64)
    o, h, l, c, v = (np.asarray(x, float) for x in (o, h, l, c, v))
    n = len(c)
    out_ok, out_stop, out_m, out_name = [0.0] * n, [None] * n, [None] * n, [None] * n
    if n < 300:
        return out_ok, out_stop, out_m, out_name
    gm = model["gate"]
    gate = pg.states(t, o, h, l, c, v, gm)
    e21, e50, e200 = ema_first(c, 21), ema_first(c, 50), ema_first(c, 200)
    up1 = (e21 > e50) & (c > e200)
    # higher-timeframe bars built from the chart's own bars (complete buckets only)
    weekly = market
    k = _buckets(t, hsize, weekly)
    starts = np.flatnonzero(np.r_[True, k[1:] != k[:-1]])
    ends = np.r_[starts[1:], n] - 1
    keep = list(range(len(starts)))                                    # as the trainer: partial buckets count
    if not weekly and keep and int(t[ends[-1]]) + size < (int(k[ends[-1]]) + 1) * hsize:
        keep = keep[:-1]                                                # the last bucket is still open
    if weekly and keep and keep[-1] == len(starts) - 1 and (int(t[-1]) // DAY + 3) % 7 != 4:
        keep = keep[:-1]                                                   # the current week is not complete yet
    s_k, e_k = starts[keep], ends[keep]
    ht = (k[s_k] * 7 - 3) * DAY if weekly else k[s_k] * hsize
    ho, hc = o[s_k], c[e_k]
    hh = np.array([h[a:b + 1].max() for a, b in zip(s_k, e_k)])
    hl = np.array([l[a:b + 1].min() for a, b in zip(s_k, e_k)])
    hv = np.array([v[a:b + 1].sum() for a, b in zip(s_k, e_k)])
    if htf is not None and len(htf[0]):                              # longer history from the real higher-timeframe bars
        close_at = {int(x) + size: i for i, x in enumerate(t)}
        H = [np.asarray(x, float) for x in htf[1:]]
        hts = np.asarray(htf[0], dtype=np.int64)
        ends_ext = np.array([close_at.get(int(x) + hsize, -1) for x in hts])
        ht, ho, hh, hl, hc, hv = hts, H[0], H[1], H[2], H[3], H[4]
        e_k = ends_ext                                              # -1: that HTF bar closes outside this chart
    hup = np.zeros(len(hc), bool)
    if len(hc):
        h21, h50 = ema_first(hc, 21), ema_first(hc, 50)
        hup = (hc > h50) & (h21 > h50)
    # trend of the last completed HTF bar at each chart bar
    # the chart index from which each HTF bar counts as completed (-1: before this chart, n + 1: after it)
    ends_t = np.asarray(ht, dtype=np.int64) + hsize
    done_at = [int(e) if e >= 0 else (-1 if ends_t[jj] <= int(t[0]) + size else n + 1) for jj, e in enumerate(e_k)]
    upH = np.zeros(n, bool)
    j = -1
    for i in range(n):
        while j + 1 < len(done_at) and done_at[j + 1] <= i:
            j += 1
        upH[i] = bool(hup[j]) if j >= 0 else False
    A = pg.atr(h, l, c)
    bars_day = max(1, DAY // size)
    S, _, _ = sg.vector_signals(t, o, h, l, c, v, bars_day)
    agents = [a for a in model["agents"] if a["group"] == group]
    sigs = {a["signal"] for a in agents}
    fired_c = {}
    for sid in sigs:
        m = S.get(sid)
        if m is None or (sid in ("rally_24h", "drop_24h") and 30 * bars_day > 4500):
            continue
        last = -10 ** 9
        for jj in np.flatnonzero(m):
            if jj < 250 or jj - last < 12:
                continue
            last = jj
            fired_c.setdefault(int(jj), set()).add(sid)
    fired_h = {}
    if len(hc) >= 60:
        SH, _, _ = sg.vector_signals(ht, ho, hh, hl, hc, hv, max(1, DAY // hsize))
        AH = pg.atr(hh, hl, hc)
        for sid in sigs:
            m = SH.get(sid)
            if m is None or (sid in ("rally_24h", "drop_24h") and 30 * max(1, DAY // hsize) > 4500):
                continue
            last = -10 ** 9
            for jh in np.flatnonzero(m):
                if jh < 60 or jh - last < 3 or AH[jh] != AH[jh]:
                    continue
                last = jh
                i = int(e_k[jh])                                        # the chart bar that closes HTF bar jh
                if i >= 250:                                            # (-1: closes outside this chart)
                    fired_h.setdefault(i, {})[sid] = float(AH[jh])
    p = model["params"]
    ex = model.get("exit", {"stop_chart": 4.0, "stop_htf": 4.0, "hold": 96})
    for i in sorted(set(fired_c) | set(fired_h)):
        g = str(gate[i])
        if g == "U" or not A[i] == A[i]:
            continue
        loud, upj = g == "L", bool(up1[i] and upH[i])
        bull = bull_of_bar[i] if bull_of_bar is not None else None
        regime = "na" if bull is None else "bull" if bull else "bear"
        entry = float(c[i]) * 0.999
        best = None
        for a in agents:
            if a["htf"]:
                if a["signal"] not in fired_h.get(i, {}):
                    continue
                stop = ex["stop_htf"] * fired_h[i][a["signal"]]
            else:
                if a["signal"] not in fired_c.get(i, ()):
                    continue
                stop = ex["stop_chart"] * float(A[i])
            var = a["variant"]
            if not (var == "any" or (var == "loud" and loud) or (var == "trend" and upj) or (var == "loudtrend" and loud and upj)):
                continue
            if not stop > 0:
                continue
            if fired_log is not None:
                fired_log.setdefault(i, []).append(a["id"])
            cost = (fees[0] + fees[1] + 2 * slip) / (stop / entry)
            if cost > 0.33:
                continue
            if (p["gate_rule"] == "loud_only" and g != "L") or (p["gate_rule"] == "no_quiet" and g == "Q"):
                continue
            if p["weekend_off"] and group == "majors" and weekend_of_bar is not None and weekend_of_bar[i]:
                continue
            if p["regime_rule"] == "memes_off_in_bear" and group == "memes" and bull is False:
                continue
            m_, se = a["edges"][regime]
            score = m_ - p["z"] * se
            if score >= p["theta"] and (best is None or score > best[0]):
                best = (score, m_, stop, a["name"])
        if best:
            out_ok[i], out_m[i], out_stop[i], out_name[i] = 1.0, best[1], best[2], best[3]
    return out_ok, out_stop, out_m, out_name
