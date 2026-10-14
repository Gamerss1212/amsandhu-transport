"""The read-only token lets a voice assistant read the system's state and nothing else."""

import pytest
from fastapi.testclient import TestClient

from tradingai.api.server import create_app
from tradingai.app import App


@pytest.fixture()
def client(tmp_path):
    a = App(str(tmp_path / "home"), offline=True, start_loop=False)
    api = create_app(a, token="FULL", read_token="READ")
    yield TestClient(api, base_url="http://127.0.0.1:8000")
    a.shutdown()


R = {"X-TA-Read-Token": "READ"}


def test_the_read_token_reads_the_allowed_pages(client):
    for path in ("/api/overview", "/api/fleet/summary", "/api/system/thermal", "/api/risk", "/api/account",
                 "/api/learning", "/api/orders"):
        assert client.get(path, headers=R).status_code == 200, path


def test_the_read_token_cannot_write_or_reach_credentials(client):
    assert client.post("/api/controls/pause-entries", headers=R, json={"paused": True}).status_code == 401
    assert client.post("/api/system/shutdown", headers=R).status_code == 401
    assert client.post("/api/system/thermal-check", headers=R, json={"minutes": 1}).status_code == 401
    for path in ("/api/connections", "/api/brokers", "/api/audit", "/api/system/autostart", "/api/bots"):
        assert client.get(path, headers=R).status_code == 401, path


def test_a_wrong_or_missing_token_is_refused_and_the_full_token_still_works(client):
    assert client.get("/api/overview", headers={"X-TA-Read-Token": "nope"}).status_code == 401
    assert client.get("/api/overview").status_code == 401
    assert client.get("/api/overview", headers={"X-TA-Token": "FULL"}).status_code == 200
    assert client.get("/api/connections", headers={"X-TA-Token": "FULL"}).status_code == 200
    assert client.get("/api/overview", headers={"X-TA-Token": "READ"}).status_code == 401   # tokens are not interchangeable
