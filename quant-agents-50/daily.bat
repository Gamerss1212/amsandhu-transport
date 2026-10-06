@echo off
rem One paper-trading day: download data, run one cycle, then the watchdog.
rem Point Windows Task Scheduler at this file (weekdays, after the US close). See docs\schedule.md.
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Run setup.bat first.
    exit /b 2
)
if not exist "config\my_universe.yaml" copy "config\us_etfs.example.yaml" "config\my_universe.yaml" >nul
".venv\Scripts\python.exe" -m quantagents --config config\my_universe.yaml daily
exit /b %errorlevel%
