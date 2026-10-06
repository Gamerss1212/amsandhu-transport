"""Agent registry: loads and validates config/agents.yaml (spec sections 9, 10, 17, 22)."""

from __future__ import annotations

import importlib
import os
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

from quantagents.agents.base import SignalAgent
from quantagents.schemas import AGENT_ID_PATTERN, team_of

TEAM_SLUGS: tuple[str, ...] = (
    "data_integrity",
    "market_context",
    "trend_momentum",
    "mean_reversion_relative_value",
    "carry_factors_events",
    "information_positioning",
    "ml_evaluation_lab",
    "adversarial_review_board",
    "research_validation_lab",
    "command_risk_execution",
)
RUNNING_STATES = frozenset({"shadow", "probation", "active", "watchlist"})
VOTING_STATES = frozenset({"probation", "active", "watchlist"})  # shadow: scored, weight 0
SIGNAL_RANGE = range(11, 34)  # A11-A33 seal predictions every cycle

State = Literal["proposed", "sandbox", "shadow", "probation", "active", "watchlist", "retired"]


class AgentSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(pattern=AGENT_ID_PATTERN)
    name: str
    team: str
    kind: Literal["code", "stat", "ml", "llm", "mixed"]
    llm: bool
    cadence: str
    info_subset: tuple[str, ...]
    output: str
    tier: int = Field(ge=0, le=4)
    state: State
    weight_cap: float = Field(gt=0, le=1)
    phase: int = Field(ge=1, le=7)
    core: bool = False  # part of the 25-agent core built in full by this kit
    implementation: str | None

    @property
    def number(self) -> int:
        return int(self.id[1:])

    @property
    def team_number(self) -> int:
        return team_of(self.id)

    @property
    def is_signal(self) -> bool:
        return self.number in SIGNAL_RANGE

    def load_class(self) -> type:
        if self.implementation is None:
            raise LookupError(f"{self.id} is not built yet")
        module_name, _, class_name = self.implementation.partition(":")
        cls = getattr(importlib.import_module(module_name), class_name)
        if not isinstance(cls, type):
            raise TypeError(f"{self.implementation} is not a class")
        return cls


def default_registry_path() -> Path:
    """config/agents.yaml: $QUANTAGENTS_HOME, then the current folder, then the repo checkout."""
    candidates = []
    home = os.environ.get("QUANTAGENTS_HOME")
    if home:
        candidates.append(Path(home) / "config" / "agents.yaml")
    candidates.append(Path.cwd() / "config" / "agents.yaml")
    candidates.append(Path(__file__).resolve().parents[2] / "config" / "agents.yaml")
    for path in candidates:
        if path.exists():
            return path
    raise FileNotFoundError(
        "config/agents.yaml not found; run from the repo root or set QUANTAGENTS_HOME"
    )


class Registry:
    def __init__(self, specs: Sequence[AgentSpec]) -> None:
        self.specs: tuple[AgentSpec, ...] = tuple(sorted(specs, key=lambda s: s.number))
        self._by_id = {s.id: s for s in self.specs}
        self._validate()

    @classmethod
    def load(cls, path: Path | None = None) -> Registry:
        raw = yaml.safe_load((path or default_registry_path()).read_text(encoding="utf-8"))
        return cls([AgentSpec.model_validate(item) for item in raw["agents"]])

    def _validate(self) -> None:
        ids = [s.id for s in self.specs]
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate agent ids")
        if len(ids) < 50:
            raise ValueError(f"the registry must hold at least 50 agents, found {len(ids)}")
        for spec in self.specs:
            if spec.number <= 50 and spec.team != TEAM_SLUGS[spec.team_number - 1]:
                raise ValueError(f"{spec.id} must be in team {TEAM_SLUGS[spec.team_number - 1]}")
            if (spec.implementation is None) != (spec.state == "proposed"):
                raise ValueError(
                    f"{spec.id}: built agents need a state other than proposed, and vice versa"
                )
        sizes = Counter(s.team for s in self.specs if s.number <= 50)
        if any(n != 5 for n in sizes.values()):
            raise ValueError(f"every team needs exactly 5 agents: {dict(sizes)}")
        tier0 = [s.id for s in self.specs if s.tier == 0]
        if tier0 != ["A49"]:
            raise ValueError(f"only A49 may hold Tier 0 authority, found {tier0}")
        if not self._by_id["A49"].core:
            raise ValueError("A49, the risk governor, must be in the core")

    def __len__(self) -> int:
        return len(self.specs)

    def get(self, agent_id: str) -> AgentSpec:
        return self._by_id[agent_id]

    def team(self, slug: str) -> list[AgentSpec]:
        return [s for s in self.specs if s.team == slug]

    def scheduled(self, phase: int) -> list[AgentSpec]:
        """Agents the roadmap switches on by this phase (built or not)."""
        return [s for s in self.specs if s.phase <= phase]

    def active(self, phase: int) -> list[AgentSpec]:
        """Agents that are scheduled, built and in a running lifecycle state."""
        return [
            s
            for s in self.scheduled(phase)
            if s.implementation is not None and s.state in RUNNING_STATES
        ]

    def missing(self, phase: int) -> list[AgentSpec]:
        """Core agents the roadmap expects by this phase that are not built yet."""
        return [s for s in self.scheduled(phase) if s.core and s.implementation is None]

    def core(self) -> list[AgentSpec]:
        """The 25-agent core this kit builds in full."""
        return [s for s in self.specs if s.core]

    def parked(self) -> list[AgentSpec]:
        """Roster agents outside the core that are not built: optional, for later."""
        return [s for s in self.specs if not s.core and s.implementation is None]

    def cumulative_counts(self) -> dict[int, int]:
        return {p: len(self.scheduled(p)) for p in range(1, 8)}

    def signal_agents(self, phase: int) -> list[SignalAgent]:
        agents: list[SignalAgent] = []
        for spec in self.active(phase):
            if not spec.is_signal:
                continue
            instance = spec.load_class()()
            if not isinstance(instance, SignalAgent) or instance.agent_id != spec.id:
                raise TypeError(f"{spec.implementation} is not the SignalAgent for {spec.id}")
            agents.append(instance)
        return agents
