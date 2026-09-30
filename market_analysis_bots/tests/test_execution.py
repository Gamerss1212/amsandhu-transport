"""Execution engine and router: duplicate-order prevention, uncertain sends, restart recovery, partial fills,
rejections, mode separation, emergency stop, live authorisation, rate limits, protective stops."""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fakes import FakeBroker  # noqa: E402
from mab.execution import engine as E  # noqa: E402
from mab.execution.base import TokenBucket  # noqa: E402
from mab.execution.engine import ExecutionEngine  # noqa: E402
from mab.execution.router import Router  # noqa: E402
from mab.storage import Storage  # noqa: E402


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.t += s


def make(tmp_path, env="paper", **kw):
    st = Storage(str(tmp_path / "x.db"))
    b = FakeBroker(env, **kw)
    clk = Clock()
    state = {"halt": None, "live": (True, "")}
    eng = ExecutionEngine(st, lambda cid: b, kill_switch=lambda: state["halt"],
                          live_allowed=lambda c: state["live"], sleep=clk.sleep, clock=clk)
    return st, b, eng, state


def place(eng, **kw):
    args = dict(connection_id="c1", mode="paper", purpose="entry", symbol="coinbase:BTC-USD", side="buy",
                order_type="limit", qty=1.0, limit_price=101.0, tif="ioc", intent_id="i1", deployment_id="d1",
                bot_id="B1", ref_price=100.0)
    args.update(kw)
    return eng.place(**args)


def test_order_is_written_before_it_is_sent_and_fills_are_recorded(tmp_path):
    st, b, eng, _ = make(tmp_path)
    seen = []
    orig = b.submit

    def spy(req):
        seen.append(eng.get(req.client_order_id)["state"])        # what the database says during the send
        return orig(req)
    b.submit = spy
    o = place(eng)
    assert seen == ["SUBMITTING"]
    assert o["state"] == "FILLED" and o["filled_qty"] == 1.0 and o["avg_price"] == 100.0
    f = eng.fills(o["client_order_id"])
    assert len(f) == 1 and f[0]["qty"] == 1.0 and f[0]["slippage_bps"] == pytest.approx(0.0)
    states = [r["to_state"] for r in st.query("SELECT to_state FROM order_events WHERE client_order_id=? ORDER BY id",
                                              (o["client_order_id"],))]
    assert states == ["SUBMITTING", "FILLED"]
    stages = [r["stage"] for r in st.lifecycle("i1")]
    assert "order_submitted" in stages and "fill" in stages and "filled" in stages


def test_same_decision_never_sends_twice(tmp_path):
    st, b, eng, _ = make(tmp_path)
    a = place(eng)
    again = place(eng)
    assert again["duplicate"] and again["client_order_id"] == a["client_order_id"]
    assert len(b.submits) == 1
    # a different attempt of the same decision is a different order (used for exit retries)
    c = place(eng, attempt=1)
    assert c["client_order_id"] != a["client_order_id"] and len(b.submits) == 2
    # and a restart with a fresh engine still finds the first order
    eng2 = ExecutionEngine(st, lambda cid: b)
    assert place(eng2)["duplicate"] and len(b.submits) == 2


def test_lost_response_is_looked_up_not_resent(tmp_path):
    st, b, eng, _ = make(tmp_path)
    b.script = ["timeout_placed"]
    o = place(eng)
    assert len(b.submits) == 1
    assert o["state"] == "FILLED" and o["broker_order_id"]           # found by its client id
    stages = [r["stage"] for r in st.lifecycle("i1")]
    assert "status_unknown" in stages


def test_lost_response_for_an_order_that_never_arrived_becomes_lost_without_resending(tmp_path):
    st, b, eng, _ = make(tmp_path)
    b.script = ["timeout_notplaced"]
    o = place(eng)
    assert o["state"] == "UNKNOWN" and len(b.submits) == 1
    E_now = E.now_ms
    try:
        E.now_ms = lambda: E_now() + 120_000                          # a couple of minutes later
        for _ in range(3):
            o = eng.refresh(o["client_order_id"])
    finally:
        E.now_ms = E_now
    assert o["state"] == "LOST" and len(b.submits) == 1


def test_lookup_failures_do_not_count_as_not_found(tmp_path):
    st, b, eng, _ = make(tmp_path)
    b.script = ["timeout_placed"]
    b.lookup_fails = 3
    o = place(eng)
    assert o["state"] == "UNKNOWN"
    assert eng.refresh(o["client_order_id"])["state"] == "FILLED"


def test_restart_recovery(tmp_path):
    st, b, eng, _ = make(tmp_path)
    # crash 1: row written, never sent
    st.write("INSERT INTO broker_orders (client_order_id, connection_id, mode, purpose, symbol, side, order_type, qty,"
             " state, created) VALUES ('jv-a','c1','paper','entry','X','buy','limit',1,'NEW',1)")
    # crash 2: sending when the process died, and the broker did get it
    b.script = ["timeout_placed"]
    real = eng._resolve_unknown
    eng._resolve_unknown = lambda cid, tries=3, gap_s=1.0: eng.get(cid)     # the process "dies" before resolving
    o = place(eng, intent_id="i9")
    eng._resolve_unknown = real
    st.write("UPDATE broker_orders SET state='SUBMITTING' WHERE client_order_id=?", (o["client_order_id"],))
    out = ExecutionEngine(st, lambda c: b).recover()
    assert out["not_sent"] == 1 and out["unknown"] == 1
    assert ExecutionEngine(st, lambda c: b).get("jv-a")["state"] == "NOT_SENT"
    assert ExecutionEngine(st, lambda c: b).get(o["client_order_id"])["state"] == "FILLED"
    assert len(b.submits) == 1


def test_partial_fills_accumulate_without_double_counting(tmp_path):
    st, b, eng, _ = make(tmp_path)
    b.fill_on_submit = False
    o = place(eng, tif="gtc")
    assert o["state"] == "ACKED"
    bo = b.orders[o["broker_order_id"]]
    b._fill(bo, 0.4, 100.0)
    bo["state"] = "PARTIALLY_FILLED"
    for _ in range(3):                                               # repeated polls add nothing new
        o = eng.refresh(o["client_order_id"])
    assert o["state"] == "PARTIALLY_FILLED" and o["filled_qty"] == pytest.approx(0.4)
    b._fill(bo, 0.6, 102.0)
    bo["state"] = "FILLED"
    o = eng.refresh(o["client_order_id"])
    fills = eng.fills(o["client_order_id"])
    assert [round(f["qty"], 6) for f in fills] == [0.4, 0.6]
    assert fills[1]["price"] == pytest.approx(102.0)
    assert o["avg_price"] == pytest.approx(101.2) and o["state"] == "FILLED"


def test_rejection_and_not_sent_are_final(tmp_path):
    st, b, eng, _ = make(tmp_path)
    b.script = ["reject", "notsent"]
    assert place(eng)["state"] == "REJECTED"
    o = place(eng, intent_id="i2")
    assert o["state"] == "NOT_SENT" and "not sent" in o["reason"]


def test_mode_must_match_connection(tmp_path):
    st, b, eng, _ = make(tmp_path, env="paper")
    o = place(eng, mode="live")
    assert o["state"] == "NOT_SENT" and "cannot go to a paper connection" in o["reason"]
    assert not b.submits


def test_live_needs_authorisation_but_exits_do_not(tmp_path):
    st, b, eng, state = make(tmp_path, env="live")
    state["live"] = (False, "owner has not authorised live trading")
    o = place(eng, mode="live")
    assert o["state"] == "NOT_SENT" and "not authorised" in o["reason"] and not b.submits
    b.holdings["coinbase:BTC-USD"] = 1.0
    ex = place(eng, mode="live", purpose="exit", side="sell", reduce_only=True, intent_id="x1", limit_price=99.0)
    assert ex["state"] == "FILLED"


def test_emergency_stop_blocks_entries_not_exits(tmp_path):
    st, b, eng, state = make(tmp_path)
    state["halt"] = "operator"
    assert place(eng)["state"] == "NOT_SENT"
    b.holdings["coinbase:BTC-USD"] = 1.0
    assert place(eng, purpose="exit", side="sell", reduce_only=True, intent_id="x1")["state"] == "FILLED"


def test_rate_limit_blocks_instead_of_bursting(tmp_path):
    st, b, eng, _ = make(tmp_path)
    b.rate = (2, 60.0)
    eng.rate_timeout = 0.0
    r = [place(eng, intent_id=f"r{i}")["state"] for i in range(3)]
    assert r == ["FILLED", "FILLED", "NOT_SENT"] and len(b.submits) == 2
    tb = TokenBucket(2, 1.0, clock=lambda: 0.0, sleep=lambda s: None)
    assert tb.acquire(0) and tb.acquire(0) and not tb.acquire(0)


def test_cancel_before_confirmation_waits_for_the_order(tmp_path):
    st, b, eng, _ = make(tmp_path)
    b.fill_on_submit = False
    b.script = ["timeout_placed"]
    b.lookup_fails = 3
    o = place(eng, tif="gtc")
    assert o["state"] == "UNKNOWN"
    o = eng.cancel(o["client_order_id"], "operator")                  # lookup fails again: remembered, not dropped
    assert o["flags"].get("cancel_wanted")
    o = eng.refresh(o["client_order_id"])                             # found -> the pending cancel is carried out
    assert o["state"] == "CANCELED"


# ---------------------------------------------------------------------------------------- router
DEP = {"deployment_id": "d1", "bot_id": "B1", "mode": "paper", "connection_id": "c1"}


def router(tmp_path, **kw):
    st, b, eng, state = make(tmp_path, **kw)
    alerts = []
    r = Router(eng, st, lambda c: b, alert=lambda lvl, kind, msg, dep: alerts.append((lvl, kind, msg)))
    return st, b, eng, r, alerts


def test_entry_places_a_protective_stop_on_the_broker(tmp_path):
    st, b, eng, r, alerts = router(tmp_path)
    res = r.enter(DEP, symbol="coinbase:BTC-USD", side=1, qty=10.0, ref_price=100.0, stop=95.0, target=110.0,
                  intent_id="e1")
    assert res["status"] == "filled"
    pos = r.position("d1")
    assert pos["qty"] == pytest.approx(res["qty"]) and pos["stop_order"]
    stop = eng.get(pos["stop_order"])
    assert stop["order_type"] == "stop" and stop["stop_price"] == pytest.approx(95.0) and stop["reduce_only"] == 1
    assert stop["state"] == "ACKED"
    # the stop fills on the broker: the position is booked
    b.trigger_stop(94.9)
    out = r.poll_stop(DEP)
    assert out["status"] == "filled" and r.position("d1") is None


def test_entry_uses_stop_limit_where_required_and_fee_in_asset(tmp_path):
    st, b, eng, r, _ = router(tmp_path, stop_kind="stop_limit")
    b.fee_in_asset = 0.0025
    res = r.enter(DEP, symbol="coinbase:BTC-USD", side=1, qty=10.0, ref_price=100.0, stop=95.0, target=None,
                  intent_id="e1")
    pos = r.position("d1")
    stop = eng.get(pos["stop_order"])
    assert stop["order_type"] == "stop_limit" and stop["limit_price"] < stop["stop_price"]
    assert pos["qty"] == pytest.approx(res["qty"]) and stop["qty"] == pytest.approx(pos["qty"])
    assert pos["qty"] < eng.get(res["order"]["client_order_id"])["filled_qty"]      # fee came out of the coins


def test_failed_protective_stop_sells_the_position(tmp_path):
    st, b, eng, r, alerts = router(tmp_path)
    b.script = ["ok", "reject"]                                       # entry fills, the stop is refused
    res = r.enter(DEP, symbol="coinbase:BTC-USD", side=1, qty=10.0, ref_price=100.0, stop=95.0, target=None,
                  intent_id="e1")
    assert res["status"] == "closed" and res["stop_deployment"]
    assert r.position("d1") is None
    assert any(k == "protective_stop_failed" for _, k, _ in alerts)


def test_partial_entry_is_protected_for_what_filled(tmp_path):
    st, b, eng, r, _ = router(tmp_path)
    b.partial = 0.3
    res = r.enter(DEP, symbol="coinbase:BTC-USD", side=1, qty=10.0, ref_price=100.0, stop=95.0, target=None,
                  intent_id="e1")
    assert res["status"] == "partial"
    pos = r.position("d1")
    assert eng.get(pos["stop_order"])["qty"] == pytest.approx(pos["qty"])


def test_exit_cancels_the_stop_then_sells(tmp_path):
    st, b, eng, r, _ = router(tmp_path)
    r.enter(DEP, symbol="coinbase:BTC-USD", side=1, qty=10.0, ref_price=100.0, stop=95.0, target=None, intent_id="e1")
    stop_id = r.position("d1")["stop_order"]
    out = r.exit(DEP, ref_price=100.0, reason="exit rule", intent_id="x1")
    assert out["status"] == "filled" and r.position("d1") is None
    assert eng.get(stop_id)["state"] == "CANCELED"


def test_short_entries_and_bad_prices_are_refused(tmp_path):
    st, b, eng, r, _ = router(tmp_path, ask=180.0, bid=179.0)
    assert r.enter(DEP, symbol="s", side=-1, qty=1, ref_price=100, stop=105, target=None, intent_id="a")["status"] == "skipped"
    res = r.enter(DEP, symbol="s", side=1, qty=1, ref_price=50, stop=45, target=None, intent_id="b")
    assert res["status"] == "skipped" and "does not match" in res["reason"]
    assert not b.submits


def test_cancel_entries_leaves_protective_stops(tmp_path):
    st, b, eng, r, _ = router(tmp_path)
    r.enter(DEP, symbol="coinbase:BTC-USD", side=1, qty=10.0, ref_price=100.0, stop=95.0, target=None, intent_id="e1")
    b.fill_on_submit = False
    o = place(eng, intent_id="e2", tif="gtc")                         # a working entry order
    out = r.cancel_entries("d1", "emergency stop")
    assert [x["order"] for x in out] == [o["client_order_id"]] and out[0]["ok"]
    assert eng.get(r.position("d1")["stop_order"])["state"] == "ACKED"


def test_trailing_stop_is_replaced_never_duplicated(tmp_path):
    st, b, eng, r, _ = router(tmp_path)
    r.enter(DEP, symbol="coinbase:BTC-USD", side=1, qty=10.0, ref_price=100.0, stop=95.0, target=None, intent_id="e1")
    old = r.position("d1")["stop_order"]
    new = r.move_stop(DEP, 98.0, "e1")
    pos = r.position("d1")
    assert pos["stop_order"] == new["client_order_id"] != old and pos["stop_price"] == pytest.approx(98.0)
    assert eng.get(old)["state"] == "CANCELED"
    working = [o for o in b.orders.values() if o["type"] == "stop" and o["state"] == "ACKED"]
    assert len(working) == 1
    assert r.move_stop(DEP, 97.0, "e1") is None                        # stops only move up


def test_exit_that_cannot_fill_keeps_the_position_protected(tmp_path):
    st, b, eng, r, alerts = router(tmp_path)
    r.enter(DEP, symbol="coinbase:BTC-USD", side=1, qty=10.0, ref_price=100.0, stop=95.0, target=None, intent_id="e1")
    b.script = ["reject", "reject", "reject"]                          # every sell attempt refused
    out = r.exit(DEP, ref_price=100.0, reason="exit rule", intent_id="x1")
    assert out["status"] == "error"
    pos = r.position("d1")
    assert pos is not None and eng.get(pos["stop_order"])["state"] == "ACKED"
    assert any(k == "exit_failed" for _, k, _ in alerts)
