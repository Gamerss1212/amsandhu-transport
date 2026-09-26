#!/bin/bash
# Double-click launcher for macOS.
# Double-clicking starts in the home folder, so step into this file's folder first.
cd "$(dirname "$0")" || exit 1

PY=""
command -v python3 >/dev/null 2>&1 && PY=python3
[ -z "$PY" ] && command -v python >/dev/null 2>&1 && PY=python

if [ -z "$PY" ]; then
  echo
  echo "  Python was not found on this Mac."
  echo
  echo "  Install it from https://www.python.org/downloads/"
  echo "  then close this window and double-click this file again."
  echo
  read -r -p "  Press return to close." _
  exit 1
fi

echo
echo "  Starting Jarvus Terminal with $PY ..."
echo "  Your browser will open at http://127.0.0.1:8787"
echo "  Press Control-C, or close this window, to stop it."
echo
"$PY" run.py || {
  echo
  echo "  Jarvus stopped with an error. The message above says why."
  read -r -p "  Press return to close." _
}
