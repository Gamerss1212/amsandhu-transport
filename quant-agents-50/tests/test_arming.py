"""Switching real money on and off from the app: only the owner's typed approval does it."""

from __future__ import annotations

import os
import shutil
import threading
from datetime import date
from pathlib import Path

import pytest

from quantagents import webapp
from quantagents.cli import main
from quantagents.config import LIVE_APPROVAL_ENV, LIVE_APPROVAL_TOKEN, ExecutionMode, load_config
from quantagents.execution import arming, live
from tests.test_menu import FakeShell
from tests.test_webapp import start

FAKE_KEY = "k" * 24
FAKE_SECRET = "s3cr3t+base64/value=="
TODAY = date(2026, 10, 7)
CRYPTO = "universe:\n  asset_class: crypto_spot\n  symbols: [BTC-CAD.KRAKEN, ETH-CAD.KRAKEN]\n"


@pytest.fixture
def home(tmp_path: Path, repo_root: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    shutil.copytree(repo_root / "config", tmp_path / "config")
    (tmp_path / "config" / "mine.yaml").write_text(CRYPTO, encoding="utf-8")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "STATUS.md").write_text(
        "# Status\n\n## Human approvals\n\n| Date | Decision | Owner |\n|---|---|---|\n"
        "| (none yet) | | |\n\n## Open issues\n\n- none\n",
        encoding="utf-8",
    )
    (tmp_path / ".env").write_text("# mine\nTELEGRAM_CHAT_ID=42\n", encoding="utf-8")
    for name in (LIVE_APPROVAL_ENV, live.KEY_ENV, live.SECRET_ENV):
        monkeypatch.setenv(name, "x")  # so whatever the code sets is removed after the test
        monkeypatch.delenv(name)
    monkeypatch.chdir(tmp_path)
    return tmp_path


def on(home: Path, **overrides: object) -> list[str]:
    args: dict[str, object] = {
        "config": home / "config" / "mine.yaml",
        "env_path": home / ".env",
        "status_file": home / "docs" / "STATUS.md",
        "name": "Test Owner",
        "budget": "150",
        "phrase": LIVE_APPROVAL_TOKEN,
        "today": TODAY,
        **overrides,
    }
    return arming.switch_on(**args)  # type: ignore[arg-type]


def test_keys_are_saved_hidden_and_other_lines_kept(home: Path) -> None:
    message = arming.save_keys(home / ".env", f" {FAKE_KEY} ", FAKE_SECRET)
    assert FAKE_KEY not in message and FAKE_SECRET not in message
    text = (home / ".env").read_text(encoding="utf-8")
    assert "# mine\nTELEGRAM_CHAT_ID=42\n" in text
    assert f"{live.KEY_ENV}={FAKE_KEY}\n" in text and f"{live.SECRET_ENV}={FAKE_SECRET}\n" in text
    assert arming.keys_saved()
    arming.save_keys(home / ".env", "n" * 20, FAKE_SECRET)  # saving again replaces, never doubles
    assert (home / ".env").read_text(encoding="utf-8").count(f"{live.KEY_ENV}=") == 1
    for bad in ("short", "has space inside", "x" * 600, "line\nbreak"):
        with pytest.raises(ValueError, match="do not look like Kraken API keys"):
            arming.save_keys(home / ".env", bad, FAKE_SECRET)


def test_switching_on_needs_every_check_before_any_file_changes(home: Path) -> None:
    config = (home / "config" / "mine.yaml").read_text(encoding="utf-8")
    status = (home / "docs" / "STATUS.md").read_text(encoding="utf-8")
    with pytest.raises(ValueError, match="save your Kraken keys first"):
        on(home)
    arming.save_keys(home / ".env", FAKE_KEY, FAKE_SECRET)
    for overrides, why in (
        ({"phrase": "yes please"}, "approval phrase exactly"),
        ({"name": "x"}, "type your name"),
        ({"name": "Eve | <script>"}, "type your name"),
        ({"budget": "0"}, "above 0 and at most 1,000"),
        ({"budget": "5000"}, "above 0 and at most 1,000"),
        ({"budget": "lots"}, "must be a number"),
    ):
        with pytest.raises(ValueError, match=why):
            on(home, **overrides)
    (home / "config" / "mine.yaml").write_text("universe:\n  symbols: [SPY]\n", encoding="utf-8")
    with pytest.raises(ValueError, match="cannot trade for real"):
        on(home)
    (home / "config" / "mine.yaml").write_text(config, encoding="utf-8")
    assert (home / "docs" / "STATUS.md").read_text(encoding="utf-8") == status
    assert LIVE_APPROVAL_TOKEN not in (home / ".env").read_text(encoding="utf-8")
    assert LIVE_APPROVAL_ENV not in os.environ


def test_switching_on_then_off(home: Path) -> None:
    arming.save_keys(home / ".env", FAKE_KEY, FAKE_SECRET)
    lines = on(home)
    assert "switched ON by Test Owner: budget 150.00 CAD on kraken" in lines[0]
    cfg = load_config(home / "config" / "mine.yaml")
    assert cfg.system.execution_mode is ExecutionMode.LIVE and cfg.system.live_trading_approved
    assert cfg.system.autonomy_level == 3 and cfg.live.budget == 150
    assert cfg.risk == load_config(None).risk  # no risk limit touched
    env_text = (home / ".env").read_text(encoding="utf-8")
    assert (
        f"{LIVE_APPROVAL_ENV}={LIVE_APPROVAL_TOKEN}" in env_text
        and "TELEGRAM_CHAT_ID=42" in env_text
    )
    status = (home / "docs" / "STATUS.md").read_text(encoding="utf-8")
    assert "| 2026-10-07 | Approve Phase 8 micro-live | Test Owner |" in status
    assert "(none yet)" not in status and "## Open issues" in status
    gates = live.gates(
        cfg,
        status_file=home / "docs" / "STATUS.md",
        kill_file=home / "state" / "kill_switch.json",
        runs_dir=home / "runs",
        today=TODAY,
        ccxt_installed=True,
    )
    still_closed = [g.name for g in gates if not g.ok]
    assert still_closed == ["a fresh paper decision"]  # orders still need a fresh paper day
    lines = arming.switch_off(config=home / "config" / "mine.yaml", env_path=home / ".env")
    assert "switched OFF" in lines[0]
    cfg = load_config(home / "config" / "mine.yaml")  # loads without the phrase: paper again
    assert cfg.system.execution_mode is ExecutionMode.PAPER and not cfg.system.live_trading_approved
    assert cfg.universe.symbols == ("BTC-CAD.KRAKEN", "ETH-CAD.KRAKEN")
    env_text = (home / ".env").read_text(encoding="utf-8")
    assert LIVE_APPROVAL_TOKEN not in env_text and FAKE_KEY in env_text  # keys stay
    assert LIVE_APPROVAL_ENV not in os.environ
    assert arming.switch_off(config=home / "config" / "mine.yaml", env_path=home / ".env")  # twice


def test_the_approval_row_lands_in_the_table(tmp_path: Path) -> None:
    status = tmp_path / "STATUS.md"
    arming.add_approval_row(status, TODAY, "A B")  # no file yet: a table is made
    arming.add_approval_row(status, date(2026, 11, 1), "A B")  # a second row goes under it
    text = status.read_text(encoding="utf-8")
    assert text.index("| 2026-10-07 |") < text.index("| 2026-11-01 |")
    assert len(live.APPROVAL_ROW.findall(text)) == 2


def test_the_page_switches_real_money(home: Path) -> None:
    app = webapp.App(
        config="config/mine.yaml", folder=home, run=main, shell=FakeShell(), system="Windows"
    )
    for client in start(app):
        status, reply = client.act(action="save_keys", key="bad", secret="bad")
        assert status == 400 and "Not saved" in reply["error"]
        status, reply = client.act(action="save_keys", key=FAKE_KEY, secret=FAKE_SECRET)
        assert status == 200 and FAKE_KEY not in str(reply)
        data = client.get("/api/status")[1]["live"]
        assert data["keys_saved"] and data["where"] == "kraken, CAD" and not data["on"]
        assert FAKE_KEY not in str(client.get("/api/status")[1])  # never sent back
        status, reply = client.act(
            action="real_money_on", name="Test Owner", budget=100, phrase="no"
        )
        assert status == 400 and "approval phrase" in reply["error"]
        status, reply = client.act(
            action="real_money_on", name="Test Owner", budget=100, phrase=LIVE_APPROVAL_TOKEN
        )
        assert status == 200 and "switched ON" in reply["message"]
        assert client.get("/api/status")[1]["live"]["on"] is True
        # switching off always works, even while a job runs
        release = threading.Event()

        def slow(argv: list[str], done: threading.Event = release) -> int:
            done.wait(10)
            return 0

        app.jobs._run = slow
        client.act(action="doctor")
        status, reply = client.act(action="real_money_off")
        release.set()
        assert status == 200 and "switched OFF" in reply["message"]
        assert client.get("/api/status")[1]["live"]["on"] is False


def test_a_stocks_folder_says_why_it_cannot_trade_for_real(home: Path) -> None:
    (home / "config" / "mine.yaml").write_text("universe:\n  symbols: [SPY]\n", encoding="utf-8")
    app = webapp.App(
        config="config/mine.yaml", folder=home, run=main, shell=FakeShell(), system="Linux"
    )
    for client in start(app):
        data = client.get("/api/status")[1]["live"]
        assert data["where"] is None and "only exchange crypto" in data["not_here"]
        assert data["approval_phrase"] == LIVE_APPROVAL_TOKEN and data["max_budget"] == 1000
