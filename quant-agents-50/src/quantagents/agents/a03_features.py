"""A03 Feature Factory (Team 1, Phase 1).

Computes causal features (Appendix B) for each tradable symbol at the as-of date.
"""

from __future__ import annotations

from collections.abc import Sequence

from quantagents.agents.base import Agent
from quantagents.features import FEATURE_VERSION, symbol_features
from quantagents.market import MarketView
from quantagents.schemas import FeatureFrame


class FeatureAgent(Agent):
    agent_id = "A03"
    name = "Feature Factory"
    kind = "code"
    info_subset = ("ohlcv",)

    def compute(self, view: MarketView, snapshot_id: str, symbols: Sequence[str]) -> FeatureFrame:
        return FeatureFrame(
            snapshot_id=snapshot_id,
            feature_version=FEATURE_VERSION,
            values={symbol: symbol_features(view, symbol) for symbol in symbols},
        )
