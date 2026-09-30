"""Order routing for one deployment: how a bot's entry or exit becomes orders, and what it then holds.

Broker connections (Alpaca paper or live, Kraken, NDAX):
* entries are capped-price limit orders (a few basis points through the provider's own ask) sent
  immediate-or-cancel, never an unbounded market buy; US stocks trade whole shares, because a protective
  stop that survives the day (good-till-canceled) needs whole shares at Alpaca;
* right after a fill, a protective stop is placed ON THE PROVIDER (stop, or stop-limit where the provider
  requires it, e.g. Alpaca crypto), so the position is protected even if this computer is off; if it cannot
  be placed, the position is sold at once and the deployment is stopped with an alert;
* exits cancel the protective stop first (or book it if it already filled), then sell what the provider
  says is sellable in up to three attempts (two capped limits, then a market order); an exit that still
  leaves something unsold re-protects the remainder and raises a critical alert;
* prices come from the provider's own market in its own currency; the bot's stop is converted with the ratio
  of the provider's price to the bot's data price (a USD-priced bot can trade a CAD market), and a ratio
  outside 0.5-2.0 means the markets do not match: nothing is sent.

Simulated connections (paper, demo): market orders through the simulator; stops and targets are watched
by the bot's trade manager on completed bars and recorded as simulated fills.

The position record (exec_positions) is updated only from confirmed fills.
"""

from __future__ import annotations

import logging
import time
from typing import Callable, Dict, List, Optional

from mab.execution.base import Provider, ProviderError
from mab.execution.engine import FILLED, TERMINAL, ExecutionEngine, now_ms

log = logging.getLogger("mab.router")
ENTRY_WAIT_S, EXIT_WAIT_S = 10.0, 10.0
STOP_LIMIT_GAP = 0.02            # stop-limit protective stops: limit this far below the trigger (fills in a fast drop)


def _round_down(x: float, step: float) -> float:
    if not step:
        return x
    return round(int(x / step + 1e-9) * step, 12)


class Router:
    def __init__(self, engine: ExecutionEngine, storage, resolve: Callable[[str], Provider],
                 alert: Optional[Callable[[str, str, str, dict], None]] = None, slippage_bps: float = 30.0):
        self.engine = engine
        self.st = storage
        self.resolve = resolve
        self.alert = alert or (lambda level, kind, msg, dep: log.warning("%s %s: %s", level, kind, msg))
        self.slip = slippage_bps / 1e4

    # ------------------------------------------------------------------ position records
    def position(self, deployment_id: str) -> Optional[dict]:
        r = self.st.query("SELECT * FROM exec_positions WHERE deployment_id=?", (deployment_id,))
        return r[0] if r and (r[0]["qty"] or 0) > 0 and r[0]["status"] != "closed" else None

    def positions(self, connection_id: str = None) -> List[dict]:
        q = "SELECT * FROM exec_positions WHERE status != 'closed' AND qty > 0"
        return self.st.query(q + (" AND connection_id=?" if connection_id else ""), (connection_id,) if connection_id else ())

    def _save_pos(self, dep: dict, **f):
        f = dict(f, updated=now_ms())
        cur = self.st.query("SELECT deployment_id FROM exec_positions WHERE deployment_id=?", (dep["deployment_id"],))
        if cur:
            cols = ", ".join(f"{k}=?" for k in f)
            self.st.write(f"UPDATE exec_positions SET {cols} WHERE deployment_id=?", (*f.values(), dep["deployment_id"]))
        else:
            base = {"deployment_id": dep["deployment_id"], "bot_id": dep["bot_id"], "connection_id": dep["connection_id"],
                    "mode": dep["mode"], "managed": 1}
            base.update(f)
            cols = ", ".join(base)
            self.st.write(f"INSERT INTO exec_positions ({cols}) VALUES ({','.join('?' * len(base))})", tuple(base.values()))

    def _audit(self, dep: dict, stage: str, summary: str, severity: str = "info", payload=None, corr=None, symbol=None):
        try:
            self.st.audit("position", summary, stage=stage, severity=severity, mode=dep["mode"], bot_id=dep["bot_id"],
                          deployment_id=dep["deployment_id"], connection_id=dep["connection_id"], symbol=symbol,
                          correlation_id=corr, payload=payload)
        except Exception as e:                                          # noqa: BLE001
            log.warning("audit: %s", e)

    # ------------------------------------------------------------------ entry
    def enter(self, dep: dict, *, symbol: str, side: int, qty: float, ref_price: float, stop: Optional[float],
              target: Optional[float], intent_id: str, correlation_id: str = None, max_notional: float = None) -> dict:
        """Open a position for this deployment. Returns {"status": filled | partial | none | skipped | error | closed,
        "qty", "avg_price" and "fee" in the bot's price currency, ...}."""
        corr = correlation_id or intent_id
        if self.position(dep["deployment_id"]) is not None:
            return {"status": "skipped", "reason": "this deployment already holds a position"}
        if side <= 0:
            return {"status": "skipped", "reason": "spot long-only: no short selling"}
        try:
            p = self.resolve(dep["connection_id"])
        except Exception as e:                                          # noqa: BLE001
            return {"status": "skipped", "reason": f"connection unavailable: {e}"}
        if p.simulated:
            return self._enter_sim(dep, p, symbol, qty, ref_price, stop, target, intent_id, corr, max_notional)
        return self._enter_broker(dep, p, symbol, qty, ref_price, stop, target, intent_id, corr, max_notional)

    def _enter_sim(self, dep, p, symbol, qty, ref, stop, target, intent_id, corr, max_notional):
        if max_notional and qty * ref > max_notional:
            qty = max_notional / ref
        o = self.engine.place(connection_id=dep["connection_id"], mode=dep["mode"], purpose="entry", symbol=symbol,
                              side="buy", order_type="market", qty=qty, intent_id=intent_id,
                              deployment_id=dep["deployment_id"], bot_id=dep["bot_id"], tif="ioc", ref_price=ref,
                              correlation_id=corr, wait=ENTRY_WAIT_S)
        if o.get("duplicate") and o["state"] not in TERMINAL:
            return {"status": "pending", "reason": f"order {o['client_order_id']} still {o['state']}", "order": o}
        if not o.get("filled_qty"):
            return {"status": "none", "reason": o.get("reason") or f"not filled ({o['state']})", "order": o}
        self._save_pos(dep, symbol=symbol, broker_symbol=symbol, side=1, qty=o["filled_qty"], avg_price=o["avg_price"],
                       fees=o["fees"], opened=now_ms(), entry_order=o["client_order_id"], stop_price=stop,
                       stop_order=None, target_price=target, status="open", ratio=1.0)
        part = o["filled_qty"] < qty - 1e-9
        self._audit(dep, "position_opened", f"position opened: long {o['filled_qty']:.8g} {symbol} @ {o['avg_price']:.8g}"
                    + (f"; stop {stop:.8g} (watched by the bot on completed bars)" if stop else "")
                    + (" (partial fill of the order)" if part else ""), payload={"qty": o["filled_qty"], "avg_price": o["avg_price"],
                                                                                  "stop": stop, "target": target, "requested": qty},
                    corr=corr, symbol=symbol)
        return {"status": "partial" if part else "filled", "qty": o["filled_qty"], "avg_price": o["avg_price"],
                "fee": o["fees"], "order": o}

    def _enter_broker(self, dep, p: Provider, symbol, qty, ref, stop, target, intent_id, corr, max_notional):
        try:
            inst = p.instrument(symbol)
            q = p.quote(symbol)
        except ProviderError as e:
            return {"status": "skipped", "reason": f"{p.label} cannot trade {symbol}: {e}"}
        if not inst.get("tradable", True):
            return {"status": "skipped", "reason": f"{symbol} is not tradable on {p.label}"}
        ask = q.get("ask") or q.get("last")
        if not ask or ask <= 0:
            return {"status": "skipped", "reason": f"no current price for {symbol} on {p.label}"}
        ratio = ask / ref
        if not 0.5 < ratio < 2.0:
            return {"status": "skipped", "reason": f"{p.label} price {ask:.8g} does not match the bot's {ref:.8g}"}
        if not stop or stop >= ref:
            return {"status": "skipped", "reason": "no valid protective stop below the entry"}
        stop_b = stop * ratio
        notional = qty * ask
        if max_notional:
            notional = min(notional, max_notional)
        limit = ask * (1 + self.slip)
        bq = notional / limit
        whole = inst.get("asset_class") == "us_equity"
        bq = float(int(bq)) if whole else _round_down(bq, inst.get("qty_step") or 0.0)
        if bq <= 0 or bq < (inst.get("min_qty") or 0) or bq * ask < (inst.get("min_notional") or 0):
            why = "less than one share (a protective stop that lasts past today needs whole shares)" if whole else \
                "below the provider's minimum order size"
            return {"status": "skipped", "reason": f"order size {bq:.8g} {symbol}: {why}"}
        o = self.engine.place(connection_id=dep["connection_id"], mode=dep["mode"], purpose="entry", symbol=symbol,
                              side="buy", order_type="limit", qty=bq, limit_price=limit, tif="ioc", intent_id=intent_id,
                              deployment_id=dep["deployment_id"], bot_id=dep["bot_id"], ref_price=ask,
                              correlation_id=corr, wait=ENTRY_WAIT_S)
        if o["state"] not in TERMINAL:
            o = self.engine.cancel(o["client_order_id"], "entry not filled in time; remainder canceled")
            o = self.engine.wait_final(o["client_order_id"], 5.0)
        filled = float(o.get("filled_qty") or 0)
        if o["state"] not in TERMINAL and not filled:
            self.alert("critical", "entry_unresolved", f"{dep['bot_id']}: entry order {o['client_order_id']} is {o['state']}; "
                       "new entries for this deployment are blocked until it is resolved", dep)
            return {"status": "error", "reason": f"entry order status {o['state']}", "order": o, "block": True}
        if not filled:
            return {"status": "none", "reason": o.get("reason") or f"not filled ({o['state']})", "order": o}
        held = filled
        try:                                     # fees taken in the bought asset (Alpaca crypto) shrink what is held
            s = p.sellable(symbol)
            if s is not None and 0 < s < filled:
                held = s
        except ProviderError:
            pass
        avg = o["avg_price"] or limit
        entry_fee = (o["fees"] or 0.0) + (filled - held) * avg        # a fee paid in coins is a cost like any other
        o = dict(o, fees=entry_fee)
        self._save_pos(dep, symbol=symbol, broker_symbol=inst.get("broker_symbol"), side=1, qty=held, avg_price=avg,
                       fees=entry_fee, opened=now_ms(), entry_order=o["client_order_id"], stop_price=stop_b,
                       stop_order=None, target_price=target * ratio if target else None, status="open", ratio=ratio)
        self._audit(dep, "position_opened", f"position opened on {p.label}: long {held:.8g} {inst.get('broker_symbol')} @ {avg:.8g}",
                    payload={"qty": held, "filled": filled, "avg_price": avg, "ratio": ratio, "stop": stop_b}, corr=corr,
                    symbol=symbol)
        st = self._place_stop(dep, p, symbol, held, stop_b, intent_id, corr, attempt=0)
        if st is None:
            self.alert("critical", "protective_stop_failed", f"{dep['bot_id']}: the protective stop could not be placed "
                       f"on {p.label}; selling the position now", dep)
            res = self.exit(dep, ref_price=ref, reason="protective stop could not be placed", intent_id=intent_id,
                            correlation_id=corr, market=True)
            return {"status": "closed", "reason": "protective stop failed; position sold", "exit": res, "stop_deployment": True}
        return {"status": "partial" if filled < bq - 1e-9 else "filled", "qty": held / 1.0, "avg_price": avg / ratio,
                "fee": (o["fees"] or 0) / ratio, "broker_price": avg, "broker_fee": o["fees"], "ratio": ratio, "order": o,
                "stop_order": st["client_order_id"]}

    @staticmethod
    def stop_kind(p: Provider, symbol: str) -> str:
        caps = p.capabilities() or {}
        kind = caps.get("protective_stop", "stop")
        by = caps.get("protective_stop_by_class")
        if by:
            try:
                kind = by.get(p.instrument(symbol).get("asset_class"), kind)
            except ProviderError:
                pass
        return kind

    def _place_stop(self, dep, p: Provider, symbol, qty, stop, intent_id, corr, attempt: int) -> Optional[dict]:
        kind = self.stop_kind(p, symbol)
        o = self.engine.place(connection_id=dep["connection_id"], mode=dep["mode"], purpose="protective_stop",
                              symbol=symbol, side="sell", order_type="stop_limit" if kind == "stop_limit" else "stop",
                              qty=qty, stop_price=stop, limit_price=stop * (1 - STOP_LIMIT_GAP) if kind == "stop_limit" else None,
                              tif="gtc", reduce_only=True, intent_id=intent_id, attempt=attempt,
                              deployment_id=dep["deployment_id"], bot_id=dep["bot_id"], ref_price=stop,
                              correlation_id=corr)
        if o["state"] in ("REJECTED", "NOT_SENT", "LOST", "CANCELED", "EXPIRED") or (o["state"] == "UNKNOWN" and not o.get("broker_order_id")):
            return None
        self._save_pos(dep, stop_order=o["client_order_id"], stop_price=stop)
        self._audit(dep, "protective_stop", f"protective stop resting on {p.label}: sell {qty:.8g} if price falls to {stop:.8g}",
                    payload={"order": o["client_order_id"], "type": o["order_type"], "stop": stop, "qty": qty}, corr=corr,
                    symbol=symbol)
        return o

    # ------------------------------------------------------------------ exit
    def exit(self, dep: dict, *, ref_price: float, reason: str, intent_id: str, correlation_id: str = None,
             market: bool = False) -> dict:
        corr = correlation_id or intent_id
        pos = self.position(dep["deployment_id"])
        if pos is None:
            return {"status": "none", "reason": "no open position"}
        p = self.resolve(dep["connection_id"])
        ratio = pos.get("ratio") or 1.0
        if pos.get("stop_order"):
            so = self.engine.refresh(pos["stop_order"])
            if so and so["state"] not in TERMINAL:
                so = self.engine.cancel(pos["stop_order"], f"exit: {reason}")
                so = self.engine.wait_final(pos["stop_order"], 5.0)
            if so and so.get("filled_qty"):
                if so["filled_qty"] >= pos["qty"] * 0.999:
                    return self._book(dep, pos, so["filled_qty"], so["avg_price"], so["fees"], "protective stop filled",
                                      corr, [so])
                pos = dict(pos, qty=pos["qty"] - so["filled_qty"])
            if so and so["state"] not in TERMINAL:
                self.alert("critical", "stop_cancel_unconfirmed", f"{dep['bot_id']}: the protective stop's cancel is not "
                           "confirmed; not selling now to avoid selling twice", dep)
                return {"status": "error", "reason": "protective stop cancel not confirmed", "block": True}
        qty = pos["qty"]
        try:
            s = p.sellable(pos["symbol"])
            if s is not None and not p.simulated:
                qty = min(qty, s)
        except ProviderError:
            pass
        sold, cost, fees, orders = 0.0, 0.0, 0.0, []
        for k in range(1, 4):
            rest = qty - sold
            if rest <= qty * 1e-6:
                break
            limit, otype = None, "market"
            if not p.simulated and not market and k < 3:
                try:
                    q = p.quote(pos["symbol"])
                    bid = q.get("bid") or q.get("last")
                except ProviderError:
                    bid = None
                if bid:
                    limit, otype = bid * (1 - self.slip), "limit"
            o = self.engine.place(connection_id=dep["connection_id"], mode=dep["mode"], purpose="exit", symbol=pos["symbol"],
                                  side="sell", order_type=otype, qty=rest, limit_price=limit,
                                  tif="ioc" if otype == "limit" else ("ioc" if p.simulated else "gtc"), reduce_only=True,
                                  intent_id=intent_id, attempt=k, deployment_id=dep["deployment_id"], bot_id=dep["bot_id"],
                                  ref_price=ref_price * ratio, correlation_id=corr, wait=EXIT_WAIT_S)
            if o["state"] not in TERMINAL:
                o = self.engine.cancel(o["client_order_id"], "exit attempt not filled in time")
                o = self.engine.wait_final(o["client_order_id"], 5.0)
            orders.append(o)
            if o.get("filled_qty"):
                sold += o["filled_qty"]
                cost += o["filled_qty"] * (o["avg_price"] or ref_price * ratio)
                fees += o["fees"] or 0
        if sold < qty * 0.999 and p.simulated and qty - sold > 0:
            rest = qty - sold
            px = ref_price * (1 - 2 * self.slip)
            o = self.engine.record_simulated(connection_id=dep["connection_id"], mode=dep["mode"], purpose="flatten",
                                             symbol=pos["symbol"], side="sell", qty=rest, price=px,
                                             fee=0.0, intent_id=intent_id, deployment_id=dep["deployment_id"],
                                             bot_id=dep["bot_id"], order_type="market", ref_price=ref_price,
                                             correlation_id=corr, model="fallback: the simulator's book walk could not fill "
                                             "the exit; remainder closed at the last price with 2x assumed slippage")
            try:                                          # keep the simulated account in step with the fallback fill
                sim = self.resolve(dep["connection_id"])
                v, s_ = sim.split(pos["symbol"])
                sim.acct.apply_fill("account", v, s_, "sell", rest, px, 0.0)
                sim._save()
            except Exception as e:                        # noqa: BLE001
                log.warning("fallback exit accounting: %s", e)
            orders.append(o)
            sold += rest
            cost += rest * px
        if sold <= 0:
            self.alert("critical", "exit_failed", f"{dep['bot_id']}: exit ({reason}) did not fill; the position is still open", dep)
            if not p.simulated:
                self._reprotect(dep, p, pos, qty, intent_id, corr)
            return {"status": "error", "reason": "exit did not fill", "orders": orders}
        avg = cost / sold
        if sold < qty * 0.999:
            left = qty - sold
            self._save_pos(dep, qty=left, status="open")
            self.alert("critical", "exit_incomplete", f"{dep['bot_id']}: only {sold:.8g} of {qty:.8g} sold ({reason}); "
                       "the rest stays open and protected", dep)
            if not p.simulated:
                self._reprotect(dep, p, dict(pos, qty=left), left, intent_id, corr)
            self._audit(dep, "partial_exit", f"partial exit: sold {sold:.8g} of {qty:.8g} @ {avg:.8g}; {left:.8g} still open",
                        "warning", {"sold": sold, "left": left, "avg_price": avg}, corr, pos["symbol"])
            return {"status": "partial", "qty": sold, "avg_price": avg / ratio, "fee": fees / ratio, "left": left,
                    "orders": orders}
        return self._book(dep, pos, sold, avg, fees, reason, corr, orders)

    def _reprotect(self, dep, p, pos, qty, intent_id, corr):
        stop = pos.get("stop_price")
        if stop and qty > 0:
            n = len(self.engine.orders(deployment_id=dep["deployment_id"]))
            if self._place_stop(dep, p, pos["symbol"], qty, stop, intent_id, corr, attempt=100 + n) is None:
                self.alert("critical", "unprotected_position", f"{dep['bot_id']}: {qty:.8g} {pos['symbol']} is open WITHOUT "
                           "a protective stop; act on the provider's site", dep)

    def _book(self, dep, pos, qty, px, fee, reason, corr, orders) -> dict:
        ratio = pos.get("ratio") or 1.0
        entry_fee_share = (pos.get("fees") or 0) * (qty / pos["qty"] if pos["qty"] else 1)
        pnl = (px - pos["avg_price"]) * qty - fee - entry_fee_share
        left = pos["qty"] - qty
        if left <= pos["qty"] * 0.001:
            self._save_pos(dep, qty=0.0, status="closed", stop_order=None)
        else:
            self._save_pos(dep, qty=left)
        self._audit(dep, "position_closed", f"position closed ({reason}): sold {qty:.8g} @ {px:.8g}, "
                    f"P&L after fees {pnl:+.2f}", payload={"qty": qty, "exit_price": px, "entry_price": pos["avg_price"],
                                                          "fees": fee + entry_fee_share, "pnl": pnl, "reason": reason},
                    corr=corr, symbol=pos["symbol"])
        return {"status": "filled", "qty": qty, "avg_price": px / ratio, "fee": fee / ratio, "pnl": pnl,
                "broker_price": px, "orders": orders}

    # ------------------------------------------------------------------ protective stops on the provider
    def poll_stop(self, dep: dict) -> Optional[dict]:
        """The provider's protective stop filled (or vanished): returns the booked exit, or None."""
        pos = self.position(dep["deployment_id"])
        if pos is None or not pos.get("stop_order"):
            return None
        so = self.engine.refresh(pos["stop_order"])
        if so is None:
            return None
        if so["state"] == FILLED or (so["state"] in TERMINAL and so.get("filled_qty")):
            return self._book(dep, pos, so["filled_qty"], so["avg_price"], so["fees"], "protective stop filled on the provider",
                              so.get("correlation_id"), [so])
        if so["state"] in TERMINAL:
            p = self.resolve(dep["connection_id"])
            self.alert("warning", "stop_replaced", f"{dep['bot_id']}: the protective stop ended ({so['state']}); placing a new one", dep)
            self._reprotect(dep, p, pos, pos["qty"], so.get("intent_id") or "restop", so.get("correlation_id"))
        return None

    def move_stop(self, dep: dict, new_stop: float, intent_id: str) -> Optional[dict]:
        """Raise a provider-side stop (trailing). Providers reserve the quantity for a working sell order, so the
        old stop is canceled first; if the new one cannot be placed the old level is restored, and if even that
        fails the position is sold (it is never left knowingly unprotected)."""
        pos = self.position(dep["deployment_id"])
        if pos is None or not pos.get("stop_order"):
            return None
        new_b = new_stop * (pos.get("ratio") or 1.0)
        if pos.get("stop_price") and new_b <= pos["stop_price"] * 1.001:
            return None
        p = self.resolve(dep["connection_id"])
        old = self.engine.cancel(pos["stop_order"], "replacing with a higher protective stop")
        old = self.engine.wait_final(old["client_order_id"], 5.0)
        if old.get("filled_qty"):
            return self._book(dep, pos, old["filled_qty"], old["avg_price"], old["fees"], "protective stop filled",
                              old.get("correlation_id"), [old])
        if old["state"] not in TERMINAL:
            return None                                         # cancel unconfirmed: the old stop may still work
        n = len(self.engine.orders(deployment_id=dep["deployment_id"]))
        o = self._place_stop(dep, p, pos["symbol"], pos["qty"], new_b, intent_id, intent_id, attempt=200 + n)
        if o is None:
            o = self._place_stop(dep, p, pos["symbol"], pos["qty"], pos["stop_price"], intent_id, intent_id, attempt=300 + n)
        if o is None:
            self.alert("critical", "protective_stop_failed", f"{dep['bot_id']}: no protective stop could be placed; selling", dep)
            return self.exit(dep, ref_price=pos["avg_price"] / (pos.get("ratio") or 1.0), reason="protective stop could not be replaced",
                             intent_id=intent_id + ":restop", market=True)
        return o

    # ------------------------------------------------------------------ simulated resting orders (paper / demo)
    def record_virtual_entry(self, dep: dict, *, symbol: str, qty: float, price: float, fee: float, stop, target,
                             intent_id: str, correlation_id: str = None, model: str = "") -> dict:
        """A simulated resting entry (stop or limit) filled inside a completed bar: record it like any order and
        keep the simulated account in step."""
        o = self.engine.record_simulated(connection_id=dep["connection_id"], mode=dep["mode"], purpose="entry",
                                         symbol=symbol, side="buy", qty=qty, price=price, fee=fee, intent_id=intent_id,
                                         deployment_id=dep["deployment_id"], bot_id=dep["bot_id"], order_type="limit",
                                         ref_price=price, correlation_id=correlation_id, model=model, liquidity="maker")
        if not o.get("duplicate"):
            sim = self.resolve(dep["connection_id"])
            v, s = sim.split(symbol)
            sim.acct.apply_fill("account", v, s, "buy", qty, price, fee)
            sim._save()
        self._save_pos(dep, symbol=symbol, broker_symbol=symbol, side=1, qty=qty, avg_price=price, fees=fee,
                       opened=now_ms(), entry_order=o["client_order_id"], stop_price=stop, stop_order=None,
                       target_price=target, status="open", ratio=1.0)
        self._audit(dep, "position_opened", f"position opened: long {qty:.8g} {symbol} @ {price:.8g} (resting order "
                    "filled inside the bar, simulated)", payload={"qty": qty, "price": price, "stop": stop, "target": target},
                    corr=correlation_id or intent_id, symbol=symbol)
        return o

    def record_virtual_exit(self, dep: dict, *, qty: float, price: float, fee: float, reason: str, intent_id: str,
                            correlation_id: str = None, model: str = "") -> dict:
        pos = self.position(dep["deployment_id"])
        if pos is None:
            return {"status": "none", "reason": "no open position"}
        purpose = "protective_stop" if "stop" in reason else "exit"
        o = self.engine.record_simulated(connection_id=dep["connection_id"], mode=dep["mode"], purpose=purpose,
                                         symbol=pos["symbol"], side="sell", qty=min(qty, pos["qty"]), price=price, fee=fee,
                                         intent_id=intent_id, deployment_id=dep["deployment_id"], bot_id=dep["bot_id"],
                                         order_type="stop" if purpose == "protective_stop" else "limit", ref_price=price,
                                         correlation_id=correlation_id, model=model,
                                         liquidity="taker" if purpose == "protective_stop" else "maker")
        if not o.get("duplicate"):
            sim = self.resolve(dep["connection_id"])
            v, s = sim.split(pos["symbol"])
            sim.acct.apply_fill("account", v, s, "sell", min(qty, pos["qty"]), price, fee)
            sim._save()
        return self._book(dep, pos, min(qty, pos["qty"]), price, fee, reason, correlation_id or intent_id, [o])

    # ------------------------------------------------------------------ controls
    def cancel_entries(self, deployment_id: str = None, reason: str = "canceled") -> List[dict]:
        """Cancel working ENTRY orders (protective stops stay). Returns each order's outcome."""
        out = []
        for o in self.engine.open_orders(deployment_id=deployment_id):
            if o.get("purpose") != "entry":
                continue
            try:
                r = self.engine.cancel(o["client_order_id"], reason)
                out.append({"order": o["client_order_id"], "state": r["state"], "filled_qty": r.get("filled_qty"),
                            "ok": r["state"] in TERMINAL})
            except Exception as e:                                      # noqa: BLE001
                out.append({"order": o["client_order_id"], "state": o["state"], "ok": False, "error": str(e)})
        return out
