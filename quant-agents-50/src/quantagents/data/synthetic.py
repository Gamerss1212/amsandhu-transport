"""Synthetic market data for demos and tests.

These are NOT real prices, and the symbols (SYN_A ... SYN_F) are deliberately fake.
Each series is a random walk with its own drift, volatility and optional pull back to
trend, plus a small turn-of-month drift, so every starter agent has something to find.
Never present results on this data as evidence that a strategy works.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np

from quantagents.agents.a23_calendar import turn_of_month_position
from quantagents.market import Bars, MarketData

DEMO_AS_OF = date(2026, 9, 30)
DEMO_END = date(2026, 10, 2)
TURN_OF_MONTH_DRIFT = 0.0005  # +5 bps a day in the turn-of-month window


@dataclass(frozen=True)
class SyntheticSpec:
    symbol: str
    annual_drift: float
    annual_vol: float
    mean_reversion: float = 0.0  # daily pull of log price back to its trend line


DEFAULT_SPECS: tuple[SyntheticSpec, ...] = (
    SyntheticSpec("SYN_A", 0.35, 0.22),
    SyntheticSpec("SYN_B", 0.15, 0.25),
    SyntheticSpec("SYN_C", 0.05, 0.18, 0.02),
    SyntheticSpec("SYN_D", 0.00, 0.30, 0.05),
    SyntheticSpec("SYN_E", -0.10, 0.28),
    SyntheticSpec("SYN_F", -0.25, 0.35),
)


def business_days(end: date, count: int) -> list[date]:
    """The last ``count`` Monday-Friday dates up to and including ``end``."""
    days: list[date] = []
    d = end
    while len(days) < count:
        if d.weekday() < 5:
            days.append(d)
        d -= timedelta(days=1)
    return days[::-1]


def synthetic_market(
    *,
    end: date = DEMO_END,
    n_days: int = 780,
    seed: int = 7,
    specs: Sequence[SyntheticSpec] = DEFAULT_SPECS,
) -> MarketData:
    rng = np.random.default_rng(seed)
    days = business_days(end, n_days)
    turn = np.array([turn_of_month_position(d) is not None for d in days])
    bars: dict[str, Bars] = {}
    for spec in specs:
        mu = spec.annual_drift / 252.0
        sd = spec.annual_vol / math.sqrt(252.0)
        shocks = rng.standard_normal(n_days)
        log_close = np.empty(n_days)
        level = trend = math.log(100.0)
        for t in range(n_days):
            trend += mu
            step = mu - spec.mean_reversion * (level - trend) + sd * shocks[t]
            level += step + (TURN_OF_MONTH_DRIFT if turn[t] else 0.0)
            log_close[t] = level
        close = np.exp(log_close)
        gaps = rng.normal(0.0, 0.25 * sd, n_days)
        open_ = np.empty(n_days)
        open_[0] = 100.0 * math.exp(gaps[0])
        open_[1:] = close[:-1] * np.exp(gaps[1:])
        high = np.maximum(open_, close) * np.exp(np.abs(rng.normal(0.0, 0.35 * sd, n_days)))
        low = np.minimum(open_, close) * np.exp(-np.abs(rng.normal(0.0, 0.35 * sd, n_days)))
        volume = np.round(rng.lognormal(mean=13.0, sigma=0.3, size=n_days))
        bars[spec.symbol] = Bars.from_arrays(
            open=open_, high=high, low=low, close=close, volume=volume
        )
    return MarketData(days, bars)


def block_bootstrap_market(
    market: MarketData, *, seed: int, mean_block: float = 20.0
) -> MarketData:
    """A noise control: the real days, reshuffled in blocks of about a month (spec section 64).

    Each new day copies one real day's moves for every symbol at once (open, high, low and close
    relative to the previous close, and the volume), so daily volatility, cross-asset correlation
    and short-run behaviour are kept. Blocks of geometric length (mean ``mean_block`` days) are
    drawn at random, so anything slower than about a month (trends, 3-12 month momentum) is
    destroyed. A rule that still looks good here is finding luck, not a market effect.
    """
    from quantagents.validation.stats import stationary_bootstrap_indices  # avoids a cycle

    n = len(market)
    if n < 3:
        raise ValueError("need at least 3 days to bootstrap")
    rng = np.random.default_rng(seed)
    source = stationary_bootstrap_indices(n - 1, mean_block, rng) + 1  # real days 1..n-1
    bars: dict[str, Bars] = {}
    for symbol in market.symbols:
        b = market.bars(symbol)
        prev = b.close[:-1]
        with np.errstate(divide="ignore", invalid="ignore"):
            ratios = {
                f: np.nan_to_num(np.asarray(b.field(f))[1:] / prev, nan=1.0, posinf=1.0, neginf=1.0)
                for f in ("open", "high", "low", "close")
            }
        r = {f: x[source - 1] for f, x in ratios.items()}
        r["close"] = np.where(r["close"] > 0, r["close"], 1.0)
        start = float(b.close[0]) if math.isfinite(float(b.close[0])) else 100.0
        close = np.concatenate([[start], start * np.cumprod(r["close"])])
        prior = close[:-1]
        open_ = np.concatenate(
            [[b.open[0] if math.isfinite(b.open[0]) else start], prior * r["open"]]
        )
        high = np.concatenate(
            [[b.high[0] if math.isfinite(b.high[0]) else start], prior * r["high"]]
        )
        low = np.concatenate([[b.low[0] if math.isfinite(b.low[0]) else start], prior * r["low"]])
        hi = np.maximum(np.maximum(high, open_), close)
        lo = np.minimum(np.minimum(low, open_), close)
        volume = np.nan_to_num(np.asarray(b.volume), nan=0.0)
        bars[symbol] = Bars.from_arrays(
            open=open_,
            high=hi,
            low=lo,
            close=close,
            volume=np.concatenate([[volume[0]], volume[source]]),
        )
    return MarketData(market.dates, bars)
