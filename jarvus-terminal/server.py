#!/usr/bin/env python3
"""Jarvus web server: the three-page app, its JSON API and its live event stream. Standard library only.

Pages (one app, three destinations): Command Center, Connections, Live Intelligence.

Security
* Listens on 127.0.0.1 only; the Host header must name this computer (stops DNS rebinding) and a POST's Origin, when
  a browser sends one, must be this app.
* Sign-in required (engine/auth.py): an HttpOnly, SameSite=Strict session cookie, plus a CSRF token the page sends in
  the X-CSRF-Token header on every change. Each account sees only its own workspaces.
* Credentials sent to /api/connections/create and /api/assistant/config go straight to the encrypted vault; request
  bodies are never logged, and no API response ever contains a credential.
* Strict Content-Security-Policy: scripts only from this app; no inline scripts; no third-party requests.

Everything that trades runs in the workspace's bot engine process (engine/supervisor.py); this server reads the
workspace database, forwards commands through the engine's control queue and streams the audit log (SSE).
"""

from __future__ import annotations

import csv
import io
import json
import mimetypes
import os
import sys
import threading
import time
import traceback
import urllib.parse
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config                      # noqa: E402
from engine import library         # noqa: E402  (also puts market_analysis_bots on sys.path)
from engine.auth import Auth       # noqa: E402
from engine.supervisor import Supervisor  # noqa: E402

from mab import news, stream, views  # noqa: E402
from mab.assistant import Assistant, AssistantUnavailable, BudgetExceeded  # noqa: E402
from mab.connections import PROVIDERS, Connections  # noqa: E402
from mab.deploy import DEFAULT_LIMITS  # noqa: E402
from mab.research.jobs import KINDS as JOB_KINDS, JobQueue  # noqa: E402

WEB_DIR = config.WEB_DIR
COOKIE = "jv_session"
CSP = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
       "connect-src 'self'; font-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
LIVE_ACK = "I UNDERSTAND THIS TRADES REAL MONEY"


class ApiError(Exception):
    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code


class App:
    def __init__(self, data_dir: str, start_engines: bool = True, research_workers=None):
        os.makedirs(data_dir, exist_ok=True)
        legacy = os.path.join(data_dir, "fleet")
        self.auth = Auth(os.path.join(data_dir, "app.db"), data_dir, legacy_home=legacy)
        self.sup = Supervisor(self.auth, research_workers=research_workers, start_pool=start_engines)
        self.start_engines = start_engines
        self._snap_cache = {}
        self._candle_cache = {}
        self.sse_clients = 0
        self.lock = threading.Lock()

    def boot(self):
        if self.start_engines:
            self.sup.boot()

    def st(self, wid):
        return self.sup.storage(wid)

    def conns(self, wid) -> Connections:
        c = Connections(self.st(wid), wid)
        w = self.auth.workspace(wid)
        c.ensure_defaults(demo=w["kind"] == "demo")
        return c

    def notify_connections(self, wid):
        if self.sup.running(wid):
            self.sup.command(wid, "connections_changed", {}, wait=2.0)


APP: App = None


def _now():
    return int(time.time() * 1000)


# ----------------------------------------------------------------------------- handlers (workspace API)

def fleet_json(wid, path, default=None):
    r = APP.sup.fleet_get(wid, path)
    if r is None or r[0] != 200:
        return default
    try:
        return json.loads(r[1])
    except ValueError:
        return default


def need_engine(wid):
    if not APP.sup.running(wid):
        raise ApiError(409, "the bot engine for this workspace is stopped; start it (top bar) first")


def cmd(wid, name, args=None, wait=10.0):
    need_engine(wid)
    r = APP.sup.command(wid, name, args or {}, wait=wait)
    if r.get("status") == "failed":
        raise ApiError(400, r.get("error") or "the command failed")
    if r.get("status") == "queued":
        return {"queued": True, "note": r.get("note")}
    return r.get("result")


def overview(ctx):
    wid, st = ctx["wid"], ctx["st"]
    w = APP.auth.workspace(wid)
    APP.conns(wid)                                            # the workspace's simulated account always exists
    accts = views.accounts(st)
    la = st.kv_get("live_authorization", {}) or {}
    deps = fleet_json(wid, "/api/deployments")
    if deps is None:
        from mab.deploy import Deployments
        deps = [dict(d, activity=d["state"], bot=None) for d in Deployments(st).list(active_only=True)]
    return {"workspace": {"id": wid, "kind": w["kind"], "label": w["label"], "demo": w["kind"] == "demo"},
            "engine": APP.sup.status(wid), "emergency": st.kv_get("emergency", None),
            "live_authorization": {"authorized": bool(la.get("authorized")), "connections": la.get("connections", []),
                                   "max_total_allocation": la.get("max_total_allocation"),
                                   "daily_loss_limit": la.get("daily_loss_limit"), "time": la.get("time"),
                                   "waive_eligibility": bool(la.get("waive_eligibility"))},
            "research_autopilot": autopilot_on(st), "autopilot": autopilot_on(st), "accounts": accts, "deployments": deps,
            "alerts": views.alerts(st, 24, 30), "default_limits": DEFAULT_LIMITS, "time": _now()}


def autopilot_on(st) -> bool:
    ap = st.kv_get("autopilot")
    if isinstance(ap, dict):
        return bool(ap.get("on"))
    legacy = st.kv_get("research_autopilot")
    return bool(legacy) if legacy is not None else False


def autopilot_view(ctx):
    wid, st = ctx["wid"], ctx["st"]
    eng = APP.sup.status(wid)
    d = fleet_json(wid, "/api/autopilot") if APP.sup.running(wid) else None
    if not d or d.get("on") is None:
        ap = st.kv_get("autopilot") or {}
        d = {"on": autopilot_on(st), "since": ap.get("since"), "by": ap.get("by"), "emergency": bool(st.kv_get("emergency")),
             "bots": None, "states": {}, "real_money": False, "today": {}, "research": {},
             "note": "the bot engine is stopped" + ("; it starts when autopilot is switched on" if not autopilot_on(st)
                                                    else "; autopilot resumes when it starts")}
    d["engine"] = eng
    d["autostart"] = bool((APP.auth.workspace(wid) or {}).get("autostart"))
    return d


def autopilot_switch(ctx, on: bool):
    """The one button. ON: record it (the engine reads it at start), make the engine start with the app, start the
    engine now if it is stopped, and tell a running engine. OFF: research bots stop opening trades; the engine keeps
    running so open positions are still managed. Never touches real money; refuses while EMERGENCY STOP is on."""
    wid, st, s = ctx["wid"], ctx["st"], ctx["session"]
    if on and st.kv_get("emergency"):
        raise ApiError(409, "EMERGENCY STOP is on. It was set on purpose, so autopilot will not override it: clear it "
                            "first (red banner), then press START AUTOPILOT again.")
    running = APP.sup.running(wid)
    if running:
        cmd(wid, "autopilot", {"on": on, "by": s["username"]}, wait=15)
    else:
        st.kv_set("autopilot", {"on": on, "since": _now(), "by": s["username"]})
        st.kv_set("research_autopilot", on)
        st.audit("control", f"AUTOPILOT {'ON' if on else 'OFF'} (set while the engine was stopped"
                 + ("; starting it now)" if on else ")"), stage="autopilot", severity="warning",
                 payload={"on": on, "by": s["username"]})
    started = None
    if on:
        APP.auth.set_autostart(wid, True)                   # from now on the engine starts whenever Jarvus opens
        if not running and APP.start_engines:
            try:
                started = APP.sup.start(wid)
            except RuntimeError as e:
                raise ApiError(409, str(e))
    out = autopilot_view(ctx)
    out["engine_started"] = bool(started and not started.get("already_running"))
    return out


def snapshot_for_stream(wid):
    """Small state message for the live stream (shared by every open page of the workspace, 1.5 s cache)."""
    hit = APP._snap_cache.get(wid)
    if hit and time.time() - hit[0] < 1.5:
        return hit[1]
    st = APP.st(wid)
    deps = fleet_json(wid, "/api/deployments", []) or []
    out = {"time": _now(), "engine": APP.sup.running(wid), "emergency": st.kv_get("emergency", None),
           "deployments": [{"deployment_id": d["deployment_id"], "bot_id": d["bot_id"], "state": d["state"],
                            "mode": d["mode"], "activity": d.get("activity"), "unrealized": d.get("unrealized"),
                            "equity": d.get("equity"), "position": bool(d.get("position")), "blocked": d.get("blocked"),
                            "last_decision": (d.get("bot") or {}).get("last_decision")} for d in deps],
           "accounts": [{k: a.get(k) for k in ("connection_id", "mode", "equity", "buying_power", "allocated",
                                                "realized_today", "unrealized", "exposure_pct", "daily_drawdown_pct",
                                                "as_of", "currency")} for a in views.accounts(st)]}
    APP._snap_cache[wid] = (time.time(), out)
    return out


def candles(ctx):
    q = ctx["q"]
    venue, symbol, tf = q("venue"), q("symbol"), q("tf", "5m")
    n = max(20, min(1000, int(q("n", "300"))))
    if not venue or not symbol:
        raise ApiError(400, "choose a market")
    wid = ctx["wid"]
    path = "/api/candles?" + urllib.parse.urlencode({"venue": venue, "symbol": symbol, "tf": tf, "n": n})
    d = fleet_json(wid, path)
    if d and d.get("t"):
        return d
    key = (venue, symbol, tf, n)
    hit = APP._candle_cache.get(key)
    if hit and time.time() - hit[0] < 30:
        return hit[1]
    from mab.data.adapters import ADAPTERS
    from mab.net import Http
    ad = ADAPTERS.get(venue)
    if ad is None:
        raise ApiError(400, f"unknown market source {venue}")
    try:
        b = ad(Http()).bars(symbol, tf, limit=min(n, 300))
    except Exception as e:                                              # noqa: BLE001
        return {"error": f"market data unavailable: {type(e).__name__}: {e}", "t": []}
    out = {"venue": venue, "symbol": symbol, "tf": tf, "source": getattr(b[-1], "provenance", venue) if b else venue,
           "t": [x.event_time for x in b], "o": [x.open for x in b], "h": [x.high for x in b], "l": [x.low for x in b],
           "c": [x.close for x in b], "v": [x.volume for x in b], "status": "fetched by the app (engine stopped)", "live": False}
    APP._candle_cache[key] = (time.time(), out)
    return out


def strategies(ctx):
    lib = library.library()
    rows = []
    for s in lib["strategies"]:
        if s["impl"] != "implemented":
            continue
        rows.append(s)
    return {"counts": lib["counts"], "runnable": rows,
            "note": "BACKTEST figures are measured on history after costs; none is a promise, and none passed the "
                    "correction for testing many ideas"}


def strategy_detail(ctx, sid):
    d = library.strategy(sid)
    if d.get("error"):
        raise ApiError(404, "unknown strategy")
    d["evaluation_runs"] = library.evaluation(sid)
    return d


def markets(ctx):
    m = fleet_json(ctx["wid"], "/api/markets")
    if m:
        return m
    with open(library.REGISTRY, encoding="utf-8") as fh:
        reg = json.load(fh)["bots"]
    w = APP.auth.workspace(ctx["wid"])
    if w["kind"] == "demo":
        from mab.data.demo import MARKETS
        return [{"venue": "demo", "symbol": s, "asset": "crypto", "demo": True} for s in MARKETS]
    seen, out = set(), []
    for b in reg:
        k = (b["venue"], b["instrument"])
        if k not in seen:
            seen.add(k)
            out.append({"venue": k[0], "symbol": k[1], "asset": "stock" if k[0] == "yahoo" else "crypto"})
    return sorted(out, key=lambda x: (x["asset"], x["symbol"]))


def markers(ctx):
    q = ctx["q"]
    venue, symbol = q("venue"), q("symbol")
    return views.markers(ctx["st"], f"{venue}:{symbol}", symbol)


def compare(ctx):
    ids = [x for x in (ctx["q"]("bots") or "").split(",") if x][:6]
    st = ctx["st"]
    sc = {r["bot_id"]: r for r in (fleet_json(ctx["wid"], "/api/scanner", []) or [])}
    out = []
    for bid in ids:
        info = sc.get(bid) or {}
        sid = info.get("strategy_id")
        if not sid:
            ub = st.query("SELECT * FROM user_bots WHERE bot_id=?", (bid,))
            if ub:
                info = {"strategy_id": ub[0]["strategy_id"], "symbol": ub[0]["instrument"], "venue": ub[0]["venue"],
                        "name": ub[0]["name"]}
                sid = info["strategy_id"]
        rows = views.trades(st, bot_id=bid, limit=2000)
        by_mode = {}
        for m in ("research", "paper", "demo", "live"):
            sel = [r for r in rows if (r.get("mode") or "paper") == m or (m == "research" and r.get("deployment_id") is None
                                                                          and (r.get("mode") in (None, "paper", "demo")))]
            if m != "research":
                sel = [r for r in sel if r.get("deployment_id")]
            by_mode[m] = views.stats(sel)
        slip = st.query("SELECT AVG(slippage_bps) AS s, COUNT(*) AS n FROM broker_fills WHERE bot_id=? AND slippage_bps IS NOT NULL",
                        (bid,))[0]
        out.append({"bot_id": bid, "name": info.get("name"), "strategy_id": sid, "symbol": info.get("symbol"),
                    "backtest": library.backtest_summary(sid, info.get("symbol"), info.get("venue")) if sid else None,
                    "results": by_mode, "avg_slippage_bps": slip["s"], "fills_measured": slip["n"],
                    "state": info.get("state"), "brain": info.get("brain")})
    return {"bots": out, "note": "backtest, research-paper, paper, demo and live results are measured separately and "
                                 "never combined"}


def events(ctx):
    q = ctx["q"]
    kinds = [k for k in (q("kinds") or "").split(",") if k]
    rows = ctx["st"].audit_search(text=q("text"), kinds=kinds, bot_id=q("bot"), deployment_id=q("deployment"),
                                  symbol=q("symbol"), mode=q("mode"), severity=q("severity"),
                                  correlation_id=q("correlation"), since=int(q("since")) if q("since") else None,
                                  until=int(q("until")) if q("until") else None,
                                  before_id=int(q("before")) if q("before") else None, limit=int(q("limit", "200")))
    return rows


def events_export(ctx, handler):
    q = ctx["q"]
    ctx2 = dict(ctx)
    ctx2["q"] = lambda k, d=None: (q("limit", "5000") if k == "limit" else q(k, d))
    rows = events(ctx2)
    fmt = q("format", "csv")
    stamp = time.strftime("%Y%m%d-%H%M%S")
    if fmt == "json":
        body = json.dumps(rows, default=str, indent=1).encode()
        return handler._send(200, body, "application/json; charset=utf-8",
                             {"Content-Disposition": f'attachment; filename="jarvus-events-{stamp}.json"'})
    buf = io.StringIO()
    w = csv.writer(buf)
    cols = ["id", "ts", "time_utc", "kind", "stage", "severity", "mode", "bot_id", "deployment_id", "symbol", "venue",
            "connection_id", "correlation_id", "order_id", "summary", "payload"]
    w.writerow(cols)
    for r in rows:
        w.writerow([r.get("id"), r.get("ts"), time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(r["ts"] / 1000)), r.get("kind"),
                    r.get("stage"), r.get("severity"), r.get("mode"), r.get("bot_id"), r.get("deployment_id"), r.get("symbol"),
                    r.get("venue"), r.get("connection_id"), r.get("correlation_id"), r.get("order_id"), r.get("summary"),
                    json.dumps(r.get("payload"), default=str) if r.get("payload") is not None else ""])
    return handler._send(200, buf.getvalue().encode("utf-8"), "text/csv; charset=utf-8",
                         {"Content-Disposition": f'attachment; filename="jarvus-events-{stamp}.csv"'})


def health(ctx):
    wid, st = ctx["wid"], ctx["st"]
    fh = fleet_json(wid, "/api/health") or {"running": False}
    q = JobQueue(st)
    pool = APP.sup.pool.status() if APP.sup.pool is not None else None
    from mab.hardware import describe
    return {"engine": APP.sup.status(wid), "fleet": fh, "research": {"queue": q.counts(), "pool": pool},
            "hardware": (pool or {}).get("hardware") or describe(), "db_bytes": st.size_bytes(),
            "stream_clients": APP.sse_clients, "time": _now()}


def connections_view(ctx):
    wid, st = ctx["wid"], ctx["st"]
    c = APP.conns(wid)
    rows = []
    for r in c.list():
        latest = c.latest(r["connection_id"])
        r["latest"] = {k: latest.get(k) for k in ("ts", "equity", "cash", "buying_power", "currency", "latency_ms")} if latest else None
        r["funding"] = c.funding(r["connection_id"]) if r["provider"] == "jarvus_paper" else \
            {"label": "Add funds on the provider's site", "note": "opens the provider's own funding page"}
        r["system"] = bool((r.get("options") or {}).get("system"))
        rows.append(r)
    la = st.kv_get("live_authorization", {}) or {}
    return {"connections": rows, "providers": {k: {kk: vv for kk, vv in v.items()} for k, v in PROVIDERS.items()},
            "oauth_app": c.oauth_app(), "live_authorization": la, "live_ack": LIVE_ACK,
            "assistant": Assistant(st, wid).status(), "news": news.items(st, limit=20),
            "secret_store": __import__("mab.secrets_store", fromlist=["x"]).backend_name(),
            "redirect_uri": f"http://127.0.0.1:{config.PORT}/oauth/callback"}


def funding(ctx, cid):
    c = APP.conns(ctx["wid"])
    if c.get(cid) is None:
        raise ApiError(404, "unknown connection")
    return c.funding(cid)


# ----------------------------------------------------------------------------- POST actions

def post_action(ctx, route, b):
    wid, st = ctx["wid"], ctx["st"]
    s = ctx["session"]
    if route == "/api/engine/start":
        return APP.sup.start(wid)
    if route == "/api/engine/stop":
        return APP.sup.stop(wid)
    if route == "/api/bots/create":
        return cmd(wid, "create_bot", {k: b.get(k) for k in ("strategy_id", "venue", "instrument", "name", "params")})
    if route == "/api/deploy/readiness":
        return cmd(wid, "deploy_readiness", _spec(b), wait=30)
    if route == "/api/deploy/start":
        return cmd(wid, "deploy_start", dict(_spec(b), confirmation=b.get("confirmation")), wait=30)
    if route == "/api/deploy/pause":
        return cmd(wid, "deploy_pause", {"deployment_id": b.get("deployment_id")})
    if route == "/api/deploy/resume":
        return cmd(wid, "deploy_resume", {"deployment_id": b.get("deployment_id")})
    if route == "/api/deploy/stop":
        return cmd(wid, "deploy_stop", {"deployment_id": b.get("deployment_id"), "positions": b.get("positions")}, wait=60)
    if route == "/api/deploy/limits":
        return cmd(wid, "update_limits", {"deployment_id": b.get("deployment_id"), "limits": b.get("limits") or {}})
    if route == "/api/emergency":
        reason = str(b.get("reason") or "owner pressed EMERGENCY STOP")[:200]
        if APP.sup.running(wid):
            return cmd(wid, "emergency_stop", {"reason": reason}, wait=30)
        return APP.sup.emergency_offline(wid, reason)
    if route == "/api/emergency/clear":
        if APP.sup.running(wid):
            return cmd(wid, "clear_emergency", {})
        st.kv_set("emergency", None)
        st.audit("control", "emergency stop cleared by the owner (engine stopped)", stage="emergency_cleared", severity="warning")
        return {"cleared": True}
    if route == "/api/close_all":
        return cmd(wid, "close_all_positions", {"confirm": b.get("confirm")}, wait=120)
    if route in ("/api/autopilot", "/api/research_autopilot"):
        return autopilot_switch(ctx, bool(b.get("on")))
    if route == "/api/paper_balance":
        return cmd(wid, "paper_balance", {"connection_id": b.get("connection_id"), "kind": b.get("kind", "set_balance"),
                                          "amount": b.get("amount")})
    # ---- connections
    if route == "/api/connections/create":
        creds = b.get("credentials") or {}
        c = APP.conns(wid)
        row = c.create(str(b.get("provider") or ""), str(b.get("environment") or ""), creds, b.get("options") or {},
                       b.get("label"))
        creds.clear()
        res = c.test(row["connection_id"])
        APP.notify_connections(wid)
        return {"connection": c.get(row["connection_id"]), "test": res}
    if route in ("/api/connections/test", "/api/connections/sync"):
        cid = str(b.get("connection_id"))
        c = APP.conns(wid)
        row = c.get(cid)
        if row is None:
            raise ApiError(404, "unknown connection")
        if row["provider"] == "jarvus_paper":                # the simulated account lives inside the bot engine
            if not APP.sup.running(wid):
                raise ApiError(409, "the simulated account runs inside the bot engine; start the engine to test it")
            return cmd(wid, "connection_test" if route.endswith("test") else "connection_sync", {"connection_id": cid})
        if route.endswith("sync"):
            return c.sync(cid)
        res = c.test(cid)
        APP.notify_connections(wid)
        return res
    if route == "/api/connections/reconnect":
        res = APP.conns(wid).reconnect(str(b.get("connection_id")))
        APP.notify_connections(wid)
        return res
    if route in ("/api/connections/disconnect", "/api/connections/remove"):
        cid = str(b.get("connection_id"))
        active = st.query("SELECT COUNT(*) AS n FROM deployments WHERE connection_id=? AND state IN "
                          "('running','paused','stopped_retaining','error')", (cid,))[0]["n"]
        c = APP.conns(wid)
        out = c.remove(cid, active) if route.endswith("remove") else c.disconnect(cid, active, forget=bool(b.get("forget", True)))
        APP.notify_connections(wid)
        return out or {"removed": cid}
    if route == "/api/oauth/app":
        APP.conns(wid).set_oauth_app(str(b.get("client_id") or ""), str(b.get("client_secret") or ""))
        return {"configured": True}
    if route == "/api/oauth/start":
        c = APP.conns(wid)
        cid = b.get("connection_id")
        if not cid:
            cid = c.create_oauth_pending("alpaca", str(b.get("environment") or "paper"))["connection_id"]
        url = c.oauth_start(cid, f"http://127.0.0.1:{config.PORT}/oauth/callback")
        return {"url": url, "connection_id": cid}
    if route == "/api/live/authorize":
        return cmd(wid, "live_authorize", {k: b.get(k) for k in ("ack", "connections", "max_total_allocation",
                                                                 "daily_loss_limit", "waive_eligibility")})
    if route == "/api/live/revoke":
        if APP.sup.running(wid):
            return cmd(wid, "live_revoke", {"reason": "owner"})
        return APP.sup.live_revoke_offline(wid, "owner")
    # ---- research, models, assistant, news, watchlists
    if route == "/api/research/submit":
        kind = str(b.get("kind") or "")
        spec = dict(b.get("spec") or {})
        if kind == "walk_forward" and not spec.get("definition"):
            spec["catalog"] = library.CATALOG
        return JobQueue(st).submit(kind, spec, int(b.get("priority") or 5), s["username"])
    if route == "/api/research/cancel":
        return JobQueue(st).cancel(str(b.get("job_id")))
    if route == "/api/models/snapshot":
        return cmd(wid, "brain_snapshot", {"note": b.get("note")})
    if route == "/api/models/promote":
        return cmd(wid, "brain_promote", {k: b.get(k) for k in ("version", "job_id", "accept", "note")})
    if route == "/api/models/strategy_approve":
        return cmd(wid, "strategy_approve", {k: b.get(k) for k in ("strategy_id", "version", "job_id", "accept", "note")})
    if route == "/api/models/strategy_retire":
        return cmd(wid, "strategy_retire", {k: b.get(k) for k in ("strategy_id", "version", "note")})
    if route == "/api/models/drift_check":
        return cmd(wid, "drift_check", {})
    if route == "/api/assistant/config":
        key = b.get("api_key")
        out = Assistant(st, wid).configure(api_key=key, budget=b.get("budget"), enabled=b.get("enabled"))
        b.pop("api_key", None)
        return out
    if route == "/api/assistant/forget":
        return Assistant(st, wid).forget_key()
    if route.startswith("/api/assistant/"):
        a = Assistant(st, wid)
        try:
            if route == "/api/assistant/summarize":
                since = _now() - int(b.get("hours") or 6) * 3_600_000
                ev = st.audit_search(bot_id=b.get("bot_id"), since=since, severity=b.get("severity") or "info",
                                     limit=int(b.get("limit") or 200))[::-1]
                return a.summarize(ev, str(b.get("focus") or ""))
            if route == "/api/assistant/explain":
                return a.explain(st.lifecycle(str(b.get("correlation_id") or "")))
            if route == "/api/assistant/candidates":
                return a.candidates(str(b.get("brief") or ""), b.get("context"), int(b.get("n") or 3))
            if route == "/api/assistant/news":
                return a.news(news.items(st, limit=60)["items"])
        except (AssistantUnavailable, BudgetExceeded) as e:
            raise ApiError(409, str(e))
        raise ApiError(404, "not found")
    if route == "/api/news/feeds":
        return {"feeds": news.set_feeds(st, b.get("feeds") or [])}
    if route == "/api/news/refresh":
        return news.refresh(st)
    if route == "/api/watchlists":
        name = str(b.get("name") or "").strip()[:40]
        syms = [str(x).strip()[:40] for x in (b.get("symbols") or []) if str(x).strip()][:100]
        if not name:
            raise ApiError(400, "name the watchlist")
        if b.get("delete"):
            st.write("DELETE FROM watchlists WHERE name=?", (name,))
        else:
            st.write("INSERT OR REPLACE INTO watchlists VALUES (?,?,?,?)", (name, json.dumps(syms), _now(), _now()))
        return {"watchlists": watchlists(ctx)}
    if route == "/api/auth/users":
        if s["role"] != "owner":
            raise ApiError(403, "only the owner can add accounts")
        return APP.auth.create_user(str(b.get("username") or ""), str(b.get("password") or ""))
    if route == "/api/auth/password":
        APP.auth.change_password(s["user_id"], str(b.get("old") or ""), str(b.get("new") or ""))
        return {"changed": True, "note": "signed out everywhere; sign in again"}
    raise ApiError(404, "not found")


def _spec(b):
    return {"bot_id": b.get("bot_id"), "mode": b.get("mode"), "connection_id": b.get("connection_id"),
            "allocation": b.get("allocation"), "limits": b.get("limits") or {}}


def watchlists(ctx):
    rows = ctx["st"].query("SELECT * FROM watchlists ORDER BY name")
    for r in rows:
        r["symbols"] = json.loads(r["symbols"] or "[]")
    if not rows:
        w = APP.auth.workspace(ctx["wid"])
        if w["kind"] == "demo":
            return [{"name": "Demo markets", "symbols": ["DEMO-BTC", "DEMO-ETH", "DEMO-SOL", "DEMO-DOGE", "DEMO-MEME"]}]
        return [{"name": "Crypto majors", "symbols": ["BTC-USD", "ETH-USD", "SOL-USD"]},
                {"name": "Memecoins", "symbols": ["DOGE-USD", "PEPE-USD", "SHIB-USD", "BONK-USD", "WIF-USD", "FLOKI-USD"]},
                {"name": "US large caps", "symbols": ["SPY", "QQQ", "NVDA", "AAPL", "TSLA", "MSFT"]}]
    return rows


def models(ctx):
    st = ctx["st"]
    from mab.research.drift import latest as drift_latest
    from mab.research.registry import Registry
    reg = Registry(st)
    return {"models": reg.models(), "strategies": reg.strategies(), "promotions": reg.promotions(50),
            "drift": drift_latest(st), "brain_samples": st.query("SELECT COUNT(*) AS n FROM brain_samples")[0]["n"],
            "note": "live bots use the approved (champion) brain snapshot; paper bots use the learning brain. Nothing is "
                    "promoted to live without an evaluation and your approval."}


GET_ROUTES = {
    "/api/overview": overview,
    "/api/accounts": lambda ctx: views.accounts(ctx["st"]),
    "/api/equity": lambda ctx: views.equity_curve(ctx["st"], ctx["q"]("connection", "paper-main"),
                                                  int(ctx["q"]("since")) if ctx["q"]("since") else None),
    "/api/deployments": lambda ctx: fleet_json(ctx["wid"], "/api/deployments", []),
    "/api/user_bots": lambda ctx: fleet_json(ctx["wid"], "/api/user_bots", []),
    "/api/strategies": strategies,
    "/api/results": lambda ctx: library.results(),
    "/api/backtest": lambda ctx: library.backtest_summary(ctx["q"]("strategy"), ctx["q"]("symbol"), ctx["q"]("venue")),
    "/api/markets": markets,
    "/api/candles": candles,
    "/api/markers": markers,
    "/api/trades": lambda ctx: views.trades(ctx["st"], ctx["q"]("mode"), ctx["q"]("connection"), ctx["q"]("deployment"),
                                            ctx["q"]("bot"), ctx["q"]("symbol"), int(ctx["q"]("limit", "100"))),
    "/api/alerts": lambda ctx: views.alerts(ctx["st"], int(ctx["q"]("hours", "24"))),
    "/api/scanner": lambda ctx: fleet_json(ctx["wid"], "/api/scanner", []),
    "/api/watchlists": watchlists,
    "/api/events": events,
    "/api/orders": lambda ctx: views.orders(ctx["st"], [s for s in (ctx["q"]("states") or "").split(",") if s],
                                            ctx["q"]("deployment"), ctx["q"]("connection"), int(ctx["q"]("limit", "200"))),
    "/api/fills": lambda ctx: views.fills(ctx["st"], ctx["q"]("deployment"), ctx["q"]("symbol"), int(ctx["q"]("limit", "200"))),
    "/api/positions": lambda ctx: views.positions(ctx["st"]),
    "/api/exposure": lambda ctx: views.exposure(ctx["st"]),
    "/api/compare": compare,
    "/api/health": health,
    "/api/autopilot": autopilot_view,
    "/api/connections": connections_view,
    "/api/research/jobs": lambda ctx: {"jobs": JobQueue(ctx["st"]).list(int(ctx["q"]("limit", "50"))),
                                       "kinds": JOB_KINDS, "counts": JobQueue(ctx["st"]).counts()},
    "/api/models": models,
    "/api/assistant/outputs": lambda ctx: ctx["st"].query(
        "SELECT id, ts, purpose, output, validated, validation FROM assistant_outputs ORDER BY id DESC LIMIT 20"),
    "/api/news": lambda ctx: news.items(ctx["st"], ctx["q"]("symbol"), int(ctx["q"]("limit", "50"))),
}


# ----------------------------------------------------------------------------- HTTP

class Handler(BaseHTTPRequestHandler):
    server_version = "Jarvus/7"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        pass

    def _send(self, code: int, body: bytes, ctype: str, extra: dict = None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", CSP)
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass

    def _json(self, obj, code: int = 200, extra: dict = None):
        self._send(code, json.dumps(obj, default=str).encode("utf-8"), "application/json; charset=utf-8", extra)

    def _file(self, rel: str):
        path = os.path.normpath(os.path.join(WEB_DIR, rel.lstrip("/")))
        if not path.startswith(os.path.normpath(WEB_DIR) + os.sep) or not os.path.isfile(path):
            return self._send(404, b"not found", "text/plain; charset=utf-8")
        ctype = mimetypes.guess_type(path)[0] or "application/octet-stream"
        if path.endswith(".js"):
            ctype = "text/javascript"
        if ctype.startswith("text/") or ctype in ("application/json",):
            ctype += "; charset=utf-8"
        with open(path, "rb") as fh:
            self._send(200, fh.read(), ctype)

    def _hosts(self):
        return {f"127.0.0.1:{config.PORT}", f"localhost:{config.PORT}", f"{config.HOST}:{config.PORT}"}

    def _guard(self, is_post: bool) -> bool:
        host = (self.headers.get("Host") or "").strip().lower()
        if host not in self._hosts():
            self._send(403, b"forbidden host", "text/plain; charset=utf-8")
            return False
        if is_post:
            origin = self.headers.get("Origin")
            if origin and origin.lower().replace("http://", "", 1) not in self._hosts():
                self._send(403, b"forbidden origin", "text/plain; charset=utf-8")
                return False
            if self.headers.get("X-Jarvus") != "1":
                self._send(403, b"missing app header", "text/plain; charset=utf-8")
                return False
        return True

    def _token(self):
        c = SimpleCookie()
        try:
            c.load(self.headers.get("Cookie") or "")
        except Exception:                                               # noqa: BLE001
            return None
        m = c.get(COOKIE)
        return m.value if m else None

    def _session(self):
        return APP.auth.session(self._token())

    def _body(self) -> dict:
        n = min(int(self.headers.get("Content-Length") or 0), 200_000)
        try:
            d = json.loads(self.rfile.read(n) or b"{}")
        except ValueError:
            return {}
        return d if isinstance(d, dict) else {}

    def _ctx(self, s, query: str = ""):
        qd = urllib.parse.parse_qs(query)
        wid = s["workspace"]
        return {"session": s, "wid": wid, "st": APP.st(wid),
                "q": lambda k, d=None: (qd.get(k) or [d])[0]}

    # ---------------------------------------------------------------- GET
    def do_GET(self):
        if not self._guard(False):
            return
        u = urllib.parse.urlparse(self.path)
        route = u.path
        try:
            if route in ("/", "/index.html"):
                return self._file("index.html")
            if route in ("/app.css", "/favicon.svg") or route.startswith("/js/") or route.startswith("/vendor/"):
                return self._file(route)
            if route == "/api/auth/state":
                s = self._session()
                out = {"needs_setup": APP.auth.needs_setup(), "signed_in": bool(s)}
                if s:
                    out.update({"user": {"user_id": s["user_id"], "username": s["username"], "role": s["role"]},
                                "csrf": s["csrf"], "workspace": s["workspace"],
                                "workspaces": [{k: w[k] for k in ("workspace_id", "kind", "label")}
                                               for w in APP.auth.workspaces(s["user_id"])]})
                return self._json(out)
            s = self._session()
            if route == "/oauth/callback":
                return self._oauth_callback(s, u.query)
            if not route.startswith("/api/"):
                return self._send(404, b"not found", "text/plain; charset=utf-8")
            if s is None:
                return self._json({"error": "sign in first"}, 401)
            ctx = self._ctx(s, u.query)
            if route == "/api/stream":
                return self._stream(ctx)
            if route == "/api/events/export":
                return events_export(ctx, self)
            if route.startswith("/api/strategy/"):
                return self._json(strategy_detail(ctx, urllib.parse.unquote(route[len("/api/strategy/"):])))
            if route.startswith("/api/lifecycle/"):
                return self._json(ctx["st"].lifecycle(urllib.parse.unquote(route[len("/api/lifecycle/"):])))
            if route.startswith("/api/research/job/"):
                j = JobQueue(ctx["st"]).get(route.rsplit("/", 1)[1])
                return self._json(j) if j else self._json({"error": "unknown job"}, 404)
            if route.startswith("/api/funding/"):
                return self._json(funding(ctx, urllib.parse.unquote(route[len("/api/funding/"):])))
            if route.startswith("/api/bot/"):
                bid = urllib.parse.quote(urllib.parse.unquote(route[len("/api/bot/"):]))
                return self._json(fleet_json(ctx["wid"], f"/api/bot/{bid}", {"error": "engine stopped"}))
            fn = GET_ROUTES.get(route)
            if fn is None:
                return self._json({"error": "not found"}, 404)
            return self._json(fn(ctx))
        except ApiError as e:
            return self._json({"error": str(e)}, e.code)
        except (ValueError, KeyError) as e:
            return self._json({"error": str(e)}, 400)
        except Exception as e:                                          # noqa: BLE001
            traceback.print_exc()
            return self._json({"error": f"{type(e).__name__}: {e}"}, 500)

    def _stream(self, ctx):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True
        last = stream.parse_last_id(self.headers.get("Last-Event-ID"), ctx["q"]("last"))
        stop = threading.Event()
        with APP.lock:
            APP.sse_clients += 1
        wid = ctx["wid"]
        try:
            for chunk in stream.follow(ctx["st"], last, snapshot=lambda: snapshot_for_stream(wid), stop=stop,
                                       min_severity=ctx["q"]("severity", "info"), max_seconds=3600):
                self.wfile.write(chunk)
                self.wfile.flush()
                if APP.auth.session(self._token()) is None:           # signed out elsewhere: end the stream
                    break
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
            pass
        finally:
            with APP.lock:
                APP.sse_clients -= 1

    def _oauth_callback(self, s, query):
        q = urllib.parse.parse_qs(query)
        if s is None:
            return self._send(401, b"sign in to Jarvus first, then connect again", "text/plain; charset=utf-8")
        try:
            APP.conns(s["workspace"]).oauth_finish((q.get("state") or [""])[0], (q.get("code") or [""])[0])
            APP.notify_connections(s["workspace"])
            msg = "connected"
        except Exception as e:                                          # noqa: BLE001
            msg = f"error: {e}"
        self.send_response(303)
        self.send_header("Location", "/#/connections?oauth=" + urllib.parse.quote(msg[:200]))
        self.send_header("Content-Length", "0")
        self.end_headers()

    # ---------------------------------------------------------------- POST
    def do_POST(self):
        if not self._guard(True):
            return
        route = urllib.parse.urlparse(self.path).path
        try:
            b = self._body()
            if route == "/api/auth/setup":
                APP.auth.setup_owner(str(b.get("username") or ""), str(b.get("password") or ""))
                return self._login(b)
            if route == "/api/auth/login":
                return self._login(b)
            s = self._session()
            if s is None:
                return self._json({"error": "sign in first"}, 401)
            if not APP.auth.check_csrf(s, self.headers.get("X-CSRF-Token")):
                return self._json({"error": "missing or wrong CSRF token; reload the page"}, 403)
            if route == "/api/auth/logout":
                APP.auth.logout(self._token())
                return self._json({"ok": True}, extra={"Set-Cookie": f"{COOKIE}=; Path=/; Max-Age=0; HttpOnly; SameSite=Strict"})
            if route == "/api/auth/workspace":
                s2 = APP.auth.switch_workspace(self._token(), str(b.get("workspace_id") or ""))
                w = APP.auth.workspace(s2["workspace"])
                if w["kind"] == "demo" and not APP.sup.running(w["workspace_id"]) and APP.start_engines:
                    try:
                        APP.sup.start(w["workspace_id"])
                    except RuntimeError as e:
                        return self._json({"workspace": s2["workspace"], "warning": str(e)})
                return self._json({"workspace": s2["workspace"]})
            ctx = self._ctx(s)
            return self._json(post_action(ctx, route, b))
        except ApiError as e:
            return self._json({"error": str(e)}, e.code)
        except PermissionError as e:
            return self._json({"error": str(e)}, 403)
        except (ValueError, KeyError) as e:                             # a message meant for the person using the app
            return self._json({"error": str(e)}, 400)
        except Exception as e:                                          # noqa: BLE001 - never echo the request body
            print(f"  {route}: {type(e).__name__}: {e}", flush=True)
            return self._json({"error": f"{type(e).__name__}: {e}"}, 500)

    def _login(self, b):
        token, s = APP.auth.login(str(b.get("username") or ""), str(b.get("password") or ""))
        cookie = f"{COOKIE}={token}; Path=/; HttpOnly; SameSite=Strict; Max-Age={14 * 86400}"
        return self._json({"ok": True, "csrf": s["csrf"], "workspace": s["workspace"]}, extra={"Set-Cookie": cookie})


class QuietServer(ThreadingHTTPServer):
    daemon_threads = True

    def handle_error(self, request, client_address):
        if isinstance(sys.exc_info()[1], (ConnectionResetError, ConnectionAbortedError, BrokenPipeError)):
            return
        super().handle_error(request, client_address)


def make_app(data_dir: str = None, start_engines: bool = True, research_workers=None) -> App:
    global APP
    APP = App(data_dir or config.DATA_DIR, start_engines, research_workers)
    return APP


def serve():
    httpd = QuietServer((config.HOST, config.PORT), Handler)
    app = make_app()
    # engines start only once the port is ours, so a second copy of the app can never run a second set of bots
    app.boot()
    print(f"\n  Jarvus is running at  http://{config.HOST}:{config.PORT}\n  Ctrl-C to stop.\n", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n  stopped.\n")
    finally:
        app.sup.stop_all()
        httpd.server_close()


if __name__ == "__main__":
    serve()
