"""The desk read: one call with everything page 1 shows, computed from real records."""

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from tradingai.api.server import create_app
from tradingai.app import App


@pytest.fixture()
def app(tmp_path):
    a = App(str(tmp_path / "home"), offline=True, start_loop=False)
    yield a
    a.shutdown()


def test_the_desk_has_every_panel_and_starts_at_zero_net(app):
    from tradingai.engine.desk import desk
    d = desk(app)
    for k in ("balance", "net_pnl", "positions", "fills", "decisions", "timeline", "agents", "checks", "control",
              "equity", "system", "hour"):
        assert k in d, k
    assert Decimal(d["net_pnl"]) == 0                                # no trade yet: nothing earned or lost
    assert d["agents"]["target"] == 100 and set(d["agents"]["groups"]) == {"crypto", "meme", "stock"}
    assert sum(g["target"] for g in d["agents"]["groups"].values()) == 100
    assert d["control"]["state"] in ("OPEN", "STANDBY", "PAUSED", "STOPPED", "BLOCKED")


def test_a_balance_change_is_not_counted_as_profit(app):
    from tradingai.engine.desk import desk
    app.set_paper_balance(Decimal(100))
    d = desk(app)
    assert Decimal(d["balance"]) == 100 and Decimal(d["net_pnl"]) == 0


def test_an_emergency_stop_shows_as_blocked(app):
    from tradingai.engine.desk import desk
    app.risk.engage_kill_switch("test", "owner")
    assert desk(app)["control"]["state"] == "BLOCKED"


def test_jarvis_can_read_the_desk_with_the_read_token(app):
    c = TestClient(create_app(app, token="FULL", read_token="READ"), base_url="http://127.0.0.1:8000")
    assert c.get("/api/desk", headers={"X-TA-Read-Token": "READ"}).status_code == 200
