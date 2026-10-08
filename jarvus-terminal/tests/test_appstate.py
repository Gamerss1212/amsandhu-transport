"""The app's state machine (section 269), start-up checks (section 120) and GET /health (section 270)."""

from __future__ import annotations

import json
import os
import socket
import sqlite3
import threading
import urllib.request

import pytest

import config
import server
from engine import appstate as A


@pytest.fixture()
def app_server(tmp_path):
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    config.PORT = s.getsockname()[1]
    s.close()
    config.DATA_DIR = str(tmp_path)
    app = server.make_app(str(tmp_path), start_engines=False)
    app.auth.open_session()                                  # the owner's workspace, as on a first start
    app.boot()
    httpd = server.QuietServer(("127.0.0.1", config.PORT), server.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield config.PORT, app
    httpd.shutdown()
    httpd.server_close()


def test_paper_never_jumps_straight_to_real_money() -> None:
    for state in A.STATES:
        if state != A.LIVE_ARMED:
            assert A.LIVE_RUNNING not in A.TRANSITIONS[state], state   # only an armed live account can run
        if state not in (A.LIVE_LOCKED, A.LIVE_RUNNING):
            assert A.LIVE_ARMED not in A.TRANSITIONS[state], state     # arming starts from the locked state
    assert A.TRANSITIONS[A.SHUTTING_DOWN] == frozenset()
    assert set(A.TRANSITIONS) == set(A.STATES)


def test_impossible_moves_are_rejected_and_change_nothing() -> None:
    m = A.Lifecycle(clock=lambda: 100.0)
    with pytest.raises(A.InvalidTransition):
        m.to(A.LIVE_RUNNING, "skip every gate")
    assert m.state == A.BOOTING and not m.history
    m.to(A.READY, "checks passed")
    m.to(A.PAPER_RUNNING, "autopilot")
    with pytest.raises(A.InvalidTransition):
        m.to(A.LIVE_ARMED, "one click")
    with pytest.raises(A.InvalidTransition):
        m.to("FLYING", "not a state")
    m.to(A.SHUTTING_DOWN, "owner")
    with pytest.raises(A.InvalidTransition):
        m.to(A.READY, "after shutdown")
    assert [h["to"] for h in m.history] == [A.READY, A.PAPER_RUNNING, A.SHUTTING_DOWN]


def test_trading_state_comes_from_recorded_facts_and_stops_win() -> None:
    assert A.trading_state({}) == A.READY
    assert A.trading_state({"engine_running": True}) == A.PAPER_RUNNING
    assert A.trading_state({"engine_running": True, "live_authorized": True}) == A.LIVE_ARMED
    running = {"engine_running": True, "live_authorized": True, "live_deployments_running": 1}
    assert A.trading_state(running) == A.LIVE_RUNNING and A.live_state(running) == "RUNNING"
    assert A.trading_state(dict(running, emergency=True)) == A.PAUSED
    assert A.trading_state(dict(running, emergency=True, reconciliation_problems=1)) == A.RECONCILIATION_REQUIRED
    assert A.live_state({"engine_running": True}) == "LOCKED"


def test_checks_report_failures_instead_of_assuming_success(tmp_path) -> None:
    good = tmp_path / "good.db"
    sqlite3.connect(good).execute("CREATE TABLE t (x)").connection.commit()
    assert A.check("db", lambda: A.sqlite_quick_check(str(good)))["ok"]
    assert "first start" in A.sqlite_quick_check(str(tmp_path / "missing.db"))
    bad = tmp_path / "bad.db"
    bad.write_bytes(b"this is not a database" * 100)
    res = A.check("db", lambda: A.sqlite_quick_check(str(bad)))
    assert not res["ok"] and "DatabaseError" in res["detail"]
    assert A.summarize([res]).startswith("db: ")
    assert A.summarize([A.check("x", lambda: "fine")]) is None


def _get(port: int, path: str):
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(req, timeout=10) as r:
        return r.status, json.loads(r.read())


def test_health_reports_every_component_without_secrets(app_server) -> None:
    port, app = app_server
    status, h = _get(port, "/health")
    assert status == 200 and h["app"] == "jarvus"
    assert h["lifecycle"]["state"] == A.READY
    assert {c["name"] for c in h["startup_checks"]} >= {"app database", "web page files", "strategy library"}
    assert all(c["ok"] for c in h["startup_checks"])
    for name in ("backend", "database", "strategy_engine", "market_feed", "execution_engine", "risk_service", "broker"):
        assert name in h["components"], name
    assert h["live"] == "LOCKED" and h["trading_state"] in (A.READY, A.PAPER_RUNNING)
    text = json.dumps(h).lower()
    assert "secret" not in text and "password" not in text and "csrf" not in text


def test_a_broken_database_stops_the_engines_from_starting(tmp_path) -> None:
    app = server.make_app(str(tmp_path), start_engines=False)
    app.auth.open_session()
    ws = [w for w in app.auth.workspaces() if w["kind"] == "main"][0]
    db = os.path.join(ws["path"], "data", "mab.db")
    os.makedirs(os.path.dirname(db), exist_ok=True)
    with open(db, "wb") as fh:
        fh.write(b"garbage" * 500)
    app.boot()
    assert app.lifecycle.state == A.ERROR
    assert any(not c["ok"] and "workspace database" in c["name"] for c in app.startup_checks)
