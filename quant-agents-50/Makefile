# Shortcuts for macOS/Linux. On Windows, run the python commands directly.
PY ?= python3

.PHONY: install check fast test demo agents validate clean

install:
	$(PY) -m pip install -e ".[dev]"

check:
	$(PY) scripts/check.py

fast:
	$(PY) scripts/check.py --fast

test:
	$(PY) -m pytest -q

demo:
	$(PY) -m quantagents demo

agents:
	$(PY) -m quantagents agents

validate:
	$(PY) -m quantagents validate --strategy tsmom

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache .coverage htmlcov build dist src/*.egg-info
