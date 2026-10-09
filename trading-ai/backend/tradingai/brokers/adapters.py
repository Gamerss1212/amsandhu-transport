"""Real broker and exchange adapters (sections 179-182, 261, 284, 321-322). Every one is UNVERIFIED until its
acceptance test passes with the owner's own credentials against the provider's paper/demo (or live) environment.

  Alpaca        US stocks/ETFs and crypto; paper and live; REST v2 with key id + secret headers
  OANDA         forex (OTC); practice and live; REST v20 with a bearer token + account id
  Kraken        crypto spot; live only (Kraken has no spot sandbox); REST with HMAC-SHA512 request signing
  IBKR          stocks, ETFs, futures, FX through the Client Portal Gateway the OWNER runs on this computer
  Coinbase      Advanced Trade requires ES256 (elliptic-curve) signed JWTs; the signing library is not bundled,
                so this adapter is REQUIRES CONNECTION and makes no calls

No adapter has a withdrawal or transfer method, and none ever asks for withdrawal permission. Eligibility comes from
the broker: an order for a product the account is not permitted to trade is refused before it is sent.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import time
import urllib.parse
from decimal import Decimal
from typing import Optional

import httpx

from tradingai.brokers.base import (AccountInfo, BrokerAdapter, BrokerError, BrokerFill, BrokerOrder,
                                    RequiresConnection)

D = Decimal


def _mask(s: Optional[str]) -> str:
    s = str(s or "")
    return "****" + s[-4:] if len(s) > 4 else "****"


class _Http(BrokerAdapter):
    base_urls: dict[str, str] = {}
    timeout = 15.0

    def __init__(self, environment: str = "paper", credentials: Optional[dict] = None):
        super().__init__(environment, credentials)
        missing = [k for k in self.needs if not (credentials or {}).get(k)]
        if missing:
            self.last_error = "REQUIRES CONNECTION: missing " + ", ".join(missing)
        self.client = httpx.Client(timeout=self.timeout)

    @property
    def base(self) -> str:
        return self.base_urls[self.environment]

    def _check_creds(self) -> None:
        missing = [k for k in self.needs if not self.credentials.get(k)]
        if missing:
            raise RequiresConnection(f"{self.label}: add {', '.join(missing)} on the Brokers & Accounts page")

    def _req(self, method: str, path: str, **kw) -> dict | list:
        self._check_creds()
        try:
            r = self.client.request(method, self.base + path, headers=self._headers(method, path, kw), **kw)
        except httpx.HTTPError as e:
            self.last_error = f"{type(e).__name__}"
            raise BrokerError(f"{self.label}: network error ({type(e).__name__})") from None
        if r.status_code in (401, 403):
            self.last_error = f"HTTP {r.status_code}: credentials refused"
            raise BrokerError(f"{self.label}: the broker refused the credentials (HTTP {r.status_code})")
        if r.status_code >= 400:
            self.last_error = f"HTTP {r.status_code}"
            raise BrokerError(f"{self.label}: HTTP {r.status_code}: {r.text[:200]}")
        return r.json() if r.content else {}

    def _headers(self, method: str, path: str, kw: dict) -> dict:
        return {}

    def connect(self) -> dict:
        acct = self.get_balance()
        self.connected, self.last_error = True, None
        return {"connected": True, "account": acct.account_id_masked, "environment": self.environment}

    def health(self) -> dict:
        t0 = time.perf_counter()
        try:
            self.get_balance()
            return {"ok": True, "latency_ms": round((time.perf_counter() - t0) * 1000, 1)}
        except BrokerError as e:
            return {"ok": False, "error": str(e)}


class Alpaca(_Http):
    name, label = "alpaca", "Alpaca (US stocks, ETFs, crypto)"
    environments = ("paper", "live")
    needs = ("key_id", "secret")
    setup = ("Create API keys in the Alpaca dashboard (paper keys for paper). Trading permission only; Alpaca keys "
             "cannot withdraw funds.")
    base_urls = {"paper": "https://paper-api.alpaca.markets/v2", "live": "https://api.alpaca.markets/v2"}

    def _headers(self, method, path, kw):
        return {"APCA-API-KEY-ID": self.credentials["key_id"], "APCA-API-SECRET-KEY": self.credentials["secret"]}

    def capabilities(self) -> dict:
        return {"stocks": True, "etfs": True, "crypto": True, "forex": False, "futures": False, "paper_mode": True,
                "fractional": "per asset (reported by /assets)", "shorting": "per account and asset",
                "bracket_orders": True, "trailing_stops": True, "websocket": True, "historical_data": True,
                "realtime_data": "depends on the data plan", "level2": False, "order_modification": True}

    def get_balance(self) -> AccountInfo:
        a = self._req("GET", "/account")
        return AccountInfo(_mask(a.get("account_number")), self.environment, a.get("currency", "USD"),
                           D(a["equity"]), D(a["cash"]), D(a["buying_power"]), None, False, "LIVE BROKER DATA"
                           if self.environment == "live" else "BROKER PAPER ACCOUNT", int(time.time() * 1000),
                           {"trading_blocked": a.get("trading_blocked"), "shorting_enabled": a.get("shorting_enabled"),
                            "crypto_status": a.get("crypto_status"), "pattern_day_trader": a.get("pattern_day_trader"),
                            "status": a.get("status")})

    def get_accounts(self) -> list[AccountInfo]:
        return [self.get_balance()]

    def get_positions(self) -> dict:
        return {f"US:{p['symbol']}": D(p["qty"]) for p in self._req("GET", "/positions")}

    def get_open_orders(self) -> list[BrokerOrder]:
        return [self._o(o) for o in self._req("GET", "/orders", params={"status": "open", "limit": 500})]

    def get_order(self, client_order_id: str) -> Optional[BrokerOrder]:
        try:
            return self._o(self._req("GET", "/orders:by_client_order_id", params={"client_order_id": client_order_id}))
        except BrokerError as e:
            if "404" in str(e):
                return None
            raise

    def get_fills(self, since_ms: int = 0) -> list[BrokerFill]:
        rows = self._req("GET", "/account/activities/FILL", params={"page_size": 100})
        return [BrokerFill(r["id"], r.get("order_id", ""), f"US:{r['symbol']}", r["side"], D(r["qty"]), D(r["price"]),
                           D(0), "USD", 0) for r in rows]

    def asset_permission(self, symbol: str) -> tuple[bool, str]:
        a = self._req("GET", f"/assets/{urllib.parse.quote(symbol)}")
        ok = bool(a.get("tradable")) and a.get("status") == "active"
        return ok, ("tradable" if ok else f"not tradable for this account ({a.get('status')})")

    def submit_order(self, *, client_order_id, instrument_id, broker_symbol, side, qty, order_type="market",
                     limit_price=None, tif="day") -> BrokerOrder:
        existing = self.get_order(client_order_id)
        if existing is not None:
            return existing
        body = {"symbol": broker_symbol, "qty": str(qty), "side": side, "type": order_type, "time_in_force": tif,
                "client_order_id": client_order_id}
        if limit_price is not None:
            body["limit_price"] = str(limit_price)
        return self._o(self._req("POST", "/orders", json=body))

    def cancel_order(self, client_order_id: str) -> bool:
        o = self.get_order(client_order_id)
        if o is None or not o.broker_order_id:
            return False
        self._req("DELETE", f"/orders/{o.broker_order_id}")
        return True

    @staticmethod
    def _o(o: dict) -> BrokerOrder:
        return BrokerOrder(o.get("client_order_id", ""), o.get("id"), f"US:{o.get('symbol')}", o.get("side", ""),
                           D(o.get("qty") or 0), D(o.get("filled_qty") or 0),
                           D(o["filled_avg_price"]) if o.get("filled_avg_price") else None,
                           str(o.get("status", "")).upper(), o.get("type", "market"),
                           D(o["limit_price"]) if o.get("limit_price") else None)


class Oanda(_Http):
    name, label = "oanda", "OANDA (forex)"
    environments = ("paper", "live")
    needs = ("token", "account_id")
    setup = "Create a personal access token in OANDA (practice account for paper) and copy your v20 account id."
    base_urls = {"paper": "https://api-fxpractice.oanda.com/v3", "live": "https://api-fxtrade.oanda.com/v3"}

    def _headers(self, method, path, kw):
        return {"Authorization": f"Bearer {self.credentials['token']}", "Content-Type": "application/json"}

    @property
    def acct(self) -> str:
        return f"/accounts/{self.credentials['account_id']}"

    def capabilities(self) -> dict:
        return {"stocks": False, "etfs": False, "crypto": False, "forex": True, "futures": False, "paper_mode": True,
                "fractional": False, "shorting": True, "bracket_orders": True, "trailing_stops": True,
                "websocket": "streaming endpoint", "historical_data": True, "realtime_data": True, "level2": False,
                "order_modification": True}

    def get_balance(self) -> AccountInfo:
        a = self._req("GET", f"{self.acct}/summary")["account"]
        return AccountInfo(_mask(a.get("id")), self.environment, a.get("currency", "USD"), D(a["NAV"]),
                           D(a["balance"]), D(a["marginAvailable"]), D(a["marginUsed"]), False,
                           "LIVE BROKER DATA" if self.environment == "live" else "BROKER PRACTICE ACCOUNT",
                           int(time.time() * 1000), {"hedging_enabled": a.get("hedgingEnabled")})

    def get_accounts(self) -> list[AccountInfo]:
        return [self.get_balance()]

    def get_positions(self) -> dict:
        out = {}
        for p in self._req("GET", f"{self.acct}/openPositions").get("positions", []):
            units = D(p["long"]["units"]) + D(p["short"]["units"])
            out[f"FX:{p['instrument'].replace('_', '')}"] = units
        return out

    def get_open_orders(self) -> list[BrokerOrder]:
        return [BrokerOrder((o.get("clientExtensions") or {}).get("id", ""), o["id"],
                            f"FX:{o.get('instrument', '').replace('_', '')}", "buy" if D(o.get("units", "0")) > 0 else
                            "sell", abs(D(o.get("units", "0"))), D(0), None, o.get("state", ""), o.get("type", ""))
                for o in self._req("GET", f"{self.acct}/pendingOrders").get("orders", [])]

    def get_order(self, client_order_id: str) -> Optional[BrokerOrder]:
        try:
            o = self._req("GET", f"{self.acct}/orders/@{client_order_id}")["order"]
        except BrokerError as e:
            if "404" in str(e):
                return None
            raise
        return BrokerOrder(client_order_id, o["id"], f"FX:{o.get('instrument', '').replace('_', '')}",
                           "buy" if D(o.get("units", "0")) > 0 else "sell", abs(D(o.get("units", "0"))), D(0), None,
                           o.get("state", ""), o.get("type", ""))

    def get_fills(self, since_ms: int = 0) -> list[BrokerFill]:
        return []

    def submit_order(self, *, client_order_id, instrument_id, broker_symbol, side, qty, order_type="market",
                     limit_price=None, tif="FOK") -> BrokerOrder:
        existing = self.get_order(client_order_id)
        if existing is not None:
            return existing
        units = str(qty if side == "buy" else -qty)
        order = {"type": "MARKET" if order_type == "market" else "LIMIT", "instrument": broker_symbol, "units": units,
                 "clientExtensions": {"id": client_order_id}, "timeInForce": "FOK" if order_type == "market" else "GTC"}
        if limit_price is not None:
            order["price"] = str(limit_price)
        self._req("POST", f"{self.acct}/orders", json={"order": order})
        return self.get_order(client_order_id) or BrokerOrder(client_order_id, None, instrument_id, side, qty, D(0),
                                                              None, "SUBMITTED")

    def cancel_order(self, client_order_id: str) -> bool:
        self._req("PUT", f"{self.acct}/orders/@{client_order_id}/cancel")
        return True


class Kraken(_Http):
    name, label = "kraken", "Kraken Pro (crypto spot)"
    environments = ("live",)
    needs = ("key", "secret")
    setup = ("Create an API key with Query Funds, Query Open/Closed Orders & Trades, Create & Modify Orders and Cancel "
             "Orders only. Leave Withdraw Funds OFF. Kraken has no spot sandbox: this adapter is live only.")
    base_urls = {"live": "https://api.kraken.com"}

    def capabilities(self) -> dict:
        return {"stocks": False, "etfs": False, "crypto": True, "forex": False, "futures": False, "paper_mode": False,
                "fractional": True, "shorting": False, "bracket_orders": False, "trailing_stops": True,
                "websocket": True, "historical_data": True, "realtime_data": True, "level2": True,
                "order_modification": True}

    @staticmethod
    def sign(path: str, data: dict, secret_b64: str) -> str:
        post = urllib.parse.urlencode(data)
        digest = hashlib.sha256((str(data["nonce"]) + post).encode()).digest()
        mac = hmac.new(base64.b64decode(secret_b64), path.encode() + digest, hashlib.sha512)
        return base64.b64encode(mac.digest()).decode()

    def _private(self, method: str, data: Optional[dict] = None) -> dict:
        self._check_creds()
        path = f"/0/private/{method}"
        data = dict(data or {}, nonce=int(time.time() * 1000))
        headers = {"API-Key": self.credentials["key"], "API-Sign": self.sign(path, data, self.credentials["secret"])}
        try:
            r = self.client.post(self.base + path, data=data, headers=headers)
        except httpx.HTTPError as e:
            raise BrokerError(f"Kraken: network error ({type(e).__name__})") from None
        d = r.json()
        if d.get("error"):
            self.last_error = ", ".join(d["error"])
            raise BrokerError(f"Kraken: {', '.join(d['error'])}")
        return d["result"]

    def get_balance(self) -> AccountInfo:
        b = self._private("Balance")
        usd = D(b.get("ZUSD", b.get("USD", "0")))
        return AccountInfo("Kraken ****", "live", "USD", None, usd, usd, None, False, "LIVE BROKER DATA",
                           int(time.time() * 1000), {"assets": {k: v for k, v in b.items() if D(v) != 0}})

    def get_accounts(self) -> list[AccountInfo]:
        return [self.get_balance()]

    def get_positions(self) -> dict:
        return {f"KRAKEN:{k}": D(v) for k, v in self._private("Balance").items() if D(v) != 0}

    def get_open_orders(self) -> list[BrokerOrder]:
        res = self._private("OpenOrders").get("open", {})
        return [BrokerOrder(str(o.get("cl_ord_id") or o.get("userref") or ""), txid, f"KRAKEN:{o['descr']['pair']}",
                            o["descr"]["type"], D(o["vol"]), D(o["vol_exec"]), None, "SUBMITTED",
                            o["descr"]["ordertype"]) for txid, o in res.items()]

    def get_order(self, client_order_id: str) -> Optional[BrokerOrder]:
        for o in self.get_open_orders():
            if o.client_order_id == client_order_id:
                return o
        return None

    def get_fills(self, since_ms: int = 0) -> list[BrokerFill]:
        res = self._private("TradesHistory", {"start": since_ms // 1000}).get("trades", {})
        return [BrokerFill(k, t.get("ordertxid", ""), f"KRAKEN:{t['pair']}", t["type"], D(t["vol"]), D(t["price"]),
                           D(t["fee"]), "USD", int(float(t["time"]) * 1000)) for k, t in res.items()]

    def submit_order(self, *, client_order_id, instrument_id, broker_symbol, side, qty, order_type="market",
                     limit_price=None, tif="GTC") -> BrokerOrder:
        if self.get_order(client_order_id):
            return self.get_order(client_order_id)
        data = {"pair": broker_symbol, "type": side, "ordertype": order_type, "volume": str(qty),
                "cl_ord_id": client_order_id}
        if limit_price is not None:
            data["price"] = str(limit_price)
        r = self._private("AddOrder", data)
        return BrokerOrder(client_order_id, (r.get("txid") or [None])[0], instrument_id, side, qty, D(0), None,
                           "SUBMITTED", order_type, limit_price)

    def cancel_order(self, client_order_id: str) -> bool:
        self._private("CancelOrder", {"cl_ord_id": client_order_id})
        return True


class IBKR(_Http):
    name, label = "ibkr", "Interactive Brokers (Client Portal Gateway)"
    environments = ("paper", "live")
    needs = ("account_id",)
    setup = ("Download and start IBKR's Client Portal Gateway on this computer, sign in to it in your browser "
             "(https://localhost:5000), then enter your account id here. Paper or live follows the account you sign "
             "in with.")
    base_urls = {"paper": "https://localhost:5000/v1/api", "live": "https://localhost:5000/v1/api"}

    def __init__(self, environment: str = "paper", credentials: Optional[dict] = None):
        super().__init__(environment, credentials)
        # the gateway runs on this computer with a self-signed certificate; only localhost is ever contacted
        self.client = httpx.Client(timeout=self.timeout, verify=False)

    def capabilities(self) -> dict:
        return {"stocks": True, "etfs": True, "crypto": "region dependent", "forex": True, "futures": True,
                "paper_mode": True, "fractional": "region dependent", "shorting": True, "bracket_orders": True,
                "trailing_stops": True, "websocket": True, "historical_data": True,
                "realtime_data": "market data subscriptions", "level2": "subscriptions", "order_modification": True}

    def get_balance(self) -> AccountInfo:
        st = self._req("GET", "/iserver/auth/status")
        if not st.get("authenticated"):
            raise RequiresConnection("IBKR: sign in to the Client Portal Gateway in your browser first")
        s = self._req("GET", f"/portfolio/{self.credentials['account_id']}/summary")
        val = lambda k: D(str((s.get(k) or {}).get("amount", 0)))      # noqa: E731
        return AccountInfo(_mask(self.credentials["account_id"]), self.environment,
                           (s.get("netliquidation") or {}).get("currency", "USD"), val("netliquidation"),
                           val("totalcashvalue"), val("buyingpower"), val("maintmarginreq"), False,
                           "LIVE BROKER DATA" if self.environment == "live" else "BROKER PAPER ACCOUNT",
                           int(time.time() * 1000))

    def get_accounts(self) -> list[AccountInfo]:
        return [self.get_balance()]

    def get_positions(self) -> dict:
        rows = self._req("GET", f"/portfolio/{self.credentials['account_id']}/positions/0")
        return {f"IBKR:{p.get('contractDesc')}": D(str(p.get("position", 0))) for p in rows}

    def get_open_orders(self) -> list[BrokerOrder]:
        rows = self._req("GET", "/iserver/account/orders").get("orders", [])
        return [BrokerOrder(o.get("order_ref", ""), str(o.get("orderId")), f"IBKR:{o.get('ticker')}",
                            o.get("side", "").lower(), D(str(o.get("totalSize", 0))), D(str(o.get("filledQuantity", 0))),
                            None, str(o.get("status", "")).upper()) for o in rows]

    def get_order(self, client_order_id: str) -> Optional[BrokerOrder]:
        return next((o for o in self.get_open_orders() if o.client_order_id == client_order_id), None)

    def get_fills(self, since_ms: int = 0) -> list[BrokerFill]:
        return []

    def submit_order(self, *, client_order_id, instrument_id, broker_symbol, side, qty, order_type="market",
                     limit_price=None, tif="DAY") -> BrokerOrder:
        raise RequiresConnection("IBKR: orders need the contract id (conid) resolved through the gateway's contract "
                                 "search and confirmed by you; connect the gateway and verify the contract first")

    def cancel_order(self, client_order_id: str) -> bool:
        o = self.get_order(client_order_id)
        if not o:
            return False
        self._req("DELETE", f"/iserver/account/{self.credentials['account_id']}/order/{o.broker_order_id}")
        return True


class Coinbase(BrokerAdapter):
    name, label = "coinbase", "Coinbase Advanced Trade"
    environments = ("live",)
    needs = ("key_name", "private_key")
    setup = ("Coinbase Advanced Trade signs every request with an ES256 JWT made from an elliptic-curve private key. "
             "The cryptography library that does this is not bundled with this build, so this connection is "
             "REQUIRES CONNECTION and sends nothing.")

    def capabilities(self) -> dict:
        return {"crypto": True, "paper_mode": False}

    def _no(self, *a, **k):
        raise RequiresConnection(self.setup)

    connect = health = get_accounts = get_balance = get_positions = get_open_orders = get_fills = _no
    submit_order = cancel_order = get_order = _no

    def status(self) -> str:
        return "requires connection"


ADAPTERS = {"alpaca": Alpaca, "oanda": Oanda, "kraken": Kraken, "ibkr": IBKR, "coinbase": Coinbase}


def matrix() -> list[dict]:
    """Broker x feature matrix from each adapter's declared capabilities (detected live where the broker reports them)."""
    from tradingai.brokers.base import CAPABILITIES
    rows = []
    for name, cls in ADAPTERS.items():
        caps = cls.capabilities(cls.__new__(cls))
        rows.append({"broker": name, "label": cls.label, "environments": list(cls.environments),
                     "verified": False, **{c: caps.get(c, False) for c in CAPABILITIES}})
    return rows
