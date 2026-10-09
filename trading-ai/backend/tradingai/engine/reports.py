"""Attribution and session reports (owner's specification: attribution analyst, session report, equity/drawdown).

Everything here is computed from the ledger: fills, fees, decisions, audit rows and recorded equity snapshots.
Paper and live records are labelled; a simulated fill is never presented as a live fill.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from tradingai.storage.db import now_ms
from tradingai.strategies.library import MARKET_OF

if TYPE_CHECKING:
    from tradingai.app import App


def record_equity(app: "App") -> None:
    v = app.account_view()
    a = v["account"]
    app.db.execute("INSERT INTO equity_history (ts, mode, equity, cash, realized, unrealized, fees, positions, simulated) "
                   "VALUES (?,?,?,?,?,?,?,?,?)", (now_ms(), v["mode"], a["equity"], a["cash"], v["realized"],
                                                  v["unrealized"], v.get("fees"), len(v["positions"]),
                                                  int(bool(a["simulated"]))))


def equity_series(app: "App", hours: float = 168) -> dict:
    rows = app.db.query("SELECT ts, equity, mode, simulated FROM equity_history WHERE ts>? ORDER BY ts",
                        (now_ms() - int(hours * 3_600_000),))
    pts, peak, dd = [], None, []
    for r in rows:
        if r["equity"] is None:
            continue
        e = float(r["equity"])
        peak = e if peak is None else max(peak, e)
        pts.append([r["ts"], e])
        dd.append([r["ts"], round((e / peak - 1) if peak else 0.0, 6)])
    adj = app.db.query("SELECT ts, amount, note FROM ledger WHERE kind IN ('adjustment','deposit') AND ts>? ORDER BY ts",
                       (now_ms() - int(hours * 3_600_000),))
    return {"equity": pts, "drawdown": dd, "simulated": any(r["simulated"] for r in rows),
            "adjustments": adj, "note": "equity recorded every minute while the program runs; owner balance changes "
                                        "and deposits are listed separately and are not trading results"}


def attribution(app: "App", since: Optional[int] = None) -> dict:
    """P&L by strategy and by market from fills (cash flows) plus the current value of each strategy's lots."""
    since = since or 0
    rows = app.db.query("SELECT f.side, f.qty, f.price, f.fee, f.instrument_id, f.environment, f.ts, f.decision_price, "
                        "o.strategy_id FROM fills f LEFT JOIN orders o ON o.client_order_id=f.client_order_id "
                        "WHERE f.ts>=? ORDER BY f.ts", (since,))
    lots: dict[tuple[str, str], Decimal] = {}
    by: dict[str, dict] = {}
    by_market: dict[str, dict] = {}
    for f in rows:
        sid = f["strategy_id"] or "manual"
        inst = app.book.get(f["instrument_id"])
        q = Decimal(f["qty"]) * (1 if f["side"] == "buy" else -1)
        flow = -q * Decimal(f["price"]) * inst.multiplier
        fee = Decimal(f["fee"])
        slip = Decimal(0)
        if f["decision_price"]:
            slip = (Decimal(f["price"]) - Decimal(f["decision_price"])) * q * inst.multiplier
        for key, table in ((sid, by), (MARKET_OF.get(inst.market_type, "other"), by_market)):
            d = table.setdefault(key, {"fills": 0, "cash_flow": Decimal(0), "fees": Decimal(0), "slippage_cost":
                                       Decimal(0), "environment": set()})
            d["fills"] += 1
            d["cash_flow"] += flow
            d["fees"] += fee
            d["slippage_cost"] += slip
            d["environment"].add(f["environment"])
        lots[(sid, f["instrument_id"])] = lots.get((sid, f["instrument_id"]), Decimal(0)) + q
    for (sid, iid), q in lots.items():
        if q == 0:
            continue
        quote = app.quote(iid)
        inst = app.book.get(iid)
        val = q * Decimal(str(quote["price"])) * inst.multiplier if quote else Decimal(0)
        for key, table in ((sid, by), (MARKET_OF.get(inst.market_type, "other"), by_market)):
            table[key].setdefault("open_value", Decimal(0))
            table[key]["open_value"] += val
            if not quote:
                table[key]["unpriced"] = True

    def fin(t: dict) -> list[dict]:
        out = []
        for k, d in t.items():
            pnl = d["cash_flow"] + d.get("open_value", Decimal(0)) - d["fees"]
            out.append({"name": k, "fills": d["fills"], "net_pnl": str(pnl.quantize(Decimal("0.01"))),
                        "fees": str(d["fees"].quantize(Decimal("0.01"))),
                        "slippage_vs_decision": str(d["slippage_cost"].quantize(Decimal("0.01"))),
                        "open_value": str(d.get("open_value", Decimal(0)).quantize(Decimal("0.01"))),
                        "environment": sorted(d["environment"]), "unpriced": d.get("unpriced", False)})
        return sorted(out, key=lambda x: Decimal(x["net_pnl"]))
    return {"since": since, "by_strategy": fin(by), "by_market": fin(by_market),
            "note": "net P&L = cash flows of fills + current value of open lots - fees; slippage is fill price minus the "
                    "decision price (positive = cost)."}


def session_report(app: "App", since: Optional[int] = None) -> dict:
    since = since or int(app.started * 1000)
    fills = app.db.query("SELECT * FROM fills WHERE ts>=? ORDER BY ts", (since,))
    dec = app.db.query("SELECT outcome, COUNT(*) AS n FROM decisions WHERE ts>=? GROUP BY outcome", (since,))
    blocked = app.db.query("SELECT instrument_id, reason, ts FROM decisions WHERE ts>=? AND outcome='RISK_REJECT' "
                           "ORDER BY ts DESC LIMIT 50", (since,))
    incidents = app.db.audit_rows(since_id=0, min_severity="warning", limit=200)
    incidents = [r for r in incidents if r["ts"] >= since]
    changes = [r for r in app.db.audit_rows(kind="autopilot", limit=200) if r["ts"] >= since] + \
        [r for r in app.db.audit_rows(kind="bot", limit=200) if r["ts"] >= since]
    fees = sum((Decimal(f["fee"]) for f in fills), Decimal(0))
    acct = app.account_view()
    return {"since": since, "until": now_ms(), "mode": app.mode, "simulated": acct["account"]["simulated"],
            "trades": len(fills), "fees": str(fees.quantize(Decimal("0.01"))),
            "decisions": {r["outcome"]: r["n"] for r in dec}, "blocked": blocked,
            "incidents": [{k: r[k] for k in ("ts", "kind", "severity", "message")} for r in incidents[:50]],
            "strategy_changes": [{k: r[k] for k in ("ts", "kind", "message")} for r in
                                 sorted(changes, key=lambda r: r["ts"])][-50:],
            "remaining_exposure": acct["positions"], "open_orders": acct["open_orders"],
            "equity": acct["account"]["equity"], "attribution": attribution(app, since),
            "label": "PAPER (simulated money)" if acct["account"]["simulated"] else "LIVE"}
