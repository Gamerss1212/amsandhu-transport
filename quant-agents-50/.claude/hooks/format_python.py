#!/usr/bin/env python3
"""Claude Code PostToolUse hook for Edit, Write and MultiEdit on Python files.

Formats the file with ruff, applies safe lint fixes, and reports anything left over to
Claude (exit code 2) so it is fixed right away instead of at commit time.
Does nothing if ruff is not installed.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return 0
    tool_input = payload.get("tool_input") if isinstance(payload, dict) else None
    file_path = str(tool_input.get("file_path", "")) if isinstance(tool_input, dict) else ""
    if not file_path.endswith(".py") or not Path(file_path).exists():
        return 0
    ruff = [sys.executable, "-m", "ruff"]
    try:
        subprocess.run(
            [*ruff, "format", "--quiet", file_path], check=False, capture_output=True, timeout=60
        )
        result = subprocess.run(
            [*ruff, "check", "--fix", "--quiet", file_path],
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired):
        return 0
    if "No module named ruff" in result.stderr:
        return 0
    if result.returncode != 0:
        print(
            f"ruff found problems in {file_path}:\n{result.stdout}{result.stderr}", file=sys.stderr
        )
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
