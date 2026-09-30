"""Research engine: walk-forward evaluation with baselines, the job pool (processes, cache, budgets), registries
with approval gates, forward brain comparison and drift."""

import json
import os
import sys
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mab.research import data as D, evaluate as RE  # noqa: E402
from mab.research.jobs import JobQueue, Pool  # noqa: E402
from mab.research.registry import ACCEPT_TEXT, Registry  # noqa: E402
from mab.storage import Storage  # noqa: E402

STRAT = {"id": "T-EMA", "name": "EMA cross (test)", "family": "trend_following", "timeframe": "5m", "direction": "long",
         "params": {}, "entry": {"long": "ema(close,8) > ema(close,21) and close > open"}, "filters": [],
         "order": {"type": "market"}, "stop": {"type": "atr", "mult": 3.0, "n": 14}, "target": {"type": "r", "r": 2.0},
         "trail": {"type": "none"}, "exit": {}, "max_bars": 48, "session": {"crypto": {"hold_overnight": True}},
         "max_trades_per_day": 20, "cooldown_bars": 2, "sizing": {"risk_pct": 0.5, "max_notional_pct": 100.0},
         "data": ["bars"], "version": "1.0.0"}


def test_data_quality_counts_duplicates_gaps_and_invalid_bars():
    from mab.models import Bar
    step = 300_000
    t0 = 1_780_000_000_000 - (1_780_000_000_000 % step)
    bars = [Bar("demo", "X", "5m", t0 + k * step, 10, 11, 9, 10.5, 5) for k in range(10)]
    bars.append(Bar("demo", "X", "5m", t0 + 3 * step, 10, 11, 9, 10.4, 5))          # duplicate
    bars.insert(2, Bar("demo", "X", "5m", t0 + 20 * step, 10, 11, 9, 10.5, 5))      # out of order, leaves a gap
    bars.append(Bar("demo", "X", "5m", t0 + 30 * step, 10, 9, 11, 10.5, 5))        # high below low
    out, q = D.clean(bars, "5m")
    assert q["duplicates"] == 1 and q["out_of_order"] >= 1 and q["invalid"] == 1 and q["gaps"] == 1
    assert q["missing_bars"] == 10 and [b.event_time for b in out] == sorted(b.event_time for b in out)
    assert "missing bars" in q["verdict"]


def test_walk_forward_has_splits_folds_baselines_and_a_verdict():
    bars, q = D.fetch("demo", "DEMO-ETH", "5m", 30)
    fr = D.frame(bars, "crypto")
    res = RE.run(STRAT, fr, "demo", fees={"taker": 0.001, "maker": 0.0008}, draws=20, k_folds=4)
    seg = res["segments"]
    assert seg["train"]["end"] <= seg["validation"]["start"] < seg["validation"]["end"] <= seg["test"]["start"]
    assert seg["validation"]["start"] - seg["train"]["end"] >= 86_400_000 - 300_000      # one-day embargo
    assert len(res["folds"]) == 4 and res["baselines"]["random_entries"]["draws"] > 0
    assert res["baselines"]["no_trade_r"] == 0.0 and "buy_and_hold_return" in res["baselines"]
    assert set(res["checks"]) >= {"enough_test_trades", "test_ci_above_zero", "beats_random_entries"}
    assert isinstance(res["verdict"], str) and res["passes"] == all(res["checks"].values())
    gross, net = res["test_gross"]["expectancy_r"], seg["test"]["expectancy_r"]
    if gross is not None and net is not None:
        assert gross >= net                                            # costs can only hurt
    assert res["assumptions"]["latency"].startswith("decided at bar close")


def test_liquidity_limit_makes_partial_fills():
    from mab import backtest
    from mab.strategy import compile_strategy, evaluate
    bars, q = D.fetch("demo", "DEMO-BTC", "5m", 10)
    fr = D.frame(bars, "crypto")
    c = compile_strategy(STRAT, None, "crypto")
    rs = evaluate(c, fr)
    full = backtest.run(c, fr, "demo", capital=10_000_000, rs=rs)
    capped = backtest.run(c, fr, "demo", capital=10_000_000, rs=rs, max_participation=0.001)
    assert capped.skipped.get("partial fill: liquidity limit", 0) > 0
    assert sum(t.qty for t in capped.trades) < sum(t.qty for t in full.trades)


def _pool(tmp_path, **kw):
    db = str(tmp_path / "w.db")
    st = Storage(db)
    return st, JobQueue(st), Pool(lambda: [("main", db)], str(tmp_path / "cache"), poll_s=0.2, **kw)


def _wait(q, jid, timeout=120):
    t = time.time()
    while time.time() - t < timeout:
        j = q.get(jid)
        if j["state"] in ("done", "failed", "canceled"):
            return j
        time.sleep(0.3)
    raise AssertionError(f"job {jid} still {q.get(jid)['state']}")


def test_pool_runs_jobs_in_processes_and_caches_results(tmp_path):
    st, q, pool = _pool(tmp_path, max_workers=2)
    spec = {"definition": STRAT, "venue": "demo", "instrument": "DEMO-SOL", "days": 14, "draws": 10, "k_folds": 3,
            "fee_profile": "low_fee"}
    a = q.submit("walk_forward", spec)
    pool.start()
    try:
        ja = _wait(q, a["job_id"])
        assert ja["state"] == "done", ja.get("error")
        assert not ja["cached"] and ja["result"]["strategy_version"] and ja["result"]["data_quality"]["bars"] > 500
        b = q.submit("walk_forward", spec)                              # the same question on the same data
        jb = _wait(q, b["job_id"])
        assert jb["state"] == "done" and jb["cached"] == 1
        assert jb["result"]["verdict"] == ja["result"]["verdict"]
        assert pool.status()["hardware"]["gpu"] is None
    finally:
        pool.stop()
    stages = [e["stage"] for e in st.audit_search(kinds=["research"])]
    assert "job_queued" in stages and "job_done" in stages


def test_pool_enforces_the_time_budget(tmp_path):
    st, q, pool = _pool(tmp_path, max_workers=1, timeout_s=0.5)
    j = q.submit("walk_forward", {"definition": STRAT, "venue": "demo", "instrument": "DEMO-BTC", "days": 60, "draws": 300})
    pool.start()
    try:
        out = _wait(q, j["job_id"], 60)
    finally:
        pool.stop()
    assert out["state"] == "failed" and "time budget" in out["error"]


def test_bad_specs_fail_cleanly(tmp_path):
    st, q, pool = _pool(tmp_path)
    with pytest.raises(ValueError):
        q.submit("mine_bitcoin", {})
    j = q.submit("walk_forward", {"venue": "demo", "instrument": "DEMO-BTC"})
    pool.start()
    try:
        out = _wait(q, j["job_id"])
    finally:
        pool.stop()
    assert out["state"] == "failed" and "definition" in out["error"]


def test_live_approval_needs_a_passing_evaluation_or_typed_acceptance(tmp_path):
    st = Storage(str(tmp_path / "r.db"))
    reg = Registry(st)
    reg.register_strategy("T-EMA", STRAT, "v1")
    assert reg.status("T-EMA", "v1") == "research"
    q = JobQueue(st)
    j = q.submit("walk_forward", {"definition": STRAT})
    st.write("UPDATE research_jobs SET state='done', result=? WHERE job_id=?",
             (json.dumps({"strategy_version": "v1", "passes": False, "checks": {"enough_test_trades": False}}), j["job_id"]))
    with pytest.raises(ValueError):
        reg.approve_live("T-EMA", "v1", q.get(j["job_id"]), "owner")
    with pytest.raises(ValueError):
        reg.approve_live("T-EMA", "v1", None, "owner")
    out = reg.approve_live("T-EMA", "v1", q.get(j["job_id"]), "owner", accept=ACCEPT_TEXT)
    assert out["status"] == "live_approved"
    p = reg.promotions()[0]
    assert p["to_status"] == "live_approved" and p["approved_by"] == "owner"


def test_brain_promotion_uses_forward_trades_only(tmp_path):
    from mab.brain import FleetBrain
    st = Storage(str(tmp_path / "b.db"))
    reg = Registry(st)
    b = FleetBrain(seed=3)
    snap = reg.snapshot_brain(b)
    feats = json.dumps([1.0] + [0.0] * 16)
    old = int(time.time() * 1000) - 10 ** 7                            # before the snapshot: must be ignored
    st.write("INSERT INTO brain_samples (ts, strategy_key, instrument, regime, features, cost_r, gate, r) VALUES "
             "(?,?,?,?,?,?,?,?)", (old, "S", "X", None, feats, 0.1, None, 5.0))
    for k in range(60):
        st.write("INSERT INTO brain_samples (ts, strategy_key, instrument, regime, features, cost_r, gate, r) VALUES "
                 "(?,?,?,?,?,?,?,?)", (int(time.time() * 1000) + k + 5, "S", "X", None, feats, 0.5 if k % 2 else 0.1, None,
                                       -1.0 if k % 2 else 0.5))
    from mab.research.worker import brain_eval
    q = JobQueue(st)
    out, _, _ = brain_eval(st, q, {"candidate": snap["version"], "champion": "none"}, "", lambda f, m: None)
    assert out["trades"] == 60                                          # the older trade is excluded
    assert out["recommendation"].startswith("candidate better")         # its cost veto skips the -1R trades
    j = q.submit("brain_eval", {"candidate": snap["version"]})
    st.write("UPDATE research_jobs SET state='done', result=? WHERE job_id=?", (json.dumps(out), j["job_id"]))
    ch = reg.promote_brain(snap["version"], q.get(j["job_id"]), "owner")
    assert ch["status"] == "champion" and reg.champion("brain")["version"] == snap["version"]


def test_performance_drift_flags_a_strategy_below_its_test_result(tmp_path):
    from mab.research import drift
    st = Storage(str(tmp_path / "d.db"))
    now = int(time.time() * 1000)
    for k in range(40):
        st.save_trade("B1", "coinbase", {"strategy_id": "S1", "instrument": "BTC-USD", "side": 1, "qty": 1,
                                         "entry_time": now, "entry_price": 1, "exit_time": now, "exit_price": 1,
                                         "fees": 0, "pnl": -1, "r": -0.8 + (0.1 if k % 2 else -0.1), "bars": 1,
                                         "entry_reason": "", "exit_reason": "", "mfe_r": 0, "mae_r": 0}, "paper")
    rows = drift.performance(st, lambda sid: [{"cost": "retail_kraken", "instrument": "BTC-USD",
                                               "test": {"expectancy_r": 0.2}}])
    assert rows[0]["status"] == "alert" and rows[0]["z"] < -3
    assert drift.latest(st)[0]["status"] == "alert"
