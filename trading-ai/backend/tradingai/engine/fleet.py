"""The trading fleet A001-A320 and the Supercomputer Brain that coordinates it (owner's specification, revision 13,
sections 3 and 4).

What is real here, and what the counts mean:

* The brain is one coordinating service (counted separately). It builds the list of DISTINCT market partitions from
  the instruments this installation can actually observe: the curated instruments, plus discovered Coinbase USD pairs
  for the crypto group (most liquid first). One partition = one instrument, owned by exactly one agent (an ownership
  lease with a version); it never hands the same instrument to two agents.
* Each agent A001... has a coverage group from the specification's table, a stable id, its partition, a runtime
  state, a job state, the market-state version it last consumed, a heartbeat, a virtual budget and its own error log.
  Agents without a distinct partition are BLOCKED with the reason: they are configured identities, not traders.
* Agent jobs run concurrently in a bounded worker pool with fault isolation: a slow or failing agent does not stop
  the others. Bot decisions run inside their owning agent's job; orders still pass one order authority per account
  (the OMS) and the deterministic risk service, which reserves capital atomically.
* Budgets: authorized capital (equity x the gross-exposure limit) is shared only among agents whose instrument has a
  QUALIFIED strategy, each capped at the per-position limit; every other agent's budget is zero. While nothing
  qualifies, no agent can open exposure.
* No agent is a language model and none makes a model call: there is no cloud AI connected.
"""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from decimal import Decimal
from typing import TYPE_CHECKING, Callable, Optional

from tradingai.market.calendars import session
from tradingai.market.universe import paper_tradable
from tradingai.storage.db import now_ms
from tradingai.strategies.library import MARKET_OF

if TYPE_CHECKING:
    from tradingai.app import App

TARGET = 320
# group, first id, last id, markets served, label (specification revision 13, section 4 table)
GROUPS = [
    ("equities", 1, 96, ("stock", "etf"), "Global stocks, ETFs and listed equity exposures"),
    ("crypto", 97, 224, ("crypto",), "Crypto, including every supported meme-coin category"),
    ("fx", 225, 256, ("fx",), "Foreign exchange"),
    ("futures", 257, 288, ("future",), "Commodity and index futures"),
    ("options", 289, 304, (), "Listed options and volatility products"),
    ("rates", 305, 312, (), "Rates, bonds and credit-related instruments"),
    ("specialty", 313, 320, (), "Supported specialty markets and overflow coverage"),
]
GAP = {
    "equities": "no exchange listing feed: only the curated stocks and ETFs are observable",
    "crypto": "no further execution-eligible pairs observable (discovery offline or exhausted)",
    "fx": "only five reference FX pairs are observable",
    "futures": "only the provider's continuous futures series are observable",
    "options": "PRODUCT_UNSUPPORTED: no option chains or option-order adapter",
    "rates": "PRODUCT_UNSUPPORTED: no bond, swap or rate-futures data",
    "specialty": "PRODUCT_UNSUPPORTED: no power, emissions, weather or freight products",
    "overflow": "no unowned eligible partition left anywhere",
}
NO_ACCESS = ("options", "rates", "specialty", "overflow")   # groups with no observable market of their own
JOB_SECONDS = 10
DATA_SECONDS = 300                     # non-crypto agents refresh their own instrument's bars this often
WORKERS = 8


@dataclass
class Agent:
    agent_id: str
    group: str
    partition: list[str] = field(default_factory=list)
    assignment_version: int = 0
    runtime: str = "starting"          # starting | available | degraded | blocked | stopped
    job: str = "idle"                  # waiting for data | waiting for an eligible strategy | running strategy |
    detail: str = ""                   # managing position | market closed | idle | failed
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

    def compact(self) -> dict:
        return {"id": self.agent_id, "group": self.group, "partition": self.partition, "runtime": self.runtime,
                "job": self.job, "detail": self.detail, "consumed_version": self.consumed_version,
                "last_input_ts": self.last_input_ts, "last_price": self.last_price, "heartbeat": self.heartbeat,
                "job_ms": self.job_ms, "eligible": len(self.eligible), "errors": len(self.errors), "fresh": self.fresh,
                "assignment_version": self.assignment_version}


class Fleet:
    def __init__(self, app: "App"):
        self.app = app
        saved = app.db.get_setting("fleet") or {}
        self.desired = int(saved.get("desired", TARGET))
        self.plan_version = int(saved.get("plan_version", 0))
        self.agents: dict[str, Agent] = {}
        for gid, first, last, _, _ in GROUPS:
            for n in range(first, last + 1):
                self.agents[f"A{n:03d}"] = Agent(f"A{n:03d}", gid)
        for n in range(TARGET + 1, max(self.desired, TARGET) + 1):
            self.agents[f"A{n:03d}"] = Agent(f"A{n:03d}", "overflow")
        for aid, a in list(self.agents.items()):
            if int(aid[1:]) > self.desired:
                del self.agents[aid]
        for aid, s in (saved.get("assign") or {}).items():
            if aid in self.agents:
                self.agents[aid].partition = list(s.get("partition") or [])
                self.agents[aid].assignment_version = int(s.get("version", 0))
        self.owner: dict[str, str] = {}
        self._lock = threading.RLock()
        self._pool = ThreadPoolExecutor(max_workers=WORKERS, thread_name_prefix="agent")
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self.metrics = {"cycles": 0, "last_cycle_ms": None, "missed_deadlines": 0, "last_cycle": None,
                        "queue_depth": 0}
        self._budget_cache: tuple[float, set[str]] = (0.0, set())
        self.assign()

    # ------------------------------------------------------------------ the brain: partitions and ownership
    def _partitions(self) -> dict[str, list[str]]:
        app = self.app
        by_group: dict[str, list[str]] = {g[0]: [] for g in GROUPS}
        for iid, src in app.sources.items():
            if src.provider == "demo" and not app.offline:
                continue
            inst = app.book.get(iid)
            if not inst.tradable:                             # an index is a reference, never traded
                continue
            m = MARKET_OF.get(inst.market_type)
            for gid, _, _, markets, _ in GROUPS:
                if m in markets:
                    by_group[gid].append(iid)
        disc = getattr(app, "discovery", None)
        if disc is not None and not app.offline:
            # crypto agents, plus agents of groups this installation cannot serve (they are reassigned, gap kept)
            cap = sum(1 for a in self.agents.values() if a.group in ("crypto",) + NO_ACCESS)
            for row in disc.tradable_crypto(cap + 40):
                if len(by_group["crypto"]) >= cap:
                    break
                iid = f"COINBASE:{row['symbol']}"
                if iid not in by_group["crypto"]:
                    by_group["crypto"].append(disc.ensure_instrument(row))
        return by_group

    def assign(self) -> dict:
        """Stable assignment: an agent keeps its instrument while it stays observable (and always while it holds a
        position); free agents take unowned partitions of their own group, then overflow agents take any left."""
        with self._lock:
            parts = self._partitions()
            valid = {i for v in parts.values() for i in v}
            held = set(self.app.paper.get_positions())
            changed = 0
            owner: dict[str, str] = {}
            for a in self.agents.values():
                keep = [i for i in a.partition if (i in valid or i in held) and i not in owner]
                if keep != a.partition:
                    self._reassign(a, keep, "partition no longer observable" if a.partition else "")
                    changed += 1
                for i in keep:
                    owner[i] = a.agent_id
            for gid in [g[0] for g in GROUPS]:                # first pass: each group's own markets
                pool = [i for i in parts.get(gid, []) if i not in owner]
                for a in (x for x in self.agents.values() if x.group == gid and not x.partition):
                    if not pool:
                        break
                    i = pool.pop(0)
                    owner[i] = a.agent_id
                    self._reassign(a, [i], "assigned by the brain")
                    changed += 1
            leftover = [i for v in parts.values() for i in v if i not in owner]
            for a in (x for x in self.agents.values() if x.group in NO_ACCESS and not x.partition):
                if not leftover:                              # second pass: idle groups reassigned, gap kept
                    break
                i = leftover.pop(0)
                owner[i] = a.agent_id
                self._reassign(a, [i], f"reassigned: {a.group} coverage gap retained ({GAP[a.group]})")
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
        self.app.db.set_setting("fleet", {"desired": self.desired, "plan_version": self.plan_version,
                                          "assign": {aid: {"partition": a.partition, "version": a.assignment_version}
                                                     for aid, a in self.agents.items() if a.partition}})

    def owner_of(self, instrument_id: str) -> Optional[str]:
        return self.owner.get(instrument_id)

    def set_desired(self, n: int) -> dict:
        """Change the configured fleet size. Agents holding a position are never removed (drain first)."""
        n = max(1, min(1000, int(n)))
        held = set(self.app.paper.get_positions())
        with self._lock:
            for aid in [a for a in self.agents if int(a[1:]) > n]:
                if any(i in held for i in self.agents[aid].partition):
                    raise ValueError(f"{aid} still holds a position: it must be drained before the fleet shrinks")
            for aid in [a for a in self.agents if int(a[1:]) > n]:
                del self.agents[aid]
            for k in range(TARGET + 1, n + 1):
                self.agents.setdefault(f"A{k:03d}", Agent(f"A{k:03d}", "overflow"))
            for gid, first, last, _, _ in GROUPS:
                for k in range(first, min(last, n) + 1):
                    self.agents.setdefault(f"A{k:03d}", Agent(f"A{k:03d}", gid))
            self.desired = n
            self._save()
        self.app.audit("fleet", f"configured fleet size set to {n}")
        return self.assign()

    # ------------------------------------------------------------------ budgets (enforced by the risk service)
    def _qualified_instruments(self) -> set[str]:
        t, cached = self._budget_cache
        if time.time() - t < 5:
            return cached
        rows = self.app.db.query(
            "SELECT json_extract(dataset, '$.instrument') AS iid, strategy_id, created, "
            "json_extract(results, '$.verdict') AS v FROM experiments WHERE status!='RUNNING' ORDER BY created")
        latest: dict[tuple, str] = {}
        for r in rows:
            latest[(r["strategy_id"], r["iid"])] = r["v"]
        out = {iid for (_, iid), v in latest.items() if v == "PAPER TEST" and iid}
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
        holders = {self.owner.get(i) for i in q if self.owner.get(i)}
        share = eq * Decimal(str(lim.max_gross_exposure)) / Decimal(max(1, len(holders)))
        return min(share, eq * Decimal(str(lim.max_position_pct_equity)))

    # ------------------------------------------------------------------ agent jobs
    def _job(self, a: Agent) -> None:
        t0 = time.perf_counter()
        app = self.app
        try:
            if not a.partition:
                a.fresh = False
                a.runtime, a.job = "blocked", "idle"
                a.detail = GAP.get(a.group, "no partition")
                a.next_action = "waits for the brain to find a distinct eligible partition"
                return
            iid = a.partition[0]
            inst = app.book.get(iid)
            m = MARKET_OF.get(inst.market_type)
            disc = getattr(app, "discovery", None)
            snap = disc.quote(iid) if disc is not None else None
            if snap is not None and disc.fresh(snap):
                a.consumed_version, a.last_input_ts, a.last_price = disc.version, snap["received"], str(snap["last"])
            elif time.time() - a.data_at > DATA_SECONDS:
                a.data_at = time.time()
                q = app.quote(iid)
                if q:
                    a.last_input_ts, a.last_price = q["ts"], str(q["price"])
            fresh_ms = (DATA_SECONDS * 2 + 120) * 1000
            data_ok = a.last_input_ts is not None and now_ms() - a.last_input_ts < fresh_ms
            a.fresh = data_ok
            open_ = inst.market_type.name == "CRYPTO_SPOT" or session(inst.calendar or "CRYPTO", now_ms())["open"]
            q = self._qualified_instruments()
            a.eligible = sorted({r["strategy_id"] for r in app.db.query(
                "SELECT strategy_id, json_extract(results, '$.verdict') AS v FROM experiments WHERE "
                "json_extract(dataset, '$.instrument')=? AND status!='RUNNING'", (iid,)) if r["v"] == "PAPER TEST"}) \
                if iid in q else []
            bots = [b for b in app.bots.values() if b.instrument_id == iid and b.state == "running"]
            pos = app.paper.get_positions().get(iid)
            tradable, why_not = paper_tradable(inst)
            a.runtime = "available" if data_ok or not open_ else "degraded"
            if pos:
                a.job, a.detail = "managing position", f"holds {pos} {inst.symbol}"
            elif bots:
                a.job, a.detail = "running strategy", ", ".join(b.strategy_id for b in bots)
            elif not open_:
                a.job, a.detail = "market closed", f"{inst.calendar} session closed; monitoring continues"
            elif not data_ok:
                a.job, a.detail = "waiting for data", "no fresh quote yet for " + inst.symbol
            elif not tradable:
                a.job, a.detail = "research only", why_not
            elif a.eligible:
                a.job, a.detail = "eligible strategy", f"{len(a.eligible)} qualified; the autopilot deploys it"
            else:
                a.job, a.detail = "waiting for an eligible strategy", "no strategy has qualified on " + inst.symbol
            a.next_action = (f"next check in {JOB_SECONDS}s" if open_ else "re-checks when the session opens")
            a.detail = f"{m}: {a.detail}"
        except Exception as e:                                # noqa: BLE001 - isolated: one agent's failure is local
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
        """Run bot decisions inside their owning agents' jobs, concurrently per agent. Results keep bot order."""
        by_agent: dict[str, list] = {}
        for b in bots:
            by_agent.setdefault(self.owner.get(b.instrument_id) or "BRAIN", []).append(b)

        def agent_work(aid: str, items: list) -> list:
            out = []
            for b in items:
                try:
                    r = fn(b)
                except Exception as e:                        # noqa: BLE001 - one bot never stops its agent
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

    # ------------------------------------------------------------------ service
    def start(self) -> None:
        if self._thread is None:
            self._thread = threading.Thread(target=self._run, name="fleet", daemon=True)
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
                self.app.bus.publish("system.error", {"error": f"fleet: {type(e).__name__}: {e}"}, severity="error")
            self._stop.wait(JOB_SECONDS)

    # ------------------------------------------------------------------ views
    def counts(self) -> dict:
        ags = list(self.agents.values())
        held = set(self.app.paper.get_positions())
        return {"target": TARGET, "configured": self.desired, "registered": len(ags),
                "assigned": sum(1 for a in ags if a.partition),
                "running": sum(1 for a in ags if a.runtime in ("available", "degraded")),
                "data_ready": sum(1 for a in ags if a.fresh and a.partition),
                "market_closed": sum(1 for a in ags if a.job == "market closed"),
                "execution_eligible": sum(1 for a in ags if a.eligible),
                "current_jobs": self.metrics["queue_depth"],
                "with_positions": sum(1 for a in ags if any(i in held for i in a.partition)),
                "blocked": sum(1 for a in ags if a.runtime == "blocked")}

    def _groups(self) -> list[dict]:
        groups = []
        for gid, first, last, markets, label in GROUPS + ([("overflow", TARGET + 1, self.desired, (), "Overflow")]
                                                           if self.desired > TARGET else []):
            ags = [a for a in self.agents.values() if a.group == gid]
            jobs: dict[str, int] = {}
            for a in ags:
                jobs[a.job] = jobs.get(a.job, 0) + 1
            groups.append({"group": gid, "label": label, "ids": f"A{first:03d}-A{min(last, self.desired):03d}",
                           "target": len(ags), "assigned": sum(1 for a in ags if a.partition),
                           "ready": sum(1 for a in ags if a.fresh and a.partition),
                           "degraded": sum(1 for a in ags if a.runtime == "degraded"),
                           "gap": GAP.get(gid) if gid in NO_ACCESS or any(not a.partition for a in ags) else None,
                           "reassigned": sum(1 for a in ags if a.partition and gid in NO_ACCESS),
                           "markets": list(markets), "jobs": jobs,
                           "heartbeat": max((a.heartbeat or 0 for a in ags), default=0) or None})
        return groups

    def _brain(self) -> dict:
        disc = getattr(self.app, "discovery", None)
        return {"name": "Supercomputer Brain", "kind": "coordinating service (not counted as a trader)",
                "plan_version": self.plan_version, "owned_instruments": len(self.owner),
                "market_state_version": disc.version if disc else None,
                "model": "no cloud AI connected: agents are deterministic code; 0 model calls",
                "metrics": dict(self.metrics),
                "plan": (f"{len(self.owner)} instruments assigned to {len(self.owner)} agents; capital only "
                         f"for qualified strategies ({len(self._qualified_instruments())} instrument(s))")}

    def market_map(self) -> dict:
        """Stock, futures and FX sessions, crypto venue health and what this installation cannot observe."""
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
            for v in venues.values():
                v["errors"] = [e for k, e in cov["errors"].items()]
        return {"sessions": sessions, "venues": venues, "uncovered": uncovered, "offline": self.app.offline}

    def summary(self) -> dict:
        """The brain, counts and groups without the per-agent cards (for page 1)."""
        return {"brain": self._brain(), "counts": self.counts(), "groups": self._groups()}

    def view(self) -> dict:
        per = self._per_instrument()
        cards = []
        for a in sorted(self.agents.values(), key=lambda x: x.agent_id):
            c = a.compact()
            iid = a.partition[0] if a.partition else None
            c.update(per.get(iid, {}) if iid else {})
            c["venue"] = iid.split(":", 1)[0] if iid else None
            c["market"] = MARKET_OF.get(self.app.book.get(iid).market_type) if iid else None
            c["budget"] = str(self.budget(a.agent_id).quantize(Decimal("0.01")))
            c["next_action"] = a.next_action
            cards.append(c)
        return {"brain": self._brain(), "counts": self.counts(), "groups": self._groups(), "agents": cards,
                "market_map": self.market_map()}

    def _per_instrument(self) -> dict[str, dict]:
        """What each owned instrument is doing, read from the paper account and the decision log (one query each)."""
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
        from tradingai.research.portfolio import PORTFOLIOS
        from tradingai.strategies import catalog as C
        from tradingai.strategies.signals import GEN
        cat = {"eligible": a.eligible, "implemented_for_market": [], "blocked": [], "unimplemented": []}
        for c in C.load()["cards"]:                           # every agent reads the whole shared catalog
            m = C.implementation(c["id"])
            gen_ok = bool(market) and any(market in GEN[g].markets for g in m["generators"] if g in GEN)
            port_ok = bool(iid) and any(iid in PORTFOLIOS[p].universe for p in m["portfolio"] if p in PORTFOLIOS)
            if m["blocked"]:
                cat["blocked"].append(c["id"])
            elif gen_ok or port_ok:
                cat["implemented_for_market"].append(c["id"])
            else:
                cat["unimplemented"].append(c["id"])
        src = app.sources.get(iid) if iid else None
        return dict(a.compact(), errors=a.errors, history=a.history, next_action=a.next_action,
                    budget=str(self.budget(agent_id)), market=market,
                    decisions=decisions, positions=[p for p in pos if p.get("instrument_id") == iid],
                    open_orders=len(orders), catalog=cat,
                    dependencies={"data": f"{src.provider} ({src.note})" if src else None,
                                  "calendar": app.book.get(iid).calendar if iid else None,
                                  "shared snapshot": bool(getattr(app, "discovery", None) and
                                                          app.discovery.quote(iid or ""))},
                    tools=["read the shared catalog and research ledger", "read the shared market snapshot and bars",
                           "propose orders through the risk service (one order authority per account)",
                           "no credential access, no risk-limit changes, no code changes"])
