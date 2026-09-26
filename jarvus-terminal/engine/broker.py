#!/usr/bin/env python3
"""The practice-money broker the bots trade through, and the live price feed.

Every fill uses the live market price, the real fee for the chosen fee tier, and
slippage. Stops behave like an exchange stop-market order: once price trades through
the stop, the position is sold at the *worse* of the stop and the current price.
That is pessimistic on purpose. A practice record that flatters itself is how people
talk themselves into risking money on something that never worked.

The bots only ever talk to a broker through `buy`, `sell` and `check_stop`, so the
trading logic does not know or care whether the money is real.
"""

from __future__ import annotations

import time
from typing import Dict, Optional

import config
from engine import http


class PaperBroker:
    name = "paper"
    live = False

    def __init__(self, fee_bps: float = None, slippage_bps: float = None):
        self.fee_bps = fee_bps if fee_bps is not None else config.FEE_TIERS.get(config.DEFAULT_FEE_TIER, 26.0)
        self.slippage_bps = slippage_bps if slippage_bps is not None else config.SLIPPAGE_BPS

    def price(self, symbol: str, venue: str = "okx") -> Optional[float]:
        return ticker(symbol, venue)

    def _fill(self, units: float, px: float) -> Dict:
        fee = units * px * self.fee_bps / 10000.0
        return {"ok": True, "units": units, "avg_price": px, "fee": fee, "cost": units * px,
                "order_id": f"paper-{int(time.time() * 1000)}"}

    def buy(self, units: float, ref_price: float, slip_bps: float = None) -> Dict:
        slip = self.slippage_bps if slip_bps is None else slip_bps
        return self._fill(units, ref_price * (1 + slip / 10000.0))

    def sell(self, units: float, ref_price: float, slip_bps: float = None) -> Dict:
        slip = self.slippage_bps if slip_bps is None else slip_bps
        return self._fill(units, ref_price * (1 - slip / 10000.0))

    def check_stop(self, stop: float, units: float, price: Optional[float],
                   slip_bps: float = None) -> Optional[Dict]:
        """If price has traded through the stop, the fill a stop order would have got."""
        if price is None or price > stop:
            return None
        return self.sell(units, min(price, stop), slip_bps)


def slippage_for(usd_volume_24h: float) -> float:
    """Slippage in basis points, wider for thinner markets.

    A flat couple of basis points is fair on Bitcoin and flattering on a small coin,
    where a market order walks the book. Most of the bots' measured edge came from
    volatile small coins, so pretending they fill like Bitcoin would make the practice
    record lie in exactly the place it matters.
    """
    v = usd_volume_24h or 0.0
    if v >= 500e6:
        return 2.0
    if v >= 100e6:
        return 5.0
    if v >= 30e6:
        return 10.0
    return 20.0


def ticker(symbol: str, venue: str = "okx") -> Optional[float]:
    """Last traded price, a few seconds fresh, from the market's own venue first."""
    def okx():
        d = http.get_json("https://www.okx.com/api/v5/market/ticker", {"instId": symbol}, ttl=4)
        if d and d.get("code") == "0" and d.get("data"):
            return float(d["data"][0]["last"])
        return None

    def coinbase():
        d = http.get_json(f"https://api.exchange.coinbase.com/products/{symbol}/ticker", ttl=4)
        if isinstance(d, dict) and d.get("price"):
            return float(d["price"])
        return None

    for fn in ([coinbase, okx] if venue == "coinbase" else [okx, coinbase]):
        try:
            px = fn()
        except Exception:                                   # noqa: BLE001
            px = None
        if px and px > 0:
            return px
    return None
