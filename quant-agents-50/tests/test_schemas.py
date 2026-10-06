from __future__ import annotations

import math
from datetime import date
from typing import Any

import pytest
from pydantic import ValidationError

from quantagents.schemas import AgentPrediction, Fill, OrderSide, team_of
from tests.helpers import prediction


def test_team_of() -> None:
    assert [team_of(a) for a in ("A01", "A05", "A06", "A23", "A50")] == [1, 1, 2, 5, 10]
    for bad in ("A00", "A51", "B01", "A1", "A0x"):
        with pytest.raises(ValueError):
            team_of(bad)


def test_valid_prediction_and_id() -> None:
    p = prediction("A23", "SYN_A", 0.55, horizon=4)
    assert p.team == 5
    assert p.prediction_id == "C1:A23:SYN_A"
    assert prediction(abstain=True).p_up == 0.5


def _base() -> dict[str, Any]:
    return prediction().model_dump()


@pytest.mark.parametrize(
    "change",
    [
        {"direction": "long", "p_up": 0.4},
        {"direction": "short", "p_up": 0.6},
        {"direction": "flat"},
        {"abstain": True, "direction": "long"},
        {"abstain": True, "direction": "flat", "p_up": 0.6},
        {"team": 4},
        {"exp_return": math.nan},
        {"agent_id": "A99"},
        {"symbol": "bad symbol!"},
        {"unexpected": 1},
    ],
)
def test_invalid_predictions_are_rejected(change: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        AgentPrediction.model_validate({**_base(), **change})


def test_messages_are_frozen() -> None:
    p = prediction()
    with pytest.raises(ValidationError):
        setattr(p, "p_up", 0.7)  # noqa: B010 - frozen models refuse assignment


def test_fill_signed_quantity() -> None:
    common: dict[str, Any] = {
        "fill_id": "F1",
        "intent_id": "I1",
        "symbol": "AAA",
        "qty": 2.0,
        "price": 10.0,
        "fee": 0.0,
        "trade_date": date(2026, 1, 2),
        "kind": "entry",
    }
    assert Fill(side=OrderSide.BUY, **common).signed_qty == 2.0
    assert Fill(side=OrderSide.SELL, **common).signed_qty == -2.0
