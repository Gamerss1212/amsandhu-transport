"""A local HTTP server that speaks the parts of Alpaca's Trading and Market Data APIs this program uses, with
Alpaca's JSON shapes and rules (header auth, crypto gtc/ioc only, fractional equities day-only, 403 for
insufficient buying power, 422 for bad input, 404 for unknown orders, by_client_order_id look-up, crypto fee
taken from the coins received, random partial fills can be switched on). The adapter talks to it over real
HTTP, so request formatting and response parsing are both exercised.

Used by tests/test_providers.py. It is a contract test double, not a claim about Alpaca's matching.
"""

import json
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

KEY, SECRET = "PKTESTKEY000000000000", "testsecret0000000000000000000000000000000"


class FakeAlpaca:
    def __init__(self):
        self.cash = 100_000.0
        self.assets = {
            "AAPL": {"class": "us_equity", "tradable": True, "fractionable": True, "status": "active"},
            "BTC/USD": {"class": "crypto", "tradable": True, "fractionable": True, "status": "active",
                        "min_order_size": "0.0001", "min_trade_increment": "0.000000001", "price_increment": "1"},
        }
        self.quotes = {"AAPL": (199.9, 200.1), "BTC/USD": (64990.0, 65010.0)}
        self.orders = {}
        self.positions = {}
        self.requests = []
        self.partial_next = None
        self.crypto_fee = 0.0025
        self.hold_new_orders = False           # leave orders working (not filled) to test cancels
        self.drop_next_response = False        # accept the order but "lose" the response (500)

    # ---------------------------------------------------------------- matching
    def _fill(self, o, qty, px):
        filled = float(o["filled_qty"])
        o["filled_avg_price"] = str((float(o["filled_avg_price"] or 0) * filled + px * qty) / (filled + qty))
        o["filled_qty"] = str(filled + qty)
        sym = o["symbol"]
        p = self.positions.setdefault(sym, {"qty": 0.0, "cost": 0.0, "class": o["asset_class"]})
        if o["side"] == "buy":
            got = qty * (1 - self.crypto_fee) if o["asset_class"] == "crypto" else qty
            p["qty"] += got
            p["cost"] += qty * px
            self.cash -= qty * px
        else:
            p["qty"] -= qty
            proceeds = qty * px * ((1 - self.crypto_fee) if o["asset_class"] == "crypto" else 1)
            self.cash += proceeds

    def new_order(self, body):
        sym = body.get("symbol")
        a = self.assets.get(sym)
        if a is None:
            return 422, {"code": 42210000, "message": f"asset {sym} not found"}
        tif, typ = body.get("time_in_force"), body.get("type")
        crypto = a["class"] == "crypto"
        if crypto and tif not in ("gtc", "ioc"):
            return 422, {"code": 42210000, "message": "invalid crypto time_in_force"}
        if crypto and typ == "stop":
            return 422, {"code": 42210000, "message": "invalid order type for crypto order"}
        qty = float(body.get("qty"))
        if not crypto and abs(qty - round(qty)) > 1e-9 and tif != "day":
            return 422, {"code": 42210000, "message": "fractional orders must be DAY orders"}
        cid = body.get("client_order_id") or str(uuid.uuid4())
        if len(cid) > 128:
            return 422, {"code": 42210000, "message": "client_order_id must be no more than 128 characters"}
        if any(o["client_order_id"] == cid for o in self.orders.values()):
            return 422, {"code": 40010001, "message": "client_order_id must be unique"}
        bid, ask = self.quotes[sym]
        if body["side"] == "buy" and typ in ("market", "limit") and qty * ask > self.cash:
            return 403, {"code": 40310000, "message": "insufficient buying power"}
        if body["side"] == "sell":
            held = self.positions.get(sym, {}).get("qty", 0.0)
            reserved = sum(float(o["qty"]) - float(o["filled_qty"]) for o in self.orders.values()
                           if o["symbol"] == sym and o["side"] == "sell" and o["status"] in ("new", "accepted", "partially_filled"))
            if qty > held - reserved + 1e-9:
                return 403, {"code": 40310000, "message": f"insufficient qty available for order (requested: {qty}, "
                                                          f"available: {held - reserved})"}
        oid = str(uuid.uuid4())
        o = {"id": oid, "client_order_id": cid, "symbol": sym, "asset_class": a["class"], "qty": body["qty"],
             "filled_qty": "0", "filled_avg_price": None, "side": body["side"], "type": typ, "time_in_force": tif,
             "limit_price": body.get("limit_price"), "stop_price": body.get("stop_price"), "status": "new",
             "created_at": "2026-09-30T12:00:00Z", "updated_at": "2026-09-30T12:00:00Z"}
        self.orders[oid] = o
        marketable = typ == "market" or (typ == "limit" and ((body["side"] == "buy" and float(body["limit_price"]) >= ask)
                                                              or (body["side"] == "sell" and float(body["limit_price"]) <= bid)))
        if marketable and not self.hold_new_orders:
            frac = self.partial_next if self.partial_next is not None else 1.0
            self.partial_next = None
            self._fill(o, qty * frac, ask if body["side"] == "buy" else bid)
            if frac >= 1:
                o["status"] = "filled"
            elif tif == "ioc":
                o["status"] = "canceled"
            else:
                o["status"] = "partially_filled"
        elif tif == "ioc" and not self.hold_new_orders:
            o["status"] = "canceled"
        if self.drop_next_response:
            self.drop_next_response = False
            return 500, {"message": "internal server error"}
        return 200, o

    def trigger_stops(self, price):
        for o in self.orders.values():
            if o["type"] in ("stop", "stop_limit") and o["status"] == "new" and price <= float(o["stop_price"]):
                self._fill(o, float(o["qty"]), price)
                o["status"] = "filled"

    def positions_json(self):
        out = []
        for sym, p in self.positions.items():
            if p["qty"] <= 1e-12:
                continue
            reserved = sum(float(o["qty"]) - float(o["filled_qty"]) for o in self.orders.values()
                           if o["symbol"] == sym and o["side"] == "sell" and o["status"] in ("new", "accepted", "partially_filled"))
            out.append({"symbol": sym.replace("/", "") if p["class"] == "crypto" else sym, "asset_class": p["class"],
                        "qty": str(p["qty"]), "qty_available": str(p["qty"] - reserved),
                        "avg_entry_price": str(p["cost"] / p["qty"]) if p["qty"] else "0", "market_value": "0",
                        "unrealized_pl": "0"})
        return out


def serve(fake: FakeAlpaca):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code, obj=None):
            data = b"" if obj is None else json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _authed(self):
            k, s = self.headers.get("APCA-API-KEY-ID"), self.headers.get("APCA-API-SECRET-KEY")
            tok = self.headers.get("Authorization")
            return (k == KEY and s == SECRET) or tok == "Bearer oauth-token-123"

        def _route(self, method):
            u = urlparse(self.path)
            q = parse_qs(u.query)
            n = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(n) or b"{}") if n else {}
            fake.requests.append((method, u.path, body, dict(self.headers)))
            if not self._authed():
                return self._send(401, {"code": 40110000, "message": "request is not authorized"})
            p = u.path
            if p == "/v2/account" and method == "GET":
                return self._send(200, {"id": "acc-uuid", "account_number": "PA3ABCD1234", "status": "ACTIVE",
                                        "crypto_status": "ACTIVE", "currency": "USD", "cash": str(fake.cash),
                                        "buying_power": str(fake.cash * 2), "non_marginable_buying_power": str(fake.cash),
                                        "equity": str(fake.cash), "last_equity": str(fake.cash),
                                        "trading_blocked": False, "account_blocked": False, "pattern_day_trader": False,
                                        "shorting_enabled": True})
            if p == "/v2/clock":
                import datetime as _dt
                now = _dt.datetime.now(_dt.timezone.utc).isoformat().replace("+00:00", "Z")
                return self._send(200, {"timestamp": now, "is_open": True})
            if p.startswith("/v2/assets/"):
                sym = unquote(p[len("/v2/assets/"):])
                a = fake.assets.get(sym)
                return self._send(200, dict(a, symbol=sym)) if a else self._send(404, {"message": "not found"})
            if p == "/v2/positions":
                return self._send(200, fake.positions_json())
            if p == "/v2/orders" and method == "POST":
                code, o = fake.new_order(body)
                return self._send(code, o)
            if p == "/v2/orders" and method == "GET":
                return self._send(200, [o for o in fake.orders.values() if o["status"] in ("new", "accepted", "partially_filled")])
            if p == "/v2/orders:by_client_order_id":
                cid = (q.get("client_order_id") or [""])[0]
                o = next((o for o in fake.orders.values() if o["client_order_id"] == cid), None)
                return self._send(200, o) if o else self._send(404, {"message": "order not found"})
            if p.startswith("/v2/orders/"):
                oid = p.split("/")[-1]
                o = fake.orders.get(oid)
                if o is None:
                    return self._send(404, {"message": "order not found"})
                if method == "DELETE":
                    if o["status"] in ("filled", "canceled", "expired"):
                        return self._send(422, {"message": "order is not cancelable"})
                    o["status"] = "canceled"
                    return self._send(204)
                return self._send(200, o)
            if p == "/v1beta3/crypto/us/latest/quotes" or p == "/v2/stocks/quotes/latest":
                syms = (q.get("symbols") or [""])[0].split(",")
                return self._send(200, {"quotes": {s: {"bp": fake.quotes[s][0], "ap": fake.quotes[s][1],
                                                       "t": "2026-09-30T12:00:00Z"} for s in syms if s in fake.quotes}})
            return self._send(404, {"message": "no route"})

        def do_GET(self):
            self._route("GET")

        def do_POST(self):
            self._route("POST")

        def do_DELETE(self):
            self._route("DELETE")

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), H)
    httpd.daemon_threads = True
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd
