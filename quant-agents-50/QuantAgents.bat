@echo off
rem QuantAgents-50: double-click this file. That is all you need to do.
rem The first time, it installs everything (about 5 minutes, needs the internet). Then it
rem opens QuantAgents in your web browser. Keep the black window open while you use it.
cd /d "%~dp0"
title QuantAgents-50
if not exist ".venv\Scripts\python.exe" goto install
".venv\Scripts\python.exe" -c "import quantagents" >nul 2>nul
if %errorlevel% neq 0 goto install
goto ready
:install
echo First run: installing QuantAgents. This takes about 5 minutes and needs the internet.
echo.
call setup.bat nopause
if %errorlevel% neq 0 goto fail
:ready
if not exist "config\my_universe.yaml" copy "config\us_etfs.example.yaml" "config\my_universe.yaml" >nul
echo Opening QuantAgents in your web browser...
".venv\Scripts\python.exe" -m quantagents --config config\my_universe.yaml app
exit /b %errorlevel%
:fail
echo.
echo The install did not finish. Read the messages above, fix the problem
echo (usually: install Python 3.11+ from python.org with "Add python.exe to PATH"),
echo then double-click QuantAgents.bat again.
pause
exit /b 1
