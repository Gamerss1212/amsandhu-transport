"""Real-money execution. OFF unless the owner arms it in the app.

The fleet trades paper money. Live trading is a separate, explicit decision: the owner connects a broker
(keys stored encrypted on this computer), sets hard limits and types the acknowledgement; only then are
chosen bots' entries sent to the exchange. Everything else keeps trading paper.

Rules enforced here, whatever a strategy or bot configuration says:
* spot only, long only: no margin, no leverage, no short selling;
* a bot trades live only if it is on the owner's list AND has earned it (out-of-sample positive at its
  venue's real costs in the batch evaluation, and at least 20 paper trades with a positive average R),
  unless the owner explicitly overrides that one bot;
* size is the smaller of the bot's paper-sized risk and the owner's per-trade limit, and total live
  exposure never exceeds the owner's total limit;
* entries are capped-price orders (a limit a few basis points through the market, immediate-or-cancel),
  never an unbounded market buy;
* every live position gets a protective stop order resting ON THE EXCHANGE right after the fill; if the
  stop cannot be placed the position is sold at once;
* a lost response is resolved by asking the exchange for the order's client id, never by resending;
* a realized loss beyond the owner's daily limit, a failed reconciliation, or any unexpected broker
  error disarms live trading (open positions keep their exchange stops; the owner decides what next).
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Callable, Dict, Optional

from mab.brokers.base import Broker, BrokerError, Order, OrderUnknown

log = logging.getLogger("mab.live")

ACK_TEXT = "I UNDERSTAND THIS TRADES REAL MONEY"
DEFAULTS = {"armed": False, "broker": None, "max_per_trade": 25.0, "max_total": 100.0, "daily_loss_limit": 25.0,
            "eligible_only": True, "bots": [], "overrides": [], "slippage_bps": 30.0, "armed_at": None,
            "disarmed_reason": None}
POLL_S, FILL_TIMEOUT_S = 0.5, 10.0


class LiveExecutor:
    def __init__(self, storage, broker: Optional[Broker], config: Optional[dict] = None,
                 eligible: Optional[Callable[[str], tuple]] = None, alert: Optional[Callable[[str, str, str], None]] = None,
                 sleep=time.sleep, clock=time.time):
        self.storage = storage
        self.broker = broker
        self.cfg = dict(DEFAULTS, **(config or storage.kv_get("live", {}) or {}))
        self.positions: Dict[str, dict] = storage.kv_get("live_positions", {}) or {}
        self.ledger = storage.kv_get("live_ledger", {"days": {}, "trades": []}) or {"days": {}, "trades": []}
        self.eligible = eligible or (lambda bot_id: (False, "no evaluation available"))
        self.alert = alert or (lambda level, kind, msg: log.warning("%s %s: %s", level, kind, msg))
        self.sleep, self.clock = sleep, clock
        self.lock = threading.RLock()

    # ------------------------------------------------------------------ state
    def _save(self):
        self.storage.kv_set("live", self.cfg)
        self.storage.kv_set("live_positions", self.positions)
        self.storage.kv_set("live_ledger", self.ledger)

    @property
    def armed(self) -> bool:
        return bool(self.cfg.get("armed")) and self.broker is not None

    def arm(self, ack: str, limits: dict, bots: list, overrides: Optional[list] = None) -> dict:
        if ack.strip().upper() != ACK_TEXT:
            raise ValueError(f'type exactly: {ACK_TEXT}')
        if self.broker is None:
            raise ValueError("connect and test a broker first")
        for k in ("max_per_trade", "max_total", "daily_loss_limit"):
            v = float(limits.get(k, self.cfg[k]))
            if not v > 0:
                raise ValueError(f"{k.replace('_', ' ')} must be more than 0")
            self.cfg[k] = v
        if self.cfg["max_per_trade"] > self.cfg["max_total"]:
            raise ValueError("the per-trade limit cannot exceed the total limit")
        self.cfg.update({"armed": True, "broker": self.broker.name, "bots": list(bots), "overrides": list(overrides or []),
                         "armed_at": int(self.clock() * 1000), "disarmed_reason": None,
                         "eligible_only": bool(limits.get("eligible_only", True))})
        self._save()
        self.alert("warning", "live_armed", f"REAL-MONEY trading armed on {self.broker.name} for {len(bots)} bots "
                                             f"(max {self.cfg['max_per_trade']:g} per trade, {self.cfg['max_total']:g} total, "
                                             f"daily loss limit {self.cfg['daily_loss_limit']:g})")
        return self.status()

    def disarm(self, reason: str) -> dict:
        with self.lock:
            was = self.cfg.get("armed")
            self.cfg.update({"armed": False, "disarmed_reason": reason})
            self._save()
        if was:
            self.alert("critical", "live_disarmed", f"real-money trading disarmed: {reason}. Open live positions keep "
                                                    "their exchange stops.")
        return self.status()

    def handles(self, bot_id: str) -> bool:
        return self.armed and bot_id in self.cfg["bots"]

    def check(self, bot_id: str) -> tuple:
        """(allowed, why) for a new live entry by this bot."""
        if not self.armed:
            return False, "live trading is not armed"
        if bot_id not in self.cfg["bots"]:
            return False, "this bot is not on the live list"
        if self.cfg["eligible_only"] and bot_id not in self.cfg["overrides"]:
            ok, why = self.eligible(bot_id)
            if not ok:
                return False, f"not eligible for live trading: {why}"
        if self._today_pnl() <= -self.cfg["daily_loss_limit"]:
            self.disarm(f"daily loss limit of {self.cfg['daily_loss_limit']:g} reached")
            return False, "daily loss limit reached"
        return True, ""

    def _today(self) -> str:
        return time.strftime("%Y-%m-%d", time.gmtime(self.clock()))

    def _today_pnl(self) -> float:
        return float(self.ledger["days"].get(self._today(), 0.0))

    def open_notional(self) -> float:
        return sum(p["qty"] * p["entry"] for p in self.positions.values())

    # ------------------------------------------------------------------ orders
    def _await(self, o: Order) -> Order:
        """Poll until the order is final; cancel whatever is still working after the timeout."""
        deadline = self.clock() + FILL_TIMEOUT_S
        cur = o
        while not cur.done and self.clock() < deadline:
            self.sleep(POLL_S)
            cur = self.broker.order(order_id=o.id) or cur
        if not cur.done:
            try:
                self.broker.cancel(o.id)
            except BrokerError as e:
                self.alert("warning", "live_cancel", f"cancel {o.id}: {e}")
            self.sleep(POLL_S)
            cur = self.broker.order(order_id=o.id) or cur
        return cur

    def _submit(self, send, client_id: str) -> Optional[Order]:
        """Send once; on a lost response, look the order up by its client id instead of resending."""
        try:
            o = send()
        except OrderUnknown as e:
            self.alert("warning", "live_unknown", f"order {client_id}: response lost ({e}); checking the exchange")
            o = None
            for _ in range(3):
                self.sleep(1.0)
                try:
                    o = self.broker.order(client_id=client_id)
                    break
                except OrderUnknown:
                    continue
            if o is None:
                return None
        if o.status == "rejected":
            return o
        return self._await(o) if o.id else o

    def enter(self, bot_id: str, instrument: str, side: int, paper_qty: float, ref_price: float, stop: float,
              intent_id: str) -> dict:
        with self.lock:
            ok, why = self.check(bot_id)
            if not ok:
                return {"status": "skipped", "reason": why}
            if side <= 0:
                return {"status": "skipped", "reason": "live trading is spot long-only (no short selling)"}
            if not stop or stop >= ref_price:
                return {"status": "skipped", "reason": "no valid protective stop below the entry"}
            if bot_id in self.positions:
                return {"status": "skipped", "reason": "this bot already has a live position"}
            # Prices come from the broker's own market, in its own currency (a USD-priced bot can trade a CAD
            # market): the bot's stop is converted with the ratio of the two prices, and limits are in the
            # broker's currency.
            try:
                self.broker.market(instrument)
                q = self.broker.price(instrument)
            except BrokerError as e:
                return {"status": "skipped", "reason": f"{self.broker.name} cannot trade {instrument}: {e}"}
            ask = q.get("ask") or q.get("last")
            if not ask or ask <= 0:
                return {"status": "skipped", "reason": f"no current price for {instrument} on {self.broker.name}"}
            ratio = ask / ref_price
            if not 0.5 < ratio < 2.0:
                return {"status": "skipped", "reason": f"{self.broker.name} price {ask:.6g} does not match the bot's {ref_price:.6g}"}
            stop = stop * ratio
            if stop >= ask:
                return {"status": "skipped", "reason": "the protective stop would be above the broker's price"}
            room = self.cfg["max_total"] - self.open_notional()
            notional = min(paper_qty * ask, self.cfg["max_per_trade"], room)
            if notional <= 0:
                return {"status": "skipped", "reason": "total live exposure limit reached"}
            limit = ask * (1 + self.cfg["slippage_bps"] / 1e4)
            qty = notional / limit
            cid = f"{intent_id}:in"
            try:
                o = self._submit(lambda: self.broker.buy(instrument, qty, limit, cid), cid)
            except BrokerError as e:
                self.disarm(f"entry order failed: {e}")
                return {"status": "error", "reason": str(e)}
            if o is None:
                self.disarm("an entry order's outcome could not be confirmed")
                return {"status": "error", "reason": "order outcome unknown"}
            if o.status == "rejected" or not o.filled_qty:
                return {"status": "none", "reason": o.reason or f"not filled ({o.status})"}
            pos = {"bot_id": bot_id, "instrument": instrument, "qty": o.filled_qty, "entry": o.avg_price or limit,
                   "fee": o.fee, "stop": stop, "stop_order": None, "intent": intent_id, "time": int(self.clock() * 1000),
                   "ratio": ratio}
            self.positions[bot_id] = pos
            self._save()
            try:
                so = self.broker.stop(instrument, o.filled_qty, stop, f"{intent_id}:stop")
                if so.status == "rejected" or not so.id:
                    raise BrokerError(so.reason or "stop rejected")
                pos["stop_order"] = so.id
                self._save()
            except BrokerError as e:
                self.alert("critical", "live_stop_failed", f"{bot_id}: protective stop could not be placed ({e}); selling now")
                res = self._close(bot_id, ref_price, "protective stop could not be placed", market=True)
                self.disarm(f"protective stop failed on {instrument}")
                return {"status": "closed", "reason": "stop failed, position sold", "exit": res}
            self.alert("warning", "live_entry", f"LIVE BUY {instrument} {o.filled_qty:g} @ {pos['entry']:.6g} for {bot_id}; "
                                                f"exchange stop {stop:.6g}")
            # avg_price and fee in the bot's own currency (for its position); broker_price in the broker's
            return {"status": "filled", "qty": o.filled_qty, "avg_price": pos["entry"] / ratio, "fee": o.fee / ratio,
                    "broker_price": pos["entry"], "broker_fee": o.fee, "order": o.to_dict()}

    def exit(self, bot_id: str, ref_price: float, reason: str) -> dict:
        with self.lock:
            if bot_id not in self.positions:
                return {"status": "none", "reason": "no live position"}
            return self._close(bot_id, ref_price, reason)

    def _close(self, bot_id: str, ref_price: float, reason: str, market: bool = False) -> dict:
        pos = self.positions[bot_id]
        try:                                                           # the broker's own bid, in its currency
            q = self.broker.price(pos["instrument"])
            ref_price = q.get("bid") or q.get("last") or ref_price * pos.get("ratio", 1.0)
        except BrokerError:
            ref_price = ref_price * pos.get("ratio", 1.0)
        if pos.get("stop_order"):
            so = self.broker.order(order_id=pos["stop_order"])
            if so and so.status == "filled":                          # the exchange stop already sold it
                return self._book(bot_id, so.avg_price or pos["stop"], so.fee, "exchange stop filled", so.filled_qty)
            try:
                self.broker.cancel(pos["stop_order"])
            except BrokerError as e:
                self.alert("warning", "live_cancel", f"{bot_id}: cancelling the stop failed ({e})")
        qty, sold, cost, fee, k = pos["qty"], 0.0, 0.0, 0.0, 0
        while qty - sold > qty * 1e-6 and k < 3:
            k += 1
            limit = None if (market or k == 3) else ref_price * (1 - self.cfg["slippage_bps"] / 1e4)
            cid = f"{pos['intent']}:out{k}"
            try:
                o = self._submit(lambda: self.broker.sell(pos["instrument"], qty - sold, limit, cid), cid)
            except BrokerError as e:
                self.alert("critical", "live_exit_failed", f"{bot_id}: sell failed ({e})")
                o = None
            if o and o.filled_qty:
                sold += o.filled_qty
                cost += o.filled_qty * (o.avg_price or ref_price)
                fee += o.fee
        if sold < qty * 0.999:
            self.alert("critical", "live_exit_incomplete", f"{bot_id}: only {sold:g} of {qty:g} sold; the rest stays on the "
                                                          "exchange; live trading disarmed")
            self.disarm(f"exit of {pos['instrument']} incomplete")
            pos["qty"] = qty - sold
            self._save()
        return self._book(bot_id, cost / sold if sold else ref_price, fee, reason, sold)

    def _book(self, bot_id, px, fee, reason, qty) -> dict:
        pos = self.positions.get(bot_id)
        pnl = (px - pos["entry"]) * qty - fee - pos["fee"] * (qty / pos["qty"] if pos["qty"] else 1)
        if qty >= pos["qty"] * 0.999:
            del self.positions[bot_id]
        day = self._today()
        self.ledger["days"][day] = self.ledger["days"].get(day, 0.0) + pnl
        self.ledger["trades"] = (self.ledger["trades"] + [{"bot_id": bot_id, "instrument": pos["instrument"], "qty": qty,
                                                           "entry": pos["entry"], "exit": px, "pnl": pnl, "reason": reason,
                                                           "time": int(self.clock() * 1000)}])[-500:]
        self._save()
        self.alert("warning", "live_exit", f"LIVE SELL {pos['instrument']} {qty:g} @ {px:.6g} for {bot_id} ({reason}); P&L {pnl:+.2f}")
        if self._today_pnl() <= -self.cfg["daily_loss_limit"]:
            self.disarm(f"daily loss limit of {self.cfg['daily_loss_limit']:g} reached")
        ratio = pos.get("ratio") or 1.0
        return {"status": "filled", "qty": qty, "avg_price": px / ratio, "fee": fee / ratio, "pnl": pnl,
                "broker_price": px, "broker_fee": fee}

    def poll_stops(self) -> list:
        """Positions whose exchange stop has filled (returned so the runtime can close the bot's trade)."""
        done = []
        with self.lock:
            for bot_id, pos in list(self.positions.items()):
                if not pos.get("stop_order"):
                    continue
                try:
                    so = self.broker.order(order_id=pos["stop_order"])
                except BrokerError as e:
                    self.alert("warning", "live_poll", f"{bot_id}: stop status unavailable ({e})")
                    continue
                if so and so.status == "filled":
                    res = self._book(bot_id, so.avg_price or pos["stop"], so.fee, "exchange stop filled", so.filled_qty)
                    done.append((bot_id, res))
        return done

    def reconcile(self) -> dict:
        """Compare live positions with the exchange's balances; disarm on any shortfall."""
        if self.broker is None:
            return {"ok": True, "note": "no broker"}
        try:
            bal = self.broker.balances()
        except BrokerError as e:
            return {"ok": False, "error": str(e)}
        need: Dict[str, float] = {}
        for p in self.positions.values():
            need[p["instrument"]] = need.get(p["instrument"], 0.0) + p["qty"]
        problems = []
        for inst, qty in need.items():
            code = self.broker.market(inst).get("base") or inst.split("-")[0]
            have = max((v for k, v in bal.items() if k.upper() in (str(code).upper(), inst.split("-")[0].upper(),
                                                                  "X" + inst.split("-")[0].upper())), default=0.0)
            if have < qty * 0.99:
                problems.append(f"{inst}: fleet expects {qty:g}, exchange holds {have:g}")
        if problems:
            self.disarm("reconciliation failed: " + "; ".join(problems))
        return {"ok": not problems, "problems": problems, "positions": len(self.positions)}

    def close_all(self, prices: Dict[str, float]) -> list:
        out = []
        with self.lock:
            for bot_id in list(self.positions):
                out.append((bot_id, self._close(bot_id, prices.get(self.positions[bot_id]["instrument"], 0.0) or 0.0,
                                                "owner closed all live positions", market=True)))
        return out

    def status(self) -> dict:
        return {"armed": self.armed, "config": {k: v for k, v in self.cfg.items()}, "positions": list(self.positions.values()),
                "open_notional": self.open_notional(), "today_pnl": self._today_pnl(),
                "recent_trades": self.ledger["trades"][-20:], "ack_text": ACK_TEXT}
