"""The master system agent and its 100 trading agents A001-A100: roles, one owner per market, training and version
selection on validation data, shadow promotion, rollback, permissions, budgets, loss limits, the emergency stop, the
one order authority and market discovery. Discovery is tested against recorded-shape fake responses: no network."""

import threading
import time
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from tradingai.app import App
from tradingai.brokers.base import BrokerOrder
from tradingai.core.events import EventBus
from tradingai.core.ids import new_id
from tradingai.engine import master as M
from tradingai.execution.oms import OMS
from tradingai.market import discovery as D
from tradingai.risk.service import Limits, OrderRequest, RiskService, Snapshot
from tradingai.storage.db import Database, now_ms
from tradingai.strategies.library import specs


@pytest.fixture()
def app(tmp_path):
    a = App(str(tmp_path / "home"), offline=True, start_loop=False)
    yield a
    a.shutdown()


def run(app, sid, iid, tf, verdict="PAPER TEST", val=1.0, test=0.5, params=None, status="ok"):
    """A finished STANDARD research run as the research engine stores it (simulated data, documented dataset)."""
    eid = app.ledger.start(family="test", strategy_id=sid, hypothesis="test", instrument=iid, tf=tf, profile="STANDARD",
                           seed=7, dataset={"simulated": True, "provider": "demo", "bars": 5000, "sha256": "x"})
    app.ledger.finish(eid, {"status": status, "verdict": verdict, "operating_mode": "intraday",
                            "params_chosen": params or {}, "train": {"sharpe": 2.0, "trades": 120},
                            "validation": {"sharpe": val, "trades": 40}, "test": {"sharpe": test, "trades": 40,
                                                                                  "expectancy": 0.001},
                            "walk_forward": {"oos_sharpe": 0.4}, "statistics": {"dsr": 0.97, "pbo": 0.1},
                            "quality": {"score": 60}, "reproducibility": {"simulated_data": True}, "checks": []})
    time.sleep(0.002)
    return eid


def train(app, aid, vals, verdicts=None, params=None):
    """Record one run per candidate of the agent's role and let the master choose."""
    a = app.fleet.agents[aid]
    role = M.ROLES[a.role]
    for k, sid in enumerate(role.candidates):
        run(app, sid, a.partition[0], role.tf, (verdicts or ["PAPER TEST"] * 3)[k], val=vals[k],
            params=(params or {}).get(sid))
    return app.fleet._choose_version(a)


# ---------------------------------------------------------------- the 100 agents and their roles
def test_exactly_100_agents_in_eight_roles_with_runnable_candidates(app):
    f = app.fleet
    assert len(f.agents) == M.TARGET == 100
    assert sorted(f.agents) == [f"A{n:03d}" for n in range(1, 101)]
    assert sum(M.ROLE_COUNT.values()) == 100
    for role, first, last, _ in M.PLAN:
        assert all(f.agents[f"A{n:03d}"].role == role for n in range(first, last + 1))
    sp = specs()
    for r in M.ROLES.values():
        assert len(r.candidates) == 3 and r.tf in M.LOOKBACK
        for sid in r.candidates:
            assert sid in sp and sp[sid].runnable, sid
            assert r.tf in sp[sid].supported_timeframes, (sid, r.tf)
    c = f.counts()
    assert c["registered"] == c["target"] == c["configured"] == 100
    with pytest.raises(ValueError, match="exactly 100"):
        f.set_desired(320)


def test_each_instrument_has_exactly_one_owner(app):
    f = app.fleet
    seen = {}
    for a in f.agents.values():
        assert len(a.partition) <= 1                   # one market per agent
        for i in a.partition:
            assert i not in seen, f"{i} owned by {seen[i]} and {a.agent_id}"
            seen[i] = a.agent_id
    assert seen == f.owner and len(seen) > 0
    assert all(app.book.get(i).tradable for i in seen)


def test_offline_agents_without_a_market_are_blocked_with_the_reason(app):
    app.fleet.cycle()
    v = app.fleet.view()
    blocked = [a for a in app.fleet.agents.values() if not a.partition]
    assert blocked and all(a.runtime == "blocked" and "discovery is offline" in a.detail for a in blocked)
    assert {a.role for a in blocked} <= {"crypto_trend", "crypto_reversion", "meme_momentum", "meme_reversion"}
    assert [app.fleet.agents[x].partition for x in ("A004", "A005", "A006")] == [[i] for i in M.DEMO]
    assert v["counts"]["data_ready"] <= v["counts"]["assigned"] < 100
    assert v["brain"]["kind"].startswith("coordinating service")    # the master is not counted as a trader
    assert "0 model calls" in v["brain"]["model"]
    assert len(v["agents"]) == 100 and all("permission" in c and "version" in c for c in v["agents"])


def test_assignment_is_stable_across_replans(app):
    before = {a.agent_id: list(a.partition) for a in app.fleet.agents.values()}
    assert app.fleet.assign()["changed"] == 0
    assert {a.agent_id: list(a.partition) for a in app.fleet.agents.values()} == before


def test_one_failing_bot_does_not_stop_its_agent_or_others(app):
    class B:
        def __init__(self, bid, iid):
            self.bot_id, self.instrument_id = bid, iid
    iids = list(app.fleet.owner)[:3]
    bots = [B("ok1", iids[0]), B("bad", iids[1]), B("ok2", iids[1]), B("ok3", iids[2])]

    def fn(b):
        if b.bot_id == "bad":
            raise RuntimeError("boom")
        return b.bot_id
    assert app.fleet.run_bots(bots, fn) == ["ok1", "ok2", "ok3"]
    owner = app.fleet.agents[app.fleet.owner[iids[1]]]
    assert any("boom" in e["error"] for e in owner.errors)


# ---------------------------------------------------------------- training, validation, versions
def test_training_submits_documented_research_per_candidate_with_bounded_jobs(app, monkeypatch):
    calls = []

    def fake(sid, iid, tf, profile, lookback, *, by):
        calls.append((sid, iid, tf, profile, lookback, by))
        return {"job_id": f"J{len(calls)}"}
    monkeypatch.setattr(app, "submit_research", fake)
    monkeypatch.setattr(app.jobs, "view", lambda jid, with_result=False: {"state": "running"})
    for _ in range(5):
        app.fleet.operate()
    assert len(calls) == M.MAX_TRAINING_JOBS                      # bounded: never more than 2 at once
    # offline, only markets with data can train: the DEMO markets of A004 and A005, not Coinbase BTC
    assert [(c[1], c[5]) for c in calls] == [("DEMO:DEMO-TREND", "master:A004"), ("DEMO:DEMO-RANGE", "master:A005")]
    app.fleet.jobs.clear()
    calls.clear()
    monkeypatch.setattr(app, "offline", False)
    app.fleet.operate()
    sid, iid, tf, profile, lookback, by = calls[0]
    assert (sid, iid, tf, profile, lookback) == ("tsmom.none.trail", "COINBASE:BTC-USD", "1h", "STANDARD", 20000)
    assert by == "master:A001"
    assert len({c[5] for c in calls}) == 2                        # one job per agent at a time


def test_a_finished_job_without_a_usable_result_is_not_resubmitted_every_cycle(app, monkeypatch):
    calls = []

    def fake(sid, iid, tf, profile, lookback, *, by):
        calls.append(sid)
        return {"job_id": f"J{len(calls)}"}
    monkeypatch.setattr(app, "submit_research", fake)
    monkeypatch.setattr(app.jobs, "view", lambda jid, with_result=False: {
        "state": "done", "result": {"status": "insufficient_data"}})
    monkeypatch.setattr(M, "MAX_TRAINING_JOBS", 1)
    monkeypatch.setattr(app, "offline", False)                    # (submit_research is faked: no network)
    for _ in range(4):
        app.fleet.operate()
    assert calls[:3] == list(M.ROLES["crypto_major"].candidates)   # each candidate once, then the next agent
    assert calls.count("tsmom.none.trail") <= 2                     # (A002 has its own) - never a tight loop
    assert all(v > now_ms() for k, v in app.fleet.unavailable.items())


def test_version_is_chosen_on_validation_never_on_the_test_segment(app):
    # the first candidate has the best TEST result but the worst VALIDATION result: it must not be chosen
    a = app.fleet.agents["A004"]
    role = M.ROLES[a.role]
    run(app, role.candidates[0], a.partition[0], role.tf, val=0.2, test=5.0)
    run(app, role.candidates[1], a.partition[0], role.tf, val=1.4, test=0.1, params={"lookback": 55})
    run(app, role.candidates[2], a.partition[0], role.tf, val=0.9, test=0.3)
    out = app.fleet._choose_version(a)
    assert out == {"version": 1, "status": "active"}
    v = app.fleet.active_version("A004")
    assert v["strategy_id"] == role.candidates[1] and v["params"] == {"lookback": 55}
    t = v["training"]
    assert t["chosen"] == role.candidates[1] and "VALIDATION" in t["objective"]
    assert t["dataset"]["instrument"] == a.partition[0] and t["dataset"]["sha256"] == "x"
    assert [c["validation_sharpe"] for c in t["candidates"]] == [0.2, 1.4, 0.9]
    assert t["dsr"] == 0.97 and t["pbo"] == 0.1 and t["verdict"] == "PAPER TEST"
    assert app.fleet._choose_version(a) is None                     # same evidence: no new version


def test_no_version_until_every_candidate_has_run(app):
    a = app.fleet.agents["A004"]
    role = M.ROLES[a.role]
    run(app, role.candidates[0], a.partition[0], role.tf, val=2.0)
    assert app.fleet._choose_version(a) is None
    assert app.fleet.permission("A004") == (False, "no validated version yet: the agent stays in cash while it trains")


def test_a_rejected_version_leaves_the_agent_in_cash(app):
    out = train(app, "A004", [1.0, 0.5, 0.2], ["RESEARCH FURTHER", "REJECT", "REJECT"])
    assert out["status"] == "rejected"
    assert app.fleet.active_version("A004") is None
    assert app.fleet.permission("A004")[0] is False and app.fleet.budget("A004") == 0
    assert "A004" not in app.fleet.bot_of


def test_first_validated_version_gets_a_bot_permission_and_a_bounded_budget(app):
    train(app, "A004", [1.0, 0.5, 0.2], params={"tsmom.none.trail": {"lookback": 48}})
    ok, why = app.fleet.permission("A004")
    assert ok and why.startswith("v1 validated")
    bot = app.bots[app.fleet.bot_of["A004"]]
    assert bot.managed_by == "master" and bot.agent_id == "A004" and bot.state == "running"
    assert bot.strategy_id == "tsmom.none.trail" and bot.params == {"lookback": 48}
    app.fleet._budget_cache = (0.0, set())
    eq = app.paper.get_balance().equity
    lim = app.risk.limits
    budgets = {aid: app.fleet.budget(aid) for aid in app.fleet.agents}
    assert {aid for aid, b in budgets.items() if b > 0} == {"A004"}
    assert sum(budgets.values()) <= eq * Decimal(str(lim.max_gross_exposure))
    assert all(b <= eq * Decimal(str(lim.max_position_pct_equity)) for b in budgets.values())
    with pytest.raises(PermissionError):
        app.bot_action(bot.bot_id, "delete")                        # an agent's loop cannot be deleted by hand


def test_a_newer_version_runs_in_shadow_and_is_promoted_only_if_it_beats_the_active_one(app, monkeypatch):
    train(app, "A004", [1.0, 0.5, 0.2])
    out = train(app, "A004", [0.3, 1.5, 0.2])                       # a different candidate is now best
    assert out == {"version": 2, "status": "shadow"}
    sim = {"donchian_breakout.none.trail": {"bars": 80, "net_return": 0.03, "max_drawdown": 0.02, "trades": 5},
           "tsmom.none.trail": {"bars": 80, "net_return": 0.01, "max_drawdown": 0.02, "trades": 5}}
    monkeypatch.setattr(app.fleet, "_simulate", lambda sid, p, iid, tf, since: sim[sid])
    a = app.fleet.agents["A004"]
    app.fleet._check_shadow(a)
    assert app.fleet.active_version("A004")["version"] == 1        # too young: shadow needs 3 days of new bars
    app.db.execute("UPDATE agent_versions SET created=? WHERE agent_id='A004' AND version=2",
                   (now_ms() - 4 * M.DAY,))
    app.fleet._check_shadow(a)
    st = {v["version"]: v["status"] for v in app.fleet.versions("A004")}
    assert st == {1: "superseded", 2: "active"}
    assert app.bots[app.fleet.bot_of["A004"]].strategy_id == "donchian_breakout.none.trail"   # flat: switched
    # a worse shadow is rejected and the active version stays
    out = train(app, "A004", [0.3, 0.2, 1.9])
    assert out["status"] == "shadow"
    sim["ema_cross.adx.flip"] = {"bars": 80, "net_return": -0.01, "max_drawdown": 0.05, "trades": 5}
    app.db.execute("UPDATE agent_versions SET created=? WHERE agent_id='A004' AND version=3",
                   (now_ms() - 4 * M.DAY,))
    app.fleet._check_shadow(a)
    st = {v["version"]: v["status"] for v in app.fleet.versions("A004")}
    assert st == {1: "superseded", 2: "active", 3: "rejected"}


def test_rollback_restores_the_previous_version_only_if_it_still_validates(app, monkeypatch):
    train(app, "A004", [1.0, 0.5, 0.2])
    train(app, "A004", [0.3, 1.5, 0.2])
    monkeypatch.setattr(app.fleet, "_simulate", lambda *a: {"bars": 80, "net_return": 0.02, "max_drawdown": 0.01,
                                                             "trades": 3})
    app.db.execute("UPDATE agent_versions SET created=? WHERE agent_id='A004' AND version=2", (now_ms() - 4 * M.DAY,))
    app.fleet._check_shadow(app.fleet.agents["A004"])
    assert app.fleet.active_version("A004")["version"] == 2
    out = app.fleet.rollback("A004", "test: worse in paper than in validation")
    assert out == {"rolled_back": True, "restored": 1}
    assert {v["version"]: v["status"] for v in app.fleet.versions("A004")} == {1: "active", 2: "rolled_back"}
    les = app.learning.lessons["VERSION_UNDERPERFORMED"]
    assert les["safeguard"] == "rollback"
    assert app.learning.replay_all("test")["failed"] == []          # v2 stays inactive: the replay proves it
    # the restored v1 now fails its own re-test: rolling it back suspends the agent instead of restoring anything
    run(app, "tsmom.none.trail", "DEMO:DEMO-TREND", "1h", verdict="REJECT")
    out = app.fleet.rollback("A004", "test again")
    assert out == {"rolled_back": True, "restored": None}
    assert app.fleet.active_version("A004") is None
    ok, why = app.fleet.permission("A004")
    assert not ok and "suspended by the master" in why


def test_after_a_rollback_a_new_version_must_make_money_in_shadow_first(app, monkeypatch):
    train(app, "A004", [1.0, 0.5, 0.2])
    app.fleet.rollback("A004", "test")
    assert app.fleet.active_version("A004") is None
    out = train(app, "A004", [0.3, 1.5, 0.2])
    assert out["status"] == "shadow"                                # not straight to active after a rollback
    app.db.execute("UPDATE agent_versions SET created=? WHERE agent_id='A004' AND version=2", (now_ms() - 4 * M.DAY,))
    monkeypatch.setattr(app.fleet, "_simulate", lambda *a: {"bars": 80, "net_return": -0.001, "max_drawdown": 0.01,
                                                             "trades": 3})
    app.fleet._check_shadow(app.fleet.agents["A004"])
    assert app.fleet.versions("A004")[1]["status"] == "rejected"   # lost money net of costs: never trades
    out = train(app, "A004", [0.3, 0.2, 1.5])
    app.db.execute("UPDATE agent_versions SET created=? WHERE agent_id='A004' AND version=3", (now_ms() - 4 * M.DAY,))
    monkeypatch.setattr(app.fleet, "_simulate", lambda *a: {"bars": 80, "net_return": 0.004, "max_drawdown": 0.01,
                                                             "trades": 3})
    app.fleet._check_shadow(app.fleet.agents["A004"])
    assert app.fleet.active_version("A004")["version"] == 3
    assert app.fleet.permission("A004")[0]                          # the rollback suspension ended with a valid version


def test_a_paper_loss_beyond_2pct_of_equity_rolls_the_version_back(app, monkeypatch):
    train(app, "A004", [1.0, 0.5, 0.2])
    eq = app.paper.get_balance().equity
    monkeypatch.setattr(app.fleet, "_paper_record", lambda v, iid: {"trips": 3, "pnl": str(-eq * Decimal("0.021")),
                                                                    "mean_return": -0.01, "returns": [-0.01] * 3})
    app.fleet._check_rollback(app.fleet.agents["A004"])
    assert app.fleet.versions("A004")[0]["status"] == "rolled_back"
    assert "more than 2% of equity" in app.fleet.versions("A004")[0]["reason"]


def test_paper_results_far_below_validation_roll_the_version_back(app, monkeypatch):
    train(app, "A004", [1.0, 0.5, 0.2])
    rets = [-0.004, -0.006, -0.005, -0.003, -0.007, -0.004, -0.005, -0.006, -0.004, -0.005]
    monkeypatch.setattr(app.fleet, "_paper_record", lambda v, iid: {"trips": 10, "pnl": "-50", "mean_return":
                                                                    sum(rets) / 10, "returns": rets})
    app.fleet._check_rollback(app.fleet.agents["A004"])
    assert app.fleet.versions("A004")[0]["status"] == "rolled_back"


def fill(app, iid, side, qty, price, ts=None):
    app.db.execute("INSERT INTO fills (fill_id, client_order_id, account_id, instrument_id, side, qty, price, fee, "
                   "fee_currency, liquidity, environment, ts) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                   (new_id("F"), new_id("C"), app.paper.account_id, iid, side, str(qty), str(price), "0", "USD",
                    "taker", "paper", ts or now_ms()))


def test_daily_loss_limit_stops_the_agents_entries_and_two_breaches_roll_back(app):
    train(app, "A004", [1.0, 0.5, 0.2])
    eq = app.paper.get_balance().equity
    loss_per_unit = eq * Decimal("0.006") / 10                      # 0.6% of equity: above the 0.5% daily limit
    fill(app, "DEMO:DEMO-TREND", "buy", 10, 100 + loss_per_unit)
    fill(app, "DEMO:DEMO-TREND", "sell", 10, 100)
    app.fleet._loss_limits()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    assert app.fleet.day_stop["A004"] == today
    ok, why = app.fleet.permission("A004")
    assert not ok and "daily loss limit" in why
    assert "AGENT_LOSS_LIMIT" in app.learning.lessons
    assert app.learning.replay_all("test")["failed"] == []
    # a second breach inside 7 days (recorded the next day) rolls the version back
    app.learning.record("AGENT_LOSS_LIMIT", agent_id="A004", instrument_id="DEMO:DEMO-TREND", detail={},
                        scenario={"agent_day_stopped": True, "qty": "1"})
    app.fleet._check_rollback(app.fleet.agents["A004"])
    assert app.fleet.versions("A004")[0]["status"] == "rolled_back"


def test_the_emergency_stop_removes_every_permission_and_budget(app):
    train(app, "A004", [1.0, 0.5, 0.2])
    assert app.fleet.permission("A004")[0]
    app.emergency_stop("test", "owner")
    ok, why = app.fleet.permission("A004")
    assert not ok and "emergency stop" in why
    app.fleet._budget_cache = (0.0, set())
    assert app.fleet.budget("A004") == 0
    app.fleet.operate()                                              # the master never restarts a stopped bot
    assert app.bots[app.fleet.bot_of["A004"]].state == "stopped" and app.risk.kill_switch


def test_stop_system_removes_permission(app):
    train(app, "A004", [1.0, 0.5, 0.2])
    app.stop_all()
    assert app.fleet.permission("A004") == (False, "system stopped (press Start System)")
    app.start_all()
    assert app.fleet.permission("A004")[0]


# ---------------------------------------------------------------- automatic execution, one owner per market
def _buy_signal(monkeypatch):
    from tradingai.engine import orchestrator as O
    monkeypatch.setattr(O.Strategy, "generate_signal", lambda self: O.Signal(1, 0, self.spec.strategy_id))
    monkeypatch.setattr(O.daytrade, "entry_check", lambda cal, ms: (True, "OK", "test: inside the entry window"))


def test_an_agent_with_a_validated_version_trades_automatically_in_paper(app, monkeypatch):
    _buy_signal(monkeypatch)
    train(app, "A004", [1.0, 0.5, 0.2])
    bot = app.bots[app.fleet.bot_of["A004"]]
    rec = app.orch.decide(bot, "paper")                              # no per-trade permission is asked
    assert rec["outcome"] == "ORDER", rec
    assert rec["agent"] == "A004" and rec["order"]["planned_risk"]
    app.paper.process()
    assert app.paper.get_positions().get("DEMO:DEMO-TREND", 0) > 0


def test_only_the_owning_agent_may_open_a_position(app, monkeypatch):
    _buy_signal(monkeypatch)
    train(app, "A004", [1.0, 0.5, 0.2])
    from tradingai.engine.orchestrator import BotConfig
    for bad in (BotConfig("X1", "DEMO:DEMO-TREND", "1h", "tsmom.none.trail", "strategy"),               # no agent
                BotConfig("X2", "DEMO:DEMO-TREND", "1h", "tsmom.none.trail", "strategy", agent_id="A005")):
        rec = app.orch.decide(bad, "paper")
        assert rec["outcome"] == "NO_TRADE" and "owning trading agent" in rec["reason"], rec
    assert app.paper.get_open_orders() == []
    # an agent without a validated version cannot open on its own market either
    rec = app.orch.decide(BotConfig("X3", "DEMO:DEMO-RANGE", "1h", "tsmom.none.trail", "strategy",
                                    agent_id="A005"), "paper")
    assert rec["outcome"] == "NO_TRADE" and rec["reason"].startswith("MASTER_PERMISSION"), rec


def test_owner_cannot_create_bots_any_more(app):
    from fastapi.testclient import TestClient
    from tradingai.api.server import create_app
    c = TestClient(create_app(app, token="T0K"), base_url="http://127.0.0.1:8000")
    h = {"X-TA-Token": "T0K", "Origin": "http://127.0.0.1:8000"}
    r = c.post("/api/bots", json={"instrument_id": "DEMO:DEMO-TREND", "tf": "1h", "strategy_id": "tsmom.none.trail"},
               headers=h)
    assert r.status_code == 403 and "100 trading agents" in r.text, r.text
    r = c.post("/api/fleet/A004/probe", headers=h)
    assert r.status_code == 200 and r.json()["agent"] == "A004"
    assert c.get("/api/learning", headers=h).json()["metrics"]["lessons"] == 0
    assert c.post("/api/learning/replay", headers=h).json()["failed"] == []


def test_probe_runs_an_agents_pipeline_in_shadow_without_sending_orders(app):
    out = app.probe_agent("A004")
    assert out["agent"] == "A004" and out["outcome"] in ("NO_TRADE", "SHADOW", "ORDER", "RISK_REJECT")
    assert app.paper.get_open_orders() == [] and app.paper.get_positions() == {}
    with pytest.raises(ValueError):
        app.probe_agent("A010")                                      # no market offline


# ---------------------------------------------------------------- one order authority, atomic reservation
class FakeBroker:
    name, environment, connected = "fake", "paper", True

    def __init__(self):
        self.orders = []
        self.lock = threading.Lock()

    def get_order(self, cid):
        return None

    def submit_order(self, *, client_order_id, instrument_id, side, qty, **kw):
        time.sleep(0.005)                           # widen the race window
        with self.lock:
            self.orders.append((instrument_id, qty))
        return BrokerOrder(client_order_id, "b-" + client_order_id, instrument_id, side, qty, Decimal(0), None, "NEW")


def test_concurrent_agents_cannot_overspend_through_the_order_authority(tmp_path):
    db = Database(tmp_path / "t.sqlite3")
    risk = RiskService(Limits(max_order_pct_equity=0.2, max_position_pct_equity=0.2, max_gross_exposure=0.5,
                              max_open_positions=100, max_orders_per_minute=100,
                              max_asset_class_pct={"crypto": 5.0}))
    oms = OMS(db, risk, EventBus(), lambda *a, **k: None)
    broker = FakeBroker()

    def positions(_):
        with broker.lock:
            return {i: {"qty": q, "price": Decimal(100), "multiplier": Decimal(1), "market": "crypto"}
                    for i, q in broker.orders}
    oms.refresh_positions = positions
    results = []

    def agent(n):
        req = OrderRequest(client_order_id="", instrument_id=f"X:{n}", market="crypto", side="buy", quantity=Decimal(100),
                           reference_price=Decimal(100), limit_price=None, multiplier=Decimal(1), environment="paper",
                           account_id="paper")
        out = oms.place(decision_id=f"D{n}", req=req, snapshot=Snapshot(equity=Decimal(100_000), positions={}),
                        broker=broker, broker_symbol=f"X{n}", mode="paper", strategy_id=None, decided_at=time.time())
        results.append(out["status"])
    ts = [threading.Thread(target=agent, args=(n,)) for n in range(16)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    # each order is 10% of equity; gross exposure is capped at 50%: exactly five can be reserved
    assert results.count("NEW") == 5 and results.count("BLOCKED_BY_RISK") == 11
    assert len(broker.orders) == 5


def test_agent_budget_check_denies_entries_but_not_exits():
    risk = RiskService(Limits(max_open_positions=100))
    base = dict(instrument_id="X:1", market="crypto", reference_price=Decimal(100), limit_price=None,
                multiplier=Decimal(1), environment="paper", account_id="paper", agent_id="A050",
                agent_budget=Decimal(500), agent_instruments=("X:1",))
    snap = Snapshot(equity=Decimal(100_000), positions={"X:1": {"qty": Decimal(4), "price": Decimal(100),
                                                                "multiplier": Decimal(1), "market": "crypto"}})
    d = risk.check(OrderRequest(client_order_id="c1", side="buy", quantity=Decimal(2), **base), snap)
    assert not d.approved and "agent budget" in d.reason
    assert risk.check(OrderRequest(client_order_id="c2", side="buy", quantity=Decimal(1), **base), snap).approved
    snap.positions["X:1"]["qty"] = Decimal(9)
    exit_ = risk.check(OrderRequest(client_order_id="c3", side="sell", quantity=Decimal(9),
                                      reduces_position=True, **base), snap)
    assert exit_.approved


# ---------------------------------------------------------------- discovery (fake provider responses)
class FakeHttp:
    def __init__(self):
        self.products = [
            {"id": "BTC-USD", "base_currency": "BTC", "quote_currency": "USD", "status": "online",
             "quote_increment": "0.01", "base_increment": "0.00000001"},
            {"id": "DOGE-USD", "base_currency": "DOGE", "quote_currency": "USD", "status": "online",
             "quote_increment": "0.00001", "base_increment": "0.1"},
            {"id": "PEPE-USD", "base_currency": "PEPE", "quote_currency": "USD", "status": "online",
             "quote_increment": "0.00000001", "base_increment": "1"},
            {"id": "OLD-USD", "base_currency": "OLD", "quote_currency": "USD", "status": "online",
             "trading_disabled": True},
            {"id": "ETH-EUR", "base_currency": "ETH", "quote_currency": "EUR", "status": "online"},
        ]
        self.calls = []

    def get_json(self, url):
        self.calls.append(url)
        if url == D.COINBASE_PRODUCTS:
            return self.products
        if url == D.KRAKEN_PAIRS:
            return {"result": {"XDGUSD": {"base": "XXDG", "quote": "ZUSD", "altname": "XDGUSD", "status": "online"}}}
        if url == D.COINBASE_STATS:
            return {"BTC-USD": {"stats_24hour": {"last": "60000", "open": "59000", "volume": "1000"}},
                    "DOGE-USD": {"stats_24hour": {"last": "0.1", "open": "0.1", "volume": "5000000"}},
                    "PEPE-USD": {"stats_24hour": {"last": "0.00001", "open": "0.00001", "volume": "1"}}}
        if url == D.KRAKEN_TICKER:
            return {"result": {"XDGUSD": {"c": ["0.1", "1"], "o": "0.1", "v": ["1", "900000"]}}}
        raise AssertionError(url)


def test_discovery_inventory_snapshot_meme_tags_and_delisting(app):
    http = FakeHttp()
    app.md.http = http
    d = app.discovery
    assert d.refresh_listings() == {"COINBASE": 5, "KRAKEN": 1}
    assert d.snapshot() == 4 and d.version == 1
    rows = {r["symbol"]: r for r in d.listed("COINBASE")}
    assert rows["OLD-USD"]["status"] == "disabled"                  # trading disabled is not "online"
    elig = [r["symbol"] for r in d.listed() if d.execution_eligible(r)]
    assert sorted(elig) == ["BTC-USD", "DOGE-USD", "PEPE-USD"]       # online Coinbase USD pairs only
    assert [r["symbol"] for r in d.tradable_crypto(2)] == ["BTC-USD", "DOGE-USD"]   # most liquid first
    cov = d.coverage()
    assert cov["venues"]["COINBASE"]["listed"] == 5 and cov["venues"]["KRAKEN"]["listed"] == 1
    assert cov["venues"]["COINBASE"]["snapshot_fresh"] == 3 and cov["venues"]["COINBASE"]["stale_or_missing"] == 2
    memes = {(m["venue"], m["base"]) for m in cov["meme"]["pairs"]}
    assert memes == {("COINBASE", "DOGE"), ("COINBASE", "PEPE"), ("KRAKEN", "XXDG")}   # Kraken's DOGE code mapped
    assert all("unverified" in m["confidence"] for m in cov["meme"]["pairs"])
    assert cov["uncovered"] and "not every market" in cov["denominator"]
    http.products = [p for p in http.products if p["id"] != "PEPE-USD"]
    d.refresh_listings()
    pepe = {r["symbol"]: r for r in d.listed("COINBASE")}["PEPE-USD"]
    assert pepe["status"] == "delisted" and pepe["delisted"]
    assert d.coverage()["venues"]["COINBASE"]["delisted"] == 1


def test_discovery_is_off_in_offline_mode(app):
    app.discovery.start()
    assert app.discovery._thread is None and "offline" in app.discovery.status()


class ManyPairs(FakeHttp):
    def __init__(self, n=120):
        super().__init__()
        self.products = [{"id": f"C{k:03d}-USD", "base_currency": f"C{k:03d}", "quote_currency": "USD",
                          "status": "online", "quote_increment": "0.01", "base_increment": "0.001"} for k in range(n)]
        self.products += [{"id": f"{b}-USD", "base_currency": b, "quote_currency": "USD", "status": "online",
                           "quote_increment": "0.0001", "base_increment": "0.01"} for b in ("USDT", "WBTC", "BTC")]

    def get_json(self, url):
        if url == D.COINBASE_STATS:
            vol = {p["id"]: 1000 + i for i, p in enumerate(self.products)}
            vol.update({"USDT-USD": 10 ** 9, "WBTC-USD": 10 ** 9 - 1, "BTC-USD": 10 ** 9 - 2})   # most liquid
            return {k: {"stats_24hour": {"last": "1", "open": "1", "volume": str(v)}} for k, v in vol.items()}
        return super().get_json(url)


def test_online_all_100_agents_get_a_distinct_market_and_stablecoins_are_skipped(app):
    http = ManyPairs()
    memes = ["DOGE", "SHIB", "PEPE", "BONK", "WIF", "FLOKI", "MOG", "POPCAT", "TURBO", "PENGU", "TRUMP", "FARTCOIN",
             "PNUT", "MOODENG", "GIGA"]
    http.products += [{"id": f"{b}-USD", "base_currency": b, "quote_currency": "USD", "status": "online",
                       "quote_increment": "0.0001", "base_increment": "0.01"} for b in memes]
    app.md.http = http
    app.discovery.refresh_listings()
    app.discovery.snapshot()
    app.offline = False
    try:
        app.fleet.assign()
        f = app.fleet
        assert all(a.partition for a in f.agents.values())                    # 100 of 100 have a market
        meme_owned = {a.partition[0].split(":")[1].split("-")[0] for a in f.agents.values() if a.role.startswith("meme")}
        assert meme_owned == set(memes)                                      # the 15 meme agents hold the 15 meme coins
        assert not any(a.partition[0].split(":")[1].split("-")[0] in memes
                       for a in f.agents.values() if a.role.startswith("crypto"))   # other crypto agents never take one
        owned = [i for a in f.agents.values() for i in a.partition]
        assert len(owned) == 100 and len(set(owned)) == 100                  # all different
        assert not any(i.startswith("DEMO:") for i in owned)                 # demo markets only offline
        assert "COINBASE:USDT-USD" not in owned and "COINBASE:WBTC-USD" not in owned
        assert f.owner["COINBASE:BTC-USD"] == "A001"                          # majors are fixed, not duplicated
        from tradingai.strategies.library import MARKET_OF
        for a in f.agents.values():                                          # every agent trades its role's market
            mk = MARKET_OF.get(app.book.get(a.partition[0]).market_type)
            assert mk == M.ROLES[a.role].market, (a.agent_id, mk)
        inst = app.book.get(f.agents["A010"].partition[0])
        assert "discovered" in inst.tags and app.sources[inst.instrument_id].provider == "coinbase"
        app.fleet.cycle()
        assert app.fleet.counts()["blocked"] == 0
    finally:
        app.offline = True


def test_a_crash_and_restart_restores_agents_versions_positions_and_lessons(tmp_path, monkeypatch):
    home = str(tmp_path / "home")
    a = App(home, offline=True, start_loop=False)
    _buy_signal(monkeypatch)
    train(a, "A004", [1.0, 0.5, 0.2], params={"tsmom.none.trail": {"lookback": 48}})
    bot_id = a.fleet.bot_of["A004"]
    assert a.orch.decide(a.bots[bot_id], "paper")["outcome"] == "ORDER"
    a.paper.process()
    held = a.paper.get_positions()["DEMO:DEMO-TREND"]
    a.learning.record("STALE_DATA", agent_id="A004", instrument_id="DEMO:DEMO-TREND", detail={},
                      scenario={"data_age_s": 9000, "bar_seconds": 3600, "qty": "1"})
    a.fleet.suspend("A005", M.DAY, "test")
    owners = dict(a.fleet.owner)
    eid = a.ledger.start(family="test", strategy_id="tsmom.none.trail", hypothesis="x", instrument="DEMO:DEMO-TREND",
                         tf="1h", profile="STANDARD", seed=7, dataset={})    # a run cut off by the crash
    # crash: no shutdown, nothing flushed by hand
    b = App(home, offline=True, start_loop=False)
    try:
        assert b.state.state == "PAPER_RUNNING" or b.state.state == "READY", b.state.state
        assert all(c["ok"] for c in b.checks if c["name"] != "frontend files"), [c for c in b.checks if not c["ok"]]
        assert b.paper.get_positions()["DEMO:DEMO-TREND"] == held           # the position survived
        assert b.fleet.owner == owners and b.fleet.bot_of["A004"] == bot_id  # same agents, same markets
        bot = b.bots[bot_id]
        assert bot.agent_id == "A004" and bot.params == {"lookback": 48} and bot.state == "running"
        assert b.fleet.active_version("A004")["version"] == 1 and b.fleet.permission("A004")[0]
        assert "suspended" in b.fleet.permission("A005")[1] or b.fleet.permission("A005")[0] is False
        assert "STALE_DATA" in b.learning.lessons and b.learning.last_regression["failed"] == []
        assert b.db.one("SELECT status FROM experiments WHERE experiment_id=?", (eid,))["status"] == "FAILED"
        assert b.reconcile()["ok"]
    finally:
        b.shutdown()
        a.shutdown()


def _online(app):
    app.md.http = ManyPairs()
    app.discovery.refresh_listings()
    app.discovery.snapshot()
    app.offline = False


def test_a_restart_before_the_first_price_snapshot_does_not_move_any_agent(app):
    _online(app)
    try:
        app.fleet.assign()
        before = {aid: list(a.partition) for aid, a in app.fleet.agents.items()}
        app.discovery.snap.clear()                       # as right after a start: no volumes, ranking unknown
        out = app.fleet.assign()
        assert out["changed"] == 0
        assert {aid: list(a.partition) for aid, a in app.fleet.agents.items()} == before
        app.discovery.snapshot()                         # ranking back: still nothing moves
        assert app.fleet.assign()["changed"] == 0
    finally:
        app.offline = True


def test_a_fresh_start_takes_no_discovered_pair_until_the_ranking_is_known(app):
    app.md.http = ManyPairs()
    app.discovery.refresh_listings()                     # listed, but no snapshot yet
    app.offline = False
    try:
        app.fleet.assign()
        crypto = [a for a in app.fleet.agents.values() if a.role in ("crypto_trend", "crypto_reversion")]
        assert all(not a.partition for a in crypto)      # no alphabetical guess: they wait
        app.discovery.snapshot()
        app.fleet.assign()
        assert all(a.partition for a in crypto)
    finally:
        app.offline = True


def test_small_rank_changes_do_not_move_agents_but_a_delisted_pair_does(app):
    _online(app)
    try:
        app.fleet.assign()
        a = app.fleet.agents["A010"]
        iid = a.partition[0]
        ps = app.md.http.products
        for k in range(0, 120, 2):                       # neighbours swap volumes: every pair moves one rank
            ps[k], ps[k + 1] = ps[k + 1], ps[k]
        app.discovery.snapshot()
        assert app.fleet.assign()["changed"] == 0 and a.partition == [iid]
        top = ps[:2]
        app.md.http.products = ps[2:120] + top + ps[120:]   # the two quietest pairs become the most liquid:
        app.discovery.snapshot()                             # nobody is pushed out of the 3x window
        assert app.fleet.assign()["changed"] == 0
        app.md.http.products = [p for p in app.md.http.products if f"COINBASE:{p['id']}" != iid]
        app.discovery.refresh_listings()                 # the pair disappears: it is delisted
        app.discovery.snapshot()
        app.fleet.assign()
        assert a.partition and a.partition != [iid]
    finally:
        app.offline = True


def test_a_version_trained_on_one_market_is_never_used_on_another(app):
    _online(app)
    try:
        app.fleet.assign()
        a = app.fleet.agents["A010"]
        old = a.partition[0]
        train(app, "A010", [1.0, 0.5, 0.2])
        assert app.fleet.active_version("A010") is not None
        app.md.http.products = [p for p in app.md.http.products if f"COINBASE:{p['id']}" != old]
        app.discovery.refresh_listings()
        app.discovery.snapshot()
        app.fleet.assign()
        assert a.partition and a.partition[0] != old
        assert app.fleet.active_version("A010") is None
        assert app.fleet.versions("A010")[-1]["status"] == "retired"
        ok, why = app.fleet.permission("A010")
        assert not ok
    finally:
        app.offline = True


def test_a_slow_agent_job_is_never_doubled_and_refreshes_are_spread(app, monkeypatch):
    import threading as th
    gate = th.Event()
    a = app.fleet.agents["A004"]
    real = app.fleet._job

    def slow(agent):
        if agent is a:
            gate.wait(5)
        return real(agent)
    monkeypatch.setattr(app.fleet, "_job", slow)
    monkeypatch.setattr(M, "JOB_SECONDS", 0.05)
    app.fleet.cycle()                                    # A004's job is stuck
    out = app.fleet.cycle()                              # the next cycle must not start a second one
    assert out["agents"] == 99 and app.fleet.metrics["busy_skipped"] >= 1
    gate.set()



def test_monitoring_jobs_never_wait_on_the_network_when_the_data_refresher_runs(app, monkeypatch):
    calls = []
    monkeypatch.setattr(app, "quote", lambda iid: calls.append(iid) or {"ts": now_ms(), "price": 1.0})
    app.fleet._refresher = object()                      # as when start() has launched the refresher thread
    app.fleet._quotes["US:QCOM"] = {"ts": now_ms(), "price": 5000.0}
    app.fleet.cycle()
    assert calls == []                                   # jobs read the refresher's cache only
    es = next(a for a in app.fleet.agents.values() if a.partition == ["US:QCOM"])
    assert es.last_price == "5000.0"
