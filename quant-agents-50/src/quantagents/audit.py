"""Tamper-evident audit log (spec section 71): an append-only JSONL hash chain.

Each record stores the hash of the previous one, so editing or deleting any line breaks
every hash after it. ``verify_chain`` finds the first broken link.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from quantagents.hashing import canonical_json, sha256_hex

GENESIS = "0" * 64


def _entry_hash(entry: Mapping[str, Any]) -> str:
    return sha256_hex(canonical_json({k: v for k, v in entry.items() if k != "hash"}))


def verify_chain(records: Sequence[Mapping[str, Any]]) -> tuple[bool, str]:
    previous = GENESIS
    for i, record in enumerate(records):
        if record.get("seq") != i or record.get("prev") != previous:
            return False, f"record {i}: broken link"
        if record.get("hash") != _entry_hash(record):
            return False, f"record {i}: content changed"
        previous = str(record["hash"])
    return True, f"{len(records)} record(s) verified"


def read_records(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


class AuditLog:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path
        self.records: list[dict[str, Any]] = read_records(path) if path is not None else []
        ok, message = verify_chain(self.records)
        if not ok:
            raise ValueError(f"audit log {path} failed verification: {message}")
        self.head = str(self.records[-1]["hash"]) if self.records else GENESIS

    def append(self, kind: str, data: Mapping[str, Any]) -> str:
        entry: dict[str, Any] = {
            "seq": len(self.records),
            "prev": self.head,
            "kind": kind,
            "data": json.loads(canonical_json(data)),
        }
        entry["hash"] = _entry_hash(entry)
        self.records.append(entry)
        self.head = entry["hash"]
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(canonical_json(entry) + "\n")
        return self.head
