"""The internal paper (and demo) account: simulated money, simulated fills, always available.

It implements the same provider interface as a real broker, so paper deployments go through exactly the
same execution engine, risk checks and audit trail as live ones. What makes it a simulator, and how every
fill was produced, is written into each fill record:

* crypto: market and marketable-limit orders walk the venue's live public order book level by level
  (size moves the price); levels beyond the slippage limit are not taken and the remainder is canceled
  (immediate-or-cancel), which produces real partial fills;
* stocks: no free quote or book data, so fills are the latest completed bar's close plus an assumed
  half-spread for the stock's liquidity tier, labelled "synthetic";
* fees: the chosen fee profile (or the venue's base tier); US stock sales add the regulatory fee;
* latency: a configurable delay before pricing (the book is fetched after the decision);
* the account is spot and cash-only: no margin, no short selling, buys limited by cash;
* resting stops and targets are not held here: the bot's trade manager watches them on completed bars and
  records their fills through the engine (mab.execution.engine.record_simulated).

Balance changes on a paper account are simulated and labelled as such; they are not deposits.
"""

from __future__ import annotations

import hashlib
import threading
import time
from typing import Callable, Dict, List, Optional

from mab.account import Account
from mab.clock import is_equity
from mab.costs import FEES, SLIPPAGE_TIER, US_SELL_FEES, tier_for
from mab.execution.base import (CANCELED, FILLED, REJECTED, OrderRejected, OrderRequest, OrderStatus, Provider,
                                ProviderError)

OWNER = "account"                     # sim accounts hold positions per market, like a broker account
BOOK_VENUES = ("coinbase", "kraken", "okx", "demo")


class SimProvider(Provider):
    name = "jarvus_paper"
    simulated = True
    real_money = False
    rate = (600, 60.0)

    def __init__(self, connection_id: str, environment: str, account: Account, persist: Callable[[dict], None],
                 book: Callable[[str, str], object], last_price: Callable[[str, str], Optional[float]],
                 instrument: Callable[[str, str], Optional[dict]], fee_rate: Callable[[str, str], float],
                 latency_ms: int = 150, max_slippage_bps: float = 50.0, label: str = None, sleep=time.sleep):
        if environment not in ("paper", "demo"):
            raise ValueError("a simulated account is paper or demo, never live")
        self.connection_id = connection_id
        self.environment = environment
        self.label = label or ("Demo account (simulated)" if environment == "demo" else "Jarvus Paper (simulated)")
        self.acct = account
        self.persist = persist
        self.book_fn, self.last_fn, self.inst_fn, self.fee_fn = book, last_price, instrument, fee_rate
        self.latency_ms = latency_ms
        self.max_slip = max_slippage_bps / 1e4
        self.sleep = sleep
        self.lock = threading.RLock()
        self.orders: Dict[str, dict] = dict(getattr(account, "sim_orders", {}) or {})

    # ------------------------------------------------------------------ symbols: "venue:instrument"
    @staticmethod
    def split(symbol: str):
        if ":" in symbol:
            v, s = symbol.split(":", 1)
            return v, s
        raise ProviderError(f"paper symbol must be venue:instrument, got {symbol!r}")

    def capabilities(self) -> dict:
        return {"asset_classes": ["crypto", "us_equity", "ca_equity"], "order_types": ["market", "limit"],
                "tif": {"crypto": ["ioc", "gtc"], "us_equity": ["ioc", "day"]}, "fractional": True, "short": False,
                "protective_stop": "virtual", "auth": ["none"], "paper": True, "live": False,
                "market_data": "the fleet's public market data (Coinbase, Kraken, OKX, Yahoo)" if self.environment == "paper"
                else "synthetic demo market", "rate_limit": {"requests": self.rate[0], "per_seconds": self.rate[1]},
                "fills": "simulated: order-book walk for crypto, bar close plus assumed spread for stocks"}

    def authenticate(self) -> dict:
        return {"ok": True, "account_id": f"{self.environment}-{self.connection_id}", "status": "ACTIVE (simulated)",
                "currency": self.acct.currency, "permissions": {"trade": True, "withdraw": False},
                "notes": ["simulated money: nothing here is real"]}

    def _mark_all(self):
        for p in list(self.acct.positions.values()):
            px = self.last_fn(p["venue"], p["instrument"])
            if px:
                self.acct.mark(p["venue"], p["instrument"], px)

    def account(self) -> dict:
        with self.lock:
            self._mark_all()
            s = self.acct.summary()
            unreal = sum(self.acct.position_value(p) - p["qty"] * p["avg_price"] for p in self.acct.positions.values())
            return {"equity": s["equity"], "cash": s["cash"], "buying_power": max(0.0, s["cash"]), "currency": s["currency"],
                    "status": "ACTIVE (simulated)", "can_trade": True, "realized_pnl": s["realized_pnl"],
                    "unrealized_pnl": unreal, "fees": s["fees"], "exposure": s["gross_exposure"], "simulated": True}

    def positions(self) -> List[dict]:
        with self.lock:
            self._mark_all()
            out = []
            for p in self.acct.positions.values():
                mv = self.acct.position_value(p)
                out.append({"symbol": f"{p['venue']}:{p['instrument']}", "qty": p["qty"], "avg_price": p["avg_price"],
                            "market_value": mv, "unrealized_pnl": mv - p["qty"] * p["avg_price"]})
            return out

    def instrument(self, symbol: str) -> dict:
        venue, inst = self.split(symbol)
        d = self.inst_fn(venue, inst)
        if not d:
            raise ProviderError(f"{symbol} is not available")
        return {"symbol": symbol, "broker_symbol": symbol, "tradable": True, "fractionable": not d.get("lot_size"),
                "min_qty": d.get("min_qty") or 0.0, "qty_step": d.get("lot_size") or 0.0, "price_step": d.get("tick_size") or 0.0,
                "min_notional": d.get("min_notional") or 0.0, "asset_class": "us_equity" if is_equity(d["asset_type"]) else "crypto",
                "asset_type": d["asset_type"], "venue": venue, "shortable": False}

    def quote(self, symbol: str) -> dict:
        venue, inst = self.split(symbol)
        if venue in BOOK_VENUES:
            bk = self.book_fn(venue, inst)
            if bk is not None and getattr(bk, "bids", None) and getattr(bk, "asks", None):
                return {"bid": bk.bids[0][0], "ask": bk.asks[0][0], "last": None, "time": getattr(bk, "event_time", None),
                        "source": getattr(bk, "provenance", venue)}
        last = self.last_fn(venue, inst)
        return {"bid": last, "ask": last, "last": last, "time": None, "source": "last completed bar"}

    # ------------------------------------------------------------------ orders
    def _status(self, rec: dict) -> OrderStatus:
        return OrderStatus(rec["id"], rec["cid"], rec["symbol"], rec["side"], rec["type"], rec["qty"], rec["state"],
                           rec["filled"], rec["avg"], rec["fee"], self.acct.currency, rec.get("reason", ""), rec["time"],
                           rec.get("liquidity", "taker"), True, rec.get("model", ""))

    def _save(self):
        # the account and its order records are written together, so a crash cannot separate them
        self.acct.sim_orders = dict(list(self.orders.items())[-2000:])
        st = self.acct.to_state()
        st["sim_orders"] = self.acct.sim_orders
        self.persist(st)

    def submit(self, req: OrderRequest) -> OrderStatus:
        with self.lock:
            if req.client_order_id in self.orders:                     # idempotent: the same id is the same order
                return self._status(self.orders[req.client_order_id])
            if req.order_type not in ("market", "limit"):
                raise OrderRejected(f"the paper account does not hold {req.order_type} orders "
                                    "(the bot's trade manager watches stops and targets)")
            venue, inst_sym = self.split(req.symbol)
            inst = self.inst_fn(venue, inst_sym)
            if inst is None:
                raise OrderRejected(f"unknown instrument {req.symbol}")
            lot = inst.get("lot_size") or 0.0
            qty = int(req.qty / lot + 1e-9) * lot if lot else req.qty
            if qty <= 0:
                raise OrderRejected("quantity rounds to zero at the market's lot size")
            held = sum(p["qty"] for p in self.acct.positions.values() if p["venue"] == venue and p["instrument"] == inst_sym)
            if req.side == "sell":
                if held <= 1e-12:
                    raise OrderRejected("spot account: nothing to sell (no short selling)")
                qty = min(qty, held)
            ref = req.ref_price or self.last_fn(venue, inst_sym)
            if not req.reduce_only and ref and qty * ref < (inst.get("min_notional") or 0.0):
                raise OrderRejected(f"below the market's minimum order ({qty:.8g} units)")
            if self.latency_ms:
                self.sleep(self.latency_ms / 1000.0)
            side = req.side
            if venue in BOOK_VENUES:
                bk = self.book_fn(venue, inst_sym)
                if bk is None or not bk.bids or not bk.asks:
                    raise OrderRejected("no executable price: order book unavailable or empty")
                levels = bk.asks if side == "buy" else bk.bids
                best = levels[0][0]
                cap = best * (1 + self.max_slip) if side == "buy" else best * (1 - self.max_slip)
                if req.limit_price:
                    cap = min(cap, req.limit_price) if side == "buy" else max(cap, req.limit_price)
                filled, cost = 0.0, 0.0
                for px, sz in levels:
                    if (side == "buy" and px > cap) or (side == "sell" and px < cap):
                        break
                    take = min(sz, qty - filled)
                    filled += take
                    cost += take * px
                    if filled >= qty - 1e-15:
                        break
                if lot and filled:
                    filled = int(filled / lot + 1e-9) * lot
                avg = cost / filled if filled else None
                model = (f"simulated: walked {getattr(bk, 'provenance', venue)} book, IOC within "
                         f"{self.max_slip * 1e4:.0f} bps of best" + (f" and limit {req.limit_price:.8g}" if req.limit_price else ""))
            else:
                if not ref:
                    raise OrderRejected("no executable price: no recent bar")
                half = SLIPPAGE_TIER[tier_for(inst_sym, inst["asset_type"])]
                avg = ref * (1 + half) if side == "buy" else ref * (1 - half)
                if req.limit_price and ((side == "buy" and avg > req.limit_price) or (side == "sell" and avg < req.limit_price)):
                    filled, avg = 0.0, None
                else:
                    filled = qty
                model = f"simulated synthetic fill: last bar close +/- {half * 1e4:.1f} bps assumed spread (no quote data)"
            liq = "taker"
            rate = self.fee_fn(venue, liq)
            fee = filled * avg * rate if filled else 0.0
            if filled and is_equity(inst["asset_type"]) and side == "sell":
                fee += filled * avg * US_SELL_FEES
            if filled and side == "buy" and not req.reduce_only:
                free = self.acct.cash
                if filled * avg + fee > free:
                    afford = max(0.0, free / (1 + rate) / avg)
                    afford = int(afford / lot + 1e-9) * lot if lot else afford
                    if afford <= 0 or afford * avg < (inst.get("min_notional") or 0.0):
                        raise OrderRejected(f"not enough paper cash ({free:,.2f} {self.acct.currency})")
                    filled = afford
                    fee = filled * avg * rate
            oid = "sim-" + hashlib.sha1(req.client_order_id.encode()).hexdigest()[:16]
            if filled <= 0:
                state, reason = CANCELED, "no liquidity within the slippage/limit cap; canceled (immediate-or-cancel)"
            elif filled < qty - 1e-12:
                state, reason = CANCELED, f"partial fill: {filled:.8g} of {qty:.8g}; the rest was canceled (immediate-or-cancel)"
            else:
                state, reason = FILLED, ""
            t = int(time.time() * 1000)
            if filled > 0:
                self.acct.apply_fill(OWNER, venue, inst_sym, side, filled, avg, fee, t)
            rec = {"id": oid, "cid": req.client_order_id, "symbol": req.symbol, "side": side, "type": req.order_type,
                   "qty": req.qty, "state": state, "filled": filled, "avg": avg, "fee": fee, "reason": reason, "time": t,
                   "model": model, "liquidity": liq}
            self.orders[req.client_order_id] = rec
            self._save()
            return self._status(rec)

    def cancel(self, broker_order_id: str) -> None:
        return None                                              # simulated orders are final when submitted

    def get_order(self, broker_order_id=None, client_order_id=None) -> Optional[OrderStatus]:
        with self.lock:
            if client_order_id and client_order_id in self.orders:
                return self._status(self.orders[client_order_id])
            if broker_order_id:
                rec = next((r for r in self.orders.values() if r["id"] == broker_order_id), None)
                return self._status(rec) if rec else None
            return None

    def open_orders(self) -> List[OrderStatus]:
        return []

    def funding(self) -> dict:
        return {"url": None, "label": "Set paper balance", "simulated": True,
                "note": "paper money only: changing it is simulated and is never a deposit"}

    def sellable(self, symbol: str) -> Optional[float]:
        venue, inst = self.split(symbol)
        return sum(p["qty"] for p in self.acct.positions.values() if p["venue"] == venue and p["instrument"] == inst)

    # ------------------------------------------------------------------ simulated balance (paper only, labelled)
    def set_balance(self, kind: str, amount: float, note: str = "") -> dict:
        with self.lock:
            rec = getattr(self.acct, kind)(float(amount), note or "paper balance change (simulated)")
            self._save()
            return rec


def venue_fee_rate(fee_profile: Optional[dict]):
    """fee_rate(venue, liquidity) for the paper account: the fee profile for crypto, the venue's own otherwise."""
    def rate(venue: str, liquidity: str) -> float:
        if fee_profile and venue != "yahoo":
            return fee_profile[liquidity]
        return FEES.get(venue, FEES["kraken"])[liquidity]
    return rate
