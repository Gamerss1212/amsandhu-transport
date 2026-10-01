"""The owner's deployments inside the fleet: per-bot START / PAUSE NEW ENTRIES / STOP / EMERGENCY STOP, readiness
checks, capital allocation, per-deployment and per-account risk limits, and the order path through the execution
engine (mab.execution). Mixed into mab.runtime.Fleet.

Two kinds of bots share the fleet:
* the research fleet: the registry's bots. They always evaluate their rules (their signals feed the scanner and
  the brain). With research autopilot on, they trade the research paper account exactly as earlier versions did;
  their results are labelled "research paper" and never mixed with the owner's accounts.
* the owner's bots (ids "U-..."), built from a strategy and a market. They trade only while deployed: one mode
  (demo, paper or live), one account connection, an allocation and risk limits. Every one of their orders goes
  through the execution engine, the per-deployment limits and the account's portfolio risk layer, in that order,
  after the brain: nothing the brain (or anything else) decides can make an order larger than those limits.
"""

from __future__ import annotations

import hashlib
import logging
import time
from collections import deque
from datetime import datetime, timezone
from typing import Dict, List, Optional

from mab.account import Account
from mab.connections import Connections
from mab.deploy import ACTIVE, Checks, Deployments, validate_limits
from mab.execution.base import ProviderError
from mab.execution.engine import ExecutionEngine, TERMINAL
from mab.execution.paper import SimProvider
from mab.execution.router import Router
from mab.models import OrderIntent, now_ms
from mab.risk import RiskLimits, RiskManager
from mab.storage import StorageError

log = logging.getLogger("mab.deploy")

LIVE_ACK = "I UNDERSTAND THIS TRADES REAL MONEY"
START_LIVE_ACK = "START LIVE"
RESEARCH_CONN = "paper-research"
ACCOUNT_SNAPSHOT_EVERY = 1          # health cycles between simulated-account equity points
BROKER_SYNC_EVERY = 1               # health cycles between broker account syncs (when a deployment uses it)
RECONCILE_EVERY = 5
AUTOPILOT_PRIORITY = 8                      # research queue: the owner's own jobs (priority 5) always go first
AUTOPILOT_MAX_PENDING = 2                   # autopilot never queues more than this many jobs at once
AUTOPILOT_WF_EVERY_MS = 20 * 60_000         # one walk-forward evaluation every 20 minutes, in rotation
AUTOPILOT_REEVAL_MS = 7 * 86_400_000        # each strategy/market pair at most once a week


def utc_day_start(ms: Optional[int] = None) -> int:
    d = datetime.fromtimestamp((ms or now_ms()) / 1000, tz=timezone.utc)
    return int(datetime(d.year, d.month, d.day, tzinfo=timezone.utc).timestamp() * 1000)


def _utc(ms) -> str:
    try:
        return time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(int(ms) / 1000))
    except (TypeError, ValueError):
        return "?"


class DeploymentMixin:
    # ================================================================== setup
    def _init_deployments(self):
        self.workspace = self.cfg.get("workspace", "main")
        self.demo = bool(self.cfg.get("demo"))
        self.deps = Deployments(self.storage)
        self.conns = Connections(self.storage, self.workspace)
        self.main_conn = self.conns.ensure_defaults(demo=self.demo)
        self._ensure_research_conn()
        self.sims: Dict[str, SimProvider] = {}
        p = self.cfg.get("paper", {})
        self._make_sim(self.main_conn, "demo" if self.demo else "paper",
                       float(self.cfg.get("paper_main_balance", 100_000.0)), p)
        self.engine = ExecutionEngine(self.storage, self.conns.provider, kill_switch=self._halt_reason,
                                      live_allowed=self._live_allowed)
        self.router = Router(self.engine, self.storage, self.conns.provider, alert=self._dep_alert,
                             slippage_bps=float(self.cfg.get("live_slippage_bps", 30.0)))
        # AUTOPILOT (one button): the research fleet trades its simulated account by itself and research runs on a
        # schedule. It persists, so it resumes when the app restarts. A workspace the app creates starts with it off
        # (cfg autopilot_default False) until the owner presses START AUTOPILOT; it never touches real money.
        ap = self.storage.kv_get("autopilot")
        if not isinstance(ap, dict):
            legacy = self.storage.kv_get("research_autopilot")
            ap = {"on": bool(legacy) if legacy is not None else bool(self.cfg.get("autopilot_default", True)),
                  "since": None, "by": None}
        self.autopilot = ap
        self.research_autopilot = bool(ap.get("on"))
        self.live_prices: Dict[tuple, tuple] = {}     # (venue, symbol) -> (price, quote time, fetched at, source)
        self.dep_cache: Dict[str, dict] = {}
        self.dep_blocks: Dict[str, str] = {}
        self.dep_peak: Dict[str, float] = dict(self.storage.kv_get("dep_peaks", {}) or {})
        self.dep_orders: Dict[str, deque] = {}
        self.dep_ratio: Dict[str, float] = {}
        self.port_risk: Dict[str, RiskManager] = {}
        self.trade_corr: Dict[str, str] = {}
        self._announced: Dict[tuple, int] = {}
        self._dep_cycle = 0
        from mab.research.registry import Registry
        self.registry_models = Registry(self.storage)
        if getattr(self, "volgate", None) is not None:
            try:
                self.registry_models.register_volgate(self.volgate)
            except Exception as e:                                      # noqa: BLE001
                log.warning("volatility gate not registered: %s", e)
        self.live_brain = None
        self.live_brain_version = None
        self.reload_models()
        self._refresh_deps()

    def _ensure_research_conn(self):
        if self.conns.get(RESEARCH_CONN) is None:
            t = now_ms()
            self.storage.write("INSERT INTO connections (connection_id, provider, environment, label, auth_method, status,"
                               " options, capabilities, created, updated) VALUES (?,?,?,?,?,?,?,?,?,?)",
                               (RESEARCH_CONN, "jarvus_paper", "demo" if self.demo else "paper",
                                "Your paper account: the AI trades this (simulated)", "none", "connected", '{"system": true}', "{}", t, t))

    def _make_sim(self, cid: str, env: str, balance: float, pcfg: dict):
        st = self.storage.kv_get(f"sim_account:{cid}")
        acct = Account.from_state(st) if st else Account(balance, 1, self.cfg.get("account", {}).get("currency", "USD"))
        acct.sim_orders = (st or {}).get("sim_orders", {})
        p = SimProvider(cid, env, acct, persist=lambda s, cid=cid: self.storage.kv_set(f"sim_account:{cid}", s),
                        book=self._book, last_price=self._last_price, instrument=self.registry.get,
                        fee_rate=lambda v, liq: self.broker.fee_rate(v, liq),
                        latency_ms=int(pcfg.get("latency_ms", 150)), max_slippage_bps=float(pcfg.get("max_slippage_bps", 50)))
        p.connection_id = cid
        if not st:
            p._save()
            self.storage.save_cash_flow(dict(acct.flows[0], note=f"opening balance of {cid} (simulated)"))
        self.sims[cid] = p
        self.conns.register_local(cid, p)
        return p

    def _book(self, venue: str, symbol: str):
        ad = self.hub.adapters.get(venue)
        if ad is None or venue == "yahoo":
            return None
        try:
            return ad.book(symbol, depth=50)
        except Exception as e:                                          # noqa: BLE001
            log.info("book %s:%s unavailable: %s", venue, symbol, e)
            return None

    def _last_price(self, venue: str, symbol: str) -> Optional[float]:
        best = None
        for (v, s, tf), ser in list(self.hub.series.items()):
            if v == venue and s == symbol and ser.last_time is not None:
                t = ser.last_time + ser.step                         # the bar's close is the price at its end
                if best is None or t > best[0]:
                    best = (t, ser.bars[ser.last_time].close)
        live = getattr(self, "live_prices", {}).get((venue, symbol))
        if live and (best is None or live[1] >= best[0]):
            return live[0]
        return best[1] if best else None

    # ================================================================== state
    def _halt_reason(self) -> Optional[str]:
        return (self.emergency or {}).get("reason") if self.emergency else None

    def _live_auth(self) -> dict:
        return self.storage.kv_get("live_authorization", {}) or {}

    def _live_allowed(self, connection_id: str):
        a = self._live_auth()
        if not a.get("authorized"):
            return False, "the owner has not authorised live trading (Connections -> Live trading authorisation)"
        if connection_id not in (a.get("connections") or []):
            return False, f"live trading is not authorised on {connection_id}"
        lim = a.get("daily_loss_limit")
        if lim:
            day = self.storage.query("SELECT COALESCE(SUM(pnl),0) AS s FROM trades WHERE mode='live' AND connection_id=?"
                                     " AND exit_time >= ?", (connection_id, utc_day_start()))[0]["s"] or 0.0
            if day <= -float(lim):
                return False, f"today's live loss {day:,.2f} reached the live daily loss limit {float(lim):,.2f}"
        return True, ""

    def _refresh_deps(self):
        self.dep_cache = {d["bot_id"]: d for d in self.deps.list(active_only=True)}
        for bid, br in self.bots.items():
            if getattr(br, "user", False):
                self._apply_dep_to_bot(br, self.dep_cache.get(bid))

    def _apply_dep_to_bot(self, br, dep: Optional[dict]):
        lim = (dep or {}).get("limits") or {}
        br.tm.risk_pct_override = lim.get("risk_per_trade_pct")
        br.tm.max_notional_pct_override = lim.get("max_position_pct")
        simulated = True
        if dep:
            c = self.conns.get(dep["connection_id"])
            simulated = c is None or c["provider"] == "jarvus_paper"
        br.tm.broker_managed = not simulated
        br.tm.equity_fn = (lambda b=br.id: self._bot_equity(b))

    def _bot_equity(self, bot_id: str) -> float:
        dep = self.dep_cache.get(bot_id)
        if dep is None:
            return 0.0
        return max(0.0, self._dep_equity(dep)) / (self.dep_ratio.get(dep["deployment_id"]) or 1.0)

    def _dep_equity(self, dep: dict) -> float:
        eq = float(dep["allocation"]) + self.deps.realized(dep["deployment_id"])
        br = self.bots.get(dep["bot_id"])
        if br is not None and br.tm.pos is not None:
            px = self._last_price(br.venue, br.symbol)
            if px:
                eq += (px - br.tm.pos.entry_price) * br.tm.pos.side * br.tm.pos.qty * (self.dep_ratio.get(dep["deployment_id"]) or 1.0)
        return eq

    @staticmethod
    def _is_user(br) -> bool:
        return bool(getattr(br, "user", False))

    def _dep_of(self, br) -> Optional[dict]:
        return self.dep_cache.get(br.id) if self._is_user(br) else None

    def _entries_allowed_for(self, br, base_ok: bool) -> bool:
        if not self._is_user(br):
            return base_ok and self.research_autopilot
        dep = self.dep_cache.get(br.id)
        return bool(base_ok and dep and dep["state"] == "running" and dep["deployment_id"] not in self.dep_blocks)

    def _strategy_exits_for(self, br) -> bool:
        dep = self._dep_of(br)
        return not (dep and dep["state"] == "stopped_retaining")

    def _dep_alert(self, level, kind, msg, dep=None):
        self._alert(level, kind, msg, (dep or {}).get("bot_id"))
        if level == "critical" and dep and kind in ("protective_stop_failed", "exit_failed", "exit_incomplete",
                                                     "unprotected_position", "entry_unresolved"):
            self.dep_blocks[dep["deployment_id"]] = f"{kind.replace('_', ' ')}: entries blocked until the owner checks"

    def _audit(self, kind: str, summary: str, **kw):
        try:
            self.storage.audit(kind, summary, **kw)
        except StorageError as e:
            self._storage_failed(e)

    def _mode_of(self, br) -> str:
        dep = self._dep_of(br)
        if dep:
            return dep["mode"]
        return "demo" if self.demo else "paper"

    # ================================================================== audit: market updates and signals
    def _announce_bar(self, br, frame, status: str):
        """One market-update event per series and bar, for the series deployed bots trade on."""
        key = (br.venue, br.symbol, br.tf)
        last = frame.t[-1]
        if self._announced.get(key) == last:
            return
        self._announced[key] = last
        s = self.hub.get(*key)
        recv = None
        prov = ""
        if s is not None and last in s.bars:
            recv = getattr(s.bars[last], "receipt_time", None)
            prov = getattr(s.bars[last], "provenance", "")
        end = last + frame.step
        age = (now_ms() - end) / 1000
        dep = self._dep_of(br)
        self._audit("market_update", f"{br.symbol} {br.tf} bar closed at {frame.c[-1]:.8g} ({prov or br.venue}; "
                    f"{age:.1f}s after the bar ended; series {status})", stage="market_update",
                    severity="info" if status == "ok" else "warning", mode=dep["mode"] if dep else None,
                    symbol=br.symbol, venue=br.venue,
                    payload={"series": "/".join(key), "bar_open": last, "bar_end": end, "close": frame.c[-1],
                             "high": frame.h[-1], "low": frame.l[-1], "volume": frame.v[-1] if hasattr(frame, "v") else None,
                             "received": recv, "age_s": round(age, 2), "source": prov, "status": status})

    def _audit_signal(self, br, sig: dict, status: str, frame, i):
        user = self._is_user(br)
        act = sig["action"]
        if not user and act in ("no_trade", "hold"):
            return
        dep = self._dep_of(br)
        side = 1 if act == "enter_long" else (-1 if act == "enter_short" else 0)
        corr = None
        if act.startswith("enter"):
            corr = hashlib.sha256(f"{br.id}|{frame.t[i]}|entry|{side}".encode()).hexdigest()[:20]
        elif act == "exit" or br.tm.pos is not None:
            corr = self.trade_corr.get(br.id)
        age = (now_ms() - (frame.t[i] + frame.step)) / 1000
        self._audit("signal", f"{br.id} {br.symbol}: {act.replace('_', ' ')} - {sig['reason']}", stage="signal",
                    severity="info" if act not in ("no_trade", "hold") else "debug",
                    mode=dep["mode"] if dep else ("research" if not user else None), bot_id=br.id,
                    deployment_id=dep["deployment_id"] if dep else None, symbol=br.symbol, venue=br.venue,
                    correlation_id=corr,
                    payload={"action": act, "reason": sig["reason"], "bar_time": sig["bar_time"],
                             "decision_time": sig["decision_time"], "data_age_s": round(age, 2), "series_status": status,
                             "strategy_id": br.c.id, "strategy_version": br.c.version_hash,
                             "config_version": br.config_version, "timeframe": br.tf,
                             "rules": sig.get("rules") or [], "features": sig.get("features") or {},
                             "brain_version": self.brain_version(dep), "volgate_version": self.volgate_version()})

    def brain_version(self, dep: Optional[dict] = None) -> str:
        if dep and dep.get("mode") == "live" and getattr(self, "live_brain", None) is not None:
            return getattr(self, "live_brain_version", "champion")
        return f"learning (trades learned {self.brain.stats.get('learned', 0)})"

    def volgate_version(self) -> Optional[str]:
        vg = getattr(self, "volgate", None)
        return getattr(vg, "version", None) if vg is not None else None

    def _brain_for(self, dep: Optional[dict]):
        if dep and dep.get("mode") == "live" and getattr(self, "live_brain", None) is not None:
            return self.live_brain                  # frozen, approved snapshot: live logic never changes by itself
        return self.brain

    def _audit_brain(self, br, dep, dec: dict, corr: str):
        cal = self.brain_calibration()
        payload = {k: dec.get(k) for k in ("action", "size", "edge", "sd", "evidence", "regime", "cost_r", "gate",
                                           "veto_kind", "benched", "parts")}
        if cal["calibrated"]:
            payload["p_win"] = dec.get("p_win")
            payload["p_win_calibration"] = cal
        else:
            payload["p_win"] = None
            payload["p_win_note"] = cal["note"]
        self._audit("brain", f"{br.id}: brain {dec['action']}" + (f" x{dec['size']:.2f}" if dec["action"] == "resize" else "")
                    + f" - expected edge {dec['edge']:+.2f}R (+/-{dec['sd']:.2f}, evidence {dec['evidence']:.0f} trades)"
                    + (f"; {dec['veto_kind']} veto" if dec.get("veto_kind") else ""), stage="brain",
                    severity="info", mode=dep["mode"] if dep else "research", bot_id=br.id,
                    deployment_id=dep["deployment_id"] if dep else None, symbol=br.symbol, correlation_id=corr,
                    payload=payload)

    def brain_calibration(self) -> dict:
        """The brain's win-probability is shown only once its calibration has been measured on enough closed
        trades AND it beats the base rate (Brier skill > 0). Otherwise no probability is displayed."""
        cal = self.brain.calib
        n = sum(c[0] for c in cal)
        wins = self.brain.stats.get("wins", 0)
        learned = self.brain.stats.get("learned", 0)
        if n < 200 or learned < 200:
            return {"calibrated": False, "n": n, "note": f"win probability not shown: calibrated on {n} closed trades "
                                                           "so far (needs 200 and to beat the base rate)"}
        brier = self.brain.stats.get("brier_sum", 0.0) / n
        base = wins / learned
        ref = base * (1 - base)
        skill = 1 - brier / ref if ref > 0 else 0.0
        return {"calibrated": skill > 0, "n": n, "brier": round(brier, 4), "brier_skill": round(skill, 4),
                "note": "" if skill > 0 else "win probability not shown: it does not beat the base rate yet"}

    # ================================================================== order path for deployments
    def _intent_id(self, br, a: dict, bar_time: int) -> str:
        return hashlib.sha256(f"{br.id}|{bar_time}|{a['kind']}|{a['side']}".encode()).hexdigest()[:20]

    def _dep_checks(self, dep: dict, br, a: dict) -> tuple:
        """Per-deployment limits for an entry: (checks, adjusted quantity or 0)."""
        L = dep["limits"] or {}
        checks = []

        def add(name, ok, detail=""):
            checks.append({"check": name, "passed": bool(ok), "detail": detail})
            return ok
        ok = add("deployment running", dep["state"] == "running", f"state {dep['state']}")
        blk = self.dep_blocks.get(dep["deployment_id"])
        ok &= add("deployment not blocked", blk is None, blk or "")
        alloc = float(dep["allocation"])
        day = self.deps.realized(dep["deployment_id"], since=utc_day_start())
        lim = (L.get("daily_loss_limit_pct") or 3.0) / 100 * alloc
        ok &= add("deployment daily loss limit", day > -lim, f"{day:+,.2f} today; limit -{lim:,.2f}")
        eq = self._dep_equity(dep)
        peak = max(self.dep_peak.get(dep["deployment_id"], alloc), eq)
        dd = (peak - eq) / peak * 100 if peak > 0 else 0.0
        ok &= add("deployment drawdown limit", dd < (L.get("max_drawdown_pct") or 15.0),
                  f"{dd:.2f}% below its peak {peak:,.2f}; limit {L.get('max_drawdown_pct') or 15.0:g}%")
        q = self.dep_orders.setdefault(dep["deployment_id"], deque())
        t = now_ms()
        while q and t - q[0] > 60_000:
            q.popleft()
        ok &= add("deployment order rate", len(q) < int(L.get("max_orders_per_minute") or 4), f"{len(q)} in the last minute")
        ratio = self.dep_ratio.get(dep["deployment_id"]) or 1.0
        qty, ref = float(a["qty"]), float(a["ref_price"])
        caps = [f"requested {qty * ref:,.2f}"]
        cap_pos = eq / ratio * float(L.get("max_position_pct") or 100.0) / 100.0
        if qty * ref > cap_pos:
            qty = cap_pos / ref
            caps.append(f"capped to {L.get('max_position_pct') or 100:g}% of the deployment's equity ({cap_pos:,.2f})")
        if L.get("max_order_notional"):
            cap_o = float(L["max_order_notional"]) / ratio
            if qty * ref > cap_o:
                qty = cap_o / ref
                caps.append(f"capped to the per-order limit {float(L['max_order_notional']):,.2f}")
        ok &= add("position size within limits", qty > 0, "; ".join(caps))
        return checks, (qty if ok else 0.0)

    def _port_risk(self, cid: str) -> RiskManager:
        rm = self.port_risk.get(cid)
        if rm is None:
            rm = RiskManager(RiskLimits(**(self.storage.kv_get(f"risk_limits:{cid}") or self.cfg.get("risk", {}))))
            st = self.storage.kv_get(f"risk:{cid}")
            if st:
                rm.restore(st)
            self.port_risk[cid] = rm
        return rm

    def account_equity(self, cid: str) -> Optional[float]:
        if cid in self.sims:
            return self.sims[cid].acct.equity()
        snap = self.conns.latest(cid)
        return snap["equity"] if snap and snap.get("equity") is not None else (snap or {}).get("cash")

    def _port_ctx(self, dep: dict, br, frame, i, ref_price: float) -> dict:
        cid = dep["connection_id"]
        positions, gross, net = [], 0.0, {}
        for p in self.router.positions(cid):
            b = self.bots.get(p["bot_id"])
            venue, inst = (b.venue, b.symbol) if b else ("?", p["symbol"])
            px = self._last_price(venue, inst) or (p["avg_price"] / (p.get("ratio") or 1.0))
            v = p["qty"] * px * (p.get("ratio") or 1.0)
            positions.append({"bot_id": p["bot_id"], "venue": venue, "instrument": inst, "qty": p["qty"] * (p["side"] or 1)})
            gross += abs(v)
            net[f"{venue}:{inst}"] = net.get(f"{venue}:{inst}", 0.0) + v
        status, _ = self._series_status(br)
        return {"equity": self.account_equity(cid) or 0.0, "positions": positions, "gross": gross, "net_by_instrument": net,
                "paused": self.paused, "emergency": bool(self.emergency), "bot_enabled": br.enabled, "data_status": status,
                "price_age_ms": now_ms() - (frame.t[i] + frame.step), "bar_ms": frame.step, "ref_price": ref_price}

    def _execute_user_intent(self, br, frame, i, a: dict, dep: Optional[dict]) -> str:
        if dep is None:
            br.tm.intent_rejected("not deployed")
            return "blocked"
        iid = self._intent_id(br, a, frame.t[i])
        sym = f"{br.venue}:{br.symbol}"
        if a["kind"] != "entry":
            corr = self.trade_corr.get(br.id) or iid
            res = self.router.exit(dep, ref_price=a["ref_price"], reason=a["reason"], intent_id=iid, correlation_id=corr)
            return self._after_exit(br, frame, i, a["reason"], res, dep)
        corr = iid
        brain = self._brain_for(dep)
        if brain.mode != "off":
            dec = brain.score(br.id, self._bkey(br), br.symbol, frame, i, a["side"],
                              cost_r=self._cost_r(br, a["ref_price"], a.get("stop")), gate=self._gate(br))
            self._audit_brain(br, dep, dec, corr)
            if dec["action"] == "veto":
                self.stats["brain_vetoes"] = self.stats.get("brain_vetoes", 0) + 1
                br.tm.intent_rejected("brain veto: " + dec["reason"])
                br.last_decision = "brain veto: " + dec["reason"]
                if brain is self.brain:
                    try:
                        self.brain.shadow_open(br.id, dec, a["ref_price"], a.get("stop"), a.get("target"),
                                               self._cost_r(br, a["ref_price"], a.get("stop")) or 0.0, frame.t[i],
                                               int(br.c.definition.get("max_bars") or 48), frame.sess_close[i])
                    except Exception as e:                              # noqa: BLE001
                        log.debug("shadow trade: %s", e)
                return "vetoed"
            if dec["size"] != 1.0:
                a = dict(a, qty=a["qty"] * dec["size"])
        dchecks, qty = self._dep_checks(dep, br, a)
        intent = OrderIntent(iid, br.id, br.c.id, br.symbol, br.venue, "buy" if a["side"] > 0 else "sell", "market",
                             qty or a["qty"], reason=a["reason"], stop_loss=a.get("stop"), take_profit=a.get("target"))
        rm = self._port_risk(dep["connection_id"])
        pdec = rm.check(intent, self._port_ctx(dep, br, frame, i, a["ref_price"])) if qty > 0 else None
        checks = dchecks + (pdec.checks if pdec else [])
        approved = qty > 0 and pdec is not None and pdec.approved
        if approved and pdec.adjusted_quantity is not None:
            qty = min(qty, pdec.adjusted_quantity)
        self._save(lambda: self.storage.save_intent(intent.to_dict()))
        self._save(lambda: self.storage.save_risk({"intent_id": iid, "bot_id": br.id, "approved": approved,
                                                   "adjusted_quantity": qty if approved else None, "checks": checks,
                                                   "decision_time": now_ms()}))
        failed = [c["check"] + (f" ({c['detail']})" if c["detail"] else "") for c in checks if not c["passed"]]
        self._audit("risk", f"{br.id}: risk {'approved' if approved else 'REJECTED'} "
                    + (f"{qty:.8g} {br.symbol}" if approved else "; ".join(failed)),
                    stage="risk_approved" if approved else "risk_rejected", severity="info" if approved else "warning",
                    mode=dep["mode"], bot_id=br.id, deployment_id=dep["deployment_id"], symbol=br.symbol,
                    correlation_id=corr, payload={"checks": checks, "requested_qty": a["qty"], "approved_qty": qty,
                                                  "ref_price": a["ref_price"], "stop": a.get("stop"), "target": a.get("target")})
        if not approved:
            self.stats["risk_blocks"] += 1
            br.tm.intent_rejected("risk: " + "; ".join(failed))
            br.last_decision = f"blocked by risk: {'; '.join(failed)}"
            return "blocked"
        self.dep_orders.setdefault(dep["deployment_id"], deque()).append(now_ms())
        self.stats["intents"] += 1
        cap = None
        if (dep["limits"] or {}).get("max_order_notional"):
            cap = float(dep["limits"]["max_order_notional"])
        res = self.router.enter(dep, symbol=sym, side=a["side"], qty=qty, ref_price=a["ref_price"], stop=a.get("stop"),
                                target=a.get("target"), intent_id=iid, correlation_id=corr, max_notional=cap)
        if res.get("ratio"):
            self.dep_ratio[dep["deployment_id"]] = res["ratio"]
        st = res["status"]
        if st in ("filled", "partial"):
            br.tm.apply_entry_fill(res["avg_price"], res["qty"], res["fee"], now_ms())
            if br.tm.pos is not None:
                br.tm.pos.reason = f"[{dep['mode'].upper()}] " + (br.tm.pos.reason or "")
            self.trade_corr[br.id] = corr
            self.stats["fills"] += 1
            br.last_decision = f"entered {res['qty']:.8g} @ {res['avg_price']:.8g} ({dep['mode']})"
            return "entered"
        if st == "closed":
            br.tm.intent_rejected(res.get("reason", "closed"))
            if res.get("stop_deployment"):
                self.deps.set_state(dep["deployment_id"], "error", res.get("reason", ""), actor="system")
                self._refresh_deps()
            return "rejected"
        if res.get("block"):
            self.dep_blocks[dep["deployment_id"]] = res.get("reason", "order state unresolved")
        br.tm.intent_rejected(res.get("reason") or st)
        br.last_decision = f"entry {st}: {res.get('reason')}"
        return "rejected" if st in ("none", "error") else "skipped"

    def _after_exit(self, br, frame, i, reason: str, res: dict, dep: dict) -> str:
        st = res.get("status")
        if st == "filled":
            out = br.tm.apply_exit_fill(frame, i, res["avg_price"], res["fee"], reason + f" ({dep['mode']})")
            self._trade_closed(br, out["trade"], dep)
            return "exited"
        if st == "partial":
            self._partial_exit(br, frame, i, res, reason, dep)
            return "partial_exit"
        if st == "none" and br.tm.pos is not None and self.router.position(dep["deployment_id"]) is None:
            # the execution record says nothing is held (e.g. closed on the provider): close the bot's view to match
            out = br.tm.apply_exit_fill(frame, i, frame.c[i], 0.0, reason + " (no position held on the account)")
            self._trade_closed(br, out["trade"], dep)
            return "exited"
        br.tm.intent_rejected(res.get("reason") or st or "exit failed")
        br.last_decision = f"exit not completed: {res.get('reason')}"
        return "error"

    def _partial_exit(self, br, frame, i, res: dict, reason: str, dep: dict):
        """Part of the position sold: book that part as its own trade and keep managing the rest."""
        pos = br.tm.pos
        if pos is None:
            return
        import copy
        keep = copy.copy(pos)
        pos.qty = res["qty"]
        out = br.tm.apply_exit_fill(frame, i, res["avg_price"], res["fee"], reason + " (partial)")
        self._trade_closed(br, out["trade"], dep)
        keep.qty = res.get("left", keep.qty - res["qty"])
        keep.fees = 0.0
        br.tm.pos = keep

    def _handle_user_virtual(self, br, frame, i, a: dict, dep: dict) -> Optional[str]:
        """Simulated resting orders of a paper/demo deployment filled inside a completed bar."""
        act = a["action"]
        sym = f"{br.venue}:{br.symbol}"
        iid = hashlib.sha256(f"{br.id}|{frame.t[i]}|{act}|rest".encode()).hexdigest()[:20]
        if act == "entry":
            corr = iid
            self.router.record_virtual_entry(dep, symbol=sym, qty=a["qty"], price=a["price"], fee=a["fee"],
                                             stop=a.get("stop"), target=a.get("target"), intent_id=iid, correlation_id=corr,
                                             model="resting order simulated against the completed bar's range")
            self.trade_corr[br.id] = corr
            return "entry"
        corr = self.trade_corr.get(br.id) or iid
        self.router.record_virtual_exit(dep, qty=a["trade"].qty, price=a["price"], fee=a["fee"], reason=a["reason"],
                                        intent_id=iid, correlation_id=corr,
                                        model="resting stop/target simulated against the completed bar's range")
        self._trade_closed(br, a["trade"], dep)
        return "exit"

    # ================================================================== health: stops, limits, accounts, reconciliation
    def _deploy_cycle(self):
        self._dep_cycle += 1
        try:
            self.engine.sync()
        except Exception as e:                                          # noqa: BLE001
            log.warning("order sync: %s", e)
        for dep in list(self.dep_cache.values()):
            br = self.bots.get(dep["bot_id"])
            if br is None:
                continue
            try:
                self._dep_health(dep, br)
            except Exception as e:                                      # noqa: BLE001
                log.exception("deployment %s health: %s", dep["deployment_id"], e)
        self._account_points()
        if self._dep_cycle % RECONCILE_EVERY == 0:
            self.reconcile()
        if self._dep_cycle % 60 == 1:
            self.drift_cycle()
        try:
            self._autopilot_cycle()
        except Exception as e:                                          # noqa: BLE001 - research never stops trading
            log.warning("autopilot research schedule: %s", e)
        self.storage.kv_set("dep_peaks", self.dep_peak)
        for cid, rm in self.port_risk.items():
            eq = self.account_equity(cid)
            if eq:
                for ev in rm.on_equity(eq, time.strftime("%Y-%m-%d", time.gmtime())):
                    self._alert(ev["level"], ev["kind"], f"{cid}: {ev['message']}")
                    if ev["kind"] == "drawdown_kill_switch":
                        for d in list(self.dep_cache.values()):
                            if d["connection_id"] == cid and d["state"] == "running":
                                self.deps.set_state(d["deployment_id"], "paused", f"account drawdown limit: {ev['message']}", "system")
                        self._refresh_deps()
            self.storage.kv_set(f"risk:{cid}", rm.to_state())

    def _dep_health(self, dep: dict, br):
        did = dep["deployment_id"]
        broker = br.tm.broker_managed
        if broker and self.router.position(did) is not None:
            res = self.router.poll_stop(dep)
            if res and res.get("status") == "filled" and br.tm.pos is not None:
                s = self.hub.get(br.venue, br.symbol, br.tf)
                fr = s.frame() if s else None
                if fr is not None and fr.n:
                    out = br.tm.apply_exit_fill(fr, fr.n - 1, res["avg_price"], res["fee"], "protective stop filled on the provider")
                    self._trade_closed(br, out["trade"], dep)
                    self._persist_states([br.id])
            elif br.tm.pos is not None and dep["state"] in ("running", "paused"):
                eff = br.tm.effective_stop()
                pos = self.router.position(did)
                if eff and pos and pos.get("stop_price") and eff * (pos.get("ratio") or 1.0) > pos["stop_price"] * 1.001:
                    self.router.move_stop(dep, eff, self.trade_corr.get(br.id) or f"{did}:trail")
        eq = self._dep_equity(dep)
        self.dep_peak[did] = max(self.dep_peak.get(did, float(dep["allocation"])), eq)
        L = dep["limits"] or {}
        peak = self.dep_peak[did]
        if dep["state"] == "running" and peak > 0 and (peak - eq) / peak * 100 >= float(L.get("max_drawdown_pct") or 15.0):
            self.deps.set_state(did, "paused", f"deployment drawdown {100 * (peak - eq) / peak:.1f}% reached its limit "
                                               f"{L.get('max_drawdown_pct') or 15.0:g}%; resume when ready", "system")
            self._alert("warning", "deployment_drawdown", f"{br.id}: paused by its drawdown limit", br.id)
            self._refresh_deps()
        day = self.deps.realized(did, since=utc_day_start())
        lim = float(L.get("daily_loss_limit_pct") or 3.0) / 100 * float(dep["allocation"])
        tag = f"daily loss limit reached ({day:+,.2f}); entries resume tomorrow (UTC)"
        if day <= -lim:
            if self.dep_blocks.get(did) != tag:
                self.dep_blocks[did] = tag
                self._alert("warning", "deployment_daily_loss", f"{br.id}: {tag}", br.id)
        elif self.dep_blocks.get(did, "").startswith("daily loss"):
            self.dep_blocks.pop(did, None)

    def _account_points(self):
        t = now_ms()
        for cid, p in self.sims.items():
            if self._dep_cycle % ACCOUNT_SNAPSHOT_EVERY:
                continue
            try:
                a = p.account()
                self.storage.write("INSERT OR REPLACE INTO account_equity (connection_id, ts, mode, equity, cash, exposure,"
                                   " realized, unrealized) VALUES (?,?,?,?,?,?,?,?)",
                                   (cid, t, p.environment, a["equity"], a["cash"], a["exposure"], a["realized_pnl"],
                                    a["unrealized_pnl"]))
            except Exception as e:                                      # noqa: BLE001
                log.debug("sim account point %s: %s", cid, e)
        research = self.account.summary()
        try:
            self.storage.write("INSERT OR REPLACE INTO account_equity (connection_id, ts, mode, equity, cash, exposure, realized,"
                               " unrealized) VALUES (?,?,?,?,?,?,?,?)",
                               (RESEARCH_CONN, t, "demo" if self.demo else "paper", research["equity"], research["cash"],
                                research["gross_exposure"], research["realized_pnl"], None))
        except StorageError as e:
            self._storage_failed(e)
        if self._dep_cycle % BROKER_SYNC_EVERY == 0:
            used = {d["connection_id"] for d in self.dep_cache.values()}
            for c in self.conns.list():
                if c["provider"] == "jarvus_paper" or not c.get("enabled") or c["status"] not in ("connected",):
                    continue
                if c["connection_id"] not in used and self._dep_cycle % 10:
                    continue                                            # idle connections: every 10th cycle
                try:
                    self.conns.sync(c["connection_id"])
                except Exception as e:                                  # noqa: BLE001
                    self._audit("connection", f"{c['label']}: sync failed ({e})", stage="sync_failed", severity="warning",
                                connection_id=c["connection_id"], mode=c["environment"])

    def reconcile(self) -> dict:
        """Compare what each broker account holds with what the deployments' fills say it should hold. A shortfall
        blocks new entries for every deployment on that account and raises a critical alert; nothing is 'fixed'
        automatically."""
        out = {}
        for c in self.conns.list():
            cid = c["connection_id"]
            if c["provider"] == "jarvus_paper" or not c.get("enabled"):
                continue
            expect: Dict[str, float] = {}
            for p in self.router.positions(cid):
                expect[p["symbol"]] = expect.get(p["symbol"], 0.0) + p["qty"]
            if not expect:
                continue
            try:
                prov = self.conns.provider(cid)
                problems = []
                for sym, q in expect.items():
                    have = prov.sellable(sym)
                    held_total = have
                    try:
                        held_total = next((x["qty"] for x in prov.positions()
                                           if x["symbol"] == prov.instrument(sym).get("broker_symbol")), have)
                    except ProviderError:
                        pass
                    if (held_total or 0.0) < q * 0.99:
                        problems.append(f"{sym}: deployments expect {q:.8g}, the account holds {held_total or 0:.8g}")
            except ProviderError as e:
                out[cid] = {"ok": None, "error": str(e)}
                continue
            out[cid] = {"ok": not problems, "problems": problems}
            if problems:
                for d in self.dep_cache.values():
                    if d["connection_id"] == cid:
                        self.dep_blocks[d["deployment_id"]] = "reconciliation mismatch: " + "; ".join(problems)
                self._alert("critical", "reconciliation_failed", f"{c['label']}: " + "; ".join(problems))
                self._audit("connection", f"{c['label']}: reconciliation FAILED - " + "; ".join(problems),
                            stage="reconciliation", severity="critical", connection_id=cid, mode=c["environment"],
                            payload={"expected": expect, "problems": problems})
            else:
                for d in self.dep_cache.values():
                    if d["connection_id"] == cid and self.dep_blocks.get(d["deployment_id"], "").startswith("reconciliation"):
                        self.dep_blocks.pop(d["deployment_id"], None)
        return out

    # ================================================================== readiness and controls
    def readiness(self, spec: dict) -> dict:
        """Everything that must be true before this bot may start in this mode. Required checks that fail disable START."""
        ck = Checks()
        mode = spec.get("mode")
        cid = spec.get("connection_id")
        bid = spec.get("bot_id")
        br = self.bots.get(bid) if bid else None
        ck.add("engine", "Bot engine running", self.running, "" if self.running else "the fleet is not running")
        ck.add("emergency", "Emergency stop off", not self.emergency,
               f"active since {_utc(self.emergency.get('time'))}: {self.emergency.get('reason')}" if self.emergency else "")
        ck.add("storage", "Storage writable", self.storage_ok, "" if self.storage_ok else "storage writes are failing")
        ck.add("bot", "Bot and strategy load", br is not None and self._is_user(br),
               "" if br is not None else f"no bot {bid}")
        if br is None:
            return ck.report()
        other = self.deps.active_for(bid)
        ck.add("single", "No other active deployment of this bot", other is None or other["deployment_id"] == spec.get("deployment_id"),
               f"{other['deployment_id']} is {other['state']}" if other and other["deployment_id"] != spec.get("deployment_id") else "")
        c = self.conns.get(cid) if cid else None
        ck.add("connection", "Account connection exists", c is not None, "" if c else f"no connection {cid}")
        if c is None:
            return ck.report()
        env_ok = {"paper": "paper", "live": "live", "demo": "demo"}.get(mode) == c["environment"]
        ck.add("mode", f"{(mode or '?').upper()} mode matches the account", env_ok,
               f"{c['label']} is a {c['environment']} account" + ("" if env_ok else f"; a {mode} bot cannot use it"))
        if self.demo and mode != "demo":
            ck.add("demo_ws", "Demo workspace trades demo only", False, "switch to your main workspace for paper or live")
        broker = c["provider"] != "jarvus_paper"
        otype = ((br.c.definition.get("order") or {}).get("type") or "market")
        if broker:
            ck.add("order_type", "Entries are market-type signals", otype == "market",
                   "" if otype == "market" else f"this strategy enters with resting {otype} orders, which broker accounts "
                   "do not support here (paper and demo do)")
        shorts = "entry_short" in br.c.rules
        ck.add("long_only", "Long-only trading", True if not shorts else None,
               "" if not shorts else "this strategy also signals shorts; deployments trade long only, so those are skipped",
               required=False)
        try:
            lim = validate_limits(spec.get("limits"))
            ck.add("limits", "Risk limits valid", True, ", ".join(f"{k} {v}" for k, v in lim.items() if v is not None))
        except ValueError as e:
            lim = None
            ck.add("limits", "Risk limits valid", False, str(e))
        try:
            alloc = float(spec.get("allocation") or 0)
        except (TypeError, ValueError):
            alloc = 0.0
        ck.add("allocation", "Capital allocated", alloc > 0, f"{alloc:,.2f}")
        if lim and lim.get("max_order_notional") and alloc and lim["max_order_notional"] > alloc:
            ck.add("order_cap", "Per-order cap within the allocation", False,
                   f"{lim['max_order_notional']:,.2f} is more than the allocation {alloc:,.2f}")
        # the account itself
        acct, test = None, None
        if broker:
            try:
                test = self.conns.test(cid)
                for x in test["checks"]:
                    ck.add("conn_" + x["id"], f"{c['provider_label']}: {x['label']}", x["status"] in ("pass", "skip") or
                           (x["status"] == "warn" and None), x["detail"], required=x["status"] == "fail" or x["id"] != "market_data",
                           warn=x["status"] == "warn")
                acct = (self.conns.latest(cid) or {}).get("body") if test["ok"] else None
            except Exception as e:                                      # noqa: BLE001
                ck.add("conn_test", "Connection test", False, str(e))
        else:
            acct = self.sims[cid].account() if cid in self.sims else None
            ck.add("conn_sim", f"{c['label']} available", acct is not None,
                   "simulated money" if acct else "the simulated account is not loaded in this workspace")
        if acct:
            used = self.deps.allocated(cid, exclude=spec.get("deployment_id"))
            bp = acct.get("buying_power")
            if bp is None:
                bp = acct.get("cash")
            if broker:
                ok = bp is not None and bp >= alloc
                detail = f"buying power {bp:,.2f} {acct.get('currency', '')}; this allocation {alloc:,.2f}" if bp is not None else "unknown"
            else:
                ok = acct["equity"] - used >= alloc
                detail = (f"equity {acct['equity']:,.2f}; already allocated to other bots {used:,.2f}; "
                          f"this allocation {alloc:,.2f}")
            ck.add("buying_power", "Enough capital for the allocation", ok, detail)
        # the market
        status, msg = self._series_status(br)
        ck.add("data", "Market data fresh", status == "ok" or (None if status in ("warming", "market_closed") else False),
               f"{br.symbol} {br.tf}: {status}" + (f" ({msg})" if msg else "") +
               (" - the bot will wait for data before its first entry" if status in ("warming", "market_closed") else ""),
               required=status not in ("warming", "market_closed"))
        if broker and test and test["ok"]:
            try:
                p = self.conns.provider(cid)
                inst = p.instrument(f"{br.venue}:{br.symbol}")
                ck.add("instrument", f"{br.symbol} tradable on {c['provider_label']}", inst.get("tradable", True),
                       f"as {inst.get('broker_symbol')} ({inst.get('asset_class')})")
                q = p.quote(f"{br.venue}:{br.symbol}")
                last = self._last_price(br.venue, br.symbol)
                if last and (q.get("ask") or q.get("last")):
                    ratio = (q.get("ask") or q.get("last")) / last
                    self.dep_ratio[spec.get("deployment_id") or "pending"] = ratio
                    ck.add("price_match", "Provider price matches the bot's market", 0.5 < ratio < 2.0,
                           f"provider {q.get('ask') or q.get('last'):.8g} vs bot data {last:.8g} (ratio {ratio:.3f})")
                kind = self.router.stop_kind(p, f"{br.venue}:{br.symbol}")
                ck.add("protective_stop", "Protective stop can rest on the provider", kind in ("stop", "stop_limit"),
                       f"{kind} orders, good-till-canceled")
                if inst.get("asset_class") == "us_equity" and last:
                    ck.add("whole_shares", "Allocation buys at least one share", alloc >= last,
                           f"one share ~{last:,.2f}; stocks trade whole shares here so the stop can be good-till-canceled")
                if hasattr(p, "validate") and last:
                    v = self.conns.validate_order(cid, f"{br.venue}:{br.symbol}", max(inst.get("min_qty") or 0.0001, 0.0001),
                                                  (q.get("bid") or last) * 0.5)
                    ck.add("validate", "Provider accepts a validate-only order", v.get("ok"), v.get("error") or v.get("descr") or "")
            except ProviderError as e:
                ck.add("instrument", f"{br.symbol} tradable on {c['provider_label']}", False, str(e))
        if mode == "live":
            a = self._live_auth()
            ck.add("live_auth", "Live trading authorised by the owner (separate step)", bool(a.get("authorized")),
                   f"authorised {a.get('time')}" if a.get("authorized") else "not authorised: Connections -> Live trading")
            if a.get("authorized"):
                ck.add("live_conn", "This account is on the live authorisation", cid in (a.get("connections") or []), "")
                cap = a.get("max_total_allocation")
                used_live = sum(float(d["allocation"]) for d in self.deps.list(active_only=True)
                                if d["mode"] == "live" and d["deployment_id"] != spec.get("deployment_id"))
                if cap:
                    ck.add("live_cap", "Within the live allocation cap", used_live + alloc <= float(cap),
                           f"live allocations {used_live + alloc:,.2f} of {float(cap):,.2f}")
                ok_l, why_l = self._live_allowed(cid)
                ck.add("live_loss", "Live daily loss limit not reached", ok_l or "not authorised on" in why_l, why_l)
            elig, why = self._strategy_live_record(br)
            waived = bool(a.get("waive_eligibility"))
            ck.add("eligibility", "Strategy earned live trading (untouched-test positive and 20+ positive paper trades)",
                   elig, why + (" (requirement waived by the owner in the live authorisation)" if waived and not elig else ""),
                   waived=waived and not elig)
            ck.add("brain_version", "Approved (frozen) brain version for live scoring", self.live_brain is not None,
                   f"champion {self.live_brain_version}" if self.live_brain is not None else
                   "no approved brain snapshot yet: live entries would be scored by the learning brain, which keeps "
                   "changing; freeze and approve one under Models", required=False)
            if hasattr(self, "strategy_status"):
                sst = self.strategy_status(br.c.id, br.c.version_hash)
                ck.add("approved", "This strategy version is approved for live (evaluation + owner approval)",
                       sst == "live_approved", f"registry status: {sst}" + ("" if sst == "live_approved" else
                       "; run its walk-forward evaluation and approve it under Research"))
        return ck.report()

    def _strategy_live_record(self, br) -> tuple:
        cost = "base" if br.venue == "yahoo" else ("low_fee_venue" if br.venue == "okx" else "retail_kraken")
        rows = [x for x in self._evaluation_rows(br.c.id) if x.get("cost") == cost]
        good = [x for x in rows if x.get("candidate") and (x["test"].get("expectancy_r") or -1) > 0
                and (x["test"].get("trades") or 0) >= 10]
        paper = self.storage.query("SELECT r FROM trades WHERE strategy_id=? AND instrument=? AND r IS NOT NULL AND "
                                   "mode IN ('paper','demo')", (br.c.id, br.symbol))
        avg = sum(x["r"] for x in paper) / len(paper) if paper else None
        if not good:
            best = max((x["test"].get("expectancy_r") or -9 for x in rows), default=None)
            return False, ("not positive on the untouched test at this market's costs"
                           + (f" (best {best:+.2f}R)" if best is not None else " (never evaluated)")
                           + f"; paper: {len(paper)} trades" + (f", {avg:+.2f}R average" if avg is not None else ""))
        if len(paper) < 20:
            return False, f"untested-period result positive; {len(paper)} of 20 paper trades so far"
        if avg <= 0:
            return False, f"paper record {avg:+.2f}R per trade over {len(paper)} trades"
        return True, f"untouched test {good[0]['test']['expectancy_r']:+.2f}R; paper {avg:+.2f}R over {len(paper)} trades"

    def start_deployment(self, spec: dict) -> dict:
        """START BOT: readiness first (never trusted from an earlier call), then only this bot, in this mode."""
        bid = spec.get("bot_id")
        br = self.bots.get(bid)
        if br is None or not self._is_user(br):
            raise ValueError("build the bot first (strategy and market)")
        mode, cid = spec.get("mode"), spec.get("connection_id")
        conn = self.conns.get(cid)
        dep = self.deps.latest_for(bid)
        if dep is None or dep["state"] not in ("stopped",) or dep["mode"] != mode or dep["connection_id"] != cid:
            if dep is not None and dep["state"] in ACTIVE:
                raise ValueError(f"this bot is already {dep['state']}; stop it before changing mode or account")
            dep = self.deps.create(bid, mode, cid, spec.get("allocation"), (conn or {}).get("account", {}).get("currency")
                                   or self.account.currency, spec.get("limits"), br.c.version_hash, br.config_version)
        else:
            dep = self.deps.update(dep["deployment_id"], allocation=float(spec.get("allocation") or dep["allocation"]),
                                   limits=validate_limits(spec.get("limits") if spec.get("limits") is not None else dep["limits"]))
        spec = dict(spec, deployment_id=dep["deployment_id"], allocation=dep["allocation"], limits=dep["limits"])
        rep = self.readiness(spec)
        if "pending" in self.dep_ratio:
            self.dep_ratio[dep["deployment_id"]] = self.dep_ratio.pop("pending")
        self.deps.update(dep["deployment_id"], readiness=rep)
        if not rep["ok"]:
            self._audit("control", f"{bid}: START refused - " + "; ".join(rep["failed"]), stage="start_refused",
                        severity="warning", mode=mode, bot_id=bid, deployment_id=dep["deployment_id"], connection_id=cid,
                        payload=rep)
            return {"started": False, "deployment": self.deps.get(dep["deployment_id"]), "readiness": rep}
        if mode == "live":
            conf = spec.get("confirmation") or {}
            want = {"deployment_id": dep["deployment_id"], "connection_id": cid, "allocation": float(dep["allocation"])}
            if (str(conf.get("ack", "")).strip().upper() != START_LIVE_ACK or conf.get("connection_id") != cid
                    or abs(float(conf.get("allocation") or -1) - float(dep["allocation"])) > 1e-9
                    or conf.get("bot_id") != bid):
                return {"started": False, "needs_confirmation": True, "confirm": dict(want, bot_id=bid, ack=START_LIVE_ACK,
                        account=(conn or {}).get("account"), strategy=br.c.definition.get("name"), strategy_id=br.c.id,
                        limits=dep["limits"], market=br.symbol), "readiness": rep,
                        "deployment": self.deps.get(dep["deployment_id"])}
            self.deps.update(dep["deployment_id"], confirmation=dict(conf, time=now_ms()))
        self.dep_peak.setdefault(dep["deployment_id"], float(dep["allocation"]))
        dep = self.deps.set_state(dep["deployment_id"], "running", f"started in {mode.upper()} on {cid}")
        self.dep_blocks.pop(dep["deployment_id"], None)
        self._refresh_deps()
        self._persist_states([bid])
        return {"started": True, "deployment": dep, "readiness": rep}

    def pause_deployment(self, dep_id: str) -> dict:
        dep = self.deps.get(dep_id)
        if dep is None or dep["state"] != "running":
            raise ValueError("only a running bot can be paused")
        dep = self.deps.set_state(dep_id, "paused", "PAUSE NEW ENTRIES: open positions keep being managed")
        n = len(self.router.cancel_entries(dep_id, "paused: no new entries"))
        br = self.bots.get(dep["bot_id"])
        if br and br.tm.pending is not None and not br.tm.pending.exit:
            br.tm.pending = None
            n += 1
        self._refresh_deps()
        return {"deployment": dep, "entry_orders_canceled": n}

    def resume_deployment(self, dep_id: str) -> dict:
        dep = self.deps.get(dep_id)
        if dep is None or dep["state"] != "paused":
            raise ValueError("only a paused bot can be resumed")
        if self.emergency:
            raise ValueError("clear the emergency stop first")
        self.dep_blocks.pop(dep_id, None) if not str(self.dep_blocks.get(dep_id, "")).startswith("reconciliation") else None
        dep = self.deps.set_state(dep_id, "running", "resumed")
        self._refresh_deps()
        return {"deployment": dep}

    def stop_deployment(self, dep_id: str, positions: str) -> dict:
        """STOP BOT: entries blocked at once, working entry orders canceled; then retain protective orders or close."""
        if positions not in ("retain", "close"):
            raise ValueError("choose what happens to open positions: retain (keep protective orders) or close")
        dep = self.deps.get(dep_id)
        if dep is None or dep["state"] not in ACTIVE:
            raise ValueError("this bot is not running")
        br = self.bots.get(dep["bot_id"])
        self.dep_blocks[dep_id] = "stopping"
        canceled = self.router.cancel_entries(dep_id, "bot stopped")
        if br and br.tm.pending is not None and not br.tm.pending.exit:
            br.tm.pending = None
        held = self.router.position(dep_id) is not None or (br is not None and br.tm.pos is not None)
        out = {"entry_orders": canceled}
        if positions == "close" and held and br is not None:
            s = self.hub.get(br.venue, br.symbol, br.tf)
            fr = s.frame() if s else None
            ref = (fr.c[-1] if fr is not None and fr.n else None) or self._last_price(br.venue, br.symbol) or \
                (br.tm.pos.entry_price if br.tm.pos else 0.0)
            iid = hashlib.sha256(f"{br.id}|stop|{now_ms()}".encode()).hexdigest()[:20]
            res = self.router.exit(dep, ref_price=ref, reason="owner stopped the bot and closed the position", intent_id=iid,
                                   correlation_id=self.trade_corr.get(br.id), market=True)
            out["close"] = {k: v for k, v in res.items() if k != "orders"}
            if fr is not None and fr.n and br.tm.pos is not None:
                self._after_exit(br, fr, fr.n - 1, "owner stopped the bot", res, dep)
            still = self.router.position(dep_id) is not None
            state = "error" if still else "stopped"
            dep = self.deps.set_state(dep_id, state, "STOP (close): " + ("position closed" if not still else
                                                                         "the close did NOT complete; see the order log"))
        elif held:
            dep = self.deps.set_state(dep_id, "stopped_retaining", "STOP (retain): the position stays open with its protective "
                                      "order until it fills or you close it")
        else:
            dep = self.deps.set_state(dep_id, "stopped", "STOP: no open position")
        self.dep_blocks.pop(dep_id, None)
        self._refresh_deps()
        self._persist_states([dep["bot_id"]])
        out["deployment"] = dep
        return out

    def emergency_stop(self, reason: str) -> dict:
        """EMERGENCY STOP: new entries blocked first (persisted), then every working entry order is canceled.
        Positions are not closed here; that is a separate, separately confirmed action (close_all_positions)."""
        self.emergency = {"time": now_ms(), "reason": reason}
        self.storage.kv_set("emergency", self.emergency)
        if self.live.armed:
            self.live.disarm(f"emergency stop: {reason}")
        results = self.router.cancel_entries(None, f"emergency stop: {reason}")
        virtual = 0
        for br in self.bots.values():
            if br.tm.pending is not None and not br.tm.pending.exit:
                br.tm.pending = None
                virtual += 1
        self._persist_states()
        failed = [r for r in results if not r["ok"]]
        self._event("critical", "emergency_stop", f"EMERGENCY STOP ({reason}): new entries blocked; "
                                                  f"{len(results) - len(failed)} of {len(results)} working entry orders canceled"
                    + (f", {len(failed)} NOT confirmed" if failed else "") + f"; {virtual} simulated resting entries removed. "
                    "Positions stay open with their protective orders until you close them.")
        self._audit("control", f"EMERGENCY STOP: {reason}", stage="emergency_stop", severity="critical",
                    payload={"canceled": results, "simulated_resting_entries_removed": virtual})
        return {"blocked": True, "reason": reason, "entry_orders": results, "failed": failed,
                "simulated_resting_entries_removed": virtual}

    def close_all_positions(self, confirm: str, reason: str = "owner closed all positions") -> dict:
        """Separately confirmed: close every deployment's position (and the research fleet's). Reports each result."""
        if str(confirm).strip().upper() != "CLOSE ALL":
            raise ValueError("type CLOSE ALL to confirm closing every position")
        out = []
        for dep in list(self.dep_cache.values()):
            if self.router.position(dep["deployment_id"]) is None and not (
                    self.bots.get(dep["bot_id"]) and self.bots[dep["bot_id"]].tm.pos is not None):
                continue
            try:
                r = self.stop_deployment(dep["deployment_id"], "close")
                res = r.get("close") or {}
                out.append({"bot_id": dep["bot_id"], "mode": dep["mode"], "status": res.get("status"),
                            "reason": res.get("reason"), "sold": res.get("qty"), "left": res.get("left")})
            except Exception as e:                                      # noqa: BLE001
                out.append({"bot_id": dep["bot_id"], "mode": dep["mode"], "status": "error", "reason": str(e)})
        research = 0
        for br in self.bots.values():
            if self._is_user(br) or br.tm.pos is None:
                continue
            s = self.hub.get(br.venue, br.symbol, br.tf)
            fr = s.frame() if s else None
            if fr is None or fr.n == 0:
                out.append({"bot_id": br.id, "mode": "research", "status": "error", "reason": "no price"})
                continue
            a = {"kind": "exit", "side": -br.tm.pos.side, "qty": br.tm.pos.qty, "ref_price": fr.c[-1],
                 "reason": reason, "reduce_only": True}
            br.tm.awaiting = {"kind": "exit", "reason": reason}
            try:
                self._execute_intent(br, fr, fr.n - 1, dict(a, action="intent"))
                research += 1
            except Exception as e:                                      # noqa: BLE001
                out.append({"bot_id": br.id, "mode": "research", "status": "error", "reason": str(e)})
        self._persist_states()
        self._persist_account()
        bad = [x for x in out if x.get("status") not in ("filled",)]
        self._audit("control", f"CLOSE ALL POSITIONS: {len(out) - len(bad)} deployment positions closed, {len(bad)} not "
                    f"completed; {research} research-fleet positions closed", stage="close_all",
                    severity="critical" if bad else "warning", payload={"results": out, "research_closed": research})
        return {"results": out, "not_completed": bad, "research_closed": research}

    def clear_emergency(self) -> dict:
        self.emergency = None
        self.storage.kv_set("emergency", None)
        self._event("warning", "emergency_cleared", "emergency stop cleared by the owner; bots that are running may enter again")
        self._audit("control", "emergency stop cleared by the owner", stage="emergency_cleared", severity="warning")
        return {"cleared": True}

    def create_user_bot(self, args: dict) -> dict:
        sid, venue, inst = args.get("strategy_id"), args.get("venue"), args.get("instrument")
        if sid not in self.strategies:
            raise ValueError(f"unknown strategy {sid}")
        if not venue or not inst:
            raise ValueError("choose a market")
        if self.demo and venue != "demo":
            raise ValueError("the demo workspace trades the demo market only")
        if venue == "yahoo":
            self.registry.require(venue, inst)
        elif self.registry.get(venue, inst) is None and not (self.registry.ensure_venue(venue) and self.registry.get(venue, inst)):
            raise ValueError(f"{venue}:{inst} is not an available market")
        b = self.deps.create_bot(sid, venue, inst, args.get("params") or {}, args.get("name"), args.get("source_bot"))
        cfg = {"bot_id": b["bot_id"], "name": b["name"], "strategy_id": sid, "venue": venue, "instrument": inst,
               "params": b["params"], "enabled": True, "user": True}
        self.bot_cfgs.append(cfg)
        self._add_bot(cfg, None)
        self.register_bot_strategy(self.bots[b["bot_id"]])
        self._refresh_deps()
        self._audit("control", f"bot {b['bot_id']} built: {self.strategies[sid].get('name')} on {inst}",
                    stage="bot_created", bot_id=b["bot_id"], symbol=inst, venue=venue)
        return b

    def live_authorize(self, args: dict) -> dict:
        if str(args.get("ack", "")).strip().upper() != LIVE_ACK:
            raise ValueError(f"type exactly: {LIVE_ACK}")
        conns = [c for c in (args.get("connections") or []) if (self.conns.get(c) or {}).get("environment") == "live"]
        if not conns:
            raise ValueError("choose at least one live account connection")
        for k in ("max_total_allocation", "daily_loss_limit"):
            try:
                if not float(args.get(k) or 0) > 0:
                    raise ValueError
            except (TypeError, ValueError):
                raise ValueError(f"{k.replace('_', ' ')} must be more than 0")
        a = {"authorized": True, "time": now_ms(), "connections": conns,
             "max_total_allocation": float(args["max_total_allocation"]), "daily_loss_limit": float(args["daily_loss_limit"]),
             "waive_eligibility": bool(args.get("waive_eligibility"))}
        self.storage.kv_set("live_authorization", a)
        self._audit("control", f"LIVE trading authorised by the owner on {', '.join(conns)} (total allocation cap "
                    f"{a['max_total_allocation']:,.2f}, daily loss limit {a['daily_loss_limit']:,.2f})"
                    + ("; paper-record requirement WAIVED" if a["waive_eligibility"] else ""), stage="live_authorized",
                    severity="critical", mode="live", payload=a)
        return a

    def live_revoke(self, reason: str = "owner") -> dict:
        a = dict(self._live_auth(), authorized=False, revoked=now_ms(), revoke_reason=reason)
        self.storage.kv_set("live_authorization", a)
        paused = []
        for d in list(self.dep_cache.values()):
            if d["mode"] == "live" and d["state"] == "running":
                self.deps.set_state(d["deployment_id"], "paused", "live authorisation revoked", "owner")
                paused.append(d["deployment_id"])
        self._refresh_deps()
        self._audit("control", f"live trading authorisation revoked ({reason}); {len(paused)} live bots paused",
                    stage="live_revoked", severity="critical", mode="live", payload={"paused": paused})
        return {"revoked": True, "paused": paused}

    def set_research_autopilot(self, on: bool) -> dict:
        self.autopilot_set(on)
        return {"research_autopilot": self.research_autopilot}

    # ================================================================== AUTOPILOT: one button, every research bot
    def autopilot_set(self, on: bool, by: str = "owner") -> dict:
        on = bool(on)
        if on and self.emergency:
            raise ValueError("EMERGENCY STOP is on: clear it first (it was set on purpose, so autopilot never overrides it)")
        self.autopilot = {"on": on, "since": now_ms(), "by": by}
        self.storage.kv_set("autopilot", self.autopilot)
        self.research_autopilot = on
        self.storage.kv_set("research_autopilot", on)
        n = sum(1 for b in self.bots.values() if not self._is_user(b))
        mode = "demo" if self.demo else "research"
        self._audit("control", (f"AUTOPILOT ON: {n} research bots trade the simulated research account by themselves "
                                "(the brain sizes and vetoes, exits are automatic) and research runs on a schedule; "
                                "real money stays off") if on else
                    "AUTOPILOT OFF: research bots stop opening trades; open positions are still managed until they exit",
                    stage="autopilot", severity="warning", mode=mode, payload={"on": on, "bots": n, "by": by})
        return self.autopilot_status()

    def autopilot_status(self) -> dict:
        from mab.research.jobs import JobQueue
        states = {"watching": 0, "managing_position": 0, "waiting": 0, "error": 0}
        n = 0
        for br in self.bots.values():
            if self._is_user(br):
                continue
            n += 1
            if br.tm.pos is not None:
                states["managing_position"] += 1
            elif br.state in ("degraded", "disabled") or not br.enabled:
                states["error"] += 1
            elif br.state in ("warming", "data_unavailable"):
                states["waiting"] += 1
            else:
                states["watching"] += 1
        day = int(time.time() // 86400 * 86400 * 1000)
        t = self.storage.query("SELECT COUNT(*) AS n, COALESCE(SUM(pnl),0) AS pnl, COALESCE(SUM(fees),0) AS fees,"
                               " SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) AS wins FROM trades"
                               " WHERE deployment_id IS NULL AND exit_time >= ?", (day,))[0]
        q = JobQueue(self.storage)
        done_today = self.storage.query("SELECT COUNT(*) AS n FROM research_jobs WHERE requested_by='autopilot' AND"
                                        " state='done' AND finished >= ?", (day,))[0]["n"]
        sched = self.storage.kv_get("autopilot_schedule") or {}
        acct = self.account.summary()
        return {"on": self.research_autopilot, "since": self.autopilot.get("since"), "by": self.autopilot.get("by"),
                "emergency": bool(self.emergency), "paused": bool(self.paused), "bots": n, "states": states,
                "mode": "demo" if self.demo else "research", "real_money": False,
                "account": {"connection_id": RESEARCH_CONN, "equity": acct.get("equity"), "cash": acct.get("cash"),
                            "currency": acct.get("currency"), "open_positions": acct.get("open_positions"),
                            "exposure_pct": acct.get("gross_exposure_pct")},
                "today": {"trades": t["n"], "pnl_after_fees": t["pnl"], "fees": t["fees"], "wins": t["wins"] or 0},
                "brain": {"trades_learned": self.brain.stats.get("learned", 0)},
                "research": {"queue": q.counts(), "done_today": done_today, "last_walk_forward": sched.get("last_wf"),
                             "last_gate_check": sched.get("last_gate"), "last_brain_check": sched.get("last_brain"),
                             "evaluated": len(sched.get("evaluated") or {}),
                             "every_min": AUTOPILOT_WF_EVERY_MS // 60_000},
                "note": "simulated money only; live trading needs your separate authorisation and a typed START LIVE "
                        "for each live bot"}

    def _autopilot_cycle(self):
        """Scheduled research while autopilot is on: one walk-forward evaluation at a time in rotation over the bots'
        strategy/market pairs, a daily volatility-gate drift check and a daily brain snapshot compared with the approved
        brain. Results are recorded for the owner; nothing is promoted to live by itself."""
        if not self.research_autopilot or self.emergency or not self.cfg.get("autopilot_research", True):
            return
        from mab.research.jobs import JobQueue
        q = JobQueue(self.storage)
        c = q.counts()
        if c.get("queued", 0) + c.get("running", 0) >= AUTOPILOT_MAX_PENDING:
            return
        sched = dict(self.storage.kv_get("autopilot_schedule") or {})
        now = now_ms()
        day = 86_400_000
        if now - sched.get("last_brain", 0) >= day and self.brain.stats.get("learned", 0) >= 30:
            sched["last_brain"] = now
            snap = self.registry_models.snapshot_brain(self.brain, "autopilot daily snapshot")
            champ = self.registry_models.champion("brain")
            q.submit("brain_eval", {"candidate": snap["version"], "champion": champ["version"] if champ else "none"},
                     AUTOPILOT_PRIORITY, "autopilot")
            self._prune_brain_snapshots()
        elif now - sched.get("last_gate", 0) >= day and getattr(self.brain, "gates", None) is not None:
            sched["last_gate"] = now
            venue, inst = ("demo", "DEMO-BTC") if self.demo else ("coinbase", "BTC-USD")
            q.submit("gate_drift", {"venue": venue, "instrument": inst, "asset": "crypto"}, AUTOPILOT_PRIORITY, "autopilot")
        elif now - sched.get("last_wf", 0) >= AUTOPILOT_WF_EVERY_MS:
            sched["last_wf"] = now
            br = self._next_autopilot_eval(sched)
            if br is not None:
                defn = dict(br.c.definition, id=br.c.id, timeframe=br.tf)
                own = dict(defn.get("params") or {})
                defn["params"] = dict(own, **{k: v for k, v in (br.c.params or {}).items() if k in own})
                days = 30 if br.tf in ("1m", "5m") else (60 if br.tf == "15m" else 180)
                q.submit("walk_forward", {"definition": defn, "venue": br.venue, "instrument": br.symbol, "days": days,
                                          "draws": 100, "fee_profile": "venue"}, AUTOPILOT_PRIORITY, "autopilot")
        self.storage.kv_set("autopilot_schedule", sched)

    def _next_autopilot_eval(self, sched: dict):
        done = dict(sched.get("evaluated") or {})
        now = now_ms()
        bots = sorted((b for b in self.bots.values() if not self._is_user(b) and b.enabled), key=lambda b: b.id)
        if not bots:
            return None
        start = int(sched.get("wf_i", 0)) % len(bots)
        for k in range(len(bots)):
            br = bots[(start + k) % len(bots)]
            key = f"{br.c.version_hash}|{br.venue}|{br.symbol}"
            if now - done.get(key, 0) >= AUTOPILOT_REEVAL_MS:
                done[key] = now
                if len(done) > 1000:
                    done = dict(sorted(done.items(), key=lambda kv: kv[1])[-1000:])
                sched["evaluated"] = done
                sched["wf_i"] = (start + k + 1) % len(bots)
                return br
        return None

    def _prune_brain_snapshots(self, keep: int = 14):
        rows = self.storage.query("SELECT version FROM model_versions WHERE model='brain' AND status='candidate'"
                                  " ORDER BY created DESC")
        for r in rows[keep:]:
            self.storage.write("DELETE FROM model_versions WHERE model='brain' AND version=? AND status='candidate'",
                               (r["version"],))

    def set_paper_balance(self, cid: str, kind: str, amount: float) -> dict:
        if cid == RESEARCH_CONN:
            rec = getattr(self.account, kind)(float(amount), "balance changed by the owner (simulated)")
            self.storage.save_cash_flow(dict(rec, note=f"{cid}: {rec.get('note', '')}"))
            self.risk.reset_peak(self.account.equity())
            if cid in self.port_risk:
                self.port_risk[cid].reset_peak(self.account.equity())
            self._persist_account()
        elif cid in self.sims:
            if kind == "withdraw" and float(amount) >= self.sims[cid].acct.equity():
                raise ValueError("withdraw less than the account holds")
            rec = self.sims[cid].set_balance(kind, amount, "balance changed by the owner (simulated)")
            self.storage.save_cash_flow(dict(rec, note=f"{cid}: {rec.get('note', '')}"))
            self._port_risk(cid).reset_peak(self.sims[cid].acct.equity())
        else:
            raise ValueError("only simulated accounts have a settable balance; broker balances are what the broker reports")
        self._audit("control", f"{cid}: simulated balance {kind} {float(amount):,.2f} (paper money, not a deposit)",
                    stage="paper_balance", mode="demo" if self.demo else "paper", connection_id=cid, payload=rec)
        return rec

    # ================================================================== models and versions
    def reload_models(self) -> dict:
        """Live deployments score with the approved (champion) brain snapshot, which never changes by itself; a
        promotion takes effect here. Without an approved snapshot, live entries are scored by the learning brain and
        the readiness check says so."""
        import json as _json
        from mab.brain import FleetBrain
        ch = self.registry_models.champion("brain")
        if ch and ch.get("blob"):
            b = FleetBrain(mode=self.brain.mode)
            b.restore(_json.loads(ch["blob"]))
            b.gates = self.brain.gates                      # market readings are shared; learned parameters are not
            b.consensus = self.brain.consensus
            self.live_brain, self.live_brain_version = b, ch["version"]
        else:
            self.live_brain, self.live_brain_version = None, None
        return {"live_brain": self.live_brain_version}

    def strategy_status(self, strategy_id: str, version_hash: str) -> str:
        return self.registry_models.status(strategy_id, version_hash)

    def register_bot_strategy(self, br) -> None:
        try:
            self.registry_models.register_strategy(br.c.id, br.c.definition, br.c.version_hash, "catalog")
        except Exception as e:                                          # noqa: BLE001
            log.debug("strategy version not registered: %s", e)

    def drift_cycle(self) -> list:
        from mab.research import drift
        try:
            return drift.performance(self.storage, self._evaluation_rows)
        except Exception as e:                                          # noqa: BLE001
            log.warning("drift check: %s", e)
            return []

    # ================================================================== live prices: the balance moves with the market
    def _mark_loop(self):
        base = float(self.cfg.get("mark_interval_s", 5.0))
        while self.running:
            # about one price request per market per pass; many open markets slow the pass so the venues' request
            # limits are never pressed (20 open markets: every 12 s; one: every 5 s)
            time.sleep(max(base, 0.6 * len(self._open_instruments())))
            if not self.running:
                break
            try:
                self.mark_live()
            except Exception as e:                                      # noqa: BLE001 - never stop trading for this
                log.debug("live prices: %s", e)

    def _open_instruments(self) -> set:
        keys = {(p["venue"], p["instrument"]) for p in list(self.account.positions.values())}
        for sim in list(self.sims.values()):
            keys |= {(p["venue"], p["instrument"]) for p in list(sim.acct.positions.values())}
        return keys

    def mark_live(self, stock_every_s: float = 30.0) -> dict:
        """Value every open position at the market's price right now (the order book's mid for crypto, Yahoo's
        latest price for stocks), so the balance moves as prices move, not only when a bar closes. Only markets
        with an open position are asked, so this stays within the venues' request limits."""
        now = time.time()
        out = {}
        for venue, sym in sorted(self._open_instruments()):
            ad = self.hub.adapters.get(venue)
            if ad is None or not hasattr(ad, "last_price"):
                continue
            prev = self.live_prices.get((venue, sym))
            if venue == "yahoo" and prev and now - prev[2] < stock_every_s:
                continue
            try:
                q = ad.last_price(sym)
            except Exception as e:                                      # noqa: BLE001 - keep the last good price
                log.debug("price %s:%s: %s", venue, sym, e)
                continue
            if not q or not q[0] or q[0] <= 0:
                continue
            px, t, src = float(q[0]), int(q[1] or now_ms()), q[2]
            self.live_prices[(venue, sym)] = (px, t, now, src)
            self.account.mark(venue, sym, px, t)
            for sim in list(self.sims.values()):
                sim.acct.mark(venue, sym, px, t)
            out[f"{venue}:{sym}"] = px
        return out

    def decision_summary(self, minutes: int = 60, recent: int = 6) -> dict:
        """What the AI decided in the last hour, counted from the audit log: how many entry signals the bots raised,
        how many the brain let through, and why it refused the rest. The AI trades rarely on purpose: most signals
        would cost more in fees than they are expected to earn."""
        hit = getattr(self, "_dec_cache", None)
        if hit and time.time() - hit[0] < 15 and hit[1] == (minutes, recent):    # refreshed every ~2 s by open pages
            return hit[2]
        since = now_ms() - minutes * 60_000
        rows = self.storage.audit_search(kinds=["brain"], mode="research", since=since, limit=2000)
        refused: Dict[str, int] = {}
        taken = 0
        latest = []
        for r in rows:
            p = r.get("payload") or {}
            act = p.get("action")
            if act is None:
                continue
            if act == "veto":
                k = p.get("veto_kind") or "learned"
                refused[k] = refused.get(k, 0) + 1
            else:
                taken += 1
            if len(latest) < recent:
                latest.append({"time": r["ts"], "bot_id": r.get("bot_id"), "symbol": r.get("symbol"), "action": act,
                               "kind": p.get("veto_kind"), "summary": r.get("summary")})
        n_refused = sum(refused.values())
        out = {"minutes": minutes, "signals": taken + n_refused, "approved": taken, "refused": n_refused,
               "refused_by": refused, "latest": latest, "brain_mode": self.brain.mode}
        self._dec_cache = (time.time(), (minutes, recent), out)
        return out

    def money_view(self) -> dict:
        """The account the AI trades, as it stands right now: balance, cash, today's result, and every open
        position valued at the latest price (with where that price came from)."""
        a = self.account
        with a.lock:
            pos = [dict(p) for p in a.positions.values()]
            marks = dict(a.marks)
            cash, eq = a.cash, a.equity()
            slots, slot_eq = a.slots_in_use(eq), eq / max(1, a.slots_in_use(eq))
        day0 = utc_day_start()
        tr = self.storage.query("SELECT COUNT(*) AS n, COALESCE(SUM(pnl),0) AS pnl, COALESCE(SUM(fees),0) AS fees,"
                                " SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) AS wins FROM trades"
                                " WHERE deployment_id IS NULL AND exit_time >= ?", (day0,))[0]
        rows, unreal = [], 0.0
        for p in pos:
            px, mt = marks.get((p["venue"], p["instrument"]), (p["avg_price"], None))
            br = self.bots.get(p["bot_id"])
            tp = br.tm.pos if br is not None else None
            qty = p["qty"]
            cost = abs(qty) * p["avg_price"]
            pnl = (px - p["avg_price"]) * qty
            unreal += pnl
            live = self.live_prices.get((p["venue"], p["instrument"]))
            rows.append({"bot_id": p["bot_id"], "strategy": br.c.definition.get("name") if br is not None else None,
                         "venue": p["venue"], "symbol": p["instrument"], "side": "long" if qty > 0 else "short",
                         "qty": abs(qty), "entry": p["avg_price"], "price": px, "price_time": mt,
                         "price_source": live[3] if live and abs(live[0] - px) < 1e-12 else "latest bar close",
                         "value": abs(qty) * px, "cost": cost, "pnl": pnl, "pnl_pct": pnl / cost * 100 if cost else None,
                         "stop": getattr(tp, "stop", None), "target": getattr(tp, "target", None), "opened": p.get("opened")})
        rows.sort(key=lambda r: -(r["opened"] or 0))
        start = self.risk.day_start_equity
        fills = self.storage.query("SELECT time, bot_id, instrument, venue, side, qty, price, fee FROM fills"
                                   " WHERE deployment_id IS NULL ORDER BY time DESC LIMIT 12")
        closed = self.storage.query("SELECT bot_id, instrument, venue, side, qty, entry_price, exit_price, entry_time,"
                                    " exit_time, fees, pnl, r, exit_reason FROM trades WHERE deployment_id IS NULL"
                                    " ORDER BY exit_time DESC LIMIT 12")
        return {"connection_id": RESEARCH_CONN, "mode": "demo" if self.demo else "research", "time": now_ms(),
                "decisions": self.decision_summary(), "equity": eq, "cash": cash, "currency": a.currency,
                "invested": sum(r["value"] for r in rows),
                "unrealized": unreal, "realized_today": tr["pnl"], "fees_today": tr["fees"], "trades_today": tr["n"],
                "wins_today": tr["wins"] or 0, "day_start_equity": start,
                "change_today": (eq - start) if start else None,
                "change_today_pct": ((eq / start - 1) * 100) if start else None,
                "slots_in_use": slots, "slot_equity": slot_eq, "positions": rows, "recent_fills": fills,
                "recent_trades": closed, "autopilot": self.research_autopilot, "real_money": False}

    # ================================================================== views
    def deployment_view(self, dep: dict) -> dict:
        br = self.bots.get(dep["bot_id"])
        pos = self.router.position(dep["deployment_id"])
        last = self._last_price(br.venue, br.symbol) if br else None
        unreal = None
        if pos and last:
            unreal = (last * (pos.get("ratio") or 1.0) - pos["avg_price"]) * pos["qty"] - (pos.get("fees") or 0)
        trades = self.storage.query("SELECT COUNT(*) AS n, COALESCE(SUM(pnl),0) AS pnl, COALESCE(SUM(fees),0) AS fees,"
                                    " AVG(r) AS avg_r, SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) AS wins FROM trades"
                                    " WHERE deployment_id=?", (dep["deployment_id"],))[0]
        working = [o for o in self.engine.open_orders(deployment_id=dep["deployment_id"])]
        state = dep["state"]
        activity = self.activity(br, dep, pos, working) if br else state
        return {**dep, "bot": {"id": br.id, "name": br.cfg.get("name"), "strategy_id": br.c.id,
                               "strategy": br.c.definition.get("name"), "family": br.c.definition.get("family"),
                               "venue": br.venue, "symbol": br.symbol, "tf": br.tf, "last_decision": br.last_decision,
                               "message": br.message, "data_state": br.state} if br else None,
                "activity": activity, "blocked": self.dep_blocks.get(dep["deployment_id"]),
                "position": pos, "last_price": last, "unrealized": unreal, "equity": self._dep_equity(dep),
                "peak": self.dep_peak.get(dep["deployment_id"]),
                "performance": {"trades": trades["n"], "pnl_after_fees": trades["pnl"], "fees": trades["fees"],
                                "avg_r": trades["avg_r"], "wins": trades["wins"]},
                "working_orders": working}

    def activity(self, br, dep, pos, working) -> str:
        """What the bot is doing now: watching, evaluating, waiting, submitting, partially_filled, managing_position,
        exiting, paused, error, stopped."""
        if dep is None or dep["state"] == "stopped":
            return "stopped"
        if dep["state"] == "error" or br.state in ("degraded", "disabled"):
            return "error"
        if any(o["state"] in ("NEW", "SUBMITTING", "UNKNOWN") for o in working if o.get("purpose") != "protective_stop"):
            return "submitting"
        if any(o["state"] == "PARTIALLY_FILLED" and o.get("purpose") == "entry" for o in working):
            return "partially_filled"
        if any(o.get("purpose") == "exit" for o in working):
            return "exiting"
        if getattr(br, "evaluating", False):
            return "evaluating"
        if dep["state"] == "paused":
            return "paused"
        if pos is not None or br.tm.pos is not None:
            return "managing_position" if dep["state"] != "stopped_retaining" else "holding_protected"
        if br.state in ("warming", "data_unavailable") or br.tm.pending is not None or self.dep_blocks.get(dep["deployment_id"]):
            return "waiting"
        return "watching"
