"""The system switch ("Start System" / "Stop"): it drives the master agent in paper only, respects the owner's stops
and the kill switch, never trades live, and old bots from earlier releases are removed once flat."""

from decimal import Decimal

import pytest

from tradingai.app import App

from test_master import run, train


@pytest.fixture()
def app(tmp_path):
    a = App(str(tmp_path / "home"), offline=True, start_loop=False)
    yield a
    a.shutdown()


def test_on_by_default_and_paper_only(app):
    assert app.autopilot.cfg.enabled and app.mode == "paper"
    app.mode = "live"
    assert app.autopilot.cycle() == {"skipped": "live"}
    assert app.fleet.operate() == {"skipped": "live"}               # the master itself refuses live as well
    app.mode = "paper"


def test_a_cycle_drives_the_master(app, monkeypatch):
    calls = []
    monkeypatch.setattr(app, "submit_research", lambda *a, **k: calls.append(a) or {"job_id": f"J{len(calls)}"})
    monkeypatch.setattr(app.jobs, "view", lambda jid, with_result=False: {"state": "running"})
    out = app.autopilot.cycle()
    assert out["submitted"] and calls and app.autopilot.doing.startswith("training A00")
    app.autopilot.configure({"enabled": False})
    assert app.autopilot.cycle() == {"skipped": "off"}


def test_entries_wait_in_cash_until_a_strategy_qualifies(app):
    ok, why = app.qualification("tsmom.none.trail", "DEMO:DEMO-TREND", "1h")
    assert not ok and "not tested" in why
    run(app, "tsmom.none.trail", "DEMO:DEMO-TREND", "1h", verdict="RESEARCH FURTHER")
    assert app.qualification("tsmom.none.trail", "DEMO:DEMO-TREND", "1h")[0] is False
    assert app.qualification("tsmom.none.trail", "DEMO:DEMO-TREND", "15m")[0] is False   # another bar size: untested
    run(app, "tsmom.none.trail", "DEMO:DEMO-TREND", "1h")
    assert app.qualification("tsmom.none.trail", "DEMO:DEMO-TREND", "1h")[0] is True


def test_risk_service_blocks_unqualified_entries_but_never_exits():
    from tradingai.risk.service import OrderRequest, RiskService, Snapshot
    rs = RiskService()
    base = dict(instrument_id="DEMO:X", market="crypto", quantity=Decimal(1), reference_price=Decimal(100),
                limit_price=None, multiplier=Decimal(1), environment="paper", account_id="P",
                qualified=(False, "not qualified"))
    entry = rs.check(OrderRequest(client_order_id="Q1", side="buy", sized_target=Decimal(1), **base),
                     Snapshot(equity=Decimal(100_000), positions={}, data_age_s=1))
    assert not entry.approved and "STRATEGY_NOT_QUALIFIED" in entry.reason_codes
    held = {"DEMO:X": {"qty": Decimal(1), "price": Decimal(100), "multiplier": Decimal(1), "market": "crypto"}}
    ex = rs.check(OrderRequest(client_order_id="Q2", side="sell", reduces_position=True, **base),
                  Snapshot(equity=Decimal(100_000), positions=held, data_age_s=1))
    assert ex.approved


def test_candidates_are_the_active_versions(app):
    assert app.autopilot.candidates() == []
    train(app, "A004", [1.0, 0.5, 0.2])
    c = app.autopilot.candidates()
    assert [(x["agent"], x["iid"], x["strategy_id"], x["version"]) for x in c] == \
        [("A004", "DEMO:DEMO-TREND", "tsmom.none.trail", 1)]
    v = app.autopilot.view()
    assert v["counts"]["validated_agents"] == 1 and v["running"] == 1


def test_owner_stop_is_respected_and_stop_turns_the_system_off(app):
    train(app, "A004", [1.0, 0.5, 0.2])
    b = app.bots[app.fleet.bot_of["A004"]]
    app.bot_action(b.bot_id, "stop")                                  # the owner stops one agent's loop
    app.autopilot.cycle()
    assert b.state == "stopped"                                       # not restarted behind the owner's back
    app.stop_all()
    assert not app.autopilot.cfg.enabled and not app.fleet.permission("A004")[0]
    app.start_all()
    assert app.autopilot.cfg.enabled and b.state == "running" and app.fleet.permission("A004")[0]


def test_kill_switch_stops_everything_and_the_system_never_rearms_it(app):
    train(app, "A004", [1.0, 0.5, 0.2])
    app.emergency_stop("test", "owner")
    app.autopilot.cycle()
    assert all(b.state == "stopped" for b in app.bots.values()) and app.risk.kill_switch is not None
    with pytest.raises(PermissionError):
        app.start_all()


def test_bots_from_earlier_releases_are_removed_once_flat(app):
    old = app.create_bot("DEMO:DEMO-RANGE", "1h", "tsmom.none.flip", signal_mode="strategy", managed_by="autopilot")
    held = app.create_bot("DEMO:DEMO-VOLATILE", "1h", "tsmom.none.flip", signal_mode="strategy")
    real = app.paper.get_positions
    app.paper.get_positions = lambda: {"DEMO:DEMO-VOLATILE": Decimal(1)}
    try:
        app.fleet._sync_bots()
        assert old["bot_id"] not in app.bots                          # flat: replaced by the 100 agents
        assert held["bot_id"] in app.bots                              # holds a position: kept until it is flat
    finally:
        app.paper.get_positions = real
    app.fleet._sync_bots()
    assert held["bot_id"] not in app.bots
