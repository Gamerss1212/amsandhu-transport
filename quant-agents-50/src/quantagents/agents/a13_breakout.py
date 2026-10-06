"""A13 Structure & Breakout Agent (Team 3, Phase 4). Appendix A1 and A11, spec section 9.

Reads price structure the way a chart trader would, but as fixed rules:
- breakout: a close above the prior 20-bar high (or below the prior 20-bar low) within the
  last 3 bars that has not been given back
- confirmation: volume at least 1.5x its 20-bar median, and a close in the top (bottom) 30%
  of the bar's range
- structure: the last two confirmed swing highs and lows (3-bar fractals). Higher highs and
  higher lows = up structure; lower highs and lower lows = down structure
- false break: broke out in the last 5 bars but closed back inside the channel -> a small
  lean the other way (trapped breakout traders)
- track record: on THIS asset over the last year, how often did a breakout keep going for
  5 bars? Shrunk toward 50%. Breakouts that usually fail give no breakout signal at all.
p_up = 0.5 + 0.08 x score, so A13 alone never claims more than 58%. Horizon 10 bars.
Starts in shadow: sealed and scored by A35, no vote until the owner promotes it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

import numpy as np

from quantagents.agents.base import AgentContext, SignalAgent
from quantagents.features import prior_channel, swing_points
from quantagents.market import FloatArray, MarketView
from quantagents.schemas import AgentPrediction


@dataclass(frozen=True)
class Breakouts:
    """Historical breakout events on one asset (bar indices into the arrays given)."""

    up: tuple[int, ...]
    down: tuple[int, ...]


def breakout_events(close: FloatArray, upper: FloatArray, lower: FloatArray) -> Breakouts:
    """First closes beyond the prior channel (a run of closes above it counts once)."""
    with np.errstate(invalid="ignore"):
        above = np.nan_to_num(close > upper, nan=0.0).astype(bool)
        below = np.nan_to_num(close < lower, nan=0.0).astype(bool)
    up = tuple(int(i) for i in np.flatnonzero(above[1:] & ~above[:-1]) + 1)
    down = tuple(int(i) for i in np.flatnonzero(below[1:] & ~below[:-1]) + 1)
    return Breakouts(up, down)


def follow_through_rate(
    close: FloatArray, events: Breakouts, horizon: int, prior: float = 10.0
) -> tuple[float, int]:
    """Share of past breakouts that moved further in the breakout direction after ``horizon``
    bars, shrunk toward 50% with ``prior`` pseudo-events. Only events whose horizon has fully
    passed are used, so the rate never peeks past the last bar."""
    last = len(close) - 1
    hits = n = 0
    for i in events.up:
        if i + horizon <= last:
            n += 1
            hits += int(close[i + horizon] > close[i])
    for i in events.down:
        if i + horizon <= last:
            n += 1
            hits += int(close[i + horizon] < close[i])
    return (hits + 0.5 * prior) / (n + prior), n


def structure(high: FloatArray, low: FloatArray, k: int = 3) -> int:
    """+1 higher highs and higher lows, -1 lower highs and lower lows, 0 otherwise."""
    highs, lows = swing_points(high, low, k)
    if len(highs) < 2 or len(lows) < 2:
        return 0
    hh = high[highs[-1]] > high[highs[-2]]
    hl = low[lows[-1]] > low[lows[-2]]
    if hh and hl:
        return 1
    if not hh and not hl:
        return -1
    return 0


class BreakoutAgent(SignalAgent):
    agent_id = "A13"
    name = "Structure & Breakout Agent"
    kind = "mixed"
    info_subset = ("ohlcv", "volume_profile")
    horizon_bars = 10

    channel: ClassVar[int] = 20
    lookback: ClassVar[int] = 252
    follow_bars: ClassVar[int] = 5
    recent: ClassVar[int] = 3
    false_break_window: ClassVar[int] = 5
    volume_confirm: ClassVar[float] = 1.5
    max_tilt: ClassVar[float] = 0.08
    min_score: ClassVar[float] = 0.15

    def score(self, view: MarketView, symbol: str) -> tuple[float, str] | None:
        """Score in [-1, 1] and a reason, or None when there is not enough clean data."""
        tail = self.lookback + self.channel + 1
        h = np.ascontiguousarray(view.high(symbol)[-tail:])
        lo = np.ascontiguousarray(view.low(symbol)[-tail:])
        c = np.ascontiguousarray(view.close(symbol)[-tail:])
        v = np.ascontiguousarray(view.volume(symbol)[-tail:])
        if len(c) < self.channel + 60 or not np.all(np.isfinite(np.stack([h, lo, c, v]))):
            return None
        upper, lower = prior_channel(h, lo, self.channel)
        events = breakout_events(c, upper, lower)
        rate, n_events = follow_through_rate(c, events, self.follow_bars)
        trust = min(1.0, max(0.0, (rate - 0.4) / 0.2))  # 40% -> 0, 50% -> 0.5, 60% -> 1
        shape = structure(h[-120:], lo[-120:])
        last = len(c) - 1
        record = f"{rate:.0%} follow-through on {n_events} past breakouts"

        live = [(i, 1) for i in events.up if last - i < self.recent and c[last] > upper[i]]
        live += [(i, -1) for i in events.down if last - i < self.recent and c[last] < lower[i]]
        if live:
            i, side = max(live)
            base = float(np.median(v[max(0, i - 20) : i])) if i > 0 else 0.0
            confirmed = base > 0 and v[i] >= self.volume_confirm * base
            width = h[i] - lo[i]
            where = (c[i] - lo[i]) / width if width > 0 else 0.5
            strong_close = where >= 0.7 if side > 0 else where <= 0.3
            agree = 1.0 if shape == side else 0.8 if shape == 0 else 0.5
            value = side * (1.0 if confirmed else 0.6) * (1.0 if strong_close else 0.7)
            value *= agree * trust
            word = "breakout" if side > 0 else "breakdown"
            return value, (
                f"20-bar {word} {last - i} bar(s) ago, volume "
                f"{'confirmed' if confirmed else 'not confirmed'}, "
                f"{'strong' if strong_close else 'weak'} close, structure {shape:+d}; {record}"
            )

        window = self.false_break_window
        failed = [(i, 1) for i in events.up if 0 < last - i <= window and c[last] < upper[i]]
        failed += [(i, -1) for i in events.down if 0 < last - i <= window and c[last] > lower[i]]
        if failed:
            i, side = max(failed)
            return (
                -0.4 * side,
                f"false {'breakout' if side > 0 else 'breakdown'} {last - i} bars ago",
            )
        if shape:
            return 0.3 * shape, f"swing structure {'up' if shape > 0 else 'down'}, no breakout"
        return 0.0, "no breakout and no clear structure"

    def predict(self, ctx: AgentContext) -> list[AgentPrediction]:
        out: list[AgentPrediction] = []
        for symbol in ctx.tradable:
            result = self.score(ctx.view, symbol)
            if result is None:
                out.append(self.abstain(ctx, symbol, "insufficient clean history"))
                continue
            value, reason = result
            if abs(value) < self.min_score:
                out.append(self.abstain(ctx, symbol, reason))
                continue
            out.append(self.forecast(ctx, symbol, 0.5 + self.max_tilt * value, reason))
        return out
