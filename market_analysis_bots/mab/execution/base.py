"""The provider adapter interface every account connection implements, and the pieces it shares.

One small, strict language for every broker and for the internal simulators, so the execution engine
cannot tell them apart:

    authenticate()                  check the credentials; the account's public identity and permissions
    account()                       equity, cash, buying power, currency, status (as the provider reports it)
    positions()                     what the account holds
    instrument(symbol)              broker symbol, tradable, fractionable, size and price steps, asset class
    quote(symbol)                   best bid / ask / last from the provider's own market data
    submit(OrderRequest)            send one order -> OrderStatus
    cancel(broker_order_id)         cancel one order (already-final orders are not an error)
    get_order(broker_id | client_id)   current status, or None when the provider says it does not exist
    open_orders()                   every working order
    capabilities()                  asset classes, order types, time-in-force rules, protective-stop type,
                                    auth methods, paper/live, funding link, rate limit

Errors say what is known about an order after a failure, which is what makes retries safe:
    OrderRejected       the provider refused it: nothing was placed
    NotSent             the request never left this computer (connection refused, DNS): nothing was placed
    OutcomeUnknown      the request may have reached the provider (timeout, dropped connection): never
                        resend; look the order up by its client id
    ProviderError       anything else (authentication, bad response)
"""

from __future__ import annotations

import hashlib
import json
import socket
import threading
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import asdict, dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

# ----------------------------------------------------------------------------- errors

class ProviderError(Exception):
    """The provider refused a request or answered in a way that cannot be used."""


class OrderRejected(ProviderError):
    """The provider refused the order. Nothing was placed."""


class NotSent(ProviderError):
    """The request never reached the provider (connection refused, name not resolved). Nothing was placed."""


class OutcomeUnknown(ProviderError):
    """The request may or may not have reached the provider. Never resend: look it up by client id."""


class AuthError(ProviderError):
    """Credentials missing, wrong, revoked or without the needed permission."""


# ----------------------------------------------------------------------------- records

# normalised order states reported by providers (the engine adds its own NEW / SUBMITTING / UNKNOWN / ...)
ACKED, PARTIALLY_FILLED, FILLED, CANCELED, REJECTED, EXPIRED, PENDING_CANCEL = (
    "ACKED", "PARTIALLY_FILLED", "FILLED", "CANCELED", "REJECTED", "EXPIRED", "PENDING_CANCEL")


@dataclass
class OrderRequest:
    client_order_id: str
    symbol: str
    side: str                                  # buy | sell
    order_type: str                            # market | limit | stop | stop_limit
    qty: float
    limit_price: Optional[float] = None
    stop_price: Optional[float] = None
    tif: str = "gtc"                           # gtc | ioc | day
    reduce_only: bool = False
    ref_price: Optional[float] = None          # the decision price (simulators fill around it; slippage is measured from it)

    def to_dict(self):
        return asdict(self)


@dataclass
class OrderStatus:
    broker_order_id: str
    client_order_id: str
    symbol: str
    side: str
    order_type: str
    qty: float
    state: str                                 # ACKED | PARTIALLY_FILLED | FILLED | CANCELED | REJECTED | EXPIRED | PENDING_CANCEL
    filled_qty: float = 0.0
    avg_price: Optional[float] = None          # average fill price, cumulative
    fees: float = 0.0                          # cumulative, in fee_currency
    fee_currency: str = ""
    reason: str = ""
    updated: Optional[int] = None
    liquidity: str = "taker"
    simulated: bool = False
    model: str = ""                            # how a simulator produced the fill
    raw: dict = field(default_factory=dict)

    @property
    def final(self) -> bool:
        return self.state in (FILLED, CANCELED, REJECTED, EXPIRED)

    def to_dict(self):
        d = asdict(self)
        d.pop("raw", None)
        return d


# ----------------------------------------------------------------------------- client order ids

def client_order_id(owner: str, intent_id: str, purpose: str, attempt: int = 0) -> str:
    """Deterministic: the same decision always maps to the same id, so a replay or a restart finds the
    order that was already placed instead of placing it again."""
    h = hashlib.sha256(f"{owner}|{intent_id}|{purpose}|{attempt}".encode()).hexdigest()[:20]
    code = {"entry": "en", "exit": "ex", "protective_stop": "st", "flatten": "fl", "test": "ts"}.get(purpose, "xx")
    return f"jv-{code}-{h}"


def uuid_for(cid: str) -> str:
    """A UUID derived from a client order id (for providers that want UUIDs, e.g. Kraken's cl_ord_id)."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "jarvus:" + cid))


def int_for(cid: str) -> int:
    """A positive 63-bit integer derived from a client order id (providers with numeric client ids)."""
    return int(hashlib.sha256(cid.encode()).hexdigest()[:15], 16)


# ----------------------------------------------------------------------------- HTTP transport

Transport = Callable[[str, str, Dict[str, str], Optional[bytes]], Tuple[int, bytes, Dict[str, str]]]


def http_transport(timeout: float = 15.0) -> Transport:
    """urllib transport that classifies failures: NotSent when nothing left this computer, OutcomeUnknown
    when a request may have been received. Returns (status, body, headers)."""
    def send(method, url, headers, body):
        req = urllib.request.Request(url, data=body, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.status, r.read(), {k.lower(): v for k, v in r.headers.items()}
        except urllib.error.HTTPError as e:
            return e.code, e.read(), {k.lower(): v for k, v in (e.headers or {}).items()}
        except urllib.error.URLError as e:
            reason = getattr(e, "reason", e)
            if isinstance(reason, (ConnectionRefusedError, socket.gaierror)):
                raise NotSent(f"{url.split('/')[2]} unreachable: {reason}") from e
            raise OutcomeUnknown(f"no response from {url.split('/')[2]}: {reason}") from e
        except (TimeoutError, socket.timeout, ConnectionResetError, OSError) as e:
            raise OutcomeUnknown(f"no response from {url.split('/')[2]}: {e}") from e
    return send


def json_body(status: int, body: bytes, where: str) -> dict:
    try:
        d = json.loads(body or b"{}")
    except ValueError:
        raise ProviderError(f"{where}: HTTP {status}, response was not JSON")
    return d


# ----------------------------------------------------------------------------- rate limiting

class TokenBucket:
    """At most `capacity` requests, refilled continuously over `per_s` seconds (a provider's documented
    limit, kept below it). acquire() waits up to `timeout` seconds for a token."""

    def __init__(self, capacity: int, per_s: float, clock=time.monotonic, sleep=time.sleep):
        self.capacity = max(1, int(capacity))
        self.rate = self.capacity / max(per_s, 1e-9)
        self.tokens = float(self.capacity)
        self.clock, self.sleep = clock, sleep
        self.t = clock()
        self.lock = threading.Lock()
        self.waited_ms = 0.0
        self.denied = 0

    def _refill(self):
        now = self.clock()
        self.tokens = min(self.capacity, self.tokens + (now - self.t) * self.rate)
        self.t = now

    def acquire(self, timeout: float = 5.0) -> bool:
        deadline = self.clock() + timeout
        while True:
            with self.lock:
                self._refill()
                if self.tokens >= 1:
                    self.tokens -= 1
                    return True
                need = (1 - self.tokens) / self.rate
            if self.clock() + need > deadline:
                with self.lock:
                    self.denied += 1
                return False
            self.waited_ms += need * 1000
            self.sleep(need)

    def usage(self) -> dict:
        with self.lock:
            self._refill()
            return {"capacity": self.capacity, "available": round(self.tokens, 2), "denied": self.denied,
                    "waited_ms": round(self.waited_ms, 1)}


# ----------------------------------------------------------------------------- the interface

class Provider:
    """Base class. `environment` is fixed at construction: a paper connection can never send to a live
    endpoint and the reverse (separate credentials, separate URLs, separate order paths)."""

    name = "base"
    label = "Base"
    environment = "paper"                      # demo | paper | live
    real_money = False
    simulated = False                          # fills produced by a simulator, not a broker
    rate = (60, 60.0)                          # requests per seconds

    def capabilities(self) -> dict:
        raise NotImplementedError

    def authenticate(self) -> dict:
        raise NotImplementedError

    def account(self) -> dict:
        raise NotImplementedError

    def positions(self) -> List[dict]:
        raise NotImplementedError

    def instrument(self, symbol: str) -> dict:
        raise NotImplementedError

    def quote(self, symbol: str) -> dict:
        raise NotImplementedError

    def submit(self, req: OrderRequest) -> OrderStatus:
        raise NotImplementedError

    def cancel(self, broker_order_id: str) -> None:
        raise NotImplementedError

    def get_order(self, broker_order_id: Optional[str] = None, client_order_id: Optional[str] = None) -> Optional[OrderStatus]:
        raise NotImplementedError

    def open_orders(self) -> List[OrderStatus]:
        raise NotImplementedError

    def server_time(self) -> Optional[int]:
        """The provider's clock (ms) if it publishes one; used to check this computer's clock."""
        return None

    def funding(self) -> dict:
        """Where the owner adds money: the provider's own funding page. Never simulated here."""
        return {"url": None, "label": None, "note": "no funding flow for this connection"}

    def sellable(self, symbol: str) -> Optional[float]:
        """What can be sold right now according to the provider (fees taken in the asset shrink it)."""
        for p in self.positions():
            if p.get("symbol") == symbol:
                return float(p.get("qty") or 0.0)
        return 0.0
