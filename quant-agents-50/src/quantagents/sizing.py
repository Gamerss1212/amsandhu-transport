"""Small shared helpers for quantities. Code does all arithmetic; LLMs never size trades."""

from __future__ import annotations

import math


def floor_to_step(quantity: float, step: float) -> float:
    """Round a non-negative quantity down to a multiple of ``step`` (never up)."""
    if step <= 0:
        raise ValueError("step must be positive")
    if not math.isfinite(quantity) or quantity <= 0:
        return 0.0
    units = math.floor(quantity / step + 1e-9)
    return round(units * step, 10)
