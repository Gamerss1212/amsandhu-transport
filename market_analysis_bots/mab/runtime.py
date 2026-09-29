"""Fleet runtime: runs every enabled bot against shared live data with paper execution.

Flow for each new completed bar of a series:
    hub -> dispatcher -> each subscribed bot: rules evaluated on the shared Frame ->
    TradeManager decision -> OrderIntent -> portfolio risk check -> paper broker -> fills ->
    account, storage, health

Isolation: every bot runs inside its own error boundary. A failing bot is marked degraded,
then disabled after repeated failures; other bots are unaffected. Bots cannot see each other's
state; the only shared objects are read-only Frames and the risk/account services.

Control: CLI and dashboard commands go through the storage control queue (pause, resume,
emergency stop, balance changes, enable/disable a bot, stop). The runtime applies them within
about a second and records the outcome.

Recovery: bot state (open position, pending order, counters) is saved after every decision and
restored at start. Bars missed while stopped are replayed for protective exits only; no new
trades are opened on stale bars.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import queue
import threading
import time
import traceback
from collections import deque
from dataclasses import asdict
from typing import Any, Dict, List, Optional, Tuple

from mab import __version__
from mab.account import Account
from mab.brain import FleetBrain, fee_key
from mab.volgate import HORIZON as GATE_HORIZON, Bars as GateBars, VolGate
from mab import broker_setup
from mab.live import LiveExecutor
from mab.broker import PaperBroker
from mab.costs import FEE_PROFILE_LABELS, FEE_PROFILES, FEES, BacktestFiller, CostModel, round_trip, tier_for
from mab.data.hub import Hub
from mab.expr import Events
from mab.instruments import InstrumentRegistry
from mab.models import BotHealth, OrderIntent, now_ms
from mab.net import Http
from mab.risk import RiskLimits, RiskManager
from mab.storage import Storage, StorageError
from mab.strategy import Compiled, TradeManager, compile_strategy, evaluate, explain

log = logging.getLogger("mab.runtime")


BOT_STATES = ("running", "warming", "idle_no_signal", "data_unavailable", "degraded", "stopped", "disabled", "paused")


def _pctl(vals, p):
    if not vals:
        return None
    s = sorted(vals)
    return s[min(len(s) - 1, int(p * len(s)))]


def _default_priors(config: dict) -> Optional[str]:
    """strategies/results/evaluation_summary.json next to the catalog (plain or .gz)."""
    from mab.cli import catalog_path
    try:
        return os.path.join(os.path.dirname(catalog_path(config)), "results", "evaluation_summary.json")
    except FileNotFoundError:
        return None


def load_events(config: dict) -> Events:
    """Scheduled-event calendars (FOMC, CPI) from strategies/data/events.json, as session-date ordinals."""
    from datetime import date as _date
    ev = Events()
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for p in (config.get("events_file"), os.path.join(os.path.dirname(here), "strategies", "data", "events.json"),
              os.path.join(here, "catalog", "events.json")):
        if p and os.path.exists(p):
            with open(p) as fh:
                d = json.load(fh)
            for name, days in d.items():
                if name.startswith("_"):
                    continue
                ev.global_days[name] = {_date.fromisoformat(x).toordinal() for x in days}
            break
    return ev


class LiveFiller(BacktestFiller):
    """Resting stops/targets/limits in live paper trading use the same model as backtests."""


class BotRunner:
    def __init__(self, cfg: dict, compiled: Compiled, inst: dict, account: Account):
        self.cfg = cfg
        self.id = cfg["bot_id"]
        self.c = compiled
        self.inst = inst
        self.venue, self.symbol, self.tf = cfg["venue"], cfg["instrument"], compiled.tf
        self.asset_type = inst["asset_type"]
        cm = CostModel(self.venue, tier_for(self.symbol, self.asset_type), 1.0, inst.get("tick_size") or 0.0,
                       self.asset_type.startswith("stock") or self.asset_type.startswith("etf"))
        self.filler = LiveFiller(cm)
        self.tm = TradeManager(compiled, self.filler, account.slot_equity, inst.get("lot_size") or 0.0,
                               inst.get("min_notional") or 0.0, bool(inst.get("can_short")), self.symbol)
        self.enabled = bool(cfg.get("enabled", True))
        self.state = "warming" if self.enabled else "disabled"
        self.message = ""
        self.errors = 0
        self.total_errors = 0
        self.last_eval: Optional[int] = None
        self.last_data: Optional[int] = None
        self.last_decision: Optional[str] = None
        self.last_signal: Optional[dict] = None
        self.eval_ms: deque = deque(maxlen=200)
        self.latency_ms: deque = deque(maxlen=200)
        self.evaluations = 0
        self.scheduled = 0
        self.config_version = hashlib.sha256(json.dumps(cfg, sort_keys=True).encode()).hexdigest()[:12]
        self.series_keys: List[Tuple[str, str, str]] = []
        self.orderflow = any(k in ("trades", "book") for k in compiled.definition.get("data", []))

    def health(self) -> dict:
        return asdict(BotHealth(self.id, self.state, self.last_eval, self.last_data, self.last_decision,
                                self.errors, self.message))


class Fleet:
    def __init__(self, config: dict, strategies: Dict[str, dict], bots: List[dict], base_dir: str = "."):
        self.cfg = config
        self.base = base_dir
        self.strategies = strategies
        self.bot_cfgs = bots
        data_dir = os.path.join(base_dir, config.get("data_dir", "data"))
        os.makedirs(data_dir, exist_ok=True)
        self.data_dir = data_dir
        self.storage = Storage(os.path.join(data_dir, "mab.db"))
        self.http = Http()
        self.registry = InstrumentRegistry(self.http, os.path.join(data_dir, "instruments.json"))
        acct = self.storage.kv_get("account")
        a = config.get("account", {})
        self.account = Account.from_state(acct) if acct else Account(a.get("balance", 100_000.0), a.get("slots", 20),
                                                                     a.get("currency", "USD"))
        if not acct:
            self.storage.save_cash_flow(self.account.flows[0])
        self.risk = RiskManager(RiskLimits(**config.get("risk", {})))
        rs = self.storage.kv_get("risk")
        if rs:
            self.risk.restore(rs)
        self.q: "queue.Queue" = queue.Queue(maxsize=10_000)
        self.hub = Hub(self.http, workers=config.get("hub", {}).get("workers", 4), storage=self.storage,
                       on_bars=self._on_bars)
        p = config.get("paper", {})
        self.broker = PaperBroker(self.hub, self.account, p.get("latency_ms", 150), p.get("max_slippage_bps", 50))
        self.fee_profile = self.storage.kv_get("fee_profile", "venue") or "venue"
        if self.fee_profile not in FEE_PROFILES:
            self.fee_profile = "venue"
        self.broker.fee_profile = FEE_PROFILES[self.fee_profile]
        self.events = load_events(config)
        bcfg = config.get("brain", {})
        self.brain = FleetBrain(mode=bcfg.get("mode", "active"))
        try:
            pri = bcfg.get("priors") or _default_priors(config)
            self.brain.load_priors(pri)
            if pri and not bcfg.get("priors"):                # the swing strategies' own evaluation, same format
                self.brain.load_priors(os.path.join(os.path.dirname(pri), "swing_eval.json"), add=True)
        except Exception as e:                      # a missing or unreadable priors file only means "start blank"
            log.warning("brain priors not loaded: %s", e)
        n_priors = self.brain.stats.get("prior_strategies", 0)
        self.brain.restore(self.storage.kv_get("brain", {}))
        self.brain.stats["prior_strategies"] = n_priors          # what this version ships, not the saved count
        self.volgate = VolGate() if bcfg.get("volatility_gate", True) else None
        self._gate_cache: Dict[tuple, tuple] = {}
        self._evaluation = None
        self.live = self._make_live()
        self.bots: Dict[str, BotRunner] = {}
        self.by_series: Dict[Tuple[str, str, str], List[str]] = {}
        self.paused = bool(self.storage.kv_get("paused", False))
        self.emergency = self.storage.kv_get("emergency", None)
        self.running = False
        self.started_at: Optional[int] = None
        self.threads: List[threading.Thread] = []
        self.storage_ok = True
        self.unsaved: deque = deque(maxlen=5_000)
        self.cycle = 0
        self.stats = {"events": 0, "evaluations": 0, "intents": 0, "orders": 0, "fills": 0, "rejections": 0,
                      "risk_blocks": 0, "bot_errors": 0, "auto_disabled": 0, "storage_failures": 0,
                      "dropped_events": 0}
        self.alerts: deque = deque(maxlen=200)
        self.lock = threading.RLock()
        self.peak_rss_mb = 0.0

    # ================================================================== setup
    def setup(self, stocks: List[str] = ()):
        venues = sorted({b["venue"] for b in self.bot_cfgs if b["venue"] != "yahoo"} |
                        {r.split(":", 1)[0] for b in self.bot_cfgs for r in (b.get("refs") or [])
                         if not r.startswith("yahoo:")})
        stock_syms = sorted({b["instrument"] for b in self.bot_cfgs if b["venue"] == "yahoo"} | set(stocks))
        for b in self.bot_cfgs:
            for extra in (b.get("refs") or []):
                if extra.startswith("yahoo:"):
                    stock_syms.append(extra.split(":", 1)[1])
        self.registry.load(venues=venues, stocks=stock_syms)
        states = self.storage.load_bot_states()
        for b in self.bot_cfgs:
            try:
                self._add_bot(b, states.get(b["bot_id"]))
            except Exception as e:
                self._alert("error", "bot_config_invalid", f"{b.get('bot_id')}: {e}", b.get("bot_id"))

    def _add_bot(self, b: dict, saved: Optional[dict]):
        d = self.strategies.get(b["strategy_id"])
        if d is None:
            raise KeyError(f"strategy {b['strategy_id']} not in the catalog")
        inst = self.registry.get(b["venue"], b["instrument"])
        if inst is None:
            raise KeyError(f"instrument {b['venue']}:{b['instrument']} not available")
        params = dict(b.get("params") or {})
        if b.get("bench"):
            params.setdefault("bench", b["bench"])
        definition = dict(d)
        if b.get("sizing"):
            definition["sizing"] = dict(d.get("sizing", {}), **b["sizing"])
        c = compile_strategy(definition, {k: v for k, v in params.items() if k in (d.get("params") or {})},
                             inst["asset_type"])
        br = BotRunner(b, c, inst, self.account)
        br.filler.cm.fees = FEE_PROFILES[self.fee_profile]
        if saved and not saved.get("corrupt"):
            try:
                br.tm.restore(saved.get("tm", {}))
                if saved.get("disabled_reason"):
                    br.enabled, br.state, br.message = False, "disabled", saved["disabled_reason"]
            except (TypeError, KeyError) as e:
                self._alert("warning", "state_restore_failed", f"{br.id}: saved state unreadable ({e}); starting flat",
                            br.id)
        elif saved and saved.get("corrupt"):
            self._alert("warning", "state_corrupt", f"{br.id}: saved state was corrupt; starting flat", br.id)
        self.bots[br.id] = br
        self.brain.connect(br.id, self._bkey(br), br.c.definition.get("family"), br.c.definition.get("name"), br.symbol)
        if not br.enabled:
            return
        for (sym, tf), need in c.warmup.items():
            venue, symbol = b["venue"], sym or b["instrument"]
            if sym and ":" in sym:
                venue, symbol = sym.split(":", 1)
            ref_inst = self.registry.get(venue, symbol) or ({"asset_type": "stock"} if venue == "yahoo" else None)
            if ref_inst is None:
                raise KeyError(f"reference instrument {venue}:{symbol} not available")
            s = self.hub.subscribe(venue, symbol, tf, need + 5, br.id, ref_inst["asset_type"],
                                   orderflow=br.orderflow and sym is None and tf == c.tf,
                                   extended_hours=bool(b.get("extended_hours")))
            br.series_keys.append(s.key)
        if self.volgate is not None and self.volgate.ready(self._gate_asset(br)):
            try:
                g = self.hub.subscribe(b["venue"], b["instrument"], "1h", 200, br.id, inst["asset_type"],
                                       extended_hours=bool(b.get("extended_hours")))
                br.gate_key = g.key
            except Exception as e:                                          # noqa: BLE001
                log.warning("volatility gate series for %s not available: %s", br.id, e)
        base = (b["venue"], b["instrument"], c.tf)
        if base not in br.series_keys:
            s = self.hub.subscribe(*base, need=max(c.warmup.values()) + 5, subscriber=br.id,
                                   asset_type=inst["asset_type"], orderflow=br.orderflow)
            br.series_keys.append(s.key)
        self.by_series.setdefault(base, []).append(br.id)

    # ================================================================== lifecycle
    def start(self):
        self.running = True
        self.started_at = now_ms()
        self._event("info", "fleet_start", f"fleet started with {sum(1 for b in self.bots.values() if b.enabled)} "
                                           f"enabled bots on {len(self.hub.series)} shared series")
        for fn, name in ((self._dispatch_loop, "dispatcher"), (self._control_loop, "control"),
                         (self._health_loop, "health")):
            t = threading.Thread(target=fn, name=name, daemon=True)
            t.start()
            self.threads.append(t)
        self.hub.start()

    def stop(self):
        self._event("info", "fleet_stop", "fleet stopping")
        self.running = False
        self.hub.stop()
        for t in self.threads:
            t.join(5)
        self._persist_states()
        self._persist_account()
        for b in self.bots.values():
            if b.enabled:
                b.state = "stopped"

    def wait(self, seconds: Optional[float] = None):
        t_end = None if seconds is None else time.time() + seconds
        try:
            while self.running and (t_end is None or time.time() < t_end):
                time.sleep(0.5)
        except KeyboardInterrupt:
            pass

    # ================================================================== events
    def _on_bars(self, key, added, replaced, initial=False):
        try:
            self.q.put_nowait((key, list(added), initial))
        except queue.Full:
            self.stats["dropped_events"] += 1
            self._alert("critical", "event_queue_full", f"dropped new-bar event for {key}")

    def _dispatch_loop(self):
        while self.running:
            try:
                key, added, initial = self.q.get(timeout=0.5)
            except queue.Empty:
                continue
            self.stats["events"] += 1
            ids = self.by_series.get(key, [])
            if not ids or not added:
                continue
            s = self.hub.get(*key)
            frame = s.frame()
            for bid in ids:
                br = self.bots.get(bid)
                if br is None or not br.enabled:
                    continue
                br.scheduled += 1
                self._evaluate(br, frame, sorted(added), initial)
            self._persist_states([bid for bid in ids])

    def _series_status(self, br: BotRunner) -> Tuple[str, str]:
        worst, msg = "ok", ""
        rank = {"ok": 0, "market_closed": 1, "warming": 2, "suspect": 3, "stale": 4, "unavailable": 5}
        for k in br.series_keys:
            s = self.hub.get(*k)
            st = s.status() if s else "unavailable"
            if rank.get(st, 5) > rank[worst]:
                worst, msg = st, f"{'/'.join(k)}: {st}" + (f" ({s.quality.last_fetch_error})" if s and s.quality.last_fetch_error else "")
        return worst, msg

    def _evaluate(self, br: BotRunner, frame, added: List[int], initial: bool = False):
        t0 = time.perf_counter()
        try:
            status, msg = self._series_status(br)
            br.last_data = frame.last_time
            if status in ("unavailable", "stale"):
                br.state, br.message = "data_unavailable", msg
            elif status == "warming":
                br.state, br.message = "warming", msg
            rs = evaluate(br.c, frame, resolver=self.hub.frame, events=self.events)
            idx = {t: i for i, t in enumerate(frame.t)}
            latest = frame.t[-1]
            decisions = []
            for t in added:
                i = idx.get(t)
                if i is None:
                    continue
                live_bar = t == latest
                entries_ok = (live_bar and status == "ok" and not self.paused and not self.emergency
                              and self.storage_ok and br.id not in self.risk.paused_bots)
                for text in self.brain.shadow_step(br.id, frame, i):      # vetoed trades followed on paper
                    self._event("info", "brain_insight", text, br.id)
                acts = br.tm.on_bar(rs, i, immediate_market=live_bar, entries_allowed=entries_ok)
                if live_bar:
                    el, es = rs.values.get("entry_long"), rs.values.get("entry_short")
                    state = 1 if (el and el[i]) else (-1 if (es and es[i]) else 0)
                    self.brain.observe(br.id, br.symbol, state, frame.t[i] + frame.step, frame, i)
                if not live_bar and acts:
                    for a in acts:
                        a["catch_up"] = True
                decisions.extend(self._handle(br, frame, rs, i, a) for a in acts)
                if live_bar:
                    self._record_signal(br, frame, rs, i, acts, status)
            br.last_eval = now_ms()
            br.evaluations += 1
            self.stats["evaluations"] += 1
            if not initial:        # the first evaluation after a backfill measures start-up, not latency
                br.latency_ms.append(br.last_eval - (latest + frame.step))
            if status == "ok":
                br.errors = 0
                if self.paused or br.id in self.risk.paused_bots:
                    br.state = "paused"
                    br.message = "fleet paused" if self.paused else self.risk.paused_bots.get(br.id, "")
                elif br.tm.pos is not None or any(d for d in decisions if d):
                    br.state, br.message = "running", ""
                else:
                    br.state, br.message = "idle_no_signal", br.last_decision or ""
            elif status == "market_closed":
                br.state, br.message = "idle_no_signal", "market closed"
            elif status == "suspect":
                br.state, br.message = "degraded", msg
        except Exception as e:
            br.errors += 1
            br.total_errors += 1
            self.stats["bot_errors"] += 1
            br.state = "degraded"
            br.message = f"{type(e).__name__}: {e}"
            self._alert("error", "bot_error", f"{br.id}: {br.message}", br.id, {"trace": traceback.format_exc()[-2000:]})
            if br.errors >= 5:
                br.enabled = False
                br.state = "disabled"
                br.message = f"auto-disabled after {br.errors} consecutive errors: {e}"
                self.stats["auto_disabled"] += 1
                self._alert("critical", "bot_auto_disabled", br.message, br.id)
        finally:
            br.eval_ms.append((time.perf_counter() - t0) * 1000)

    # ================================================================== decisions
    def _record_signal(self, br: BotRunner, frame, rs, i, acts, status):
        kinds = [a["action"] for a in acts]
        if "intent" in kinds:
            a = next(a for a in acts if a["action"] == "intent")
            action = ("enter_long" if a["side"] > 0 else "enter_short") if a["kind"] == "entry" else "exit"
            reason = a["reason"]
        elif "exit" in kinds:
            action, reason = "exit", next(a for a in acts if a["action"] == "exit")["reason"]
        elif "entry" in kinds:
            action, reason = "enter", "resting order filled"
        elif "skip" in kinds or "rejected" in kinds:
            a = next(a for a in acts if a["action"] in ("skip", "rejected"))
            action, reason = "no_trade", a["reason"]
        elif br.tm.pos is not None:
            action, reason = "hold", "position open; no exit condition met"
        else:
            side, why = br.tm.entry_check(rs, i)
            action, reason = "no_trade", why if status == "ok" else f"data {status}"
        side = 1
        if br.tm.pos is not None:
            side = br.tm.pos.side
        elif "short" in reason:
            side = -1
        rows, feats = explain(br.c, rs, i, "long" if side > 0 else "short")
        sig = {"bot_id": br.id, "strategy_id": br.c.id, "strategy_version": br.c.definition.get("version", "1.0.0"),
               "config_version": br.config_version, "instrument": br.symbol, "venue": br.venue, "timeframe": br.tf,
               "bar_time": frame.t[i], "decision_time": now_ms(), "action": action, "reason": reason,
               "features": feats, "rules": rows}
        br.last_signal = sig
        br.last_decision = f"{action}: {reason}"
        compact = dict(sig)
        if action in ("no_trade", "hold") and "skip" not in kinds:
            compact["features"], compact["rules"] = {}, []
        self._save(lambda: self.storage.save_signals([compact]))

    def _intent(self, br: BotRunner, a: dict, bar_time: int) -> OrderIntent:
        iid = hashlib.sha256(f"{br.id}|{bar_time}|{a['kind']}|{a['side']}".encode()).hexdigest()[:20]
        return OrderIntent(iid, br.id, br.c.id, br.symbol, br.venue, "buy" if a["side"] > 0 else "sell", "market",
                           a["qty"], reduce_only=a.get("reduce_only", False), reason=a["reason"],
                           stop_loss=a.get("stop"), take_profit=a.get("target"),
                           risk_amount=(abs(a["ref_price"] - a["stop"]) * a["qty"]) if a.get("stop") else None)

    def _handle(self, br: BotRunner, frame, rs, i, a: dict) -> Optional[str]:
        act = a["action"]
        if act == "intent":
            return self._execute_intent(br, frame, i, a)
        if act == "order_placed":
            return self._accept_resting(br, frame, i)
        if act in ("entry", "exit"):
            # a resting order (stop / limit / target) filled inside the bar
            side = a.get("side", 0) if act == "entry" else (-1 if a["trade"].side > 0 else 1)
            qty = a.get("qty") if act == "entry" else a["trade"].qty
            fill = {"fill_id": hashlib.sha1(f"{br.id}|{frame.t[i]}|{act}".encode()).hexdigest()[:16],
                    "order_id": f"rest-{br.id}-{frame.t[i]}", "intent_id": f"rest-{br.id}-{frame.t[i]}",
                    "bot_id": br.id, "instrument": br.symbol, "venue": br.venue,
                    "side": "buy" if side > 0 else "sell", "quantity": qty, "price": a["price"], "fee": a["fee"],
                    "liquidity": a.get("liquidity", "taker"), "event_time": frame.t[i] + frame.step,
                    "simulated": True,
                    "model": "resting order simulated against the completed bar's range" +
                             (" (catch-up after downtime)" if a.get("catch_up") else "")}
            self.account.apply_fill(br.id, br.venue, br.symbol, fill["side"], qty, a["price"], a["fee"],
                                    fill["event_time"])
            self.stats["fills"] += 1
            self._save(lambda: self.storage.save_fill(fill))
            if act == "exit":
                self._trade_closed(br, a["trade"])
            return act
        return None

    def _execute_intent(self, br: BotRunner, frame, i, a: dict) -> str:
        if a["kind"] == "entry" and not a.get("reduce_only") and self.brain.mode != "off":
            dec = self.brain.score(br.id, self._bkey(br), br.symbol, frame, i, a["side"],
                                   cost_r=self._cost_r(br, a["ref_price"], a.get("stop")), gate=self._gate(br))
            if dec["action"] == "veto":
                self.stats["brain_vetoes"] = self.stats.get("brain_vetoes", 0) + 1
                br.tm.intent_rejected("brain veto: " + dec["reason"])
                br.last_decision = "brain veto: " + dec["reason"]
                self._save(lambda: self.storage.save_risk({"intent_id": f"brain-{br.id}-{frame.t[i]}", "bot_id": br.id,
                                                           "approved": False, "adjusted_quantity": None,
                                                           "checks": [{"check": "fleet brain", "passed": False,
                                                                       "detail": dec["reason"]}],
                                                           "decision_time": now_ms()}))
                # follow the blocked trade on paper so the brain learns what the veto was worth
                try:
                    ref, stop = a["ref_price"], a.get("stop")
                    cost_r = self._cost_r(br, ref, stop) or 0.0
                    self.brain.shadow_open(br.id, dec, ref, stop, a.get("target"), cost_r, frame.t[i],
                                           int(br.c.definition.get("max_bars") or 48), frame.sess_close[i])
                except Exception as e:                                    # noqa: BLE001
                    log.debug("shadow trade not opened for %s: %s", br.id, e)
                return "vetoed"
            if dec["size"] != 1.0:
                a = dict(a, qty=a["qty"] * dec["size"])
        intent = self._intent(br, a, frame.t[i])
        self.stats["intents"] += 1
        dec = self.risk.check(intent, self._risk_ctx(br, frame, i, a["ref_price"]))
        self._save(lambda: self.storage.save_intent(intent.to_dict()))
        self._save(lambda: self.storage.save_risk(dec.to_dict()))
        if not dec.approved:
            self.stats["risk_blocks"] += 1
            failed = [c["check"] + (f" ({c['detail']})" if c["detail"] else "") for c in dec.checks if not c["passed"]]
            if intent.reduce_only:
                return self._fallback_exit(br, frame, i, a, "risk layer refused an exit")
            br.tm.intent_rejected("risk: " + "; ".join(failed))
            br.last_decision = f"blocked by risk: {'; '.join(failed)}"
            return "blocked"
        intent.quantity = dec.adjusted_quantity or intent.quantity
        if self.live.handles(br.id) or br.id in self.live.positions:
            routed = self._live_route(br, frame, i, a, intent)
            if routed is not None:
                return routed
        res = self.broker.execute(intent, a["ref_price"], self.registry.get(br.venue, br.symbol))
        self.stats["orders"] += 1
        self._save(lambda: self.storage.save_order(dict(res), intent.to_dict()))
        if res["status"] == "rejected":
            self.stats["rejections"] += 1
            if intent.reduce_only:
                return self._fallback_exit(br, frame, i, a, res["reason"])
            br.tm.intent_rejected(res["reason"])
            br.last_decision = f"order rejected: {res['reason']}"
            return "rejected"
        for f in res["fills"]:
            fd = f.to_dict()
            fd["quantity"] = f.quantity
            self.account.apply_fill(br.id, br.venue, br.symbol, f.side, f.quantity, f.price, f.fee, f.event_time)
            self.stats["fills"] += 1
            self._save(lambda fd=fd: self.storage.save_fill(fd))
        if a["kind"] == "entry":
            br.tm.apply_entry_fill(res["avg_price"], res["filled_qty"], res["fee"], now_ms())
            return "entered"
        if res["filled_qty"] < br.tm.pos.qty - 1e-12:
            # partial exit: close the rest at the fallback price so no position is left unmanaged
            return self._fallback_exit(br, frame, i, a, res["reason"], already=res)
        out = br.tm.apply_exit_fill(frame, i, res["avg_price"], res["fee"], a["reason"])
        self._trade_closed(br, out["trade"])
        return "exited"

    # ================================================================== real money (off unless armed)
    def _make_live(self) -> LiveExecutor:
        cfg = self.storage.kv_get("live", {}) or {}
        broker = None
        if cfg.get("broker"):
            try:
                broker = broker_setup.load(self.storage, cfg["broker"])
            except Exception as e:                                          # noqa: BLE001
                log.warning("live broker %s not loaded: %s", cfg.get("broker"), e)
        ex = LiveExecutor(self.storage, broker, eligible=self._live_eligible,
                          alert=lambda level, kind, msg: self._alert(level, kind, msg))
        if cfg.get("armed") and broker is None:
            ex.disarm("the broker's saved keys could not be loaded at start")
        return ex

    def _evaluation_rows(self, sid: str) -> list:
        if self._evaluation is None:
            path = _default_priors(self.cfg) or ""
            self._evaluation = {}
            for p in (path, path + ".gz"):
                if p and os.path.exists(p):
                    import gzip
                    with (gzip.open(p, "rt") if p.endswith(".gz") else open(p)) as fh:
                        self._evaluation = json.load(fh).get("strategies", {})
                    break
            sw = os.path.join(os.path.dirname(path), "swing_eval.json") if path else ""
            if sw and os.path.exists(sw):
                with open(sw) as fh:
                    self._evaluation.update(json.load(fh).get("strategies", {}))
        return (self._evaluation.get(sid) or {}).get("runs", [])

    def _live_eligible(self, bot_id: str) -> tuple:
        """(eligible, why): has this bot earned real money? Out-of-sample positive at its venue's costs AND at
        least 20 paper trades with a positive average R, market orders only, not benched by the brain."""
        br = self.bots.get(bot_id)
        if br is None:
            return False, "unknown bot"
        if (br.c.definition.get("order") or {}).get("type", "market") != "market":
            return False, "uses resting stop/limit entries, which live trading does not support"
        if br.id in self.brain.bench:
            return False, "benched by the brain"
        cost = "base" if br.venue == "yahoo" else ("low_fee_venue" if br.venue == "okx" else "retail_kraken")
        rows = [x for x in self._evaluation_rows(br.c.id) if x.get("cost") == cost]
        good = [x for x in rows if x.get("candidate") and (x["test"].get("expectancy_r") or -1) > 0 and (x["test"].get("trades") or 0) >= 10]
        if not good:
            best = max((x["test"].get("expectancy_r") or -9 for x in rows), default=None)
            return False, ("not positive on train, validation AND the untouched test at this venue's costs"
                           + (f" (best test {best:+.2f}R)" if best is not None else ""))
        paper = self.storage.query("SELECT r FROM trades WHERE bot_id=? AND r IS NOT NULL AND entry_reason NOT LIKE '[LIVE]%'", (bot_id,))
        if len(paper) < 20:
            return False, f"{len(paper)} of 20 paper trades so far"
        avg = sum(x["r"] for x in paper) / len(paper)
        if avg <= 0:
            return False, f"paper record {avg:+.2f}R per trade over {len(paper)} trades"
        return True, f"test {good[0]['test']['expectancy_r']:+.2f}R; paper {avg:+.2f}R over {len(paper)} trades"

    def _live_route(self, br: BotRunner, frame, i, a: dict, intent) -> Optional[str]:
        """Send this bot's order to the real broker; None means: carry on with paper for this signal."""
        if a["kind"] == "entry":
            if br.id not in self.live.cfg.get("bots", []):
                return None
            r = self.live.enter(br.id, br.symbol, a["side"], intent.quantity, a["ref_price"], a.get("stop"), intent.intent_id)
            if r["status"] == "filled":
                br.tm.apply_entry_fill(r["avg_price"], r["qty"], r["fee"], now_ms())
                if br.tm.pos is not None:
                    br.tm.pos.reason = "[LIVE] " + (br.tm.pos.reason or "")
                br.last_decision = f"LIVE entry {r['qty']:g} @ {r['avg_price']:.6g} on {self.live.broker.name}"
                self._save(lambda: self.storage.save_fill({"fill_id": f"live-{intent.intent_id}", "order_id": (r.get("order") or {}).get("id", ""),
                                                          "intent_id": intent.intent_id, "bot_id": br.id, "instrument": br.symbol,
                                                          "venue": "LIVE:" + self.live.broker.name, "side": "buy", "quantity": r["qty"],
                                                          "price": r.get("broker_price", r["avg_price"]),
                                                          "fee": r.get("broker_fee", r["fee"]), "liquidity": "taker",
                                                          "event_time": now_ms(), "simulated": False,
                                                          "model": "real order (broker's currency)"}))
                return "entered"
            if r["status"] == "closed":
                br.tm.intent_rejected("live: protective stop failed, position sold")
                return "rejected"
            br.last_decision = f"live entry not sent ({r.get('reason')}); this signal trades on paper"
            return None
        if br.id in self.live.positions and br.tm.pos is not None:
            r = self.live.exit(br.id, a["ref_price"], a.get("reason", "exit"))
            if r.get("status") != "filled":
                return None
            out = br.tm.apply_exit_fill(frame, i, r["avg_price"], r["fee"], a.get("reason", "exit") + " (live)")
            self._trade_closed(br, out["trade"])
            return "exited"
        return None

    def _live_poll(self):
        """Exchange-side stops that filled: close the bots' trades to match; reconcile every 10 cycles."""
        if not self.live.positions and not self.live.armed:
            return
        for bot_id, res in self.live.poll_stops():
            br = self.bots.get(bot_id)
            if br is None or br.tm.pos is None:
                continue
            s = self.hub.get(br.venue, br.symbol, br.tf)
            fr = s.frame() if s else None
            if fr is None or fr.n == 0:
                continue
            out = br.tm.apply_exit_fill(fr, fr.n - 1, res["avg_price"], res["fee"], "exchange stop filled (live)")
            self._trade_closed(br, out["trade"])
        if self.cycle % 10 == 0:
            self.live.reconcile()

    def _risk_ctx(self, br: BotRunner, frame, i, ref_price: float) -> dict:
        status, _ = self._series_status(br)
        ex = self.account.exposure()
        positions = [{"bot_id": p["bot_id"], "venue": p["venue"], "instrument": p["instrument"], "qty": p["qty"]}
                     for p in self.account.positions.values()]
        return {"equity": self.account.equity(), "positions": positions, "gross": ex["gross"],
                "net_by_instrument": ex["net_by_instrument"], "paused": self.paused, "emergency": bool(self.emergency),
                "bot_enabled": br.enabled, "data_status": status,
                "price_age_ms": now_ms() - (frame.t[i] + frame.step), "bar_ms": frame.step, "ref_price": ref_price}

    def _accept_resting(self, br: BotRunner, frame, i) -> str:
        """A strategy placed a resting entry (stop, limit or bracket). Like a broker accepting the order, the
        fleet brain scores it (it can cancel or resize it) and the portfolio risk layer must approve it, at
        its estimated size, before it can fill; otherwise it is cancelled."""
        p = br.tm.pending
        if p is None or p.exit:
            return "order_placed"
        if self.brain.mode != "off":
            px0 = p.price or frame.c[i]
            plan0 = br.tm._plan(p, px0)
            dec = self.brain.score(br.id, self._bkey(br), br.symbol, frame, i, p.side,
                                   cost_r=self._cost_r(br, px0, plan0[1] if plan0 else None), gate=self._gate(br))
            if dec["action"] == "veto":
                br.tm.pending = None
                self.stats["brain_vetoes"] = self.stats.get("brain_vetoes", 0) + 1
                br.last_decision = "brain cancelled the resting order: " + dec["reason"]
                self._save(lambda: self.storage.save_risk({"intent_id": f"brain-{br.id}-{frame.t[i]}", "bot_id": br.id,
                                                           "approved": False, "adjusted_quantity": None,
                                                           "checks": [{"check": "fleet brain (resting order)",
                                                                       "passed": False, "detail": dec["reason"]}],
                                                           "decision_time": now_ms()}))
                return "vetoed"
            p.size = dec["size"]
        px = p.price or frame.c[i]
        plan = br.tm._plan(p, px)
        if plan is None or plan[0] <= 0:
            return "order_placed"                          # sized at fill time; nothing to pre-check yet
        qty, stop, target = plan
        a = {"kind": "entry", "side": p.side, "qty": qty, "ref_price": px, "stop": stop, "target": target,
             "reason": p.reason + f" ({p.kind} order)", "reduce_only": False}
        intent = self._intent(br, a, frame.t[i])
        dec = self.risk.check(intent, self._risk_ctx(br, frame, i, px))
        self._save(lambda: self.storage.save_risk(dec.to_dict()))
        if not dec.approved:
            br.tm.pending = None
            self.stats["risk_blocks"] += 1
            failed = [c["check"] + (f" ({c['detail']})" if c["detail"] else "") for c in dec.checks if not c["passed"]]
            br.last_decision = f"resting order cancelled by risk: {'; '.join(failed)}"
            return "blocked"
        return "order_placed"

    def _fallback_exit(self, br: BotRunner, frame, i, a, why: str, already: Optional[dict] = None) -> str:
        """Exits must not fail. If the book walk could not fill an exit, the remainder is closed
        at the bar close with doubled assumed slippage, and the record says so."""
        pos = br.tm.pos
        if pos is None:
            return "noop"
        done_qty = already["filled_qty"] if already else 0.0
        rest = pos.qty - done_qty
        px_close = frame.c[i] * (1 - pos.side * 2 * br.filler.cm.slip)
        fee = br.filler.fee(rest * px_close, "taker")
        side = "sell" if pos.side > 0 else "buy"
        fill = {"fill_id": hashlib.sha1(f"{br.id}|{frame.t[i]}|fallback".encode()).hexdigest()[:16],
                "order_id": f"fallback-{br.id}-{frame.t[i]}", "intent_id": f"fallback-{br.id}-{frame.t[i]}",
                "bot_id": br.id, "instrument": br.symbol, "venue": br.venue, "side": side, "quantity": rest,
                "price": px_close, "fee": fee, "liquidity": "taker", "event_time": now_ms(), "simulated": True,
                "model": f"fallback exit at bar close with 2x assumed slippage: {why}"}
        self.account.apply_fill(br.id, br.venue, br.symbol, side, rest, px_close, fee, fill["event_time"])
        self._save(lambda: self.storage.save_fill(fill))
        self._alert("warning", "fallback_exit", f"{br.id}: {why}; exit completed at the fallback price", br.id)
        if already:
            avg = (already["avg_price"] * done_qty + px_close * rest) / pos.qty
            out = br.tm.apply_exit_fill(frame, i, avg, already["fee"] + fee, a["reason"] + " (partly fallback)")
        else:
            out = br.tm.apply_exit_fill(frame, i, px_close, fee, a["reason"] + " (fallback price)")
        self._trade_closed(br, out["trade"])
        return "exited"

    @staticmethod
    def _cost_r(br: BotRunner, ref: float, stop: Optional[float]) -> Optional[float]:
        """Round-trip costs as a fraction of the trade's risk (a limit entry pays the maker fee; see costs.round_trip)."""
        if not stop or not ref or ref == stop:
            return None
        limit = ((br.c.definition or {}).get("order") or {}).get("type") == "limit"
        return round_trip(br.filler, limit) * ref / abs(ref - stop)

    @staticmethod
    def _gate_asset(br: BotRunner) -> str:
        return "stock" if br.venue == "yahoo" else "crypto"

    def _refresh_gates(self):
        """A current gate reading for every market, not only those whose bots just signalled (for the app)."""
        seen = set()
        for br in list(self.bots.values()):
            key = getattr(br, "gate_key", None)
            if key is None or key in seen or not br.enabled:
                continue
            seen.add(key)
            try:
                self._gate(br)                                  # cached per hourly bar: cheap after the first
            except Exception as e:                              # noqa: BLE001
                log.debug("gate reading for %s failed: %s", key, e)

    def _gate(self, br: BotRunner) -> Optional[dict]:
        """The volatility gate reading for this bot's market (one computation per market per hour)."""
        key = getattr(br, "gate_key", None)
        if self.volgate is None or key is None:
            return None
        s = self.hub.get(*key)
        if s is None or len(s.times) < 200:
            return None
        last = s.times[-1]
        hit = self._gate_cache.get(key)
        if hit and hit[0] == last:
            return hit[1]
        f = s.frame()
        asset = self._gate_asset(br)
        reading = self.volgate.read(GateBars.from_frame(f, GATE_HORIZON[asset]), f.n - 1, asset)
        reading["time"] = last + s.step
        self._gate_cache[key] = (last, reading)
        self.brain.gates[br.symbol] = dict(reading, venue=br.venue)
        return reading

    @staticmethod
    def _bkey(br: BotRunner) -> str:
        """The brain judges a strategy separately at each fee level (retail, about 0.20%, low-fee): costs decide
        most results. The level follows the fees the bot actually pays (its venue, or the fee profile)."""
        f = getattr(br, "filler", None)
        taker = f.fee(1.0, "taker") if f is not None else FEES.get(br.venue, FEES["kraken"])["taker"]
        return br.c.id + fee_key(taker, br.venue == "yahoo")

    def set_fee_profile(self, name: str) -> dict:
        if name not in FEE_PROFILES:
            raise ValueError(f"unknown fee profile {name!r}; choose one of {', '.join(FEE_PROFILES)}")
        with self.lock:
            self.fee_profile = name
            self.broker.fee_profile = FEE_PROFILES[name]
            for br in self.bots.values():
                br.filler.cm.fees = FEE_PROFILES[name]
                self.brain.connect(br.id, self._bkey(br), br.c.definition.get("family"), br.c.definition.get("name"), br.symbol)
            self.storage.kv_set("fee_profile", name)
        self._event("info", "fee_profile", f"crypto fees now: {FEE_PROFILE_LABELS[name]}")
        return {"profile": name, "label": FEE_PROFILE_LABELS[name]}

    def _trade_closed(self, br: BotRunner, trade):
        for text in self.brain.learn(br.id, self._bkey(br), br.symbol, trade.r):
            self._event("info", "brain_insight", text, br.id)
        td = trade.to_dict()
        self._save(lambda: self.storage.save_trade(br.id, br.venue, td))
        ev = self.risk.on_trade_closed(br.id, trade.pnl, self.account.equity())
        if ev:
            self._alert(ev["level"], ev["kind"], ev["message"], br.id)

    # ================================================================== control
    def _control_loop(self):
        while self.running:
            try:
                for cmd in self.storage.pending_commands():
                    try:
                        res = self.apply_command(cmd["command"], cmd["args"])
                        self.storage.finish_command(cmd["id"], "done", res)
                    except Exception as e:
                        self.storage.finish_command(cmd["id"], "failed", str(e))
            except StorageError as e:
                self._storage_failed(e)
            except Exception:
                log.exception("control loop")
            time.sleep(1.0)

    def apply_command(self, command: str, args: dict) -> Any:
        if command == "pause":
            self.paused = True
            self.storage.kv_set("paused", True)
            self._event("warning", "pause", "fleet paused: no new entries; open positions keep their exits")
            return "paused"
        if command == "resume":
            self.paused = False
            self.storage.kv_set("paused", False)
            self._event("info", "resume", "fleet resumed")
            return "resumed"
        if command == "emergency_stop":
            return self.emergency_stop(args.get("reason", "operator"))
        if command == "clear_emergency":
            self.emergency = None
            self.storage.kv_set("emergency", None)
            self._event("warning", "emergency_cleared", "emergency stop cleared by operator")
            return "cleared"
        if command == "stop":
            threading.Thread(target=self.stop, daemon=True).start()
            return "stopping"
        if command in ("deposit", "withdraw", "set_balance"):
            amt = float(args["amount"])
            with self.lock:
                rec = getattr(self.account, command)(amt, args.get("note", ""))
                self.storage.save_cash_flow(rec)
                self.risk.reset_peak(self.account.equity())
                self._persist_account()
            self._event("info", "cash_flow", f"{command} {amt:,.2f}: equity {rec['equity_before']:,.2f} -> "
                                             f"{rec['equity_after']:,.2f}")
            return rec
        if command == "set_fee_profile":
            return self.set_fee_profile(str(args.get("profile") or ""))
        if command == "live_status":
            st = self.live.status()
            st["eligibility"] = {b: dict(zip(("eligible", "why"), self._live_eligible(b))) for b in
                                 (args.get("bots") or st["config"].get("bots") or [])}
            return st
        if command == "live_eligibility":
            out = []
            for bid, br in self.bots.items():
                ok, why = self._live_eligible(bid)
                out.append({"bot_id": bid, "strategy_id": br.c.id, "name": br.c.definition.get("name"), "venue": br.venue,
                            "instrument": br.symbol, "asset": "stock" if br.venue == "yahoo" else "crypto",
                            "eligible": ok, "why": why})
            return out
        if command == "live_arm":
            name = args.get("broker")
            broker = broker_setup.load(self.storage, name) if name else None
            last = ((self.storage.kv_get("brokers", {}) or {}).get(name) or {}).get("last_test") or {}
            if broker is None or not last.get("ok"):
                raise ValueError("connect the broker and pass its connection test first")
            self.live.broker = broker
            return self.live.arm(args.get("ack", ""), args.get("limits") or {}, args.get("bots") or [], args.get("overrides") or [])
        if command == "live_disarm":
            return self.live.disarm(args.get("reason") or "owner")
        if command == "live_close_all":
            prices = {}
            for p in self.live.positions.values():
                s = next((self.hub.get(*k) for k in self.hub.series if k[1] == p["instrument"]), None)
                if s is not None and s.times:
                    prices[p["instrument"]] = s.bars[s.times[-1]].close
            closed = self.live.close_all(prices)
            for bot_id, res in closed:
                br = self.bots.get(bot_id)
                if br is not None and br.tm.pos is not None and res.get("status") == "filled":
                    s = self.hub.get(br.venue, br.symbol, br.tf)
                    fr = s.frame() if s else None
                    if fr is not None and fr.n:
                        out = br.tm.apply_exit_fill(fr, fr.n - 1, res["avg_price"], res["fee"], "owner closed live positions")
                        self._trade_closed(br, out["trade"])
            self.live.disarm("owner closed all live positions")
            return {"closed": len(closed)}
        if command in ("enable_bot", "disable_bot"):
            br = self.bots[args["bot_id"]]
            br.enabled = command == "enable_bot"
            br.state = "warming" if br.enabled else "disabled"
            br.message = "" if br.enabled else "disabled by operator"
            if br.enabled and br.id not in sum(self.by_series.values(), []):
                self._add_bot(br.cfg, {"tm": br.tm.state()})
            self._persist_states([br.id])
            return br.state
        if command == "test_order":
            return self.test_order(args["bot_id"], float(args.get("notional", 50.0)))
        raise ValueError(f"unknown command {command!r}")

    def test_order(self, bot_id: str, notional: float = 50.0) -> dict:
        """Operator check of the live paper order path: a small buy then sell through the risk layer
        and the paper broker on the bot's instrument, recorded under '<bot>:test' so it never
        touches the bot's own position. Labelled as a test in every record."""
        br = self.bots[bot_id]
        s = self.hub.get(br.venue, br.symbol, br.tf)
        fr = s.frame()
        i = fr.n - 1
        px = fr.c[i]
        out = []
        tid = f"{bot_id}:test"
        for leg, side in (("open", "buy"), ("close", "sell")):
            iid = hashlib.sha256(f"{tid}|{now_ms()}|{leg}".encode()).hexdigest()[:20]
            intent = OrderIntent(iid, tid, br.c.id, br.symbol, br.venue, side, "market", notional / px,
                                 reduce_only=leg == "close", reason="operator test order (not a strategy decision)")
            status, _ = self._series_status(br)
            ex = self.account.exposure()
            ctx = {"equity": self.account.equity(), "positions": [], "gross": ex["gross"],
                   "net_by_instrument": {}, "paused": False, "emergency": False, "bot_enabled": True,
                   "data_status": status, "price_age_ms": now_ms() - (fr.t[i] + fr.step), "bar_ms": fr.step,
                   "ref_price": px}
            dec = self.risk.check(intent, ctx)
            self.storage.save_intent(intent.to_dict())
            self.storage.save_risk(dec.to_dict())
            if not dec.approved:
                out.append({"leg": leg, "risk": [c for c in dec.checks if not c["passed"]]})
                break
            if leg == "close":
                intent.quantity = out[0]["filled_qty"]
            res = self.broker.execute(intent, px, self.registry.get(br.venue, br.symbol))
            self.storage.save_order(dict(res), intent.to_dict())
            for f in res["fills"]:
                fd = f.to_dict()
                fd["model"] = "OPERATOR TEST ORDER: " + fd["model"]
                self.account.apply_fill(tid, br.venue, br.symbol, f.side, f.quantity, f.price, f.fee, f.event_time)
                self.storage.save_fill(fd)
            out.append({"leg": leg, "status": res["status"], "filled_qty": res["filled_qty"],
                        "avg_price": res["avg_price"], "fee": res["fee"], "model": res["model"], "reason": res["reason"],
                        "ref_price": px})
            if res["status"] == "rejected":
                break
        self._persist_account()
        self._event("info", "test_order", f"operator test order on {br.symbol}: " +
                    "; ".join(f"{o['leg']} {o.get('status')} @ {o.get('avg_price')}" for o in out), tid, out)
        return {"bot_id": bot_id, "legs": out}

    def emergency_stop(self, reason: str) -> dict:
        self.emergency = {"time": now_ms(), "reason": reason}
        self.storage.kv_set("emergency", self.emergency)
        if self.live.armed:
            self.live.disarm(f"emergency stop: {reason}")
        closed = 0
        for br in self.bots.values():
            br.tm.pending = None
            if br.tm.pos is None:
                continue
            s = self.hub.get(br.venue, br.symbol, br.tf)
            fr = s.frame() if s else None
            if fr is None or fr.n == 0:
                continue
            i = fr.n - 1
            a = {"kind": "exit", "side": -br.tm.pos.side, "qty": br.tm.pos.qty, "ref_price": fr.c[i],
                 "reason": f"emergency stop: {reason}", "reduce_only": True}
            br.tm.awaiting = {"kind": "exit", "reason": a["reason"]}
            try:
                self._execute_intent(br, fr, i, dict(a, action="intent"))
                closed += 1
            except Exception as e:
                self._alert("critical", "emergency_flatten_failed", f"{br.id}: {e}", br.id)
        self._persist_states()
        self._persist_account()
        self._event("critical", "emergency_stop", f"emergency stop ({reason}): {closed} positions flattened; "
                                                  "new entries blocked until cleared")
        return {"flattened": closed, "reason": reason}

    # ================================================================== health
    def _health_loop(self):
        interval = self.cfg.get("health_interval_s", 60)
        next_backup = time.time() + self.cfg.get("backup_interval_h", 6) * 3600
        last_prune_day = None
        while self.running:
            time.sleep(min(interval, 5) if self.cycle == 0 else interval)
            if not self.running:
                break
            self.cycle += 1
            try:
                self.health_cycle()
                self._live_poll()
                self._refresh_gates()
                day = time.strftime("%Y-%m-%d", time.gmtime())
                if day != last_prune_day:
                    self.storage.prune()
                    last_prune_day = day
                if time.time() >= next_backup:
                    self.storage.backup(os.path.join(self.data_dir, "backups"))
                    next_backup = time.time() + self.cfg.get("backup_interval_h", 6) * 3600
            except StorageError as e:
                self._storage_failed(e)
            except Exception:
                log.exception("health cycle")

    def health_cycle(self) -> dict:
        t = now_ms()
        # mark positions to the latest close of their series
        for br in self.bots.values():
            s = self.hub.get(br.venue, br.symbol, br.tf)
            if s and s.last_time is not None:
                self.account.mark(br.venue, br.symbol, s.bars[s.last_time].close, s.last_time + s.step)
        eq = self.account.equity()
        for ev in self.risk.on_equity(eq, time.strftime("%Y-%m-%d", time.gmtime(t / 1000))):
            self._alert(ev["level"], ev["kind"], ev["message"])
            if ev["kind"] == "drawdown_kill_switch" and not self.emergency:
                self.emergency_stop(ev["message"])
        for br in self.bots.values():
            if not self.running and br.enabled:
                br.state = "stopped"
            elif br.enabled and br.last_eval is None:
                st, msg = self._series_status(br)
                if st in ("unavailable", "stale"):
                    br.state, br.message = "data_unavailable", msg
                elif st == "market_closed":
                    br.state, br.message = "idle_no_signal", "market closed"
                else:
                    br.state = "warming"
        rows = [br.health() for br in self.bots.values()]
        sysh = self.system_health()
        self.storage.save_health(rows, sysh, t)
        ex = self.account.exposure()
        self.storage.save_equity(t, eq, self.account.cash, ex["gross"], self.account.twr())
        self._persist_account()
        self.storage.kv_set("risk", self.risk.to_state())
        self.storage.kv_set("brain", self.brain.to_state())
        if not self.storage_ok:
            self.storage_ok = True
            self._event("info", "storage_recovered", "storage writes succeed again; new entries re-enabled")
            while self.unsaved:
                fn = self.unsaved.popleft()
                try:
                    fn()
                except StorageError:
                    break
        return sysh

    def rss_mb(self) -> Optional[float]:
        try:
            with open("/proc/self/status") as fh:
                for line in fh:
                    if line.startswith("VmRSS:"):
                        return int(line.split()[1]) / 1024
        except OSError:
            pass
        try:
            import ctypes
            from ctypes import wintypes

            class PMC(ctypes.Structure):
                _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                            ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                            ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]
            pmc = PMC()
            pmc.cb = ctypes.sizeof(PMC)
            h = ctypes.windll.kernel32.GetCurrentProcess()
            if ctypes.windll.psapi.GetProcessMemoryInfo(h, ctypes.byref(pmc), pmc.cb):
                return pmc.WorkingSetSize / 1024 / 1024
        except Exception:
            pass
        return None

    def system_health(self) -> dict:
        counts = {s: 0 for s in BOT_STATES}
        for br in self.bots.values():
            counts[br.state] = counts.get(br.state, 0) + 1
        evals = [x for br in self.bots.values() for x in br.eval_ms]
        lats = [x for br in self.bots.values() for x in br.latency_ms]
        sched = sum(br.scheduled for br in self.bots.values())
        done = sum(br.evaluations for br in self.bots.values())
        rss = self.rss_mb()
        if rss:
            self.peak_rss_mb = max(self.peak_rss_mb, rss)
        hub = self.hub.snapshot()
        http = hub["http"]
        reqs = sum(h.get("requests", 0) for h in http.values())
        r429 = sum(h.get("http_429", 0) for h in http.values())
        return {"time": now_ms(), "uptime_s": (now_ms() - self.started_at) / 1000 if self.started_at else 0,
                "bots": len(self.bots), "bot_states": counts, "series": len(self.hub.series),
                "series_status": hub["status_counts"], "hub": hub["stats"], "queue": self.q.qsize(),
                "eval_ms_p50": _pctl(evals, 0.5), "eval_ms_p95": _pctl(evals, 0.95),
                "latency_ms_p50": _pctl(lats, 0.5), "latency_ms_p95": _pctl(lats, 0.95),
                "scheduled_evaluations": sched, "completed_evaluations": done,
                "completion_rate": done / sched if sched else None,
                "requests": reqs, "http_429": r429, "rate_429": r429 / reqs if reqs else 0.0,
                "rss_mb": rss, "peak_rss_mb": self.peak_rss_mb, "db_bytes": self.storage.size_bytes(),
                "threads": threading.active_count(), "paused": self.paused, "emergency": self.emergency,
                "storage_ok": self.storage_ok, "stats": dict(self.stats), "version": __version__,
                "account": self.account.summary(), "broker": dict(self.broker.stats),
                "brain": {k: v for k, v in self.brain.summary().items() if k in (
                    "mode", "connected_bots", "trades_learned", "scored", "approved", "vetoed", "resized", "win_rate",
                    "avg_r", "brier")}}

    # ================================================================== persistence helpers
    def _persist_states(self, ids: Optional[List[str]] = None):
        ids = ids or list(self.bots)
        st = {}
        for bid in ids:
            br = self.bots.get(bid)
            if br is None:
                continue
            st[bid] = {"tm": br.tm.state(), "disabled_reason": None if br.enabled else br.message,
                       "strategy_version": br.c.version_hash, "config_version": br.config_version}
        self._save(lambda: self.storage.save_bot_states(st))

    def _persist_account(self):
        self._save(lambda: self.storage.kv_set("account", self.account.to_state()))

    def _save(self, fn):
        try:
            fn()
        except StorageError as e:
            self.unsaved.append(fn)
            self._storage_failed(e)

    def _storage_failed(self, e: Exception):
        self.stats["storage_failures"] += 1
        if self.storage_ok:
            self.storage_ok = False
            self._alert("critical", "storage_failure", f"{e}: new entries stopped until storage recovers "
                                                       "(open positions keep their stops)", persist=False)

    def _event(self, level: str, kind: str, message: str, bot_id: str = None, body=None):
        self.alerts.append({"time": now_ms(), "level": level, "kind": kind, "message": message, "bot_id": bot_id})
        log.log(logging.WARNING if level in ("warning", "error", "critical") else logging.INFO, "%s: %s", kind, message)
        try:
            self.storage.event(level, kind, message, bot_id, body)
        except StorageError:
            pass

    def _alert(self, level, kind, message, bot_id=None, body=None, persist=True):
        if persist:
            self._event(level, kind, message, bot_id, body)
        else:
            self.alerts.append({"time": now_ms(), "level": level, "kind": kind, "message": message, "bot_id": bot_id})
            log.error("%s: %s", kind, message)

    # ================================================================== views (dashboard / CLI)
    def bot_view(self, bid: str) -> dict:
        br = self.bots[bid]
        pos = br.tm.pos
        return {"bot_id": br.id, "name": br.cfg.get("name", br.id), "strategy_id": br.c.id,
                "strategy_name": br.c.definition.get("name"), "family": br.c.definition.get("family"),
                "venue": br.venue, "instrument": br.symbol, "timeframe": br.tf, "enabled": br.enabled,
                "state": br.state, "message": br.message, "last_eval": br.last_eval, "last_data": br.last_data,
                "last_decision": br.last_decision, "errors": br.errors, "evaluations": br.evaluations,
                "eval_ms_p95": _pctl(list(br.eval_ms), 0.95), "latency_ms_p95": _pctl(list(br.latency_ms), 0.95),
                "position": None if pos is None else {"side": "long" if pos.side > 0 else "short", "qty": pos.qty,
                                                      "entry": pos.entry_price, "stop": pos.stop, "target": pos.target,
                                                      "trail": pos.trail, "opened": pos.entry_time},
                "trades": len(br.tm.trades), "last_signal": br.last_signal,
                "config_version": br.config_version, "strategy_version": br.c.version_hash,
                "rules": {k: v.key() for k, v in br.c.rules.items()}, "params": br.c.params,
                "series": ["/".join(k) for k in br.series_keys]}
