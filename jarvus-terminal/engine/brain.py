#!/usr/bin/env python3
"""The Brain: 120 agents and one learned coordinator.

Every candidate trade is looked at by 120 agents at once:

  * 95 strategy agents, one per strategy in the library. Each says how strongly its own
    pattern is present right now (0 when it is not).
  * 25 context agents, each watching one thing the strategies do not: how volatile the
    market is and whether that is expanding or compressing, the trend on three horizons,
    how stretched price is, momentum, volume, fees as a share of the risk, the time of
    day, the overnight gap, where price sits against session VWAP, how many strategies
    and families agree, the verification backtest's measured edge on this coin, and what
    the market leader (Bitcoin for crypto, the S&P 500 for stocks) is doing.

The coordinator is a ridge regression per asset class that turns those 120 readings into
one number: the expected result of taking this trade now, in R, after fees. It is
trained on history in which every agent's reading was recorded next to how the trade
really turned out, and it only ever learns from the past: the weights shipped with the
app were fitted on the first 60% of each market's history and judged on the last 40%,
which the model never saw.

Why a simple model: with a few hundred thousand noisy examples, a model that can bend
into any shape will memorise the noise, and in markets the noise is most of what there
is. A regularised linear model can only learn "this agent tends to help, that one tends
to hurt, by this much", which is exactly what can be learned reliably here, and every
prediction can be explained agent by agent.

After it ships, the Brain keeps learning from every trade the bots close: each closed
trade nudges the weights of the agents that were active in it toward what actually
happened.
"""

from __future__ import annotations

import json
import math
import os
import threading
from typing import Dict, List, Optional, Sequence, Tuple

import config
from engine import strategies as S
from engine import swarm

CONTEXT = [
    ("atr_level", "Volatility level", "How big a typical bar is, as a share of price."),
    ("atr_rank", "Volatility expanding", "Is volatility high or low versus its own last 100 bars?"),
    ("squeeze_rank", "Compression", "How tight the Bollinger bands are versus their last 100 bars."),
    ("volume", "Volume surge", "Volume against its 20-bar average."),
    ("trend_long", "Long trend", "Price versus the 200 SMA, in ATRs."),
    ("trend_mid", "Mid trend slope", "The 50 EMA's slope over 10 bars, in ATRs."),
    ("rsi", "RSI", "14-bar RSI, centred on 50."),
    ("stretch", "Stretch", "Distance from the 21 EMA, in ATRs."),
    ("range_pos", "Range position", "Where price sits in its last 60 bars' range."),
    ("momentum", "Momentum", "The last 24 bars' move, in ATRs."),
    ("cost", "Cost", "Round-trip fees and slippage as a share of the risk on the trade."),
    ("is_stock", "Stock market", "1 for a stock, 0 for crypto."),
    ("hour_sin", "Time of day (a)", "Hour of the day, as a cycle."),
    ("hour_cos", "Time of day (b)", "Hour of the day, as a cycle."),
    ("weekend", "Weekend", "Saturday or Sunday (crypto only trades then)."),
    ("gap", "Overnight gap", "Today's open versus yesterday's close, for stocks."),
    ("vs_vwap", "Versus VWAP", "Price against session VWAP, in ATRs."),
    ("n_fired", "Crowd size", "How many strategies fired."),
    ("n_families", "Family agreement", "How many different strategy families fired."),
    ("edge_best", "Verified edge", "Best recent per-trade result of a firing strategy on this market."),
    ("edge_vs_random", "Edge over random", "That edge minus what random buying made on this market."),
    ("has_edge", "Passes the backtest", "1 if a firing strategy passes the bots' backtest rule."),
    ("leader_trend", "Leader trend", "Bitcoin (crypto) or the S&P 500 (stocks) versus its 50 EMA."),
    ("leader_momentum", "Leader momentum", "The leader's last 24 bars, in ATRs."),
    ("session_bar", "Session clock", "How far into the stock session this bar is."),
]
CONTEXT_NAMES = [c[0] for c in CONTEXT]
CONTEXT_LABEL = {c[0]: c[1] for c in CONTEXT}
CONTEXT_HELP = {c[0]: c[2] for c in CONTEXT}


def strategy_agents() -> List[str]:
    return sorted(n for n, s in S.REGISTRY.items() if s.group != "control")


def agent_names() -> List[str]:
    return ["bias"] + CONTEXT_NAMES + ["s:" + n for n in strategy_agents()]


def _clip(x, lo, hi):
    return lo if x < lo else hi if x > hi else x


def _pct_rank(series, i: int, look: int = 100) -> Optional[float]:
    v = series[i] if 0 <= i < len(series) else None
    if v is None:
        return None
    lo = max(0, i - look + 1)
    window = [x for x in series[lo:i + 1] if x is not None]
    if len(window) < 20:
        return None
    return sum(1 for x in window if x < v) / len(window)


# =============================================================================
# the agents' readings at one bar
# =============================================================================

def context_features(ctx: "S.Ctx", fired: List[Tuple[str, float]], *, fee_bps: float, slip_bps: float,
                     stop_atr: float, is_stock: bool, edge: Dict = None,
                     leader: Dict = None) -> Dict[str, float]:
    """The 25 context agents' readings, each scaled to roughly -1..1.

    Used identically by the research that trains the Brain and by the live bots, which is
    the only way its predictions can mean anything.
    """
    f: Dict[str, float] = {}
    i = ctx.n - 1
    cache = ctx.cache
    price = ctx.price
    atr = ctx.atr
    if not atr or not price:
        return f
    atr_pct = atr / price * 100
    f["atr_level"] = _clip(atr_pct / 2.0, 0.0, 2.0)
    atr_series = cache.indicator("atr", {"period": 14})
    r = _pct_rank(atr_series, i) if atr_series else None
    if r is not None:
        f["atr_rank"] = (r - 0.5) * 2
    bb = cache.indicator("bollinger", {"period": 20, "mult": 2.0})
    if bb:
        r = _pct_rank(bb[3], i)                          # bandwidth, (upper - lower) / middle
        if r is not None:
            f["squeeze_rank"] = (r - 0.5) * 2
    rv = ctx.last(ctx.ind("relative_volume", period=20))
    if rv:
        f["volume"] = _clip(math.log(max(rv, 1e-6)), -1.5, 1.5) / 1.5
    s200 = ctx.last(ctx.ind("sma", period=200))
    if s200:
        f["trend_long"] = _clip((price - s200) / atr, -10, 10) / 10
    e50 = ctx.ind("ema", period=50)
    a, b = ctx.last(e50), ctx.last(e50, 10)
    if a is not None and b is not None:
        f["trend_mid"] = _clip((a - b) / atr, -5, 5) / 5
    rs = ctx.last(ctx.ind("rsi", period=14))
    if rs is not None:
        f["rsi"] = (rs - 50) / 50
    e21 = ctx.last(ctx.ind("ema", period=21))
    if e21 is not None:
        f["stretch"] = _clip((price - e21) / atr, -5, 5) / 5
    if ctx.n >= 60:
        hi, lo = max(ctx.high[-60:]), min(ctx.low[-60:])
        if hi > lo:
            f["range_pos"] = ((price - lo) / (hi - lo) - 0.5) * 2
    if ctx.n > 25:
        f["momentum"] = _clip((price - ctx.close[-25]) / atr, -10, 10) / 10
    stop_pct = stop_atr * atr_pct
    f["cost"] = _clip(2 * (fee_bps + slip_bps) / 100.0 / stop_pct, 0, 1.0) if stop_pct else 1.0
    f["is_stock"] = 1.0 if is_stock else 0.0
    ts = ctx.candles[-1]["ts"]
    h = ts.hour + ts.minute / 60
    f["hour_sin"] = math.sin(2 * math.pi * h / 24)
    f["hour_cos"] = math.cos(2 * math.pi * h / 24)
    f["weekend"] = 1.0 if ts.weekday() >= 5 else 0.0
    sess = ctx.sess()
    if sess:
        if sess.get("gap_pct") is not None and sess["gapped"]:
            f["gap"] = _clip(sess["gap_pct"], -5, 5) / 5
        if sess.get("vwap"):
            f["vs_vwap"] = _clip((price - sess["vwap"]) / atr, -5, 5) / 5
        if sess["gapped"]:
            f["session_bar"] = min(sess["idx"], 7) / 7
    f["n_fired"] = min(len(fired), 20) / 20
    fams = {swarm.FAMILY.get(S.REGISTRY[n].group, S.REGISTRY[n].group) for n, _ in fired if n in S.REGISTRY}
    f["n_families"] = len(fams) / 7
    if edge:
        if edge.get("best") is not None:
            f["edge_best"] = _clip(edge["best"], -1.0, 1.5)
            if edge.get("control") is not None:
                f["edge_vs_random"] = _clip(edge["best"] - edge["control"], -1.5, 1.5)
        f["has_edge"] = 1.0 if edge.get("passes") else 0.0
    if leader:
        if leader.get("trend") is not None:
            f["leader_trend"] = _clip(leader["trend"], -5, 5) / 5
        if leader.get("momentum") is not None:
            f["leader_momentum"] = _clip(leader["momentum"], -10, 10) / 10
    return f


def leader_state(candles: List[dict], upto_ts=None) -> Optional[Dict]:
    """Trend and momentum of the market leader at (or just before) a timestamp."""
    if not candles:
        return None
    if upto_ts is not None:
        lo, hi = 0, len(candles)
        while lo < hi:                                 # last bar that opened at or before upto_ts
            mid = (lo + hi) // 2
            if candles[mid]["ts"] <= upto_ts:
                lo = mid + 1
            else:
                hi = mid
        k = lo - 1
    else:
        k = len(candles) - 1
    if k < 60:
        return None
    ctx = S.Ctx(candles, "leader", cache=_leader_cache(candles), at=k)
    atr = ctx.atr
    e50 = ctx.last(ctx.ind("ema", period=50))
    if not atr or e50 is None:
        return None
    return {"trend": (ctx.price - e50) / atr, "momentum": (ctx.price - ctx.close[-25]) / atr if ctx.n > 25 else 0.0}


_leader_caches: Dict[int, "S.SeriesCache"] = {}


def _leader_cache(candles):
    key = id(candles)
    c = _leader_caches.get(key)
    if c is None or c.n != len(candles):
        if len(_leader_caches) > 8:
            _leader_caches.clear()
        c = S.SeriesCache(candles)
        _leader_caches[key] = c
    return c


def vectorize(context: Dict[str, float], fired: List[Tuple[str, float]], index: Dict[str, int]) -> Tuple[List[int], List[float]]:
    """Sparse (indices, values) over agent_names(); the bias is always index 0."""
    idx, val = [0], [1.0]
    for k, v in context.items():
        j = index.get(k)
        if j is not None and v:
            idx.append(j)
            val.append(float(v))
    for n, st in fired:
        j = index.get("s:" + n)
        if j is not None and st:
            idx.append(j)
            val.append(float(st))
    return idx, val


# =============================================================================
# training: ridge regression from sparse rows, standard library only
# =============================================================================

class Ridge:
    """Accumulates X'X and X'y from sparse rows, then solves (X'X + lambda I) w = X'y."""

    def __init__(self, dim: int):
        self.dim = dim
        self.xtx = [[0.0] * dim for _ in range(dim)]
        self.xty = [0.0] * dim
        self.n = 0
        self.y_sum = 0.0

    def add(self, idx: Sequence[int], val: Sequence[float], y: float, weight: float = 1.0):
        self.n += 1
        self.y_sum += y
        for a in range(len(idx)):
            ia, va = idx[a], val[a] * weight
            row = self.xtx[ia]
            self.xty[ia] += va * y
            for b in range(len(idx)):
                row[idx[b]] += va * val[b]

    def solve(self, lam: float = 50.0) -> List[float]:
        d = self.dim
        m = [self.xtx[r][:] + [self.xty[r]] for r in range(d)]
        for r in range(1, d):                          # never shrink the intercept
            m[r][r] += lam
        for col in range(d):                           # Gauss-Jordan with partial pivoting
            piv = max(range(col, d), key=lambda r: abs(m[r][col]))
            if abs(m[piv][col]) < 1e-12:
                continue
            m[col], m[piv] = m[piv], m[col]
            p = m[col][col]
            m[col] = [x / p for x in m[col]]
            for r in range(d):
                if r != col and m[r][col]:
                    f = m[r][col]
                    rowc = m[col]
                    m[r] = [x - f * y for x, y in zip(m[r], rowc)]
        return [m[r][d] for r in range(d)]


# =============================================================================
# the live Brain
# =============================================================================

WEIGHTS_BUNDLED = os.path.join(os.path.dirname(os.path.abspath(__file__)), "brain_weights.json")
WEIGHTS_LEARNED = os.path.join(config.DATA_DIR, "brain.json")


class Brain:
    def __init__(self):
        self._lock = threading.Lock()
        self.models: Dict[str, Dict] = {}
        self.meta: Dict = {}
        self.load()

    # -- persistence ---------------------------------------------------------
    def load(self):
        for path in (WEIGHTS_LEARNED, WEIGHTS_BUNDLED):
            try:
                with open(path, encoding="utf-8") as fh:
                    d = json.load(fh)
                self.models = d.get("models", {})
                self.meta = d.get("meta", {})
                self.meta["source"] = "learned on this computer" if path == WEIGHTS_LEARNED else "shipped with the app"
                return
            except Exception:                            # noqa: BLE001
                continue
        self.models, self.meta = {}, {"source": "untrained"}

    def save(self):
        os.makedirs(os.path.dirname(WEIGHTS_LEARNED), exist_ok=True)
        tmp = WEIGHTS_LEARNED + ".tmp"
        with self._lock:
            payload = {"models": self.models, "meta": {k: v for k, v in self.meta.items() if k != "source"}}
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(payload, fh)
        os.replace(tmp, WEIGHTS_LEARNED)

    @property
    def trained(self) -> bool:
        return bool(self.models)

    # -- thinking ------------------------------------------------------------
    def _model(self, asset: str) -> Optional[Dict]:
        """'crypto', 'stock', or 'stock_dt' (stocks traded flat by the close)."""
        return self.models.get(asset) or self.models.get("stock" if asset.startswith("stock") else "crypto")

    def predict(self, asset: str, context: Dict[str, float], fired: List[Tuple[str, float]]) -> Optional[float]:
        m = self._model(asset)
        if not m:
            return None
        w = m["weights"]
        total = w.get("bias", 0.0)
        for k, v in context.items():
            total += w.get(k, 0.0) * v
        for n, st in fired:
            total += w.get("s:" + n, 0.0) * st
        return total

    def skilled(self, asset: str) -> bool:
        """Did this model show skill on data it never saw? Only then may it vote."""
        m = self._model(asset)
        return bool(m and m.get("skilled"))

    def veto_threshold(self, asset: str) -> Optional[float]:
        """Predictions below this are the model's most confident 'this will lose' calls."""
        m = self._model(asset)
        return m.get("veto_below") if (m and m.get("skilled")) else None

    def explain(self, asset: str, context: Dict[str, float], fired: List[Tuple[str, float]],
                top: int = 6) -> List[Dict]:
        """The agents that pushed this prediction most, up or down."""
        m = self._model(asset)
        if not m:
            return []
        w = m["weights"]
        parts = [(k, w.get(k, 0.0) * v) for k, v in context.items()]
        parts += [("s:" + n, w.get("s:" + n, 0.0) * st) for n, st in fired]
        parts = [p for p in parts if abs(p[1]) > 1e-4]
        parts.sort(key=lambda p: -abs(p[1]))
        return [{"agent": label(k), "effect": round(v, 3)} for k, v in parts[:top]]

    # -- learning from the bots' own trades ---------------------------------
    def learn(self, asset: str, context: Dict[str, float], fired: List[Tuple[str, float]],
              realized_r: float, rate: float = 0.01):
        """One small step toward what actually happened. Many trades move it; one cannot."""
        m = self._model(asset)
        if not m:
            return
        pred = self.predict(asset, context, fired)
        if pred is None:
            return
        err = _clip(realized_r, -1.5, 3.0) - pred
        with self._lock:
            w = m["weights"]
            w["bias"] = w.get("bias", 0.0) + rate * err
            for k, v in context.items():
                w[k] = w.get(k, 0.0) + rate * err * v
            for n, st in fired:
                w["s:" + n] = w.get("s:" + n, 0.0) + rate * err * st
            m["online_updates"] = m.get("online_updates", 0) + 1
        self.save()

    # -- reporting -----------------------------------------------------------
    def agents(self) -> List[Dict]:
        """Every agent with how much the coordinator trusts it, per asset class."""
        rows = []
        for key in agent_names()[1:]:
            row = {"key": key, "name": label(key), "kind": "strategy" if key.startswith("s:") else "context",
                   "help": CONTEXT_HELP.get(key) or (S.REGISTRY[key[2:]].description if key[2:] in S.REGISTRY else "")}
            for asset in ("crypto", "stock"):
                m = self.models.get(asset)
                row[asset] = round(m["weights"].get(key, 0.0), 4) if m else None
                st = (m or {}).get("agent_stats", {}).get(key)
                if st:
                    row[asset + "_stats"] = st
            if key.startswith("s:") and key[2:] in S.REGISTRY:
                row["family"] = swarm.FAMILY.get(S.REGISTRY[key[2:]].group, S.REGISTRY[key[2:]].group)
            else:
                row["family"] = "context"
            rows.append(row)
        return rows

    def summary(self) -> Dict:
        return {"trained": self.trained, "source": self.meta.get("source"), "meta": self.meta,
                "agents": len(agent_names()) - 1,
                "models": {a: {k: v for k, v in m.items() if k not in ("weights", "agent_stats")}
                           for a, m in self.models.items()}}


def label(key: str) -> str:
    if key.startswith("s:"):
        return key[2:]
    return CONTEXT_LABEL.get(key, key)


BRAIN: Optional[Brain] = None


def get() -> Brain:
    global BRAIN
    if BRAIN is None:
        BRAIN = Brain()
    return BRAIN
