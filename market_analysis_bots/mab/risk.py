"""Portfolio risk layer. Every order intent passes through `check()` before execution.

Exits that only reduce a position are always allowed (a risk layer that could trap a losing
position would be a risk in itself). Entries must pass every check below; each check's outcome
is recorded with the intent, whether or not the order goes ahead.
"""

from __future__ import annotations

import threading
from collections import deque
from dataclasses import asdict, dataclass, field
from typing import Deque, Dict, List, Optional

from mab.models import OrderIntent, RiskDecision, now_ms


@dataclass
class RiskLimits:
    max_gross_exposure_pct: float = 100.0         # sum of |position value| / equity (no leverage)
    max_instrument_exposure_pct: float = 25.0     # |net value in one instrument| / equity
    max_open_positions: int = 20
    daily_loss_limit_pct: float = 3.0             # portfolio: halts new entries for the rest of the day
    max_drawdown_pct: float = 15.0                # from the equity peak: triggers the emergency stop
    bot_daily_loss_limit_pct: float = 1.0         # per bot, of total equity: pauses that bot for the day
    max_orders_per_minute: int = 30               # whole fleet
    max_orders_per_minute_per_bot: int = 4
    conflict_policy: str = "block"                # opposite-direction entries on an instrument other bots hold
    max_price_age_bars: float = 3.0               # the reference price must be this fresh


class RiskManager:
    def __init__(self, limits: Optional[RiskLimits] = None):
        self.limits = limits or RiskLimits()
        self.lock = threading.RLock()
        self.day: Optional[str] = None
        self.day_start_equity: Optional[float] = None
        self.peak_equity: Optional[float] = None
        self.halted_for_day: Optional[str] = None
        self.orders: Deque[int] = deque()
        self.bot_orders: Dict[str, Deque[int]] = {}
        self.seen: Dict[str, int] = {}
        self.bot_day_pnl: Dict[str, float] = {}
        self.paused_bots: Dict[str, str] = {}        # bot -> reason (cleared at the next day)
        self.events: List[dict] = []

    # ------------------------------------------------------------------ day roll / marks
    def on_equity(self, equity: float, day: str) -> List[dict]:
        """Called every cycle. Returns risk events (e.g. drawdown kill switch)."""
        ev = []
        with self.lock:
            if day != self.day:
                self.day, self.day_start_equity = day, equity
                self.halted_for_day = None
                self.bot_day_pnl.clear()
                self.paused_bots = {k: v for k, v in self.paused_bots.items() if not v.startswith("daily")}
            self.peak_equity = equity if self.peak_equity is None else max(self.peak_equity, equity)
            if self.day_start_equity and not self.halted_for_day:
                loss = (self.day_start_equity - equity) / self.day_start_equity * 100
                if loss >= self.limits.daily_loss_limit_pct:
                    self.halted_for_day = f"portfolio daily loss {loss:.2f}% >= {self.limits.daily_loss_limit_pct}%"
                    ev.append({"kind": "daily_loss_halt", "level": "warning", "message": self.halted_for_day})
            if self.peak_equity:
                dd = (self.peak_equity - equity) / self.peak_equity * 100
                if dd >= self.limits.max_drawdown_pct:
                    ev.append({"kind": "drawdown_kill_switch", "level": "critical",
                               "message": f"drawdown {dd:.2f}% >= {self.limits.max_drawdown_pct}%: emergency stop"})
        return ev

    def reset_peak(self, equity: float):
        """After the balance is changed by a cash flow, drawdown restarts from the new balance."""
        with self.lock:
            self.peak_equity = equity
            self.day_start_equity = equity

    def on_trade_closed(self, bot_id: str, pnl: float, equity: float) -> Optional[dict]:
        with self.lock:
            self.bot_day_pnl[bot_id] = self.bot_day_pnl.get(bot_id, 0.0) + pnl
            lim = -self.limits.bot_daily_loss_limit_pct / 100 * equity
            if self.bot_day_pnl[bot_id] <= lim and bot_id not in self.paused_bots:
                self.paused_bots[bot_id] = f"daily loss limit ({self.bot_day_pnl[bot_id]:,.2f})"
                return {"kind": "bot_daily_loss_pause", "level": "warning", "bot_id": bot_id,
                        "message": f"{bot_id} paused for the rest of the day: {self.paused_bots[bot_id]}"}
        return None

    # ------------------------------------------------------------------ the check
    def check(self, intent: OrderIntent, ctx: dict) -> RiskDecision:
        """ctx: equity, positions (list of dicts with bot_id, venue, instrument, qty, value),
        gross, net_by_instrument, paused, emergency, bot_enabled, data_status, price_age_ms,
        bar_ms, ref_price."""
        L = self.limits
        checks: List[dict] = []
        qty = intent.quantity
        now = now_ms()

        def add(name, ok, detail=""):
            checks.append({"check": name, "passed": bool(ok), "detail": detail})
            return ok

        with self.lock:
            dup = intent.intent_id in self.seen
            add("unique intent", not dup, "duplicate intent id: already processed" if dup else "")
            if dup:
                return RiskDecision(intent.intent_id, intent.bot_id, False, None, checks, now)
            self.seen[intent.intent_id] = now
            if len(self.seen) > 50_000:
                for k in list(self.seen)[:10_000]:
                    self.seen.pop(k, None)
            if intent.reduce_only:
                add("reduce-only exit", True, "exits are always allowed")
                self._count(intent.bot_id, now)
                return RiskDecision(intent.intent_id, intent.bot_id, True, qty, checks, now)
            ok = True
            ok &= add("emergency stop off", not ctx.get("emergency"), "emergency stop is active" if ctx.get("emergency") else "")
            ok &= add("fleet not paused", not ctx.get("paused"), "fleet paused by operator" if ctx.get("paused") else "")
            ok &= add("bot enabled", ctx.get("bot_enabled", True), "")
            pr = self.paused_bots.get(intent.bot_id)
            ok &= add("bot not paused by risk", pr is None, pr or "")
            ok &= add("data quality ok", ctx.get("data_status") == "ok", f"series status: {ctx.get('data_status')}")
            age, bar = ctx.get("price_age_ms"), ctx.get("bar_ms") or 60_000
            fresh = age is not None and age <= L.max_price_age_bars * bar
            ok &= add("price fresh", fresh, f"reference price age {age / 1000 if age is not None else 'n/a'}s")
            ok &= add("daily loss limit", self.halted_for_day is None, self.halted_for_day or "")
            self._trim(now)
            rate_ok = len(self.orders) < L.max_orders_per_minute
            ok &= add("fleet order rate", rate_ok, f"{len(self.orders)} orders in the last minute")
            bq = self.bot_orders.get(intent.bot_id, deque())
            ok &= add("bot order rate", len(bq) < L.max_orders_per_minute_per_bot, f"{len(bq)} in the last minute")
            n_open = len(ctx.get("positions", []))
            ok &= add("open position limit", n_open < L.max_open_positions, f"{n_open} open of {L.max_open_positions}")
            inst_key = f"{intent.venue}:{intent.instrument}"
            others = [p for p in ctx.get("positions", []) if f"{p['venue']}:{p['instrument']}" == inst_key
                      and p["bot_id"] != intent.bot_id]
            sgn = 1 if intent.side == "buy" else -1
            opposite = [p for p in others if p["qty"] * sgn < 0]
            if L.conflict_policy == "block":
                ok &= add("no conflicting position", not opposite,
                          f"{len(opposite)} other bot(s) hold the opposite side" if opposite else "")
            equity = max(ctx.get("equity", 0.0), 1e-9)
            px = ctx.get("ref_price") or 0.0
            net = ctx.get("net_by_instrument", {}).get(inst_key, 0.0)
            cap_inst = L.max_instrument_exposure_pct / 100 * equity
            room_inst = max(0.0, cap_inst - abs(net + 0.0)) if net * sgn >= 0 else cap_inst + abs(net)
            cap_gross = L.max_gross_exposure_pct / 100 * equity
            room_gross = max(0.0, cap_gross - ctx.get("gross", 0.0))
            room = min(room_inst, room_gross)
            adj = qty
            if px > 0 and qty * px > room:
                adj = room / px
            enough = px > 0 and adj * px >= 0.25 * qty * px and adj > 0
            ok &= add("exposure limits", enough,
                      f"instrument room {room_inst:,.0f}, gross room {room_gross:,.0f}; order {qty * px:,.0f}"
                      + (f" reduced to {adj * px:,.0f}" if adj < qty else ""))
            if ok:
                self._count(intent.bot_id, now)
            return RiskDecision(intent.intent_id, intent.bot_id, bool(ok), adj if ok else None, checks, now)

    def _trim(self, now):
        while self.orders and now - self.orders[0] > 60_000:
            self.orders.popleft()
        for q in self.bot_orders.values():
            while q and now - q[0] > 60_000:
                q.popleft()

    def _count(self, bot_id, now):
        self.orders.append(now)
        self.bot_orders.setdefault(bot_id, deque()).append(now)

    def to_state(self) -> dict:
        with self.lock:
            return {"day": self.day, "day_start_equity": self.day_start_equity, "peak_equity": self.peak_equity,
                    "halted_for_day": self.halted_for_day, "bot_day_pnl": dict(self.bot_day_pnl),
                    "paused_bots": dict(self.paused_bots), "limits": asdict(self.limits)}

    def restore(self, st: dict):
        with self.lock:
            self.day, self.day_start_equity = st.get("day"), st.get("day_start_equity")
            self.peak_equity, self.halted_for_day = st.get("peak_equity"), st.get("halted_for_day")
            self.bot_day_pnl = dict(st.get("bot_day_pnl", {}))
            self.paused_bots = dict(st.get("paused_bots", {}))
