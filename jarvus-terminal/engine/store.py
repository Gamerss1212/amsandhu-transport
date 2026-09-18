#!/usr/bin/env python3
"""SQLite persistence. Every prediction is written down before its outcome is known.

That ordering is the whole point. A system that records what it thought only after
seeing what happened cannot be held to account, and almost all trading software is
built that way: it shows you a signal, the signal scrolls off the screen, and nobody
ever checks. Here each scan commits its claims first, with the thresholds that will
later decide whether the claim was right, and a separate pass grades them.
"""

from __future__ import annotations

import os
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import config

_local = threading.local()

SCHEMA = """
CREATE TABLE IF NOT EXISTS predictions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    made_at TEXT NOT NULL,              -- UTC ISO, when we committed to this
    resolve_at TEXT NOT NULL,           -- UTC ISO, when it becomes gradeable
    symbol TEXT NOT NULL,
    venue TEXT,
    price REAL NOT NULL,
    gate_label TEXT,
    blow_score REAL,
    energy REAL,
    expansion REAL,
    compression REAL,
    atr_pct REAL,
    big_move_threshold REAL,            -- forward range % that counts as "big", fixed now
    confluence_score INTEGER,
    confluence_max INTEGER,
    grade TEXT,
    verdict TEXT,
    cost_r REAL,
    -- filled in by the resolver, later
    resolved_at TEXT,
    realized_range_pct REAL,
    realized_change_pct REAL,
    big_move INTEGER,                   -- 1 if realized range cleared the threshold
    direction_up INTEGER,               -- 1 if price finished higher
    resolve_error TEXT
);
CREATE INDEX IF NOT EXISTS idx_pred_resolve ON predictions(resolved_at, resolve_at);
CREATE INDEX IF NOT EXISTS idx_pred_symbol ON predictions(symbol, made_at);

CREATE TABLE IF NOT EXISTS scans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    markets_discovered INTEGER,
    markets_analysed INTEGER,
    predictions_written INTEGER,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS journal (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    opened_at TEXT NOT NULL,
    symbol TEXT NOT NULL,
    entry REAL, stop REAL, target REAL,
    risk_pct REAL, units REAL,
    grade TEXT, gate_label TEXT, cost_r REAL,
    closed_at TEXT, exit_price REAL, r_multiple REAL, notes TEXT
);
"""


def conn() -> sqlite3.Connection:
    """One connection per thread; the HTTP server is threaded."""
    c = getattr(_local, "conn", None)
    if c is None:
        os.makedirs(os.path.dirname(config.DB_PATH), exist_ok=True)
        c = sqlite3.connect(config.DB_PATH, timeout=30)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL")
        c.executescript(SCHEMA)
        _local.conn = c
    return c


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def start_scan() -> int:
    c = conn()
    cur = c.execute("INSERT INTO scans(started_at) VALUES(?)", (now_iso(),))
    c.commit()
    return cur.lastrowid


def finish_scan(scan_id: int, discovered: int, analysed: int, written: int, notes: str = "") -> None:
    c = conn()
    c.execute("UPDATE scans SET finished_at=?, markets_discovered=?, markets_analysed=?, "
              "predictions_written=?, notes=? WHERE id=?",
              (now_iso(), discovered, analysed, written, notes, scan_id))
    c.commit()


def write_prediction(row: Dict[str, Any]) -> None:
    cols = ("made_at", "resolve_at", "symbol", "venue", "price", "gate_label", "blow_score",
            "energy", "expansion", "compression", "atr_pct", "big_move_threshold",
            "confluence_score", "confluence_max", "grade", "verdict", "cost_r")
    c = conn()
    c.execute(f"INSERT INTO predictions({','.join(cols)}) VALUES({','.join('?' * len(cols))})",
              tuple(row.get(k) for k in cols))
    c.commit()


def write_predictions(rows: List[Dict[str, Any]]) -> int:
    for r in rows:
        write_prediction(r)
    return len(rows)


def due_for_resolution(limit: int = 200) -> List[sqlite3.Row]:
    return conn().execute(
        "SELECT * FROM predictions WHERE resolved_at IS NULL AND resolve_at <= ? "
        "ORDER BY resolve_at LIMIT ?", (now_iso(), limit)).fetchall()


def resolve(pred_id: int, realized_range_pct: Optional[float], realized_change_pct: Optional[float],
            threshold: Optional[float], error: str = None) -> None:
    c = conn()
    if error:
        c.execute("UPDATE predictions SET resolved_at=?, resolve_error=? WHERE id=?",
                  (now_iso(), error, pred_id))
    else:
        big = 1 if (threshold is not None and realized_range_pct is not None
                    and realized_range_pct >= threshold) else 0
        up = 1 if (realized_change_pct or 0) > 0 else 0
        c.execute("UPDATE predictions SET resolved_at=?, realized_range_pct=?, realized_change_pct=?, "
                  "big_move=?, direction_up=? WHERE id=?",
                  (now_iso(), realized_range_pct, realized_change_pct, big, up, pred_id))
    c.commit()


def resolved(limit: int = 5000) -> List[sqlite3.Row]:
    return conn().execute(
        "SELECT * FROM predictions WHERE resolved_at IS NOT NULL AND resolve_error IS NULL "
        "ORDER BY made_at DESC LIMIT ?", (limit,)).fetchall()


def counts() -> Dict[str, int]:
    c = conn()
    q = lambda sql: c.execute(sql).fetchone()[0]
    return {
        "predictions_total": q("SELECT COUNT(*) FROM predictions"),
        "pending": q("SELECT COUNT(*) FROM predictions WHERE resolved_at IS NULL"),
        "resolved": q("SELECT COUNT(*) FROM predictions WHERE resolved_at IS NOT NULL AND resolve_error IS NULL"),
        "failed": q("SELECT COUNT(*) FROM predictions WHERE resolve_error IS NOT NULL"),
        "scans": q("SELECT COUNT(*) FROM scans"),
        "journal_open": q("SELECT COUNT(*) FROM journal WHERE closed_at IS NULL"),
        "journal_closed": q("SELECT COUNT(*) FROM journal WHERE closed_at IS NOT NULL"),
    }


def recent_predictions(symbol: str = None, limit: int = 50) -> List[sqlite3.Row]:
    if symbol:
        return conn().execute("SELECT * FROM predictions WHERE symbol=? ORDER BY made_at DESC LIMIT ?",
                              (symbol, limit)).fetchall()
    return conn().execute("SELECT * FROM predictions ORDER BY made_at DESC LIMIT ?", (limit,)).fetchall()


# --- journal ---------------------------------------------------------------

def journal_add(row: Dict[str, Any]) -> int:
    cols = ("opened_at", "symbol", "entry", "stop", "target", "risk_pct", "units", "grade",
            "gate_label", "cost_r", "notes")
    c = conn()
    cur = c.execute(f"INSERT INTO journal({','.join(cols)}) VALUES({','.join('?' * len(cols))})",
                    tuple(row.get(k) for k in cols))
    c.commit()
    return cur.lastrowid


def journal_close(jid: int, exit_price: float, notes: str = "") -> Optional[float]:
    c = conn()
    r = c.execute("SELECT entry, stop FROM journal WHERE id=?", (jid,)).fetchone()
    if not r:
        return None
    risk = abs(r["entry"] - r["stop"])
    rmult = (exit_price - r["entry"]) / risk if risk else 0.0
    c.execute("UPDATE journal SET closed_at=?, exit_price=?, r_multiple=?, "
              "notes=COALESCE(notes,'')||? WHERE id=?",
              (now_iso(), exit_price, rmult, (" | " + notes) if notes else "", jid))
    c.commit()
    return rmult


def journal_rows(limit: int = 200) -> List[sqlite3.Row]:
    return conn().execute("SELECT * FROM journal ORDER BY opened_at DESC LIMIT ?", (limit,)).fetchall()
