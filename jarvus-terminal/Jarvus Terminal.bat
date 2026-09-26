@echo off
REM Double-click launcher for Windows.
REM Finds whichever Python is installed, starts the terminal, and keeps this
REM window open if something goes wrong so the error is readable.
title Jarvus Terminal
cd /d "%~dp0"

REM Ask each candidate for its version rather than just looking it up, because
REM on a machine without Python "python" is a Microsoft Store stub that exists
REM but does not run.
set PY=
py -3 --version >nul 2>&1
if not errorlevel 1 set "PY=py -3"
if not defined PY (
  python --version >nul 2>&1
  if not errorlevel 1 set "PY=python"
)
if not defined PY (
  python3 --version >nul 2>&1
  if not errorlevel 1 set "PY=python3"
)

if not defined PY (
  echo.
  echo   Python was not found on this computer.
  echo.
  echo   Install it from https://www.python.org/downloads/
  echo   On the first screen of the installer, tick "Add Python to PATH".
  echo   Then close this window and double-click this file again.
  echo.
  pause
  exit /b 1
)

echo.
echo   Starting Jarvus Terminal with %PY% ...
echo   Your browser will open at http://127.0.0.1:8787
echo   Close this window to stop it.
echo.

%PY% run.py
if errorlevel 1 (
  echo.
  echo   Jarvus stopped with an error. The message above says why.
  echo.
  pause
)
