"""Paper account with a balance you can change at any time.

The balance is changed through cash-flow events (deposit, withdraw, set balance), each logged
with the equity before and after. Performance is time-weighted (TWR): the return of each
interval between cash flows is chained, so adding or removing money never shows up as profit
or loss.

Sizing uses capital slots: each bot sizes its trades as if it had equity / slots to itself
(default 20 slots). The portfolio risk layer then caps total exposure, so a fleet of 250 bots
cannot collectively borrow money it does not have.

Any balance works: a small account is split into fewer slots (each at least `min_slot`, $25 by
default), so its orders stay above the venues' minimum sizes instead of being refused as dust.
From 20 x $25 = $500 upward every slot is in use. The number of slots in use is recomputed from
the equity at every order, so it grows and shrinks with the account.
"""

from __future__ import annotations

import threading
from typing import Dict, List, Optional, Tuple

from mab.models import now_ms

PKey = Tuple[str, str, str]      # (bot_id, venue, instrument)


class Account:
    MIN_SLOT = 25.0                     # smallest slot worth trading: venue minimums are $1 to about $5

    def __init__(self, balance: float = 100_000.0, slots: int = 20, currency: str = "USD"):
        self.cash = float(balance)
        self.currency = currency
        self.slots = max(1, int(slots))
        self.min_slot = self.MIN_SLOT
        self.positions: Dict[PKey, dict] = {}
        self.marks: Dict[Tuple[str, str], Tuple[float, int]] = {}      # (venue, instrument) -> (price, time)
        self.realized = 0.0
        self.fees = 0.0
        self.flows: List[dict] = [{"time": now_ms(), "kind": "initial", "amount": float(balance),
                                   "equity_before": 0.0, "equity_after": float(balance), "note": "opening balance"}]
        self.twr_index = 1.0
        self.twr_anchor = float(balance)
        self.lock = threading.RLock()

    # ------------------------------------------------------------------ valuation
    def mark(self, venue: str, instrument: str, price: float, t: Optional[int] = None):
        with self.lock:
            self.marks[(venue, instrument)] = (price, t or now_ms())

    def position_value(self, p: dict) -> float:
        px = self.marks.get((p["venue"], p["instrument"]), (p["avg_price"], 0))[0]
        return p["qty"] * px

    def equity(self) -> float:
        with self.lock:
            return self.cash + sum(self.position_value(p) for p in self.positions.values())

    def exposure(self) -> dict:
        with self.lock:
            gross = 0.0
            net_by_inst: Dict[str, float] = {}
            for p in self.positions.values():
                v = self.position_value(p)
                gross += abs(v)
                k = f"{p['venue']}:{p['instrument']}"
                net_by_inst[k] = net_by_inst.get(k, 0.0) + v
            return {"gross": gross, "net_by_instrument": net_by_inst, "open_positions": len(self.positions)}

    def slots_in_use(self, equity: Optional[float] = None) -> int:
        eq = max(0.0, self.equity() if equity is None else equity)
        if not self.min_slot:
            return self.slots
        return max(1, min(self.slots, int(eq // self.min_slot)))

    def slot_equity(self) -> float:
        eq = max(0.0, self.equity())
        return eq / self.slots_in_use(eq)

    def twr(self) -> float:
        """Time-weighted return since the account was opened."""
        with self.lock:
            eq = self.equity()
            return self.twr_index * (eq / self.twr_anchor if self.twr_anchor > 0 else 1.0) - 1.0

    # ------------------------------------------------------------------ cash flows
    def _flow(self, kind: str, amount: float, note: str) -> dict:
        before = self.equity()
        if self.twr_anchor > 0:
            self.twr_index *= before / self.twr_anchor
        self.cash += amount
        after = self.equity()
        self.twr_anchor = after
        rec = {"time": now_ms(), "kind": kind, "amount": amount, "equity_before": before, "equity_after": after,
               "note": note}
        self.flows.append(rec)
        return rec

    def deposit(self, amount: float, note: str = "") -> dict:
        if amount <= 0:
            raise ValueError("deposit must be positive")
        with self.lock:
            return self._flow("deposit", float(amount), note)

    def withdraw(self, amount: float, note: str = "") -> dict:
        if amount <= 0:
            raise ValueError("withdrawal must be positive")
        with self.lock:
            if amount >= self.equity():
                raise ValueError(f"the account holds {self.equity():,.2f} {self.currency}; withdraw less than that")
            # money tied up in open positions stays there: the bots close their own trades, and new
            # entries wait until there is free cash again
            return self._flow("withdraw", -float(amount), note)

    def set_balance(self, equity: float, note: str = "") -> dict:
        """Make total equity equal `equity` by an adjusting cash flow."""
        if not equity > 0:
            raise ValueError("the balance must be more than 0")
        with self.lock:
            # any amount is allowed. If it is below the value of open positions, cash goes negative for
            # a while: the bots keep managing (and closing) their own trades and new entries wait for
            # free cash. Nothing is closed on the operator's behalf.
            diff = float(equity) - self.equity()
            return self._flow("set_balance", diff, note or f"balance set to {equity:,.2f}")

    # ------------------------------------------------------------------ fills
    def apply_fill(self, bot_id: str, venue: str, instrument: str, side: str, qty: float, price: float,
                   fee: float, t: Optional[int] = None, meta: Optional[dict] = None) -> dict:
        """Cash accounting: buying spends cash, selling (including short sales) receives it."""
        with self.lock:
            sgn = 1 if side == "buy" else -1
            key = (bot_id, venue, instrument)
            p = self.positions.get(key)
            self.cash -= sgn * qty * price + fee
            self.fees += fee
            realized = 0.0
            if p is None:
                p = self.positions[key] = {"bot_id": bot_id, "venue": venue, "instrument": instrument,
                                           "qty": sgn * qty, "avg_price": price, "opened": t or now_ms(),
                                           **(meta or {})}
            else:
                q0 = p["qty"]
                q1 = q0 + sgn * qty
                if q0 * sgn >= 0:                                  # adding
                    p["avg_price"] = (abs(q0) * p["avg_price"] + qty * price) / abs(q1)
                else:                                              # reducing / flipping
                    closed = min(abs(q0), qty)
                    realized = closed * (price - p["avg_price"]) * (1 if q0 > 0 else -1)
                    if abs(q1) > 1e-12 and q1 * q0 < 0:
                        p["avg_price"] = price
                        p["opened"] = t or now_ms()
                p["qty"] = q1
                if abs(q1) <= 1e-12:
                    del self.positions[key]
            self.realized += realized
            self.mark(venue, instrument, price, t)
            return {"realized": realized, "cash": self.cash}

    # ------------------------------------------------------------------ persistence
    def to_state(self) -> dict:
        with self.lock:
            return {"cash": self.cash, "currency": self.currency, "slots": self.slots,
                    "positions": [dict(p) for p in self.positions.values()],
                    "marks": [[v, i, p, t] for (v, i), (p, t) in self.marks.items()],
                    "realized": self.realized, "fees": self.fees, "flows": self.flows[-500:],
                    "twr_index": self.twr_index, "twr_anchor": self.twr_anchor}

    @classmethod
    def from_state(cls, st: dict) -> "Account":
        a = cls(0.0, st.get("slots", 20), st.get("currency", "USD"))
        a.cash = st["cash"]
        a.positions = {(p["bot_id"], p["venue"], p["instrument"]): p for p in st.get("positions", [])}
        a.marks = {(v, i): (p, t) for v, i, p, t in st.get("marks", [])}
        a.realized, a.fees = st.get("realized", 0.0), st.get("fees", 0.0)
        a.flows = st.get("flows", [])
        a.twr_index, a.twr_anchor = st.get("twr_index", 1.0), st.get("twr_anchor", a.equity() or 1.0)
        return a

    def summary(self) -> dict:
        eq = self.equity()
        ex = self.exposure()
        return {"equity": eq, "cash": self.cash, "currency": self.currency, "realized_pnl": self.realized,
                "fees": self.fees, "open_positions": ex["open_positions"], "gross_exposure": ex["gross"],
                "gross_exposure_pct": 100 * ex["gross"] / eq if eq else None, "twr": self.twr(),
                "slots": self.slots, "slots_in_use": self.slots_in_use(eq), "slot_equity": self.slot_equity(),
                "deposits": sum(f["amount"] for f in self.flows if f["kind"] in ("initial", "deposit", "set_balance")
                                and f["amount"] > 0),
                "withdrawals": -sum(f["amount"] for f in self.flows if f["amount"] < 0)}
