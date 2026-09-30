"""Provider adapters against contract fakes over real HTTP (Alpaca), plus request-building checks for Kraken."""

import os
import sys
import urllib.parse

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from alpaca_fake import KEY, SECRET, FakeAlpaca, serve  # noqa: E402
from mab.execution.alpaca import Alpaca, oauth_authorize_url  # noqa: E402
from mab.execution.base import AuthError, OrderRejected, OrderRequest, uuid_for  # noqa: E402
from mab.execution.engine import ExecutionEngine  # noqa: E402
from mab.execution.kraken import Kraken  # noqa: E402
from mab.execution.router import Router  # noqa: E402
from mab.storage import Storage  # noqa: E402


@pytest.fixture()
def alpaca(tmp_path):
    fake = FakeAlpaca()
    httpd = serve(fake)
    url = f"http://127.0.0.1:{httpd.server_address[1]}"
    p = Alpaca("paper", KEY, SECRET, base_url=url, data_url=url)
    st = Storage(str(tmp_path / "w.db"))
    eng = ExecutionEngine(st, lambda c: p, sleep=lambda s: None)
    alerts = []
    r = Router(eng, st, lambda c: p, alert=lambda *a: alerts.append(a))
    yield fake, p, st, eng, r, alerts
    httpd.shutdown()


DEP = {"deployment_id": "dep-1", "bot_id": "U-1", "mode": "paper", "connection_id": "alpaca-paper"}


def posts(fake):
    return [b for m, path, b, h in fake.requests if m == "POST" and path == "/v2/orders"]


def test_authenticate_masks_account_and_reports_paper(alpaca):
    fake, p, *_ = alpaca
    a = p.authenticate()
    assert a["ok"] and a["account_id"] == "...1234" and a["permissions"]["withdraw"] is False
    assert "paper account" in " ".join(a["notes"])
    acct = p.account()
    assert acct["buying_power"] == 100_000.0 and acct["currency"] == "USD"
    hdrs = {k.lower(): v for k, v in fake.requests[-1][3].items()}
    assert hdrs.get("apca-api-key-id") == KEY


def test_wrong_keys_are_an_auth_error(alpaca):
    fake, p, *_ = alpaca
    bad = Alpaca("paper", "PKWRONG", "nope", base_url=p.base, data_url=p.data)
    with pytest.raises(AuthError):
        bad.authenticate()


def test_oauth_token_is_sent_as_bearer(alpaca):
    fake, p, *_ = alpaca
    tok = Alpaca("paper", token="oauth-token-123", base_url=p.base, data_url=p.data)
    assert tok.authenticate()["ok"]
    assert {k.lower(): v for k, v in fake.requests[-1][3].items()}.get("authorization") == "Bearer oauth-token-123"
    u = urllib.parse.urlparse(oauth_authorize_url("cid", "http://127.0.0.1:8787/cb", "st8", "paper"))
    q = urllib.parse.parse_qs(u.query)
    assert u.netloc == "app.alpaca.markets" and q["env"] == ["paper"] and q["response_type"] == ["code"]
    assert set(q["scope"][0].split()) == {"account:write", "trading", "data"}


def test_crypto_entry_is_capped_ioc_and_protected_by_stop_limit(alpaca):
    fake, p, st, eng, r, alerts = alpaca
    res = r.enter(DEP, symbol="coinbase:BTC-USD", side=1, qty=0.02, ref_price=65000.0, stop=62000.0, target=None,
                  intent_id="i1")
    assert res["status"] == "filled", res
    entry, stop = posts(fake)
    assert entry["type"] == "limit" and entry["time_in_force"] == "ioc" and entry["symbol"] == "BTC/USD"
    assert float(entry["limit_price"]) > 65010.0 and entry["client_order_id"].startswith("jv-en-")
    assert stop["type"] == "stop_limit" and stop["time_in_force"] == "gtc"
    assert float(stop["limit_price"]) < float(stop["stop_price"])
    pos = r.position("dep-1")
    assert pos["qty"] < float(entry["qty"])                          # the fee came out of the coins
    assert float(stop["qty"]) == pytest.approx(pos["qty"], rel=1e-6)
    assert pos["fees"] > 0                                           # and is counted as a cost


def test_stock_entry_is_whole_shares_with_gtc_stop(alpaca):
    fake, p, st, eng, r, alerts = alpaca
    res = r.enter(DEP, symbol="yahoo:AAPL", side=1, qty=3.7, ref_price=200.0, stop=190.0, target=None, intent_id="s1")
    assert res["status"] == "filled"
    entry, stop = posts(fake)
    assert entry["qty"] == "3" and entry["time_in_force"] == "ioc"
    assert stop["type"] == "stop" and stop["time_in_force"] == "gtc" and stop["qty"] == "3"
    small = r.enter(dict(DEP, deployment_id="dep-2"), symbol="yahoo:AAPL", side=1, qty=0.4, ref_price=200.0, stop=190.0,
                    target=None, intent_id="s2")
    assert small["status"] == "skipped" and "one share" in small["reason"]


def test_fractional_stock_order_outside_day_is_refused_before_sending(alpaca):
    fake, p, *_ = alpaca
    with pytest.raises(OrderRejected):
        p.submit(OrderRequest("jv-x", "yahoo:AAPL", "buy", "limit", 1.5, 201.0, tif="ioc"))
    assert not posts(fake)


def test_lost_response_is_found_by_client_id_not_resent(alpaca):
    fake, p, st, eng, r, alerts = alpaca
    fake.drop_next_response = True
    o = eng.place(connection_id="alpaca-paper", mode="paper", purpose="entry", symbol="coinbase:BTC-USD", side="buy",
                  order_type="limit", qty=0.01, limit_price=65100.0, tif="ioc", intent_id="lost1",
                  deployment_id="dep-1", ref_price=65010.0)
    assert o["state"] == "FILLED" and len(posts(fake)) == 1
    assert any(path == "/v2/orders:by_client_order_id" for _, path, _, _ in fake.requests)


def test_insufficient_buying_power_is_a_rejection(alpaca):
    fake, p, st, eng, r, alerts = alpaca
    o = eng.place(connection_id="alpaca-paper", mode="paper", purpose="entry", symbol="yahoo:AAPL", side="buy",
                  order_type="limit", qty=1000, limit_price=201.0, tif="ioc", intent_id="big", deployment_id="dep-1")
    assert o["state"] == "REJECTED" and "insufficient buying power" in o["reason"]


def test_stop_fill_and_exit_paths(alpaca):
    fake, p, st, eng, r, alerts = alpaca
    r.enter(DEP, symbol="yahoo:AAPL", side=1, qty=5, ref_price=200.0, stop=190.0, target=None, intent_id="s1")
    fake.trigger_stops(189.5)
    out = r.poll_stop(DEP)
    assert out["status"] == "filled" and r.position("dep-1") is None
    # a second position closed by the bot: the stop is canceled on the broker before selling
    d2 = dict(DEP, deployment_id="dep-2")
    r.enter(d2, symbol="yahoo:AAPL", side=1, qty=5, ref_price=200.0, stop=190.0, target=None, intent_id="s2")
    out = r.exit(d2, ref_price=200.0, reason="exit rule", intent_id="x2")
    assert out["status"] == "filled"
    assert any(m == "DELETE" for m, *_ in fake.requests)
    sells = [b for b in posts(fake) if b["side"] == "sell" and b["type"] == "limit"]
    assert sells and sells[-1]["time_in_force"] == "ioc"


def test_working_order_cancel_and_partial(alpaca):
    fake, p, st, eng, r, alerts = alpaca
    fake.hold_new_orders = True
    o = eng.place(connection_id="alpaca-paper", mode="paper", purpose="entry", symbol="yahoo:AAPL", side="buy",
                  order_type="limit", qty=2, limit_price=150.0, tif="gtc", intent_id="w1", deployment_id="dep-1")
    assert o["state"] == "ACKED"
    out = r.cancel_entries("dep-1", "operator stop")
    assert out[0]["state"] == "CANCELED"


def test_kraken_requests_carry_a_uuid_client_id_and_validate_flag():
    sent = []

    def transport(method, url, headers, body):
        sent.append((method, url, headers, body))
        if "AssetPairs" in url:
            return 200, b'{"error":[],"result":{"XXBTZCAD":{"altname":"XBTCAD","ordermin":"0.0001","lot_decimals":8,' \
                        b'"tick_size":"0.1","costmin":"0.5","base":"XXBT","quote":"ZCAD","status":"online"}}}', {}
        return 200, b'{"error":[],"result":{"descr":{"order":"buy 0.01 XBTCAD @ limit 90000.0"}}}', {}
    k = Kraken("key", "c2VjcmV0", quote="CAD", transport=transport)
    req = OrderRequest("jv-en-abc", "coinbase:BTC-USD", "buy", "limit", 0.01, 90000.04, tif="ioc")
    assert k.validate(req)["ok"]
    body = urllib.parse.parse_qs(sent[-1][3].decode())
    assert body["validate"] == ["true"] and body["cl_ord_id"] == [uuid_for("jv-en-abc")]
    assert body["timeinforce"] == ["IOC"] and body["oflags"] == ["fciq"] and body["pair"] == ["XBTCAD"]
    assert body["price"] == ["90000.0"]
    assert "API-Sign" in sent[-1][2]


# ---------------------------------------------------------------------------------------- vault and connections
def test_vault_encrypts_binds_names_and_detects_tampering(tmp_path, monkeypatch):
    import json as _json
    from mab import crypto_box, secrets_store
    monkeypatch.setenv("MAB_SECRETS_DIR", str(tmp_path / "vault"))
    secrets_store.set_secret("ws:main:conn:a:key", "PKSECRETVALUE123")
    raw = open(tmp_path / "vault" / "vault.json").read()
    assert "PKSECRETVALUE123" not in raw
    assert secrets_store.get_secret("ws:main:conn:a:key") == "PKSECRETVALUE123"
    v = _json.loads(raw)
    v["ws:main:conn:b:key"] = v["ws:main:conn:a:key"]                  # copy a blob into another slot
    open(tmp_path / "vault" / "vault.json", "w").write(_json.dumps(v))
    with pytest.raises(crypto_box.DecryptError):
        secrets_store.get_secret("ws:main:conn:b:key")
    key = b"k" * 32
    blob = crypto_box.seal(key, b"hello", b"n")
    bad = blob[:-6] + ("A" if blob[-6] != "A" else "B") + blob[-5:]
    with pytest.raises(crypto_box.DecryptError):
        crypto_box.open_(key, bad, b"n")
    assert crypto_box.open_(key, blob, b"n") == b"hello"
    assert secrets_store.delete_prefix("ws:main:conn:") == 2


def test_legacy_per_value_secrets_move_into_the_vault(tmp_path, monkeypatch):
    import base64 as _b64
    import json as _json
    from mab import secrets_store
    d = tmp_path / "old"
    d.mkdir()
    monkeypatch.setenv("MAB_SECRETS_DIR", str(d))
    (d / "secrets.json").write_text(_json.dumps({"broker:kraken:key": {"backend": "file",
                                                                        "blob": _b64.b64encode(b"OLDKEY123").decode()}}))
    assert secrets_store.get_secret("broker:kraken:key") == "OLDKEY123"
    assert "broker:kraken:key" not in _json.loads((d / "secrets.json").read_text())
    assert "OLDKEY123" not in (d / "vault.json").read_text()


def _rewrite_to(url):
    from mab.execution.base import http_transport
    inner = http_transport(5)

    def send(method, u, headers, body):
        for real in ("https://paper-api.alpaca.markets", "https://api.alpaca.markets", "https://data.alpaca.markets"):
            u = u.replace(real, url)
        return inner(method, u, headers, body)
    return send


def test_connection_lifecycle_never_exposes_credentials(tmp_path, monkeypatch):
    from mab.connections import Connections
    monkeypatch.setenv("MAB_SECRETS_DIR", str(tmp_path / "vault"))
    fake = FakeAlpaca()
    httpd = serve(fake)
    try:
        st = Storage(str(tmp_path / "c.db"))
        conns = Connections(st, "main", transport=_rewrite_to(f"http://127.0.0.1:{httpd.server_address[1]}"))
        conns.ensure_defaults()
        c = conns.create("alpaca", "paper", {"key": KEY, "secret": SECRET})
        assert c["connection_id"] == "alpaca-paper" and c["status"] == "untested" and c["has_credentials"]
        assert KEY not in str(c) and SECRET not in str(conns.list())
        res = conns.test("alpaca-paper")
        assert res["ok"], res
        ids = {x["id"]: x["status"] for x in res["checks"]}
        assert ids["auth"] == ids["account"] == ids["trading"] == "pass" and ids["withdraw"] == "pass"
        c = conns.get("alpaca-paper")
        assert c["status"] == "connected" and c["account"]["account_id"] == "...1234" and c["last_sync"]
        assert conns.latest("alpaca-paper")["buying_power"] == 100_000.0
        assert SECRET not in str(st.query("SELECT * FROM audit_events")) and SECRET not in str(st.query("SELECT * FROM connections"))
        with pytest.raises(ValueError):
            conns.create("alpaca", "sandbox", {"key": "a", "secret": "b"})
        with pytest.raises(ValueError):
            conns.create("kraken", "paper", {"key": "a", "secret": "b"})     # Kraken has no spot sandbox
        with pytest.raises(ValueError):
            conns.disconnect("alpaca-paper", active_deployments=1)
        conns.disconnect("alpaca-paper")
        assert not conns.get("alpaca-paper")["has_credentials"]
        with pytest.raises(ValueError):
            conns.disconnect("paper-main")
        f = conns.funding("paper-main")
        assert f["simulated"] and f["url"] is None
    finally:
        httpd.shutdown()


def test_bad_credentials_fail_the_test_and_say_why(tmp_path, monkeypatch):
    from mab.connections import Connections
    monkeypatch.setenv("MAB_SECRETS_DIR", str(tmp_path / "vault"))
    fake = FakeAlpaca()
    httpd = serve(fake)
    try:
        st = Storage(str(tmp_path / "c.db"))
        conns = Connections(st, "main", transport=_rewrite_to(f"http://127.0.0.1:{httpd.server_address[1]}"))
        conns.create("alpaca", "paper", {"key": "PKWRONG", "secret": "nope"})
        res = conns.test("alpaca-paper")
        assert not res["ok"]
        assert conns.get("alpaca-paper")["status"] == "error" and "not authorised" in conns.get("alpaca-paper")["last_error"]
    finally:
        httpd.shutdown()
