#!/usr/bin/env python3
"""Jarvus Terminal HTTP server. Standard library only; no install step.

Serves a small JSON API and the single-page dashboard. Threaded, because a scan
fans out to many venues at once and a blocking request would freeze the UI.
"""

from __future__ import annotations

import json
import mimetypes
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
from engine import http as ehttp
from engine import learn, news, scanner, store

WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")
_scan_lock = threading.Lock()
_last_scan = {"data": None, "at": 0.0}


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

    # -- routes -------------------------------------------------------------
    def do_GET(self):
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

            return self._send(404, b"not found", "text/plain; charset=utf-8")
        except Exception:                                    # noqa: BLE001
            traceback.print_exc()
            return self._json({"error": traceback.format_exc(limit=3)}, 500)

    def do_POST(self):
        try:
            parsed = urllib.parse.urlparse(self.path)
            length = int(self.headers.get("Content-Length") or 0)
            payload = json.loads(self.rfile.read(length) or b"{}") if length else {}

            if parsed.path == "/api/resolve":
                return self._json(learn.resolve_due(int(payload.get("limit", 100))))

            if parsed.path == "/api/journal":
                if payload.get("close_id"):
                    r = store.journal_close(int(payload["close_id"]), float(payload["exit_price"]),
                                            payload.get("notes", ""))
                    return self._json({"ok": r is not None, "r_multiple": r})
                jid = store.journal_add({"opened_at": store.now_iso(), **payload})
                return self._json({"ok": True, "id": jid})

            if parsed.path == "/api/cache/clear":
                ehttp.cache_clear()
                _last_scan["data"] = None
                return self._json({"ok": True})

            return self._send(404, b"not found", "text/plain; charset=utf-8")
        except Exception:                                    # noqa: BLE001
            traceback.print_exc()
            return self._json({"error": traceback.format_exc(limit=3)}, 500)


def serve():
    store.conn()
    httpd = ThreadingHTTPServer((config.HOST, config.PORT), Handler)
    httpd.daemon_threads = True
    url = f"http://{config.HOST}:{config.PORT}"
    print(f"\n  Jarvus Terminal is running at  {url}\n", flush=True)
    print(f"  scanning the top {config.DEEP_SCAN_N} of every liquid market, "
          f"fee tier '{config.DEFAULT_FEE_TIER}', {config.RESOLVE_HORIZON_H}h grading horizon", flush=True)
    print("  Ctrl-C to stop.\n", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n  stopped.\n")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    serve()
