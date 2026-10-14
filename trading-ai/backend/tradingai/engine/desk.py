"""One read for the trading desk (page 1) and for JARVIS: everything that screen shows, computed here from the database
and the live services. It replaces seven separate polls with one. Nothing in it is estimated or decorative."""

from __future__ import annotations

import json
from collections import Counter
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from tradingai.storage.db import now_ms

if TYPE_CHECKING:
    from tradingai.app import App

GROUPS = {"crypto": ("crypto_major", "crypto_trend", "crypto_reversion"),
          "meme": ("meme_momentum", "meme_reversion"),
          "stock": ("stock_breakout", "stock_reversion", "stock_intraday")}
ENTRY = ("BUY", "SELL", "ENTER", "ENTRY", "OPEN")


def _j(v):
    try:
        return json.loads(v) if v else None
    except (TypeError, ValueError):
        return None


def _decisions(app: "App", limit: int) -> list[dict]:
    out = []
    for r in app.db.query("SELECT decision_id, ts, instrument_id, tf, strategy_id, outcome, reason, order_json, "
                          "json_extract(votes, '$.ensemble') AS ensemble, latency FROM decisions "
                          "ORDER BY ts DESC LIMIT ?", (limit,)):
        order, ens, lat = _j(r["order_json"]), _j(r["ensemble"]), _j(r["latency"])
        out.append({"id": r["decision_id"], "ts": r["ts"], "instrument": r["instrument_id"], "tf": r["tf"],
                    "agent": app.fleet.owner_of(r["instrument_id"]), "strategy": r["strategy_id"],
                    "outcome": r["outcome"], "reason": r["reason"],
                    "order": (order or {}).get("status") if isinstance(order, dict) else None,
                    "agree": (ens or {}).get("agreeing_clusters"), "clusters": (ens or {}).get("independent_clusters"),
                    "ms": (lat or {}).get("total_ms")})
    return out


def _equity(app: "App", since: int, points: int = 240) -> list[list]:
    rows = app.db.query("SELECT ts, equity FROM equity_history WHERE ts>? AND equity IS NOT NULL ORDER BY ts", (since,))
    step = max(1, len(rows) // points)
    pts = [[r["ts"], float(r["equity"])] for r in rows[::step]]
    if rows and (not pts or pts[-1][0] != rows[-1]["ts"]):
        pts.append([rows[-1]["ts"], float(rows[-1]["equity"])])
    return pts


def desk(app: "App") -> dict:
    now = now_ms()
    acct = app.account_view()
    a = acct.get("account") or {}
    equity = Decimal(str(a["equity"])) if a.get("equity") is not None else None
    contributed: Optional[Decimal] = None
    if app.mode != "live":                               # paper: deposits and owner balance changes are not trading
        contributed = sum((Decimal(r["amount"]) for r in app.db.query(
            "SELECT amount FROM ledger WHERE account_id=? AND kind IN ('adjustment','deposit')", (app.paper.account_id,))),
            Decimal(0))
    health = app.health()
    uptime = ((health.get("components") or {}).get("backend") or {}).get("uptime_s")
    started = now - int(uptime * 1000) if uptime is not None else None
    fleet = app.fleet.summary()
    counts = fleet.get("counts") or {}
    by_group = {k: {"target": 0, "active": 0, "validated": 0} for k in GROUPS}
    for g in fleet.get("groups") or []:
        for k, roles in GROUPS.items():
            if g["group"] in roles:
                by_group[k]["target"] += int(g.get("target") or 0)
                by_group[k]["active"] += int(g.get("assigned") or 0)
                by_group[k]["validated"] += int(g.get("validated") or 0)

    decisions = _decisions(app, 14)
    hour = [d for d in _decisions(app, 400) if now - d["ts"] <= 3_600_000]
    entries_hour = [d for d in hour if d["order"]]
    refused = Counter(d["reason"] for d in hour if not d["order"] and d["reason"])
    env = "live" if app.mode == "live" else "paper"
    fills = app.db.query("SELECT ts, side, instrument_id, qty, price FROM fills WHERE environment=? ORDER BY ts DESC LIMIT 1",
                         (env,))
    last_fill = fills[0]["ts"] if fills else None

    timeline = []
    if started:
        timeline.append({"ts": started, "label": "System started", "kind": "info"})
        first = app.db.one("SELECT MIN(ts) AS t FROM decisions WHERE ts>=?", (started,))
        if first and first["t"]:
            timeline.append({"ts": first["t"], "label": "First decision", "kind": "info"})
        ff = app.db.one("SELECT MIN(ts) AS t FROM fills WHERE ts>=? AND environment=?", (started, env))
        if ff and ff["t"]:
            timeline.append({"ts": ff["t"], "label": "First trade", "kind": "good"})
    risk = app.risk
    for key, label in (("kill_switch", "Emergency stop"), ("trading_locked", "Trading locked"),
                       ("entries_paused", "Entries paused")):
        v = getattr(risk, key, None)
        if v:
            timeline.append({"ts": v.get("ts") or now, "label": label, "kind": "bad" if key != "entries_paused" else "warn"})
    if last_fill and (not timeline or last_fill > max(t["ts"] for t in timeline)):
        timeline.append({"ts": last_fill, "label": "Latest trade", "kind": "good"})
    timeline.sort(key=lambda t: t["ts"])

    autopilot_on = bool(getattr(app.autopilot.cfg, "enabled", False))
    eligible = int(counts.get("execution_eligible") or 0)
    if risk.kill_switch or risk.trading_locked:
        control = {"state": "BLOCKED", "why": (risk.kill_switch or risk.trading_locked).get("reason", "")}
    elif not autopilot_on:
        control = {"state": "STOPPED", "why": "press Start"}
    elif risk.entries_paused:
        control = {"state": "PAUSED", "why": "open positions still managed"}
    elif not eligible:
        control = {"state": "STANDBY", "why": "no strategy has qualified yet"}
    else:
        control = {"state": "OPEN", "why": f"{eligible} agent{'s' if eligible != 1 else ''} cleared to trade"}
    day0 = risk.day_start_equity
    day_loss = float((day0 - equity) / day0) if (day0 and equity is not None and day0 > 0) else None

    series = list((((health.get("components") or {}).get("market_feed") or {}).get("series") or {}).values())
    latest = decisions[0] if decisions else None
    reading = (app.hardware.view() or {}).get("reading") or {}
    return {
        "ts": now, "mode": app.mode, "simulated": app.mode != "live", "version": health.get("version"),
        "state": (health.get("state") or {}).get("state"), "autopilot": autopilot_on, "doing": fleet.get("brain", {}).get("doing"),
        "balance": None if equity is None else str(equity), "cash": a.get("cash"),
        "contributed": None if contributed is None else str(contributed),
        "net_pnl": None if (equity is None or contributed is None) else str((equity - contributed).quantize(Decimal("0.01"))),
        "day_pnl": acct.get("day_pnl"), "realized": acct.get("realized"), "unrealized": acct.get("unrealized"),
        "fees": acct.get("fees"), "trades_today": acct.get("trades_today"),
        "positions": acct.get("positions") or [], "fills": (acct.get("fills") or [])[:8],
        "uptime_s": uptime, "started": started, "timeline": timeline,
        "agents": {"target": counts.get("target"), "running": counts.get("running"), "eligible": eligible,
                   "with_positions": counts.get("with_positions"), "groups": by_group},
        "decisions": decisions,
        "hour": {"decisions": len(hour), "entries": len(entries_hour),
                 "top_refusal": refused.most_common(1)[0][0] if refused else None},
        "last_trade_ts": last_fill,
        "checks": {"qualified": [eligible, counts.get("target") or 0],
                   "fresh_data": [sum(1 for s in series if s.get("fresh")), len(series)],
                   "signals_agree": [latest["agree"], latest["clusters"]] if latest and latest["clusters"] else None},
        "control": control, "day_loss": day_loss, "day_loss_limit": risk.limits.max_daily_loss_pct,
        "risk_counters": ((health.get("components") or {}).get("risk_service") or {}).get("counters"),
        "equity": _equity(app, now - 7 * 86_400_000),
        "system": {"checks": [sum(1 for c in health.get("startup_checks") or [] if c.get("ok")),
                              len(health.get("startup_checks") or [])],
                   "cpu": reading.get("cpu_load_pct"), "temp": reading.get("max_temp_c"),
                   "ram": (health.get("system") or {}).get("ram_used_pct")},
        "jarvis_pending": len(app.jarvis.view()["pending"]),
    }
