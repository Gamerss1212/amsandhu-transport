"""Fleet Brain: scoring, vetoes, self-learning, calibration, persistence."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mab.brain import FleetBrain  # noqa: E402
from mab.frame import Frame  # noqa: E402
from tests.test_platform import crypto_bars  # noqa: E402

F = Frame("test", "TST", "5m", "crypto", crypto_bars(600))


def test_brain_starts_neutral_and_approves():
    b = FleetBrain(seed=1)
    d = b.score("B1", "S1", "TST", F, 500, 1)
    assert d["action"] in ("approve", "resize") and 0.5 <= d["size"] <= 1.5 and 0 < d["p_win"] < 1


def test_brain_vetoes_a_strategy_with_a_bad_record_and_keeps_a_good_one():
    b = FleetBrain(seed=2)
    for _ in range(40):
        b.score("B1", "BAD", "TST", F, 500, 1); b.learn("B1", "BAD", "TST", -1.0)
        b.score("B2", "GOOD", "TST", F, 500, 1); b.learn("B2", "GOOD", "TST", 1.5)
    bad = [b.score("B1", "BAD", "TST", F, 500, 1)["action"] for _ in range(20)]
    good = [b.score("B2", "GOOD", "TST", F, 500, 1) for _ in range(20)]
    assert bad.count("veto") >= 18
    assert all(g["action"] != "veto" and g["size"] > 1.0 for g in good)


def test_priors_from_evaluation_and_live_data_overrides_them(tmp_path):
    p = tmp_path / "ev.json"
    p.write_text(json.dumps({"strategies": {"S9": {"runs": [
        {"cost": "base", "instrument": "TST", "full": {"trades": 200, "expectancy_r": -0.6}}]}}}))
    b = FleetBrain(seed=3)
    assert b.load_priors(str(p)) == 1
    assert b.estimate("S:S9")["mean"] < -0.5
    for _ in range(200):
        b.learn("B", "S9", "TST", 0.8)
    assert b.estimate("S:S9")["mean"] > 0.5            # 200 live trades outweigh the capped prior


def test_consensus_and_advisory_mode():
    b = FleetBrain(mode="advisory", seed=4)
    for k in range(6):
        b.observe(f"B{k}", "TST", 1 if k < 5 else -1, 10 ** 13)
    c = b.consensus_of("TST")
    assert c["long"] == 5 and c["short"] == 1
    for _ in range(40):
        b.learn("B1", "BAD", "TST", -2.0)
    assert b.score("B1", "BAD", "TST", F, 500, 1)["action"] == "approve"   # advisory never blocks


def test_learning_updates_model_and_state_round_trips():
    b = FleetBrain(seed=5)
    for k in range(100):
        d = b.score("B", "S", "TST", F, 400 + k, 1 if k % 2 else -1)
        b.learn("B", "S", "TST", 1.0 if k % 2 else -1.0, d)
    s = b.summary()
    assert s["trades_learned"] == 100 and sum(c["trades"] for c in s["calibration"]) == 100
    assert s["weights"]["is_long"] > 0                  # learned that longs won in this data
    b2 = FleetBrain(seed=5)
    b2.restore(json.loads(json.dumps(b.to_state())))
    assert b2.summary()["trades_learned"] == 100 and b2.w == b.w


def test_regime_detection_is_causal_and_sensible():
    from mab.brain import regime_of, regime_key
    up = [100 + k for k in range(300)]
    flat = [100 + (1 if k % 2 else -1) for k in range(300)]
    assert regime_of(up, 250)["trend"] == "up" and regime_of(flat, 250)["trend"] == "range"
    assert regime_key(regime_of(up, 250), 1).startswith("with") and regime_key(regime_of(up, 250), -1).startswith("against")
    # no look-ahead: the regime at bar i does not change when later bars are appended
    xs = F.c
    assert regime_of(xs[:401], 400) == regime_of(xs, 400)


def test_hierarchy_transfers_family_evidence_to_a_new_strategy():
    b = FleetBrain(seed=6)
    b.connect("B1", "OLD", "gaps", "Old gap strategy")
    b.connect("B2", "NEW", "gaps", "New gap strategy")
    for _ in range(60):
        b.learn("B1", "OLD", "TST", -1.0)
    est = b._combined("NEW", "TST")
    assert est["mean"] < -0.5 and est["n_eff"] == 0          # pulled down by its family, with no evidence of its own
    b.connect("B3", "OTHER", "vwap")
    assert abs(b._combined("OTHER", "TST")["mean"]) < 0.5     # another family is not dragged down as much


def test_shadow_trades_learn_from_vetoes_and_insights_are_written():
    b = FleetBrain(seed=8)
    b.connect("B1", "BAD", "gaps", "Bad gaps")
    for _ in range(40):
        b.score("B1", "BAD", "TST", F, 500, 1)
        b.learn("B1", "BAD", "TST", -1.0)
    d = b.score("B1", "BAD", "TST", F, 500, 1)
    assert d["action"] == "veto" and d["benched"]
    assert b.summary()["benched_now"] == 1
    assert any("Learned: Bad gaps loses" in x["text"] for x in b.summary()["insights"])
    # a long shadow with the stop just under the next bar's low and a target at its high hits the target
    i = 450
    entry = F.c[i]
    b.shadow_open("B1", d, entry, entry - 10 * (F.h[i + 1] - F.l[i + 1] + 1), F.h[i + 1], 0.0, F.t[i])
    n0 = b.post["S:BAD"]["n"]
    b.shadow_step("B1", F, i + 1)
    s = b.summary()
    assert s["shadow_trades"] == 1 and s["shadow_avg_r"] >= 0 and b.post["S:BAD"]["n"] == n0 + 0.5
    assert "B1" not in b.shadows


def test_restore_keeps_learning_across_an_upgrade_that_adds_features():
    b = FleetBrain(seed=9)
    for k in range(60):
        d = b.score("B", "S", "TST", F, 400 + k, 1)
        b.learn("B", "S", "TST", 1.0, d)
    st = json.loads(json.dumps(b.to_state()))
    old_names = st["features"][:11]
    st["w"], st["features"] = st["w"][:11], old_names             # a state saved by the previous version
    b2 = FleetBrain(seed=9)
    b2.restore(st)
    from mab.brain import FEATURES
    assert b2.w[:11] == b.w[:11] and b2.w[11:] == [0.0] * (len(FEATURES) - 11) and b2.summary()["trades_learned"] == 60


def test_priors_follow_each_venue_costs(tmp_path):
    p = tmp_path / "ev.json"
    p.write_text(json.dumps({"strategies": {"S1": {"runs": [
        {"cost": "retail_kraken", "instrument": "BTC-USD", "full": {"trades": 100, "expectancy_r": -1.5}},
        {"cost": "low_fee_venue", "instrument": "BTC-USD", "full": {"trades": 100, "expectancy_r": 0.2}}]}}}))
    b = FleetBrain(seed=10)
    b.load_priors(str(p))
    assert b.estimate("S:S1")["mean"] < -1 and b.estimate("S:S1@low")["mean"] > 0
    assert b._combined("S1@low", "BTC-USDT")["mean"] > 0 > b._combined("S1", "BTC-USD")["mean"]


def test_resting_orders_go_through_the_brain_and_the_risk_layer(tmp_path, monkeypatch):
    """A stop/limit/bracket entry fills inside the bar, so it must be accepted when it is placed."""
    from types import SimpleNamespace
    from mab import runtime
    from mab.runtime import Fleet
    from mab.strategy import Pending
    fl = Fleet({"data_dir": str(tmp_path / "d"), "brain": {"mode": "active"}}, {}, [], str(tmp_path))
    i = 500
    monkeypatch.setattr(runtime, "now_ms", lambda: F.t[i] + F.step + 2000)     # the bar just closed

    def bot(bid, sid):
        p = Pending(1, "stop", F.c[i] * 1.001, F.t[i], F.t[i] + F.step, F.c[i] * 0.99, False, None, False, "long entry")
        tm = SimpleNamespace(pending=p, _plan=lambda pp, px: (10.0 * pp.size, F.c[i] * 0.99, None))
        filler = SimpleNamespace(fee=lambda notional, liq: notional * 0.001, cm=SimpleNamespace(slip=0.0005))
        return SimpleNamespace(id=bid, venue="coinbase", symbol="TST", c=SimpleNamespace(id=sid, definition={}),
                               tm=tm, enabled=True, series_keys=[], last_decision="", filler=filler)
    for _ in range(40):
        fl.brain.learn("B0", "BAD", "TST", -1.0)
    bad = bot("B1", "BAD")
    assert fl._accept_resting(bad, F, i) == "vetoed" and bad.tm.pending is None
    good = bot("B2", "NEW")
    r = fl._accept_resting(good, F, i)
    assert r == "order_placed" and good.tm.pending is not None, good.last_decision
    fl.paused = True                                   # the risk layer refuses entries while paused
    held = bot("B3", "NEW")
    assert fl._accept_resting(held, F, i) == "blocked" and held.tm.pending is None



def test_cost_and_volatility_gates():
    b = FleetBrain(seed=11)
    assert b.score("B", "S", "TST", F, 500, 1, cost_r=0.5)["veto_kind"] == "cost"
    half = b.score("B", "S", "TST", F, 500, 1, cost_r=0.25)
    assert half["action"] == "resize" and half["size"] <= 0.5 + 1e-9
    q = b.score("B", "S", "TST", F, 500, 1, cost_r=0.05, gate={"state": "QUIET", "p_loud": 0.1, "p_quiet": 0.9})
    assert q["action"] == "veto" and q["veto_kind"] == "quiet"
    loud = b.score("B", "S", "TST", F, 500, 1, cost_r=0.05, gate={"state": "LOUD", "p_loud": 0.9, "p_quiet": 0.1})
    assert loud["action"] == "resize" and abs(loud["size"] - 0.6) < 1e-9
    ok = b.score("B", "S", "TST", F, 500, 1, cost_r=0.05, gate={"state": "NORMAL", "p_loud": 0.4, "p_quiet": 0.2})
    assert ok["action"] == "approve" and ok["size"] == 1.0
    adv = FleetBrain(mode="advisory", seed=11)          # advisory never blocks, even on costs
    assert adv.score("B", "S", "TST", F, 500, 1, cost_r=0.9)["action"] == "approve"
    # shadow results are tracked per veto reason
    d = b.score("B", "S", "TST", F, 450, 1, cost_r=0.5)
    b.shadow_open("B", d, F.c[450], F.c[450] * 0.9, None, 0.0, F.t[450], max_bars=1)
    b.shadow_step("B", F, 451)
    assert b.summary()["shadow_by_kind"]["cost"]["trades"] == 1


def test_volatility_gate_reads_states():
    from mab import volgate as VG
    import math as m
    n = 600
    t = [1_700_000_000_000 + k * 3_600_000 for k in range(n)]
    c = [100 + 5 * m.sin(k / 9) + (k % 7) * 0.1 for k in range(n)]
    bars = VG.Bars(t, c, [x + 0.5 for x in c], [x - 0.5 for x in c], c, [1000.0] * n)
    f = VG.features(bars, n - 1)
    assert f is not None and len(f) == len(VG.FEATURES)
    assert VG.features(bars, 10) is None                   # not enough history yet
    k = len(VG.FEATURES)
    model = {"crypto": {"mean": [0.0] * k, "std": [1.0] * k, "w_loud": [5.0] + [0.0] * (k - 1),
                        "w_quiet": [-5.0] + [0.0] * (k - 1), "t_loud": 0.8, "t_quiet": 0.8}}
    assert VG.VolGate(model).read(bars, n - 1)["state"] == "LOUD"
    model["crypto"]["w_loud"][0], model["crypto"]["w_quiet"][0] = -5.0, 5.0
    assert VG.VolGate(model).read(bars, n - 1)["state"] == "QUIET"
    assert VG.VolGate({}).read(bars, n - 1)["state"] == "UNKNOWN"
