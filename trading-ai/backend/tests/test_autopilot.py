"""The autopilot deploys only researched strategies, in paper, respects the owner and the kill switch, and retires
bots whose strategy fails a re-test."""

import time

import pytest

from tradingai.app import App


def result(verdict, quality=60.0, trades=40, test_ret=0.05, wf=0.8, sh2x=0.5, sim=True):
    return {"status": "ok", "verdict": verdict, "operating_mode": "intraday", "quality": {"score": quality}, "test": {"trades": trades,
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


def test_deploys_only_qualified_strategies(app):
    record(app, "tsmom.none.flip", "DEMO:DEMO-TREND", "1h", result("PAPER TEST"))
    record(app, "tsmom.none.trail", "DEMO:DEMO-RANGE", "1h", result("RESEARCH FURTHER", quality=50))   # strong, but
    record(app, "tsmom.none.time", "DEMO:DEMO-VOLATILE", "1h", result("REJECT", quality=90))          # not qualified
    app.autopilot.cycle()
    bots = {b.instrument_id: b for b in app.autopilot.bots()}
    assert bots["DEMO:DEMO-TREND"].tier == "qualified" and bots["DEMO:DEMO-TREND"].state == "running"
    assert set(bots) == {"DEMO:DEMO-TREND"}                  # no probation tier: no unverified fallback
    assert app.state.state == "PAPER_RUNNING"


def test_entries_wait_in_cash_until_a_strategy_qualifies(app):
    ok, why = app.qualification("tsmom.none.flip", "DEMO:DEMO-TREND", "1h")
    assert not ok and "not tested" in why
    record(app, "tsmom.none.flip", "DEMO:DEMO-TREND", "1h", result("RESEARCH FURTHER"))
    assert app.qualification("tsmom.none.flip", "DEMO:DEMO-TREND", "1h")[0] is False
    assert app.qualification("tsmom.none.flip", "DEMO:DEMO-TREND", "5m")[0] is False     # another timeframe: untested
    record(app, "tsmom.none.flip", "DEMO:DEMO-TREND", "1h", result("PAPER TEST"))
    assert app.qualification("tsmom.none.flip", "DEMO:DEMO-TREND", "1h")[0] is True


def test_a_bot_whose_strategy_says_buy_waits_until_the_strategy_qualifies(app, monkeypatch):
    from tradingai.engine import orchestrator as O
    monkeypatch.setattr(O.Strategy, "generate_signal", lambda self: O.Signal(1, 0, "tsmom.none.flip"))
    monkeypatch.setattr(O.daytrade, "entry_check", lambda cal, ms: (True, "OK", "test: inside the entry window"))
    app.autopilot.cfg.enabled = False
    bot = app.create_bot("DEMO:DEMO-TREND", "1h", "tsmom.none.flip", signal_mode="strategy")
    app.bot_action(bot["bot_id"], "start")
    app.tick()
    assert app.paper.get_positions() == {}
    last = app.db.one("SELECT outcome, reason FROM decisions WHERE bot_id=? ORDER BY ts DESC LIMIT 1", (bot["bot_id"],))
    assert last["outcome"] == "NO_TRADE" and last["reason"].startswith("STRATEGY_NOT_QUALIFIED"), dict(last)
    record(app, "tsmom.none.flip", "DEMO:DEMO-TREND", "1h", result("PAPER TEST"))
    rec = app.orch.decide(app.bots[bot["bot_id"]], "paper")              # the next bar's decision
    assert rec["outcome"] not in ("NO_TRADE",) and "STRATEGY_NOT_QUALIFIED" not in rec.get("reason", ""), rec
    app.paper.process()
    assert app.paper.get_positions().get("DEMO:DEMO-TREND", 0) > 0     # qualified: the same signal now trades


def test_risk_service_blocks_unqualified_entries_but_never_exits():
    from decimal import Decimal as D
    from tradingai.risk.service import OrderRequest, RiskService, Snapshot
    rs = RiskService()
    base = dict(instrument_id="DEMO:X", market="crypto", quantity=D(1), reference_price=D(100), limit_price=None,
                multiplier=D(1), environment="paper", account_id="P", qualified=(False, "not qualified"))
    entry = rs.check(OrderRequest(client_order_id="Q1", side="buy", sized_target=D(1), **base),
                     Snapshot(equity=D(100_000), positions={}, data_age_s=1))
    assert not entry.approved and "STRATEGY_NOT_QUALIFIED" in entry.reason_codes
    held = {"DEMO:X": {"qty": D(1), "price": D(100), "multiplier": D(1), "market": "crypto"}}
    ex = rs.check(OrderRequest(client_order_id="Q2", side="sell", reduces_position=True, **base),
                  Snapshot(equity=D(100_000), positions=held, data_age_s=1))
    assert ex.approved


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
    app.stop_all()                                       # Stop turns the autopilot off
    assert not app.autopilot.cfg.enabled
    app.start_all()                                      # Start System turns it back on
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
