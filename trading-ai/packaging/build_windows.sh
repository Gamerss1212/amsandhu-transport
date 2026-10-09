#!/usr/bin/env bash
# Builds the Windows release folder TradingAI/ (START_TRADING_AI.exe + _internal/) and a zip.
#
# On Linux it runs PyInstaller with a Windows Python under Wine (WINEPREFIX with C:\PyTA holding the pinned
# requirements and PyInstaller). On Windows, run the same steps natively:
#   cd frontend && npm ci && npm run build
#   python -m PyInstaller packaging\trading_ai.spec --noconfirm --distpath release --workpath build
#
# Steps: tests -> dashboard build -> strategy-library cache check -> PyInstaller -> docs -> self-test of the built exe
# under Wine (it starts the real server and drives it over HTTP and WebSocket) -> zip.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
OUT="${1:-$ROOT/release}"
export WINEPREFIX="${WINEPREFIX:-/root/.wine64}" WINEDEBUG=-all
PY="C:\\PyTA\\python.exe"
winpath() { echo "Z:${1//\//\\}"; }
# `yes` answers any console prompt and is ended by SIGPIPE, so the pipe status is ignored here; callers check results.
wine_run() { ( set +o pipefail; yes "" | wine "$@" 2>&1 | tr -d '\r' ); }

echo "== 1/6 backend tests"
( cd "$ROOT/backend" && "$ROOT/.venv/bin/python" -m pytest -q tests )

echo "== 2/6 dashboard"
( cd "$ROOT/frontend" && npm ci --no-audit --no-fund >/dev/null && npm run build )

echo "== 3/6 strategy-library cache is current"
( cd "$ROOT/backend" && "$ROOT/.venv/bin/python" -c "
from tradingai.strategies import library as L
import json
fp = L._fingerprint(); d = json.loads(L.CACHE_FILE.read_text())
assert d['fingerprint'] == fp, 'cache stale: run python -c \"from tradingai.strategies.library import build; build()\"'
print('cache ok', fp, len(d['kept']), 'templates')" )

echo "== 4/6 PyInstaller (Windows Python under Wine)"
WORK="$WINEPREFIX/drive_c/tabuild"
rm -rf "$WORK" "$OUT"
mkdir -p "$WORK" "$OUT"
wine_run "$PY" -m PyInstaller "$(winpath "$HERE/trading_ai.spec")" --noconfirm --clean \
  --distpath 'C:\tabuild\dist' --workpath 'C:\tabuild\work' | grep -E "INFO: Build complete|ERROR|Traceback|WARNING: Hidden import" || true
test -f "$WORK/dist/TradingAI/START_TRADING_AI.exe" || { echo "build failed"; exit 1; }
cp -r "$WORK/dist/TradingAI" "$OUT/TradingAI"

echo "== 5/6 documents"
cp "$ROOT/docs/START_HERE.txt" "$OUT/TradingAI/START_HERE.txt"
cp "$ROOT/docs/REQUIREMENTS_MATRIX.md" "$OUT/TradingAI/REQUIREMENTS_MATRIX.md"
cp "$ROOT/docs/CATALOG_BACKTEST_REPORT.md" "$OUT/TradingAI/CATALOG_BACKTEST_REPORT.md"
cp "$ROOT/README.md" "$OUT/TradingAI/README.md"

echo "== 6/6 self-test of the built exe (fresh data folder, offline: no network needed)"
ST="$WINEPREFIX/drive_c/tatest"
rm -rf "$ST" && mkdir -p "$ST"
cp -r "$OUT/TradingAI" "$ST/TradingAI"
wine_run 'C:\tatest\TradingAI\START_TRADING_AI.exe' --selftest --offline --home 'C:\tatest\home' \
  | grep -v '^{"ts"' | tee "$OUT/selftest.log" | tail -60
grep -q '"passed": true' "$OUT/selftest.log" || { echo "SELF-TEST FAILED"; exit 1; }

( cd "$OUT" && rm -f TradingAI.zip && zip -qr TradingAI.zip TradingAI )
echo "built: $OUT/TradingAI.zip ($(du -h "$OUT/TradingAI.zip" | cut -f1))"
