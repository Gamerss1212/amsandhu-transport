"""The local web app: its safety checks, every button, and the job runner."""

from __future__ import annotations

import http.client
import json
import shutil
import threading
import time
from collections.abc import Iterator
from datetime import date
from pathlib import Path
from typing import Any

import pytest
import yaml

from quantagents import webapp
from quantagents.cli import main
from quantagents.config import load_config
from quantagents.data import sources
from quantagents.risk.killswitch import KillSwitch
from tests.test_menu import FakeShell
from tests.test_ops import last_weekday
from tests.test_watchdog_daily import fake_history

CONFIG = "config/mine.yaml"


@pytest.fixture
def home(tmp_path: Path, repo_root: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    shutil.copytree(repo_root / "config", tmp_path / "config")
    (tmp_path / "config" / "mine.yaml").write_text(
        "universe:\n  asset_class: US_equities\n  symbols: [AAA, BBB]\n"
        "risk:\n  max_daily_loss_pct: 1.5\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sources, "fetch_yahoo", lambda s, a, b: fake_history(s, last_weekday()))
    return tmp_path


class Client:
    def __init__(self, app: webapp.App) -> None:
        self.app = app

    def request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        *,
        key: bool = True,
        host: str | None = None,
        origin: str | None = None,
    ) -> tuple[int, Any, http.client.HTTPResponse]:
        conn = http.client.HTTPConnection("127.0.0.1", self.app.port, timeout=30)
        headers = {"Host": host or f"127.0.0.1:{self.app.port}"}
        if key:
            headers[webapp.KEY_HEADER] = self.app.token
        if origin:
            headers["Origin"] = origin
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        conn.request(method, path, body=data, headers=headers)
        reply = conn.getresponse()
        raw = reply.read()
        conn.close()
        kind = reply.getheader("Content-Type", "")
        return reply.status, json.loads(raw) if "json" in kind else raw.decode("utf-8"), reply

    def get(self, path: str, **kw: Any) -> tuple[int, Any]:
        status, data, _ = self.request("GET", path, **kw)
        return status, data

    def act(self, **body: Any) -> tuple[int, Any]:
        status, data, _ = self.request("POST", "/api/action", body)
        return status, data

    def wait(self, job_id: str) -> dict[str, Any]:
        for _ in range(600):
            status, job = self.get(f"/api/job/{job_id}")
            assert status == 200
            if job["done"]:
                return dict(job)
            time.sleep(0.05)
        raise AssertionError("job did not finish")


def start(app: webapp.App) -> Iterator[Client]:
    server = webapp.make_server(app, 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield Client(app)
    finally:
        server.shutdown()
        server.server_close()


@pytest.fixture
def shell() -> FakeShell:
    return FakeShell()


@pytest.fixture
def client(home: Path, shell: FakeShell) -> Iterator[Client]:
    app = webapp.App(config=CONFIG, folder=home, run=main, shell=shell, system="Windows")
    yield from start(app)


def test_the_page_and_its_safety_headers(client: Client) -> None:
    status, page, reply = client.request("GET", "/", key=False)
    assert status == 200 and f'content="{client.app.token}"' in page
    csp = reply.getheader("Content-Security-Policy", "")
    assert "frame-ancestors 'none'" in csp and "default-src 'self'" in csp
    assert reply.getheader("X-Frame-Options") == "DENY"
    for path, kind in (("/app.js", "text/javascript"), ("/app.css", "text/css")):
        status, _, reply = client.request("GET", path, key=False)
        assert status == 200 and reply.getheader("Content-Type", "").startswith(kind)
    status, ping = client.get("/api/ping", key=False)
    assert status == 200 and ping["app"] == "QuantAgents"
    assert client.get("/nothing", key=False)[0] == 404


def test_requests_from_anywhere_else_are_refused(client: Client) -> None:
    assert client.get("/api/status", key=False)[0] == 403  # no key: another site cannot read it
    port = client.app.port
    for host in (f"evil.example:{port}", f"127.0.0.1:{port + 1}", "localhost"):
        assert client.get("/", key=False, host=host)[0] == 403  # DNS rebinding
        assert client.request("POST", "/api/action", {"action": "stop"}, host=host)[0] == 403
    status, _, _ = client.request(
        "POST", "/api/action", {"action": "stop"}, origin="http://evil.example"
    )
    assert status == 403
    assert client.request("POST", "/api/action", {"action": "stop"}, key=False)[0] == 403
    assert not KillSwitch(Path("state/kill_switch.json")).engaged  # nothing got through
    status, _, _ = client.request(
        "POST", "/api/action", {"action": "nope"}, origin=f"http://localhost:{port}"
    )
    assert status == 400  # this app's own page is let in
    assert client.request("POST", "/api/elsewhere", {})[0] == 404


def test_a_paper_day_from_the_page(client: Client, shell: FakeShell) -> None:
    status, before = client.get("/api/status")
    assert status == 200 and before["account"] == {"exists": False}
    assert before["mode"] == "paper" and before["paper_days"] == 0 and not before["kill"]["engaged"]
    assert len(before["live"]["gates"]) == 11 and not before["live"]["armed"]
    assert before["schedule"]["on"] is False and before["errors"] == []
    status, reply = client.act(action="run_today")
    assert status == 200 and reply["label"] == "Today's paper trading day"
    job = client.wait(reply["job"])
    assert job["code"] == 0 and "--- cycle (exit 0)" in job["output"]
    seconds = job["seconds"]
    time.sleep(1.1)
    assert client.wait(reply["job"])["seconds"] == seconds  # the clock stops when it is done
    status, after = client.get("/api/status")
    account = after["account"]
    assert account["exists"] and account["equity"] == pytest.approx(10_000.0)
    assert account["scoreboard"].startswith("Scoreboard since ")
    assert after["paper_days"] == 1 and len(after["series"]) == 1
    assert {d["symbol"] for d in after["last_cycle"]["decisions"]} == {"AAA", "BBB"}
    assert after["last_daily"] and after["job"] is None
    # schedule on and off
    assert "ON: Monday to Friday" in client.act(action="schedule_on")[1]["message"]
    assert client.get("/api/status")[1]["schedule"]["on"] is True
    assert client.act(action="schedule_off")[1]["message"] == "The automatic daily run is OFF."


def test_stop_always_works_and_resume_needs_the_phrase(home: Path, shell: FakeShell) -> None:
    release = threading.Event()

    def slow(argv: list[str]) -> int:
        print("working on", argv[-1])
        release.wait(10)
        return 0

    app = webapp.App(config=CONFIG, folder=home, run=slow, shell=shell, system="Windows")
    for client in start(app):
        _, reply = client.act(action="doctor")
        assert client.get("/api/status")[1]["job"]["label"] == "Install check"
        assert client.act(action="run_today")[0] == 409  # one job at a time
        assert client.act(action="symbols", preset="us_etfs")[0] == 409
        status, _ = client.act(action="stop")  # stopping never waits
        assert status == 200 and KillSwitch(Path("state/kill_switch.json")).engaged
        release.set()
        assert client.wait(reply["job"])["output"].startswith("working on doctor")
        status, wrong = client.act(action="resume", phrase="please")
        assert status == 400 and "exact phrase" in wrong["error"]
        status, _ = client.act(action="resume", phrase=" I_REVIEWED_THE_HALT ")
        assert status == 200 and not KillSwitch(Path("state/kill_switch.json")).engaged


def test_a_crashing_command_still_finishes_its_job(home: Path) -> None:
    def broken(argv: list[str]) -> int:
        raise RuntimeError("boom")

    app = webapp.App(config=CONFIG, folder=home, run=broken, shell=FakeShell(), system="Linux")
    for client in start(app):
        job = client.wait(client.act(action="doctor")[1]["job"])
        assert job["code"] == 1 and "RuntimeError: boom" in job["output"]


def test_symbols_from_the_page(client: Client, home: Path) -> None:
    status, reply = client.act(action="symbols", preset="us_etfs")
    assert status == 200 and "SPY" in reply["message"]
    cfg = load_config(home / CONFIG)
    assert cfg.universe.symbols[0] == "SPY" and cfg.risk.max_daily_loss_pct == 1.5  # kept
    status, reply = client.act(action="symbols", symbols="btc-cad.kraken, ETH-CAD.KRAKEN")
    assert status == 200
    cfg = load_config(home / CONFIG)
    assert cfg.universe.symbols == ("BTC-CAD.KRAKEN", "ETH-CAD.KRAKEN")
    assert cfg.universe.asset_class == "crypto_spot" and cfg.risk.quantity_step == 0.0001
    for text, why in (
        ("SPY, BTC-CAD.KRAKEN", "separate folders"),
        ("SPY, <script>", "do not look like symbols"),
        (" , ", "at least one symbol"),
        (",".join(f"S{i}" for i in range(31)), "at most 30"),
    ):
        status, reply = client.act(action="symbols", symbols=text)
        assert status == 400 and why in reply["error"]
    # after the first paper day, a completely different list is refused (one account per folder)
    client.act(action="symbols", symbols="AAA, BBB")
    client.wait(client.act(action="run_today")[1]["job"])
    status, reply = client.act(action="symbols", symbols="XYZ")
    assert status == 400 and "already trades AAA, BBB" in reply["error"]
    assert client.act(action="symbols", symbols="AAA, BBB, CCC")[0] == 200  # adding is fine


def test_write_symbols_never_writes_a_file_that_would_not_load(tmp_path: Path) -> None:
    config = tmp_path / "mine.yaml"
    config.write_text("risk:\n  max_daily_loss_pct: -5\n", encoding="utf-8")
    with pytest.raises(ValueError):
        webapp.write_symbols(config, ["SPY"], "US_equities", tmp_path / "runs")
    assert "max_daily_loss_pct: -5" in config.read_text(encoding="utf-8")  # untouched
    fresh = tmp_path / "new" / "mine.yaml"
    webapp.write_symbols(fresh, ["spy", "SPY", "qqq"], "US_equities", tmp_path / "runs")
    raw = yaml.safe_load(fresh.read_text(encoding="utf-8"))
    assert raw["universe"]["symbols"] == ["SPY", "QQQ"]


def test_real_money_buttons_keep_their_guards(client: Client) -> None:
    status, reply = client.act(action="live_test_order")
    assert status == 400 and "Type YES" in reply["error"]
    status, reply = client.act(action="live_test_order", confirm="YES")
    job = client.wait(reply["job"])
    assert job["code"] == 3 and "REFUSED" in job["output"]  # the gates still decide
    job = client.wait(client.act(action="live_preview")[1]["job"])
    assert "REFUSED" in job["output"] and "exchange keys" in job["output"]
    job = client.wait(client.act(action="live_check")[1]["job"])
    assert "Real money is OFF" in job["output"]


def test_import_and_quit_from_the_page(
    home: Path, tmp_path_factory: pytest.TempPathFactory
) -> None:
    old = tmp_path_factory.mktemp("old")
    (old / "state").mkdir()
    (old / "state" / "paper_account.json").write_text("{}", encoding="utf-8")
    app = webapp.App(config=CONFIG, folder=home, run=main, shell=FakeShell(), system="Windows")
    server = webapp.make_server(app, 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    client = Client(app)
    assert client.act(action="import", path="")[0] == 400
    status, reply = client.act(action="import", path=f'"{old}"')
    assert status == 200 and "OLD folder is now stopped" in reply["message"]
    assert KillSwitch(old / "state" / "kill_switch.json").engaged
    status, reply = client.act(action="import", path=str(old))
    assert status == 400 and "already brought over once" in reply["error"]
    assert webapp._running_here(app.port, home) and not webapp._running_here(app.port, old)
    assert client.act(action="quit")[0] == 200
    thread.join(5)
    assert not thread.is_alive()  # the server stopped
    server.server_close()


def test_a_broken_settings_file_is_shown_not_fatal(client: Client, home: Path) -> None:
    (home / CONFIG).write_text("risk:\n  max_daily_loss_pct: -5\n", encoding="utf-8")
    status, data = client.get("/api/status")
    assert status == 200 and "has a problem" in data["errors"][0]


def test_score_series_for_the_chart(tmp_path: Path) -> None:
    from quantagents.ops import score_series

    def cycle(day: str, equity: float, a: float) -> dict[str, Any]:
        return {"as_of": day, "equity": equity, "snapshot": {"last_close": {"AAA": a}}}

    cycles = [cycle("2026-10-01", 10_000, 100), cycle("2026-10-02", 10_100, 110)]
    assert score_series(cycles, None, 10_000) == [
        ("2026-10-01", 0.0, 0.0),
        ("2026-10-02", pytest.approx(0.01), pytest.approx(0.10)),
    ]
    assert score_series([], None, 10_000) == []
    assert date.fromisoformat(score_series(cycles, None, 10_000)[-1][0]) == date(2026, 10, 2)


def test_double_clicking_twice_reuses_the_running_app(
    home: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import socket

    with socket.socket() as probe:  # a port that is free right now
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    opened: list[str] = []
    import webbrowser

    monkeypatch.setattr(webbrowser, "open", opened.append)
    first = threading.Thread(
        target=webapp.serve, args=(CONFIG,), kwargs={"port": port, "open_browser": False}
    )
    first.start()
    for _ in range(100):
        if webapp._running_here(port, home.resolve()):
            break
        time.sleep(0.05)
    assert webapp.serve(CONFIG, port=port, open_browser=True) == 0  # no second server
    assert opened == [f"http://127.0.0.1:{port}/"]
    assert "already running for this folder" in capsys.readouterr().out
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    conn.request("GET", "/", headers={"Host": f"127.0.0.1:{port}"})
    key = conn.getresponse().read().decode().split('name="qa-key" content="')[1].split('"')[0]
    conn.request(
        "POST",
        "/api/action",
        body=b'{"action": "quit"}',
        headers={"Host": f"127.0.0.1:{port}", webapp.KEY_HEADER: key},
    )
    assert conn.getresponse().status == 200
    first.join(10)
    assert not first.is_alive() and "QuantAgents stopped." in capsys.readouterr().out
