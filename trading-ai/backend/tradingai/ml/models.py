"""Small, dependable models in numpy (sections 195-198). Nothing is fitted on the data it is scored on.

* LogisticModel: L2-regularized logistic regression (Newton / IRLS), features standardized with TRAINING statistics.
* BoostedStumps: gradient boosting of depth-1 trees on quantile thresholds, log-loss, shrinkage.
* Calibration: Platt scaling and isotonic regression (pool-adjacent-violators); Brier score, expected calibration
  error, reliability curve and rank AUC for evaluation.
"""

from __future__ import annotations

import numpy as np


def _sig(z: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(z, -35, 35)))


class LogisticModel:
    name = "logistic_l2"

    def __init__(self, l2: float = 1.0, iters: int = 25):
        self.l2, self.iters = l2, iters
        self.mu = self.sd = self.w = None

    def fit(self, X: np.ndarray, y: np.ndarray) -> "LogisticModel":
        self.mu = np.nanmean(X, axis=0)
        self.sd = np.nanstd(X, axis=0)
        self.sd[self.sd == 0] = 1.0
        Z = np.c_[np.ones(len(X)), np.nan_to_num((X - self.mu) / self.sd)]
        w = np.zeros(Z.shape[1])
        reg = self.l2 * np.eye(Z.shape[1])
        reg[0, 0] = 0.0
        for _ in range(self.iters):
            p = _sig(Z @ w)
            g = Z.T @ (p - y) + reg @ w
            H = (Z * (p * (1 - p))[:, None]).T @ Z + reg
            step = np.linalg.solve(H + 1e-9 * np.eye(len(w)), g)
            w -= step
            if np.max(np.abs(step)) < 1e-8:
                break
        self.w = w
        return self

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        Z = np.c_[np.ones(len(X)), np.nan_to_num((X - self.mu) / self.sd)]
        return _sig(Z @ self.w)


class BoostedStumps:
    name = "boosted_stumps"

    def __init__(self, n_estimators: int = 150, learning_rate: float = 0.05, n_bins: int = 16, min_leaf: int = 30):
        self.n, self.lr, self.bins, self.min_leaf = n_estimators, learning_rate, n_bins, min_leaf
        self.stumps: list[tuple[int, float, float, float]] = []
        self.base = 0.0

    def fit(self, X: np.ndarray, y: np.ndarray) -> "BoostedStumps":
        X = np.nan_to_num(X)
        p0 = np.clip(y.mean(), 1e-4, 1 - 1e-4)
        self.base = float(np.log(p0 / (1 - p0)))
        f = np.full(len(y), self.base)
        thresholds = [np.unique(np.quantile(X[:, j], np.linspace(0.05, 0.95, self.bins))) for j in range(X.shape[1])]
        for _ in range(self.n):
            p = _sig(f)
            g, h = y - p, p * (1 - p) + 1e-9
            best = None
            for j, ths in enumerate(thresholds):
                col = X[:, j]
                for t in ths:
                    left = col <= t
                    nl = left.sum()
                    if nl < self.min_leaf or len(y) - nl < self.min_leaf:
                        continue
                    gl, hl = g[left].sum(), h[left].sum()
                    gr, hr = g.sum() - gl, h.sum() - hl
                    gain = gl * gl / hl + gr * gr / hr
                    if best is None or gain > best[0]:
                        best = (gain, j, t, gl / hl, gr / hr)
            if best is None:
                break
            _, j, t, vl, vr = best
            self.stumps.append((j, float(t), float(vl), float(vr)))
            f += self.lr * np.where(X[:, j] <= t, vl, vr)
        return self

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        X = np.nan_to_num(X)
        f = np.full(len(X), self.base)
        for j, t, vl, vr in self.stumps:
            f += self.lr * np.where(X[:, j] <= t, vl, vr)
        return _sig(f)


class PriorModel:
    """Baseline: always predicts the training base rate. A real model must beat this out of sample."""
    name = "base_rate"

    def fit(self, X, y):
        self.p = float(np.mean(y)) if len(y) else 0.5
        return self

    def predict_proba(self, X):
        return np.full(len(X), self.p)


# ----------------------------------------------------------------------------- calibration and scoring

class Platt:
    def fit(self, s: np.ndarray, y: np.ndarray) -> "Platt":
        self.m = LogisticModel(l2=1e-3).fit(s.reshape(-1, 1), y)
        return self

    def __call__(self, s) -> np.ndarray:
        return self.m.predict_proba(np.atleast_1d(np.asarray(s, dtype=float)).reshape(-1, 1))


class Isotonic:
    """Monotone mapping score -> probability by pool-adjacent-violators."""

    def fit(self, s: np.ndarray, y: np.ndarray) -> "Isotonic":
        o = np.argsort(s)
        xs, ys = s[o], y[o].astype(float)
        blocks = [[ys[i], 1.0, xs[i], xs[i]] for i in range(len(ys))]
        out: list[list[float]] = []
        for b in blocks:
            out.append(b)
            while len(out) > 1 and out[-2][0] / out[-2][1] > out[-1][0] / out[-1][1]:
                v2, w2, lo2, hi2 = out.pop()
                v1, w1, lo1, hi1 = out.pop()
                out.append([v1 + v2, w1 + w2, lo1, hi2])
        self.x = np.array([(b[2] + b[3]) / 2 for b in out])
        self.p = np.array([b[0] / b[1] for b in out])
        return self

    def __call__(self, s) -> np.ndarray:
        return np.interp(np.atleast_1d(np.asarray(s, dtype=float)), self.x, self.p)


def brier(p: np.ndarray, y: np.ndarray) -> float:
    return float(np.mean((p - y) ** 2))


def logloss(p: np.ndarray, y: np.ndarray) -> float:
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def reliability(p: np.ndarray, y: np.ndarray, bins: int = 10) -> list[dict]:
    edges = np.linspace(0, 1, bins + 1)
    out = []
    for a, b in zip(edges[:-1], edges[1:]):
        m = (p >= a) & (p < b if b < 1 else p <= b)
        if m.sum():
            out.append({"bin": f"{a:.1f}-{b:.1f}", "n": int(m.sum()), "predicted": round(float(p[m].mean()), 4),
                        "observed": round(float(y[m].mean()), 4)})
    return out


def ece(p: np.ndarray, y: np.ndarray, bins: int = 10) -> float:
    r = reliability(p, y, bins)
    n = len(p)
    return float(sum(x["n"] / n * abs(x["predicted"] - x["observed"]) for x in r)) if n else float("nan")


def auc(p: np.ndarray, y: np.ndarray) -> float:
    pos, neg = p[y == 1], p[y == 0]
    if not len(pos) or not len(neg):
        return float("nan")
    ranks = np.argsort(np.argsort(np.r_[pos, neg])) + 1
    return float((ranks[: len(pos)].sum() - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg)))
