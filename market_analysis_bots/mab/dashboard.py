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
ALLOWED_COMMANDS = {"deploy_readiness", "deploy_start", "deploy_pause", "deploy_resume", "deploy_stop", "close_all_positions",
                    "create_bot", "update_limits", "live_authorize", "live_revoke", "research_autopilot", "paper_balance",
                    "connection_test", "connection_sync", "reconcile", "deployments", "brain_snapshot", "brain_promote",
                    "strategy_approve", "strategy_retire", "reload_models", "drift_check", "connections_changed",
"set_fee_profile", "live_status", "live_eligibility", "live_arm", "live_disarm", "live_close_all", "pause", "resume", "emergency_stop", "clear_emergency", "deposit", "withdraw", "set_balance",
                    "enable_bot", "disable_bot", "test_order"}


class Provider:
    """Live view of a Fleet in this process, falling back to the database."""

    def __init__(self, storage: Storage, fleet=None):
        self.storage = storage
        self.fleet = fleet
        self._books: dict = {}
        self._book_lock = threading.Lock()

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
        return {"key": key, "t": times, "o": [s.bars[t].open for t in times], "c": [s.bars[t].close for t in times],
                "h": [s.bars[t].high for t in times], "l": [s.bars[t].low for t in times], "step": s.step}

    def book(self, key: str, depth: int = 8) -> dict:
        """Live top of the order book for a crypto series (cached a few seconds, one request at most)."""
        if self.fleet is None:
            return {"key": key, "bids": [], "asks": [], "note": "fleet not running"}
        venue, symbol = (key.split("/") + ["", ""])[:2]
        ad = self.fleet.hub.adapters.get(venue)
        if ad is None or venue == "yahoo":
            return {"key": key, "bids": [], "asks": [], "note": "no free order book for stocks: stock fills are synthetic"}
        now = time.time()
        hit = self._books.get(key)
        if hit and now - hit[0] < 4.0:
            return hit[1]
        with self._book_lock:
            hit = self._books.get(key)
            if hit and time.time() - hit[0] < 4.0:
                return hit[1]
            try:
                bk = ad.book(symbol, depth=depth)
                out = {"key": key, "bids": bk.bids[:depth], "asks": bk.asks[:depth], "time": bk.event_time} if bk else \
                    {"key": key, "bids": [], "asks": [], "note": "order book unavailable"}
            except Exception as e:                                      # noqa: BLE001
                out = {"key": key, "bids": [], "asks": [], "note": f"order book unavailable ({type(e).__name__})"}
            self._books[key] = (time.time(), out)
            return out

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

    # ---------------------------------------------------------------- views for the three-page app
    def deployments(self) -> list:
        if self.fleet is None:
            return []
        f = self.fleet
        rows = f.deps.list()
        keep = [d for d in rows if d["state"] != "stopped"] + [d for d in rows if d["state"] == "stopped"][-20:]
        return [f.deployment_view(d) for d in keep]

    def user_bots(self) -> list:
        if self.fleet is None:
            return []
        out = []
        for b in self.fleet.deps.bots():
            br = self.fleet.bots.get(b["bot_id"])
            dep = self.fleet.dep_cache.get(b["bot_id"]) or self.fleet.deps.latest_for(b["bot_id"])
            out.append(dict(b, loaded=br is not None, strategy_name=(br.c.definition.get("name") if br else None),
                            timeframe=br.tf if br else None, data_state=br.state if br else None,
                            last_decision=br.last_decision if br else None,
                            deployment=None if dep is None else {k: dep.get(k) for k in (
                                "deployment_id", "state", "mode", "connection_id", "allocation", "limits")}))
        return out

    def scanner(self) -> list:
        """Every bot's latest evaluation: the signal, how many rule conditions held, the brain's current estimate for
        it (with its evidence), the volatility gate for its market, data freshness. No invented confidence."""
        if self.fleet is None:
            return []
        f = self.fleet
        out = []
        for bid, br in list(f.bots.items()):
            sig = br.last_signal or {}
            rules = sig.get("rules") or []
            entry = [r for r in rules if r.get("group") == "entry"]
            passed = sum(1 for r in entry if r.get("passed"))
            try:
                est = f.brain._combined(f._bkey(br), br.symbol)
                est = {"edge_r": round(est["mean"], 3), "sd_r": round(est["sd"], 3), "evidence_trades": round(est["n_eff"], 1)}
            except Exception:                                           # noqa: BLE001
                est = None
            gate = f.brain.gates.get(br.symbol)
            age = (int(time.time() * 1000) - (br.last_data + 0)) / 1000 if br.last_data else None
            dep = f.dep_cache.get(bid)
            out.append({"bot_id": bid, "user": bool(getattr(br, "user", False)), "name": br.cfg.get("name", bid),
                        "strategy_id": br.c.id, "strategy": br.c.definition.get("name"),
                        "family": br.c.definition.get("family"), "venue": br.venue, "symbol": br.symbol, "tf": br.tf,
                        "asset": "stock" if br.venue == "yahoo" else "crypto", "state": br.state,
                        "action": sig.get("action"), "reason": sig.get("reason"), "bar_time": sig.get("bar_time"),
                        "conditions": {"passed": passed, "total": len(entry)}, "brain": est,
                        "gate": None if not gate else {"state": gate.get("state"), "time": gate.get("time"),
                                                       "evidence": gate.get("evidence")},
                        "data_age_s": round(age, 1) if age is not None else None,
                        "position": br.tm.pos is not None, "deployed": bool(dep), "mode": dep["mode"] if dep else None,
                        "benched": bid in f.brain.bench})
        return out

    def candles(self, venue: str, symbol: str, tf: str, n: int = 300) -> dict:
        if self.fleet is None:
            return {"error": "the bot engine is not running", "t": []}
        s = self.fleet.hub.get(venue, symbol, tf)
        if s is not None and len(s.times) >= min(n, 50):
            times = s.times[-n:]
            b = [s.bars[t] for t in times]
            return {"venue": venue, "symbol": symbol, "tf": tf, "source": getattr(b[-1], "provenance", venue) if b else venue,
                    "t": times, "o": [x.open for x in b], "h": [x.high for x in b], "l": [x.low for x in b],
                    "c": [x.close for x in b], "v": [x.volume for x in b], "status": s.status(), "live": True}
        key = (venue, symbol, tf, n)
        hit = self._books.get(("candles",) + key)
        if hit and time.time() - hit[0] < 30:
            return hit[1]
        ad = self.fleet.hub.adapters.get(venue)
        if ad is None or not ad.supports(tf):
            return {"error": f"{venue} has no {tf} bars", "t": []}
        try:
            b = ad.bars(symbol, tf, limit=min(n, 300))
        except Exception as e:                                          # noqa: BLE001
            return {"error": f"market data unavailable: {type(e).__name__}: {e}", "t": []}
        out = {"venue": venue, "symbol": symbol, "tf": tf, "source": getattr(b[-1], "provenance", venue) if b else venue,
               "t": [x.event_time for x in b], "o": [x.open for x in b], "h": [x.high for x in b], "l": [x.low for x in b],
               "c": [x.close for x in b], "v": [x.volume for x in b], "status": "fetched on request", "live": False}
        self._books[("candles",) + key] = (time.time(), out)
        return out

    def markets(self) -> list:
        """Markets the owner can build bots on: everything the fleet already follows, plus its registry's stocks."""
        if self.fleet is None:
            return []
        seen, out = set(), []
        for b in self.fleet.bot_cfgs:
            k = (b["venue"], b["instrument"])
            if k in seen:
                continue
            seen.add(k)
            inst = self.fleet.registry.get(*k) or {}
            out.append({"venue": k[0], "symbol": k[1], "asset": "stock" if k[0] == "yahoo" else "crypto",
                        "quote": inst.get("quote"), "demo": k[0] == "demo"})
        out.sort(key=lambda x: (x["asset"], x["symbol"]))
        return out

    def health(self) -> dict:
        if self.fleet is None:
            return {"running": False}
        f = self.fleet
        h = f.system_health()
        hub = f.hub.snapshot()
        series = []
        now = int(time.time() * 1000)
        for s in hub.get("series", [])[:400]:
            row = {k: s.get(k) for k in ("key", "status", "last_bar", "bars", "need", "subscribers", "fetches",
                                         "last_fetch_error", "last_fetch_ok", "counts", "last_issue") if k in s}
            if s.get("last_bar"):
                tf = s["key"].split("/")[-1]
                from mab.clock import tf_ms
                row["data_age_s"] = round((now - (s["last_bar"] + tf_ms(tf))) / 1000, 1)
            series.append(row)
        from mab.hardware import cpu_percent, describe
        h.update({"series_detail": series, "http": hub.get("http"), "hardware": describe(),
                  "cpu_percent": cpu_percent(), "execution": f.engine.health(),
                  "connections": [{k: c.get(k) for k in ("connection_id", "label", "provider", "environment", "status",
                                                          "last_sync", "last_error")} for c in f.conns.list()],
                  "rate_limits": f.engine.health().get("rate_limits"), "live_brain": f.live_brain_version,
                  "research_autopilot": f.research_autopilot})
        return h

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


def make_handler(provider: Provider, token: str, page: str, api_token: Optional[str] = None):
    class H(BaseHTTPRequestHandler):
        server_version = "mab-dashboard"

        def log_message(self, *a):
            pass

        def _host_ok(self) -> bool:
            host = (self.headers.get("Host") or "").split(":")[0]
            if host not in ("127.0.0.1", "localhost"):
                return False
            if api_token:                     # supervised: only the app that started this fleet may talk to it
                got = self.headers.get("Authorization") or ""
                return secrets.compare_digest(got, f"Bearer {api_token}")
            return True

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
                if u.path == "/api/book":
                    return self._send(200, provider.book(q.get("key", [""])[0]))
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
                if u.path == "/api/deployments":
                    return self._send(200, provider.deployments())
                if u.path == "/api/user_bots":
                    return self._send(200, provider.user_bots())
                if u.path == "/api/scanner":
                    return self._send(200, provider.scanner())
                if u.path == "/api/candles":
                    one = lambda k, d="": (q.get(k) or [d])[0]                     # noqa: E731
                    return self._send(200, provider.candles(one("venue"), one("symbol"), one("tf", "5m"),
                                                            max(20, min(1000, int(one("n", "300"))))))
                if u.path == "/api/markets":
                    return self._send(200, provider.markets())
                if u.path == "/api/health":
                    return self._send(200, provider.health())
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


def serve(provider: Provider, host: str = "127.0.0.1", port: int = 8765, block: bool = False, token: Optional[str] = None):
    if host not in ("127.0.0.1", "localhost"):
        raise ValueError("the dashboard only listens on this computer (127.0.0.1)")
    with open(os.path.join(HERE, "dashboard.html"), encoding="utf-8") as fh:
        page = fh.read()
    api_token = token
    csrf = secrets.token_urlsafe(24)
    httpd = QuietServer((host, port), make_handler(provider, csrf, page, api_token=api_token))
    httpd.daemon_threads = True
    if block:
        httpd.serve_forever()
        return httpd
    t = threading.Thread(target=httpd.serve_forever, name="dashboard", daemon=True)
    t.start()
    return httpd
