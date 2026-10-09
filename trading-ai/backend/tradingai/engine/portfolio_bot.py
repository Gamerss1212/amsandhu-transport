"""Portfolio bots: run a catalog portfolio template (ST004, ST010, ST045 ...) in paper with a fixed share of equity.

Same decision code as the research engine (`research.portfolio`): at the first check after a new month (or week)
begins, target weights are computed from daily closes up to the last day of the previous period, exactly as in the
backtest. The orders that move each holding to its target are then sent one instrument at a time when that market is
open, through the OMS and the risk service like every other order. A holding is identified by the strategy's own lot
in the paper ledger, so positions of other bots are never touched.

Deployable universes are those valued simply in USD (US stocks/ETFs, spot crypto). Futures and FX portfolios
(ST001, ST040) stay research-only until contract-aware portfolio execution exists.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from decimal import ROUND_DOWN, Decimal
from typing import TYPE_CHECKING, Optional

import numpy as np

from tradingai.core.ids import new_id
from tradingai.market.calendars import session
from tradingai.market.instruments import MarketType
from tradingai.market.universe import paper_tradable
from tradingai.research.portfolio import PORTFOLIOS, load_panel
from tradingai.risk.service import OrderRequest
from tradingai.storage.db import dumps, now_ms
from tradingai.strategies.library import MARKET_OF

if TYPE_CHECKING:
    from tradingai.app import App

DEPLOYABLE = {MarketType.STOCK, MarketType.ETF, MarketType.CRYPTO_SPOT}
DAY = 86_400_000


def deployable(app: "App", sid: str) -> tuple[bool, str]:
    spec = PORTFOLIOS.get(sid)
    if spec is None:
        return False, "unknown portfolio template"
    bad = [i for i in spec.universe if app.book.get(i).market_type not in DEPLOYABLE]
    if bad:
        return False, "contract-aware portfolio execution (futures/FX) is not implemented: research only"
    return True, "ok"


def period_key(day: int, freq: str) -> str:
    t = datetime.fromtimestamp(day * 86400, tz=timezone.utc)
    return t.strftime("%Y-%m") if freq == "M" else t.strftime("%G-W%V")


def held_lots(app: "App", sid: str) -> dict[str, Decimal]:
    out = {}
    for p in app.paper.positions_detail():
        q = Decimal(str((p.get("strategy_lots") or {}).get(sid, "0")))
        if q != 0:
            out[p["instrument_id"]] = q
    return out


def strategy_pnl(app: "App", sid: str) -> Decimal:
    """Cash flows of this strategy's fills plus the current value of its lots (fees included)."""
    cash = Decimal(0)
    for f in app.db.query("SELECT f.side, f.qty, f.price, f.fee, f.instrument_id FROM fills f JOIN orders o ON "
                          "o.client_order_id=f.client_order_id WHERE o.strategy_id=? AND f.environment='paper'", (sid,)):
        m = app.book.get(f["instrument_id"]).multiplier
        q = Decimal(f["qty"]) * (1 if f["side"] == "buy" else -1)
        cash -= q * Decimal(f["price"]) * m + Decimal(f["fee"])
    for iid, q in held_lots(app, sid).items():
        quote = app.quote(iid)
        if quote:
            cash += q * Decimal(str(quote["price"])) * app.book.get(iid).multiplier
    return cash


def step(app: "App", bot, mode: str) -> Optional[dict]:
    """Called on every trading-loop tick for a running portfolio bot (cheap unless something is due)."""
    spec = PORTFOLIOS[bot.strategy_id]
    now = time.time()
    if not bot.pending and now - (bot.checked_at or 0) < 600:          # look for a new period every 10 minutes
        return None
    bot.checked_at = now
    rec = None
    if not bot.pending:
        panel = load_panel(app.md, app.book, spec.universe, lookback=400)
        days = panel["days"]
        cur = period_key(int(days[-1]), spec.rebalance)
        if bot.rebalance_key == cur:
            return None
        if bot.rebalance_key is None:
            t_dec = len(days) - 1                                     # a new bot starts from the latest closes
        else:
            prev = [i for i, d in enumerate(days) if period_key(int(d), spec.rebalance) != cur]
            t_dec = prev[-1] if prev else len(days) - 1
        exp = app.ledger.get(bot.experiment_id) if bot.experiment_id else None
        params = ((exp or {}).get("results") or {}).get("params_chosen") or spec.params
        ppy = 365.0 if all(app.book.get(i).market_type is MarketType.CRYPTO_SPOT for i in spec.universe) else 252.0
        w = np.nan_to_num(spec.fn(panel["c"], panel["r"], t_dec, ppy, **params))
        w = np.clip(w, 0, None) if spec.long_only else w
        g = float(np.abs(w).sum())
        if g > 1:
            w = w / g
        bot.pending = {iid: round(float(x), 6) for iid, x in zip(spec.universe, w)}
        for iid in held_lots(app, bot.strategy_id):                     # holdings no longer wanted go to zero
            bot.pending.setdefault(iid, 0.0)
        bot.rebalance_key = cur
        rec = _record(app, bot, mode, "REBALANCE", f"new {('month' if spec.rebalance == 'M' else 'week')}: targets "
                      + ", ".join(f"{k.split(':')[1]} {v:.0%}" for k, v in bot.pending.items() if v), bot.pending)
        app._save_bots()
    _execute(app, bot, mode)
    return rec


def _execute(app: "App", bot, mode: str) -> None:
    acct = app.paper.get_balance()
    budget = (acct.equity or Decimal(0)) * Decimal(str(bot.allocation))
    held = held_lots(app, bot.strategy_id)
    for iid, w in list(bot.pending.items()):
        inst = app.book.get(iid)
        if inst.market_type is not MarketType.CRYPTO_SPOT and not session(inst.calendar or "CRYPTO", now_ms())["open"]:
            continue
        q = app.quote(iid)
        if q is None:
            continue
        px = Decimal(str(q["price"]))
        target = (budget * Decimal(str(w)) / (px * inst.multiplier) / inst.quantity_step).to_integral_value(
            ROUND_DOWN) * inst.quantity_step
        cur = held.get(iid, Decimal(0))
        delta = target - cur
        if abs(delta) < inst.min_quantity:
            bot.pending.pop(iid)
            continue
        bars, st = app.md.bars(iid, "1d", lookback=3)
        snap = app.risk_snapshot(inst, bars, st, mode)
        side = "buy" if delta > 0 else "sell"
        req = OrderRequest(client_order_id="", instrument_id=iid, market=MARKET_OF.get(inst.market_type, "etf"),
                           side=side, quantity=abs(delta), reference_price=px, limit_price=None,
                           multiplier=inst.multiplier, environment=mode if mode != "shadow" else "paper",
                           account_id=acct.account_id_masked, sized_target=abs(delta),
                           reduces_position=abs(target) < abs(cur) and (target == 0 or (target > 0) == (cur > 0)),
                           tradable=paper_tradable(inst), quantity_step=inst.quantity_step)
        did = new_id("PF")
        res = app.oms.place(decision_id=did, req=req, snapshot=snap, broker=app.broker_for(mode),
                            broker_symbol=inst.symbol, mode=mode, strategy_id=bot.strategy_id, decided_at=time.time())
        status = res.get("status")
        if status in ("FILLED", "PARTIALLY_FILLED", "SUBMITTED", "SHADOW_NOT_SENT", "REJECTED") or \
                (status == "BLOCKED_BY_RISK" and "STALE_DATA" not in res["risk"].get("reason_codes", [])):
            bot.pending.pop(iid)                                       # done, or refused for a non-transient reason
            if status in ("FILLED", "PARTIALLY_FILLED"):
                bot.trades_today += 1
        _record(app, bot, mode, "ORDER" if status not in ("BLOCKED_BY_RISK", "REJECTED") else "RISK_REJECT",
                f"{side} {abs(delta)} {iid} toward {w:.0%} ({status})", {"instrument": iid, "target_qty": str(target),
                                                                       "held": str(cur), "order": res}, did, iid)
    app._save_bots()


def _record(app: "App", bot, mode: str, outcome: str, reason: str, data: dict, did: Optional[str] = None,
            iid: Optional[str] = None) -> dict:
    rec = {"decision_id": did or new_id("DEC"), "ts": now_ms(), "bot_id": bot.bot_id, "instrument": iid or
           bot.instrument_id, "tf": "1d", "mode": mode, "strategy_id": bot.strategy_id, "outcome": outcome,
           "reason": reason, "signal": {"portfolio": data}, "simulated_data": False}
    app.db.execute("INSERT INTO decisions (decision_id, ts, instrument_id, strategy_id, mode, signal, outcome, reason, "
                   "bot_id, tf, simulated) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                   (rec["decision_id"], rec["ts"], rec["instrument"], bot.strategy_id, mode, dumps(rec["signal"]),
                    outcome, reason[:500], bot.bot_id, "1d", 0))
    app.bus.publish("decision", rec, correlation_id=rec["decision_id"])
    return rec
