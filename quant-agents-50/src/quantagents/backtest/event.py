"""A43 event-driven backtester: orders and fills, not weights (spec section 56, Phase 1).

The vectorized engine (``engine.py``) is for screening. Finalists are re-tested here, where
every trade is an order that can be partly filled or rejected:

- Timeline: the strategy sees a MarketView ending at the close of day t. Orders are sized from
  that close and fill at the **open of t+1** (one bar of latency). Nothing ever fills at the
  close that produced the signal.
- Quantities are whole multiples of ``quantity_step`` (1 = whole shares), rounded toward zero.
- Liquidity cap: one order fills at most ``max_adv_participation`` (1%) of the average daily
  traded value (median close x volume over the 20 days up to t). The rest is not filled: a
  **partial fill**. The next decision re-targets from what was actually filled.
- Price: open x (1 + half-spread/slippage + square-root impact) for buys, minus for sells.
  Impact = 0.8 x daily volatility x sqrt(order value / ADV), the same model A09 uses.
- Fees: ``fee_bps`` of the filled value, paid in cash.
- **Rejections**: no open price that day (halted, holiday or missing data), no volume history,
  or a liquidity cap below one unit. Buys that would overdraw cash are shrunk to what cash
  allows; a buy with no cash for even one unit is counted as **unfunded**, not rejected (a
  fully invested strategy asks for small top-ups every day that no broker would ever see).
- Sells go first each morning, so their cash can pay for that morning's buys.
- Long only, no leverage, so there is no borrow, funding or financing cost to charge. Prices
  should be the store's adjusted prices, so dividends and splits are already in them. Taxes
  are estimated from paper fills by ``quantagents acb`` (not here, and not tax advice).
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import date
from enum import StrEnum

import numpy as np

from quantagents.backtest.engine import Strategy, performance_metrics
from quantagents.config import AppConfig
from quantagents.market import FloatArray, MarketData


@dataclass(frozen=True)
class EventCosts:
    fee_bps: float = 10.0
    slippage_bps: float = 5.0
    impact_coef: float = 0.8
    adv_window: int = 20
    max_adv_participation: float = 0.01
    quantity_step: float = 1.0

    def __post_init__(self) -> None:
        if min(self.fee_bps, self.slippage_bps, self.impact_coef) < 0:
            raise ValueError("costs must be >= 0")
        if self.adv_window < 2 or self.quantity_step <= 0 or self.max_adv_participation <= 0:
            raise ValueError("adv_window >= 2, quantity_step > 0 and participation > 0 required")

    @classmethod
    def from_config(cls, cfg: AppConfig) -> EventCosts:
        return cls(
            fee_bps=cfg.costs.fee_bps,
            slippage_bps=cfg.costs.slippage_bps,
            max_adv_participation=cfg.risk.max_adv_participation_pct / 100.0,
            quantity_step=cfg.risk.quantity_step,
        )

    def doubled(self) -> EventCosts:
        """Spec section 56 cost stress: fees, slippage and impact all twice as high."""
        return EventCosts(
            fee_bps=2 * self.fee_bps,
            slippage_bps=2 * self.slippage_bps,
            impact_coef=2 * self.impact_coef,
            adv_window=self.adv_window,
            max_adv_participation=self.max_adv_participation,
            quantity_step=self.quantity_step,
        )


class FillStatus(StrEnum):
    FILLED = "filled"
    PARTIAL = "partial"
    REJECTED = "rejected"
    UNFUNDED = "unfunded"  # a buy with no cash left for even one unit (never sent)


@dataclass(frozen=True)
class OrderEvent:
    """One order: decided after the close of ``signal_date``, worked at the open of ``fill_date``."""

    signal_date: date
    fill_date: date
    symbol: str
    requested_qty: float  # signed: + buy, - sell
    filled_qty: float  # signed, 0 when rejected
    price: float  # average fill price including slippage and impact (nan when rejected)
    fee: float
    impact_bps: float
    status: FillStatus
    reason: str = ""


@dataclass(frozen=True)
class EventResult:
    name: str
    dates: tuple[date, ...]
    equity: FloatArray  # account value in currency at each close, starting at ``capital``
    returns: FloatArray
    orders: tuple[OrderEvent, ...]
    capital: float
    costs: EventCosts
    metrics: dict[str, float] = field(default_factory=dict)

    def count(self, status: FillStatus) -> int:
        return sum(1 for o in self.orders if o.status is status)


def _round_toward_zero(qty: float, step: float) -> float:
    units = math.floor(abs(qty) / step + 1e-9)
    return math.copysign(units * step, qty) if units else 0.0


class EventBacktester:
    agent_id = "A43"
    name = "Backtest Engineer (event-driven)"
    kind = "code"

    def __init__(self, costs: EventCosts, capital: float, *, max_gross: float = 1.0) -> None:
        if capital <= 0:
            raise ValueError("capital must be > 0")
        self.costs = costs
        self.capital = capital
        self.max_gross = max_gross

    def _targets(self, target: Mapping[str, float], symbols: tuple[str, ...]) -> dict[str, float]:
        unknown = set(target) - set(symbols)
        if unknown:
            raise ValueError(f"strategy returned unknown symbols {sorted(unknown)}")
        weights = {s: float(w) for s, w in target.items()}
        if not all(math.isfinite(w) for w in weights.values()):
            raise ValueError("strategy returned a non-finite weight")
        if any(w < 0 for w in weights.values()):
            raise ValueError("strategy returned a short weight; the event engine is long only")
        if sum(weights.values()) > self.max_gross + 1e-9:
            raise ValueError(f"gross exposure {sum(weights.values()):.3f} above {self.max_gross}")
        return weights

    def run(
        self, market: MarketData, strategy: Strategy, *, warmup: int = 260, name: str = "strategy"
    ) -> EventResult:
        n = len(market)
        c = self.costs
        if not max(warmup, c.adv_window) < n - 1:
            raise ValueError(f"warmup {warmup} leaves no days to trade in {n} bars")
        symbols = market.symbols
        opens = {s: market.bars(s).open for s in symbols}
        closes = {s: market.bars(s).close for s in symbols}
        volumes = {s: market.bars(s).volume for s in symbols}
        cash = self.capital
        qty = dict.fromkeys(symbols, 0.0)
        last_close = dict.fromkeys(symbols, math.nan)
        equity = [self.capital]
        orders: list[OrderEvent] = []

        def mark(t: int) -> float:
            for s in symbols:
                if math.isfinite(closes[s][t]) and closes[s][t] > 0:
                    last_close[s] = float(closes[s][t])
            held = sum(q * last_close[s] for s, q in qty.items() if q)
            return cash + held

        mark(warmup)
        for t in range(warmup, n - 1):
            value = equity[-1]
            weights = self._targets(strategy(market.view_at(t)), symbols)
            wanted: dict[str, float] = {}
            for s in symbols:
                ref = last_close[s]
                goal = weights.get(s, 0.0) * value / ref if math.isfinite(ref) else qty[s]
                delta = _round_toward_zero(goal - qty[s], c.quantity_step)
                if delta:
                    wanted[s] = delta
            # sells first (they free cash), then buys
            for s in sorted(wanted, key=lambda k: wanted[k] > 0):
                event = self._fill(market, t, s, wanted[s], cash, opens, closes, volumes)
                orders.append(event)
                if event.filled_qty:
                    notional = event.filled_qty * event.price
                    cash -= notional + event.fee
                    qty[s] += event.filled_qty
            equity.append(mark(t + 1))
        values = np.array(equity)
        returns = values[1:] / values[:-1] - 1.0
        turnover = np.zeros(len(returns))
        metrics = performance_metrics(returns, turnover)
        filled = [o for o in orders if o.filled_qty]
        traded = sum(abs(o.filled_qty * o.price) for o in filled)
        metrics.update(
            {
                "orders": float(len(orders)),
                "partial_fills": float(sum(o.status is FillStatus.PARTIAL for o in orders)),
                "rejections": float(sum(o.status is FillStatus.REJECTED for o in orders)),
                "unfunded": float(sum(o.status is FillStatus.UNFUNDED for o in orders)),
                "fees_paid": float(sum(o.fee for o in orders)),
                "avg_impact_bps": float(np.mean([o.impact_bps for o in filled])) if filled else 0.0,
                "avg_daily_turnover": traded / float(np.mean(values)) / max(len(returns), 1),
            }
        )
        del metrics["exposure_days_pct"]
        return EventResult(
            name=name,
            dates=market.dates[warmup:],
            equity=values,
            returns=returns,
            orders=tuple(orders),
            capital=self.capital,
            costs=c,
            metrics=metrics,
        )

    def _fill(
        self,
        market: MarketData,
        t: int,
        symbol: str,
        requested: float,
        cash: float,
        opens: Mapping[str, FloatArray],
        closes: Mapping[str, FloatArray],
        volumes: Mapping[str, FloatArray],
    ) -> OrderEvent:
        c = self.costs
        signal_day, fill_day = market.dates[t], market.dates[t + 1]

        def rejected(reason: str) -> OrderEvent:
            return OrderEvent(
                signal_day, fill_day, symbol, requested, 0.0, math.nan, 0.0, 0.0,
                FillStatus.REJECTED, reason,
            )  # fmt: skip

        price = float(opens[symbol][t + 1])
        if not (math.isfinite(price) and price > 0):
            return rejected("no opening price (halted, holiday or missing data)")
        lo = t + 1 - c.adv_window
        window_c = closes[symbol][lo : t + 1]
        traded = window_c * volumes[symbol][lo : t + 1]
        traded = traded[np.isfinite(traded) & (traded > 0)]
        if len(traded) < c.adv_window // 2:
            return rejected("not enough volume history to size the order")
        adv = float(np.median(traded))
        with np.errstate(divide="ignore", invalid="ignore"):
            r = np.diff(np.log(window_c))
        r = r[np.isfinite(r)]
        sigma = float(np.std(r, ddof=1)) if len(r) > 2 else 0.0

        qty, reason = requested, ""
        cap_qty = _round_toward_zero(c.max_adv_participation * adv / price, c.quantity_step)
        if abs(qty) > cap_qty:
            qty, reason = math.copysign(cap_qty, qty), "capped at 1% of daily traded value"
        side = 1.0 if qty > 0 else -1.0

        def cost_rate(q: float) -> tuple[float, float]:
            impact = c.impact_coef * sigma * math.sqrt(abs(q) * price / adv)
            return c.slippage_bps / 1e4 + impact, impact

        if side > 0:
            # shrink a buy until price + fee fits in the cash we have
            for _ in range(60):
                rate, _impact = cost_rate(qty)
                need = qty * price * (1 + rate) * (1 + c.fee_bps / 1e4)
                if need <= cash + 1e-9 or not qty:
                    break
                qty = _round_toward_zero(
                    min(qty * 0.999, cash / (price * (1 + rate) * (1 + c.fee_bps / 1e4))),
                    c.quantity_step,
                )
                reason = "shrunk to the cash available"
        if not qty and reason == "shrunk to the cash available":
            return replace(rejected("no cash left for one unit"), status=FillStatus.UNFUNDED)
        if not qty:
            return rejected(reason or "size rounds to zero")
        rate, impact = cost_rate(qty)
        fill_price = price * (1 + side * rate)
        fee = abs(qty) * fill_price * c.fee_bps / 1e4
        status = FillStatus.FILLED if qty == requested else FillStatus.PARTIAL
        return OrderEvent(
            signal_day, fill_day, symbol, requested, qty, fill_price, fee, 1e4 * impact,
            status, reason,
        )  # fmt: skip
