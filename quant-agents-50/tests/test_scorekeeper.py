"""A35 Scorekeeper & Calibration Agent."""

from __future__ import annotations

import math
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pytest

from quantagents.agents.a35_scorekeeper import (
    PredictionRecord,
    Scorekeeper,
    brier,
    effective_n,
    fit_temperature,
    known_by,
    log_loss,
    record_key,
    reliability,
    skill_t_stat,
)
from quantagents.schemas import Direction
from tests.helpers import path_market, prediction

DAY0 = date(2024, 1, 1)
LAST = DAY0 + timedelta(days=20_000)  # a cutoff after every test record has settled


def record(
    agent: str,
    p_up: float,
    outcome: int | None,
    *,
    day: int = 0,
    symbol: str = "AAA",
    horizon: int = 1,
    voting: bool = True,
    regime: str = "unknown",
) -> PredictionRecord:
    as_of = DAY0 + timedelta(days=day)
    return PredictionRecord(
        prediction=prediction(agent, symbol, p_up, horizon=horizon, cycle_id=f"C{day}"),
        as_of=as_of,
        voting=voting,
        regime=regime,
        outcome=outcome,
        realized_return=None if outcome is None else (0.01 if outcome else -0.01),
        matured_on=None if outcome is None else as_of + timedelta(days=horizon),
    )


def overconfident(agent: str, n: int, seed: int, shrink: float = 0.5) -> list[PredictionRecord]:
    """An agent whose true hit probability is only ``shrink`` of what it claims."""
    rng = np.random.default_rng(seed)
    out = []
    for i in range(n):
        claim = float(rng.choice([0.35, 0.4, 0.6, 0.65]))
        truth = 0.5 + shrink * (claim - 0.5)
        out.append(record(agent, claim, int(rng.random() < truth), day=i))
    return out


def test_predictions_are_scored_only_after_their_horizon() -> None:
    market = path_market([100.0 + i for i in range(40)])
    keeper = Scorekeeper()
    day = market.dates[20]
    stored = keeper.record(
        [prediction("A11", "AAA", 0.6, horizon=5), prediction("A16", "AAA", 0.5, abstain=True)],
        as_of=day,
        voters={"A11"},
        regimes={"AAA": "trending_up"},
    )
    assert stored == 2
    assert keeper.record([prediction("A11", "AAA", 0.6, horizon=5)], as_of=day, voters=set()) == 0
    assert keeper.score_matured(market.view(market.dates[24])) == 0  # 4 bars later: not yet
    assert keeper.score_matured(market.view(market.dates[25])) == 1
    r = keeper.records[record_key(day, "A11", "AAA")]
    assert r.outcome == 1 and r.realized_return == pytest.approx(125 / 120 - 1)
    assert r.voting and r.regime == "trending_up" and r.matured_on == market.dates[25]
    assert keeper.records[record_key(day, "A16", "AAA")].outcome is None  # abstentions: never
    assert keeper.score_matured(market.view(market.dates[-1])) == 0  # never scored twice


def test_unscorable_predictions_stay_pending() -> None:
    market = path_market([100.0] * 30)
    keeper = Scorekeeper()
    keeper.record([prediction("A11", "AAA", 0.6, horizon=1)], as_of=date(2001, 1, 1), voters=set())
    keeper.record(
        [prediction("A11", "ZZZ", 0.6, horizon=1, cycle_id="C2")],
        as_of=market.dates[3],
        voters=set(),
    )
    assert keeper.score_matured(market.view(market.dates[-1])) == 0
    flat = keeper.summary(market.dates[-1], {"A11": "active"})
    assert flat.n_pending == 2 and flat.n_scored == 0 and flat.notes


def test_flat_prices_count_as_not_up() -> None:
    market = path_market([100.0] * 30)
    keeper = Scorekeeper()
    keeper.record([prediction("A11", "AAA", 0.6, horizon=2)], as_of=market.dates[5], voters=set())
    keeper.score_matured(market.view(market.dates[-1]))
    assert keeper.records[record_key(market.dates[5], "A11", "AAA")].outcome == 0


def test_effective_sample_size() -> None:
    assert effective_n([20] * 40) == pytest.approx(2.0)
    days = [DAY0] * 6
    assert effective_n([1] * 6, days, rho=1.0) == pytest.approx(1.0)
    assert effective_n([1] * 6, days, rho=0.0) == pytest.approx(6.0)
    assert effective_n([1] * 6, days, rho=-0.5) == pytest.approx(6.0)


def test_skill_t_stat() -> None:
    o = [1, 0] * 50
    assert skill_t_stat([0.9, 0.1] * 50, o, 100) is None  # perfect forecasts: zero spread
    good = skill_t_stat([0.7, 0.3] * 50, o, 100)
    bad = skill_t_stat([0.3, 0.7] * 50, o, 100)
    assert good is not None and good > 2 and bad is not None and bad < -2
    assert skill_t_stat([0.6], [1], 1) is None
    assert skill_t_stat([0.6, 0.6, 0.6], [1, 1, 1], 3) is None  # outcomes never vary


def test_basic_scores() -> None:
    assert brier([1.0, 0.0], [1, 0]) == 0.0
    assert log_loss([0.5, 0.5], [1, 0]) == pytest.approx(math.log(2))
    bins = reliability([0.52, 0.58, 0.7, 0.3], [1, 1, 0, 1])
    assert [b.n for b in bins] == [1, 1, 2]
    assert bins[-1].hit_rate == 0.0  # both 70% calls were wrong


def test_temperature_recovers_overconfidence_and_never_exceeds_one() -> None:
    claims = [r.prediction.p_up for r in overconfident("A11", 6000, seed=1)]
    outcomes = [r.outcome or 0 for r in overconfident("A11", 6000, seed=1)]
    a = fit_temperature(claims, outcomes)
    assert 0.35 < a < 0.65
    honest = overconfident("A11", 6000, seed=2, shrink=1.0)
    a = fit_temperature([r.prediction.p_up for r in honest], [r.outcome or 0 for r in honest])
    assert a == pytest.approx(1.0, abs=0.12) and a <= 1.0
    useless = overconfident("A11", 6000, seed=3, shrink=0.0)
    a = fit_temperature([r.prediction.p_up for r in useless], [r.outcome or 0 for r in useless])
    assert a < 0.15


def test_scorecard_noise_guards() -> None:
    few = Scorekeeper(overconfident("A11", 8, seed=4, shrink=0.0))
    card = few.scorecard("A11", "active")
    assert card.temperature == 1.0 and card.weight == 1.0  # not enough evidence to act on
    many = Scorekeeper(overconfident("A11", 3000, seed=4, shrink=0.0))
    card = many.scorecard("A11", "active")
    assert card.n_scored == 3000 and card.effective_n == pytest.approx(3000)
    assert card.temperature < 0.2 and card.weight < 1.0
    assert card.brier_skill is not None and card.brier_skill < 0
    overlapping = Scorekeeper(
        [r.model_copy(update={"prediction": r.prediction.model_copy(update={"horizon_bars": 20})})
         for r in overconfident("A11", 300, seed=4, shrink=0.0)]
    )  # fmt: skip
    card = overlapping.scorecard("A11", "active")
    assert card.effective_n == pytest.approx(15) and card.temperature > 0.5  # 300 overlapping


def test_regimes_and_bins_in_scorecard() -> None:
    records = [
        record("A16", 0.6, i % 2, day=i, regime="ranging" if i < 20 else "trending_up")
        for i in range(40)
    ]
    card = Scorekeeper(records).scorecard("A16", "active")
    assert set(card.brier_by_regime) == {"ranging", "trending_up"}
    assert card.bins and card.hit_rate == pytest.approx(0.5)
    empty = Scorekeeper().scorecard("A16", "active")
    assert empty.n_scored == 0 and empty.brier is None


def test_calibration_tempers_but_never_flips() -> None:
    keeper = Scorekeeper(overconfident("A11", 3000, seed=5, shrink=0.0))
    summary = keeper.summary(LAST, {"A11": "active", "A12": "active"})
    raw = [
        prediction("A11", "AAA", 0.62),
        prediction("A11", "BBB", 0.4),
        prediction("A11", "CCC", abstain=True),
        prediction("A12", "AAA", 0.6),  # no matured history: unchanged
    ]
    calibrated = keeper.calibrate(raw, summary)
    assert 0.5 < calibrated[0].p_up < 0.62 and calibrated[0].direction is Direction.LONG
    assert 0.4 < calibrated[1].p_up < 0.5 and calibrated[1].direction is Direction.SHORT
    assert calibrated[2] == raw[2] and calibrated[3] == raw[3]
    assert "A35 calibrated" in calibrated[0].reasoning_summary
    frozen = summary.model_copy(
        update={"cards": tuple(c.model_copy(update={"temperature": 0.0}) for c in summary.cards)}
    )
    zeroed = keeper.calibrate(raw[:1], frozen)[0]
    assert zeroed.abstain and zeroed.p_up == 0.5 and zeroed.direction is Direction.FLAT


def test_promotion_needs_real_skill() -> None:
    rng = np.random.default_rng(6)
    skilled = []
    for i in range(400):
        claim = float(rng.choice([0.4, 0.6]))
        skilled.append(record("A13", claim, int(rng.random() < claim), day=i, voting=False))
    keeper = Scorekeeper(skilled + overconfident("A15", 400, seed=7, shrink=0.0))
    summary = keeper.summary(LAST, {"A13": "shadow", "A15": "shadow"})
    a13, a15 = summary.card("A13"), summary.card("A15")
    assert a13 is not None and a13.promotion_ready and (a13.skill_t or 0) >= 2
    assert a15 is not None and not a15.promotion_ready
    assert any("A13" in note and "promotion" in note for note in summary.notes)
    assert summary.card("A99") is None


def forecasts(agent: str, n: int, seed: int) -> list[PredictionRecord]:
    rng = np.random.default_rng(seed)
    return [record(agent, float(rng.uniform(0.3, 0.7)), None, day=i) for i in range(n)]


def test_n_eff_from_forecast_correlation() -> None:
    a = forecasts("A11", 200, seed=8)
    same = [r.model_copy(update={"prediction": r.prediction.model_copy(update={"agent_id": "A12"})}) for r in a]  # fmt: skip
    other = forecasts("A16", 200, seed=9)
    third = forecasts("A23", 200, seed=10)
    assert Scorekeeper(a + same).n_eff(["A11", "A12"]) == pytest.approx(1.0, abs=0.05)
    # Independent views count as independent (with errors they would look ~100% alike).
    assert Scorekeeper(a + other).n_eff(["A11", "A16"]) == pytest.approx(2.0, abs=0.2)
    assert Scorekeeper(a + other + third).n_eff(["A11", "A16", "A23"]) == pytest.approx(
        3.0, abs=0.3
    )
    assert Scorekeeper(a[:10] + other[:10]).n_eff(["A11", "A16"]) is None  # too little overlap
    assert Scorekeeper(a).n_eff(["A11"]) is None
    shifted = [r.model_copy(update={"as_of": r.as_of + timedelta(days=1000)}) for r in other]
    assert Scorekeeper(a + shifted).n_eff(["A11", "A16"]) is None  # no shared days
    flat = [record("A23", 0.55, None, day=i) for i in range(200)]
    assert Scorekeeper(a + flat).n_eff(["A11", "A23"]) == pytest.approx(1.0)  # cautious
    assert Scorekeeper(a + other).n_eff(["A11", "A16"], cutoff=DAY0 + timedelta(days=20)) is None


def test_pooled_scoring_and_outcome_correlation() -> None:
    market = path_market([100.0 + i for i in range(60)])
    keeper = Scorekeeper()
    for i in range(10, 40):
        keeper.record_pooled("AAA", market.dates[i], 0.6, horizon=5)
    keeper.record_pooled("AAA", market.dates[10], 0.6, horizon=5)  # same again: ignored
    keeper.score_matured(market.view(market.dates[-1]))
    summary = keeper.summary(market.dates[-1], {})
    assert summary.pooled_n == 30 and summary.pooled_brier == pytest.approx(0.16)
    assert summary.pooled_brier_skill is None  # prices only rose: no base-rate variance
    assert keeper.outcome_correlation() == 0.5  # one symbol: the cautious prior
    keeper.record_pooled("AAA", market.dates[10], 0.9, horizon=5)  # a re-run day replaces it
    assert keeper.pooled[f"{market.dates[10].isoformat()}:AAA"].outcome is None


def test_persistence_and_trimming(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    keeper = Scorekeeper(overconfident("A11", 50, seed=10))
    keeper.record_pooled("AAA", DAY0, 0.55, 20)
    path = tmp_path / "scores.json"
    keeper.save(path)
    again = Scorekeeper.load_or_new(path)
    assert again.records == keeper.records and again.pooled == keeper.pooled
    assert Scorekeeper.load_or_new(tmp_path / "missing.json").records == {}
    monkeypatch.setattr(Scorekeeper, "max_records", 10)
    keeper.record(
        [prediction("A12", "AAA", 0.6, cycle_id="NEW")],
        as_of=DAY0 + timedelta(days=999),
        voters=set(),
    )
    assert len(keeper.records) == 10
    assert record_key(DAY0 + timedelta(days=999), "A12", "AAA") in keeper.records
    assert Scorekeeper.weights(keeper.summary(LAST, {}))


def test_missing_closing_price_keeps_a_prediction_pending() -> None:
    closes = [100.0 + i for i in range(30)]
    closes[12] = float("nan")
    market = path_market(closes)
    keeper = Scorekeeper()
    keeper.record([prediction("A11", "AAA", 0.6, horizon=2)], as_of=market.dates[10], voters=set())
    assert keeper.score_matured(market.view(market.dates[-1])) == 0
    assert keeper.records[record_key(market.dates[10], "A11", "AAA")].outcome is None


def test_days_run_out_of_order_never_see_later_outcomes() -> None:
    rng = np.random.default_rng(11)
    market = path_market(list(100 * np.exp(np.cumsum(rng.normal(0, 0.01, 420)))))
    keeper = Scorekeeper()
    for i in range(400):
        p = float(rng.choice([0.35, 0.65]))
        keeper.record(
            [prediction("A11", "AAA", p, horizon=5, cycle_id=f"C{i}")],
            as_of=market.dates[i],
            voters={"A11"},
        )
    keeper.score_matured(market.view(market.dates[-1]))  # outcomes known up to the end
    early = keeper.summary(market.dates[210], {"A11": "active"})
    card = early.card("A11")
    assert card is not None and card.n_scored == 206  # days 0-205 had settled by day 210
    assert early.n_records == 211 and early.n_pending == 5
    late = keeper.summary(market.dates[-1], {"A11": "active"})
    assert late.n_scored == 400
    assert known_by(1, market.dates[5], market.dates[5]) and not known_by(1, None, None)


def test_rerunning_a_day_replaces_instead_of_double_counting() -> None:
    keeper = Scorekeeper()
    day = DAY0
    assert (
        keeper.record([prediction("A11", "AAA", 0.6, cycle_id="C-old")], as_of=day, voters=set())
        == 1
    )
    assert (
        keeper.record([prediction("A11", "AAA", 0.62, cycle_id="C-new")], as_of=day, voters=set())
        == 1
    )
    assert len(keeper.records) == 1
    assert keeper.records[record_key(day, "A11", "AAA")].prediction.p_up == 0.62


def test_cross_symbol_discount_is_cautious_until_measured() -> None:
    keeper = Scorekeeper()
    assert keeper.outcome_correlation() == 0.5
    six_same_day = effective_n([1] * 6, [DAY0] * 6, rho=keeper.outcome_correlation())
    assert six_same_day == pytest.approx(6 / 3.5)


def test_old_memory_files_are_rescored_not_forgotten() -> None:
    market = path_market([100.0 + i for i in range(40)])
    keeper = Scorekeeper()
    keeper.record([prediction("A11", "AAA", 0.6, horizon=5)], as_of=market.dates[10], voters=set())
    keeper.score_matured(market.view(market.dates[-1]))
    key = record_key(market.dates[10], "A11", "AAA")
    legacy = keeper.records[key].model_copy(update={"matured_on": None})  # saved by v0.4 code
    old = Scorekeeper([legacy])
    assert old.summary(market.dates[-1], {}).n_scored == 0
    assert old.score_matured(market.view(market.dates[-1])) == 1
    assert old.records[key].matured_on == market.dates[15]
    assert old.summary(market.dates[-1], {}).n_scored == 1


def test_measured_correlation_above_the_prior_is_used_early() -> None:
    rng = np.random.default_rng(12)
    keeper = Scorekeeper()
    for i in range(15):  # 15 dates: far fewer than 30 independent ones
        common = rng.normal()
        for symbol in ("AAA", "BBB", "CCC"):
            day = DAY0 + timedelta(days=i)
            keeper.record_pooled(symbol, day, 0.55, horizon=1)
            key = f"{day.isoformat()}:{symbol}"
            ret = 0.01 * (common + 0.3 * rng.normal())
            keeper.pooled[key] = keeper.pooled[key].model_copy(
                update={"outcome": int(ret > 0), "realized_return": ret, "matured_on": day}
            )
    assert keeper.outcome_correlation() > 0.8  # strongly co-moving symbols are not discounted less
