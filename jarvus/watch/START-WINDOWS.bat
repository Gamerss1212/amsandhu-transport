@echo off
title Jarvus watcher
cd /d "%~dp0scripts"
where python >nul 2>nul
if errorlevel 1 (
  echo Python is not installed. Get it from https://www.python.org/downloads/ and tick "Add python.exe to PATH" in the installer, then double-click this file again.
  pause
  exit /b 1
)
python watch.py run
pause
