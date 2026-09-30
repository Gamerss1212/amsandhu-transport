"""A scriptable in-memory broker for execution tests: acks, partial fills, rejections, lost responses,
orders that exist or not after a timeout, cancels that race fills, fees taken in the bought asset."""

import itertools
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mab.execution.base import (ACKED, CANCELED, FILLED, PARTIALLY_FILLED, REJECTED, NotSent, OrderRejected,  # noqa: E402
                                OrderStatus, OutcomeUnknown, Provider)


class FakeBroker(Provider):
    name = "fake"
    label = "Fake broker"
    simulated = False

    def __init__(self, environment="paper", ask=100.0, bid=99.9, stop_kind="stop"):
        self.environment = environment
        self.real_money = environment == "live"
        self.ask, self.bid = ask, bid
        self.stop_kind = stop_kind
        self.orders = {}                     # broker id -> dict
        self.by_cid = {}
        self.ids = itertools.count(1)
        self.submits = []                    # every submit call (to count real sends)
        self.script = []                     # queued behaviours for the next submits
        self.fill_on_submit = True
        self.partial = None                  # fraction filled for the next entry
        self.fee_in_asset = 0.0              # e.g. 0.0025: buys credit qty * (1 - fee)
        self.holdings = {}
        self.lookup_fails = 0
        self.cash = 10_000.0

    # interface ------------------------------------------------------------------------
    def capabilities(self):
        return {"protective_stop": self.stop_kind, "order_types": ["market", "limit", "stop", "stop_limit"]}

    def authenticate(self):
        return {"ok": True, "account_id": "FAKE-1", "status": "ACTIVE", "currency": "USD"}

    def account(self):
        return {"equity": self.cash, "cash": self.cash, "buying_power": self.cash, "currency": "USD", "status": "ACTIVE",
                "can_trade": True}

    def positions(self):
        return [{"symbol": s, "qty": q} for s, q in self.holdings.items() if q > 0]

    def instrument(self, symbol):
        return {"symbol": symbol, "broker_symbol": symbol.split(":")[-1], "tradable": True, "qty_step": 0.0001,
                "min_qty": 0.0001, "min_notional": 1.0, "asset_class": "crypto"}

    def quote(self, symbol):
        return {"bid": self.bid, "ask": self.ask, "last": (self.bid + self.ask) / 2}

    def _status(self, o):
        return OrderStatus(o["id"], o["cid"], o["symbol"], o["side"], o["type"], o["qty"], o["state"], o["filled"],
                           o["avg"], o["fee"], "USD", o.get("reason", ""))

    def _fill(self, o, qty, px):
        o["avg"] = ((o["avg"] or 0) * o["filled"] + px * qty) / (o["filled"] + qty)
        o["filled"] += qty
        o["fee"] += qty * px * 0.001
        if o["side"] == "buy":
            self.holdings[o["symbol"]] = self.holdings.get(o["symbol"], 0) + qty * (1 - self.fee_in_asset)
        else:
            self.holdings[o["symbol"]] = self.holdings.get(o["symbol"], 0) - qty

    def submit(self, req):
        self.submits.append(req)
        action = self.script.pop(0) if self.script else "ok"
        if action == "reject":
            raise OrderRejected("insufficient buying power")
        if action == "notsent":
            raise NotSent("connection refused")
        placed = action in ("ok", "timeout_placed")
        o = {"id": f"B{next(self.ids)}", "cid": req.client_order_id, "symbol": req.symbol, "side": req.side,
             "type": req.order_type, "qty": req.qty, "state": ACKED, "filled": 0.0, "avg": None, "fee": 0.0,
             "stop": req.stop_price, "limit": req.limit_price}
        if placed:
            self.orders[o["id"]] = o
            self.by_cid[req.client_order_id] = o
            if req.order_type in ("market", "limit") and self.fill_on_submit:
                px = self.ask if req.side == "buy" else self.bid
                frac = self.partial if (self.partial is not None and req.side == "buy") else 1.0
                self.partial = None
                self._fill(o, req.qty * frac, px)
                o["state"] = FILLED if frac >= 1 else (CANCELED if req.tif == "ioc" else PARTIALLY_FILLED)
        if action.startswith("timeout"):
            raise OutcomeUnknown("read timed out")
        return self._status(o)

    def cancel(self, broker_order_id):
        o = self.orders.get(broker_order_id)
        if o and o["state"] in (ACKED, PARTIALLY_FILLED):
            o["state"] = CANCELED

    def get_order(self, broker_order_id=None, client_order_id=None):
        if self.lookup_fails:
            self.lookup_fails -= 1
            raise OutcomeUnknown("lookup timed out")
        o = self.orders.get(broker_order_id) if broker_order_id else self.by_cid.get(client_order_id)
        return self._status(o) if o else None

    def open_orders(self):
        return [self._status(o) for o in self.orders.values() if o["state"] in (ACKED, PARTIALLY_FILLED)]

    def sellable(self, symbol):
        held = self.holdings.get(symbol, 0.0)
        reserved = sum(o["qty"] - o["filled"] for o in self.orders.values()
                       if o["symbol"] == symbol and o["side"] == "sell" and o["state"] in (ACKED, PARTIALLY_FILLED))
        return max(0.0, held - reserved)

    # test helpers ------------------------------------------------------------------------
    def trigger_stop(self, px=None):
        for o in self.orders.values():
            if o["type"] in ("stop", "stop_limit") and o["state"] == ACKED:
                self._fill(o, o["qty"], px or o["stop"])
                o["state"] = FILLED
                return o

    def reject_everything(self):
        self.script = ["reject"] * 50
