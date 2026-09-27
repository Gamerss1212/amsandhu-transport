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
