#!/usr/bin/env bash
# Show the paper account, kill switch, last cycle and progress toward 30 paper days.
set -euo pipefail
cd "$(dirname "$0")"
[ -x .venv/bin/python ] || { echo "Run setup.sh first."; exit 2; }
if [ -f config/my_universe.yaml ]; then
  exec .venv/bin/python -m quantagents --config config/my_universe.yaml status --data data/prices.csv
fi
exec .venv/bin/python -m quantagents status
