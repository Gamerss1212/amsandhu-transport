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
rem Used by the Windows CI check: stop here once Node and Claude Code have been found.
if "%JARVIS_CHECK_ONLY%"=="1" (
  echo  Checks passed: Node.js and Claude Code found.
  exit /b 0
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
echo  Then press the TALK button ^(or Space^) once and just talk to him, about anything. He keeps listening after
echo  every answer. Say "goodbye" or press the button again to end.
start "" /min "%CD%\open_face.cmd"
:run
call npm start
if exist restart.flag (
  del restart.flag
  echo  Restarting JARVIS with his changes...
  goto run
)
pause
