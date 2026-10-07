"""Change the owner's settings file (``config/my_universe.yaml``) safely.

Only the keys a change names are touched; every other setting stays exactly as written. The
new file is checked by loading it as a real config first, so a file that would not load is
never written, and it is replaced in one step (never half-written).
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml

from quantagents.config import AppConfig

HEADER = (
    "# Your QuantAgents settings. Written by the app; edit by hand if you like.\n"
    "# Every setting not written here keeps its default (config/default.yaml).\n"
)


def read_raw(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    return loaded if isinstance(loaded, dict) else {}


def update_config(path: Path, change: Callable[[dict[str, Any]], None]) -> AppConfig:
    """Apply ``change`` to the raw settings, check them, then write the file."""
    raw = read_raw(path)
    change(raw)
    cfg = AppConfig.model_validate(raw)  # raises before anything is written
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(HEADER + yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    tmp.replace(path)
    return cfg
