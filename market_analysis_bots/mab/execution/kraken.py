"""Kraken spot (Kraken Pro) for live trading. Kraken has no spot sandbox, so this connection is live only.

Facts this adapter relies on (docs.kraken.com, checked Sept 2026):
* private REST calls are signed: API-Sign = base64(HMAC-SHA512(path + SHA256(nonce + body), base64-decoded
  secret)) (tested against Kraken's published example in tests/test_live.py);
* AddOrder takes ordertype market, limit, stop-loss, stop-loss-limit ...; timeinforce GTC, IOC, GTD, FOK;
  oflags fciq (fee in quote currency, so the coins bought are exactly the coins the stop must sell);
  cl_ord_id (a UUID, or up to 18 characters) identifies an order for later look-up; validate=true checks an
  order without sending it to the matching engine (used by the readiness check);
* OpenOrders and ClosedOrders filter by cl_ord_id; BalanceEx reports balance and hold_trade per asset;
* Kraken reports no key permissions over the API: a key without trading permission fails at the first order.
Create the key WITHOUT withdrawal permission.
"""

from __future__ import annotations

import threading
import time
import urllib.parse
from typing import Dict, List, Optional

from mab.brokers.kraken import BASES, sign
from mab.execution.base import (ACKED, CANCELED, EXPIRED, FILLED, PARTIALLY_FILLED, AuthError, NotSent, OrderRejected,
                                OrderRequest, OrderStatus, OutcomeUnknown, Provider, ProviderError, http_transport,
                                json_body, uuid_for)

API = "https://api.kraken.com"
SITE = "https://pro.kraken.com/"
STATUS = {"pending": ACKED, "open": ACKED, "closed": FILLED, "canceled": CANCELED, "expired": EXPIRED}
QUOTE_CODES = {"USD": "ZUSD", "CAD": "ZCAD", "EUR": "ZEUR"}
ASSET_CODES = {"BTC": ["XXBT", "XBT"], "ETH": ["XETH", "ETH"], "DOGE": ["XXDG", "XDG"], "LTC": ["XLTC", "LTC"],
               "XRP": ["XXRP", "XRP"]}


class Kraken(Provider):
    name = "kraken"
    label = "Kraken Pro"
    environment = "live"
    real_money = True
    rate = (15, 30.0)

    def __init__(self, key: str, secret: str, quote: str = "CAD", transport=None, **_):
        if not key or not secret:
            raise AuthError("Kraken needs an API key and secret")
        self._key, self._secret = key, secret
        self.quote = quote.upper()
        self.http = transport or http_transport()
        self._nonce = 0
        self._lock = threading.Lock()
        self._pairs: Dict[str, dict] = {}

    # ------------------------------------------------------------------ transport
    def _nonce_next(self) -> str:
        with self._lock:
            self._nonce = max(self._nonce + 1, time.time_ns() // 1000)
            return str(self._nonce)

    @staticmethod
    def _check(d: dict, where: str, order_send: bool = False):
        errs = d.get("error") or []
        if not errs:
            return
        text = ", ".join(errs)
        if any(e.startswith(("EAPI:Invalid key", "EAPI:Invalid signature", "EGeneral:Permission denied", "EAPI:Invalid nonce"))
               for e in errs):
            raise AuthError(f"{where}: {text}")
        if any("Rate limit" in e or "Too many requests" in e for e in errs):
            raise NotSent(f"{where}: rate limited by Kraken ({text})")
        if order_send and any(e.startswith(("EService:", "EGeneral:Internal")) for e in errs):
            raise OutcomeUnknown(f"{where}: {text}; the order may or may not exist")
        if order_send:
            raise OrderRejected(f"{where}: {text}")
        raise ProviderError(f"{where}: {text}")

    def _public(self, method: str, params: dict) -> dict:
        status, raw, _ = self.http("GET", f"{API}/0/public/{method}?" + urllib.parse.urlencode(params), {"User-Agent": "jarvus"}, None)
        d = json_body(status, raw, f"Kraken {method}")
        self._check(d, f"Kraken {method}")
        return d.get("result") or {}

    def _private(self, method: str, params: dict, order_send: bool = False) -> dict:
        path = f"/0/private/{method}"
        nonce = self._nonce_next()
        body = urllib.parse.urlencode({"nonce": nonce, **params})
        headers = {"API-Key": self._key, "API-Sign": sign(path, nonce, body, self._secret),
                   "Content-Type": "application/x-www-form-urlencoded; charset=utf-8", "User-Agent": "jarvus"}
        status, raw, _ = self.http("POST", API + path, headers, body.encode())
        if status >= 500 and order_send:
            raise OutcomeUnknown(f"Kraken {method}: HTTP {status}; the order may or may not exist")
        d = json_body(status, raw, f"Kraken {method}")
        self._check(d, f"Kraken {method}", order_send)
        return d.get("result") or {}

    # ------------------------------------------------------------------ markets
    def _base(self, symbol: str) -> str:
        s = symbol.split(":", 1)[-1].upper()
        if len(s) == 8 and s.startswith("X") and s[4] == "Z":
            b = s[1:4]
        else:
            b = s.replace("/", "-").split("-")[0]
        return {"XBT": "BTC", "XDG": "DOGE"}.get(b, b)

    def instrument(self, symbol: str) -> dict:
        base = self._base(symbol)
        alt = BASES.get(base, base) + self.quote
        if alt not in self._pairs:
            res = self._public("AssetPairs", {"pair": alt})
            if not res:
                raise ProviderError(f"Kraken does not list {alt}")
            code, p = next(iter(res.items()))
            self._pairs[alt] = {"symbol": symbol, "broker_symbol": p.get("altname", alt), "code": code, "tradable": True,
                                "min_qty": float(p.get("ordermin") or 0), "qty_step": 10 ** -int(p.get("lot_decimals", 8)),
                                "price_step": float(p.get("tick_size") or 10 ** -int(p.get("pair_decimals", 1))),
                                "min_notional": float(p.get("costmin") or 0), "asset_class": "crypto", "base": p.get("base"),
                                "quote": p.get("quote"), "fractionable": True, "shortable": False,
                                "status": p.get("status", "online")}
            self._pairs[alt]["tradable"] = self._pairs[alt]["status"] in ("online", None)
        return self._pairs[alt]

    def quote(self, symbol: str) -> dict:
        m = self.instrument(symbol)
        t = next(iter(self._public("Ticker", {"pair": m["broker_symbol"]}).values()))
        return {"bid": float(t["b"][0]), "ask": float(t["a"][0]), "last": float(t["c"][0]), "time": None,
                "source": "Kraken ticker"}

    def _px(self, x: float, m: dict) -> str:
        step = m["price_step"]
        dec = max(0, len(f"{step:.10f}".rstrip("0").split(".")[1])) if step < 1 else 0
        return f"{round(round(x / step) * step, dec):.{dec}f}"

    # ------------------------------------------------------------------ interface
    def capabilities(self) -> dict:
        return {"asset_classes": ["crypto"], "order_types": ["market", "limit", "stop", "stop_limit"],
                "tif": {"crypto": ["gtc", "ioc", "gtd", "fok"]}, "fractional": True, "short": False,
                "protective_stop": "stop", "auth": ["api_key"], "paper": False, "live": True,
                "market_data": "Kraken public REST", "rate_limit": {"requests": 15, "per_seconds": 30},
                "validate_only": True, "withdrawals": "never requested (create the key without withdraw permission)",
                "notes": ["Kraken has no spot sandbox: this connection is live only",
                          "key permissions are not reported by the API; a key without trading permission fails at the first order"]}

    def authenticate(self) -> dict:
        bal = self._private("Balance", {})
        return {"ok": True, "account_id": "Kraken account (key ..." + self._key[-4:] + ")", "status": "ACTIVE",
                "currency": self.quote, "environment": "live",
                "permissions": {"query_funds": True, "trade": None, "withdraw": False},
                "notes": ["Kraken does not report key permissions; trading permission is confirmed by the readiness "
                          "check's validate-only order"], "assets": len([v for v in bal.values() if float(v)])}

    def _balances(self) -> Dict[str, dict]:
        try:
            ex = self._private("BalanceEx", {})
            return {k: {"balance": float(v.get("balance") or 0), "hold": float(v.get("hold_trade") or 0)} for k, v in ex.items()}
        except ProviderError:
            return {k: {"balance": float(v), "hold": 0.0} for k, v in self._private("Balance", {}).items()}

    def account(self) -> dict:
        bal = self._balances()
        qc = QUOTE_CODES.get(self.quote, self.quote)
        cash = bal.get(qc, {"balance": 0.0, "hold": 0.0})
        equity = None
        try:
            tb = self._private("TradeBalance", {"asset": qc})
            equity = float(tb.get("eb") or 0) or None
        except ProviderError:
            pass
        return {"equity": equity, "cash": cash["balance"], "buying_power": cash["balance"] - cash["hold"],
                "currency": self.quote, "status": "ACTIVE", "can_trade": True, "simulated": False}

    def positions(self) -> List[dict]:
        qc = QUOTE_CODES.get(self.quote, self.quote)
        out = []
        for k, v in self._balances().items():
            if k in (qc, self.quote) or k.startswith("Z") or v["balance"] <= 0:
                continue
            out.append({"symbol": k, "qty": v["balance"], "qty_available": v["balance"] - v["hold"]})
        return out

    def sellable(self, symbol: str) -> Optional[float]:
        base = self._base(symbol)
        names = [n.upper() for n in ASSET_CODES.get(base, [base, "X" + base])]
        for p in self.positions():
            if p["symbol"].upper() in names:
                return p["qty_available"]
        return 0.0

    def order_params(self, req: OrderRequest) -> dict:
        m = self.instrument(req.symbol)
        kind = {"limit": "limit", "market": "market", "stop": "stop-loss", "stop_limit": "stop-loss-limit"}.get(req.order_type)
        if kind is None:
            raise OrderRejected(f"order type {req.order_type} is not supported here")
        params = {"pair": m["broker_symbol"], "type": req.side, "ordertype": kind,
                  "volume": f"{req.qty:.8f}".rstrip("0").rstrip("."), "cl_ord_id": uuid_for(req.client_order_id),
                  "oflags": "fciq"}
        if kind == "limit":
            params["price"] = self._px(req.limit_price, m)
        elif kind in ("stop-loss", "stop-loss-limit"):
            params["price"] = self._px(req.stop_price, m)
            if kind == "stop-loss-limit":
                params["price2"] = self._px(req.limit_price, m)
        if req.tif == "ioc" and kind == "limit":
            params["timeinforce"] = "IOC"
        return params

    def validate(self, req: OrderRequest) -> dict:
        """Kraken's validate-only order: checks key permission, pair, size and price without trading."""
        res = self._private("AddOrder", dict(self.order_params(req), validate="true"), order_send=True)
        return {"ok": True, "descr": (res.get("descr") or {}).get("order")}

    def submit(self, req: OrderRequest) -> OrderStatus:
        m = self.instrument(req.symbol)
        if req.qty < m["min_qty"]:
            raise OrderRejected(f"size {req.qty} is below Kraken's minimum {m['min_qty']} for {m['broker_symbol']}")
        res = self._private("AddOrder", self.order_params(req), order_send=True)
        txid = (res.get("txid") or [""])[0]
        if not txid:
            raise OutcomeUnknown("Kraken accepted the request but returned no order id")
        got = None
        try:
            got = self.get_order(broker_order_id=txid)
        except ProviderError:
            pass
        return got or OrderStatus(txid, req.client_order_id, m["broker_symbol"], req.side, req.order_type, req.qty, ACKED)

    def _parse(self, txid: str, o: dict, cid: str = "") -> OrderStatus:
        d = o.get("descr", {})
        filled = float(o.get("vol_exec") or 0)
        cost = float(o.get("cost") or 0)
        state = STATUS.get(o.get("status"), ACKED)
        if state == ACKED and filled > 0:
            state = PARTIALLY_FILLED
        return OrderStatus(txid, cid or o.get("cl_ord_id") or "", d.get("pair", ""), d.get("type", ""), d.get("ordertype", ""),
                           float(o.get("vol") or 0), state, filled, (cost / filled) if filled else None,
                           float(o.get("fee") or 0), self.quote, o.get("reason") or "", int(time.time() * 1000),
                           "taker", False, "", raw={k: o.get(k) for k in ("status", "vol", "vol_exec", "cost", "fee",
                                                                         "price", "opentm", "closetm", "reason")})

    def get_order(self, broker_order_id=None, client_order_id=None) -> Optional[OrderStatus]:
        if broker_order_id:
            res = self._private("QueryOrders", {"txid": broker_order_id, "trades": "true"})
        elif client_order_id:
            ref = uuid_for(client_order_id)
            res = dict(self._private("OpenOrders", {"cl_ord_id": ref}).get("open", {}))
            res.update(self._private("ClosedOrders", {"cl_ord_id": ref}).get("closed", {}))
        else:
            raise ProviderError("get_order needs an order id or a client order id")
        if not res:
            return None
        txid, o = next(iter(res.items()))
        return self._parse(txid, o, client_order_id or "")

    def cancel(self, broker_order_id: str) -> None:
        try:
            self._private("CancelOrder", {"txid": broker_order_id})
        except OrderRejected:
            return None
        except ProviderError as e:
            if "Unknown order" in str(e):
                return None
            raise

    def open_orders(self) -> List[OrderStatus]:
        return [self._parse(k, v) for k, v in (self._private("OpenOrders", {}).get("open") or {}).items()]

    def server_time(self) -> Optional[int]:
        t = self._public("Time", {})
        return int(t["unixtime"]) * 1000 if t.get("unixtime") else None

    def funding(self) -> dict:
        return {"url": SITE, "label": "Add funds on Kraken", "simulated": False,
                "note": "deposits are made in your Kraken account (Funding / Deposit). Jarvus never moves money and "
                        "never needs withdrawal permission; balances here update after Kraken reports them."}
