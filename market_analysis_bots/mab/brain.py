"""Fleet Brain: one learning coordinator that every bot in the fleet is connected to.

What it does
------------
1. **Listens to every bot.** Each completed bar, every bot reports whether its entry rule wants
   long, short or nothing on its instrument. The brain keeps this as a live *consensus* per
   instrument (how many of the connected bots lean each way).
2. **Scores every entry before it is sent.** For each entry intent it combines
   - what has been learned about that strategy (and that strategy on that instrument): a Bayesian
     estimate of its average result per trade in R, after costs, and
   - a shared context model (online logistic regression) trained on the closed trades of ALL bots:
     trend alignment, RSI, volatility percentile, distance from VWAP, relative volume, time of day,
     market type and the fleet consensus.
   It then approves, resizes (0.5x-1.5x) or vetoes the trade.
3. **Learns from every closed trade** (self-learning): the strategy and strategy-instrument
   estimates are updated with the trade's R, the context model takes a gradient step, and the
   brain's own calibration (predicted vs actual win rate) is tracked so you can see whether its
   predictions are any good.

How it starts
-------------
Priors come from the batch evaluation (strategies/results): each strategy's measured
expectancy after realistic costs, weighted as a limited number of pseudo-trades so live paper
results can overturn it. Decisions use Thompson sampling (a random draw from the uncertainty of
each estimate), so strategies with few trades still get tried and the brain keeps exploring
instead of freezing on early noise.

Honesty
-------
The brain can only learn what paper trading and history show. Its value is measured, not
assumed: the dashboard reports its calibration, how many trades it vetoed or resized, and how
trades it scored highly actually performed. Setting `brain.mode` to "advisory" keeps it
learning and scoring without touching orders; "off" disconnects it.
"""

from __future__ import annotations

import gzip
import json
import math
import os
import random
import threading
import time
from collections import deque
from typing import Dict, List, Optional

from mab import expr

FEATURES = ["bias", "trend_aligned", "rsi_aligned", "vol_percentile", "vwap_distance", "rel_volume", "tod_sin",
            "tod_cos", "consensus_aligned", "is_stock", "is_long"]
R_CLIP = 3.0                 # trade R is winsorised before learning, so one extreme trade cannot dominate
PRIOR_WEIGHT = 0.5           # pseudo-trades per backtest trade
PRIOR_CAP = 25.0             # at most this many pseudo-trades from history
R_VAR = 1.0                  # assumed variance of per-trade R before data says otherwise


def _post() -> dict:
    return {"n": 0, "sum": 0.0, "sum2": 0.0, "prior_mean": 0.0, "prior_n": 0.0}


class FleetBrain:
    def __init__(self, mode: str = "active", seed: int = 7, veto_edge: float = -0.05, min_evidence: float = 8.0):
        self.mode = mode
        self.veto_edge = veto_edge
        self.min_evidence = min_evidence
        self.rng = random.Random(seed)
        self.post: Dict[str, dict] = {}
        self.w = [0.0] * len(FEATURES)
        self.lr, self.l2 = 0.05, 1e-3
        self.calib = [[0, 0] for _ in range(10)]          # predicted win-probability decile -> [trades, wins]
        self.consensus: Dict[str, Dict[str, tuple]] = {}   # instrument -> bot -> (state, time)
        self.pending: Dict[str, dict] = {}                 # bot -> context of its open entry
        self.recent: deque = deque(maxlen=300)             # decisions and lessons, newest last
        self.stats = {"scored": 0, "approved": 0, "vetoed": 0, "resized": 0, "learned": 0, "wins": 0,
                      "sum_r": 0.0, "hi_score_trades": 0, "hi_score_sum_r": 0.0, "lo_score_trades": 0,
                      "lo_score_sum_r": 0.0, "brier_sum": 0.0, "prior_strategies": 0}
        self.lock = threading.RLock()
        self.connected: set = set()

    # ------------------------------------------------------------------ priors from the batch evaluation
    def load_priors(self, path: str) -> int:
        if not path or not os.path.exists(path):
            gz = (path or "") + ".gz"
            if not os.path.exists(gz):
                return 0
            path = gz
        opener = gzip.open if path.endswith(".gz") else open
        with opener(path, "rt") as fh:
            d = json.load(fh)
        n = 0
        with self.lock:
            for sid, s in d.get("strategies", {}).items():
                rows = [x for x in s.get("runs", []) if x.get("cost") in ("retail_kraken", "base") and x["full"].get("trades")]
                if not rows:
                    continue
                tot = sum(x["full"]["trades"] for x in rows)
                mean = sum(max(-R_CLIP, min(R_CLIP, x["full"]["expectancy_r"] or 0)) * x["full"]["trades"] for x in rows) / tot
                self._set_prior(f"S:{sid}", mean, tot)
                for x in rows:
                    self._set_prior(f"SI:{sid}|{x['instrument']}",
                                    max(-R_CLIP, min(R_CLIP, x["full"]["expectancy_r"] or 0)), x["full"]["trades"])
                n += 1
            self.stats["prior_strategies"] = n
        return n

    def _set_prior(self, key, mean, trades):
        p = self.post.setdefault(key, _post())
        p["prior_mean"], p["prior_n"] = float(mean), min(PRIOR_CAP, PRIOR_WEIGHT * float(trades))

    # ------------------------------------------------------------------ connection and consensus
    def connect(self, bot_id: str):
        self.connected.add(bot_id)

    def observe(self, bot_id: str, instrument: str, state: int, t: int):
        """A bot reports its entry-rule state on its instrument (+1 long, -1 short, 0 none)."""
        with self.lock:
            self.consensus.setdefault(instrument, {})[bot_id] = (state, t)

    def consensus_of(self, instrument: str, exclude: Optional[str] = None, max_age_ms: int = 3_600_000) -> dict:
        now = int(time.time() * 1000)
        votes = [s for b, (s, t) in self.consensus.get(instrument, {}).items() if b != exclude and now - t <= max_age_ms]
        long_, short_ = sum(1 for s in votes if s > 0), sum(1 for s in votes if s < 0)
        return {"bots": len(votes), "long": long_, "short": short_,
                "net": (long_ - short_) / len(votes) if votes else 0.0}

    # ------------------------------------------------------------------ estimates
    def estimate(self, key: str):
        p = self.post.get(key)
        if p is None:
            return None
        n_eff = p["n"] + p["prior_n"]
        if n_eff <= 0:
            return None
        mean = (p["prior_mean"] * p["prior_n"] + p["sum"]) / n_eff
        var = R_VAR
        if p["n"] >= 5:
            m = p["sum"] / p["n"]
            var = max(0.05, (p["sum2"] / p["n"] - m * m) * p["n"] / (p["n"] - 1))
        return {"mean": mean, "sd": math.sqrt(var / n_eff), "n_eff": n_eff, "n": p["n"]}

    def _combined(self, sid: str, inst: str):
        a, b = self.estimate(f"SI:{sid}|{inst}"), self.estimate(f"S:{sid}")
        if a and b:
            # shrink the specific estimate toward the strategy-wide one by their evidence
            wa, wb = a["n_eff"], 0.5 * b["n_eff"]
            mean = (a["mean"] * wa + b["mean"] * wb) / (wa + wb)
            sd = math.sqrt(1.0 / (1.0 / max(a["sd"], 1e-6) ** 2 + 0.5 / max(b["sd"], 1e-6) ** 2))
            return {"mean": mean, "sd": sd, "n_eff": wa + wb, "n": a["n"]}
        return a or b

    # ------------------------------------------------------------------ context features
    @staticmethod
    def features(frame, i: int, side: int, consensus_net: float) -> List[float]:
        ev = expr.Evaluator(frame)

        def v(e):
            x = ev.series(expr.parse(e))[i]
            return x
        close = frame.c[i]
        ema50, rsi, atr = v("ema(close,50)"), v("rsi(close,14)"), v("atr(14)")
        volp = v("pctrank(atr(14) / close, 200)")
        vw, rv = v("vwap()"), v("rvol(20)")
        tod = frame.tod[i] / 1440.0 * 2 * math.pi
        f = [1.0,
             0.0 if ema50 is None else (1.0 if (close - ema50) * side > 0 else -1.0),
             0.0 if rsi is None else (rsi - 50) / 50 * side,
             0.0 if volp is None else volp / 100 - 0.5,
             0.0 if (vw is None or not atr) else max(-3, min(3, (close - vw) / atr * side)) / 3,
             0.0 if not rv else max(-2, min(2, math.log(rv))) / 2,
             math.sin(tod), math.cos(tod),
             consensus_net * side,
             1.0 if frame.asset_type.startswith("stock") else -1.0,
             1.0 if side > 0 else -1.0]
        return f

    def p_win(self, f: List[float]) -> float:
        z = sum(w * x for w, x in zip(self.w, f))
        return 1 / (1 + math.exp(-max(-30, min(30, z))))

    # ------------------------------------------------------------------ decide
    def score(self, bot_id: str, strategy_id: str, instrument: str, frame, i: int, side: int) -> dict:
        """Decision for an entry intent: {"action": approve|resize|veto, "size": multiplier, ...}."""
        with self.lock:
            cons = self.consensus_of(instrument, exclude=bot_id)
            try:
                f = self.features(frame, i, side, cons["net"])
            except Exception:
                f = [1.0] + [0.0] * (len(FEATURES) - 1)
            p = self.p_win(f)
            base = self._base_rate()
            est = self._combined(strategy_id, instrument)
            prior_mean = est["mean"] if est else 0.0
            sd = est["sd"] if est else 1.0
            n_eff = est["n_eff"] if est else 0.0
            ctx_adj = (p - base) * 1.0 if self.stats["learned"] >= 30 else 0.0
            edge = prior_mean + ctx_adj
            sample = self.rng.gauss(prior_mean, sd) + ctx_adj            # Thompson draw
            action, size = "approve", 1.0
            reason = f"learned edge {edge:+.2f}R (+/-{sd:.2f}, evidence {n_eff:.0f} trades); win chance {100 * p:.0f}%; " \
                     f"fleet consensus {cons['long']} long / {cons['short']} short of {cons['bots']}"
            if self.mode == "active":
                if n_eff >= self.min_evidence and sample < self.veto_edge:
                    action, size = "veto", 0.0
                else:
                    size = max(0.5, min(1.5, 1.0 + 1.5 * edge))
                    if abs(size - 1.0) > 0.05:
                        action = "resize"
            self.stats["scored"] += 1
            self.stats["vetoed" if action == "veto" else "approved"] += 1
            if action == "resize":
                self.stats["resized"] += 1
            dec = {"time": int(time.time() * 1000), "bot_id": bot_id, "strategy_id": strategy_id, "instrument": instrument,
                   "side": side, "p_win": round(p, 4), "edge": round(edge, 4), "sample": round(sample, 4),
                   "sd": round(sd, 4), "evidence": round(n_eff, 1), "action": action, "size": round(size, 3),
                   "mode": self.mode, "reason": reason, "features": [round(x, 4) for x in f]}
            self.recent.append({"kind": "decision", **{k: dec[k] for k in ("time", "bot_id", "strategy_id", "instrument",
                                                                          "side", "p_win", "edge", "action", "size")}})
            if action != "veto":
                self.pending[bot_id] = dec
            return dec

    def _base_rate(self) -> float:
        n = self.stats["learned"]
        return (self.stats["wins"] + 1) / (n + 2)

    # ------------------------------------------------------------------ learn
    def learn(self, bot_id: str, strategy_id: str, instrument: str, r: Optional[float], ctx: Optional[dict] = None):
        """Self-learning step from one closed trade (called for every bot's every trade)."""
        if r is None:
            return
        rc = max(-R_CLIP, min(R_CLIP, float(r)))
        with self.lock:
            ctx = ctx or self.pending.pop(bot_id, None)
            for key in (f"S:{strategy_id}", f"SI:{strategy_id}|{instrument}", "G"):
                p = self.post.setdefault(key, _post())
                p["n"] += 1
                p["sum"] += rc
                p["sum2"] += rc * rc
            win = 1.0 if rc > 0 else 0.0
            self.stats["learned"] += 1
            self.stats["wins"] += int(win)
            self.stats["sum_r"] += rc
            if ctx:
                f, p_hat = ctx["features"], ctx["p_win"]
                g = p_hat - win                                   # logistic-loss gradient
                self.w = [w - self.lr * (g * x + self.l2 * w) for w, x in zip(self.w, f)]
                b = min(9, int(p_hat * 10))
                self.calib[b][0] += 1
                self.calib[b][1] += int(win)
                self.stats["brier_sum"] += (p_hat - win) ** 2
                if ctx["edge"] > 0:
                    self.stats["hi_score_trades"] += 1
                    self.stats["hi_score_sum_r"] += rc
                else:
                    self.stats["lo_score_trades"] += 1
                    self.stats["lo_score_sum_r"] += rc
            self.recent.append({"kind": "lesson", "time": int(time.time() * 1000), "bot_id": bot_id,
                                "strategy_id": strategy_id, "instrument": instrument, "r": round(rc, 3),
                                "p_win": ctx["p_win"] if ctx else None})

    # ------------------------------------------------------------------ persistence and reporting
    def to_state(self) -> dict:
        with self.lock:
            return {"post": self.post, "w": self.w, "calib": self.calib, "stats": self.stats, "mode": self.mode,
                    "pending": self.pending}

    def restore(self, st: dict):
        if not st:
            return
        with self.lock:
            for k, v in st.get("post", {}).items():
                p = self.post.setdefault(k, _post())
                p.update({x: v[x] for x in ("n", "sum", "sum2") if x in v})
                if not p["prior_n"]:
                    p["prior_mean"], p["prior_n"] = v.get("prior_mean", 0.0), v.get("prior_n", 0.0)
            if len(st.get("w", [])) == len(self.w):
                self.w = st["w"]
            self.calib = st.get("calib", self.calib)
            self.stats.update(st.get("stats", {}))
            self.pending = st.get("pending", {})

    def summary(self, names: Optional[Dict[str, str]] = None) -> dict:
        with self.lock:
            names = names or {}
            learned = []
            for k, p in self.post.items():
                if k.startswith("S:") and p["n"] > 0:
                    e = self.estimate(k)
                    learned.append({"strategy_id": k[2:], "name": names.get(k[2:], k[2:]), "trades": p["n"],
                                    "live_mean_r": round(p["sum"] / p["n"], 3), "estimate_r": round(e["mean"], 3),
                                    "prior_r": round(p["prior_mean"], 3)})
            learned.sort(key=lambda x: x["estimate_r"], reverse=True)
            n = self.stats["learned"]
            cons = {inst: self.consensus_of(inst) for inst in list(self.consensus)[:40]}
            hi, lo = self.stats["hi_score_trades"], self.stats["lo_score_trades"]
            return {"mode": self.mode, "connected_bots": len(self.connected), "trades_learned": n,
                    "win_rate": self.stats["wins"] / n if n else None,
                    "avg_r": self.stats["sum_r"] / n if n else None,
                    "scored": self.stats["scored"], "approved": self.stats["approved"], "vetoed": self.stats["vetoed"],
                    "resized": self.stats["resized"], "prior_strategies": self.stats["prior_strategies"],
                    "brier": self.stats["brier_sum"] / max(1, sum(c[0] for c in self.calib)) if any(c[0] for c in self.calib) else None,
                    "calibration": [{"predicted": (b + 0.5) / 10, "trades": c[0], "actual": c[1] / c[0] if c[0] else None}
                                    for b, c in enumerate(self.calib)],
                    "high_score_avg_r": self.stats["hi_score_sum_r"] / hi if hi else None, "high_score_trades": hi,
                    "low_score_avg_r": self.stats["lo_score_sum_r"] / lo if lo else None, "low_score_trades": lo,
                    "weights": {f: round(w, 4) for f, w in zip(FEATURES, self.w)},
                    "best_learned": learned[:8], "worst_learned": learned[-8:][::-1], "consensus": cons,
                    "recent": list(self.recent)[-60:]}
