"""Backtest and replay: the live trade manager driven over historical bars.

Rules are evaluated once over the whole frame (every rule is causal, so values at bar i use
bars <= i only), then the TradeManager walks the bars in order exactly as the live runtime
does. A backtest over [start, end) still evaluates rules on earlier bars, so indicators arrive
warm, but only trades ENTERED inside the window count, and any position still open at the end
is closed at the last bar's close.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from mab.clock import is_equity
from mab import metrics as M
from mab.costs import filler_for
from mab.frame import Frame
from mab.strategy import Compiled, RuleSeries, TradeManager, evaluate


@dataclass
class Result:
    strategy_id: str
    instrument: str
    tf: str
    period: str
    start: Optional[int]
    end: Optional[int]
    trades: list
    metrics: dict
    params: dict
    cost: dict
    bars: int
    runtime_s: float
    skipped: Dict[str, int] = field(default_factory=dict)

    def summary(self) -> dict:
        m = self.metrics
        return {"strategy": self.strategy_id, "instrument": self.instrument, "period": self.period,
                "trades": m.get("trades"), "win_rate": m.get("win_rate"), "expectancy_r": m.get("expectancy_r"),
                "net_return": m.get("net_return"), "sharpe": m.get("sharpe"), "max_drawdown": m.get("max_drawdown")}


def session_days(frame: Frame, i0: int, i1: int) -> List[str]:
    seen, out = set(), []
    for i in range(i0, i1):
        if frame.sess[i] < 0:
            continue
        d = M.utc_day(frame.t[i] + frame.step)
        if d not in seen:
            seen.add(d)
            out.append(d)
    return out


def run(c: Compiled, frame: Frame, venue: str = None, capital: float = 10_000.0, cost_mult: float = 1.0,
        start: Optional[int] = None, end: Optional[int] = None, period: str = "full", resolver=None, events=None,
        rs: Optional[RuleSeries] = None, lot_size: float = 0.0, min_notional: float = 0.0,
        can_short: bool = True, tick: float = 0.0, fees: Optional[dict] = None,
        max_participation: Optional[float] = None) -> Result:
    """fees: a mab.costs.FEE_PROFILES entry overriding the venue's crypto fees.
    max_participation: liquidity limit - an entry may take at most this fraction of its fill bar's volume; a
    larger order is filled partially (the rest is treated as not filled, as an immediate-or-cancel order)."""
    t0 = time.time()
    venue = venue or frame.venue
    filler = filler_for(venue, frame.instrument, frame.asset_type, cost_mult, tick)
    filler.cm.fees = fees
    rs = rs or evaluate(c, frame, resolver, events)
    tm = TradeManager(c, filler, lambda: capital, lot_size, min_notional, can_short, frame.instrument)
    i0 = 0 if start is None else next((i for i, t in enumerate(frame.t) if t >= start), frame.n)
    i1 = frame.n if end is None else next((i for i, t in enumerate(frame.t) if t >= end), frame.n)
    skipped: Dict[str, int] = {}
    in_mkt = 0
    for i in range(i0, i1):
        acts = tm.on_bar(rs, i)
        if tm.pos is not None:
            in_mkt += 1
        for a in acts:
            if a["action"] in ("skip", "rejected"):
                skipped[a["reason"]] = skipped.get(a["reason"], 0) + 1
            elif a["action"] == "entry" and max_participation and tm.pos is not None:
                cap = max_participation * (frame.v[i] or 0.0)
                if cap <= 0:
                    tm.pos = None
                    tm.trades_today = max(0, tm.trades_today - 1)
                    skipped["no volume to fill against (liquidity limit)"] = skipped.get("no volume to fill against (liquidity limit)", 0) + 1
                elif tm.pos.qty > cap:
                    tm.pos.fees *= cap / tm.pos.qty
                    tm.pos.qty = cap
                    skipped["partial fill: liquidity limit"] = skipped.get("partial fill: liquidity limit", 0) + 1
    if tm.pos is not None and i1 > i0:
        tm.force_exit(frame, i1 - 1, frame.c[i1 - 1], "end of test period")
    days = session_days(frame, i0, i1)
    ppy = 252 if is_equity(frame.asset_type) else 365
    m = M.compute(tm.trades, capital, days, ppy, i1 - i0, in_mkt)
    return Result(c.id, frame.instrument, frame.tf, period, frame.t[i0] if i0 < frame.n else None,
                  frame.t[i1 - 1] if i1 > i0 else None, tm.trades, m, c.params, filler.cm.describe(), i1 - i0,
                  round(time.time() - t0, 3), skipped)
