"""Alpaca (US stocks and crypto) through the Trading API v2 - paper and live.

Facts this adapter relies on (docs.alpaca.markets, checked Sept 2026):
* Paper: https://paper-api.alpaca.markets, live: https://api.alpaca.markets, market data:
  https://data.alpaca.markets. Paper accounts have their own API keys, separate from live keys; anyone can
  open a paper-only account with an email address. Paper fills happen when an order is marketable against
  the NBBO and, when eligible, are partial "for a random size 10% of the time".
* Authentication: APCA-API-KEY-ID / APCA-API-SECRET-KEY headers, or an OAuth2 bearer token (authorize at
  https://app.alpaca.markets/oauth/authorize with env=paper|live; token from
  https://api.alpaca.markets/oauth/token; scopes account:write, trading, data). OAuth needs an OAuth app
  registered with Alpaca (client id and secret); Jarvus does not ship one.
* Orders: client_order_id <= 128 characters; look-up via GET /v2/orders:by_client_order_id.
  Crypto supports market, limit and stop_limit with time_in_force gtc or ioc; symbols like BTC/USD; no
  short selling or margin; the fee is charged on the asset received. Fractional equity orders must be
  time_in_force=day, so stocks here trade whole shares (a protective stop has to outlive the day: gtc).
* Rate limit: 200 requests per minute per account (this adapter budgets 180).
* Funding happens only on Alpaca's own site; this program never moves money.
"""

from __future__ import annotations

import json
import time
import urllib.parse
from typing import Dict, List, Optional

from mab.execution.base import (ACKED, CANCELED, EXPIRED, FILLED, PARTIALLY_FILLED, PENDING_CANCEL, REJECTED,
                                AuthError, NotSent, OrderRejected, OrderRequest, OrderStatus, OutcomeUnknown,
                                Provider, ProviderError, http_transport, json_body)

URLS = {"paper": "https://paper-api.alpaca.markets", "live": "https://api.alpaca.markets"}
DATA = "https://data.alpaca.markets"
OAUTH_AUTHORIZE = "https://app.alpaca.markets/oauth/authorize"
OAUTH_TOKEN = "https://api.alpaca.markets/oauth/token"
OAUTH_SCOPES = "account:write trading data"
DASHBOARD = "https://app.alpaca.markets/"
STATUS = {"new": ACKED, "accepted": ACKED, "pending_new": ACKED, "accepted_for_bidding": ACKED, "held": ACKED,
          "calculated": ACKED, "stopped": ACKED, "suspended": ACKED, "pending_replace": ACKED,
          "partially_filled": PARTIALLY_FILLED, "filled": FILLED, "done_for_day": CANCELED, "canceled": CANCELED,
          "replaced": CANCELED, "expired": EXPIRED, "rejected": REJECTED, "pending_cancel": PENDING_CANCEL}
CRYPTO_TAKER_FEE_EST = 0.0025       # tier 1 upper bound (15-25 bps by 30-day volume); used only to estimate sell fees
CRYPTO_BASES = {"XBT": "BTC", "XXBT": "BTC", "XETH": "ETH", "XDG": "DOGE"}


def _num(x) -> Optional[float]:
    try:
        return float(x) if x not in (None, "") else None
    except (TypeError, ValueError):
        return None


def mask(s: str) -> str:
    s = str(s or "")
    return ("..." + s[-4:]) if len(s) > 4 else s


class Alpaca(Provider):
    name = "alpaca"
    label = "Alpaca"
    rate = (180, 60.0)

    def __init__(self, environment: str = "paper", key: str = None, secret: str = None, token: str = None,
                 transport=None, stock_feed: str = "iex", base_url: str = None, data_url: str = None):
        if environment not in URLS:
            raise ProviderError("environment must be 'paper' or 'live'")
        if not token and not (key and secret):
            raise AuthError("Alpaca needs an API key and secret, or an OAuth token")
        self.environment = environment
        self.real_money = environment == "live"
        self.label = f"Alpaca {'Paper' if environment == 'paper' else 'Live'}"
        self.base = base_url or URLS[environment]           # overrides exist for the contract tests only
        self.data = data_url or DATA
        self._key, self._secret, self._token = key, secret, token
        self.http = transport or http_transport()
        self.feed = stock_feed
        self._assets: Dict[str, dict] = {}

    # ------------------------------------------------------------------ transport
    def _headers(self) -> dict:
        h = {"Accept": "application/json", "User-Agent": "jarvus"}
        if self._token:
            h["Authorization"] = f"Bearer {self._token}"
        else:
            h["APCA-API-KEY-ID"], h["APCA-API-SECRET-KEY"] = self._key, self._secret
        return h

    def _req(self, method: str, path: str, body: dict = None, params: dict = None, base: str = None,
             order_send: bool = False):
        url = (base or self.base) + path + ("?" + urllib.parse.urlencode(params) if params else "")
        headers = self._headers()
        data = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(body).encode()
        status, raw, _ = self.http(method, url, headers, data)
        where = f"Alpaca {method} {path.split('?')[0]}"
        if status in (200, 201, 204, 207):
            return json_body(status, raw, where) if raw else {}
        try:
            msg = json.loads(raw or b"{}").get("message") or raw[:200].decode(errors="replace")
        except ValueError:
            msg = (raw or b"")[:200].decode(errors="replace")
        if status == 404:
            return None
        if status in (401,):
            raise AuthError(f"{where}: not authorised ({msg}); check the key/secret or reconnect")
        if status == 403:
            if order_send:
                raise OrderRejected(f"{where}: {msg}")
            raise AuthError(f"{where}: forbidden ({msg})")
        if status == 429:
            raise NotSent(f"{where}: rate limited by Alpaca ({msg})")
        if status in (400, 422):
            if order_send:
                raise OrderRejected(f"{where}: {msg}")
            raise ProviderError(f"{where}: HTTP {status}: {msg}")
        if status >= 500 and order_send:
            raise OutcomeUnknown(f"{where}: HTTP {status} from Alpaca; the order may or may not exist")
        raise ProviderError(f"{where}: HTTP {status}: {msg}")

    # ------------------------------------------------------------------ symbols
    def _alpaca_symbol(self, symbol: str) -> str:
        """Fleet market key -> Alpaca symbol. coinbase:BTC-USD -> BTC/USD, yahoo:AAPL -> AAPL."""
        s = symbol
        if ":" in s:
            venue, s = s.split(":", 1)
            if venue == "yahoo":
                if "." in s or "^" in s or "=" in s:
                    raise ProviderError(f"{s} is not a US-listed stock Alpaca trades")
                return s.upper()
            base = s.upper().replace("/", "-").split("-")[0]
            if len(s) == 8 and s.startswith("X") and s[4] == "Z":            # Kraken codes like XXBTZUSD
                base = s[1:4]
            return f"{CRYPTO_BASES.get(base, base)}/USD"
        return s.upper()

    # ------------------------------------------------------------------ interface
    def capabilities(self) -> dict:
        return {"asset_classes": ["us_equity", "crypto"], "order_types": ["market", "limit", "stop", "stop_limit"],
                "tif": {"crypto": ["gtc", "ioc"], "us_equity": ["day", "gtc", "ioc", "fok", "opg", "cls"],
                        "fractional_equity": ["day"]},
                "fractional": True, "short": False, "protective_stop": "stop_limit",
                "protective_stop_by_class": {"crypto": "stop_limit", "us_equity": "stop"},
                "auth": ["api_key", "oauth"], "paper": True, "live": True, "market_data": "Alpaca Market Data API",
                "rate_limit": {"requests": 200, "per_seconds": 60}, "withdrawals": "never requested",
                "notes": ["stocks trade whole shares here so the protective stop can be good-till-canceled",
                          "crypto fees are taken from the asset received"]}

    def authenticate(self) -> dict:
        a = self._req("GET", "/v2/account")
        if not a:
            raise AuthError("Alpaca returned no account")
        blocked = bool(a.get("trading_blocked") or a.get("account_blocked"))
        return {"ok": True, "account_id": mask(a.get("account_number") or a.get("id")), "status": a.get("status"),
                "currency": a.get("currency") or "USD", "environment": self.environment,
                "permissions": {"trade": not blocked, "crypto": a.get("crypto_status") == "ACTIVE",
                                "short": bool(a.get("shorting_enabled")), "withdraw": False},
                "pattern_day_trader": bool(a.get("pattern_day_trader")),
                "notes": (["trading is blocked on this account"] if blocked else []) +
                         (["paper account: no real money moves"] if self.environment == "paper" else [])}

    def account(self) -> dict:
        a = self._req("GET", "/v2/account") or {}
        blocked = bool(a.get("trading_blocked") or a.get("account_blocked"))
        return {"equity": _num(a.get("equity")), "cash": _num(a.get("cash")),
                "buying_power": _num(a.get("non_marginable_buying_power")) or _num(a.get("cash")),
                "margin_buying_power": _num(a.get("buying_power")), "currency": a.get("currency") or "USD",
                "status": a.get("status"), "can_trade": not blocked,
                "last_equity": _num(a.get("last_equity")), "simulated": self.environment == "paper"}

    def positions(self) -> List[dict]:
        out = []
        for p in self._req("GET", "/v2/positions") or []:
            sym = p.get("symbol", "")
            if p.get("asset_class") == "crypto" and "/" not in sym and sym.endswith("USD"):
                sym = sym[:-3] + "/USD"
            out.append({"symbol": sym, "qty": _num(p.get("qty")) or 0.0,
                        "qty_available": _num(p.get("qty_available")), "avg_price": _num(p.get("avg_entry_price")),
                        "market_value": _num(p.get("market_value")), "unrealized_pnl": _num(p.get("unrealized_pl")),
                        "asset_class": p.get("asset_class")})
        return out

    def instrument(self, symbol: str) -> dict:
        sym = self._alpaca_symbol(symbol)
        if sym not in self._assets:
            a = self._req("GET", "/v2/assets/" + urllib.parse.quote(sym, safe=""))
            if not a:
                raise ProviderError(f"Alpaca does not list {sym}")
            crypto = a.get("class") == "crypto"
            self._assets[sym] = {"symbol": symbol, "broker_symbol": sym, "tradable": bool(a.get("tradable")),
                                 "fractionable": bool(a.get("fractionable")), "asset_class": "crypto" if crypto else "us_equity",
                                 "min_qty": _num(a.get("min_order_size")) or (0.0 if crypto else 1.0),
                                 "qty_step": _num(a.get("min_trade_increment")) or (1e-9 if crypto else 1.0),
                                 "price_step": _num(a.get("price_increment")) or 0.01, "min_notional": 1.0,
                                 "shortable": False, "status": a.get("status")}
        return self._assets[sym]

    def quote(self, symbol: str) -> dict:
        inst = self.instrument(symbol)
        sym = inst["broker_symbol"]
        if inst["asset_class"] == "crypto":
            d = self._req("GET", "/v1beta3/crypto/us/latest/quotes", params={"symbols": sym}, base=self.data) or {}
        else:
            d = self._req("GET", "/v2/stocks/quotes/latest", params={"symbols": sym, "feed": self.feed}, base=self.data) or {}
        q = (d.get("quotes") or {}).get(sym) or {}
        return {"bid": _num(q.get("bp")) or None, "ask": _num(q.get("ap")) or None, "last": None, "time": q.get("t"),
                "source": f"Alpaca market data ({'crypto' if inst['asset_class'] == 'crypto' else self.feed})"}

    @staticmethod
    def _fmt(x: float, step: float = 0.0) -> str:
        if step and step >= 1:
            return str(int(x))
        s = f"{x:.9f}".rstrip("0").rstrip(".")
        return s or "0"

    def _price(self, x: float, inst: dict) -> str:
        if inst["asset_class"] == "us_equity":
            return f"{x:.2f}" if x >= 1 else f"{x:.4f}"
        step = inst.get("price_step") or 0.0
        if step:
            x = round(round(x / step) * step, 10)
        return self._fmt(x)

    def submit(self, req: OrderRequest) -> OrderStatus:
        inst = self.instrument(req.symbol)
        crypto = inst["asset_class"] == "crypto"
        otype, tif = req.order_type, req.tif
        if crypto:
            if otype == "stop":
                raise OrderRejected("Alpaca crypto has no plain stop orders; use stop_limit")
            tif = tif if tif in ("gtc", "ioc") else "gtc"
        elif abs(req.qty - round(req.qty)) > 1e-9 and tif != "day":
            raise OrderRejected("fractional stock orders must be day orders; whole shares are required here")
        body = {"symbol": inst["broker_symbol"], "qty": self._fmt(req.qty, inst.get("qty_step") if not crypto else 0.0),
                "side": req.side, "type": otype, "time_in_force": tif, "client_order_id": req.client_order_id[:128]}
        if req.limit_price is not None and otype in ("limit", "stop_limit"):
            body["limit_price"] = self._price(req.limit_price, inst)
        if req.stop_price is not None and otype in ("stop", "stop_limit"):
            body["stop_price"] = self._price(req.stop_price, inst)
        o = self._req("POST", "/v2/orders", body, order_send=True)
        if not o:
            raise OutcomeUnknown("Alpaca returned an empty response to an order")
        return self._parse(o, req.client_order_id)

    def _parse(self, o: dict, cid: str = "") -> OrderStatus:
        filled = _num(o.get("filled_qty")) or 0.0
        avg = _num(o.get("filled_avg_price"))
        state = STATUS.get(o.get("status"), ACKED)
        crypto = o.get("asset_class") == "crypto"
        fees, cur = 0.0, "USD"
        if crypto and o.get("side") == "sell" and filled and avg:
            fees = filled * avg * CRYPTO_TAKER_FEE_EST        # estimate; buys pay in the coins received instead
            cur = "USD (estimated)"
        sym = o.get("symbol", "")
        return OrderStatus(o.get("id", ""), o.get("client_order_id") or cid, sym, o.get("side", ""), o.get("type", ""),
                           _num(o.get("qty")) or 0.0, state, filled, avg, fees, cur,
                           o.get("status") if state in (REJECTED, CANCELED, EXPIRED) else "",
                           int(time.time() * 1000), "taker", False, "", raw={k: o.get(k) for k in (
                               "id", "status", "symbol", "qty", "filled_qty", "filled_avg_price", "type", "time_in_force",
                               "limit_price", "stop_price", "created_at", "updated_at", "filled_at", "canceled_at")})

    def cancel(self, broker_order_id: str) -> None:
        try:
            self._req("DELETE", f"/v2/orders/{urllib.parse.quote(broker_order_id)}")
        except ProviderError as e:
            if "422" in str(e):                          # not cancelable any more: filled or already canceled
                return None
            raise

    def get_order(self, broker_order_id=None, client_order_id=None) -> Optional[OrderStatus]:
        if broker_order_id:
            o = self._req("GET", f"/v2/orders/{urllib.parse.quote(broker_order_id)}")
        elif client_order_id:
            o = self._req("GET", "/v2/orders:by_client_order_id", params={"client_order_id": client_order_id[:128]})
        else:
            raise ProviderError("get_order needs an order id or a client order id")
        return self._parse(o, client_order_id or "") if o else None

    def open_orders(self) -> List[OrderStatus]:
        return [self._parse(o) for o in (self._req("GET", "/v2/orders", params={"status": "open", "limit": 500}) or [])]

    def server_time(self) -> Optional[int]:
        c = self._req("GET", "/v2/clock") or {}
        ts = c.get("timestamp")
        if not ts:
            return None
        from datetime import datetime
        try:
            return int(datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp() * 1000)
        except ValueError:
            return None

    def market_clock(self) -> dict:
        return self._req("GET", "/v2/clock") or {}

    def sellable(self, symbol: str) -> Optional[float]:
        sym = self.instrument(symbol)["broker_symbol"]
        for p in self.positions():
            if p["symbol"] == sym:
                return p["qty_available"] if p.get("qty_available") is not None else p["qty"]
        return 0.0

    def funding(self) -> dict:
        if self.environment == "paper":
            return {"url": DASHBOARD, "label": "Open Alpaca dashboard (paper account settings)", "simulated": True,
                    "note": "paper accounts start with simulated money; create or delete paper accounts in Alpaca's "
                            "dashboard. Nothing here is a deposit."}
        return {"url": DASHBOARD, "label": "Add funds on Alpaca", "simulated": False,
                "note": "deposits are made on Alpaca's own site (banking / transfers). Jarvus never moves money and "
                        "never requests withdrawal permission; your balance updates here after Alpaca reports it."}


def oauth_authorize_url(client_id: str, redirect_uri: str, state: str, environment: str) -> str:
    return OAUTH_AUTHORIZE + "?" + urllib.parse.urlencode({
        "response_type": "code", "client_id": client_id, "redirect_uri": redirect_uri, "state": state,
        "scope": OAUTH_SCOPES, "env": environment})


def oauth_exchange(code: str, client_id: str, client_secret: str, redirect_uri: str, transport=None) -> dict:
    http = transport or http_transport()
    body = urllib.parse.urlencode({"grant_type": "authorization_code", "code": code, "client_id": client_id,
                                   "client_secret": client_secret, "redirect_uri": redirect_uri}).encode()
    status, raw, _ = http("POST", OAUTH_TOKEN, {"Content-Type": "application/x-www-form-urlencoded",
                                                "Accept": "application/json"}, body)
    d = json_body(status, raw, "Alpaca OAuth token")
    if status >= 400 or not d.get("access_token"):
        raise AuthError(f"Alpaca OAuth: {d.get('message') or d.get('error') or status}")
    return {"access_token": d["access_token"], "token_type": d.get("token_type"), "scope": d.get("scope")}
