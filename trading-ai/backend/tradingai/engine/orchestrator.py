"""The master orchestrator (sections 171, 187-188): one decision for one bot on one newly completed bar.

    data -> features -> regime -> strategy signal -> agents -> ensemble -> sizing -> risk -> order

Signal modes: "strategy" (the chosen template decides; agent vetoes still block new entries), "ensemble" (the agents'
cluster-weighted vote decides), "strategy+ensemble" (the template decides and the ensemble must not lean the other
way). Exits are never blocked by agents. Every decision, including NO TRADE, is written with its reasons.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Optional

import numpy as np

from tradingai.agents import roster
from tradingai.agents.base import AGENTS, run as run_agent
from tradingai.agents.ensemble import combine
from tradingai.backtest.costs import default_for, half_spread_price
from tradingai.core.ids import new_id
from tradingai.data.bars import TF_MS
from tradingai.features.registry import FeatureFrame
from tradingai.market.calendars import session
from tradingai.market.universe import paper_tradable
from tradingai.regime.detect import detect
from tradingai.risk.service import OrderRequest, Snapshot
from tradingai.storage.db import dumps, now_ms
from tradingai.strategies.library import MARKET_OF, SHORTABLE, Signal, Strategy, specs, summary as lib_summary

RISK_PROFILES = {"conservative": 0.0025, "moderate": 0.005, "aggressive": 0.01}
HTF = {"1m": "15m", "5m": "1h", "15m": "1h", "30m": "4h", "1h": "4h", "4h": "1d", "1d": "1d"}


@dataclass
class BotConfig:
    bot_id: str
    instrument_id: str
    tf: str
    strategy_id: str
    signal_mode: str = "strategy+ensemble"
    risk_profile: str = "conservative"
    max_trades_per_day: int = 10
    regular_hours_only: bool = True
    state: str = "stopped"                  # running / paused / stopped
    created: int = field(default_factory=now_ms)
    last_bar_ts: Optional[int] = None
    trades_today: int = 0
    day: Optional[str] = None

    def as_dict(self) -> dict:
        return dict(vars(self))


class Orchestrator:
    def __init__(self, app: Any):
        self.app = app
        self._regime_cache: dict[str, tuple[int, Any, dict]] = {}

    def _extra(self, inst, tf: str) -> dict:
        """Data other agents can use, only when it really exists in this installation."""
        md, out = self.app.md, {}
        try:
            if inst.instrument_id == "COINBASE:BTC-USD":
                out["other_venue_close"] = md.bars("KRAKEN:XBTUSD", tf, 50)[0].close
            elif inst.instrument_id == "KRAKEN:XBTUSD":
                out["other_venue_close"] = md.bars("COINBASE:BTC-USD", tf, 50)[0].close
            if inst.market_type.value in ("stock", "etf") and inst.instrument_id != "US:SPY":
                out["benchmark_close"] = md.bars("US:SPY", tf if tf == "1d" else "1d", 300)[0].close
            if inst.market_type.value == "fx_otc":
                out["fx_basket"] = {p: md.bars(f"FX:{p}", tf, 60)[0].close for p in
                                    ("EURUSD", "GBPUSD", "USDJPY", "USDCAD", "AUDUSD")}
            if inst.root in ("ES", "MES"):
                out["index_close"] = md.bars("INDEX:SPX", "1d", 5)[0].close
        except Exception:                            # noqa: BLE001 - optional context; agents abstain without it
            pass
        return out

    def decide(self, bot: BotConfig, mode: str) -> dict:
        t_start = time.time()
        lat: dict[str, float] = {}
        app = self.app
        inst = app.book.get(bot.instrument_id)
        did = new_id("DEC")
        market = MARKET_OF.get(inst.market_type, "crypto")
        t = time.perf_counter()
        bars, dstatus = app.md.bars(inst.instrument_id, bot.tf, lookback=700)
        lat["data_ms"] = (time.perf_counter() - t) * 1000
        rec: dict = {"decision_id": did, "ts": now_ms(), "bot_id": bot.bot_id, "instrument": inst.instrument_id,
                     "tf": bot.tf, "mode": mode, "strategy_id": bot.strategy_id, "simulated_data": bars.simulated,
                     "data": {k: dstatus.get(k) for k in ("provider", "fresh", "error", "simulated")}}
        if len(bars) < 250:
            return self._finish(rec, "NO_TRADE", f"not enough history yet ({len(bars)} bars, need 250)", lat, t_start)
        t = time.perf_counter()
        ff = FeatureFrame(bars, inst.calendar or "CRYPTO", market)
        reg, _ = detect(ff)
        lat["features_regime_ms"] = (time.perf_counter() - t) * 1000
        spec = specs().get(bot.strategy_id)
        sig = Signal(0, int(bars.available_at[-1]), bot.strategy_id)
        strat = None
        if spec is not None and spec.runnable:
            strat = Strategy(spec)
            strat.on_market_data(bars, inst.calendar or "CRYPTO", market)
            t = time.perf_counter()
            sig = strat.generate_signal()
            lat["strategy_ms"] = (time.perf_counter() - t) * 1000
        acct = app.broker_for(mode).get_balance()
        pos_qty = app.broker_for(mode).get_positions().get(inst.instrument_id, Decimal(0))
        snap = app.risk_snapshot(inst, bars, dstatus, mode)
        cm = default_for(inst)
        last = float(bars.close[-1])
        execution = {"route": app.broker_for(mode).label, "open_orders": len(app.broker_for(mode).get_open_orders()),
                     "spread_bps": round(half_spread_price(cm, inst, last) / last * 2e4, 2),
                     "slippage_bps": round(cm.vol_slip_frac * (bars.high[-1] - bars.low[-1]) / last * 1e4, 2),
                     "estimated_cost_bps": round((cm.commission_pct * 2 + half_spread_price(cm, inst, last) / last * 2)
                                                 * 1e4, 2),
                     "market_ok": True, "reconciliation": "ok" if snap.reconciliation_ok else "REQUIRED",
                     "duplicates_blocked": app.risk.counters["duplicates_blocked"]}
        research = app.research_snapshot(bot.strategy_id, inst.instrument_id)
        ctx = roster.AgentContext(
            instrument=inst, market=market, tf=bot.tf, bars=bars, ff=ff, now_ms=now_ms(), regime=reg,
            quality=dstatus, extra_data=self._extra(inst, bot.tf),
            risk={"usage": app.risk.usage(snap), "limits": vars(app.risk.limits), "kill_switch": app.risk.kill_switch,
                  "trading_locked": app.risk.trading_locked},
            execution=execution, research=research, strategy={"signal": sig.direction},
            broker={"broker": app.broker_for(mode).name, "status": app.broker_for(mode).status() if mode == "live"
                    else "simulated", "environment": mode}, library=lib_summary())
        t = time.perf_counter()
        outs = [run_agent(a, ctx) for a in AGENTS.values()]
        ens = combine(outs, calibrator=None)
        ctx.ensemble = ens
        outs = [run_agent(a, ctx) if a.group == "meta" else o for a, o in zip(AGENTS.values(), outs)]
        lat["agents_ms"] = (time.perf_counter() - t) * 1000
        rec.update(regime=reg.as_dict(), signal={"strategy": sig.direction, "reasons": sig.reasons},
                   ensemble=ens, votes=[o.as_dict() for o in outs if o.status != "abstain" or o.group == "meta"],
                   position_before=str(pos_qty), equity=str(acct.equity))
        # ---- final direction
        if bot.signal_mode == "ensemble":
            want = ens["raw_direction"]
        elif bot.signal_mode == "strategy":
            want = sig.direction
        else:
            want = sig.direction if np.sign(ens["score"]) != -sig.direction or abs(ens["score"]) < 0.25 else 0
        if market not in SHORTABLE:
            want = max(want, 0)
        tradable = paper_tradable(inst)
        cur = int(np.sign(pos_qty))
        entering = want != 0 and want != cur
        if entering and ens["vetoes"]:
            return self._finish(rec, "NO_TRADE", "vetoed: " + "; ".join(v["name"] + " (" + v["message"] + ")"
                                                                         for v in ens["vetoes"]), lat, t_start)
        if entering and bot.trades_today >= bot.max_trades_per_day:
            return self._finish(rec, "NO_TRADE", f"daily trade cap reached ({bot.max_trades_per_day})", lat, t_start)
        if bot.regular_hours_only and inst.calendar == "XNYS" and not session("XNYS", now_ms())["open"]:
            if entering:
                return self._finish(rec, "NO_TRADE", "outside regular trading hours", lat, t_start)
        if want == cur and want != 0:
            return self._finish(rec, "HOLD", "already positioned in the signal direction", lat, t_start)
        if want == 0 and cur == 0:
            why = "strategy flat" if sig.direction == 0 else "ensemble disagrees with the strategy"
            if bot.signal_mode == "ensemble":
                why = f"ensemble score {ens['score']:+.2f}, {ens['agreeing_clusters']} agreeing cluster(s)"
            return self._finish(rec, "NO_TRADE", why, lat, t_start)
        # ---- size
        target = Decimal(0)
        if want != 0 and strat is not None:
            budget = acct.equity * Decimal(str(RISK_PROFILES.get(bot.risk_profile, 0.0025)))
            target = strat.calculate_position(Signal(want, sig.as_of, bot.strategy_id), inst, budget)
        elif want != 0:
            return self._finish(rec, "NO_TRADE", "ensemble mode needs a strategy for sizing (stop distance)", lat,
                                t_start)
        delta = target - pos_qty
        if delta == 0:
            return self._finish(rec, "NO_TRADE", "target equals the current position (size rounded to zero)", lat,
                                t_start)
        side = "buy" if delta > 0 else "sell"
        req = OrderRequest(client_order_id="", instrument_id=inst.instrument_id, market=market, side=side,
                           quantity=abs(delta), reference_price=Decimal(str(last)), limit_price=None,
                           multiplier=inst.multiplier, environment=mode, account_id=acct.account_id_masked,
                           sized_target=abs(target) if target != 0 else abs(delta),
                           reduces_position=abs(target) < abs(pos_qty) and np.sign(target) in (0, np.sign(pos_qty)),
                           tradable=tradable,
                           permitted=app.permission(inst, mode), quantity_step=inst.quantity_step)
        t = time.perf_counter()
        res = app.oms.place(decision_id=did, req=req, snapshot=snap, broker=app.broker_for(mode),
                            broker_symbol=app.broker_symbol(inst, mode), mode=mode, strategy_id=bot.strategy_id,
                            decided_at=t_start)
        lat["risk_and_order_ms"] = (time.perf_counter() - t) * 1000
        rec["order"] = {"side": side, "qty": str(abs(delta)), "target": str(target), **res}
        outcome = "ORDER" if res.get("status") not in ("BLOCKED_BY_RISK", "BLOCKED", "REJECTED") else "RISK_REJECT"
        if outcome == "ORDER" and entering:
            bot.trades_today += 1
        reason = res["risk"]["reason"] if outcome == "RISK_REJECT" else f"{side} {abs(delta)} ({res.get('status')})"
        return self._finish(rec, outcome, reason, lat, t_start)

    def _finish(self, rec: dict, outcome: str, reason: str, lat: dict, t0: float) -> dict:
        lat["total_ms"] = (time.time() - t0) * 1000
        rec.update(outcome=outcome, reason=reason, latency={k: round(v, 2) for k, v in lat.items()})
        app = self.app
        app.db.execute("INSERT INTO decisions (decision_id, ts, instrument_id, strategy_id, mode, signal, regime, votes, "
                       "risk, order_json, outcome, reason, latency) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                       (rec["decision_id"], rec["ts"], rec["instrument"], rec.get("strategy_id"), rec["mode"],
                        dumps(rec.get("signal")), dumps(rec.get("regime")),
                        dumps({"ensemble": rec.get("ensemble"), "votes": rec.get("votes")}),
                        dumps((rec.get("order") or {}).get("risk")), dumps(rec.get("order")), outcome, reason,
                        dumps(rec["latency"])))
        app.bus.publish("decision", {k: rec.get(k) for k in ("decision_id", "ts", "bot_id", "instrument", "tf", "mode",
                                                              "outcome", "reason", "signal", "ensemble", "regime",
                                                              "order", "latency", "simulated_data")},
                        correlation_id=rec["decision_id"])
        app.bus.publish("agents", {"decision_id": rec["decision_id"], "instrument": rec["instrument"],
                                   "votes": rec.get("votes", [])}, correlation_id=rec["decision_id"])
        return rec
