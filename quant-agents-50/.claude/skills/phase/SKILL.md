---
name: phase
description: Use when the owner asks to start, continue or finish a QuantAgents-50 build phase (0-9), or types /phase with a number.
argument-hint: "[phase number 0-9]"
disable-model-invocation: true
---

# Build phase $0

Every session on this phase ends with three things: working code, all gates green, and an updated `docs/STATUS.md`.

## Steps

1. Read `docs/STATUS.md` and `docs/phases/phase-$0.md`.
   If an earlier phase is not marked **accepted** in STATUS, stop and name it.
2. Read only the spec sections the phase file lists. Find one with `grep -n "^### 48\." docs/SPEC.md`, then read that range.
3. Run `python scripts/check.py --fast`. If anything is already broken, report it before changing code.
4. Write a short plan: tasks in order, files to touch, tests to add, and anything the owner must do. Wait for "go".
5. For each task: write the test, write the code, run `python scripts/check.py --fast`, commit when green.
6. After changes to risk, execution or sizing code, ask the `risk-reviewer` subagent. For any strategy or signal, ask the `red-team` subagent.
7. When the tasks are done, run `/verify`, then ask the `spec-checker` subagent to check every acceptance criterion.
8. Update `docs/STATUS.md`: what was built, test count, open issues, next step.
   Mark the phase **accepted** only if every acceptance criterion passed. Otherwise list the ones that did not.

## Stop and ask the owner when

- a task needs money, an account, an API key or a paid data source
- a risk limit, the autonomy level or the execution mode would change
- the phase file and the spec disagree
- a criterion cannot be met with the data available
