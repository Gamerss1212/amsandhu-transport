"""A01 Market Data & PIT Librarian (Team 1, Phase 1).

Builds the cycle's MarketSnapshot. The snapshot id is a hash of every value the cycle may
see, so any decision can be traced back to the exact data behind it.
Real data adapters (CCXT, IBKR via ib_async, vendor files) plug in here in later phases.
"""

from __future__ import annotations

import hashlib
import math

import numpy as np

from quantagents.agents.base import Agent
from quantagents.market import FIELDS, MarketView
from quantagents.schemas import MarketSnapshot


class MarketDataAgent(Agent):
    agent_id = "A01"
    name = "Market Data & PIT Librarian"
    kind = "code"
    info_subset = ("ohlcv",)

    def snapshot(self, view: MarketView) -> MarketSnapshot:
        digest = hashlib.sha256(view.as_of.isoformat().encode())
        last_close: dict[str, float] = {}
        for symbol in view.symbols:
            digest.update(symbol.encode())
            for field in FIELDS:
                digest.update(np.ascontiguousarray(view.series(symbol, field)).tobytes())
            close = float(view.close(symbol)[-1])
            if math.isfinite(close) and close > 0:
                last_close[symbol] = close
        return MarketSnapshot(
            snapshot_id=digest.hexdigest()[:16],
            as_of=view.as_of,
            symbols=view.symbols,
            n_bars=len(view),
            last_close=last_close,
        )
