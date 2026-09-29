"""Broker adapters and the real-money executor, tested against fake exchanges (no network, no money)."""
import json
import os
import socket
import sys
import threading
import urllib.parse

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mab.brokers.alpaca import Alpaca  # noqa: E402
from mab.brokers.base import Broker, BrokerError, Order, OrderUnknown  # noqa: E402
from mab.brokers import kraken as K  # noqa: E402
from mab.brokers import ndax as N  # noqa: E402
from mab.live import ACK_TEXT, LiveExecutor  # noqa: E402


# ------------------------------------------------------------------ Kraken
def test_kraken_signature_matches_krakens_published_example():
    sig = K.sign("/0/private/AddOrder", "1616492376594",
                 "nonce=1616492376594&ordertype=limit&pair=XBTUSD&price=37500&type=buy&volume=1.25",
                 "kQH5HW/8p1uGOVjbgWA7FunAmGO8lsSUXNsu3eow76sz84Q18fWxnyRzBHCd3pd5nE9qa99HAZtuZuj6F1huXg==")
    assert sig == "4/dpxb3iT4tp/ZCVEwSnEsLxx0bqyhLpdfOpc6fn7OR8+UClSV5n9E6aSS8MPtnRfp32bAb0nmbRn6H8ndwLUQ=="


class KrakenFake:
    def __init__(self):
        self.calls = []

    def __call__(self, method, url, headers, body):
        path = urllib.parse.urlparse(url).path
        self.calls.append((method, path, headers, dict(urllib.parse.parse_qsl(body.decode())) if body else {}))
        if path.endswith("AssetPairs"):
            return 200, json.dumps({"error": [], "result": {"XXBTZCAD": {"altname": "XBTCAD", "ordermin": "0.00005",
                                   "lot_decimals": 8, "pair_decimals": 1, "tick_size": "0.1", "costmin": "0.5",
                                   "base": "XXBT", "quote": "ZCAD"}}}).encode()
        if path.endswith("AddOrder"):
            return 200, json.dumps({"error": [], "result": {"txid": ["OABC-123"], "descr": {"order": "buy"}}}).encode()
        if path.endswith("QueryOrders"):
            return 200, json.dumps({"error": [], "result": {"OABC-123": {"status": "closed", "vol": "0.001", "vol_exec": "0.001",
                                   "cost": "95.0", "fee": "0.25", "descr": {"pair": "XBTCAD", "type": "buy", "ordertype": "limit"}}}}).encode()
        if path.endswith("Balance"):
            return 200, json.dumps({"error": [], "result": {"ZCAD": "250.5", "XXBT": "0.001"}}).encode()
        return 200, json.dumps({"error": ["EGeneral:Unknown method"]}).encode()


def test_kraken_order_request_and_parse():
    fake = KrakenFake()
    k = K.Kraken("key", "c2VjcmV0", transport=fake, quote="CAD")
    o = k.buy("BTC-USD", 0.0012345678901, 95000.04, "intent-1:in")
    add = [c for c in fake.calls if c[1].endswith("AddOrder")][0]
    p = add[3]
    assert p["pair"] == "XBTCAD" and p["type"] == "buy" and p["ordertype"] == "limit" and p["timeinforce"] == "IOC"
    assert p["oflags"] == "fciq" and p["price"] == "95000.0" and p["volume"] == "0.00123456"
    assert int(p["userref"]) == K.userref("intent-1:in") and "API-Sign" in add[2] and add[2]["API-Key"] == "key"
    done = k.order(order_id=o.id)
    assert done.status == "filled" and abs(done.avg_price - 95000.0) < 1e-6 and done.fee == 0.25
    assert k.buy("BTC-USD", 0.00001, 95000, "tiny").status == "rejected"          # below the pair minimum
    assert k.test()["cash"] == 250.5


def test_kraken_nonces_always_increase():
    k = K.Kraken("key", "c2VjcmV0", transport=KrakenFake())
    ns = [int(k._next_nonce()) for _ in range(50)]
    assert ns == sorted(ns) and len(set(ns)) == 50


# ------------------------------------------------------------------ Alpaca
def test_alpaca_paper_orders_use_headers_and_parse():
    calls = []

    def fake(method, url, headers, body):
        calls.append((method, url, headers, json.loads(body) if body else None))
        if "/v2/assets/" in url:
            return 200, json.dumps({"tradable": True, "fractionable": True}).encode()
        if url.endswith("/v2/orders") and method == "POST":
            return 200, json.dumps({"id": "o1", "client_order_id": "c1", "symbol": "SPY", "side": "buy", "type": "limit",
                                    "qty": "0.5", "status": "filled", "filled_qty": "0.5", "filled_avg_price": "500.10"}).encode()
        return 404, b"{}"
    a = Alpaca("kid", "sec", transport=fake, environment="paper")
    o = a.buy("SPY", 0.5, 500.25, "c1")
    method, url, headers, body = calls[-1]
    assert url.startswith("https://paper-api.alpaca.markets") and headers["APCA-API-KEY-ID"] == "kid"
    assert body["limit_price"] == "500.25" and body["side"] == "buy" and body["client_order_id"] == "c1"
    assert o.status == "filled" and o.avg_price == 500.10 and not a.real_money
    assert Alpaca("k", "s", transport=fake, environment="live").real_money
    with pytest.raises(BrokerError):
        Alpaca("k", "s", transport=fake, environment="demo")


# ------------------------------------------------------------------ NDAX (WebSocket gateway)
def ws_server(sock, replies):
    """A tiny WebSocket server on one end of a socketpair that answers AlphaPoint frames."""
    import base64
    import hashlib
    head = b""
    while b"\r\n\r\n" not in head:
        head += sock.recv(1)
    key = [ln.split(":", 1)[1].strip() for ln in head.decode().split("\r\n") if ln.lower().startswith("sec-websocket-key")][0]
    acc = base64.b64encode(hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()).digest()).decode()
    sock.sendall(f"HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: {acc}\r\n\r\n".encode())
    srv = N.WebSocket.__new__(N.WebSocket)
    srv.sock = sock
    while True:
        try:
            msg = json.loads(srv.recv())
        except Exception:
            return
        body = replies[msg["n"]](json.loads(msg["o"]))
        data = json.dumps({"m": 1, "i": msg["i"], "n": msg["n"], "o": json.dumps(body)}).encode()
        sock.sendall(bytes([0x81, 126]) + len(data).to_bytes(2, "big") + data if len(data) >= 126 else bytes([0x81, len(data)]) + data)


def test_ndax_authenticates_and_sends_orders_over_websocket():
    seen = {}
    replies = {
        "AuthenticateUser": lambda o: seen.setdefault("auth", o) and {"Authenticated": True, "User": {"AccountId": 77}},
        "GetInstruments": lambda o: [{"Symbol": "BTCCAD", "InstrumentId": 1, "MinimumQuantity": 0.0001,
                                      "QuantityIncrement": 0.00000001, "PriceIncrement": 0.01}],
        "SendOrder": lambda o: seen.setdefault("order", o) and {"status": "Accepted", "OrderId": 555},
        "GetAccountPositions": lambda o: [{"ProductSymbol": "CAD", "Amount": 300, "Hold": 20}],
    }
    a, b = socket.socketpair()
    threading.Thread(target=ws_server, args=(b, replies), daemon=True).start()
    n = N.NDAX("apikey", "secret", user_id="96", connect=lambda: N.WebSocket("ws://ndax.test/WSGateway/", sock=a))
    o = n.buy("BTC-USD", 0.002, 90000.0, "i1:in")
    auth = seen["auth"]
    assert auth["Signature"] == N.signature("secret", auth["Nonce"], "96", "apikey") and auth["UserId"] == "96"
    assert o.id == "555" and seen["order"]["Side"] == 0 and seen["order"]["TimeInForce"] == 3 and seen["order"]["AccountId"] == 77
    assert n.balances()["CAD"] == 280
    with pytest.raises(BrokerError):
        N.NDAX("k", "s", user_id="")


# ------------------------------------------------------------------ live executor
class Store:
    def __init__(self):
        self.kv = {}

    def kv_get(self, k, d=None):
        return json.loads(json.dumps(self.kv.get(k, d)))

    def kv_set(self, k, v):
        self.kv[k] = json.loads(json.dumps(v))


class FakeBroker(Broker):
    name = "fake"

    def __init__(self, fill_ratio=1.0, stop_fails=False, lose_first=False, stop_fills=False):
        super().__init__("k", "s", transport=lambda *a: (200, b"{}"))
        self.orders, self.fill_ratio, self.stop_fails, self.lose_first, self.stop_fills = {}, fill_ratio, stop_fails, lose_first, stop_fills
        self.hold = {}
        self.n = 0

    def market(self, inst):
        return {"base": inst.split("-")[0], "min_qty": 0.0}

    def _new(self, inst, side, kind, qty, price, cid):
        self.n += 1
        filled = qty * (self.fill_ratio if side == "buy" else 1.0) if kind != "stop" else 0.0
        o = Order(f"o{self.n}", cid, inst, side, kind, qty, "filled" if kind != "stop" else "open", filled, price or 100.0, 0.1)
        self.orders[o.id] = o
        base = inst.split("-")[0]
        self.hold[base] = self.hold.get(base, 0.0) + (filled if side == "buy" else -filled)
        return o

    def buy(self, inst, qty, limit, cid):
        if self.lose_first:
            self.lose_first = False
            self._new(inst, "buy", "limit", qty, limit, cid)
            raise OrderUnknown("timeout")
        return self._new(inst, "buy", "limit", qty, limit, cid)

    def sell(self, inst, qty, limit, cid):
        return self._new(inst, "sell", "limit" if limit else "market", qty, limit, cid)

    def stop(self, inst, qty, px, cid):
        if self.stop_fails:
            raise BrokerError("stop rejected")
        o = self._new(inst, "sell", "stop", qty, px, cid)
        if self.stop_fills:
            o.status, o.filled_qty, o.avg_price = "filled", qty, px
        return o

    def cancel(self, oid):
        self.orders[oid].status = "canceled"

    def order(self, order_id=None, client_id=None):
        if order_id:
            return self.orders.get(order_id)
        return next((o for o in self.orders.values() if o.client_id == client_id), None)

    def balances(self):
        return dict(self.hold, CAD=1000.0)


def executor(broker, eligible=True):
    alerts = []
    ex = LiveExecutor(Store(), broker, eligible=lambda b: (eligible, "not enough paper trades"),
                      alert=lambda lvl, kind, msg: alerts.append((kind, msg)), sleep=lambda s: None)
    return ex, alerts


def arm(ex, **kw):
    lim = {"max_per_trade": 50, "max_total": 120, "daily_loss_limit": 10}
    lim.update(kw)
    return ex.arm(ACK_TEXT, lim, ["BOT-1", "BOT-2", "BOT-3"])


def test_live_needs_explicit_arming_and_valid_limits():
    ex, _ = executor(FakeBroker())
    assert ex.enter("BOT-1", "BTC-USD", 1, 1.0, 100, 95, "i1")["status"] == "skipped"
    with pytest.raises(ValueError):
        ex.arm("yes", {}, ["BOT-1"])
    with pytest.raises(ValueError):
        ex.arm(ACK_TEXT, {"max_per_trade": 200, "max_total": 100, "daily_loss_limit": 5}, ["BOT-1"])
    with pytest.raises(ValueError):
        LiveExecutor(Store(), None).arm(ACK_TEXT, {}, ["BOT-1"])
    assert arm(ex)["armed"]
    assert ex.enter("BOT-9", "BTC-USD", 1, 1.0, 100, 95, "i2")["reason"] == "this bot is not on the live list"


def test_live_entry_is_capped_long_only_and_gets_an_exchange_stop():
    b = FakeBroker()
    ex, alerts = executor(b)
    arm(ex)
    assert ex.enter("BOT-1", "BTC-USD", -1, 1.0, 100, 105, "s1")["reason"].startswith("live trading is spot long-only")
    r = ex.enter("BOT-1", "BTC-USD", 1, 5.0, 100.0, 95.0, "i1")       # paper wants 500 of notional; the limit is 50
    assert r["status"] == "filled" and abs(r["qty"] * r["avg_price"] - 50) < 0.5
    pos = ex.positions["BOT-1"]
    assert pos["stop_order"] and b.orders[pos["stop_order"]].kind == "stop" and b.orders[pos["stop_order"]].qty == pos["qty"]
    r2 = ex.enter("BOT-2", "ETH-USD", 1, 5.0, 100.0, 95.0, "i2")
    r3 = ex.enter("BOT-3", "SOL-USD", 1, 5.0, 100.0, 95.0, "i3")        # only 120 in total: 50 + 50 + 20
    assert r2["status"] == "filled" and r3["status"] == "filled" and ex.open_notional() <= 120 + 1
    assert any(k == "live_entry" for k, _ in alerts)


def test_live_eligibility_gate_and_override():
    ex, _ = executor(FakeBroker(), eligible=False)
    ex.arm(ACK_TEXT, {"max_per_trade": 50, "max_total": 100, "daily_loss_limit": 10}, ["BOT-1", "BOT-2"], overrides=["BOT-2"])
    assert ex.enter("BOT-1", "BTC-USD", 1, 1.0, 100, 95, "a")["reason"].startswith("not eligible")
    assert ex.enter("BOT-2", "BTC-USD", 1, 1.0, 100, 95, "b")["status"] == "filled"


def test_failed_stop_sells_the_position_and_disarms():
    b = FakeBroker(stop_fails=True)
    ex, alerts = executor(b)
    arm(ex)
    r = ex.enter("BOT-1", "BTC-USD", 1, 1.0, 100.0, 95.0, "i1")
    assert r["status"] == "closed" and "BOT-1" not in ex.positions and not ex.armed
    assert abs(b.hold["BTC"]) < 1e-9 and any(k == "live_stop_failed" for k, _ in alerts)


def test_lost_response_is_resolved_by_client_id_not_resent():
    b = FakeBroker(lose_first=True)
    ex, _ = executor(b)
    arm(ex)
    r = ex.enter("BOT-1", "BTC-USD", 1, 1.0, 100.0, 95.0, "i1")
    buys = [o for o in b.orders.values() if o.side == "buy"]
    assert r["status"] == "filled" and len(buys) == 1                  # found by client id, never sent twice


def test_exit_cancels_the_stop_and_books_pnl_and_daily_limit_disarms():
    b = FakeBroker()
    ex, _ = executor(b)
    arm(ex, daily_loss_limit=1.0)
    ex.enter("BOT-1", "BTC-USD", 1, 1.0, 100.0, 95.0, "i1")
    stop_id = ex.positions["BOT-1"]["stop_order"]
    r = ex.exit("BOT-1", 90.0, "stop hit")                              # sold at 90*(1-0.3%) after buying ~100
    assert r["status"] == "filled" and r["pnl"] < -1 and b.orders[stop_id].status == "canceled"
    assert not ex.armed and "daily loss" in ex.cfg["disarmed_reason"]


def test_exchange_stop_fill_is_detected_and_booked():
    b = FakeBroker(stop_fills=True)
    ex, _ = executor(b)
    arm(ex)
    ex.enter("BOT-1", "BTC-USD", 1, 1.0, 100.0, 95.0, "i1")
    done = ex.poll_stops()
    assert done and done[0][0] == "BOT-1" and done[0][1]["avg_price"] == 95.0 and "BOT-1" not in ex.positions


def test_reconciliation_shortfall_disarms_and_state_survives_restart():
    b = FakeBroker()
    ex, _ = executor(b)
    arm(ex)
    ex.enter("BOT-1", "BTC-USD", 1, 1.0, 100.0, 95.0, "i1")
    again = LiveExecutor(ex.storage, b, eligible=lambda x: (True, ""), sleep=lambda s: None)
    assert again.armed and "BOT-1" in again.positions                  # restart keeps config and positions
    assert again.reconcile()["ok"]
    b.hold["BTC"] = 0.0                                                # someone sold the coins outside the fleet
    rep = again.reconcile()
    assert not rep["ok"] and not again.armed


def test_fleet_routes_listed_bots_to_the_live_broker_and_falls_back_to_paper(tmp_path):
    from types import SimpleNamespace
    from mab.runtime import Fleet
    from mab.strategy import Trade
    fl = Fleet({"data_dir": str(tmp_path / "d")}, {}, [], str(tmp_path))
    b = FakeBroker()
    fl.live = LiveExecutor(fl.storage, b, eligible=lambda x: (True, ""), alert=lambda *a: None, sleep=lambda s: None)
    fl.live.arm(ACK_TEXT, {"max_per_trade": 50, "max_total": 100, "daily_loss_limit": 20}, ["B1"])
    got = {}

    class TM:
        pos = None

        def apply_entry_fill(self, px, qty, fee, t):
            got["entry"] = (px, qty)
            self.pos = SimpleNamespace(reason="long entry rule true", qty=qty)

        def apply_exit_fill(self, frame, i, px, fee, reason):
            got["exit"] = (px, reason)
            self.pos = None
            return {"trade": Trade("S1", "BTC-USD", 1, got["entry"][1], 0, got["entry"][0], 1, px, fee, (px - got["entry"][0]) * got["entry"][1], -0.5,
                                   3, "[LIVE] long", reason, 0.1, -0.6)}

        def intent_rejected(self, why):
            got["rejected"] = why

    br = SimpleNamespace(id="B1", symbol="BTC-USD", venue="coinbase", tf="5m", c=SimpleNamespace(id="S1", definition={"order": {"type": "market"}}),
                         tm=TM(), last_decision="")
    intent = SimpleNamespace(quantity=2.0, intent_id="int-1")
    assert fl._live_route(br, None, 0, {"kind": "entry", "side": 1, "ref_price": 100.0, "stop": 95.0}, intent) == "entered"
    assert br.tm.pos.reason.startswith("[LIVE]") and "B1" in fl.live.positions and got["entry"][1] * got["entry"][0] <= 51
    assert fl._live_route(br, None, 0, {"kind": "exit", "ref_price": 98.0, "reason": "time stop"}, intent) == "exited"
    assert "B1" not in fl.live.positions and got["exit"][1] == "time stop (live)"
    assert fl.storage.query("SELECT COUNT(*) n FROM trades")[0]["n"] == 1
    br2 = SimpleNamespace(id="B2", symbol="ETH-USD", venue="coinbase", tf="5m", c=br.c, tm=TM(), last_decision="")
    assert fl._live_route(br2, None, 0, {"kind": "entry", "side": 1, "ref_price": 100.0, "stop": 95.0}, intent) is None  # not listed: paper
    fl.live.disarm("test")
    assert fl._live_route(br, None, 0, {"kind": "entry", "side": 1, "ref_price": 100.0, "stop": 95.0}, intent) is None   # disarmed: paper
