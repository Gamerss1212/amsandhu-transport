"""Schema migrations and the audit log."""

import os
import sqlite3
import sys
import threading

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mab import migrations  # noqa: E402
from mab.storage import Storage, sanitize  # noqa: E402


def test_fresh_database_gets_every_migration(tmp_path):
    st = Storage(str(tmp_path / "a.db"))
    assert st.migrated == [v for v, _, _ in migrations.MIGRATIONS]
    tables = {r["name"] for r in st.query("SELECT name FROM sqlite_master WHERE type='table'")}
    for t in ("audit_events", "deployments", "broker_orders", "order_events", "broker_fills", "connections",
              "research_jobs", "strategy_versions", "model_versions", "trades", "kv"):
        assert t in tables
    assert Storage(str(tmp_path / "a.db")).migrated == []            # re-open: nothing to do


def test_legacy_database_is_adopted_backed_up_and_labelled(tmp_path):
    p = str(tmp_path / "old.db")
    c = sqlite3.connect(p)
    c.executescript(migrations.V1)
    c.execute("INSERT INTO trades (bot_id, entry_reason, pnl) VALUES ('A', '[LIVE] breakout', 1.0), ('B', 'rule', 2.0)")
    c.commit()
    c.close()
    st = Storage(p)
    assert st.migrated == [1, 2]
    modes = {r["bot_id"]: r["mode"] for r in st.query("SELECT bot_id, mode FROM trades")}
    assert modes == {"A": "live", "B": "paper"}
    assert any(f.startswith("pre-migration-v1") for f in os.listdir(tmp_path / "backups"))


def test_changed_migration_is_refused(tmp_path):
    p = str(tmp_path / "c.db")
    Storage(p).close()
    c = sqlite3.connect(p)
    c.execute("UPDATE schema_migrations SET checksum='tampered' WHERE version=2")
    c.commit()
    c.close()
    with pytest.raises(RuntimeError):
        Storage(p)


def test_failed_migration_rolls_back(tmp_path, monkeypatch):
    p = str(tmp_path / "d.db")
    bad = list(migrations.MIGRATIONS) + [(99, "broken", ["CREATE TABLE zz (a INT)", "THIS IS NOT SQL"])]
    monkeypatch.setattr(migrations, "MIGRATIONS", bad)
    with pytest.raises(sqlite3.OperationalError):
        Storage(p)
    c = sqlite3.connect(p)
    names = {r[0] for r in c.execute("SELECT name FROM sqlite_master")}
    assert "zz" not in names                                          # the half-applied step was undone
    assert [r[0] for r in c.execute("SELECT version FROM schema_migrations")] == [1, 2]


def test_concurrent_openers_migrate_once(tmp_path):
    p = str(tmp_path / "e.db")
    errors = []

    def open_it():
        try:
            Storage(p)
        except Exception as e:                                        # noqa: BLE001
            errors.append(e)
    ts = [threading.Thread(target=open_it) for _ in range(6)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert not errors
    c = sqlite3.connect(p)
    assert [r[0] for r in c.execute("SELECT version FROM schema_migrations")] == [1, 2]


def test_audit_log_sanitises_and_streams_in_order(tmp_path):
    st = Storage(str(tmp_path / "f.db"))
    seen = []
    st.audit_hook = seen.append
    a = st.audit("signal", "entry rule true", stage="signal", bot_id="B1", correlation_id="k1",
                 payload={"api_key": "PK123", "secret": "zzz", "rules": [{"rule": "close > ema21", "passed": True}]})
    b = st.audit("order", "buy submitted with key AbCdEfGhIjKlMnOp1234567890QrStUvWx", stage="order_submitted",
                 correlation_id="k1", order_id="jv-1")
    st.audit("control", "paused", severity="warning")
    rows = st.audit_since(0)
    assert [r["id"] for r in rows] == [a, b, a + 2]
    assert rows[0]["payload"]["api_key"] == "[removed]" and rows[0]["payload"]["secret"] == "[removed]"
    assert rows[0]["payload"]["rules"][0]["rule"] == "close > ema21"
    assert "[masked]" in rows[1]["summary"]
    assert [e["id"] for e in seen] == [a, b, a + 2]
    assert [r["stage"] for r in st.lifecycle("k1")] == ["signal", "order_submitted"]
    assert st.audit_since(a) and st.audit_since(0, min_severity="warning")[0]["kind"] == "control"
    assert st.audit_search(text="buy", kinds=["order"])[0]["id"] == b
    assert st.audit_last_id() == a + 2


def test_sanitize_keeps_hashes_readable():
    h = "0123456789abcdef" * 4
    out = sanitize({"version": h, "token_budget": 5, "Authorization": "Bearer x", "note": "sk-ant-api03-abcdefghijklmnop"})
    assert out["version"] == h and out["token_budget"] == 5
    assert out["Authorization"] == "[removed]" and out["note"] == "[masked]"


def test_sse_stream_resumes_after_last_event_id(tmp_path):
    from mab import stream
    st = Storage(str(tmp_path / "g.db"))
    ids = [st.audit("signal", f"s{i}") for i in range(5)]
    chunks = list(stream.follow(st, last_id=ids[1], snapshot=lambda: {"bots": 1}, max_seconds=0,
                                sleep=lambda s: None))
    text = b"".join(chunks).decode()
    assert text.startswith("retry: 3000")
    assert f"id: {ids[2]}" in text and f"id: {ids[4]}" in text and f"id: {ids[1]}\n" not in text
    assert "event: state" in text
    assert stream.parse_last_id(None, "7") == 7 and stream.parse_last_id("x", None) is None
    assert stream.sse("a\nb") == b"data: a\ndata: b\n\n"
