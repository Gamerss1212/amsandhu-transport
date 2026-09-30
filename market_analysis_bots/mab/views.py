"""Read-only views over a workspace database for the app's pages: account figures, equity and drawdown curves,
trades, positions, orders, exposure, bot comparisons and chart markers.

Every figure says where it came from and when: simulated accounts are computed here from their saved state;
broker accounts show what the broker last reported (with the time of that report), never an estimate dressed up
as a balance. Paper, demo, research and live results are always kept apart.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional

ACTIVE = ("running", "paused", "stopped_retaining", "error")


def now_ms() -> int:
    return int(time.time() * 1000)


def day_start(ms: Optional[int] = None) -> int:
    d = datetime.fromtimestamp((ms or now_ms()) / 1000, tz=timezone.utc)
    return int(datetime(d.year, d.month, d.day, tzinfo=timezone.utc).timestamp() * 1000)


def _j(x, default=None):
    if not x:
        return default
    try:
        return json.loads(x) if isinstance(x, str) else x
    except ValueError:
        return default


def connections(st) -> List[dict]:
    rows = st.query("SELECT * FROM connections ORDER BY created")
    for r in rows:
        for k in ("options", "account", "permissions", "capabilities", "last_test"):
            r[k] = _j(r.get(k), {})
    return rows


def _sim_state(st, cid: str) -> Optional[dict]:
    key = "account" if cid == "paper-research" else f"sim_account:{cid}"
    return st.kv_get(key)


def account(st, c: dict) -> dict:
    """Figures for one account connection."""
    cid = c["connection_id"]
    env = c["environment"]
    simulated = c["provider"] == "jarvus_paper"
    out = {"connection_id": cid, "label": c.get("label"), "provider": c["provider"], "environment": env,
           "mode": "research" if cid == "paper-research" else env, "simulated": simulated, "real_money": env == "live",
           "status": c.get("status"), "equity": None, "cash": None, "buying_power": None, "currency": None,
           "unrealized": None, "exposure": None, "as_of": None, "source": None}
    if simulated:
        s = _sim_state(st, cid)
        if s:
            from mab.account import Account
            a = Account.from_state(s)
            summ = a.summary()
            unreal = sum(a.position_value(p) - p["qty"] * p["avg_price"] for p in a.positions.values())
            out.update(equity=summ["equity"], cash=summ["cash"], buying_power=max(0.0, summ["cash"]), currency=summ["currency"],
                       unrealized=unreal, exposure=summ["gross_exposure"], as_of=now_ms(),
                       source="simulated account (marked at the latest prices the bots saw)")
    else:
        r = st.query("SELECT * FROM connection_snapshots WHERE connection_id=? ORDER BY ts DESC LIMIT 1", (cid,))
        if r:
            b = _j(r[0].get("body"), {})
            out.update(equity=r[0]["equity"], cash=r[0]["cash"], buying_power=r[0]["buying_power"], currency=r[0]["currency"],
                       as_of=r[0]["ts"], source=f"reported by {c.get('label') or c['provider']}", latency_ms=r[0].get("latency_ms"))
            pos = st.query("SELECT * FROM broker_positions WHERE connection_id=?", (cid,))
            if pos:
                out["unrealized"] = sum(p["unrealized_pnl"] or 0 for p in pos if p["unrealized_pnl"] is not None)
                mv = [abs(p["market_value"]) for p in pos if p["market_value"] is not None]
                out["exposure"] = sum(mv) if mv else None
            out["broker_status"] = b.get("status")
        else:
            out["source"] = "not synced yet: test or sync the connection"
    deps = st.query("SELECT allocation FROM deployments WHERE connection_id=? AND state IN (%s)" % ",".join("?" * len(ACTIVE)),
                    (cid, *ACTIVE))
    out["allocated"] = sum(d["allocation"] for d in deps)
    out["active_bots"] = len(deps)
    if cid == "paper-research":
        tq = "SELECT COALESCE(SUM(pnl),0) AS s, COUNT(*) AS n FROM trades WHERE (connection_id='paper-research' OR (connection_id IS NULL AND deployment_id IS NULL))"
        a = ()
    else:
        tq = "SELECT COALESCE(SUM(pnl),0) AS s, COUNT(*) AS n FROM trades WHERE connection_id=?"
        a = (cid,)
    tot = st.query(tq, a)[0]
    today = st.query(tq + " AND exit_time >= ?", a + (day_start(),))[0]
    out.update(realized_total=tot["s"], trades_total=tot["n"], realized_today=today["s"], trades_today=today["n"])
    eq = st.query("SELECT ts, equity FROM account_equity WHERE connection_id=? AND ts >= ? ORDER BY ts", (cid, day_start()))
    if out["equity"] is not None:
        peak = max([e["equity"] for e in eq if e["equity"] is not None] + [out["equity"]])
        out["daily_drawdown_pct"] = (peak - out["equity"]) / peak * 100 if peak > 0 else 0.0
        out["day_peak"] = peak
    if out["equity"] and out["exposure"] is not None:
        out["exposure_pct"] = out["exposure"] / out["equity"] * 100
    return out


def accounts(st) -> List[dict]:
    return [account(st, c) for c in connections(st) if c.get("enabled", 1)]


def equity_curve(st, cid: str, since: Optional[int] = None, points: int = 600) -> dict:
    since = since or now_ms() - 30 * 86_400_000
    rows = st.query("SELECT ts, equity FROM account_equity WHERE connection_id=? AND ts >= ? AND equity IS NOT NULL ORDER BY ts",
                    (cid, since))
    if cid == "paper-research" and len(rows) < 2:
        rows = st.query("SELECT time AS ts, equity FROM equity WHERE time >= ? ORDER BY time", (since,))
    if len(rows) > points:
        k = len(rows) / points
        rows = [rows[int(i * k)] for i in range(points)] + [rows[-1]]
    peak, dd = None, []
    for r in rows:
        peak = r["equity"] if peak is None else max(peak, r["equity"])
        dd.append({"ts": r["ts"], "drawdown_pct": -(peak - r["equity"]) / peak * 100 if peak else 0.0})
    flows = st.query("SELECT time, kind, amount, note FROM cash_flows WHERE time >= ? ORDER BY time", (since,))
    return {"connection_id": cid, "equity": rows, "drawdown": dd,
            "max_drawdown_pct": min((d["drawdown_pct"] for d in dd), default=0.0),
            "cash_flows": [f for f in flows if cid in (f.get("note") or "") or cid == "paper-research"],
            "note": "balance changes on simulated accounts are simulated and excluded from performance"}


def trades(st, mode: str = None, connection_id: str = None, deployment_id: str = None, bot_id: str = None,
           symbol: str = None, limit: int = 100) -> List[dict]:
    where, a = [], []
    for col, v in (("mode", mode), ("connection_id", connection_id), ("deployment_id", deployment_id), ("bot_id", bot_id),
                   ("instrument", symbol)):
        if v:
            where.append(f"{col}=?")
            a.append(v)
    q = "SELECT * FROM trades" + (" WHERE " + " AND ".join(where) if where else "") + " ORDER BY exit_time DESC LIMIT ?"
    return st.query(q, tuple(a + [max(1, min(limit, 2000))]))


def stats(rows: List[dict]) -> dict:
    n = len(rows)
    if not n:
        return {"trades": 0}
    rs = [r["r"] for r in rows if r.get("r") is not None]
    pnl = [r["pnl"] or 0 for r in rows]
    eq, peak, mdd = 0.0, 0.0, 0.0
    for p in reversed(pnl):
        eq += p
        peak = max(peak, eq)
        mdd = max(mdd, peak - eq)
    return {"trades": n, "pnl_after_fees": sum(pnl), "fees": sum(r.get("fees") or 0 for r in rows),
            "win_rate": sum(1 for p in pnl if p > 0) / n, "avg_r": sum(rs) / len(rs) if rs else None,
            "max_drawdown_money": mdd, "first": min(r["exit_time"] for r in rows), "last": max(r["exit_time"] for r in rows)}


def orders(st, states=None, deployment_id=None, connection_id=None, limit=200) -> List[dict]:
    where, a = [], []
    if states:
        where.append("state IN (%s)" % ",".join("?" * len(states)))
        a += list(states)
    if deployment_id:
        where.append("deployment_id=?")
        a.append(deployment_id)
    if connection_id:
        where.append("connection_id=?")
        a.append(connection_id)
    rows = st.query("SELECT client_order_id, broker_order_id, connection_id, mode, deployment_id, bot_id, correlation_id,"
                    " purpose, symbol, side, order_type, tif, qty, limit_price, stop_price, reduce_only, state, filled_qty,"
                    " avg_price, fees, fee_currency, reason, attempts, ref_price, created, submitted, acked, updated, closed"
                    " FROM broker_orders" + (" WHERE " + " AND ".join(where) if where else "") + " ORDER BY created DESC LIMIT ?",
                    tuple(a + [limit]))
    return rows


def fills(st, deployment_id=None, symbol=None, limit=200) -> List[dict]:
    where, a = [], []
    if deployment_id:
        where.append("deployment_id=?")
        a.append(deployment_id)
    if symbol:
        where.append("symbol LIKE ?")
        a.append(f"%{symbol}")
    return st.query("SELECT fill_id, client_order_id, connection_id, mode, deployment_id, bot_id, symbol, side, qty, price,"
                    " fee, fee_currency, liquidity, ts, simulated, ref_price, slippage_bps FROM broker_fills"
                    + (" WHERE " + " AND ".join(where) if where else "") + " ORDER BY ts DESC LIMIT ?", tuple(a + [limit]))


def positions(st) -> List[dict]:
    out = []
    for p in st.query("SELECT * FROM exec_positions WHERE status != 'closed' AND qty > 0"):
        out.append(dict(p, source="deployment", simulated=p["mode"] in ("paper", "demo") and (p.get("stop_order") is None)))
    s = st.kv_get("account") or {}
    for p in s.get("positions", []):
        out.append({"deployment_id": None, "bot_id": p["bot_id"], "connection_id": "paper-research", "mode": "research",
                    "symbol": f"{p['venue']}:{p['instrument']}", "side": 1 if p["qty"] > 0 else -1, "qty": abs(p["qty"]),
                    "avg_price": p["avg_price"], "opened": p.get("opened"), "status": "open", "source": "research fleet",
                    "simulated": True})
    return out


def exposure(st, accts: Optional[List[dict]] = None) -> dict:
    accts = accts if accts is not None else accounts(st)
    by_account = [{"connection_id": a["connection_id"], "label": a["label"], "mode": a["mode"], "exposure": a.get("exposure"),
                   "equity": a.get("equity"), "exposure_pct": a.get("exposure_pct"), "currency": a.get("currency")}
                  for a in accts]
    by_symbol: Dict[str, dict] = {}
    for p in positions(st):
        k = (p["symbol"], p["mode"])
        d = by_symbol.setdefault(k, {"symbol": p["symbol"], "mode": p["mode"], "qty": 0.0, "cost": 0.0, "positions": 0})
        d["qty"] += p["qty"] * (p.get("side") or 1)
        d["cost"] += p["qty"] * (p.get("avg_price") or 0)
        d["positions"] += 1
    return {"by_account": by_account, "by_symbol": sorted(by_symbol.values(), key=lambda x: -abs(x["cost"])),
            "note": "exposure is computed per account; accounts in different modes are never added together"}


def markers(st, symbol_key: str, instrument: str, since: Optional[int] = None) -> List[dict]:
    """Entries and exits on the chart: deployment fills (by mode) and research-fleet fills, from the records."""
    since = since or now_ms() - 30 * 86_400_000
    out = []
    for f in st.query("SELECT f.ts, f.side, f.qty, f.price, f.mode, f.bot_id, f.simulated, o.purpose FROM broker_fills f"
                      " LEFT JOIN broker_orders o ON o.client_order_id = f.client_order_id WHERE f.symbol=? AND f.ts>=?"
                      " ORDER BY f.ts", (symbol_key, since)):
        out.append({"time": f["ts"], "side": f["side"], "qty": f["qty"], "price": f["price"], "mode": f["mode"],
                    "bot_id": f["bot_id"], "kind": "entry" if f["purpose"] == "entry" else "exit",
                    "simulated": bool(f["simulated"])})
    for f in st.query("SELECT time, side, qty, price, bot_id FROM fills WHERE instrument=? AND time>=? AND "
                      "(mode IS NULL OR mode IN ('paper','demo')) AND deployment_id IS NULL ORDER BY time", (instrument, since)):
        out.append({"time": f["time"], "side": f["side"], "qty": f["qty"], "price": f["price"], "mode": "research",
                    "bot_id": f["bot_id"], "kind": "entry" if f["side"] == "buy" else "exit", "simulated": True})
    out.sort(key=lambda x: x["time"])
    return out[-500:]


def alerts(st, hours: int = 24, limit: int = 50) -> List[dict]:
    return st.audit_search(severity="warning", since=now_ms() - hours * 3_600_000, limit=limit)
