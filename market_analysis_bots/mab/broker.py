"""Order execution: the broker interface, the paper engine, and the (disabled) live path.

Paper execution model
---------------------
* Latency: the order is priced against a book fetched AFTER the decision (real network round
  trip) plus a configurable simulated delay.
* Crypto market orders walk the venue's live order book level by level: the fill price is the
  volume-weighted price of the levels consumed, so size moves the price (slippage). Levels
  beyond `max_slippage_bps` from the best price are not taken; any unfilled remainder is
  cancelled (immediate-or-cancel), giving partial fills.
* US/Canadian stock orders have no free quote or book data. They fill at the latest completed
  bar's close plus an assumed half-spread for the instrument's liquidity tier, and every such
  fill is labelled `synthetic` in its record.
* Resting stops, limits and targets are managed by the strategy's trade manager against
  completed bars (a touch is not a fill for limits; stops fill at the stop price or the gap
  price, with extra slippage).
* Fees: the venue's base-tier taker/maker rate (mab.costs).
* Rejections: unknown instrument, size below the venue minimum after lot rounding, not enough
  free cash, shorting an instrument that cannot be shorted, no executable price, book empty.

Real money
----------
No code in this package can submit an order to a real broker or exchange. `LiveBroker` exists
so the interface is complete and refuses every call. Enabling real-money trading requires a
separate, explicitly authorised change that adds a venue adapter, reviewed on its own.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import asdict
from typing import List, Optional, Tuple

from mab.clock import is_equity
from mab.costs import FEES, SLIPPAGE_TIER, US_SELL_FEES, tier_for
from mab.models import Fill, OrderIntent, now_ms
from mab.net import HttpError


class OrderResult(dict):
    """{order_id, intent_id, status: filled|partially_filled|rejected|cancelled, filled_qty, avg_price,
    fee, reason, model, fills: [Fill]}"""


class BrokerAdapter:
    name = "base"
    real_money = False

    def execute(self, intent: OrderIntent, ref_price: float, instrument: dict) -> OrderResult:
        raise NotImplementedError


class LiveTradingDisabled(RuntimeError):
    pass


class LiveBroker(BrokerAdapter):
    """Placeholder for real-money brokers. Every call is refused in this build."""
    name = "live"
    real_money = True

    def __init__(self, *_, **__):
        raise LiveTradingDisabled(
            "Real-money order submission is disabled in this build. It can only be enabled by a separate, "
            "explicitly authorised change that adds and reviews a broker adapter. Paper trading is unaffected.")


def _oid(*parts) -> str:
    return hashlib.sha1("|".join(str(p) for p in parts).encode()).hexdigest()[:16]


class PaperBroker(BrokerAdapter):
    name = "paper"

    def __init__(self, hub, account, latency_ms: int = 150, max_slippage_bps: float = 50.0, depth: int = 50):
        self.hub = hub
        self.account = account
        self.latency_ms = latency_ms
        self.max_slip = max_slippage_bps / 1e4
        self.depth = depth
        self.stats = {"orders": 0, "filled": 0, "partial": 0, "rejected": 0, "book_walks": 0, "synthetic": 0}

    # ------------------------------------------------------------------ helpers
    def _reject(self, intent: OrderIntent, reason: str) -> OrderResult:
        self.stats["rejected"] += 1
        return OrderResult(order_id=_oid(intent.intent_id, "o"), intent_id=intent.intent_id, status="rejected",
                           filled_qty=0.0, avg_price=None, fee=0.0, reason=reason, model="", fills=[])

    @staticmethod
    def _round(qty: float, lot: float) -> float:
        if lot and lot > 0:
            return int(qty / lot + 1e-9) * lot
        return qty

    def fee_rate(self, venue: str, liquidity: str = "taker") -> float:
        return FEES.get(venue, FEES["kraken"])[liquidity]

    # ------------------------------------------------------------------ execute
    def execute(self, intent: OrderIntent, ref_price: float, inst: dict) -> OrderResult:
        self.stats["orders"] += 1
        if inst is None:
            return self._reject(intent, "unknown instrument")
        side = intent.side
        qty = self._round(intent.quantity, inst.get("lot_size") or 0.0)
        if qty <= 0:
            return self._reject(intent, "quantity rounds to zero at the venue's lot size")
        min_notional = inst.get("min_notional") or 0.0
        min_qty = inst.get("min_qty") or 0.0
        if not intent.reduce_only and (qty * ref_price < min_notional or qty < min_qty):
            return self._reject(intent, f"below the venue minimum order ({qty:.8g} units, ~{qty * ref_price:,.2f})")
        opening_short = side == "sell" and not intent.reduce_only
        if opening_short and not inst.get("can_short", False):
            return self._reject(intent, "this instrument cannot be sold short (spot market)")
        if self.latency_ms:
            time.sleep(self.latency_ms / 1000.0)
        venue = inst["venue"]
        if venue in ("coinbase", "kraken", "okx"):
            try:
                book = self.hub.adapters[venue].book(inst["symbol"], depth=self.depth)
            except (HttpError, KeyError, ValueError) as e:
                return self._reject(intent, f"no executable price: order book unavailable ({e})")
            if book is None or not book.bids or not book.asks:
                return self._reject(intent, "no executable price: order book empty")
            levels = book.asks if side == "buy" else book.bids
            best = levels[0][0]
            limit = best * (1 + self.max_slip) if side == "buy" else best * (1 - self.max_slip)
            filled, cost = 0.0, 0.0
            for px, sz in levels:
                if (side == "buy" and px > limit) or (side == "sell" and px < limit):
                    break
                take = min(sz, qty - filled)
                filled += take
                cost += take * px
                if filled >= qty - 1e-15:
                    break
            if filled <= 0:
                return self._reject(intent, "no liquidity within the slippage limit")
            avg = cost / filled
            filled = self._round(filled, inst.get("lot_size") or 0.0)
            if filled <= 0:
                return self._reject(intent, "no liquidity within the slippage limit")
            model = f"book walk: {len(levels)} levels from {book.provenance}, IOC within {self.max_slip * 1e4:.0f} bps"
            self.stats["book_walks"] += 1
        else:
            tier = tier_for(inst["symbol"], inst["asset_type"])
            half = SLIPPAGE_TIER[tier]
            avg = ref_price * (1 + half) if side == "buy" else ref_price * (1 - half)
            filled = qty
            model = f"synthetic: last bar close +/- {half * 1e4:.1f} bps assumed spread ({tier}); no quote data"
            self.stats["synthetic"] += 1
        fee = filled * avg * self.fee_rate(venue)
        if is_equity(inst["asset_type"]) and side == "sell":
            fee += filled * avg * US_SELL_FEES
        if side == "buy" and not intent.reduce_only:
            free = self.account.cash
            if filled * avg + fee > free:
                afford = self._round(max(0.0, (free / (1 + self.fee_rate(venue))) / avg), inst.get("lot_size") or 0.0)
                if afford <= 0 or afford * avg < min_notional:
                    return self._reject(intent, f"not enough free cash ({free:,.2f})")
                filled = afford
                fee = filled * avg * self.fee_rate(venue)
        status = "filled" if filled >= qty - 1e-12 else "partially_filled"
        self.stats["filled" if status == "filled" else "partial"] += 1
        order_id = _oid(intent.intent_id, "o")
        t = now_ms()
        fill = Fill(_oid(order_id, "f", 0), order_id, intent.intent_id, intent.bot_id, inst["symbol"], venue, side,
                    filled, avg, fee, "taker", t, True, model)
        return OrderResult(order_id=order_id, intent_id=intent.intent_id, status=status, filled_qty=filled,
                           avg_price=avg, fee=fee, reason="" if status == "filled" else
                           f"partial: {filled:.8g} of {qty:.8g} within the slippage limit; remainder cancelled",
                           model=model, fills=[fill])
