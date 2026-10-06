from __future__ import annotations

from pathlib import Path

import pytest

from quantagents.registry import AgentSpec, Registry, default_registry_path


def test_fifty_agents_in_ten_teams_of_five(registry: Registry) -> None:
    assert len(registry) == 50
    teams = {s.team for s in registry.specs}
    assert len(teams) == 10
    assert all(len(registry.team(t)) == 5 for t in teams)


def test_activation_schedule_matches_spec_section_22(registry: Registry) -> None:
    assert registry.cumulative_counts() == {1: 5, 2: 13, 3: 20, 4: 27, 5: 40, 6: 47, 7: 50}


def test_authority_tiers_match_spec_section_8(registry: Registry) -> None:
    assert [s.id for s in registry.specs if s.tier == 0] == ["A49"]
    tier1 = {s.id for s in registry.specs if s.tier == 1}
    assert tier1 == {"A02", "A05", "A07", "A34", "A39", "A40", "A44"}
    assert {s.id for s in registry.specs if s.tier == 2} == {"A47", "A48"}


def test_exactly_nine_agents_use_an_llm(registry: Registry) -> None:
    llm = {s.id for s in registry.specs if s.llm}
    assert llm == {"A04", "A25", "A26", "A36", "A37", "A38", "A39", "A41", "A46"}


def test_every_built_agent_imports_and_matches_its_id(registry: Registry) -> None:
    built = [s for s in registry.specs if s.implementation]
    assert len(built) == 25
    for spec in built:
        assert getattr(spec.load_class(), "agent_id") == spec.id  # noqa: B009


CORE = {
    "A01", "A02", "A03", "A05",  # data and integrity
    "A06", "A07", "A08", "A09",  # market context
    "A11", "A12", "A13", "A15",  # trend and momentum
    "A16", "A23",  # mean reversion, calendar
    "A35",  # scorekeeper
    "A39", "A40",  # red team, no-trade
    "A43", "A44", "A45",  # research and validation
    "A46", "A47", "A48", "A49", "A50",  # command, risk, execution
}  # fmt: skip


def test_the_25_agent_core_is_complete(registry: Registry) -> None:
    core = registry.core()
    assert {s.id for s in core} == CORE and len(core) == 25
    assert all(s.implementation is not None for s in core), "every core agent is built"
    assert all(s.phase <= 4 for s in core), "phase 4 switches the whole core on"
    assert {s.id for s in registry.active(4)} == CORE
    assert registry.missing(4) == []
    parked = registry.parked()
    assert len(parked) == 25 and not any(s.core or s.implementation for s in parked)
    assert [a.agent_id for a in registry.signal_agents(4)] == [
        "A11",
        "A12",
        "A13",
        "A15",
        "A16",
        "A23",
    ]
    new_signals = {s.id: s.state for s in core if s.id in {"A13", "A15"}}
    assert new_signals == {"A13": "shadow", "A15": "shadow"}  # scored, no vote until promoted
    # Every agent with stop power (Tier 0 and 1) that the core needs is in it.
    assert {"A02", "A05", "A07", "A39", "A40", "A44", "A49"} <= CORE


def test_phase_3_running_and_missing(registry: Registry) -> None:
    running = {s.id for s in registry.active(3)}
    assert running == {
        "A01",
        "A02",
        "A03",
        "A05",
        "A08",
        "A09",
        "A11",
        "A12",
        "A16",
        "A23",
        "A39",
        "A40",
        "A43",
        "A44",
        "A45",
        "A46",
        "A48",
        "A49",
        "A50",
    }
    assert registry.missing(3) == []  # A21 is scheduled for Phase 2 but parked, not missing
    assert [a.agent_id for a in registry.signal_agents(3)] == ["A11", "A12", "A16", "A23"]
    assert registry.signal_agents(1) == []


def _replace(registry: Registry, agent_id: str, **changes: object) -> list[AgentSpec]:
    return [s.model_copy(update=changes) if s.id == agent_id else s for s in registry.specs]


def test_bad_rosters_are_rejected(registry: Registry) -> None:
    specs = list(registry.specs)
    with pytest.raises(ValueError, match="duplicate"):
        Registry([*specs, specs[0]])
    with pytest.raises(ValueError, match="at least 50"):
        Registry(specs[:-1])
    with pytest.raises(ValueError, match="must be in team"):
        Registry(_replace(registry, "A11", team="market_context"))
    with pytest.raises(ValueError, match="Tier 0"):
        Registry(_replace(registry, "A47", tier=0))
    with pytest.raises(ValueError, match="state"):
        Registry(_replace(registry, "A11", state="proposed"))
    with pytest.raises(ValueError, match="core"):
        Registry(_replace(registry, "A49", core=False))


def test_class_loading_errors(registry: Registry) -> None:
    with pytest.raises(LookupError):
        registry.get("A21").load_class()
    not_a_class = registry.get("A11").model_copy(
        update={"implementation": "quantagents.config:LIVE_APPROVAL_ENV"}
    )
    with pytest.raises(TypeError):
        not_a_class.load_class()
    wrong = Registry(
        _replace(registry, "A11", implementation="quantagents.agents.a03_features:FeatureAgent")
    )
    with pytest.raises(TypeError, match="SignalAgent"):
        wrong.signal_agents(3)


def test_registry_path_lookup(
    repo_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("QUANTAGENTS_HOME", str(repo_root))
    assert default_registry_path() == repo_root / "config" / "agents.yaml"
    monkeypatch.setenv("QUANTAGENTS_HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    assert default_registry_path() == repo_root / "config" / "agents.yaml"
    assert len(Registry.load()) == 50
