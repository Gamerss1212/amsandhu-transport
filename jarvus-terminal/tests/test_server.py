"""The app server end to end over real HTTP (engines not started): first-run setup and sign-in, CSRF, Host / Origin /
app-header guards, lockout, account isolation, credentials never leaving the vault (with Alpaca's paper API played
by a local contract fake), the one-button autopilot, emergency controls while the engine is stopped, the live event
stream with resume, event search and export, static files and security headers."""

import http.client
import json
import os
import socket
import threading
import urllib.error
import urllib.request

import pytest

import config
import server
from alpaca_fake import KEY, SECRET, FakeAlpaca, serve as serve_alpaca
from mab.execution import alpaca as alpaca_mod

PW = "correct horse battery"


def _port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


class Client:
    def __init__(self, base):
        self.base, self.token, self.csrf = base, None, None

    def req(self, path, body=None, headers=None, csrf=True, app_header=True):
        h = {}
        if body is not None:
            h["Content-Type"] = "application/json"
            if app_header:
                h["X-Jarvus"] = "1"
            if csrf and self.csrf:
                h["X-CSRF-Token"] = self.csrf
        if self.token:
            h["Cookie"] = f"jv_session={self.token}"
        h.update(headers or {})
        rq = urllib.request.Request(self.base + path, data=None if body is None else json.dumps(body).encode(), headers=h,
                                    method="POST" if body is not None else "GET")
        try:
            with urllib.request.urlopen(rq, timeout=30) as r:
                raw, code, hdrs = r.read(), r.status, r.headers
        except urllib.error.HTTPError as e:
            raw, code, hdrs = e.read(), e.code, e.headers
        ck = hdrs.get("Set-Cookie") or ""
        if ck.startswith("jv_session="):
            self.token = ck.split(";", 1)[0].split("=", 1)[1] or None
        try:
            data = json.loads(raw)
        except ValueError:
            data = raw
        if isinstance(data, dict) and data.get("csrf"):
            self.csrf = data["csrf"]
        return code, data, hdrs, raw

    def sign_in(self, user="abhi", pw=PW, setup=False):
        code, d, _, _ = self.req("/api/auth/setup" if setup else "/api/auth/login", {"username": user, "password": pw}, csrf=False)
        assert code == 200, d
        return d


@pytest.fixture()
def app(tmp_path):
    config.PORT = _port()
    config.DATA_DIR = str(tmp_path)
    a = server.make_app(str(tmp_path), start_engines=False)
    httpd = server.QuietServer(("127.0.0.1", config.PORT), server.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{config.PORT}"
    owner = Client(base)
    owner.sign_in(setup=True)
    yield a, base, owner
    httpd.shutdown()
    httpd.server_close()


def test_first_run_setup_sign_in_and_sign_out(app):
    a, base, owner = app
    anon = Client(base)
    code, st, _, _ = anon.req("/api/auth/state")
    assert code == 200 and st["needs_setup"] is False and st["signed_in"] is False
    assert anon.req("/api/overview")[0] == 401
    assert anon.req("/api/auth/setup", {"username": "x", "password": PW})[0] == 400        # only one owner, ever
    code, ov, _, _ = owner.req("/api/overview")
    assert code == 200 and ov["workspace"]["kind"] == "main" and ov["live_authorization"]["authorized"] is False
    assert ov["autopilot"] is False                                                     # waits for the button
    assert owner.req("/api/auth/logout", {})[0] == 200
    assert owner.req("/api/overview")[0] == 401


def test_every_change_needs_the_csrf_token_and_the_app_header(app):
    a, base, owner = app
    assert owner.req("/api/emergency", {"reason": "x"}, csrf=False)[0] == 403
    assert owner.req("/api/emergency", {"reason": "x"}, headers={"X-CSRF-Token": "wrong"})[0] == 403
    assert owner.req("/api/emergency", {"reason": "x"}, app_header=False)[0] == 403
    assert owner.req("/api/emergency", {"reason": "x"}, headers={"Origin": "http://evil.example"})[0] == 403
    assert owner.req("/api/overview", headers={"Host": "evil.example"})[0] == 403        # DNS rebinding
    code, d, _, _ = owner.req("/api/overview")
    assert d["emergency"] is None                                                       # none of those got through


def test_wrong_passwords_lock_the_account_for_a_while(app):
    a, base, owner = app
    c = Client(base)
    for _ in range(5):
        assert c.req("/api/auth/login", {"username": "abhi", "password": "wrong password"}, csrf=False)[0] == 403
    code, d, _, _ = c.req("/api/auth/login", {"username": "abhi", "password": PW}, csrf=False)
    assert code == 403 and "too many" in d["error"]


def test_accounts_are_isolated(app):
    a, base, owner = app
    assert owner.req("/api/auth/users", {"username": "bea", "password": "another long password"})[0] == 200
    bea = Client(base)
    bea.sign_in("bea", "another long password")
    _, st_o, _, _ = owner.req("/api/auth/state")
    _, st_b, _, _ = bea.req("/api/auth/state")
    mine = {w["workspace_id"] for w in st_o["workspaces"]}
    hers = {w["workspace_id"] for w in st_b["workspaces"]}
    assert mine and hers and not (mine & hers)
    code, d, _, _ = bea.req("/api/auth/workspace", {"workspace_id": st_o["workspace"]})
    assert code == 403                                                                  # not hers
    assert bea.req("/api/auth/users", {"username": "eve", "password": "yet another password"})[0] == 403
    owner.req("/api/emergency", {"reason": "owner only"})
    _, ov_b, _, _ = bea.req("/api/overview")
    assert ov_b["emergency"] is None                                                    # her workspace is untouched


def test_credentials_never_leave_the_vault(app, monkeypatch):
    a, base, owner = app
    fake = FakeAlpaca()
    httpd = serve_alpaca(fake)
    url = f"http://127.0.0.1:{httpd.server_address[1]}"
    monkeypatch.setitem(alpaca_mod.URLS, "paper", url)
    monkeypatch.setattr(alpaca_mod, "DATA", url)
    try:
        code, d, _, raw = owner.req("/api/connections/create", {"provider": "alpaca", "environment": "paper",
                                                                "credentials": {"key": KEY, "secret": SECRET}})
        assert code == 200, d
        assert d["test"]["ok"] is True and d["connection"]["connection_id"] == "alpaca-paper"
        checks = {c["id"]: c["status"] for c in d["test"]["checks"]}
        assert checks["auth"] == "pass" and checks["account"] == "pass" and checks["withdraw"] == "pass"
        bodies = [raw]
        for path in ("/api/connections", "/api/events?limit=500&severity=debug", "/api/events/export?format=csv",
                     "/api/events/export?format=json", "/api/overview", "/api/accounts"):
            code, _, _, body = owner.req(path)
            assert code == 200, path
            bodies.append(body)
        for b in bodies:
            assert KEY.encode() not in b and SECRET.encode() not in b
        on_disk = []
        for root, _, files in os.walk(config.DATA_DIR):
            for f in files:
                with open(os.path.join(root, f), "rb") as fh:
                    on_disk.append(fh.read())
        with open(os.path.join(os.environ["MAB_SECRETS_DIR"], "vault.json"), "rb") as fh:
            vault = fh.read()
        assert SECRET.encode() not in vault                                             # encrypted at rest
        assert all(SECRET.encode() not in blob for blob in on_disk)
        code, _, _, _ = owner.req("/api/connections/disconnect", {"connection_id": "alpaca-paper"})
        assert code == 200
        code, lst, _, _ = owner.req("/api/connections")
        row = [c for c in lst["connections"] if c["connection_id"] == "alpaca-paper"][0]
        assert row["status"] == "disconnected" and row["has_credentials"] is False     # deleted from the vault
    finally:
        httpd.shutdown()


def test_the_simulated_account_cannot_be_disconnected_and_funding_never_simulates_a_deposit(app):
    a, base, owner = app
    code, d, _, _ = owner.req("/api/connections/disconnect", {"connection_id": "paper-main"})
    assert code == 400
    code, f, _, _ = owner.req("/api/funding/paper-main")
    assert code == 200 and f["simulated"] is True and f["url"] is None and "never a deposit" in f["note"]
    assert owner.req("/api/paper_balance", {"connection_id": "paper-main", "amount": 5})[0] == 409   # engine stopped


def test_live_trading_cannot_be_authorised_without_the_engine_but_can_always_be_revoked(app):
    a, base, owner = app
    code, d, _, _ = owner.req("/api/live/authorize", {"ack": server.LIVE_ACK, "connections": ["x"],
                                                     "max_total_allocation": 10, "daily_loss_limit": 1})
    assert code == 409
    code, d, _, _ = owner.req("/api/live/revoke", {})
    assert code == 200 and d["revoked"] is True


def test_one_button_autopilot_and_emergency_stop_while_the_engine_is_stopped(app):
    a, base, owner = app
    code, ap, _, _ = owner.req("/api/autopilot")
    assert code == 200 and ap["on"] is False and ap["real_money"] is False
    code, ap, _, _ = owner.req("/api/autopilot", {"on": True})
    assert code == 200 and ap["on"] is True and ap["autostart"] is True                 # starts with Jarvus from now on
    assert owner.req("/api/overview")[1]["autopilot"] is True
    code, d, _, _ = owner.req("/api/emergency", {"reason": "test"})
    assert code == 200 and d["blocked"] is True
    owner.req("/api/autopilot", {"on": False})
    code, d, _, _ = owner.req("/api/autopilot", {"on": True})
    assert code == 409 and "EMERGENCY" in d["error"]                                    # never overrides it
    assert owner.req("/api/emergency/clear", {})[0] == 200
    assert owner.req("/api/autopilot", {"on": True})[1]["on"] is True
    code, ev, _, _ = owner.req("/api/events?kinds=control&limit=50")
    stages = [e["stage"] for e in ev]
    assert "autopilot" in stages and "emergency_stop" in stages and "emergency_cleared" in stages


def test_live_stream_sends_events_and_resumes_after_the_last_one_seen(app):
    a, base, owner = app
    _, st, _, _ = owner.req("/api/auth/state")
    store = a.st(st["workspace"])
    first = store.audit("control", "first event", stage="test")
    second = store.audit("order", "second event", stage="test")
    conn = http.client.HTTPConnection("127.0.0.1", config.PORT, timeout=10)
    conn.request("GET", "/api/stream?severity=debug", headers={"Cookie": f"jv_session={owner.token}",
                                                                "Last-Event-ID": str(first)})
    r = conn.getresponse()
    assert r.status == 200 and r.getheader("Content-Type").startswith("text/event-stream")
    buf = b""
    while b"second event" not in buf and len(buf) < 200_000:
        buf += r.fp.readline()
    text = buf.decode()
    assert "event: hello" in text and f"id: {second}" in text and "first event" not in text
    conn.close()


def test_event_search_and_export(app):
    a, base, owner = app
    _, st, _, _ = owner.req("/api/auth/state")
    store = a.st(st["workspace"])
    store.audit("signal", "entry rule true on BTC", stage="signal", bot_id="B1", symbol="BTC-USD", correlation_id="c1")
    store.audit("order", "buy submitted", stage="order_submitted", bot_id="B1", symbol="BTC-USD", correlation_id="c1")
    store.audit("order", "other bot", stage="order_submitted", bot_id="B2", symbol="ETH-USD")
    code, rows, _, _ = owner.req("/api/events?kinds=order&bot=B1")
    assert code == 200 and [r["summary"] for r in rows] == ["buy submitted"]
    code, life, _, _ = owner.req("/api/lifecycle/c1")
    assert [r["stage"] for r in life] == ["signal", "order_submitted"]
    code, _, hdrs, raw = owner.req("/api/events/export?format=csv&bot=B1")
    assert code == 200 and hdrs.get("Content-Disposition", "").startswith("attachment")
    lines = raw.decode().strip().splitlines()
    assert lines[0].startswith("id,ts,time_utc,kind") and len(lines) == 3


def test_static_files_and_security_headers(app):
    a, base, owner = app
    anon = Client(base)
    code, _, hdrs, raw = anon.req("/")
    assert code == 200 and b"/js/app.js" in raw
    csp = hdrs.get("Content-Security-Policy")
    assert "script-src 'self'" in csp and "frame-ancestors 'none'" in csp
    assert hdrs.get("X-Content-Type-Options") == "nosniff"
    code, _, hdrs, _ = anon.req("/js/app.js")
    assert code == 200 and hdrs.get("Content-Type").startswith("text/javascript")
    assert anon.req("/vendor/lightweight-charts.standalone.production.js")[0] == 200
    for bad in ("/../server.py", "/js/../../config.py", "/config.py"):
        assert anon.req(bad)[0] == 404


def test_assistant_key_is_validated_and_never_returned(app):
    a, base, owner = app
    code, d, _, _ = owner.req("/api/assistant/config", {"api_key": "not-a-key"})
    assert code == 400
    key = "sk-ant-test-" + "x" * 40
    code, d, _, raw = owner.req("/api/assistant/config", {"api_key": key, "budget": {"max_requests_per_day": 5}})
    assert code == 200 and d["has_key"] is True and d["budget"]["max_requests_per_day"] == 5 and d["can_trade"] is False
    assert key.encode() not in raw
    _, _, _, raw = owner.req("/api/connections")
    assert key.encode() not in raw
    code, d, _, _ = owner.req("/api/assistant/forget", {})
    assert code == 200 and d["has_key"] is False
