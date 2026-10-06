"""The simple menu, the daily task schedule and the real-money step of the daily run."""

from __future__ import annotations

import shlex
import shutil
from collections.abc import Iterator
from pathlib import Path

import pytest

from quantagents import menu
from quantagents.cli import main
from quantagents.config import LIVE_APPROVAL_ENV, LIVE_APPROVAL_TOKEN, AppConfig
from quantagents.data import sources
from quantagents.risk.killswitch import KillSwitch
from tests.test_ops import last_weekday
from tests.test_watchdog_daily import fake_history

STOCKS = AppConfig.model_validate({"universe": {"symbols": ["SPY", "TLT"]}})
CRYPTO = AppConfig.model_validate({"universe": {"symbols": ["BTC-CAD.KRAKEN"]}})
LIVE_SETTINGS = (
    "system:\n  execution_mode: live\n  autonomy_level: 3\n  live_trading_approved: true\n"
)


@pytest.fixture
def home(tmp_path: Path, repo_root: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    shutil.copytree(repo_root / "config", tmp_path / "config")
    shutil.copy(tmp_path / "config" / "us_etfs.example.yaml", tmp_path / "config" / "mine.yaml")
    monkeypatch.chdir(tmp_path)
    return tmp_path


class FakeShell:
    """schtasks and crontab, remembered in memory."""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []
        self.tasks: set[str] = set()
        self.crontab: str | None = "MAILTO=me\n5 4 * * * backup.sh\n"

    def __call__(self, cmd: list[str], stdin: str | None) -> tuple[int, str]:
        self.calls.append(cmd)
        if cmd[0] == "schtasks":
            name = cmd[cmd.index("/TN") + 1]
            if cmd[1] == "/Create":
                self.tasks.add(name)
            elif name not in self.tasks:
                return 1, "ERROR: The system cannot find the file specified."
            elif cmd[1] == "/Delete":
                self.tasks.discard(name)
            return 0, f"TaskName: \\{name}" if cmd[1] == "/Query" else "SUCCESS"
        if cmd == ["crontab", "-l"]:
            return (0, self.crontab) if self.crontab is not None else (1, "no crontab for user")
        if cmd == ["crontab", "-"]:
            self.crontab = stdin
            return 0, ""
        return 127, "not found"


def answers(*items: str) -> menu.Ask:
    it: Iterator[str] = iter(items)

    def ask(prompt: str) -> str:
        try:
            return next(it)
        except StopIteration:
            raise EOFError from None

    return ask


def test_schedule_times_follow_the_market(tmp_path: Path) -> None:
    stocks = menu.schedule_for(STOCKS, tmp_path / "QuantAgents-50")
    crypto = menu.schedule_for(CRYPTO, tmp_path / "QuantAgents-Crypto")
    assert (stocks.time, stocks.every_day) == ("15:30", False)
    assert (crypto.time, crypto.every_day) == ("19:00", True)
    assert stocks.name == "QuantAgents daily (QuantAgents-50)" != crypto.name
    on = menu.windows_commands(stocks, Path("C:/My Files/QuantAgents-50"))["on"]
    assert on[on.index("/TR") + 1] == f'"{Path("C:/My Files/QuantAgents-50/daily.bat")}"'
    assert on[on.index("/SC") :] == [
        "/SC",
        "WEEKLY",
        "/D",
        "MON,TUE,WED,THU,FRI",
        "/ST",
        "15:30",
        "/F",
    ]
    assert menu.windows_commands(crypto, tmp_path)["on"][-5:] == [
        "/SC",
        "DAILY",
        "/ST",
        "19:00",
        "/F",
    ]
    script = shlex.quote(str(Path("/home/a b") / "daily.sh"))  # quoted: the path has a space
    assert menu.cron_line(stocks, Path("/home/a b")).startswith(f"30 15 * * 1-5 bash {script} >")


def test_windows_task_on_and_off(tmp_path: Path) -> None:
    shell, s = FakeShell(), menu.schedule_for(STOCKS, tmp_path)
    assert not menu.is_scheduled(s, tmp_path, "Windows", shell)
    # a stub schtasks that says yes to everything (Wine) is not taken as ON
    assert not menu.is_scheduled(s, tmp_path, "Windows", lambda cmd, stdin: (0, ""))
    assert (
        "ON: Monday to Friday at 15:30" in menu.set_schedule(True, s, tmp_path, "Windows", shell)[0]
    )
    assert menu.is_scheduled(s, tmp_path, "Windows", shell)
    assert menu.set_schedule(False, s, tmp_path, "Windows", shell) == [
        "The automatic daily run is OFF."
    ]
    assert "already off" in menu.set_schedule(False, s, tmp_path, "Windows", shell)[0]


def test_cron_on_and_off_keeps_other_lines(tmp_path: Path) -> None:
    shell, s = FakeShell(), menu.schedule_for(CRYPTO, tmp_path)
    menu.set_schedule(True, s, tmp_path, "Linux", shell)
    menu.set_schedule(True, s, tmp_path, "Linux", shell)  # twice: still one line
    assert shell.crontab is not None and shell.crontab.count(s.name) == 1
    assert "backup.sh" in shell.crontab and menu.is_scheduled(s, tmp_path, "Linux", shell)
    menu.set_schedule(False, s, tmp_path, "Linux", shell)
    assert s.name not in shell.crontab and "backup.sh" in shell.crontab

    def no_cron(cmd: list[str], stdin: str | None) -> tuple[int, str]:
        return 127, "No such file or directory: 'crontab'"

    assert "Add this line" in menu.set_schedule(True, s, tmp_path, "Linux", no_cron)[0]
    assert "Remove the line" in menu.set_schedule(False, s, tmp_path, "Linux", no_cron)[0]
    shell.crontab = None  # a user with no crontab yet
    menu.set_schedule(True, s, tmp_path, "Darwin", shell)
    assert str(shell.crontab).startswith("0 19 * * * bash")


def run_menu(
    home: Path, *items: str, shell: FakeShell | None = None
) -> tuple[list[list[str]], str]:
    out: list[str] = []
    calls: list[list[str]] = []

    def run(argv: list[str]) -> int:
        calls.append(argv)
        return main(argv)

    code = menu.run_menu(
        config="config/mine.yaml",
        run=run,
        ask=answers(*items),
        say=out.append,
        shell=shell or FakeShell(),
        opener=lambda path: False,
        folder=home,
        system="Windows",
    )
    assert code == 0
    return calls, "\n".join(out)


def test_menu_stop_and_resume(home: Path, capsys: pytest.CaptureFixture[str]) -> None:
    switch = KillSwitch(home / "state" / "kill_switch.json")
    calls, out = run_menu(home, "5", "")
    assert switch.engaged and "Kill switch: armed" in out and "Real money: OFF" in out
    assert "automatic daily run: OFF" in out and "SPY, EFA" in out
    calls, out = run_menu(home, "6", "", "", "6", "wrong words", "", "6", "I_REVIEWED_THE_HALT", "")
    assert "Cancelled: trading stays stopped." in out
    assert calls[-1] == [
        "--config",
        "config/mine.yaml",
        "killswitch",
        "reset",
        "--confirm",
        "I_REVIEWED_THE_HALT",
    ]
    assert not switch.engaged and "Kill switch reset" in capsys.readouterr().out


def test_menu_other_choices(home: Path, capsys: pytest.CaptureFixture[str]) -> None:
    shell = FakeShell()
    calls, out = run_menu(
        home, "3", "", "7", "", "8", "", "10", "no", "", "11", "", "x", "q", shell=shell
    )
    assert "ON: Monday to Friday at 15:30" in out and "Could not open an editor" in out
    assert "Cancelled: nothing was sent." in out and "Please type one of the numbers" in out
    assert [c[2:] for c in calls] == [["config"], ["live", "check"], ["doctor"]]
    assert "Real money is OFF" in capsys.readouterr().out
    assert shell.tasks and "automatic daily run: ON" in out  # the next header shows it


def test_menu_survives_a_broken_settings_file(home: Path) -> None:
    (home / "config" / "mine.yaml").write_text(
        "risk:\n  max_daily_loss_pct: -1\n", encoding="utf-8"
    )
    _, out = run_menu(home, "0")
    assert "has a problem" in out and "choice 7 opens it" in out and "Goodbye" in out
    (home / "config" / "mine.yaml").write_text(LIVE_SETTINGS, encoding="utf-8")
    _, out = run_menu(home, "0")
    assert f"{LIVE_APPROVAL_ENV}=" in out and "add the line named above to .env" in out


def test_menu_reads_a_line_added_to_env(home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(LIVE_APPROVAL_ENV, "")  # so the phrase the menu loads is removed after
    monkeypatch.delenv(LIVE_APPROVAL_ENV)
    (home / ".env").write_text(f"{LIVE_APPROVAL_ENV}={LIVE_APPROVAL_TOKEN}\n", encoding="utf-8")
    (home / "config" / "mine.yaml").write_text(LIVE_SETTINGS, encoding="utf-8")
    _, out = run_menu(home, "0")
    assert "has a problem" not in out and "Real money: NOT armed" in out


def test_daily_runs_the_real_money_step_only_in_live_mode(
    home: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sources, "fetch_yahoo", lambda s, a, b: fake_history(s, last_weekday()))
    assert main(["--config", "config/mine.yaml", "daily", "--out", "data/p.csv"]) == 0
    assert "live sync" not in capsys.readouterr().out
    monkeypatch.setenv(LIVE_APPROVAL_ENV, LIVE_APPROVAL_TOKEN)
    text = (home / "config" / "mine.yaml").read_text(encoding="utf-8")
    (home / "config" / "mine.yaml").write_text(text + LIVE_SETTINGS, encoding="utf-8")
    # stocks cannot trade for real here, the keys and the STATUS row are missing: refused
    assert main(["--config", "config/mine.yaml", "daily", "--out", "data/p.csv"]) == 1
    out = capsys.readouterr().out
    assert "--- live sync (exit 3)" in out and "Real money: REFUSED" in out
    assert "only exchange crypto" in out and not (home / "state" / "live_ledger.json").exists()
    assert main(["--config", "config/mine.yaml", "status"]) == 0
    assert "Live mode is ON in the config" in capsys.readouterr().out


def test_a_second_daily_run_at_the_same_time_does_nothing(
    home: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from quantagents.runlock import RunLock

    fetched: list[str] = []
    monkeypatch.setattr(sources, "fetch_yahoo", lambda s, a, b: fetched.append(s))
    lock = RunLock(home / "state" / "daily.lock")
    assert lock.acquire()  # the scheduled run is still going when the owner clicks "1"
    assert main(["--config", "config/mine.yaml", "daily"]) == 0
    assert "Another daily run is still going" in capsys.readouterr().out and not fetched
    lock.release()
