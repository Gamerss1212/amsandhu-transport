"""Pooling and GO rules (spec section 13). Deterministic code; every number comes from config.

Two-stage log-odds pooling: pool inside each team, then across teams, so five similar
agents in one team cannot outvote a team with different information.
"""

from __future__ import annotations

import math
from collections.abc import Hashable, Mapping, Sequence
from dataclasses import dataclass, field
from statistics import NormalDist
from typing import TypeVar

import numpy as np
import numpy.typing as npt

from quantagents.config import AggregationConfig, CostConfig
from quantagents.schemas import AgentPrediction, Direction

K = TypeVar("K", bound=Hashable)

_NORMAL = NormalDist()
_EPS = 1e-6


def clamp_probability(p: float) -> float:
    return min(max(p, _EPS), 1.0 - _EPS)


def logit(p: float) -> float:
    q = clamp_probability(p)
    return math.log(q / (1.0 - q))


def sigmoid(x: float) -> float:
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-x))
    z = math.exp(x)
    return z / (1.0 + z)


def harmonize(p_up: float, horizon: int, target: int) -> float:
    """Restate a forecast made for ``horizon`` bars on the ``target`` horizon.

    Normal model: the edge is earned within the shorter of the two horizons while noise grows
    with the square root of time, so z_target = z * sqrt(min(h, H) / max(h, H)).
    """
    if horizon < 1 or target < 1:
        raise ValueError("horizons must be >= 1")
    z = _NORMAL.inv_cdf(clamp_probability(p_up))
    return _NORMAL.cdf(z * math.sqrt(min(horizon, target) / max(horizon, target)))


def normalize(weights: Mapping[K, float]) -> dict[K, float]:
    if not weights:
        raise ValueError("no weights")
    if any(w < 0 or not math.isfinite(w) for w in weights.values()):
        raise ValueError("weights must be finite and non-negative")
    total = sum(weights.values())
    if total <= 0:
        raise ValueError("weights must have a positive sum")
    return {k: w / total for k, w in weights.items()}


def shrink_to_equal(weights: Mapping[K, float], amount: float) -> dict[K, float]:
    """Blend normalized weights with equal weights: (1 - amount) * w + amount / n."""
    if not 0.0 <= amount <= 1.0:
        raise ValueError("amount must be in [0, 1]")
    w = normalize(weights)
    n = len(w)
    return {k: (1.0 - amount) * v + amount / n for k, v in w.items()}


def waterfill(weights: Mapping[K, float], cap: float) -> dict[K, float]:
    """Cap each weight at ``cap`` and hand the excess to uncapped names pro rata.

    If the cap is infeasible (n * cap < 1) the only fair answer is equal weights.
    """
    if cap <= 0:
        raise ValueError("cap must be positive")
    w = normalize(weights)
    n = len(w)
    if n * cap < 1.0 - 1e-12:
        return dict.fromkeys(w, 1.0 / n)
    capped: list[K] = []
    free = dict(w)
    while True:
        remaining = 1.0 - cap * len(capped)
        total_free = sum(free.values())
        if total_free <= 0:
            scaled = {k: remaining / len(free) for k in free}
        else:
            scaled = {k: v / total_free * remaining for k, v in free.items()}
        over = [k for k, v in scaled.items() if v > cap + 1e-12]
        if not over:
            result = dict.fromkeys(capped, cap)
            result.update(scaled)
            return {k: result[k] for k in w}
        for k in over:
            capped.append(k)
            del free[k]


def n_eff_from_correlation(corr: npt.ArrayLike) -> float:
    """Effective number of independent agents: (sum of eigenvalues)^2 / sum of squares."""
    m = np.asarray(corr, dtype=np.float64)
    if m.ndim != 2 or m.shape[0] != m.shape[1] or m.shape[0] == 0:
        raise ValueError("need a non-empty square matrix")
    if not np.allclose(m, m.T, atol=1e-10):
        raise ValueError("correlation matrix must be symmetric")
    eig = np.clip(np.linalg.eigvalsh(m), 0.0, None)
    sq = float(np.sum(eig**2))
    return float(np.sum(eig)) ** 2 / sq if sq > 0 else 0.0


@dataclass(frozen=True)
class Vote:
    agent_id: str
    team: int
    p_up: float  # already restated on the decision horizon
    weight: float = 1.0


@dataclass(frozen=True)
class PoolResult:
    symbol: str
    method: str
    p_up_raw: float
    p_up: float
    direction: Direction
    p_direction: float
    disagreement: float
    n_agents: int
    teams_present: int
    teams_agree: int
    n_eff: float
    team_logits: dict[int, float] = field(default_factory=dict)
    agent_weights: dict[str, float] = field(default_factory=dict)


def votes_from_predictions(
    predictions: Sequence[AgentPrediction],
    horizon: int,
    weights: Mapping[str, float] | None = None,
) -> list[Vote]:
    """Votes on the decision horizon. ``weights`` come from A35 (default 1 for everyone)."""
    w = weights or {}
    return [
        Vote(p.agent_id, p.team, harmonize(p.p_up, p.horizon_bars, horizon), w.get(p.agent_id, 1.0))
        for p in predictions
        if not p.abstain
    ]


def pool_votes(
    symbol: str,
    votes: Sequence[Vote],
    cfg: AggregationConfig,
    *,
    two_stage: bool,
    n_eff: float | None = None,
) -> PoolResult:
    """Pool votes into one probability. ``n_eff`` comes from A35's error-correlation matrix;
    until A35 exists, the number of teams present is used as a stand-in."""
    method = "two_stage" if two_stage else "equal_weight"
    if not votes:
        return PoolResult(symbol, method, 0.5, 0.5, Direction.FLAT, 0.5, 0.0, 0, 0, 0, 0.0)
    ids = [v.agent_id for v in votes]
    if len(set(ids)) != len(ids):
        raise ValueError(f"{symbol}: duplicate votes from one agent")
    logits = {v.agent_id: logit(v.p_up) for v in votes}
    teams: dict[int, list[Vote]] = {}
    for v in sorted(votes, key=lambda x: (x.team, x.agent_id)):
        teams.setdefault(v.team, []).append(v)

    if two_stage:
        agent_w = waterfill(
            shrink_to_equal({v.agent_id: v.weight for v in votes}, cfg.shrink_to_equal),
            cfg.agent_weight_cap,
        )
        mass = {t: sum(agent_w[v.agent_id] for v in members) for t, members in teams.items()}
        team_w = waterfill(mass, cfg.team_weight_cap)
        team_logits = {
            t: sum(agent_w[v.agent_id] * logits[v.agent_id] for v in members) / mass[t]
            for t, members in teams.items()
        }
        effective = {
            v.agent_id: team_w[t] * agent_w[v.agent_id] / mass[t]
            for t, members in teams.items()
            for v in members
        }
        system_logit = sum(team_w[t] * team_logits[t] for t in teams)
    else:
        effective = {v.agent_id: 1.0 / len(votes) for v in votes}
        team_logits = {
            t: sum(logits[v.agent_id] for v in members) / len(members)
            for t, members in teams.items()
        }
        system_logit = sum(logits.values()) / len(votes)

    disagreement = math.sqrt(sum(w * (logits[a] - system_logit) ** 2 for a, w in effective.items()))
    n_eff_value = float(len(teams)) if n_eff is None else n_eff
    p_raw = sigmoid(system_logit)
    p = p_raw
    if n_eff_value < cfg.n_eff_min:
        p = min(max(p, 1.0 - cfg.low_n_eff_p_cap), cfg.low_n_eff_p_cap)
    if p > 0.5:
        direction, p_direction = Direction.LONG, p
    elif p < 0.5:
        direction, p_direction = Direction.SHORT, 1.0 - p
    else:
        direction, p_direction = Direction.FLAT, 0.5
    sign = (system_logit > 0) - (system_logit < 0)
    teams_agree = sum(1 for value in team_logits.values() if sign != 0 and value * sign > 0)
    return PoolResult(
        symbol=symbol,
        method=method,
        p_up_raw=p_raw,
        p_up=p,
        direction=direction,
        p_direction=p_direction,
        disagreement=disagreement,
        n_agents=len(votes),
        teams_present=len(teams),
        teams_agree=teams_agree,
        n_eff=n_eff_value,
        team_logits=team_logits,
        agent_weights=effective,
    )


@dataclass(frozen=True)
class GoDecision:
    go: bool
    net_edge: float
    exp_return: float
    reasons: tuple[str, ...]


def implied_return(p_up: float, sigma_daily: float, horizon: int) -> float:
    """Expected return over ``horizon`` implied by p and volatility (normal approximation)."""
    return sigma_daily * math.sqrt(horizon) * _NORMAL.inv_cdf(clamp_probability(p_up))


def go_decision(
    pool: PoolResult,
    *,
    sigma_daily: float | None,
    agg: AggregationConfig,
    costs: CostConfig,
    phase: int,
    p_no_trade: float | None,
    blocks: Sequence[str],
    round_trip_cost: float | None = None,
) -> GoDecision:
    """Apply the GO rules. Every failed rule is listed, so a no-trade is always explained.

    ``round_trip_cost`` is A09's estimate; it is only used when it is ABOVE the configured
    cost, so a liquidity estimate can raise the hurdle but never lower it.
    """
    if pool.n_agents == 0:
        return GoDecision(False, 0.0, 0.0, ("no agent made a forecast",))
    reasons: list[str] = []
    mu = 0.0
    if sigma_daily is None:
        reasons.append("no volatility forecast from A08")
    else:
        mu = implied_return(pool.p_up, sigma_daily, agg.decision_horizon_days)
    cost = max(costs.round_trip_cost, round_trip_cost or 0.0)
    net_edge = abs(mu) - cost - costs.edge_buffer
    if pool.p_direction < agg.go_min_p:
        reasons.append(f"pooled p {pool.p_direction:.3f} below {agg.go_min_p:.2f}")
    if net_edge < agg.edge_cost_multiple * cost:
        reasons.append(
            f"net edge {net_edge:.2%} under the {agg.edge_cost_multiple * cost:.2%} needed "
            f"({agg.edge_cost_multiple:g}x the {cost:.2%} round-trip cost)"
        )
    needed = agg.min_teams_agree(phase)
    if pool.teams_agree < needed:
        reasons.append(f"{pool.teams_agree} team(s) agree, {needed} needed")
    if p_no_trade is not None and p_no_trade >= agg.max_p_no_trade:
        reasons.append(f"A40 p_no_trade {p_no_trade:.2f} at or above {agg.max_p_no_trade:.2f}")
    reasons.extend(f"Tier-1 block: {b}" for b in blocks)
    if reasons:
        return GoDecision(False, net_edge, mu, tuple(reasons))
    return GoDecision(True, net_edge, mu, ("all GO rules passed",))


def size_hint(pool: PoolResult, agg: AggregationConfig) -> float:
    """Confidence (0.5-1.0) times the disagreement multiplier 1 - min(0.5, D / D_max)."""
    span = max(agg.low_n_eff_p_cap - agg.go_min_p, 1e-9)
    confidence = min(1.0, max(0.5, 0.5 + 0.5 * (pool.p_direction - agg.go_min_p) / span))
    disagreement = 1.0 - min(0.5, pool.disagreement / agg.disagreement_max)
    return confidence * disagreement
