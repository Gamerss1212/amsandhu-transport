"""Alpaca (US stocks) through the Trading API v2.

Alpaca has a free paper-trading endpoint with the same API, which makes it the safe way to check the
whole live path end to end before any money is involved: choose "paper" when adding the broker.
Account availability depends on the country of residence (check Alpaca's site); this adapter does not
assume eligibility. Long only here: shorting needs a margin account and is never used.
"""

from __future__ import annotations

import json
import urllib.parse
from typing import Dict

from mab.brokers.base import Broker, BrokerError, Order, round_step

URLS = {"paper": "https://paper-api.alpaca.markets", "live": "https://api.alpaca.markets"}
DATA = "https://data.alpaca.markets"             # market data (same keys, paper or live)
STATUS = {"new": "open", "accepted": "open", "pending_new": "open", "partially_filled": "open", "filled": "filled",
          "done_for_day": "canceled", "canceled": "canceled", "expired": "canceled", "replaced": "canceled",
          "pending_cancel": "open", "pending_replace": "open", "rejected": "rejected", "suspended": "open",
          "calculated": "open", "stopped": "open", "held": "open", "accepted_for_bidding": "open"}


class Alpaca(Broker):
    name = "alpaca"
    asset_class = "stock"

    def __init__(self, key, secret, transport=None, environment="paper", **opts):
        super().__init__(key, secret, transport, **opts)
        if environment not in URLS:
            raise BrokerError("environment must be 'paper' or 'live'")
        self.environment = environment
        self.real_money = environment == "live"
        self.base = URLS[environment]
        self._assets: Dict[str, dict] = {}

    def _req(self, method, path, body=None, params=None):
        url = self.base + path + ("?" + urllib.parse.urlencode(params) if params else "")
        headers = {"APCA-API-KEY-ID": self.key, "APCA-API-SECRET-KEY": self.secret, "Content-Type": "application/json"}
        status, raw = self.http(method, url, headers, json.dumps(body).encode() if body is not None else None)
        if method == "DELETE" and status in (200, 204):
            return {}
        if status == 404 and path.startswith("/v2/orders"):
            return None
        return self._json(status, raw, f"Alpaca {method} {path}")

    def market(self, instrument):
        sym = instrument.upper()
        if sym not in self._assets:
            a = self._req("GET", f"/v2/assets/{urllib.parse.quote(sym)}")
            if not a or not a.get("tradable"):
                raise BrokerError(f"Alpaca: {sym} is not tradable")
            self._assets[sym] = {"symbol": sym, "min_qty": 0.0 if a.get("fractionable") else 1.0,
                                 "qty_step": 1e-9 if a.get("fractionable") else 1.0, "price_step": 0.01, "min_notional": 1.0}
        return self._assets[sym]

    def price(self, instrument):
        sym = self.market(instrument)["symbol"]
        headers = {"APCA-API-KEY-ID": self.key, "APCA-API-SECRET-KEY": self.secret}
        status, raw = self.http("GET", f"{DATA}/v2/stocks/{urllib.parse.quote(sym)}/quotes/latest", headers, None)
        q = self._json(status, raw, "Alpaca quote").get("quote") or {}
        return {"bid": float(q.get("bp") or 0) or None, "ask": float(q.get("ap") or 0) or None, "last": None}

    def _order(self, instrument, side, kind, qty, price, client_id, tif) -> Order:
        m = self.market(instrument)
        q = round_step(qty, m["qty_step"])
        if q <= 0 or q < m["min_qty"]:
            return Order("", client_id, instrument, side, kind, qty, "rejected", reason=f"size {qty:.6f} below the minimum")
        body = {"symbol": m["symbol"], "qty": f"{q:.9f}".rstrip("0").rstrip("."), "side": side,
                "type": kind, "time_in_force": tif, "client_order_id": client_id[:48]}
        if kind == "limit":
            body["limit_price"] = f"{price:.2f}"
        if kind == "stop":
            body["stop_price"] = f"{price:.2f}"
        o = self._req("POST", "/v2/orders", body)
        return self._parse(o, client_id)

    def _parse(self, o, client_id="") -> Order:
        filled = float(o.get("filled_qty") or 0)
        status = STATUS.get(o.get("status"), "unknown")
        if status == "canceled" and filled > 0:
            status = "partially_filled"
        return Order(o.get("id", ""), o.get("client_order_id") or client_id, o.get("symbol", ""), o.get("side", ""),
                     o.get("type", ""), float(o.get("qty") or 0), status, filled,
                     float(o["filled_avg_price"]) if o.get("filled_avg_price") else None, 0.0, "", raw=o)

    def buy(self, instrument, qty, limit_price, client_id):
        # a capped limit order; Alpaca rejects IOC for fractional shares, so it is a day order and the
        # executor cancels whatever has not filled after a few seconds (the same effect as IOC)
        return self._order(instrument, "buy", "limit", qty, limit_price, client_id, "day")

    def sell(self, instrument, qty, limit_price, client_id):
        if limit_price is None:
            return self._order(instrument, "sell", "market", qty, None, client_id, "day")
        return self._order(instrument, "sell", "limit", qty, limit_price, client_id, "day")

    def stop(self, instrument, qty, stop_price, client_id):
        return self._order(instrument, "sell", "stop", qty, stop_price, client_id, "gtc")

    def cancel(self, order_id):
        self._req("DELETE", f"/v2/orders/{order_id}")

    def order(self, order_id=None, client_id=None):
        if order_id:
            o = self._req("GET", f"/v2/orders/{order_id}")
        elif client_id:
            o = self._req("GET", "/v2/orders:by_client_order_id", params={"client_order_id": client_id[:48]})
        else:
            raise BrokerError("order(): give an order id or a client id")
        return self._parse(o, client_id or "") if o else None

    def balances(self):
        a = self._req("GET", "/v2/account")
        out = {"USD": float(a.get("cash") or 0)}
        for p in self._req("GET", "/v2/positions") or []:
            out[p["symbol"]] = float(p.get("qty") or 0)
        return out

    def test(self):
        a = self._req("GET", "/v2/account")
        blocked = bool(a.get("trading_blocked") or a.get("account_blocked"))
        return {"ok": True, "broker": f"Alpaca ({self.environment})", "quote": "USD", "cash": float(a.get("cash") or 0),
                "equity": float(a.get("equity") or 0), "balances": self.balances(), "can_trade": not blocked,
                "status": a.get("status"), "notes": (["this account is blocked from trading"] if blocked else []) +
                (["paper endpoint: no real money moves"] if self.environment == "paper" else [])}
