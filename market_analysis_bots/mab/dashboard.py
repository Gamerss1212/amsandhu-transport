"""Local web dashboard (127.0.0.1 only).

Shows what section 10 of the requirements asks for: how many bots are configured, enabled,
running, warming, idle, without data, degraded, stopped, disabled or paused; shared data health;
the paper account; positions, trades, risk events; and for any bot the indicator values,
thresholds and rule outcomes behind its latest decision.

Controls (pause, resume, emergency stop, balance changes, enable/disable a bot) are POSTs that
must carry the per-process CSRF token embedded in the page, and requests must name a local Host.
When the dashboard runs inside the fleet process it reads live objects; standalone, it reads the
database the fleet writes and sends commands through the control queue.
"""

from __future__ import annotations

import json
import os
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Optional
from urllib.parse import parse_qs, urlparse

from mab.storage import Storage

HERE = os.path.dirname(os.path.abspath(__file__))
ALLOWED_COMMANDS = {"pause", "resume", "emergency_stop", "clear_emergency", "deposit", "withdraw", "set_balance",
                    "enable_bot", "disable_bot", "test_order"}


class Provider:
    """Live view of a Fleet in this process, falling back to the database."""

    def __init__(self, storage: Storage, fleet=None):
        self.storage = storage
        self.fleet = fleet

    def summary(self) -> dict:
        if self.fleet is not None:
            h = self.fleet.system_health()
            h["alerts"] = list(self.fleet.alerts)[-30:]
            h["source"] = "live"
            h["configured"] = len(self.fleet.bot_cfgs)
            h["enabled"] = sum(1 for b in self.fleet.bots.values() if b.enabled)
            return h
        r = self.storage.query("SELECT body FROM system_health ORDER BY time DESC LIMIT 1")
        h = json.loads(r[0]["body"]) if r else {}
        h["alerts"] = self.storage.query("SELECT time, level, kind, message, bot_id FROM events ORDER BY id DESC LIMIT 30")[::-1]
        h["source"] = "database (fleet not running in this process)"
        return h

    def bots(self) -> list:
        if self.fleet is not None:
            out = []
            for bid, br in self.fleet.bots.items():
                p = br.tm.pos
                out.append({"bot_id": bid, "name": br.cfg.get("name", bid), "strategy_id": br.c.id,
                            "family": br.c.definition.get("family"), "venue": br.venue, "instrument": br.symbol,
                            "tf": br.tf, "state": br.state, "message": br.message, "last_decision": br.last_decision,
                            "last_eval": br.last_eval, "position": None if p is None else
                            f"{'long' if p.side > 0 else 'short'} {p.qty:.6g} @ {p.entry_price:.6g}",
                            "trades": len(br.tm.trades), "errors": br.total_errors})
            return out
        rows = self.storage.query(
            "SELECT h.* FROM bot_health h JOIN (SELECT bot_id, MAX(time) m FROM bot_health GROUP BY bot_id) x "
            "ON h.bot_id = x.bot_id AND h.time = x.m")
        return [{"bot_id": r["bot_id"], "state": r["state"], "message": r["message"], "last_decision": r["last_decision"],
                 "last_eval": r["last_eval"], "errors": r["errors"]} for r in rows]

    def bot(self, bid: str) -> dict:
        d = self.fleet.bot_view(bid) if self.fleet is not None and bid in self.fleet.bots else {"bot_id": bid}
        d["recent_signals"] = self.storage.query(
            "SELECT bar_time, decision_time, action, reason, features, rules FROM signals WHERE bot_id=? "
            "ORDER BY id DESC LIMIT 20", (bid,))
        for s in d["recent_signals"]:
            s["features"] = json.loads(s["features"] or "{}")
            s["rules"] = json.loads(s["rules"] or "[]")
        d["trades_list"] = self.storage.query("SELECT * FROM trades WHERE bot_id=? ORDER BY id DESC LIMIT 50", (bid,))
        d["risk"] = self.storage.query("SELECT * FROM risk_decisions WHERE bot_id=? ORDER BY time DESC LIMIT 20", (bid,))
        for r in d["risk"]:
            r["checks"] = json.loads(r["checks"] or "[]")
        return d

    def brain(self) -> dict:
        if self.fleet is None:
            st = self.storage.kv_get("brain") or {}
            return {"mode": "unknown (fleet not running here)", "trades_learned": (st.get("stats") or {}).get("learned", 0)}
        names = {br.c.id: br.c.definition.get("name") for br in self.fleet.bots.values()}
        return self.fleet.brain.summary(names)

    def chart(self, key: str, n: int = 240) -> dict:
        if self.fleet is None:
            return {"key": key, "t": [], "c": []}
        s = self.fleet.hub.series.get(tuple(key.split("/", 2)))
        if s is None:
            return {"key": key, "t": [], "c": []}
        times = s.times[-n:]
        return {"key": key, "t": times, "c": [s.bars[t].close for t in times], "h": [s.bars[t].high for t in times],
                "l": [s.bars[t].low for t in times]}

    def tickers(self) -> list:
        if self.fleet is None:
            return []
        out, seen = [], set()
        prefer = ["BTC-USD", "ETH-USD", "SOL-USD", "SPY", "QQQ", "NVDA", "XXBTZUSD", "BTC-USDT"]
        keys = sorted(self.fleet.hub.series, key=lambda k: (prefer.index(k[1]) if k[1] in prefer else 99, k[2] != "5m"))
        for k in keys:
            if k[1] in seen or len(out) >= 8:
                continue
            s = self.fleet.hub.series[k]
            if len(s.times) < 2:
                continue
            last = s.bars[s.times[-1]].close
            ref = s.bars[s.times[max(0, len(s.times) - 1 - 288 * 300_000 // s.step)]].close
            seen.add(k[1])
            out.append({"symbol": k[1], "venue": k[0], "last": last, "change": last / ref - 1 if ref else None,
                        "key": "/".join(k), "status": s.quality.status})
        return out

    def series(self) -> dict:
        if self.fleet is not None:
            return self.fleet.hub.snapshot()
        return {"series": [], "note": "series detail is only available while the fleet runs in this process"}

    def trades(self, limit=200) -> list:
        return self.storage.query("SELECT * FROM trades ORDER BY id DESC LIMIT ?", (limit,))

    def fills(self, limit=200) -> list:
        return self.storage.query("SELECT * FROM fills ORDER BY time DESC LIMIT ?", (limit,))

    def equity(self, limit=2000) -> list:
        return self.storage.query("SELECT * FROM equity ORDER BY time DESC LIMIT ?", (limit,))[::-1]

    def events(self, limit=200) -> list:
        return self.storage.query("SELECT time, level, kind, bot_id, message FROM events ORDER BY id DESC LIMIT ?",
                                  (limit,))

    def positions(self) -> list:
        if self.fleet is not None:
            a = self.fleet.account
            return [dict(p, mark=a.marks.get((p["venue"], p["instrument"]), (None, None))[0])
                    for p in a.positions.values()]
        st = self.storage.kv_get("account") or {}
        return st.get("positions", [])

    def control(self, command: str, args: dict) -> dict:
        if command not in ALLOWED_COMMANDS:
            raise ValueError("command not allowed")
        if self.fleet is not None:
            return {"result": self.fleet.apply_command(command, args)}
        cid = self.storage.command(command, args)
        for _ in range(30):
            r = self.storage.command_result(cid)
            if r and r["status"] != "pending":
                return {"result": r["result"], "status": r["status"]}
            time.sleep(0.2)
        return {"status": "queued", "note": "the fleet is not running; the command will apply when it starts"}


def make_handler(provider: Provider, token: str, page: str):
    class H(BaseHTTPRequestHandler):
        server_version = "mab-dashboard"

        def log_message(self, *a):
            pass

        def _host_ok(self) -> bool:
            host = (self.headers.get("Host") or "").split(":")[0]
            return host in ("127.0.0.1", "localhost")

        def _send(self, code: int, body, ctype="application/json"):
            data = body if isinstance(body, bytes) else (json.dumps(body, default=str).encode() if ctype ==
                                                         "application/json" else body.encode())
            self.send_response(code)
            self.send_header("Content-Type", ctype + "; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            # embeddable only by pages on this computer (the Jarvus Terminal Fleet tab)
            self.send_header("Content-Security-Policy", "frame-ancestors 'self' http://127.0.0.1:* http://localhost:*")
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if not self._host_ok():
                return self._send(403, {"error": "local access only"})
            u = urlparse(self.path)
            q = parse_qs(u.query)
            try:
                if u.path in ("/", "/index.html"):
                    return self._send(200, page.replace("__TOKEN__", token), "text/html")
                if u.path == "/api/summary":
                    return self._send(200, provider.summary())
                if u.path == "/api/bots":
                    return self._send(200, provider.bots())
                if u.path.startswith("/api/bot/"):
                    return self._send(200, provider.bot(u.path.split("/api/bot/", 1)[1]))
                if u.path == "/api/brain":
                    return self._send(200, provider.brain())
                if u.path == "/api/chart":
                    return self._send(200, provider.chart(q.get("key", [""])[0]))
                if u.path == "/api/tickers":
                    return self._send(200, provider.tickers())
                if u.path == "/api/series":
                    return self._send(200, provider.series())
                if u.path == "/api/trades":
                    return self._send(200, provider.trades(int(q.get("limit", ["200"])[0])))
                if u.path == "/api/fills":
                    return self._send(200, provider.fills())
                if u.path == "/api/equity":
                    return self._send(200, provider.equity())
                if u.path == "/api/events":
                    return self._send(200, provider.events())
                if u.path == "/api/positions":
                    return self._send(200, provider.positions())
                return self._send(404, {"error": "not found"})
            except Exception as e:
                return self._send(500, {"error": f"{type(e).__name__}: {e}"})

        def do_POST(self):
            if not self._host_ok():
                return self._send(403, {"error": "local access only"})
            if self.headers.get("X-CSRF-Token") != token:
                return self._send(403, {"error": "missing or wrong CSRF token"})
            if urlparse(self.path).path != "/api/control":
                return self._send(404, {"error": "not found"})
            try:
                n = min(int(self.headers.get("Content-Length") or 0), 10_000)
                body = json.loads(self.rfile.read(n) or b"{}")
                return self._send(200, provider.control(body.get("command", ""), body.get("args") or {}))
            except Exception as e:
                return self._send(400, {"error": f"{type(e).__name__}: {e}"})
    return H


class QuietServer(ThreadingHTTPServer):
    """A browser closing a tab resets its open connection; that is normal, not an error worth a traceback."""

    def handle_error(self, request, client_address):
        import sys
        if isinstance(sys.exc_info()[1], (ConnectionResetError, ConnectionAbortedError, BrokenPipeError)):
            return
        super().handle_error(request, client_address)


def serve(provider: Provider, host: str = "127.0.0.1", port: int = 8765, block: bool = False):
    if host not in ("127.0.0.1", "localhost"):
        raise ValueError("the dashboard only listens on this computer (127.0.0.1)")
    with open(os.path.join(HERE, "dashboard.html"), encoding="utf-8") as fh:
        page = fh.read()
    token = secrets.token_urlsafe(24)
    httpd = QuietServer((host, port), make_handler(provider, token, page))
    httpd.daemon_threads = True
    if block:
        httpd.serve_forever()
        return httpd
    t = threading.Thread(target=httpd.serve_forever, name="dashboard", daemon=True)
    t.start()
    return httpd
