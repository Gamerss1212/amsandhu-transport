"""The application container: builds every service, runs start-up checks, recovery, the trading loop and shutdown.

Start-up order (section 120): paths and logging -> database integrity -> audit chain check -> configuration ->
credential vault -> instrument registry and market calendars -> data store -> strategy library -> agents -> risk
service (persisted kill switch and limits restored) -> paper broker -> broker connections -> OMS -> research jobs ->
recovery (unknown orders resolved, bots restored) -> READY.

Modes: PAPER (default), SHADOW (real data, orders recorded and never sent), LIVE (only after explicit arming with a
verified live connection, the owner's typed acknowledgement and caps; LIVE_LOCKED -> LIVE_ARMED -> LIVE_RUNNING).
"""

from __future__ import annotations

import os
import platform
import shutil
import threading
import time
from dataclasses import asdict
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Optional

import numpy as np

from tradingai import APP_ID, __version__, config
from tradingai.agents import roster as _roster          # noqa: F401  (registers the 100 agents)
from tradingai.agents.base import AGENTS
from tradingai.brokers.adapters import ADAPTERS, matrix as broker_matrix
from tradingai.brokers.base import BrokerAdapter, BrokerError, RequiresConnection
from tradingai.brokers.paper import PaperBroker
from tradingai.core import logs, state as S
from tradingai.core.events import EventBus
from tradingai.core.ids import new_id
from tradingai.data.bars import TF_MS
from tradingai.data.net import Http
from tradingai.data.pipeline import MarketData
from tradingai.engine.orchestrator import BotConfig, Orchestrator
from tradingai.execution.oms import OMS
from tradingai.features.registry import summary as feature_summary
from tradingai.market import universe
from tradingai.market.calendars import session
from tradingai.market.instruments import Instrument, MarketType
from tradingai.research.jobs import Jobs
from tradingai.research.ledger import Ledger
from tradingai.risk.service import RiskService, Snapshot
from tradingai.storage.db import Database, dumps, now_ms
from tradingai.storage.marketstore import MarketStore
from tradingai.storage.secrets import Vault
from tradingai.strategies.library import MARKET_OF, specs, summary as lib_summary

log = logs.get("app")
LIVE_ACK = "I UNDERSTAND THIS TRADES REAL MONEY"


class App:
    def __init__(self, home: Optional[str] = None, *, offline: bool = False, start_loop: bool = True,
                 tick_seconds: float = 3.0):
        self.started = time.time()
        self.paths = config.paths(home).ensure()
        logs.setup(self.paths.logs, console=start_loop)
        self.bus = EventBus()
        self.state = S.StateMachine(on_change=self._on_state)
        self.checks: list[dict] = []
        self.tick_seconds = tick_seconds
        self._stop = threading.Event()
        self._loop_thread: Optional[threading.Thread] = None
        self.offline = offline
        self.mode = "paper"
        self.bots: dict[str, BotConfig] = {}
        self.connections: dict[str, BrokerAdapter] = {}
        self.live: dict = {"armed": False}
        self.last_tick: Optional[float] = None
        self._boot()
        if start_loop:
            self.start_loop()

    # ================================================================== start-up
    def _check(self, name: str, fn) -> bool:
        t = time.perf_counter()
        try:
            detail, ok = fn(), True
        except Exception as e:                      # noqa: BLE001 - every failure is reported
            detail, ok = f"{type(e).__name__}: {e}", False
        self.checks.append({"name": name, "ok": ok, "detail": str(detail)[:300],
                            "ms": round((time.perf_counter() - t) * 1000, 1)})
        return ok

    def _boot(self) -> None:
        self._check("database open and migrated", self._open_db)
        self._check("database integrity", lambda: self._expect(self.db.integrity(), "ok"))
        self._check("audit chain intact", self._audit_chain)
        self._check("credential vault", lambda: self._vault())
        self._check("instrument registry and calendars", self._instruments)
        self._check("market data store (DuckDB + Parquet)", self._marketdata)
        self._check("strategy library", lambda: f"{lib_summary()['runnable']} runnable templates")
        self._check("agents", lambda: f"{len(AGENTS)} agents registered")
        self._check("risk service (persisted state restored)", self._risk)
        self._check("paper broker", self._paper)
        self._check("broker connections", self._load_connections)
        self._check("order management", self._oms)
        self._check("research engine", self._research)
        self._check("frontend files", self._frontend)
        critical = [c for c in self.checks if not c["ok"] and c["name"] not in ("frontend files", "broker connections")]
        if critical:
            self.state.to(S.ERROR, "start-up check failed: " + "; ".join(f"{c['name']}: {c['detail']}" for c in critical))
            return
        self._check("recovery", self._recover)
        if self.state.state == S.BOOTING:
            self.state.to(S.READY, "start-up checks passed")
        self.audit("system", f"Trading AI {__version__} started ({platform.system()} {platform.release()})",
                   data={"checks": self.checks})

    @staticmethod
    def _expect(v, want):
        if v != want:
            raise RuntimeError(str(v))
        return v

    def _open_db(self) -> str:
        self.db = Database(self.paths.db)
        return f"schema v{self.db.version}"

    def _audit_chain(self) -> str:
        ok, bad_row = self.db.verify_audit()
        if not ok:
            raise RuntimeError(f"audit chain broken at row {bad_row}")
        return "verified"

    @staticmethod
    def _frontend() -> str:
        d = config.frontend_dir()
        if not (d / "index.html").exists():
            raise FileNotFoundError("frontend not built")
        return str(d)

    def audit(self, kind: str, message: str, **kw) -> dict:
        row = self.db.audit(kind, message, **kw)
        self.bus.publish("audit", {k: row[k] for k in ("id", "ts", "kind", "severity", "message", "correlation_id")},
                         severity=row["severity"], correlation_id=row.get("correlation_id"))
        return row

    def _vault(self) -> str:
        self.vault = Vault(self.paths.secrets)
        return self.vault.backend

    def _instruments(self) -> str:
        self.book, self.sources = universe.build()
        session("XNYS", now_ms())
        session("FX", now_ms())
        return f"{len(self.book)} instruments; calendars XNYS, FX, CME, CRYPTO"

    def _marketdata(self) -> str:
        self.store = MarketStore(self.paths.market, self.db)
        self.http = Http(min_interval={"query1.finance.yahoo.com": 0.35, "api.kraken.com": 1.0,
                                       "api.exchange.coinbase.com": 0.15})
        self.md = MarketData(self.store, self.book, self.sources, self.http, offline=self.offline)
        return f"{len(self.store.datasets())} stored dataset(s)"

    def _risk(self) -> str:
        self.risk = RiskService(audit=self.audit, on_kill=self._on_kill)
        saved = self.db.get_setting("risk_state")
        if saved:
            self.risk.restore(saved)
        return "kill switch ENGAGED (persisted)" if self.risk.kill_switch else "armed"

    def _persist_risk(self) -> None:
        st = self.risk.state()
        self.db.set_setting("risk_state", {"limits": st["limits"], "kill_switch": st["kill_switch"],
                                           "trading_locked": st["trading_locked"]})

    def _paper(self) -> str:
        self.paper = PaperBroker(self.db, self.book, self.quote, audit=self.audit)
        return f"paper equity {self.paper.get_balance().equity} (SIMULATED)"

    def _oms(self) -> str:
        self.oms = OMS(self.db, self.risk, self.bus, self.audit)
        self.orch = Orchestrator(self)
        return "ready"

    def _research(self) -> str:
        self.ledger = Ledger(self.db)
        self.jobs = Jobs(self.bus, workers=max(1, min(2, (os.cpu_count() or 2) - 1)))
        return f"{self.ledger.counts()['experiments']} experiment(s) in the ledger"

    def _load_connections(self) -> str:
        rows = self.db.query("SELECT * FROM connections")
        for r in rows:
            creds = None
            try:
                creds = self.vault.get(r["connection_id"])
            except Exception as e:                    # noqa: BLE001
                log.warning(f"credential read failed for {r['connection_id']}: {type(e).__name__}")
            try:
                self.connections[r["connection_id"]] = ADAPTERS[r["broker"]](r["environment"], creds)
            except BrokerError as e:
                log.warning(str(e))
        return f"{len(rows)} saved connection(s); none connected automatically"

    def _recover(self) -> str:
        notes = []
        res = self.oms.resolve_unknown(self.paper)
        if res:
            notes.append(f"{len(res)} uncertain paper order(s) resolved")
        saved = self.db.get_setting("bots", {})
        for bid, b in saved.items():
            bot = BotConfig(**{k: v for k, v in b.items() if k in BotConfig.__dataclass_fields__})
            was_running = bot.state == "running"
            bot.state = "stopped"
            self.bots[bid] = bot
            if was_running and self.db.get_setting("mode", "paper") in ("paper", "shadow") and \
                    self.db.get_setting("auto_resume", True) and not self.risk.kill_switch:
                bot.state = "running"
                notes.append(f"bot {bid} resumed ({self.db.get_setting('mode', 'paper')})")
        self.mode = self.db.get_setting("mode", "paper")
        if self.mode == "live":                       # live never resumes by itself after a restart
            self.mode = "paper"
            self.db.set_setting("mode", "paper")
            notes.append("previous session was LIVE: back to PAPER; re-arm live trading to continue")
        if self.risk.kill_switch:
            notes.append("STOP ALL TRADING is still engaged from the previous session")
        self._sync_state("recovered")
        return "; ".join(notes) or "clean start"

    # ================================================================== helpers used by the orchestrator
    def quote(self, instrument_id: str) -> Optional[dict]:
        """The newest completed bar's close (never an invented price). None without fresh data."""
        inst = self.book.get(instrument_id)
        prov = self.md.providers[self.sources[instrument_id].provider]
        tf = "1m" if "1m" in prov.timeframes else ("5m" if "5m" in prov.timeframes else "1d")
        try:
            b, st = self.md.bars(instrument_id, tf, lookback=30, max_age_s=20)
        except Exception:                             # noqa: BLE001
            return None
        if not len(b):
            return None
        r = np.diff(np.log(b.close)) if len(b) > 2 else np.zeros(1)
        return {"price": float(b.close[-1]), "ts": int(b.available_at[-1]), "volume": float(b.volume[-1]) or None,
                "sigma": float(np.std(r)) if len(r) > 2 else 0.0, "range": float(b.high[-1] - b.low[-1]),
                "simulated": b.simulated, "tf": tf, "fresh": st.get("fresh"), "currency": inst.currency}

    def broker_for(self, mode: str) -> BrokerAdapter:
        if mode == "live" and self.live.get("armed") and self.live.get("connection_id") in self.connections:
            return self.connections[self.live["connection_id"]]
        return self.paper

    def broker_symbol(self, inst: Instrument, mode: str) -> str:
        if mode != "live":
            return inst.symbol
        b = self.broker_for(mode).name
        if b == "oanda":
            return f"{inst.symbol[:3]}_{inst.symbol[3:]}"
        return inst.broker_symbol or inst.symbol

    def permission(self, inst: Instrument, mode: str) -> tuple[bool, str]:
        if mode != "live":
            return True, "paper/shadow"
        perms = self.live.get("permissions", {})
        allowed = perms.get(MARKET_OF.get(inst.market_type, "?"))
        return (bool(allowed), "permitted by the broker" if allowed else
                f"the live account does not report permission for {MARKET_OF.get(inst.market_type)}")

    def risk_snapshot(self, inst: Instrument, bars, dstatus: dict, mode: str) -> Snapshot:
        br = self.broker_for(mode)
        acct = br.get_balance()
        pos = {}
        for p in (self.paper.positions_detail() if br is self.paper else []):
            i = self.book.get(p["instrument_id"])
            pos[p["instrument_id"]] = {"qty": p["qty"], "price": p["price"] or p["avg_price"],
                                       "multiplier": p["multiplier"], "market": MARKET_OF.get(i.market_type)}
        age = (now_ms() - int(bars.available_at[-1])) / 1000 if len(bars) else None
        cal = session(inst.calendar or "CRYPTO", now_ms())
        return Snapshot(equity=acct.equity or Decimal(0), positions=pos, clusters=self._clusters(),
                        data_age_s=age, bar_seconds=TF_MS[bars.tf] / 1000 if len(bars) else 60,
                        last_volume=float(bars.volume[-1]) if len(bars) and bars.volume[-1] > 0 else None,
                        market_open=bool(cal["open"]) or inst.market_type is MarketType.CRYPTO_SPOT,
                        broker_ok=br is self.paper or br.connected,
                        reconciliation_ok=self.state.state != S.RECONCILIATION_REQUIRED)

    def _clusters(self) -> list[list[str]]:
        crypto = [i for i in self.paper.get_positions() if self.book.get(i).market_type is MarketType.CRYPTO_SPOT]
        return [crypto] if len(crypto) > 1 else []

    def research_snapshot(self, strategy_id: str, instrument_id: str) -> dict:
        e = self.ledger.latest_for(strategy_id, instrument_id)
        if not e or not e.get("results"):
            return {}
        r = e["results"]
        st = r.get("statistics", {})
        return {"oos_sharpe": (r.get("test") or {}).get("sharpe"), "wf_oos_sharpe": (r.get("walk_forward") or {})
                .get("oos_sharpe"), "dsr": st.get("dsr"), "param_stability": r.get("param_stability"),
                "sharpe_2x_costs": (r.get("cost_stress") or {}).get("2.0x", {}).get("sharpe"),
                "mc_p95_drawdown": ((r.get("monte_carlo") or {}).get("trade_reshuffle") or {}).get("max_drawdown_p95"),
                "capacity_usd": (r.get("capacity") or {}).get("estimate_usd"), "trials": e.get("trials_at_run"),
                "regimes_positive": sum(1 for v in ((r.get("full") or {}).get("by_regime", {}).get("trend") or {})
                                        .values() if v.get("net", 0) > 0), "verdict": r.get("verdict")}

    # ================================================================== bots and the loop
    def start_loop(self) -> None:
        if self._loop_thread is None:
            self._loop_thread = threading.Thread(target=self._loop, name="trading-loop", daemon=True)
            self._loop_thread.start()

    def _loop(self) -> None:
        last_account = 0.0
        while not self._stop.is_set():
            t0 = time.time()
            try:
                self.tick()
                if time.time() - last_account > 5:
                    self.publish_account()
                    last_account = time.time()
            except Exception as e:                    # noqa: BLE001 - the loop survives; the error is logged
                log.error(f"trading loop error: {type(e).__name__}: {e}")
                self.bus.publish("system.error", {"error": f"{type(e).__name__}: {e}"}, severity="error")
            self.last_tick = time.time()
            self._stop.wait(max(0.5, self.tick_seconds - (time.time() - t0)))

    def tick(self) -> list[dict]:
        out = []
        if self.state.state in (S.ERROR, S.SHUTTING_DOWN, S.BOOTING):
            return out
        self.paper.process()
        acct = self.broker_for(self.mode).get_balance()
        d = datetime.now(timezone.utc)
        fired = self.risk.on_equity(acct.equity or Decimal(0), d.strftime("%Y-%m-%d"), d.strftime("%G-W%V"))
        if fired:
            self._persist_risk()
            self.oms.cancel_all(self.broker_for(self.mode), "loss breaker: " + ", ".join(fired))
            self.bus.publish("risk.locked", {"breakers": fired, "state": self.risk.trading_locked}, severity="critical")
        for bot in list(self.bots.values()):
            if bot.state != "running":
                continue
            day = d.strftime("%Y-%m-%d")
            if bot.day != day:
                bot.day, bot.trades_today = day, 0
            try:
                bars, _ = self.md.bars(bot.instrument_id, bot.tf, lookback=3, max_age_s=self.tick_seconds)
            except Exception as e:                    # noqa: BLE001
                self.bus.publish("data.error", {"bot": bot.bot_id, "error": str(e)}, severity="warning")
                continue
            if not len(bars):
                continue
            newest = int(bars.ts[-1])
            if bot.last_bar_ts == newest:
                continue
            bot.last_bar_ts = newest
            mode = "shadow" if self.mode == "shadow" else ("live" if self.mode == "live" and
                                                           self.state.state == S.LIVE_RUNNING else "paper")
            out.append(self.orch.decide(bot, mode))
            self._save_bots()
        return out

    def publish_account(self) -> None:
        self.bus.publish("account", self.account_view())

    def _save_bots(self) -> None:
        self.db.set_setting("bots", {k: b.as_dict() for k, b in self.bots.items()})

    def create_bot(self, instrument_id: str, tf: str, strategy_id: str, signal_mode: str = "strategy+ensemble",
                   risk_profile: str = "conservative", max_trades_per_day: int = 10) -> dict:
        inst = self.book.get(instrument_id)
        ok, why = universe.paper_tradable(inst)
        if not ok:
            raise ValueError(why)
        sp = specs().get(strategy_id)
        if sp is None:
            raise ValueError(f"unknown strategy {strategy_id!r}")
        if not sp.runnable:
            raise ValueError(f"{strategy_id} needs data this installation does not have: {', '.join(sp.required_data)}")
        if tf not in TF_MS:
            raise ValueError(f"unknown timeframe {tf}")
        bid = new_id("BOT")
        self.bots[bid] = BotConfig(bid, instrument_id, tf, strategy_id, signal_mode, risk_profile,
                                   int(max_trades_per_day))
        self._save_bots()
        self.audit("bot", f"bot {bid} created: {strategy_id} on {instrument_id} {tf}", data=self.bots[bid].as_dict())
        return self.bots[bid].as_dict()

    def bot_action(self, bot_id: str, action: str) -> dict:
        bot = self.bots.get(bot_id)
        if bot is None:
            raise KeyError("unknown bot")
        if action == "start":
            if self.risk.kill_switch:
                raise PermissionError("STOP ALL TRADING is engaged: re-arm trading first")
            bot.state = "running"
        elif action == "pause":
            bot.state = "paused"
        elif action == "stop":
            bot.state = "stopped"
        elif action == "delete":
            if bot.state == "running":
                raise PermissionError("stop the bot first")
            del self.bots[bot_id]
        else:
            raise ValueError(action)
        self._save_bots()
        self._sync_state(f"bot {bot_id} {action}")
        self.audit("bot", f"bot {bot_id}: {action}")
        return {"bot_id": bot_id, "state": action}

    def start_all(self) -> dict:
        if self.risk.kill_switch:
            raise PermissionError("STOP ALL TRADING is engaged: re-arm trading first")
        for b in self.bots.values():
            b.state = "running"
        self._save_bots()
        self._sync_state("START BOT")
        self.audit("bot", "START BOT: all bots running", data={"mode": self.mode})
        return {"running": len(self.bots)}

    def stop_all(self) -> dict:
        for b in self.bots.values():
            b.state = "stopped"
        self._save_bots()
        self._sync_state("STOP BOT")
        self.audit("bot", "STOP BOT: all bots stopped (positions kept, protective logic continues)")
        return {"stopped": len(self.bots)}

    def emergency_stop(self, reason: str, by: str = "owner") -> dict:
        self.risk.engage_kill_switch(reason, by)
        for b in self.bots.values():
            b.state = "stopped"
        self._save_bots()
        self._persist_risk()
        self._sync_state("EMERGENCY STOP")
        return {"kill_switch": self.risk.kill_switch}

    def _on_kill(self, reason: str) -> None:
        br = self.broker_for(self.mode)
        self.oms.cancel_all(br, f"STOP ALL TRADING: {reason}")
        if self.risk.limits.emergency_flatten:
            for iid, q in br.get_positions().items():
                if q != 0:
                    try:
                        br.submit_order(client_order_id=new_id("FLAT"), instrument_id=iid, broker_symbol=iid,
                                        side="sell" if q > 0 else "buy", qty=abs(q))
                    except BrokerError as e:
                        self.audit("kill_switch", f"flatten {iid} failed: {e}", severity="critical")
        self.bus.publish("kill_switch", {"engaged": True, "reason": reason}, severity="critical")

    def rearm(self, phrase: str) -> dict:
        out = self.risk.rearm(phrase, "owner")
        self._persist_risk()
        self._sync_state("trading re-armed")
        return out

    def set_mode(self, mode: str) -> dict:
        if mode not in ("paper", "shadow"):
            raise PermissionError("LIVE is entered only through the arming steps on the Broker & Money page")
        if self.mode == "live":
            self.disarm_live("owner switched to " + mode)
        self.mode = mode
        self.db.set_setting("mode", mode)
        self._sync_state(f"mode {mode}")
        self.audit("mode", f"mode set to {mode.upper()}")
        return {"mode": mode}

    def _sync_state(self, reason: str) -> None:
        running = any(b.state == "running" for b in self.bots.values())
        cur = self.state.state
        if cur in (S.ERROR, S.SHUTTING_DOWN, S.RECONCILIATION_REQUIRED, S.BOOTING):
            return
        if self.risk.kill_switch or self.risk.trading_locked:
            target = S.PAUSED
        elif self.mode == "live":
            target = S.LIVE_RUNNING if running and self.live.get("armed") else (S.LIVE_ARMED if self.live.get("armed")
                                                                                 else S.LIVE_LOCKED)
        elif running:
            target = S.SHADOW_RUNNING if self.mode == "shadow" else S.PAPER_RUNNING
        else:
            target = S.READY
        if target == cur:
            return
        try:
            self.state.to(target, reason)
        except S.InvalidTransition:
            # go through READY when a direct move is not allowed (for example PAUSED -> SHADOW_RUNNING)
            if self.state.can(S.READY):
                self.state.to(S.READY, reason)
                if self.state.can(target):
                    self.state.to(target, reason)

    def _on_state(self, old: str, new: str, reason: str) -> None:
        try:
            self.bus.publish("state", {"from": old, "to": new, "reason": reason},
                             severity="warning" if new in (S.PAUSED, S.ERROR, S.RECONCILIATION_REQUIRED) else "info")
        except Exception:                             # noqa: BLE001
            pass

    # ================================================================== connections and live arming
    def add_connection(self, broker: str, environment: str, label: str, credentials: dict) -> dict:
        if broker not in ADAPTERS:
            raise ValueError(f"unknown broker {broker!r}")
        cls = ADAPTERS[broker]
        if environment not in cls.environments:
            raise ValueError(f"{cls.label} offers {', '.join(cls.environments)} only")
        cid = new_id("CONN")
        needed = [k for k in cls.needs if not credentials.get(k)]
        if needed:
            raise ValueError("missing: " + ", ".join(needed))
        stored = self.vault.put(cid, {k: str(v).strip() for k, v in credentials.items() if k in cls.needs})
        self.db.execute("INSERT INTO connections (connection_id, broker, environment, label, status, created, updated) "
                        "VALUES (?,?,?,?,?,?,?)", (cid, broker, environment, label[:80] or cls.label, "disconnected",
                                                   now_ms(), now_ms()))
        self.connections[cid] = cls(environment, self.vault.get(cid))
        self.audit("connection", f"connection {cid} saved ({broker} {environment}); credentials in the vault",
                   data={"masked": stored["masked"], "vault": stored["backend"]})
        return {"connection_id": cid, "masked": stored["masked"], "vault": stored["backend"]}

    def test_connection(self, cid: str) -> dict:
        ad = self.connections[cid]
        t0 = time.perf_counter()
        try:
            r = ad.connect()
            status, detail = "connected", r
        except RequiresConnection as e:
            status, detail = "requires connection", {"error": str(e)}
        except BrokerError as e:
            status, detail = "error", {"error": str(e)}
        ms = round((time.perf_counter() - t0) * 1000, 1)
        self.db.execute("UPDATE connections SET status=?, last_test=?, capabilities=?, updated=? WHERE connection_id=?",
                        (status, dumps(dict(detail, ms=ms)), dumps(ad.capabilities()), now_ms(), cid))
        self.audit("connection", f"connection {cid} test: {status}", severity="info" if status == "connected" else
                   "warning", data=dict(detail, ms=ms))
        return {"connection_id": cid, "status": status, "latency_ms": ms, **detail}

    def remove_connection(self, cid: str) -> dict:
        if self.live.get("connection_id") == cid:
            self.disarm_live("connection removed")
        self.connections.pop(cid, None)
        self.vault.delete(cid)
        self.db.execute("DELETE FROM connections WHERE connection_id=?", (cid,))
        self.audit("connection", f"connection {cid} removed and its credentials deleted")
        return {"removed": cid}

    def connections_view(self) -> list[dict]:
        out = [dict(self.paper.describe(), connection_id="paper", balance=_acct(self.paper.get_balance()))]
        for r in self.db.query("SELECT * FROM connections ORDER BY created"):
            ad = self.connections.get(r["connection_id"])
            d = ad.describe() if ad else {"status": "unavailable"}
            bal = None
            if ad is not None and ad.connected:
                try:
                    bal = _acct(ad.get_balance())
                except BrokerError as e:
                    d["last_error"] = str(e)
            out.append(dict(d, connection_id=r["connection_id"], label=r["label"], saved_status=r["status"],
                            last_test=r["last_test"], balance=bal,
                            masked=(self.vault.describe(r["connection_id"]) or {}).get("masked")))
        return out

    def readiness(self, cid: str) -> list[dict]:
        """Section 210: every critical item must pass before live trading can be armed."""
        ad = self.connections.get(cid)
        items = []

        def add(name, ok, detail):
            items.append({"check": name, "passed": bool(ok), "detail": detail})
        add("connection exists", ad is not None, cid)
        add("environment is LIVE", ad is not None and ad.environment == "live",
            ad.environment if ad else "-")
        add("broker connected", ad is not None and ad.connected, ad.status() if ad else "-")
        acct = None
        if ad is not None and ad.connected:
            try:
                acct = ad.get_balance()
            except BrokerError as e:
                add("account readable", False, str(e))
        add("account identity read", acct is not None, acct.account_id_masked if acct else "-")
        add("adapter verified by an acceptance test", ad is not None and ad.verified,
            "UNVERIFIED: run the broker acceptance test with this account first" if ad and not ad.verified else "ok")
        add("kill switch armed (not engaged)", self.risk.kill_switch is None, "ok" if not self.risk.kill_switch else
            "engaged")
        add("trading not locked", self.risk.trading_locked is None, "ok")
        add("reconciliation clean", self.state.state != S.RECONCILIATION_REQUIRED, self.state.state)
        off = self.clock_offset()
        add("clock in sync (measured)", off is not None and abs(off) < 2.0,
            "not measured yet: no data-provider response" if off is None else f"offset {off} s")
        return items

    def arm_live(self, cid: str, ack: str, max_capital: Decimal, daily_loss: Decimal) -> dict:
        if ack.strip() != LIVE_ACK:
            raise PermissionError(f"type {LIVE_ACK!r} exactly")
        items = self.readiness(cid)
        failed = [i for i in items if not i["passed"]]
        if failed:
            raise PermissionError("LIVE NOT READY: " + "; ".join(f"{i['check']} ({i['detail']})" for i in failed))
        if max_capital <= 0 or daily_loss <= 0:
            raise ValueError("set a maximum capital and a daily loss cap above 0")
        ad = self.connections[cid]
        caps = ad.capabilities()
        self.live = {"armed": True, "connection_id": cid, "max_capital": str(max_capital),
                     "daily_loss": str(daily_loss), "ts": now_ms(),
                     "permissions": {"stock": caps.get("stocks"), "etf": caps.get("etfs"), "crypto": caps.get("crypto"),
                                     "fx": caps.get("forex"), "future": caps.get("futures")}}
        self.mode = "live"
        self._sync_state("live armed")
        self.db.execute("INSERT INTO session_snapshots (session_id, ts, mode, config) VALUES (?,?,?,?)",
                        (new_id("SESS"), now_ms(), "live", dumps({"live": self.live, "limits": asdict(self.risk.limits),
                                                                  "bots": {k: b.as_dict() for k, b in self.bots.items()},
                                                                  "version": __version__})))
        self.audit("mode", f"LIVE ARMED on {cid} with caps {max_capital} / daily loss {daily_loss}",
                   severity="critical", data=self.live)
        return self.live

    def disarm_live(self, reason: str) -> dict:
        self.live = {"armed": False}
        self.mode = "paper"
        self.db.set_setting("mode", "paper")
        self._sync_state("live disarmed: " + reason)
        self.audit("mode", f"LIVE disarmed: {reason}", severity="warning")
        return {"armed": False}

    # ================================================================== views and health
    def account_view(self) -> dict:
        br = self.broker_for(self.mode)
        a = br.get_balance()
        positions = self.paper.positions_detail() if br is self.paper else [
            {"instrument_id": k, "qty": str(v)} for k, v in br.get_positions().items()]
        fills = self.db.query("SELECT * FROM fills WHERE environment=? ORDER BY ts DESC LIMIT 50",
                              ("live" if self.mode == "live" else "paper",))
        day0 = self.risk.day_start_equity
        realized = sum(Decimal(p.get("realized") or 0) for p in positions)
        unreal = sum(Decimal(p["unrealized"]) for p in positions if p.get("unrealized"))
        return {"mode": self.mode, "badge": a.source, "account": _acct(a), "positions": positions,
                "open_orders": [asdict(o) for o in br.get_open_orders()],
                "day_pnl": None if day0 is None or a.equity is None else str((a.equity - day0).quantize(Decimal("0.01"))),
                "realized": str(realized.quantize(Decimal("0.01"))), "unrealized": str(unreal.quantize(Decimal("0.01"))),
                "drawdown": None if not self.risk.peak_equity or a.equity is None else
                str(((self.risk.peak_equity - a.equity) / self.risk.peak_equity).quantize(Decimal("0.0001"))),
                "trades_today": sum(b.trades_today for b in self.bots.values()),
                "fills": fills[:20], "ts": now_ms()}

    def clock_offset(self) -> Optional[float]:
        """Median seconds between this computer's clock and data-provider Date headers; None until one responds."""
        return self.http.clock_offset()

    def health(self) -> dict:
        comp = {"backend": {"status": "ok", "uptime_s": round(time.time() - self.started), "pid": os.getpid()},
                "database": {"status": "ok" if all(c["ok"] for c in self.checks if "database" in c["name"]) else
                             "error", "bytes": self.db.size_bytes()},
                "market_feed": {"status": "ok" if not self.offline else "offline", "http": self.http.summary(),
                                "series": {k: {"fresh": v.get("fresh"), "provider": v.get("provider"),
                                               "quality": (v.get("quality") or {}).get("score"),
                                               "age_s": (v.get("quality") or {}).get("last_bar_age_s"),
                                               "simulated": v.get("simulated")}
                                           for k, v in list(self.md.status_by_series.items())[-30:]}},
                "broker": {"status": "ok", "mode": self.mode, "paper": "simulated",
                           "connections": {k: v.status() for k, v in self.connections.items()}},
                "strategy_engine": {"status": "running" if any(b.state == "running" for b in self.bots.values())
                                    else "idle", "bots": len(self.bots),
                                    "last_tick_s_ago": None if not self.last_tick else round(time.time() - self.last_tick,
                                                                                             1)},
                "risk_service": {"status": "ENGAGED" if self.risk.kill_switch else ("LOCKED" if self.risk.trading_locked
                                                                                    else "armed"),
                                 "counters": self.risk.counters},
                "execution_engine": {"status": "ok", "latency_ms": self.oms.latency_stats()},
                "research": {"jobs": len(self.jobs.jobs), "ledger": self.ledger.counts()},
                "websocket": {"clients": self.bus.subscribers}}
        return {"app": APP_ID, "version": __version__, "state": self.state.view(), "mode": self.mode,
                "startup_checks": self.checks, "components": comp, "system": system_resources(self.paths.base),
                "gpu": "not used (no GPU acceleration in this build)", "ts": now_ms()}

    def overview(self) -> dict:
        return {"version": __version__, "state": self.state.view(), "mode": self.mode, "live": self.live,
                "risk": self.risk.state(), "bots": [b.as_dict() for b in self.bots.values()],
                "library": lib_summary(), "features": feature_summary(), "agents": _roster.roster_summary(),
                "brokers": broker_matrix(), "live_ack": LIVE_ACK, "offline": self.offline}

    # ================================================================== shutdown
    def shutdown(self) -> dict:
        """Section 215: stop new signals, report live exposure, persist, stop threads, close the database."""
        if self.state.can(S.SHUTTING_DOWN):
            self.state.to(S.SHUTTING_DOWN, "owner shut down")
        for b in self.bots.values():
            if b.state == "running":
                b.state = "running"            # remembered: paper bots resume after restart
        self._save_bots()
        self._persist_risk()
        live_open = []
        if self.mode == "live":
            try:
                live_open = [k for k, v in self.broker_for("live").get_positions().items() if v != 0]
            except BrokerError:
                pass
        self._stop.set()
        self.jobs.shutdown()
        self.audit("system", "shut down" + (f"; LIVE positions still open at the broker: {live_open}" if live_open
                                            else ""), severity="warning" if live_open else "info")
        try:
            self.db.backup(self.paths.backups / f"app-{datetime.now(timezone.utc):%Y%m%d}.sqlite3")
        except Exception:                             # noqa: BLE001
            pass
        return {"stopped": True, "live_positions_open": live_open}


def _acct(a) -> dict:
    return {"account": a.account_id_masked, "environment": a.environment, "currency": a.base_currency,
            "equity": None if a.equity is None else str(a.equity), "cash": None if a.cash is None else str(a.cash),
            "buying_power": None if a.buying_power is None else str(a.buying_power),
            "margin_used": None if a.margin_used is None else str(a.margin_used), "simulated": a.simulated,
            "badge": a.source, "permissions": a.permissions, "as_of": a.as_of}


def system_resources(base: Path) -> dict:
    out: dict[str, Any] = {"cpu_count": os.cpu_count()}
    try:
        du = shutil.disk_usage(base)
        out["disk_free_gb"] = round(du.free / 1e9, 1)
    except OSError:
        pass
    try:
        if os.name == "nt":
            import ctypes

            class MS(ctypes.Structure):
                _fields_ = [("l", ctypes.c_ulong), ("load", ctypes.c_ulong), ("total", ctypes.c_ulonglong),
                            ("avail", ctypes.c_ulonglong), ("tp", ctypes.c_ulonglong), ("ap", ctypes.c_ulonglong),
                            ("tv", ctypes.c_ulonglong), ("av", ctypes.c_ulonglong), ("ae", ctypes.c_ulonglong)]
            m = MS()
            m.l = ctypes.sizeof(MS)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
            out["ram_used_pct"] = m.load
            out["ram_total_gb"] = round(m.total / 1e9, 1)
        else:
            info = {}
            with open("/proc/meminfo") as fh:
                for line in fh:
                    k, v = line.split(":", 1)
                    info[k] = int(v.split()[0])
            out["ram_total_gb"] = round(info["MemTotal"] / 1e6, 1)
            out["ram_used_pct"] = round(100 * (1 - info["MemAvailable"] / info["MemTotal"]), 1)
            out["load_1m"] = round(os.getloadavg()[0], 2)
    except Exception:                                 # noqa: BLE001
        pass
    return out
