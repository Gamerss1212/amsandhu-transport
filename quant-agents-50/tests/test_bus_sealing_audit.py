from __future__ import annotations

import json
from pathlib import Path

import pytest

from quantagents.audit import AuditLog, read_records, verify_chain
from quantagents.bus import BusPermissionError, MessageBus
from quantagents.hashing import model_hash
from quantagents.schemas import AgentPrediction, Commitment, NoTradeVerdict
from quantagents.sealing import SealedBox, SealError, commitment_hash, new_nonce
from tests.helpers import prediction

VERDICT = NoTradeVerdict(cycle_id="C1", symbol="AAA", p_no_trade=0.2, reasons=("no red flags",))


def _publish(bus: MessageBus, agent: str, topic: str, cycle: str = "C1") -> None:
    bus.publish(
        from_agent=agent, topic=topic, payload=VERDICT, cycle_id=cycle, snapshot_id="S1", ts_utc="t"
    )


def test_bus_envelope_and_filters() -> None:
    bus = MessageBus()
    _publish(bus, "A40", "signals.notrade")
    _publish(bus, "A40", "signals.notrade", cycle="C2")
    env = bus.messages("signals.notrade", "C1")[0]
    assert env.msg_id == "C1-M00000"
    assert env.schema == "NoTradeVerdict"
    assert env.payload_hash == model_hash(VERDICT)
    assert len(bus) == 2
    assert len(bus.messages(cycle_id="C2")) == 1
    assert bus.messages("risk.verdict") == []


def test_bus_enforces_topic_ownership() -> None:
    bus = MessageBus()
    with pytest.raises(BusPermissionError):
        _publish(bus, "A11", "risk.verdict")
    with pytest.raises(BusPermissionError):
        _publish(bus, "A47", "signals.commit")
    with pytest.raises(KeyError):
        _publish(bus, "A40", "no.such.topic")
    _publish(bus, "A33", "signals.commit")


def _sealed(nonce: str = "n1") -> tuple[SealedBox, list[AgentPrediction]]:
    preds = [prediction("A11", "AAA", 0.6), prediction("A11", "BBB", 0.4)]
    box = SealedBox("C1")
    box.commit(Commitment(agent_id="A11", cycle_id="C1", commit_hash=commitment_hash(preds, nonce)))
    return box, preds


def test_commit_reveal_roundtrip() -> None:
    box, preds = _sealed()
    assert box.committed == ("A11",)
    box.close()
    assert box.closed
    assert box.reveal("A11", preds, "n1")
    assert box.accepted["A11"] == preds
    assert box.unrevealed() == ()


def test_changed_prediction_or_nonce_is_rejected() -> None:
    box, preds = _sealed()
    box.close()
    assert not box.reveal("A11", [prediction("A11", "AAA", 0.7), preds[1]], "n1")
    assert "hash mismatch" in box.rejected["A11"]
    box2, preds2 = _sealed()
    box2.close()
    assert not box2.reveal("A11", preds2, "other-nonce")


def test_protocol_violations() -> None:
    box, preds = _sealed()
    with pytest.raises(SealError, match="before the deadline"):
        box.reveal("A11", preds, "n1")
    with pytest.raises(SealError, match="twice"):
        box.commit(Commitment(agent_id="A11", cycle_id="C1", commit_hash="0" * 64))
    with pytest.raises(SealError, match="wrong cycle"):
        box.commit(Commitment(agent_id="A12", cycle_id="C9", commit_hash="0" * 64))
    box.commit(Commitment(agent_id="A16", cycle_id="C1", commit_hash="0" * 64))
    box.close()
    with pytest.raises(SealError, match="after the deadline"):
        box.commit(Commitment(agent_id="A23", cycle_id="C1", commit_hash="0" * 64))
    assert not box.reveal("A12", [], "x")
    assert "no commitment" in box.rejected["A12"]
    assert not box.reveal("A16", preds, "n1")
    assert "another agent" in box.rejected["A16"]
    assert box.unrevealed() == ("A11",)
    box.reveal("A11", preds, "n1")
    with pytest.raises(SealError, match="twice"):
        box.reveal("A11", preds, "n1")


def test_nonces_are_unique() -> None:
    assert len({new_nonce() for _ in range(50)}) == 50


def test_audit_chain_detects_tampering(tmp_path: Path) -> None:
    path = tmp_path / "audit.jsonl"
    log = AuditLog(path)
    for i in range(3):
        log.append("step", {"n": i})
    ok, message = verify_chain(read_records(path))
    assert ok, message
    reopened = AuditLog(path)
    assert reopened.head == log.head
    reopened.append("step", {"n": 3})
    assert len(read_records(path)) == 4

    lines = path.read_text(encoding="utf-8").splitlines()
    record = json.loads(lines[1])
    record["data"]["n"] = 99
    lines[1] = json.dumps(record)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    ok, message = verify_chain(read_records(path))
    assert not ok and "record 1" in message
    with pytest.raises(ValueError, match="failed verification"):
        AuditLog(path)


def test_audit_detects_deleted_records() -> None:
    log = AuditLog()
    for i in range(3):
        log.append("step", {"n": i})
    assert verify_chain(log.records)[0]
    assert not verify_chain([log.records[0], log.records[2]])[0]
    assert read_records(Path("does-not-exist.jsonl")) == []
