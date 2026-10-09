"""Autopilot: fully automated PAPER trading, from research to running bots, with no clicks.

Every cycle (a few seconds apart, in its own thread) it does three things, in this order:

1. Review the bots it runs. A bot is retired (its position closed through the risk service, then removed) when
   * it has 30+ closed paper trades and their mean return sits below the backtest's 95% interval or is not positive,
   * it has 15+ closed paper trades and has lost more than 10% of traded notional in total, or
   * a fresh re-test of its strategy on newer data (every 14 days) is REJECTED.
   A retired strategy/market/timeframe is not used again for 30 days.
2. Fill free bot slots from the research ledger, best evidence first:
   * QUALIFIED: STANDARD/DEEP research verdict PAPER TEST (every required gate passed), then
   * PROBATION: verdict RESEARCH FURTHER, with a positive untouched test segment, positive walk-forward
     out-of-sample Sharpe, positive Sharpe at 2x costs, 20+ test trades and quality >= 45. Paper trading is how such
     a strategy collects real out-of-sample evidence; it is labelled PROBATION everywhere.
   REJECTED strategies are never deployed. At most one bot per instrument and two per market type.
3. Research in the background, one job at a time so trading and the page stay responsive:
   * screen untested strategy/market/timeframe combinations with FAST research (rate limited per hour),
   * confirm promising screens with STANDARD research (9 parameter sets, walk-forward, Monte Carlo, DSR, PBO).
   Every run is written to the ledger and counted as a trial, so the multiple-testing correction gets stricter
   as the autopilot searches more.

What it never does: trade real money (it only creates paper/shadow bots; live needs the owner's separate arming),
change risk limits, re-arm a kill switch, or write new trading code (it chooses among the fixed, versioned
templates of the strategy library).
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from collections import deque
from dataclasses import asdict, dataclass, field
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Optional

from tradingai.core import logs
from tradingai.core.ids import new_id
from tradingai.market.instruments import MarketType
from tradingai.market.universe import paper_tradable
from tradingai.research.compare import compare as compare_runs
from tradingai.risk.service import OrderRequest
from tradingai.storage.db import now_ms
from tradingai.strategies.library import MARKET_OF, specs

if TYPE_CHECKING:
    from tradingai.app import App

log = logs.get("autopilot")
DAY = 86_400_000
MARKET_TFS = {"crypto": ("1h", "4h", "1d"), "stock": ("1d",), "etf": ("1d", "1h"), "fx": ("1h", "4h"),
              "future": ("1d",)}
LOOKBACK = {"1h": 5000, "4h": 3000, "1d": 2500}
MARKETS = ("crypto", "stock", "etf", "fx", "future")


@dataclass
class APConfig:
    enabled: bool = True
    max_bots: int = 6
    markets: list = field(default_factory=lambda: list(MARKETS))
    allow_probation: bool = True
    screens_per_hour: int = 60
    confirms_per_hour: int = 12
    risk_profile: str = "conservative"


class Autopilot:
    def __init__(self, app: "App"):
        self.app = app
        saved = app.db.get_setting("autopilot", {}) or {}
        known = APConfig.__dataclass_fields__
        self.cfg = APConfig(**{k: v for k, v in (saved.get("config") or {}).items() if k in known})
        self.mem: dict[str, Any] = {"retired": {}, "cursor": {}, "slot_cursor": 0, "unavailable": {},
                                    "screened": 0, "confirmed": 0, "deployed": 0, "retired_count": 0}
        self.mem.update({k: v for k, v in (saved.get("memory") or {}).items() if k in self.mem})
        self.jobs: dict[str, dict] = {}                   # job id -> {"kind", "key", ...} for jobs this run started
        self.activity: deque = deque(maxlen=60)
        self.doing = "starting"
        self.last_cycle: Optional[int] = None
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._rate: dict[str, list[float]] = {"screen": [], "confirm": []}

    # ------------------------------------------------------------------ lifecycle
    def start(self) -> None:
        if self._thread is None:
            self._thread = threading.Thread(target=self._loop, name="autopilot", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._save()

    def _loop(self) -> None:
        self._stop.wait(5)                                 # let the trading loop and the page come up first
        while not self._stop.is_set():
            try:
                self.cycle()
            except Exception as e:                         # noqa: BLE001 - the autopilot survives; the error is shown
                log.error(f"autopilot cycle error: {type(e).__name__}: {e}")
                self._note(f"error: {type(e).__name__}: {e}", "error")
            self._stop.wait(10)

    def _save(self) -> None:
        self.app.db.set_setting("autopilot", {"config": asdict(self.cfg), "memory": self.mem})

    def _note(self, msg: str, severity: str = "info", **data) -> None:
        ev = {"ts": now_ms(), "message": msg, **data}
        self.activity.appendleft(ev)
        self.app.bus.publish("autopilot", ev, severity=severity)

    # ------------------------------------------------------------------ owner controls
    def configure(self, changes: dict) -> dict:
        with self._lock:
            if "enabled" in changes:
                self.cfg.enabled = bool(changes["enabled"])
            if "max_bots" in changes:
                self.cfg.max_bots = max(0, min(20, int(changes["max_bots"])))
            if "markets" in changes:
                self.cfg.markets = [m for m in changes["markets"] if m in MARKETS]
            if "allow_probation" in changes:
                self.cfg.allow_probation = bool(changes["allow_probation"])
            self._save()
        self.app.audit("autopilot", f"autopilot settings changed: {changes}", data=asdict(self.cfg))
        if "enabled" in changes:
            self._note("AUTOPILOT ON" if self.cfg.enabled else "AUTOPILOT OFF: its bots were stopped")
        else:
            self._note("autopilot settings changed")
        if changes.get("enabled") is False:
            for b in self.bots():
                if b.state == "running":
                    self.app.bot_action(b.bot_id, "stop", by="autopilot")
        return self.view()

    def bots(self) -> list:
        return [b for b in self.app.bots.values() if getattr(b, "managed_by", "owner") == "autopilot"]

    def view(self) -> dict:
        bots = self.bots()
        return {"config": asdict(self.cfg), "doing": self.doing if self.cfg.enabled else "off",
                "last_cycle": self.last_cycle, "bots": [b.as_dict() for b in bots],
                "running": sum(1 for b in bots if b.state == "running"),
                "counts": {k: self.mem[k] for k in ("screened", "confirmed", "deployed", "retired_count")},
                "candidates": self.candidates()[:10], "activity": list(self.activity)[:25],
                "rules": "paper only; never live; chooses among fixed strategy templates; risk limits unchanged"}

    # ------------------------------------------------------------------ one cycle
    def cycle(self) -> dict:
        app = self.app
        with self._lock:
            self.last_cycle = now_ms()
            if not self.cfg.enabled:
                self.doing = "off"
                return {"skipped": "off"}
            if app.state.state in ("ERROR", "SHUTTING_DOWN", "BOOTING"):
                return {"skipped": app.state.state}
            if app.mode == "live":
                self.doing = "paused: the system is in LIVE mode (autopilot runs paper only)"
                return {"skipped": "live"}
            out = {"reviewed": self._review(), "deployed": self._deploy()}
            self._collect_jobs()
            out["research"] = self._research()
            self._save()
            return out

    # ------------------------------------------------------------------ 1. review running bots
    def _review(self) -> list[str]:
        retired = []
        for b in list(self.bots()):
            why = self._retire_reason(b)
            if why and self._retire(b, why):
                retired.append(b.bot_id)
        return retired

    def _retire_reason(self, b) -> Optional[str]:
        if b.state == "retiring":
            return b.note or "retiring"
        if b.kind == "portfolio":
            return self._portfolio_retire_reason(b)
        paper = self.app.paper_trades(b.strategy_id, b.instrument_id)
        if len(paper) >= 15 and sum(paper) < -0.10:
            return f"early stop: {len(paper)} paper trades lost {sum(paper):.1%} of traded notional"
        if len(paper) >= 30:
            exp = self.app.ledger.get(b.experiment_id) if b.experiment_id else None
            bt = [t["ret"] for t in ((exp or {}).get("results") or {}).get("test_trades", []) if t.get("ret") is not None]
            c = compare_runs(bt, paper)
            mean = c["columns"]["paper"]["expectancy"]
            if "PAPER_BELOW_BACKTEST_RANGE" in c["flags"] or mean <= 0:
                return f"{len(paper)} paper trades: mean {mean:+.3%} per trade, below the backtest's range or not positive"
        last = self.app.db.one("SELECT json_extract(results, '$.verdict') AS v, created FROM experiments WHERE "
                               "strategy_id=? AND json_extract(dataset, '$.instrument')=? AND json_extract(dataset, "
                               "'$.tf')=? AND profile IN ('STANDARD','DEEP','PORTFOLIO') AND status!='RUNNING' ORDER BY created "
                               "DESC LIMIT 1", (b.strategy_id, b.instrument_id, b.tf))
        if last and last["created"] > b.created and last["v"] == "REJECT":
            return "re-test on newer data: REJECT"
        if now_ms() - b.created > 14 * DAY and (not last or now_ms() - last["created"] > 14 * DAY):
            self._queue("revalidate", b.strategy_id, b.instrument_id, b.tf, "STANDARD")
        return None

    def _portfolio_retire_reason(self, b) -> Optional[str]:
        from tradingai.engine.portfolio_bot import strategy_pnl
        last = self.app.db.one("SELECT json_extract(results, '$.verdict') AS v, created FROM experiments WHERE "
                               "strategy_id=? AND profile='PORTFOLIO' AND status!='RUNNING' ORDER BY created DESC "
                               "LIMIT 1", (b.strategy_id,))
        if last and last["created"] > b.created and last["v"] == "REJECT":
            return "re-test on newer data: REJECT"
        budget = (self.app.paper.get_balance().equity or Decimal(0)) * Decimal(str(b.allocation))
        pnl = strategy_pnl(self.app, b.strategy_id)
        if budget > 0 and pnl < -Decimal("0.15") * budget:
            return f"loss stop: the portfolio lost {pnl:,.2f} (more than 15% of its allocation)"
        if now_ms() - b.created > 14 * DAY and (not last or now_ms() - last["created"] > 14 * DAY):
            self._queue("revalidate", b.strategy_id, b.instrument_id, "1d", "PORTFOLIO")
        return None

    def _retire(self, b, why: str) -> bool:
        """Close this strategy's paper position(s) through the risk service, then remove the bot."""
        app = self.app
        b.state, b.note = "retiring", why
        if b.kind == "portfolio":
            from tradingai.engine.portfolio_bot import held_lots
            open_lots = held_lots(app, b.strategy_id)
            if open_lots:
                b.pending = {iid: 0.0 for iid in open_lots}
                from tradingai.engine.portfolio_bot import _execute
                _execute(app, b, "paper")
                if held_lots(app, b.strategy_id):
                    self.doing = f"retiring {b.strategy_id}: closing its holdings when markets open"
                    app._save_bots()
                    return False
            return self._remove(b, why)
        lots = {p["instrument_id"]: p for p in app.paper.positions_detail()}.get(b.instrument_id)
        held = Decimal((lots or {}).get("strategy_lots", {}).get(b.strategy_id, "0"))
        if held != 0:
            inst = app.book.get(b.instrument_id)
            q = app.quote(b.instrument_id)
            if q is None:
                self.doing = f"retiring {b.instrument_id}: waiting for a fresh price to close the position"
                return False
            bars, st = app.md.bars(b.instrument_id, b.tf, lookback=3)
            snap = app.risk_snapshot(inst, bars, st, "paper")
            acct = app.paper.get_balance()
            req = OrderRequest(client_order_id="", instrument_id=b.instrument_id,
                               market=MARKET_OF.get(inst.market_type, "crypto"), side="sell" if held > 0 else "buy",
                               quantity=abs(held), reference_price=Decimal(str(q["price"])), limit_price=None,
                               multiplier=inst.multiplier, environment="paper", account_id=acct.account_id_masked,
                               reduces_position=True, tradable=paper_tradable(inst), quantity_step=inst.quantity_step)
            res = app.oms.place(decision_id=new_id("RET"), req=req, snapshot=snap, broker=app.paper,
                                broker_symbol=inst.symbol, mode="paper", strategy_id=b.strategy_id,
                                decided_at=time.time())
            if res.get("status") not in ("FILLED",):
                self.doing = f"retiring {b.instrument_id}: close order {res.get('status')} ({res['risk']['reason']})"
                app._save_bots()
                return False
        return self._remove(b, why)

    def _remove(self, b, why: str) -> bool:
        app = self.app
        key = self._key(b.strategy_id, b.instrument_id, b.tf)
        self.mem["retired"][key] = now_ms() + 30 * DAY
        self.mem["retired_count"] += 1
        app.bots.pop(b.bot_id, None)
        app._save_bots()
        app._sync_state("autopilot retired a bot")
        app.audit("autopilot", f"retired {b.strategy_id} on {b.instrument_id} {b.tf}: {why}", severity="warning")
        self._note(f"retired {b.strategy_id} on {b.instrument_id} {b.tf}: {why}", "warning")
        return True

    # ------------------------------------------------------------------ 2. deploy
    def candidates(self) -> list[dict]:
        rows = self.app.db.query(
            "SELECT experiment_id, strategy_id, created, json_extract(dataset, '$.instrument') AS iid, "
            "json_extract(dataset, '$.tf') AS tf, json_extract(results, '$.verdict') AS verdict, "
            "json_extract(results, '$.quality.score') AS quality, json_extract(results, '$.test.trades') AS trades, "
            "json_extract(results, '$.test.total_return') AS test_ret, "
            "json_extract(results, '$.walk_forward.oos_sharpe') AS wf, "
            "json_extract(results, '$.cost_stress.\"2.0x\".sharpe') AS sh2x, "
            "json_extract(results, '$.reproducibility.simulated_data') AS sim, "
            "json_extract(results, '$.beats_benchmark') AS beats "
            "FROM experiments WHERE profile IN ('STANDARD','DEEP','PORTFOLIO') AND status!='RUNNING' AND created>? "
            "ORDER BY created DESC", (now_ms() - 30 * DAY,))
        seen, out = set(), []
        for r in rows:
            k = self._key(r["strategy_id"], r["iid"], r["tf"])
            if k in seen:                                   # only the newest result per combination counts
                continue
            seen.add(k)
            tier = None
            if r["verdict"] == "PAPER TEST":
                tier = "qualified"
            elif r["verdict"] == "RESEARCH FURTHER" and self.cfg.allow_probation and (r["trades"] or 0) >= 20 and \
                    (r["test_ret"] or 0) > 0 and (r["wf"] or 0) > 0 and (r["sh2x"] or 0) > 0 and (r["quality"] or 0) >= 45:
                tier = "probation"
            if tier is None or self.mem["retired"].get(k, 0) > now_ms():
                continue
            if (r["iid"] or "").startswith("PORTFOLIO:") and not r["beats"]:
                continue                       # a portfolio must also beat simply holding its universe (held out)
            if bool(r["sim"]) != bool(self.app.offline):    # real data online, DEMO only when offline
                continue
            out.append(dict(r, tier=tier, key=k))
        out.sort(key=lambda r: (r["tier"] != "qualified", -(r["quality"] or 0)))
        return out

    def _deploy(self) -> list[str]:
        app = self.app
        if app.risk.kill_switch or app.risk.trading_locked:
            self.doing = "waiting: STOP ALL TRADING or a loss lock is engaged (the autopilot never re-arms)"
            return []
        if app.state.state == "RECONCILIATION_REQUIRED":
            self.doing = "waiting: reconciliation required"
            return []
        mine = self.bots()
        for b in mine:                                      # restart bots the owner did not stop on purpose
            if b.state == "stopped" and b.note != "stopped by owner":
                app.bot_action(b.bot_id, "start", by="autopilot")
        free = self.cfg.max_bots - len(mine)
        if free <= 0:
            return []
        used_inst = {b.instrument_id for b in app.bots.values() if b.kind != "portfolio"}
        used_keys = {self._key(b.strategy_id, b.instrument_id, b.tf) for b in app.bots.values()}
        per_market: dict[str, int] = {}
        for b in mine:
            m = "portfolio" if b.kind == "portfolio" else MARKET_OF.get(app.book.get(b.instrument_id).market_type)
            per_market[m] = per_market.get(m, 0) + 1
        made = []
        for c in self.candidates():
            if len(made) >= free:
                break
            if c["key"] in used_keys or c["iid"] in used_inst:
                continue
            if c["iid"].startswith("PORTFOLIO:"):
                from tradingai.engine.portfolio_bot import deployable
                if not deployable(app, c["strategy_id"])[0] or per_market.get("portfolio", 0) >= 2:
                    continue
                alloc = 0.15 if c["tier"] == "qualified" else 0.10
                try:
                    bot = app.create_portfolio_bot(c["strategy_id"], experiment_id=c["experiment_id"], allocation=alloc,
                                                   managed_by="autopilot", tier=c["tier"],
                                                   note=f"{c['tier'].upper()}: portfolio research {c['verdict']}, "
                                                        f"quality {c['quality']}, {alloc:.0%} of equity")
                    app.bot_action(bot["bot_id"], "start", by="autopilot")
                except (ValueError, PermissionError) as e:
                    self._note(f"could not start portfolio {c['strategy_id']}: {e}", "warning")
                    continue
                made.append(bot["bot_id"])
                used_keys.add(c["key"])
                per_market["portfolio"] = per_market.get("portfolio", 0) + 1
                self.mem["deployed"] += 1
                self._note(f"started a {c['tier'].upper()} paper PORTFOLIO bot: {c['strategy_id']} with {alloc:.0%} of "
                           f"equity (research {c['verdict']}, quality {c['quality']})", bot_id=bot["bot_id"])
                continue
            if c["iid"] not in app.sources:
                continue
            inst = app.book.get(c["iid"])
            m = MARKET_OF.get(inst.market_type)
            if m not in self.cfg.markets or per_market.get(m, 0) >= 2 or not paper_tradable(inst)[0]:
                continue
            try:
                bot = app.create_bot(c["iid"], c["tf"], c["strategy_id"], "strategy+ensemble", self.cfg.risk_profile, 10,
                                     managed_by="autopilot", tier=c["tier"], experiment_id=c["experiment_id"],
                                     note=f"{c['tier'].upper()}: research {c['verdict']}, quality {c['quality']}")
                app.bot_action(bot["bot_id"], "start", by="autopilot")
            except (ValueError, PermissionError) as e:
                self._note(f"could not start {c['strategy_id']} on {c['iid']}: {e}", "warning")
                continue
            made.append(bot["bot_id"])
            used_inst.add(c["iid"])
            used_keys.add(c["key"])
            per_market[m] = per_market.get(m, 0) + 1
            self.mem["deployed"] += 1
            self._note(f"started a {c['tier'].upper()} paper bot: {c['strategy_id']} on {c['iid']} {c['tf']} "
                       f"(research {c['verdict']}, quality {c['quality']})", bot_id=bot["bot_id"])
        return made

    # ------------------------------------------------------------------ 3. research
    def _collect_jobs(self) -> None:
        for jid, meta in list(self.jobs.items()):
            j = self.app.jobs.view(jid, with_result=True)
            if j is None or j["state"] in ("queued", "running"):
                continue
            self.jobs.pop(jid)
            if j["state"] != "done":
                if any(x in (j.get("error") or "") for x in ("bars of", "HttpError", "no daily data")):
                    self.mem["unavailable"][f"{meta['iid']}|{meta['tf']}"] = now_ms() + DAY // 4
                continue
            eid = (j.get("result") or {}).get("experiment_id")
            e = self.app.ledger.get(eid) if eid else None
            r = (e or {}).get("results") or {}
            if meta["kind"] == "screen":
                self.mem["screened"] += 1
                t = r.get("test") or {}
                if r.get("status") == "ok" and (t.get("trades") or 0) >= 10 and (t.get("total_return") or 0) > 0 and \
                        ((r.get("quality") or {}).get("score") or 0) >= 30:
                    self._queue("confirm", meta["sid"], meta["iid"], meta["tf"], "STANDARD")
                    self._note(f"screen passed: {meta['sid']} on {meta['iid']} {meta['tf']} → full test queued")
            elif meta["kind"] in ("confirm", "revalidate", "portfolio"):
                self.mem["confirmed"] += 1
                self._note(f"{meta['kind']}: {meta['sid']} on {meta['iid']} {meta['tf']} → {r.get('verdict')}",
                           "info" if r.get("verdict") != "REJECT" else "warning")

    def _queue(self, kind: str, sid: str, iid: str, tf: str, profile: str) -> None:
        pend = self.mem.setdefault("pending", [])
        if not any(p["sid"] == sid and p["iid"] == iid and p["tf"] == tf for p in pend):
            pend.append({"kind": kind, "sid": sid, "iid": iid, "tf": tf, "profile": profile})

    def _allowed(self, kind: str) -> bool:
        now = time.time()
        self._rate[kind] = [t for t in self._rate[kind] if now - t < 3600]
        cap = self.cfg.screens_per_hour if kind == "screen" else self.cfg.confirms_per_hour
        return len(self._rate[kind]) < cap

    def _research(self) -> Optional[dict]:
        app = self.app
        if any(app.jobs.view(j) and app.jobs.view(j)["state"] in ("queued", "running") for j in self.jobs):
            return None                                     # one autopilot job at a time
        if any(j["state"] in ("queued", "running") for j in app.jobs.list()):
            self.doing = "waiting for your research job to finish"
            return None
        pend = self.mem.setdefault("pending", [])
        if pend and self._allowed("confirm"):
            p = pend.pop(0)
            return self._submit(p["kind"], p["sid"], p["iid"], p["tf"], p["profile"])
        if not app.offline and self._allowed("confirm"):
            due = self._portfolio_due()
            if due:
                return self._submit("portfolio", due, f"PORTFOLIO:{due}", "1d", "PORTFOLIO")
        if not self._allowed("screen"):
            self.doing = f"research paused for the hour (screening limit {self.cfg.screens_per_hour}/hour)"
            return None
        nxt = self._next_screen()
        if nxt is None:
            self.doing = "nothing new to screen in the selected markets"
            return None
        return self._submit("screen", *nxt, "FAST")

    def _portfolio_due(self) -> Optional[str]:
        from tradingai.research.portfolio import PORTFOLIOS
        for sid in PORTFOLIOS:
            if self.mem["unavailable"].get(f"PORTFOLIO:{sid}|1d", 0) > now_ms():
                continue
            r = self.app.db.one("SELECT created FROM experiments WHERE strategy_id=? AND profile='PORTFOLIO' "
                                "ORDER BY created DESC LIMIT 1", (sid,))
            if not r or now_ms() - r["created"] > 7 * DAY:
                return sid
        return None

    def _submit(self, kind: str, sid: str, iid: str, tf: str, profile: str) -> Optional[dict]:
        try:
            if profile == "PORTFOLIO":
                j = self.app.submit_portfolio(sid, by="autopilot")
            else:
                j = self.app.submit_research(sid, iid, tf, profile, LOOKBACK.get(tf, 3000), slim=(kind == "screen"),
                                             by="autopilot")
        except ValueError as e:
            self._note(f"skipped {sid} on {iid} {tf}: {e}", "warning")
            return None
        self.jobs[j["job_id"]] = {"kind": kind, "sid": sid, "iid": iid, "tf": tf}
        self._rate["screen" if kind == "screen" else "confirm"].append(time.time())
        label = {"screen": "screening", "confirm": "full test", "revalidate": "re-testing on newer data",
                 "portfolio": "portfolio backtest"}[kind]
        self.doing = f"{label}: {sid} on {iid} {tf}"
        return {"kind": kind, "job_id": j["job_id"]}

    def _slots(self) -> list[tuple[str, str, str]]:
        app = self.app
        out = []
        for iid, src in app.sources.items():
            demo = src.provider == "demo"
            if demo != bool(app.offline):
                continue
            inst = app.book.get(iid)
            m = MARKET_OF.get(inst.market_type)
            if m not in self.cfg.markets or not paper_tradable(inst)[0]:
                continue
            tfs = ("1h", "4h") if demo else MARKET_TFS.get(m, ())
            for tf in tfs:
                if self.mem["unavailable"].get(f"{iid}|{tf}", 0) > now_ms():
                    continue
                out.append((iid, tf, m))
        return out

    def _next_screen(self) -> Optional[tuple[str, str, str]]:
        slots = self._slots()
        if not slots:
            return None
        lib = specs()
        recent = {self._key(r["strategy_id"], r["iid"], r["tf"]) for r in self.app.db.query(
            "SELECT strategy_id, json_extract(dataset, '$.instrument') AS iid, json_extract(dataset, '$.tf') AS tf "
            "FROM experiments WHERE created>?", (now_ms() - 30 * DAY,))}
        for k in range(len(slots)):
            iid, tf, m = slots[(self.mem["slot_cursor"] + k) % len(slots)]
            names = sorted((s.strategy_id for s in lib.values() if s.runnable and m in s.supported_markets and
                            (not s.supported_timeframes or tf in s.supported_timeframes)),
                           key=lambda sid: hashlib.sha256(f"{sid}|{iid}|{tf}".encode()).hexdigest())
            cur = self.mem["cursor"].get(f"{iid}|{tf}", 0)
            for i in range(cur, len(names)):
                key = self._key(names[i], iid, tf)
                if key in recent or self.mem["retired"].get(key, 0) > now_ms():
                    continue
                self.mem["cursor"][f"{iid}|{tf}"] = i + 1
                self.mem["slot_cursor"] = (self.mem["slot_cursor"] + k + 1) % len(slots)
                return names[i], iid, tf
        return None

    @staticmethod
    def _key(sid: str, iid: str, tf: str) -> str:
        return f"{sid}|{iid}|{tf}"

    def _clear_unavailable(self) -> None:
        self.mem["unavailable"] = {}

    def export(self) -> str:
        return json.dumps(self.view(), default=str)
