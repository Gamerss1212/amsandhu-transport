"""The broker adapter standard (sections 179-181, 284). Every broker or exchange implements these methods.

An adapter is VERIFIED only after its acceptance test has passed against the provider's real paper/demo (or live)
environment with the owner's own credentials; until then its status says UNVERIFIED and the page says what it needs
(REQUIRES CONNECTION). Capabilities are detected from the provider where it reports them, never assumed.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional


class BrokerError(RuntimeError):
    pass


class RequiresConnection(BrokerError):
    """The operation needs credentials, a running gateway or a library this installation does not have."""


@dataclass
class AccountInfo:
    account_id_masked: str
    environment: str                 # paper / live
    base_currency: str
    equity: Optional[Decimal]
    cash: Optional[Decimal]
    buying_power: Optional[Decimal]
    margin_used: Optional[Decimal] = None
    simulated: bool = False
    source: str = ""                 # "LIVE BROKER DATA" or "SIMULATED"
    as_of: int = 0
    permissions: dict = field(default_factory=dict)


@dataclass
class BrokerOrder:
    client_order_id: str
    broker_order_id: Optional[str]
    instrument_id: str
    side: str
    qty: Decimal
    filled_qty: Decimal
    avg_price: Optional[Decimal]
    status: str
    order_type: str = "market"
    limit_price: Optional[Decimal] = None


@dataclass
class BrokerFill:
    fill_id: str
    client_order_id: str
    instrument_id: str
    side: str
    qty: Decimal
    price: Decimal
    fee: Decimal
    fee_currency: str
    ts: int
    liquidity: str = "taker"


CAPABILITIES = ("stocks", "etfs", "crypto", "forex", "futures", "paper_mode", "fractional", "shorting",
                "bracket_orders", "trailing_stops", "websocket", "historical_data", "realtime_data", "level2",
                "order_modification")


class BrokerAdapter(ABC):
    name: str = ""
    label: str = ""
    environments: tuple[str, ...] = ("paper",)
    needs: tuple[str, ...] = ()              # credential fields
    setup: str = ""                           # what the owner must do, in plain words
    verified: bool = False

    def __init__(self, environment: str = "paper", credentials: Optional[dict] = None):
        if environment not in self.environments:
            raise BrokerError(f"{self.label} has no {environment} environment")
        self.environment = environment
        self.credentials = credentials or {}
        self.connected = False
        self.last_error: Optional[str] = None

    def status(self) -> str:
        if self.connected:
            return "connected"
        if self.last_error:
            return "error"
        return "disconnected"

    @abstractmethod
    def capabilities(self) -> dict: ...
    @abstractmethod
    def connect(self) -> dict: ...
    def disconnect(self) -> None:
        self.connected = False
    @abstractmethod
    def health(self) -> dict: ...
    @abstractmethod
    def get_accounts(self) -> list[AccountInfo]: ...
    @abstractmethod
    def get_balance(self) -> AccountInfo: ...
    @abstractmethod
    def get_positions(self) -> dict: ...
    @abstractmethod
    def get_open_orders(self) -> list[BrokerOrder]: ...
    @abstractmethod
    def get_fills(self, since_ms: int = 0) -> list[BrokerFill]: ...
    def get_instruments(self) -> list[dict]:
        raise RequiresConnection(f"{self.label}: instrument discovery needs a connection")
    def get_market_data_permissions(self) -> dict:
        return {}
    @abstractmethod
    def submit_order(self, *, client_order_id: str, instrument_id: str, broker_symbol: str, side: str, qty: Decimal,
                     order_type: str = "market", limit_price: Optional[Decimal] = None,
                     tif: str = "day") -> BrokerOrder: ...
    def modify_order(self, client_order_id: str, **changes) -> BrokerOrder:
        raise BrokerError(f"{self.label}: order modification not supported here")
    @abstractmethod
    def cancel_order(self, client_order_id: str) -> bool: ...
    def cancel_all(self) -> int:
        n = 0
        for o in self.get_open_orders():
            n += 1 if self.cancel_order(o.client_order_id) else 0
        return n
    @abstractmethod
    def get_order(self, client_order_id: str) -> Optional[BrokerOrder]: ...
    def stream_orders(self):
        raise RequiresConnection(f"{self.label}: streaming needs a connection")
    def stream_positions(self):
        raise RequiresConnection(f"{self.label}: streaming needs a connection")
    def stream_market_data(self):
        raise RequiresConnection(f"{self.label}: streaming needs a connection")

    def reconcile(self, local_positions: dict, local_open: set[str]) -> dict:
        """Broker truth vs the local ledger. Any difference -> RECONCILIATION_REQUIRED (never guessed away)."""
        problems = []
        try:
            bpos = self.get_positions()
            bopen = {o.client_order_id for o in self.get_open_orders()}
        except BrokerError as e:
            return {"ok": False, "problems": [f"could not read the broker: {e}"]}
        for k in set(bpos) | set(local_positions):
            a, b = Decimal(str(local_positions.get(k, 0))), Decimal(str(bpos.get(k, 0)))
            if a != b:
                problems.append(f"{k}: local {a} vs broker {b}")
        for cid in local_open - bopen:
            problems.append(f"order {cid} open locally but not at the broker")
        for cid in bopen - local_open:
            problems.append(f"order {cid} open at the broker but unknown locally")
        return {"ok": not problems, "problems": problems}

    def describe(self) -> dict:
        return {"broker": self.name, "label": self.label, "environment": self.environment, "status": self.status(),
                "verified": self.verified, "needs": list(self.needs), "setup": self.setup,
                "capabilities": self.capabilities(), "last_error": self.last_error,
                "badge": "SIMULATED" if self.name == "paper" else ("LIVE BROKER DATA" if self.connected else
                                                                   "REQUIRES CONNECTION")}
