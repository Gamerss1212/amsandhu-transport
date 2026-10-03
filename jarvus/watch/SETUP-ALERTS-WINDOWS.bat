@echo off
title Jarvus alerts setup
cd /d "%~dp0scripts"
python watch.py setup
echo.
echo Subscribe to that topic in the ntfy phone app, then press a key to send a test alert.
pause
python watch.py test
pause
