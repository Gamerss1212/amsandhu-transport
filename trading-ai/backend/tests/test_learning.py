"""Continuous learning shared by the 100 agents: every mistake is recorded with its root cause, the first one of each
cause becomes a lesson whose safeguard applies to every agent, a regression replay proves the safeguard, repeats are
counted and three repeats suspend the agent. Safeguards can only block or shrink entries; exits are never touched."""

import json
import random
import time
from decimal import Decimal

import pytest

from tradingai.app import App
from tradingai.core.ids import new_id
from tradingai.engine import learning as L
from tradingai.risk.service import OrderRequest, RiskService, Snapshot
from tradingai.storage.db import dumps, now_ms

from test_master import _buy_signal, train


@pytest.fixture()
def app(tmp_path):
    a = App(str(tmp_path / "home"), offline=True, start_loop=False)
    yield a
    a.shutdown()


# one representative scenario per root cause (the shape the orchestrator stores; see Orchestrator._guard_context)
SCENARIOS = {
    "CONTROL_ENGAGED": {"controls_engaged": "entries paused", "qty": "1"},
    "MARKET_CLOSED": {"session_open": False, "qty": "1"},
    "STALE_DATA": {"data_age_s": 8000, "bar_seconds": 3600, "qty": "1"},
    "DUPLICATE_ORDER": {"open_orders": 1, "qty": "1"},
    "ORDER_RATE": {"orders_last_minute": 26, "max_orders_per_minute": 30, "qty": "1"},
    "EXECUTION_ERROR": {"cooldown_s": 900, "qty": "1", "instrument_id": "X:1"},
    "DATA_ERROR": {"cooldown_s": 900, "qty": "1", "instrument_id": "X:2"},
    "BAD_PRICE": {"price_deviation": 0.045, "max_price_deviation": 0.05, "qty": "1"},
    "SIZE_OVER_LIMIT": {"limits": {"order": "1000", "gross": "500"}, "price": "100", "multiplier": "1", "qty": "10"},
    "LIQUIDITY": {"participation_qty": "5", "qty": "10"},
    "LOSS_BEYOND_PLAN_HIGH_VOL": {"vol_regime": "high", "qty": "1"},
    "LOSS_BEYOND_PLAN_SLIPPAGE": {"market": "crypto", "qty": "1"},
    "AGENT_LOSS_LIMIT": {"agent_day_stopped": True, "qty": "1"},
}


def test_every_root_cause_has_a_scenario_and_a_safeguard_that_changes_the_outcome(app):
    assert set(SCENARIOS) | {"VERSION_UNDERPERFORMED"} == set(L.ROOT_CAUSES)
    for rc, sc in SCENARIOS.items():
        before = app.learning.guard(sc, only=set())                  # no lesson: the guard does nothing
        assert before["allow"] and before["qty"] == Decimal(sc["qty"]), rc
        app.learning.record(rc, agent_id="A004", instrument_id=sc.get("instrument_id", "DEMO:DEMO-TREND"),
                            detail={"market": sc.get("market")}, scenario=sc)
        after = app.learning.guard(sc, only={rc})
        assert (not after["allow"]) or after["qty"] < Decimal(sc["qty"]), rc
    run = app.learning.replay_all("test")
    assert run["scenarios"] == len(SCENARIOS) and run["passed"] == len(SCENARIOS) and run["failed"] == []
    assert app.db.one("SELECT COUNT(*) AS n FROM regression_runs")["n"] >= len(SCENARIOS)   # one per new lesson too


def test_a_risk_denial_of_an_agents_entry_becomes_a_shared_lesson(app):
    rs = RiskService()
    req = OrderRequest(client_order_id="E1", instrument_id="DEMO:DEMO-TREND", market="crypto", side="buy",
                       quantity=Decimal(1), reference_price=Decimal(100), limit_price=None, multiplier=Decimal(1),
                       environment="paper", account_id="P", agent_id="A004")
    snap = Snapshot(equity=Decimal(100_000), positions={}, data_age_s=20_000, bar_seconds=3600)
    d = rs.check(req, snap)
    assert not d.approved
    ctx = {"agent_id": "A004", "qty": "1", "data_age_s": 20_000, "bar_seconds": 3600}
    out = app.learning.record_rejection(req, d, ctx)
    assert [o["repeat"] for o in out] == [False]
    les = app.learning.lessons["STALE_DATA"]
    assert les["first_agent"] == "A004" and les["safeguard"] == "require_fresh_data"
    # the safeguard now applies to EVERY agent, before the risk service sees the order
    other = {"agent_id": "A050", "qty": "3", "data_age_s": 8000, "bar_seconds": 3600}
    g = app.learning.guard(other)
    assert not g["allow"] and g["applied"][0].startswith("STALE_DATA")
    assert app.learning.guard(dict(other, data_age_s=100))["allow"]
    assert app.learning.record_rejection(req, d, ctx)[0]["repeat"] is True
    row = app.db.one("SELECT * FROM mistakes WHERE repeat=1")
    assert row["agent_id"] == "A004" and row["ref"] == "E1" and row["root_cause"] == "STALE_DATA"
    # an exit is never a mistake: the risk service may refuse it, but no lesson restricts exits
    ex = OrderRequest(client_order_id="E2", instrument_id="DEMO:DEMO-TREND", market="crypto", side="sell",
                      quantity=Decimal(1), reference_price=Decimal(100), limit_price=None, multiplier=Decimal(1),
                      environment="paper", account_id="P", agent_id="A004", reduces_position=True)
    assert app.learning.record_rejection(ex, d, ctx) == []


def test_the_order_authority_reports_a_denied_agent_entry(app):
    req = OrderRequest(client_order_id="", instrument_id="DEMO:DEMO-TREND", market="crypto", side="buy",
                       quantity=Decimal(1), reference_price=Decimal(100), limit_price=None, multiplier=Decimal(1),
                       environment="paper", account_id=app.paper.get_balance().account_id_masked, agent_id="A004")
    out = app.oms.place(decision_id="D1", req=req, snapshot=Snapshot(equity=Decimal(100_000), positions={},
                                                                         market_open=False),
                        broker=app.paper, broker_symbol="DEMO-TREND", mode="paper", strategy_id="tsmom.none.trail",
                        decided_at=time.time(), context={"session_open": False, "qty": "1"})
    assert out["status"] == "BLOCKED_BY_RISK" and "_decision" not in out
    assert "MARKET_CLOSED" in app.learning.lessons
    assert app.learning.replay_all("test")["failed"] == []


def test_safeguards_never_raise_a_quantity(app):
    for rc, sc in SCENARIOS.items():
        app.learning.record(rc, agent_id=None, instrument_id=sc.get("instrument_id"), detail={"market": "crypto"},
                            scenario=sc)
    rnd = random.Random(7)
    for _ in range(3000):
        q = Decimal(str(round(rnd.uniform(0, 50), 4)))
        ctx = {"qty": str(q), "price": str(round(rnd.uniform(0.01, 500), 4)), "multiplier": "1",
               "quantity_step": rnd.choice([None, "0.001", "1"]),
               "vol_regime": rnd.choice([None, "low", "normal", "high"]),
               "market": rnd.choice(["crypto", "stock", "fx"]),
               "participation_qty": rnd.choice([None, str(round(rnd.uniform(0, 80), 3))]),
               "limits": rnd.choice([None, {"order": str(rnd.uniform(-10, 5000)), "gross": str(rnd.uniform(0, 9000))}]),
               "data_age_s": rnd.uniform(0, 9000), "bar_seconds": rnd.choice([900, 3600]),
               "open_orders": rnd.choice([0, 0, 1]), "orders_last_minute": rnd.randint(0, 40),
               "max_orders_per_minute": 30, "price_deviation": rnd.uniform(0, 0.06), "max_price_deviation": 0.05,
               "session_open": rnd.choice([True, True, False]), "cooldown_s": rnd.choice([0, 0, 30]),
               "agent_day_stopped": rnd.random() < 0.1, "controls_engaged": rnd.choice([None] * 9 + ["locked"])}
        out = app.learning.guard(ctx)
        assert out["qty"] <= q, (ctx, out)
        assert out["allow"] or out["qty"] == 0
        assert out["qty"] >= 0


def test_three_repeats_within_24_hours_suspend_the_agent(app):
    train(app, "A004", [1.0, 0.5, 0.2])
    assert app.fleet.permission("A004")[0]
    sc = SCENARIOS["DUPLICATE_ORDER"]
    for k in range(4):                                              # 1 new lesson + 3 repeats
        r = app.learning.record("DUPLICATE_ORDER", agent_id="A004", instrument_id="DEMO:DEMO-TREND", detail={},
                                scenario=sc)
        assert r["repeat"] is (k > 0)
    ok, why = app.fleet.permission("A004")
    assert not ok and "3 repeats of DUPLICATE_ORDER" in why
    les = app.learning.lessons["DUPLICATE_ORDER"]
    assert les["occurrences"] == 4 and les["repeats"] == 3
    assert app.fleet.permission("A005")[0] is False                 # (no version) - but not suspended
    assert "A005" not in app.fleet.suspended


def test_an_execution_error_starts_a_cooldown_on_that_instrument(app):
    r = app.learning.record("EXECUTION_ERROR", agent_id="A004", instrument_id="DEMO:DEMO-TREND",
                            detail={"error": "timeout"}, scenario=SCENARIOS["EXECUTION_ERROR"])
    assert not r["repeat"]
    left = app.learning.cooldown_left("DEMO:DEMO-TREND")
    assert 800 < left <= 900
    assert app.learning.cooldown_left("DEMO:DEMO-RANGE") == 0
    again = app.learning.record("EXECUTION_ERROR", agent_id="A004", instrument_id="DEMO:DEMO-TREND", detail={},
                                scenario=SCENARIOS["EXECUTION_ERROR"])
    assert "skipped" in again                                       # one error burst is one mistake, not hundreds
    assert not app.learning.guard({"qty": "1", "cooldown_s": left})["allow"]


def _trip(app, iid, entry, exit_, planned, vol, qty="1"):
    did = new_id("DEC")
    t = now_ms() + 5
    app.db.execute("INSERT INTO decisions (decision_id, ts, instrument_id, strategy_id, mode, regime, order_json, "
                   "outcome, reason) VALUES (?,?,?,?,?,?,?,?,?)",
                   (did, t, iid, "tsmom.none.trail", "paper", dumps({"volatility": vol}),
                    dumps({"planned_risk": planned}), "ORDER", "test"))
    for k, (side, px) in enumerate((("buy", entry), ("sell", exit_))):
        cid = new_id("C")
        app.db.execute("INSERT INTO orders (client_order_id, decision_id, strategy_id, account_id, environment, "
                       "instrument_id, side, qty, order_type, tif, status, created, updated) VALUES "
                       "(?,?,?,?,?,?,?,?,?,?,?,?,?)", (cid, did if k == 0 else None, "tsmom.none.trail",
                                                       app.paper.account_id, "paper", iid, side, qty, "market",
                                                       "day", "FILLED", t, t))
        app.db.execute("INSERT INTO fills (fill_id, client_order_id, account_id, instrument_id, side, qty, price, fee, "
                       "fee_currency, liquidity, environment, ts) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                       (new_id("F"), cid, app.paper.account_id, iid, side, qty, str(px), "0", "USD", "taker", "paper",
                        t + k + 1))


def test_closed_trades_that_lose_more_than_planned_become_lessons(app):
    _trip(app, "DEMO:DEMO-TREND", 100, 95, "10", "high")            # lost 5: within plan
    assert app.learning.scan_trades() == []
    _trip(app, "DEMO:DEMO-TREND", 100, 80, "10", "high")            # lost 20 > 1.5 x 10, high volatility
    out = app.learning.scan_trades()
    assert len(out) == 1 and "LOSS_BEYOND_PLAN_HIGH_VOL" in app.learning.lessons
    m = app.db.one("SELECT * FROM mistakes WHERE root_cause='LOSS_BEYOND_PLAN_HIGH_VOL'")
    assert m["agent_id"] == "A004" and json.loads(m["detail"])["loss"] == "20"
    g = app.learning.guard({"qty": "2", "vol_regime": "high"})
    assert g["allow"] and g["qty"] == Decimal("1")                  # half size in high volatility, for every agent
    _trip(app, "DEMO:DEMO-RANGE", 100, 70, "10", "normal")          # normal regime: gap or slippage beyond the model
    app.learning.scan_trades()
    g = app.learning.guard({"qty": "4", "market": "crypto"})
    assert g["qty"] == Decimal("3")
    assert app.learning.guard({"qty": "4", "market": "stock"})["qty"] == Decimal("4")   # only the market it happened in
    assert app.learning.scan_trades() == []                          # each trip is examined once


def test_metrics_measure_mistakes_per_100_decisions_week_over_week(app):
    t = now_ms()
    for k in range(40):
        app.db.execute("INSERT INTO decisions (decision_id, ts, instrument_id, mode, outcome) VALUES (?,?,?,?,?)",
                       (new_id("DEC"), t - 1000 - k, "DEMO:DEMO-TREND", "paper", "NO_TRADE"))
        app.db.execute("INSERT INTO decisions (decision_id, ts, instrument_id, mode, outcome) VALUES (?,?,?,?,?)",
                       (new_id("DEC"), t - 8 * L.DAY - k, "DEMO:DEMO-TREND", "paper", "NO_TRADE"))
    for k in range(4):
        app.db.execute("INSERT INTO mistakes (mistake_id, ts, agent_id, instrument_id, kind, root_cause, detail, "
                       "lesson_id, repeat, ref) VALUES (?,?,?,?,?,?,?,?,?,?)",
                       (new_id("MIS"), t - 8 * L.DAY - k, "A004", "DEMO:DEMO-TREND", "execution", "DUPLICATE_ORDER",
                        "{}", None, int(k > 0), None))
    app.learning.record("DUPLICATE_ORDER", agent_id="A004", instrument_id="DEMO:DEMO-TREND", detail={},
                        scenario=SCENARIOS["DUPLICATE_ORDER"])
    m = app.learning.metrics()
    assert m["last_week"] == {"mistakes": 4, "repeats": 3, "decisions": 40, "per_100_decisions": 10.0}
    assert m["this_week"]["mistakes"] == 1 and m["this_week"]["per_100_decisions"] == 2.5
    assert m["lessons"] == 1 and m["regression"]["failed"] == []


def test_entries_are_shrunk_or_skipped_by_lessons_but_exits_still_go_through(app, monkeypatch):
    _buy_signal(monkeypatch)
    train(app, "A004", [1.0, 0.5, 0.2])
    bot = app.bots[app.fleet.bot_of["A004"]]
    rec = app.orch.decide(bot, "paper")
    assert rec["outcome"] == "ORDER"
    app.paper.process()
    held = app.paper.get_positions()["DEMO:DEMO-TREND"]
    assert held > 0
    # a lesson that blocks entries while controls are engaged, then the owner pauses entries
    app.learning.record("CONTROL_ENGAGED", agent_id="A005", instrument_id="DEMO:DEMO-RANGE", detail={},
                        scenario=SCENARIOS["CONTROL_ENGAGED"])
    app.pause_entries(True, "owner", "test")
    from tradingai.engine import orchestrator as O
    monkeypatch.setattr(O.Strategy, "generate_signal", lambda self: O.Signal(0, 0, self.spec.strategy_id))
    bot.last_bar_ts = None
    rec = app.orch.decide(bot, "paper")                              # the exit is not touched by any safeguard
    assert rec["outcome"] == "ORDER" and rec["order"]["side"] == "sell", rec
    assert "safeguards" not in rec


def test_lessons_persist_and_are_replayed_at_every_start(tmp_path):
    home = str(tmp_path / "home")
    a = App(home, offline=True, start_loop=False)
    a.learning.record("STALE_DATA", agent_id="A004", instrument_id="DEMO:DEMO-TREND", detail={},
                      scenario=SCENARIOS["STALE_DATA"])
    a.shutdown()
    b = App(home, offline=True, start_loop=False)
    try:
        assert "STALE_DATA" in b.learning.lessons
        chk = next(c for c in b.checks if c["name"].startswith("learning"))
        assert chk["ok"] and "1/1 regression scenario(s) pass" in chk["detail"]
        assert not b.learning.guard({"qty": "1", "data_age_s": 9000, "bar_seconds": 3600})["allow"]
    finally:
        b.shutdown()


def test_a_safeguard_that_stops_working_fails_the_start_up_check(tmp_path):
    home = str(tmp_path / "home")
    a = App(home, offline=True, start_loop=False)
    a.learning.record("STALE_DATA", agent_id="A004", instrument_id="DEMO:DEMO-TREND", detail={},
                      scenario=SCENARIOS["STALE_DATA"])
    # simulate a regression: the stored scenario no longer trips the safeguard (e.g. its rule was weakened)
    a.db.execute("UPDATE lessons SET scenario=? WHERE root_cause='STALE_DATA'",
                 (dumps({"data_age_s": 10, "bar_seconds": 3600, "qty": "1"}),))
    a.shutdown()
    b = App(home, offline=True, start_loop=False)
    try:
        chk = next(c for c in b.checks if c["name"].startswith("learning"))
        assert not chk["ok"] and "STALE_DATA" in chk["detail"]
        assert b.state.state == "ERROR"                              # the system does not start trading
    finally:
        b.shutdown()


def test_upgrading_an_older_database_keeps_a_recoverable_copy_first(tmp_path, monkeypatch):
    from tradingai.storage import db as DB
    path = tmp_path / "data" / "app.sqlite3"
    monkeypatch.setattr(DB, "MIGRATIONS", DB.MIGRATIONS[:4])        # a 1.4.1 database (schema 4)
    old = DB.Database(path)
    old.set_setting("marker", {"from": "1.4.1"})
    assert old.version == 4 and old.pre_upgrade_backup is None
    old.close()
    monkeypatch.undo()
    new = DB.Database(path)
    try:
        assert new.version == len(DB.MIGRATIONS) and new.pre_upgrade_backup is not None
        assert new.pre_upgrade_backup.name.startswith("pre-upgrade-schema4-")
        import sqlite3
        con = sqlite3.connect(str(new.pre_upgrade_backup))
        assert con.execute("SELECT version FROM schema_version").fetchone()[0] == 4
        assert con.execute("SELECT COUNT(*) FROM sqlite_master WHERE name='agent_versions'").fetchone()[0] == 0
        assert "1.4.1" in con.execute("SELECT value FROM settings WHERE key='marker'").fetchone()[0]
        con.close()
    finally:
        new.close()
