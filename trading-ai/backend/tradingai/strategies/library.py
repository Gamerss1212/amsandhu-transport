"""The strategy template library and every template's formal contract (sections 141-142, 231-232).

A template = base signal generator x entry filter x exit model. The library is built, then pruned: two
(generator, filter) combinations whose signals agree on 95% or more of active bars across three reference series are
the same strategy with a different name, and the later one is dropped (novelty check). The counts reported by
`summary()` are after pruning, and runnable templates are counted separately from those that need data this
installation does not have.

Every template exposes the same lifecycle (Strategy): initialize, on_market_data, generate_signal,
calculate_position, generate_order_intent, on_fill, on_exit, reset.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from functools import lru_cache
from typing import Optional

import numpy as np

from tradingai.data.bars import Bars
from tradingai.features import indicators as I
from tradingai.features.registry import FeatureFrame
from tradingai.market.instruments import Instrument, MarketType, size_from_risk
from tradingai.strategies.signals import GEN, Generator, evaluate

VERSION = "1.0"
CREATED = "2026-10-08"

FILTERS = {
    "none": "no extra entry filter",
    "trend200": "longs only above the 200-bar average, shorts only below it",
    "adx": "trend/breakout/momentum entries need ADX>=20; reversion entries need ADX<25",
    "vol_band": "no new entries when 20-bar volatility is in its top or bottom 10% of the last 250 bars",
    "session": "no entries in the first/last 3 bars of a session, at the FX rollover, or on crypto weekends",
    "relvol": "entries need at least average volume (relative volume >= 1)",
}
EXITS = {
    "flip": {"desc": "exit when the signal turns flat or reverses", "params": {}},
    "atr_bracket": {"desc": "stop 2 ATR, target 2R (4 ATR), whichever comes first; signal flip also exits",
                    "params": {"stop_atr": 2.0, "target_r": 2.0}},
    "time": {"desc": "exit after 20 bars, or on a 2-ATR stop", "params": {"max_bars": 20, "stop_atr": 2.0}},
    "trail": {"desc": "3-ATR trailing stop; signal flip also exits", "params": {"trail_atr": 3.0}},
}
TREND_FAMILIES = {"trend", "momentum", "breakout", "vwap", "volatility", "seasonality", "forex", "cross_market"}


def entry_mask(ff: FeatureFrame, filt: str, family: str) -> tuple[np.ndarray, np.ndarray]:
    """(may enter long, may enter short) per bar for an entry filter."""
    n = len(ff.c)
    yes = np.ones(n, dtype=bool)
    if filt == "none":
        return yes, yes
    if filt == "trend200":
        s = I.sma(ff.c, 200)
        return np.nan_to_num(ff.c > s) > 0, np.nan_to_num(ff.c < s) > 0
    if filt == "adx":
        a = np.nan_to_num(I.adx(ff.h, ff.l, ff.c, 14)[0])
        m = a >= 20 if family in TREND_FAMILIES else (a < 25) & (a > 0)
        return m, m
    if filt == "vol_band":
        r = I.percent_rank(I.realized_vol(ff.c, 20, ff.ppy), 250)
        m = (r > 10) & (r < 90)
        return m, m
    if filt == "session":
        first = np.r_[True, ff.session[1:] != ff.session[:-1]]
        k = np.zeros(n)
        for i in range(1, n):
            k[i] = 0 if first[i] else k[i - 1] + 1
        last = np.r_[ff.session[1:] != ff.session[:-1], True]
        to_end = np.zeros(n)
        for i in range(n - 2, -1, -1):
            to_end[i] = 0 if last[i] else to_end[i + 1] + 1
        m = (k >= 3) & (to_end >= 3)
        if ff.calendar == "CRYPTO":
            m = (((ff.b.ts // 86_400_000) + 3) % 7) < 5
        return m, m
    if filt == "relvol":
        if not np.any(ff.v > 0):
            return yes, yes
        m = np.nan_to_num(I.rvol(ff.v, 20)) >= 1.0
        return m, m
    raise KeyError(filt)


def apply_filter(sig: np.ndarray, ok_long: np.ndarray, ok_short: np.ndarray) -> np.ndarray:
    """A filter gates NEW entries only: a position already open continues while the signal holds it."""
    out = np.zeros(len(sig))
    pos = 0.0
    for i, s in enumerate(sig):
        if s == pos:
            out[i] = pos
            continue
        if s == 0:
            pos = 0.0
        elif s > 0:
            pos = 1.0 if ok_long[i] else 0.0
        else:
            pos = -1.0 if ok_short[i] else 0.0
        out[i] = pos
    return out


@dataclass(frozen=True)
class StrategySpec:
    strategy_id: str
    name: str
    family: str
    version: str
    description: str
    economic_hypothesis: str
    supported_markets: tuple[str, ...]
    supported_timeframes: tuple[str, ...]
    required_features: tuple[str, ...]
    required_data: tuple[str, ...]
    parameters: dict
    parameter_grid: dict
    entry_rules: str
    exit_rules: str
    stop_rules: str
    position_sizing: str
    session_rules: str
    event_filters: str
    execution_model: str
    invalidation_conditions: str
    known_failure_regimes: str
    risk_class: str
    research_sources: tuple[tuple[str, str], ...]
    generator: str
    entry_filter: str
    exit_model: str
    pairs: bool = False
    created_at: str = CREATED
    updated_at: str = CREATED

    @property
    def runnable(self) -> bool:
        return not self.required_data

    def as_dict(self) -> dict:
        d = {k: getattr(self, k) for k in self.__dataclass_fields__}
        d["runnable"] = self.runnable
        d["status_note"] = ("UNAVAILABLE: needs " + ", ".join(self.required_data)) if self.required_data else "ok"
        return d


def _risk_class(g: Generator, exit_model: str) -> str:
    if g.family in ("mean_reversion",) and exit_model == "flip":
        return "high (no hard stop)"
    if exit_model in ("atr_bracket", "time", "trail"):
        return "medium (hard stop)"
    return "medium"


def make_spec(g: Generator, filt: str, exit_model: str) -> StrategySpec:
    ex = EXITS[exit_model]
    sid = f"{g.key}.{filt}.{exit_model}"
    stop = ("stop at 2 ATR from entry" if exit_model in ("atr_bracket", "time") else
            "3-ATR trailing stop" if exit_model == "trail" else "no price stop: exits on the signal")
    return StrategySpec(
        strategy_id=sid, name=f"{g.key.replace('_', ' ')} | {filt} | {exit_model}", family=g.family, version=VERSION,
        description=f"{g.hypothesis}. Entry filter: {FILTERS[filt]}. Exit: {ex['desc']}.",
        economic_hypothesis=g.hypothesis, supported_markets=g.markets, supported_timeframes=g.timeframes,
        required_features=g.features, required_data=g.requires, parameters=dict(g.params, **ex["params"]),
        parameter_grid=dict(g.grid), entry_rules=f"{g.key} signal turns non-zero and the '{filt}' filter allows it; "
        "orders go in at the NEXT bar's open (never the signal bar's close)",
        exit_rules=ex["desc"], stop_rules=stop,
        position_sizing="risk-based: (account risk budget) / (stop distance x contract multiplier + costs), rounded "
                        "down; capped by the deterministic risk limits",
        session_rules="trades only while the instrument's market is open; equity-index futures stay flat in the roll "
                      "window", event_filters="none by default; event calendar blocks entries when connected",
        execution_model="market order at next open with modelled spread, slippage and fees; limit-order variant in "
                        "paper trading", invalidation_conditions="drawdown beyond 2x the backtest's max drawdown, or "
        "live/backtest expectancy gap beyond its bootstrap interval -> moved to PAPER_ONLY",
        known_failure_regimes=g.failure_regimes or "not documented: see the regime breakdown of its backtest",
        risk_class=_risk_class(g, exit_model), research_sources=((g.grade, g.source),), generator=g.key,
        entry_filter=filt, exit_model=exit_model, pairs=g.pairs)


# ----------------------------------------------------------------------------- the library with novelty pruning

def _reference_frames() -> list[FeatureFrame]:
    from tradingai.data.providers.demo import ANCHOR, Demo
    d = Demo()
    out = []
    for sym in ("DEMO-TREND", "DEMO-RANGE", "DEMO-VOLATILE"):
        b = d.fetch(f"DEMO:{sym}", sym, "15m", ANCHOR, ANCHOR + 50 * 86_400_000)
        out.append(FeatureFrame(b.slice(max(0, len(b) - 3000), len(b)), "CRYPTO", "crypto"))
    return out


CACHE_FILE = __import__("pathlib").Path(__file__).with_name("library_cache.json")


def _fingerprint() -> str | None:
    import hashlib
    import inspect
    from tradingai.strategies import signals
    try:
        src = inspect.getsource(signals) + inspect.getsource(entry_mask) + inspect.getsource(apply_filter)
    except (OSError, TypeError):           # a packaged build without source files: the shipped cache was made from it
        return None
    return hashlib.sha256(src.encode()).hexdigest()[:16]


@lru_cache(maxsize=1)
def build() -> dict:
    """All templates, after the novelty check. The pruning result is cached in library_cache.json, keyed by a hash of
    the signal code, so it is recomputed (about 20 s) only when a generator or filter changes."""
    import json
    fp = _fingerprint()
    kept: list[tuple[str, str]] = []
    dropped: list[dict] = []
    try:
        d = json.loads(CACHE_FILE.read_text())
        if d.get("fingerprint") == fp or (fp is None and d.get("kept")):
            kept, dropped = [tuple(k) for k in d["kept"]], d["dropped"]
    except (OSError, ValueError, KeyError):
        pass
    if not kept:
        kept, dropped = _prune()
        try:
            CACHE_FILE.write_text(json.dumps({"fingerprint": fp, "kept": kept, "dropped": dropped}))
        except OSError:
            pass
    return _assemble(kept, dropped)


def _prune() -> tuple[list[tuple[str, str]], list[dict]]:
    frames = _reference_frames()
    kept: list[tuple[str, str]] = []
    kept_sigs: list[list[np.ndarray]] = []
    dropped: list[dict] = []
    for g in GEN.values():
        if g.requires or g.pairs:
            continue
        for filt in g.filters:
            sigs = []
            for ff in frames:
                if ff.market not in g.markets and not set(g.markets) & {"crypto"}:
                    sigs.append(np.zeros(len(ff.c)))
                    continue
                s = evaluate(g.key, ff)
                ml, ms = entry_mask(ff, filt, g.family)
                sigs.append(apply_filter(s, ml, ms))
            dup = None
            for (k_gen, k_filt), ks in zip(kept, kept_sigs):
                agree = []
                for a, b in zip(sigs, ks):
                    active = (a != 0) | (b != 0)
                    agree.append(1.0 if not active.any() else float((a[active] == b[active]).mean()))
                if min(agree) >= 0.95 and any(np.any(s != 0) for s in sigs):
                    dup = f"{k_gen}.{k_filt}"
                    break
            if dup:
                dropped.append({"candidate": f"{g.key}.{filt}", "same_as": dup})
                continue
            kept.append((g.key, filt))
            kept_sigs.append(sigs)
    return kept, dropped


def _assemble(kept: list[tuple[str, str]], dropped: list[dict]) -> dict:
    specs: dict[str, StrategySpec] = {}
    for key, filt in kept:
        g = GEN[key]
        for ex in g.exits:
            s = make_spec(g, filt, ex)
            specs[s.strategy_id] = s
    for g in GEN.values():
        if g.pairs:
            for filt in g.filters:
                for ex in g.exits:
                    s = make_spec(g, filt, ex)
                    specs[s.strategy_id] = s
        elif g.requires:
            s = make_spec(g, "none", "atr_bracket")
            specs[s.strategy_id] = s
    return {"specs": specs, "dropped": dropped, "signal_templates": len(kept)}


def specs() -> dict[str, StrategySpec]:
    return build()["specs"]


def summary() -> dict:
    b = build()
    sp = b["specs"].values()
    fam: dict[str, int] = {}
    for s in sp:
        fam[s.family] = fam.get(s.family, 0) + 1
    return {"templates_total": len(b["specs"]), "runnable": sum(1 for s in sp if s.runnable),
            "need_external_data": sum(1 for s in sp if not s.runnable),
            "base_generators": len(GEN), "distinct_entry_filter_templates": b["signal_templates"],
            "dropped_as_near_duplicates": len(b["dropped"]), "by_family": fam,
            "exit_models": list(EXITS), "filters": list(FILTERS)}


# ----------------------------------------------------------------------------- the common lifecycle

@dataclass
class Signal:
    direction: int                 # -1, 0, +1
    as_of: int                     # available_at of the bar it was computed on (UTC ms)
    strategy_id: str
    reasons: dict = field(default_factory=dict)


@dataclass
class OrderIntent:
    strategy_id: str
    instrument_id: str
    side: str                      # buy / sell
    quantity: Decimal
    order_type: str
    limit_price: Optional[Decimal]
    stop_price: Optional[Decimal]
    reason: str


MARKET_OF = {MarketType.CRYPTO_SPOT: "crypto", MarketType.CRYPTO_PERP: "crypto", MarketType.STOCK: "stock",
             MarketType.ETF: "etf", MarketType.FX_OTC: "fx", MarketType.FUTURE: "future",
             MarketType.FX_FUTURE: "future", MarketType.INDEX_REFERENCE: "index"}
SHORTABLE = {"fx", "future"}           # stocks/ETFs: no borrow data -> long-only; spot crypto: no shorting


class Strategy:
    def __init__(self, spec: StrategySpec, params: Optional[dict] = None):
        self.spec = spec
        self.params = dict(spec.parameters, **(params or {}))
        self.ff: Optional[FeatureFrame] = None
        self.last_signal: Optional[Signal] = None
        self.position: Decimal = Decimal(0)
        self.fills: list[dict] = []

    def initialize(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.ff, self.last_signal, self.position, self.fills = None, None, Decimal(0), []

    def on_market_data(self, bars: Bars, calendar: str, market: str, other_close: Optional[np.ndarray] = None) -> None:
        self.ff = FeatureFrame(bars, calendar, market)
        self._other = other_close

    def signal_series(self) -> np.ndarray:
        if self.ff is None:
            raise RuntimeError("no market data yet")
        gp = {k: v for k, v in self.params.items() if k in GEN[self.spec.generator].params}
        s = evaluate(self.spec.generator, self.ff, gp, getattr(self, "_other", None))
        ml, ms = entry_mask(self.ff, self.spec.entry_filter, self.spec.family)
        s = apply_filter(s, ml, ms)
        if self.ff.market not in SHORTABLE:
            s = np.maximum(s, 0.0)
        return s

    def generate_signal(self) -> Signal:
        s = self.signal_series()
        b = self.ff.b
        reasons = {"generator": self.spec.generator, "filter": self.spec.entry_filter,
                   "raw_last": float(s[-1]) if len(s) else 0.0, "bars": len(b)}
        self.last_signal = Signal(int(s[-1]) if len(s) else 0, int(b.available_at[-1]) if len(b) else 0,
                                  self.spec.strategy_id, reasons)
        return self.last_signal

    def stop_distance(self) -> Optional[float]:
        a = I.atr(self.ff.h, self.ff.l, self.ff.c, 14)[-1]
        if not np.isfinite(a) or a <= 0:
            return None
        mult = self.params.get("stop_atr") or self.params.get("trail_atr") or 2.0
        return float(a * mult)

    def calculate_position(self, signal: Signal, inst: Instrument, risk_budget: Decimal,
                           cost_per_unit: Decimal = Decimal(0)) -> Decimal:
        """Target quantity (signed) from the risk budget and the stop distance; 0 when no stop can be measured."""
        if signal.direction == 0:
            return Decimal(0)
        dist = self.stop_distance()
        if dist is None:
            return Decimal(0)
        px = Decimal(str(float(self.ff.c[-1])))
        stop = px - Decimal(str(dist)) if signal.direction > 0 else px + Decimal(str(dist))
        q = size_from_risk(inst, risk_budget, px, stop, cost_per_unit=cost_per_unit)
        return q if signal.direction > 0 else -q

    def generate_order_intent(self, inst: Instrument, target: Decimal) -> Optional[OrderIntent]:
        delta = target - self.position
        if delta == 0:
            return None
        return OrderIntent(self.spec.strategy_id, inst.instrument_id, "buy" if delta > 0 else "sell", abs(delta),
                           "market", None, None,
                           f"target {target} from {self.position} ({self.spec.generator}/{self.spec.entry_filter})")

    def on_fill(self, side: str, qty: Decimal, price: Decimal) -> None:
        self.position += qty if side == "buy" else -qty
        self.fills.append({"side": side, "qty": str(qty), "price": str(price)})

    def on_exit(self, reason: str) -> None:
        self.fills.append({"exit": reason})
