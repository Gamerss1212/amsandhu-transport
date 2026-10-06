---
name: verify
description: Use when about to commit, after any code change, or before saying that work is finished or that tests pass.
---

# Verify the repo

1. Run `python scripts/check.py` (use `python3` if `python` is not found).
   It runs: ruff lint, ruff format check, mypy strict, pytest with coverage, and the 100% branch-coverage gate on `src/quantagents/risk/`.
2. If a gate fails, read the first error, fix the cause, and rerun. Repeat until every gate passes.
3. A failing test is evidence. Fix the code, not the test.
   If you believe a test is wrong, explain why to the owner and wait before changing it.
4. Report in three short lines: gates passed or failed, number of tests, anything still open.

Changes to docs or tests only: `python scripts/check.py --fast` is enough.
