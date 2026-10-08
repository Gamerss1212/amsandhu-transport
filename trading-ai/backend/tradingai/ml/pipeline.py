"""Leakage-safe ML research (sections 156, 158-160, 195-197).

Target (never "will the next candle be green"): starting at bar i's close and entering at bar i+1's open, does price
reach +k ATR before -k ATR within H bars, after round-trip costs? (a "triple-barrier" label). A label at bar i uses
bars i+1..i+H, so:
* PURGING: training samples whose label window reaches into the test period are dropped;
* EMBARGO: a further `embargo` bars after each test period are excluded from the next training set.

Walk-forward: train -> calibrate on a validation slice -> score the following test slice; parameters frozen per fold.
Every fold compares the model with the base-rate baseline. The verdict "model beats baseline out of sample" is
reported only when it is true on log-loss AND Brier score over all test folds; otherwise the model is REJECTED and no
probability from it is shown anywhere.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from tradingai.features import indicators as I
from tradingai.features.registry import FeatureFrame
from tradingai.ml.models import (BoostedStumps, LogisticModel, Platt, PriorModel, auc, brier, ece, logloss,
                                 reliability)

DEFAULT_FEATURES = ["rsi_14", "roc_10", "zscore_20", "adx_14", "bb_pctb_20", "natr_14", "vol_ratio_10_60",
                    "linreg_slope_20", "dist_sma_50_atr", "ibs", "autocorr_60", "vol_pctrank_20"]


def triple_barrier(ff: FeatureFrame, horizon: int = 20, k: float = 1.5, cost_frac: float = 0.0) -> tuple[np.ndarray, np.ndarray]:
    """(label, valid): label 1 if +k ATR (net of cost) is reached before -k ATR within `horizon` bars, else 0.
    Entry is the NEXT bar's open. valid is False where the window runs past the data."""
    n = len(ff.c)
    a = I.atr(ff.h, ff.l, ff.c, 14)
    y = np.zeros(n)
    valid = np.zeros(n, dtype=bool)
    for i in range(n - horizon - 1):
        if not np.isfinite(a[i]):
            continue
        entry = ff.o[i + 1]
        up = entry + k * a[i] + cost_frac * entry
        dn = entry - k * a[i]
        hit = 0
        for j in range(i + 1, i + 1 + horizon):
            if ff.l[j] <= dn:
                hit = -1
                break
            if ff.h[j] >= up:
                hit = 1
                break
        y[i] = 1.0 if hit == 1 else 0.0
        valid[i] = True
    return y, valid


@dataclass
class FoldResult:
    fold: int
    train: tuple[int, int]
    test: tuple[int, int]
    n_train: int
    n_test: int
    model_logloss: float
    base_logloss: float
    model_brier: float
    base_brier: float
    model_auc: float


def walk_forward(ff: FeatureFrame, *, model: str = "logistic", features: list[str] | None = None, folds: int = 4,
                 horizon: int = 20, k: float = 1.5, cost_frac: float = 0.001, embargo: int | None = None,
                 min_train: int = 300) -> dict:
    names = [f for f in (features or DEFAULT_FEATURES) if ff.status(f) == "OK"]
    X = ff.matrix(names)
    y, valid = triple_barrier(ff, horizon, k, cost_frac)
    good = valid & np.all(np.isfinite(X), axis=1)
    n = len(y)
    emb = embargo if embargo is not None else horizon
    first = int(np.argmax(good)) if good.any() else n
    usable = n - first
    if usable < min_train + 200:
        return {"status": "insufficient_data", "needed_bars": min_train + 200 + first, "have": n}
    test_len = (usable - min_train) // folds
    results, all_p, all_y, all_base = [], [], [], []
    calibrator = None
    for k_ in range(folds):
        t0 = first + min_train + k_ * test_len
        t1 = t0 + test_len if k_ < folds - 1 else n
        # purge + embargo: a training label at i covers bars i+1..i+horizon, so training stops `horizon` bars before
        # the test window, plus an extra `emb`-bar gap (forward-only walk-forward: no training data after the test)
        train_idx = np.flatnonzero(good[:max(0, t0 - horizon - 1 - emb)])
        test_idx = np.arange(t0, t1)[good[t0:t1]]
        if len(train_idx) < 100 or len(test_idx) < 30:
            continue
        cut = int(len(train_idx) * 0.8)
        fit_idx, cal_idx = train_idx[:cut], train_idx[cut:]
        m = (BoostedStumps() if model == "boosted" else LogisticModel()).fit(X[fit_idx], y[fit_idx])
        # Platt scaling: smoother than isotonic on small calibration slices (isotonic produced 0/1 probabilities)
        iso = Platt().fit(m.predict_proba(X[cal_idx]), y[cal_idx])
        p = np.clip(iso(m.predict_proba(X[test_idx])), 0.01, 0.99)
        b = PriorModel().fit(None, y[train_idx]).predict_proba(test_idx)
        yt = y[test_idx]
        results.append(FoldResult(k_, (int(train_idx[0]), int(train_idx[-1])), (int(t0), int(t1)), len(train_idx),
                                  len(test_idx), logloss(p, yt), logloss(b, yt), brier(p, yt), brier(b, yt),
                                  auc(p, yt)))
        all_p.append(p)
        all_y.append(yt)
        all_base.append(b)
        calibrator = (m, iso)
    if not results:
        return {"status": "insufficient_data", "have": n}
    P, Y, B = np.concatenate(all_p), np.concatenate(all_y), np.concatenate(all_base)
    beats = logloss(P, Y) < logloss(B, Y) and brier(P, Y) < brier(B, Y)
    return {
        "status": "ok", "model": model, "features": names, "target": f"+{k} ATR before -{k} ATR within {horizon} bars, "
        f"net of {cost_frac:.2%} round-trip cost; entry at next open", "folds": [vars(r) for r in results],
        "oos": {"n": int(len(Y)), "base_rate": round(float(Y.mean()), 4), "model_logloss": round(logloss(P, Y), 5),
                "base_logloss": round(logloss(B, Y), 5), "model_brier": round(brier(P, Y), 5),
                "base_brier": round(brier(B, Y), 5), "auc": round(auc(P, Y), 4), "ece": round(ece(P, Y), 4),
                "reliability": reliability(P, Y)},
        "beats_baseline": bool(beats),
        "verdict": ("ACCEPTED: beats the base rate out of sample on log-loss and Brier" if beats else
                    "REJECTED: does not beat the base rate out of sample; its probabilities are not shown"),
        "purge_bars": horizon, "embargo_bars": emb,
        "_live": calibrator if beats else None,
    }
