"""Structured records passed between layers.

Every record that describes something the market did carries two clocks: `event_time`
(when it happened, according to the venue) and `receipt_time` (when this process learned
about it). Both are UTC, as epoch milliseconds, internally. Records that come out of a bot
carry the strategy version and config version that produced them, so any decision can be
traced back to exact code and parameters.
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


def now_ms() -> int:
    return int(time.time() * 1000)


def iso(ms: Optional[int]) -> Optional[str]:
    if ms is None:
        return None
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(ms / 1000)) + f".{int(ms % 1000):03d}Z"


class Record:
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ----------------------------------------------------------------------------- market events

@dataclass
class Bar(Record):
    """A completed OHLCV bar. `event_time` is the bar's OPEN time; it is complete at
    event_time + timeframe. Incomplete (forming) bars are never passed to strategies."""
    venue: str
    instrument: str
    timeframe: str
    event_time: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    receipt_time: int = field(default_factory=now_ms)
    provenance: str = ""                 # e.g. "coinbase.rest.candles"
    complete: bool = True

    @property
    def key(self):
        return (self.venue, self.instrument, self.timeframe, self.event_time)


@dataclass
class Trade(Record):
    venue: str
    instrument: str
    event_time: int
    price: float
    size: float
    side: str                            # "buy" / "sell": the aggressor side as reported by the venue
    trade_id: str
    receipt_time: int = field(default_factory=now_ms)
    provenance: str = ""


@dataclass
class BookSnapshot(Record):
    venue: str
    instrument: str
    event_time: int
    bids: List[List[float]]              # [[price, size], ...] best first
    asks: List[List[float]]
    receipt_time: int = field(default_factory=now_ms)
    provenance: str = ""
    sequence: Optional[int] = None

    @property
    def best_bid(self):
        return self.bids[0][0] if self.bids else None

    @property
    def best_ask(self):
        return self.asks[0][0] if self.asks else None


# ----------------------------------------------------------------------------- bot outputs

@dataclass
class FeatureValue(Record):
    name: str                            # e.g. "ema(close,21)"
    value: Any
    instrument: str
    timeframe: str
    bar_time: int                        # the completed bar the value belongs to
    warm: bool = True                    # False while the indicator is still warming up


@dataclass
class RuleOutcome(Record):
    rule: str                            # human-readable rule, e.g. "close > ema21"
    passed: bool
    detail: str = ""                     # values behind the outcome, e.g. "101.2 > 100.7"


@dataclass
class Signal(Record):
    bot_id: str
    strategy_id: str
    strategy_version: str
    config_version: str
    instrument: str
    venue: str
    timeframe: str
    bar_time: int
    decision_time: int
    action: str                          # "enter_long" | "enter_short" | "exit" | "hold" | "no_trade"
    reason: str
    features: Dict[str, Any] = field(default_factory=dict)
    rules: List[Dict[str, Any]] = field(default_factory=list)
    stop: Optional[float] = None
    target: Optional[float] = None
    provenance: str = ""


@dataclass
class OrderIntent(Record):
    intent_id: str                       # deterministic: bot + bar + action, so a replayed decision cannot double-submit
    bot_id: str
    strategy_id: str
    instrument: str
    venue: str
    side: str                            # "buy" / "sell"
    order_type: str                      # "market" | "limit" | "stop"
    quantity: float
    limit_price: Optional[float] = None
    stop_price: Optional[float] = None
    reduce_only: bool = False
    created_time: int = field(default_factory=now_ms)
    reason: str = ""
    risk_amount: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None


@dataclass
class RiskDecision(Record):
    intent_id: str
    bot_id: str
    approved: bool
    adjusted_quantity: Optional[float]
    checks: List[Dict[str, Any]]          # [{"check": name, "passed": bool, "detail": str}]
    decision_time: int = field(default_factory=now_ms)


@dataclass
class Fill(Record):
    fill_id: str
    order_id: str
    intent_id: str
    bot_id: str
    instrument: str
    venue: str
    side: str
    quantity: float
    price: float
    fee: float
    liquidity: str                       # "taker" | "maker"
    event_time: int
    simulated: bool = True
    model: str = ""                      # how the fill was simulated


@dataclass
class Position(Record):
    bot_id: str
    instrument: str
    venue: str
    quantity: float                      # signed: positive long, negative short
    avg_price: float
    opened_time: int
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    realized_pnl: float = 0.0
    fees: float = 0.0
    max_exit_time: Optional[int] = None


@dataclass
class BotHealth(Record):
    bot_id: str
    state: str                           # "running" | "warming" | "idle_no_signal" | "data_unavailable" |
                                         # "degraded" | "stopped" | "disabled" | "paused"
    last_evaluation_time: Optional[int]
    last_data_time: Optional[int]
    last_decision: Optional[str]
    consecutive_errors: int = 0
    message: str = ""
    time: int = field(default_factory=now_ms)


@dataclass
class EvaluationResult(Record):
    experiment_id: str
    strategy_id: str
    strategy_version: str
    config: Dict[str, Any]
    dataset: str
    period: str                          # "train" | "validation" | "test" | "walk_forward" | "paper"
    metrics: Dict[str, Any]
    code_version: str
    seed: Optional[int] = None
    created_time: int = field(default_factory=now_ms)
