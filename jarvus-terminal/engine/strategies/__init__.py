#!/usr/bin/env python3
"""Strategy registry, evaluation context, and the loader for user-written strategies.

A strategy here is a small function that looks at one market and either returns a
Signal or returns None. It does not place orders, size positions or decide anything
about risk — those belong to one place each, and keeping them out means a strategy
stays small enough to read in one sitting and cheap enough to run hundreds of times
per scan.

Adding your own takes one file. Drop it in `engine/strategies/custom/` and it is
picked up on the next run; there is a worked example in that folder.
"""

from __future__ import annotations

import importlib.util
import os
import traceback
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from engine import indicators as ind


@dataclass
class Signal:
    """One strategy's opinion about one market.

    `strength` is deliberately not a probability. It is the strategy's own sense of
    how textbook this instance is, on 0..1, and it is only ever compared against
    other readings from the same strategy. What a strategy is actually worth is
    decided by its measured record, not by what it claims here.
    """
    direction: str                      # "long" | "flat"
    strength: float = 0.5
    reason: str = ""
    stop_hint: Optional[float] = None   # a level the strategy considers invalidating
    tags: List[str] = field(default_factory=list)


@dataclass
class StrategySpec:
    name: str
    fn: Callable
    group: str = "other"
    timeframes: List[str] = field(default_factory=lambda: ["1h", "4h"])
    description: str = ""
    source: str = "builtin"
    enabled: bool = True
    params: Dict = field(default_factory=dict)


REGISTRY: Dict[str, StrategySpec] = {}


def strategy(name: str, group: str = "other", description: str = "",
             timeframes: List[str] = None, params: Dict = None, source: str = "builtin"):
    """Decorator that registers a strategy under a stable name."""
    def wrap(fn):
        REGISTRY[name] = StrategySpec(name=name, fn=fn, group=group, description=description,
                                      timeframes=timeframes or ["1h", "4h"],
                                      params=params or {}, source=source)
        return fn
    return wrap


class _Prefix:
    """A read-only view of the first n elements of a list, without copying it.

    The backtester walks a market bar by bar and each step needs "the data as it was
    then". Slicing a 3,000-bar history at every step copies three thousand floats,
    times sixty-five strategies, times every bar, which turns a minute of work into an
    afternoon of it. This presents the prefix instead: negative indices resolve
    against n rather than the underlying length, so `close[-1]` means the bar under
    consideration and not the last bar that ever happened. That is also the
    difference between a backtest and a lookahead bug.
    """
    __slots__ = ("_d", "_n")

    def __init__(self, data, n: int):
        self._d = data
        self._n = max(0, min(n, len(data) if data is not None else 0))

    def __len__(self):
        return self._n

    def __bool__(self):
        return self._n > 0

    def __getitem__(self, i):
        if isinstance(i, slice):
            start, stop, step = i.indices(self._n)
            return self._d[start:stop:step]
        if i < 0:
            i += self._n
        if i < 0 or i >= self._n:
            raise IndexError("prefix index out of range")
        return self._d[i]

    def __iter__(self):
        return iter(self._d[:self._n])


class SeriesCache:
    """Indicators computed once over a market's whole history, shared by every
    strategy and every bar of a backtest.

    A 200-period EMA over 3,000 bars is the same array whether it is asked for once
    or a hundred thousand times, so it is computed once and then read from. This is
    the difference between backtesting sixty-five strategies in seconds and in hours.
    """

    def __init__(self, candles: List[dict]):
        self.candles = candles
        self.n = len(candles)
        self.open = [c["open"] for c in candles]
        self.high = [c["high"] for c in candles]
        self.low = [c["low"] for c in candles]
        self.close = [c["close"] for c in candles]
        self.volume = [c["volume"] for c in candles]
        self._ind: Dict[str, object] = {}

    def indicator(self, name: str, params: Dict):
        key = name + ":" + ",".join(f"{k}={v}" for k, v in sorted(params.items()))
        if key not in self._ind:
            try:
                self._ind[key] = ind.compute(name, self.candles, **params)
            except Exception:                      # noqa: BLE001
                self._ind[key] = None
        return self._ind[key]


class Ctx:
    """Everything a strategy can look at, as of one particular bar.

    In a live scan `at` is the last bar. In a backtest it walks forward, and because
    every series is a prefix view the strategy physically cannot read a price that
    had not happened yet.
    """

    def __init__(self, candles: List[dict], symbol: str = "", meta: Dict = None,
                 htf_candles: List[dict] = None, cache: "SeriesCache" = None,
                 at: int = None):
        self.cache = cache or SeriesCache(candles)
        self.n = (at + 1) if at is not None else self.cache.n
        self.symbol = symbol
        self.meta = meta or {}
        self.htf = htf_candles
        self.candles = _Prefix(self.cache.candles, self.n)
        self.open = _Prefix(self.cache.open, self.n)
        self.high = _Prefix(self.cache.high, self.n)
        self.low = _Prefix(self.cache.low, self.n)
        self.close = _Prefix(self.cache.close, self.n)
        self.volume = _Prefix(self.cache.volume, self.n)
        self.price = self.cache.close[self.n - 1] if self.n else 0.0
        self._local: Dict[str, object] = {}

    def ind(self, name: str, **params):
        """An indicator, truncated to this bar. Multi-output indicators come back as
        a tuple of views, so `line, direction = c.ind("supertrend")` still works."""
        key = name + ":" + ",".join(f"{k}={v}" for k, v in sorted(params.items()))
        hit = self._local.get(key)
        if hit is not None:
            return hit
        full = self.cache.indicator(name, params)
        if full is None:
            return None
        if isinstance(full, tuple):
            out = tuple(_Prefix(x, self.n) if isinstance(x, list) else x for x in full)
        elif isinstance(full, list):
            out = _Prefix(full, self.n)
        else:
            out = full                              # scalar results: linreg, zigzag
        self._local[key] = out
        return out

    def last(self, series, back: int = 0):
        """Value `back` bars before this one, or None where it is not defined."""
        if series is None:
            return None
        try:
            ln = len(series)
        except TypeError:
            return None
        i = ln - 1 - back
        if i < 0 or i >= ln:
            return None
        try:
            return series[i]
        except (IndexError, TypeError):
            return None

    def crossed_up(self, a, b, within: int = 1) -> bool:
        """True if series a crossed above series b within the last `within` bars."""
        if a is None or b is None:
            return False
        for k in range(within):
            cur_a, cur_b = self.last(a, k), self.last(b, k)
            pre_a, pre_b = self.last(a, k + 1), self.last(b, k + 1)
            if None in (cur_a, cur_b, pre_a, pre_b):
                continue
            if pre_a <= pre_b and cur_a > cur_b:
                return True
        return False

    def crossed_down(self, a, b, within: int = 1) -> bool:
        if a is None or b is None:
            return False
        for k in range(within):
            cur_a, cur_b = self.last(a, k), self.last(b, k)
            pre_a, pre_b = self.last(a, k + 1), self.last(b, k + 1)
            if None in (cur_a, cur_b, pre_a, pre_b):
                continue
            if pre_a >= pre_b and cur_a < cur_b:
                return True
        return False

    @property
    def atr(self):
        return self.last(self.ind("atr", period=14))

    @property
    def atr_pct(self):
        a = self.atr
        return (a / self.price * 100) if (a and self.price) else None

    def htf_uptrend(self) -> Optional[bool]:
        """Whether the bias timeframe agrees, or None when it is unavailable."""
        if not self.htf or len(self.htf) < 60:
            return None
        hc = [c["close"] for c in self.htf]
        e50 = ind.ema(hc, 50)
        last50 = next((v for v in reversed(e50) if v is not None), None)
        if last50 is None:
            return None
        if len(hc) >= 200:
            e200 = ind.ema(hc, 200)
            last200 = next((v for v in reversed(e200) if v is not None), None)
            if last200 is not None:
                return hc[-1] > last50 > last200
        return hc[-1] > last50


def load_custom(folder: str = None) -> Dict[str, str]:
    """Import every .py in the custom folder so its decorators register.

    A broken user file reports its traceback and is skipped rather than taking the
    whole app down, because the most likely time to have a syntax error in a
    strategy is the moment you are writing one.
    """
    folder = folder or os.path.join(os.path.dirname(os.path.abspath(__file__)), "custom")
    results: Dict[str, str] = {}
    if not os.path.isdir(folder):
        return results
    for fname in sorted(os.listdir(folder)):
        if not fname.endswith(".py") or fname.startswith("_"):
            continue
        path = os.path.join(folder, fname)
        before = set(REGISTRY)
        try:
            spec = importlib.util.spec_from_file_location(f"jarvus_custom_{fname[:-3]}", path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            added = sorted(set(REGISTRY) - before)
            for nm in added:
                REGISTRY[nm].source = f"custom/{fname}"
            results[fname] = f"ok: {', '.join(added)}" if added else "ok: no strategies registered"
        except Exception:                          # noqa: BLE001
            results[fname] = "error: " + traceback.format_exc(limit=2).strip().splitlines()[-1]
    return results


def all_strategies(include_disabled: bool = False) -> List[StrategySpec]:
    return [s for s in REGISTRY.values() if include_disabled or s.enabled]


def evaluate(spec: StrategySpec, ctx: Ctx) -> Optional[Signal]:
    """Run one strategy, never letting it raise into the scan."""
    try:
        sig = spec.fn(ctx)
    except Exception:                              # noqa: BLE001
        return None
    if sig is None or not isinstance(sig, Signal):
        return None
    if sig.direction not in ("long", "flat"):
        return None
    sig.strength = max(0.0, min(1.0, float(sig.strength or 0.0)))
    return sig


# importing the built-ins registers them
from engine.strategies import builtin  # noqa: E402,F401
