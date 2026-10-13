"""The master system agent and its 100 trading agents A001-A100 (owner's instruction of 2026-10-13).

One master agent powers and coordinates exactly 100 trading agents. It controls:

* STRATEGY ASSIGNMENTS. Each agent has a role: a market group, a strategy family, a bar size, and three candidate
  templates chosen from the evidence in docs/STRATEGY_RESEARCH.md. Each agent owns one distinct instrument, so two
  agents can never hold conflicting positions in the same market.
* TRAINING AND VALIDATION. For every candidate the master runs the research engine on the agent's own market data.
  The data is a documented dataset: provider, symbol, bar size, date range, bar count and SHA-256, all stored in the
  research ledger.
  - Parameters are fitted on the first 60% of the bars (train).
  - The candidate is chosen on the next 20% (validation).
  - The last 20% is a held-out test, touched once. Walk-forward refits are checked out of sample.
  - The objective is Sharpe net of modelled costs under the intraday rules, plus every gate of the research engine
    (Deflated Sharpe, PBO, 2x-cost stress, minimum trades...). Only a PAPER TEST verdict may trade, and only in paper.
* VERSIONS, PROMOTION, ROLLBACK.
  - Every chosen policy is a numbered version (agent_versions table).
  - The first validated version becomes active in paper.
  - A newer validated version first runs in shadow. It is promoted only if, on the bars since it was created (bars it
    was not trained on), it beat the active version net of costs without a deeper drawdown.
  - An active version is rolled back automatically, or the agent suspended if no earlier version is valid, when its
    paper results fall below its validation, it loses more than 2% of equity, or it breaches its daily loss limit
    twice in 7 days.
* CAPITAL ALLOCATION. Virtual budgets go only to agents allowed to trade. They sum within the gross-exposure limit and
  each is capped at the per-position limit. Each agent has a daily loss limit; breaching it stops its entries for the
  rest of the UTC day.
* EXECUTION PERMISSIONS. An entry needs the master's permission: a validated active version, not suspended, not
  stopped for the day, system running. Exits are always allowed. The deterministic risk service still checks every
  order, and learned safeguards (engine/learning.py) can only block or shrink entries. No agent can change a limit,
  re-arm a kill switch or turn on live trading.
* MONITORING AND EMERGENCY SHUTDOWN. Agent jobs run in a bounded pool with fault isolation. The emergency stop
  (risk.kill_switch) stops every agent's entries at once.

Live trading stays off here: "promotion" means the paper account. Real money needs the owner's separate arming.
No agent is a language model.
"""

from __future__ import annotations

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Callable, Optional

from tradingai.market.calendars import session
from tradingai.market.universe import paper_tradable
from tradingai.storage.db import dumps, now_ms
from tradingai.strategies.library import MARKET_OF

if TYPE_CHECKING:
    from tradingai.app import App

TARGET = 100
DAY = 86_400_000
JOB_SECONDS = 10
DATA_SECONDS = 300
WORKERS = 8
RETRAIN_DAYS = 7
SHADOW_MIN_DAYS = 3
MAX_TRAINING_JOBS = 2
DAY_LOSS_PCT = Decimal("0.005")          # an agent may lose 0.5% of equity in a UTC day, then it stops entering
VERSION_LOSS_PCT = Decimal("0.02")       # a version that loses 2% of equity in paper is rolled back
# the longest history the research engine accepts: a held-out test needs at least 30 trades, which 5,000 hourly
# bars (about 7 months of crypto) could not give most strategies (1.5.0 training, first pass: 256 of 300 runs)
LOOKBACK = {"15m": 6000, "1h": 20000, "4h": 6000}
STABLE = {"USDT", "USDC", "DAI", "PYUSD", "EURC", "GUSD", "USDS", "PAX", "BUSD", "TUSD", "FDUSD", "RLUSD", "USD1",
          "WBTC", "CBBTC", "CBETH", "WETH", "LSETH", "MSOL", "JITOSOL"}


@dataclass(frozen=True)
class Role:
    role: str
    label: str
    market: str
    family: str
    tf: str
    candidates: tuple[str, ...]
    why: str


ROLES = {
    "crypto_major": Role("crypto_major", "Crypto majors: trend", "crypto", "trend / time-series momentum", "1h",
                         ("tsmom.none.trail", "donchian_breakout.none.trail", "ema_cross.adx.flip"),
                         "crypto time-series momentum (Liu and Tsyvinski 2021); large coins show momentum"),
    "crypto_trend": Role("crypto_trend", "Liquid crypto: trend", "crypto", "trend / momentum", "1h",
                         ("tsmom.none.trail", "donchian_breakout.none.trail", "ema_cross.adx.flip"),
                         "large, liquid coins show daily and weekly momentum (IRFA 2021; Ficura 2023)"),
    "crypto_reversion": Role("crypto_reversion", "Liquid crypto: mean reversion", "crypto", "short-term mean reversion",
                             "1h", ("rsi2_reversion.none.time", "zscore_reversion.none.atr_bracket",
                                    "bollinger_reversion.adx.time"),
                             "reversal documented in less liquid coins; most cost-sensitive family"),
    "etf_intraday": Role("etf_intraday", "Index and sector ETFs: intraday momentum", "etf", "intraday momentum / ORB",
                         "15m", ("first_hour_momentum.none.time", "noise_band_momentum.none.time", "orb.none.time"),
                         "first half-hour predicts last half-hour in SPY and active ETFs (Gao et al. 2018)"),
    "stock_breakout": Role("stock_breakout", "Large US stocks: breakouts", "stock", "opening-range / volatility breakout",
                           "15m", ("active_orb.none.time", "orb.relvol.time", "vol_breakout.none.atr_bracket"),
                           "stocks-in-play opening-range breakout (Zarattini, Barbon and Aziz); disputed after costs"),
    "stock_reversion": Role("stock_reversion", "Large US stocks: mean reversion", "stock", "short-term mean reversion",
                            "1h", ("rsi2_reversion.none.time", "ibs_reversion.none.time",
                                   "zscore_reversion.none.atr_bracket"),
                            "short-term reversal survives costs only in large caps with lower turnover"),
    "fx_trend": Role("fx_trend", "Forex: session momentum", "fx", "session momentum / trend", "1h",
                     ("london_open_momentum.none.time", "ny_overlap_continuation.none.time", "tsmom.none.trail"),
                     "currency time-series momentum (Moskowitz, Ooi and Pedersen 2012)"),
    "index_futures": Role("index_futures", "Equity-index futures: opening breakouts", "future",
                          "opening-range / initial-balance breakout", "15m",
                          ("orb.none.time", "initial_balance_breakout.none.time", "overnight_range_breakout.none.time"),
                          "intraday momentum in index products (Gao et al. 2018)"),
}
ETF_INTRADAY = ["SPY", "QQQ", "IWM", "DIA", "XLK", "XLF", "XLE", "XLV", "XLY", "XLI", "SMH", "XBI", "KRE", "GLD", "TLT"]
STOCK_BREAKOUT = ["AAPL", "MSFT", "NVDA", "AMZN", "TSLA", "META", "GOOGL", "AMD", "NFLX", "AVGO", "PLTR", "COIN", "UBER",
                  "ORCL", "CRM", "ADBE", "INTC"]
STOCK_REVERSION = ["JPM", "XOM", "BRK-B", "LLY", "V", "MA", "UNH", "COST", "WMT", "HD", "PG", "JNJ", "KO", "PEP", "MRK",
                   "CVX", "BAC"]
# role, first agent number, last agent number, fixed instrument ids (None: chosen from market discovery)
PLAN: list[tuple[str, int, int, Optional[list[str]]]] = [
    ("crypto_major", 1, 3, ["COINBASE:BTC-USD", "COINBASE:ETH-USD", "COINBASE:SOL-USD"]),
    ("crypto_trend", 4, 25, None),
    ("crypto_reversion", 26, 40, None),
    ("etf_intraday", 41, 55, [f"US:{s}" for s in ETF_INTRADAY]),
    ("stock_breakout", 56, 72, [f"US:{s}" for s in STOCK_BREAKOUT]),
    ("stock_reversion", 73, 89, [f"US:{s}" for s in STOCK_REVERSION]),
    ("fx_trend", 90, 94, ["FX:EURUSD", "FX:GBPUSD", "FX:USDJPY", "FX:USDCAD", "FX:AUDUSD"]),
    ("index_futures", 95, 100, ["CME:ES", "CME:MES", "CME:NQ", "CME:MNQ", "CBOT:YM", "CME:RTY"]),
]
DEMO = ["DEMO:DEMO-TREND", "DEMO:DEMO-RANGE", "DEMO:DEMO-VOLATILE"]     # offline only: given to A004-A006


@dataclass
class Agent:
    agent_id: str
    role: str
    partition: list[str] = field(default_factory=list)
    assignment_version: int = 0
    runtime: str = "starting"          # starting | available | degraded | blocked | stopped
    job: str = "idle"
    detail: str = ""
    consumed_version: Optional[int] = None
    last_input_ts: Optional[int] = None
    last_price: Optional[str] = None
    heartbeat: Optional[int] = None
    job_ms: Optional[float] = None
    next_action: Optional[str] = None
    eligible: list[str] = field(default_factory=list)
    errors: list[dict] = field(default_factory=list)
    history: list[dict] = field(default_factory=list)
    data_at: float = 0.0
    fresh: bool = False

    @property
    def group(self) -> str:
        return self.role

    def compact(self) -> dict:
        r = ROLES[self.role]
        return {"id": self.agent_id, "group": self.role, "role_label": r.label, "family": r.family, "tf": r.tf,
                "partition": self.partition, "runtime": self.runtime, "job": self.job, "detail": self.detail,
                "consumed_version": self.consumed_version, "last_input_ts": self.last_input_ts,
                "last_price": self.last_price, "heartbeat": self.heartbeat, "job_ms": self.job_ms,
                "eligible": len(self.eligible), "errors": len(self.errors), "fresh": self.fresh,
                "assignment_version": self.assignment_version}


class Master:
    """The master system agent. Kept as app.fleet (and app.master) so every page and service uses the same object."""

    def __init__(self, app: "App"):
        self.app = app
        saved = app.db.get_setting("master") or {}
        self.desired = TARGET
        self.plan_version = int(saved.get("plan_version", 0))
        self.agents: dict[str, Agent] = {}
        for role, first, last, _ in PLAN:
            for n in range(first, last + 1):
                self.agents[f"A{n:03d}"] = Agent(f"A{n:03d}", role)
        for aid, s in (saved.get("assign") or {}).items():
            if aid in self.agents:
                self.agents[aid].partition = list(s.get("partition") or [])
                self.agents[aid].assignment_version = int(s.get("version", 0))
        self.suspended: dict[str, dict] = dict(saved.get("suspended") or {})      # aid -> {"until", "why"}
        self.day_stop: dict[str, str] = dict(saved.get("day_stop") or {})         # aid -> UTC date
        self.bot_of: dict[str, str] = dict(saved.get("bot_of") or {})             # aid -> bot id
        self.unavailable: dict[str, int] = dict(saved.get("unavailable") or {})   # "aid|sid" -> retry after (ms)
        self.owner: dict[str, str] = {}
        self.jobs: dict[str, dict] = {}                     # research job id -> {"agent", "sid"}
        self.doing = "starting"
        self.activity: list[dict] = []
        self._lock = threading.RLock()
        self._pool = ThreadPoolExecutor(max_workers=WORKERS, thread_name_prefix="agent")
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self.metrics = {"cycles": 0, "last_cycle_ms": None, "missed_deadlines": 0, "last_cycle": None,
                        "queue_depth": 0, "operate_cycles": 0, "trained": 0, "promoted": 0, "rolled_back": 0,
                        "rejected": 0}
        self._budget_cache: tuple[float, set[str]] = (0.0, set())
        self._last_evolve = 0.0
        self.assign()

    # ================================================================== assignment: one distinct market per agent
    def _discovered(self) -> list[str]:
        app = self.app
        disc = getattr(app, "discovery", None)
        if disc is None or app.offline:
            return []
        out = []
        for row in disc.tradable_crypto(400):
            base = (row.get("base") or "").upper()
            meta = json.loads(row.get("meta") or "{}")
            iid = f"COINBASE:{row['symbol']}"
            if base in STABLE or meta.get("fx_stablecoin") or iid in ROLE_FIXED:
                continue
            out.append(iid)
        return out

    def _partitions(self) -> dict[str, list[str]]:
        app = self.app
        parts: dict[str, list[str]] = {}
        disc = self._discovered()
        for role, first, last, fixed in PLAN:
            n = last - first + 1
            if fixed is not None:
                parts[role] = [i for i in fixed if i in app.sources and paper_tradable(app.book.get(i))[0]][:n]
            elif role == "crypto_trend":
                live = disc[:n]
                if app.offline:
                    live = [i for i in DEMO if i in app.sources]
                parts[role] = live
            else:
                parts[role] = disc[ROLE_COUNT["crypto_trend"]:ROLE_COUNT["crypto_trend"] + n]
        for role, ids in parts.items():                     # discovered pairs must be in the book to be traded
            for iid in ids:
                if iid not in app.sources and app.discovery is not None:
                    row = next((r for r in app.discovery.listed("COINBASE") if f"COINBASE:{r['symbol']}" == iid), None)
                    if row:
                        app.discovery.ensure_instrument(row)
        return parts

    def assign(self) -> dict:
        """Stable assignment inside each role: an agent keeps its instrument while it stays valid (always while it
        holds a position); free agents take their role's next unowned instrument."""
        with self._lock:
            parts = self._partitions()
            held = set(self.app.paper.get_positions())
            changed = 0
            owner: dict[str, str] = {}
            for a in self.agents.values():
                valid = set(parts.get(a.role, []))
                keep = [i for i in a.partition if (i in valid or i in held) and i not in owner]
                if keep != a.partition:
                    self._reassign(a, keep, "instrument no longer valid for this role" if a.partition else "")
                    changed += 1
                for i in keep:
                    owner[i] = a.agent_id
            for role, first, last, _ in PLAN:
                pool = [i for i in parts.get(role, []) if i not in owner]
                for n in range(first, last + 1):
                    a = self.agents[f"A{n:03d}"]
                    if a.partition or not pool:
                        continue
                    i = pool.pop(0)
                    owner[i] = a.agent_id
                    self._reassign(a, [i], f"assigned by the master ({ROLES[role].label})")
                    changed += 1
            self.owner = owner
            if changed:
                self.plan_version += 1
                self._save()
            return {"changed": changed, "owned": len(owner), "plan_version": self.plan_version}

    def _reassign(self, a: Agent, partition: list[str], why: str) -> None:
        a.history = (a.history + [{"ts": now_ms(), "from": a.partition, "to": partition, "why": why}])[-10:]
        a.partition = partition
        a.assignment_version += 1

    def _save(self) -> None:
        self.app.db.set_setting("master", {
            "plan_version": self.plan_version, "suspended": self.suspended, "day_stop": self.day_stop,
            "bot_of": self.bot_of, "unavailable": self.unavailable,
            "assign": {aid: {"partition": a.partition, "version": a.assignment_version}
                       for aid, a in self.agents.items() if a.partition}})

    def owner_of(self, instrument_id: str) -> Optional[str]:
        return self.owner.get(instrument_id)

    def agent_of_bot(self, bot_id: str) -> Optional[str]:
        return next((aid for aid, b in self.bot_of.items() if b == bot_id), None)

    def set_desired(self, n: int) -> dict:
        raise ValueError("the system has exactly 100 trading agents (owner's instruction)")

    # ================================================================== versions
    def versions(self, agent_id: str) -> list[dict]:
        rows = self.app.db.query("SELECT * FROM agent_versions WHERE agent_id=? ORDER BY version", (agent_id,))
        out = []
        for r in rows:
            d = dict(r)
            for k in ("params", "training", "shadow", "paper"):
                d[k] = json.loads(d[k]) if d.get(k) else None
            out.append(d)
        return out

    def active_version(self, agent_id: Optional[str]) -> Optional[dict]:
        if not agent_id:
            return None
        r = self.app.db.one("SELECT * FROM agent_versions WHERE agent_id=? AND status='active' ORDER BY version DESC "
                            "LIMIT 1", (agent_id,))
        if not r:
            return None
        d = dict(r)
        d["params"] = json.loads(d["params"] or "{}")
        d["training"] = json.loads(d["training"] or "{}")
        return d

    def _set_status(self, agent_id: str, version: int, status: str, reason: str, **extra: Any) -> None:
        sets = ", ".join(["status=?", "changed=?", "reason=?"] + [f"{k}=?" for k in extra])
        self.app.db.execute(f"UPDATE agent_versions SET {sets} WHERE agent_id=? AND version=?",
                            (status, now_ms(), reason, *[dumps(v) for v in extra.values()], agent_id, version))
        self._note(f"{agent_id} v{version}: {status} ({reason})", "warning" if status in ("rolled_back", "rejected")
                   else "info", agent=agent_id)

    def _note(self, msg: str, severity: str = "info", **data: Any) -> None:
        ev = {"ts": now_ms(), "message": msg, **data}
        self.activity = ([ev] + self.activity)[:80]
        self.app.bus.publish("master", ev, severity=severity)

    # ================================================================== training: research per candidate
    def _runs(self, agent: Agent) -> dict[str, Optional[dict]]:
        """Latest finished STANDARD intraday run of each candidate on the agent's market and bar size."""
        role = ROLES[agent.role]
        iid = agent.partition[0]
        out: dict[str, Optional[dict]] = {}
        for sid in role.candidates:
            r = self.app.db.one(
                "SELECT experiment_id, created, dataset, results FROM experiments WHERE strategy_id=? AND "
                "json_extract(dataset, '$.instrument')=? AND json_extract(dataset, '$.tf')=? AND profile='STANDARD' "
                "AND status!='RUNNING' AND json_extract(results, '$.operating_mode')='intraday' "
                "ORDER BY created DESC LIMIT 1", (sid, iid, role.tf))
            out[sid] = None if r is None else {"experiment_id": r["experiment_id"], "created": r["created"],
                                               "dataset": json.loads(r["dataset"] or "{}"),
                                               "results": json.loads(r["results"] or "{}")}
        return out

    def _trainable(self, agent: Agent) -> bool:
        """Offline, only markets with simulated (DEMO) or already stored bars can be trained; online, all can."""
        app = self.app
        if not app.offline:
            return True
        src = app.sources.get(agent.partition[0])
        if src is None:
            return False
        if src.provider == "demo":
            return True
        tf = ROLES[agent.role].tf
        return any(app.store.last_ts(src.provider, src.symbol, t) is not None for t in (tf, "15m"))

    def _training_due(self, agent: Agent) -> Optional[str]:
        if not agent.partition or not self._trainable(agent):
            return None
        if any(j["agent"] == agent.agent_id for j in self.jobs.values()):
            return None
        for sid, run in self._runs(agent).items():
            if self.unavailable.get(f"{agent.agent_id}|{sid}", 0) > now_ms():
                continue
            if run is None or now_ms() - run["created"] > RETRAIN_DAYS * DAY:
                return sid
        return None

    def _submit_training(self) -> Optional[dict]:
        """Start training jobs up to the bound (MAX_TRAINING_JOBS at once); returns the last job started."""
        app = self.app
        last = None
        for a in sorted(self.agents.values(), key=lambda x: x.agent_id):
            if len(self.jobs) >= MAX_TRAINING_JOBS:
                break
            sid = self._training_due(a)
            if sid is None:
                continue
            role = ROLES[a.role]
            try:
                j = app.submit_research(sid, a.partition[0], role.tf, "STANDARD", LOOKBACK.get(role.tf, 3000),
                                        by=f"master:{a.agent_id}")
            except ValueError as e:
                self.unavailable[f"{a.agent_id}|{sid}"] = now_ms() + DAY // 2
                self._note(f"{a.agent_id}: cannot train {sid}: {e}", "warning", agent=a.agent_id)
                continue
            self.jobs[j["job_id"]] = {"agent": a.agent_id, "sid": sid, "since": now_ms()}
            self.doing = f"training {a.agent_id} ({role.label}): {sid} on {a.partition[0]} {role.tf}"
            last = j
        return last

    def _collect_training(self) -> None:
        for jid, meta in list(self.jobs.items()):
            j = self.app.jobs.view(jid, with_result=True)
            if j is not None and j["state"] in ("queued", "running"):
                continue
            self.jobs.pop(jid)
            res = (j or {}).get("result") or {}
            if j is None or j["state"] != "done" or res.get("status") != "ok":
                # a failed job, or a finished one without a usable result (e.g. too few bars), is not retried for
                # 12 hours: without this the same candidate would be resubmitted every cycle
                err = (j or {}).get("error") or (f"result status {res.get('status')}" if j else "job lost")
                self.unavailable[f"{meta['agent']}|{meta['sid']}"] = now_ms() + DAY // 2
                self._note(f"{meta['agent']}: training {meta['sid']} failed: {err[:160]}", "warning",
                           agent=meta["agent"])
            else:
                self.metrics["trained"] += 1
            self._choose_version(self.agents[meta["agent"]])     # the other candidates may still give a version

    def _choose_version(self, agent: Agent) -> Optional[dict]:
        """When every candidate has a recent run (or cannot run), pick the one with the best VALIDATION Sharpe (never
        the test segment) and record it as a new version if it differs from the latest one."""
        if not agent.partition:
            return None
        runs = self._runs(agent)
        pending = [s for s, r in runs.items() if (r is None or now_ms() - r["created"] > RETRAIN_DAYS * DAY)
                   and self.unavailable.get(f"{agent.agent_id}|{s}", 0) <= now_ms()]
        if pending:
            return None
        ok = {s: r for s, r in runs.items() if r and r["results"].get("status") == "ok"}
        if not ok:
            return None

        def val_sharpe(r: dict) -> float:
            return float(((r["results"].get("validation") or {}).get("sharpe")) or -99)
        best_sid = max(ok, key=lambda s: val_sharpe(ok[s]))
        best = ok[best_sid]
        latest = self.app.db.one("SELECT version, experiment_id FROM agent_versions WHERE agent_id=? ORDER BY version "
                                 "DESC LIMIT 1", (agent.agent_id,))
        if latest and latest["experiment_id"] == best["experiment_id"]:
            return None
        res = best["results"]
        role = ROLES[agent.role]

        def seg(k: str) -> dict:
            m = res.get(k) or {}
            return {x: m.get(x) for x in ("sharpe", "total_return", "max_drawdown", "trades", "win_rate", "expectancy")}
        training = {
            "dataset": dict(best["dataset"], instrument=agent.partition[0], tf=role.tf),
            "objective": "maximise Sharpe net of modelled costs on TRAIN (60%); choose among candidates by "
                         "VALIDATION Sharpe (next 20%); judge once on the held-out TEST (last 20%) and walk-forward "
                         "out of sample; every research gate must pass for PAPER TEST",
            "candidates": [{"strategy_id": s, "experiment_id": (r or {}).get("experiment_id"),
                            "validation_sharpe": None if not r else (r["results"].get("validation") or {}).get("sharpe"),
                            "verdict": None if not r else r["results"].get("verdict"),
                            "status": "unavailable" if r is None else r["results"].get("status")}
                           for s, r in runs.items()],
            "chosen": best_sid, "params": res.get("params_chosen"), "train": seg("train"),
            "validation": seg("validation"), "test": seg("test"),
            "walk_forward": {k: (res.get("walk_forward") or {}).get(k) for k in ("oos_sharpe", "oos_is_ratio")},
            "dsr": (res.get("statistics") or {}).get("dsr"), "pbo": (res.get("statistics") or {}).get("pbo"),
            "verdict": res.get("verdict"), "reason_codes": res.get("reason_codes"),
            "quality": (res.get("quality") or {}).get("score"),
        }
        version = (latest["version"] + 1) if latest else 1
        active = self.active_version(agent.agent_id)
        if active and runs.get(active["strategy_id"]) and runs[active["strategy_id"]]["experiment_id"] != \
                active["experiment_id"] and runs[active["strategy_id"]]["results"].get("verdict") != "PAPER TEST":
            self.rollback(agent.agent_id, f"re-validation on newer data failed: "
                                          f"{runs[active['strategy_id']]['results'].get('verdict')}")
            active = self.active_version(agent.agent_id)
        was_rolled_back = self.app.db.one("SELECT 1 FROM agent_versions WHERE agent_id=? AND status='rolled_back'",
                                          (agent.agent_id,)) is not None
        if res.get("verdict") != "PAPER TEST":
            status, reason = "rejected", f"validation verdict {res.get('verdict')}: not allowed to trade"
            self.metrics["rejected"] += 1
        elif active is None and not was_rolled_back:
            status, reason = "active", "first validated version: trading starts in paper"
            self.metrics["promoted"] += 1
        elif active is None:
            status, reason = "shadow", ("validated, but an earlier version of this agent was rolled back: it must be "
                                        "profitable net of costs on new bars before it may trade")
        else:
            status, reason = "shadow", f"validated; must beat v{active['version']} on new bars before promotion"
        if status != "rejected":                              # an older shadow that never ran out its test is dropped
            for r in self.app.db.query("SELECT version FROM agent_versions WHERE agent_id=? AND status='shadow'",
                                       (agent.agent_id,)):
                self._set_status(agent.agent_id, r["version"], "rejected",
                                 f"replaced by v{version} before its shadow test finished")
        self.app.db.execute(
            "INSERT INTO agent_versions (agent_id, version, created, status, strategy_id, tf, params, experiment_id, "
            "training, shadow, paper, changed, reason) VALUES (?,?,?,?,?,?,?,?,?,NULL,NULL,?,?)",
            (agent.agent_id, version, now_ms(), status, best_sid, role.tf, dumps(res.get("params_chosen") or {}),
             best["experiment_id"], dumps(training), now_ms(), reason))
        self._note(f"{agent.agent_id} v{version}: {best_sid} on {agent.partition[0]} {role.tf} -> {status} ({reason})",
                   "info" if status != "rejected" else "warning", agent=agent.agent_id)
        if status == "active":
            self._lift_rollback_suspension(agent.agent_id)
            self._sync_bot(agent)
        return {"version": version, "status": status}

    def _lift_rollback_suspension(self, agent_id: str) -> None:
        """A suspension that only waited for a new valid version ends when one is promoted (other kinds stay)."""
        if (self.suspended.get(agent_id) or {}).get("kind") == "rollback":
            self.suspended.pop(agent_id)
            self._save()

    # ================================================================== shadow promotion and rollback
    def _simulate(self, strategy_id: str, params: dict, iid: str, tf: str, since: int) -> Optional[dict]:
        """Paper-simulate a version on the bars since `since` (costs and intraday rules included)."""
        from tradingai.features.registry import FeatureFrame
        from tradingai.research.engine import _bt, _signal
        from tradingai.strategies.library import specs
        sp = specs().get(strategy_id)
        if sp is None:
            return None
        bars, _ = self.app.md.bars(iid, tf, lookback=LOOKBACK.get(tf, 3000), max_age_s=600)
        if len(bars) < 300:
            return None
        inst = self.app.book.get(iid)
        market = MARKET_OF.get(inst.market_type, "crypto")
        sig = _signal(sp, bars, inst.calendar or "CRYPTO", market, params)
        r = _bt(sp, bars, sig, inst, FeatureFrame(bars, inst.calendar or "CRYPTO", market).ppy, params)
        import numpy as np
        idx = int(np.searchsorted(bars.ts, since))
        if len(bars) - idx < 24:
            return None
        eq = r.equity[max(idx - 1, 0):]
        peak = np.maximum.accumulate(eq)
        trades = [t for t in r.trades if t.entry_ts >= since]
        return {"bars": int(len(bars) - idx), "net_return": float(eq[-1] / eq[0] - 1),
                "max_drawdown": float(((peak - eq) / peak).max()), "trades": len(trades)}

    def _evolve(self) -> None:
        """Shadow promotion and rollback checks (every 10 minutes)."""
        if time.time() - self._last_evolve < 600:
            return
        self._last_evolve = time.time()
        for a in self.agents.values():
            if not a.partition:
                continue
            try:
                self._check_shadow(a)
                self._check_rollback(a)
            except Exception as e:                            # noqa: BLE001 - one agent's problem stays local
                a.errors = (a.errors + [{"ts": now_ms(), "error": f"evolve: {type(e).__name__}: {e}"}])[-10:]

    def _check_shadow(self, a: Agent) -> None:
        sh = self.app.db.one("SELECT * FROM agent_versions WHERE agent_id=? AND status='shadow' ORDER BY version DESC "
                             "LIMIT 1", (a.agent_id,))
        if not sh or now_ms() - sh["created"] < SHADOW_MIN_DAYS * DAY:
            return
        active = self.active_version(a.agent_id)
        cand = self._simulate(sh["strategy_id"], json.loads(sh["params"]), a.partition[0], sh["tf"], sh["created"])
        if cand is None:
            return
        cur = self._simulate(active["strategy_id"], active["params"], a.partition[0], active["tf"], sh["created"]) \
            if active else None
        if active is not None and cur is None:
            return                                            # cannot compare yet: try again next time
        shadow = {"candidate": cand, "active": cur, "since": sh["created"]}
        if cur is None:                                       # nothing to beat (after a rollback): must make money
            better = cand["net_return"] > 0
            vs = "no active version: needs a net gain"
        else:
            better = cand["net_return"] >= cur["net_return"] and cand["max_drawdown"] <= cur["max_drawdown"] + 0.01
            vs = f"active {cur['net_return']:+.2%}"
        if better:
            if active:
                self._set_status(a.agent_id, active["version"], "superseded", f"replaced by v{sh['version']}")
            self._set_status(a.agent_id, sh["version"], "active",
                             f"shadow {cand['net_return']:+.2%} vs {vs} on {cand['bars']} new bars", shadow=shadow)
            self.metrics["promoted"] += 1
            self._lift_rollback_suspension(a.agent_id)
            self._sync_bot(a)
        else:
            self._set_status(a.agent_id, sh["version"], "rejected",
                             f"shadow {cand['net_return']:+.2%} did not beat {vs} on {cand['bars']} new bars",
                             shadow=shadow)

    def _paper_record(self, version: dict, iid: str) -> dict:
        """Closed paper round trips of this version's strategy on this instrument since it became active."""
        rows = self.app.db.query(
            "SELECT f.side, f.qty, f.price, f.fee, f.ts FROM fills f JOIN orders o ON o.client_order_id=f.client_order_id "
            "WHERE f.environment='paper' AND f.instrument_id=? AND o.strategy_id=? AND f.ts>=? ORDER BY f.ts",
            (iid, version["strategy_id"], version["changed"]))
        mult = self.app.book.get(iid).multiplier
        pos, cash, notional, trips = Decimal(0), Decimal(0), Decimal(0), []
        for r in rows:
            q = Decimal(r["qty"]) * (1 if r["side"] == "buy" else -1)
            if pos == 0:
                cash, notional = Decimal(0), abs(q) * Decimal(r["price"]) * mult
            pos += q
            cash -= q * Decimal(r["price"]) * mult + Decimal(r["fee"])
            if pos == 0 and notional > 0:
                trips.append((cash, cash / notional))
        pnl = sum((t[0] for t in trips), Decimal(0))
        return {"trips": len(trips), "pnl": str(pnl), "mean_return": None if not trips else
                float(sum(t[1] for t in trips) / len(trips)), "returns": [float(t[1]) for t in trips]}

    def _check_rollback(self, a: Agent) -> None:
        active = self.active_version(a.agent_id)
        if not active:
            return
        rec = self._paper_record(active, a.partition[0])
        eq = self.app.paper.get_balance().equity or Decimal(0)
        why = None
        if eq > 0 and Decimal(rec["pnl"]) < -VERSION_LOSS_PCT * eq:
            why = f"lost {Decimal(rec['pnl']):,.2f} in paper (more than {VERSION_LOSS_PCT:.0%} of equity)"
        breaches = self.app.db.one("SELECT COUNT(*) AS n FROM mistakes WHERE agent_id=? AND root_cause='AGENT_LOSS_LIMIT' "
                                   "AND ts>?", (a.agent_id, max(active["changed"], now_ms() - 7 * DAY)))
        if why is None and breaches and breaches["n"] >= 2:
            why = f"breached its daily loss limit {breaches['n']} times in 7 days"
        if why is None and rec["trips"] >= 10 and rec["mean_return"] is not None:
            test = (active["training"].get("test") or {})
            exp = test.get("expectancy")
            rets = rec["returns"]
            import statistics
            se = statistics.pstdev(rets) / max(1, len(rets)) ** 0.5
            if rec["mean_return"] < 0 and (exp is None or rec["mean_return"] < float(exp) - 2 * se):
                why = (f"{rec['trips']} paper trades: mean {rec['mean_return']:+.3%} per trade, below its validated "
                       f"test result")
        self.app.db.execute("UPDATE agent_versions SET paper=? WHERE agent_id=? AND version=?",
                            (dumps(rec), a.agent_id, active["version"]))
        if why:
            self.rollback(a.agent_id, why)

    def rollback(self, agent_id: str, why: str) -> dict:
        a = self.agents[agent_id]
        active = self.active_version(agent_id)
        if not active:
            return {"rolled_back": False}
        self._set_status(agent_id, active["version"], "rolled_back", why)
        self.metrics["rolled_back"] += 1
        prev = self.app.db.one("SELECT version, strategy_id, tf FROM agent_versions WHERE agent_id=? AND "
                               "status='superseded' ORDER BY version DESC LIMIT 1", (agent_id,))
        restored = None
        still_valid = False
        if prev and a.partition:                              # restore only if its own latest test still passes
            last = self.app.db.one(
                "SELECT json_extract(results, '$.verdict') AS v FROM experiments WHERE strategy_id=? AND "
                "json_extract(dataset, '$.instrument')=? AND json_extract(dataset, '$.tf')=? AND status!='RUNNING' "
                "AND json_extract(results, '$.operating_mode')='intraday' ORDER BY created DESC LIMIT 1",
                (prev["strategy_id"], a.partition[0], prev["tf"]))
            still_valid = bool(last and last["v"] == "PAPER TEST")
        if prev and still_valid:
            self._set_status(agent_id, prev["version"], "active", f"restored after v{active['version']} was rolled back")
            restored = prev["version"]
        else:
            self.suspend(agent_id, RETRAIN_DAYS * DAY, f"v{active['version']} rolled back and no earlier valid version: "
                                                       "in cash until a new version validates", kind="rollback")
        self.app.learning.record("VERSION_UNDERPERFORMED", agent_id=agent_id, instrument_id=(a.partition or [None])[0],
                                 detail={"version": active["version"], "why": why, "restored": restored},
                                 scenario={"agent_id": agent_id, "version": active["version"]})
        for k in list(self.unavailable):                      # candidates that could not run get another try
            if k.startswith(agent_id + "|"):
                self.unavailable.pop(k)
        self._sync_bot(a)
        return {"rolled_back": True, "restored": restored}

    # ================================================================== permissions, budgets, loss limits
    def suspend(self, agent_id: str, ms: int, why: str, kind: str = "safety") -> None:
        old = self.suspended.get(agent_id)
        until = now_ms() + int(ms)
        if old and old["until"] > now_ms() and old.get("kind", "safety") == "safety":
            # a running safety suspension is never shortened, and a promotion cannot lift it
            until, kind = max(until, old["until"]), "safety"
        self.suspended[agent_id] = {"until": until, "why": why, "kind": kind}
        self._save()
        self.app.audit("master", f"{agent_id} entries suspended: {why}", severity="warning")
        self._note(f"{agent_id} suspended: {why}", "warning", agent=agent_id)

    def permission(self, agent_id: Optional[str]) -> tuple[bool, str]:
        if not agent_id or agent_id not in self.agents:
            return False, "no owning trading agent"
        a = self.agents[agent_id]
        if not a.partition:
            return False, "no market assigned"
        if self.app.risk.kill_switch:
            return False, "emergency stop engaged: every agent is stopped"
        ap = getattr(self.app, "autopilot", None)
        if ap is None or not ap.cfg.enabled:
            return False, "system stopped (press Start System)"
        s = self.suspended.get(agent_id)
        if s and s["until"] > now_ms():
            return False, f"suspended by the master: {s['why']}"
        if self.day_stop.get(agent_id) == datetime.now(timezone.utc).strftime("%Y-%m-%d"):
            return False, f"daily loss limit ({DAY_LOSS_PCT:.1%} of equity) reached: no entries until tomorrow (UTC)"
        v = self.active_version(agent_id)
        if v is None:
            return False, "no validated version yet: the agent stays in cash while it trains"
        return True, f"v{v['version']} validated ({v['experiment_id']})"

    def _qualified_instruments(self) -> set[str]:
        t, cached = self._budget_cache
        if time.time() - t < 5:
            return cached
        out = {a.partition[0] for a in self.agents.values() if a.partition and self.permission(a.agent_id)[0]}
        self._budget_cache = (time.time(), out)
        return out

    def budget(self, agent_id: Optional[str]) -> Decimal:
        if not agent_id or agent_id not in self.agents:
            return Decimal(0)
        q = self._qualified_instruments()
        mine = [i for i in self.agents[agent_id].partition if i in q]
        if not mine:
            return Decimal(0)
        eq = self.app.paper.get_balance().equity or Decimal(0)
        lim = self.app.risk.limits
        share = eq * Decimal(str(lim.max_gross_exposure)) / Decimal(max(1, len(q)))
        return min(share, eq * Decimal(str(lim.max_position_pct_equity)))

    def _day_pnl(self, iid: str) -> Decimal:
        start = int(datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).timestamp() * 1000)
        mult = self.app.book.get(iid).multiplier
        rows = self.app.db.query("SELECT side, qty, price, fee FROM fills WHERE environment='paper' AND instrument_id=? "
                                 "AND ts>=?", (iid, start))
        cash = sum((-(Decimal(r["qty"]) * (1 if r["side"] == "buy" else -1)) * Decimal(r["price"]) * mult -
                    Decimal(r["fee"]) for r in rows), Decimal(0))
        net_qty = sum((Decimal(r["qty"]) * (1 if r["side"] == "buy" else -1) for r in rows), Decimal(0))
        if net_qty:
            q = self.app.quote(iid)
            if q is None:
                return Decimal(0)
            cash += net_qty * Decimal(str(q["price"])) * mult
        return cash

    def _loss_limits(self) -> None:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        eq = self.app.paper.get_balance().equity or Decimal(0)
        traded = {r["instrument_id"] for r in self.app.db.query(
            "SELECT DISTINCT instrument_id FROM fills WHERE environment='paper' AND ts>?", (now_ms() - DAY,))}
        for iid in traded:
            aid = self.owner.get(iid)
            if not aid or self.day_stop.get(aid) == today or eq <= 0:
                continue
            pnl = self._day_pnl(iid)
            if pnl < -DAY_LOSS_PCT * eq:
                self.day_stop[aid] = today
                self._save()
                self.app.learning.record("AGENT_LOSS_LIMIT", agent_id=aid, instrument_id=iid,
                                         detail={"day_pnl": str(pnl), "limit": str(-DAY_LOSS_PCT * eq)},
                                         scenario={"agent_day_stopped": True, "qty": "1"})

    # ================================================================== the agent's execution loop (its bot)
    def _sync_bot(self, a: Agent) -> None:
        app = self.app
        v = self.active_version(a.agent_id)
        bid = self.bot_of.get(a.agent_id)
        bot = app.bots.get(bid) if bid else None
        iid = a.partition[0] if a.partition else None
        held = bool(iid and app.paper.get_positions().get(iid))
        if v is None or iid is None:
            if bot is not None and not held:
                app.bots.pop(bot.bot_id, None)
                self.bot_of.pop(a.agent_id, None)
                app._save_bots()
            return
        if bot is None or bot.instrument_id != iid:
            try:
                b = app.create_bot(iid, v["tf"], v["strategy_id"], "strategy", "conservative", 10, managed_by="master",
                                   tier="qualified", experiment_id=v["experiment_id"],
                                   note=f"{a.agent_id} v{v['version']} ({ROLES[a.role].label})")
            except ValueError as e:
                a.errors = (a.errors + [{"ts": now_ms(), "error": f"bot: {e}"}])[-10:]
                return
            app.bots[b["bot_id"]].params = dict(v["params"] or {})
            app.bots[b["bot_id"]].agent_id = a.agent_id
            self.bot_of[a.agent_id] = b["bot_id"]
            if app.autopilot.cfg.enabled and not app.risk.kill_switch:
                app.bot_action(b["bot_id"], "start", by="master")
            app._save_bots()
            self._save()
            return
        if (bot.strategy_id, bot.tf, bot.params) != (v["strategy_id"], v["tf"], dict(v["params"] or {})) and not held:
            bot.strategy_id, bot.tf, bot.params = v["strategy_id"], v["tf"], dict(v["params"] or {})
            bot.experiment_id, bot.note = v["experiment_id"], f"{a.agent_id} v{v['version']} ({ROLES[a.role].label})"
            bot.last_bar_ts = None
            app._save_bots()

    def _sync_bots(self) -> None:
        for a in self.agents.values():
            self._sync_bot(a)
        mine = set(self.bot_of.values())
        held = set(self.app.paper.get_positions())
        for b in list(self.app.bots.values()):               # bots from older releases: removed once flat
            if b.bot_id not in mine and b.instrument_id not in held:
                self.app.bots.pop(b.bot_id, None)
                self.app._save_bots()
                self._note(f"removed legacy bot {b.bot_id} ({b.strategy_id} on {b.instrument_id}): the 100 agents "
                           "replace all earlier bots")

    # ================================================================== the master's work cycle
    def operate(self) -> dict:
        """Called by the system loop every ~10 s while the system runs (paper only)."""
        app = self.app
        with self._lock:
            self.metrics["operate_cycles"] += 1
            if app.mode == "live":
                self.doing = "paused: LIVE mode is not run by the master (paper only)"
                return {"skipped": "live"}
            self._collect_training()
            sub = self._submit_training()
            self._evolve()
            self._loss_limits()
            app.learning.tick()
            self._sync_bots()
            if sub is None and not self.jobs:
                done = sum(1 for a in self.agents.values() if a.partition and self._training_due(a) is None)
                act = sum(1 for a in self.agents.values() if self.active_version(a.agent_id))
                self.doing = (f"monitoring: {done} agents trained and current, {act} with a validated version "
                              "trading in paper")
            self._save()
            return {"submitted": bool(sub), "jobs": len(self.jobs)}

    # ================================================================== monitoring jobs (one per agent)
    def _job(self, a: Agent) -> None:
        t0 = time.perf_counter()
        app = self.app
        try:
            if not a.partition:
                a.fresh = False
                a.runtime, a.job = "blocked", "idle"
                a.detail = ("market discovery is offline: no liquid pair to assign" if ROLES[a.role].market == "crypto"
                            else "no tradable instrument available for this role")
                a.next_action = "waits for the master to assign a market"
                return
            iid = a.partition[0]
            inst = app.book.get(iid)
            disc = getattr(app, "discovery", None)
            snap = disc.quote(iid) if disc is not None else None
            if snap is not None and disc.fresh(snap):
                a.consumed_version, a.last_input_ts, a.last_price = disc.version, snap["received"], str(snap["last"])
            elif time.time() - a.data_at > DATA_SECONDS:
                a.data_at = time.time()
                q = app.quote(iid)
                if q:
                    a.last_input_ts, a.last_price = q["ts"], str(q["price"])
            data_ok = a.last_input_ts is not None and now_ms() - a.last_input_ts < (DATA_SECONDS * 2 + 120) * 1000
            a.fresh = data_ok
            open_ = inst.market_type.name == "CRYPTO_SPOT" or session(inst.calendar or "CRYPTO", now_ms())["open"]
            v = self.active_version(a.agent_id)
            a.eligible = [v["strategy_id"]] if v else []
            perm, why = self.permission(a.agent_id)
            pos = app.paper.get_positions().get(iid)
            training = next((j for j in self.jobs.values() if j["agent"] == a.agent_id), None)
            a.runtime = "available" if data_ok or not open_ else "degraded"
            if pos:
                a.job, a.detail = "managing position", f"holds {pos} {inst.symbol}"
            elif training:
                a.job, a.detail = "training", f"research on {training['sid']}"
            elif v and perm:
                a.job, a.detail = "running strategy", f"v{v['version']} {v['strategy_id']} ({v['tf']}, paper)"
            elif v is None and not self._trainable(a):
                a.job, a.detail = "waiting for data", "offline: no stored history for this market, so it cannot train"
            elif not open_:
                a.job, a.detail = "market closed", f"{inst.calendar} session closed; monitoring continues"
            elif not data_ok:
                a.job, a.detail = "waiting for data", "no fresh quote yet for " + inst.symbol
            elif v is None:
                a.job, a.detail = "in cash: no validated version", why
            else:
                a.job, a.detail = "entries paused", why
            a.next_action = (f"next check in {JOB_SECONDS}s" if open_ else "re-checks when the session opens")
        except Exception as e:                                # noqa: BLE001 - isolated
            a.runtime, a.job = "degraded", "failed"
            a.errors = (a.errors + [{"ts": now_ms(), "error": f"{type(e).__name__}: {e}"}])[-10:]
            a.detail = f"{type(e).__name__}: {e}"
        finally:
            a.heartbeat = now_ms()
            a.job_ms = round((time.perf_counter() - t0) * 1000, 1)

    def cycle(self) -> dict:
        t0 = time.perf_counter()
        futs = [self._pool.submit(self._job, a) for a in list(self.agents.values())]
        self.metrics["queue_depth"] = len(futs)
        done, pending = wait(futs, timeout=JOB_SECONDS * 3)
        self.metrics["missed_deadlines"] += len(pending)
        self.metrics["cycles"] += 1
        self.metrics["last_cycle_ms"] = round((time.perf_counter() - t0) * 1000, 1)
        self.metrics["last_cycle"] = now_ms()
        self.metrics["queue_depth"] = len(pending)
        return {"agents": len(futs), "done": len(done), "late": len(pending)}

    def run_bots(self, bots: list, fn: Callable) -> list:
        """Run each agent's bot decision inside that agent's job, concurrently per agent; errors stay local."""
        by_agent: dict[str, list] = {}
        for b in bots:
            by_agent.setdefault(self.agent_of_bot(b.bot_id) or self.owner.get(b.instrument_id) or "MASTER", []).append(b)

        def agent_work(aid: str, items: list) -> list:
            out = []
            for b in items:
                try:
                    r = fn(b)
                except Exception as e:                        # noqa: BLE001
                    if aid in self.agents:
                        ag = self.agents[aid]
                        ag.errors = (ag.errors + [{"ts": now_ms(), "error": f"{b.bot_id}: {type(e).__name__}: {e}"}])[-10:]
                    self.app.bus.publish("agent.error", {"agent": aid, "bot": b.bot_id, "error": str(e)},
                                         severity="warning")
                    r = None
                if r:
                    out.append(r)
            return out
        futs = [self._pool.submit(agent_work, aid, items) for aid, items in by_agent.items()]
        results: list = []
        for f in futs:
            results.extend(f.result(timeout=120))
        return results

    def start(self) -> None:
        if self._thread is None:
            self._thread = threading.Thread(target=self._run, name="master", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        for a in self.agents.values():
            a.runtime = "stopped"
        self._pool.shutdown(wait=False, cancel_futures=True)

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self.cycle()
            except Exception as e:                            # noqa: BLE001
                self.app.bus.publish("system.error", {"error": f"master: {type(e).__name__}: {e}"}, severity="error")
            self._stop.wait(JOB_SECONDS)

    # ================================================================== views
    def counts(self) -> dict:
        ags = list(self.agents.values())
        held = set(self.app.paper.get_positions())
        act = {r["agent_id"] for r in self.app.db.query("SELECT agent_id FROM agent_versions WHERE status='active'")}
        trained = {r["agent_id"] for r in self.app.db.query("SELECT DISTINCT agent_id FROM agent_versions")}
        perm = sum(1 for a in ags if a.agent_id in act and self.permission(a.agent_id)[0])
        return {"target": TARGET, "configured": TARGET, "registered": len(ags),
                "assigned": sum(1 for a in ags if a.partition),
                "running": sum(1 for a in ags if a.runtime in ("available", "degraded")),
                "data_ready": sum(1 for a in ags if a.fresh and a.partition),
                "market_closed": sum(1 for a in ags if a.job == "market closed"),
                "trained": len(trained), "validated": len(act), "execution_eligible": perm,
                "training_jobs": len(self.jobs), "current_jobs": self.metrics["queue_depth"],
                "with_positions": sum(1 for a in ags if any(i in held for i in a.partition)),
                "suspended": sum(1 for v in self.suspended.values() if v["until"] > now_ms()),
                "blocked": sum(1 for a in ags if not a.partition)}

    def history(self) -> dict:
        """Lifetime counts from the database (they survive restarts, unlike the in-memory cycle metrics)."""
        st = {r["status"]: r["n"] for r in self.app.db.query(
            "SELECT status, COUNT(*) AS n FROM agent_versions GROUP BY status")}
        runs = self.app.db.one("SELECT COUNT(*) AS n FROM experiments WHERE profile='STANDARD' AND status!='RUNNING' "
                               "AND json_extract(results, '$.operating_mode')='intraday'")
        return {"trained_runs": int(runs["n"] if runs else 0),
                "promoted": sum(st.get(k, 0) for k in ("active", "superseded", "rolled_back")),
                "rolled_back": st.get("rolled_back", 0), "rejected": st.get("rejected", 0),
                "shadow": st.get("shadow", 0), "versions": sum(st.values())}

    def _groups(self) -> list[dict]:
        out = []
        act = {r["agent_id"] for r in self.app.db.query("SELECT agent_id FROM agent_versions WHERE status='active'")}
        for role, first, last, _ in PLAN:
            ags = [self.agents[f"A{n:03d}"] for n in range(first, last + 1)]
            jobs: dict[str, int] = {}
            for a in ags:
                jobs[a.job] = jobs.get(a.job, 0) + 1
            r = ROLES[role]
            out.append({"group": role, "label": r.label, "family": r.family, "tf": r.tf, "markets": [r.market],
                        "candidates": list(r.candidates), "why": r.why, "ids": f"A{first:03d}-A{last:03d}",
                        "target": len(ags), "assigned": sum(1 for a in ags if a.partition),
                        "ready": sum(1 for a in ags if a.fresh and a.partition),
                        "validated": sum(1 for a in ags if a.agent_id in act),
                        "degraded": sum(1 for a in ags if a.runtime == "degraded"),
                        "gap": None if all(a.partition for a in ags) else
                        ("market discovery offline" if r.market == "crypto" else "instrument unavailable"),
                        "reassigned": 0, "jobs": jobs,
                        "heartbeat": max((a.heartbeat or 0 for a in ags), default=0) or None})
        return out

    def _brain(self) -> dict:
        disc = getattr(self.app, "discovery", None)
        c = self.counts()
        return {"name": "Master system agent", "kind": "coordinating service (not counted as a trader)",
                "plan_version": self.plan_version, "owned_instruments": len(self.owner),
                "market_state_version": disc.version if disc else None,
                "model": "no cloud AI connected: agents are deterministic code; 0 model calls",
                "metrics": dict(self.metrics), "history": self.history(), "doing": self.doing,
                "controls": ["strategy assignment", "training and validation", "version promotion and rollback",
                             "capital allocation", "portfolio risk (through the risk service)", "execution permissions",
                             "monitoring", "emergency shutdown"],
                "plan": (f"{c['assigned']} of {TARGET} agents hold a distinct market; {c['validated']} have a validated "
                         f"version and {c['execution_eligible']} may open paper trades now")}

    def market_map(self) -> dict:
        t = now_ms()
        sessions = {}
        for cal, label in (("XNYS", "US stocks (NYSE)"), ("CME", "CME futures"), ("FX", "Forex")):
            s = session(cal, t)
            sessions[cal] = {"label": label, "open": s["open"], "session": s.get("session"), "note": s.get("note")}
        sessions["CRYPTO"] = {"label": "Crypto", "open": True, "session": "24/7", "note": "trades continuously"}
        disc = getattr(self.app, "discovery", None)
        venues, uncovered = {}, []
        if disc is not None:
            cov = disc.coverage()
            venues, uncovered = cov["venues"], cov["uncovered"]
        return {"sessions": sessions, "venues": venues, "uncovered": uncovered, "offline": self.app.offline}

    def summary(self) -> dict:
        return {"brain": self._brain(), "counts": self.counts(), "groups": self._groups()}

    def _per_instrument(self) -> dict[str, dict]:
        app, out = self.app, {}

        def row(iid: str) -> dict:
            return out.setdefault(iid, {"strategies": [], "position": None, "unrealized": None, "realized": None,
                                        "fees": None, "open_orders": 0, "last_decision": None})
        for b in app.bots.values():
            if b.state == "running" and b.kind != "portfolio":
                row(b.instrument_id)["strategies"].append(b.strategy_id)
        for p in app.paper.positions_detail():
            r = row(p["instrument_id"])
            r["position"], r["unrealized"] = p["qty"], p["unrealized"]
        acct = app.paper.account_id
        for r in app.db.query("SELECT instrument_id, realized FROM positions WHERE account_id=?", (acct,)):
            row(r["instrument_id"])["realized"] = r["realized"]
        for r in app.db.query("SELECT instrument_id, SUM(CAST(fee AS REAL)) AS fees FROM fills WHERE account_id=? "
                              "GROUP BY instrument_id", (acct,)):
            row(r["instrument_id"])["fees"] = f"{r['fees']:.2f}"
        for o in app.paper.get_open_orders():
            row(o.instrument_id)["open_orders"] += 1
        for r in app.db.query("SELECT instrument_id, MAX(ts) AS ts, outcome, reason FROM decisions GROUP BY "
                              "instrument_id"):
            row(r["instrument_id"])["last_decision"] = {"ts": r["ts"], "outcome": r["outcome"],
                                                        "reason": (r["reason"] or "")[:160]}
        return out

    def view(self) -> dict:
        per = self._per_instrument()
        vers = {r["agent_id"]: dict(r) for r in self.app.db.query(
            "SELECT agent_id, version, strategy_id, status FROM agent_versions WHERE status='active'")}
        nver = {r["agent_id"]: r["n"] for r in self.app.db.query(
            "SELECT agent_id, COUNT(*) AS n FROM agent_versions GROUP BY agent_id")}
        mis = {r["agent_id"]: r["n"] for r in self.app.db.query(
            "SELECT agent_id, COUNT(*) AS n FROM mistakes WHERE agent_id IS NOT NULL GROUP BY agent_id")}
        cards = []
        disc = getattr(self.app, "discovery", None)
        for a in sorted(self.agents.values(), key=lambda x: x.agent_id):
            c = a.compact()
            iid = a.partition[0] if a.partition else None
            c.update(per.get(iid, {}) if iid else {})
            c["venue"] = iid.split(":", 1)[0] if iid else None
            c["market"] = MARKET_OF.get(self.app.book.get(iid).market_type) if iid else None
            c["meme"] = bool(iid and disc is not None and c["market"] == "crypto" and
                             disc.meme_tags(self.app.book.get(iid).base_asset))
            c["budget"] = str(self.budget(a.agent_id).quantize(Decimal("0.01")))
            perm, why = self.permission(a.agent_id)
            c["permission"], c["permission_reason"] = perm, why
            av = vers.get(a.agent_id)
            c["version"] = None if not av else {"version": av["version"], "strategy_id": av["strategy_id"]}
            c["versions"] = nver.get(a.agent_id, 0)
            c["mistakes"] = mis.get(a.agent_id, 0)
            c["next_action"] = a.next_action
            cards.append(c)
        return {"brain": self._brain(), "counts": self.counts(), "groups": self._groups(), "agents": cards,
                "market_map": self.market_map(), "learning": self.app.learning.metrics(),
                "activity": self.activity[:30]}

    def detail(self, agent_id: str) -> dict:
        a = self.agents.get(agent_id)
        if a is None:
            raise KeyError(agent_id)
        app = self.app
        iid = a.partition[0] if a.partition else None
        decisions = app.db.query("SELECT ts, outcome, reason, strategy_id, tf, bot_id FROM decisions WHERE "
                                 "instrument_id=? ORDER BY ts DESC LIMIT 10", (iid,)) if iid else []
        pos = app.paper.positions_detail() if iid else []
        orders = [o for o in app.paper.get_open_orders() if getattr(o, "instrument_id", None) == iid] if iid else []
        market = MARKET_OF.get(app.book.get(iid).market_type) if iid else None
        mistakes = [dict(r, detail=json.loads(r["detail"])) for r in app.db.query(
            "SELECT * FROM mistakes WHERE agent_id=? ORDER BY ts DESC LIMIT 20", (agent_id,))]
        r = ROLES[a.role]
        src = app.sources.get(iid) if iid else None
        perm, why = self.permission(agent_id)
        catalog = {"eligible": a.eligible, "implemented_for_market": list(r.candidates), "blocked": [],
                   "unimplemented": []}
        return dict(a.compact(), errors=a.errors, history=a.history, next_action=a.next_action,
                    budget=str(self.budget(agent_id)), market=market, decisions=decisions,
                    positions=[p for p in pos if p.get("instrument_id") == iid], open_orders=len(orders),
                    role={"id": r.role, "label": r.label, "family": r.family, "tf": r.tf,
                          "candidates": list(r.candidates), "why": r.why},
                    versions=self.versions(agent_id), permission=perm, permission_reason=why,
                    suspended=self.suspended.get(agent_id), day_stopped=self.day_stop.get(agent_id),
                    mistakes=mistakes, catalog=catalog,
                    dependencies={"data": f"{src.provider} ({src.note})" if src else None,
                                  "calendar": app.book.get(iid).calendar if iid else None,
                                  "shared snapshot": bool(getattr(app, "discovery", None) and
                                                          app.discovery.quote(iid or ""))},
                    tools=["read its market's bars and the shared snapshot", "propose orders for its own instrument "
                           "only, through the learned safeguards and the risk service (one order authority)",
                           "no credential access, no risk-limit changes, no code changes, no live trading"])


ROLE_FIXED = {i for _, _, _, fixed in PLAN if fixed for i in fixed}
ROLE_COUNT = {role: last - first + 1 for role, first, last, _ in PLAN}
