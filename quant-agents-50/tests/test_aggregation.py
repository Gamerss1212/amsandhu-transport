from __future__ import annotations

import math

import numpy as np
import pytest
from hypothesis import given
from hypothesis import strategies as st

from quantagents.aggregation import (
    PoolResult,
    Vote,
    go_decision,
    harmonize,
    implied_return,
    logit,
    n_eff_from_correlation,
    normalize,
    pool_votes,
    shrink_to_equal,
    sigmoid,
    size_hint,
    votes_from_predictions,
    waterfill,
)
from quantagents.config import AppConfig
from quantagents.schemas import Direction
from tests.helpers import prediction


def test_logit_and_sigmoid_are_inverses() -> None:
    for p in (0.01, 0.3, 0.5, 0.77, 0.99):
        assert sigmoid(logit(p)) == pytest.approx(p)
    assert sigmoid(-800.0) == pytest.approx(0.0)
    assert sigmoid(800.0) == pytest.approx(1.0)


def test_harmonize_horizons() -> None:
    assert harmonize(0.6, 20, 20) == pytest.approx(0.6)
    short = harmonize(0.6, 5, 20)
    assert 0.5 < short < 0.6
    assert harmonize(0.6, 80, 20) == pytest.approx(short)
    assert harmonize(0.4, 5, 20) == pytest.approx(1.0 - short)
    with pytest.raises(ValueError):
        harmonize(0.6, 0, 20)


def test_normalize_and_shrink() -> None:
    assert normalize({"a": 1.0, "b": 3.0}) == {"a": 0.25, "b": 0.75}
    for bad in ({}, {"a": -1.0}, {"a": 0.0}, {"a": math.nan}):
        with pytest.raises(ValueError):
            normalize(bad)
    shrunk = shrink_to_equal({"a": 1.0, "b": 0.0}, 0.3)
    assert shrunk == pytest.approx({"a": 0.85, "b": 0.15})
    with pytest.raises(ValueError):
        shrink_to_equal({"a": 1.0}, 1.5)


@given(st.lists(st.floats(min_value=0.01, max_value=100.0), min_size=4, max_size=12))
def test_waterfill_caps_and_sums_to_one(raw: list[float]) -> None:
    weights = waterfill({str(i): w for i, w in enumerate(raw)}, 0.25)
    assert sum(weights.values()) == pytest.approx(1.0)
    assert max(weights.values()) <= 0.25 + 1e-9


def test_waterfill_edge_cases() -> None:
    assert waterfill({"a": 5.0, "b": 1.0}, 0.25) == {"a": 0.5, "b": 0.5}
    zeros = waterfill({"a": 1.0, "b": 0.0, "c": 0.0, "d": 0.0, "e": 0.0}, 0.25)
    assert zeros["a"] == pytest.approx(0.25)
    assert sum(zeros.values()) == pytest.approx(1.0)
    with pytest.raises(ValueError):
        waterfill({"a": 1.0}, 0.0)


def test_n_eff() -> None:
    assert n_eff_from_correlation(np.eye(6)) == pytest.approx(6.0)
    # herding test (spec section 77): ten clones of one agent count as one opinion
    assert n_eff_from_correlation(np.ones((10, 10))) == pytest.approx(1.0)
    with pytest.raises(ValueError):
        n_eff_from_correlation(np.array([[1.0, 0.5], [0.1, 1.0]]))
    with pytest.raises(ValueError):
        n_eff_from_correlation(np.ones(3))
    assert n_eff_from_correlation(np.zeros((2, 2))) == 0.0


def test_two_stage_pooling_stops_one_team_outvoting_another(cfg: AppConfig) -> None:
    crowd = [Vote(f"A{11 + i}", 3, 0.7) for i in range(5)]
    lone = [Vote("A16", 4, 0.3)]
    equal = pool_votes("AAA", crowd + lone, cfg.aggregation, two_stage=False, n_eff=10)
    two = pool_votes("AAA", crowd + lone, cfg.aggregation, two_stage=True, n_eff=10)
    assert equal.p_up > 0.6
    assert two.p_up == pytest.approx(0.5)
    assert sum(two.agent_weights.values()) == pytest.approx(1.0)


def test_pool_details(cfg: AppConfig) -> None:
    agg = cfg.aggregation
    empty = pool_votes("AAA", [], agg, two_stage=True)
    assert empty.n_agents == 0 and empty.direction is Direction.FLAT
    with pytest.raises(ValueError, match="duplicate"):
        pool_votes("AAA", [Vote("A11", 3, 0.6), Vote("A11", 3, 0.6)], agg, two_stage=False)
    votes = [Vote("A11", 3, 0.7), Vote("A12", 3, 0.65), Vote("A23", 5, 0.6), Vote("A16", 4, 0.45)]
    capped = pool_votes("AAA", votes, agg, two_stage=True)
    assert capped.n_eff == 3.0
    assert capped.p_up <= agg.low_n_eff_p_cap
    assert capped.teams_agree == 2
    short = pool_votes("AAA", [Vote("A11", 3, 0.3), Vote("A23", 5, 0.4)], agg, two_stage=False)
    assert short.direction is Direction.SHORT
    assert short.p_direction == pytest.approx(1.0 - short.p_up)
    assert short.teams_agree == 2
    assert short.disagreement > 0


def test_votes_skip_abstentions_and_harmonize() -> None:
    preds = [
        prediction("A11", p_up=0.6),
        prediction("A16", abstain=True),
        prediction("A23", p_up=0.55, horizon=4),
    ]
    votes = votes_from_predictions(preds, 20)
    assert [v.agent_id for v in votes] == ["A11", "A23"]
    assert votes[1].p_up < 0.55


def _pool(p: float, teams_agree: int = 3, disagreement: float = 0.1) -> PoolResult:
    direction = Direction.LONG if p > 0.5 else Direction.SHORT
    return PoolResult(
        "AAA", "equal_weight", p, p, direction, max(p, 1 - p), disagreement, 4, 3, teams_agree, 3.0
    )


def test_go_rules_each_failure_is_explained(cfg: AppConfig) -> None:
    agg, costs = cfg.aggregation, cfg.costs
    ok = go_decision(
        _pool(0.6), sigma_daily=0.02, agg=agg, costs=costs, phase=3, p_no_trade=0.2, blocks=()
    )
    assert ok.go and ok.reasons == ("all GO rules passed",)
    assert ok.exp_return == pytest.approx(implied_return(0.6, 0.02, 20))
    cases = {
        "below 0.55": go_decision(
            _pool(0.53), sigma_daily=0.02, agg=agg, costs=costs, phase=3, p_no_trade=None, blocks=()
        ),
        "round-trip cost": go_decision(
            _pool(0.6), sigma_daily=0.001, agg=agg, costs=costs, phase=3, p_no_trade=None, blocks=()
        ),
        "team(s) agree": go_decision(
            _pool(0.6, teams_agree=1),
            sigma_daily=0.02,
            agg=agg,
            costs=costs,
            phase=3,
            p_no_trade=None,
            blocks=(),
        ),
        "p_no_trade": go_decision(
            _pool(0.6), sigma_daily=0.02, agg=agg, costs=costs, phase=3, p_no_trade=0.5, blocks=()
        ),
        "Tier-1 block": go_decision(
            _pool(0.6),
            sigma_daily=0.02,
            agg=agg,
            costs=costs,
            phase=3,
            p_no_trade=None,
            blocks=("A02",),
        ),
        "volatility forecast": go_decision(
            _pool(0.6), sigma_daily=None, agg=agg, costs=costs, phase=3, p_no_trade=None, blocks=()
        ),
    }
    for text, decision in cases.items():
        assert not decision.go
        assert any(text in r for r in decision.reasons), (text, decision.reasons)
    phase5 = go_decision(
        _pool(0.6, teams_agree=2),
        sigma_daily=0.02,
        agg=agg,
        costs=costs,
        phase=5,
        p_no_trade=None,
        blocks=(),
    )
    assert not phase5.go
    nobody = go_decision(
        pool_votes("AAA", [], agg, two_stage=False),
        sigma_daily=0.02,
        agg=agg,
        costs=costs,
        phase=3,
        p_no_trade=None,
        blocks=(),
    )
    assert nobody.reasons == ("no agent made a forecast",)


def test_size_hint_bounds(cfg: AppConfig) -> None:
    agg = cfg.aggregation
    assert size_hint(_pool(0.55), agg) == pytest.approx(0.5 * (1 - 0.1))
    assert size_hint(_pool(0.60), agg) == pytest.approx(1.0 * (1 - 0.1))
    assert size_hint(_pool(0.60, disagreement=5.0), agg) == pytest.approx(0.5)


def test_a35_weights_and_a09_costs_only_act_where_allowed(cfg: AppConfig) -> None:
    agg = cfg.aggregation
    four = [prediction(a, p_up=0.6) for a in ("A11", "A12", "A23")] + [prediction("A16", p_up=0.4)]
    votes = votes_from_predictions(four, 20, {"A16": 2.0})
    assert [v.weight for v in votes] == [1.0, 1.0, 1.0, 2.0]
    # With 4 voters the 25% per-agent cap is only met by equal weights: A35 cannot tilt them.
    capped = pool_votes("AAA", votes, agg, two_stage=True)
    assert set(capped.agent_weights.values()) != set() and capped.p_up == pytest.approx(
        pool_votes("AAA", votes_from_predictions(four, 20), agg, two_stage=True).p_up
    )
    six = [*four, prediction("A13", p_up=0.6), prediction("A15", p_up=0.6)]
    heavy = pool_votes("AAA", votes_from_predictions(six, 20, {"A16": 2.0}), agg, two_stage=True)
    equal = pool_votes("AAA", votes_from_predictions(six, 20), agg, two_stage=True)
    assert heavy.p_up < equal.p_up  # with 6 voters, extra weight on the bearish A16 counts
    flat = pool_votes("AAA", votes, agg, two_stage=False)
    assert set(flat.agent_weights.values()) == {0.25}  # the stand-in ignores weights
    strong = pool_votes("AAA", [Vote("A11", 3, 0.7), Vote("A16", 4, 0.7)], agg, two_stage=True)
    base = go_decision(
        strong, sigma_daily=0.02, agg=agg, costs=cfg.costs, phase=4, p_no_trade=0.1, blocks=()
    )
    higher = go_decision(
        strong,
        sigma_daily=0.02,
        agg=agg,
        costs=cfg.costs,
        phase=4,
        p_no_trade=0.1,
        blocks=(),
        round_trip_cost=0.02,
    )
    lower = go_decision(
        strong,
        sigma_daily=0.02,
        agg=agg,
        costs=cfg.costs,
        phase=4,
        p_no_trade=0.1,
        blocks=(),
        round_trip_cost=0.0,
    )
    assert higher.net_edge == pytest.approx(base.net_edge - (0.02 - cfg.costs.round_trip_cost))
    assert lower.net_edge == base.net_edge  # a lower estimate never lowers the hurdle
