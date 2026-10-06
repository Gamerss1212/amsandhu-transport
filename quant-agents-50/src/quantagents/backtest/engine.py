"""A43 Backtest Engineer: a daily backtester with next-open execution (spec section 56).

Timeline for each day t (decision after the close of t, trade at the open of t+1):
    equity[t+1] = equity[t]
                  x (1 + sum w_prev * (open[t+1] / close[t] - 1))      overnight, old weights
                  x (1 - turnover * cost_rate)                         trade at the open
                  x (1 + sum w_new * (close[t+1] / open[t+1] - 1))     intraday, new weights
The strategy only ever receives a MarketView ending at t, so it cannot see t+1.
This is a vectorized screening engine; re-test finalists event-driven (e.g. NautilusTrader).
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import date

import numpy as np

from quantagents.market import FloatArray, MarketData, MarketView

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
        w_prev = np.zeros(len(symbols))
        equity = [1.0]
        rets: list[float] = []
        turns: list[float] = []
        history: list[dict[str, float]] = []
        for t in range(warmup, n - 1):
            w_new = self._weights(strategy(market.view_at(t)), symbols)
            overnight_r = np.nan_to_num(opens[t + 1] / closes[t] - 1.0)
            intraday_r = np.nan_to_num(closes[t + 1] / opens[t + 1] - 1.0)
            turnover = float(np.sum(np.abs(w_new - w_prev)))
            growth = (
                (1.0 + float(w_prev @ overnight_r))
                * (1.0 - turnover * self.cost_rate)
                * (1.0 + float(w_new @ intraday_r))
            )
            equity.append(equity[-1] * growth)
            rets.append(growth - 1.0)
            turns.append(turnover)
            history.append({s: float(x) for s, x in zip(symbols, w_new, strict=True) if x != 0})
            w_prev = w_new
        returns = np.array(rets)
        turnover_arr = np.array(turns)
        metrics = performance_metrics(returns, turnover_arr)
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
