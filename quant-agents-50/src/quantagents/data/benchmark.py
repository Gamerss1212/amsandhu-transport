"""Phase 1 benchmark: can we reproduce buy-and-hold total return within 0.1% a year? (spec section 56)

Three independent routes to the same number, from the same stored snapshot:
- ``adjusted``: the source's dividend- and split-adjusted closes (adj_close[end] / adj_close[start]).
- ``rebuilt``: raw closes plus every dividend reinvested at the close, computed here
  (total return each day = (close_t + dividend_t) / close_t-1). It does not use the source's
  adjustment at all, so it checks it.
- ``backtester``: A43 holding 100% from the first trading day at zero cost on the adjusted
  panel. It enters at the next open (the backtester never fills at the signal's own close), so
  its comparison number is the adjusted return from that same open.
Each pair is compared as an annual (CAGR) difference; the benchmark passes when every
difference is within ``tolerance`` (0.1% a year).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from quantagents.backtest.engine import Backtester
from quantagents.data.sources import RawDaily
from quantagents.data.store import adjusted_market
from quantagents.market import MarketView

TRADING_DAYS = 252
TOLERANCE_PER_YEAR = 0.001


def cagr(total_return: float, n_days: int) -> float:
    years = n_days / TRADING_DAYS
    return (1.0 + total_return) ** (1.0 / years) - 1.0 if years > 0 and total_return > -1 else -1.0


def rebuilt_total_return(raw: RawDaily, first: int, last: int) -> float:
    """Raw closes plus dividends reinvested at the close, from index ``first`` to ``last``."""
    growth = 1.0
    for k in range(first + 1, last + 1):
        prev = float(raw.close[k - 1])
        growth *= (float(raw.close[k]) + float(raw.dividends.get(raw.dates[k], 0.0))) / prev
    return growth - 1.0


@dataclass(frozen=True)
class BenchmarkReport:
    symbol: str
    start: str
    end: str
    n_days: int
    dividends: int
    adjusted_total: float
    rebuilt_total: float
    backtester_total: float
    adjusted_from_open_total: float
    cagr_gap_rebuilt: float
    cagr_gap_backtester: float
    tolerance: float

    @property
    def passed(self) -> bool:
        return (
            abs(self.cagr_gap_rebuilt) <= self.tolerance
            and abs(self.cagr_gap_backtester) <= self.tolerance
        )


def buy_and_hold_benchmark(
    raw: RawDaily, *, tolerance: float = TOLERANCE_PER_YEAR
) -> BenchmarkReport:
    if len(raw) < 3:
        raise ValueError(f"{raw.symbol}: need at least 3 bars")
    prices = np.concatenate([raw.open, raw.high, raw.low, raw.close, raw.adj_close])
    if not np.all(np.isfinite(prices)) or np.any(prices <= 0):
        raise ValueError(f"{raw.symbol}: non-finite or non-positive prices in the snapshot")
    first, last = 0, len(raw) - 1
    adjusted = float(raw.adj_close[last] / raw.adj_close[first] - 1.0)
    rebuilt = rebuilt_total_return(raw, first, last)
    n = last - first
    gap_rebuilt = cagr(rebuilt, n) - cagr(adjusted, n)

    market = adjusted_market({raw.symbol: raw})
    symbol = raw.symbol

    def hold(_: MarketView) -> dict[str, float]:
        return {symbol: 1.0}

    result = Backtester(0.0).run(market, hold, warmup=0, name="buy and hold")
    bt_total = float(result.equity[-1] - 1.0)
    adj = market.bars(symbol)
    from_open = float(adj.close[-1] / adj.open[1] - 1.0)  # A43 buys at the open after day 0
    gap_bt = cagr(bt_total, n - 1) - cagr(from_open, n - 1)
    return BenchmarkReport(
        symbol=raw.symbol,
        start=raw.dates[first].isoformat(),
        end=raw.dates[last].isoformat(),
        n_days=n,
        dividends=sum(1 for d in raw.dividends if raw.dates[first] < d <= raw.dates[last]),
        adjusted_total=adjusted,
        rebuilt_total=rebuilt,
        backtester_total=bt_total,
        adjusted_from_open_total=from_open,
        cagr_gap_rebuilt=gap_rebuilt,
        cagr_gap_backtester=gap_bt,
        tolerance=tolerance,
    )


def annual_gaps(raw: RawDaily) -> list[tuple[int, float]]:
    """Per calendar year: rebuilt minus adjusted return (a year-by-year view of the same check)."""
    years = sorted({d.year for d in raw.dates})
    out: list[tuple[int, float]] = []
    idx = np.arange(len(raw))
    for y in years:
        ks = idx[[d.year == y for d in raw.dates]]
        if len(ks) < 2:
            continue
        a, b = int(ks[0]) - (1 if ks[0] > 0 else 0), int(ks[-1])
        adj = float(raw.adj_close[b] / raw.adj_close[a] - 1.0)
        out.append((y, rebuilt_total_return(raw, a, b) - adj))
    return out
