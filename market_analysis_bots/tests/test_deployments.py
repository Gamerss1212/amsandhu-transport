"""The owner's deployments inside a real fleet, on the synthetic DEMO market (no network): readiness, START,
the full order lifecycle in the audit log, PAUSE NEW ENTRIES, STOP (retain / close), EMERGENCY STOP, risk
limits that the brain cannot exceed, live gating."""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mab import runtime  # noqa: E402
from mab.runtime import Fleet  # noqa: E402

STRAT = {"id": "TEST-ALWAYS", "name": "Always long (test)", "family": "test", "timeframe": "1m", "direction": "long",
         "params": {}, "entry": {"long": "close > 0"}, "filters": [], "order": {"type": "market"},
         "stop": {"type": "atr", "mult": 3.0, "n": 14}, "target": {"type": "r", "r": 50.0}, "trail": {"type": "none"},
         "exit": {}, "max_bars": 0, "session": {"crypto": {"hold_overnight": True}}, "max_trades_per_day": 100,
         "cooldown_bars": 0, "sizing": {"risk_pct": 1.0, "max_notional_pct": 100.0}, "data": ["bars"], "version": "1.0.0"}


@pytest.fixture()
def fleet(tmp_path, monkeypatch):
    cfg = {"data_dir": str(tmp_path / "d"), "demo": True, "workspace": "demo", "brain": {"mode": "off", "volatility_gate": False},
           "paper": {"latency_ms": 0, "max_slippage_bps": 50}, "paper_main_balance": 100_000.0}
    fl = Fleet(cfg, {"TEST-ALWAYS": STRAT}, [], str(tmp_path))
    fl.setup()
    fl.running = True
    yield fl
    fl.running = False


def build(fl, allocation=10_000.0, limits=None, start=True):
    b = fl.create_user_bot({"strategy_id": "TEST-ALWAYS", "venue": "demo", "instrument": "DEMO-BTC"})
    br = fl.bots[b["bot_id"]]
    s = fl.hub.get("demo", "DEMO-BTC", "1m")
    fl.hub.refresh(s)
    spec = {"bot_id": b["bot_id"], "mode": "demo", "connection_id": "demo-main", "allocation": allocation,
            "limits": limits or {}}
    res = fl.start_deployment(spec) if start else None
    return br, s, spec, res


def step(fl, br, s, monkeypatch, k=0):
    """Evaluate the newest bar as live (k bars later on a shifted clock)."""
    f = s.frame()
    t = f.t[-1]
    monkeypatch.setattr(runtime, "now_ms", lambda: t + f.step + 1500)
    fl._evaluate(br, f, [t])
    return f


def test_start_trade_and_full_lifecycle_in_the_audit_log(fleet, monkeypatch):
    br, s, spec, res = build(fleet)
    assert res["started"], res["readiness"]["failed"]
    ids = {c["id"]: c["status"] for c in res["readiness"]["checks"]}
    assert ids["mode"] == "pass" and ids["buying_power"] == "pass" and ids["data"] == "pass"
    step(fleet, br, s, monkeypatch)
    dep = fleet.dep_cache[br.id]
    pos = fleet.router.position(dep["deployment_id"])
    assert br.tm.pos is not None and pos is not None and pos["qty"] == pytest.approx(br.tm.pos.qty)
    corr = fleet.trade_corr[br.id]
    stages = [e["stage"] for e in fleet.storage.lifecycle(corr)]
    for st in ("signal", "risk_approved", "order_submitted", "fill", "filled", "position_opened"):
        assert st in stages, (st, stages)
    assert stages.index("signal") < stages.index("risk_approved") < stages.index("order_submitted") < stages.index("fill")
    view = fleet.deployment_view(fleet.deps.get(dep["deployment_id"]))
    assert view["activity"] == "managing_position" and view["mode"] == "demo"
    # sized from the allocation, not from the account: risk 1% of 10,000 over a 3 ATR stop, capped at 100% of it
    assert br.tm.pos.qty * br.tm.pos.entry_price <= 10_000 * 1.001


def test_pause_blocks_entries_but_keeps_managing(fleet, monkeypatch):
    br, s, spec, res = build(fleet)
    step(fleet, br, s, monkeypatch)
    dep_id = fleet.dep_cache[br.id]["deployment_id"]
    fleet.pause_deployment(dep_id)
    assert fleet.dep_cache[br.id]["state"] == "paused"
    assert fleet._entries_allowed_for(br, True) is False and fleet._strategy_exits_for(br) is True
    with pytest.raises(ValueError):
        fleet.pause_deployment(dep_id)
    fleet.resume_deployment(dep_id)
    assert fleet.dep_cache[br.id]["state"] == "running"


def test_stop_retain_keeps_the_position_and_stop_close_sells_it(fleet, monkeypatch):
    br, s, spec, res = build(fleet)
    step(fleet, br, s, monkeypatch)
    dep_id = fleet.dep_cache[br.id]["deployment_id"]
    with pytest.raises(ValueError):
        fleet.stop_deployment(dep_id, "")                              # must choose
    out = fleet.stop_deployment(dep_id, "retain")
    assert out["deployment"]["state"] == "stopped_retaining"
    assert fleet.router.position(dep_id) is not None and br.tm.pos is not None
    assert fleet._strategy_exits_for(br) is False and fleet._entries_allowed_for(br, True) is False
    out = fleet.stop_deployment(dep_id, "close")
    assert out["deployment"]["state"] == "stopped" and out["close"]["status"] == "filled"
    assert fleet.router.position(dep_id) is None and br.tm.pos is None
    t = fleet.storage.query("SELECT * FROM trades WHERE deployment_id=?", (dep_id,))
    assert len(t) == 1 and t[0]["mode"] == "demo" and t[0]["connection_id"] == "demo-main"
    acct = fleet.sims["demo-main"].account()
    assert acct["exposure"] == pytest.approx(0.0, abs=1e-6)


def test_emergency_stop_blocks_new_entries_and_reports(fleet, monkeypatch):
    br, s, spec, res = build(fleet)
    out = fleet.emergency_stop("test")
    assert out["blocked"] and fleet.emergency
    step(fleet, br, s, monkeypatch)
    assert br.tm.pos is None                                           # no entry while the emergency stop is on
    o = fleet.engine.place(connection_id="demo-main", mode="demo", purpose="entry", symbol="demo:DEMO-BTC", side="buy",
                           order_type="market", qty=0.01, intent_id="x", deployment_id="D-x", ref_price=65000.0)
    assert o["state"] == "NOT_SENT" and "emergency" in o["reason"]
    rep = fleet.readiness(spec)
    assert not rep["ok"] and any("Emergency" in f for f in rep["failed"])
    fleet.clear_emergency()
    assert fleet.readiness(dict(spec, deployment_id=fleet.dep_cache[br.id]["deployment_id"]))["ok"]


def test_close_all_needs_its_own_confirmation(fleet, monkeypatch):
    br, s, spec, res = build(fleet)
    step(fleet, br, s, monkeypatch)
    with pytest.raises(ValueError):
        fleet.close_all_positions("yes")
    out = fleet.close_all_positions("CLOSE ALL")
    assert out["results"][0]["status"] == "filled" and not out["not_completed"]
    assert br.tm.pos is None


def test_limits_cap_size_whatever_the_brain_says(fleet, monkeypatch):
    br, s, spec, res = build(fleet, limits={"max_order_notional": 250.0})
    fleet.brain.mode = "active"
    monkeypatch.setattr(fleet.brain, "score", lambda *a, **k: {"action": "resize", "size": 1.5, "edge": 0.5, "sd": 0.1,
                                                                "evidence": 50, "reason": "test", "p_win": 0.9})
    step(fleet, br, s, monkeypatch)
    assert br.tm.pos is not None
    assert br.tm.pos.qty * br.tm.pos.entry_price <= 250.0 * 1.01
    risk = fleet.storage.audit_search(kinds=["risk"])[0]
    assert risk["stage"] == "risk_approved"
    assert any(c["check"] == "position size within limits" and "per-order limit" in c["detail"]
               for c in risk["payload"]["checks"])
    brain = fleet.storage.audit_search(kinds=["brain"])[0]
    assert brain["payload"]["p_win"] is None and "not shown" in brain["payload"]["p_win_note"]   # uncalibrated: hidden


def test_daily_loss_limit_blocks_entries(fleet, monkeypatch):
    br, s, spec, res = build(fleet, limits={"daily_loss_limit_pct": 1.0})
    dep = fleet.dep_cache[br.id]
    fleet.storage.save_trade(br.id, "demo", {"strategy_id": "TEST-ALWAYS", "instrument": "DEMO-BTC", "side": 1, "qty": 1,
                                             "entry_time": runtime.now_ms(), "entry_price": 1, "exit_time": runtime.now_ms(),
                                             "exit_price": 1, "fees": 0, "pnl": -150.0, "r": -1, "bars": 1,
                                             "entry_reason": "", "exit_reason": "", "mfe_r": 0, "mae_r": 0},
                             "demo", dep["deployment_id"], "demo-main")
    step(fleet, br, s, monkeypatch)
    assert br.tm.pos is None
    risk = fleet.storage.audit_search(kinds=["risk"])[0]
    assert risk["stage"] == "risk_rejected" and "daily loss" in risk["summary"]


def test_readiness_refuses_wrong_mode_and_too_much_capital(fleet):
    b = fleet.create_user_bot({"strategy_id": "TEST-ALWAYS", "venue": "demo", "instrument": "DEMO-ETH"})
    rep = fleet.readiness({"bot_id": b["bot_id"], "mode": "live", "connection_id": "demo-main", "allocation": 100})
    assert not rep["ok"] and any("mode" in c["id"] and c["status"] == "fail" for c in rep["checks"])
    rep = fleet.readiness({"bot_id": b["bot_id"], "mode": "demo", "connection_id": "demo-main", "allocation": 10 ** 9})
    assert any(c["id"] == "buying_power" and c["status"] == "fail" for c in rep["checks"])
    res = fleet.start_deployment({"bot_id": b["bot_id"], "mode": "demo", "connection_id": "demo-main", "allocation": 10 ** 9})
    assert not res["started"] and fleet.deps.get(res["deployment"]["deployment_id"])["state"] == "stopped"


def test_live_needs_separate_authorisation_and_explicit_confirmation(fleet):
    with pytest.raises(ValueError):
        fleet.live_authorize({"ack": "yes", "connections": ["x"], "max_total_allocation": 1, "daily_loss_limit": 1})
    ok, why = fleet._live_allowed("alpaca-live")
    assert not ok and "not authorised" in why
    b = fleet.create_user_bot({"strategy_id": "TEST-ALWAYS", "venue": "demo", "instrument": "DEMO-SOL"})
    rep = fleet.readiness({"bot_id": b["bot_id"], "mode": "live", "connection_id": "demo-main", "allocation": 100})
    assert any(c["id"] == "live_auth" and c["status"] == "fail" for c in rep["checks"])
    assert any(c["id"] == "demo_ws" and c["status"] == "fail" for c in rep["checks"])


def test_bot_rechecked_when_a_series_it_reads_finishes_loading(fleet):
    """A bot that also reads another series is re-checked when that series loads, instead of showing 'warming' until
    the next bar of its own chart (an hour for the ULTRON crypto bots)."""
    fleet.strategies["TEST-REF"] = dict(STRAT, id="TEST-REF", entry={"long": 'tf("5m", close) > 0'})
    b = fleet.create_user_bot({"strategy_id": "TEST-REF", "venue": "demo", "instrument": "DEMO-BTC"})
    br = fleet.bots[b["bot_id"]]
    own, ref = fleet.hub.get("demo", "DEMO-BTC", "1m"), fleet.hub.get("demo", "DEMO-BTC", "5m")
    assert br.id in fleet.refs_by_series[ref.key]
    fleet._on_event(own.key, fleet.hub.refresh(own), True)
    assert br.state == "warming"                                # its 5m bars are not loaded yet
    fleet._on_event(ref.key, fleet.hub.refresh(ref), True)
    assert br.state == "idle_no_signal" and br.message.startswith("data ready"), br.message   # re-checked at once
