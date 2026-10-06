"""No agent may see the future (spec section 59).

Every bar after date t is scrambled; every agent's output as of t must stay exactly the same.
Run once per agent, and once for the whole 25-agent cycle.
"""

from __future__ import annotations

from datetime import date

import pytest

from quantagents.agents.a01_market_data import MarketDataAgent
from quantagents.agents.a02_data_quality import DataQualityAgent
from quantagents.agents.a03_features import FeatureAgent
from quantagents.agents.a06_regime import RegimeAgent
from quantagents.agents.a07_transition import TransitionAgent
from quantagents.agents.a08_volatility import VolatilityAgent
from quantagents.agents.a09_liquidity import LiquidityAgent
from quantagents.agents.a35_scorekeeper import Scorekeeper
from quantagents.agents.a45_stress import StressAgent
from quantagents.agents.base import AgentContext
from quantagents.config import AppConfig
from quantagents.execution.paper import PaperAccount
from quantagents.market import MarketData
from quantagents.orchestrator import Orchestrator
from quantagents.registry import Registry
from quantagents.risk.killswitch import KillSwitch
from quantagents.validation.leakage import perturb_future
from tests.helpers import prediction

T = date(2026, 6, 30)


@pytest.fixture(scope="module")
def pair(market: MarketData) -> tuple[MarketData, MarketData]:
    return market, perturb_future(market, market.index_of(T), seed=99)


def outputs(market: MarketData, registry: Registry) -> dict[str, object]:
    cfg = AppConfig()
    view = market.view(T)
    symbols = market.symbols
    features = FeatureAgent().compute(view, "S", symbols)
    vol = VolatilityAgent().forecast(view, "S", symbols)
    regime = RegimeAgent().classify(view, "S", symbols, features)
    ctx = AgentContext("C", "S", view, cfg, features, vol, symbols)
    out: dict[str, object] = {
        "A01": MarketDataAgent().snapshot(view),
        "A02": DataQualityAgent().check(view, "S", cfg.risk),
        "A03": features,
        "A06": regime,
        "A07": TransitionAgent().detect(view, "S", symbols, regime),
        "A08": vol,
        "A09": LiquidityAgent().assess(view, symbols, vol, reference_notional=2000, cfg=cfg),
    }
    for agent in registry.signal_agents(4):
        out[agent.agent_id] = agent.predict(ctx)
    keeper = Scorekeeper()
    early = market.dates[market.index_of(T) - 30]
    keeper.record([prediction("A11", "SYN_A", 0.6, horizon=10)], as_of=early, voters={"A11"})
    keeper.record(
        [prediction("A16", "SYN_B", 0.6, horizon=60, cycle_id="C2")], as_of=early, voters=set()
    )
    keeper.score_matured(view)
    out["A35"] = sorted((k, r.outcome) for k, r in keeper.records.items())
    prices = {s: float(view.close(s)[-1]) for s in symbols}
    out["A45"] = StressAgent().assess(
        cycle_id="C",
        view=view,
        before={},
        after={"SYN_A": 10.0, "SYN_C": 5.0},
        prices=prices,
        stops={},
        equity=10_000.0,
        drawdown_pct=0.0,
        context=vol,
        cfg=cfg,
    )
    return out


def test_every_agent_ignores_the_future(
    pair: tuple[MarketData, MarketData], registry: Registry
) -> None:
    original, scrambled = pair
    assert original.bars("SYN_A").close[-1] != scrambled.bars("SYN_A").close[-1]
    a, b = outputs(original, registry), outputs(scrambled, registry)
    assert set(a) >= {"A01", "A02", "A03", "A06", "A07", "A08", "A09", "A11", "A12", "A13"}
    assert set(a) >= {"A15", "A16", "A23", "A35", "A45"}
    for agent_id in a:
        assert a[agent_id] == b[agent_id], f"{agent_id} changed when only the future changed"
    a35 = a["A35"]
    assert (
        isinstance(a35, list) and (a35[0][1] is not None) and a35[1][1] is None
    )  # 60 bars: pending


def test_the_whole_cycle_ignores_the_future(
    pair: tuple[MarketData, MarketData], registry: Registry
) -> None:
    def cycle(market: MarketData) -> object:
        cfg = AppConfig()
        orchestrator = Orchestrator(
            cfg,
            registry,
            PaperAccount(cfg.system.capital, cfg.costs),
            KillSwitch(),
            nonce_factory=lambda: "fixed",
            simulate_next_open=False,  # filling at tomorrow's open is the one allowed peek
        )
        return orchestrator.run_cycle(market, T).model_dump()

    original, scrambled = pair
    assert cycle(original) == cycle(scrambled)
