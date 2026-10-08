"""Market-regime detection (sections 164, 239). Causal: the regime at bar i uses bars up to i only, so it can be used
live, and the same labels are used to split backtest results by regime.

Components (each from a rule anyone can check):
* trend:      ADX(14) >= 25 and the 50-bar slope's sign -> "trend_up" / "trend_down"; else "range"
* volatility: percent rank of 20-bar realized volatility over the last 250 bars -> low (<20), normal, high (>80),
              extreme (>95)
* character:  variance ratio(4) over 100 bars: > 1.1 trending, < 0.9 mean-reverting, else random-walk-like
* liquidity:  relative volume (when the market reports volume): thin (<0.5), normal, heavy (>2)
* hmm:        a 2-state Gaussian hidden Markov model on returns, fitted on PAST data only (EM), then filtered
              forward. Its state probability is a model output, not a calibrated forecast, and is labelled so.
* change:     two-sided CUSUM on standardized returns: a recent structural break is flagged.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from tradingai.features import indicators as I
from tradingai.features.registry import FeatureFrame


@dataclass
class Regime:
    trend: str
    volatility: str
    character: str
    liquidity: str
    hmm_state: str | None
    hmm_state_prob: float | None
    change_point: bool
    label: str

    def as_dict(self) -> dict:
        d = dict(vars(self))
        d["hmm_note"] = "model state probability (uncalibrated), not a forecast of returns"
        return d


def trend_labels(ff: FeatureFrame) -> np.ndarray:
    adx = ff["adx_14"]
    slope = ff["linreg_slope_50"]
    out = np.full(len(ff.c), "unknown", dtype=object)
    ok = np.isfinite(adx) & np.isfinite(slope)
    out[ok] = "range"
    out[ok & (adx >= 25) & (slope > 0)] = "trend_up"
    out[ok & (adx >= 25) & (slope < 0)] = "trend_down"
    return out


def vol_labels(ff: FeatureFrame) -> np.ndarray:
    r = ff["vol_pctrank_20"]
    out = np.full(len(ff.c), "unknown", dtype=object)
    ok = np.isfinite(r)
    out[ok] = "normal"
    out[ok & (r < 20)] = "low"
    out[ok & (r > 80)] = "high"
    out[ok & (r > 95)] = "extreme"
    return out


def character_labels(ff: FeatureFrame) -> np.ndarray:
    vr = ff["variance_ratio_100"]
    out = np.full(len(ff.c), "unknown", dtype=object)
    ok = np.isfinite(vr)
    out[ok] = "random_walk"
    out[ok & (vr > 1.1)] = "trending"
    out[ok & (vr < 0.9)] = "mean_reverting"
    return out


def liquidity_labels(ff: FeatureFrame) -> np.ndarray:
    out = np.full(len(ff.c), "unknown", dtype=object)
    if ff.status("relvol_20") != "OK" or not np.any(ff.v > 0):
        return out
    rv = ff["relvol_20"]
    ok = np.isfinite(rv)
    out[ok] = "normal"
    out[ok & (rv < 0.5)] = "thin"
    out[ok & (rv > 2.0)] = "heavy"
    return out


# ----------------------------------------------------------------------------- Gaussian HMM (2 states)

def fit_hmm(r: np.ndarray, iters: int = 50, seed: int = 7) -> dict:
    """EM (Baum-Welch) for a 2-state Gaussian HMM. States are ordered so state 0 is the calmer one."""
    r = r[np.isfinite(r)]
    if len(r) < 100:
        raise ValueError("need at least 100 returns to fit the regime model")
    rng = np.random.default_rng(seed)
    mu = np.array([np.mean(r), np.mean(r)]) + rng.normal(0, 1e-6, 2)
    sd = np.array([np.std(r) * 0.6, np.std(r) * 1.6])
    A = np.array([[0.97, 0.03], [0.05, 0.95]])
    pi = np.array([0.5, 0.5])
    for _ in range(iters):
        B = np.exp(-0.5 * ((r[:, None] - mu) / sd) ** 2) / (sd * np.sqrt(2 * np.pi)) + 1e-300
        n = len(r)
        alpha, c = np.zeros((n, 2)), np.zeros(n)
        alpha[0] = pi * B[0]
        c[0] = alpha[0].sum()
        alpha[0] /= c[0]
        for t in range(1, n):
            alpha[t] = (alpha[t - 1] @ A) * B[t]
            c[t] = alpha[t].sum()
            alpha[t] /= c[t]
        beta = np.ones((n, 2))
        for t in range(n - 2, -1, -1):
            beta[t] = (A @ (B[t + 1] * beta[t + 1])) / c[t + 1]
        gamma = alpha * beta
        gamma /= gamma.sum(axis=1, keepdims=True)
        xi = (alpha[:-1, :, None] * A[None] * (B[1:] * beta[1:])[:, None, :]) / c[1:, None, None]
        A = xi.sum(axis=0) / gamma[:-1].sum(axis=0)[:, None]
        A /= A.sum(axis=1, keepdims=True)
        pi = gamma[0]
        w = gamma.sum(axis=0)
        mu = (gamma * r[:, None]).sum(axis=0) / w
        sd = np.sqrt((gamma * (r[:, None] - mu) ** 2).sum(axis=0) / w) + 1e-12
    order = np.argsort(sd)
    return {"mu": mu[order], "sd": sd[order], "A": A[np.ix_(order, order)], "pi": pi[order],
            "loglik": float(np.log(c).sum())}


def filter_hmm(r: np.ndarray, m: dict) -> np.ndarray:
    """Forward filter: P(state | returns up to t). Causal by construction."""
    out = np.full((len(r), 2), np.nan)
    p = m["pi"].copy()
    for t, x in enumerate(r):
        if not np.isfinite(x):
            out[t] = p
            continue
        b = np.exp(-0.5 * ((x - m["mu"]) / m["sd"]) ** 2) / m["sd"]
        p = (p @ m["A"]) * b
        s = p.sum()
        p = p / s if s > 0 else np.array([0.5, 0.5])
        out[t] = p
    return out


def cusum(r: np.ndarray, k: float = 0.5, h: float = 6.0) -> np.ndarray:
    """1 where a two-sided CUSUM on standardized returns crosses h (then resets)."""
    z = (r - np.nanmean(r)) / (np.nanstd(r) + 1e-12)
    pos = neg = 0.0
    out = np.zeros(len(r))
    for i, x in enumerate(np.nan_to_num(z)):
        pos, neg = max(0.0, pos + x - k), min(0.0, neg + x + k)
        if pos > h or neg < -h:
            out[i], pos, neg = 1.0, 0.0, 0.0
    return out


def detect(ff: FeatureFrame, *, hmm_train: int | None = None) -> tuple[Regime, dict]:
    """The regime at the LAST bar, and the full label series for research. The HMM is fitted on all bars except the
    last `len - hmm_train` (default: the first 70%), then filtered forward over everything."""
    tr, vo, ch, li = trend_labels(ff), vol_labels(ff), character_labels(ff), liquidity_labels(ff)
    r = I.logret(ff.c)
    state, prob, probs = None, None, None
    try:
        n_fit = hmm_train or int(len(r) * 0.7)
        m = fit_hmm(r[1:n_fit])
        probs = filter_hmm(r, m)
        k = int(np.argmax(probs[-1]))
        state, prob = ("calm" if k == 0 else "turbulent"), round(float(probs[-1, k]), 3)
    except ValueError:
        pass
    cp = cusum(r)
    recent_break = bool(cp[-20:].any()) if len(cp) else False
    label = f"{tr[-1]} / {vo[-1]} vol / {ch[-1]}" if len(tr) else "unknown"
    reg = Regime(str(tr[-1]) if len(tr) else "unknown", str(vo[-1]) if len(vo) else "unknown",
                 str(ch[-1]) if len(ch) else "unknown", str(li[-1]) if len(li) else "unknown", state, prob,
                 recent_break, label)
    series = {"trend": tr, "volatility": vo, "character": ch, "liquidity": li, "change_point": cp,
              "hmm_turbulent_prob": probs[:, 1] if probs is not None else None}
    return reg, series
