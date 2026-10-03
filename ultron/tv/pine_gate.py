"""The TradingView volatility gate: a logistic model on 14 features that Pine Script can compute exactly.

Same idea as Jarvus's trained gate (LOUD = the next 12 hours' range lands in the top third of the last 30 days,
QUIET = bottom third), rebuilt so that the Python backtest and the Pine indicator compute identical numbers:
every rolling window, average and seed follows Pine's ta.* semantics (RMA seeded by an SMA, population stdev).

  fit(arrays_by_coin, split_ms)       -> model dict (weights, means, stds, thresholds, test scores)
  states(t, o, h, l, c, v, model)     -> array of "L" / "N" / "Q" / "U" (not enough history)
"""

from __future__ import annotations

import math

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view as swv

FEATURES = ["bias", "atr_ratio", "bbw_ratio", "rvol6", "rv_ratio", "range12", "move12", "shock1", "hour_sin", "hour_cos",
            "weekend", "rv6_ratio", "range72", "vol24_z"]
H = 12
WEEK = 168


def sma(x, n):
    out = np.full(len(x), np.nan)
    if len(x) >= n:
        out[n - 1:] = swv(x, n).mean(axis=1)
    return out


def ssum(x, n):
    out = np.full(len(x), np.nan)
    if len(x) >= n:
        out[n - 1:] = swv(x, n).sum(axis=1)
    return out


def stdev(x, n):
    out = np.full(len(x), np.nan)
    if len(x) >= n:
        out[n - 1:] = swv(x, n).std(axis=1)
    return out


def highest(x, n):
    out = np.full(len(x), np.nan)
    if len(x) >= n:
        out[n - 1:] = swv(x, n).max(axis=1)
    return out


def lowest(x, n):
    out = np.full(len(x), np.nan)
    if len(x) >= n:
        out[n - 1:] = swv(x, n).min(axis=1)
    return out


def rma(x, n):
    """Pine ta.rma: seeded with the SMA of the first n values, then (prev*(n-1)+x)/n."""
    out = np.full(len(x), np.nan)
    if len(x) < n:
        return out
    v = float(np.mean(x[:n]))
    out[n - 1] = v
    for i in range(n, len(x)):
        v = (v * (n - 1) + x[i]) / n
        out[i] = v
    return out


def atr(h, l, c, n=14):
    pc = np.concatenate([[np.nan], c[:-1]])
    tr = np.where(np.isnan(pc), h - l, np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc))))
    return rma(tr, n)


def lg(x):
    return np.log(np.maximum(1e-6, x))


def features(t, o, h, l, c, v):
    """(n x 14) feature matrix, NaN where history is too short. Bar i uses bars <= i only."""
    with np.errstate(divide="ignore", invalid="ignore"):
        A = atr(h, l, c)
        bbw = 4 * stdev(c, 20) / sma(c, 20)
        r12 = (highest(h, 12) - lowest(l, 12)) / c
        r72 = (highest(h, 72) - lowest(l, 72)) / c
        lr = np.concatenate([[0.0], np.log(c[1:] / c[:-1])])
        rms = lambda k: np.sqrt(ssum(lr * lr, k) / k)                       # noqa: E731
        hour = (t // 3_600_000) % 24
        dow = ((t // 86_400_000) + 3) % 7
        c12 = np.concatenate([np.full(12, np.nan), c[:-12]])
        X = np.column_stack([
            np.ones(len(c)),
            lg(A / sma(A, WEEK)),
            lg(bbw / sma(bbw, WEEK)),
            lg((ssum(v, 6) / 6 + 1e-12) / (sma(v, WEEK) + 1e-12)),
            lg(rms(24) / rms(WEEK)),
            lg(r12 / sma(r12, WEEK)),
            np.minimum(6.0, np.abs(c - c12) / A),
            np.minimum(6.0, (h - l) / A),
            np.sin(2 * math.pi * hour / 24), np.cos(2 * math.pi * hour / 24),
            (dow >= 5).astype(float),
            lg(rms(6) / rms(WEEK)),
            lg(r72 / sma(r72, WEEK)),
            np.clip((sma(v, 24) - sma(v, WEEK)) / np.where(stdev(v, WEEK) > 0, stdev(v, WEEK), 1e-12), -4, 4),
        ])
    X[:WEEK + 80] = np.nan                                     # warm-up (the RMA/SMA chains need history)
    return X


def labels(h, l, c, window=720):
    """1 = next 12h range in the top third of the last 30 days of finished 12h ranges, 0 = bottom third, else nan."""
    n = len(c)
    fwd = np.full(n, np.nan)
    hh = highest(h, H)
    ll = lowest(l, H)
    fwd[:n - H] = (hh[H:] - ll[H:]) / c[:n - H]                # range of bars i+1..i+12
    hi_q, lo_q = np.full(n, np.nan), np.full(n, np.nan)
    for i in range(window + H, n, 24):                         # thresholds refreshed daily (causal: ranges ended by i)
        w = fwd[i - window - H:i - H]
        w = w[~np.isnan(w)]
        if len(w) > 200:
            hi_q[i:i + 24], lo_q[i:i + 24] = np.percentile(w, 66.67), np.percentile(w, 33.33)
    loud = np.where(np.isnan(fwd) | np.isnan(hi_q), np.nan, (fwd > hi_q).astype(float))
    quiet = np.where(np.isnan(fwd) | np.isnan(lo_q), np.nan, (fwd < lo_q).astype(float))
    return loud, quiet


def _fit_logit(X, y, l2=1e-3, iters=400, lr=0.5):
    w = np.zeros(X.shape[1])
    for _ in range(iters):
        p = 1 / (1 + np.exp(-np.clip(X @ w, -30, 30)))
        g = X.T @ (p - y) / len(y) + l2 * np.r_[0, w[1:]]
        w -= lr * g
    return w


def auc(p, y):
    order = np.argsort(p)
    r = np.empty(len(p))
    r[order] = np.arange(1, len(p) + 1)
    n1 = y.sum()
    n0 = len(y) - n1
    return float((r[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0)) if n1 and n0 else float("nan")


def fit(data, split_b, split_c, flag_share=0.05):
    """data: list of (t, o, h, l, c, v) numpy arrays per coin. Fit on bars before split_b; report B and C."""
    rows = {"A": [], "B": [], "C": []}
    for t, o, h, l, c, v in data:
        X = features(t, o, h, l, c, v)
        yl, yq = labels(h, l, c)
        ok = ~np.isnan(X).any(axis=1) & ~np.isnan(yl) & ~np.isnan(yq)
        for k, m in (("A", t < split_b), ("B", (t >= split_b) & (t < split_c)), ("C", t >= split_c)):
            sel = ok & m
            rows[k].append((X[sel], yl[sel], yq[sel]))
    pack = {k: (np.vstack([r[0] for r in v]), np.concatenate([r[1] for r in v]), np.concatenate([r[2] for r in v]))
            for k, v in rows.items()}
    XA, yA_l, yA_q = pack["A"]
    mu = XA.mean(axis=0)
    sd = XA.std(axis=0)
    mu[0], sd[0] = 0.0, 1.0
    sd[sd == 0] = 1.0
    Z = lambda X: (X - mu) / sd                                 # noqa: E731
    wl = _fit_logit(Z(XA), yA_l)
    wq = _fit_logit(Z(XA), yA_q)
    pl = 1 / (1 + np.exp(-(Z(XA) @ wl)))
    pq = 1 / (1 + np.exp(-(Z(XA) @ wq)))
    tl = float(np.quantile(pl, 1 - flag_share))
    tq = float(np.quantile(pq, 1 - flag_share))
    model = {"features": FEATURES, "mean": mu.tolist(), "std": sd.tolist(), "w_loud": wl.tolist(), "w_quiet": wq.tolist(),
             "t_loud": tl, "t_quiet": tq, "scores": {}}
    for k, (X, yl, yq) in pack.items():
        p1 = 1 / (1 + np.exp(-(Z(X) @ wl)))
        p0 = 1 / (1 + np.exp(-(Z(X) @ wq)))
        fl, fq = p1 >= tl, p0 >= tq
        model["scores"][k] = {"rows": int(len(yl)), "auc_loud": round(auc(p1, yl), 4), "auc_quiet": round(auc(p0, yq), 4),
                              "loud_flagged": round(float(fl.mean()) * 100, 2),
                              "loud_precision": round(float(yl[fl].mean()) * 100, 1) if fl.any() else None,
                              "quiet_precision": round(float(yq[fq].mean()) * 100, 1) if fq.any() else None,
                              "base_rate": round(float(yl.mean()) * 100, 1)}
    return model


def states(t, o, h, l, c, v, model):
    X = features(t, o, h, l, c, v)
    mu, sd = np.array(model["mean"]), np.array(model["std"])
    Z = (X - mu) / sd
    with np.errstate(invalid="ignore"):
        pl = 1 / (1 + np.exp(-(Z @ np.array(model["w_loud"]))))
        pq = 1 / (1 + np.exp(-(Z @ np.array(model["w_quiet"]))))
    out = np.where(pl >= model["t_loud"], "L", np.where(pq >= model["t_quiet"], "Q", "N")).astype(object)
    out[np.isnan(X).any(axis=1)] = "U"
    return out
