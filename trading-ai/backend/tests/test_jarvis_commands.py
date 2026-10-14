"""What the voice assistant may ask for. Risk-reducing actions run at once; everything that does more or changes the
account waits for the owner's click; orders, limits, live trading, credentials and the emergency stop do not exist for it."""

import pytest
from fastapi.testclient import TestClient

from tradingai.api.server import create_app
from tradingai.app import App
from tradingai.engine import jarvis_link as J

FULL = {"X-TA-Token": "FULL"}
READ = {"X-TA-Read-Token": "READ"}
CMD = {"X-TA-Command-Token": "CMD"}


@pytest.fixture()
def env(tmp_path):
    a = App(str(tmp_path / "home"), offline=True, start_loop=False)
    api = create_app(a, token="FULL", read_token="READ", command_token="CMD")
    yield a, TestClient(api, base_url="http://127.0.0.1:8000")
    a.shutdown()


def ask(c, action, **kw):
    return c.post("/api/jarvis/command", headers=CMD, json={"action": action, **kw})


def test_risk_reducing_actions_run_at_once(env):
    a, c = env
    r = ask(c, "pause_entries", reason="the market is moving fast")
    assert r.status_code == 200 and r.json()["status"] == "done"
    assert a.risk.entries_paused and a.risk.entries_paused["by"] == "jarvis"
    assert ask(c, "stop_system").json()["status"] == "done" and a.autopilot.cfg.enabled is False


def test_actions_that_do_more_wait_for_the_owner_and_nothing_happens_yet(env):
    a, c = env
    a.autopilot.configure({"enabled": False})
    a.pause_entries(True, "owner", "test")
    for action, extra in (("start_system", {}), ("resume_entries", {}), ("run_thermal_check", {"minutes": 2}),
                          ("set_paper_balance", {"amount": "100"})):
        out = ask(c, action, reason="because", **extra).json()
        assert out["status"] == "waiting_for_owner", action
    assert a.autopilot.cfg.enabled is False and a.risk.entries_paused          # nothing ran
    assert a.hardware.check["state"] != "running"
    pending = c.get("/api/jarvis/pending", headers=READ).json()["pending"]     # JARVIS can see what is waiting
    assert {p["action"] for p in pending} == {"start_system", "resume_entries", "run_thermal_check", "set_paper_balance"}


def test_only_the_owners_full_token_can_approve_or_reject(env):
    a, c = env
    a.autopilot.configure({"enabled": False})
    cid = ask(c, "start_system").json()["id"]
    for hdr in (CMD, READ, {}):
        assert c.post(f"/api/jarvis/pending/{cid}/approve", headers=hdr).status_code == 401
    assert a.autopilot.cfg.enabled is False
    assert c.post(f"/api/jarvis/pending/{cid}/approve", headers=FULL).json()["status"] == "done"
    assert a.autopilot.cfg.enabled is True
    cid = ask(c, "set_paper_balance", amount="250").json()["id"]
    assert c.post(f"/api/jarvis/pending/{cid}/reject", headers=FULL).json()["status"] == "rejected"
    assert c.get("/api/jarvis/pending", headers=FULL).json()["pending"] == []


def test_an_approved_balance_change_is_applied_and_recorded(env):
    a, c = env
    cid = ask(c, "set_paper_balance", amount="100").json()["id"]
    r = c.post(f"/api/jarvis/pending/{cid}/approve", headers=FULL)
    assert r.status_code == 200 and r.json()["result"]["equity"] == "100.00"
    row = a.db.one("SELECT message FROM audit WHERE kind='jarvis' ORDER BY id DESC LIMIT 1")
    assert "set_paper_balance" in row["message"] and "approved" in row["message"]


@pytest.mark.parametrize("action", ["place_order", "buy", "set_limits", "raise_limits", "arm_live", "enable_live",
                                    "emergency_stop", "rearm", "flatten", "shutdown", "connect_broker", "add_key",
                                    "deploy_code", "pause_entries; rm", ""])
def test_nothing_else_exists_for_jarvis(env, action):
    a, c = env
    r = ask(c, action) if action else c.post("/api/jarvis/command", headers=CMD, json={"action": "x" * 41})
    assert r.status_code in (403, 422), (action, r.status_code)
    assert not a.risk.kill_switch and not a.risk.entries_paused


def test_the_command_token_opens_exactly_one_route(env):
    a, c = env
    assert c.get("/api/overview", headers=CMD).status_code == 401
    assert c.get("/api/jarvis/pending", headers=CMD).status_code == 401
    assert c.post("/api/controls/pause-entries", headers=CMD, json={"paused": True}).status_code == 401
    assert c.post("/api/jarvis/command", headers=READ, json={"action": "pause_entries"}).status_code == 401
    assert c.post("/api/jarvis/command", headers={"X-TA-Command-Token": "nope"},
                  json={"action": "pause_entries"}).status_code == 401
    assert not a.risk.entries_paused


def test_bad_arguments_are_refused(env):
    a, c = env
    assert ask(c, "set_paper_balance", amount="0").status_code == 400
    assert ask(c, "set_paper_balance", amount="99999999999").status_code == 400
    assert ask(c, "set_paper_balance").status_code == 400
    assert ask(c, "run_thermal_check", minutes=60).status_code == 400


def test_a_start_is_refused_while_the_emergency_stop_is_engaged(env):
    a, c = env
    a.autopilot.configure({"enabled": False})
    a.risk.engage_kill_switch("test", "owner")
    cid = ask(c, "start_system").json()["id"]
    r = c.post(f"/api/jarvis/pending/{cid}/approve", headers=FULL)
    assert r.status_code == 403 and a.autopilot.cfg.enabled is False


def test_old_requests_expire_and_text_is_cleaned(env, monkeypatch):
    a, c = env
    out = ask(c, "start_system", reason="<script>alert(1)</script> go").json()
    pend = c.get("/api/jarvis/pending", headers=FULL).json()["pending"][0]
    assert "<" not in pend["reason"] and ">" not in pend["reason"]
    monkeypatch.setattr(J, "EXPIRES_S", -1)
    assert c.get("/api/jarvis/pending", headers=FULL).json()["pending"] == []
    assert c.post(f"/api/jarvis/pending/{out['id']}/approve", headers=FULL).status_code == 404


def test_a_retried_command_id_never_acts_twice(env):
    a, c = env
    first = ask(c, "set_paper_balance", amount="100", command_id="cmd-1").json()
    again = ask(c, "set_paper_balance", amount="100", command_id="cmd-1").json()
    assert again["id"] == first["id"] and again["duplicate"] is True
    assert len(c.get("/api/jarvis/pending", headers=FULL).json()["pending"]) == 1
