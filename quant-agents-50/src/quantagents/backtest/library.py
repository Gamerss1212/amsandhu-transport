"""Phase 2 strategy library: published Grade A/B rules (spec Appendix A), long-only, no leverage.

Every family has a small grid fixed **before** any real-data run (pre-registered): the first
variant is the primary one that gets reported, the others are neighbours that show whether the
result depends on one lucky parameter. All of them count as trials (spec section 63).

- ``tsmom_blend``: Hurst-Ooi-Pedersen multi-horizon trend (A1). Per symbol, the share of its
  1-, 3- and 12-month returns that are positive (0, 1/3, 2/3 or 1; the long-only form of
  "average the signs"), times 1/n, optionally scaled down to a 10% volatility target.
- ``xs_momentum``: Jegadeesh-Titman 12-1 momentum (A2). Hold the top third of the universe by
  the return from 12 months ago to 1 month ago; optionally only while the market trends up
  (Daniel-Moskowitz style crash filter).
- ``faber``: Faber's moving-average timing (A1). Hold a symbol while its month-end close is
  above the average of its last 10 month-end closes.
- ``rsi2``: Connors RSI(2) reversion (A3). Buy when RSI(2) is below 10 (or 5) and the close is
  above its 200-day average; sell on a close above the 5-day average.
- ``vol_target``: volatility-targeting overlay (A16) on any base strategy: scale the book so its
  estimated volatility is 10% (or 15%) a year, never above 100% invested.

Added for the research grid (2026-10-06):
- ``sma_cross``: the golden-cross trend filter (A1). Hold a symbol while its fast moving average
  (e.g. 50 days) is above its slow one (e.g. 200 days).
- ``dual_momentum``: Antonacci dual momentum (A2). Rank by the lookback return, keep the top k,
  and hold each only while its own return is positive (absolute momentum); otherwise cash.
- ``donchian``: Turtle-style channel breakout (A1). Buy on a close above the highest high of
  the previous N days; sell on a close below the lowest low of the previous M days.

Volatility is annualized with 365 days for markets that trade every day (crypto), else 252.

Monthly strategies decide on the first trading day of each month using data up to that day,
then trade at the next open (one day later than the papers' month-end rule; never earlier).
"""

from __future__ import annotations

import math
from collections.abc import Callable

import numpy as np

from quantagents.backtest.engine import Strategy, StrategyFactory
from quantagents.features import rsi
from quantagents.market import FloatArray, MarketData, MarketView, periods_per_year

Weights = dict[str, float]
TRADING_DAYS = 252


def _closes(view: MarketView, symbol: str, n: int) -> FloatArray:
    return np.ascontiguousarray(view.close(symbol)[-n:])


def _ann_vol(close: FloatArray, window: int, periods: int = TRADING_DAYS) -> float:
    c = close[-(window + 1) :]
    if len(c) < window + 1 or not np.all(np.isfinite(c)) or np.any(c <= 0):
        return math.nan
    return float(np.std(np.diff(np.log(c)), ddof=1)) * math.sqrt(periods)


def _periods(view: MarketView, window: int) -> int:
    return periods_per_year(view.dates[-(window + 1) :])


def new_month(view: MarketView) -> bool:
    d = view.dates
    return len(d) < 2 or d[-1].month != d[-2].month


class Monthly:
    """Recompute weights on the first trading day of each month (and on the first call)."""

    def __init__(self, compute: Callable[[MarketView], Weights]) -> None:
        self.compute = compute
        self.weights: Weights | None = None

    def __call__(self, view: MarketView) -> Weights:
        if self.weights is None or new_month(view):
            self.weights = self.compute(view)
        return dict(self.weights)


def tsmom_blend(
    lookbacks: tuple[int, ...] = (21, 63, 252), target_vol: float | None = 0.10, window: int = 63
) -> StrategyFactory:
    need = max(*lookbacks, window) + 1

    def compute(view: MarketView) -> Weights:
        n = len(view.symbols)
        out: Weights = {}
        for s in view.symbols:
            c = _closes(view, s, need)
            if len(c) < need or not math.isfinite(c[-1]):
                continue
            share = float(np.mean([c[-1] / c[-1 - k] - 1.0 > 0 for k in lookbacks]))
            if share <= 0:
                continue
            weight = share / n
            if target_vol is not None:
                vol = _ann_vol(c, window, _periods(view, window))
                if not (math.isfinite(vol) and vol > 0):
                    continue
                weight *= min(1.0, target_vol / vol)
            out[s] = weight
        return out

    def factory(market: MarketData) -> Strategy:
        return Monthly(compute)

    return factory


def xs_momentum(
    lookback: int = 252, skip: int = 21, top_frac: float = 1 / 3, trend_filter: bool = False
) -> StrategyFactory:
    def market_up(view: MarketView) -> bool:
        rets = []
        for s in view.symbols:
            c = _closes(view, s, 202)
            if len(c) == 202 and np.all(np.isfinite(c)) and np.all(c > 0):
                rets.append(np.diff(np.log(c)))
        if not rets:
            return False
        index = np.exp(np.cumsum(np.mean(rets, axis=0)))
        return bool(index[-1] > np.mean(index[-200:]))

    def compute(view: MarketView) -> Weights:
        scores: dict[str, float] = {}
        for s in view.symbols:
            c = _closes(view, s, lookback + 1)
            if len(c) == lookback + 1 and math.isfinite(c[0]) and math.isfinite(c[-1 - skip]):
                scores[s] = float(c[-1 - skip] / c[0] - 1.0)
        if not scores or (trend_filter and not market_up(view)):
            return {}
        k = max(1, round(top_frac * len(view.symbols)))
        top = sorted(scores, key=lambda s: (-scores[s], s))[:k]
        return dict.fromkeys(top, 1.0 / k)

    def factory(market: MarketData) -> Strategy:
        return Monthly(compute)

    return factory


def month_end_closes(view: MarketView, symbol: str, months: int) -> FloatArray:
    """Closes on the last trading day of each of the last ``months`` completed months."""
    dates = view.dates
    close = view.close(symbol)
    out: list[float] = []
    i = len(dates) - 2
    while i >= 0 and len(out) < months:
        if dates[i].month != dates[i + 1].month:
            out.append(float(close[i]))
        i -= 1
    return np.array(out[::-1])


def faber(months: int = 10) -> StrategyFactory:
    def compute(view: MarketView) -> Weights:
        n = len(view.symbols)
        out: Weights = {}
        for s in view.symbols:
            ends = month_end_closes(view, s, months)
            if len(ends) == months and np.all(np.isfinite(ends)) and ends[-1] > np.mean(ends):
                out[s] = 1.0 / n
        return out

    def factory(market: MarketData) -> Strategy:
        return Monthly(compute)

    return factory


class _Rsi2:
    def __init__(self, entry: float, exit_sma: int, trend_sma: int) -> None:
        self.entry, self.exit_sma, self.trend_sma = entry, exit_sma, trend_sma
        self.held: set[str] = set()

    def __call__(self, view: MarketView) -> Weights:
        n = len(view.symbols)
        for s in view.symbols:
            c = _closes(view, s, self.trend_sma)
            if len(c) < self.trend_sma or not np.all(np.isfinite(c)):
                self.held.discard(s)
                continue
            if s in self.held:
                if c[-1] > float(np.mean(c[-self.exit_sma :])):
                    self.held.discard(s)
            elif c[-1] > float(np.mean(c)) and float(rsi(c[-40:], 2)[-1]) < self.entry:
                self.held.add(s)
        return dict.fromkeys(sorted(self.held), 1.0 / n)


def rsi2(entry: float = 10.0, exit_sma: int = 5, trend_sma: int = 200) -> StrategyFactory:
    def factory(market: MarketData) -> Strategy:
        return _Rsi2(entry, exit_sma, trend_sma)

    return factory


def vol_target(base: StrategyFactory, target: float = 0.10, window: int = 63) -> StrategyFactory:
    """Scale ``base`` so the book's estimated volatility is ``target`` a year (never above 1x)."""

    def factory(market: MarketData) -> Strategy:
        inner = base(market)

        def compute(view: MarketView) -> Weights:
            w = {s: x for s, x in inner(view).items() if x > 0}
            if not w:
                return {}
            rets = []
            for s in w:
                c = _closes(view, s, window + 1)
                if len(c) < window + 1 or not np.all(np.isfinite(c)) or np.any(c <= 0):
                    return {}
                rets.append(np.diff(np.log(c)))
            weights = np.array(list(w.values()))
            cov = np.atleast_2d(np.cov(np.array(rets)))
            vol = math.sqrt(max(float(weights @ cov @ weights), 0.0) * _periods(view, window))
            if vol <= 0:
                return {}
            scale = min(target / vol, 1.0 / float(np.sum(weights)))
            return {s: x * scale for s, x in w.items()}

        return Monthly(compute)

    return factory


def sma_cross(fast: int = 50, slow: int = 200) -> StrategyFactory:
    if not 0 < fast < slow:
        raise ValueError("need 0 < fast < slow")

    def factory(market: MarketData) -> Strategy:
        def strategy(view: MarketView) -> Weights:
            n = len(view.symbols)
            out: Weights = {}
            for s in view.symbols:
                c = _closes(view, s, slow)
                if len(c) == slow and np.all(np.isfinite(c)) and np.mean(c[-fast:]) > np.mean(c):
                    out[s] = 1.0 / n
            return out

        return strategy

    return factory


def dual_momentum(lookback: int = 252, top_k: int = 1) -> StrategyFactory:
    def compute(view: MarketView) -> Weights:
        scores: dict[str, float] = {}
        for s in view.symbols:
            c = _closes(view, s, lookback + 1)
            if len(c) == lookback + 1 and math.isfinite(c[0]) and math.isfinite(c[-1]):
                scores[s] = float(c[-1] / c[0] - 1.0)
        top = sorted(scores, key=lambda s: (-scores[s], s))[:top_k]
        return {s: 1.0 / top_k for s in top if scores[s] > 0}

    def factory(market: MarketData) -> Strategy:
        return Monthly(compute)

    return factory


class _Donchian:
    def __init__(self, entry: int, exit_: int) -> None:
        self.entry, self.exit = entry, exit_
        self.held: set[str] = set()

    def __call__(self, view: MarketView) -> Weights:
        n = len(view.symbols)
        span = max(self.entry, self.exit) + 1
        for s in view.symbols:
            h = np.ascontiguousarray(view.high(s)[-span:])
            lo = np.ascontiguousarray(view.low(s)[-span:])
            c = float(view.close(s)[-1])
            ok = len(h) == span and np.all(np.isfinite(h)) and np.all(np.isfinite(lo))
            if not ok or not math.isfinite(c):
                self.held.discard(s)
                continue
            if s in self.held:
                if c < float(np.min(lo[-self.exit - 1 : -1])):
                    self.held.discard(s)
            elif c > float(np.max(h[-self.entry - 1 : -1])):
                self.held.add(s)
        return dict.fromkeys(sorted(self.held), 1.0 / n)


def donchian(entry: int = 55, exit_: int = 20) -> StrategyFactory:
    if entry < 2 or exit_ < 2:
        raise ValueError("channels need at least 2 days")

    def factory(market: MarketData) -> Strategy:
        return _Donchian(entry, exit_)

    return factory
