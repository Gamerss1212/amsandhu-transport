"""Kraken spot (Kraken Pro) through the REST API.

Signing follows Kraken's documented scheme (API-Sign = base64(HMAC-SHA512(path + SHA256(nonce + body),
base64-decoded secret))) and is tested against Kraken's published example. Create the API key WITHOUT
withdrawal permission; it needs "Query funds", "Query open/closed orders & trades" and, for live trading,
"Create & modify orders" and "Cancel/close orders".

Details that matter with real money:
* every order carries a userref derived from the fleet's intent id, so an order whose response was lost
  can be found instead of sent twice;
* fees are charged in the quote currency (oflags=fciq), so the coins bought are exactly the coins the
  protective stop has to sell;
* entries are limit orders with timeinforce=IOC at a capped price (never an unbounded market order);
* the protective stop is a stop-loss order resting on Kraken, so it works even if this computer is off.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import threading
import time
import urllib.parse
import zlib
from typing import Dict, Optional

from mab.brokers.base import Broker, BrokerError, Order, round_step

API = "https://api.kraken.com"
# fleet instrument (Coinbase-style "BASE-QUOTE" or Kraken code) -> Kraken base asset name
BASES = {"BTC": "XBT", "XBT": "XBT", "DOGE": "XDG"}
STATUS = {"pending": "open", "open": "open", "closed": "filled", "canceled": "canceled", "expired": "canceled"}


def sign(path: str, nonce: str, body: str, secret: str) -> str:
    msg = path.encode() + hashlib.sha256((nonce + body).encode()).digest()
    return base64.b64encode(hmac.new(base64.b64decode(secret), msg, hashlib.sha512).digest()).decode()


def userref(client_id: str) -> int:
    """Kraken wants a signed 32-bit integer; derive it deterministically from the client id."""
    return zlib.crc32(client_id.encode()) & 0x7FFFFFFF


class Kraken(Broker):
    name = "kraken"
    asset_class = "crypto"

    def __init__(self, key, secret, transport=None, quote="CAD", **opts):
        super().__init__(key, secret, transport, **opts)
        self.quote = quote.upper()
        self._nonce = 0
        self._lock = threading.Lock()
        self._pairs: Dict[str, dict] = {}

    # ------------------------------------------------------------------ transport
    def _next_nonce(self) -> str:
        with self._lock:
            self._nonce = max(self._nonce + 1, time.time_ns() // 1000)
            return str(self._nonce)

    def _public(self, method: str, params: dict) -> dict:
        url = f"{API}/0/public/{method}?" + urllib.parse.urlencode(params)
        status, body = self.http("GET", url, {"User-Agent": "mab"}, None)
        d = self._json(status, body, f"Kraken {method}")
        if d.get("error"):
            raise BrokerError(f"Kraken {method}: {', '.join(d['error'])}")
        return d["result"]

    def _private(self, method: str, params: dict) -> dict:
        path = f"/0/private/{method}"
        nonce = self._next_nonce()
        body = urllib.parse.urlencode({"nonce": nonce, **params})
        headers = {"API-Key": self.key, "API-Sign": sign(path, nonce, body, self.secret),
                   "Content-Type": "application/x-www-form-urlencoded; charset=utf-8", "User-Agent": "mab"}
        status, raw = self.http("POST", API + path, headers, body.encode())
        d = self._json(status, raw, f"Kraken {method}")
        if d.get("error"):
            raise BrokerError(f"Kraken {method}: {', '.join(d['error'])}")
        return d["result"]

    # ------------------------------------------------------------------ markets
    def pair_name(self, instrument: str) -> str:
        inst = instrument.upper()
        if inst.startswith("X") and inst.endswith(("ZUSD", "ZCAD", "ZEUR")) and len(inst) == 8:
            base = inst[1:4]
        else:
            base = inst.split("-")[0].split("/")[0]
        return BASES.get(base, base) + ("USD" if self.quote == "USD" else self.quote)

    def market(self, instrument: str) -> dict:
        alt = self.pair_name(instrument)
        if alt not in self._pairs:
            res = self._public("AssetPairs", {"pair": alt})
            code, p = next(iter(res.items()))
            self._pairs[alt] = {"symbol": code, "altname": p.get("altname", alt), "min_qty": float(p.get("ordermin") or 0),
                                "qty_step": 10 ** -int(p.get("lot_decimals", 8)),
                                "price_step": float(p.get("tick_size") or 10 ** -int(p.get("pair_decimals", 1))),
                                "min_notional": float(p.get("costmin") or 0), "base": p.get("base"), "quote": p.get("quote")}
        return self._pairs[alt]

    def _price(self, x: float, instrument: str) -> str:
        step = self.market(instrument)["price_step"]
        decimals = max(0, len(f"{step:.10f}".rstrip("0").split(".")[1])) if step < 1 else 0
        return f"{round(round(x / step) * step, decimals):.{decimals}f}"

    # ------------------------------------------------------------------ orders
    def _add(self, instrument, side, kind, qty, price, client_id, ioc=False) -> Order:
        m = self.market(instrument)
        q = round_step(qty, m["qty_step"])
        if q < m["min_qty"]:
            return Order("", client_id, instrument, side, kind, qty, "rejected",
                         reason=f"size {q} is below Kraken's minimum {m['min_qty']} for {m['altname']}")
        params = {"pair": m["altname"], "type": side, "ordertype": {"limit": "limit", "market": "market", "stop": "stop-loss"}[kind],
                  "volume": f"{q:.8f}".rstrip("0").rstrip("."), "userref": userref(client_id), "oflags": "fciq"}
        if price is not None:
            params["price"] = self._price(price, instrument)
        if ioc:
            params["timeinforce"] = "IOC"
        res = self._private("AddOrder", params)
        txid = (res.get("txid") or [""])[0]
        return Order(txid, client_id, instrument, side, kind, q, "open", raw=res)

    def buy(self, instrument, qty, limit_price, client_id):
        return self._add(instrument, "buy", "limit", qty, limit_price, client_id, ioc=True)

    def sell(self, instrument, qty, limit_price, client_id):
        if limit_price is None:
            return self._add(instrument, "sell", "market", qty, None, client_id)
        return self._add(instrument, "sell", "limit", qty, limit_price, client_id, ioc=True)

    def stop(self, instrument, qty, stop_price, client_id):
        return self._add(instrument, "sell", "stop", qty, stop_price, client_id)

    def cancel(self, order_id):
        self._private("CancelOrder", {"txid": order_id})

    def order(self, order_id=None, client_id=None) -> Optional[Order]:
        if order_id:
            res = self._private("QueryOrders", {"txid": order_id, "trades": "true"})
        elif client_id:
            ref = userref(client_id)
            res = dict(self._private("OpenOrders", {"userref": ref}).get("open", {}))
            res.update(self._private("ClosedOrders", {"userref": ref}).get("closed", {}))
        else:
            raise BrokerError("order(): give an order id or a client id")
        if not res:
            return None
        txid, o = next(iter(res.items()))
        d = o.get("descr", {})
        filled = float(o.get("vol_exec") or 0)
        cost = float(o.get("cost") or 0)
        status = STATUS.get(o.get("status"), "unknown")
        if status == "canceled" and filled > 0:
            status = "partially_filled"
        return Order(txid, client_id or "", d.get("pair", ""), d.get("type", ""), d.get("ordertype", ""),
                     float(o.get("vol") or 0), status, filled, (cost / filled) if filled else None,
                     float(o.get("fee") or 0), o.get("reason") or "", raw=o)

    def balances(self) -> Dict[str, float]:
        return {k: float(v) for k, v in self._private("Balance", {}).items()}

    def test(self) -> dict:
        bal = self.balances()
        quote_code = {"USD": "ZUSD", "CAD": "ZCAD", "EUR": "ZEUR"}.get(self.quote, self.quote)
        return {"ok": True, "broker": "Kraken", "quote": self.quote, "cash": bal.get(quote_code, 0.0),
                "balances": {k: v for k, v in bal.items() if v}, "can_trade": True,
                "notes": ["Kraken does not report key permissions over the API; a key without order permission "
                          "fails on the first order and live trading stops with an alert."]}
