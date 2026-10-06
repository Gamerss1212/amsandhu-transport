"""A05 Ledger & Reconciliation Keeper and A50 paper broker (Phase 3).

- The broker owns its own book, like a real broker account would.
- The ledger rebuilds the book independently from fill reports (idempotent by fill id).
- ``reconcile`` compares the two every cycle; any break halts trading (Tier 1).
Orders decided after the close of day t fill at the open of day t+1, never at the close
that generated the signal (spec section 56).
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Literal

from quantagents.config import CostConfig
from quantagents.market import Bar
from quantagents.schemas import (
    Fill,
    LedgerState,
    OrderIntent,
    OrderSide,
    ReconciliationReport,
)

QTY_EPS = 1e-9


@dataclass
class Position:
    qty: float = 0.0
    avg_price: float = 0.0


class Book:
    """Cash and positions with average-cost accounting."""

    def __init__(self, cash: float) -> None:
        self.cash = cash
        self.positions: dict[str, Position] = {}
        self.realized_pnl = 0.0
        self.fees_paid = 0.0

    def apply(self, fill: Fill) -> None:
        pos = self.positions.setdefault(fill.symbol, Position())
        signed = fill.signed_qty
        self.cash -= signed * fill.price + fill.fee
        self.fees_paid += fill.fee
        if pos.qty == 0 or pos.qty * signed > 0:
            new_qty = pos.qty + signed
            pos.avg_price = (pos.avg_price * abs(pos.qty) + fill.price * abs(signed)) / abs(new_qty)
            pos.qty = new_qty
        else:
            closing = min(abs(signed), abs(pos.qty))
            sign = 1.0 if pos.qty > 0 else -1.0
            self.realized_pnl += closing * (fill.price - pos.avg_price) * sign
            new_qty = pos.qty + signed
            if abs(new_qty) <= QTY_EPS:
                new_qty = 0.0
            elif new_qty * pos.qty < 0:
                pos.avg_price = fill.price
            pos.qty = new_qty
        if pos.qty == 0:
            del self.positions[fill.symbol]

    def quantities(self) -> dict[str, float]:
        return {s: p.qty for s, p in sorted(self.positions.items())}

    def equity(self, prices: Mapping[str, float]) -> float:
        """Cash plus positions marked at ``prices`` (falls back to cost if a price is missing)."""
        value = self.cash
        for symbol, pos in self.positions.items():
            price = prices.get(symbol, math.nan)
            value += pos.qty * (price if math.isfinite(price) else pos.avg_price)
        return value


class Ledger:
    """A05: single source of truth for cash, positions, fills and fees."""

    agent_id = "A05"
    name = "Ledger & Reconciliation Keeper"

    def __init__(self, starting_cash: float) -> None:
        self.starting_cash = starting_cash
        self.book = Book(starting_cash)
        self.fills: list[Fill] = []
        self._seen: set[str] = set()

    def record(self, fill: Fill) -> bool:
        """Apply a fill once. Returns False for a duplicate (idempotent processing)."""
        if fill.fill_id in self._seen:
            return False
        self._seen.add(fill.fill_id)
        self.fills.append(fill)
        self.book.apply(fill)
        return True

    def state(self, prices: Mapping[str, float]) -> LedgerState:
        return LedgerState(
            cash=self.book.cash,
            positions=self.book.quantities(),
            equity=self.book.equity(prices),
            realized_pnl=self.book.realized_pnl,
            fees_paid=self.book.fees_paid,
            n_fills=len(self.fills),
        )


@dataclass(frozen=True)
class PendingOrder:
    intent: OrderIntent
    decision_date: date


class PaperBroker:
    """A50 on a simulated account: fills at the next open with slippage and fees."""

    agent_id = "A50"
    name = "Execution & TCA Agent (paper)"

    def __init__(self, starting_cash: float, costs: CostConfig) -> None:
        self.costs = costs
        self.book = Book(starting_cash)
        self.pending: list[PendingOrder] = []
        self.stops: dict[str, float] = {}
        self.fills: list[Fill] = []
        self.fill_seq = 0

    def submit(self, intents: Sequence[OrderIntent], decision_date: date) -> None:
        self.pending.extend(PendingOrder(intent, decision_date) for intent in intents)

    def _slipped(self, side: OrderSide, price: float) -> float:
        slip = self.costs.slippage_bps / 1e4
        return price * (1.0 + slip) if side is OrderSide.BUY else price * (1.0 - slip)

    def _fill(
        self,
        intent_id: str,
        symbol: str,
        side: OrderSide,
        qty: float,
        price: float,
        day: date,
        kind: Literal["entry", "exit", "stop"],
    ) -> Fill:
        self.fill_seq += 1
        fill = Fill(
            fill_id=f"F{self.fill_seq:06d}",
            intent_id=intent_id,
            symbol=symbol,
            side=side,
            qty=qty,
            price=price,
            fee=qty * price * self.costs.fee_bps / 1e4,
            trade_date=day,
            kind=kind,
        )
        self.book.apply(fill)
        self.fills.append(fill)
        return fill

    def fill_pending(self, opens: Mapping[str, float], fill_date: date) -> list[Fill]:
        """Fill queued orders decided before ``fill_date`` at that day's open."""
        filled: list[Fill] = []
        keep: list[PendingOrder] = []
        for order in self.pending:
            intent = order.intent
            price = opens.get(intent.symbol, math.nan)
            if order.decision_date >= fill_date or not math.isfinite(price) or price <= 0:
                keep.append(order)
                continue
            kind: Literal["entry", "exit"] = "entry" if intent.stop_price is not None else "exit"
            filled.append(
                self._fill(
                    intent.intent_id,
                    intent.symbol,
                    intent.side,
                    intent.qty,
                    self._slipped(intent.side, price),
                    fill_date,
                    kind,
                )
            )
            position = self.book.positions.get(intent.symbol)
            if position is None:
                self.stops.pop(intent.symbol, None)
            elif intent.stop_price is not None:
                self.stops[intent.symbol] = intent.stop_price
        self.pending = keep
        return filled

    def check_stops(self, bars: Mapping[str, Bar], day: date) -> list[Fill]:
        """Trigger resting stops against the day's bar; gaps fill at the open."""
        filled: list[Fill] = []
        for symbol, stop in sorted(self.stops.items()):
            position = self.book.positions.get(symbol)
            bar = bars.get(symbol)
            if position is None or bar is None or not bar.is_finite():
                continue
            if position.qty > 0 and bar.low <= stop:
                price, side = min(bar.open, stop), OrderSide.SELL
            elif position.qty < 0 and bar.high >= stop:
                price, side = max(bar.open, stop), OrderSide.BUY
            else:
                continue
            filled.append(
                self._fill(
                    f"STOP-{symbol}-{day.isoformat()}",
                    symbol,
                    side,
                    abs(position.qty),
                    self._slipped(side, price),
                    day,
                    "stop",
                )
            )
            del self.stops[symbol]
        return filled


def reconcile(
    ledger: Ledger, broker: PaperBroker, cash_tolerance: float = 0.01
) -> ReconciliationReport:
    diffs: list[str] = []
    ours, theirs = ledger.book.quantities(), broker.book.quantities()
    for symbol in sorted(set(ours) | set(theirs)):
        a, b = ours.get(symbol, 0.0), theirs.get(symbol, 0.0)
        if abs(a - b) > QTY_EPS:
            diffs.append(f"{symbol}: ledger {a:g} vs broker {b:g}")
    if abs(ledger.book.cash - broker.book.cash) > cash_tolerance:
        diffs.append(f"cash: ledger {ledger.book.cash:.2f} vs broker {broker.book.cash:.2f}")
    return ReconciliationReport(
        ok=not diffs, diffs=tuple(diffs), ledger_cash=ledger.book.cash, broker_cash=broker.book.cash
    )


class PaperAccount:
    """Ledger + paper broker + equity history, saved as JSON between daily runs."""

    def __init__(self, capital: float, costs: CostConfig) -> None:
        self.capital = capital
        self.ledger = Ledger(capital)
        self.broker = PaperBroker(capital, costs)
        self.equity_history: list[tuple[date, float]] = []

    def record_equity(self, day: date, equity: float) -> None:
        self.equity_history = [(d, e) for d, e in self.equity_history if d != day]
        self.equity_history.append((day, equity))
        self.equity_history.sort()

    def loss_metrics(self, day: date, equity: float) -> tuple[float, float, float]:
        """Daily loss, weekly loss and drawdown in percent (positive numbers are losses)."""
        before = [e for d, e in self.equity_history if d < day]
        week = day.isocalendar()[:2]
        before_week = [e for d, e in self.equity_history if d.isocalendar()[:2] < week]
        daily_base = before[-1] if before else self.capital
        weekly_base = before_week[-1] if before_week else self.capital
        peak = max([self.capital, equity, *(e for _, e in self.equity_history)])
        daily = max(0.0, (daily_base - equity) / daily_base * 100.0)
        weekly = max(0.0, (weekly_base - equity) / weekly_base * 100.0)
        drawdown = max(0.0, (peak - equity) / peak * 100.0)
        return daily, weekly, drawdown

    def to_json(self) -> dict[str, Any]:
        return {
            "capital": self.capital,
            "ledger_fills": [f.model_dump(mode="json") for f in self.ledger.fills],
            "broker_fills": [f.model_dump(mode="json") for f in self.broker.fills],
            "broker_cash_start": self.capital,
            "fill_seq": self.broker.fill_seq,
            "pending": [
                {
                    "intent": p.intent.model_dump(mode="json"),
                    "decision_date": p.decision_date.isoformat(),
                }
                for p in self.broker.pending
            ],
            "stops": dict(sorted(self.broker.stops.items())),
            "equity_history": [[d.isoformat(), e] for d, e in self.equity_history],
        }

    @classmethod
    def from_json(cls, data: Mapping[str, Any], costs: CostConfig) -> PaperAccount:
        account = cls(float(data["capital"]), costs)
        for raw in data["ledger_fills"]:
            account.ledger.record(Fill.model_validate(raw))
        for raw in data["broker_fills"]:
            fill = Fill.model_validate(raw)
            account.broker.book.apply(fill)
            account.broker.fills.append(fill)
        account.broker.fill_seq = int(data["fill_seq"])
        account.broker.pending = [
            PendingOrder(
                OrderIntent.model_validate(p["intent"]), date.fromisoformat(p["decision_date"])
            )
            for p in data["pending"]
        ]
        account.broker.stops = {str(k): float(v) for k, v in data["stops"].items()}
        account.equity_history = [
            (date.fromisoformat(d), float(e)) for d, e in data["equity_history"]
        ]
        return account

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps(self.to_json(), indent=2), encoding="utf-8")
        tmp.replace(path)

    @classmethod
    def load_or_new(cls, path: Path, capital: float, costs: CostConfig) -> PaperAccount:
        if path.exists():
            return cls.from_json(json.loads(path.read_text(encoding="utf-8")), costs)
        return cls(capital, costs)
