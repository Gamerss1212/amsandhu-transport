@echo off
title JARVIS
cd /d "%~dp0jarvis"
echo.
echo  JARVIS: voice control for your Trading AI.
echo  Needs: Node.js 20+ (nodejs.org), Google Chrome or Edge, and Claude Code installed and logged in.
echo  Start START_TRADING_AI.exe FIRST.
echo.
where node >/dev/null 2>nul
if errorlevel 1 (
  echo  Node.js was not found. Install it from https://nodejs.org , then double-click this file again.
  pause
  exit /b 1
)
where claude >/dev/null 2>nul
if errorlevel 1 (
  echo  Claude Code was not found. Install it: npm install -g @anthropic-ai/claude-code , run "claude" once and log in.
  pause
  exit /b 1
)
if not exist node_modules (
  echo  First run: installing JARVIS ^(a few minutes, needs the internet^)...
  call npm install --no-audit --no-fund
  if errorlevel 1 ( echo  The install failed. & pause & exit /b 1 )
)
rem Actions that change your computer wait for Allow on his screen; he may edit his own folder (backed up first).
set JARVIS_ASK_FIRST=1
set JARVIS_SELF_EDIT=1
echo  JARVIS opens in his own window and starts by himself. Allow the microphone the first time.
echo  Then just talk: "Hey Jarvis, open the trading system."
start "" /min "%CD%\open_face.cmd"
:run
call npm start
if exist restart.flag (
  del restart.flag
  echo  Restarting JARVIS with his changes...
  goto run
)
pause
