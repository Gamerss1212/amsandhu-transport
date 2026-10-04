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
    """Completed hourly rows -> completed bars of size_ms (UTC-aligned); drops a bucket that is not complete."""
    out, cur, k_cur = [], None, None
    per = size_ms // (60 * MIN)
    for r in rows:
        k = r[0] // size_ms
        if k != k_cur:
            if cur is not None:
                out.append(cur)
            k_cur, cur = k, [k * size_ms, r[1], r[2], r[3], r[4], r[5], 1]
        else:
            cur[2], cur[3], cur[4], cur[5], cur[6] = max(cur[2], r[2]), min(cur[3], r[3]), r[4], cur[5] + r[5], cur[6] + 1
    if cur is not None:
        out.append(cur)
    return [b[:6] for b in out if b[6] == per]


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
    gate = str(pg.states(t, o, h, l, c, v, model["gate"])[i])
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
    info = {"tf": tf, "gate": gate, "up": up1, "upH": upH, "firing": firing, "why": "approved" if best else why,
            "price": float(c[i]), "atr": atr, "fired_agents": fired_agents}
    return best, info
