"""The 25 core logical roles of the owner's specification (section 4), mapped onto the components that actually do
the work in this software, with an honest implementation type and a state read from the running system.

Implementation types: "deterministic service" (plain code), "agent functions" (the rule-based agents that vote or
advise on every decision), "statistical model", or "unavailable". No role here is a language model: this build has
no cloud AI model connected, and the page says so (active model calls: 0).
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from tradingai.agents.base import AGENTS
from tradingai.storage.db import now_ms

if TYPE_CHECKING:
    from tradingai.app import App

# role id, name, implementation type, component, agent groups (for the specialist roles)
ROLES = [
    ("01", "Master coordinator", "deterministic service", "engine/autopilot.py + engine/orchestrator.py", ()),
    ("02", "Market-data supervisor", "deterministic service", "data/pipeline.py (providers, store, freshness)", ()),
    ("03", "Data-quality analyst", "agent functions", "data/quality.py + data agents D01-D10", ("data",)),
    ("04", "Regime analyst", "statistical model", "regime/detect.py (rules + 2-state HMM + CUSUM) + market agents",
     ("market",)),
    ("05", "Trend specialist", "agent functions", "technical agents (trend) + trend templates", ("technical",)),
    ("06", "Momentum specialist", "agent functions", "technical agents (momentum) + momentum templates", ("technical",)),
    ("07", "Mean-reversion specialist", "agent functions", "technical agents (reversion) + reversion templates",
     ("technical",)),
    ("08", "Breakout specialist", "agent functions", "technical agents (breakout) + breakout templates", ("technical",)),
    ("09", "Market-structure specialist", "deterministic service", "structure_break / sweep_reclaim / failed_breakout "
     "templates (catalog ST026, ST031, ST032)", ()),
    ("10", "Volume and order-flow specialist", "agent functions", "volume agents; order-book agents need a depth feed",
     ("technical",)),
    ("11", "Statistical-arbitrage specialist", "deterministic service", "pairs templates (shortable markets only)", ()),
    ("12", "Crypto specialist", "agent functions", "crypto agents (funding/OI agents need feeds)", ("crypto",)),
    ("13", "Equity specialist", "agent functions", "calendars, corporate-action agent, sessions", ("data",)),
    ("14", "FX specialist", "agent functions", "forex agents, FX sessions", ("forex",)),
    ("15", "Futures and index-products specialist", "agent functions", "futures agents, contract specs, roll windows",
     ("futures",)),
    ("16", "News and event analyst", "unavailable", "REQUIRES CONNECTION: no licensed news or economic-calendar feed", ()),
    ("17", "Strategy researcher", "deterministic service", "strategies/library.py (1,400+ templates, rule fingerprints) "
     "+ the 80-card catalog", ()),
    ("18", "Validation analyst", "statistical model", "research/engine.py + research/portfolio.py (walk-forward, "
     "Monte Carlo, deflated Sharpe, PBO)", ("research",)),
    ("19", "Portfolio allocator", "deterministic service", "engine/portfolio_bot.py + portfolio/optimize.py", ()),
    ("20", "Risk-policy analyst", "deterministic service", "risk/service.py + risk agents", ("risk",)),
    ("21", "Execution analyst", "deterministic service", "execution/oms.py + execution agents", ("execution",)),
    ("22", "Reconciliation analyst", "deterministic service", "App.reconcile (start-up and every 5 minutes)", ()),
    ("23", "Attribution analyst", "deterministic service", "engine/reports.py (by strategy, market, fees, slippage)", ()),
    ("24", "Reliability supervisor", "deterministic service", "start-up checks, /health, trading-loop watchdog", ()),
    ("25", "Voice and reporting assistant", "deterministic service", "engine/assistant.py: typed intents and "
     "templates over verified state; browser speech (no cloud AI)", ()),
]


def view(app: "App") -> dict:
    last_dec = app.db.one("SELECT ts, instrument_id, outcome, reason, regime FROM decisions ORDER BY ts DESC LIMIT 1")
    last_exp = app.db.one("SELECT created, strategy_id, json_extract(results, '$.verdict') AS v FROM experiments "
                          "WHERE status!='RUNNING' ORDER BY created DESC LIMIT 1")
    running_jobs = [j for j in app.jobs.list() if j["state"] in ("queued", "running")]
    feeds = list(app.md.status_by_series.values())
    stale = sum(1 for f in feeds if not f.get("fresh") and not f.get("simulated"))
    loop_age = None if not app.last_tick else round(time.time() - app.last_tick, 1)
    groups: dict[str, int] = {}
    for a in AGENTS.values():
        groups[a.group] = groups.get(a.group, 0) + 1
    recon = app.db.one("SELECT ts, message, severity FROM audit WHERE kind='reconcile' ORDER BY id DESC LIMIT 1")
    ap = app.autopilot.view()

    def state_of(rid: str) -> tuple[str, str, int | None]:
        if rid == "01":
            return ("running" if app.autopilot.cfg.enabled else "idle", ap["doing"], ap["last_cycle"])
        if rid == "02":
            return ("degraded" if stale else ("running" if feeds else "waiting for data"),
                    f"{len(feeds)} series, {stale} stale" + (" (offline mode)" if app.offline else ""), None)
        if rid in ("03", "04", "05", "06", "07", "08", "10", "12", "13", "14", "15"):
            if not last_dec:
                return ("idle", "no decision yet: agents run when a bot sees a new completed bar", None)
            res = f"last decision: {last_dec['instrument_id']} {last_dec['outcome']}"
            return ("completed", res, last_dec["ts"])
        if rid == "16":
            return ("blocked", "REQUIRES CONNECTION: news/economic calendar feed", None)
        if rid in ("17", "18"):
            if running_jobs:
                return ("running", running_jobs[0]["title"] + f" ({running_jobs[0]['stage']})", None)
            if last_exp:
                return ("idle", f"last result: {last_exp['strategy_id']} -> {last_exp['v']}", last_exp["created"])
            return ("idle", "no research yet", None)
        if rid == "19":
            pb = [b for b in app.bots.values() if b.kind == "portfolio"]
            return ("running" if any(b.state == "running" for b in pb) else "idle",
                    f"{len(pb)} portfolio bot(s)", None)
        if rid == "20":
            r = app.risk
            st = "blocked" if r.kill_switch or r.trading_locked else ("paused" if r.entries_paused else "running")
            c = r.counters
            return (st, f"{c['approved']} approved, {c['adjusted']} shrunk, {c['denied']} denied", None)
        if rid == "21":
            lat = app.oms.latency_stats()["decision_to_submit_ms"]
            return ("running", f"{lat['n']} orders this session, p50 {lat['p50']} ms decision-to-submit", None)
        if rid == "22":
            if not recon:
                return ("idle", "not run yet", None)
            return ("completed" if recon["severity"] == "info" else "failed", recon["message"], recon["ts"])
        if rid == "23":
            fees = app.account_view().get("fees")
            return ("running", f"fees so far {fees}", None)
        if rid == "24":
            bad = [c for c in app.checks if not c["ok"]]
            return ("degraded" if bad or (loop_age and loop_age > 30) else "running",
                    f"{len(app.checks) - len(bad)}/{len(app.checks)} start-up checks; loop {loop_age}s ago", None)
        if rid == "25":
            a = getattr(app, "assistant", None)
            return ("running" if a else "unavailable", a.status() if a else "not started", None)
        return ("idle", "", None)

    roles = []
    for rid, name, kind, comp, grp in ROLES:
        st, latest, ts = state_of(rid)
        roles.append({"id": rid, "name": name, "implementation": kind, "component": comp, "state": st,
                      "latest": latest, "latest_ts": ts, "agent_functions": sum(groups.get(g, 0) for g in grp)})
    return {"roles": roles, "counts": {"configured_roles": len(ROLES), "agent_functions": len(AGENTS),
                                       "running_jobs": len(running_jobs) + (1 if app._loop_thread else 0) +
                                       (1 if app.autopilot._thread else 0),
                                       "active_model_calls": 0},
            "queue_depth": len(running_jobs), "stale_feeds": stale, "model": "no cloud AI model connected: every role "
            "is deterministic code or a statistical model", "ts": now_ms()}
