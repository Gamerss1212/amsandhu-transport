"""Safety tests: the risk service rejects bad orders (section 286), the OMS never sends an order twice, the paper
ledger balances, and a restart restores the kill switch and paper bots but never LIVE mode."""

from __future__ import annotations

from decimal import Decimal as D

import pytest

from tradingai.brokers.base import BrokerError
from tradingai.brokers.paper import PaperBroker
from tradingai.core.events import EventBus
from tradingai.core.ids import client_order_id
from tradingai.execution.oms import OMS
from tradingai.market import universe
from tradingai.risk.service import RAISE_PHRASE, REARM_PHRASE, Limits, OrderRequest, RiskService, Snapshot
from tradingai.storage.db import Database


def req(**kw) -> OrderRequest:
    base = dict(client_order_id="TA-1", instrument_id="COINBASE:BTC-USD", market="crypto", side="buy",
                quantity=D("0.01"), reference_price=D("60000"), limit_price=None, multiplier=D(1),
                environment="paper", account_id="PAPER-1", sized_target=D("0.01"))
    base.update(kw)
    return OrderRequest(**base)


def snap(**kw) -> Snapshot:
    base = dict(equity=D(100_000), positions={}, data_age_s=5.0, bar_seconds=60.0, account_id="PAPER-1",
                environment="paper")
    base.update(kw)
    return Snapshot(**base)


def failed(decision) -> set[str]:
    return {c.name for c in decision.checks if not c.passed}


# ---------------------------------------------------------------- risk: bad orders are denied
def test_good_order_is_approved():
    d = RiskService().check(req(), snap())
    assert d.approved and d.quantity == D("0.01") and not d.adjusted


@pytest.mark.parametrize("order,snapshot,check", [
    (req(limit_price=D("66000")), snap(), "price within band"),                          # fat-finger price
    (req(quantity=D("0.05"), sized_target=D("0.01")), snap(), "quantity matches the sized target"),
    (req(quantity=D(0)), snap(), "positive quantity"),
    (req(reference_price=D(0)), snap(), "valid price"),
    (req(side="hold"), snap(), "valid side"),
    (req(market="index"), snap(), "known market"),                                       # wrong market
    (req(account_id="OTHER-9"), snap(), "account validated"),                            # account mismatch
    (req(environment="live"), snap(), "account validated"),                              # environment mismatch
    (req(), snap(data_age_s=600.0), "data fresh"),                                       # stale data
    (req(), snap(market_open=False), "market open"),
    (req(), snap(broker_ok=False), "broker connected"),
    (req(), snap(reconciliation_ok=False), "reconciliation clean"),
    (req(tradable=(False, "reference index")), snap(), "instrument tradable"),
    (req(permitted=(False, "no futures permission")), snap(), "broker permits this product"),
    (req(multiplier=D(0)), snap(), "valid contract multiplier"),
    (req(), snap(equity=D(0)), "positive equity"),
])
def test_bad_orders_are_denied(order, snapshot, check):
    d = RiskService().check(order, snapshot)
    assert not d.approved and d.quantity == 0
    assert check in failed(d), d.reason


def test_oversized_order_is_shrunk_to_the_venue_step_never_grown():
    o = req(instrument_id="DEMO:DEMO-TREND", quantity=D("5"), sized_target=D("5"), reference_price=D("5471.99"),
            quantity_step=D("0.0001"))
    d = RiskService().check(o, snap())
    assert d.approved and d.adjusted and d.quantity < D("5")
    assert d.quantity == (d.quantity / D("0.0001")).to_integral_value() * D("0.0001")          # on the step
    assert d.quantity * D("5471.99") <= D(10_000)                                               # 10% of equity


def test_excess_leverage_and_exposure_are_denied():
    big = {f"X{i}": {"qty": D(1), "price": D(25_000), "multiplier": D(1), "market": "future"} for i in range(8)}  # 2.0x
    o = req(instrument_id="CME:ES", market="future", quantity=D(1), sized_target=D(1), reference_price=D(100),
            multiplier=D(50))
    d = RiskService().check(o, snap(positions=big))
    assert not d.approved and {"gross exposure", "leverage"} <= failed(d)


def pos(qty, price, market="crypto", mult=1):
    return {"qty": D(qty), "price": D(price), "multiplier": D(mult), "market": market}


def test_position_limit_denied_when_adding_to_a_large_position():
    held = {"COINBASE:BTC-USD": pos("0.41", 60000)}                    # 24.6% of equity already; +0.6% breaks 25%
    d = RiskService().check(req(quantity=D("0.01"), sized_target=D("0.01")), snap(positions=held))
    assert not d.approved and "position limit" in failed(d)


def test_asset_class_and_correlated_cluster_limits():
    held = {"COINBASE:ETH-USD": pos(10, 3000), "COINBASE:SOL-USD": pos(100, 150)}   # 45k crypto
    o = req(quantity=D("0.1"), sized_target=D("0.1"))                             # +6k BTC
    d = RiskService().check(o, snap(positions=held, clusters=[["COINBASE:BTC-USD", "COINBASE:ETH-USD",
                                                                 "COINBASE:SOL-USD"]]))
    assert not d.approved and {"asset-class exposure", "correlated exposure"} <= failed(d)


def test_open_positions_cap():
    held = {f"US:X{i}": pos(1, 100, "stock") for i in range(10)}
    d = RiskService().check(req(), snap(positions=held))
    assert not d.approved and "open positions" in failed(d)


def test_liquidity_and_spread_checks():
    d = RiskService().check(req(), snap(last_volume=0.05, spread_bps=80.0))     # 20% of the bar's volume, wide spread
    assert not d.approved and {"liquidity", "spread"} <= failed(d)


def test_event_restriction_blocks_entries():
    d = RiskService().check(req(), snap(event_block="FOMC in 10 minutes"))
    assert not d.approved and "no event restriction" in failed(d)


def test_order_rate_limit():
    rs = RiskService(Limits(max_orders_per_minute=3, duplicate_window_s=0))
    for i in range(3):
        assert rs.check(req(client_order_id=f"R{i}", quantity=D("0.01") + D(i) / 1000,
                            sized_target=D("0.02")), snap()).approved
    d = rs.check(req(client_order_id="R9", quantity=D("0.015"), sized_target=D("0.02")), snap())
    assert not d.approved and "order rate" in failed(d)


def test_weekly_loss_and_drawdown_locks():
    rs = RiskService(Limits(max_daily_loss_pct=0.5, max_weekly_loss_pct=0.06, max_drawdown_pct=0.5))
    rs.on_equity(D(100_000), "2026-10-05", "2026-W41")
    rs.on_equity(D(97_000), "2026-10-06", "2026-W41")             # new day: daily reference resets
    assert rs.on_equity(D(93_900), "2026-10-07", "2026-W41") == ["weekly loss"]
    rs2 = RiskService(Limits(max_daily_loss_pct=0.5, max_weekly_loss_pct=0.5, max_drawdown_pct=0.15))
    rs2.on_equity(D(100_000), "2026-09-01", "2026-W36")
    rs2.on_equity(D(120_000), "2026-09-20", "2026-W38")
    assert rs2.on_equity(D(101_000), "2026-10-07", "2026-W41") == ["drawdown"]   # 15.8% below the 120k peak


def test_duplicate_order_is_blocked_and_counted():
    rs = RiskService()
    assert rs.check(req(), snap()).approved
    d = rs.check(req(client_order_id="TA-2"), snap())           # same instrument, side and size within 10 s
    assert not d.approved and "not a duplicate" in failed(d)
    assert rs.counters["duplicates_blocked"] == 1


def test_reduce_only_claim_is_verified_against_positions():
    rs = RiskService()
    rs.engage_kill_switch("test", "test")
    held = {"COINBASE:BTC-USD": {"qty": D("0.02"), "price": D(60000), "multiplier": D(1), "market": "crypto"}}
    # a genuine exit passes even with the kill switch engaged
    assert rs.check(req(side="sell", reduces_position=True), snap(positions=held)).approved
    # claiming "reduce" on a buy (adds to the position) is caught and denied
    d = rs.check(req(client_order_id="TA-3", side="buy", quantity=D("0.03"), reduces_position=True),
                 snap(positions=held))
    assert not d.approved and {"reduce-only claim verified", "kill switch not engaged"} <= failed(d)


def test_kill_switch_blocks_new_orders_until_rearmed_with_the_phrase():
    rs = RiskService()
    rs.engage_kill_switch("owner pressed stop", "owner")
    assert not rs.check(req(), snap()).approved
    with pytest.raises(PermissionError):
        rs.rearm("yes please", "owner")
    rs.rearm(REARM_PHRASE, "owner")
    assert rs.check(req(client_order_id="TA-9", quantity=D("0.011"), sized_target=D("0.011")), snap()).approved


def test_raising_a_limit_needs_the_typed_phrase_lowering_does_not():
    rs = RiskService()
    rs.update_limits({"max_daily_loss_pct": 0.01}, "owner")                       # lower: allowed
    with pytest.raises(PermissionError):
        rs.update_limits({"max_daily_loss_pct": 0.5}, "agent")                    # raise without phrase: refused
    assert rs.limits.max_daily_loss_pct == 0.01
    rs.update_limits({"max_daily_loss_pct": 0.02}, "owner", confirm=RAISE_PHRASE)
    assert rs.limits.max_daily_loss_pct == 0.02


def test_daily_loss_breaker_locks_trading():
    rs = RiskService(Limits(max_daily_loss_pct=0.03))
    assert rs.on_equity(D(100_000), "2026-10-08", "2026-W41") == []
    assert rs.on_equity(D(96_900), "2026-10-08", "2026-W41") == ["daily loss"]
    d = rs.check(req(), snap(equity=D(96_900)))
    assert not d.approved and "trading not locked" in failed(d)


# ---------------------------------------------------------------- paper broker and OMS
@pytest.fixture()
def paper(tmp_path):
    book, _ = universe.build()
    prices = {"DEMO:DEMO-TREND": D("100.00"), "CME:ES": D("5000.00")}
    quote = lambda iid: {"price": prices[iid], "ts": 0, "volume": None, "sigma": 0.0, "range": 0.0}  # noqa: E731
    db = Database(tmp_path / "t.sqlite3")
    return PaperBroker(db, book, quote), prices, db


def test_paper_round_trip_closes_the_position_and_balances(paper):
    pb, prices, db = paper
    b = pb.submit_order(client_order_id="A1", instrument_id="DEMO:DEMO-TREND", side="buy", qty=D("10.5"))
    assert b.status == "FILLED"
    prices["DEMO:DEMO-TREND"] = D("110.00")
    s = pb.submit_order(client_order_id="A2", instrument_id="DEMO:DEMO-TREND", side="sell", qty=D("10.5"))
    assert s.status == "FILLED"
    assert pb.get_positions() == {}                       # fully closed: not listed as an open zero position
    inv = pb.invariant()
    assert inv["ok"]
    fills = db.query("SELECT qty, price, fee, side FROM fills ORDER BY ts")
    cash = D(100_000) + sum((D(f["qty"]) * D(f["price"]) * (1 if f["side"] == "sell" else -1) - D(f["fee"])
                             for f in fills), D(0))
    assert D(inv["cash"]) == cash == pb.get_balance().cash
    assert pb.get_balance().equity == cash.quantize(D("0.01"))


def test_paper_futures_use_the_multiplier(paper):
    pb, prices, _ = paper
    pb.submit_order(client_order_id="F1", instrument_id="CME:ES", side="buy", qty=D(1))
    entry = pb.get_order("F1").avg_price
    prices["CME:ES"] = entry + D("10")
    pb.submit_order(client_order_id="F2", instrument_id="CME:ES", side="sell", qty=D(1))
    exit_ = pb.get_order("F2").avg_price
    realized = sum(D(r["amount"]) for r in pb.db.query("SELECT amount FROM ledger WHERE kind='realized'"))
    assert realized == (exit_ - entry) * 50


def test_paper_rejects_spot_short_and_resubmit_is_idempotent(paper):
    pb, _, db = paper
    assert pb.submit_order(client_order_id="S1", instrument_id="DEMO:DEMO-TREND", side="sell",
                           qty=D(1)).status == "REJECTED"
    pb.submit_order(client_order_id="B1", instrument_id="DEMO:DEMO-TREND", side="buy", qty=D(1))
    pb.submit_order(client_order_id="B1", instrument_id="DEMO:DEMO-TREND", side="buy", qty=D(1))
    assert len(db.query("SELECT * FROM fills WHERE client_order_id='B1'")) == 1


class TimesOutAfterSending(PaperBroker):
    """Simulates the dangerous case: the order reaches the broker, then the response is lost."""
    def submit_order(self, **kw):
        super().submit_order(**kw)
        raise BrokerError("timeout")


def test_oms_never_sends_twice_after_an_uncertain_submission(tmp_path):
    book, _ = universe.build()
    quote = lambda iid: {"price": D("100"), "ts": 0, "volume": None, "sigma": 0.0, "range": 0.0}  # noqa: E731
    db = Database(tmp_path / "o.sqlite3")
    broker = TimesOutAfterSending(db, book, quote)
    risk = RiskService(Limits(duplicate_window_s=0))
    oms = OMS(db, risk, EventBus(), audit=lambda *a, **k: None)
    o = lambda: req(instrument_id="DEMO:DEMO-TREND", quantity=D(2), sized_target=D(2),  # noqa: E731
                    reference_price=D(100), quantity_step=D("0.0001"))
    first = oms.place(decision_id="DEC-1", req=o(), snapshot=snap(), broker=broker, broker_symbol="X", mode="paper",
                      strategy_id="s", decided_at=0)
    assert first["status"] == "UNKNOWN"                   # never assumed unsent
    cid = client_order_id("DEC-1", 0)
    assert first["client_order_id"] == cid
    # a retry of the same decision asks the broker first and does not send again
    again = oms.place(decision_id="DEC-1", req=o(), snapshot=snap(), broker=broker, broker_symbol="X", mode="paper",
                      strategy_id="s", decided_at=0)
    assert again.get("note", "").startswith("already at the broker")
    assert len(db.query("SELECT * FROM fills WHERE client_order_id=?", (cid,))) == 1
    rows = db.query("SELECT status FROM orders WHERE client_order_id=?", (cid,))
    assert [r["status"] for r in rows] == ["FILLED"]       # one order, known to the broker
    assert all("resolved" in r for r in oms.resolve_unknown(broker))


def test_shadow_mode_never_sends(tmp_path):
    book, _ = universe.build()
    quote = lambda iid: {"price": D("100"), "ts": 0, "volume": None, "sigma": 0.0, "range": 0.0}  # noqa: E731
    db = Database(tmp_path / "s.sqlite3")
    pb = PaperBroker(db, book, quote)
    oms = OMS(db, RiskService(), EventBus(), audit=lambda *a, **k: None)
    r = oms.place(decision_id="DEC-S", req=req(instrument_id="DEMO:DEMO-TREND", quantity=D(1), sized_target=D(1),
                                              reference_price=D(100)),
                  snapshot=snap(), broker=pb, broker_symbol="X", mode="shadow", strategy_id="s", decided_at=0)
    assert r["status"] == "SHADOW_NOT_SENT"
    assert db.query("SELECT * FROM orders") == [] and db.query("SELECT * FROM fills") == []


def test_live_order_refused_without_a_connected_live_broker(paper):
    pb, _, db = paper
    oms = OMS(db, RiskService(), EventBus(), audit=lambda *a, **k: None)
    r = oms.place(decision_id="DEC-L", req=req(environment="live"), snapshot=snap(environment="live"), broker=pb,
                  broker_symbol="X", mode="live", strategy_id="s", decided_at=0)
    assert r["status"] == "BLOCKED"
    assert db.query("SELECT * FROM orders") == []


# ---------------------------------------------------------------- the app: modes, arming, recovery
def test_live_cannot_be_entered_without_arming(tmp_path):
    from tradingai.app import LIVE_ACK, App
    app = App(str(tmp_path / "home"), offline=True, start_loop=False)
    try:
        assert app.mode == "paper"
        with pytest.raises(PermissionError):
            app.set_mode("live")
        with pytest.raises(PermissionError):
            app.arm_live("CONN-none", "yes", D(100), D(10))                       # wrong acknowledgement
        with pytest.raises(PermissionError, match="LIVE NOT READY"):
            app.arm_live("CONN-none", LIVE_ACK, D(100), D(10))                   # no verified live connection
        assert app.mode == "paper" and not app.live["armed"]
    finally:
        app.shutdown()


def test_restart_restores_kill_switch_and_paper_bots_but_never_live(tmp_path):
    from tradingai.app import App
    home = str(tmp_path / "home")
    app = App(home, offline=True, start_loop=False)
    bot = app.create_bot("DEMO:DEMO-TREND", "5m", "tsmom.none.flip")
    app.bot_action(bot["bot_id"], "start")
    app.shutdown()

    app2 = App(home, offline=True, start_loop=False)          # paper session: running bots resume in paper
    try:
        assert app2.mode == "paper" and app2.bots[bot["bot_id"]].state == "running"
        app2.db.set_setting("mode", "live")                     # pretend this session was live
    finally:
        app2.shutdown()

    app3 = App(home, offline=True, start_loop=False)          # after a LIVE session: back to paper, bots stopped
    try:
        assert app3.mode == "paper" and app3.bots[bot["bot_id"]].state == "stopped"
        app3.emergency_stop("test", "owner")
    finally:
        app3.shutdown()

    app4 = App(home, offline=True, start_loop=False)
    try:
        assert app4.risk.kill_switch is not None               # STOP ALL TRADING survives a restart
        with pytest.raises(PermissionError):
            app4.bot_action(bot["bot_id"], "start")
        assert app4.db.verify_audit()[0]                        # audit chain intact across restarts
    finally:
        app4.shutdown()


def test_account_view_with_no_positions(tmp_path):
    from tradingai.app import App
    app = App(str(tmp_path / "home"), offline=True, start_loop=False)
    try:
        v = app.account_view()
        assert v["realized"] == "0.00" and v["unrealized"] == "0.00" and v["badge"] == "SIMULATED"
    finally:
        app.shutdown()


def test_api_guard_and_shutdown(tmp_path):
    """Through the real ASGI app: token, Host and Origin checks, then the Shut down button stops the core."""
    from fastapi.testclient import TestClient

    from tradingai.api.server import create_app
    from tradingai.app import App
    app = App(str(tmp_path / "home"), offline=True, start_loop=False)
    stopped = []
    api = create_app(app, token="T0K", on_shutdown=lambda: stopped.append(True))
    c = TestClient(api, base_url="http://127.0.0.1:8000")
    assert c.get("/api/overview").status_code == 401
    assert c.get("/api/overview", headers={"X-TA-Token": "T0K"}).json()["mode"] == "paper"
    assert c.get("/health", headers={"Host": "attacker.example"}).status_code == 421
    assert c.post("/api/bot/start", headers={"X-TA-Token": "T0K", "Origin": "http://attacker.example"}).status_code == 403
    r = c.post("/api/mode", json={"mode": "live"}, headers={"X-TA-Token": "T0K"})
    assert r.status_code == 403
    r = c.post("/api/system/shutdown", headers={"X-TA-Token": "T0K", "Origin": "http://127.0.0.1:8000"})
    assert r.status_code == 200 and r.json()["stopped"] is True
    assert app.state.state == "SHUTTING_DOWN"


def test_paper_balance_change_is_not_a_loss_and_references_survive_restart(tmp_path):
    from tradingai.app import App
    home = str(tmp_path / "home")
    app = App(home, offline=True, start_loop=False)
    app.tick()                                               # sets the day's reference at 100,000
    app.set_paper_balance(D(25_000))
    app.tick()
    assert app.risk.trading_locked is None                   # a balance change is not a 75% loss
    assert app.risk.day_start_equity == D("25000.00")
    app.shutdown()
    app2 = App(home, offline=True, start_loop=False)
    try:
        assert app2.risk.day_start_equity == D("25000.00")   # a restart does not reset the loss allowance
        assert app2.state.state == "READY"
    finally:
        app2.shutdown()
