"""Typed configuration that mirrors section 1 of the spec.

Every ``*_pct`` value is in percent, so ``0.5`` means 0.5%. Code reads every limit
from here; nothing money-related is hard-coded anywhere else.
"""

from __future__ import annotations

import os
from enum import StrEnum
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

LIVE_APPROVAL_ENV = "QUANTAGENTS_LIVE_APPROVED"
LIVE_APPROVAL_TOKEN = "I_ACCEPT_REAL_MONEY_RISK"


class ExecutionMode(StrEnum):
    """Where orders go. Only backtest and paper have brokers in this kit."""

    BACKTEST = "backtest"
    PAPER = "paper"
    SHADOW = "shadow"
    LIVE = "live"


# Autonomy levels (spec section 1): 0 research, 1 paper, 2 shadow,
# 3 micro-live (human approval), 4 scaled live (human approval).
MODE_MIN_AUTONOMY: dict[ExecutionMode, int] = {
    ExecutionMode.BACKTEST: 0,
    ExecutionMode.PAPER: 1,
    ExecutionMode.SHADOW: 2,
    ExecutionMode.LIVE: 3,
}


def live_approval_present() -> bool:
    """True only when a human has typed the approval token into the environment."""
    return os.environ.get(LIVE_APPROVAL_ENV) == LIVE_APPROVAL_TOKEN


class _Section(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SystemConfig(_Section):
    name: str = "quantagents-50"
    phase: int = Field(default=4, ge=0, le=9)
    execution_mode: ExecutionMode = ExecutionMode.PAPER
    autonomy_level: int = Field(default=1, ge=0, le=4)
    live_trading_approved: bool = False
    capital: float = Field(default=10_000.0, gt=0)
    base_currency: str = "CAD"
    jurisdiction: str = "CA-AB"
    timezone: str = "America/Edmonton"
    seed: int = 7


class RiskConfig(_Section):
    """Limits enforced by A49. Raising any of them needs human approval (spec section 2)."""

    max_risk_per_trade_pct: float = Field(default=0.5, gt=0, le=5)
    major_trade_risk_pct: float = Field(default=0.25, gt=0, le=5)
    max_daily_loss_pct: float = Field(default=2.0, gt=0, le=50)
    max_weekly_loss_pct: float = Field(default=4.0, gt=0, le=50)
    max_drawdown_pct: float = Field(default=15.0, gt=0, le=90)
    leverage_allowed: bool = False
    max_gross_exposure_pct: float = Field(default=100.0, gt=0, le=400)
    max_position_pct: float = Field(default=20.0, gt=0, le=100)
    shorting_allowed: bool = False
    max_order_notional_pct: float = Field(default=25.0, gt=0, le=100)
    price_band_pct: float = Field(default=5.0, gt=0, le=50)
    max_orders_per_minute: int = Field(default=10, ge=1, le=1000)
    max_adv_participation_pct: float = Field(default=1.0, gt=0, le=100)  # of daily traded value
    stop_atr_multiple: float = Field(default=2.0, gt=0, le=10)
    quantity_step: float = Field(default=1.0, gt=0)
    data_health_defensive: float = Field(default=80.0, ge=0, le=100)
    data_health_halt: float = Field(default=50.0, ge=0, le=100)
    quorum_pct: float = Field(default=0.70, gt=0, le=1)
    quorum_reduced_pct: float = Field(default=0.85, gt=0, le=1)
    drawdown_reduced_frac: float = Field(default=0.50, gt=0, lt=1)
    drawdown_defensive_frac: float = Field(default=0.75, gt=0, lt=1)

    @model_validator(mode="after")
    def _limits_are_consistent(self) -> RiskConfig:
        if self.max_weekly_loss_pct < self.max_daily_loss_pct:
            raise ValueError("max_weekly_loss_pct must be >= max_daily_loss_pct")
        if self.max_drawdown_pct < self.max_weekly_loss_pct:
            raise ValueError("max_drawdown_pct must be >= max_weekly_loss_pct")
        if self.max_gross_exposure_pct > 100 and not self.leverage_allowed:
            raise ValueError("max_gross_exposure_pct above 100 requires leverage_allowed: true")
        if self.major_trade_risk_pct > self.max_risk_per_trade_pct:
            raise ValueError("major_trade_risk_pct must be <= max_risk_per_trade_pct")
        if self.data_health_halt >= self.data_health_defensive:
            raise ValueError("data_health_halt must be below data_health_defensive")
        if self.quorum_pct > self.quorum_reduced_pct:
            raise ValueError("quorum_pct must be <= quorum_reduced_pct")
        if self.drawdown_reduced_frac >= self.drawdown_defensive_frac:
            raise ValueError("drawdown_reduced_frac must be below drawdown_defensive_frac")
        return self


class CostConfig(_Section):
    fee_bps: float = Field(default=10.0, ge=0, le=500)
    slippage_bps: float = Field(default=5.0, ge=0, le=500)
    edge_buffer_pct: float = Field(default=0.10, ge=0, le=10)

    @property
    def one_way_cost(self) -> float:
        """Fees plus slippage for one side of a trade, as a fraction of notional."""
        return (self.fee_bps + self.slippage_bps) / 1e4

    @property
    def round_trip_cost(self) -> float:
        return 2.0 * self.one_way_cost

    @property
    def edge_buffer(self) -> float:
        return self.edge_buffer_pct / 100.0


class AggregationConfig(_Section):
    """Pooling and GO rules (spec section 13)."""

    decision_horizon_days: int = Field(default=20, ge=1, le=260)
    shrink_to_equal: float = Field(default=0.30, ge=0, le=1)
    agent_weight_cap: float = Field(default=0.25, gt=0, le=1)
    team_weight_cap: float = Field(default=0.40, gt=0, le=1)
    go_min_p: float = Field(default=0.55, gt=0.5, lt=1)
    go_min_teams_agree: int = Field(default=2, ge=1, le=10)
    go_min_teams_agree_from_phase5: int = Field(default=3, ge=1, le=10)
    edge_cost_multiple: float = Field(default=1.5, ge=0)
    max_p_no_trade: float = Field(default=0.50, gt=0, le=1)
    n_eff_min: float = Field(default=5.0, ge=1)
    low_n_eff_p_cap: float = Field(default=0.60, gt=0.5, lt=1)
    disagreement_max: float = Field(default=1.0, gt=0)
    two_stage_from_phase: int = Field(default=4, ge=0, le=9)
    debate_live_from_phase: int = Field(default=6, ge=0, le=9)

    def min_teams_agree(self, phase: int) -> int:
        """Two teams until Phase 5 (few teams exist yet), then the spec's three."""
        return self.go_min_teams_agree_from_phase5 if phase >= 5 else self.go_min_teams_agree


class ValidationConfig(_Section):
    """Promotion thresholds used by A44 (spec section 64)."""

    min_t_stat: float = 3.0
    min_psr: float = Field(default=0.95, gt=0, lt=1)
    min_dsr: float = Field(default=0.95, gt=0, lt=1)
    max_pbo: float = Field(default=0.20, ge=0, le=1)
    reject_pbo: float = Field(default=0.50, ge=0, le=1)
    fdr_q: float = Field(default=0.10, gt=0, lt=1)
    min_observations: int = Field(default=252, ge=30)
    bootstrap_samples: int = Field(default=500, ge=50)
    bootstrap_mean_block: float = Field(default=10.0, ge=1)
    max_spa_p: float = Field(default=0.05, gt=0, lt=1)  # Hansen SPA, all variants vs cash
    min_oos_is_ratio: float = Field(default=0.5, ge=0)  # walk-forward OOS / IS Sharpe
    wf_train_days: int = Field(default=756, ge=60)  # 3 years in, then
    wf_test_days: int = Field(default=252, ge=20)  # 1 year out, rolling


class UniverseConfig(_Section):
    asset_class: str = "US_equities"
    symbols: tuple[str, ...] = ("SYN_A", "SYN_B", "SYN_C", "SYN_D", "SYN_E", "SYN_F")


class LiveConfig(_Section):
    """Limits of the real-money mirror (Phase 8, ``execution/live.py``).

    Amounts are in the pair's quote currency (CAD for ``BTC-CAD.KRAKEN``). A budget of 0 means
    nothing real is ever bought. Only the owner raises these (spec section 2).
    """

    budget: float = Field(default=0.0, ge=0)  # the most the mirror may have invested
    max_order_value: float = Field(default=50.0, gt=0)  # the largest single order
    min_order_value: float = Field(default=10.0, ge=0)  # smaller differences are left alone
    max_slippage_pct: float = Field(default=0.5, gt=0, le=5)  # limit price vs bid/ask
    order_timeout_seconds: int = Field(default=60, ge=5, le=900)  # then the rest is cancelled

    @model_validator(mode="after")
    def _orders_fit(self) -> LiveConfig:
        if self.min_order_value > self.max_order_value:
            raise ValueError("live.min_order_value must be <= live.max_order_value")
        return self


class AppConfig(_Section):
    system: SystemConfig = Field(default_factory=SystemConfig)
    risk: RiskConfig = Field(default_factory=RiskConfig)
    costs: CostConfig = Field(default_factory=CostConfig)
    aggregation: AggregationConfig = Field(default_factory=AggregationConfig)
    validation: ValidationConfig = Field(default_factory=ValidationConfig)
    universe: UniverseConfig = Field(default_factory=UniverseConfig)
    live: LiveConfig = Field(default_factory=LiveConfig)

    @model_validator(mode="after")
    def _safety_rules(self) -> AppConfig:
        system = self.system
        minimum = MODE_MIN_AUTONOMY[system.execution_mode]
        if system.autonomy_level < minimum:
            raise ValueError(
                f"execution_mode {system.execution_mode.value!r} needs autonomy_level >= {minimum}"
            )
        if system.execution_mode is ExecutionMode.LIVE and not system.live_trading_approved:
            raise ValueError("execution_mode 'live' requires live_trading_approved: true")
        if system.live_trading_approved:
            if system.execution_mode is not ExecutionMode.LIVE:
                raise ValueError(
                    "live_trading_approved is only meaningful in execution_mode 'live'"
                )
            if not live_approval_present():
                raise ValueError(
                    f"live trading needs a human to set {LIVE_APPROVAL_ENV}={LIVE_APPROVAL_TOKEN}"
                )
        return self


def load_config(path: Path | str | None = None) -> AppConfig:
    """Load and validate a YAML config. No path means the built-in defaults."""
    if path is None:
        return AppConfig()
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if raw is None:
        return AppConfig()
    if not isinstance(raw, dict):
        raise ValueError(f"{path}: top level must be a mapping")
    return AppConfig.model_validate(raw)
