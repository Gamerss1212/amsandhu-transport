#!/usr/bin/env python3
"""Run every quality gate in order and stop at the first failure.

    python scripts/check.py          # lint, format check, types, tests, risk coverage
    python scripts/check.py --fast   # skip the slower test run (lint, format, types only)

Uses the current Python interpreter, so it works the same on Windows, macOS and Linux.
"""

from __future__ import annotations

import subprocess
import sys

GATES: list[tuple[str, list[str]]] = [
    ("lint", ["ruff", "check", "."]),
    ("format", ["ruff", "format", "--check", "."]),
    ("types", ["mypy"]),
    ("tests", ["pytest", "--cov=quantagents", "--cov-report=term-missing:skip-covered"]),
    (
        "risk coverage (Phase 3 gate: 100% of src/quantagents/risk)",
        [
            "coverage",
            "report",
            "--include=*/quantagents/risk/*",
            "--fail-under=100",
            "--show-missing",
        ],
    ),
]


def main(argv: list[str]) -> int:
    fast = "--fast" in argv
    for name, command in GATES:
        if fast and name.startswith(("tests", "risk")):
            continue
        print(f"\n=== {name}: python -m {' '.join(command)}", flush=True)
        code = subprocess.call([sys.executable, "-m", *command])
        if code != 0:
            print(f"\nFAILED: {name}. Fix this before committing.", flush=True)
            return code
    print("\nAll gates passed.", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
