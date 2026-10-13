"""Continuous learning from mistakes, shared by all 100 trading agents (owner's instruction of 2026-10-13).

The loop, for every mistake:
  1. RECORD it: what happened, which agent, which instrument, and the exact inputs (the "scenario").
  2. Find its ROOT CAUSE with fixed rules (below): for example a risk check the order failed, a broker error, a closed
     trade that lost more than 1.5 times its planned risk.
  3. Turn it into a LESSON the first time that root cause is seen. A lesson switches on a SAFEGUARD for every agent at
     once: a pre-trade guard that can only make an entry more conservative (skip it or shrink it). Safeguards never
     loosen a limit and never touch exits; the deterministic risk service still checks every order after them.
  4. Prove the safeguard with a REGRESSION REPLAY: the stored scenario is run through the guard and must now be blocked
     or shrunk as specified. All stored scenarios are replayed at start-up, after each new lesson and on demand.
  5. Count REPEATS: a mistake whose lesson already existed is a repeat. Three repeats by one agent within 24 hours
     suspend that agent's entries for a day (the master enforces it) and the repeat is reported as a safeguard gap.

Measured evidence: mistakes per 100 decisions (this week vs last week), repeats, lessons, regression pass rate.
This aims to stop known mistakes from recurring; it cannot promise that an agent never repeats one.
"""

from __future__ import annotations

import threading
import time
from decimal import ROUND_DOWN, Decimal
from typing import TYPE_CHECKING, Any, Optional

from tradingai.core.ids import new_id
from tradingai.storage.db import dumps, now_ms

if TYPE_CHECKING:
    from tradingai.app import App

DAY = 86_400_000
COOLDOWN_MS = 15 * 60_000
# root cause -> (kind, what went wrong, safeguard, what the safeguard does)
ROOT_CAUSES: dict[str, tuple[str, str, str, str]] = {
    "CONTROL_ENGAGED": ("control", "an entry was proposed while trading was stopped, locked, paused or under "
                        "reconciliation", "respect_controls", "no entry proposal while any trading control is engaged"),
    "MARKET_CLOSED": ("execution", "an entry was proposed while the market was closed", "check_session",
                      "no entry unless the instrument's session is open"),
    "STALE_DATA": ("data", "an entry was proposed on market data older than the freshness limit", "require_fresh_data",
                   "no entry when the newest bar is older than 2 bars (the risk service allows 3)"),
    "DUPLICATE_ORDER": ("execution", "an order repeated one already sent", "one_order_in_flight",
                        "no entry while the instrument has a working order or had an entry in the last 60 seconds"),
    "ORDER_RATE": ("execution", "too many orders in one minute", "pace_orders",
                   "no entry when the last minute already holds the order limit minus 5"),
    "EXECUTION_ERROR": ("execution", "the broker returned an error or an unknown order state", "error_cooldown",
                        "no entry on that instrument for 15 minutes after an execution or data error"),
    "DATA_ERROR": ("data", "the market data feed failed during a decision", "error_cooldown",
                   "no entry on that instrument for 15 minutes after an execution or data error"),
    "BAD_PRICE": ("data", "an order's price was outside the fat-finger band", "price_sanity",
                  "no entry when the reference price is beyond 80% of the fat-finger band"),
    "SIZE_OVER_LIMIT": ("risk", "an order was larger than an order, position, exposure or agent-budget limit",
                        "pre_clamp_size", "shrink an entry to 95% of the tightest remaining limit before sending"),
    "LIQUIDITY": ("execution", "an order exceeded the allowed share of the bar's volume", "clamp_participation",
                  "shrink an entry to 80% of the allowed share of the bar's volume"),
    "LOSS_BEYOND_PLAN_HIGH_VOL": ("risk", "a closed trade lost more than 1.5x its planned risk, entered in a high "
                                  "volatility regime", "half_size_high_vol",
                                  "halve entry size when the volatility regime is high"),
    "LOSS_BEYOND_PLAN_SLIPPAGE": ("risk", "a closed trade lost more than 1.5x its planned risk in a normal regime "
                                  "(gap or slippage beyond the model)", "market_size_haircut",
                                  "reduce entry size by 25% in the market type where it happened"),
    "AGENT_LOSS_LIMIT": ("risk", "an agent lost more than its daily loss limit", "agent_day_stop",
                         "no new entries for that agent until the next UTC day"),
    "VERSION_UNDERPERFORMED": ("model", "a promoted version did worse in paper than in validation, or breached its "
                               "loss limits", "rollback", "roll back to the previous validated version, or suspend "
                               "the agent until a new version validates"),
}
# risk-service check name -> root cause (entries only; controls that are expected gates are not mistakes)
CHECK_CAUSE = {
    "kill switch not engaged": "CONTROL_ENGAGED", "trading not locked": "CONTROL_ENGAGED",
    "new entries allowed": "CONTROL_ENGAGED", "reconciliation clean": "CONTROL_ENGAGED",
    "market open": "MARKET_CLOSED", "data fresh": "STALE_DATA", "not a duplicate": "DUPLICATE_ORDER",
    "order rate": "ORDER_RATE", "price within band": "BAD_PRICE", "quantity matches the sized target": "BAD_PRICE",
    "order size": "SIZE_OVER_LIMIT", "position limit": "SIZE_OVER_LIMIT", "gross exposure": "SIZE_OVER_LIMIT",
    "leverage": "SIZE_OVER_LIMIT", "asset-class exposure": "SIZE_OVER_LIMIT", "correlated exposure": "SIZE_OVER_LIMIT",
    "agent budget": "SIZE_OVER_LIMIT", "open positions": "SIZE_OVER_LIMIT", "shrunk quantity above zero": "SIZE_OVER_LIMIT",
    "liquidity": "LIQUIDITY",
}
BLOCKING = {"CONTROL_ENGAGED", "MARKET_CLOSED", "STALE_DATA", "DUPLICATE_ORDER", "ORDER_RATE", "EXECUTION_ERROR",
            "DATA_ERROR", "BAD_PRICE", "AGENT_LOSS_LIMIT"}


def _d(x: Any) -> Optional[Decimal]:
    return None if x is None else Decimal(str(x))


class Learning:
    def __init__(self, app: "App"):
        self.app = app
        self._lock = threading.RLock()
        self.lessons: dict[str, dict] = {r["root_cause"]: dict(r) for r in app.db.query("SELECT * FROM lessons")}
        self.cooldown: dict[str, int] = {}                  # instrument -> entries blocked until (ms)
        self.last_regression: Optional[dict] = None
        self._scan_from = int(app.db.get_setting("learning.scan_from") or now_ms())
        self._open: dict[str, dict] = {}                    # instrument -> running round trip being tracked

    # ------------------------------------------------------------------ 1-3: record, root cause, lesson
    def record(self, root_cause: str, *, agent_id: Optional[str], instrument_id: Optional[str], detail: dict,
               scenario: dict, ref: Optional[str] = None) -> dict:
        kind, what, safeguard, does = ROOT_CAUSES[root_cause]
        t = now_ms()
        if root_cause in ("EXECUTION_ERROR", "DATA_ERROR") and instrument_id and self.cooldown_left(instrument_id) > 0:
            return {"skipped": "instrument already in its error cooldown"}
        with self._lock:
            lesson = self.lessons.get(root_cause)
            repeat = lesson is not None
            mid = new_id("MIS")
            if root_cause in ("EXECUTION_ERROR", "DATA_ERROR") and instrument_id:
                self.cooldown[instrument_id] = t + COOLDOWN_MS
            if lesson is None:
                lesson = {"lesson_id": new_id("LES"), "created": t, "root_cause": root_cause, "kind": kind,
                          "first_agent": agent_id, "safeguard": safeguard, "description": does, "occurrences": 1,
                          "repeats": 0, "last_seen": t, "scenario": dumps(scenario)}
                self.app.db.execute("INSERT INTO lessons (lesson_id, created, root_cause, kind, first_agent, safeguard, "
                                    "description, occurrences, repeats, last_seen, scenario) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                                    tuple(lesson[k] for k in ("lesson_id", "created", "root_cause", "kind",
                                                              "first_agent", "safeguard", "description", "occurrences",
                                                              "repeats", "last_seen", "scenario")))
                self.lessons[root_cause] = lesson
            else:
                lesson["occurrences"] += 1
                lesson["repeats"] += 1
                lesson["last_seen"] = t
                self.app.db.execute("UPDATE lessons SET occurrences=?, repeats=?, last_seen=? WHERE root_cause=?",
                                    (lesson["occurrences"], lesson["repeats"], t, root_cause))
            self.app.db.execute("INSERT INTO mistakes (mistake_id, ts, agent_id, instrument_id, kind, root_cause, detail, "
                                "lesson_id, repeat, ref) VALUES (?,?,?,?,?,?,?,?,?,?)",
                                (mid, t, agent_id, instrument_id, kind, root_cause, dumps(detail), lesson["lesson_id"],
                                 int(repeat), ref))
        sev = "warning" if repeat else "info"
        msg = (f"repeat mistake {root_cause} by {agent_id or 'system'} on {instrument_id or '-'}: safeguard "
               f"'{safeguard}' was already active" if repeat else
               f"lesson learned from {agent_id or 'system'}: {root_cause} ({what}); safeguard '{safeguard}' now applies "
               f"to all agents: {does}")
        self.app.audit("learning", msg, severity=sev, data={"mistake": mid, "root_cause": root_cause, "detail": detail})
        self.app.bus.publish("learning", {"mistake_id": mid, "root_cause": root_cause, "agent": agent_id,
                                          "instrument": instrument_id, "repeat": repeat, "message": msg}, severity=sev)
        if not repeat:
            self.replay_all(f"new lesson {root_cause}")
        elif agent_id:
            recent = self.app.db.one("SELECT COUNT(*) AS n FROM mistakes WHERE agent_id=? AND root_cause=? AND repeat=1 "
                                     "AND ts>?", (agent_id, root_cause, t - DAY))
            if recent and recent["n"] >= 3:
                master = getattr(self.app, "fleet", None)
                if master is not None and hasattr(master, "suspend"):
                    master.suspend(agent_id, DAY, f"3 repeats of {root_cause} in 24 hours (safeguard gap under review)")
        return {"mistake_id": mid, "lesson_id": lesson["lesson_id"], "repeat": repeat}

    def record_rejection(self, req: Any, decision: Any, context: Optional[dict]) -> list[dict]:
        """A risk-service denial of an agent's ENTRY becomes one mistake per distinct root cause."""
        if getattr(req, "reduces_position", False) or not getattr(req, "agent_id", None):
            return []
        causes = []
        for c in decision.checks:
            rc = CHECK_CAUSE.get(c.name)
            if not c.passed and rc and rc not in causes:
                causes.append(rc)
        out = []
        for rc in causes:
            failed = [f"{c.name} ({c.detail})" for c in decision.checks if not c.passed and CHECK_CAUSE.get(c.name) == rc]
            out.append(self.record(rc, agent_id=req.agent_id, instrument_id=req.instrument_id,
                                   detail={"failed_checks": failed, "side": req.side, "qty": str(req.quantity)},
                                   scenario=dict(context or {}, cause=rc), ref=getattr(req, "client_order_id", None)))
        return out

    # ------------------------------------------------------------------ the shared pre-trade guard
    def active(self) -> set[str]:
        return set(self.lessons)

    def cooldown_left(self, instrument_id: str) -> float:
        return max(0.0, (self.cooldown.get(instrument_id, 0) - now_ms()) / 1000)

    def guard(self, ctx: dict, only: Optional[set[str]] = None) -> dict:
        """Apply the safeguards learned so far to an ENTRY proposal. Returns {allow, qty, applied}. A safeguard can only
        block or shrink: it never raises a quantity or loosens a limit."""
        on = self.active() if only is None else only
        qty = _d(ctx.get("qty")) or Decimal(0)
        q0 = qty
        applied: list[str] = []

        def block(rc: str, why: str) -> dict:
            return {"allow": False, "qty": Decimal(0), "applied": applied + [f"{rc}: {why}"]}
        if "CONTROL_ENGAGED" in on and ctx.get("controls_engaged"):
            return block("CONTROL_ENGAGED", str(ctx.get("controls_engaged")))
        if "AGENT_LOSS_LIMIT" in on and ctx.get("agent_day_stopped"):
            return block("AGENT_LOSS_LIMIT", "agent stopped for the day")
        if "MARKET_CLOSED" in on and ctx.get("session_open") is False:
            return block("MARKET_CLOSED", "session closed")
        if "STALE_DATA" in on and ctx.get("data_age_s") is not None and ctx.get("bar_seconds") and \
                float(ctx["data_age_s"]) > 2 * float(ctx["bar_seconds"]):
            return block("STALE_DATA", f"newest bar {float(ctx['data_age_s']):.0f}s old")
        if "DUPLICATE_ORDER" in on and (int(ctx.get("open_orders") or 0) > 0 or
                                        (ctx.get("last_entry_age_s") is not None and
                                         float(ctx["last_entry_age_s"]) < 60)):
            return block("DUPLICATE_ORDER", "working order or entry in the last 60 s")
        if "ORDER_RATE" in on and ctx.get("max_orders_per_minute") and \
                int(ctx.get("orders_last_minute") or 0) >= int(ctx["max_orders_per_minute"]) - 5:
            return block("ORDER_RATE", f"{ctx.get('orders_last_minute')} orders in the last minute")
        if ({"EXECUTION_ERROR", "DATA_ERROR"} & on) and float(ctx.get("cooldown_s") or 0) > 0:
            return block("EXECUTION_ERROR" if "EXECUTION_ERROR" in on else "DATA_ERROR",
                         f"cooldown {float(ctx['cooldown_s']):.0f}s after an error")
        if "BAD_PRICE" in on and ctx.get("price_deviation") is not None and ctx.get("max_price_deviation") and \
                float(ctx["price_deviation"]) > 0.8 * float(ctx["max_price_deviation"]):
            return block("BAD_PRICE", f"price {float(ctx['price_deviation']):.2%} from the last close")
        if "LOSS_BEYOND_PLAN_HIGH_VOL" in on and ctx.get("vol_regime") == "high":
            qty = qty * Decimal("0.5")
            applied.append("LOSS_BEYOND_PLAN_HIGH_VOL: half size in high volatility")
        if "LOSS_BEYOND_PLAN_SLIPPAGE" in on and ctx.get("market") in self._haircut_markets(only):
            qty = qty * Decimal("0.75")
            applied.append(f"LOSS_BEYOND_PLAN_SLIPPAGE: 25% smaller in {ctx.get('market')}")
        if "LIQUIDITY" in on and ctx.get("participation_qty") is not None:
            cap = Decimal(str(ctx["participation_qty"])) * Decimal("0.8")
            if qty > cap:
                qty = cap
                applied.append("LIQUIDITY: shrunk to 80% of the volume cap")
        if "SIZE_OVER_LIMIT" in on and ctx.get("limits"):
            notional_unit = (_d(ctx.get("price")) or Decimal(0)) * (_d(ctx.get("multiplier")) or Decimal(1))
            tight = min(Decimal(str(v)) for v in ctx["limits"].values())
            if tight <= 0 or notional_unit <= 0:
                return block("SIZE_OVER_LIMIT", "no room left under the tightest limit")
            cap = tight * Decimal("0.95") / notional_unit
            if qty > cap:
                qty = cap
                applied.append("SIZE_OVER_LIMIT: shrunk to 95% of the tightest limit")
        step = _d(ctx.get("quantity_step"))
        if step and step > 0 and qty != q0:
            qty = (qty / step).to_integral_value(ROUND_DOWN) * step
        if qty <= 0 and q0 > 0:
            return block(applied[-1].split(":")[0] if applied else "SIZE_OVER_LIMIT", "shrunk to zero")
        return {"allow": True, "qty": qty, "applied": applied}

    def _haircut_markets(self, only: Optional[set[str]]) -> set[str]:
        les = self.lessons.get("LOSS_BEYOND_PLAN_SLIPPAGE")
        if not les:
            return set()
        import json
        rows = self.app.db.query("SELECT detail FROM mistakes WHERE root_cause='LOSS_BEYOND_PLAN_SLIPPAGE'")
        return {json.loads(r["detail"]).get("market") for r in rows} | {json.loads(les["scenario"]).get("market")}

    # ------------------------------------------------------------------ 4: regression replay
    def replay_one(self, root_cause: str, scenario: dict) -> tuple[bool, str]:
        if root_cause == "VERSION_UNDERPERFORMED":
            # read the version table itself: this replay also runs at start-up, before the master exists
            aid, ver = scenario.get("agent_id"), scenario.get("version")
            row = self.app.db.one("SELECT status FROM agent_versions WHERE agent_id=? AND version=?", (aid, ver))
            ok = row is None or row["status"] != "active"
            return ok, "the rolled-back version is not active" if ok else f"{aid} v{ver} is active again"
        out = self.guard(scenario, only={root_cause})
        q0 = _d(scenario.get("qty")) or Decimal(0)
        if root_cause in BLOCKING:
            return (not out["allow"]), "blocked" if not out["allow"] else "NOT blocked"
        if root_cause == "LOSS_BEYOND_PLAN_HIGH_VOL":
            ok = (not out["allow"]) or out["qty"] <= q0 * Decimal("0.5") + Decimal("1e-12")
            return ok, f"qty {out['qty']} vs {q0}"
        if root_cause == "LOSS_BEYOND_PLAN_SLIPPAGE":
            ok = (not out["allow"]) or out["qty"] <= q0 * Decimal("0.75") + Decimal("1e-12")
            return ok, f"qty {out['qty']} vs {q0}"
        if root_cause == "LIQUIDITY":
            cap = (_d(scenario.get("participation_qty")) or Decimal(0)) * Decimal("0.8")
            ok = (not out["allow"]) or out["qty"] <= cap + Decimal("1e-12")
            return ok, f"qty {out['qty']} vs cap {cap}"
        if root_cause == "SIZE_OVER_LIMIT":
            unit = (_d(scenario.get("price")) or Decimal(0)) * (_d(scenario.get("multiplier")) or Decimal(1))
            tight = min(Decimal(str(v)) for v in (scenario.get("limits") or {"x": 0}).values())
            ok = (not out["allow"]) or out["qty"] * unit <= tight * Decimal("0.95") + Decimal("1e-6")
            return ok, f"notional {out['qty'] * unit} vs limit {tight}"
        return False, "no replay rule"

    def replay_all(self, trigger: str) -> dict:
        import json
        failed, n = [], 0
        for rc, les in list(self.lessons.items()):
            n += 1
            try:
                ok, why = self.replay_one(rc, json.loads(les["scenario"]))
            except Exception as e:                            # noqa: BLE001 - a broken replay is a failure, shown
                ok, why = False, f"{type(e).__name__}: {e}"
            if not ok:
                failed.append({"root_cause": rc, "why": why})
        run = {"run_id": new_id("REG"), "ts": now_ms(), "scenarios": n, "passed": n - len(failed),
               "failed": failed, "trigger": trigger}
        self.app.db.execute("INSERT INTO regression_runs (run_id, ts, scenarios, passed, failed, trigger) VALUES "
                            "(?,?,?,?,?,?)", (run["run_id"], run["ts"], n, n - len(failed), dumps(failed), trigger))
        self.last_regression = run
        if failed:
            self.app.audit("learning", f"regression replay: {len(failed)} of {n} scenario(s) FAILED", severity="error",
                           data=run)
        return run

    # ------------------------------------------------------------------ loss beyond plan (closed paper round trips)
    def scan_trades(self) -> list[dict]:
        """Walk paper fills in time order; when a position returns to flat, compare the trip's loss with the planned
        risk recorded by the entry decision."""
        import json
        rows = self.app.db.query("SELECT f.fill_id, f.instrument_id, f.side, f.qty, f.price, f.fee, f.ts, "
                                 "o.decision_id FROM fills f LEFT JOIN orders o ON o.client_order_id=f.client_order_id "
                                 "WHERE f.environment='paper' AND f.ts>? ORDER BY f.ts", (self._scan_from,))
        found = []
        for r in rows:
            iid = r["instrument_id"]
            st = self._open.setdefault(iid, {"qty": Decimal(0), "cash": Decimal(0), "decision": None})
            q = Decimal(r["qty"]) * (1 if r["side"] == "buy" else -1)
            if st["qty"] == 0:
                st["decision"] = r["decision_id"]
            st["qty"] += q
            mult = self.app.book.get(iid).multiplier if iid in self.app.book else Decimal(1)
            st["cash"] -= q * Decimal(r["price"]) * mult + Decimal(r["fee"])
            if st["qty"] == 0:
                pnl, dec = st["cash"], st["decision"]
                self._open[iid] = {"qty": Decimal(0), "cash": Decimal(0), "decision": None}
                d = self.app.db.one("SELECT order_json, regime, bot_id FROM decisions WHERE decision_id=?", (dec,)) \
                    if dec else None
                plan = (json.loads(d["order_json"] or "{}") or {}).get("planned_risk") if d else None
                if plan and pnl < 0 and -pnl > Decimal("1.5") * Decimal(str(plan)):
                    regime = (json.loads(d["regime"] or "{}") or {}).get("volatility")
                    inst = self.app.book.get(iid)
                    from tradingai.strategies.library import MARKET_OF
                    market = MARKET_OF.get(inst.market_type)
                    rc = "LOSS_BEYOND_PLAN_HIGH_VOL" if regime == "high" else "LOSS_BEYOND_PLAN_SLIPPAGE"
                    owner = self.app.fleet.owner_of(iid) if hasattr(self.app, "fleet") else None
                    found.append(self.record(rc, agent_id=owner, instrument_id=iid,
                                             detail={"loss": str(-pnl), "planned_risk": str(plan), "market": market,
                                                     "regime": regime},
                                             scenario={"qty": "1", "vol_regime": regime, "market": market,
                                                       "instrument_id": iid}, ref=dec))
            self._scan_from = max(self._scan_from, int(r["ts"]))
        self.app.db.set_setting("learning.scan_from", self._scan_from)
        return found

    # ------------------------------------------------------------------ 5: measurable evidence
    def metrics(self) -> dict:
        t = now_ms()

        def window(a: int, b: int) -> dict:
            m = self.app.db.one("SELECT COUNT(*) AS n, SUM(repeat) AS r FROM mistakes WHERE ts>? AND ts<=?", (a, b))
            d = self.app.db.one("SELECT COUNT(*) AS n FROM decisions WHERE ts>? AND ts<=?", (a, b))
            n, dn = int(m["n"] or 0), int(d["n"] or 0)
            return {"mistakes": n, "repeats": int(m["r"] or 0), "decisions": dn,
                    "per_100_decisions": None if not dn else round(100 * n / dn, 2)}
        by = self.app.db.query("SELECT root_cause, COUNT(*) AS n, SUM(repeat) AS r FROM mistakes GROUP BY root_cause "
                               "ORDER BY n DESC")
        return {"this_week": window(t - 7 * DAY, t), "last_week": window(t - 14 * DAY, t - 7 * DAY),
                "lessons": len(self.lessons), "by_root_cause": [dict(r) for r in by],
                "regression": self.last_regression}

    def view(self) -> dict:
        import json
        lessons = []
        for rc, les in sorted(self.lessons.items(), key=lambda kv: kv[1]["created"]):
            lessons.append({k: les[k] for k in ("lesson_id", "created", "root_cause", "kind", "first_agent", "safeguard",
                                                 "description", "occurrences", "repeats", "last_seen")})
        mistakes = [dict(r, detail=json.loads(r["detail"])) for r in self.app.db.query(
            "SELECT * FROM mistakes ORDER BY ts DESC LIMIT 100")]
        runs = [dict(r, failed=json.loads(r["failed"])) for r in self.app.db.query(
            "SELECT * FROM regression_runs ORDER BY ts DESC LIMIT 20")]
        return {"metrics": self.metrics(), "lessons": lessons, "mistakes": mistakes, "regression_runs": runs,
                "root_causes": {k: {"kind": v[0], "what": v[1], "safeguard": v[2], "does": v[3]}
                                for k, v in ROOT_CAUSES.items()},
                "note": "Safeguards only block or shrink entries; the risk service still checks every order. This "
                        "aims to prevent known mistakes from recurring; it cannot guarantee an agent never repeats one."}

    def tick(self) -> None:
        """Periodic work: scan closed trades. Called by the master every cycle."""
        try:
            self.scan_trades()
        except Exception as e:                                # noqa: BLE001 - reported, never fatal
            self.app.bus.publish("system.error", {"error": f"learning scan: {type(e).__name__}: {e}"}, severity="error")
        if self.last_regression is None or time.time() * 1000 - self.last_regression["ts"] > 3_600_000:
            self.replay_all("hourly")
