#!/bin/bash
# Launcher for Linux.
cd "$(dirname "$0")" || exit 1
PY=""
command -v python3 >/dev/null 2>&1 && PY=python3
[ -z "$PY" ] && command -v python >/dev/null 2>&1 && PY=python
if [ -z "$PY" ]; then
  echo "Python 3 was not found. Install it with your package manager, e.g. apt install python3"
  exit 1
fi
exec "$PY" run.py "$@"
