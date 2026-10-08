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


class ResearchIn(BaseModel):
    strategy_id: str
    instrument_id: str
    tf: str = "1h"
    profile: str = Field("STANDARD", pattern="^(FAST|STANDARD|DEEP)$")
    lookback: int = Field(5000, ge=400, le=20000)


# ---------------------------------------------------------------- the app
def create_app(core, *, token: Optional[str] = None, on_shutdown=None) -> FastAPI:
    """`core` is a tradingai.app.App. `on_shutdown` is called after the owner presses Shut down."""
    token = token or secrets.token_urlsafe(32)
    api = FastAPI(title="Trading AI", version=__version__, docs_url=None, redoc_url=None, openapi_url=None,
                  default_response_class=J)
    api.state.token = token

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
                if not secrets.compare_digest(request.headers.get("x-ta-token", ""), token):
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

    # ------------------------------------------------------------ Command Center
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
        return core.create_bot(b.instrument_id, b.tf, b.strategy_id, b.signal_mode, b.risk_profile,
                               b.max_trades_per_day)

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

    # ------------------------------------------------------------ research (Command Center strategy lab)
    @api.post("/api/research")
    def research(r: ResearchIn):
        return core.submit_research(r.strategy_id, r.instrument_id, r.tf, r.profile, r.lookback)

    @api.get("/api/research/jobs")
    def jobs():
        return core.jobs.list()

    @api.get("/api/research/jobs/{job_id}")
    def job(job_id: str):
        v = core.jobs.view(job_id, with_result=True)
        if v is None:
            raise KeyError(job_id)
        return v

    @api.post("/api/research/jobs/{job_id}/cancel")
    def cancel(job_id: str):
        return {"cancelled": core.jobs.cancel(job_id)}

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

    # ------------------------------------------------------------ Broker & Money
    @api.get("/api/brokers")
    def brokers():
        return {"matrix": broker_matrix(), "adapters": {k: {"label": v.label, "environments": v.environments,
                                                           "needs": v.needs, "setup": v.setup,
                                                           "verified": v.verified}
                                                       for k, v in ADAPTERS.items()}}

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

    # ------------------------------------------------------------ Live Intelligence
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
