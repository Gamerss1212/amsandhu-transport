"""AUTOPILOT, the one button: research bots trade the simulated research account only while it is on, it persists
across restarts, it never overrides an emergency stop, and its research schedule queues at most a couple of jobs,
in rotation, at a lower priority than the owner's own jobs. It never touches real money."""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mab import runtime_deploy  # noqa: E402
from mab.research.jobs import JobQueue  # noqa: E402
from mab.runtime import Fleet  # noqa: E402
from test_deployments import STRAT  # noqa: E402

BOTS = [{"bot_id": f"R-{i}", "name": f"research {i}", "strategy_id": "TEST-ALWAYS", "venue": "demo",
         "instrument": sym, "enabled": True} for i, sym in enumerate(["DEMO-BTC", "DEMO-ETH", "DEMO-SOL"])]


def make(tmp_path, **extra):
    cfg = {"data_dir": str(tmp_path / "d"), "demo": True, "workspace": "demo", "brain": {"mode": "off", "volatility_gate": False},
           "paper": {"latency_ms": 0, "max_slippage_bps": 50}, "paper_main_balance": 100_000.0, **extra}
    fl = Fleet(cfg, {"TEST-ALWAYS": STRAT}, list(BOTS), str(tmp_path))
    fl.setup()
    fl.running = True
    return fl


def finish_all(q):
    while q.claim("w") is not None:
        pass
    for j in q.list():
        if j["state"] == "running":
            q.finish(j["job_id"], {"verdict": "test"})


def test_off_by_default_for_app_workspaces_then_one_press_turns_every_research_bot_on(tmp_path):
    fl = make(tmp_path, autopilot_default=False)
    br = fl.bots["R-0"]
    assert fl.autopilot_status()["on"] is False
    assert fl._entries_allowed_for(br, True) is False                  # watching only until the button is pressed
    st = fl.autopilot_set(True, "abhi")
    assert st["on"] is True and st["bots"] == 3 and st["real_money"] is False
    assert all(fl._entries_allowed_for(b, True) for b in fl.bots.values())
    ev = fl.storage.audit_search(kinds=["control"], limit=5)
    assert any(e["stage"] == "autopilot" and "AUTOPILOT ON" in e["summary"] for e in ev)
    fl.running = False
    again = make(tmp_path, autopilot_default=False)                     # restart: it resumes by itself
    assert again.autopilot_status()["on"] is True and again._entries_allowed_for(again.bots["R-1"], True)
    again.autopilot_set(False)
    assert again._entries_allowed_for(again.bots["R-1"], True) is False
    assert again._strategy_exits_for(again.bots["R-1"]) is True         # open positions are still managed


def test_emergency_stop_is_never_overridden(tmp_path):
    fl = make(tmp_path, autopilot_default=False)
    fl.emergency_stop("test")
    with pytest.raises(ValueError, match="EMERGENCY"):
        fl.autopilot_set(True)
    assert fl.research_autopilot is False
    fl.clear_emergency()
    assert fl.autopilot_set(True)["on"] is True


def test_research_schedule_rotates_and_stays_within_its_budget(tmp_path, monkeypatch):
    fl = make(tmp_path, autopilot_default=False)
    q = JobQueue(fl.storage)
    fl._autopilot_cycle()
    assert q.list() == []                                               # nothing while autopilot is off
    fl.autopilot_set(True)
    clock = [10 ** 13]
    monkeypatch.setattr(runtime_deploy, "now_ms", lambda: clock[0])
    fl.storage.kv_set("autopilot_schedule", {"last_brain": clock[0], "last_gate": clock[0]})   # isolate walk-forward
    fl._autopilot_cycle()
    jobs = q.list()
    assert len(jobs) == 1 and jobs[0]["kind"] == "walk_forward" and jobs[0]["priority"] == runtime_deploy.AUTOPILOT_PRIORITY
    assert jobs[0]["requested_by"] == "autopilot" and jobs[0]["spec"]["definition"]["id"] == "TEST-ALWAYS"
    fl._autopilot_cycle()
    assert len(q.list()) == 1                                           # not due yet: one every 20 minutes
    clock[0] += runtime_deploy.AUTOPILOT_WF_EVERY_MS
    fl._autopilot_cycle()
    markets = {j["spec"]["instrument"] for j in q.list()}
    assert len(q.list()) == 2 and len(markets) == 2                     # the next pair in rotation
    clock[0] += runtime_deploy.AUTOPILOT_WF_EVERY_MS
    fl._autopilot_cycle()
    assert len(q.list()) == runtime_deploy.AUTOPILOT_MAX_PENDING        # never more than two waiting at once
    finish_all(q)                                                       # workers finish them
    clock[0] += runtime_deploy.AUTOPILOT_WF_EVERY_MS
    fl._autopilot_cycle()
    assert {j["spec"]["instrument"] for j in q.list()} == {"DEMO-BTC", "DEMO-ETH", "DEMO-SOL"}
    clock[0] += runtime_deploy.AUTOPILOT_WF_EVERY_MS
    finish_all(q)
    n = len(q.list())
    fl._autopilot_cycle()
    assert len(q.list()) == n                                           # every pair evaluated this week: nothing new
