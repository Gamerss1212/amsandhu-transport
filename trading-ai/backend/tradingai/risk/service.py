"""The deterministic risk service (sections 171-175, 259, 286, 310-312). Every order passes through `check()`.

Rules of the module:
* Pure, deterministic code. No model, agent or language model can call anything here that loosens a limit.
* A check can only APPROVE, SHRINK (never grow) or DENY an order. DENY means the order is not submitted.
* Limits: lowering is always allowed; RAISING a limit needs the owner's typed confirmation through the API
  (`update_limits(..., confirm=RAISE_PHRASE)`), and every change is written to the audit log.
* STOP ALL TRADING (kill switch): blocks every new order, asks the OMS to cancel working orders, optionally flattens,
  and stays engaged until the owner re-arms it with a typed phrase. The daily/weekly-loss and drawdown breakers lock
  trading the same way; no agent can unlock them.
"""

from __future__ import annotations

import threading
import time
from dataclasses import asdict, dataclass, field, fields
from decimal import ROUND_DOWN, Decimal
from typing import Any, Callable, Optional

RAISE_PHRASE = "RAISE MY RISK LIMITS"
REARM_PHRASE = "RE-ARM TRADING"
MARKETS = ("crypto", "stock", "etf", "fx", "future")


@dataclass
class Limits:
    max_order_pct_equity: float = 0.10          # one order's notional / equity
    max_position_pct_equity: float = 0.25       # one instrument's notional / equity
    max_asset_class_pct: dict = field(default_factory=lambda: {"crypto": 0.5, "stock": 1.0, "etf": 1.0, "fx": 2.0,
                                                               "future": 2.0})
    max_gross_exposure: float = 1.5             # sum of |notional| / equity
    max_leverage: float = 2.0
    max_correlated_pct: float = 0.35            # one correlation cluster's notional / equity
    max_open_positions: int = 10
    max_daily_loss_pct: float = 0.03            # realized + unrealized vs the day's starting equity -> LOCK
    max_weekly_loss_pct: float = 0.06
    max_drawdown_pct: float = 0.15              # from the equity peak -> LOCK
    max_orders_per_minute: int = 20
    max_price_deviation_pct: float = 0.05       # a limit/reference price this far from the last price -> fat finger
    max_qty_vs_target: float = 1.5              # an order bigger than 1.5x the sized target -> fat finger
    max_participation: float = 0.10             # of the last bar's volume, when volume is known
    stale_data_bars: float = 3.0                # newest bar older than this many bars -> STALE
    max_spread_bps: float = 50.0                # when quotes are known
    duplicate_window_s: float = 10.0
    emergency_flatten: bool = False             # kill switch: cancel only (default) or also flatten positions


@dataclass
class Check:
    name: str
    passed: bool
    detail: str


@dataclass
class RiskDecision:
    approved: bool
    quantity: Decimal
    checks: list[Check]
    reason: str
    adjusted: bool = False
    ts: int = 0

    def as_dict(self) -> dict:
        return {"approved": self.approved, "quantity": str(self.quantity), "adjusted": self.adjusted,
                "reason": self.reason, "ts": self.ts, "checks": [asdict(c) for c in self.checks]}


@dataclass
class OrderRequest:
    client_order_id: str
    instrument_id: str
    market: str                     # crypto / stock / etf / fx / future
    side: str                       # buy / sell
    quantity: Decimal
    reference_price: Decimal        # last trusted price
    limit_price: Optional[Decimal]
    multiplier: Decimal
    environment: str                # paper / shadow / live
    account_id: str
    sized_target: Optional[Decimal] = None
    reduces_position: bool = False
    tradable: tuple[bool, str] = (True, "ok")
    permitted: tuple[bool, str] = (True, "ok")       # broker-reported product permission (live)
    quantity_step: Decimal = Decimal("1e-8")         # a shrunk order is rounded DOWN to the venue's step


@dataclass
class Snapshot:
    equity: Decimal
    positions: dict                 # instrument_id -> {"qty": Decimal, "price": Decimal, "multiplier": Decimal, "market"}
    clusters: list = field(default_factory=list)      # lists of instrument ids that move together
    data_age_s: Optional[float] = None
    bar_seconds: float = 60.0
    last_volume: Optional[float] = None
    spread_bps: Optional[float] = None
    market_open: bool = True
    broker_ok: bool = True
    reconciliation_ok: bool = True
    event_block: Optional[str] = None
    account_ok: bool = True
    account_id: Optional[str] = None                 # the account the broker reports; must equal the order's
    environment: Optional[str] = None                # paper / live, as the broker reports it


class RiskService:
    def __init__(self, limits: Optional[Limits] = None, audit: Optional[Callable[..., Any]] = None,
                 on_kill: Optional[Callable[[str], None]] = None):
        self.limits = limits or Limits()
        self._lock = threading.RLock()
        self.kill_switch: Optional[dict] = None
        self.trading_locked: Optional[dict] = None
        self.day_start_equity: Optional[Decimal] = None
        self.week_start_equity: Optional[Decimal] = None
        self.peak_equity: Optional[Decimal] = None
        self.day_key: Optional[str] = None
        self.week_key: Optional[str] = None
        self.recent: list[tuple[float, str, str, str, str]] = []     # (time, client id, instrument, side, qty)
        self.audit = audit or (lambda *a, **k: None)
        self.on_kill = on_kill
        self.counters = {"approved": 0, "denied": 0, "adjusted": 0, "duplicates_blocked": 0}

    # ------------------------------------------------------------------ the check
    def check(self, o: OrderRequest, s: Snapshot) -> RiskDecision:
        with self._lock:
            L = self.limits
            checks: list[Check] = []
            qty = o.quantity
            adjusted = False

            def add(name: str, ok: bool, detail: str) -> bool:
                checks.append(Check(name, bool(ok), detail))
                return ok
            # "reduces the position" is verified from the broker's positions, never taken from the caller
            held = Decimal(str(s.positions.get(o.instrument_id, {}).get("qty", 0)))
            reduce_only = bool(o.reduces_position) and held != 0 and qty <= abs(held) and \
                ((held > 0 and o.side == "sell") or (held < 0 and o.side == "buy"))
            if o.reduces_position and not reduce_only:
                add("reduce-only claim verified", False, f"order {o.side} {qty} does not reduce the held {held}")
            add("kill switch not engaged", self.kill_switch is None or reduce_only,
                "engaged: " + self.kill_switch["reason"] if self.kill_switch else "armed")
            add("trading not locked", self.trading_locked is None or reduce_only,
                self.trading_locked["reason"] if self.trading_locked else "open")
            add("instrument tradable", o.tradable[0], o.tradable[1])
            add("broker permits this product", o.permitted[0], o.permitted[1])
            acct_match = s.account_id is None or o.account_id == s.account_id
            env_match = s.environment is None or o.environment == "shadow" or o.environment == s.environment
            add("account validated", s.account_ok and acct_match and env_match,
                "account identity confirmed" if s.account_ok and acct_match and env_match else
                f"account/environment mismatch (order {o.account_id}/{o.environment}, broker "
                f"{s.account_id}/{s.environment})")
            add("known market", o.market in MARKETS, o.market)
            add("broker connected", s.broker_ok, "ok" if s.broker_ok else "broker connection down")
            add("reconciliation clean", s.reconciliation_ok or reduce_only,
                "ok" if s.reconciliation_ok else "RECONCILIATION_REQUIRED")
            add("market open", s.market_open, "open" if s.market_open else "market closed")
            stale = s.data_age_s is not None and s.data_age_s > L.stale_data_bars * s.bar_seconds
            add("data fresh", not stale or reduce_only, f"newest bar {s.data_age_s:.0f}s old" if s.data_age_s is not None
                else "age unknown")
            add("no event restriction", s.event_block is None or reduce_only, s.event_block or "none")
            add("positive quantity", qty > 0, f"quantity {qty}")
            add("valid side", o.side in ("buy", "sell"), o.side)
            add("valid price", o.reference_price > 0, f"reference {o.reference_price}")
            add("valid contract multiplier", o.multiplier > 0, f"multiplier {o.multiplier}")
            # fat finger
            if o.limit_price is not None and o.reference_price > 0:
                dev = abs(float(o.limit_price / o.reference_price) - 1)
                add("price within band", dev <= L.max_price_deviation_pct,
                    f"{dev:.2%} from the last price (max {L.max_price_deviation_pct:.0%})")
            if o.sized_target is not None and o.sized_target > 0 and not reduce_only:
                add("quantity matches the sized target", qty <= o.sized_target * Decimal(str(L.max_qty_vs_target)),
                    f"order {qty} vs sized target {o.sized_target}")
            # duplicate orders
            now = time.time()
            self.recent = [r for r in self.recent if now - r[0] <= L.duplicate_window_s]
            dup = any(r[1] == o.client_order_id or (r[2], r[3], r[4]) == (o.instrument_id, o.side, str(qty))
                      for r in self.recent)
            if dup:
                self.counters["duplicates_blocked"] += 1
            add("not a duplicate", not dup, "same order seen in the last "
                f"{L.duplicate_window_s:.0f}s" if dup else "new")
            add("order rate", sum(1 for r in self.recent if now - r[0] <= 60) < L.max_orders_per_minute,
                f"{sum(1 for r in self.recent if now - r[0] <= 60)} orders in the last minute")
            eq = s.equity
            add("positive equity", eq > 0, f"equity {eq}")
            if eq > 0 and not reduce_only:
                px = o.reference_price * o.multiplier
                notional = qty * px
                max_order = eq * Decimal(str(L.max_order_pct_equity))
                if notional > max_order:                         # shrink to the limit, never grow
                    step = o.quantity_step if o.quantity_step > 0 else Decimal("1e-8")
                    new_q = (max_order / px / step).to_integral_value(ROUND_DOWN) * step
                    if new_q < qty:
                        qty, adjusted = new_q, True
                        add("shrunk quantity above zero", qty > 0, f"shrunk to {qty} (step {step})")
                add("order size", qty * px <= max_order + Decimal("1e-6"),
                    f"{qty * px:,.2f} vs max {max_order:,.2f}" + (" (shrunk)" if adjusted else ""))
                cur = s.positions.get(o.instrument_id, {})
                cur_qty = Decimal(str(cur.get("qty", 0)))
                signed = qty if o.side == "buy" else -qty
                after = abs(cur_qty + signed) * px
                add("position limit", after <= eq * Decimal(str(L.max_position_pct_equity)),
                    f"{after:,.2f} vs max {eq * Decimal(str(L.max_position_pct_equity)):,.2f}")
                gross_now = sum(abs(Decimal(str(p["qty"]))) * Decimal(str(p["price"])) * Decimal(str(p.get("multiplier",
                                1))) for k, p in s.positions.items() if k != o.instrument_id)
                gross_after = gross_now + after
                add("gross exposure", gross_after <= eq * Decimal(str(L.max_gross_exposure)),
                    f"{gross_after / eq:.2f}x vs max {L.max_gross_exposure}x")
                add("leverage", gross_after / eq <= Decimal(str(L.max_leverage)),
                    f"{gross_after / eq:.2f}x vs max {L.max_leverage}x")
                cls = sum(abs(Decimal(str(p["qty"]))) * Decimal(str(p["price"])) * Decimal(str(p.get("multiplier", 1)))
                          for k, p in s.positions.items() if p.get("market") == o.market and k != o.instrument_id)
                cap = L.max_asset_class_pct.get(o.market, 1.0)
                add("asset-class exposure", cls + after <= eq * Decimal(str(cap)),
                    f"{(cls + after) / eq:.2f}x of equity in {o.market} vs max {cap}x")
                for group in s.clusters:
                    if o.instrument_id in group:
                        g = sum(abs(Decimal(str(s.positions[k]["qty"]))) * Decimal(str(s.positions[k]["price"])) *
                                Decimal(str(s.positions[k].get("multiplier", 1)))
                                for k in group if k in s.positions and k != o.instrument_id) + after
                        add("correlated exposure", g <= eq * Decimal(str(L.max_correlated_pct)),
                            f"cluster {group}: {g / eq:.2f}x vs max {L.max_correlated_pct}x")
                opened = sum(1 for p in s.positions.values() if Decimal(str(p["qty"])) != 0)
                add("open positions", cur_qty != 0 or opened < L.max_open_positions,
                    f"{opened} open vs max {L.max_open_positions}")
                if s.last_volume is not None and s.last_volume > 0:
                    part = float(qty) / s.last_volume
                    add("liquidity", part <= L.max_participation, f"{part:.1%} of the last bar's volume "
                        f"(max {L.max_participation:.0%})")
                if s.spread_bps is not None:
                    add("spread", s.spread_bps <= L.max_spread_bps, f"{s.spread_bps:.1f} bp vs max {L.max_spread_bps}")
            ok = all(c.passed for c in checks)
            failed = [c for c in checks if not c.passed]
            reason = "approved" + (" (quantity reduced)" if adjusted else "") if ok else \
                "DENIED: " + "; ".join(f"{c.name} ({c.detail})" for c in failed)
            if ok:
                self.recent.append((now, o.client_order_id, o.instrument_id, o.side, str(qty)))
                self.counters["approved"] += 1
                if adjusted:
                    self.counters["adjusted"] += 1
            else:
                self.counters["denied"] += 1
            return RiskDecision(ok, qty if ok else Decimal(0), checks, reason, adjusted, int(now * 1000))

    # ------------------------------------------------------------------ equity breakers
    def on_equity(self, equity: Decimal, day_key: str, week_key: str) -> list[str]:
        """Update the loss and drawdown breakers. Returns the breakers that fired (they LOCK trading)."""
        fired = []
        with self._lock:
            if self.day_key != day_key or self.day_start_equity is None:
                self.day_key, self.day_start_equity = day_key, equity
            if self.week_key != week_key or self.week_start_equity is None:
                self.week_key, self.week_start_equity = week_key, equity
            self.peak_equity = equity if self.peak_equity is None else max(self.peak_equity, equity)
            L = self.limits
            checks = (("daily loss", self.day_start_equity, L.max_daily_loss_pct),
                      ("weekly loss", self.week_start_equity, L.max_weekly_loss_pct),
                      ("drawdown", self.peak_equity, L.max_drawdown_pct))
            for name, ref, lim in checks:
                if ref and ref > 0 and (ref - equity) / ref >= Decimal(str(lim)) and self.trading_locked is None:
                    self.trading_locked = {"reason": f"{name} limit reached: {(ref - equity) / ref:.2%} "
                                           f"(limit {lim:.0%})", "ts": int(time.time() * 1000)}
                    self.audit("risk", f"TRADING_LOCKED by the {name} breaker", severity="critical",
                               data=self.trading_locked)
                    fired.append(name)
        return fired

    def usage(self, s: Snapshot) -> dict:
        """How much of each limit is used now, for the risk panel and the risk agents."""
        L = self.limits
        eq = float(s.equity) if s.equity else 0.0
        pos = s.positions
        notion = {k: abs(float(p["qty"])) * float(p["price"]) * float(p.get("multiplier", 1)) for k, p in pos.items()}
        gross = sum(notion.values())
        out = {"gross_exposure": gross / eq / L.max_gross_exposure if eq > 0 else None,
               "leverage": gross / eq / L.max_leverage if eq > 0 else None,
               "position": (max(notion.values()) / eq / L.max_position_pct_equity) if eq > 0 and notion else 0.0,
               "concentration": (max(notion.values()) / gross) if gross > 0 else 0.0,
               "correlated_exposure": max([sum(notion.get(k, 0) for k in g) / eq / L.max_correlated_pct
                                           for g in s.clusters] or [0.0]) if eq > 0 else None}
        if self.day_start_equity and self.day_start_equity > 0:
            loss = float((self.day_start_equity - s.equity) / self.day_start_equity)
            out["daily_loss"] = max(0.0, loss) / L.max_daily_loss_pct
        if self.peak_equity and self.peak_equity > 0:
            dd = float((self.peak_equity - s.equity) / self.peak_equity)
            out["drawdown"] = max(0.0, dd) / L.max_drawdown_pct
        return {k: (None if v is None else round(v, 4)) for k, v in out.items()}

    # ------------------------------------------------------------------ kill switch and locks
    def engage_kill_switch(self, reason: str, by: str) -> dict:
        with self._lock:
            self.kill_switch = {"reason": reason[:300], "by": by, "ts": int(time.time() * 1000)}
        self.audit("kill_switch", f"STOP ALL TRADING engaged by {by}: {reason}", severity="critical",
                   data=self.kill_switch)
        if self.on_kill:
            self.on_kill(reason)
        return self.kill_switch

    def rearm(self, phrase: str, by: str) -> dict:
        if phrase.strip() != REARM_PHRASE:
            raise PermissionError(f"type {REARM_PHRASE!r} exactly to re-arm trading")
        with self._lock:
            was = {"kill_switch": self.kill_switch, "trading_locked": self.trading_locked}
            self.kill_switch = None
            self.trading_locked = None
            self.peak_equity = None
            self.day_start_equity = None
        self.audit("kill_switch", f"trading re-armed by {by}", severity="warning", data=was)
        return {"rearmed": True}

    def update_limits(self, changes: dict, by: str, confirm: str = "") -> dict:
        """Lowering a limit is always allowed. Raising one needs the owner's typed confirmation."""
        with self._lock:
            cur = asdict(self.limits)
            raising = []
            for k, v in changes.items():
                if k not in cur:
                    raise KeyError(f"unknown limit {k!r}")
                if isinstance(cur[k], dict):
                    for kk, vv in v.items():
                        if float(vv) > float(cur[k].get(kk, 0)):
                            raising.append(f"{k}.{kk}")
                elif isinstance(cur[k], bool):
                    if bool(v) != cur[k] and k == "emergency_flatten":
                        pass
                elif float(v) > float(cur[k]) and not k.startswith("min_"):
                    raising.append(k)
            if raising and confirm.strip() != RAISE_PHRASE:
                raise PermissionError(f"raising {', '.join(raising)} needs the typed confirmation {RAISE_PHRASE!r}")
            new = dict(cur)
            for k, v in changes.items():
                new[k] = dict(cur[k], **v) if isinstance(cur[k], dict) else type(cur[k])(v)
            self.limits = Limits(**new)
        self.audit("risk_limits", f"risk limits changed by {by}" + (" (RAISED: " + ", ".join(raising) + ")"
                                                                     if raising else " (lowered or unchanged)"),
                   severity="warning" if raising else "info", data={"changes": changes})
        return asdict(self.limits)

    def state(self) -> dict:
        return {"kill_switch": self.kill_switch, "trading_locked": self.trading_locked,
                "limits": asdict(self.limits), "counters": dict(self.counters),
                "day_start_equity": str(self.day_start_equity) if self.day_start_equity else None,
                "peak_equity": str(self.peak_equity) if self.peak_equity else None,
                "phrases": {"rearm": REARM_PHRASE, "raise_limits": RAISE_PHRASE}}

    def restore(self, saved: dict) -> None:
        """Re-load persisted state after a restart: an engaged kill switch or lock survives a crash."""
        with self._lock:
            if saved.get("limits"):
                known = {f.name for f in fields(Limits)}
                self.limits = Limits(**{k: v for k, v in saved["limits"].items() if k in known})
            self.kill_switch = saved.get("kill_switch")
            self.trading_locked = saved.get("trading_locked")
