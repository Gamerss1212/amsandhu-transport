"""Typed messages between agents (spec section 81).

Every model is frozen and rejects unknown fields, so a malformed message fails loudly
instead of flowing silently into a trading decision.
"""

from __future__ import annotations

import math
from datetime import date
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

AGENT_ID_PATTERN = r"^A(0[1-9]|[1-4][0-9]|50)$"
SYMBOL_PATTERN = r"^[A-Za-z0-9._:/-]{1,32}$"
HEX64_PATTERN = r"^[0-9a-f]{64}$"
SCHEMA_VERSION = "v1"


def team_of(agent_id: str) -> int:
    """Team number 1-10 for an agent id such as 'A23' (five agents per team)."""
    if len(agent_id) != 3 or agent_id[0] != "A" or not agent_id[1:].isdigit():
        raise ValueError(f"bad agent id {agent_id!r}")
    number = int(agent_id[1:])
    if not 1 <= number <= 50:
        raise ValueError(f"bad agent id {agent_id!r}")
    return (number - 1) // 5 + 1


class Message(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Direction(StrEnum):
    LONG = "long"
    SHORT = "short"
    FLAT = "flat"


class OrderSide(StrEnum):
    BUY = "buy"
    SELL = "sell"


class DegradationLevel(StrEnum):
    NORMAL = "NORMAL"
    REDUCED = "REDUCED"
    DEFENSIVE = "DEFENSIVE"
    HALTED = "HALTED"


class HealthAction(StrEnum):
    OK = "ok"
    DEFENSIVE = "defensive"
    HALT = "halt"


class DebateOutcome(StrEnum):
    PROCEED = "proceed"
    REDUCE = "reduce"
    DEFER = "defer"
    REJECT = "reject"
    NOT_LIVE = "not_live"


class CheckResult(Message):
    name: str
    passed: bool
    detail: str = ""


class MarketSnapshot(Message):
    """A01 output: what data the cycle is allowed to see, identified by a hash."""

    snapshot_id: str
    as_of: date
    symbols: tuple[str, ...]
    n_bars: int = Field(ge=1)
    last_close: dict[str, float]


class DataHealthReport(Message):
    """A02 output. Score below 80: no new entries. Below 50: kill switch."""

    snapshot_id: str
    score_0_100: float = Field(ge=0, le=100)
    checks: tuple[CheckResult, ...]
    stale_symbols: tuple[str, ...] = ()
    blocked_symbols: tuple[str, ...] = ()
    action: HealthAction


class FeatureFrame(Message):
    """A03 output: causal feature values per symbol at the as-of date (finite values only)."""

    snapshot_id: str
    feature_version: str
    values: dict[str, dict[str, float]]

    def get(self, symbol: str) -> dict[str, float]:
        return self.values.get(symbol, {})


class VolForecast(Message):
    symbol: str
    sigma_daily: float = Field(gt=0)
    sigma_annual: float = Field(gt=0)
    regime: Literal["low", "normal", "high"]
    shock: bool = False


class SymbolRegime(Message):
    """A06 view of one symbol: is it trending or ranging, and which way?"""

    symbol: str
    p_trending: float = Field(ge=0, le=1)
    direction: Direction
    label: Literal["trending_up", "trending_down", "ranging", "unknown"]


class RegimeReport(Message):
    """A06 output: market regime probabilities plus a per-symbol trend/range label."""

    snapshot_id: str
    agent_id: str = Field(default="A06", pattern=AGENT_ID_PATTERN)
    p_high_vol: float = Field(ge=0, le=1)
    p_high_vol_prev: float = Field(ge=0, le=1)  # the same estimate 5 bars earlier
    p_risk_on: float = Field(ge=0, le=1)
    p_crisis: float = Field(ge=0, le=1)
    breadth: float = Field(ge=0, le=1)  # share of symbols above their 200-day average
    confidence: float = Field(ge=0, le=1)
    label: Literal["risk_on", "risk_off", "mixed", "crisis", "unknown"]
    vol_label: Literal["calm", "turbulent", "unknown"]
    symbols: tuple[SymbolRegime, ...] = ()
    methods: tuple[str, ...] = ()

    def get(self, symbol: str) -> SymbolRegime | None:
        for item in self.symbols:
            if item.symbol == symbol:
                return item
        return None


class DetectorResult(Message):
    name: str
    ran: bool = True  # False when there was not enough data to run this detector
    fired: bool
    value: float | None = None
    threshold: float
    detail: str = ""


class TransitionReport(Message):
    """A07 output. ``alert`` halves system risk through A49 (REDUCED level)."""

    snapshot_id: str
    agent_id: str = Field(default="A07", pattern=AGENT_ID_PATTERN)
    alert: bool
    severity: float = Field(ge=0, le=1)
    p_recent_change: float = Field(ge=0, le=1)
    detectors: tuple[DetectorResult, ...]

    @property
    def fired(self) -> tuple[str, ...]:
        return tuple(d.name for d in self.detectors if d.fired)


class LiquidityReport(Message):
    """A09 output for one symbol: can we trade this size cheaply right now?"""

    symbol: str
    spread_bps: float = Field(ge=0)  # high-low proxy, information only (too noisy to act on)
    spread_ratio: float = Field(ge=0)  # proxy today / its 1-year median, information only
    adv_notional: float = Field(ge=0)  # median daily traded value, last 20 days
    amihud: float | None = Field(default=None, ge=0)  # None when it cannot be measured
    impact_bps: float = Field(ge=0)  # square-root impact of the reference order
    est_cost_bps: float = Field(ge=0)  # half spread + impact, one way
    tradability: float = Field(ge=0, le=1)
    max_order_notional: float = Field(ge=0)  # participation cap x ADV
    reference_notional: float = Field(ge=0)
    detail: str = ""


class ContextReport(Message):
    """Team 2 output shared with every agent (context is shared by design, signals are not).

    A08 fills the volatility forecasts; A46 adds A06's regime, A07's transition check and
    A09's liquidity when those agents are running.
    """

    snapshot_id: str
    agent_id: str = Field(pattern=AGENT_ID_PATTERN)
    vol_forecasts: tuple[VolForecast, ...]
    transition_alert: bool = False
    novelty_score: float = Field(default=0.0, ge=0, le=1)
    regime: RegimeReport | None = None
    transition: TransitionReport | None = None
    liquidity: tuple[LiquidityReport, ...] = ()

    def vol(self, symbol: str) -> VolForecast | None:
        for forecast in self.vol_forecasts:
            if forecast.symbol == symbol:
                return forecast
        return None

    def liq(self, symbol: str) -> LiquidityReport | None:
        for report in self.liquidity:
            if report.symbol == symbol:
                return report
        return None


class AgentPrediction(Message):
    """A sealed signal-agent forecast.

    ``p_up`` is P(asset return over ``horizon_bars`` > 0). It is direction-free so that
    log-odds pooling works across agents; costs are handled by the net-edge rule (section 13).
    """

    agent_id: str = Field(pattern=AGENT_ID_PATTERN)
    team: int = Field(ge=1, le=10)
    model_version: str = "1.0"
    cycle_id: str
    snapshot_id: str
    symbol: str = Field(pattern=SYMBOL_PATTERN)
    horizon_bars: int = Field(ge=1, le=520)
    abstain: bool = False
    direction: Direction
    p_up: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    exp_return: float = 0.0
    exp_vol: float = Field(default=0.0, ge=0.0)
    reasoning_summary: str = Field(default="", max_length=500)
    info_subset: tuple[str, ...] = ()

    @field_validator("exp_return", "exp_vol", "p_up", "confidence")
    @classmethod
    def _finite(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("must be a finite number")
        return value

    @model_validator(mode="after")
    def _consistent(self) -> AgentPrediction:
        if self.team != team_of(self.agent_id):
            raise ValueError(f"{self.agent_id} belongs to team {team_of(self.agent_id)}")
        if self.abstain:
            if self.direction is not Direction.FLAT or self.p_up != 0.5:
                raise ValueError("an abstention must have direction 'flat' and p_up 0.5")
        elif self.direction is Direction.FLAT:
            raise ValueError("a non-abstaining prediction must be long or short")
        elif self.direction is Direction.LONG and not self.p_up > 0.5:
            raise ValueError("a long prediction needs p_up > 0.5")
        elif self.direction is Direction.SHORT and not self.p_up < 0.5:
            raise ValueError("a short prediction needs p_up < 0.5")
        return self

    @property
    def prediction_id(self) -> str:
        return f"{self.cycle_id}:{self.agent_id}:{self.symbol}"


class Commitment(Message):
    agent_id: str = Field(pattern=AGENT_ID_PATTERN)
    cycle_id: str
    commit_hash: str = Field(pattern=HEX64_PATTERN)


class NoTradeVerdict(Message):
    """A40 output. p_no_trade >= 0.5 blocks new entries for this symbol."""

    cycle_id: str
    symbol: str
    p_no_trade: float = Field(ge=0, le=1)
    reasons: tuple[str, ...]


class DecisionProposal(Message):
    decision_id: str
    cycle_id: str
    symbol: str
    direction: Direction
    pooled_p: float = Field(ge=0, le=1)
    p_direction: float = Field(ge=0, le=1)
    n_eff: float = Field(ge=0)
    disagreement: float = Field(ge=0)
    teams_agree: int = Field(ge=0)
    net_edge: float
    exp_return: float
    go: bool
    reasons: tuple[str, ...]
    debate_outcome: DebateOutcome
    size_hint: float = Field(ge=0, le=1)
    rationale_ids: tuple[str, ...] = ()
    memo: str = ""


class OrderIntent(Message):
    intent_id: str
    decision_id: str | None
    symbol: str
    side: OrderSide
    qty: float = Field(gt=0)
    ref_price: float = Field(gt=0)
    stop_price: float | None = Field(default=None, gt=0)
    order_type: Literal["market"] = "market"
    reason: str


class TargetPosition(Message):
    symbol: str
    target_qty: float
    stop_price: float | None = None
    risk_pct: float = Field(default=0.0, ge=0)


class TargetPortfolio(Message):
    cycle_id: str
    positions: tuple[TargetPosition, ...]
    notes: tuple[str, ...] = ()


class LimitCheck(Message):
    name: str
    passed: bool
    limit: float | None = None
    value: float | None = None
    detail: str = ""


class RiskCheckResult(Message):
    """A49 verdict on one order intent."""

    risk_check_id: str
    intent_id: str
    decision_id: str | None
    symbol: str
    side: OrderSide
    requested_qty: float = Field(ge=0)
    approved_qty: float = Field(ge=0)
    passed: bool
    risk_reducing: bool
    checks: tuple[LimitCheck, ...]
    size_adjustment: float = Field(ge=0, le=1)
    degradation_level: DegradationLevel
    reason: str
    engine_version: str


class RiskVerdict(Message):
    cycle_id: str
    level: DegradationLevel
    level_reasons: tuple[str, ...]
    results: tuple[RiskCheckResult, ...]
    kill_switch_engaged: bool


class Fill(Message):
    fill_id: str
    intent_id: str
    symbol: str
    side: OrderSide
    qty: float = Field(gt=0)
    price: float = Field(gt=0)
    fee: float = Field(ge=0)
    trade_date: date
    kind: Literal["entry", "exit", "stop"]

    @property
    def signed_qty(self) -> float:
        return self.qty if self.side is OrderSide.BUY else -self.qty


class LedgerState(Message):
    cash: float
    positions: dict[str, float]
    equity: float
    realized_pnl: float
    fees_paid: float
    n_fills: int = Field(ge=0)


class ReconciliationReport(Message):
    ok: bool
    diffs: tuple[str, ...]
    ledger_cash: float
    broker_cash: float


class ReliabilityBin(Message):
    """One bucket of a reliability table: when the agent said p, how often was it right?"""

    lower: float
    upper: float
    n: int = Field(ge=0)
    mean_confidence: float
    hit_rate: float


class AgentScorecard(Message):
    """A35 scorecard for one agent, from matured predictions only (spec section 16)."""

    agent_id: str = Field(pattern=AGENT_ID_PATTERN)
    state: str
    n_scored: int = Field(ge=0)
    effective_n: float = Field(default=0.0, ge=0)  # independent outcomes (overlaps removed)
    n_abstained: int = Field(ge=0)
    n_pending: int = Field(ge=0)
    hit_rate: float | None = None
    brier: float | None = None
    brier_climatology: float | None = None
    brier_skill: float | None = None  # above 0 beats always guessing the base rate
    skill_t: float | None = None  # how many standard errors the skill is above zero
    log_loss: float | None = None
    mean_confidence: float | None = None
    temperature: float = Field(default=1.0, ge=0, le=1)  # 1 = unchanged, lower = less sure
    weight: float = Field(default=1.0, ge=0)
    promotion_ready: bool = False
    brier_by_regime: dict[str, float] = Field(default_factory=dict)
    bins: tuple[ReliabilityBin, ...] = ()


class ScoreSummary(Message):
    """A35 output for one cycle."""

    as_of: date
    n_records: int = Field(ge=0)
    n_scored: int = Field(ge=0)
    n_pending: int = Field(ge=0)
    cards: tuple[AgentScorecard, ...]
    pooled_n: int = Field(ge=0)
    pooled_brier: float | None = None
    pooled_brier_skill: float | None = None
    n_eff: float | None = None
    rho: float | None = None  # cross-symbol outcome correlation used to discount samples
    notes: tuple[str, ...] = ()

    def card(self, agent_id: str) -> AgentScorecard | None:
        for card in self.cards:
            if card.agent_id == agent_id:
                return card
        return None


class StressScenario(Message):
    name: str
    loss_pct: float  # percent of equity; positive = loss
    detail: str = ""


class StressReport(Message):
    """A45 output: what could the book lose in bad conditions, and should entries shrink?"""

    cycle_id: str
    equity: float
    gross_exposure_pct: float = Field(ge=0)
    scenarios: tuple[StressScenario, ...]
    var_99_1d_pct: float
    es_99_1d_pct: float
    mc_es_99_20d_pct: float
    p_daily_limit_breach_20d: float = Field(ge=0, le=1)
    p_ruin_20d: float = Field(ge=0, le=1)
    tail_loss_before_pct: float  # the book after today's exits, before new entries
    tail_loss_pct: float  # ... with today's entries at full size
    tail_loss_final_pct: float | None = None  # ... with entries after A45 scaled them
    budget_pct: float = Field(gt=0)
    entry_scale: float = Field(ge=0, le=1)
    notes: tuple[str, ...] = ()


class TradeDecisionRecord(Message):
    """One row of the trade journal (spec section 70)."""

    decision_id: str
    cycle_id: str
    as_of: date
    snapshot_hash: str
    prediction_ids: tuple[str, ...]
    proposal: DecisionProposal
    risk_check_id: str | None = None
    order: OrderIntent | None = None
    fills: tuple[Fill, ...] = ()
    outcome: str = "open"
