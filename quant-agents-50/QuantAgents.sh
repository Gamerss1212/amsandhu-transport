#!/usr/bin/env bash
# QuantAgents-50 for macOS and Linux: bash QuantAgents.sh
# The first time, it installs everything (about 5 minutes, needs the internet). Then it opens
# QuantAgents in your web browser. Keep the terminal open while you use it.
set -euo pipefail
cd "$(dirname "$0")"
if ! { [ -x .venv/bin/python ] && .venv/bin/python -c "import quantagents" 2>/dev/null; }; then
  echo "First run: installing QuantAgents. This takes about 5 minutes and needs the internet."
  bash setup.sh
fi
[ -f config/my_universe.yaml ] || cp config/us_etfs.example.yaml config/my_universe.yaml
echo "Opening QuantAgents in your web browser..."
exec .venv/bin/python -m quantagents --config config/my_universe.yaml app
