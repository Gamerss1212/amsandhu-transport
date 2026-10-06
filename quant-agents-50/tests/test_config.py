from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from quantagents.config import (
    LIVE_APPROVAL_ENV,
    LIVE_APPROVAL_TOKEN,
    AppConfig,
    ExecutionMode,
    RiskConfig,
    load_config,
)


def test_yaml_matches_code_defaults(repo_root: Path) -> None:
    assert load_config(repo_root / "config" / "default.yaml") == AppConfig()


def test_defaults_are_paper_and_conservative(cfg: AppConfig) -> None:
    assert cfg.system.execution_mode is ExecutionMode.PAPER
    assert cfg.system.live_trading_approved is False
    assert cfg.risk.leverage_allowed is False
    assert cfg.risk.shorting_allowed is False
    assert cfg.risk.max_risk_per_trade_pct == 0.5
    assert cfg.risk.max_adv_participation_pct == 1.0
    assert cfg.system.phase == 4  # runs the full 25-agent core


def test_load_none_empty_and_bad_files(tmp_path: Path) -> None:
    assert load_config(None) == AppConfig()
    empty = tmp_path / "empty.yaml"
    empty.write_text("", encoding="utf-8")
    assert load_config(empty) == AppConfig()
    bad = tmp_path / "bad.yaml"
    bad.write_text("- 1\n- 2\n", encoding="utf-8")
    with pytest.raises(ValueError, match="mapping"):
        load_config(bad)
    unknown = tmp_path / "unknown.yaml"
    unknown.write_text("risk:\n  max_risk_per_trade: 2\n", encoding="utf-8")
    with pytest.raises(ValidationError):
        load_config(unknown)


@pytest.mark.parametrize(
    ("risk", "message"),
    [
        ({"max_weekly_loss_pct": 1.0}, "max_weekly_loss_pct"),
        ({"max_drawdown_pct": 3.0}, "max_drawdown_pct"),
        ({"max_gross_exposure_pct": 150.0}, "leverage_allowed"),
        ({"major_trade_risk_pct": 1.0}, "major_trade_risk_pct"),
        ({"data_health_halt": 90.0}, "data_health_halt"),
        ({"quorum_pct": 0.9}, "quorum_pct"),
        ({"drawdown_reduced_frac": 0.8}, "drawdown_reduced_frac"),
    ],
)
def test_inconsistent_risk_limits_are_rejected(risk: dict[str, Any], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        RiskConfig.model_validate(risk)


def test_leverage_unlocks_gross_above_100() -> None:
    assert (
        RiskConfig.model_validate(
            {"leverage_allowed": True, "max_gross_exposure_pct": 150}
        ).max_gross_exposure_pct
        == 150
    )


def test_mode_needs_matching_autonomy() -> None:
    with pytest.raises(ValidationError, match="autonomy_level >= 2"):
        AppConfig.model_validate({"system": {"execution_mode": "shadow", "autonomy_level": 1}})
    assert AppConfig.model_validate({"system": {"execution_mode": "backtest", "autonomy_level": 0}})


def test_live_mode_needs_the_approval_flag() -> None:
    with pytest.raises(ValidationError, match="live_trading_approved"):
        AppConfig.model_validate({"system": {"execution_mode": "live", "autonomy_level": 3}})


def test_approval_flag_only_in_live_mode() -> None:
    with pytest.raises(ValidationError, match="only meaningful"):
        AppConfig.model_validate({"system": {"live_trading_approved": True}})


def test_live_needs_the_human_token(monkeypatch: pytest.MonkeyPatch) -> None:
    live = {
        "system": {"execution_mode": "live", "autonomy_level": 3, "live_trading_approved": True}
    }
    monkeypatch.delenv(LIVE_APPROVAL_ENV, raising=False)
    with pytest.raises(ValidationError, match=LIVE_APPROVAL_ENV):
        AppConfig.model_validate(live)
    monkeypatch.setenv(LIVE_APPROVAL_ENV, "yes")
    with pytest.raises(ValidationError):
        AppConfig.model_validate(live)
    monkeypatch.setenv(LIVE_APPROVAL_ENV, LIVE_APPROVAL_TOKEN)
    assert AppConfig.model_validate(live).system.execution_mode is ExecutionMode.LIVE


def test_teams_needed_rises_in_phase_5(cfg: AppConfig) -> None:
    assert cfg.aggregation.min_teams_agree(4) == 2
    assert cfg.aggregation.min_teams_agree(5) == 3


def test_cost_helpers(cfg: AppConfig) -> None:
    assert cfg.costs.one_way_cost == pytest.approx(0.0015)
    assert cfg.costs.round_trip_cost == pytest.approx(0.003)
    assert cfg.costs.edge_buffer == pytest.approx(0.001)
