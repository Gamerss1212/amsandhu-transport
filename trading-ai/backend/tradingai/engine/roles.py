"""The shared operational capabilities C01-C50 of the owner's specification (revision 13, section 4), mapped onto the
components that actually do the work in this software, with an honest implementation type and a state read from the
running system. Capability IDs are not trading-agent IDs and are not counted among the 100 trading agents
(engine/master.py).

Implementation types: "deterministic service" (plain code), "agent functions" (the rule-based agents that vote or
advise on every decision), "statistical model", or "unavailable". No role here is a language model: this build has
no cloud AI model connected, and the page says so (active model calls: 0).
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from tradingai.agents.base import AGENTS
from tradingai.storage.db import now_ms
from tradingai.strategies.library import specs

if TYPE_CHECKING:
    from tradingai.app import App

# role id, name, implementation type, component, agent groups (for the specialist roles)
ROLES = [
    ("01", "Master system agent / fleet coordinator", "deterministic service", "engine/master.py (assignments, "
     "training, versions, capital, permissions, monitoring, emergency stop) + engine/learning.py", ()),
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
    ("26", "Liquidity analyst", "deterministic service", "risk check 'liquidity' (order vs last bar volume) + paper fill "
     "participation cap + discovery 24-hour USD volume", ()),
    ("27", "Spread monitor", "unavailable", "REQUIRES CONNECTION: no bid/ask quote feed; costs use a modelled half-spread",
     ()),
    ("28", "Transaction-cost estimator", "deterministic service", "backtest/costs.py (fees, half-spread, slippage, "
     "impact) + measured paper slippage", ()),
    ("29", "Borrowing analyst", "unavailable", "PRODUCT_UNSUPPORTED: no short selling or borrow data (long-only spot "
     "and paper)", ()),
    ("30", "Funding analyst", "unavailable", "REQUIRES CONNECTION: no funding-rate or financing feed (spot only)", ()),
    ("31", "Event-calendar supervisor", "unavailable", "REQUIRES CONNECTION: no economic or earnings calendar feed", ()),
    ("32", "Corporate-actions analyst", "deterministic service", "provider-adjusted daily bars + delisting tracking in "
     "market discovery (no corporate-action feed)", ()),
    ("33", "Session-calendar supervisor", "deterministic service", "market/calendars.py (NYSE rules, holidays, early "
     "closes, FX and futures sessions, DST)", ()),
    ("34", "Contract-roll analyst", "deterministic service", "equity-index quarterly roll window on continuous series; "
     "other futures research-only (no contract months)", ()),
    ("35", "Correlation analyst", "deterministic service", "risk check 'correlated exposure' (clusters) + agent "
     "correlation features", ("risk",)),
    ("36", "Concentration analyst", "deterministic service", "risk limits per position and market + the concentration "
     "figure on the risk panel", ()),
    ("37", "Stress-scenario analyst", "statistical model", "research cost stress (1.5x, 2x) and Monte Carlo resampling "
     "in every full test", ()),
    ("38", "Strategy-deduplication analyst", "deterministic service", "rule fingerprints in strategies/library.py", ()),
    ("39", "Parameter-stability analyst", "statistical model", "walk-forward folds and the probability of backtest "
     "overfitting (PBO) in research/engine.py", ()),
    ("40", "Signal-calibration analyst", "statistical model", "ensemble reliability check: probabilities are shown only "
     "when calibrated and evaluated", ()),
    ("41", "Model-drift monitor", "deterministic service", "research/compare.py (paper vs backtest drift warnings) + "
     "autopilot retirement review", ()),
    ("42", "Data-drift monitor", "agent functions", "data agents (gaps, stale bars, schema) + discovery listing changes",
     ("data",)),
    ("43", "Reconciliation-anomaly investigator", "deterministic service", "App.reconcile mismatch report "
     "(RECONCILIATION_REQUIRED stops new entries)", ()),
    ("44", "Security-event monitor", "deterministic service", "local-only server guard: host check, session token, "
     "cross-site refusal; secrets in Windows DPAPI", ()),
    ("45", "Compute-and-API budget supervisor", "deterministic service", "research rate limits (screens and full tests "
     "per hour), bounded agent worker pool, provider request pacing", ()),
    ("46", "Storage-health supervisor", "deterministic service", "SQLite quick_check at start-up + backups", ()),
    ("47", "Restart-recovery coordinator", "deterministic service", "start-up checks: database, reconciliation, "
     "ownership restored from the saved fleet plan", ()),
    ("48", "Voice-intent validator", "deterministic service", "engine/assistant.py typed intents; money commands "
     "refused; command ids de-duplicated", ()),
    ("49", "Alert-priority coordinator", "deterministic service", "assistant announcements: severity, dedupe key, "
     "cooldown, expiry, quiet hours", ()),
    ("50", "Session-reporting analyst", "deterministic service", "engine/reports.py session report (trades, costs, "
     "incidents, remaining exposure)", ()),
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

    def state_of(rid: str, kind: str, comp: str) -> tuple[str, str, int | None]:
        if rid == "01":
            c = app.fleet.counts()
            return ("running" if app.fleet._thread else "idle",
                    f"{c['assigned']}/{c['registered']} agents assigned, {c['blocked']} blocked; autopilot: {ap['doing']}",
                    app.fleet.metrics["last_cycle"])
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
        if kind == "unavailable":
            return ("blocked", comp, None)
        if rid == "26":
            d = app.discovery.coverage()["venues"]["COINBASE"] if not app.offline else None
            return ("running", f"max {app.risk.limits.max_participation:.0%} of the last bar's volume per order" +
                    (f"; {d['snapshot_fresh']} Coinbase pairs with a fresh 24-hour volume" if d else ""), None)
        if rid == "28":
            lat = app.oms.latency_stats()["decision_to_submit_ms"]
            return ("running", f"fees, half-spread and slippage modelled per instrument; {lat['n']} paper order(s) "
                    "measured this session", None)
        if rid == "32":
            dl = app.db.one("SELECT COUNT(*) AS n FROM instruments_discovered WHERE delisted IS NOT NULL")
            return ("running", f"{dl['n'] if dl else 0} delisted pair(s) recorded by discovery", None)
        if rid == "33":
            from tradingai.market.calendars import session
            st = {c: session(c, now_ms()) for c in ("XNYS", "CME", "FX")}
            return ("running", "; ".join(f"{c} {v['session'] if v.get('session') else ('open' if v['open'] else 'closed')}"
                                         for c, v in st.items()), None)
        if rid in ("35", "36"):
            L = app.risk.limits
            return ("running", f"limit {L.max_correlated_pct:.0%} of equity per correlation cluster" if rid == "35" else
                    f"limit {L.max_position_pct_equity:.0%} of equity per position", None)
        if rid in ("37", "39"):
            return ("idle" if not last_exp else "completed",
                    "part of every full research test" + (f"; last: {last_exp['strategy_id']} -> {last_exp['v']}"
                                                           if last_exp else ""), last_exp["created"] if last_exp else None)
        if rid == "38":
            return ("completed", f"{len(specs())} templates fingerprinted", None)
        if rid == "40":
            return ("running", "no calibrated probability model yet: strengths are shown, not probabilities", None)
        if rid in ("41", "42"):
            n = sum(1 for until in app.autopilot.mem.get("retired", {}).values() if until > now_ms())
            return ("running", f"{stale} stale series; {n} strategy/market pair(s) retired after paper review", None)
        if rid == "43":
            st = app.state.state
            return ("blocked" if st == "RECONCILIATION_REQUIRED" else "running", f"application state {st}", None)
        if rid == "44":
            return ("running", "server answers only on 127.0.0.1; every API call needs the session token", None)
        if rid == "45":
            return ("running", f"{app.autopilot.cfg.screens_per_hour} screens/hour, {app.autopilot.cfg.confirms_per_hour}"
                    f" full tests/hour; {app.fleet.metrics['queue_depth']} agent job(s) queued", None)
        if rid in ("46", "47"):
            chk = [c for c in app.checks if c["name"] in (("database integrity", "audit chain intact") if rid == "46"
                                                          else ("recovery", "trading fleet and Supercomputer Brain"))]
            return ("running" if all(c["ok"] for c in chk) else "degraded",
                    "; ".join(f"{c['name']}: {'ok' if c['ok'] else c.get('detail')}" for c in chk) or "start-up checks",
                    None)
        if rid in ("48", "49"):
            a = getattr(app, "assistant", None)
            return ("running" if a else "unavailable", a.status() if a else "not started", None)
        if rid == "50":
            return ("running", "session report on the Live Intelligence page", None)
        return ("idle", comp, None)

    roles = []
    for rid, name, kind, comp, grp in ROLES:
        st, latest, ts = state_of(rid, kind, comp)
        roles.append({"id": "C" + rid, "name": name, "implementation": kind, "component": comp, "state": st,
                      "latest": latest, "latest_ts": ts, "agent_functions": sum(groups.get(g, 0) for g in grp)})
    return {"roles": roles, "counts": {"configured_roles": len(ROLES), "unavailable": sum(1 for r in ROLES if r[2] == "unavailable"), "agent_functions": len(AGENTS),
                                       "running_jobs": len(running_jobs) + (1 if app._loop_thread else 0) +
                                       (1 if app.autopilot._thread else 0),
                                       "active_model_calls": 0},
            "queue_depth": len(running_jobs), "stale_feeds": stale, "model": "no cloud AI model connected: every role "
            "is deterministic code or a statistical model", "ts": now_ms()}
