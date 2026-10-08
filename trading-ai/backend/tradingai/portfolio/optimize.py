"""Portfolio construction (sections 199-201, 240-243). Inputs are return series known up to now; outputs are weights.

* equal, inverse_vol: simple and hard to overfit
* risk_parity: equal risk contribution (iterative solver)
* min_variance: on a Ledoit-Wolf shrunk covariance (sample covariances of few observations are too noisy to invert)
* hrp: Lopez de Prado's hierarchical risk parity (no inversion at all)
* mean_variance: shrunk covariance, expected returns shrunk toward zero, long-only, every weight capped. Expected
  returns are the most error-prone input, so this method is offered last and capped hardest.
* clusters(): groups instruments whose returns move together, so exposure limits see "long BTC, long ETH" as one
  crypto bet (section 200).
"""

from __future__ import annotations

import numpy as np


def ledoit_wolf(X: np.ndarray) -> tuple[np.ndarray, float]:
    """Shrinkage toward a scaled identity (Ledoit & Wolf 2004). X: T x N returns. Returns (covariance, shrinkage)."""
    X = X - X.mean(axis=0)
    t, n = X.shape
    S = X.T @ X / t
    mu = np.trace(S) / n
    F = mu * np.eye(n)
    d2 = np.sum((S - F) ** 2)
    b2 = sum(np.sum((np.outer(x, x) - S) ** 2) for x in X) / t ** 2
    delta = min(1.0, b2 / d2) if d2 > 0 else 1.0
    return delta * F + (1 - delta) * S, float(delta)


def equal(n: int) -> np.ndarray:
    return np.full(n, 1.0 / n)


def inverse_vol(X: np.ndarray) -> np.ndarray:
    v = X.std(axis=0, ddof=1)
    w = np.where(v > 0, 1 / v, 0.0)
    return w / w.sum() if w.sum() > 0 else equal(X.shape[1])


def risk_parity(cov: np.ndarray, iters: int = 500) -> np.ndarray:
    n = len(cov)
    w = np.full(n, 1.0 / n)
    for _ in range(iters):
        rc = w * (cov @ w)
        target = rc.sum() / n
        w = w * np.sqrt(target / np.maximum(rc, 1e-18))
        w /= w.sum()
    return w


def min_variance(cov: np.ndarray, cap: float = 1.0) -> np.ndarray:
    inv = np.linalg.pinv(cov)
    w = inv @ np.ones(len(cov))
    w = np.clip(w / w.sum(), 0, None)
    return _cap(w, cap)


def _cap(w: np.ndarray, cap: float) -> np.ndarray:
    w = np.clip(w, 0, None)
    w = w / w.sum() if w.sum() > 0 else np.full(len(w), 1 / len(w))
    for _ in range(50):
        over = w > cap
        if not over.any():
            break
        excess = (w[over] - cap).sum()
        w[over] = cap
        free = ~over
        if not free.any():
            break
        w[free] += excess * w[free] / w[free].sum()
    return w


def hrp(X: np.ndarray) -> np.ndarray:
    cov = np.cov(X, rowvar=False)
    sd = np.sqrt(np.diag(cov))
    corr = cov / np.outer(sd, sd)
    dist = np.sqrt(np.clip((1 - corr) / 2, 0, 1))
    order = _quasi_diag(dist)
    w = np.ones(len(cov))
    stack = [order]
    while stack:
        items = stack.pop()
        if len(items) <= 1:
            continue
        half = len(items) // 2
        a, b = items[:half], items[half:]
        va, vb = _cluster_var(cov, a), _cluster_var(cov, b)
        alpha = 1 - va / (va + vb)
        w[a] *= alpha
        w[b] *= 1 - alpha
        stack += [a, b]
    return w / w.sum()


def _cluster_var(cov: np.ndarray, idx: list[int]) -> float:
    c = cov[np.ix_(idx, idx)]
    iv = 1 / np.diag(c)
    iv /= iv.sum()
    return float(iv @ c @ iv)


def _quasi_diag(dist: np.ndarray) -> list[int]:
    """Single-linkage order of the assets (a small agglomerative clustering, enough for tens of assets)."""
    clusters = [[i] for i in range(len(dist))]
    while len(clusters) > 1:
        best = None
        for i in range(len(clusters)):
            for j in range(i + 1, len(clusters)):
                d = min(dist[a, b] for a in clusters[i] for b in clusters[j])
                if best is None or d < best[0]:
                    best = (d, i, j)
        _, i, j = best
        clusters[i] = clusters[i] + clusters[j]
        del clusters[j]
    return clusters[0]


def mean_variance(X: np.ndarray, risk_aversion: float = 5.0, shrink_mu: float = 0.5, cap: float = 0.3) -> np.ndarray:
    cov, _ = ledoit_wolf(X)
    mu = X.mean(axis=0) * (1 - shrink_mu)
    w = np.linalg.pinv(risk_aversion * cov) @ mu
    return _cap(np.clip(w, 0, None) if w.sum() > 0 else equal(X.shape[1]), cap)


def optimize(X: np.ndarray, method: str = "risk_parity", cap: float = 0.4) -> dict:
    X = X[np.all(np.isfinite(X), axis=1)]
    n = X.shape[1]
    if len(X) < max(30, 2 * n):
        return {"method": method, "weights": equal(n).tolist(), "note": "too few observations: equal weight"}
    cov, delta = ledoit_wolf(X)
    w = {"equal": lambda: equal(n), "inverse_vol": lambda: inverse_vol(X), "risk_parity": lambda: risk_parity(cov),
         "min_variance": lambda: min_variance(cov, cap), "hrp": lambda: hrp(X),
         "mean_variance": lambda: mean_variance(X, cap=cap)}[method]()
    w = _cap(w, cap)
    port_vol = float(np.sqrt(w @ cov @ w))
    rc = w * (cov @ w) / (port_vol ** 2) if port_vol > 0 else w
    return {"method": method, "weights": [round(float(x), 6) for x in w], "shrinkage": round(delta, 4),
            "vol_per_period": port_vol, "risk_contribution": [round(float(x), 4) for x in rc]}


def clusters(X: np.ndarray, names: list[str], threshold: float = 0.6) -> list[list[str]]:
    """Instruments whose return correlation exceeds `threshold` (linked) end up in one cluster."""
    X = X[np.all(np.isfinite(X), axis=1)]
    if len(X) < 20:
        return [[n] for n in names]
    corr = np.corrcoef(X, rowvar=False)
    parent = list(range(len(names)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            if corr[i, j] >= threshold:
                parent[find(i)] = find(j)
    groups: dict[int, list[str]] = {}
    for i, n in enumerate(names):
        groups.setdefault(find(i), []).append(n)
    return list(groups.values())
