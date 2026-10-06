"""Typed publish/subscribe bus with per-topic publisher permissions (spec section 11).

In-memory and append-only. A single-machine build can persist it to SQLite or DuckDB later
without changing agents: they only call ``publish`` and ``messages``.
"""

from __future__ import annotations

from dataclasses import dataclass

from quantagents.hashing import model_hash
from quantagents.schemas import SCHEMA_VERSION, Message

SIGNAL_AGENTS = frozenset(f"A{n:02d}" for n in range(11, 34))

TOPIC_PUBLISHERS: dict[str, frozenset[str]] = {
    "data.snapshot": frozenset({"A01"}),
    "data.health": frozenset({"A02"}),
    "ledger.state": frozenset({"A05"}),
    "features.ready": frozenset({"A03"}),
    "text.items": frozenset({"A04"}),
    "context.regime": frozenset({"A06"}),
    "context.transition": frozenset({"A07"}),
    "context.vol": frozenset({"A08"}),
    "context.liquidity": frozenset({"A09"}),
    "context.macro": frozenset({"A10"}),
    "context.novelty": frozenset({"A34"}),
    "signals.commit": SIGNAL_AGENTS,
    "signals.reveal": SIGNAL_AGENTS,
    "signals.notrade": frozenset({"A40"}),
    "scores.calibrated": frozenset({"A35"}),
    "decision.candidates": frozenset({"A46", "A47"}),
    "debate.cases": frozenset({"A36", "A37", "A38", "A39", "A40"}),
    "decision.proposal": frozenset({"A46", "A47"}),
    "portfolio.target": frozenset({"A48"}),
    "orders.intent": frozenset({"A48"}),
    "risk.stress": frozenset({"A45"}),
    "risk.verdict": frozenset({"A49"}),
    "orders.fills": frozenset({"A50"}),
    "tca.report": frozenset({"A50"}),
    "ops.alerts": frozenset({"A02", "A05", "A46", "A49", "A50"}),
    "ops.killswitch": frozenset({"A46", "A49"}),
    "research.trials": frozenset({"A41", "A42", "A43"}),
    "research.validation": frozenset({"A39", "A44", "A45"}),
    "governance.scorecards": frozenset({"A35"}),
}


class BusPermissionError(PermissionError):
    """An agent tried to publish on a topic it does not own."""


@dataclass(frozen=True)
class Envelope:
    """MessageEnvelope v1 (spec section 81)."""

    msg_id: str
    cycle_id: str
    snapshot_id: str
    from_agent: str
    topic: str
    schema: str
    schema_version: str
    ts_utc: str
    payload: Message
    payload_hash: str


class MessageBus:
    def __init__(self) -> None:
        self._log: list[Envelope] = []

    def publish(
        self,
        *,
        from_agent: str,
        topic: str,
        payload: Message,
        cycle_id: str,
        snapshot_id: str,
        ts_utc: str,
    ) -> Envelope:
        if topic not in TOPIC_PUBLISHERS:
            raise KeyError(f"unknown topic {topic!r}")
        if from_agent not in TOPIC_PUBLISHERS[topic]:
            raise BusPermissionError(f"{from_agent} may not publish on {topic}")
        envelope = Envelope(
            msg_id=f"{cycle_id}-M{len(self._log):05d}",
            cycle_id=cycle_id,
            snapshot_id=snapshot_id,
            from_agent=from_agent,
            topic=topic,
            schema=type(payload).__name__,
            schema_version=SCHEMA_VERSION,
            ts_utc=ts_utc,
            payload=payload,
            payload_hash=model_hash(payload),
        )
        self._log.append(envelope)
        return envelope

    def messages(self, topic: str | None = None, cycle_id: str | None = None) -> list[Envelope]:
        return [
            e
            for e in self._log
            if (topic is None or e.topic == topic) and (cycle_id is None or e.cycle_id == cycle_id)
        ]

    def __len__(self) -> int:
        return len(self._log)
