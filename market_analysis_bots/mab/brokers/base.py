"""Common interface for real brokers and exchanges.

Every adapter speaks the same small language, so the live executor cannot tell them apart:
    test()                      read-only check: can we sign requests, what are the balances, may we trade
    market(instrument)          venue symbol, minimum size, size and price steps
    buy / sell(...)             a marketable limit order (immediate-or-cancel) with a price cap
    stop(...)                   a protective stop-loss sell resting ON THE EXCHANGE
    cancel(order_id)
    order(order_id=None, client_id=None)   current status, filled size, average price, fee
    balances()

Orders carry a client id derived from the fleet's intent id, so after a timeout the executor asks the
exchange whether the order exists instead of sending it twice. Spot only: no margin, no leverage.
HTTP goes through an injectable transport so adapters can be tested without a network.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Callable, Dict, Optional, Tuple

Transport = Callable[[str, str, Dict[str, str], Optional[bytes]], Tuple[int, bytes]]


class BrokerError(Exception):
    """The broker refused a request or could not be reached."""


class OrderUnknown(BrokerError):
    """The request may or may not have reached the exchange (timeout or dropped connection)."""


def http_transport(timeout: float = 15.0) -> Transport:
    def send(method, url, headers, body):
        req = urllib.request.Request(url, data=body, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()
        except (TimeoutError, OSError) as e:                     # includes URLError and socket timeouts
            raise OrderUnknown(f"no response from {url.split('/')[2]}: {e}") from e
    return send


@dataclass
class Order:
    id: str
    client_id: str
    instrument: str
    side: str                    # buy | sell
    kind: str                    # limit | market | stop
    qty: float
    status: str                  # open | filled | partially_filled | canceled | rejected | unknown
    filled_qty: float = 0.0
    avg_price: Optional[float] = None
    fee: float = 0.0
    reason: str = ""
    raw: dict = field(default_factory=dict)

    @property
    def done(self) -> bool:
        return self.status in ("filled", "canceled", "rejected", "partially_filled")

    def to_dict(self):
        d = dict(self.__dict__)
        d.pop("raw", None)
        return d


class Broker:
    name = "base"
    asset_class = "crypto"       # crypto | stock
    real_money = True            # False for a broker's own paper endpoint

    def __init__(self, key: str, secret: str, transport: Optional[Transport] = None, **opts):
        if not key or not secret:
            raise BrokerError("API key and secret are required")
        self.key, self.secret = key, secret
        self.http = transport or http_transport()
        self.opts = opts

    # the adapter API ---------------------------------------------------------------
    def test(self) -> dict:
        raise NotImplementedError

    def market(self, instrument: str) -> dict:
        raise NotImplementedError

    def buy(self, instrument: str, qty: float, limit_price: float, client_id: str) -> Order:
        raise NotImplementedError

    def sell(self, instrument: str, qty: float, limit_price: Optional[float], client_id: str) -> Order:
        raise NotImplementedError

    def stop(self, instrument: str, qty: float, stop_price: float, client_id: str) -> Order:
        raise NotImplementedError

    def cancel(self, order_id: str) -> None:
        raise NotImplementedError

    def order(self, order_id: Optional[str] = None, client_id: Optional[str] = None) -> Optional[Order]:
        raise NotImplementedError

    def balances(self) -> Dict[str, float]:
        raise NotImplementedError

    # helpers -------------------------------------------------------------------------
    @staticmethod
    def _json(status: int, body: bytes, where: str) -> dict:
        try:
            d = json.loads(body or b"{}")
        except ValueError:
            raise BrokerError(f"{where}: HTTP {status}, response was not JSON")
        if status >= 400:
            msg = d.get("message") or d.get("error") or d
            raise BrokerError(f"{where}: HTTP {status}: {msg}")
        return d


def round_step(x: float, step: float) -> float:
    """Round DOWN to a multiple of step (never buy or sell more than asked)."""
    if not step:
        return x
    n = int(x / step + 1e-9)
    return round(n * step, 12)
