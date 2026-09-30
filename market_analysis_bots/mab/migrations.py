"""Versioned schema migrations for a workspace database.

Every database records which migrations it has in `schema_migrations`. On open, the pending ones run in
order, each inside one write transaction (SQLite DDL is transactional, so a failed migration leaves the
database exactly as it was). Two processes opening the same database at once cannot both migrate it: the
transaction takes the write lock first and re-reads the applied versions inside it.

Databases created by earlier versions of this program (no `schema_migrations` table) are adopted: the
baseline migration only creates what is missing, then the later migrations run. A consistent copy of an
existing database is written to `backups/` before its first pending migration is applied.

Rules for new migrations: append, never edit an applied one (its checksum is recorded and verified), and
keep each step idempotent where SQLite allows it (ADD COLUMN goes through `add_column`, which checks first).
"""

from __future__ import annotations

import hashlib
import os
import sqlite3
import time
from typing import Callable, List, Sequence, Tuple, Union

Step = Union[str, Callable[[sqlite3.Connection], None]]

# ----------------------------------------------------------------------------- v1: the original schema
V1 = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS bars (venue TEXT, instrument TEXT, tf TEXT, t INTEGER, o REAL, h REAL, l REAL, c REAL,
    v REAL, recv INTEGER, prov TEXT, PRIMARY KEY (venue, instrument, tf, t)) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS signals (id INTEGER PRIMARY KEY, bot_id TEXT, strategy_id TEXT, strategy_version TEXT,
    config_version TEXT, instrument TEXT, venue TEXT, tf TEXT, bar_time INTEGER, decision_time INTEGER, action TEXT,
    reason TEXT, features TEXT, rules TEXT);
CREATE INDEX IF NOT EXISTS ix_signals_bot ON signals (bot_id, bar_time);
CREATE TABLE IF NOT EXISTS intents (intent_id TEXT PRIMARY KEY, bot_id TEXT, time INTEGER, body TEXT);
CREATE TABLE IF NOT EXISTS risk_decisions (intent_id TEXT, bot_id TEXT, approved INTEGER, adjusted_qty REAL,
    checks TEXT, time INTEGER);
CREATE INDEX IF NOT EXISTS ix_risk_bot ON risk_decisions (bot_id, time);
CREATE TABLE IF NOT EXISTS orders (order_id TEXT PRIMARY KEY, intent_id TEXT, bot_id TEXT, instrument TEXT,
    venue TEXT, side TEXT, qty REAL, filled_qty REAL, avg_price REAL, status TEXT, reason TEXT, model TEXT,
    time INTEGER);
CREATE TABLE IF NOT EXISTS fills (fill_id TEXT PRIMARY KEY, order_id TEXT, intent_id TEXT, bot_id TEXT,
    instrument TEXT, venue TEXT, side TEXT, qty REAL, price REAL, fee REAL, liquidity TEXT, time INTEGER,
    simulated INTEGER, model TEXT);
CREATE INDEX IF NOT EXISTS ix_fills_bot ON fills (bot_id, time);
CREATE TABLE IF NOT EXISTS trades (id INTEGER PRIMARY KEY, bot_id TEXT, strategy_id TEXT, instrument TEXT,
    venue TEXT, side INTEGER, qty REAL, entry_time INTEGER, entry_price REAL, exit_time INTEGER, exit_price REAL,
    fees REAL, pnl REAL, r REAL, bars INTEGER, entry_reason TEXT, exit_reason TEXT, mfe_r REAL, mae_r REAL);
CREATE INDEX IF NOT EXISTS ix_trades_bot ON trades (bot_id, exit_time);
CREATE TABLE IF NOT EXISTS bot_state (bot_id TEXT PRIMARY KEY, state TEXT, updated INTEGER);
CREATE TABLE IF NOT EXISTS bot_health (time INTEGER, bot_id TEXT, state TEXT, last_eval INTEGER, last_data INTEGER,
    last_decision TEXT, errors INTEGER, message TEXT);
CREATE INDEX IF NOT EXISTS ix_health_time ON bot_health (time);
CREATE TABLE IF NOT EXISTS system_health (time INTEGER PRIMARY KEY, body TEXT);
CREATE TABLE IF NOT EXISTS equity (time INTEGER PRIMARY KEY, equity REAL, cash REAL, gross REAL, twr REAL);
CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY, time INTEGER, level TEXT, kind TEXT, bot_id TEXT,
    message TEXT, body TEXT);
CREATE INDEX IF NOT EXISTS ix_events_time ON events (time);
CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT, updated INTEGER);
CREATE TABLE IF NOT EXISTS cash_flows (id INTEGER PRIMARY KEY, time INTEGER, kind TEXT, amount REAL,
    equity_before REAL, equity_after REAL, note TEXT);
CREATE TABLE IF NOT EXISTS control (id INTEGER PRIMARY KEY, time INTEGER, command TEXT, args TEXT,
    status TEXT DEFAULT 'pending', result TEXT, done INTEGER);
CREATE TABLE IF NOT EXISTS experiments (experiment_id TEXT PRIMARY KEY, created INTEGER, kind TEXT, spec TEXT,
    code_version TEXT, summary TEXT);
CREATE TABLE IF NOT EXISTS evaluation_results (id INTEGER PRIMARY KEY, experiment_id TEXT, strategy_id TEXT,
    strategy_version TEXT, instrument TEXT, tf TEXT, period TEXT, config TEXT, dataset TEXT, metrics TEXT,
    code_version TEXT, seed INTEGER, created INTEGER);
CREATE INDEX IF NOT EXISTS ix_eval_strategy ON evaluation_results (strategy_id, period);
"""

# ----------------------------------------------------------------------------- v2: the three-page application
V2 = """
-- Append-only record of everything the bots and the owner did, in order: market update, signal, risk
-- decision, order submission, broker acknowledgement, fills, position management, exit; plus controls,
-- connections, research and data-quality events. correlation_id ties one decision's whole lifecycle together.
CREATE TABLE IF NOT EXISTS audit_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts INTEGER NOT NULL,
    kind TEXT NOT NULL,
    stage TEXT,
    severity TEXT NOT NULL DEFAULT 'info',
    mode TEXT,
    bot_id TEXT,
    deployment_id TEXT,
    symbol TEXT,
    venue TEXT,
    connection_id TEXT,
    correlation_id TEXT,
    order_id TEXT,
    summary TEXT NOT NULL,
    payload TEXT
);
CREATE INDEX IF NOT EXISTS ix_audit_ts ON audit_events (ts);
CREATE INDEX IF NOT EXISTS ix_audit_bot ON audit_events (bot_id, id);
CREATE INDEX IF NOT EXISTS ix_audit_deploy ON audit_events (deployment_id, id);
CREATE INDEX IF NOT EXISTS ix_audit_corr ON audit_events (correlation_id);
CREATE INDEX IF NOT EXISTS ix_audit_kind ON audit_events (kind, id);

-- Bots the owner built from a strategy and a market (the research fleet's bots come from the registry file).
CREATE TABLE IF NOT EXISTS user_bots (
    bot_id TEXT PRIMARY KEY,
    name TEXT,
    strategy_id TEXT NOT NULL,
    venue TEXT NOT NULL,
    instrument TEXT NOT NULL,
    params TEXT,
    source_bot TEXT,
    created INTEGER,
    archived INTEGER NOT NULL DEFAULT 0
);

-- A bot started by the owner: one mode (demo, paper or live), one account connection, its own capital
-- allocation and risk limits. At most one active deployment per bot.
CREATE TABLE IF NOT EXISTS deployments (
    deployment_id TEXT PRIMARY KEY,
    bot_id TEXT NOT NULL,
    mode TEXT NOT NULL,
    connection_id TEXT NOT NULL,
    state TEXT NOT NULL,
    allocation REAL NOT NULL,
    currency TEXT,
    limits TEXT NOT NULL,
    strategy_version TEXT,
    config_version TEXT,
    brain_version TEXT,
    created INTEGER,
    updated INTEGER,
    started INTEGER,
    stopped INTEGER,
    stop_reason TEXT,
    readiness TEXT,
    confirmation TEXT
);
CREATE INDEX IF NOT EXISTS ix_deploy_bot ON deployments (bot_id, state);

-- The execution engine's order book. Write-ahead: the row exists (state NEW) before anything is sent, so a
-- crash can never leave an order the program does not know about. client_order_id is the idempotency key.
CREATE TABLE IF NOT EXISTS broker_orders (
    client_order_id TEXT PRIMARY KEY,
    broker_order_id TEXT,
    connection_id TEXT NOT NULL,
    mode TEXT NOT NULL,
    deployment_id TEXT,
    bot_id TEXT,
    intent_id TEXT,
    correlation_id TEXT,
    purpose TEXT,
    symbol TEXT NOT NULL,
    broker_symbol TEXT,
    side TEXT NOT NULL,
    order_type TEXT NOT NULL,
    tif TEXT,
    qty REAL NOT NULL,
    limit_price REAL,
    stop_price REAL,
    reduce_only INTEGER NOT NULL DEFAULT 0,
    state TEXT NOT NULL,
    filled_qty REAL NOT NULL DEFAULT 0,
    avg_price REAL,
    fees REAL NOT NULL DEFAULT 0,
    fee_currency TEXT,
    reason TEXT,
    attempts INTEGER NOT NULL DEFAULT 0,
    ref_price REAL,
    created INTEGER,
    submitted INTEGER,
    acked INTEGER,
    updated INTEGER,
    closed INTEGER,
    flags TEXT,
    raw TEXT
);
CREATE INDEX IF NOT EXISTS ix_border_state ON broker_orders (state);
CREATE INDEX IF NOT EXISTS ix_border_deploy ON broker_orders (deployment_id, created);
CREATE INDEX IF NOT EXISTS ix_border_broker ON broker_orders (connection_id, broker_order_id);
CREATE INDEX IF NOT EXISTS ix_border_intent ON broker_orders (intent_id);

CREATE TABLE IF NOT EXISTS order_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_order_id TEXT NOT NULL,
    ts INTEGER NOT NULL,
    from_state TEXT,
    to_state TEXT NOT NULL,
    detail TEXT
);
CREATE INDEX IF NOT EXISTS ix_oevents_order ON order_events (client_order_id, id);

CREATE TABLE IF NOT EXISTS broker_fills (
    fill_id TEXT PRIMARY KEY,
    client_order_id TEXT NOT NULL,
    connection_id TEXT,
    mode TEXT,
    deployment_id TEXT,
    bot_id TEXT,
    symbol TEXT,
    side TEXT,
    qty REAL,
    price REAL,
    fee REAL,
    fee_currency TEXT,
    liquidity TEXT,
    ts INTEGER,
    simulated INTEGER,
    ref_price REAL,
    slippage_bps REAL,
    raw TEXT
);
CREATE INDEX IF NOT EXISTS ix_bfills_order ON broker_fills (client_order_id);
CREATE INDEX IF NOT EXISTS ix_bfills_deploy ON broker_fills (deployment_id, ts);
CREATE INDEX IF NOT EXISTS ix_bfills_symbol ON broker_fills (symbol, ts);

-- What each deployment holds, as the execution engine knows it from its own fills, with its protective stop.
CREATE TABLE IF NOT EXISTS exec_positions (
    deployment_id TEXT PRIMARY KEY,
    bot_id TEXT,
    connection_id TEXT,
    mode TEXT,
    symbol TEXT,
    broker_symbol TEXT,
    side INTEGER,
    qty REAL,
    avg_price REAL,
    fees REAL,
    opened INTEGER,
    entry_order TEXT,
    stop_price REAL,
    stop_order TEXT,
    target_price REAL,
    managed INTEGER NOT NULL DEFAULT 1,
    status TEXT,
    ratio REAL,
    updated INTEGER
);

-- What the broker says the account holds (for reconciliation).
CREATE TABLE IF NOT EXISTS broker_positions (
    connection_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    qty REAL,
    avg_price REAL,
    market_value REAL,
    unrealized_pnl REAL,
    synced INTEGER,
    raw TEXT,
    PRIMARY KEY (connection_id, symbol)
);

-- Account connections. Credentials are never stored here: they live in the encrypted secret store, keyed by
-- connection id. account/permissions hold only what the provider reports publicly (masked account number,
-- currency, status, trading permissions).
CREATE TABLE IF NOT EXISTS connections (
    connection_id TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    environment TEXT NOT NULL,
    label TEXT,
    auth_method TEXT,
    status TEXT,
    options TEXT,
    account TEXT,
    permissions TEXT,
    capabilities TEXT,
    last_sync INTEGER,
    last_test TEXT,
    last_error TEXT,
    created INTEGER,
    updated INTEGER,
    enabled INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS connection_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    connection_id TEXT NOT NULL,
    ts INTEGER NOT NULL,
    equity REAL,
    cash REAL,
    buying_power REAL,
    currency TEXT,
    latency_ms REAL,
    body TEXT
);
CREATE INDEX IF NOT EXISTS ix_csnap ON connection_snapshots (connection_id, ts);

-- Account equity over time, per connection (paper accounts and broker accounts are never mixed).
CREATE TABLE IF NOT EXISTS account_equity (
    connection_id TEXT NOT NULL,
    ts INTEGER NOT NULL,
    mode TEXT,
    equity REAL,
    cash REAL,
    exposure REAL,
    realized REAL,
    unrealized REAL,
    PRIMARY KEY (connection_id, ts)
);

CREATE TABLE IF NOT EXISTS research_jobs (
    job_id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    spec TEXT NOT NULL,
    spec_hash TEXT NOT NULL,
    state TEXT NOT NULL,
    priority INTEGER NOT NULL DEFAULT 5,
    created INTEGER,
    started INTEGER,
    finished INTEGER,
    worker TEXT,
    progress REAL,
    message TEXT,
    result TEXT,
    error TEXT,
    cached INTEGER NOT NULL DEFAULT 0,
    requested_by TEXT,
    cpu_s REAL,
    peak_mb REAL
);
CREATE INDEX IF NOT EXISTS ix_rjobs_state ON research_jobs (state, priority, created);

CREATE TABLE IF NOT EXISTS research_cache (
    spec_hash TEXT PRIMARY KEY,
    kind TEXT,
    result TEXT,
    created INTEGER,
    code_version TEXT,
    data_fingerprint TEXT,
    hits INTEGER NOT NULL DEFAULT 0
);

-- Every strategy definition and model that can trade is versioned; nothing reaches live trading without an
-- evaluation and an explicit approval (recorded in promotions).
CREATE TABLE IF NOT EXISTS strategy_versions (
    strategy_id TEXT NOT NULL,
    version_hash TEXT NOT NULL,
    definition TEXT NOT NULL,
    source TEXT,
    created INTEGER,
    status TEXT NOT NULL,
    evaluation_job TEXT,
    approved_by TEXT,
    approved INTEGER,
    notes TEXT,
    PRIMARY KEY (strategy_id, version_hash)
);

CREATE TABLE IF NOT EXISTS model_versions (
    model TEXT NOT NULL,
    version TEXT NOT NULL,
    created INTEGER,
    source TEXT,
    status TEXT NOT NULL,
    metrics TEXT,
    blob TEXT,
    approved_by TEXT,
    approved INTEGER,
    notes TEXT,
    PRIMARY KEY (model, version)
);

CREATE TABLE IF NOT EXISTS promotions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts INTEGER NOT NULL,
    object TEXT NOT NULL,
    object_id TEXT NOT NULL,
    from_status TEXT,
    to_status TEXT NOT NULL,
    evaluation TEXT,
    approved_by TEXT,
    note TEXT
);

CREATE TABLE IF NOT EXISTS drift_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts INTEGER NOT NULL,
    subject TEXT NOT NULL,
    metric TEXT NOT NULL,
    value REAL,
    threshold REAL,
    status TEXT,
    body TEXT
);
CREATE INDEX IF NOT EXISTS ix_drift ON drift_reports (subject, ts);

-- The brain's decision context for every closed trade (features, keys, costs, gate) with the trade's result:
-- what a candidate brain is compared on against the approved one, on trades that closed after the candidate
-- was frozen (forward, out-of-sample for both).
CREATE TABLE IF NOT EXISTS brain_samples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts INTEGER NOT NULL,
    bot_id TEXT,
    strategy_key TEXT,
    instrument TEXT,
    side INTEGER,
    regime TEXT,
    features TEXT,
    cost_r REAL,
    gate TEXT,
    r REAL,
    mode TEXT
);
CREATE INDEX IF NOT EXISTS ix_bsamples_ts ON brain_samples (ts);

CREATE TABLE IF NOT EXISTS watchlists (
    name TEXT PRIMARY KEY,
    symbols TEXT NOT NULL,
    created INTEGER,
    updated INTEGER
);

CREATE TABLE IF NOT EXISTS assistant_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts INTEGER NOT NULL,
    model TEXT,
    purpose TEXT,
    input_tokens INTEGER,
    output_tokens INTEGER,
    ok INTEGER,
    error TEXT
);

CREATE TABLE IF NOT EXISTS assistant_outputs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts INTEGER NOT NULL,
    purpose TEXT,
    request TEXT,
    output TEXT,
    validated INTEGER,
    validation TEXT,
    candidate_id TEXT
);
"""


def add_column(table: str, column: str, decl: str) -> Callable[[sqlite3.Connection], None]:
    """ALTER TABLE ... ADD COLUMN, skipped when the column already exists (SQLite has no IF NOT EXISTS)."""
    def step(conn: sqlite3.Connection):
        cols = {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        if column not in cols:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")
    step.__name__ = f"add_column({table}.{column} {decl})"
    return step


V2_STEPS: List[Step] = [V2] + [
    add_column("trades", "mode", "TEXT"),
    add_column("trades", "deployment_id", "TEXT"),
    add_column("trades", "connection_id", "TEXT"),
    add_column("fills", "mode", "TEXT"),
    add_column("fills", "deployment_id", "TEXT"),
    add_column("signals", "deployment_id", "TEXT"),
    add_column("orders", "mode", "TEXT"),
    # rows written before modes existed: the internal paper simulator, except the real-money trades that
    # the earlier live executor tagged in their entry reason
    "UPDATE trades SET mode = CASE WHEN entry_reason LIKE '[LIVE]%' THEN 'live' ELSE 'paper' END WHERE mode IS NULL",
    "UPDATE fills SET mode = CASE WHEN simulated = 0 THEN 'live' ELSE 'paper' END WHERE mode IS NULL",
    "UPDATE orders SET mode = 'paper' WHERE mode IS NULL",
    "CREATE INDEX IF NOT EXISTS ix_trades_deploy ON trades (deployment_id, exit_time)",
    "CREATE INDEX IF NOT EXISTS ix_trades_mode ON trades (mode, exit_time)",
]

MIGRATIONS: List[Tuple[int, str, Sequence[Step]]] = [
    (1, "baseline: bars, signals, orders, fills, trades, health, account, control queue", [V1]),
    (2, "three-page app: audit log, deployments, execution engine, connections, research, registries", V2_STEPS),
]

LATEST = MIGRATIONS[-1][0]


def _checksum(steps: Sequence[Step]) -> str:
    h = hashlib.sha256()
    for s in steps:
        h.update((s if isinstance(s, str) else getattr(s, "__name__", repr(s))).encode())
    return h.hexdigest()[:16]


def _statements(sql: str) -> List[str]:
    """Split a script into statements (none of ours contain ';' inside literals or triggers)."""
    body = "\n".join(ln for ln in sql.splitlines() if not ln.strip().startswith("--"))
    return [s.strip() for s in body.split(";") if s.strip()]


def applied(conn: sqlite3.Connection) -> List[int]:
    conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY, name TEXT, "
                 "applied INTEGER, checksum TEXT)")
    return [r[0] for r in conn.execute("SELECT version FROM schema_migrations ORDER BY version").fetchall()]


def _has_user_data(conn: sqlite3.Connection) -> bool:
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    for t in ("trades", "fills", "kv", "bot_state"):
        if t in tables and conn.execute(f"SELECT 1 FROM {t} LIMIT 1").fetchone():
            return True
    return False


def _backup(conn: sqlite3.Connection, path: str, version: int) -> str:
    dest_dir = os.path.join(os.path.dirname(os.path.abspath(path)), "backups")
    os.makedirs(dest_dir, exist_ok=True)
    dest = os.path.join(dest_dir, time.strftime(f"pre-migration-v{version}-%Y%m%d-%H%M%S.db"))
    dst = sqlite3.connect(dest)
    try:
        conn.backup(dst)
    finally:
        dst.close()
    return dest


def migrate(conn: sqlite3.Connection, path: str = "", backup: bool = True) -> List[int]:
    """Apply every pending migration. Returns the versions applied now (empty when up to date)."""
    done_now: List[int] = []
    have = set(applied(conn))
    conn.commit()
    pending = [m for m in MIGRATIONS if m[0] not in have]
    if not pending:
        _verify(conn)
        return done_now
    if backup and path and os.path.exists(path) and have and _has_user_data(conn):
        _backup(conn, path, pending[0][0])
    elif backup and path and os.path.exists(path) and not have and _has_user_data(conn):
        _backup(conn, path, pending[0][0])                      # a database from before migrations existed
    for version, name, steps in MIGRATIONS:
        conn.execute("BEGIN IMMEDIATE")
        try:
            if conn.execute("SELECT 1 FROM schema_migrations WHERE version=?", (version,)).fetchone():
                conn.execute("COMMIT")                          # another process got here first
                continue
            for s in steps:
                if isinstance(s, str):
                    for stmt in _statements(s):
                        conn.execute(stmt)
                else:
                    s(conn)
            conn.execute("INSERT INTO schema_migrations VALUES (?,?,?,?)",
                         (version, name, int(time.time() * 1000), _checksum(steps)))
            conn.execute("INSERT OR REPLACE INTO meta VALUES ('schema_version', ?)", (str(version),))
            conn.execute("COMMIT")
            done_now.append(version)
        except Exception:
            conn.execute("ROLLBACK")
            raise
    _verify(conn)
    return done_now


def _verify(conn: sqlite3.Connection):
    """An applied migration whose code changed afterwards is a programming error: refuse to run on it."""
    known = {v: _checksum(steps) for v, _, steps in MIGRATIONS}
    for version, checksum in conn.execute("SELECT version, checksum FROM schema_migrations").fetchall():
        if version in known and checksum != known[version]:
            raise RuntimeError(f"schema migration {version} was changed after it was applied "
                               f"(recorded {checksum}, code {known[version]}); add a new migration instead")
        if version not in known:
            raise RuntimeError(f"this database has schema version {version}, newer than this program "
                               f"(knows up to {LATEST}); use the newer program")


def status(conn: sqlite3.Connection) -> dict:
    have = applied(conn)
    return {"applied": have, "latest": LATEST, "pending": [v for v, _, _ in MIGRATIONS if v not in have]}
