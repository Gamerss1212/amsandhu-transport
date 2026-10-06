@echo off
rem Show the paper account, kill switch, last cycle and progress toward 30 paper days.
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Run setup.bat first.
    pause
    exit /b 2
)
if exist "config\my_universe.yaml" (
    ".venv\Scripts\python.exe" -m quantagents --config config\my_universe.yaml status --data data\prices.csv
) else (
    ".venv\Scripts\python.exe" -m quantagents status
)
pause
