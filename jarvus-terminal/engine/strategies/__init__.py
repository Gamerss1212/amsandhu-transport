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
        self._session: Optional[Dict[str, list]] = None

    def session(self) -> Dict[str, list]:
        """Per-bar facts about the trading session each bar belongs to, computed once.

        Stocks trade in sessions separated by overnight gaps; crypto trades around the
        clock. Which one a market is gets decided from the data itself (regular gaps of
        three hours or more mean sessions), so the same strategy works on both and in
        a backtest, where no metadata is available.

        Everything here is known at the bar it is stored on: running highs, lows and
        VWAP include only bars up to and including that bar; previous-session values
        come from sessions that had already finished. The opening range only counts
        once its window has closed. Nothing looks ahead.

          gapped      True for session markets (stocks), judged from the previous 200 bars
          start       True on the first bar of a session
          idx         bar number within its session, 0 for the first
          s_open      the session's opening price
          s_high/low  session high / low so far, including this bar
          vwap        session VWAP so far
          prev_*      high, low, close, open of the previous full session
          gap_pct     session open vs previous session close, in percent
          or_high/low opening range: the first bar of a stock session, or the
                      00:00-08:00 UTC (Asia) range of a crypto day
          or_done     True once the opening-range window has finished
        """
        if self._session is not None:
            return self._session
        from collections import deque
        n = self.n
        ts = [c["ts"] for c in self.candles]
        cols = ("start", "idx", "s_open", "s_high", "s_low", "vwap", "prev_high", "prev_low",
                "prev_close", "prev_open", "gap_pct", "or_high", "or_low", "or_done", "gapped")
        out: Dict[str, list] = {k: [None] * n for k in cols}
        prev = None                                   # (high, low, close, open) of the last finished session
        cur = None
        pv = vv = 0.0
        orh = orl = None
        recent_gaps: "deque[int]" = deque()
        for i in range(n):
            gap = i > 0 and (ts[i] - ts[i - 1]).total_seconds() >= 3 * 3600
            if gap:
                recent_gaps.append(i)
            while recent_gaps and recent_gaps[0] <= i - 200:
                recent_gaps.popleft()
            # A session market (stocks) shows overnight gaps; decided from the past 200 bars
            # only, so the answer at any bar never depends on bars after it.
            gapped = len(recent_gaps) >= 2
            new = i == 0 or gap or ts[i].date() != ts[i - 1].date()
            if new:
                if cur is not None:
                    prev = (cur["high"], cur["low"], self.close[i - 1], cur["open"])
                cur = {"open": self.open[i], "high": self.high[i], "low": self.low[i], "idx": 0}
                pv = vv = 0.0
                orh = orl = None
            else:
                cur["idx"] += 1
                cur["high"] = max(cur["high"], self.high[i])
                cur["low"] = min(cur["low"], self.low[i])
            typical = (self.high[i] + self.low[i] + self.close[i]) / 3
            pv += typical * self.volume[i]
            vv += self.volume[i]
            in_or = (cur["idx"] == 0) if gapped else (ts[i].hour < 8)
            if in_or:
                orh = self.high[i] if orh is None else max(orh, self.high[i])
                orl = self.low[i] if orl is None else min(orl, self.low[i])
            out["start"][i] = new
            out["idx"][i] = cur["idx"]
            out["s_open"][i] = cur["open"]
            out["s_high"][i] = cur["high"]
            out["s_low"][i] = cur["low"]
            out["vwap"][i] = pv / vv if vv else typical
            if prev:
                out["prev_high"][i], out["prev_low"][i], out["prev_close"][i], out["prev_open"][i] = prev
                out["gap_pct"][i] = (cur["open"] / prev[2] - 1) * 100 if prev[2] else None
            out["or_high"][i], out["or_low"][i] = orh, orl
            out["or_done"][i] = (orh is not None) and not in_or
            out["gapped"][i] = gapped
        self._session = out
        return out

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

    def sess(self, back: int = 0) -> Optional[Dict]:
        """Session facts at this bar (or `back` bars earlier). See SeriesCache.session."""
        i = self.n - 1 - back
        if i < 0:
            return None
        s = self.cache.session()
        return {k: s[k][i] for k in s}

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
    folders = []
    if folder:
        folders = [folder]
    else:
        folders = [os.path.join(os.path.dirname(os.path.abspath(__file__)), "custom")]
        # A packaged build keeps its code in a temporary folder, so also look for a
        # "strategies" folder beside the executable. That is where someone who
        # downloaded the .exe can actually drop a file.
        try:
            import config as _cfg
            beside = os.path.join(_cfg.BASE_DIR, "strategies")
            if beside not in folders:
                folders.append(beside)
        except Exception:                          # noqa: BLE001
            pass
    results: Dict[str, str] = {}
    for folder in folders:
        if not os.path.isdir(folder):
            continue
        results.update(_load_folder(folder))
    return results


def _load_folder(folder: str) -> Dict[str, str]:
    results: Dict[str, str] = {}
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
from engine.strategies import builtin, pro  # noqa: E402,F401
