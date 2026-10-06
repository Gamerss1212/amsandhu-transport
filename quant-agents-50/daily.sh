#!/usr/bin/env bash
# One paper-trading day: download data, run one cycle, then the watchdog (for cron).
set -euo pipefail
cd "$(dirname "$0")"
[ -x .venv/bin/python ] || { echo "Run setup.sh first."; exit 2; }
[ -f config/my_universe.yaml ] || cp config/us_etfs.example.yaml config/my_universe.yaml
exec .venv/bin/python -m quantagents --config config/my_universe.yaml daily
