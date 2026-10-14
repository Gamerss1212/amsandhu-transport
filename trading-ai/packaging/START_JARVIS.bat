@echo off
title JARVIS
cd /d "%~dp0jarvis"
echo.
echo  JARVIS: voice control for your Trading AI.
echo  Needs: Node.js 20+ (nodejs.org), Google Chrome or Edge, and Claude Code installed and logged in.
echo  Start START_TRADING_AI.exe FIRST.
echo.
where node >nul 2>nul
if errorlevel 1 (
  echo  Node.js was not found. Install it from https://nodejs.org , then double-click this file again.
  pause
  exit /b 1
)
where claude >nul 2>nul
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
echo  JARVIS opens in its own window and starts by himself. Allow the microphone the first time.
echo  Then just talk: "Hey Jarvis, open the trading system."
start "" /min "%CD%\open_face.cmd"
call npm start
pause
