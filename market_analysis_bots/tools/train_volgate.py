"""Fit and measure the volatility gate (writes mab/models/volgate.json and docs/VOLGATE.md).

    python tools/train_volgate.py --cache DIR

Data (free): Coinbase hourly bars for BTC, ETH, SOL and the six listed memecoins (up to five years);
Yahoo hourly bars for SPY, QQQ, NVDA, AAPL, TSLA, IWM (about two years, the endpoint's limit).

Label at hour i: the range of the next H hours (crypto H=12, stocks H=7, about one session) divided
by the close, compared with the same quantity over that market's previous 90 days (only windows
already finished at i): top third = LOUD, bottom third = QUIET. Features are causal (mab.volgate).
Split by time: fit on the first 60%, choose thresholds on the next 20% (smallest threshold whose
precision reaches the target with at least 1% of bars flagged), measure once on the last 20%.
A one-feature model (ATR ratio only) is fitted the same way as a baseline. Needs numpy (offline only).
"""

import argparse
import datetime
import json
import os
import pickle
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from mab import volgate as VG  # noqa: E402

CRYPTO = ["BTC-USD", "ETH-USD", "SOL-USD", "DOGE-USD", "SHIB-USD", "PEPE-USD", "BONK-USD", "WIF-USD", "FLOKI-USD"]
STOCKS = ["SPY", "QQQ", "NVDA", "AAPL", "TSLA", "IWM"]
TARGET_PRECISION = 0.65       # about twice the base rate of a third; tested on the untouched segment
MIN_COVERAGE = 0.02


def fetch(cache):
    path = os.path.join(cache, "hourly.pkl")
    if os.path.exists(path):
        with open(path, "rb") as fh:
            return pickle.load(fh)
    from mab.data.adapters import Coinbase, Yahoo
    from mab.net import Http
    http = Http(limits={"api.exchange.coinbase.com": (2.0, 3), "query1.finance.yahoo.com": (1.0, 2)})
    cb, yh = Coinbase(http), Yahoo(http)
    data = {}
    for s in CRYPTO:
        out, end = {}, None
        for _ in range(160):                                   # 160 x 300 hours = 5.5 years at most
            try:
                batch = cb.bars(s, "1h", limit=300, end_ms=end)
            except Exception as e:
                print("error", s, e)
                break
            if not batch:
                break
            for b in batch:
                out[b.event_time] = b
            oldest = min(b.event_time for b in batch)
            if end is not None and oldest >= end:
                break
            end = oldest - 1
        data[("crypto", s)] = [out[k] for k in sorted(out)]
        print(s, len(data[("crypto", s)]), flush=True)
    for s in STOCKS:
        try:
            data[("stock", s)] = yh.bars(s, "1h", limit=10 ** 6)
        except Exception as e:
            print("error", s, e)
        print(s, len(data.get(("stock", s), [])), flush=True)
    os.makedirs(cache, exist_ok=True)
    with open(path, "wb") as fh:
        pickle.dump(data, fh)
    return data


def dataset(bars_list, horizon):
    X, yl, yq, T = [], [], [], []
    for bars in bars_list:
        b = VG.Bars([x.event_time for x in bars], [x.open for x in bars], [x.high for x in bars],
                    [x.low for x in bars], [x.close for x in bars], [x.volume for x in bars], horizon)
        fr = [VG.future_range(b, i, horizon) for i in range(len(bars))]
        hist = []                                               # (index, future range) of finished windows
        for i in range(len(bars)):
            j = i - horizon
            if j >= 0 and fr[j] is not None:
                hist.append(fr[j])
            if len(hist) > 90 * 24:
                hist.pop(0)
            f = VG.features(b, i)
            if f is None or fr[i] is None or len(hist) < 30 * 24:
                continue
            srt = sorted(hist)
            lo, hi = srt[len(srt) // 3], srt[2 * len(srt) // 3]
            X.append(f)
            yl.append(1 if fr[i] > hi else 0)
            yq.append(1 if fr[i] < lo else 0)
            T.append(b.t[i])
    return np.array(X), np.array(yl), np.array(yq), np.array(T)


def fit(X, y, l2=1e-3, iters=400, lr=0.5):
    w = np.zeros(X.shape[1])
    for _ in range(iters):
        p = 1 / (1 + np.exp(-np.clip(X @ w, -30, 30)))
        g = X.T @ (p - y) / len(y) + l2 * np.r_[0, w[1:]]
        w -= lr * g
    return w


def auc(p, y):
    order = np.argsort(p)
    ranks = np.empty(len(p))
    ranks[order] = np.arange(1, len(p) + 1)
    pos = y == 1
    n1, n0 = pos.sum(), (~pos).sum()
    return float((ranks[pos].sum() - n1 * (n1 + 1) / 2) / (n1 * n0)) if n1 and n0 else None


def threshold(p, y, target):
    """Lowest threshold whose validation precision reaches the target while flagging at least
    MIN_COVERAGE of the hours; 1.01 (never fires) if no threshold does."""
    for t in np.arange(0.3, 0.99, 0.01):
        m = p >= t
        if m.mean() < MIN_COVERAGE:
            break
        if y[m].mean() >= target:
            return float(round(t, 2))
    return 1.01


def evaluate(p, y, t):
    m = p >= t
    return {"auc": auc(p, y), "flagged_share": float(m.mean()), "flagged": int(m.sum()),
            "precision": float(y[m].mean()) if m.any() else None, "base_rate": float(y.mean())}


def export_gbm(m):
    """sklearn HistGradientBoostingClassifier -> {"base": float, "trees": [[node, ...], ...]} for mab.volgate."""
    trees = []
    for pred in m._predictors:
        nodes = []
        for nd in pred[0].nodes:
            if nd["is_leaf"]:
                nodes.append([-1, float(nd["value"])])
            else:
                nodes.append([int(nd["feature_idx"]), float(nd["num_threshold"]), int(nd["left"]), int(nd["right"]),
                              bool(nd["missing_go_to_left"])])
        trees.append(nodes)
    return {"base": float(np.ravel(m._baseline_prediction)[0]), "trees": trees}


def fit_gbm(X, y):
    from sklearn.ensemble import HistGradientBoostingClassifier
    m = HistGradientBoostingClassifier(max_iter=200, learning_rate=0.05, max_leaf_nodes=15, min_samples_leaf=200,
                                       l2_regularization=1.0, random_state=0)
    m.fit(X, y)
    return m


def train(asset, bars_list, horizon):
    X, yl, yq, T = dataset(bars_list, horizon)
    order = np.argsort(T)
    X, yl, yq, T = X[order], yl[order], yq[order], T[order]
    n = len(T)
    a, b = int(n * 0.6), int(n * 0.8)
    mu, sd = X[:a].mean(0), X[:a].std(0)
    mu[0], sd[0] = 0.0, 1.0
    Z = (X - mu) / np.where(sd == 0, 1, sd)
    Z[:, 0] = 1.0
    res = {"horizon_hours": horizon, "rows": n, "period": [datetime.datetime.utcfromtimestamp(T[0] / 1000).strftime("%Y-%m-%d"),
                                                          datetime.datetime.utcfromtimestamp(T[-1] / 1000).strftime("%Y-%m-%d")],
           "split": {"fit": a, "validation": b - a, "test": n - b}, "mean": mu.tolist(), "std": sd.tolist(),
           "target_precision": TARGET_PRECISION, "features": VG.FEATURES}
    for name, y in (("loud", yl), ("quiet", yq)):
        w = fit(Z[:a], y[:a])
        pv, pt = 1 / (1 + np.exp(-(Z[a:b] @ w))), 1 / (1 + np.exp(-(Z[b:] @ w)))
        t = threshold(pv, y[a:b], TARGET_PRECISION)
        wb_ = fit(Z[:a][:, :2], y[:a])                           # baseline: ATR ratio only
        pb = 1 / (1 + np.exp(-(Z[b:][:, :2] @ wb_)))
        res[f"w_{name}"], res[f"t_{name}"] = w.tolist(), t
        res[f"test_{name}"] = evaluate(pt, y[b:], t)
        res[f"validation_{name}"] = evaluate(pv, y[a:b], t)
        res[f"baseline_auc_{name}"] = auc(pb, y[b:])
        # reliability: actual rate by predicted-probability decile on the test segment
        bins = []
        for k in range(10):
            m = (pt >= k / 10) & (pt < (k + 1) / 10)
            bins.append({"p": (k + 0.5) / 10, "n": int(m.sum()), "actual": float(y[b:][m].mean()) if m.any() else None})
        res[f"reliability_{name}"] = bins
    # gradient-boosted trees: kept only if they beat the logistic model on the VALIDATION segment
    try:
        gb = {}
        for name, y in (("loud", yl), ("quiet", yq)):
            m = fit_gbm(X[:a], y[:a])
            gb[name] = (m, auc(m.predict_proba(X[a:b])[:, 1], y[a:b]),
                        auc(1 / (1 + np.exp(-(Z[a:b] @ np.array(res[f"w_{name}"])))), y[a:b]))
        if all(v[1] > v[2] for v in gb.values()):
            res["kind"] = "gbm"
            for name, y in (("loud", yl), ("quiet", yq)):
                m = gb[name][0]
                ex = export_gbm(m)
                res[f"trees_{name}"], res[f"base_{name}"] = ex["trees"], ex["base"]
                # the exported pure-Python ensemble must reproduce sklearn's scores
                probe = X[b:b + 200]
                mine = np.array([VG._tree_raw(ex["trees"], ex["base"], list(r)) for r in probe])
                assert np.allclose(mine, m.decision_function(probe), atol=1e-6), "exported trees disagree with sklearn"
                pv, pt = m.predict_proba(X[a:b])[:, 1], m.predict_proba(X[b:])[:, 1]
                t = threshold(pv, y[a:b], TARGET_PRECISION)
                res[f"t_{name}"] = t
                res[f"test_{name}"] = evaluate(pt, y[b:], t)
                res[f"validation_{name}"] = evaluate(pv, y[a:b], t)
            res["logit_validation_auc"] = {k: v[2] for k, v in gb.items()}
            res["gbm_validation_auc"] = {k: v[1] for k, v in gb.items()}
        else:
            res["kind"] = "logit"
            res["gbm_validation_auc"] = {k: v[1] for k, v in gb.items()}
    except ImportError:
        res["kind"] = "logit"
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", required=True)
    a = ap.parse_args()
    t0 = time.time()
    data = fetch(a.cache)
    model = {"generated": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()),
             "crypto": train("crypto", [v for k, v in data.items() if k[0] == "crypto" and len(v) > 2000], 12),
             "stock": train("stock", [v for k, v in data.items() if k[0] == "stock" and len(v) > 1000], 7)}
    os.makedirs(os.path.dirname(VG.MODEL_PATH), exist_ok=True)
    with open(VG.MODEL_PATH, "w") as fh:
        json.dump(model, fh, indent=1)
    L = ["# Volatility gate: measured results\n", f"Generated {model['generated']} by `tools/train_volgate.py`. "
         "Chronological split: fit 60%, thresholds chosen on the next 20%, measured once on the last 20% (test). "
         f"Thresholds are the lowest that reached {int(TARGET_PRECISION * 100)}% precision on validation.\n"]
    for asset in ("crypto", "stock"):
        m = model[asset]
        L.append(f"## {asset} (next {m['horizon_hours']} hours; {m['rows']:,} hourly rows, {m['period'][0]} to {m['period'][1]}; "
                 f"model: {'gradient-boosted trees' if m.get('kind') == 'gbm' else 'logistic regression'})\n")
        L.append("| Forecast | Test AUC | Baseline AUC (ATR ratio only) | Threshold | Share of hours flagged (test) | Right when flagged (test) | Base rate |")
        L.append("|---|---|---|---|---|---|---|")
        for name in ("loud", "quiet"):
            t = m[f"test_{name}"]
            L.append(f"| {name.upper()} | {t['auc']:.3f} | {m[f'baseline_auc_{name}']:.3f} | {m[f't_{name}']:.2f} | "
                     f"{100 * t['flagged_share']:.1f}% ({t['flagged']:,}) | "
                     + (f"{100 * t['precision']:.1f}%" if t["precision"] is not None else "-") + f" | {100 * t['base_rate']:.1f}% |")
        L.append("")
    L.append("A LOUD or QUIET reading is about how much the market will move, never which way. Coin flip AUC = 0.500.\n")
    with open(os.path.join(ROOT, "docs", "VOLGATE.md"), "w") as fh:
        fh.write("\n".join(L))
    print("\n".join(L))
    print(f"{(time.time() - t0) / 60:.1f} min")


if __name__ == "__main__":
    main()
