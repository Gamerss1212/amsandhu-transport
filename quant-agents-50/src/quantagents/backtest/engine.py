"""A43 Backtest Engineer: a daily backtester with next-open execution (spec section 56).

Timeline for each day t (decision after the close of t, trade at the open of t+1):
    equity[t+1] = equity[t]
                  x (1 + sum w_held * (open[t+1] / close[t] - 1))      overnight, what is held
                  x (1 - turnover * cost_rate)                         trade at the open
                  x (1 + sum w_after * (close[t+1] / open[t+1] - 1))   intraday, after the trade
The strategy only ever receives a MarketView ending at t, so it cannot see t+1.

Holdings drift with prices (fix, 2026-10-06). ``w_held`` is what the book really holds after
prices moved, not yesterday's target:
- a target **identical** to the previous one means "no new decision": nothing is traded and the
  book keeps drifting (a monthly strategy holds between rebalances, and buy-and-hold really is
  buy-and-hold);
- any **change** in the target trades the whole book back to it, and turnover is measured from
  the drifted holdings, so the cost of undoing drift is paid.
Before this fix the engine assumed the book was reset to its targets every day for free.
This is a screening engine; re-test finalists in the event-driven engine (``event.py``).
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import date

import numpy as np

from quantagents.market import FloatArray, MarketData, MarketView, periods_per_year

Strategy = Callable[[MarketView], Mapping[str, float]]
StrategyFactory = Callable[[MarketData], Strategy]


def performance_metrics(
    returns: FloatArray, turnover: FloatArray, periods: int = 252
) -> dict[str, float]:
    if len(returns) == 0:
        return {"n_days": 0.0}
    growth = np.cumprod(1.0 + returns)
    total = float(growth[-1] - 1.0)
    years = len(returns) / periods
    sd = float(np.std(returns, ddof=1)) if len(returns) > 1 else 0.0
    peak = np.maximum.accumulate(np.concatenate([[1.0], growth]))
    drawdown = 1.0 - np.concatenate([[1.0], growth]) / peak
    return {
        "n_days": float(len(returns)),
        "total_return": total,
        "cagr": float((1.0 + total) ** (1.0 / years) - 1.0) if total > -1.0 else -1.0,
        "ann_vol": sd * math.sqrt(periods),
        "sharpe": float(np.mean(returns)) / sd * math.sqrt(periods) if sd > 0 else 0.0,
        "max_drawdown": float(np.max(drawdown)),
        "avg_daily_turnover": float(np.mean(turnover)) if len(turnover) else 0.0,
        "exposure_days_pct": 0.0,
    }


def _drift(weights: FloatArray, returns: FloatArray, growth: float) -> FloatArray:
    """Weights after prices move by ``returns`` (cash, the rest, earns nothing)."""
    if growth <= 0:
        return np.zeros_like(weights)
    drifted: FloatArray = weights * (1.0 + returns) / growth
    return drifted


@dataclass(frozen=True)
class BacktestResult:
    name: str
    dates: tuple[date, ...]
    equity: FloatArray
    returns: FloatArray
    turnover: FloatArray
    weights: tuple[dict[str, float], ...]
    cost_rate: float
    metrics: dict[str, float] = field(default_factory=dict)


class Backtester:
    agent_id = "A43"
    name = "Backtest Engineer"
    kind = "code"

    def __init__(
        self, cost_rate: float, *, max_gross: float = 1.0, allow_short: bool = False
    ) -> None:
        if cost_rate < 0:
            raise ValueError("cost_rate must be >= 0")
        self.cost_rate = cost_rate
        self.max_gross = max_gross
        self.allow_short = allow_short

    def _weights(self, target: Mapping[str, float], symbols: tuple[str, ...]) -> FloatArray:
        unknown = set(target) - set(symbols)
        if unknown:
            raise ValueError(f"strategy returned unknown symbols {sorted(unknown)}")
        w = np.array([float(target.get(s, 0.0)) for s in symbols], dtype=np.float64)
        if not np.all(np.isfinite(w)):
            raise ValueError("strategy returned a non-finite weight")
        if not self.allow_short and np.any(w < 0):
            raise ValueError("strategy returned a short weight but shorting is off")
        if float(np.sum(np.abs(w))) > self.max_gross + 1e-9:
            raise ValueError(f"gross exposure {np.sum(np.abs(w)):.3f} above {self.max_gross}")
        return w

    def run(
        self, market: MarketData, strategy: Strategy, *, warmup: int = 260, name: str = "strategy"
    ) -> BacktestResult:
        n = len(market)
        if not 0 <= warmup < n - 1:
            raise ValueError(f"warmup {warmup} leaves no days to trade in {n} bars")
        symbols = market.symbols
        opens = np.column_stack([market.bars(s).open for s in symbols])
        closes = np.column_stack([market.bars(s).close for s in symbols])
        target_prev: FloatArray | None = None
        held = np.zeros(len(symbols))  # weights actually held, drifting with prices
        equity = [1.0]
        rets: list[float] = []
        turns: list[float] = []
        history: list[dict[str, float]] = []
        for t in range(warmup, n - 1):
            w_new = self._weights(strategy(market.view_at(t)), symbols)
            overnight_r = np.nan_to_num(opens[t + 1] / closes[t] - 1.0)
            intraday_r = np.nan_to_num(closes[t + 1] / opens[t + 1] - 1.0)
            g_overnight = 1.0 + float(held @ overnight_r)
            held = _drift(held, overnight_r, g_overnight)
            if target_prev is not None and np.array_equal(w_new, target_prev):
                turnover = 0.0  # no new decision: keep what is held
            else:
                turnover = float(np.sum(np.abs(w_new - held)))
                held = w_new.copy()
            g_intraday = 1.0 + float(held @ intraday_r)
            growth = g_overnight * (1.0 - turnover * self.cost_rate) * g_intraday
            held = _drift(held, intraday_r, g_intraday)
            equity.append(equity[-1] * growth)
            rets.append(growth - 1.0)
            turns.append(turnover)
            history.append({s: float(x) for s, x in zip(symbols, w_new, strict=True) if x != 0})
            target_prev = w_new
        returns = np.array(rets)
        turnover_arr = np.array(turns)
        metrics = performance_metrics(
            returns, turnover_arr, periods_per_year(market.dates[warmup:])
        )
        metrics["exposure_days_pct"] = 100.0 * sum(1 for h in history if h) / len(history)
        return BacktestResult(
            name=name,
            dates=market.dates[warmup:],
            equity=np.array(equity),
            returns=returns,
            turnover=turnover_arr,
            weights=tuple(history),
            cost_rate=self.cost_rate,
            metrics=metrics,
        )
