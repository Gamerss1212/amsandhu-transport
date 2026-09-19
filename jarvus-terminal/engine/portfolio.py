#!/usr/bin/env python3
"""Portfolios: paper trading with real-money accounting, and a readiness gate.

Why this exists instead of live order execution
-----------------------------------------------
The obvious next feature is a button that sends real orders. This app deliberately
does not have one, and the reason is in its own measurements rather than in caution
for its own sake: of the configurations tested in this project, essentially none were
profitable after retail taker fees, and the strategies here have no forward-tested
record yet. Automating real orders on an untested edge does not make money faster, it
loses it faster and without a human in the loop to notice.

What this module does instead is make paper trading indistinguishable from the real
thing in every way that affects the outcome — real prices, real fees, real slippage,
real position sizing, real drawdown — so that the record it produces is a fair
prediction of what real money would have done. Then `readiness()` states plainly
whether that record justifies risking anything.

When the gate passes, going live is a matter of placing the orders yourself from the
plan the app already prints. That keeps a human at the point where money moves,
which is the correct place for one.
"""

from __future__ import annotations

import statistics
from datetime import datetime, timezone
from typing import Dict, List, Optional

import config
from engine import store


SCHEMA = """
CREATE TABLE IF NOT EXISTS portfolios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    kind TEXT NOT NULL DEFAULT 'paper',      -- 'paper' or 'live-record'
    starting_cash REAL NOT NULL,
    cash REAL NOT NULL,
    fee_bps REAL NOT NULL DEFAULT 26.0,
    slippage_bps REAL NOT NULL DEFAULT 2.0,
    risk_pct REAL NOT NULL DEFAULT 1.0,
    created_at TEXT NOT NULL,
    notes TEXT
);
CREATE TABLE IF NOT EXISTS positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    portfolio_id INTEGER NOT NULL,
    symbol TEXT NOT NULL,
    opened_at TEXT NOT NULL,
    units REAL NOT NULL,
    entry REAL NOT NULL,
    stop REAL NOT NULL,
    target REAL,
    fees_paid REAL NOT NULL DEFAULT 0,
    strategy TEXT, grade TEXT, gate_label TEXT, consensus REAL,
    closed_at TEXT, exit_price REAL, r_multiple REAL, pnl REAL, exit_reason TEXT,
    notes TEXT
);
CREATE INDEX IF NOT EXISTS idx_pos_pf ON positions(portfolio_id, closed_at);
"""


def _init():
    c = store.conn()
    c.executescript(SCHEMA)
    c.commit()


def ensure_default() -> Dict:
    _init()
    c = store.conn()
    row = c.execute("SELECT * FROM portfolios WHERE name='paper'").fetchone()
    if row:
        return dict(row)
    c.execute("INSERT INTO portfolios(name, kind, starting_cash, cash, fee_bps, slippage_bps, "
              "risk_pct, created_at, notes) VALUES(?,?,?,?,?,?,?,?,?)",
              ("paper", "paper", config.DEFAULT_ACCOUNT, config.DEFAULT_ACCOUNT,
               config.FEE_TIERS.get(config.DEFAULT_FEE_TIER, 26.0), config.SLIPPAGE_BPS,
               config.RISK_PCT_A, store.now_iso(),
               "Default paper book. Real prices, real fees, real sizing."))
    c.commit()
    return dict(c.execute("SELECT * FROM portfolios WHERE name='paper'").fetchone())


def create(name: str, starting_cash: float, kind: str = "paper", fee_bps: float = None,
           risk_pct: float = None, notes: str = "") -> Dict:
    _init()
    c = store.conn()
    c.execute("INSERT OR IGNORE INTO portfolios(name, kind, starting_cash, cash, fee_bps, "
              "slippage_bps, risk_pct, created_at, notes) VALUES(?,?,?,?,?,?,?,?,?)",
              (name, kind, starting_cash, starting_cash,
               fee_bps if fee_bps is not None else config.FEE_TIERS.get(config.DEFAULT_FEE_TIER, 26.0),
               config.SLIPPAGE_BPS, risk_pct if risk_pct is not None else config.RISK_PCT_A,
               store.now_iso(), notes))
    c.commit()
    return get(name)


def get(name: str = "paper") -> Optional[Dict]:
    _init()
    row = store.conn().execute("SELECT * FROM portfolios WHERE name=?", (name,)).fetchone()
    return dict(row) if row else None


def list_all() -> List[Dict]:
    _init()
    return [dict(r) for r in store.conn().execute("SELECT * FROM portfolios ORDER BY id").fetchall()]


def open_position(portfolio: str, symbol: str, price: float, stop: float, target: float = None,
                  strategy: str = None, grade: str = None, gate_label: str = None,
                  consensus: float = None, notes: str = "") -> Dict:
    """Size from the stop, charge the fee, take the cash. Same arithmetic as real life."""
    pf = get(portfolio) or ensure_default()
    if stop >= price:
        return {"error": "the stop must sit below the entry on a long"}
    c = store.conn()
    open_rows = c.execute("SELECT * FROM positions WHERE portfolio_id=? AND closed_at IS NULL",
                          (pf["id"],)).fetchall()
    if any(r["symbol"] == symbol for r in open_rows):
        return {"error": f"already holding {symbol} in this book"}

    equity = equity_of(pf["id"])["equity"]
    risk_amount = equity * pf["risk_pct"] / 100.0
    fill = price * (1 + pf["slippage_bps"] / 10000.0)
    per_unit_risk = fill - stop
    if per_unit_risk <= 0:
        return {"error": "the stop is not below the fill after slippage"}
    units = risk_amount / per_unit_risk
    notional = units * fill
    fee = notional * pf["fee_bps"] / 10000.0

    if notional + fee > pf["cash"]:
        # Spot means no borrowing: scale down to what the cash actually covers.
        scale = max(0.0, (pf["cash"] - fee) / notional) if notional else 0
        units *= scale
        notional = units * fill
        fee = notional * pf["fee_bps"] / 10000.0
        if units <= 0:
            return {"error": "not enough cash in this book for even a minimum position"}

    c.execute("INSERT INTO positions(portfolio_id, symbol, opened_at, units, entry, stop, target, "
              "fees_paid, strategy, grade, gate_label, consensus, notes) "
              "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
              (pf["id"], symbol, store.now_iso(), units, fill, stop, target, fee,
               strategy, grade, gate_label, consensus, notes))
    c.execute("UPDATE portfolios SET cash=cash-? WHERE id=?", (notional + fee, pf["id"]))
    c.commit()
    return {"ok": True, "units": units, "fill": fill, "notional": notional, "fee": fee,
            "risk_amount": risk_amount,
            "risk_pct_of_equity": round(risk_amount / equity * 100, 3) if equity else None}


def close_position(position_id: int, price: float, reason: str = "manual") -> Dict:
    pf_rows = store.conn().execute(
        "SELECT p.*, f.fee_bps, f.slippage_bps, f.id AS pfid FROM positions p "
        "JOIN portfolios f ON f.id = p.portfolio_id WHERE p.id=?", (position_id,)).fetchone()
    if not pf_rows:
        return {"error": "no such position"}
    if pf_rows["closed_at"]:
        return {"error": "already closed"}
    c = store.conn()
    fill = price * (1 - pf_rows["slippage_bps"] / 10000.0)
    proceeds = pf_rows["units"] * fill
    fee = proceeds * pf_rows["fee_bps"] / 10000.0
    risk = (pf_rows["entry"] - pf_rows["stop"]) * pf_rows["units"]
    gross = proceeds - pf_rows["units"] * pf_rows["entry"]
    pnl = gross - fee - pf_rows["fees_paid"]
    r = pnl / risk if risk else 0.0
    c.execute("UPDATE positions SET closed_at=?, exit_price=?, r_multiple=?, pnl=?, "
              "exit_reason=?, fees_paid=fees_paid+? WHERE id=?",
              (store.now_iso(), fill, round(r, 4), round(pnl, 2), reason, fee, position_id))
    c.execute("UPDATE portfolios SET cash=cash+? WHERE id=?", (proceeds - fee, pf_rows["pfid"]))
    c.commit()
    return {"ok": True, "r_multiple": round(r, 4), "pnl": round(pnl, 2), "fill": fill, "fee": fee}


def mark_to_market(portfolio: str, prices: Dict[str, float]) -> Dict:
    """Check open positions against live prices; auto-close anything through its stop or target."""
    pf = get(portfolio) or ensure_default()
    rows = store.conn().execute("SELECT * FROM positions WHERE portfolio_id=? AND closed_at IS NULL",
                                (pf["id"],)).fetchall()
    closed = []
    for r in rows:
        px = prices.get(r["symbol"])
        if px is None:
            continue
        if px <= r["stop"]:
            closed.append({"id": r["id"], "symbol": r["symbol"],
                           **close_position(r["id"], r["stop"], "stop")})
        elif r["target"] and px >= r["target"]:
            closed.append({"id": r["id"], "symbol": r["symbol"],
                           **close_position(r["id"], r["target"], "target")})
    return {"closed": closed, "checked": len(rows)}


def equity_of(portfolio_id: int, prices: Dict[str, float] = None) -> Dict:
    c = store.conn()
    pf = c.execute("SELECT * FROM portfolios WHERE id=?", (portfolio_id,)).fetchone()
    if not pf:
        return {"equity": 0.0}
    rows = c.execute("SELECT * FROM positions WHERE portfolio_id=? AND closed_at IS NULL",
                     (portfolio_id,)).fetchall()
    open_value = 0.0
    for r in rows:
        px = (prices or {}).get(r["symbol"], r["entry"])
        open_value += r["units"] * px
    return {"equity": pf["cash"] + open_value, "cash": pf["cash"], "open_value": open_value,
            "open_positions": len(rows)}


def performance(portfolio: str = "paper", prices: Dict[str, float] = None) -> Dict:
    pf = get(portfolio) or ensure_default()
    c = store.conn()
    closed = [dict(r) for r in c.execute(
        "SELECT * FROM positions WHERE portfolio_id=? AND closed_at IS NOT NULL ORDER BY closed_at",
        (pf["id"],)).fetchall()]
    open_rows = [dict(r) for r in c.execute(
        "SELECT * FROM positions WHERE portfolio_id=? AND closed_at IS NULL", (pf["id"],)).fetchall()]
    eq = equity_of(pf["id"], prices)

    rs = [t["r_multiple"] for t in closed if t["r_multiple"] is not None]
    pnls = [t["pnl"] for t in closed if t["pnl"] is not None]
    n = len(rs)
    wins = [r for r in rs if r > 0]
    losses = [r for r in rs if r <= 0]
    gw, gl = sum(wins), -sum(losses)

    curve, peak, dd = [], 0.0, 0.0
    run = pf["starting_cash"]
    for t in closed:
        run += t["pnl"] or 0.0
        curve.append({"t": t["closed_at"], "equity": round(run, 2)})
        peak = max(peak, run)
        dd = max(dd, (peak - run) / peak * 100 if peak else 0)

    return {
        "portfolio": pf["name"], "kind": pf["kind"],
        "starting_cash": pf["starting_cash"], "cash": round(pf["cash"], 2),
        "equity": round(eq["equity"], 2),
        "return_pct": round((eq["equity"] / pf["starting_cash"] - 1) * 100, 2) if pf["starting_cash"] else 0,
        "open_positions": open_rows, "closed_count": n,
        "win_rate": round(100 * len(wins) / n, 1) if n else None,
        "expectancy_r": round(sum(rs) / n, 4) if n else None,
        "total_r": round(sum(rs), 2) if n else 0,
        "avg_win_r": round(gw / len(wins), 3) if wins else None,
        "avg_loss_r": round(-gl / len(losses), 3) if losses else None,
        "profit_factor": round(gw / gl, 2) if gl > 0 else None,
        "total_pnl": round(sum(pnls), 2) if pnls else 0,
        "total_fees": round(sum(t["fees_paid"] or 0 for t in closed + open_rows), 2),
        "max_drawdown_pct": round(dd, 2),
        "equity_curve": curve[-200:],
        "fee_bps": pf["fee_bps"], "risk_pct": pf["risk_pct"],
        "recent": closed[-25:],
    }


# --- the gate that decides whether real money is justified -------------------

READINESS_RULES = [
    ("At least 50 closed trades", lambda p: (p["closed_count"] or 0) >= 50,
     "Under 50 trades the expectancy is noise. A losing system routinely shows a profit over 20."),
    ("Positive expectancy after fees", lambda p: (p["expectancy_r"] or 0) > 0,
     "Expectancy already includes fees and slippage here. If it is negative, size is not the problem."),
    ("Profit factor above 1.2", lambda p: (p["profit_factor"] or 0) > 1.2,
     "Below this the edge is inside the noise band and a normal losing streak erases it."),
    ("Max drawdown under 20%", lambda p: (p["max_drawdown_pct"] or 0) < 20,
     "Whatever the paper drawdown was, assume the real one is worse, because paper does not panic."),
    ("Average win larger than average loss", lambda p: abs(p["avg_win_r"] or 0) > abs(p["avg_loss_r"] or 0),
     "If losers are bigger than winners you are relying on a high hit rate, which does not survive a bad week."),
    ("Fees under a third of gross profit", lambda p: (p["total_fees"] or 0) < max(1e-9, abs(p["total_pnl"] or 0) + (p["total_fees"] or 0)) / 3,
     "If fees eat a third of the gross, the venue is the problem and a better fee tier beats a better strategy."),
]


def readiness(portfolio: str = "paper") -> Dict:
    """Has this book earned the right to real money? Six checks, all must pass."""
    p = performance(portfolio)
    checks = []
    for name, test, why in READINESS_RULES:
        try:
            ok = bool(test(p))
        except Exception:                               # noqa: BLE001
            ok = False
        checks.append({"check": name, "passed": ok, "why": why})
    passed = sum(1 for c in checks if c["passed"])
    ready = passed == len(checks)
    return {
        "ready": ready, "passed": passed, "total": len(checks), "checks": checks,
        "verdict": (
            "This book has met every bar. Going live is now a decision about size, and the "
            "sane first size is smaller than the maths allows — a quarter of it — because live "
            "execution and live emotions are both worse than paper."
            if ready else
            f"Not yet: {len(checks) - passed} of {len(checks)} checks still fail. Every "
            "additional paper trade costs nothing and buys evidence; a live trade taken before "
            "this passes is buying the same evidence with money."),
        "performance": p,
    }
