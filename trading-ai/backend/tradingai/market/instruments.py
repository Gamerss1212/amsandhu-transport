"""Typed instruments: what each market actually is, so money math never treats a futures contract like a share.

Master prompt sections 130, 132, 137, 202, 212, 322-324.

* `Instrument`: one tradable thing, resolved through `InstrumentBook` (no strategy uses a raw ticker string). It names
  its market type, venue, currency, multiplier, tick, quantity step, settlement and unit.
* Money is `Decimal` throughout (`money()`), so a ledger never drifts by float rounding (0.1 + 0.2 == 0.3 here).
* `pnl()` includes the contract multiplier: one ES point is 50 USD per contract, not 1.
* `size_from_risk()` works backwards from an acceptable loss (section 202) and never rounds risk UP: below the minimum
  size it answers 0 (no trade), it never buys one "just to have a position".
* Futures specs are versioned metadata in `data/contract_specs.json` (section 212), each marked `verify_with_broker`:
  before a live order the broker's own contract definition must match (section 322). Nothing here talks to a broker.
* An index is a calculated benchmark (section 130): `INDEX_REFERENCES` lists the instruments that can be traded in its
  place, and `Instrument.trades_as` says which one an order really goes to.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, replace
from decimal import ROUND_DOWN, ROUND_HALF_EVEN, Decimal, InvalidOperation
from enum import Enum
from typing import Dict, Iterable, List, Optional, Tuple, Union

Number = Union[int, str, Decimal]          # never float: build Decimals from strings or ints (money("0.1"))


class MarketType(str, Enum):
    STOCK = "stock"
    ETF = "etf"
    CRYPTO_SPOT = "crypto_spot"
    CRYPTO_PERP = "crypto_perpetual"
    CRYPTO_FUTURE = "crypto_dated_future"
    FX_OTC = "fx_otc"                       # dealer-quoted spot forex: bid/ask from one dealer, financing at rollover
    FX_FUTURE = "fx_future"                 # exchange-traded currency futures (6E, 6B ...): a different product
    FUTURE = "future"                       # index, metals, energy, rates, agriculture futures
    INDEX_REFERENCE = "index_reference"     # a calculated benchmark: never ordered directly


class Settlement(str, Enum):
    SPOT = "spot"                           # shares, coins, OTC FX: you hold the thing itself
    CASH = "cash"
    PHYSICAL = "physical"                   # holding into delivery means making or taking delivery
    NONE = "none"                           # perpetuals (funding instead of expiry), index references


class Unit(str, Enum):
    SHARES = "shares"
    COINS = "coins"
    CONTRACTS = "contracts"
    CURRENCY_UNITS = "currency_units"       # OTC FX position size, in base-currency units
    INDEX_POINTS = "index_points"


UNIT_FOR = {MarketType.STOCK: Unit.SHARES, MarketType.ETF: Unit.SHARES, MarketType.CRYPTO_SPOT: Unit.COINS,
            MarketType.CRYPTO_PERP: Unit.CONTRACTS, MarketType.CRYPTO_FUTURE: Unit.CONTRACTS,
            MarketType.FX_OTC: Unit.CURRENCY_UNITS, MarketType.FX_FUTURE: Unit.CONTRACTS,
            MarketType.FUTURE: Unit.CONTRACTS, MarketType.INDEX_REFERENCE: Unit.INDEX_POINTS}


def money(x: Number) -> Decimal:
    """A Decimal from an int, a string or a Decimal. Floats are refused: 0.1 as a float is not 0.1."""
    if isinstance(x, float):
        raise TypeError("money needs a str, int or Decimal, not a float (use money('0.1'))")
    try:
        return Decimal(x)
    except InvalidOperation as e:
        raise ValueError(f"not a number: {x!r}") from e


@dataclass(frozen=True)
class Instrument:
    instrument_id: str                      # "<venue>:<symbol>", unique in an InstrumentBook
    market_type: MarketType
    symbol: str
    venue: str
    currency: str                           # the currency prices and P&L are quoted in
    multiplier: Decimal = Decimal(1)        # P&L per 1.0 price move per 1 unit of quantity
    tick_size: Decimal = Decimal("0.01")
    quantity_step: Decimal = Decimal(1)
    min_quantity: Decimal = Decimal(1)
    settlement: Settlement = Settlement.SPOT
    base_asset: Optional[str] = None
    quote_asset: Optional[str] = None
    root: Optional[str] = None              # futures root (ES), when this is a futures contract
    contract_month: Optional[str] = None    # "2026-12"
    expiry: Optional[str] = None            # last trading day, ISO date, from the broker's contract definition
    first_notice: Optional[str] = None      # physically settled futures only, from the broker's contract definition
    exchange: Optional[str] = None
    calendar: Optional[str] = None
    trades_as: Optional[str] = None         # INDEX_REFERENCE only: never set; see INDEX_REFERENCES
    data_source: Optional[str] = None
    broker_symbol: Optional[str] = None
    verified_with_broker: bool = False      # set only from a broker's own contract definition (section 322)
    spec_version: Optional[str] = None
    tags: Tuple[str, ...] = field(default_factory=tuple)

    @property
    def unit(self) -> Unit:
        return UNIT_FOR[self.market_type]

    @property
    def tick_value(self) -> Decimal:
        return self.tick_size * self.multiplier

    @property
    def tradable(self) -> bool:
        return self.market_type is not MarketType.INDEX_REFERENCE

    def round_price(self, price: Number) -> Decimal:
        """To the nearest tick (half-even). A strategy's price is never sent with more precision than the venue takes."""
        p = money(price)
        return (p / self.tick_size).quantize(Decimal(1), rounding=ROUND_HALF_EVEN) * self.tick_size

    def round_quantity(self, qty: Number) -> Decimal:
        """Down to the quantity step: rounding a size up would add risk nobody approved."""
        q = money(qty)
        return (q / self.quantity_step).to_integral_value(rounding=ROUND_DOWN) * self.quantity_step


def pnl(inst: Instrument, entry: Number, exit_: Number, quantity: Number, *, fees: Number = 0,
        fx_to_account: Optional[Number] = None, account_currency: Optional[str] = None) -> Decimal:
    """Realized P&L of a position: (exit - entry) x multiplier x quantity - fees, in the instrument's currency, or in
    the account's currency when `account_currency` differs (then `fx_to_account`, the rate at the time of the trade,
    is required: it is never guessed). A negative quantity is a short."""
    if not inst.tradable:
        raise ValueError(f"{inst.instrument_id} is an index reference: trade one of its proxies instead")
    gross = (money(exit_) - money(entry)) * inst.multiplier * money(quantity)
    out = gross - money(fees)
    if account_currency and account_currency != inst.currency:
        if fx_to_account is None:
            raise ValueError(f"P&L in {inst.currency} needs a {inst.currency}->{account_currency} rate for that time")
        out = out * money(fx_to_account)
    return out


def size_from_risk(inst: Instrument, risk_budget: Number, entry: Number, stop: Number, *,
                   cost_per_unit: Number = 0) -> Decimal:
    """Section 202: quantity = risk budget / loss per unit if the stop is hit (price distance x multiplier + costs),
    rounded DOWN to the quantity step. 0 when even the minimum size would risk more than the budget."""
    dist = abs(money(entry) - money(stop))
    if dist == 0:
        raise ValueError("the stop equals the entry: the risk per unit is undefined")
    per_unit = dist * inst.multiplier + money(cost_per_unit)
    q = inst.round_quantity(money(risk_budget) / per_unit)
    return q if q >= inst.min_quantity else Decimal(0)


# ----------------------------------------------------------------------------- forex conventions

def pip_size(inst: Instrument) -> Decimal:
    """0.0001 for most pairs, 0.01 when the quote currency is JPY. OTC FX only."""
    if inst.market_type is not MarketType.FX_OTC:
        raise ValueError("pips apply to OTC forex pairs")
    return Decimal("0.01") if inst.quote_asset == "JPY" else Decimal("0.0001")


def pip_value(inst: Instrument, units: Number) -> Decimal:
    """Value of one pip for `units` of the base currency, in the QUOTE currency."""
    return pip_size(inst) * money(units)


# ----------------------------------------------------------------------------- the book and the contract specs

SPECS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "contract_specs.json")

# Section 130: an index is a calculated number. These are the instruments that can be ordered in its place; an order
# always names one of them, and the app shows which.
INDEX_REFERENCES: Dict[str, List[str]] = {
    "SPX": ["US:SPY", "CME:MES", "CME:ES"],
    "NDX": ["US:QQQ", "CME:MNQ", "CME:NQ"],
    "DJI": ["US:DIA", "CBOT:YM"],
    "RUT": ["US:IWM", "CME:RTY"],
}


def load_specs(path: str = SPECS_PATH) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def future_from_spec(root: str, specs: Optional[dict] = None) -> Instrument:
    """The generic (not yet month-resolved) futures instrument for a root, from the versioned spec file. Unverified:
    `resolve_contract` with the broker's definition is required before an order (section 322)."""
    specs = specs or load_specs()
    s = specs["contracts"].get(root)
    if s is None:
        raise KeyError(f"no contract spec for {root!r}")
    return Instrument(
        instrument_id=f"{s['exchange']}:{root}", market_type=MarketType(s.get("market_type", "future")), symbol=root,
        venue=s["exchange"], exchange=s["exchange"], currency=s["currency"], multiplier=money(s["multiplier"]),
        tick_size=money(s["tick_size"]), quantity_step=Decimal(1), min_quantity=Decimal(1),
        settlement=Settlement(s["settlement"]), root=root, calendar=s.get("calendar"),
        spec_version=specs.get("version"), tags=tuple(s.get("group", "").split()))


def resolve_contract(generic: Instrument, broker_definition: dict) -> Instrument:
    """Section 322: an order goes to an exact contract (exchange, month, expiry, currency, multiplier) that the broker
    defined. Any disagreement with the spec file is refused, never smoothed over."""
    b = broker_definition
    problems = []
    if str(b.get("exchange", "")).upper() != (generic.exchange or "").upper():
        problems.append(f"exchange {b.get('exchange')!r} != {generic.exchange!r}")
    if str(b.get("currency", "")).upper() != generic.currency:
        problems.append(f"currency {b.get('currency')!r} != {generic.currency!r}")
    try:
        if money(str(b.get("multiplier"))) != generic.multiplier:
            problems.append(f"multiplier {b.get('multiplier')!r} != {generic.multiplier}")
    except (ValueError, TypeError):
        problems.append(f"multiplier {b.get('multiplier')!r} is not a number")
    if not b.get("expiry") or not b.get("contract_month"):
        problems.append("the broker gave no expiry or contract month")
    if generic.settlement is Settlement.PHYSICAL and not b.get("first_notice"):
        problems.append("a physically settled contract needs its first notice date")
    if problems:
        raise ValueError(f"{generic.root}: broker contract does not match the spec: " + "; ".join(problems))
    return replace(generic, instrument_id=f"{generic.exchange}:{generic.root}:{b['contract_month']}",
                   contract_month=b["contract_month"], expiry=b["expiry"], first_notice=b.get("first_notice"),
                   broker_symbol=b.get("broker_symbol"), verified_with_broker=True)


class InstrumentBook:
    """Every instrument by id. Strategies and orders ask the book; an unknown id is an error, not a guess."""

    def __init__(self, items: Iterable[Instrument] = ()):
        self._items: Dict[str, Instrument] = {}
        for i in items:
            self.add(i)

    def add(self, inst: Instrument) -> Instrument:
        if inst.instrument_id in self._items and self._items[inst.instrument_id] != inst:
            raise ValueError(f"{inst.instrument_id} is already defined differently")
        self._items[inst.instrument_id] = inst
        return inst

    def get(self, instrument_id: str) -> Instrument:
        try:
            return self._items[instrument_id]
        except KeyError:
            raise KeyError(f"unknown instrument {instrument_id!r}: resolve it through the registry first") from None

    def __contains__(self, instrument_id: str) -> bool:
        return instrument_id in self._items

    def __len__(self) -> int:
        return len(self._items)

    def proxies(self, index: str) -> List[Instrument]:
        """The tradable instruments known for an index reference, in INDEX_REFERENCES order."""
        return [self._items[i] for i in INDEX_REFERENCES.get(index, []) if i in self._items]
