#!/usr/bin/env bash
# QuantAgents-50 one-time setup for macOS and Linux: bash setup.sh
set -euo pipefail
cd "$(dirname "$0")"
PY=${PYTHON:-python3}
[ -x .venv/bin/python ] || "$PY" -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e ".[dev,data]"
.venv/bin/python -m quantagents doctor
.venv/bin/python scripts/check.py
.venv/bin/python -m quantagents demo
[ -f config/my_universe.yaml ] || cp config/us_etfs.example.yaml config/my_universe.yaml
echo
echo "Setup finished. Next: edit config/my_universe.yaml, then run: bash daily.sh  (see START_HERE.md)"
