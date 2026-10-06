"""A47 Meta-Aggregator, the CIO (Team 10, Phase 4; an equal-weight combiner stands in before).

Pools sealed predictions per symbol, applies the GO rules and writes a DecisionProposal
with a plain-English memo. It can never override A49.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from quantagents.agents.base import Agent
from quantagents.aggregation import (
    GoDecision,
    PoolResult,
    pool_votes,
    size_hint,
    votes_from_predictions,
)
from quantagents.config import AppConfig
from quantagents.schemas import AgentPrediction, DebateOutcome, DecisionProposal


class MetaAggregator(Agent):
    agent_id = "A47"
    name = "Meta-Aggregator (CIO)"
    kind = "stat"
    info_subset = ("sealed_predictions", "context", "scorecards")

    def pool(
        self,
        symbol: str,
        predictions: Sequence[AgentPrediction],
        cfg: AppConfig,
        *,
        two_stage: bool,
        n_eff: float | None = None,
        weights: Mapping[str, float] | None = None,
    ) -> PoolResult:
        """Pool one symbol's votes. ``weights`` and ``n_eff`` come from A35's scorecards;
        weights only matter in two-stage mode, where they are shrunk toward equal and capped."""
        votes = votes_from_predictions(predictions, cfg.aggregation.decision_horizon_days, weights)
        return pool_votes(symbol, votes, cfg.aggregation, two_stage=two_stage, n_eff=n_eff)

    def propose(
        self,
        *,
        decision_id: str,
        cycle_id: str,
        pool: PoolResult,
        decision: GoDecision,
        predictions: Sequence[AgentPrediction],
        cfg: AppConfig,
        debate_outcome: DebateOutcome = DebateOutcome.NOT_LIVE,
    ) -> DecisionProposal:
        voters = [p for p in predictions if not p.abstain]
        hint = size_hint(pool, cfg.aggregation) if decision.go else 0.0
        verdict = "GO" if decision.go else "NO TRADE"
        memo = (
            f"{pool.symbol}: {verdict}. {pool.n_agents} agent(s) from {pool.teams_present} team(s) "
            f"voted; pooled P(up) {pool.p_up:.3f} ({pool.method}), {pool.teams_agree} team(s) agree, "
            f"disagreement {pool.disagreement:.2f}, net edge {decision.net_edge:.2%}. "
            f"Why: {'; '.join(decision.reasons)}."
        )
        return DecisionProposal(
            decision_id=decision_id,
            cycle_id=cycle_id,
            symbol=pool.symbol,
            direction=pool.direction,
            pooled_p=pool.p_up,
            p_direction=pool.p_direction,
            n_eff=pool.n_eff,
            disagreement=pool.disagreement,
            teams_agree=pool.teams_agree,
            net_edge=decision.net_edge,
            exp_return=decision.exp_return,
            go=decision.go,
            reasons=decision.reasons,
            debate_outcome=debate_outcome,
            size_hint=hint,
            rationale_ids=tuple(p.prediction_id for p in voters),
            memo=memo,
        )
