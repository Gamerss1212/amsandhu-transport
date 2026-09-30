"""Shared strategy interface: a definition, its compiled rules, and the trade manager.

One code path decides and manages trades everywhere. The backtester, the replay tool and the
live paper runtime all call the same `TradeManager.on_bar()` with the same precomputed rule
series; only the `Filler` differs (simulated next-bar fills in backtests, the paper execution
engine live). Decisions are made on COMPLETED bars only.

Definition fields (JSON):
    id, name, version, family, direction ("long" | "short" | "both"), timeframe,
    params          {name: default}, referenced in rules as $name
    entry           {"long": rule, "short": rule}
    filters         [rule, ...] every one must be true to enter (listed separately for explanations)
    order           {"type": "market"} | {"type": "stop"|"limit", "long": rule, "short": rule, "ttl_bars": n}
    stop            {"type": "atr", "mult": m, "n": 14} | {"type": "pct", "pct": p} |
                    {"type": "level", "long": rule, "short": rule, "buffer_atr": 0}
    target          {"type": "none"} | {"type": "r", "r": 2} | {"type": "level", "long": rule, "short": rule}
    trail           {"type": "none"} | {"type": "atr", "mult": m, "n": 14, "activate_r": 0} |
                    {"type": "level", "long": rule, "short": rule}
    exit            {"long": rule, "short": rule}   signal exits, at the next bar's open
    max_bars        time stop in bars (0 = none)
    session         {"entry_start": "HH:MM", "entry_end": "HH:MM", "flat_minutes_before_close": 5}
                    or {"hold_overnight": true} for swing strategies (positions are not closed at the session end)
    max_trades_per_day, cooldown_bars
    sizing          {"risk_pct": 0.5, "max_notional_pct": 100}
    data            required data kinds: "bars", "trades", "book", "funding", "events:<name>", "bench"
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from mab import expr
from mab.expr import Evaluator, ExprError, Node
from mab.frame import Frame

VALID_DATA = {"bars", "trades", "book", "funding", "oi", "bench", "quotes", "extended_hours"}

DEFAULTS = {
    "version": "1.0.0", "direction": "both", "params": {}, "filters": [], "order": {"type": "market"},
    "stop": {"type": "atr", "mult": 2.0, "n": 14}, "target": {"type": "none"}, "trail": {"type": "none"},
    "exit": {}, "max_bars": 0, "session": {}, "max_trades_per_day": 3, "cooldown_bars": 0,
    "sizing": {"risk_pct": 0.5, "max_notional_pct": 100.0}, "data": ["bars"], "engine": "rules",
}


class DefinitionError(ValueError):
    pass


def config_hash(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()[:12]


@dataclass
class Compiled:
    definition: dict
    params: dict
    rules: Dict[str, Node]                       # name -> parsed rule
    warmup: Dict[Tuple[Optional[str], str], int]
    references: Dict[str, set]
    version_hash: str

    @property
    def id(self):
        return self.definition["id"]

    @property
    def tf(self):
        return self.definition["timeframe"]


def normalise(d: dict) -> dict:
    out = copy.deepcopy(DEFAULTS)
    for k, v in d.items():
        out[k] = copy.deepcopy(v)
    for k in ("id", "name", "timeframe"):
        if not out.get(k):
            raise DefinitionError(f"strategy definition is missing {k!r}")
    if out["direction"] not in ("long", "short", "both"):
        raise DefinitionError(f"{out['id']}: direction must be long, short or both")
    return out


def compile_strategy(d: dict, overrides: Optional[dict] = None, asset_type: str = "crypto") -> Compiled:
    """Validate a definition and parse every rule with parameters substituted."""
    d = normalise(d)
    sess = d.get("session") or {}
    if "stock" in sess or "crypto" in sess:            # market-specific session windows
        from mab.clock import is_equity
        d["session"] = sess.get("stock" if is_equity(asset_type) else "crypto", {})
    params = dict(d.get("params") or {})
    for k, v in (overrides or {}).items():
        if k not in params:
            raise DefinitionError(f"{d['id']}: unknown parameter override {k!r}")
        params[k] = v
    rules: Dict[str, Node] = {}

    def add(name, text):
        if text in (None, ""):
            return
        try:
            rules[name] = expr.parse(str(text), params)
        except ExprError as e:
            raise DefinitionError(f"{d['id']} {name}: {e}") from None

    sides = [s for s in ("long", "short") if d["direction"] in (s, "both")]
    for s in sides:
        add(f"entry_{s}", (d.get("entry") or {}).get(s))
        add(f"exit_{s}", (d.get("exit") or {}).get(s))
    if not any(f"entry_{s}" in rules for s in sides):
        raise DefinitionError(f"{d['id']}: no entry rule for direction {d['direction']}")
    for j, flt in enumerate(d.get("filters") or []):
        add(f"filter_{j}", flt)
    o = d["order"]
    if o.get("type") not in ("market", "stop", "limit", "oco"):
        raise DefinitionError(f"{d['id']}: order type must be market, stop, limit or oco")
    if o["type"] == "oco":
        if d["direction"] != "both":
            raise DefinitionError(f"{d['id']}: an oco bracket needs direction both")
        for s in ("long", "short"):
            add(f"order_{s}", o.get(s))
            if f"order_{s}" not in rules:
                raise DefinitionError(f"{d['id']}: oco order needs a stop price rule for {s}")
    elif o["type"] != "market":
        for s in sides:
            add(f"order_{s}", o.get(s))
            if f"order_{s}" not in rules and f"entry_{s}" in rules:
                raise DefinitionError(f"{d['id']}: {o['type']} order needs a price rule for {s}")
    st = d["stop"]
    if st.get("type") == "atr":
        add("atr_stop", f"atr({int(st.get('n', 14))})")
    elif st.get("type") == "level":
        for s in sides:
            add(f"stop_{s}", st.get(s))
        if st.get("buffer_atr"):
            add("atr_stop", f"atr({int(st.get('n', 14))})")
    elif st.get("type") != "pct":
        raise DefinitionError(f"{d['id']}: stop type must be atr, pct or level")
    tg = d["target"]
    if tg.get("type") == "level":
        for s in sides:
            add(f"target_{s}", tg.get(s))
    elif tg.get("type") not in ("none", "r"):
        raise DefinitionError(f"{d['id']}: target type must be none, r or level")
    tr = d["trail"]
    if tr.get("type") == "atr":
        add("atr_trail", f"atr({int(tr.get('n', 14))})")
    elif tr.get("type") == "level":
        for s in sides:
            add(f"trail_{s}", tr.get(s))
    elif tr.get("type") != "none":
        raise DefinitionError(f"{d['id']}: trail type must be none, atr or level")
    for k in d.get("data") or []:
        base = k.split(":")[0]
        if base not in VALID_DATA and base != "events":
            raise DefinitionError(f"{d['id']}: unknown data requirement {k!r}")
    warm: Dict[Tuple[Optional[str], str], int] = {}
    refs = {"indicators": set(), "functions": set(), "sources": set(), "timeframes": set(),
            "instruments": set(), "events": set()}
    for node in rules.values():
        for key, v in expr.warmup_by_series(node, d["timeframe"], asset_type).items():
            warm[key] = max(warm.get(key, 1), v)
        for k, v in expr.references(node).items():
            refs[k] |= v
    vh = config_hash({"def": d, "params": params})
    return Compiled(d, params, rules, warm, refs, vh)


# ============================================================================ rule series

@dataclass
class RuleSeries:
    """Every rule evaluated over a frame, as aligned lists."""
    frame: Frame
    values: Dict[str, List]
    evaluator: Evaluator


def evaluate(c: Compiled, frame: Frame, resolver=None, events=None) -> RuleSeries:
    ev = Evaluator(frame, resolver, events)
    return RuleSeries(frame, {k: ev.series(n) for k, n in c.rules.items()}, ev)


def explain(c: Compiled, rs: RuleSeries, i: int, side: str) -> Tuple[List[dict], Dict[str, Any]]:
    rows, feats = [], {}
    names = [f"entry_{side}"] + [k for k in c.rules if k.startswith("filter_")]
    for k in names:
        if k in c.rules:
            for r in expr.explain(rs.evaluator, c.rules[k], i):
                r["group"] = "entry" if k.startswith("entry") else "filter"
                rows.append(r)
            feats.update(expr.feature_values(rs.evaluator, c.rules[k], i))
    return rows, feats


# ============================================================================ trade manager

@dataclass
class Position:
    side: int                    # +1 long, -1 short
    qty: float
    entry_price: float
    entry_time: int              # fill time
    first_bar: int               # open time of the first bar the position is managed on
    stop: Optional[float]
    target: Optional[float]
    risk_per_unit: float
    trail: Optional[float] = None
    fees: float = 0.0
    reason: str = ""
    mfe: float = 0.0             # best excursion in R
    mae: float = 0.0             # worst excursion in R
    intrabar_entry: bool = False


@dataclass
class Pending:
    side: int
    kind: str                    # "market" | "stop" | "limit"
    price: Optional[float]
    placed_time: int             # open time of the signal bar
    expires_time: int            # last bar open time on which the order may fill
    stop_ref: Optional[float]    # stop level (level stops) or distance / fraction (atr / pct)
    stop_is_distance: bool
    target_ref: Optional[float]
    target_is_r: bool
    reason: str
    exit: bool = False           # a market exit, not an entry
    other: Optional[dict] = None # oco: the opposite stop leg {"side", "price", "stop_ref", "target_ref"}
    size: float = 1.0            # size multiplier set when the order was accepted (the fleet brain's resize)


@dataclass
class Trade:
    strategy_id: str
    instrument: str
    side: int
    qty: float
    entry_time: int
    entry_price: float
    exit_time: int
    exit_price: float
    fees: float
    pnl: float
    r: Optional[float]
    bars: int
    entry_reason: str
    exit_reason: str
    mfe_r: float
    mae_r: float

    def to_dict(self):
        return dict(self.__dict__)


class Filler:
    """How orders become fills. Subclassed by the backtest and live paper engines."""

    def fee(self, notional: float, liquidity: str) -> float:
        raise NotImplementedError

    def market_price(self, side: int, ref_price: float, qty: float) -> Optional[float]:
        raise NotImplementedError

    def stop_price(self, side: int, stop: float, bar_open: float) -> float:
        raise NotImplementedError

    def limit_fill(self, side: int, limit: float, o: float, h: float, l: float) -> Optional[float]:
        raise NotImplementedError


class TradeManager:
    """Position and order logic for one bot on one instrument. Deterministic given the bars.

    All bookkeeping is keyed by bar open TIMES, not list positions, so live buffers that roll
    forward, restarts and replays all line up."""

    def __init__(self, c: Compiled, filler: Filler, equity_fn, lot_size: float = 0.0, min_notional: float = 0.0,
                 can_short: bool = True, instrument: str = ""):
        self.c = c
        self.d = c.definition
        self.filler = filler
        self.equity_fn = equity_fn          # callable -> equity allocated to this bot
        self.lot = lot_size
        self.min_notional = min_notional
        self.can_short = can_short
        self.instrument = instrument
        self.pos: Optional[Position] = None
        self.pending: Optional[Pending] = None
        self.trades: List[Trade] = []
        self.day = None
        self.trades_today = 0
        self.last_exit_time = -10 ** 15
        self.last_bar_time = None
        self.awaiting: Optional[dict] = None   # a live intent sent to the paper engine, not yet answered
        # set by the fleet for a deployment: its own risk per trade and position cap (fractions of its equity), and
        # whether its stops rest on a broker (then stops are the broker's job, and a target reached becomes an
        # exit order instead of a simulated fill)
        self.risk_pct_override: Optional[float] = None
        self.max_notional_pct_override: Optional[float] = None
        self.broker_managed = False
        s = self.d.get("session") or {}
        self.entry_start = _hhmm(s.get("entry_start"))
        self.entry_end = _hhmm(s.get("entry_end"))
        self.flat_before = None if s.get("hold_overnight") else float(s.get("flat_minutes_before_close", 5))

    # ------------------------------------------------------------------ state persistence
    def state(self) -> dict:
        return {"pos": None if self.pos is None else dict(self.pos.__dict__),
                "pending": None if self.pending is None else dict(self.pending.__dict__),
                "day": self.day, "trades_today": self.trades_today, "last_exit_time": self.last_exit_time,
                "last_bar_time": self.last_bar_time, "awaiting": self.awaiting,
                "trades": len(self.trades)}

    def restore(self, st: dict):
        self.pos = Position(**st["pos"]) if st.get("pos") else None
        self.pending = Pending(**st["pending"]) if st.get("pending") else None
        self.day, self.trades_today = st.get("day"), st.get("trades_today", 0)
        self.last_exit_time = st.get("last_exit_time", -10 ** 15)
        self.last_bar_time = st.get("last_bar_time")
        self.awaiting = None      # an unanswered intent is not re-sent after a restart; the decision is logged as lost

    # ------------------------------------------------------------------ main step
    def on_bar(self, rs: RuleSeries, i: int, immediate_market: bool = False, entries_allowed: bool = True,
               strategy_exits: bool = True) -> List[dict]:
        """Process completed bar i. Returns the actions taken, for the decision log.

        Backtests pass immediate_market=False: a market order decided at bar i fills at bar
        i+1's open. The live runtime passes True: the paper engine fills it now at the live
        price. entries_allowed=False is used when catching up after downtime: resting stops and
        targets are honoured (as orders resting at a venue would have been), no new trades."""
        f = rs.frame
        t = f.t[i]
        if self.last_bar_time is not None and t <= self.last_bar_time:
            return []                           # already processed (restart / duplicate delivery)
        self.last_bar_time = t
        out: List[dict] = []
        o, h, l, cl = f.o[i], f.h[i], f.l[i], f.c[i]
        if f.sess[i] != self.day:
            self.day, self.trades_today = f.sess[i], 0
        # 1) orders waiting for this bar
        if self.pending is not None:
            p = self.pending
            if p.kind == "market":
                self.pending = None
                if p.exit:
                    if self.pos:
                        px = self.filler.market_price(-self.pos.side, o, self.pos.qty) or o
                        out.append(self._close(f, i, px, p.reason, "taker"))
                elif entries_allowed:
                    out.extend(self._open(f, i, p, self.filler.market_price(p.side, o, 0) or o, "taker"))
            elif t > p.expires_time or not entries_allowed:
                out.append({"action": "order_expired", "bar": t, "kind": p.kind})
                self.pending = None
            else:
                px = None
                if p.kind in ("stop", "oco"):
                    legs = [p]
                    if p.kind == "oco" and p.other:
                        q = Pending(**{**p.__dict__, **p.other, "other": None})
                        legs.append(q)
                    hit = [x for x in legs if (x.side > 0 and h >= x.price) or (x.side < 0 and l <= x.price)]
                    if len(hit) == 2:
                        # both sides traded this bar: the order of events is unknown, so assume the leg nearer the
                        # open filled first (and its stop is then tested in the same bar)
                        hit.sort(key=lambda x: abs(x.price - o))
                    if hit:
                        p = hit[0]
                        px = self.filler.stop_price(p.side, max(p.price, o) if p.side > 0 else min(p.price, o), o)
                else:
                    px = self.filler.limit_fill(p.side, p.price, o, h, l)
                if px is not None:
                    self.pending = None
                    out.extend(self._open(f, i, p, px, "taker" if p.kind in ("stop", "oco") else "maker", intrabar=True))
        # 2) protective exits inside this bar (stop before target: the conservative assumption)
        if self.pos is not None and self.pos.first_bar <= t:
            if self.broker_managed:
                out.extend(self._broker_target(f, i, immediate_market))
            else:
                out.extend(self._check_exits(f, i, entry_bar=self.pos.intrabar_entry and self.pos.first_bar == t))
        # 3) end-of-bar decisions
        flat_due = self._flat_due(f, i)
        if not strategy_exits:
            if self.pos is not None and self.pos.first_bar <= t:
                ps = self.pos
                ps.mfe = max(ps.mfe, ((h - ps.entry_price) if ps.side > 0 else (ps.entry_price - l)) / ps.risk_per_unit)
                ps.mae = min(ps.mae, ((l - ps.entry_price) if ps.side > 0 else (ps.entry_price - h)) / ps.risk_per_unit)
            return out
        if self.pos is not None and self.pos.first_bar <= t and self.awaiting is None:
            ps = self.pos
            ps.mfe = max(ps.mfe, ((h - ps.entry_price) if ps.side > 0 else (ps.entry_price - l)) / ps.risk_per_unit)
            ps.mae = min(ps.mae, ((l - ps.entry_price) if ps.side > 0 else (ps.entry_price - h)) / ps.risk_per_unit)
            held = (t - ps.first_bar) // f.step + 1
            reason = None
            if flat_due:
                reason = "session end: day trades are closed before the close"
            elif self._rule(rs, "exit_long" if ps.side > 0 else "exit_short", i):
                reason = "exit rule"
            elif self.d.get("max_bars") and held >= int(self.d["max_bars"]):
                reason = f"time stop ({self.d['max_bars']} bars)"
            if reason:
                if immediate_market:
                    self.awaiting = {"kind": "exit", "reason": reason}
                    out.append({"action": "intent", "kind": "exit", "bar": t, "side": -ps.side, "qty": ps.qty,
                                "ref_price": cl, "reason": reason, "reduce_only": True})
                elif flat_due or not self._next_in_session(f, i):
                    out.append(self._close(f, i, self.filler.market_price(-ps.side, cl, ps.qty) or cl, reason, "taker"))
                else:
                    self.pending = Pending(-ps.side, "market", None, t, t + f.step, None, False, None, False, reason, exit=True)
                    out.append({"action": "exit_ordered", "bar": t, "reason": reason})
            else:
                self._update_trail(rs, i)
        if entries_allowed and self.pos is None and self.pending is None and self.awaiting is None and not flat_due:
            out.extend(self._consider_entry(f, rs, i, immediate_market))
        return out

    # ------------------------------------------------------------------ helpers
    def _rule(self, rs, name, i):
        v = rs.values.get(name)
        return bool(v and v[i])

    def _next_in_session(self, f: Frame, i: int) -> bool:
        return i + 1 < f.n and f.sess[i + 1] == f.sess[i]

    def _flat_due(self, f: Frame, i: int) -> bool:
        if self.flat_before is None:                     # swing: held through session ends
            return False
        if f.sess[i] < 0:
            return True
        return (f.sess_close[i] - (f.t[i] + f.step)) <= self.flat_before * 60_000

    def _in_entry_window(self, f: Frame, i: int) -> bool:
        tod_close = f.tod[i] + f.step // 60_000        # the decision is made at the bar's close
        if self.entry_start is not None and tod_close < self.entry_start:
            return False
        if self.entry_end is not None and tod_close > self.entry_end:
            return False
        return True

    def entry_check(self, rs: RuleSeries, i: int) -> Tuple[Optional[int], str]:
        """(side or None, reason) for bar i, without acting. Used for explanations."""
        f = rs.frame
        if f.sess[i] < 0:
            return None, "outside the session"
        if not self._in_entry_window(f, i):
            return None, "outside the entry window"
        if self.trades_today >= int(self.d.get("max_trades_per_day") or 10 ** 9):
            return None, "daily trade limit reached"
        if f.t[i] - self.last_exit_time <= int(self.d.get("cooldown_bars") or 0) * f.step:
            return None, "cooling down after the last exit"
        if f.t[i] in f.suspect:
            return None, "bar flagged suspect by data quality"
        filt = all(self._rule(rs, k, i) for k in rs.values if k.startswith("filter_"))
        for side, name in ((1, "entry_long"), (-1, "entry_short")):
            if name in rs.values and self._rule(rs, name, i):
                if not filt:
                    return None, f"{'long' if side > 0 else 'short'} entry rule true but filters not met"
                if side < 0 and not self.can_short:
                    return None, "short entry rule true but shorting is not allowed on this instrument"
                return side, f"{'long' if side > 0 else 'short'} entry rule true"
        unknown = [k for k in rs.values if k.startswith("entry_") and rs.values[k][i] is None]
        if unknown:
            return None, "entry rule unknown (indicators warming up or inputs missing)"
        return None, "entry rule false"

    def _consider_entry(self, f: Frame, rs: RuleSeries, i: int, immediate: bool) -> List[dict]:
        side, why = self.entry_check(rs, i)
        if side is None:
            return [{"action": "skip", "bar": f.t[i], "reason": why}] if "filters" in why or "shorting" in why else []
        return self._place_entry(f, rs, i, side, immediate)

    def _stop_plan(self, rs: RuleSeries, i: int, side: int) -> Tuple[Optional[float], bool]:
        st = self.d["stop"]
        t = st.get("type")
        if t == "atr":
            a = rs.values["atr_stop"][i]
            return (None, True) if a is None else (float(st.get("mult", 2.0)) * a, True)
        if t == "pct":
            return (float(st.get("pct", 1.0)) / 100.0, True)          # fraction of the fill price
        lv = rs.values.get("stop_long" if side > 0 else "stop_short")
        v = lv[i] if lv else None
        if v is not None and st.get("buffer_atr"):
            a = rs.values["atr_stop"][i]
            if a is None:
                return None, False
            v = v - side * float(st["buffer_atr"]) * a
        return v, False

    def _target_plan(self, rs: RuleSeries, i: int, side: int) -> Tuple[Optional[float], bool]:
        tg = self.d["target"]
        if tg.get("type") == "r":
            return float(tg.get("r", 2.0)), True
        if tg.get("type") == "level":
            lv = rs.values.get("target_long" if side > 0 else "target_short")
            return (lv[i] if lv else None), False
        return None, False

    def _place_entry(self, f, rs, i, side, immediate) -> List[dict]:
        t = f.t[i]
        stop_ref, dist = self._stop_plan(rs, i, side)
        if stop_ref is None:
            return [{"action": "skip", "bar": t, "reason": "stop level unavailable (warming up)", "side": side}]
        tgt, is_r = self._target_plan(rs, i, side)
        kind = self.d["order"]["type"]
        reason = f"{'long' if side > 0 else 'short'} entry rule true at bar close"
        price = None
        if kind != "market":
            pv = rs.values.get(f"order_{'long' if side > 0 else 'short'}")
            price = pv[i] if pv else None
            if price is None:
                return [{"action": "skip", "bar": t, "reason": "order price unavailable", "side": side}]
        ttl = int(self.d["order"].get("ttl_bars", 1)) if kind != "market" else 1
        p = Pending(side, kind, price, t, t + ttl * f.step, stop_ref, dist, tgt, is_r, reason)
        if kind == "oco":
            ov = rs.values.get("order_short" if side > 0 else "order_long")
            op = ov[i] if ov else None
            s2, d2 = self._stop_plan(rs, i, -side)
            t2, r2 = self._target_plan(rs, i, -side)
            if op is None or s2 is None:
                return [{"action": "skip", "bar": t, "reason": "bracket price unavailable", "side": side}]
            p.other = {"side": -side, "price": op, "stop_ref": s2, "stop_is_distance": d2, "target_ref": t2,
                       "target_is_r": r2, "reason": f"{'short' if side > 0 else 'long'} bracket leg"}
        if kind == "market" and immediate:
            ref = f.c[i]
            plan = self._plan(p, ref)
            if plan is None:
                return [{"action": "skip", "bar": t, "reason": "reference price already beyond the stop", "side": side}]
            qty, stop, target = plan
            if qty <= 0 or qty * ref < self.min_notional:
                return [{"action": "rejected", "bar": t, "reason": f"order size below the venue minimum ({qty:.8g} units)"}]
            self.awaiting = {"kind": "entry", "pending": dict(p.__dict__), "first_bar": t + f.step}
            return [{"action": "intent", "kind": "entry", "bar": t, "side": side, "qty": qty, "ref_price": ref,
                     "stop": stop, "target": target, "reason": reason, "reduce_only": False}]
        self.pending = p
        return [{"action": "order_placed", "bar": t, "kind": kind, "side": side, "price": price}]

    def _plan(self, p: Pending, px: float):
        """(qty, stop, target) for an entry at price px, or None if px is already beyond the stop."""
        side = p.side
        if p.stop_is_distance:
            d = p.stop_ref * px if self.d["stop"].get("type") == "pct" else p.stop_ref
            stop = px - side * d
        else:
            stop = p.stop_ref
        risk = (px - stop) * side if stop is not None else None
        if risk is None or risk <= 0:
            return None
        eq = self.equity_fn()
        rp, mp = self._sizing()
        qty = eq * rp / 100.0 / risk * float(p.size or 1.0)
        qty = min(qty, eq * mp / 100.0 / px)
        if self.lot:
            qty = math.floor(qty / self.lot + 1e-9) * self.lot
        target = None
        if p.target_ref is not None:
            target = px + side * p.target_ref * risk if p.target_is_r else p.target_ref
            if (target - px) * side <= 0:
                target = None
        return qty, stop, target

    def _sizing(self) -> Tuple[float, float]:
        sz = self.d.get("sizing") or {}
        rp = self.risk_pct_override if self.risk_pct_override is not None else float(sz.get("risk_pct", 0.5))
        mp = float(sz.get("max_notional_pct", 100.0))
        if self.max_notional_pct_override is not None:
            mp = min(mp, self.max_notional_pct_override)
        return rp, mp

    def _broker_target(self, f, i, immediate_market: bool) -> List[dict]:
        """Stops rest on the broker; a profit target reached on a completed bar becomes an exit order."""
        ps = self.pos
        if ps.target is None or self.awaiting is not None or not immediate_market:
            return []
        h, l = f.h[i], f.l[i]
        if (ps.side > 0 and h >= ps.target) or (ps.side < 0 and l <= ps.target):
            self.awaiting = {"kind": "exit", "reason": "profit target reached"}
            return [{"action": "intent", "kind": "exit", "bar": f.t[i], "side": -ps.side, "qty": ps.qty,
                     "ref_price": f.c[i], "reason": "profit target reached", "reduce_only": True}]
        return []

    def effective_stop(self) -> Optional[float]:
        ps = self.pos
        if ps is None:
            return None
        stops = [x for x in (ps.stop, ps.trail) if x is not None]
        return (max(stops) if ps.side > 0 else min(stops)) if stops else None

    # ------------------------------------------------------------------ live fills (paper engine callbacks)
    def apply_entry_fill(self, px: float, qty: float, fee: float, fill_time: int) -> dict:
        """The paper engine filled (possibly partially) an entry intent."""
        aw = self.awaiting or {}
        self.awaiting = None
        p = Pending(**aw["pending"])
        side = p.side
        if p.stop_is_distance:
            d = p.stop_ref * px if self.d["stop"].get("type") == "pct" else p.stop_ref
            stop = px - side * d
        else:
            stop = p.stop_ref
        risk = (px - stop) * side
        if risk <= 0:                                  # slipped past the stop: exit on the next bar check
            risk = abs(px) * 1e-4
        target = None
        if p.target_ref is not None:
            target = px + side * p.target_ref * risk if p.target_is_r else p.target_ref
            if (target - px) * side <= 0:
                target = None
        self.pos = Position(side, qty, px, fill_time, aw["first_bar"], stop, target, risk, None, fee, p.reason)
        self.trades_today += 1
        return {"action": "entry", "side": side, "qty": qty, "price": px, "stop": stop, "target": target, "fee": fee}

    def apply_exit_fill(self, f: Frame, i: int, px: float, fee: float, reason: str) -> dict:
        self.awaiting = None
        ps = self.pos
        if ps is None:
            return {"action": "noop"}
        # fee for the exit leg is supplied by the paper engine; _close adds the filler's fee, so undo that
        saved = self.filler
        self.filler = _FixedFee(fee)
        try:
            return self._close(f, i, px, reason, "taker")
        finally:
            self.filler = saved

    def intent_rejected(self, reason: str) -> dict:
        aw = self.awaiting
        self.awaiting = None
        return {"action": "intent_rejected", "kind": (aw or {}).get("kind"), "reason": reason}

    def _open(self, f, i, p: Pending, px: float, liquidity: str, intrabar=False, after_close=False) -> List[dict]:
        side = p.side
        t = f.t[i]
        if p.stop_is_distance:
            d = p.stop_ref * px if self.d["stop"].get("type") == "pct" else p.stop_ref
            stop = px - side * d
        else:
            stop = p.stop_ref
        risk = (px - stop) * side if stop is not None else None
        if risk is None or risk <= 0:
            return [{"action": "skip", "bar": t, "reason": "fill price already beyond the stop", "side": side}]
        eq = self.equity_fn()
        rp, mp = self._sizing()
        qty = eq * rp / 100.0 / risk * float(p.size or 1.0)
        qty = min(qty, eq * mp / 100.0 / px)
        if self.lot:
            qty = math.floor(qty / self.lot + 1e-9) * self.lot
        if qty <= 0 or qty * px < self.min_notional:
            return [{"action": "rejected", "bar": t, "reason": f"order size below the venue minimum ({qty:.8g} units)"}]
        target = None
        if p.target_ref is not None:
            target = px + side * p.target_ref * risk if p.target_is_r else p.target_ref
            if (target - px) * side <= 0:
                target = None                      # level already passed: managed by stop and exit rules
        fee = self.filler.fee(qty * px, liquidity)
        first = t + f.step if after_close else t
        self.pos = Position(side, qty, px, t + f.step if after_close else t, first, stop, target, risk, None, fee,
                            p.reason, intrabar_entry=intrabar)
        self.trades_today += 1
        return [{"action": "entry", "bar": t, "side": side, "qty": qty, "price": px, "stop": stop, "target": target,
                 "fee": fee, "reason": p.reason, "liquidity": liquidity}]

    def _check_exits(self, f, i, entry_bar=False) -> List[dict]:
        """Stops (and targets) against bar i's range. On the bar an intrabar entry happened the
        order of events is unknown, so only the stop is tested (the conservative reading)."""
        ps = self.pos
        o, h, l = f.o[i], f.h[i], f.l[i]
        stops = [x for x in (ps.stop, ps.trail) if x is not None]
        eff = (max(stops) if ps.side > 0 else min(stops)) if stops else None
        if eff is not None and ((ps.side > 0 and l <= eff) or (ps.side < 0 and h >= eff)):
            gapped = not entry_bar and ((ps.side > 0 and o <= eff) or (ps.side < 0 and o >= eff))
            px = self.filler.stop_price(-ps.side, o if gapped else eff, o)
            why = "trailing stop" if (ps.trail is not None and eff == ps.trail and ps.trail != ps.stop) else "stop loss"
            return [self._close(f, i, px, why + (" (gapped through: filled at the open)" if gapped else ""), "taker")]
        if ps.target is not None and not entry_bar and ((ps.side > 0 and h >= ps.target) or (ps.side < 0 and l <= ps.target)):
            if (ps.side > 0 and o >= ps.target) or (ps.side < 0 and o <= ps.target):
                px = o
            else:
                px = self.filler.limit_fill(-ps.side, ps.target, o, h, l)
            if px is not None:
                return [self._close(f, i, px, "profit target", "maker")]
        return []

    def _update_trail(self, rs: RuleSeries, i: int):
        ps = self.pos
        tr = self.d["trail"]
        t = tr.get("type")
        if t == "none" or ps is None:
            return
        f = rs.frame
        if t == "atr":
            a = rs.values["atr_trail"][i]
            if a is None or ps.mfe < float(tr.get("activate_r", 0)):
                return
            lvl = f.c[i] - ps.side * float(tr.get("mult", 3.0)) * a
        else:
            lv = rs.values.get("trail_long" if ps.side > 0 else "trail_short")
            lvl = lv[i] if lv else None
            if lvl is None:
                return
        if ps.trail is None or (lvl - ps.trail) * ps.side > 0:
            ps.trail = lvl

    def force_exit(self, f: Frame, i: int, px: float, reason: str) -> dict:
        """Emergency stop / operator flatten."""
        return self._close(f, i, px, reason, "taker")

    def _close(self, f, i, px: float, reason: str, liquidity: str) -> dict:
        ps = self.pos
        fee = self.filler.fee(ps.qty * px, liquidity)
        gross = (px - ps.entry_price) * ps.side * ps.qty
        fees = ps.fees + fee
        pnl = gross - fees
        r = pnl / (ps.risk_per_unit * ps.qty) if ps.risk_per_unit and ps.qty else None
        exit_t = f.t[i] + f.step
        bars = max(1, (f.t[i] - ps.first_bar) // f.step + 1)
        tr = Trade(self.c.id, self.instrument, ps.side, ps.qty, ps.entry_time, ps.entry_price, exit_t, px, fees,
                   pnl, r, bars, ps.reason, reason, round(ps.mfe, 4), round(ps.mae, 4))
        self.trades.append(tr)
        self.pos = None
        self.last_exit_time = f.t[i]
        return {"action": "exit", "bar": f.t[i], "price": px, "reason": reason, "pnl": pnl, "r": r, "fee": fee,
                "liquidity": liquidity, "trade": tr}


class _FixedFee(Filler):
    def __init__(self, fee):
        self._fee = fee

    def fee(self, notional, liquidity):
        return self._fee


def _hhmm(s):
    if not s:
        return None
    h, m = str(s).split(":")
    return int(h) * 60 + int(m)
