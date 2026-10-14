"""The local web server: REST for every page action, one WebSocket for live updates, /health, and the compiled
React app. It is bound to 127.0.0.1 by the launcher and refuses anything that does not come from this computer.

Security (sections 232-236):
* Host header must be 127.0.0.1 or localhost (stops DNS-rebinding pages from reaching the API).
* Every /api call and the WebSocket need the per-run session token. The token is written into index.html when the
  page is served, so only a page loaded from this server has it; another website cannot read it (same-origin policy),
  which blocks cross-site request forgery.
* State-changing requests with an Origin header must come from 127.0.0.1/localhost.
* Strict Content-Security-Policy; no third-party scripts; API responses are never cached.
* Credentials go into the vault and never come back out: the API only ever returns masked values.
"""

from __future__ import annotations

import asyncio
import math
import secrets
from decimal import Decimal
from typing import Any, Optional
from urllib.parse import urlsplit

import numpy as np
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from pydantic import BaseModel, Field
from starlette.middleware.base import BaseHTTPMiddleware

from tradingai import APP_ID, __version__, config
from tradingai.agents.base import AGENTS
from tradingai.brokers.adapters import ADAPTERS, matrix as broker_matrix
from tradingai.core import logs
from tradingai.storage.db import dumps
from tradingai.strategies.library import specs

log = logs.get("api")
LOCAL_HOSTS = {"127.0.0.1", "localhost"}

# What the read-only token (X-TA-Read-Token) may fetch: GET only, and only these pages of information. It cannot reach
# brokers, connections, credentials, the audit chain, or any route that changes anything. It exists so a voice
# assistant (JARVIS) can read the system's state without being able to act on it.
READ_ONLY_PATHS = frozenset({
    "/api/overview", "/api/fleet", "/api/fleet/summary", "/api/learning", "/api/market/strip", "/api/daytrade",
    "/api/activity", "/api/autopilot", "/api/system/thermal", "/api/account", "/api/risk", "/api/orders",
    "/api/fills", "/api/decisions", "/api/equity", "/api/report/session", "/api/report/attribution", "/api/events",
    "/api/jarvis/pending", "/api/instruments", "/api/coverage", "/api/roles",
})


def read_only_allows(method: str, path: str) -> bool:
    if method != "GET":
        return False
    if path.startswith("/api/fleet/A") and path[len("/api/fleet/"):].isalnum():      # one agent: /api/fleet/A004
        return True
    return path in READ_ONLY_PATHS


def clean(o: Any) -> Any:
    """JSON-safe: Decimals as text (exact money), NaN/inf as null, numpy scalars as Python numbers."""
    if isinstance(o, dict):
        return {str(k): clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    if isinstance(o, Decimal):
        return str(o)
    if isinstance(o, (np.floating, float)):
        f = float(o)
        return f if math.isfinite(f) else None
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, np.bool_):
        return bool(o)
    if isinstance(o, np.ndarray):
        return clean(o.tolist())
    return o


class J(JSONResponse):
    def render(self, content: Any) -> bytes:
        return dumps(clean(content)).encode("utf-8")


# ---------------------------------------------------------------- request bodies
class BotIn(BaseModel):
    instrument_id: str
    tf: str = "5m"
    strategy_id: str
    signal_mode: str = Field("strategy+ensemble", pattern="^(strategy|ensemble|strategy\\+ensemble)$")
    risk_profile: str = Field("conservative", pattern="^(conservative|moderate|aggressive)$")
    max_trades_per_day: int = Field(10, ge=1, le=200)


class PhraseIn(BaseModel):
    phrase: str = ""


class ReasonIn(BaseModel):
    reason: str = "owner pressed EMERGENCY STOP"


class ModeIn(BaseModel):
    mode: str


class LimitsIn(BaseModel):
    changes: dict
    confirm: str = ""


class ConnectionIn(BaseModel):
    broker: str
    environment: str
    label: str = ""
    credentials: dict[str, str]


class ArmIn(BaseModel):
    connection_id: str
    ack: str
    max_capital: Decimal = Field(gt=0)
    daily_loss: Decimal = Field(gt=0)


class BalanceIn(BaseModel):
    amount: Decimal = Field(gt=0, le=Decimal("1000000000"))


class AutopilotIn(BaseModel):
    enabled: Optional[bool] = None
    max_bots: Optional[int] = Field(None, ge=0, le=20)
    markets: Optional[list[str]] = None
    allow_probation: Optional[bool] = None


class ThermalIn(BaseModel):
    minutes: float = 5.0


class AutostartIn(BaseModel):
    enabled: bool


class CommandIn(BaseModel):
    action: str = Field(min_length=1, max_length=40)
    reason: str = Field("", max_length=200)
    minutes: Optional[float] = None
    amount: Optional[Decimal] = None
    command_id: Optional[str] = Field(None, max_length=64)


class PauseIn(BaseModel):
    paused: bool
    reason: str = ""


class AskIn(BaseModel):
    text: str = Field(min_length=1, max_length=500)
    command_id: Optional[str] = Field(None, max_length=64)


# ---------------------------------------------------------------- the app
def create_app(core, *, token: Optional[str] = None, on_shutdown=None, read_token: Optional[str] = None,
               command_token: Optional[str] = None) -> FastAPI:
    """`core` is a tradingai.app.App. `on_shutdown` is called after the owner presses Shut down."""
    token = token or secrets.token_urlsafe(32)
    api = FastAPI(title="Trading AI", version=__version__, docs_url=None, redoc_url=None, openapi_url=None,
                  default_response_class=J)
    api.state.token = token
    api.state.read_token = read_token or secrets.token_urlsafe(32)
    api.state.command_token = command_token or secrets.token_urlsafe(32)

    class Guard(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next):
            host = (request.headers.get("host") or "").rsplit(":", 1)[0].strip("[]")
            if host not in LOCAL_HOSTS:
                return Response("this server only answers on 127.0.0.1", status_code=421)
            path = request.url.path
            if request.method not in ("GET", "HEAD", "OPTIONS"):
                origin = request.headers.get("origin")
                if origin and urlsplit(origin).hostname not in LOCAL_HOSTS:
                    return J({"error": "cross-site request refused"}, status_code=403)
            if path.startswith("/api/") and path != "/api/system/ping":
                full = secrets.compare_digest(request.headers.get("x-ta-token", ""), token)
                read = (not full and read_only_allows(request.method, path) and secrets.compare_digest(
                    request.headers.get("x-ta-read-token", ""), api.state.read_token))
                # the voice assistant's command token works on exactly one route: it may ASK (see engine/jarvis_link.py)
                ask = (not full and request.method == "POST" and path == "/api/jarvis/command" and
                       secrets.compare_digest(request.headers.get("x-ta-command-token", ""), api.state.command_token))
                if not (full or read or ask):
                    return J({"error": "missing or wrong session token: reload the page"}, status_code=401)
            resp = await call_next(request)
            resp.headers["X-Content-Type-Options"] = "nosniff"
            resp.headers["X-Frame-Options"] = "DENY"
            resp.headers["Referrer-Policy"] = "no-referrer"
            resp.headers["Content-Security-Policy"] = (
                "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
                "connect-src 'self' ws://127.0.0.1:* ws://localhost:*; frame-ancestors 'none'; base-uri 'none'; "
                "form-action 'self'")
            if path.startswith("/api/") or path == "/health":
                resp.headers["Cache-Control"] = "no-store"
            return resp

    api.add_middleware(Guard)

    @api.exception_handler(PermissionError)
    async def _perm(_: Request, e: PermissionError):
        return J({"error": str(e), "kind": "refused"}, status_code=403)

    @api.exception_handler(ValueError)
    async def _val(_: Request, e: ValueError):
        return J({"error": str(e), "kind": "invalid"}, status_code=400)

    @api.exception_handler(KeyError)
    async def _key(_: Request, e: KeyError):
        return J({"error": f"not found: {e}", "kind": "not_found"}, status_code=404)

    # ------------------------------------------------------------ system
    @api.get("/health")
    def health():
        return core.health()

    @api.get("/api/system/ping")
    def ping():
        return {"app": APP_ID, "version": __version__, "state": core.state.state}

    @api.get("/api/overview")
    def overview():
        return core.overview()

    @api.get("/api/events")
    def events(since: int = 0, limit: int = 300):
        return core.bus.since(since, limit=min(limit, 2000))

    @api.post("/api/system/shutdown")
    async def shutdown():
        out = await asyncio.to_thread(core.shutdown)
        if on_shutdown:
            asyncio.get_running_loop().call_later(0.5, on_shutdown)
        return out

    # ------------------------------------------------------------ catalog, portfolio templates, reports, roles
    @api.get("/api/catalog")
    def catalog():
        return core.catalog_view()

    # No manual test or deployment routes (owner's specification, revision 13, section 2): research runs only inside
    # the autopilot, and portfolio bots are created only by the autopilot for strategies that qualify.

    # ------------------------------------------------------------ the voice assistant (engine/jarvis_link.py)
    @api.post("/api/jarvis/command")
    def jarvis_command(c: CommandIn):
        return core.jarvis.submit(c.action, c.reason, c.minutes, c.amount, c.command_id)

    @api.get("/api/jarvis/pending")
    def jarvis_pending():
        return core.jarvis.view()

    @api.post("/api/jarvis/pending/{cid}/approve")
    def jarvis_approve(cid: str):
        return core.jarvis.approve(cid)

    @api.post("/api/jarvis/pending/{cid}/reject")
    def jarvis_reject(cid: str):
        return core.jarvis.reject(cid)

    @api.post("/api/controls/pause-entries")
    def pause_entries(p: PauseIn):
        return core.pause_entries(p.paused, "owner", p.reason)

    @api.post("/api/controls/flatten")
    def flatten():
        return core.flatten_all("owner")

    @api.get("/api/equity")
    def equity(hours: float = 168):
        from tradingai.engine.reports import equity_series
        return equity_series(core, min(max(hours, 1), 24 * 365))

    @api.get("/api/report/session")
    def session_report(since: int = 0):
        from tradingai.engine.reports import session_report as sr
        return sr(core, since or None)

    @api.get("/api/report/attribution")
    def attribution(since: int = 0):
        from tradingai.engine.reports import attribution as at
        return at(core, since or None)

    @api.get("/api/roles")
    def roles():
        from tradingai.engine.roles import view
        return view(core)

    @api.get("/api/coverage")
    def coverage():
        return core.coverage()

    @api.get("/api/coverage/discovery")
    def coverage_discovery():
        return core.discovery.coverage()

    # ------------------------------------------------------------ the trading fleet A001... and its brain
    @api.get("/api/fleet")
    def fleet():
        return core.fleet.view()

    @api.get("/api/learning")
    def learning():
        return core.learning.view()

    @api.post("/api/learning/replay")
    def learning_replay():
        return core.learning.replay_all("owner request")

    @api.post("/api/fleet/{agent_id}/probe")
    def fleet_probe(agent_id: str):
        return core.probe_agent(agent_id)

    @api.get("/api/fleet/summary")
    def fleet_summary():
        return core.fleet.summary()

    @api.get("/api/fleet/{agent_id}")
    def fleet_agent(agent_id: str):
        return core.fleet.detail(agent_id)

    @api.get("/api/market/strip")
    def market_strip():
        from tradingai.engine.dashboard import market_strip as ms
        return ms(core)

    @api.get("/api/daytrade")
    def daytrade_rules():
        from tradingai.engine.daytrade import describe
        return describe()

    @api.get("/api/activity")
    def activity(minutes: int = 60):
        from tradingai.engine.dashboard import decision_activity
        return decision_activity(core, min(max(minutes, 5), 1440))

    @api.post("/api/assistant/ask")
    def ask(a: AskIn):
        return core.assistant.ask(a.text, a.command_id)

    # ------------------------------------------------------------ autopilot and start with Windows
    @api.get("/api/autopilot")
    def autopilot():
        return core.autopilot.view()

    @api.post("/api/autopilot")
    def autopilot_set(a: AutopilotIn):
        changes = {k: v for k, v in a.model_dump().items() if v is not None}
        if changes.get("enabled") and core.risk.kill_switch:
            raise PermissionError("STOP ALL TRADING is engaged: re-arm trading first")
        return core.autopilot.configure(changes)

    @api.get("/api/system/thermal")
    def thermal():
        return core.hardware.view()

    @api.post("/api/system/thermal-check")
    def thermal_check(a: ThermalIn):
        return core.hardware.start_check(a.minutes)

    @api.post("/api/system/thermal-check/stop")
    def thermal_check_stop():
        return core.hardware.stop_check()

    @api.get("/api/system/autostart")
    def autostart():
        from tradingai.app import autostart_status
        return autostart_status()

    @api.post("/api/system/autostart")
    def autostart_set(a: AutostartIn):
        from tradingai.app import set_autostart
        out = set_autostart(a.enabled)
        core.audit("system", f"start with Windows turned {'on' if a.enabled else 'off'}")
        return out

    # ------------------------------------------------------------ AI Trading System page
    @api.get("/api/instruments")
    def instruments():
        return core.instruments_view()

    @api.get("/api/chart")
    def chart(instrument: str, tf: str = "5m", n: int = 300):
        return core.chart(instrument, tf, n)

    @api.get("/api/account")
    def account():
        return core.account_view()

    @api.get("/api/bots")
    def bots():
        return [b.as_dict() for b in core.bots.values()]

    @api.post("/api/bots")
    def create_bot(b: BotIn):
        raise PermissionError("bots are run only by the 100 trading agents: each market has exactly one owning agent, "
                              "so a manual bot could hold a position that conflicts with it")

    @api.post("/api/bots/{bot_id}/{action}")
    def bot_action(bot_id: str, action: str):
        if action not in ("start", "pause", "stop", "delete"):
            raise ValueError("action must be start, pause, stop or delete")
        return core.bot_action(bot_id, action)

    @api.post("/api/bot/start")
    def start_all():
        return core.start_all()

    @api.post("/api/bot/stop")
    def stop_all():
        return core.stop_all()

    @api.post("/api/emergency-stop")
    def emergency(r: ReasonIn):
        return core.emergency_stop(r.reason[:300] or "owner pressed EMERGENCY STOP", "owner")

    @api.post("/api/rearm")
    def rearm(p: PhraseIn):
        return core.rearm(p.phrase)

    @api.post("/api/mode")
    def mode(m: ModeIn):
        return core.set_mode(m.mode)

    @api.get("/api/risk")
    def risk():
        snap = None
        try:
            acct = core.broker_for(core.mode).get_balance()
            from tradingai.risk.service import Snapshot
            pos = {p["instrument_id"]: {"qty": p["qty"], "price": p["price"] or p["avg_price"],
                                        "multiplier": p["multiplier"]} for p in core.paper.positions_detail()} \
                if core.mode != "live" else {}
            snap = core.risk.usage(Snapshot(equity=acct.equity or Decimal(0), positions=pos,
                                            clusters=core._clusters()))
        except Exception as e:                               # noqa: BLE001
            log.warning(f"risk usage unavailable: {e}")
        return dict(core.risk.state(), usage=snap, state=core.state.view())

    @api.post("/api/risk/limits")
    def limits(li: LimitsIn):
        out = core.risk.update_limits(li.changes, "owner", li.confirm)
        core._persist_risk()
        return out

    @api.get("/api/strategies")
    def strategies(market: str = "", q: str = "", runnable: bool = True, limit: int = 200):
        out = []
        for sp in specs().values():
            if runnable and not sp.runnable:
                continue
            if market and market not in sp.supported_markets:
                continue
            if q and q.lower() not in (sp.strategy_id + " " + sp.name + " " + sp.family).lower():
                continue
            out.append({"strategy_id": sp.strategy_id, "name": sp.name, "family": sp.family,
                        "markets": sp.supported_markets, "timeframes": sp.supported_timeframes,
                        "risk_class": sp.risk_class, "runnable": sp.runnable,
                        "status": core.db.one("SELECT status FROM experiments WHERE strategy_id=? AND status!='RUNNING' "
                                              "ORDER BY created DESC LIMIT 1", (sp.strategy_id,))})
            if len(out) >= limit:
                break
        return out

    @api.get("/api/strategies/{strategy_id}")
    def strategy(strategy_id: str):
        sp = specs().get(strategy_id)
        if sp is None:
            raise KeyError(strategy_id)
        return sp.as_dict()

    # ------------------------------------------------------------ research (strategy lab on the AI Trading System page)
    @api.get("/api/research/jobs")
    def jobs():
        return core.jobs.list()

    @api.get("/api/research/jobs/{job_id}")
    def job(job_id: str):
        v = core.jobs.view(job_id, with_result=True)
        if v is None:
            raise KeyError(job_id)
        return v

    @api.get("/api/research/experiments")
    def experiments(limit: int = 100):
        return {"experiments": core.ledger.list(min(limit, 500)), "counts": core.ledger.counts()}

    @api.get("/api/research/experiments/{eid}")
    def experiment(eid: str):
        e = core.ledger.get(eid)
        if e is None:
            raise KeyError(eid)
        return e

    @api.get("/api/research/compare")
    def compare(strategy_id: str, instrument: str):
        return core.compare(strategy_id, instrument)

    # ------------------------------------------------------------ Brokers & Accounts page
    @api.get("/api/brokers")
    def brokers():
        from tradingai.brokers.adapters import FUNDING
        # only brokers for the markets this program trades (US stocks, crypto, meme coins): a forex-only broker is hidden
        rows = [r for r in broker_matrix() if r.get("stocks") or r.get("crypto")]
        shown = {r["broker"] for r in rows}
        return {"matrix": rows, "adapters": {k: {"label": v.label, "environments": v.environments,
                                                "needs": v.needs, "setup": v.setup, "verified": v.verified}
                                            for k, v in ADAPTERS.items() if k in shown},
                "funding": [{"broker": k, "label": ADAPTERS[k].label, "url": u, "domain": dom, "how": how}
                            for k, (u, dom, how) in FUNDING.items() if k in shown]}

    @api.get("/api/connections")
    def connections():
        return core.connections_view()

    @api.post("/api/connections")
    def add_connection(c: ConnectionIn):
        return core.add_connection(c.broker, c.environment, c.label, c.credentials)

    @api.post("/api/connections/{cid}/test")
    def test_connection(cid: str):
        if cid not in core.connections:
            raise KeyError(cid)
        return core.test_connection(cid)

    @api.delete("/api/connections/{cid}")
    def remove_connection(cid: str):
        return core.remove_connection(cid)

    @api.get("/api/live/readiness/{cid}")
    def readiness(cid: str):
        return {"connection_id": cid, "items": core.readiness(cid), "ack_phrase": core_ack()}

    @api.post("/api/live/arm")
    def arm(a: ArmIn):
        return core.arm_live(a.connection_id, a.ack, a.max_capital, a.daily_loss)

    @api.post("/api/live/disarm")
    def disarm():
        return core.disarm_live("owner pressed disarm")

    @api.post("/api/paper/balance")
    def paper_balance(b: BalanceIn):
        return core.set_paper_balance(b.amount)

    @api.post("/api/reconcile")
    def reconcile():
        return core.reconcile()

    @api.get("/api/orders")
    def orders(limit: int = 100):
        return core.oms.orders(min(limit, 1000))

    @api.get("/api/fills")
    def fills(limit: int = 100):
        return core.oms.fills(min(limit, 1000))

    # ------------------------------------------------------------ Agent Activity page
    @api.get("/api/decisions")
    def decisions(limit: int = 50, instrument: str = ""):
        """Same shape as the live "decision" event, so a reloaded page shows exactly what it showed before."""
        sql = "SELECT decision_id, ts, bot_id, instrument_id, tf, strategy_id, mode, signal, regime, " \
              "json_extract(votes, '$.ensemble') AS ensemble, order_json, outcome, reason, latency, simulated " \
              "FROM decisions"
        args: tuple = ()
        if instrument:
            sql += " WHERE instrument_id=?"
            args = (instrument,)
        out = []
        import json
        for r in core.db.query(sql + " ORDER BY ts DESC LIMIT ?", args + (min(limit, 500),)):
            j = {k: (json.loads(r[k]) if r.get(k) else None) for k in ("signal", "regime", "ensemble", "order_json",
                                                                      "latency")}
            out.append({"decision_id": r["decision_id"], "ts": r["ts"], "bot_id": r["bot_id"],
                        "instrument": r["instrument_id"], "tf": r["tf"], "mode": r["mode"],
                        "strategy_id": r["strategy_id"], "outcome": r["outcome"], "reason": r["reason"],
                        "signal": j["signal"], "regime": j["regime"], "ensemble": j["ensemble"], "order": j["order_json"],
                        "latency": j["latency"], "simulated_data": bool(r["simulated"])})
        return out

    @api.get("/api/decisions/{decision_id}")
    def decision(decision_id: str):
        import json
        r = core.db.one("SELECT * FROM decisions WHERE decision_id=?", (decision_id,))
        if r is None:
            raise KeyError(decision_id)
        for k in ("signal", "regime", "votes", "risk", "order_json", "latency"):
            r[k] = json.loads(r[k]) if r.get(k) else None
        r["audit"] = core.db.audit_rows(correlation_id=decision_id)
        return r

    @api.get("/api/agents")
    def agents():
        from tradingai.agents.roster import roster_summary
        return {"summary": roster_summary(),
                "agents": [{"agent_id": a.agent_id, "name": a.name, "group": a.group, "cluster": a.cluster,
                            "votes": a.votes, "requires": list(a.requires), "description": a.description}
                           for a in AGENTS.values()]}

    @api.get("/api/audit")
    def audit(since: int = 0, kind: str = "", limit: int = 200):
        return core.db.audit_rows(since_id=since, kind=kind or None, limit=min(limit, 2000))

    @api.get("/api/audit/verify")
    def audit_verify():
        ok, bad = core.db.verify_audit()
        return {"ok": ok, "first_bad_row": bad}

    # ------------------------------------------------------------ WebSocket
    @api.websocket("/ws")
    async def ws(sock: WebSocket):
        host = (sock.headers.get("host") or "").rsplit(":", 1)[0].strip("[]")
        origin = sock.headers.get("origin")
        if host not in LOCAL_HOSTS or (origin and urlsplit(origin).hostname not in LOCAL_HOSTS) or \
                not secrets.compare_digest(sock.query_params.get("token", ""), token):
            await sock.close(code=4401)
            return
        await sock.accept()
        sid = core.bus.subscribe()
        rtask: Optional[asyncio.Task] = None
        try:
            since = int(sock.query_params.get("since", "0") or 0)
            missed = core.bus.since(since, limit=500) if since else []
            await sock.send_text(dumps(clean({"topic": "hello", "data": {
                "overview": core.overview(), "account": core.account_view(), "missed": missed}})))

            async def reader():
                while True:
                    await sock.receive_text()          # pings from the page; a disconnect ends the loop
            rtask = asyncio.create_task(reader())
            while not rtask.done():
                evs = await asyncio.to_thread(core.bus.drain, sid, 1.0)
                for ev in evs:
                    await sock.send_text(dumps(clean(ev)))
        except (WebSocketDisconnect, RuntimeError):
            pass
        except Exception as e:                               # noqa: BLE001
            log.warning(f"websocket closed: {type(e).__name__}")
        finally:
            core.bus.unsubscribe(sid)
            if rtask is not None:
                if rtask.done():
                    rtask.exception() if not rtask.cancelled() else None      # mark the disconnect as seen
                else:
                    rtask.cancel()

    # ------------------------------------------------------------ the compiled frontend
    def core_ack():
        from tradingai.app import LIVE_ACK
        return LIVE_ACK

    def index() -> Response:
        f = config.frontend_dir() / "index.html"
        if not f.is_file():
            return HTMLResponse(f'<!doctype html><html><head><meta name="ta-token" content="{token}"></head><body>'
                                "<h1>Trading AI</h1><p>The dashboard files are missing from this installation. The "
                                "server is running: see <a href='/health'>/health</a>.</p></body></html>",
                                status_code=503)
        html = f.read_text(encoding="utf-8").replace(
            "</head>", f'<meta name="ta-token" content="{token}"></head>', 1)
        return HTMLResponse(html, headers={"Cache-Control": "no-store"})

    @api.get("/")
    def root():
        return index()

    @api.get("/{path:path}")
    def static(path: str):
        if path.startswith(("api/", "ws")):
            raise HTTPException(404)
        base = config.frontend_dir().resolve()
        f = (base / path).resolve()
        if base in f.parents and f.is_file():
            return FileResponse(f, headers={"Cache-Control": "public, max-age=31536000, immutable"}
                                if "/assets/" in f.as_posix() else None)
        return index()                                       # client-side routes (/broker, /intelligence)

    return api
