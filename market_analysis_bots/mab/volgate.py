"""Volatility gate: will the next hours be LOUD, NORMAL or QUIET?

Direction is barely predictable on these markets; the size of the coming move is. This gate
forecasts whether the range of the next `horizon` hourly bars will be in the top third (LOUD) or
the bottom third (QUIET) of what that market has recently done, from causal features of completed
hourly bars only:

    atr_ratio      ATR(14) against its 7-day mean                (volatility clusters)
    bbw_ratio      Bollinger width against its 7-day mean         (compression before expansion)
    rvol6          volume of the last 6 hours against the 7-day hourly mean
    rv_ratio       realized volatility 24h against 168h
    range12        the last 12 hours' range against the 7-day mean 12-hour range
    move12         |12-hour return| in ATRs
    shock1         the last bar's range in ATRs
    hour_sin/cos   time of day (UTC)                              (session liquidity)
    weekend        Saturday or Sunday (UTC)
    rv6_ratio      realized volatility 6h against 168h            (the very latest burst)
    range72        the last 72 hours' range against the 7-day mean 72-hour range
    hour_profile   how big the next hours usually are when they start at this hour (last 14 days,
                   finished windows only) against all hours                (daily volatility rhythm)
    vol24_z        volume of the last 24 hours against the 7-day mean, as a z-score

Two models (LOUD vs not, QUIET vs not) are fitted offline on history: gradient-boosted trees where
they beat a logistic regression on the validation segment (crypto), logistic regression otherwise
(tools/train_volgate.py) with a chronological split; decision thresholds are chosen on the
validation segment so that a declared LOUD or QUIET is right at least `target_precision` of the
time, and the untouched test segment measures what the gate really delivers. The fitted
coefficients and those measurements ship in mab/models/volgate.json. Prediction is pure Python.

How the fleet uses it: QUIET blocks new entries (fees are fixed, the range is not); LOUD cuts the
size to 0.6x (bigger swings against the same stop). The gate never says which way.
"""

from __future__ import annotations

import json
import math
import os
from typing import Dict, List, Optional

FEATURES = ["bias", "atr_ratio", "bbw_ratio", "rvol6", "rv_ratio", "range12", "move12", "shock1",
            "hour_sin", "hour_cos", "weekend", "rv6_ratio", "range72", "hour_profile", "vol24_z"]
HORIZON = {"crypto": 12, "stock": 7}
WEEK = 168
HERE = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(HERE, "models", "volgate.json")


def _mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def _atr_series(h, l, c, n=14):
    out, prev = [None] * len(c), None
    tr = [None] * len(c)
    for i in range(len(c)):
        tr[i] = h[i] - l[i] if i == 0 else max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1]))
        if i + 1 == n:
            prev = sum(tr[:n]) / n
        elif i + 1 > n:
            prev = (prev * (n - 1) + tr[i]) / n
        out[i] = prev
    return out


class Bars:
    """Hourly OHLCV arrays plus the rolling series the features need (computed once, causally)."""

    def __init__(self, t: List[int], o, h, l, c, v, horizon: int = 12):
        self.t, self.o, self.h, self.l, self.c, self.v = t, o, h, l, c, v
        n = len(c)
        self.atr = _atr_series(h, l, c)
        self.lr = [None] + [math.log(c[i] / c[i - 1]) if c[i - 1] and c[i] else None for i in range(1, n)]
        self.bbw = [None] * n
        for i in range(19, n):
            w = c[i - 19:i + 1]
            m = sum(w) / 20
            sd = math.sqrt(sum((x - m) ** 2 for x in w) / 20)
            self.bbw[i] = 4 * sd / m if m else None
        self.r12 = [None] * n
        for i in range(11, n):
            self.r12[i] = (max(h[i - 11:i + 1]) - min(l[i - 11:i + 1])) / c[i] if c[i] else None
        self.r72 = [None] * n
        for i in range(71, n):
            self.r72[i] = (max(h[i - 71:i + 1]) - min(l[i - 71:i + 1])) / c[i] if c[i] else None
        self.horizon = horizon
        # forward range of each bar (a label); features only ever read windows already finished
        self.fwd = [None] * n
        for i in range(n - horizon):
            self.fwd[i] = (max(h[i + 1:i + horizon + 1]) - min(l[i + 1:i + horizon + 1])) / c[i] if c[i] else None

    @classmethod
    def from_frame(cls, f, horizon: int = 12):
        return cls(f.t, f.o, f.h, f.l, f.c, f.v, horizon)


def features(b: Bars, i: int) -> Optional[List[float]]:
    """Feature vector at hourly bar i (uses bars up to and including i only)."""
    if i < WEEK + 24 or b.atr[i] is None or not b.c[i]:
        return None
    atr_m = _mean(b.atr[i - WEEK + 1:i + 1])
    bbw_m = _mean(b.bbw[i - WEEK + 1:i + 1])
    vol_m = _mean(b.v[i - WEEK + 1:i + 1])
    r12_m = _mean(b.r12[i - WEEK + 1:i + 1])
    rv24 = [x for x in b.lr[i - 23:i + 1] if x is not None]
    rv168 = [x for x in b.lr[i - WEEK + 1:i + 1] if x is not None]
    if not (atr_m and bbw_m and r12_m and len(rv24) > 10 and len(rv168) > 100) or b.bbw[i] is None or b.r12[i] is None:
        return None
    sd = lambda xs: math.sqrt(sum(x * x for x in xs) / len(xs)) or 1e-12  # noqa: E731
    lg = lambda x: math.log(max(1e-6, x))  # noqa: E731
    hour = (b.t[i] // 3_600_000) % 24
    dow = ((b.t[i] // 86_400_000) + 3) % 7                  # 0 = Monday (1970-01-01 was a Thursday)
    vol6 = sum(b.v[i - 5:i + 1]) / 6
    rv6 = [x for x in b.lr[i - 5:i + 1] if x is not None]
    r72_m = _mean(b.r72[i - WEEK + 1:i + 1])
    # daily rhythm: finished forward windows (j <= i - horizon) that started at this hour, last 14 days
    H = b.horizon
    same = [b.fwd[j] for j in range(i - H, max(-1, i - 14 * 24 - 1), -1) if b.fwd[j] is not None and (b.t[j] // 3_600_000) % 24 == hour]
    allf = [b.fwd[j] for j in range(max(0, i - 14 * 24), i - H + 1) if b.fwd[j] is not None]
    prof = (sum(same) / len(same)) / (sum(allf) / len(allf)) if same and allf and sum(allf) else 1.0
    v24 = b.v[i - 23:i + 1]
    vw = b.v[i - WEEK + 1:i + 1]
    vm = sum(vw) / len(vw)
    vsd = math.sqrt(sum((x - vm) ** 2 for x in vw) / len(vw)) or 1e-12
    return [1.0,
            lg(b.atr[i] / atr_m), lg(b.bbw[i] / bbw_m), lg((vol6 + 1e-12) / (vol_m + 1e-12)) if vol_m else 0.0,
            lg(sd(rv24) / sd(rv168)), lg(b.r12[i] / r12_m),
            min(6.0, abs(b.c[i] - b.c[i - 12]) / b.atr[i]), min(6.0, (b.h[i] - b.l[i]) / b.atr[i]),
            math.sin(2 * math.pi * hour / 24), math.cos(2 * math.pi * hour / 24), 1.0 if dow >= 5 else 0.0,
            lg(sd(rv6) / sd(rv168)) if len(rv6) >= 4 else 0.0,
            lg(b.r72[i] / r72_m) if (b.r72[i] and r72_m) else 0.0,
            lg(prof), max(-4.0, min(4.0, (sum(v24) / 24 - vm) / vsd))]


def future_range(b: Bars, i: int, horizon: int) -> Optional[float]:
    """Range of the next `horizon` bars relative to the close at i (a label: uses the future)."""
    if i + horizon >= len(b.c) or not b.c[i]:
        return None
    return (max(b.h[i + 1:i + horizon + 1]) - min(b.l[i + 1:i + horizon + 1])) / b.c[i]


def _sig(z):
    return 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, z))))


def _tree_raw(trees, base, x):
    """Raw score of an exported gradient-boosted tree ensemble (pure Python)."""
    z = base
    for nodes in trees:
        k = 0
        while True:
            nd = nodes[k]
            if nd[0] < 0:                                   # leaf: [-1, value]
                z += nd[1]
                break
            f, thr, left, right, miss_left = nd
            v = x[f]
            k = (left if miss_left else right) if v is None or v != v else (left if v <= thr else right)
    return z


class VolGate:
    def __init__(self, model: Optional[dict] = None):
        self.model = model if model is not None else self.load()
        self.version = self.model.get("generated") and f"volgate {self.model.get('generated')}"
        self._rel = {}
        for asset, m in self.model.items():
            if not isinstance(m, dict):
                continue
            for kind in ("loud", "quiet"):
                r = m.get(f"reliability_{kind}")
                if isinstance(r, str):
                    try:
                        import ast
                        r = ast.literal_eval(r)
                    except (ValueError, SyntaxError):
                        r = None
                if r:
                    self._rel[(asset, kind)] = r

    def evidence(self, asset: str, kind: str, p: Optional[float]) -> Optional[dict]:
        """What held-out testing says about readings like this one: the observed rate in the test period for
        readings in the same probability band, with its sample size, the gate's precision when it flags, and
        the base rate. This, not the raw model output, is what may be shown as a probability."""
        m = self.model.get(asset) or {}
        rel = self._rel.get((asset, kind))
        if p is None or not rel:
            return None
        band = min(rel, key=lambda r: abs(r["p"] - p))
        test = m.get(f"test_{kind}") or {}
        return {"observed_rate": band.get("actual"), "n": band.get("n"), "band": band.get("p"),
                "precision_when_flagged": test.get("precision"), "flagged_n": test.get("flagged"),
                "base_rate": test.get("base_rate"), "auc": test.get("auc"), "period": m.get("period")}

    @staticmethod
    def load(path: str = MODEL_PATH) -> dict:
        try:
            with open(path, encoding="utf-8") as fh:
                return json.load(fh)
        except (OSError, ValueError):
            return {}

    def ready(self, asset: str) -> bool:
        return bool(self.model.get(asset))

    def read(self, b: Bars, i: int, asset: str = "crypto") -> dict:
        """Bars must be built with the asset's horizon (HORIZON[asset]) for hour_profile to match training."""
        """{"state": LOUD|NORMAL|QUIET|UNKNOWN, "p_loud", "p_quiet"} at hourly bar i."""
        m = self.model.get(asset)
        f = features(b, i) if m else None
        if not m or f is None:
            return {"state": "UNKNOWN", "p_loud": None, "p_quiet": None}
        if m.get("kind") == "gbm":
            pl = _sig(_tree_raw(m["trees_loud"], m["base_loud"], f))
            pq = _sig(_tree_raw(m["trees_quiet"], m["base_quiet"], f))
        else:
            mu, sd = m["mean"], m["std"]
            x = [f[0]] + [(f[k] - mu[k]) / sd[k] if sd[k] else 0.0 for k in range(1, len(f))]
            pl = _sig(sum(w * v for w, v in zip(m["w_loud"], x)))
            pq = _sig(sum(w * v for w, v in zip(m["w_quiet"], x)))
        state = "LOUD" if pl >= m["t_loud"] else ("QUIET" if pq >= m["t_quiet"] else "NORMAL")
        return {"state": state, "p_loud": round(pl, 4), "p_quiet": round(pq, 4),
                "evidence": {"loud": self.evidence(asset, "loud", pl), "quiet": self.evidence(asset, "quiet", pq)}}
