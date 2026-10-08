"""Bringing an account over from an older folder after an update."""

from __future__ import annotations

from pathlib import Path

import pytest

from quantagents import menu
from quantagents.cli import main
from quantagents.migrate import import_from
from quantagents.risk.killswitch import RESET_PHRASE, KillSwitch
from tests.test_menu import FakeShell, answers


@pytest.fixture
def old(tmp_path: Path) -> Path:
    folder = tmp_path / "QuantAgents-50-old"
    files = {
        "state/paper_account.json": "{}",
        "state/live_ledger.json": "{}",
        "state/live.lock": "pid 1",
        "runs/cycles/C1.json": '{"as_of": "2026-10-05"}',
        "runs/daily.log": "=== daily run",
        "data/prices.csv": "date,symbol\n",
        "config/my_universe.yaml": "universe:\n  symbols: [SPY]\n",
        ".env": "LIVE_API_KEY=not-a-real-key\n",
    }
    for name, text in files.items():
        (folder / name).parent.mkdir(parents=True, exist_ok=True)
        (folder / name).write_text(text, encoding="utf-8")
    return folder


def test_import_copies_the_account_and_stops_the_old_folder(old: Path, tmp_path: Path) -> None:
    new = tmp_path / "QuantAgents-50"
    (new / "config").mkdir(parents=True)
    (new / "config" / "my_universe.yaml").write_text("universe: {}\n", encoding="utf-8")
    lines = "\n".join(import_from(old, new))
    for name in ("state/paper_account.json", "state/live_ledger.json", "runs/cycles/C1.json",
                 "runs/daily.log", "data/prices.csv", ".env"):  # fmt: skip
        assert (new / name).read_text(encoding="utf-8") == (old / name).read_text(encoding="utf-8")
    assert (new / "config" / "my_universe.yaml").read_text(encoding="utf-8").endswith("[SPY]\n")
    assert not (new / "state" / "live.lock").exists()  # a lock never travels
    assert "not-a-real-key" not in lines and ".env (contents not shown)" in lines
    state = KillSwitch(old / "state" / "kill_switch.json").state()
    assert state.engaged and "moved to" in state.reason and state.by == "import"
    assert not KillSwitch(new / "state" / "kill_switch.json").engaged
    with pytest.raises(ValueError, match="already brought over once"):
        import_from(old, new)  # one account never runs in two places
    KillSwitch(old / "state" / "kill_switch.json").reset(RESET_PHRASE, by="test")
    with pytest.raises(ValueError, match="already has its own paper account"):
        import_from(old, new)  # and two accounts never mix


def test_import_refuses_what_is_not_an_older_account(old: Path, tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="that is this folder"):
        import_from(old, old)
    with pytest.raises(ValueError, match="is not a folder"):
        import_from(tmp_path / "missing", tmp_path / "new")
    (tmp_path / "empty").mkdir()
    with pytest.raises(ValueError, match="no QuantAgents account"):
        import_from(tmp_path / "empty", tmp_path / "new")


def test_import_from_the_command_line_and_the_menu(
    old: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    new = tmp_path / "new"
    new.mkdir()
    monkeypatch.chdir(new)
    assert main(["import-from", str(old)]) == 0
    assert "OLD folder is now stopped" in capsys.readouterr().out
    assert main(["import-from", str(old)]) == 2  # a second time is refused
    other = tmp_path / "other"
    other.mkdir()
    monkeypatch.chdir(other)
    out: list[str] = []
    shell = FakeShell()
    menu.run_menu(
        config="config/mine.yaml",
        run=main,
        ask=answers("12", f'"{old}"', "", "12", "", "", "0"),
        say=out.append,
        shell=shell,
        opener=lambda path: False,
        folder=other,
        system="Windows",
    )
    text = "\n".join(out)
    # the old folder was already brought over to `new`: a second copy is refused
    assert "Not imported:" in text and "already brought over once" in text
    assert "Cancelled: nothing was copied." in text
    assert not (other / "state" / "paper_account.json").exists()
    # from the folder in use now, it works, and the old task is switched off
    out.clear()
    menu.run_menu(
        config="config/mine.yaml",
        run=main,
        ask=answers("12", f'"{new}"', "", "0"),
        say=out.append,
        shell=shell,
        opener=lambda path: False,
        folder=other,
        system="Windows",
    )
    text = "\n".join(out)
    assert f"Bringing your account over from {new.resolve()}" in text
    assert "Old folder: The automatic daily run was already off." in text
    assert any(c[:2] == ["schtasks", "/Query"] for c in shell.calls)  # asked, nothing to delete
    assert (other / "state" / "paper_account.json").exists()


def test_import_finds_the_account_inside_a_newer_download(old: Path, tmp_path: Path) -> None:
    root = tmp_path / "QuantAgents-50-0.10"  # 0.10.0 on: QuantAgents.bat + program/
    root.mkdir()
    old.rename(root / "program")
    (root / "program" / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    new = tmp_path / "next" / "program"
    new.mkdir(parents=True)
    import_from(root, new)  # the owner types the folder they unzipped, not program/
    assert (new / "state" / "paper_account.json").exists()
    assert KillSwitch(root / "program" / "state" / "kill_switch.json").engaged
