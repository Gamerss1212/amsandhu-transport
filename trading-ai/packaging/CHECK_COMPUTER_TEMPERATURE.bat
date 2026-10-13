@echo off
title Trading AI - computer temperature check
cd /d "%~dp0"
echo.
echo  TRADING AI - COMPUTER TEMPERATURE CHECK
echo  ========================================
echo  This runs every CPU core at full load for 5 minutes (1 minute idle before,
echo  1 minute to cool down after) and watches the temperature and whether
echo  Windows has to slow the CPU down to cool it.
echo.
echo  It stops by itself at 95 C. Press Ctrl+C at any time to stop it.
echo  Close games and other heavy programs first. Laptops: plug in the charger.
echo.
pause
"%~dp0START_TRADING_AI.exe" --thermal-check --minutes 5
echo.
echo  The report was saved in the thermal-reports folder next to this file.
echo  You can send that .txt file to whoever helps you with this program.
echo.
pause
