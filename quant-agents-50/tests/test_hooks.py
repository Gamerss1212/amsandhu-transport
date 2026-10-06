"""The Claude Code hooks in .claude/hooks must block secrets and human-only changes."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
GUARD = ROOT / ".claude" / "hooks" / "guard_files.py"
FORMAT = ROOT / ".claude" / "hooks" / "format_python.py"

# Built by concatenation so this file never contains a real-looking secret itself.
FAKE_ANTHROPIC = "sk-" + "ant-" + "A1b2C3d4E5f6G7h8"
FAKE_AWS = "AKIA" + "ABCDEFGHIJKLMNOP"
FAKE_KEY = "-----BEGIN " + "PRIVATE KEY-----"
TOKEN_LINE = "QUANTAGENTS_LIVE_APPROVED" + "=" + "I_ACCEPT_REAL_MONEY_RISK"


def run_hook(script: Path, payload: Any) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(script)],
        input=payload if isinstance(payload, str) else json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def write(path: str, content: str) -> dict[str, Any]:
    return {"tool_name": "Write", "tool_input": {"file_path": path, "content": content}}


@pytest.mark.parametrize(
    "payload",
    [
        write(".env", "X=1"),
        write("config/.env.local", "X=1"),
        write("secrets/broker.json", "{}"),
        write(".git/config", ""),
        write("keys/api.pem", ""),
        write("src/x.py", f'KEY = "{FAKE_ANTHROPIC}"'),
        write("src/x.py", f"aws = '{FAKE_AWS}'"),
        write("notes.txt", FAKE_KEY),
        write("src/x.py", 'password = "hunter2hunter2"'),
        write("scripts/run.sh", f"export {TOKEN_LINE}"),
        write("config/default.yaml", "system:\n  execution_mode: live\n"),
        write("config/default.yaml", "system:\n  autonomy_level: 3\n"),
        write("config/default.yaml", "system:\n  live_trading_approved: true\n"),
        {
            "tool_name": "Edit",
            "tool_input": {
                "file_path": "src/x.py",
                "old_string": "a",
                "new_string": f'api_key = "{FAKE_ANTHROPIC}"',
            },
        },
        {
            "tool_name": "MultiEdit",
            "tool_input": {
                "file_path": "src/x.py",
                "edits": [{"old_string": "a", "new_string": f"k = '{FAKE_AWS}'"}],
            },
        },
    ],
)
def test_guard_blocks(payload: dict[str, Any]) -> None:
    result = run_hook(GUARD, payload)
    assert result.returncode == 2, result.stderr
    assert "Blocked" in result.stderr


@pytest.mark.parametrize(
    "payload",
    [
        write(".env.example", "BROKER_API_KEY=\n"),
        write("src/quantagents/agents/a13_structure.py", "x = 1\n"),
        write("config/default.yaml", "system:\n  autonomy_level: 1\n  execution_mode: paper\n"),
        write("docs/notes.md", "autonomy_level: 3 needs the owner"),
        write("src/x.py", 'password = os.environ["BROKER_PASSWORD"]'),
        {"tool_name": "Write"},
        {"tool_name": "Write", "tool_input": "oops"},
        [],
    ],
)
def test_guard_allows(payload: Any) -> None:
    assert run_hook(GUARD, payload).returncode == 0


def test_guard_ignores_garbage() -> None:
    assert run_hook(GUARD, "not json").returncode == 0


def test_format_hook(tmp_path: Path) -> None:
    messy = tmp_path / "messy.py"
    messy.write_text("x=1\nimport os\n", encoding="utf-8")
    result = run_hook(FORMAT, write(str(messy), ""))
    assert result.returncode == 0, result.stderr
    assert messy.read_text(encoding="utf-8") == "x = 1\n"
    broken = tmp_path / "broken.py"
    broken.write_text("def f():\n    return undefined_name\n", encoding="utf-8")
    result = run_hook(FORMAT, write(str(broken), ""))
    assert result.returncode == 2 and "undefined_name" in result.stderr
    assert run_hook(FORMAT, write(str(tmp_path / "notes.md"), "")).returncode == 0
    assert run_hook(FORMAT, "not json").returncode == 0
