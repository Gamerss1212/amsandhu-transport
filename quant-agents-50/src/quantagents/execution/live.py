"""Real-money mirror for crypto exchanges (Phase 8 micro-live). OFF until the owner arms it.

The paper cycle still makes every decision: the agents vote, A49 sizes and limits the orders,
and the paper account records them. This module copies the paper account's decided portfolio,
as weights, onto a real exchange account, scaled to ``live.budget``:

    paper weight of BTC 12%, live.budget 200 CAD  ->  the mirror holds about 24 CAD of BTC

It sends an order only when every gate in ``gates()`` is open, and the owner opens each one by
hand: the Phase 8 row in ``docs/STATUS.md``, the three live settings in the config, the
approval phrase and trade-only exchange keys in ``.env``, and a budget above 0.

Safety rules in code. Each one can only shrink, skip or cancel an order:
- before every run the mirror's own ledger is reconciled with the exchange; a break engages
  the kill switch;
- it sells before it buys, sells only what the mirror itself bought (the owner's other coins
  are never touched), and never shorts or borrows;
- every order is a limit order at most ``max_slippage_pct`` past the bid/ask and at most
  ``max_order_value``; whatever is unfilled after ``order_timeout_seconds`` is cancelled;
- a buy needs free cash and the exchange price inside A49's price band around the paper price;
- any error in a real run engages the kill switch and sends an alert;
- only one real-money run at a time (a lock file), so a click and a scheduled run never
  both buy;
- nothing here can move money off the exchange: no withdrawal or transfer call exists.
Keys come only from the environment (the owner's ``.env``) and are scrubbed from every message.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Protocol

from quantagents import alerts
from quantagents.config import (
    LIVE_APPROVAL_ENV,
    LIVE_APPROVAL_TOKEN,
    AppConfig,
    ExecutionMode,
    LiveConfig,
    live_approval_present,
    load_config,
)
from quantagents.data.sources import ccxt_symbol, split_universe
from quantagents.execution.paper import PaperAccount
from quantagents.risk.killswitch import RESET_PHRASE, KillSwitch
from quantagents.runlock import RunLock
from quantagents.schemas import OrderSide

KEY_ENV = "LIVE_API_KEY"
SECRET_ENV = "LIVE_API_SECRET"
PASSWORD_ENV = "LIVE_API_PASSWORD"  # only a few exchanges use one
SECRET_NAMES = (KEY_ENV, SECRET_ENV, PASSWORD_ENV, alerts.TOKEN_ENV)
STATUS_FILE = Path("docs/STATUS.md")
STATE_FILE = Path("state/paper_account.json")
KILL_FILE = Path("state/kill_switch.json")
RUNS_DIR = Path("runs")
LEDGER_NAME = "live_ledger.json"
LOCK_NAME = "live.lock"  # one real-money run at a time (runlock.py)
APPROVAL_ROW = re.compile(
    r"^\|\s*\d{4}-\d{2}-\d{2}\s*\|\s*Approve Phase 8 micro-live\s*\|\s*[^|<>]*[A-Za-z][^|<>]*\|",
    re.M | re.I,
)
MAX_DECISION_AGE_DAYS = 4  # the newest paper cycle may be at most this many days old
RECONCILE_TOLERANCE = 0.002  # fee and rounding dust; a bigger gap is a reconciliation break
FEE_RESERVE = 0.01  # buys leave 1% of the free cash for fees
LIMIT_WARNING = 0.75  # alert when any loss limit is 75% used (Phase 8)
TEST_ORDER_DISCOUNT = 0.8  # the test order rests 20% under the bid, so it does not fill
DONE = frozenset({"closed", "canceled", "cancelled", "expired", "rejected"})
LIVE_EXCHANGES = frozenset({"kraken"})  # others need extra key fields; not supported yet
PREVIEW_GATES = ("exchange keys in .env", "crypto on one exchange", "ccxt installed")


class Exchange(Protocol):
    """The CCXT methods the mirror uses. None of them can move money off the exchange."""

    def load_markets(self) -> Any: ...
    def fetch_balance(self) -> Any: ...
    def fetch_ticker(self, symbol: str) -> Any: ...
    def create_order(
        self, symbol: str, type: str, side: str, amount: float, price: float | None = None
    ) -> Any: ...
    def fetch_order(self, id: str, symbol: str | None = None) -> Any: ...
    def cancel_order(self, id: str, symbol: str | None = None) -> Any: ...
    def amount_to_precision(self, symbol: str, amount: float) -> Any: ...
    def price_to_precision(self, symbol: str, price: float) -> Any: ...


Connect = Callable[[str], Exchange]
Say = Callable[[str], None]


class ReconciliationBreak(RuntimeError):
    """The exchange holds less than the mirror's ledger says it bought."""


def scrub(text: str) -> str:
    """``text`` with every secret from the environment replaced by ***."""
    for name in SECRET_NAMES:
        value = os.environ.get(name, "")
        if len(value) >= 4:
            text = text.replace(value, "***")
    return text


def ccxt_client(exchange_id: str) -> Exchange:  # pragma: no cover - needs ccxt, keys, network
    """A CCXT client for ``exchange_id`` with the owner's trade-only keys from the environment."""
    import ccxt  # optional [data] extra

    params: dict[str, Any] = {
        "apiKey": os.environ[KEY_ENV],
        "secret": os.environ[SECRET_ENV],
        "enableRateLimit": True,
        "requests_trust_env": True,
    }
    if os.environ.get(PASSWORD_ENV):
        params["password"] = os.environ[PASSWORD_ENV]
    client: Exchange = getattr(ccxt, exchange_id)(params)
    return client


def _base(symbol: str) -> str:
    """``BTC-CAD.KRAKEN`` -> ``BTC``."""
    return symbol.rpartition(".")[0].partition("-")[0] or symbol


@dataclass(frozen=True)
class Venue:
    """Where a crypto universe trades: one exchange, one quote currency."""

    exchange: str
    quote: str
    pairs: dict[str, str]  # BTC-CAD.KRAKEN -> BTC/CAD


def venue(symbols: tuple[str, ...] | list[str]) -> Venue | str:
    """The exchange and quote currency of the universe, or the reason it cannot trade for real."""
    yahoo, specs = split_universe(list(symbols))
    if yahoo:
        return (
            "only exchange crypto (like BTC-CAD.KRAKEN) can trade for real here; these are not: "
            + ", ".join(yahoo[:5])
        )
    if not specs:
        return "the universe has no symbols"
    pairs = {ccxt_symbol(*s.split(":", 1)): s.split(":", 1)[1] for s in specs}
    exchanges = sorted({s.split(":", 1)[0] for s in specs})
    quotes = sorted({p.split("/")[1] for p in pairs.values()})
    if len(exchanges) > 1:
        return f"one exchange per folder; this universe uses {', '.join(exchanges)}"
    if exchanges[0] not in LIVE_EXCHANGES:
        return (
            f"real money supports {', '.join(sorted(LIVE_EXCHANGES))} in this version, "
            f"not {exchanges[0]}"
        )
    if len(quotes) > 1:
        return f"one quote currency per folder; this universe uses {', '.join(quotes)}"
    return Venue(exchanges[0], quotes[0], pairs)


@dataclass(frozen=True)
class Decision:
    """The newest paper cycle: its date, its A49 level and its closing prices."""

    as_of: date
    level: str
    prices: dict[str, float]


def latest_decision(runs_dir: Path) -> Decision | None:
    newest: tuple[tuple[str, float], dict[str, Any]] | None = None
    for path in (runs_dir / "cycles").glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(data, dict) and "as_of" in data:
            key = (str(data["as_of"]), path.stat().st_mtime)
            if newest is None or key > newest[0]:
                newest = (key, data)
    if newest is None:
        return None
    data = newest[1]
    return Decision(
        as_of=date.fromisoformat(str(data["as_of"])),
        level=str(data.get("risk", {}).get("level", "?")),
        prices={
            str(k): float(v) for k, v in data.get("snapshot", {}).get("last_close", {}).items()
        },
    )


@dataclass(frozen=True)
class Gate:
    name: str
    ok: bool
    detail: str  # what it found when open; what the owner does when closed


def gates(
    cfg: AppConfig,
    *,
    status_file: Path,
    kill_file: Path,
    runs_dir: Path,
    today: date,
    ccxt_installed: bool,
) -> list[Gate]:
    """Every condition for a real order, in the order the owner opens them."""
    s = cfg.system
    row = status_file.exists() and bool(
        APPROVAL_ROW.search(status_file.read_text(encoding="utf-8", errors="replace"))
    )
    where = venue(cfg.universe.symbols)
    switch = KillSwitch(kill_file).state()
    decision = latest_decision(runs_dir)
    if decision is None:
        fresh, fresh_detail = False, "no paper cycle yet: run today's paper day first"
    elif decision.level == "HALTED":
        fresh, fresh_detail = False, f"the paper cycle of {decision.as_of} was HALTED by A49"
    elif (today - decision.as_of).days > MAX_DECISION_AGE_DAYS:
        fresh, fresh_detail = False, f"the newest paper cycle ({decision.as_of}) is too old"
    else:
        fresh, fresh_detail = True, f"paper cycle of {decision.as_of}, level {decision.level}"
    return [
        Gate(
            "Phase 8 approved in docs/STATUS.md",
            row,
            "your dated row is there"
            if row
            else "add a row to the Human approvals table: | <date> | Approve Phase 8 micro-live | <your name> |",
        ),
        Gate(
            "config: execution_mode live",
            s.execution_mode is ExecutionMode.LIVE,
            "set"
            if s.execution_mode is ExecutionMode.LIVE
            else "set system.execution_mode to live",
        ),
        Gate(
            "config: autonomy_level 3",
            s.autonomy_level >= 3,
            f"level {s.autonomy_level}"
            if s.autonomy_level >= 3
            else "set system.autonomy_level to 3",
        ),
        Gate(
            "config: live_trading_approved",
            s.live_trading_approved,
            "set" if s.live_trading_approved else "set system.live_trading_approved to true",
        ),
        Gate(
            "approval phrase in .env",
            live_approval_present(),
            "set"
            if live_approval_present()
            else f"add this line to .env: {LIVE_APPROVAL_ENV}={LIVE_APPROVAL_TOKEN}",
        ),
        Gate(
            "exchange keys in .env",
            bool(os.environ.get(KEY_ENV) and os.environ.get(SECRET_ENV)),
            "set (values hidden)"
            if os.environ.get(KEY_ENV) and os.environ.get(SECRET_ENV)
            else f"make trade-only keys (withdrawals OFF) and add {KEY_ENV}= and {SECRET_ENV}= to .env",
        ),
        Gate(
            "a budget above 0",
            cfg.live.budget > 0,
            f"live.budget {cfg.live.budget:g}"
            if cfg.live.budget > 0
            else "set live.budget in your config (start small, e.g. 100)",
        ),
        Gate(
            "crypto on one exchange",
            isinstance(where, Venue),
            f"{where.exchange}, prices in {where.quote}" if isinstance(where, Venue) else where,
        ),
        Gate(
            "ccxt installed",
            ccxt_installed,
            "yes" if ccxt_installed else 'python -m pip install -e ".[data]"',
        ),
        Gate(
            "kill switch armed",
            not switch.engaged,
            "not engaged"
            if not switch.engaged
            else f"ENGAGED ({switch.reason}); review, then: quantagents killswitch reset --confirm {RESET_PHRASE}",
        ),
        Gate("a fresh paper decision", fresh, fresh_detail),
    ]


@dataclass
class LiveLedger:
    """What the mirror itself bought and still holds, plus every real fill."""

    exchange: str
    qty: dict[str, float] = field(default_factory=dict)
    pending: list[dict[str, str]] = field(default_factory=list)
    trades: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def load(cls, path: Path, exchange: str) -> LiveLedger:
        if not path.exists():
            return cls(exchange)
        data = json.loads(path.read_text(encoding="utf-8"))
        if data["exchange"] != exchange:
            raise ValueError(
                f"{path} belongs to {data['exchange']}, not {exchange}. Close the positions there "
                "first, then move this file away: one folder trades on one exchange."
            )
        return cls(
            exchange,
            {str(k): float(v) for k, v in data["qty"].items()},
            [dict(p) for p in data["pending"]],
            list(data["trades"]),
        )

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        body = {
            "exchange": self.exchange,
            "qty": {k: v for k, v in sorted(self.qty.items()) if v > 0},
            "pending": self.pending,
            "trades": self.trades,
        }
        tmp.write_text(json.dumps(body, indent=2), encoding="utf-8")
        tmp.replace(path)

    def settle(self, order: Mapping[str, Any], symbol: str, side: str) -> str:
        """Book a finished order's fill (fees charged in the coin count too) and say what happened."""
        oid = str(order.get("id", ""))
        filled = float(order.get("filled") or 0.0)
        average = float(order.get("average") or order.get("price") or 0.0)
        fee = order.get("fee") or {}
        fee_cost = float(fee.get("cost") or 0.0)
        fee_currency = str(fee.get("currency") or "")
        base = _base(symbol)
        in_coin = fee_cost if fee_currency.upper() == base.upper() else 0.0
        change = filled - in_coin if side == "buy" else -(filled + in_coin)
        self.qty[symbol] = max(0.0, self.qty.get(symbol, 0.0) + change)
        self.pending = [p for p in self.pending if p.get("id") != oid]
        if filled <= 0:
            return f"{side.upper()} {symbol}: nothing filled (order {order.get('status', '?')})"
        self.trades.append(
            {
                "at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
                "order_id": oid,
                "symbol": symbol,
                "side": side,
                "qty": filled,
                "price": average,
                "fee": fee_cost,
                "fee_currency": fee_currency,
            }
        )
        verb = "BOUGHT" if side == "buy" else "SOLD"
        fee_text = f"{fee_cost:g} {fee_currency}".strip()
        return f"{verb} {filled:g} {symbol} at {average:,.2f} (value {filled * average:,.2f}, fee {fee_text})"


def reconcile(ledger: LiveLedger, balance: Mapping[str, Any]) -> list[str]:
    """Problems if the exchange holds less than the ledger; tiny dust is trimmed from the ledger."""
    totals = balance.get("total") or {}
    problems: list[str] = []
    for symbol, qty in sorted(ledger.qty.items()):
        if qty <= 0:
            continue
        base = _base(symbol)
        held = float(totals.get(base) or 0.0)
        if held + 1e-12 < qty * (1.0 - RECONCILE_TOLERANCE):
            problems.append(
                f"the mirror's ledger holds {qty:g} {base} but the exchange account has only "
                f"{held:g}: coins were sold or moved outside QuantAgents"
            )
        elif held < qty:
            ledger.qty[symbol] = held
    return problems


def decided_weights(
    account: PaperAccount, prices: Mapping[str, float], max_position: float
) -> dict[str, float]:
    """The paper portfolio after its queued orders, as long-only weights of paper equity."""
    qty = dict(account.ledger.book.quantities())
    for order in account.broker.pending:
        intent = order.intent
        signed = intent.qty if intent.side is OrderSide.BUY else -intent.qty
        qty[intent.symbol] = qty.get(intent.symbol, 0.0) + signed
    held = {s: q for s, q in qty.items() if q > 0}
    missing = sorted(s for s in held if not prices.get(s, 0.0) > 0)
    if missing:
        raise ValueError(f"the paper cycle has no price for {', '.join(missing)}")
    equity = account.ledger.book.equity(prices)
    if equity <= 0:
        raise ValueError("the paper account's equity is not positive")
    weights = {s: min(q * prices[s] / equity, max_position) for s, q in held.items()}
    total = sum(weights.values())
    return {s: w / total for s, w in weights.items()} if total > 1.0 else weights


def _quote(ticker: Mapping[str, Any]) -> tuple[float, float] | None:
    bid, ask = ticker.get("bid"), ticker.get("ask")
    if not bid or not ask or float(bid) <= 0 or float(ask) < float(bid):
        return None
    return float(bid), float(ask)


def _limits(market: Mapping[str, Any]) -> tuple[float, float]:
    limits = market.get("limits") or {}
    amount = (limits.get("amount") or {}).get("min") or 0.0
    cost = (limits.get("cost") or {}).get("min") or 0.0
    return float(amount), float(cost)


@dataclass(frozen=True)
class PlannedOrder:
    symbol: str
    pair: str
    side: str  # "buy" or "sell"
    amount: float  # coins
    limit: float  # quote currency per coin

    @property
    def value(self) -> float:
        return self.amount * self.limit


@dataclass
class Plan:
    orders: list[PlannedOrder] = field(default_factory=list)
    lines: list[str] = field(default_factory=list)


def _sized(
    exchange: Exchange, market: Mapping[str, Any], pair: str, amount: float, limit: float
) -> tuple[float, float, str]:
    """Amount and price at the exchange's precision, or a reason the order is too small."""
    min_amount, min_cost = _limits(market)
    try:
        amount = float(exchange.amount_to_precision(pair, amount))
        limit = float(exchange.price_to_precision(pair, limit))
    except Exception:  # CCXT raises when the amount rounds down to 0
        amount = 0.0
    if amount <= 0 or amount < min_amount or amount * limit < min_cost:
        return (
            0.0,
            limit,
            f"too small for the exchange (minimum {min_amount:g} coins, {min_cost:g} value)",
        )
    return amount, limit, ""


def plan_orders(
    *,
    exchange: Exchange,
    markets: Mapping[str, Any],
    where: Venue,
    weights: Mapping[str, float],
    ledger: LiveLedger,
    quotes: Mapping[str, tuple[float, float] | None],
    paper_prices: Mapping[str, float],
    live: LiveConfig,
    price_band_pct: float,
) -> Plan:
    """The orders that move the mirror toward ``weights`` x budget. Sells come first."""
    plan = Plan()
    slip = live.max_slippage_pct / 100.0
    symbols = sorted(set(weights) | {s for s, q in ledger.qty.items() if q > 0})
    for symbol in symbols:
        pair = where.pairs.get(symbol)
        quote = quotes.get(pair) if pair else None
        if pair is None:
            plan.lines.append(f"{symbol}: not in this folder's universe any more; left alone")
            continue
        if quote is None:
            plan.lines.append(f"{symbol}: the exchange gave no bid/ask; skipped this run")
            continue
        bid, ask = quote
        mid = (bid + ask) / 2.0
        held = ledger.qty.get(symbol, 0.0)
        target = weights.get(symbol, 0.0) * live.budget
        delta = target - held * mid
        plan.lines.append(
            f"{symbol}: paper weight {weights.get(symbol, 0.0):.1%} -> target {target:,.2f} "
            f"{where.quote}; the mirror holds {held:g} ({held * mid:,.2f} {where.quote})"
        )
        market = markets.get(pair) or {}
        if delta < 0 and held > 0 and (target <= 0 or -delta >= live.min_order_value):
            amount = held if target <= 0 else min(held, -delta / mid)
            side, limit = "sell", bid * (1.0 - slip)
        elif delta >= live.min_order_value:
            paper = paper_prices.get(symbol, 0.0)
            gap = abs(mid / paper - 1.0) * 100.0 if paper > 0 else float("inf")
            if gap > price_band_pct:
                plan.lines.append(
                    f"  buy skipped: the exchange price {mid:,.2f} is {gap:.1f}% from the paper "
                    f"price {paper:,.2f} (band {price_band_pct:g}%)"
                )
                continue
            limit = ask * (1.0 + slip)
            side, amount = "buy", min(delta, live.max_order_value) / limit
        else:
            continue
        amount, limit, why = _sized(exchange, market, pair, amount, limit)
        if why:
            plan.lines.append(f"  {side} skipped: {why}")
            continue
        plan.orders.append(PlannedOrder(symbol, pair, side, amount, limit))
    plan.orders.sort(key=lambda o: (o.side != "sell", o.symbol))
    return plan


def fit_to_cash(
    order: PlannedOrder, free: float, exchange: Exchange, market: Mapping[str, Any]
) -> PlannedOrder | None:
    """A buy shrunk to the free cash (less a fee reserve), or None if too little is left."""
    room = free * (1.0 - FEE_RESERVE)
    if order.value <= room:
        return order
    amount, limit, why = _sized(exchange, market, order.pair, room / order.limit, order.limit)
    if why:
        return None
    return PlannedOrder(order.symbol, order.pair, order.side, amount, limit)


def finish(
    exchange: Exchange,
    oid: str,
    pair: str,
    timeout: float,
    *,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> Mapping[str, Any]:
    """Wait up to ``timeout`` seconds for the order, cancel what is left, return the final order."""
    deadline = clock() + timeout
    order: Mapping[str, Any] = exchange.fetch_order(oid, pair)
    while order.get("status") not in DONE and clock() < deadline:
        sleep(2.0)
        order = exchange.fetch_order(oid, pair)
    if order.get("status") not in DONE:
        exchange.cancel_order(oid, pair)
        order = exchange.fetch_order(oid, pair)
        if order.get("status") not in DONE:
            raise RuntimeError(
                f"order {oid} on {pair} is still open after cancelling: cancel it on the "
                "exchange website"
            )
    return order


def _free(balance: Mapping[str, Any], currency: str) -> float:
    return float((balance.get("free") or {}).get(currency) or 0.0)


def execute(
    exchange: Exchange,
    markets: Mapping[str, Any],
    plan: Plan,
    ledger: LiveLedger,
    ledger_path: Path,
    where: Venue,
    live: LiveConfig,
    say: Say,
    *,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> list[str]:
    """Send the plan's orders one by one, saving the ledger after each. Returns the fill lines."""
    done: list[str] = []
    for planned in plan.orders:
        order = planned
        if planned.side == "buy":
            free = _free(exchange.fetch_balance(), where.quote)
            fitted = fit_to_cash(planned, free, exchange, markets.get(planned.pair) or {})
            if fitted is None:
                say(f"BUY {planned.symbol} skipped: not enough free {where.quote} ({free:,.2f})")
                continue
            order = fitted
        placed = exchange.create_order(order.pair, "limit", order.side, order.amount, order.limit)
        oid = str(placed["id"])
        ledger.pending.append(
            {"id": oid, "symbol": order.symbol, "pair": order.pair, "side": order.side}
        )
        ledger.save(ledger_path)
        say(
            f"Sent: {order.side.upper()} {order.amount:g} {order.symbol}, limit {order.limit:,.2f} "
            f"(about {order.value:,.2f} {where.quote}), order {oid}"
        )
        final = finish(
            exchange, oid, order.pair, live.order_timeout_seconds, sleep=sleep, clock=clock
        )
        line = ledger.settle(final, order.symbol, order.side)
        ledger.save(ledger_path)
        say(line)
        done.append(line)
    return done


def limit_use(cfg: AppConfig, account: PaperAccount, decision: Decision) -> tuple[float, str]:
    """How much of A49's daily, weekly and drawdown loss limits the paper account has used."""
    equity = account.ledger.book.equity(decision.prices)
    daily, weekly, drawdown = account.loss_metrics(decision.as_of, equity)
    r = cfg.risk
    parts = [
        (daily / r.max_daily_loss_pct, f"daily loss {daily:.2f}% of {r.max_daily_loss_pct:g}%"),
        (
            weekly / r.max_weekly_loss_pct,
            f"weekly loss {weekly:.2f}% of {r.max_weekly_loss_pct:g}%",
        ),
        (drawdown / r.max_drawdown_pct, f"drawdown {drawdown:.2f}% of {r.max_drawdown_pct:g}%"),
    ]
    return max(use for use, _ in parts), ", ".join(text for _, text in parts)


def _invested(
    ledger: LiveLedger, quotes: Mapping[str, tuple[float, float] | None], where: Venue
) -> float:
    """The mirror's holdings at mid prices (coins without a quote count as 0)."""
    total = 0.0
    for symbol, qty in ledger.qty.items():
        quote = quotes.get(where.pairs.get(symbol, ""))
        if quote is not None:
            total += qty * (quote[0] + quote[1]) / 2.0
    return total


def has_ccxt() -> bool:
    return importlib.util.find_spec("ccxt") is not None


def _refused(closed: list[Gate], say: Say) -> int:
    say("Real money: REFUSED. Still needed:")
    for g in closed:
        say(f"  - {g.name}: {g.detail}")
    say("Run `quantagents live check` for the full list. Nothing was sent.")
    return 3


def run_sync(
    cfg: AppConfig,
    *,
    dry_run: bool,
    connect: Connect = ccxt_client,
    say: Say = print,
    today: date | None = None,
    state_file: Path = STATE_FILE,
    kill_file: Path = KILL_FILE,
    runs_dir: Path = RUNS_DIR,
    status_file: Path = STATUS_FILE,
    ccxt_installed: bool | None = None,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> int:
    """Copy the paper portfolio onto the exchange (or preview it). 0 ok, 1 error, 3 refused."""

    def out(text: str) -> None:
        say(scrub(text))

    checks = gates(
        cfg,
        status_file=status_file,
        kill_file=kill_file,
        runs_dir=runs_dir,
        today=today or datetime.now(UTC).date(),
        ccxt_installed=has_ccxt() if ccxt_installed is None else ccxt_installed,
    )
    needed = [g for g in checks if g.name in PREVIEW_GATES] if dry_run else checks
    closed = [g for g in needed if not g.ok]
    if closed:
        return _refused(closed, out)
    where = venue(cfg.universe.symbols)
    decision = latest_decision(runs_dir)
    if not isinstance(where, Venue) or decision is None:
        out("Real money: no paper decision yet. Run today's paper day first.")
        return 3
    ledger_path = state_file.with_name(LEDGER_NAME)
    account = PaperAccount.load_or_new(state_file, cfg.system.capital, cfg.costs)
    out(
        f"Real-money mirror on {where.exchange}: budget {cfg.live.budget:,.2f} {where.quote}, "
        f"paper decision of {decision.as_of}"
        + (" (PREVIEW: nothing will be sent)" if dry_run else "")
    )
    lock = RunLock(state_file.with_name(LOCK_NAME))
    if not dry_run and not lock.acquire():
        out(f"Real money: another real-money run is still going ({lock.path}). Nothing was sent.")
        return 3
    try:
        exchange = connect(where.exchange)
        markets: Mapping[str, Any] = exchange.load_markets()
        ledger = LiveLedger.load(ledger_path, where.exchange)
        for p in list(ledger.pending):
            if dry_run:
                out(
                    f"Order {p['id']} from an earlier run is unsettled; a real run settles it first."
                )
                continue
            final = finish(exchange, p["id"], p["pair"], 0, sleep=sleep, clock=clock)
            out("Settled an earlier order: " + ledger.settle(final, p["symbol"], p["side"]))
            ledger.save(ledger_path)
        balance = exchange.fetch_balance()
        problems = reconcile(ledger, balance)
        if problems:
            if dry_run:
                for problem in problems:
                    out(f"Reconciliation break: {problem}")
                return 1
            raise ReconciliationBreak("; ".join(problems))
        weights = decided_weights(account, decision.prices, cfg.risk.max_position_pct / 100.0)
        wanted = sorted(set(weights) | {s for s, q in ledger.qty.items() if q > 0})
        quotes = {
            where.pairs[s]: _quote(exchange.fetch_ticker(where.pairs[s]))
            for s in wanted
            if s in where.pairs
        }
        plan = plan_orders(
            exchange=exchange,
            markets=markets,
            where=where,
            weights=weights,
            ledger=ledger,
            quotes=quotes,
            paper_prices=decision.prices,
            live=cfg.live,
            price_band_pct=cfg.risk.price_band_pct,
        )
        for line in plan.lines or ["The paper portfolio is all cash, and so is the mirror."]:
            out(f"  {line}")
        if dry_run:
            free = _free(balance, where.quote)
            for o in plan.orders:
                out(
                    f"Would {o.side.upper()} {o.amount:g} {o.symbol} at limit {o.limit:,.2f} ({o.value:,.2f} {where.quote})"
                )
            out(f"Free {where.quote} on the exchange: {free:,.2f}. Preview only: nothing was sent.")
            return 0
        if not plan.orders:
            out("No orders needed: the mirror already matches the paper portfolio.")
        fills = execute(
            exchange,
            markets,
            plan,
            ledger,
            ledger_path,
            where,
            cfg.live,
            out,
            sleep=sleep,
            clock=clock,
        )
        ledger.save(ledger_path)
        invested = _invested(ledger, quotes, where)
        use = invested / cfg.live.budget
        summary = f"invested about {invested:,.2f} of the {cfg.live.budget:,.2f} {where.quote} budget ({use:.0%})"
        out(f"Real-money sync done: {summary}.")
        if fills:
            alerts.send(
                scrub(f"{len(fills)} real fill(s): " + "; ".join(fills) + f". Now {summary}.")
            )
        worst, detail = limit_use(cfg, account, decision)
        if worst >= LIMIT_WARNING:
            warning = (
                f"the paper account that the mirror copies has used {worst:.0%} of a loss "
                f"limit ({detail}). At 100% A49 stops new trades."
            )
            out(f"WARNING: {warning}")
            alerts.send(f"Limit warning: {warning}")
        return 0
    except Exception as exc:  # any surprise with real money stops everything (fail safe)
        message = scrub(f"{type(exc).__name__}: {exc}")
        if dry_run:
            out(f"Preview failed: {message}")
            return 1
        KillSwitch(kill_file).engage(f"real-money sync stopped: {message}"[:300], by="live")
        out(f"Real-money sync STOPPED; the kill switch is ENGAGED. {message}")
        out(
            f"Check your orders and balances on the {where.exchange} website and {ledger_path}, "
            f"then: quantagents killswitch reset --confirm {RESET_PHRASE}"
        )
        alerts.send(f"HALT: real-money sync stopped. {message}")
        return 1
    finally:
        lock.release()


def run_test_order(
    cfg: AppConfig,
    *,
    connect: Connect = ccxt_client,
    say: Say = print,
    today: date | None = None,
    state_file: Path = STATE_FILE,
    kill_file: Path = KILL_FILE,
    runs_dir: Path = RUNS_DIR,
    status_file: Path = STATUS_FILE,
    ccxt_installed: bool | None = None,
) -> int:
    """Place the smallest buy the exchange takes, 20% under the bid, then cancel it at once.

    It proves the keys can place and cancel orders. It needs every gate except a fresh paper
    decision, so it can run before the first live day.
    """

    def out(text: str) -> None:
        say(scrub(text))

    checks = gates(
        cfg,
        status_file=status_file,
        kill_file=kill_file,
        runs_dir=runs_dir,
        today=today or datetime.now(UTC).date(),
        ccxt_installed=has_ccxt() if ccxt_installed is None else ccxt_installed,
    )
    closed = [g for g in checks if not g.ok and g.name != "a fresh paper decision"]
    if closed:
        return _refused(closed, out)
    where = venue(cfg.universe.symbols)
    assert isinstance(where, Venue)  # the gates checked it
    symbol, pair = sorted(where.pairs.items())[0]
    ledger_path = state_file.with_name(LEDGER_NAME)
    oid = ""
    lock = RunLock(state_file.with_name(LOCK_NAME))
    if not lock.acquire():
        out(f"Test order: another real-money run is still going ({lock.path}). Nothing was sent.")
        return 3
    try:
        exchange = connect(where.exchange)
        markets = exchange.load_markets()
        market = markets.get(pair) or {}
        quote = _quote(exchange.fetch_ticker(pair))
        if quote is None:
            out(f"Test order: the exchange gave no bid/ask for {pair}. Try again later.")
            return 1
        price = float(exchange.price_to_precision(pair, quote[0] * TEST_ORDER_DISCOUNT))
        min_amount, min_cost = _limits(market)
        amount = max(min_amount, min_cost * 1.05 / price) or cfg.live.min_order_value / price
        amount, price, why = _sized(exchange, market, pair, amount, price)
        if why:
            out(f"Test order: {why}.")
            return 1
        free = _free(exchange.fetch_balance(), where.quote)
        if amount * price > min(free * (1.0 - FEE_RESERVE), cfg.live.max_order_value):
            out(
                f"Test order needs about {amount * price:,.2f} {where.quote}: more than the free "
                f"{free:,.2f} or live.max_order_value {cfg.live.max_order_value:g}. Nothing was sent."
            )
            return 1
        ledger = LiveLedger.load(ledger_path, where.exchange)
        placed = exchange.create_order(pair, "limit", "buy", amount, price)
        oid = str(placed["id"])
        ledger.pending.append({"id": oid, "symbol": symbol, "pair": pair, "side": "buy"})
        ledger.save(ledger_path)
        out(
            f"Test order sent: BUY {amount:g} {pair} at {price:,.2f}, 20% under the bid (order {oid})."
        )
        final = finish(exchange, oid, pair, 0)
        line = ledger.settle(final, symbol, "buy")
        ledger.save(ledger_path)
        out(f"Test order {final.get('status')}: {line}")
        out("The keys can place and cancel orders. Nothing else was done.")
        return 0
    except Exception as exc:
        message = scrub(f"{type(exc).__name__}: {exc}")
        KillSwitch(kill_file).engage(f"real-money test order failed: {message}"[:300], by="live")
        out(f"Test order FAILED; the kill switch is ENGAGED. {message}")
        if oid:
            out(
                f"Order {oid} may still be open: check open orders on the {where.exchange} website."
            )
        alerts.send(f"HALT: real-money test order failed. {message}")
        return 1
    finally:
        lock.release()


def check_lines(
    cfg: AppConfig,
    *,
    connect: Connect = ccxt_client,
    today: date | None = None,
    state_file: Path = STATE_FILE,
    kill_file: Path = KILL_FILE,
    runs_dir: Path = RUNS_DIR,
    status_file: Path = STATUS_FILE,
    ccxt_installed: bool | None = None,
) -> tuple[bool, list[str]]:
    """Each gate with [ok] or [--], then a read-only balance check when the keys are there."""
    checks = gates(
        cfg,
        status_file=status_file,
        kill_file=kill_file,
        runs_dir=runs_dir,
        today=today or datetime.now(UTC).date(),
        ccxt_installed=has_ccxt() if ccxt_installed is None else ccxt_installed,
    )
    lines = ["Real money (Phase 8): every gate must say ok", ""]
    lines += [f"  [{'ok' if g.ok else '--'}] {g.name}: {g.detail}" for g in checks]
    armed = all(g.ok for g in checks)
    closed = sum(1 for g in checks if not g.ok)
    where = venue(cfg.universe.symbols)
    lines.append("")
    if armed and isinstance(where, Venue):
        lines.append(
            f"Real money is ARMED: each daily run copies the paper portfolio to {where.exchange}, "
            f"up to {cfg.live.budget:,.2f} {where.quote}."
        )
    else:
        lines.append(
            f"Real money is OFF: {closed} of {len(checks)} gates closed. Nothing real can be bought."
        )
    ready = {g.name: g.ok for g in checks}
    if isinstance(where, Venue) and all(ready[n] for n in PREVIEW_GATES):
        try:
            exchange = connect(where.exchange)
            balance = exchange.fetch_balance()
            ledger = LiveLedger.load(state_file.with_name(LEDGER_NAME), where.exchange)
            held = ", ".join(f"{q:g} {_base(s)}" for s, q in sorted(ledger.qty.items()) if q > 0)
            lines.append(
                f"Connected to {where.exchange} (read only): free {where.quote} "
                f"{_free(balance, where.quote):,.2f}; the mirror holds {held or 'nothing'}."
            )
        except Exception as exc:  # a read-only check reports, it never halts
            lines.append(
                f"Could not read the {where.exchange} account: {type(exc).__name__}: {exc}"
            )
    lines.append("Guide: docs/REAL_MONEY.md. Not financial advice.")
    return armed, [scrub(line) for line in lines]


def mirror_summary(state_file: Path) -> str | None:
    """One status line about the mirror's holdings, or None if it never traded."""
    path = state_file.with_name(LEDGER_NAME)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        held = ", ".join(f"{float(q):g} {_base(str(s))}" for s, q in sorted(data["qty"].items()))
        return (
            f"Real-money mirror on {data['exchange']}: holds {held or 'nothing'} | real fills "
            f"{len(data['trades'])} | unsettled orders {len(data['pending'])}"
        )
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return f"Real-money mirror ledger {path} is unreadable: check it before any real run"


def add_parser(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    p = sub.add_parser(
        "live", help="real money (Phase 8): check, preview, sync, test order. OFF until you arm it"
    )
    live_sub = p.add_subparsers(dest="live_command", required=True)
    live_sub.add_parser("check", help="what is still needed for real orders (reads only)")
    s = live_sub.add_parser("sync", help="copy the paper portfolio onto the exchange (every gate)")
    s.add_argument("--dry-run", action="store_true", help="preview the orders; send nothing")
    live_sub.add_parser("test-order", help="a tiny buy 20%% under the market, cancelled at once")

    def run(args: argparse.Namespace) -> int:
        path = Path(args.config) if args.config else Path("config/default.yaml")
        cfg = load_config(path if path.exists() else None)
        if args.live_command == "check":
            armed, lines = check_lines(cfg)
            print("\n".join(lines))
            return 0 if armed else 1
        if args.live_command == "sync":
            return run_sync(cfg, dry_run=args.dry_run)
        return run_test_order(cfg)

    p.set_defaults(func=run)
