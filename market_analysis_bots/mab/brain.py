"""Fleet Brain: one learning coordinator that every bot in the fleet is connected to.

What it does
------------
1. **Listens to every bot.** Each completed bar, every bot reports whether its entry rule wants
   long, short or nothing on its instrument. The brain keeps a live *consensus* per instrument,
   with each bot's vote weighted by its strategy's learned track record, and it classifies every
   market's current *regime*: trending up, trending down or sideways, and calm or volatile.
2. **Scores every entry before it is sent** and decides on its own: approve, resize (0.5x-1.5x),
   veto, or bench a bot whose strategy keeps losing. The score combines
   - a hierarchical Bayesian estimate of the trade's result in R after costs, pooled across
     levels: the whole fleet -> the strategy family -> the strategy -> the strategy on this
     instrument and the strategy in this regime (and its family in this regime), so evidence
     from one bot helps every related bot and a new strategy starts from what its family showed;
   - a shared context model (online logistic regression) trained on the closed trades of ALL
     bots: trend alignment and strength, RSI, volatility level and expansion, distance from VWAP,
     relative volume, time of day, market type and the weighted fleet consensus;
   - a stacking layer that learns how much to trust each of the two parts above.
3. **Learns from every closed trade** (self-learning): every level above is updated with the
   trade's R, the context model and the stacking layer take a gradient step, and the brain's own
   calibration (predicted vs actual win rate) is tracked.
4. **Learns from the trades it blocked.** A vetoed entry is followed as a *shadow trade* with the
   bot's own stop, target and session exit (costs included) and learned from at half weight, so a
   benched strategy can earn its way back and the brain measures what its vetoes were worth.
5. **Explains itself.** When a pattern becomes statistically clear (|t| >= 2 on at least 10
   trades) it writes a plain-language insight such as "ORB loses when trading against the trend
   (volatile)".

How it starts
-------------
Priors come from the batch evaluation (strategies/results): each strategy's measured expectancy
after realistic costs, weighted as a limited number of pseudo-trades so live paper results can
overturn it. Decisions use Thompson sampling (a random draw from the uncertainty of each
estimate), so strategies with little evidence still get tried and the brain keeps exploring.

Honesty
-------
The brain can only learn what paper trading and history show; it cannot create an edge the
markets do not offer. Its value is measured, not assumed: calibration, high- vs low-score trade
results and the average result of vetoed (shadow) trades are all reported. Setting `brain.mode`
to "advisory" keeps it learning and scoring without touching orders; "off" disconnects it.
Everything runs locally: no AI service is called and nothing is sent anywhere.
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
            "tod_cos", "consensus_aligned", "is_stock", "is_long", "trend_strength", "vol_expansion",
            "weekend", "cost_r", "p_loud", "p_quiet"]
COST_VETO_R = 0.33           # round-trip costs above a third of the risk: no trade
COST_HALF_R = 0.20           # 20-33%: half size
LOUD_SIZE = 0.6              # volatility gate LOUD: 0.6x size (bigger swings against the same stop)
R_CLIP = 3.0                 # trade R is winsorised before learning, so one extreme trade cannot dominate
PRIOR_WEIGHT = 0.5           # pseudo-trades per backtest trade
PRIOR_CAP = 25.0             # at most this many pseudo-trades from history
R_VAR = 1.0                  # assumed variance of per-trade R before data says otherwise
SHRINK = 6.0                 # pseudo-trades pulling each level toward its parent level
LOW_FEE = "@low"             # brain key suffix for bots on a low-fee venue (their costs differ, so do their results)
SHADOW_WEIGHT = 0.5          # a shadow (vetoed, simulated) trade counts as half a real one
STACK0 = [0.0, 1.0, 1.0]     # stacking weights at start: base, history estimate, context model
REGIME_TEXT = {"with": "trading with the trend", "against": "trading against the trend", "range": "the market is sideways"}


def _post() -> dict:
    return {"n": 0.0, "sum": 0.0, "sum2": 0.0, "prior_mean": 0.0, "prior_n": 0.0}


def regime_of(closes: List[float], i: int, n: int = 20, long_n: int = 200) -> Optional[dict]:
    """Market regime at bar i from closes up to i (no look-ahead).

    trend: efficiency ratio over n bars (net move / path length) above 0.3 -> up, below -0.3 -> down,
    otherwise range. vol: mean absolute return over n bars vs over long_n bars (> 1.15 -> volatile)."""
    if i < n + 5:
        return None
    move = closes[i] - closes[i - n]
    path = sum(abs(closes[k] - closes[k - 1]) for k in range(i - n + 1, i + 1)) or 1e-12
    er = move / path
    lo = max(1, i - long_n)
    short = sum(abs(closes[k] / closes[k - 1] - 1) for k in range(i - n + 1, i + 1) if closes[k - 1]) / n
    long_ = sum(abs(closes[k] / closes[k - 1] - 1) for k in range(lo, i + 1) if closes[k - 1]) / (i + 1 - lo)
    vr = short / long_ if long_ > 0 else 1.0
    return {"trend": "up" if er > 0.3 else ("down" if er < -0.3 else "range"),
            "vol": "volatile" if vr > 1.15 else "calm", "er": round(er, 3), "vr": round(vr, 3)}


def regime_key(reg: Optional[dict], side: int) -> Optional[str]:
    if not reg:
        return None
    rel = "range" if reg["trend"] == "range" else ("with" if (reg["trend"] == "up") == (side > 0) else "against")
    return f"{rel}-{reg['vol']}"


def regime_text(key: Optional[str]) -> str:
    if not key:
        return "regime unknown"
    rel, vol = key.split("-")
    return f"{REGIME_TEXT[rel]} ({vol})"


class FleetBrain:
    def __init__(self, mode: str = "active", seed: int = 7, veto_edge: float = -0.05, min_evidence: float = 8.0):
        self.mode = mode
        self.veto_edge = veto_edge
        self.min_evidence = min_evidence
        self.rng = random.Random(seed)
        self.post: Dict[str, dict] = {}
        self.w = [0.0] * len(FEATURES)
        self.lr, self.l2 = 0.05, 1e-3
        self.a = list(STACK0)                               # stacking weights
        self.calib = [[0, 0] for _ in range(10)]          # predicted win-probability decile -> [trades, wins]
        self.consensus: Dict[str, Dict[str, tuple]] = {}   # instrument -> bot -> (state, time)
        self.market: Dict[str, dict] = {}                  # instrument -> latest regime
        self.gates: Dict[str, dict] = {}                   # instrument -> latest volatility gate reading
        self.pending: Dict[str, dict] = {}                 # bot -> context of its open entry
        self.shadows: Dict[str, dict] = {}                 # bot -> vetoed entry followed as a shadow trade
        self.bench: Dict[str, str] = {}                    # bot -> why the brain benched it
        self.bot_sid: Dict[str, str] = {}
        self.bot_inst: Dict[str, str] = {}
        self.family: Dict[str, str] = {}                   # strategy -> family
        self.names: Dict[str, str] = {}
        self.reported: Dict[str, int] = {}                 # insight key -> evidence bucket already reported
        self.insights: deque = deque(maxlen=60)
        self.recent: deque = deque(maxlen=400)             # decisions, lessons, shadows and insights, newest last
        self.stats = {"scored": 0, "approved": 0, "vetoed": 0, "resized": 0, "benched": 0, "learned": 0, "wins": 0,
                      "sum_r": 0.0, "hi_score_trades": 0, "hi_score_sum_r": 0.0, "lo_score_trades": 0,
                      "lo_score_sum_r": 0.0, "brier_sum": 0.0, "prior_strategies": 0,
                      "shadow_trades": 0, "shadow_sum_r": 0.0, "shadow_wins": 0}
        self.lock = threading.RLock()
        self.connected: set = set()

    # ------------------------------------------------------------------ priors from the batch evaluation
    def load_priors(self, path: str, segment: str = "full") -> int:
        """Priors from the batch evaluation. segment="train" uses only the first 60% of each dataset
        (the system backtest does, so the brain never starts with knowledge of the period it is tested on)."""
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
                # costs decide most results, so each bot starts from the runs priced like its own venue:
                # retail fees (Kraken/Coinbase crypto, stocks) or a low-fee venue (key suffix "@low")
                for suffix, costs in (("", ("retail_kraken", "base")), (LOW_FEE, ("low_fee_venue", "base"))):
                    rows = [x for x in s.get("runs", []) if x.get("cost") in costs and (x.get(segment) or {}).get("trades")]
                    if not rows:
                        continue
                    key = sid + suffix
                    tot = sum(x[segment]["trades"] for x in rows)
                    mean = sum(max(-R_CLIP, min(R_CLIP, x[segment]["expectancy_r"] or 0)) * x[segment]["trades"] for x in rows) / tot
                    self._set_prior(f"S:{key}", mean, tot)
                    for x in rows:
                        self._set_prior(f"SI:{key}|{x['instrument']}",
                                        max(-R_CLIP, min(R_CLIP, x[segment]["expectancy_r"] or 0)), x[segment]["trades"])
                n += 1
            self.stats["prior_strategies"] = n
        return n

    def _set_prior(self, key, mean, trades):
        p = self.post.setdefault(key, _post())
        p["prior_mean"], p["prior_n"] = float(mean), min(PRIOR_CAP, PRIOR_WEIGHT * float(trades))

    # ------------------------------------------------------------------ connection, consensus and regimes
    def connect(self, bot_id: str, strategy_id: Optional[str] = None, family: Optional[str] = None,
                name: Optional[str] = None, instrument: Optional[str] = None):
        with self.lock:
            self.connected.add(bot_id)
            if instrument:
                self.bot_inst[bot_id] = instrument
            if strategy_id:
                self.bot_sid[bot_id] = strategy_id
                if family:
                    self.family[strategy_id] = family
                if name:
                    self.names[strategy_id] = name

    def observe(self, bot_id: str, instrument: str, state: int, t: int, frame=None, i: Optional[int] = None):
        """A bot reports its entry-rule state on its instrument (+1 long, -1 short, 0 none)."""
        with self.lock:
            self.consensus.setdefault(instrument, {})[bot_id] = (state, t)
            if frame is not None and i is not None and self.market.get(instrument, {}).get("t") != t:
                reg = regime_of(frame.c, i)
                if reg:
                    self.market[instrument] = dict(reg, t=t, price=frame.c[i])

    def _track_weight(self, bot_id: str) -> float:
        e = self.estimate(f"S:{self.bot_sid.get(bot_id, '')}")
        return max(0.1, min(2.0, 1.0 + 2.0 * e["mean"])) if e else 1.0

    def consensus_of(self, instrument: str, exclude: Optional[str] = None, max_age_ms: int = 6 * 3_600_000) -> dict:
        now = int(time.time() * 1000)
        votes = [(b, s) for b, (s, t) in self.consensus.get(instrument, {}).items()
                 if b != exclude and now - t <= max_age_ms]
        long_, short_ = sum(1 for _, s in votes if s > 0), sum(1 for _, s in votes if s < 0)
        wts = [self._track_weight(b) for b, _ in votes]
        smart = sum(w * s for w, (_, s) in zip(wts, votes)) / sum(wts) if votes else 0.0
        return {"bots": len(votes), "long": long_, "short": short_,
                "net": (long_ - short_) / len(votes) if votes else 0.0, "smart_net": smart}

    # ------------------------------------------------------------------ estimates
    def estimate(self, key: str):
        """Raw estimate of one level (its own prior and data only)."""
        p = self.post.get(key)
        if p is None:
            return None
        n_eff = p["n"] + p["prior_n"]
        if n_eff <= 0:
            return None
        mean = (p["prior_mean"] * p["prior_n"] + p["sum"]) / n_eff
        return {"mean": mean, "sd": math.sqrt(self._var(p) / n_eff), "n_eff": n_eff, "n": p["n"]}

    @staticmethod
    def _var(p) -> float:
        if p["n"] >= 5:
            m = p["sum"] / p["n"]
            return max(0.05, (p["sum2"] / p["n"] - m * m) * p["n"] / (p["n"] - 1))
        return R_VAR

    def _level(self, key: str, parent: float, k: float = SHRINK):
        """(mean, evidence) of one level, shrunk toward its parent level's mean."""
        p = self.post.get(key)
        if not p or p["n"] + p["prior_n"] <= 0:
            return parent, 0.0
        return (parent * k + p["prior_mean"] * p["prior_n"] + p["sum"]) / (k + p["prior_n"] + p["n"]), p["n"] + p["prior_n"]

    def _combined(self, sid: str, inst: str, reg: Optional[str] = None) -> dict:
        """Hierarchical estimate for this strategy on this instrument in this regime."""
        fam = self.family.get(sid)
        g, _ = self._level("G", 0.0, k=20.0)
        base = 0.5 * g                          # other families say less about this one than its own family does
        n_fam = 0.0
        if fam:
            base, n_fam = self._level(f"F:{fam}", base)
        s, n_s = self._level(f"S:{sid}", base)
        si, n_si = self._level(f"SI:{sid}|{inst}", s)
        sr, n_sr = s, 0.0
        if reg:
            fr = base
            if fam:
                fr, _ = self._level(f"FR:{fam}|{reg}", base)
            sr, n_sr = self._level(f"SR:{sid}|{reg}", s + (fr - base))
        mean = max(-R_CLIP, min(R_CLIP, s + (si - s) + (sr - s)))
        evidence = n_s + n_si + n_sr
        p = self.post.get(f"S:{sid}")
        var = self._var(p) if p else R_VAR
        return {"mean": mean, "sd": math.sqrt(var / (evidence + SHRINK)), "n_eff": evidence,
                "parts": {"family": round(base, 3), "strategy": round(s, 3), "instrument": round(si - s, 3),
                          "regime": round(sr - s, 3), "family_evidence": round(n_fam, 1)}}

    # ------------------------------------------------------------------ context features
    @staticmethod
    def features(frame, i: int, side: int, consensus_net: float, reg: Optional[dict] = None,
                 cost_r: Optional[float] = None, gate: Optional[dict] = None) -> List[float]:
        ev = expr.Evaluator(frame)

        def v(e):
            return ev.series(expr.parse(e))[i]
        close = frame.c[i]
        ema50, rsi, atr = v("ema(close,50)"), v("rsi(close,14)"), v("atr(14)")
        volp = v("pctrank(atr(14) / close, 200)")
        vw, rv = v("vwap()"), v("rvol(20)")
        tod = frame.tod[i] / 1440.0 * 2 * math.pi
        return [1.0,
                0.0 if ema50 is None else (1.0 if (close - ema50) * side > 0 else -1.0),
                0.0 if rsi is None else (rsi - 50) / 50 * side,
                0.0 if volp is None else volp / 100 - 0.5,
                0.0 if (vw is None or not atr) else max(-3, min(3, (close - vw) / atr * side)) / 3,
                0.0 if not rv else max(-2, min(2, math.log(rv))) / 2,
                math.sin(tod), math.cos(tod),
                consensus_net * side,
                1.0 if frame.asset_type.startswith("stock") else -1.0,
                1.0 if side > 0 else -1.0,
                0.0 if not reg else max(-1.0, min(1.0, reg["er"] * side)),
                0.0 if not reg or reg["vr"] <= 0 else max(-1.0, min(1.0, math.log(reg["vr"]))),
                1.0 if ((frame.t[i] // 86_400_000) + 3) % 7 >= 5 else 0.0,
                0.0 if cost_r is None else min(1.0, cost_r),
                0.0 if not gate or gate.get("p_loud") is None else gate["p_loud"] - 0.33,
                0.0 if not gate or gate.get("p_quiet") is None else gate["p_quiet"] - 0.33]

    def p_win(self, f: List[float]) -> float:
        z = sum(w * x for w, x in zip(self.w, f))
        return 1 / (1 + math.exp(-max(-30, min(30, z))))

    def _base_rate(self) -> float:
        n = self.stats["learned"]
        return (self.stats["wins"] + 1) / (n + 2)

    # ------------------------------------------------------------------ decide
    def score(self, bot_id: str, strategy_id: str, instrument: str, frame, i: int, side: int,
              cost_r: Optional[float] = None, gate: Optional[dict] = None) -> dict:
        """Decision for an entry intent: {"action": approve|resize|veto, "size": multiplier, ...}.

        cost_r: round-trip costs as a fraction of the trade's risk (1R); gate: the volatility gate
        reading for this market. Both are hard rules in active mode, applied before the learned score."""
        with self.lock:
            cons = self.consensus_of(instrument, exclude=bot_id)
            reg = None
            try:
                reg = regime_of(frame.c, i)
                f = self.features(frame, i, side, cons["smart_net"], reg, cost_r, gate)
            except Exception:
                f = [1.0] + [0.0] * (len(FEATURES) - 1)
            return self.decide(bot_id, strategy_id, instrument, side, f, regime_key(reg, side), cons, cost_r, gate)

    def decide(self, bot_id: str, strategy_id: str, instrument: str, side: int, f: List[float], rkey: Optional[str],
               cons: Optional[dict] = None, cost_r: Optional[float] = None, gate: Optional[dict] = None) -> dict:
        """The decision itself, from precomputed context features (used live via score() and by the
        system backtest, which computes each candidate's features once)."""
        with self.lock:
            cons = cons or {"bots": 0, "long": 0, "short": 0, "net": 0.0, "smart_net": 0.0}
            p = self.p_win(f)
            est = self._combined(strategy_id, instrument, rkey)
            ctx = (p - self._base_rate()) if self.stats["learned"] >= 30 else 0.0
            z = [1.0, est["mean"], ctx]
            a0, a1, a2 = self.a
            edge = a0 + a1 * est["mean"] + a2 * ctx
            sample = a0 + a1 * self.rng.gauss(est["mean"], est["sd"]) + a2 * ctx        # Thompson draw
            n_eff, sd = est["n_eff"], est["sd"]
            action, size = "approve", 1.0
            benched = self.mode == "active" and n_eff >= 30 and est["mean"] + 1.64 * sd < 0
            reason = (f"learned edge {edge:+.2f}R (+/-{sd:.2f}, evidence {n_eff:.0f} trades, {regime_text(rkey)}); "
                      f"win chance {100 * p:.0f}%; fleet {cons['long']} long / {cons['short']} short of {cons['bots']} "
                      f"(track-record weighted {cons['smart_net']:+.2f})")
            kind = None
            gstate = (gate or {}).get("state")
            if self.mode == "active":
                if cost_r is not None and cost_r > COST_VETO_R:
                    action, size, kind = "veto", 0.0, "cost"
                    reason = f"costs would take {100 * cost_r:.0f}% of the risk on this trade (limit {100 * COST_VETO_R:.0f}%); " + reason
                elif gstate == "QUIET":
                    action, size, kind = "veto", 0.0, "quiet"
                    reason = f"volatility gate QUIET ({100 * gate['p_quiet']:.0f}%): the next hours are likely too quiet to pay the costs; " + reason
                elif benched:
                    action, size, kind = "veto", 0.0, "benched"
                    reason = "benched: this strategy keeps losing here (95% confident), so the brain sits it out " \
                             "and follows its signals as shadow trades until they improve; " + reason
                elif n_eff >= self.min_evidence and sample < self.veto_edge:
                    action, size, kind = "veto", 0.0, "learned"
                else:
                    size = max(0.5, min(1.5, 1.0 + 1.5 * edge))
                    if cost_r is not None and cost_r > COST_HALF_R:
                        size *= 0.5
                        reason = f"half size: costs are {100 * cost_r:.0f}% of the risk; " + reason
                    if gstate == "LOUD":
                        size *= LOUD_SIZE
                        reason = f"volatility gate LOUD: {LOUD_SIZE}x size; " + reason
                    size = max(0.25, min(1.5, size))
                    if abs(size - 1.0) > 0.05:
                        action = "resize"
            if benched and bot_id not in self.bench:
                self.stats["benched"] += 1
            if benched:
                self.bench[bot_id] = reason
            else:
                self.bench.pop(bot_id, None)
            self.stats["scored"] += 1
            self.stats["vetoed" if action == "veto" else "approved"] += 1
            if action == "resize":
                self.stats["resized"] += 1
            dec = {"time": int(time.time() * 1000), "bot_id": bot_id, "strategy_id": strategy_id, "instrument": instrument,
                   "side": side, "p_win": round(p, 4), "edge": round(edge, 4), "sample": round(sample, 4),
                   "sd": round(sd, 4), "evidence": round(n_eff, 1), "action": action, "size": round(size, 3),
                   "mode": self.mode, "reason": reason, "features": [round(x, 4) for x in f], "z": [round(x, 5) for x in z],
                   "regime": rkey, "parts": est["parts"], "benched": benched, "veto_kind": kind,
                   "cost_r": None if cost_r is None else round(cost_r, 4), "gate": gstate}
            self.recent.append({"kind": "decision", **{k: dec[k] for k in ("time", "bot_id", "strategy_id", "instrument",
                                                                          "side", "p_win", "edge", "action", "size",
                                                                          "regime", "benched", "veto_kind", "gate")}})
            if action != "veto":
                self.pending[bot_id] = dec
            return dec

    # ------------------------------------------------------------------ learn
    def _update(self, sid: str, inst: str, reg: Optional[str], rc: float, w: float) -> List[str]:
        fam = self.family.get(sid)
        keys = ["G", f"S:{sid}", f"SI:{sid}|{inst}"]
        if fam:
            keys.append(f"F:{fam}")
        if reg:
            keys.append(f"SR:{sid}|{reg}")
            if fam:
                keys.append(f"FR:{fam}|{reg}")
        for key in keys:
            p = self.post.setdefault(key, _post())
            p["n"] += w
            p["sum"] += w * rc
            p["sum2"] += w * rc * rc
        return keys

    def _step_models(self, ctx: dict, rc: float, w: float):
        win = 1.0 if rc > 0 else 0.0
        f, p_hat = ctx["features"], ctx["p_win"]
        if len(f) == len(self.w):
            g = p_hat - win                                   # logistic-loss gradient
            self.w = [wi - w * self.lr * (g * x + self.l2 * wi) for wi, x in zip(self.w, f)]
        z = ctx.get("z")
        if z and len(z) == 3:
            err = sum(ak * zk for ak, zk in zip(self.a, z)) - rc
            lr_s, l2s = 0.01 * w, 0.05
            a = [ak - lr_s * (err * zk + l2s * (ak - a0k)) for ak, zk, a0k in zip(self.a, z, STACK0)]
            self.a = [max(-0.5, min(0.5, a[0])), max(0.0, min(2.0, a[1])), max(0.0, min(2.0, a[2]))]

    def learn(self, bot_id: str, strategy_id: str, instrument: str, r: Optional[float],
              ctx: Optional[dict] = None) -> List[str]:
        """Self-learning step from one closed trade (called for every bot's every trade). Returns new insights."""
        if r is None:
            return []
        rc = max(-R_CLIP, min(R_CLIP, float(r)))
        with self.lock:
            ctx = ctx or self.pending.pop(bot_id, None)
            keys = self._update(strategy_id, instrument, (ctx or {}).get("regime"), rc, 1.0)
            win = 1.0 if rc > 0 else 0.0
            self.stats["learned"] += 1
            self.stats["wins"] += int(win)
            self.stats["sum_r"] += rc
            if ctx:
                self._step_models(ctx, rc, 1.0)
                b = min(9, int(ctx["p_win"] * 10))
                self.calib[b][0] += 1
                self.calib[b][1] += int(win)
                self.stats["brier_sum"] += (ctx["p_win"] - win) ** 2
                if ctx["edge"] > 0:
                    self.stats["hi_score_trades"] += 1
                    self.stats["hi_score_sum_r"] += rc
                else:
                    self.stats["lo_score_trades"] += 1
                    self.stats["lo_score_sum_r"] += rc
            self.recent.append({"kind": "lesson", "time": int(time.time() * 1000), "bot_id": bot_id,
                                "strategy_id": strategy_id, "instrument": instrument, "r": round(rc, 3),
                                "p_win": ctx["p_win"] if ctx else None, "regime": (ctx or {}).get("regime")})
            return self._insights(keys, strategy_id, instrument)

    # ------------------------------------------------------------------ shadow trades (vetoed entries)
    def shadow_open(self, bot_id: str, dec: dict, entry: float, stop: Optional[float], target: Optional[float],
                    cost_r: float, t: int, max_bars: int = 48, sess_close: int = 0):
        if not stop or not entry or abs(entry - stop) <= 0:
            return
        with self.lock:
            self.shadows[bot_id] = {"dec": dec, "side": dec["side"], "entry": entry, "stop": stop, "target": target,
                                    "cost_r": max(0.0, cost_r), "t": t, "bars": 0, "max_bars": max(1, max_bars),
                                    "sess_close": sess_close or 0}

    def shadow_step(self, bot_id: str, frame, i: int) -> List[str]:
        """Advance this bot's shadow trade by bar i; learn from it when it would have closed."""
        with self.lock:
            sh = self.shadows.get(bot_id)
            if not sh or frame.t[i] <= sh["t"]:
                return []
            side, entry, stop, target = sh["side"], sh["entry"], sh["stop"], sh["target"]
            risk = abs(entry - stop)
            o, h, lo, c = frame.o[i], frame.h[i], frame.l[i], frame.c[i]
            r, why = None, ""
            if (side > 0 and lo <= stop) or (side < 0 and h >= stop):          # stop first: the cautious assumption
                px = min(o, stop) if side > 0 else max(o, stop)
                r, why = (px - entry) * side / risk, "stop"
            elif target and ((side > 0 and h >= target) or (side < 0 and lo <= target)):
                px = max(o, target) if side > 0 else min(o, target)
                r, why = (px - entry) * side / risk, "target"
            else:
                sh["bars"] += 1
                if sh["bars"] >= sh["max_bars"] or (sh["sess_close"] and frame.t[i] + frame.step >= sh["sess_close"]):
                    r, why = (c - entry) * side / risk, "time"
            if r is None:
                return []
            del self.shadows[bot_id]
            return self.learn_counterfactual(bot_id, sh["dec"], r - sh["cost_r"], why)

    def learn_counterfactual(self, bot_id: str, dec: dict, r: float, why: str = "") -> List[str]:
        """Learn, at half weight, from what a blocked entry would have made (r net of costs)."""
        with self.lock:
            rc = max(-R_CLIP, min(R_CLIP, r))
            keys = self._update(dec["strategy_id"], dec["instrument"], dec.get("regime"), rc, SHADOW_WEIGHT)
            self._step_models(dec, rc, SHADOW_WEIGHT)
            self.stats["shadow_trades"] += 1
            self.stats["shadow_sum_r"] += rc
            self.stats["shadow_wins"] += int(rc > 0)
            k = dec.get("veto_kind") or "learned"
            by = self.stats.setdefault("shadow_by_kind", {}).setdefault(k, [0, 0.0])
            by[0] += 1
            by[1] += rc
            self.recent.append({"kind": "shadow", "time": int(time.time() * 1000), "bot_id": bot_id,
                                "strategy_id": dec["strategy_id"], "instrument": dec["instrument"], "r": round(rc, 3),
                                "exit": why, "regime": dec.get("regime")})
            out = self._insights(keys, dec["strategy_id"], dec["instrument"])
            n = self.stats["shadow_trades"]
            if n in (10, 25, 50) or (n >= 100 and n % 100 == 0):
                avg = self.stats["shadow_sum_r"] / n
                out.append(self._say("vetoes", f"The {n} trades the brain blocked would have averaged {avg:+.2f}R each "
                                               f"after costs ({'the vetoes are helping' if avg < 0 else 'so far the vetoes cost money; it keeps adjusting'})."))
            return out

    # ------------------------------------------------------------------ insights
    def _say(self, key: str, text: str) -> str:
        item = {"kind": "insight", "time": int(time.time() * 1000), "key": key, "text": text}
        self.insights.append(item)
        self.recent.append(item)
        return text

    def _insights(self, keys: List[str], sid: str, inst: str) -> List[str]:
        out = []
        name = self.names.get(sid, sid)
        for key in keys:
            if key == "G":
                continue
            p = self.post[key]
            n = p["n"]
            if n < 10:
                continue
            m = p["sum"] / n
            t = m / math.sqrt(self._var(p) / n)
            if abs(t) < 2.0:
                continue
            bucket = int(math.log2(n / 10))
            tag = f"{key}|{'+' if m > 0 else '-'}"
            if self.reported.get(tag, -1) >= bucket:
                continue
            self.reported[tag] = bucket
            verb = "wins" if m > 0 else "loses"
            kind, _, rest = key.partition(":")
            if kind == "S":
                what = f"{name} {verb} overall"
            elif kind == "SI":
                what = f"{name} {verb} on {inst}"
            elif kind == "SR":
                what = f"{name} {verb} when {regime_text(rest.split('|')[1])}"
            elif kind == "F":
                what = f"{rest.replace('_', ' ')} strategies as a group {'win' if m > 0 else 'lose'}"
            else:                                        # FR
                fam, reg = rest.split("|")
                what = f"{fam.replace('_', ' ')} strategies {'win' if m > 0 else 'lose'} when {regime_text(reg)}"
            out.append(self._say(key, f"Learned: {what}: {m:+.2f}R per trade over {n:.0f} trades (t = {t:+.1f})."))
        return out

    # ------------------------------------------------------------------ persistence and reporting
    def to_state(self) -> dict:
        with self.lock:
            return {"post": self.post, "w": self.w, "features": FEATURES, "a": self.a, "calib": self.calib,
                    "stats": self.stats, "mode": self.mode, "pending": self.pending, "shadows": self.shadows,
                    "reported": self.reported, "insights": list(self.insights), "bench": self.bench}

    def restore(self, st: dict):
        """Carry learned state over, including across upgrades that add features or levels."""
        if not st:
            return
        with self.lock:
            for k, v in st.get("post", {}).items():
                p = self.post.setdefault(k, _post())
                p.update({x: v[x] for x in ("n", "sum", "sum2") if x in v})
                if not p["prior_n"]:
                    p["prior_mean"], p["prior_n"] = v.get("prior_mean", 0.0), v.get("prior_n", 0.0)
            old = st.get("features") or FEATURES[:len(st.get("w", []))]
            byname = dict(zip(old, st.get("w", [])))
            self.w = [byname.get(f, 0.0) for f in FEATURES]
            if len(st.get("a", [])) == 3:
                self.a = st["a"]
            self.calib = st.get("calib", self.calib)
            self.stats.update(st.get("stats", {}))
            self.pending = st.get("pending", {})
            self.shadows = st.get("shadows", {})
            self.reported = st.get("reported", {})
            self.bench = st.get("bench", {})
            for it in st.get("insights", []):
                self.insights.append(it)

    def summary(self, names: Optional[Dict[str, str]] = None) -> dict:
        with self.lock:
            names = {**self.names, **(names or {})}
            learned = []
            for k, p in self.post.items():
                if k.startswith("S:") and p["n"] > 0:
                    e = self.estimate(k)
                    learned.append({"strategy_id": k[2:], "name": names.get(k[2:], k[2:]), "trades": round(p["n"], 1),
                                    "live_mean_r": round(p["sum"] / p["n"], 3), "estimate_r": round(e["mean"], 3),
                                    "prior_r": round(p["prior_mean"], 3)})
            learned.sort(key=lambda x: x["estimate_r"], reverse=True)
            regimes = []
            for k, p in self.post.items():
                if k.startswith("FR:") and p["n"] >= 3:
                    fam, reg = k[3:].split("|")
                    regimes.append({"family": fam, "regime": reg, "text": regime_text(reg), "trades": round(p["n"], 1),
                                    "mean_r": round(p["sum"] / p["n"], 3)})
            regimes.sort(key=lambda x: x["mean_r"])
            n = self.stats["learned"]
            now = int(time.time() * 1000)
            cons = {inst: self.consensus_of(inst) for inst in list(self.consensus)[:40]}
            stances = {b: s for inst in self.consensus.values() for b, (s, t) in inst.items() if now - t <= 6 * 3_600_000}
            hi, lo = self.stats["hi_score_trades"], self.stats["lo_score_trades"]
            sh = self.stats["shadow_trades"]
            picks = []
            for b, sid in self.bot_sid.items():
                inst = self.bot_inst.get(b, "")
                e = self._combined(sid, inst)
                picks.append({"bot_id": b, "strategy_id": sid, "name": names.get(sid, sid), "instrument": inst,
                              "edge_r": round(e["mean"], 3), "evidence": round(e["n_eff"], 1)})
            picks.sort(key=lambda x: x["edge_r"], reverse=True)
            return {"mode": self.mode, "connected_bots": len(self.connected), "trades_learned": n,
                    "win_rate": self.stats["wins"] / n if n else None,
                    "avg_r": self.stats["sum_r"] / n if n else None,
                    "scored": self.stats["scored"], "approved": self.stats["approved"], "vetoed": self.stats["vetoed"],
                    "resized": self.stats["resized"], "prior_strategies": self.stats["prior_strategies"],
                    "benched_now": len(self.bench), "benched_bots": sorted(self.bench),
                    "shadow_trades": sh, "shadow_avg_r": self.stats["shadow_sum_r"] / sh if sh else None,
                    "shadow_win_rate": self.stats["shadow_wins"] / sh if sh else None, "shadows_open": len(self.shadows),
                    "shadow_by_kind": {k: {"trades": v[0], "avg_r": round(v[1] / v[0], 4) if v[0] else None}
                                       for k, v in self.stats.get("shadow_by_kind", {}).items()},
                    "gates": dict(self.gates),
                    "trust": {"base": round(self.a[0], 3), "history": round(self.a[1], 3), "context": round(self.a[2], 3)},
                    "brier": self.stats["brier_sum"] / max(1, sum(c[0] for c in self.calib)) if any(c[0] for c in self.calib) else None,
                    "calibration": [{"predicted": (b + 0.5) / 10, "trades": c[0], "actual": c[1] / c[0] if c[0] else None}
                                    for b, c in enumerate(self.calib)],
                    "high_score_avg_r": self.stats["hi_score_sum_r"] / hi if hi else None, "high_score_trades": hi,
                    "low_score_avg_r": self.stats["lo_score_sum_r"] / lo if lo else None, "low_score_trades": lo,
                    "weights": {f: round(w, 4) for f, w in zip(FEATURES, self.w)},
                    "best_learned": learned[:8], "worst_learned": learned[-8:][::-1], "consensus": cons,
                    "markets": {k: {x: v[x] for x in ("trend", "vol", "er", "vr", "price")} for k, v in self.market.items()},
                    "regime_lessons": (regimes[:6] + regimes[-6:][::-1]) if len(regimes) > 12 else regimes,
                    "insights": list(self.insights)[-20:][::-1], "stances": stances, "top_picks": picks[:5],
                    "recent": list(self.recent)[-150:]}
