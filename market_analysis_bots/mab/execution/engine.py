"""The execution engine: every order, in every mode, goes through here.

Order states
    NEW               written to the database, not sent yet (write-ahead: a crash can never leave an order
                      this program does not know about)
    SUBMITTING        being sent now
    ACKED             the provider accepted it and it is working
    PARTIALLY_FILLED  some filled, the rest still working
    FILLED            completely filled
    CANCEL_REQUESTED  a cancel was sent; waiting for the provider to confirm
    CANCELED          canceled (possibly after a partial fill: filled_qty says how much)
    REJECTED          the provider refused it
    EXPIRED           the provider expired it
    UNKNOWN           the send may or may not have reached the provider (timeout, dropped connection, restart
                      during the send). Resolved ONLY by looking the order up by its client id; never resent
    LOST              looked up repeatedly for over a minute and the provider says it does not exist
    NOT_SENT          blocked before sending (emergency stop, live not authorised, rate limit, mode mismatch,
                      provider unreachable before anything was sent)

Guarantees (each has a test in tests/test_execution.py):
* Duplicate protection: the client order id is derived from the decision (deployment, intent, purpose,
  attempt), so the same decision can never create a second order, even across restarts.
* An uncertain send is never repeated; it is looked up by client id until found or confirmed absent.
* A restart turns NEW into NOT_SENT and SUBMITTING into UNKNOWN, then resolves them with the provider.
* Fills are recorded from the provider's cumulative filled quantity, so repeated polls cannot double count
  and a partial fill is recorded as it happens.
* A paper order can only go to a paper connection, a live order only to a live connection; live orders that
  would add risk also need the owner's live authorisation, checked here as the last line of defence.
* While the emergency stop is on, only orders that reduce a position (exits, protective stops) can be sent.
* Each connection has a token-bucket rate limit below the provider's documented limit.

Every transition is appended to order_events and to the audit log (kind "order" / "fill").
"""

from __future__ import annotations

import json
import logging
import threading
import time
from typing import Callable, Dict, List, Optional

from mab.execution.base import (ACKED, CANCELED, EXPIRED, FILLED, PARTIALLY_FILLED, PENDING_CANCEL, REJECTED,
                                NotSent, OrderRejected, OrderRequest, OrderStatus, OutcomeUnknown, Provider,
                                ProviderError, TokenBucket, client_order_id)

log = logging.getLogger("mab.execution")

NEW, SUBMITTING, UNKNOWN, CANCEL_REQUESTED, LOST, NOT_SENT = (
    "NEW", "SUBMITTING", "UNKNOWN", "CANCEL_REQUESTED", "LOST", "NOT_SENT")
TERMINAL = {FILLED, CANCELED, REJECTED, EXPIRED, LOST, NOT_SENT}
OPEN = {NEW, SUBMITTING, ACKED, PARTIALLY_FILLED, CANCEL_REQUESTED, UNKNOWN}
LOST_AFTER_S = 60.0
EPS = 1e-12
MODE_ENV = {"paper": "paper", "live": "live", "demo": "demo"}
STAGE = {SUBMITTING: "order_submitted", ACKED: "broker_ack", PARTIALLY_FILLED: "partially_filled", FILLED: "filled",
         CANCEL_REQUESTED: "cancel_requested", CANCELED: "canceled", REJECTED: "rejected", EXPIRED: "expired",
         UNKNOWN: "status_unknown", LOST: "lost", NOT_SENT: "not_sent"}
SEVERITY = {REJECTED: "warning", UNKNOWN: "warning", LOST: "error", NOT_SENT: "warning"}


def now_ms() -> int:
    return int(time.time() * 1000)


class ExecutionError(RuntimeError):
    pass


class ExecutionEngine:
    def __init__(self, storage, resolve: Callable[[str], Provider], *,
                 kill_switch: Optional[Callable[[], Optional[str]]] = None,
                 live_allowed: Optional[Callable[[str], tuple]] = None,
                 rate_timeout: float = 5.0, sleep=time.sleep, clock=time.time):
        self.st = storage
        self.resolve = resolve                     # connection id -> Provider (raises if not available)
        self.kill_switch = kill_switch or (lambda: None)
        self.live_allowed = live_allowed or (lambda connection_id: (False, "live trading is not authorised"))
        self.rate_timeout = rate_timeout
        self.sleep, self.clock = sleep, clock
        self.lock = threading.RLock()
        self.inflight: set = set()
        self.buckets: Dict[str, TokenBucket] = {}
        self.not_found: Dict[str, int] = {}
        self.stats = {"placed": 0, "duplicates": 0, "rejected": 0, "unknown": 0, "lost": 0, "not_sent": 0,
                      "fills": 0, "ack_ms": []}

    # ------------------------------------------------------------------ records
    def get(self, cid: str) -> Optional[dict]:
        r = self.st.query("SELECT * FROM broker_orders WHERE client_order_id=?", (cid,))
        return self._row(r[0]) if r else None

    @staticmethod
    def _row(r: dict) -> dict:
        r = dict(r)
        for k in ("flags", "raw"):
            if r.get(k):
                try:
                    r[k] = json.loads(r[k])
                except ValueError:
                    pass
        r["flags"] = r.get("flags") or {}
        return r

    def orders(self, *, states=None, connection_id=None, deployment_id=None, limit: int = 500) -> List[dict]:
        where, args = [], []
        if states:
            where.append("state IN (%s)" % ",".join("?" * len(states)))
            args += list(states)
        if connection_id:
            where.append("connection_id=?")
            args.append(connection_id)
        if deployment_id:
            where.append("deployment_id=?")
            args.append(deployment_id)
        q = "SELECT * FROM broker_orders" + (" WHERE " + " AND ".join(where) if where else "") + \
            " ORDER BY created DESC LIMIT ?"
        return [self._row(r) for r in self.st.query(q, tuple(args + [limit]))]

    def open_orders(self, **kw) -> List[dict]:
        return self.orders(states=sorted(OPEN), **kw)

    def fills(self, cid: str) -> List[dict]:
        return self.st.query("SELECT * FROM broker_fills WHERE client_order_id=? ORDER BY ts", (cid,))

    def _audit(self, row: dict, kind: str, stage: str, summary: str, severity: str = "info", payload=None):
        try:
            self.st.audit(kind, summary, stage=stage, severity=severity, mode=row.get("mode"), bot_id=row.get("bot_id"),
                          deployment_id=row.get("deployment_id"), symbol=row.get("symbol"),
                          connection_id=row.get("connection_id"), correlation_id=row.get("correlation_id"),
                          order_id=row.get("client_order_id"), payload=payload)
        except Exception as e:                                          # noqa: BLE001 - the order record is what counts
            log.warning("audit write failed: %s", e)

    def _describe(self, row: dict) -> str:
        px = row.get("limit_price") or row.get("stop_price")
        return (f"{row['side']} {row['qty']:.8g} {row['symbol']} {row['order_type']}"
                + (f" @ {px:.8g}" if px else "") + f" ({row.get('purpose') or 'order'}, {row['mode']})")

    def _transition(self, cid: str, to: str, detail: str = "", **fields) -> dict:
        with self.lock:
            row = self.get(cid)
            if row is None:
                raise ExecutionError(f"unknown order {cid}")
            frm = row["state"]
            if frm in TERMINAL and to != frm and not (frm == LOST and to in OPEN | TERMINAL):
                log.warning("order %s: ignoring %s -> %s (already final)", cid, frm, to)
                return row
            t = now_ms()
            fields = dict(fields, state=to, updated=t)
            if to in TERMINAL:
                fields["closed"] = t
            if "flags" in fields and isinstance(fields["flags"], dict):
                fields["flags"] = json.dumps(fields["flags"])
            if "raw" in fields and isinstance(fields["raw"], dict):
                fields["raw"] = json.dumps(fields["raw"], default=str)[:20000]
            cols = ", ".join(f"{k}=?" for k in fields)
            self.st.write(f"UPDATE broker_orders SET {cols} WHERE client_order_id=?", (*fields.values(), cid))
            if to != frm or detail:
                self.st.write("INSERT INTO order_events (client_order_id, ts, from_state, to_state, detail) VALUES (?,?,?,?,?)",
                              (cid, t, frm, to, detail[:2000]))
            new = self.get(cid)
        if to != frm:
            summ = f"{STAGE.get(to, to.lower()).replace('_', ' ')}: {self._describe(new)}" + (f" - {detail}" if detail else "")
            self._audit(new, "order", STAGE.get(to, to.lower()), summ, SEVERITY.get(to, "info"),
                        {"from": frm, "to": to, "detail": detail, "broker_order_id": new.get("broker_order_id"),
                         "filled_qty": new.get("filled_qty"), "avg_price": new.get("avg_price"), "fees": new.get("fees"),
                         "limit_price": new.get("limit_price"), "stop_price": new.get("stop_price"),
                         "tif": new.get("tif"), "reduce_only": bool(new.get("reduce_only"))})
        return new

    # ------------------------------------------------------------------ placing
    def bucket(self, connection_id: str, provider: Provider) -> TokenBucket:
        b = self.buckets.get(connection_id)
        if b is None:
            cap, per = provider.rate
            b = self.buckets[connection_id] = TokenBucket(cap, per, sleep=self.sleep)
        return b

    def place(self, *, connection_id: str, mode: str, purpose: str, symbol: str, side: str, order_type: str,
              qty: float, intent_id: str, deployment_id: str = None, bot_id: str = None, attempt: int = 0,
              limit_price: float = None, stop_price: float = None, tif: str = "gtc", reduce_only: bool = False,
              ref_price: float = None, correlation_id: str = None, wait: float = 0.0) -> dict:
        """Create (write-ahead), check, rate-limit and send one order. Returns the order row; row["duplicate"]
        is True when this decision already had an order (nothing new was sent)."""
        cid = client_order_id(deployment_id or bot_id or connection_id, intent_id, purpose, attempt)
        with self.lock:
            existing = self.get(cid)
            if existing is not None or cid in self.inflight:
                self.stats["duplicates"] += 1
                row = existing or {"client_order_id": cid, "mode": mode, "bot_id": bot_id, "deployment_id": deployment_id,
                                   "symbol": symbol, "connection_id": connection_id, "correlation_id": correlation_id}
                self._audit(row, "order", "duplicate_blocked",
                            f"duplicate blocked: this decision already has order {cid} ({(existing or {}).get('state', 'in flight')});"
                            " nothing was sent again", "warning", {"intent_id": intent_id, "purpose": purpose})
                return dict(existing or row, duplicate=True)
            self.inflight.add(cid)
            t = now_ms()
            self.st.write("INSERT INTO broker_orders (client_order_id, connection_id, mode, deployment_id, bot_id, intent_id,"
                          " correlation_id, purpose, symbol, side, order_type, tif, qty, limit_price, stop_price, reduce_only,"
                          " state, ref_price, created, updated) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                          (cid, connection_id, mode, deployment_id, bot_id, intent_id, correlation_id or intent_id, purpose,
                           symbol, side, order_type, tif, float(qty), limit_price, stop_price, int(bool(reduce_only)), NEW,
                           ref_price, t, t))
        try:
            row = self._send(cid, connection_id, mode, reduce_only)
        finally:
            with self.lock:
                self.inflight.discard(cid)
        if wait and row["state"] not in TERMINAL:
            row = self.wait_final(cid, wait)
        return row

    def _block(self, cid: str, why: str) -> dict:
        self.stats["not_sent"] += 1
        return self._transition(cid, NOT_SENT, why, reason=why)

    def _send(self, cid: str, connection_id: str, mode: str, reduce_only: bool) -> dict:
        row = self.get(cid)
        if row["qty"] is None or row["qty"] <= 0:
            return self._block(cid, "quantity must be more than zero")
        if row["side"] not in ("buy", "sell"):
            return self._block(cid, f"unknown side {row['side']!r}")
        try:
            provider = self.resolve(connection_id)
        except Exception as e:                                          # noqa: BLE001
            return self._block(cid, f"connection {connection_id} is not available: {e}")
        want_env = MODE_ENV.get(mode)
        if want_env is None or provider.environment != want_env:
            return self._block(cid, f"a {mode} order cannot go to a {provider.environment} connection")
        halt = self.kill_switch()
        if halt and not reduce_only:
            return self._block(cid, f"emergency stop is on ({halt}): only orders that reduce a position are sent")
        if mode == "live" and not reduce_only:
            ok, why = self.live_allowed(connection_id)
            if not ok:
                return self._block(cid, f"live trading not authorised: {why}")
        if not self.bucket(connection_id, provider).acquire(self.rate_timeout):
            return self._block(cid, "rate limit: the connection's request budget is used up; not sent")
        req = OrderRequest(cid, row["symbol"], row["side"], row["order_type"], row["qty"], row["limit_price"],
                           row["stop_price"], row["tif"] or "gtc", bool(row["reduce_only"]), row["ref_price"])
        self._transition(cid, SUBMITTING, "", attempts=int(row.get("attempts") or 0) + 1, submitted=now_ms())
        t0 = time.monotonic()
        try:
            st = provider.submit(req)
        except OrderRejected as e:
            self.stats["rejected"] += 1
            return self._transition(cid, REJECTED, str(e), reason=str(e)[:500])
        except NotSent as e:
            return self._block(cid, f"not sent: {e}")
        except OutcomeUnknown as e:
            self.stats["unknown"] += 1
            self._transition(cid, UNKNOWN, f"send outcome unknown ({e}); looking it up by client id, never resending",
                             reason=str(e)[:500])
            return self._resolve_unknown(cid, tries=3)
        except ProviderError as e:
            self.stats["rejected"] += 1
            return self._transition(cid, REJECTED, f"refused: {e}", reason=str(e)[:500])
        self.stats["placed"] += 1
        self.stats["ack_ms"] = (self.stats["ack_ms"] + [(time.monotonic() - t0) * 1000])[-200:]
        return self._apply(cid, st)

    # ------------------------------------------------------------------ provider status -> our record
    def _apply(self, cid: str, st: OrderStatus) -> dict:
        with self.lock:
            row = self.get(cid)
            if row is None:
                raise ExecutionError(f"unknown order {cid}")
            old_q, new_q = float(row["filled_qty"] or 0), float(st.filled_qty or 0)
            fields = {}
            if st.broker_order_id and st.broker_order_id != row.get("broker_order_id"):
                fields["broker_order_id"] = st.broker_order_id
            if new_q > old_q + EPS:
                dq = new_q - old_q
                if st.avg_price is None:
                    px = row.get("limit_price") or row.get("ref_price") or 0.0
                elif row.get("avg_price") and old_q > 0:
                    px = (st.avg_price * new_q - row["avg_price"] * old_q) / dq
                else:
                    px = st.avg_price
                dfee = max(0.0, float(st.fees or 0) - float(row["fees"] or 0))
                ref = row.get("ref_price")
                slip = None
                if ref and px:
                    slip = ((px / ref - 1) if row["side"] == "buy" else (ref / px - 1)) * 1e4
                fid = f"{cid}#{new_q:.10g}"
                self.st.write("INSERT OR IGNORE INTO broker_fills (fill_id, client_order_id, connection_id, mode, deployment_id,"
                              " bot_id, symbol, side, qty, price, fee, fee_currency, liquidity, ts, simulated, ref_price,"
                              " slippage_bps, raw) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                              (fid, cid, row["connection_id"], row["mode"], row.get("deployment_id"), row.get("bot_id"),
                               row["symbol"], row["side"], dq, px, dfee, st.fee_currency, st.liquidity,
                               st.updated or now_ms(), int(bool(st.simulated)), ref, slip,
                               json.dumps({"model": st.model}) if st.model else None))
                self.stats["fills"] += 1
                fields.update(filled_qty=new_q, avg_price=st.avg_price if st.avg_price is not None else px,
                              fees=float(st.fees or 0), fee_currency=st.fee_currency)
                part = new_q < float(row["qty"]) - 1e-9
                self._audit(dict(row, **fields), "fill", "partial_fill" if part else "fill",
                            f"{'partial fill' if part else 'fill'}: {row['side']} {dq:.8g} {row['symbol']} @ {px:.8g}"
                            + (f", fee {dfee:.6g} {st.fee_currency}".rstrip() if dfee else "")
                            + (f", slippage {slip:+.1f} bps vs decision price" if slip is not None else "")
                            + (" (simulated)" if st.simulated else "") + f" [{row['mode']}]",
                            payload={"fill_id": fid, "qty": dq, "price": px, "fee": dfee, "cumulative": new_q,
                                     "order_qty": row["qty"], "ref_price": ref, "slippage_bps": slip,
                                     "simulated": bool(st.simulated), "model": st.model, "liquidity": st.liquidity})
            to = {PENDING_CANCEL: CANCEL_REQUESTED}.get(st.state, st.state)
            if to == ACKED and new_q > EPS:
                to = PARTIALLY_FILLED
            if row["state"] == CANCEL_REQUESTED and to in (ACKED, PARTIALLY_FILLED):
                to = CANCEL_REQUESTED                               # still waiting for the cancel to land
            if to in (ACKED,) and row.get("acked") is None:
                fields["acked"] = now_ms()
            if st.reason and to in (REJECTED, CANCELED, EXPIRED):
                fields["reason"] = st.reason[:500]
            fields["raw"] = st.raw or {}
            if to == row["state"]:
                if fields:
                    raw = fields.pop("raw", None)
                    if fields:
                        cols = ", ".join(f"{k}=?" for k in fields)
                        self.st.write(f"UPDATE broker_orders SET {cols}, updated=? WHERE client_order_id=?",
                                      (*fields.values(), now_ms(), cid))
                    if raw:
                        self.st.write("UPDATE broker_orders SET raw=? WHERE client_order_id=?",
                                      (json.dumps(raw, default=str)[:20000], cid))
                return self.get(cid)
            detail = st.reason if to in (REJECTED, CANCELED, EXPIRED) else ""
            if to == ACKED and row.get("acked") is None:
                detail = f"broker order id {st.broker_order_id}"
            return self._transition(cid, to, detail, **fields)

    # ------------------------------------------------------------------ uncertain orders
    def _lookup(self, row: dict) -> Optional[OrderStatus]:
        p = self.resolve(row["connection_id"])
        if row.get("broker_order_id"):
            return p.get_order(broker_order_id=row["broker_order_id"])
        return p.get_order(client_order_id=row["client_order_id"])

    def _resolve_unknown(self, cid: str, tries: int = 3, gap_s: float = 1.0) -> dict:
        row = self.get(cid)
        for k in range(tries):
            try:
                st = self._lookup(row)
            except ProviderError as e:                   # the lookup failed: that says nothing about the order
                log.info("lookup of %s failed: %s", cid, e)
                if k + 1 < tries:
                    self.sleep(gap_s)
                continue
            if st is not None:
                self.not_found.pop(cid, None)
                flags = row.get("flags") or {}
                if row["state"] == LOST:
                    self._audit(row, "order", "adopted", f"order {cid} was found after being marked lost; tracking it again",
                                "error")
                out = self._apply(cid, st)
                if flags.get("cancel_wanted") and out["state"] not in TERMINAL:
                    return self.cancel(cid, flags.get("cancel_reason") or "cancel requested while unconfirmed")
                return out
            self.not_found[cid] = self.not_found.get(cid, 0) + 1
            if k + 1 < tries:
                self.sleep(gap_s)
        row = self.get(cid)
        age = (now_ms() - (row.get("submitted") or row.get("created") or now_ms())) / 1000
        if row["state"] == UNKNOWN and self.not_found.get(cid, 0) >= 3 and age >= LOST_AFTER_S:
            self.stats["lost"] += 1
            return self._transition(cid, LOST, f"the provider has no order with this client id after {age:.0f}s and "
                                               f"{self.not_found[cid]} lookups; it was never placed")
        return row

    # ------------------------------------------------------------------ cancel / refresh / wait
    def cancel(self, cid: str, reason: str = "cancel requested") -> dict:
        row = self.get(cid)
        if row is None:
            raise ExecutionError(f"unknown order {cid}")
        if row["state"] in TERMINAL:
            return row
        if row["state"] in (NEW,):
            return self._block(cid, f"canceled before sending: {reason}")
        if not row.get("broker_order_id"):
            flags = dict(row.get("flags") or {}, cancel_wanted=True, cancel_reason=reason)
            self.st.write("UPDATE broker_orders SET flags=? WHERE client_order_id=?", (json.dumps(flags), cid))
            self._audit(row, "order", "cancel_pending", f"cancel for {cid} waits until the provider confirms the order "
                                                        "exists (its send outcome is unknown)", "warning")
            return self._resolve_unknown(cid, tries=1)
        row = self._transition(cid, CANCEL_REQUESTED, reason)
        try:
            p = self.resolve(row["connection_id"])
            p.cancel(row["broker_order_id"])
        except (OrderRejected, ProviderError) as e:
            log.info("cancel %s: %s", cid, e)                     # often: it filled or was canceled meanwhile
        return self.refresh(cid)

    def refresh(self, cid: str) -> dict:
        row = self.get(cid)
        if row is None or row["state"] in TERMINAL - {LOST}:
            return row
        if row["state"] in (UNKNOWN, LOST) or (row["state"] == SUBMITTING and not row.get("broker_order_id")):
            if row["state"] == SUBMITTING:
                row = self._transition(cid, UNKNOWN, "status after sending was not recorded; looking it up")
            return self._resolve_unknown(cid, tries=1)
        try:
            st = self._lookup(row)
        except ProviderError as e:
            log.info("refresh %s: %s", cid, e)
            return row
        if st is None:
            return self._transition(cid, UNKNOWN, "the provider does not know this order id; looking it up by client id")
        return self._apply(cid, st)

    def wait_final(self, cid: str, timeout: float = 10.0, poll: float = 0.5) -> dict:
        deadline = self.clock() + timeout
        row = self.get(cid)
        while row is not None and row["state"] not in TERMINAL and self.clock() < deadline:
            self.sleep(poll)
            row = self.refresh(cid)
        return row

    # ------------------------------------------------------------------ restart recovery and sync
    def recover(self) -> dict:
        """At start: nothing unsent is sent late, nothing possibly-sent is sent again."""
        out = {"not_sent": 0, "unknown": 0, "resolved": 0}
        for row in self.orders(states=[NEW]):
            self._block(row["client_order_id"], "the program stopped before this order was sent; it was not sent")
            out["not_sent"] += 1
        for row in self.orders(states=[SUBMITTING]):
            self._transition(row["client_order_id"], UNKNOWN, "the program stopped while sending; checking with the provider")
            out["unknown"] += 1
        res = self.sync()
        out["resolved"] = res["updated"]
        return out

    def sync(self, connection_id: Optional[str] = None) -> dict:
        """Refresh every open order from its provider (fills, cancels, expiries that happened meanwhile)."""
        n, errors = 0, []
        for row in self.orders(states=[ACKED, PARTIALLY_FILLED, CANCEL_REQUESTED, UNKNOWN], connection_id=connection_id):
            try:
                new = self.refresh(row["client_order_id"])
                if new and (new["state"] != row["state"] or new["filled_qty"] != row["filled_qty"]):
                    n += 1
            except Exception as e:                                      # noqa: BLE001
                errors.append(f"{row['client_order_id']}: {e}")
        return {"updated": n, "errors": errors}

    def record_simulated(self, *, connection_id: str, mode: str, purpose: str, symbol: str, side: str, qty: float,
                         price: float, fee: float, intent_id: str, deployment_id: str = None, bot_id: str = None,
                         order_type: str = "stop", ref_price: float = None, correlation_id: str = None,
                         model: str = "", liquidity: str = "taker") -> dict:
        """A simulator's resting order (stop or target) that filled inside a bar: recorded like any order."""
        cid = client_order_id(deployment_id or bot_id or connection_id, intent_id, purpose, 0)
        if self.get(cid) is not None:
            return dict(self.get(cid), duplicate=True)
        t = now_ms()
        self.st.write("INSERT INTO broker_orders (client_order_id, connection_id, mode, deployment_id, bot_id, intent_id,"
                      " correlation_id, purpose, symbol, side, order_type, tif, qty, stop_price, reduce_only, state,"
                      " ref_price, created, updated, submitted) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                      (cid, connection_id, mode, deployment_id, bot_id, intent_id, correlation_id or intent_id, purpose,
                       symbol, side, order_type, "gtc", qty, ref_price, 1, ACKED, ref_price, t, t, t))
        st = OrderStatus("sim-" + cid[-12:], cid, symbol, side, order_type, qty, FILLED, qty, price, fee, "", "",
                         t, liquidity, True, model)
        return self._apply(cid, st)

    def health(self) -> dict:
        counts = {r["state"]: r["n"] for r in self.st.query("SELECT state, COUNT(*) AS n FROM broker_orders GROUP BY state")}
        acks = sorted(self.stats["ack_ms"])
        return {"orders_by_state": counts, "open": sum(v for k, v in counts.items() if k in OPEN),
                "ack_ms_p50": acks[len(acks) // 2] if acks else None,
                "ack_ms_p95": acks[min(len(acks) - 1, int(0.95 * len(acks)))] if acks else None,
                "rate_limits": {k: b.usage() for k, b in self.buckets.items()},
                "stats": {k: v for k, v in self.stats.items() if k != "ack_ms"}}
