#!/usr/bin/env python3
"""Jarvus web server: the app's one page and its JSON API. Standard library only.

Routes
    GET  /                          the app (web/index.html)
    GET  /app.css, /app.js          its style and code
    GET  /api/f/<name>              live fleet data (summary, bots, bot/<id>, brain, chart, book, tickers, series,
                                    trades, fills, equity, events, positions): read from the running fleet, or
                                    from its database while it is stopped
    GET  /api/status                autopilot, account, pause/emergency, live-money flag
    GET  /api/library[/<id>]        the strategy library
    GET  /api/results               every measured result shipped with this build
    GET  /api/brokers               which brokers are connected (never their keys)
    GET  /api/live                  live-money status
    POST /api/fleet/start|stop      turn the autopilot on or off
    POST /api/command               pause, resume, emergency stop, balance, enable/disable a bot, live controls
    POST /api/broker/save|test|remove

Only this app's own page can talk to it: the Host header must be this computer (stops DNS
rebinding), and every POST must carry the X-Jarvus header and, when a browser sends one, a local
Origin (a foreign web page cannot add that header). Request bodies are never logged: the broker
form sends API keys here, and they go straight to the encrypted secret store.
"""

from __future__ import annotations

import http.client
import json
import mimetypes
import os
import sys
import traceback
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config                      # noqa: E402
from engine import fleet           # noqa: E402

WEB_DIR = config.WEB_DIR
FLEET_VIEWS = {"summary", "bots", "brain", "chart", "book", "tickers", "series", "trades", "fills", "equity", "events",
               "positions"}
_provider = None


def _offline_provider():
    """The fleet dashboard's data layer over the fleet database, for when the fleet is stopped."""
    global _provider
    if _provider is None:
        from mab.dashboard import Provider
        _provider = Provider(fleet._db_storage())
    return _provider


def _offline_view(name: str, q: dict):
    p = _offline_provider()
    one = lambda k, d="": (q.get(k) or [d])[0]              # noqa: E731
    if name.startswith("bot/"):
        return p.bot(urllib.parse.unquote(name[4:]))
    if name == "chart":
        return p.chart(one("key"))
    if name == "book":
        return p.book(one("key"))
    if name == "trades":
        return p.trades(int(one("limit", "200")))
    if name == "bots":
        return _registry_bots(p.bots())
    return getattr(p, name)()


_registry = None


def _registry_bots(health: list) -> list:
    """Every configured bot with its strategy and market, plus its last saved health."""
    global _registry
    if _registry is None:
        with open(fleet.REGISTRY, encoding="utf-8") as fh:
            reg = json.load(fh)["bots"]
        cat = {s["id"]: s for s in fleet.catalog()["strategies"]}
        _registry = [{"bot_id": b["bot_id"], "name": b.get("name", b["bot_id"]), "strategy_id": b["strategy_id"],
                      "family": (cat.get(b["strategy_id"]) or {}).get("family"), "venue": b["venue"],
                      "instrument": b["instrument"], "tf": (cat.get(b["strategy_id"]) or {}).get("timeframe")}
                     for b in reg if b.get("enabled", True)]
    h = {x["bot_id"]: x for x in health}
    return [dict(b, state=(h.get(b["bot_id"]) or {}).get("state") or "stopped",
                 message=(h.get(b["bot_id"]) or {}).get("message") or "the fleet is stopped",
                 last_decision=(h.get(b["bot_id"]) or {}).get("last_decision"), position=None) for b in _registry]


def fleet_view(name: str, query: str):
    """(code, body bytes) for /api/f/<name>: proxied to the running fleet, else read from its database."""
    q = urllib.parse.parse_qs(query)
    if not (name in FLEET_VIEWS or (name.startswith("bot/") and len(name) < 120)):
        return 404, b'{"error": "not found"}'
    if fleet.running():
        try:
            c = http.client.HTTPConnection("127.0.0.1", fleet.PORT, timeout=8)
            c.request("GET", "/api/" + name + ("?" + query if query else ""), headers={"Host": f"127.0.0.1:{fleet.PORT}"})
            r = c.getresponse()
            body = r.read()
            c.close()
            if r.status == 200:
                return 200, body
        except OSError:
            pass                                              # starting up or restarting: fall back to the database
    try:
        data = _offline_view(name, q)
    except Exception as e:                                    # noqa: BLE001
        return 200, json.dumps({"error": f"{type(e).__name__}: {e}", "offline": True}).encode()
    if isinstance(data, dict):
        data.setdefault("offline", True)
    return 200, json.dumps(data, default=str).encode()


class Handler(BaseHTTPRequestHandler):
    server_version = "Jarvus/6"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):                        # quiet: the window is for people, not access logs
        pass

    # -- helpers ------------------------------------------------------------
    def _send(self, code: int, body: bytes, ctype: str):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass

    def _json(self, obj, code: int = 200):
        self._send(code, json.dumps(obj, default=str).encode("utf-8"), "application/json; charset=utf-8")

    def _file(self, rel: str):
        path = os.path.normpath(os.path.join(WEB_DIR, rel.lstrip("/")))
        if not path.startswith(os.path.normpath(WEB_DIR) + os.sep) or not os.path.isfile(path):
            return self._send(404, b"not found", "text/plain; charset=utf-8")
        ctype = mimetypes.guess_type(path)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript", "application/json"):
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

    def _body(self) -> dict:
        n = min(int(self.headers.get("Content-Length") or 0), 20_000)
        try:
            d = json.loads(self.rfile.read(n) or b"{}")
        except ValueError:
            return {}
        return d if isinstance(d, dict) else {}

    # -- routes -------------------------------------------------------------
    def do_GET(self):
        if not self._guard(False):
            return
        try:
            u = urllib.parse.urlparse(self.path)
            route = u.path
            if route in ("/", "/index.html"):
                return self._file("index.html")
            if route in ("/app.css", "/app.js"):
                return self._file(route)
            if route.startswith("/api/f/"):
                code, body = fleet_view(route[len("/api/f/"):], u.query)
                return self._send(code, body, "application/json; charset=utf-8")
            if route == "/api/status":
                return self._json(fleet.status())
            if route == "/api/library":
                return self._json(fleet.library())
            if route.startswith("/api/library/"):
                return self._json(fleet.strategy(urllib.parse.unquote(route[len("/api/library/"):])))
            if route == "/api/results":
                return self._json(fleet.results())
            if route == "/api/brokers":
                return self._json(fleet.brokers())
            if route == "/api/live":
                return self._json(fleet.live())
            return self._send(404, b"not found", "text/plain; charset=utf-8")
        except Exception as e:                                # noqa: BLE001
            traceback.print_exc()
            return self._json({"error": f"{type(e).__name__}: {e}"}, 500)

    def do_POST(self):
        if not self._guard(True):
            return
        route = urllib.parse.urlparse(self.path).path
        try:
            b = self._body()
            if route == "/api/fleet/start":
                return self._json(fleet.start(str(b.get("stage") or "250")))
            if route == "/api/fleet/stop":
                return self._json(fleet.stop())
            if route == "/api/command":
                return self._json(fleet.command(str(b.get("command") or ""), b.get("args") or {}))
            if route == "/api/broker/save":
                return self._json(fleet.broker_save(str(b.get("name") or ""), b.get("key") or "", b.get("secret") or "",
                                                    b.get("options") or {}))
            if route == "/api/broker/test":
                return self._json(fleet.broker_test(str(b.get("name") or "")))
            if route == "/api/broker/remove":
                return self._json(fleet.broker_remove(str(b.get("name") or "")))
            return self._send(404, b"not found", "text/plain; charset=utf-8")
        except ValueError as e:                               # a message meant for the person using the app
            return self._json({"error": str(e)}, 400)
        except Exception as e:                                # noqa: BLE001 - never echo the request body
            print(f"  {route}: {type(e).__name__}: {e}", flush=True)
            return self._json({"error": f"{type(e).__name__}: {e}"}, 500)


class QuietServer(ThreadingHTTPServer):
    """A browser closing a tab resets its open connection; that is normal, not an error worth a traceback."""
    daemon_threads = True

    def handle_error(self, request, client_address):
        if isinstance(sys.exc_info()[1], (ConnectionResetError, ConnectionAbortedError, BrokenPipeError)):
            return
        super().handle_error(request, client_address)


def serve():
    httpd = QuietServer((config.HOST, config.PORT), Handler)
    # the fleet starts only once the port is ours, so a second copy of the app can never run a second fleet
    fleet.boot()
    print(f"\n  Jarvus is running at  http://{config.HOST}:{config.PORT}\n  Ctrl-C to stop.\n", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n  stopped.\n")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    serve()
