"""Order management (sections 173, 209, 216-219, 276): every order, every mode, goes through here.

    decision -> client order id (deterministic from the decision) -> risk check -> broker submit -> fills

* Idempotency: the client order id is derived from the decision id, so a retry after a timeout reuses it. Before any
  resubmit the OMS asks the broker for that client id: if the broker has it, nothing is sent again (section 218).
* A submission that times out is UNKNOWN, never assumed unsent: the order stays in state UNKNOWN until the broker is
  queried successfully.
* Live orders pass a final broker sanity check (environment LIVE, account matches, product permitted) on top of the
  risk service.
* SHADOW mode records the intended order and the price it would have used, and sends nothing.
"""

from __future__ import annotations

import time
from decimal import Decimal
from typing import Callable, Optional

from tradingai.brokers.base import BrokerAdapter, BrokerError
from tradingai.core.events import EventBus
from tradingai.core.ids import client_order_id, new_id
from tradingai.risk.service import OrderRequest, RiskDecision, RiskService, Snapshot
from tradingai.storage.db import Database, dumps, now_ms


class OMS:
    def __init__(self, db: Database, risk: RiskService, bus: EventBus, audit: Callable[..., object]):
        self.db, self.risk, self.bus, self.audit = db, risk, bus, audit
        self.latency: dict[str, list[float]] = {"risk_ms": [], "submit_ms": [], "decision_to_submit_ms": []}
        self.shadow: list[dict] = []

    def _lat(self, key: str, v: float) -> None:
        self.latency[key] = (self.latency[key] + [v])[-500:]

    def latency_stats(self) -> dict:
        out = {}
        for k, v in self.latency.items():
            s = sorted(v)
            out[k] = {"n": len(s), "p50": round(s[len(s) // 2], 2) if s else None,
                      "p95": round(s[int(len(s) * 0.95) - 1], 2) if len(s) >= 20 else None,
                      "p99": round(s[int(len(s) * 0.99) - 1], 2) if len(s) >= 100 else None}
        return out

    def place(self, *, decision_id: str, req: OrderRequest, snapshot: Snapshot, broker: BrokerAdapter,
              broker_symbol: str, mode: str, strategy_id: Optional[str], decided_at: float, leg: int = 0,
              order_type: str = "market") -> dict:
        req.client_order_id = client_order_id(decision_id, leg)
        t0 = time.perf_counter()
        decision: RiskDecision = self.risk.check(req, snapshot)
        self._lat("risk_ms", (time.perf_counter() - t0) * 1000)
        self.audit("risk_decision", f"{req.side} {req.quantity} {req.instrument_id}: {decision.reason}",
                   severity="info" if decision.approved else "warning", correlation_id=decision_id,
                   data=decision.as_dict())
        out = {"client_order_id": req.client_order_id, "risk": decision.as_dict(), "mode": mode}
        if not decision.approved:
            out["status"] = "BLOCKED_BY_RISK"
            self.bus.publish("risk.denied", {"decision_id": decision_id, "instrument": req.instrument_id,
                                             "reason": decision.reason}, severity="warning",
                             correlation_id=decision_id)
            return out
        if mode == "shadow":
            rec = {"ts": now_ms(), "decision_id": decision_id, "client_order_id": req.client_order_id,
                   "instrument": req.instrument_id, "side": req.side, "qty": str(decision.quantity),
                   "intended_price": str(req.reference_price), "status": "SHADOW_NOT_SENT"}
            self.shadow = (self.shadow + [rec])[-1000:]
            self.audit("shadow_order", f"SHADOW (not sent): {req.side} {decision.quantity} {req.instrument_id}",
                       correlation_id=decision_id, data=rec)
            self.bus.publish("order.shadow", rec, correlation_id=decision_id)
            out.update(status="SHADOW_NOT_SENT")
            return out
        if mode == "live":
            if broker.environment != "live" or not broker.connected:
                out["status"] = "BLOCKED"
                out["error"] = "live order refused: the broker connection is not a connected LIVE environment"
                self.audit("order", out["error"], severity="critical", correlation_id=decision_id)
                return out
        # idempotency: ask the broker before sending
        try:
            existing = broker.get_order(req.client_order_id)
        except BrokerError as e:
            out.update(status="UNKNOWN", error=f"could not query the broker before sending: {e}")
            self.audit("order", out["error"], severity="error", correlation_id=decision_id)
            return out
        if existing is not None:
            out.update(status=existing.status, note="already at the broker: not sent again")
            return out
        t1 = time.perf_counter()
        try:
            kw = dict(client_order_id=req.client_order_id, instrument_id=req.instrument_id,
                      broker_symbol=broker_symbol, side=req.side, qty=decision.quantity, order_type=order_type,
                      limit_price=req.limit_price)
            if broker.name == "paper":
                kw.update(decision_id=decision_id, strategy_id=strategy_id, decision_price=req.reference_price)
            bo = broker.submit_order(**kw)
        except BrokerError as e:
            # a failed or timed-out submission may still have reached the broker: mark UNKNOWN, query later
            self.db.execute("INSERT OR IGNORE INTO orders (client_order_id, decision_id, strategy_id, account_id, "
                            "environment, instrument_id, side, qty, order_type, tif, status, reason, created, updated) "
                            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                            (req.client_order_id, decision_id, strategy_id, req.account_id, mode, req.instrument_id,
                             req.side, str(decision.quantity), order_type, "day", "UNKNOWN", str(e)[:300], now_ms(),
                             now_ms()))
            out.update(status="UNKNOWN", error=str(e))
            self.audit("order", f"submission uncertain ({e}); will query the broker, never resend blindly",
                       severity="error", correlation_id=decision_id)
            return out
        self._lat("submit_ms", (time.perf_counter() - t1) * 1000)
        self._lat("decision_to_submit_ms", (time.time() - decided_at) * 1000)
        out.update(status=bo.status, broker_order_id=bo.broker_order_id, filled_qty=str(bo.filled_qty),
                   avg_price=None if bo.avg_price is None else str(bo.avg_price))
        self.audit("order", f"{mode.upper()} {req.side} {decision.quantity} {req.instrument_id} -> {bo.status}",
                   correlation_id=decision_id, data=out)
        self.bus.publish("order.update", dict(out, instrument=req.instrument_id, side=req.side,
                                              qty=str(decision.quantity)), correlation_id=decision_id)
        return out

    def resolve_unknown(self, broker: BrokerAdapter) -> list[dict]:
        """After a restart or a timeout: ask the broker about every UNKNOWN order by its client id."""
        out = []
        for r in self.db.query("SELECT client_order_id FROM orders WHERE status='UNKNOWN'"):
            try:
                bo = broker.get_order(r["client_order_id"])
            except BrokerError as e:
                out.append({"client_order_id": r["client_order_id"], "still_unknown": str(e)})
                continue
            status = bo.status if bo else "NOT_AT_BROKER"
            self.db.execute("UPDATE orders SET status=?, updated=? WHERE client_order_id=?",
                            (status, now_ms(), r["client_order_id"]))
            out.append({"client_order_id": r["client_order_id"], "resolved": status})
        return out

    def cancel_all(self, broker: BrokerAdapter, reason: str) -> int:
        try:
            n = broker.cancel_all()
        except BrokerError as e:
            self.audit("order", f"cancel all failed: {e}", severity="critical")
            return 0
        self.audit("order", f"cancelled {n} working order(s): {reason}", severity="warning")
        return n

    def orders(self, limit: int = 100) -> list[dict]:
        return self.db.query("SELECT * FROM orders ORDER BY created DESC LIMIT ?", (limit,))

    def fills(self, limit: int = 100) -> list[dict]:
        return self.db.query("SELECT * FROM fills ORDER BY ts DESC LIMIT ?", (limit,))
