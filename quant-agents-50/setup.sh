#!/usr/bin/env bash
# QuantAgents-50 one-time setup for macOS and Linux: bash setup.sh
set -euo pipefail
cd "$(dirname "$0")"
PY=${PYTHON:-python3}
[ -x .venv/bin/python ] || "$PY" -m venv .venv
.venv/bin/python -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" || {
  echo "This Python is too old: QuantAgents needs 3.11 or newer. Install a newer one, delete .venv, run again."
  exit 1
}
.venv/bin/python -m pip install --upgrade pip
EXTRAS=data
[ -d tests ] && EXTRAS=dev,data   # the developer copy also gets the test tools
.venv/bin/python -m pip install -e ".[$EXTRAS]"
[ -f config/my_universe.yaml ] || cp config/us_etfs.example.yaml config/my_universe.yaml
.venv/bin/python -m quantagents --config config/my_universe.yaml doctor
[ -d tests ] && .venv/bin/python scripts/check.py
.venv/bin/python -m quantagents demo
echo
echo "Setup finished. Next: bash QuantAgents.sh: it opens in your web browser (see START_HERE.md)"
