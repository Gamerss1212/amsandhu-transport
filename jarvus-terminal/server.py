#!/usr/bin/env python3
"""Jarvus Terminal HTTP server. Standard library only; no install step.

Serves a small JSON API and the single-page dashboard. Threaded, because a scan
fans out to many venues at once and a blocking request would freeze the UI.
"""

from __future__ import annotations

import json
import mimetypes
import time
import os
import socketserver
import sys
import threading
import traceback
import urllib.parse
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config
from engine import fleet
from engine import http as ehttp
from engine import automation, bots, learn, news, portfolio, research, scanner, store, swarm
from engine import indicators as eind
from engine import strategies as estrat

WEB_DIR = config.WEB_DIR
_scan_lock = threading.Lock()
_last_scan = {"data": None, "at": 0.0}

SETTINGS_PATH = os.path.join(config.DATA_DIR, "settings.json")


def load_settings() -> dict:
    try:
        with open(SETTINGS_PATH, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:                                    # noqa: BLE001
        return {}


def save_settings(d: dict) -> dict:
    os.makedirs(os.path.dirname(SETTINGS_PATH), exist_ok=True)
    cur = load_settings()
    cur.update(d or {})
    tmp = SETTINGS_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(cur, fh, indent=2)
    os.replace(tmp, SETTINGS_PATH)
    return cur


def _scan_for_scheduler():
    """What the background scheduler runs each cycle."""
    with _scan_lock:
        data = scanner.scan(write=True)
        _last_scan["data"] = data
        _last_scan["at"] = time.time()
    return data, data.get("_swarm_full") or {"by_symbol": {
        m["symbol"]: m.get("swarm") for m in data.get("markets", []) if m.get("swarm")}}


def _json_default(o):
    if isinstance(o, datetime):
        return o.strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        return dict(o)          # sqlite3.Row
    except Exception:           # noqa: BLE001
        return str(o)


class Handler(BaseHTTPRequestHandler):
    server_version = "JarvusTerminal/1.0"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):     # quieter console
        if "/api/" in (self.path or ""):
            sys.stderr.write(f"  {self.command} {self.path}\n")

    # -- helpers ------------------------------------------------------------
    def _send(self, code: int, body: bytes, ctype: str, extra: dict = None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _json(self, obj, code: int = 200):
        self._send(code, json.dumps(obj, default=_json_default).encode("utf-8"),
                   "application/json; charset=utf-8")

    def _file(self, rel: str):
        path = os.path.normpath(os.path.join(WEB_DIR, rel.lstrip("/")))
        if not path.startswith(WEB_DIR) or not os.path.isfile(path):
            return self._send(404, b"not found", "text/plain; charset=utf-8")
        ctype = mimetypes.guess_type(path)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript", "application/json"):
            ctype += "; charset=utf-8"
        with open(path, "rb") as fh:
            self._send(200, fh.read(), ctype)

    def _allowed_hosts(self):
        hosts = {f"127.0.0.1:{config.PORT}", f"localhost:{config.PORT}", f"{config.HOST}:{config.PORT}"}
        return hosts

    def _guard(self, is_post: bool) -> bool:
        """Only this app's own page may talk to this server.

        The server listens on your machine only, but any website open in your browser
        can still try to send requests to 127.0.0.1. Checking the Host header stops
        DNS-rebinding tricks, and requiring a custom header on every change stops a
        foreign page from pressing buttons, because browsers will not let another
        site add that header without this server's permission, which it never gives.
        """
        host = (self.headers.get("Host") or "").strip().lower()
        if host not in self._allowed_hosts():
            self._send(403, b"forbidden host", "text/plain; charset=utf-8")
            return False
        if is_post:
            origin = self.headers.get("Origin")
            if origin and origin.lower().replace("http://", "", 1) not in self._allowed_hosts():
                self._send(403, b"forbidden origin", "text/plain; charset=utf-8")
                return False
            if self.headers.get("X-Jarvus") != "1":
                self._send(403, b"missing app header", "text/plain; charset=utf-8")
                return False
        return True

    # -- routes -------------------------------------------------------------
    def do_GET(self):
        if not self._guard(False):
            return
        try:
            parsed = urllib.parse.urlparse(self.path)
            route, q = parsed.path, urllib.parse.parse_qs(parsed.query)
            one = lambda k, d=None: (q.get(k) or [d])[0]

            if route in ("/", "/index.html"):
                return self._file("index.html")
            if route.startswith("/static/"):
                # served from web/static/, so the path is used as-is under WEB_DIR
                return self._file(route)

            if route == "/api/health":
                return self._json({
                    "ok": True, "time": store.now_iso(),
                    "counts": store.counts(),
                    "fee_tiers": list(config.FEE_TIERS),
                    "default_fee_tier": config.DEFAULT_FEE_TIER,
                    "deep_n": config.DEEP_SCAN_N,
                    "resolve_horizon_h": config.RESOLVE_HORIZON_H,
                    "network_errors": list(ehttp.last_errors().items())[:5],
                    "strategies": len(estrat.REGISTRY),
                    "indicators": len(eind.CATALOG),
                    "research": research.latest_run(),
                    "automation": (automation.get_scheduler().status()
                                   if automation.get_scheduler() else {"enabled": False}),
                    "settings": load_settings(),
                    "bots_running": bots.load_settings()["running"],
                })

            if route == "/api/scan":
                force = one("force") == "1"
                deep = int(one("n", config.DEEP_SCAN_N))
                tier = one("fee_tier", config.DEFAULT_FEE_TIER)
                acct = float(one("account", config.DEFAULT_ACCOUNT))
                import time as _t
                with _scan_lock:
                    fresh = (_last_scan["data"] and not force
                             and (_t.time() - _last_scan["at"]) < config.CACHE_TTL_UNIVERSE
                             and _last_scan["data"].get("fee_tier") == tier
                             and _last_scan["data"]["universe"]["analysed"] == deep)
                    if not fresh:
                        _last_scan["data"] = scanner.scan(deep_n=deep, fee_tier=tier, account=acct)
                        _last_scan["at"] = _t.time()
                return self._json(_last_scan["data"])

            if route == "/api/market":
                sym = one("symbol")
                if not sym:
                    return self._json({"error": "symbol required"}, 400)
                return self._json(scanner.market_detail(
                    sym, one("venue", "okx"), one("fee_tier", config.DEFAULT_FEE_TIER),
                    float(one("account", config.DEFAULT_ACCOUNT))))

            if route == "/api/news":
                return self._json(news.headlines(int(one("limit", config.NEWS_MAX_ITEMS))))

            if route == "/api/learning":
                return self._json(learn.summary())

            if route == "/api/journal":
                return self._json({"rows": [dict(r) for r in store.journal_rows()]})

            if route == "/api/predictions":
                return self._json({"rows": [dict(r) for r in store.recent_predictions(one("symbol"), 100)]})

            if route == "/api/strategies":
                return self._json({"roster": swarm.roster(),
                                   "custom_load": estrat.load_custom(),
                                   "count": len(estrat.REGISTRY)})

            if route == "/api/indicators":
                return self._json({"catalog": [
                    {"name": n, "group": spec.get("group", "other"),
                     "params": spec.get("params", {}), "multi": bool(spec.get("multi")),
                     "scalar": bool(spec.get("scalar"))}
                    for n, spec in sorted(eind.CATALOG.items())]})

            if route == "/api/indicator":
                sym, name = one("symbol"), one("name")
                if not sym or not name:
                    return self._json({"error": "symbol and name are required"}, 400)
                params = {}
                for k, v in q.items():
                    if k in ("symbol", "name", "venue", "tf"):
                        continue
                    try:
                        params[k] = float(v[0]) if "." in v[0] else int(v[0])
                    except ValueError:
                        params[k] = v[0]
                from engine import marketdata as _md
                cs = _md.candles(sym, one("venue", "okx"), one("tf", config.SETUP_TF), config.CANDLES)
                if not cs:
                    return self._json({"error": "no candles"}, 404)
                try:
                    out = eind.compute(name, cs, **params)
                except Exception as exc:                 # noqa: BLE001
                    return self._json({"error": str(exc)}, 400)
                def pack(series):
                    return [None if v is None else (round(v, 10) if isinstance(v, (int, float)) else v)
                            for v in series]
                if isinstance(out, tuple):
                    data = {f"series_{i}": pack(x) if isinstance(x, list) else x
                            for i, x in enumerate(out)}
                elif isinstance(out, list):
                    data = {"series_0": pack(out)}
                else:
                    data = {"scalar": out}
                return self._json({"name": name, "params": params,
                                   "t": [c["ts"].strftime("%Y-%m-%dT%H:%MZ") for c in cs], **data})

            if route == "/api/research":
                return self._json(research.summary(one("asset")))

            if route == "/api/portfolio":
                name = one("name", "paper")
                prices = {}
                if _last_scan["data"]:
                    prices = {m["symbol"]: m["price"] for m in _last_scan["data"].get("markets", [])
                              if not m.get("error")}
                return self._json({"portfolios": portfolio.list_all(),
                                   "performance": portfolio.performance(name, prices),
                                   "readiness": portfolio.readiness(name)})

            if route == "/api/alerts":
                return self._json({"rules": automation.rules(),
                                   "alerts": automation.recent_alerts(int(one("limit", 80))),
                                   "unseen": len(automation.recent_alerts(500, unseen_only=True))})

            if route == "/api/automation":
                sch = automation.get_scheduler()
                return self._json(sch.status() if sch else {"enabled": False, "alive": False})

            if route == "/api/settings":
                return self._json(load_settings())

            if route == "/api/brain":
                from engine import brain as ebrain
                eng = bots.get_engine()
                st = bots.load_settings()
                return self._json({"summary": ebrain.get().summary(), "agents": ebrain.get().agents(),
                                   "votes": (eng.brain_last[-60:][::-1] if eng else []),
                                   "vote_count": eng.brain_votes if eng else 0,
                                   "mode": st.get("brain_mode")})

            if route == "/api/learn":
                book = os.path.join(os.path.dirname(os.path.abspath(bots.__file__)), "research_book.json")
                try:
                    with open(book, encoding="utf-8") as fh:
                        data = json.load(fh)
                except Exception:                            # noqa: BLE001
                    data = {"error": "the research book is missing from this install"}
                data["strategies"] = [{"name": sp.name, "group": sp.group,
                                       "family": swarm.FAMILY.get(sp.group, sp.group),
                                       "description": sp.description, "source": sp.source}
                                      for sp in sorted(estrat.REGISTRY.values(), key=lambda x: x.name)]
                data["bots"] = [{"name": d["name"], "families": d["families"], "playbook": d["playbook"]}
                                for d in bots.BOT_DEFS]
                return self._json(data)

            if route == "/api/library":
                return self._json(fleet.library())
            if route.startswith("/api/library/"):
                return self._json(fleet.strategy(route.rsplit("/", 1)[1]))
            if route == "/api/fleet/status":
                return self._json(fleet.status())

            if route == "/api/bots":
                eng = bots.get_engine()
                return self._json(eng.status() if eng else {"error": "bots are not running in this process"})

            return self._send(404, b"not found", "text/plain; charset=utf-8")
        except Exception:                                    # noqa: BLE001
            traceback.print_exc()
            return self._json({"error": traceback.format_exc(limit=3)}, 500)

    def do_POST(self):
        if not self._guard(True):
            return
        try:
            parsed = urllib.parse.urlparse(self.path)
            length = int(self.headers.get("Content-Length") or 0)
            payload = json.loads(self.rfile.read(length) or b"{}") if length else {}

            if parsed.path == "/api/fleet/start":
                return self._json(fleet.start(str(payload.get("stage", "250")), payload.get("balance")))
            if parsed.path == "/api/fleet/stop":
                return self._json(fleet.stop())
            if parsed.path == "/api/fleet/command":
                return self._json(fleet.command(str(payload.get("command", "")), payload.get("args") or {}))

            if parsed.path == "/api/resolve":
                return self._json(learn.resolve_due(int(payload.get("limit", 100))))

            if parsed.path == "/api/journal":
                if payload.get("close_id"):
                    r = store.journal_close(int(payload["close_id"]), float(payload["exit_price"]),
                                            payload.get("notes", ""))
                    return self._json({"ok": r is not None, "r_multiple": r})
                jid = store.journal_add({"opened_at": store.now_iso(), **payload})
                return self._json({"ok": True, "id": jid})

            if parsed.path == "/api/settings":
                return self._json(save_settings(payload))

            if parsed.path == "/api/strategies/toggle":
                n = swarm.set_enabled(payload.get("set") or {})
                _last_scan["data"] = None            # the roster changed; the cached scan is stale
                return self._json({"ok": True, "changed": n, "roster": swarm.roster()})

            if parsed.path == "/api/research/run":
                research.run_background(bars=int(payload.get("bars", 3000)),
                                        market_count=int(payload.get("markets", 12)),
                                        split=float(payload.get("split", 0.6)),
                                        asset="stock" if payload.get("asset") == "stock" else "crypto")
                return self._json({"ok": True, "started": True,
                                   "note": "Running in the background. It backtests every strategy "
                                           "on every market over deep history, so it takes minutes, "
                                           "not seconds. The Research tab updates when it lands."})

            if parsed.path == "/api/portfolio/open":
                return self._json(portfolio.open_position(
                    payload.get("portfolio", "paper"), payload["symbol"], float(payload["price"]),
                    float(payload["stop"]), float(payload["target"]) if payload.get("target") else None,
                    payload.get("strategy"), payload.get("grade"), payload.get("gate_label"),
                    payload.get("consensus"), payload.get("notes", "")))

            if parsed.path == "/api/portfolio/close":
                return self._json(portfolio.close_position(
                    int(payload["id"]), float(payload["price"]), payload.get("reason", "manual")))

            if parsed.path == "/api/portfolio/create":
                return self._json(portfolio.create(
                    payload["name"], float(payload.get("starting_cash", config.DEFAULT_ACCOUNT)),
                    payload.get("kind", "paper"), payload.get("fee_bps"),
                    payload.get("risk_pct"), payload.get("notes", "")))

            if parsed.path == "/api/alerts/rule":
                if payload.get("delete_id"):
                    automation.delete_rule(int(payload["delete_id"]))
                    return self._json({"ok": True})
                if "enabled" in payload and payload.get("id"):
                    automation.set_rule_enabled(int(payload["id"]), bool(payload["enabled"]))
                    return self._json({"ok": True})
                rid = automation.add_rule(**payload)
                return self._json({"ok": True, "id": rid})

            if parsed.path == "/api/alerts/seen":
                return self._json({"ok": True, "marked": automation.mark_seen(payload.get("ids"))})

            if parsed.path == "/api/automation":
                sch = automation.get_scheduler(_scan_for_scheduler,
                                               int(payload.get("interval_s", 300)))
                if payload.get("enabled"):
                    sch.start(int(payload.get("interval_s", sch.interval_s)))
                else:
                    sch.stop()
                return self._json(sch.status())

            if parsed.path.startswith("/api/bots/"):
                eng = bots.get_engine()
                if not eng:
                    return self._json({"error": "bots are not running in this process"}, 503)
                action = parsed.path[len("/api/bots/"):]
                if action == "run":
                    return self._json(eng.run())
                if action == "stop":
                    return self._json(eng.stop())
                if action == "close-all":
                    return self._json({**eng.close_all(), "status": eng.status()})
                if action == "scan-now":
                    eng.next_cycle_at = 0
                    eng._wake.set()
                    return self._json({"ok": True})
                if action == "reset":
                    money = float(payload.get("practice_money") or bots.load_settings()["practice_money"])
                    if not 0 < money <= 1e12:
                        return self._json({"error": "practice money must be more than $0"}, 400)
                    eng.close_all("reset")
                    return self._json(eng.reset(money))
                if action == "set-money":
                    try:
                        money = float(payload.get("practice_money"))
                    except (TypeError, ValueError):
                        return self._json({"error": "type an amount"}, 400)
                    if not 0 < money <= 1e12:
                        return self._json({"error": "practice money must be more than $0"}, 400)
                    return self._json(eng.set_money(money, bool(payload.get("close_trades"))))
                if action == "settings":
                    bots.save_settings(payload)
                    return self._json(eng.status())
                if action == "bot":
                    r = eng.set_bot(payload.get("key", ""), payload.get("enabled"), payload.get("overrides"))
                    return self._json(r if r.get("error") else eng.status())
                return self._send(404, b"not found", "text/plain; charset=utf-8")

            if parsed.path == "/api/cache/clear":
                ehttp.cache_clear()
                _last_scan["data"] = None
                return self._json({"ok": True})

            return self._send(404, b"not found", "text/plain; charset=utf-8")
        except Exception:                                    # noqa: BLE001
            traceback.print_exc()
            return self._json({"error": traceback.format_exc(limit=3)}, 500)


class QuietServer(ThreadingHTTPServer):
    """A browser closing a tab resets its open connection; that is normal, not an error worth a traceback."""

    def handle_error(self, request, client_address):
        import sys
        if isinstance(sys.exc_info()[1], (ConnectionResetError, ConnectionAbortedError, BrokenPipeError)):
            return
        super().handle_error(request, client_address)


def serve():
    store.conn()
    loaded = estrat.load_custom()
    portfolio.ensure_default()
    automation.seed_default_rules()
    if loaded:
        for f, msg in loaded.items():
            print(f"  custom strategy {f}: {msg}", flush=True)
    httpd = QuietServer((config.HOST, config.PORT), Handler)
    httpd.daemon_threads = True
    # The bots start their threads only once the port is ours, so a second copy of
    # the app that fails to bind can never trade the same practice account twice.
    engine = bots.get_engine(lambda: _scan_for_scheduler()[0])
    engine.boot()
    fleet.boot()
    url = f"http://{config.HOST}:{config.PORT}"
    print(f"\n  Jarvus Terminal is running at  {url}\n", flush=True)
    print(f"  {len(estrat.REGISTRY)} strategies | {len(eind.CATALOG)} indicators | "
          f"top {config.DEEP_SCAN_N} of every liquid market | fee tier '{config.DEFAULT_FEE_TIER}'", flush=True)
    print("  Ctrl-C to stop.\n", flush=True)
    if bots.load_settings()["running"]:
        print("  Autopilot: the seven Jarvus bots are running by themselves.\n", flush=True)
    else:
        print("  The Jarvus bots are stopped (you pressed Stop). Press Run bots to turn them back on.\n", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n  stopped.\n")
    finally:
        engine.shutdown()
        httpd.server_close()


if __name__ == "__main__":
    serve()
