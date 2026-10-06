from __future__ import annotations

from pathlib import Path

import pytest

from quantagents.risk.killswitch import RESET_PHRASE, KillSwitch


def test_in_memory_switch() -> None:
    switch = KillSwitch()
    assert not switch.engaged
    state = switch.engage("daily loss limit hit", by="A49")
    assert switch.engaged and state.reason == "daily loss limit hit" and state.by == "A49"
    assert (
        switch.engage("second reason", by="human").reason == "daily loss limit hit"
    )  # first cause kept
    with pytest.raises(PermissionError):
        switch.reset("yes please", by="human")
    assert switch.engaged
    assert not switch.reset(RESET_PHRASE, by="human").engaged
    assert not switch.engaged


def test_file_switch_survives_restarts(tmp_path: Path) -> None:
    path = tmp_path / "state" / "kill_switch.json"
    KillSwitch(path).engage("manual stop", by="human")
    reopened = KillSwitch(path)
    assert reopened.engaged and reopened.state().reason == "manual stop"
    reopened.reset(RESET_PHRASE, by="human")
    assert not path.exists() and not KillSwitch(path).engaged


@pytest.mark.parametrize("content", ["not json", "[1, 2]"])
def test_unreadable_file_fails_safe(tmp_path: Path, content: str) -> None:
    path = tmp_path / "kill_switch.json"
    path.write_text(content, encoding="utf-8")
    state = KillSwitch(path).state()
    assert state.engaged and "fail safe" in state.reason
