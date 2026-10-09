"""The autopilot deploys only researched strategies, in paper, respects the owner and the kill switch, and retires
bots whose strategy fails a re-test."""

import time

import pytest

from tradingai.app import App


def result(verdict, quality=60.0, trades=40, test_ret=0.05, wf=0.8, sh2x=0.5, sim=True):
    return {"status": "ok", "verdict": verdict, "quality": {"score": quality}, "test": {"trades": trades,
            "total_return": test_ret}, "walk_forward": {"oos_sharpe": wf}, "cost_stress": {"2.0x": {"sharpe": sh2x}},
            "reproducibility": {"simulated_data": sim}, "checks": [], "test_trades": []}


def record(app, sid, iid, tf, res, profile="STANDARD"):
    eid = app.ledger.start(family="test", strategy_id=sid, hypothesis="test", instrument=iid, tf=tf, profile=profile,
                           seed=7, dataset={"simulated": True})
    app.ledger.finish(eid, res)
    time.sleep(0.002)                                   # distinct creation times
    return eid


@pytest.fixture()
def app(tmp_path):
    a = App(str(tmp_path / "home"), offline=True, start_loop=False)
    a.autopilot.cfg.screens_per_hour = 0                # these tests drive deployment, not research
    a.autopilot.cfg.confirms_per_hour = 0
    yield a
    a.shutdown()


def test_on_by_default_and_paper_only(app):
    assert app.autopilot.cfg.enabled and app.mode == "paper"
    app.mode = "live"
    assert app.autopilot.cycle() == {"skipped": "live"}
    app.mode = "paper"


def test_deploys_qualified_and_probation_but_never_rejected(app):
    record(app, "tsmom.none.flip", "DEMO:DEMO-TREND", "1h", result("PAPER TEST"))
    record(app, "tsmom.none.trail", "DEMO:DEMO-RANGE", "1h", result("RESEARCH FURTHER", quality=50))
    record(app, "tsmom.none.time", "DEMO:DEMO-VOLATILE", "1h", result("REJECT", quality=90))
    app.autopilot.cycle()
    bots = {b.instrument_id: b for b in app.autopilot.bots()}
    assert bots["DEMO:DEMO-TREND"].tier == "qualified" and bots["DEMO:DEMO-TREND"].state == "running"
    assert bots["DEMO:DEMO-RANGE"].tier == "probation"
    assert "DEMO:DEMO-VOLATILE" not in bots
    assert app.state.state == "PAPER_RUNNING"


def test_weak_research_is_not_deployed(app):
    record(app, "tsmom.none.flip", "DEMO:DEMO-TREND", "1h", result("RESEARCH FURTHER", wf=-0.2))   # walk-forward lost
    record(app, "tsmom.none.trail", "DEMO:DEMO-RANGE", "1h", result("RESEARCH FURTHER", trades=8))  # too few trades
    app.autopilot.cycle()
    assert app.autopilot.bots() == []


def test_kill_switch_blocks_deployment_and_autopilot_never_rearms(app):
    record(app, "tsmom.none.flip", "DEMO:DEMO-TREND", "1h", result("PAPER TEST"))
    app.emergency_stop("test", "owner")
    app.autopilot.cycle()
    assert app.autopilot.bots() == [] and app.risk.kill_switch is not None


def test_owner_stop_is_respected_and_stop_bot_pauses_autopilot(app):
    record(app, "tsmom.none.flip", "DEMO:DEMO-TREND", "1h", result("PAPER TEST"))
    app.autopilot.cycle()
    b = app.autopilot.bots()[0]
    app.bot_action(b.bot_id, "stop")                    # the owner stops one bot
    app.autopilot.cycle()
    assert b.state == "stopped"                          # not restarted behind the owner's back
    app.stop_all()                                       # STOP BOT turns the autopilot off
    assert not app.autopilot.cfg.enabled
    app.start_all()                                      # START BOT turns it back on
    assert app.autopilot.cfg.enabled and b.state == "running"


def test_failed_retest_retires_the_bot(app):
    record(app, "tsmom.none.flip", "DEMO:DEMO-TREND", "1h", result("PAPER TEST"))
    app.autopilot.cycle()
    assert len(app.autopilot.bots()) == 1
    record(app, "tsmom.none.flip", "DEMO:DEMO-TREND", "1h", result("REJECT"))
    app.autopilot.cycle()
    assert app.autopilot.bots() == []                    # retired, and not redeployed for 30 days
    assert app.autopilot.mem["retired_count"] == 1


def test_screening_runs_by_itself(tmp_path):
    a = App(str(tmp_path / "home"), offline=True, start_loop=False)
    try:
        r = a.autopilot.cycle()
        assert r["research"]["kind"] == "screen"
        jid = r["research"]["job_id"]
        t0 = time.time()
        while a.jobs.view(jid)["state"] in ("queued", "running") and time.time() - t0 < 60:
            time.sleep(0.1)
        a.autopilot.cycle()
        assert a.autopilot.mem["screened"] == 1 and a.ledger.counts()["experiments"] == 1
    finally:
        a.shutdown()
