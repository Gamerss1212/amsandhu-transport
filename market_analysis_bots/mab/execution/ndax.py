"""NDAX (Canada; AlphaPoint platform) for live trading, over its authenticated WebSocket gateway.

NDAX publishes no sandbox, so this connection is live only. It follows NDAX's published API (AuthenticateUser
with HMAC-SHA256(secret, nonce + user id + key), SendOrder, CancelOrder, GetOrderStatus, GetOpenOrders,
GetOrderHistory, GetAccountPositions, GetLevel1, GetInstruments) and has NOT been run against a live NDAX
account in this build: the connection test is the first real check. Create the key without withdrawal rights.
"""

from __future__ import annotations

import json
import threading
import time
from typing import Dict, List, Optional

from mab.brokers.base import BrokerError as _OldBrokerError, OrderUnknown as _OldUnknown
from mab.brokers.ndax import GATEWAY, OMS, WebSocket, signature
from mab.execution.base import (ACKED, CANCELED, EXPIRED, FILLED, PARTIALLY_FILLED, REJECTED, AuthError,
                                OrderRejected, OrderRequest, OrderStatus, OutcomeUnknown, Provider, ProviderError,
                                int_for)

SITE = "https://ndax.io/"
STATE = {"Working": ACKED, "FullyExecuted": FILLED, "Canceled": CANCELED, "Rejected": REJECTED, "Expired": EXPIRED}


class NDAX(Provider):
    name = "ndax"
    label = "NDAX"
    environment = "live"
    real_money = True
    rate = (30, 60.0)

    def __init__(self, key: str, secret: str, user_id: str = "", quote: str = "CAD", connect=None, **_):
        if not key or not secret:
            raise AuthError("NDAX needs an API key and secret")
        if not str(user_id).strip():
            raise AuthError("NDAX needs the numeric User ID shown with the API key")
        self._key, self._secret, self.user_id = key, secret, str(user_id).strip()
        self.quote = quote.upper()
        self._connect = connect or (lambda: WebSocket(GATEWAY))
        self._ws = None
        self._seq = 0
        self._lock = threading.Lock()
        self.account_id = None
        self._inst: Dict[str, dict] = {}

    def _call(self, fn: str, payload: dict, order_send: bool = False):
        with self._lock:
            try:
                if self._ws is None:
                    self._ws = self._connect()
                    self._auth()
                return self._raw(fn, payload)
            except OutcomeUnknown:
                self._ws = None
                raise
            except _OldUnknown as e:                        # the socket closed mid-request
                self._ws = None
                if order_send:
                    raise OutcomeUnknown(f"NDAX {fn}: {e}")
                raise ProviderError(f"NDAX {fn}: {e}")
            except _OldBrokerError as e:
                self._ws = None
                raise ProviderError(str(e))
            except (OSError, ConnectionError) as e:
                self._ws = None
                if order_send:
                    raise OutcomeUnknown(f"NDAX {fn}: connection lost ({e})")
                raise ProviderError(f"NDAX {fn}: {e}")

    def _raw(self, fn, payload):
        self._seq += 2
        seq = self._seq
        self._ws.send(json.dumps({"m": 0, "i": seq, "n": fn, "o": json.dumps(payload)}))
        deadline = time.time() + 15
        while time.time() < deadline:
            msg = json.loads(self._ws.recv())
            if msg.get("i") != seq or msg.get("m") not in (1, 5):
                continue
            body = json.loads(msg.get("o") or "{}") if isinstance(msg.get("o"), str) else (msg.get("o") or {})
            if msg["m"] == 5:
                raise ProviderError(f"NDAX {fn}: {body}")
            return body
        raise OutcomeUnknown(f"NDAX {fn}: no reply")

    def _auth(self):
        nonce = str(int(time.time() * 1000))
        r = self._raw("AuthenticateUser", {"APIKey": self._key, "Signature": signature(self._secret, nonce, self.user_id, self._key),
                                           "UserId": self.user_id, "Nonce": nonce})
        if not (r.get("Authenticated") or r.get("authenticated")):
            self._ws.close()
            self._ws = None
            raise AuthError(f"NDAX authentication failed: {r.get('errormsg') or 'check the key, secret and user id'}")
        user = r.get("User") or r.get("user") or {}
        self.account_id = user.get("AccountId") or user.get("accountId")

    def capabilities(self) -> dict:
        return {"asset_classes": ["crypto"], "order_types": ["market", "limit", "stop"], "tif": {"crypto": ["gtc", "ioc"]},
                "fractional": True, "short": False, "protective_stop": "stop", "auth": ["api_key"], "paper": False,
                "live": True, "market_data": "NDAX Level 1", "rate_limit": {"requests": 30, "per_seconds": 60},
                "withdrawals": "never requested", "notes": ["NDAX has no sandbox: live only",
                                                            "not yet run against a live NDAX account in this build"]}

    def authenticate(self) -> dict:
        self._call("GetAccountPositions", {"AccountId": self.account_id, "OMSId": OMS})
        return {"ok": True, "account_id": f"NDAX account ...{str(self.account_id)[-4:]}", "status": "ACTIVE",
                "currency": self.quote, "environment": "live", "permissions": {"trade": None, "withdraw": False},
                "notes": ["NDAX does not report key permissions; trading permission shows at the first order"]}

    def _positions_raw(self):
        return self._call("GetAccountPositions", {"AccountId": self.account_id, "OMSId": OMS}) or []

    def account(self) -> dict:
        rows = self._positions_raw()
        cash = next((r for r in rows if r.get("ProductSymbol") == self.quote), {})
        amt, hold = float(cash.get("Amount") or 0), float(cash.get("Hold") or 0)
        return {"equity": None, "cash": amt, "buying_power": amt - hold, "currency": self.quote, "status": "ACTIVE",
                "can_trade": True, "simulated": False,
                "note": "NDAX reports balances per currency; equity across coins is not computed here"}

    def positions(self) -> List[dict]:
        return [{"symbol": r["ProductSymbol"], "qty": float(r.get("Amount") or 0),
                 "qty_available": float(r.get("Amount") or 0) - float(r.get("Hold") or 0)}
                for r in self._positions_raw() if r.get("ProductSymbol") != self.quote and float(r.get("Amount") or 0) > 0]

    def instrument(self, symbol: str) -> dict:
        base = symbol.split(":", 1)[-1].upper().replace("/", "-").split("-")[0]
        base = {"XBT": "BTC"}.get(base, base)
        sym = base + self.quote
        if sym not in self._inst:
            for ins in self._call("GetInstruments", {"OMSId": OMS}) or []:
                self._inst[ins["Symbol"]] = {"broker_symbol": ins["Symbol"], "id": ins["InstrumentId"], "tradable": True,
                                             "min_qty": float(ins.get("MinimumQuantity") or 0),
                                             "qty_step": float(ins.get("QuantityIncrement") or 1e-8),
                                             "price_step": float(ins.get("PriceIncrement") or 0.01), "min_notional": 0.0,
                                             "asset_class": "crypto", "base": base, "fractionable": True, "shortable": False}
            if sym not in self._inst:
                raise ProviderError(f"NDAX does not list {sym}")
        return dict(self._inst[sym], symbol=symbol)

    def quote(self, symbol: str) -> dict:
        m = self.instrument(symbol)
        l1 = self._call("GetLevel1", {"OMSId": OMS, "InstrumentId": m["id"]}) or {}
        return {"bid": float(l1.get("BestBid") or 0) or None, "ask": float(l1.get("BestOffer") or 0) or None,
                "last": float(l1.get("LastTradedPx") or 0) or None, "time": l1.get("TimeStamp"), "source": "NDAX Level 1"}

    def submit(self, req: OrderRequest) -> OrderStatus:
        m = self.instrument(req.symbol)
        step = m["price_step"]
        body = {"InstrumentId": m["id"], "OMSId": OMS, "AccountId": self.account_id,
                "TimeInForce": 3 if req.tif == "ioc" else 1, "ClientOrderId": int_for(req.client_order_id),
                "OrderIdOCO": 0, "UseDisplayQuantity": False, "Side": 0 if req.side == "buy" else 1, "Quantity": req.qty,
                "OrderType": {"market": 1, "limit": 2, "stop": 3}.get(req.order_type)}
        if body["OrderType"] is None:
            raise OrderRejected(f"order type {req.order_type} is not supported on NDAX here")
        if req.order_type == "limit":
            body["LimitPrice"] = round(round(req.limit_price / step) * step, 10)
        if req.order_type == "stop":
            body["StopPrice"] = round(round(req.stop_price / step) * step, 10)
        r = self._call("SendOrder", body, order_send=True)
        if str(r.get("status", "")).lower() == "rejected" or r.get("errormsg"):
            raise OrderRejected(f"NDAX: {r.get('errormsg') or 'rejected'}")
        oid = str(r.get("OrderId") or "")
        if not oid:
            raise OutcomeUnknown("NDAX accepted the request but returned no order id")
        return self.get_order(broker_order_id=oid) or OrderStatus(oid, req.client_order_id, m["broker_symbol"], req.side,
                                                                   req.order_type, req.qty, ACKED)

    def _parse(self, o: dict, cid: str = "") -> OrderStatus:
        filled = float(o.get("QuantityExecuted") or 0)
        state = STATE.get(o.get("OrderState"), ACKED)
        if state == ACKED and filled > 0:
            state = PARTIALLY_FILLED
        return OrderStatus(str(o.get("OrderId")), cid, str(o.get("Instrument")), "buy" if o.get("Side") in (0, "Buy") else "sell",
                           str(o.get("OrderType")), float(o.get("OrigQuantity") or o.get("Quantity") or 0), state, filled,
                           float(o["AvgPrice"]) if o.get("AvgPrice") else None, 0.0, self.quote,
                           o.get("RejectReason") or "", int(time.time() * 1000))

    def get_order(self, broker_order_id=None, client_order_id=None) -> Optional[OrderStatus]:
        if broker_order_id:
            o = self._call("GetOrderStatus", {"OMSId": OMS, "AccountId": self.account_id, "OrderId": int(broker_order_id)})
        elif client_order_id:
            n = int_for(client_order_id)
            rows = (self._call("GetOpenOrders", {"OMSId": OMS, "AccountId": self.account_id}) or []) + \
                   (self._call("GetOrderHistory", {"OMSId": OMS, "AccountId": self.account_id, "Depth": 200}) or [])
            o = next((x for x in rows if x.get("ClientOrderId") == n), None)
        else:
            raise ProviderError("get_order needs an order id or a client order id")
        return self._parse(o, client_order_id or "") if o and o.get("OrderId") else None

    def cancel(self, broker_order_id: str) -> None:
        try:
            self._call("CancelOrder", {"OMSId": OMS, "AccountId": self.account_id, "OrderId": int(broker_order_id)})
        except ProviderError as e:
            if "not found" in str(e).lower():
                return None
            raise

    def open_orders(self) -> List[OrderStatus]:
        return [self._parse(o) for o in (self._call("GetOpenOrders", {"OMSId": OMS, "AccountId": self.account_id}) or [])]

    def sellable(self, symbol: str) -> Optional[float]:
        base = self.instrument(symbol)["base"]
        return next((p["qty_available"] for p in self.positions() if p["symbol"] == base), 0.0)

    def funding(self) -> dict:
        return {"url": SITE, "label": "Add funds on NDAX", "simulated": False,
                "note": "deposits are made in your NDAX account. Jarvus never moves money and never needs withdrawal "
                        "permission; balances here update after NDAX reports them."}
