"""Commit-reveal sealing of predictions (spec section 11).

1. Before the deadline each signal agent posts hash(nonce + predictions).
2. After the deadline agents reveal; the orchestrator checks every hash.
3. Late, missing or mismatched reveals count as abstentions for the cycle.
No agent can see, copy or anchor on another agent's call before committing its own.
"""

from __future__ import annotations

import secrets
from collections.abc import Sequence

from quantagents.hashing import canonical_json, sha256_hex
from quantagents.schemas import AgentPrediction, Commitment


class SealError(RuntimeError):
    """A protocol violation: committing late, revealing early or twice."""


def new_nonce() -> str:
    return secrets.token_hex(16)


def commitment_hash(predictions: Sequence[AgentPrediction], nonce: str) -> str:
    body = canonical_json([p.model_dump(mode="json") for p in predictions])
    return sha256_hex(f"{nonce}|{body}")


class SealedBox:
    def __init__(self, cycle_id: str) -> None:
        self.cycle_id = cycle_id
        self._commits: dict[str, Commitment] = {}
        self._closed = False
        self.accepted: dict[str, list[AgentPrediction]] = {}
        self.rejected: dict[str, str] = {}

    @property
    def closed(self) -> bool:
        return self._closed

    @property
    def committed(self) -> tuple[str, ...]:
        return tuple(sorted(self._commits))

    def commit(self, commitment: Commitment) -> None:
        if self._closed:
            raise SealError(f"{commitment.agent_id} committed after the deadline")
        if commitment.cycle_id != self.cycle_id:
            raise SealError(f"{commitment.agent_id} committed to the wrong cycle")
        if commitment.agent_id in self._commits:
            raise SealError(f"{commitment.agent_id} committed twice")
        self._commits[commitment.agent_id] = commitment

    def close(self) -> None:
        self._closed = True

    def reveal(self, agent_id: str, predictions: Sequence[AgentPrediction], nonce: str) -> bool:
        """Accept the predictions only if they match the commitment exactly."""
        if not self._closed:
            raise SealError("reveal before the deadline")
        if agent_id in self.accepted or agent_id in self.rejected:
            raise SealError(f"{agent_id} revealed twice")
        commitment = self._commits.get(agent_id)
        if commitment is None:
            self.rejected[agent_id] = "no commitment before the deadline"
            return False
        if any(p.agent_id != agent_id or p.cycle_id != self.cycle_id for p in predictions):
            self.rejected[agent_id] = "predictions belong to another agent or cycle"
            return False
        if commitment_hash(predictions, nonce) != commitment.commit_hash:
            self.rejected[agent_id] = "hash mismatch: prediction changed after commit"
            return False
        self.accepted[agent_id] = list(predictions)
        return True

    def unrevealed(self) -> tuple[str, ...]:
        done = set(self.accepted) | set(self.rejected)
        return tuple(a for a in self.committed if a not in done)
