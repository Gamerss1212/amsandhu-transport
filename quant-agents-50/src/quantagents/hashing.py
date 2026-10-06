"""Canonical JSON and hashing used by the bus, the seal and the audit log."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from pydantic import BaseModel


def canonical_json(obj: Any) -> str:
    """Stable JSON: sorted keys, no whitespace, no NaN or infinity."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), allow_nan=False, default=str)


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def model_hash(model: BaseModel) -> str:
    return sha256_hex(canonical_json(model.model_dump(mode="json")))
