# Phase 0: Setup on one PC

**Goal:** the project runs on the owner's PC with every quality gate green, plus git and CI.
**Spec sections to read:** 1, 2, 3, 71, 72, 73, 83.

## Already in the kit

- Code, tests, config, Claude Code settings, hooks, skills, subagents and rules.

## Owner does (Claude explains each step)

1. Install Python 3.11 or newer from python.org. On Windows, tick "Add python.exe to PATH".
2. Install Git. On Windows, Git for Windows also gives Claude Code its Bash tool.
3. Install Claude Code (see README).
4. Create a GitHub account and an empty **private** repository.

## Claude does

1. Check versions: `python --version` (3.11+) and `git --version`.
   On Windows, if `python3` is not found, ask the owner to approve changing `"command": "python3"` to `"python"` in `.claude/settings.json`.
2. Create a virtual environment: `python -m venv .venv`, then activate it
   (Windows: `.venv\Scripts\activate`; macOS/Linux: `source .venv/bin/activate`).
3. Install: `python -m pip install -e ".[dev]"`.
4. Run `/verify`. Every gate must pass on this PC.
5. Run `python -m quantagents demo` and explain each of the 15 steps to the owner in plain words.
6. `git init` if needed, make the first commit, add the GitHub remote and push (the owner signs in).
7. Confirm the CI run on GitHub passes.
8. Confirm secrets stay out of git: `git check-ignore .env` prints `.env`, and `git ls-files` shows no `.env`, keys or `state/`.
9. Update `docs/STATUS.md`.

## Acceptance (spec section 83)

- [ ] `python scripts/check.py` passes on the owner's PC
- [ ] CI is green on GitHub
- [ ] No secrets in git; `.env` is ignored
- [ ] The owner has seen the demo and can say what the 15 steps do
