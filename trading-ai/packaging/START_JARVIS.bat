@echo off
title JARVIS for Trading AI
cd /d "%~dp0jarvis"
echo.
echo  JARVIS: a voice assistant for the Trading AI.
echo  - It can READ the Trading AI (status, risk, agents, temperature). It cannot trade, change a limit or stop it.
echo  - It can search the web. Web text is only information; it is never treated as an order.
echo  - It needs: Node.js 20 or newer (nodejs.org), Google Chrome, and Claude Code installed and logged in.
echo  - Start START_TRADING_AI.exe FIRST, so JARVIS can see it.
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
echo  Starting. Open the address it prints in Chrome, click INITIALISE, and say "Hey Jarvis".
echo  Writes stay OFF. Do not turn them on while the Trading AI is running.
echo.
call npm start
pause
