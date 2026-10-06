@echo off
rem QuantAgents-50 one-time setup for Windows: double-click this file.
rem Creates a private Python environment in .venv, installs everything, checks it, runs a demo.
cd /d "%~dp0"
echo.
echo === QuantAgents-50 setup (paper trading only) ===
echo.
if exist ".venv\Scripts\python.exe" goto have_venv
where py >nul 2>nul
if %errorlevel%==0 (
    py -3 -m venv .venv
) else (
    python -m venv .venv
)
if not exist ".venv\Scripts\python.exe" (
    echo Could not create the Python environment.
    echo Install Python 3.11 or newer from python.org and tick "Add python.exe to PATH".
    goto fail
)
:have_venv
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -e ".[dev,data]"
if errorlevel 1 goto fail
echo.
echo === Checking the install ===
".venv\Scripts\python.exe" -m quantagents doctor
if errorlevel 1 goto fail
echo.
echo === Running every quality gate (takes about a minute) ===
".venv\Scripts\python.exe" scripts\check.py
if errorlevel 1 goto fail
echo.
echo === Demo: one decision cycle on synthetic data ===
".venv\Scripts\python.exe" -m quantagents demo
if not exist "config\my_universe.yaml" copy "config\us_etfs.example.yaml" "config\my_universe.yaml" >nul
echo.
echo Setup finished. Next: edit config\my_universe.yaml if you want other symbols,
echo then double-click daily.bat once. See START_HERE.md.
pause
exit /b 0
:fail
echo.
echo Setup stopped because a step failed. Read the messages above.
pause
exit /b 1
