"""The Claude Code setup must stay valid: settings, hooks, skills, subagents, rules, phases."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
CLAUDE = ROOT / ".claude"


def frontmatter(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n"), f"{path} has no frontmatter"
    data = yaml.safe_load(text.split("---\n", 2)[1])
    assert isinstance(data, dict)
    return data


def test_claude_md_is_short_and_loads_status() -> None:
    lines = (ROOT / "CLAUDE.md").read_text(encoding="utf-8").splitlines()
    assert len(lines) < 200  # Claude Code guidance: keep CLAUDE.md under 200 lines
    assert "@docs/STATUS.md" in lines
    assert (ROOT / "docs" / "STATUS.md").exists()


def test_settings_hooks_and_permissions() -> None:
    settings = json.loads((CLAUDE / "settings.json").read_text(encoding="utf-8"))
    deny = settings["permissions"]["deny"]
    assert "Read(/.env)" in deny and "Bash(curl *)" in deny
    ask = settings["permissions"]["ask"]
    assert "Edit(/src/quantagents/risk/**)" in ask and "Edit(/config/default.yaml)" in ask
    for event in ("PreToolUse", "PostToolUse"):
        for group in settings["hooks"][event]:
            assert group["matcher"] == "Edit|Write"
            for hook in group["hooks"]:
                script = hook["args"][0].replace("${CLAUDE_PROJECT_DIR}", str(ROOT))
                assert Path(script).exists(), script


@pytest.mark.parametrize("skill", ["phase", "verify", "new-agent", "validate-strategy"])
def test_skills_have_trigger_descriptions(skill: str) -> None:
    meta = frontmatter(CLAUDE / "skills" / skill / "SKILL.md")
    assert meta["name"] == skill
    assert str(meta["description"]).startswith("Use when")
    assert len(str(meta["description"])) < 300


def test_phase_skill_is_owner_only_and_verify_is_automatic() -> None:
    assert frontmatter(CLAUDE / "skills" / "phase" / "SKILL.md")["disable-model-invocation"] is True
    assert "disable-model-invocation" not in frontmatter(CLAUDE / "skills" / "verify" / "SKILL.md")


@pytest.mark.parametrize("agent", ["risk-reviewer", "red-team", "spec-checker", "test-writer"])
def test_subagents_are_well_formed(agent: str) -> None:
    meta = frontmatter(CLAUDE / "agents" / f"{agent}.md")
    assert meta["name"] == agent and meta["description"] and meta["model"] == "inherit"
    if agent != "test-writer":
        assert "Edit" not in meta["tools"] and "Write" not in meta["tools"]  # reviewers never edit


def test_rules_point_at_real_files() -> None:
    rules = sorted((CLAUDE / "rules").glob("*.md"))
    assert {r.stem for r in rules} == {"agents", "research", "risk"}
    for rule in rules:
        for pattern in frontmatter(rule)["paths"]:
            assert list(ROOT.glob(pattern)), f"{rule.name}: {pattern} matches nothing"


def test_every_phase_has_a_prompt_with_acceptance_criteria() -> None:
    for n in range(10):
        text = (ROOT / "docs" / "phases" / f"phase-{n}.md").read_text(encoding="utf-8")
        assert text.startswith(f"# Phase {n}:")
        assert "## Acceptance" in text and "- [ ]" in text
    assert "Approve Phase 8" in (ROOT / "docs" / "phases" / "phase-8.md").read_text(
        encoding="utf-8"
    )


def test_secrets_and_state_are_ignored() -> None:
    ignored = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert {".env", "/state/", "/runs/", "secrets/", "!.env.example"} <= set(ignored)
    assert "data/" not in ignored  # would hide src/quantagents/data
