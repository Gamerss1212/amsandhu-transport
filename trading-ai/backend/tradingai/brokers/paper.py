"""The internal paper broker (sections 224, 324-327, 343). SIMULATED money, simulated fills, real market prices.

* A proper ledger (SQLite, Decimal): deposits, fill cash flows, fees, funding. Paper balance = the ledger, never a sum
  of strategy P&L. `invariant()` checks cash = deposits + flows - fees, and equity = cash + marked positions.
* Fills are deliberately a little pessimistic: market orders pay half the modelled spread plus slippage; a fill is
  capped at the cost model's participation share of the last bar's volume (the rest waits for later bars); limit
  orders fill only when the last price trades through the limit.
* Rejections: quantity below the instrument minimum, not enough cash for a spot buy, shorting where the market does
  not allow it (spot crypto, stocks without borrow data), no fresh price.
* Spot (stocks, ETFs, crypto) moves cash by the full notional; futures and FX book only P&L (with the contract
  multiplier and the quote-to-account conversion).
* Durable: orders are found again by client order id after a restart; submitting the same client id twice returns the
  existing order (idempotent), it never creates a second one.
"""

from __future__ import annotations

import json
import threading
import time
from decimal import ROUND_DOWN, Decimal
from typing import Callable, Optional

from tradingai.backtest.costs import CostModel, default_for, half_spread_price
from tradingai.brokers.base import AccountInfo, BrokerAdapter, BrokerError, BrokerFill, BrokerOrder
from tradingai.core.ids import new_id
from tradingai.market.instruments import Instrument, InstrumentBook, MarketType
from tradingai.storage.db import Database, now_ms

SPOT = {MarketType.STOCK, MarketType.ETF, MarketType.CRYPTO_SPOT}
D = Decimal
OPEN_STATES = ("NEW", "SUBMITTED", "PARTIALLY_FILLED")
Quote = Callable[[str], Optional[dict]]      # -> {"price", "ts", "volume", "sigma", "range"} or None


def _s(x: Decimal) -> str:
    """Stored decimal text; an exact zero is always "0" (Decimal('0E-8') would read as an open position)."""
    return "0" if x == 0 else format(x, "f")


def _d(x) -> Decimal:
    return x if isinstance(x, Decimal) else Decimal(str(x))


class PaperBroker(BrokerAdapter):
    name = "paper"
    label = "Paper account (simulated)"
    environments = ("paper",)
    setup = "Nothing to set up: simulated money at real market prices."
    verified = True

    def __init__(self, db: Database, book: InstrumentBook, quote: Quote, account_id: str = "PAPER-1",
                 base_currency: str = "USD", starting_cash: Decimal = D(100_000),
                 costs: Optional[Callable[[Instrument], CostModel]] = None, audit=None):
        super().__init__("paper")
        self.db, self.book, self.quote = db, book, quote
        self.account_id, self.base = account_id, base_currency
        self.costs = costs or default_for
        self.audit = audit or (lambda *a, **k: None)
        self._lock = threading.RLock()
        if not self.db.one("SELECT 1 FROM accounts WHERE account_id=?", (account_id,)):
            with self.db.tx() as c:
                c.execute("INSERT INTO accounts (account_id, broker, environment, label, base_currency, simulated, "
                          "created) VALUES (?,?,?,?,?,?,?)", (account_id, "paper", "paper", "Paper account",
                                                              base_currency, 1, now_ms()))
                c.execute("INSERT INTO ledger (account_id, ts, kind, currency, amount, ref, note) VALUES "
                          "(?,?,?,?,?,?,?)", (account_id, now_ms(), "deposit", base_currency, str(starting_cash),
                                              None, "SIMULATED starting balance"))
        self.connected = True

    # ------------------------------------------------------------------ interface
    def capabilities(self) -> dict:
        return {"stocks": True, "etfs": True, "crypto": True, "forex": True, "futures": True, "paper_mode": True,
                "fractional": True, "shorting": "FX and futures only", "bracket_orders": False,
                "trailing_stops": False, "websocket": False, "historical_data": False, "realtime_data": False,
                "level2": False, "order_modification": False}

    def connect(self) -> dict:
        self.connected = True
        return {"connected": True, "environment": "paper"}

    def health(self) -> dict:
        return {"ok": True, "status": "simulated", "orders_open": len(self.get_open_orders())}

    def get_accounts(self) -> list[AccountInfo]:
        return [self.get_balance()]

    def _cash(self) -> Decimal:
        rows = self.db.query("SELECT amount FROM ledger WHERE account_id=?", (self.account_id,))
        return sum((D(r["amount"]) for r in rows), D(0))

    def get_balance(self) -> AccountInfo:
        cash = self._cash()
        eq, used = cash, D(0)
        for iid, p in self._positions().items():
            inst = self.book.get(iid)
            q = self.quote(iid)
            px = _d(q["price"]) if q else D(p["avg_price"])
            qty = D(p["qty"])
            if inst.market_type in SPOT:
                eq += qty * px
            else:
                eq += (px - D(p["avg_price"])) * qty * inst.multiplier * self._fx(inst, px)
                used += abs(qty) * px * inst.multiplier * self._fx(inst, px) / D(5)
        return AccountInfo(self.account_id, "paper", self.base, eq.quantize(D("0.01")), cash.quantize(D("0.01")),
                           max(D(0), cash - used).quantize(D("0.01")), used.quantize(D("0.01")), True, "SIMULATED",
                           now_ms(), {"shorting": "FX and futures only", "withdrawals": "not applicable"})

    def _positions(self) -> dict:
        return {r["instrument_id"]: r for r in self.db.query(
            "SELECT * FROM positions WHERE account_id=? AND qty != '0'", (self.account_id,))}

    def get_positions(self) -> dict:
        return {k: D(v["qty"]) for k, v in self._positions().items()}

    def positions_detail(self) -> list[dict]:
        out = []
        for iid, p in self._positions().items():
            inst = self.book.get(iid)
            q = self.quote(iid)
            px = _d(q["price"]) if q else None
            qty, avg = D(p["qty"]), D(p["avg_price"])
            unreal = None if px is None else (px - avg) * qty * inst.multiplier * self._fx(inst, px)
            out.append({"instrument_id": iid, "qty": str(qty), "avg_price": str(avg), "price": None if px is None else
                        str(px), "price_ts": q["ts"] if q else None, "unrealized": None if unreal is None else
                        str(unreal.quantize(D("0.01"))), "realized": p["realized"], "currency": p["currency"],
                        "multiplier": str(inst.multiplier), "market_type": inst.market_type.value,
                        "strategy_lots": json.loads(p["strategy_lots"] or "{}"), "simulated": True})
        return out

    def get_open_orders(self) -> list[BrokerOrder]:
        rows = self.db.query(f"SELECT * FROM orders WHERE account_id=? AND status IN ({','.join('?' * len(OPEN_STATES))})",
                             (self.account_id, *OPEN_STATES))
        return [self._bo(r) for r in rows]

    def get_order(self, client_order_id: str) -> Optional[BrokerOrder]:
        r = self.db.one("SELECT * FROM orders WHERE client_order_id=?", (client_order_id,))
        return self._bo(r) if r else None

    def get_fills(self, since_ms: int = 0) -> list[BrokerFill]:
        rows = self.db.query("SELECT * FROM fills WHERE account_id=? AND ts>=? ORDER BY ts", (self.account_id, since_ms))
        return [BrokerFill(r["fill_id"], r["client_order_id"], r["instrument_id"], r["side"], D(r["qty"]),
                           D(r["price"]), D(r["fee"]), r["fee_currency"], r["ts"], r["liquidity"] or "taker")
                for r in rows]

    @staticmethod
    def _bo(r: dict) -> BrokerOrder:
        return BrokerOrder(r["client_order_id"], r["broker_order_id"], r["instrument_id"], r["side"], D(r["qty"]),
                           D(r["filled_qty"]), D(r["avg_fill_price"]) if r["avg_fill_price"] else None, r["status"],
                           r["order_type"], D(r["limit_price"]) if r["limit_price"] else None)

    # ------------------------------------------------------------------ orders
    def submit_order(self, *, client_order_id: str, instrument_id: str, broker_symbol: str = "", side: str,
                     qty: Decimal, order_type: str = "market", limit_price: Optional[Decimal] = None,
                     tif: str = "day", decision_id: Optional[str] = None, strategy_id: Optional[str] = None,
                     decision_price: Optional[Decimal] = None) -> BrokerOrder:
        with self._lock:
            existing = self.get_order(client_order_id)
            if existing is not None:                  # idempotent: a retry returns the same order
                return existing
            inst = self.book.get(instrument_id)
            qty = _d(qty)
            status, reason = "SUBMITTED", None
            q = self.quote(instrument_id)
            pos = D(self._positions().get(instrument_id, {}).get("qty", "0"))
            after = pos + (qty if side == "buy" else -qty)
            if q is None:
                status, reason = "REJECTED", "no fresh price"
            elif qty < inst.min_quantity:
                status, reason = "REJECTED", f"quantity below the minimum {inst.min_quantity}"
            elif after < 0 and inst.market_type in SPOT:
                status, reason = "REJECTED", "shorting is not available for this market in paper trading"
            elif side == "buy" and inst.market_type in SPOT and q and \
                    qty * _d(q["price"]) * D("1.01") > self._cash():
                status, reason = "REJECTED", "not enough cash"
            t = now_ms()
            self.db.execute("INSERT INTO orders (client_order_id, decision_id, strategy_id, account_id, environment, "
                            "instrument_id, side, qty, order_type, limit_price, tif, status, broker_order_id, reason, "
                            "created, updated) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                            (client_order_id, decision_id, strategy_id, self.account_id, "paper", instrument_id, side,
                             str(qty), order_type, None if limit_price is None else str(limit_price), tif, status,
                             new_id("PB"), reason, t, t))
            if status == "SUBMITTED":
                self._try_fill(client_order_id, decision_price)
            return self.get_order(client_order_id)

    def cancel_order(self, client_order_id: str) -> bool:
        with self._lock:
            r = self.db.one("SELECT status FROM orders WHERE client_order_id=?", (client_order_id,))
            if not r or r["status"] not in OPEN_STATES:
                return False
            self.db.execute("UPDATE orders SET status='CANCELLED', updated=? WHERE client_order_id=?",
                            (now_ms(), client_order_id))
            return True

    def process(self) -> int:
        """Called on every engine tick: work open orders against the newest prices (partial fills, limits)."""
        n = 0
        for o in self.get_open_orders():
            if self._try_fill(o.client_order_id, None):
                n += 1
        return n

    def _fx(self, inst: Instrument, px: Decimal) -> Decimal:
        if inst.market_type is MarketType.FX_OTC and inst.quote_asset and inst.quote_asset != self.base:
            return D(1) / px if inst.base_asset == self.base else D(1)
        return D(1)

    def _try_fill(self, cid: str, decision_price: Optional[Decimal]) -> bool:
        with self._lock:
            r = self.db.one("SELECT * FROM orders WHERE client_order_id=?", (cid,))
            if not r or r["status"] not in OPEN_STATES:
                return False
            inst = self.book.get(r["instrument_id"])
            q = self.quote(r["instrument_id"])
            if q is None:
                return False
            last = _d(q["price"])
            side = 1 if r["side"] == "buy" else -1
            if r["order_type"] == "limit":
                lim = D(r["limit_price"])
                if (side > 0 and last > lim) or (side < 0 and last < lim):
                    return False
            remaining = D(r["qty"]) - D(r["filled_qty"])
            cm = self.costs(inst)
            vol = q.get("volume")
            fill_qty = remaining
            if vol and vol > 0:
                cap = (_d(vol) * _d(cm.participation_cap) / inst.quantity_step).to_integral_value(ROUND_DOWN) * \
                    inst.quantity_step
                fill_qty = min(remaining, cap)
            if fill_qty <= 0:
                return False
            hs = _d(half_spread_price(cm, inst, float(last)))
            slip = _d(cm.slippage_frac(price=float(last), bar_range=float(q.get("range") or 0),
                                       qty=float(fill_qty * inst.multiplier),
                                       bar_volume=float((vol or 0) * float(inst.multiplier)),
                                       sigma_bar=float(q.get("sigma") or 0))) * last
            px = last + side * (hs + slip)
            if r["order_type"] == "limit":
                px = min(px, D(r["limit_price"])) if side > 0 else max(px, D(r["limit_price"]))
            px = inst.round_price(px)
            fx = self._fx(inst, px)
            notional = fill_qty * px * inst.multiplier * fx
            fee = (_d(cm.fees(notional=float(notional), contracts=float(fill_qty) if inst.market_type not in SPOT
                              else 0.0))).quantize(D("0.0001"))
            self._book_fill(r, inst, fill_qty if side > 0 else -fill_qty, px, fee, fx, decision_price, last)
            filled = D(r["filled_qty"]) + fill_qty
            avg = ((D(r["avg_fill_price"] or 0) * D(r["filled_qty"]) + px * fill_qty) / filled)
            status = "FILLED" if filled >= D(r["qty"]) else "PARTIALLY_FILLED"
            self.db.execute("UPDATE orders SET filled_qty=?, avg_fill_price=?, status=?, updated=? WHERE "
                            "client_order_id=?", (str(filled), str(avg), status, now_ms(), cid))
            return True

    def _book_fill(self, order: dict, inst: Instrument, signed_qty: Decimal, px: Decimal, fee: Decimal, fx: Decimal,
                   decision_price: Optional[Decimal], arrival: Decimal) -> None:
        iid, acct, t = inst.instrument_id, self.account_id, now_ms()
        p = self.db.one("SELECT * FROM positions WHERE account_id=? AND instrument_id=?", (acct, iid))
        qty0 = D(p["qty"]) if p else D(0)
        avg0 = D(p["avg_price"]) if p else D(0)
        realized0 = D(p["realized"]) if p else D(0)
        lots = json.loads(p["strategy_lots"]) if p else {}
        new_qty = qty0 + signed_qty
        realized = D(0)
        if qty0 != 0 and (qty0 > 0) != (signed_qty > 0):                 # reducing or flipping
            closed = min(abs(signed_qty), abs(qty0))
            realized = (px - avg0) * closed * (1 if qty0 > 0 else -1) * inst.multiplier * fx
        if new_qty == 0:
            avg = D(0)
        elif qty0 == 0 or (qty0 > 0) != (new_qty > 0):
            avg = px
        elif abs(new_qty) > abs(qty0):
            avg = (avg0 * abs(qty0) + px * abs(signed_qty)) / abs(new_qty)
        else:
            avg = avg0
        sid = order.get("strategy_id") or "manual"
        lots[sid] = _s(D(lots.get(sid, "0")) + signed_qty)
        lots = {k: v for k, v in lots.items() if v != "0"}
        fill_id = new_id("F")
        with self.db.tx() as c:
            if inst.market_type in SPOT:
                c.execute("INSERT INTO ledger (account_id, ts, kind, currency, amount, ref, note) VALUES (?,?,?,?,?,?,?)",
                          (acct, t, "fill", self.base, str(-(signed_qty * px * inst.multiplier * fx)), fill_id,
                           f"{order['side']} {abs(signed_qty)} {iid} @ {px}"))
            elif realized != 0:
                c.execute("INSERT INTO ledger (account_id, ts, kind, currency, amount, ref, note) VALUES (?,?,?,?,?,?,?)",
                          (acct, t, "realized", self.base, str(realized), fill_id, f"realized P&L {iid}"))
            if fee:
                c.execute("INSERT INTO ledger (account_id, ts, kind, currency, amount, ref, note) VALUES (?,?,?,?,?,?,?)",
                          (acct, t, "fee", self.base, str(-fee), fill_id, f"fee {iid}"))
            c.execute("INSERT INTO fills (fill_id, client_order_id, account_id, instrument_id, side, qty, price, fee, "
                      "fee_currency, liquidity, environment, ts, decision_price, arrival_mid) VALUES "
                      "(?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (fill_id, order["client_order_id"], acct, iid, order["side"],
                                                        str(abs(signed_qty)), str(px), str(fee), self.base, "taker",
                                                        "paper", t, None if decision_price is None else
                                                        str(decision_price), str(arrival)))
            c.execute("INSERT INTO positions (account_id, instrument_id, qty, avg_price, realized, currency, "
                      "strategy_lots, updated) VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(account_id, instrument_id) DO "
                      "UPDATE SET qty=excluded.qty, avg_price=excluded.avg_price, realized=excluded.realized, "
                      "strategy_lots=excluded.strategy_lots, updated=excluded.updated",
                      (acct, iid, _s(new_qty), _s(avg), _s(realized0 + realized), inst.currency, json.dumps(lots), t))

    # ------------------------------------------------------------------ owner actions and checks
    def set_balance(self, amount: Decimal, by: str) -> dict:
        """Owner-set SIMULATED balance: a ledger adjustment, never counted as profit or loss."""
        amount = _d(amount)
        if amount <= 0:
            raise BrokerError("enter an amount above 0")
        bal = self.get_balance()
        delta = amount - bal.equity
        self.db.execute("INSERT INTO ledger (account_id, ts, kind, currency, amount, ref, note) VALUES (?,?,?,?,?,?,?)",
                        (self.account_id, now_ms(), "adjustment", self.base, str(delta), None,
                         f"SIMULATED balance set to {amount} by {by}"))
        self.audit("paper", f"paper balance set to {amount} by {by}", data={"delta": str(delta)})
        return {"equity": str(self.get_balance().equity), "delta": str(delta)}

    def invariant(self) -> dict:
        """Ledger identity: cash = sum of ledger rows; equity = cash + marked positions. Returns the check."""
        rows = self.db.query("SELECT kind, amount FROM ledger WHERE account_id=?", (self.account_id,))
        by: dict[str, Decimal] = {}
        for r in rows:
            by[r["kind"]] = by.get(r["kind"], D(0)) + D(r["amount"])
        cash = sum(by.values(), D(0))
        fills = self.db.query("SELECT side, qty, price, fee FROM fills WHERE account_id=?", (self.account_id,))
        fees = sum((D(f["fee"]) for f in fills), D(0))
        return {"cash": str(cash), "by_kind": {k: str(v) for k, v in by.items()}, "fees_from_fills": str(fees),
                "fees_in_ledger": str(-by.get("fee", D(0))), "ok": fees == -by.get("fee", D(0))}
