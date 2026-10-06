"""Kill switch (spec section 51). One command stops new trading; only a human can reset it.

The switch is a file, so it survives restarts and a separate watchdog process can fire it
even if the orchestrator crashes. An unreadable file counts as engaged (fail safe).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

RESET_PHRASE = "I_REVIEWED_THE_HALT"


@dataclass(frozen=True)
class KillSwitchState:
    engaged: bool
    reason: str = ""
    by: str = ""
    at_utc: str = ""


class KillSwitch:
    def __init__(self, path: Path | None = None) -> None:
        self._path = path
        self._memory = KillSwitchState(engaged=False)

    def state(self) -> KillSwitchState:
        if self._path is None:
            return self._memory
        if not self._path.exists():
            return KillSwitchState(engaged=False)
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = None
        if not isinstance(data, dict):
            return KillSwitchState(True, "kill-switch file unreadable (fail safe)", "system")
        return KillSwitchState(
            True, str(data.get("reason", "")), str(data.get("by", "")), str(data.get("at_utc", ""))
        )

    @property
    def engaged(self) -> bool:
        return self.state().engaged

    def engage(self, reason: str, by: str) -> KillSwitchState:
        """Engage the switch. If it is already engaged, the first reason is kept."""
        current = self.state()
        if current.engaged:
            return current
        state = KillSwitchState(True, reason, by, datetime.now(UTC).isoformat(timespec="seconds"))
        if self._path is None:
            self._memory = state
        else:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._path.with_name(self._path.name + ".tmp")
            tmp.write_text(json.dumps(asdict(state), indent=2), encoding="utf-8")
            tmp.replace(self._path)
        return state

    def reset(self, confirmation: str, by: str) -> KillSwitchState:
        """Clear the switch. A human must type the exact reset phrase."""
        if confirmation != RESET_PHRASE:
            raise PermissionError(f"to reset, type the exact phrase {RESET_PHRASE}")
        if self._path is None:
            self._memory = KillSwitchState(engaged=False)
        else:
            self._path.unlink(missing_ok=True)
        return KillSwitchState(engaged=False, reason=f"reset by {by}")
