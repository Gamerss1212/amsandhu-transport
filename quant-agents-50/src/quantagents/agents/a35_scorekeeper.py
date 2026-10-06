"""A35 Scorekeeper & Calibration Agent (Team 7, Phase 4). Spec sections 16, 17, 67-69.

The permanent performance memory of the system:
1. Learn (step 15): every sealed prediction is stored with its date, its regime and whether
   the agent was voting. A35 never sees live inputs, only predictions and later prices.
2. Score (step 6): once a prediction's horizon has passed, its outcome is filled in from the
   closing prices (1 = price ended higher). Only prices up to today are used.
3. Scorecards: Brier score, climatology baseline and Brier skill, log loss, hit rate,
   reliability table, Brier by regime, and readiness for promotion (the owner still decides).
   Noise guard: a forecast made every day for 20 days ahead overlaps the next 19, so 500 such
   predictions hold only about 25 independent outcomes; and same-day forecasts on symbols
   that move together share their outcome. Every sample size below is the EFFECTIVE number
   of outcomes (see ``effective_n``), never the raw count.
   Skill t-stat: is Brier skill above zero by more than noise? (paired Brier differences
   vs the base rate, standard error from the effective sample size)
4. Calibration: temperature scaling p' = sigmoid(a x logit(p)) with 0 <= a <= 1, fitted on
   matured predictions and shrunk toward 1 (no change) with 30 effective pseudo-outcomes.
   It can only make an agent LESS sure of itself, never more, so it cannot create an edge.
5. Weights: 1 + 10 x shrunken Brier skill, between 0.25 and 2, after 15 effective outcomes.
   A47 then shrinks them toward equal and caps each agent at 25%. With 4 or fewer voters
   that cap can only be met by equal weights, so weights start to matter at 5+ voters
   (for example once the owner promotes A13 or A15 from shadow).
   Promotion review: 200+ scored, 30+ effective outcomes and skill t-stat of 2 or more.
6. N_eff: effective number of independent voters from how correlated their forecasts are.
7. Time discipline: every statistic uses only outcomes that were knowable on the cycle date
   (each record keeps the date its outcome settled), so days run out of order cannot leak.
Also scores the pooled forecast (A47's output), which is A35's own report card.
"""

from __future__ import annotations

import json
import math
from collections.abc import Iterable, Mapping, Sequence
from datetime import date
from itertools import pairwise
from pathlib import Path
from statistics import NormalDist
from typing import Any, ClassVar

import numpy as np

from quantagents.agents.base import Agent
from quantagents.aggregation import logit, n_eff_from_correlation, sigmoid
from quantagents.market import MarketView
from quantagents.regime_models import average_correlation
from quantagents.schemas import (
    AgentPrediction,
    AgentScorecard,
    Direction,
    Message,
    ReliabilityBin,
    ScoreSummary,
)

_NORMAL = NormalDist()
_P_EPS = 1e-6
BIN_EDGES: tuple[float, ...] = (0.5, 0.55, 0.6, 0.65, 1.0)  # on max(p, 1 - p)


class PredictionRecord(Message):
    """One stored prediction and, once matured, its outcome."""

    prediction: AgentPrediction
    as_of: date
    voting: bool
    regime: str = "unknown"
    outcome: int | None = None  # 1 = the close rose over the horizon, 0 = it did not
    realized_return: float | None = None
    matured_on: date | None = None  # the date whose close settled the outcome


def record_key(as_of: date, agent_id: str, symbol: str) -> str:
    """One record per agent, symbol and day: re-running a day replaces, never duplicates."""
    return f"{as_of.isoformat()}:{agent_id}:{symbol}"


class PooledRecord(Message):
    """A47's pooled P(up) for one symbol and day, on the decision horizon."""

    key: str
    symbol: str
    as_of: date
    horizon_bars: int
    p_up: float
    outcome: int | None = None
    realized_return: float | None = None
    matured_on: date | None = None


def known_by(outcome: int | None, matured_on: date | None, cutoff: date | None) -> bool:
    """True when an outcome exists AND was knowable on ``cutoff`` (None = no cutoff)."""
    if outcome is None or matured_on is None:
        return False
    return cutoff is None or matured_on <= cutoff


def brier(p: Sequence[float], o: Sequence[int]) -> float:
    return float(np.mean((np.asarray(p) - np.asarray(o)) ** 2))


def log_loss(p: Sequence[float], o: Sequence[int]) -> float:
    q = np.clip(np.asarray(p, dtype=np.float64), _P_EPS, 1.0 - _P_EPS)
    y = np.asarray(o, dtype=np.float64)
    return float(-np.mean(y * np.log(q) + (1.0 - y) * np.log(1.0 - q)))


def brier_skill(p: Sequence[float], o: Sequence[int]) -> tuple[float, float | None]:
    """(climatology Brier, Brier skill). Skill is None when the outcomes never vary."""
    base = float(np.mean(o))
    clim = base * (1.0 - base)
    if clim <= 1e-12:
        return clim, None
    return clim, 1.0 - brier(p, o) / clim


def effective_n(
    horizons: Sequence[int], days: Sequence[date] | None = None, rho: float = 0.0
) -> float:
    """Independent outcomes in a set of overlapping forecasts.

    Over time: a forecast for h bars ahead counts as 1 / h (it overlaps the next h - 1).
    Across symbols: m same-day forecasts on symbols whose returns correlate by ``rho`` count
    as m / (1 + (m - 1) rho), the usual design effect. ``rho`` <= 0 is treated as 0.
    """
    if days is None:
        return float(sum(1.0 / h for h in horizons))
    weight: dict[date, float] = {}
    count: dict[date, int] = {}
    for h, d in zip(horizons, days, strict=True):
        weight[d] = weight.get(d, 0.0) + 1.0 / h
        count[d] = count.get(d, 0) + 1
    r = max(rho, 0.0)
    return float(sum(w / (1.0 + (count[d] - 1) * r) for d, w in weight.items()))


def skill_t_stat(p: Sequence[float], o: Sequence[int], eff: float) -> float | None:
    """t-stat that the forecasts beat the base rate (positive = better), using the paired
    per-forecast Brier differences and the effective sample size ``eff``."""
    if eff < 2 or len(p) < 2:
        return None
    y = np.asarray(o, dtype=np.float64)
    base = float(np.mean(y))
    diff = (base - y) ** 2 - (np.asarray(p) - y) ** 2  # > 0 when the forecast beats the base
    sd = float(np.std(diff, ddof=1))
    if sd <= 0:
        return None
    return float(np.mean(diff)) / (sd / math.sqrt(eff))


def fit_temperature(p: Sequence[float], o: Sequence[int], iterations: int = 80) -> float:
    """The a in [0, 1] that minimizes log loss of sigmoid(a x logit(p)) (golden-section search;
    the loss is convex in a)."""
    z = np.array([logit(x) for x in p])
    y = np.asarray(o, dtype=np.float64)

    def loss(a: float) -> float:
        q = np.clip(1.0 / (1.0 + np.exp(-a * z)), _P_EPS, 1.0 - _P_EPS)
        return float(-np.mean(y * np.log(q) + (1.0 - y) * np.log(1.0 - q)))

    lo, hi = 0.0, 1.0
    ratio = (math.sqrt(5.0) - 1.0) / 2.0
    x1, x2 = hi - ratio * (hi - lo), lo + ratio * (hi - lo)
    f1, f2 = loss(x1), loss(x2)
    for _ in range(iterations):
        if f1 <= f2:
            hi, x2, f2 = x2, x1, f1
            x1 = hi - ratio * (hi - lo)
            f1 = loss(x1)
        else:
            lo, x1, f1 = x1, x2, f2
            x2 = lo + ratio * (hi - lo)
            f2 = loss(x2)
    best = (lo + hi) / 2.0
    # The ends of the interval are candidates too (the minimum can sit exactly on 0 or 1).
    return min((best, 0.0, 1.0), key=loss)


def reliability(p: Sequence[float], o: Sequence[int]) -> tuple[ReliabilityBin, ...]:
    """Bucket by confidence max(p, 1-p); hit = the outcome went the predicted way."""
    conf = np.maximum(np.asarray(p), 1.0 - np.asarray(p))
    hit = np.where(np.asarray(p) > 0.5, np.asarray(o), 1 - np.asarray(o))
    bins = []
    for lo, hi in pairwise(BIN_EDGES):
        mask = (conf >= lo) & ((conf < hi) | (hi == 1.0))
        n = int(np.count_nonzero(mask))
        if n:
            bins.append(
                ReliabilityBin(
                    lower=lo,
                    upper=hi,
                    n=n,
                    mean_confidence=float(np.mean(conf[mask])),
                    hit_rate=float(np.mean(hit[mask])),
                )
            )
    return tuple(bins)


class Scorekeeper(Agent):
    agent_id = "A35"
    name = "Scorekeeper & Calibration Agent"
    kind = "stat"
    info_subset = ("sealed_predictions", "outcomes")

    min_calibration_eff: ClassVar[float] = 10.0  # effective outcomes before calibrating
    prior_strength: ClassVar[float] = 30.0  # effective pseudo-outcomes pulling toward "no change"
    min_weight_eff: ClassVar[float] = 15.0
    weight_prior: ClassVar[float] = 30.0
    weight_gain: ClassVar[float] = 10.0
    weight_bounds: ClassVar[tuple[float, float]] = (0.25, 2.0)
    promotion_n: ClassVar[int] = 200
    promotion_eff: ClassVar[float] = 30.0
    promotion_t: ClassVar[float] = 2.0
    min_overlap: ClassVar[int] = 30
    rho_prior: ClassVar[float] = 0.5  # cautious cross-symbol correlation until measured
    rho_prior_strength: ClassVar[float] = 10.0  # independent dates the prior is worth
    rho_min_independent: ClassVar[float] = 30.0  # below this, use max(prior, measured)
    min_regime_n: ClassVar[int] = 10
    max_records: ClassVar[int] = 50_000

    def __init__(
        self, records: Iterable[PredictionRecord] = (), pooled: Iterable[PooledRecord] = ()
    ) -> None:
        self.records: dict[str, PredictionRecord] = {}
        self.pooled: dict[str, PooledRecord] = {}
        for r in records:
            self.records[record_key(r.as_of, r.prediction.agent_id, r.prediction.symbol)] = r
        for q in pooled:
            self.pooled[q.key] = q

    # ---- step 15: learn -------------------------------------------------------------------
    def record(
        self,
        predictions: Sequence[AgentPrediction],
        *,
        as_of: date,
        voters: set[str],
        regimes: Mapping[str, str] | None = None,
    ) -> int:
        """Store sealed predictions (raw, before calibration). Returns how many were stored.

        A day that is run again (for example after a data fix) replaces that day's record
        instead of adding a second copy of the same outcome.
        """
        added = 0
        for p in predictions:
            key = record_key(as_of, p.agent_id, p.symbol)
            existing = self.records.get(key)
            if existing is not None and existing.prediction.prediction_id == p.prediction_id:
                continue
            self.records[key] = PredictionRecord(
                prediction=p,
                as_of=as_of,
                voting=p.agent_id in voters,
                regime=(regimes or {}).get(p.symbol, "unknown"),
            )
            added += 1
        self._trim()
        return added

    def record_pooled(self, symbol: str, as_of: date, p_up: float, horizon: int) -> None:
        key = f"{as_of.isoformat()}:{symbol}"
        existing = self.pooled.get(key)
        if existing is None or existing.p_up != p_up or existing.horizon_bars != horizon:
            self.pooled[key] = PooledRecord(
                key=key, symbol=symbol, as_of=as_of, horizon_bars=horizon, p_up=p_up
            )

    def _trim(self) -> None:
        if len(self.records) > self.max_records:
            ordered = sorted(self.records.values(), key=lambda r: r.as_of)
            keep = ordered[-self.max_records :]
            self.records = {
                record_key(r.as_of, r.prediction.agent_id, r.prediction.symbol): r for r in keep
            }

    # ---- step 6: score --------------------------------------------------------------------
    def score_matured(self, view: MarketView) -> int:
        """Fill in outcomes whose horizon has passed by the view's as-of date. Returns the
        number newly scored. Only closes up to the as-of date are read."""
        index = {d: i for i, d in enumerate(view.dates)}
        last = len(view) - 1
        closes: dict[str, np.ndarray[Any, np.dtype[np.float64]]] = {}

        dates = view.dates

        def outcome(symbol: str, day: date, horizon: int) -> dict[str, Any] | None:
            i = index.get(day)
            if i is None or i + horizon > last or symbol not in view.symbols:
                return None
            if symbol not in closes:
                closes[symbol] = np.asarray(view.close(symbol), dtype=np.float64)
            start, end = float(closes[symbol][i]), float(closes[symbol][i + horizon])
            if not (math.isfinite(start) and math.isfinite(end) and start > 0):
                return None
            ret = end / start - 1.0
            return {
                "outcome": 1 if ret > 0 else 0,
                "realized_return": ret,
                "matured_on": dates[i + horizon],
            }

        scored = 0
        for key, r in list(self.records.items()):
            # Records saved before outcomes carried a settle date are scored again, so an
            # older memory file can never silently lose its history (or its calibration).
            if r.prediction.abstain or (r.outcome is not None and r.matured_on is not None):
                continue
            result = outcome(r.prediction.symbol, r.as_of, r.prediction.horizon_bars)
            if result is not None:
                self.records[key] = r.model_copy(update=result)
                scored += 1
        for key, q in list(self.pooled.items()):
            if q.outcome is None or q.matured_on is None:
                result = outcome(q.symbol, q.as_of, q.horizon_bars)
                if result is not None:
                    self.pooled[key] = q.model_copy(update=result)
        return scored

    # ---- scorecards -----------------------------------------------------------------------
    def outcome_correlation(self, cutoff: date | None = None) -> float:
        """How much the symbols' outcomes move together (0-1), for discounting same-day
        forecasts. Until 30 independent dates exist it is the larger of a cautious 0.5 and
        the measured average correlation of matured decision-horizon returns; after that it
        blends toward the measurement. Negative values count as 0."""
        table: dict[date, dict[str, float]] = {}
        horizon = 1
        for q in self.pooled.values():
            if q.realized_return is not None and known_by(q.outcome, q.matured_on, cutoff):
                table.setdefault(q.as_of, {})[q.symbol] = q.realized_return
                horizon = max(horizon, q.horizon_bars)
        symbols = sorted({s for row in table.values() for s in row})
        prior = self.rho_prior
        if len(symbols) < 2 or len(table) < 10:
            return prior
        matrix = np.array(
            [[row.get(s, math.nan) for s in symbols] for _, row in sorted(table.items())]
        )
        measured = average_correlation(matrix)
        if not math.isfinite(measured):
            return prior
        measured = min(1.0, max(measured, 0.0))
        independent = len(table) / horizon  # overlapping windows share most of their move
        if independent < self.rho_min_independent:
            return max(prior, measured)  # too little data: never less cautious than the prior
        weight = independent / (independent + self.rho_prior_strength)
        return weight * measured + (1.0 - weight) * prior

    def scorecard(
        self, agent_id: str, state: str, rho: float | None = None, cutoff: date | None = None
    ) -> AgentScorecard:
        """Scorecard from outcomes that were knowable on ``cutoff`` (None = everything)."""
        rho = self.rho_prior if rho is None else rho
        mine = [
            r
            for r in self.records.values()
            if r.prediction.agent_id == agent_id and (cutoff is None or r.as_of <= cutoff)
        ]
        abstained = sum(r.prediction.abstain for r in mine)
        done = [
            r
            for r in mine
            if not r.prediction.abstain and known_by(r.outcome, r.matured_on, cutoff)
        ]
        pending = sum(1 for r in mine if not r.prediction.abstain) - len(done)
        if not done:
            return AgentScorecard(
                agent_id=agent_id,
                state=state,
                n_scored=0,
                n_abstained=abstained,
                n_pending=pending,
            )
        p = [r.prediction.p_up for r in done]
        o = [int(r.outcome) for r in done if r.outcome is not None]
        clim, skill = brier_skill(p, o)
        n = len(done)
        eff = effective_n([r.prediction.horizon_bars for r in done], [r.as_of for r in done], rho)
        t_stat = skill_t_stat(p, o, eff)
        temperature = 1.0
        if eff >= self.min_calibration_eff:
            fitted = fit_temperature(p, o)
            temperature = (eff * fitted + self.prior_strength) / (eff + self.prior_strength)
        weight = 1.0
        if eff >= self.min_weight_eff and skill is not None:
            low, high = self.weight_bounds
            shrunk = skill * eff / (eff + self.weight_prior)
            weight = min(high, max(low, 1.0 + self.weight_gain * shrunk))
        regimes: dict[str, list[int]] = {}
        for i, r in enumerate(done):
            regimes.setdefault(r.regime, []).append(i)
        by_regime = {
            label: brier([p[i] for i in idx], [o[i] for i in idx])
            for label, idx in sorted(regimes.items())
            if len(idx) >= self.min_regime_n
        }
        hits = [int((pi > 0.5) == bool(oi)) for pi, oi in zip(p, o, strict=True)]
        return AgentScorecard(
            agent_id=agent_id,
            state=state,
            n_scored=n,
            effective_n=eff,
            n_abstained=abstained,
            n_pending=pending,
            hit_rate=float(np.mean(hits)),
            brier=brier(p, o),
            brier_climatology=clim,
            brier_skill=skill,
            skill_t=t_stat,
            log_loss=log_loss(p, o),
            mean_confidence=float(np.mean([abs(x - 0.5) * 2.0 for x in p])),
            temperature=min(1.0, max(0.0, temperature)),
            weight=weight,
            promotion_ready=(
                n >= self.promotion_n
                and eff >= self.promotion_eff
                and t_stat is not None
                and t_stat >= self.promotion_t
            ),
            brier_by_regime=by_regime,
            bins=reliability(p, o),
        )

    def n_eff(self, agent_ids: Sequence[str], cutoff: date | None = None) -> float | None:
        """Effective number of independent voters from how alike their forecasts are.

        Correlates each pair's log-odds on the (day, symbol) pairs both forecast. Errors are
        not used: forecasts sit near 50%, so every agent's error is mostly the shared
        outcome and the errors would look ~100% correlated whatever the agents do.
        A pair that cannot be measured (a constant forecaster) counts as fully redundant.
        None when any pair has fewer than ``min_overlap`` shared forecasts (A47 then uses
        its stand-in, the number of teams present).
        """
        views: dict[str, dict[tuple[date, str], float]] = {a: {} for a in agent_ids}
        for r in self.records.values():
            a = r.prediction.agent_id
            if a in views and not r.prediction.abstain and (cutoff is None or r.as_of <= cutoff):
                views[a][(r.as_of, r.prediction.symbol)] = logit(r.prediction.p_up)
        ids = sorted(agent_ids)
        if len(ids) < 2:
            return None
        k = len(ids)
        corr = np.eye(k)
        for i in range(k):
            for j in range(i + 1, k):
                shared = sorted(set(views[ids[i]]) & set(views[ids[j]]))
                if len(shared) < self.min_overlap:
                    return None
                x = np.array([views[ids[i]][s] for s in shared])
                y = np.array([views[ids[j]][s] for s in shared])
                if np.std(x) < 1e-12 or np.std(y) < 1e-12:
                    value = 1.0
                else:
                    value = float(np.corrcoef(x, y)[0, 1])
                corr[i, j] = corr[j, i] = value
        return n_eff_from_correlation(corr)

    def summary(
        self, as_of: date, states: Mapping[str, str], voters: Sequence[str] = ()
    ) -> ScoreSummary:
        """Everything A35 knows as of the close of ``as_of``, and nothing it learned later
        (so running an earlier day after a later one can never use future outcomes)."""
        visible = [r for r in self.records.values() if r.as_of <= as_of]
        agents = sorted({r.prediction.agent_id for r in visible} | set(states))
        rho = self.outcome_correlation(as_of)
        cards = tuple(self.scorecard(a, states.get(a, "unknown"), rho, as_of) for a in agents)
        pooled_done = [q for q in self.pooled.values() if known_by(q.outcome, q.matured_on, as_of)]
        pooled_brier = pooled_skill = None
        if pooled_done:
            pp = [q.p_up for q in pooled_done]
            po = [int(q.outcome) for q in pooled_done if q.outcome is not None]
            pooled_brier = brier(pp, po)
            pooled_skill = brier_skill(pp, po)[1]
        scored = sum(known_by(r.outcome, r.matured_on, as_of) for r in visible)
        pending = sum(not r.prediction.abstain for r in visible) - scored
        notes = []
        if scored == 0:
            notes.append("no prediction has matured yet: calibration and weights stay neutral")
        ready = [c.agent_id for c in cards if c.promotion_ready and c.state == "shadow"]
        if ready:
            notes.append(f"ready for an owner promotion review: {', '.join(ready)}")
        return ScoreSummary(
            as_of=as_of,
            n_records=len(visible),
            n_scored=scored,
            n_pending=pending,
            cards=cards,
            pooled_n=len(pooled_done),
            pooled_brier=pooled_brier,
            pooled_brier_skill=pooled_skill,
            n_eff=self.n_eff(list(voters), as_of) if voters else None,
            rho=rho,
            notes=tuple(notes),
        )

    # ---- step 6: calibrate ----------------------------------------------------------------
    @staticmethod
    def calibrate(
        predictions: Sequence[AgentPrediction], summary: ScoreSummary
    ) -> list[AgentPrediction]:
        """Apply each agent's temperature. Direction never flips; at a = 0 a vote becomes an
        abstention. Builds validated copies (the sealed originals are never changed)."""
        out: list[AgentPrediction] = []
        for p in predictions:
            card = summary.card(p.agent_id)
            if p.abstain or card is None or card.temperature >= 1.0:
                out.append(p)
                continue
            q = sigmoid(card.temperature * logit(p.p_up))
            data = p.model_dump()
            note = f" [A35 calibrated {p.p_up:.3f}->{q:.3f}]"
            if abs(q - 0.5) < 1e-9:
                data.update(
                    abstain=True,
                    direction=Direction.FLAT,
                    p_up=0.5,
                    confidence=0.0,
                    exp_return=0.0,
                )
            else:
                data.update(
                    p_up=q,
                    confidence=min(1.0, abs(q - 0.5) * 2.0),
                    exp_return=p.exp_vol * _NORMAL.inv_cdf(q) if p.exp_vol > 0 else 0.0,
                )
            data["reasoning_summary"] = (p.reasoning_summary + note)[:500]
            out.append(AgentPrediction.model_validate(data))
        return out

    @staticmethod
    def weights(summary: ScoreSummary) -> dict[str, float]:
        return {c.agent_id: c.weight for c in summary.cards}

    # ---- persistence ----------------------------------------------------------------------
    def to_json(self) -> dict[str, Any]:
        return {
            "records": [r.model_dump(mode="json") for r in self.records.values()],
            "pooled": [q.model_dump(mode="json") for q in self.pooled.values()],
        }

    @classmethod
    def from_json(cls, data: Mapping[str, Any]) -> Scorekeeper:
        return cls(
            (PredictionRecord.model_validate(r) for r in data.get("records", [])),
            (PooledRecord.model_validate(q) for q in data.get("pooled", [])),
        )

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps(self.to_json()), encoding="utf-8")
        tmp.replace(path)

    @classmethod
    def load_or_new(cls, path: Path) -> Scorekeeper:
        if path.exists():
            return cls.from_json(json.loads(path.read_text(encoding="utf-8")))
        return cls()
