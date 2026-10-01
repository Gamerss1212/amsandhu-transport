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


def test_opens_without_a_sign_in_page(app):
    a, base, owner = app
    anon = Client(base)
    assert anon.req("/api/overview")[0] == 401                                          # no session cookie yet
    code, st, _, _ = anon.req("/api/auth/state")                                        # no sign-in page:
    assert code == 200 and st["signed_in"] is True and anon.token and anon.csrf         # the page opens straight in
    assert anon.req("/api/overview")[0] == 200
    assert anon.req("/api/auth/setup", {"username": "x", "password": PW})[0] == 400        # only one owner, ever
    code, ov, _, _ = owner.req("/api/overview")
    assert code == 200 and ov["workspace"]["kind"] == "main" and ov["live_authorization"]["authorized"] is False
    assert ov["autopilot"] is True                                                      # the AI trades (paper) by default
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



def test_paper_balances_change_any_time_even_with_the_engine_stopped(app):
    a, base, owner = app
    for cid in ("paper-research", "paper-main"):                     # the AI's account and the owner's
        code, r, _, _ = owner.req("/api/paper_balance", {"connection_id": cid, "kind": "set_balance", "amount": 25000})
        assert code == 200 and r["equity_after"] == pytest.approx(25000), r
    code, r, _, _ = owner.req("/api/paper_balance", {"connection_id": "paper-research", "kind": "deposit", "amount": 5000})
    assert code == 200 and r["equity_after"] == pytest.approx(30000)
    code, r, _, _ = owner.req("/api/paper_balance", {"connection_id": "paper-research", "kind": "withdraw", "amount": 20000})
    assert code == 200 and r["equity_after"] == pytest.approx(10000)
    accts = {x["connection_id"]: x for x in owner.req("/api/overview")[1]["accounts"]}
    assert accts["paper-research"]["equity"] == pytest.approx(10000) and accts["paper-main"]["equity"] == pytest.approx(25000)
    assert accts["paper-research"]["simulated"] is True
    for bad in (0, -5, "abc", None, 1e13, float("nan")):
        body = {"connection_id": "paper-main", "kind": "set_balance", "amount": bad}
        assert owner.req("/api/paper_balance", body)[0] == 400, bad
    assert owner.req("/api/paper_balance", {"connection_id": "paper-main", "kind": "withdraw", "amount": 10 ** 9})[0] == 400
    assert owner.req("/api/paper_balance", {"connection_id": "nope", "kind": "set_balance", "amount": 5})[0] == 400
    _, st, _, _ = owner.req("/api/auth/state")
    store = a.st(st["workspace"])
    store.kv_set("risk", {"peak_equity": 100000.0, "day_start_equity": 100000.0})
    owner.req("/api/paper_balance", {"connection_id": "paper-research", "kind": "set_balance", "amount": 5000})
    assert store.kv_get("risk")["peak_equity"] == pytest.approx(5000)   # a lower balance is not a drawdown
    code, ev, _, _ = owner.req("/api/events?kinds=connection&limit=50")
    assert any(e["stage"] == "paper_balance" for e in ev)


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
    assert code == 200 and ap["on"] is True and ap["real_money"] is False
    owner.req("/api/autopilot", {"on": False})
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


def test_money_view_shows_the_ais_open_trades_and_the_fee_level(app):
    a, base, owner = app
    from mab.account import Account
    _, st, _, _ = owner.req("/api/auth/state")
    store = a.st(st["workspace"])
    code, m, _, _ = owner.req("/api/money")
    assert code == 200 and m["equity"] is None and m["positions"] == []              # the account opens with the engine
    acct = Account(100_000.0, 20)
    acct.apply_fill("BOT-9", "coinbase", "BTC-USD", "buy", 0.1, 50_000.0, 6.0)
    acct.mark("coinbase", "BTC-USD", 51_000.0)
    store.kv_set("account", acct.to_state())
    code, m, _, _ = owner.req("/api/money")
    p = m["positions"][0]
    assert code == 200 and m["engine"] is False and m["real_money"] is False
    assert p["symbol"] == "BTC-USD" and p["side"] == "long" and p["price"] == 51_000.0
    assert p["pnl"] == pytest.approx(100.0) and p["pnl_pct"] == pytest.approx(2.0)
    assert m["equity"] == pytest.approx(100_000.0 - 6.0 + 100.0) and m["unrealized"] == pytest.approx(100.0)
    code, f, _, _ = owner.req("/api/fees")                                              # NDAX until the owner picks another
    assert code == 200 and f["current"] == "ndax" and {"ndax", "kraken", "coinbase", "low_fee", "venue"} <= {x["name"] for x in f["profiles"]}
    assert owner.req("/api/fees", {"profile": "kraken"})[1]["current"] == "kraken"
    assert owner.req("/api/fees", {"profile": "free-money"})[0] == 400
    assert owner.req("/api/fees", {"profile": "kraken"}, csrf=False)[0] == 403


def test_stopping_the_engine_stops_the_ai_and_starting_it_again_resumes_it(app):
    a, base, owner = app
    assert owner.req("/api/autopilot")[1]["on"] is True
    code, out, _, _ = owner.req("/api/engine/stop", {})
    assert code == 200
    assert owner.req("/api/autopilot")[1]["on"] is False                                 # stays off after a restart too
    code, ap, _, _ = owner.req("/api/engine/start", {})
    assert code == 200 and ap["on"] is True
    owner.req("/api/engine/stop", {})
    owner.req("/api/emergency", {"reason": "test"})
    code, out, _, _ = owner.req("/api/engine/start", {})                                 # an emergency stop still wins:
    assert code == 200 and "EMERGENCY" in out["note"]                                    # it runs, but opens nothing new
    assert owner.req("/api/autopilot")[1]["on"] is False                                 # and the AI stays off


def test_start_with_windows_is_a_per_user_run_entry_and_says_when_it_is_unavailable(app):
    a, base, owner = app
    code, st, _, _ = owner.req("/api/startup")
    assert code == 200 and st["supported"] is False and "Windows app" in st["note"]       # from source / Linux
    assert owner.req("/api/startup", {"on": True})[0] == 400
    from engine import startup

    class FakeKey:
        pass

    class FakeReg:
        HKEY_CURRENT_USER, KEY_READ, KEY_SET_VALUE, REG_SZ = 1, 2, 3, 4

        def __init__(self):
            self.values = {}

        def OpenKey(self, root, path, res, access):
            reg = self
            if path != startup.RUN_KEY:
                raise OSError

            class K:
                def __enter__(s): return s
                def __exit__(s, *a): return False
            return K()

        def QueryValueEx(self, key, name):
            if name not in self.values:
                raise OSError
            return (self.values[name], 1)

        def CreateKeyEx(self, root, path, res, access):
            assert path == startup.RUN_KEY                                                # HKCU only: no admin rights
            return FakeKey()

        def SetValueEx(self, key, name, res, typ, val):
            self.values[name] = val

        def DeleteValue(self, key, name):
            if name not in self.values:
                raise OSError
            del self.values[name]

        def CloseKey(self, key):
            pass

    reg = FakeReg()
    on = startup.set_enabled(True, reg=reg, force=True)
    assert on["supported"] and on["enabled"] and "--background" in reg.values["Jarvus"] and "/min" in reg.values["Jarvus"]
    off = startup.set_enabled(False, reg=reg, force=True)
    assert off["enabled"] is False and "Jarvus" not in reg.values
    assert startup.set_enabled(False, reg=reg, force=True)["enabled"] is False            # removing twice is fine


def test_goal_calculator_answers_from_measured_windows_and_says_when_a_goal_is_out_of_reach(app, monkeypatch):
    a, base, owner = app
    from engine import library, projection
    inputs = {"generated": "test", "window_days": 10, "runs": 40, "period": ["2026-06-09", "2026-09-30"], "profiles": {
        "ndax": {"100": {"returns": [-0.004, 0.0, 0.002, 0.001] * 10, "trades_per_window": 3.8},
                 "100000": {"returns": [-0.0002, 0.0001] * 20, "trades_per_window": 4.5}},
        "venue": {"100": {"returns": [0.0] * 40}}}}
    monkeypatch.setattr(library, "_projection", inputs)
    code, r, _, _ = owner.req("/api/projection?balance=100&days=90&target=300000&fees=ndax")
    assert code == 200 and r["tier"] == 100 and r["windows"] == 9 and r["fees"] == "ndax"
    g = r["goal"]
    assert g["needed_per_day_pct"] == pytest.approx(((300000 / 100) ** (1 / 90) - 1) * 100) and 9.2 < g["needed_per_day_pct"] < 9.4
    assert g["share_reaching"] == 0.0 and g["multiple"] == pytest.approx(3000.0)           # out of reach, said plainly
    assert r["outcome"]["p05"] <= r["outcome"]["median"] <= r["outcome"]["p95"] <= r["outcome"]["best"]
    assert r["even_the_best_window_every_time"] == pytest.approx(100 * 1.002 ** 9)
    code, r2, _, _ = owner.req("/api/projection?balance=100&days=90&target=300000&fees=ndax")
    assert r2["outcome"] == r["outcome"]                                                    # same question, same answer
    big = owner.req("/api/projection?balance=250000&days=30")[1]
    assert big["tier"] == 100000 and big["windows"] == 3                                    # nearest measured balance
    assert owner.req("/api/projection?balance=abc")[0] == 400
    assert owner.req("/api/projection?balance=0&days=90")[0] == 400
    assert owner.req("/api/projection?balance=100&days=3")[0] == 400
    fallback = owner.req("/api/projection?balance=100&days=90&fees=coinbase")[1]
    assert fallback["fees"] == "venue"                                                      # nearest profile that was measured
    monkeypatch.setattr(library, "_projection", {})
    assert owner.req("/api/projection?balance=100&days=90")[0] == 400                       # nothing bundled: it says so


def test_projection_math_compounds_windows():
    from engine import projection
    inp = {"window_days": 10, "profiles": {"ndax": {"1000": {"returns": [0.01] * 20}}}}
    r = projection.project(inp, "ndax", 1000.0, 90, 2000.0)
    assert r["outcome"]["median"] == pytest.approx(1000 * 1.01 ** 9) and r["outcome"]["worst"] == r["outcome"]["best"]
    assert r["share_ending_up"] == 1.0 and r["goal"]["share_reaching"] == 0.0
    assert r["goal"]["times_the_best_window"] == pytest.approx(((2.0) ** (1 / 9) - 1) / 0.01)
