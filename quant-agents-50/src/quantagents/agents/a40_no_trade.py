"""A40 No-Trade Agent (Team 8, Phase 2, Tier 1: blocks new entries).

Estimates P(doing nothing is best) with a transparent rule score. p_no_trade >= 0.5
blocks new entries for that symbol this cycle. Reads A06's crisis label and A09's
tradability when those agents run (each adds a red flag; neither can remove one). If A06 or
A35 crashes, that counts as a red flag too: a missing check must never make trading easier. A calibrated classifier trained on past
regret can replace the rule score later; keep the rules as a floor.
"""

from __future__ import annotations

from typing import ClassVar

from quantagents.agents.base import Agent
from quantagents.config import AppConfig
from quantagents.schemas import LiquidityReport, NoTradeVerdict, RegimeReport, VolForecast


class NoTradeAgent(Agent):
    agent_id = "A40"
    name = "No-Trade Agent"
    kind = "stat"
    info_subset = ("net_edge", "data_health", "disagreement", "novelty", "drawdown")

    base_rate: ClassVar[float] = 0.15
    cap: ClassVar[float] = 0.95

    def verdict(
        self,
        *,
        cycle_id: str,
        symbol: str,
        health_score: float,
        vol: VolForecast | None,
        disagreement: float,
        net_edge: float | None,
        drawdown_used: float,
        cfg: AppConfig,
        regime: RegimeReport | None = None,
        liquidity: LiquidityReport | None = None,
        round_trip_cost: float | None = None,
        regime_failed: bool = False,
        scorekeeper_failed: bool = False,
    ) -> NoTradeVerdict:
        cost = max(cfg.costs.round_trip_cost, round_trip_cost or 0.0)
        rules: list[tuple[bool, float, str]] = [
            (
                net_edge is None or net_edge < cfg.aggregation.edge_cost_multiple * cost,
                0.35,
                "net edge too small for the costs",
            ),
            (health_score < 90.0, 0.20, f"data health {health_score:.0f} below 90"),
            (vol is None, 0.30, "no volatility forecast"),
            (vol is not None and vol.shock, 0.25, "volatility shock on the last bar"),
            (
                vol is not None and not vol.shock and vol.regime == "high",
                0.15,
                "high-volatility regime",
            ),
            (
                disagreement > 0.5 * cfg.aggregation.disagreement_max,
                0.15,
                "agents disagree strongly",
            ),
            (drawdown_used >= 0.5, 0.15, "half or more of the drawdown limit is used"),
            (
                regime is not None and regime.label == "crisis",
                0.25,
                "A06 crisis regime",
            ),
            (regime_failed, 0.25, "A06 regime check failed: counted as a red flag"),
            (scorekeeper_failed, 0.25, "A35 calibration failed: counted as a red flag"),
            (
                liquidity is not None and liquidity.tradability < 0.5,
                0.25,
                "thin liquidity (A09): " + (liquidity.detail if liquidity is not None else ""),
            ),
        ]
        fired = [(weight, text) for hit, weight, text in rules if hit]
        p = min(self.cap, self.base_rate + sum(weight for weight, _ in fired))
        reasons = tuple(text for _, text in fired) or ("no red flags",)
        return NoTradeVerdict(cycle_id=cycle_id, symbol=symbol, p_no_trade=p, reasons=reasons)
