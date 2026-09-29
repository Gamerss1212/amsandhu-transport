"""NDAX (Canadian exchange, AlphaPoint platform) through its WebSocket gateway.

NDAX authenticates API keys only over the WebSocket gateway (wss://api.ndax.io/WSGateway/); the HTTP
path cannot authenticate. This adapter includes a small standard-library WebSocket client and speaks
the AlphaPoint message frame {"m": type, "i": sequence, "n": function, "o": payload-as-JSON-string}.

Credentials: API key, API secret and the numeric User ID shown with the key in NDAX's API settings.
Signature = HMAC-SHA256(secret, nonce + user id + API key), hex. Create the key without withdrawal
rights. Written from NDAX's published API documentation; it has not been run against a live NDAX
account in this build, so the first connection test is the real check.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import socket
import ssl
import struct
import threading
import time
import zlib
from typing import Dict
from urllib.parse import urlparse

from mab.brokers.base import Broker, BrokerError, Order, OrderUnknown, round_step

GATEWAY = "wss://api.ndax.io/WSGateway/"
OMS = 1
STATE = {"Working": "open", "FullyExecuted": "filled", "Canceled": "canceled", "Rejected": "rejected",
         "Expired": "canceled", "Unknown": "unknown"}


class WebSocket:
    """Minimal RFC 6455 client: text frames, client masking, ping/pong, close."""

    def __init__(self, url: str, timeout: float = 15.0, sock=None):
        u = urlparse(url)
        self.timeout = timeout
        if sock is None:
            raw = socket.create_connection((u.hostname, u.port or (443 if u.scheme == "wss" else 80)), timeout=timeout)
            sock = ssl.create_default_context().wrap_socket(raw, server_hostname=u.hostname) if u.scheme == "wss" else raw
        self.sock = sock
        key = base64.b64encode(os.urandom(16)).decode()
        req = (f"GET {u.path or '/'} HTTP/1.1\r\nHost: {u.hostname}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
               f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n")
        self.sock.sendall(req.encode())
        head = b""
        while b"\r\n\r\n" not in head:
            chunk = self.sock.recv(1)
            if not chunk:
                raise BrokerError("NDAX gateway closed during the handshake")
            head += chunk
        lines = head.decode(errors="replace").split("\r\n")
        if " 101 " not in lines[0]:
            raise BrokerError(f"NDAX gateway refused the connection: {lines[0]}")
        expect = base64.b64encode(hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()).digest()).decode()
        acc = next((ln.split(":", 1)[1].strip() for ln in lines if ln.lower().startswith("sec-websocket-accept:")), "")
        if acc != expect:
            raise BrokerError("NDAX gateway handshake could not be verified")

    def _read(self, n: int) -> bytes:
        buf = b""
        while len(buf) < n:
            chunk = self.sock.recv(n - len(buf))
            if not chunk:
                raise OrderUnknown("NDAX connection closed")
            buf += chunk
        return buf

    def _send(self, opcode: int, payload: bytes):
        head = bytes([0x80 | opcode])
        n = len(payload)
        if n < 126:
            head += bytes([0x80 | n])
        elif n < 65536:
            head += bytes([0x80 | 126]) + struct.pack(">H", n)
        else:
            head += bytes([0x80 | 127]) + struct.pack(">Q", n)
        mask = os.urandom(4)
        self.sock.sendall(head + mask + bytes(b ^ mask[k % 4] for k, b in enumerate(payload)))

    def send(self, text: str):
        self._send(0x1, text.encode())

    def recv(self) -> str:
        parts = []
        while True:
            b1, b2 = self._read(2)
            op, n = b1 & 0x0F, b2 & 0x7F
            if n == 126:
                n = struct.unpack(">H", self._read(2))[0]
            elif n == 127:
                n = struct.unpack(">Q", self._read(8))[0]
            mask = self._read(4) if b2 & 0x80 else None
            data = self._read(n)
            if mask:
                data = bytes(b ^ mask[k % 4] for k, b in enumerate(data))
            if op == 0x9:
                self._send(0xA, data)
                continue
            if op == 0x8:
                raise OrderUnknown("NDAX closed the connection")
            if op in (0x1, 0x0, 0x2):
                parts.append(data)
                if b1 & 0x80:
                    return b"".join(parts).decode()

    def close(self):
        try:
            self._send(0x8, b"")
            self.sock.close()
        except OSError:
            pass


def signature(secret: str, nonce: str, user_id: str, key: str) -> str:
    return hmac.new(secret.encode(), (nonce + user_id + key).encode(), hashlib.sha256).hexdigest()


class NDAX(Broker):
    name = "ndax"
    asset_class = "crypto"

    def __init__(self, key, secret, transport=None, user_id="", quote="CAD", connect=None, **opts):
        super().__init__(key, secret, transport, **opts)
        if not str(user_id).strip():
            raise BrokerError("NDAX needs the numeric User ID shown with the API key")
        self.user_id = str(user_id).strip()
        self.quote = quote.upper()
        self._connect = connect or (lambda: WebSocket(GATEWAY))
        self._ws = None
        self._seq = 0
        self._lock = threading.Lock()
        self.account_id = None
        self._instruments: Dict[str, dict] = {}

    # ------------------------------------------------------------------ session
    def _call(self, fn: str, payload: dict) -> dict:
        with self._lock:
            if self._ws is None:
                self._ws = self._connect()
                self._authenticate()
            return self._raw_call(fn, payload)

    def _raw_call(self, fn, payload):
        self._seq += 2
        seq = self._seq
        self._ws.send(json.dumps({"m": 0, "i": seq, "n": fn, "o": json.dumps(payload)}))
        deadline = time.time() + 15
        while time.time() < deadline:
            msg = json.loads(self._ws.recv())
            if msg.get("i") != seq or msg.get("m") not in (1, 5):
                continue                                   # an event for another subscription
            body = json.loads(msg.get("o") or "{}") if isinstance(msg.get("o"), str) else (msg.get("o") or {})
            if msg["m"] == 5:
                raise BrokerError(f"NDAX {fn}: {body}")
            return body
        raise OrderUnknown(f"NDAX {fn}: no reply")

    def _authenticate(self):
        nonce = str(int(time.time() * 1000))
        r = self._raw_call("AuthenticateUser", {"APIKey": self.key, "Signature": signature(self.secret, nonce, self.user_id, self.key),
                                                "UserId": self.user_id, "Nonce": nonce})
        if not (r.get("Authenticated") or r.get("authenticated")):
            self._ws.close()
            self._ws = None
            raise BrokerError(f"NDAX authentication failed: {r.get('errormsg') or r.get('ErrorMessage') or 'check the key, secret and user id'}")
        user = r.get("User") or r.get("user") or {}
        self.account_id = user.get("AccountId") or user.get("accountId")

    # ------------------------------------------------------------------ markets
    def market(self, instrument):
        base = instrument.upper().split("-")[0]
        base = {"XBT": "BTC"}.get(base, base)
        sym = base + self.quote
        if sym not in self._instruments:
            for ins in self._call("GetInstruments", {"OMSId": OMS}):
                self._instruments[ins["Symbol"]] = {"symbol": ins["Symbol"], "id": ins["InstrumentId"],
                                                    "min_qty": float(ins.get("MinimumQuantity") or 0),
                                                    "qty_step": float(ins.get("QuantityIncrement") or 1e-8),
                                                    "price_step": float(ins.get("PriceIncrement") or 0.01), "min_notional": 0.0}
            if sym not in self._instruments:
                raise BrokerError(f"NDAX does not list {sym}")
        return self._instruments[sym]

    @staticmethod
    def _cid(client_id: str) -> int:
        return zlib.crc32(client_id.encode()) & 0x7FFFFFFF

    def _send(self, instrument, side, otype, qty, price, client_id, tif) -> Order:
        m = self.market(instrument)
        q = round_step(qty, m["qty_step"])
        if q < m["min_qty"] or q <= 0:
            return Order("", client_id, instrument, side, otype, qty, "rejected", reason=f"size {q} is below NDAX's minimum {m['min_qty']}")
        body = {"InstrumentId": m["id"], "OMSId": OMS, "AccountId": self.account_id, "TimeInForce": tif,
                "ClientOrderId": self._cid(client_id), "OrderIdOCO": 0, "UseDisplayQuantity": False,
                "Side": 0 if side == "buy" else 1, "Quantity": q, "OrderType": {"market": 1, "limit": 2, "stop": 3}[otype]}
        if otype == "limit":
            body["LimitPrice"] = round(round(price / m["price_step"]) * m["price_step"], 10)
        if otype == "stop":
            body["StopPrice"] = round(round(price / m["price_step"]) * m["price_step"], 10)
        r = self._call("SendOrder", body)
        if str(r.get("status", "")).lower() == "rejected" or r.get("errormsg"):
            return Order("", client_id, instrument, side, otype, q, "rejected", reason=r.get("errormsg") or "rejected")
        return Order(str(r.get("OrderId", "")), client_id, instrument, side, otype, q, "open", raw=r)

    def buy(self, instrument, qty, limit_price, client_id):
        return self._send(instrument, "buy", "limit", qty, limit_price, client_id, 3)          # IOC

    def sell(self, instrument, qty, limit_price, client_id):
        if limit_price is None:
            return self._send(instrument, "sell", "market", qty, None, client_id, 1)
        return self._send(instrument, "sell", "limit", qty, limit_price, client_id, 3)

    def stop(self, instrument, qty, stop_price, client_id):
        return self._send(instrument, "sell", "stop", qty, stop_price, client_id, 1)          # GTC stop-market

    def cancel(self, order_id):
        self._call("CancelOrder", {"OMSId": OMS, "AccountId": self.account_id, "OrderId": int(order_id)})

    def order(self, order_id=None, client_id=None):
        if order_id:
            o = self._call("GetOrderStatus", {"OMSId": OMS, "AccountId": self.account_id, "OrderId": int(order_id)})
        elif client_id:
            cid = self._cid(client_id)
            orders = (self._call("GetOpenOrders", {"OMSId": OMS, "AccountId": self.account_id}) or []) + \
                     (self._call("GetOrderHistory", {"OMSId": OMS, "AccountId": self.account_id, "Depth": 200}) or [])
            o = next((x for x in orders if x.get("ClientOrderId") == cid), None)
        else:
            raise BrokerError("order(): give an order id or a client id")
        if not o:
            return None
        filled = float(o.get("QuantityExecuted") or 0)
        status = STATE.get(o.get("OrderState"), "unknown")
        if status == "canceled" and filled > 0:
            status = "partially_filled"
        return Order(str(o.get("OrderId")), client_id or "", str(o.get("Instrument")), "buy" if o.get("Side") in (0, "Buy") else "sell",
                     str(o.get("OrderType")), float(o.get("OrigQuantity") or o.get("Quantity") or 0), status, filled,
                     float(o["AvgPrice"]) if o.get("AvgPrice") else None, 0.0, o.get("RejectReason") or "", raw=o)

    def balances(self):
        rows = self._call("GetAccountPositions", {"AccountId": self.account_id, "OMSId": OMS}) or []
        return {r["ProductSymbol"]: float(r.get("Amount") or 0) - float(r.get("Hold") or 0) for r in rows}

    def test(self):
        bal = self.balances()
        return {"ok": True, "broker": "NDAX", "quote": self.quote, "cash": bal.get(self.quote, 0.0),
                "balances": {k: v for k, v in bal.items() if v}, "can_trade": True, "account_id": self.account_id,
                "notes": ["NDAX adapter follows the published API; this is its first live check."]}
