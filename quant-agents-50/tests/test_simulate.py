from __future__ import annotations

import pytest

from quantagents.config import AppConfig
from quantagents.data.synthetic import DEMO_AS_OF
from quantagents.market import MarketData
from quantagents.registry import Registry
from quantagents.report import format_simulation
from quantagents.simulate import blocker, run_paper_simulation
from tests.helpers import with_second_team


def test_simulation_runs_the_full_cycle_every_day(
    cfg: AppConfig, registry: Registry, market: MarketData
) -> None:
    sim = run_paper_simulation(cfg, registry, market, days=25, end=DEMO_AS_OF, keep_reports=True)
    assert len(sim.days) == len(sim.reports) == 25 and sim.days[-1].as_of == DEMO_AS_OF
    assert sum(sim.levels.values()) == 25
    assert sim.final_scores is not None and sim.final_scores.n_scored > 0
    assert sim.stats["start_equity"] == cfg.system.capital
    assert sim.blockers and not sim.kill_switch_engaged
    text = format_simulation(sim)
    assert "25 trading days" in text and "Why symbols were not traded" in text
    again = run_paper_simulation(cfg, registry, market, days=25, end=DEMO_AS_OF)
    assert [d.model_dump() for d in again.days] == [d.model_dump() for d in sim.days]


def test_simulation_trades_when_the_chain_says_go(registry: Registry, market: MarketData) -> None:
    sim = run_paper_simulation(AppConfig(), with_second_team(registry), market, days=15)
    assert sim.stats["n_fills"] > 0 and sim.stats["days_with_go"] > 0
    assert sim.account.ledger.fills and sim.final_scores is not None
    assert all(d.entry_scale is not None for d in sim.days)


def test_simulation_input_checks(cfg: AppConfig, registry: Registry, market: MarketData) -> None:
    with pytest.raises(ValueError, match="days"):
        run_paper_simulation(cfg, registry, market, days=0)
    with pytest.raises(ValueError, match="not enough data"):
        run_paper_simulation(cfg, registry, market, days=len(market))


def test_blocker_labels() -> None:
    assert blocker("pooled p 0.53 below 0.55") == "pooled probability below the GO bar"
    assert blocker("1 team(s) agree, 2 needed") == "too few teams agree"
    assert blocker("Tier-1 block: A05 reconciliation break").startswith("Tier-1")
    assert blocker("something new") == "something new"
