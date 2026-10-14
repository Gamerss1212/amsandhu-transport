@echo off
rem Opens the JARVIS screen in its own Chrome (or Edge) window where sound may play without a click,
rem so JARVIS starts and speaks by himself. The microphone still asks for permission once.
set "URL=http://localhost:5173/?autostart=1"
rem Wait until his screen is being served (first start can take a while), up to 3 minutes, then open the window.
set /a tries=0
:wait
curl.exe -s -o nul --max-time 2 "http://localhost:5173/" && goto open
set /a tries+=1
if %tries% geq 90 goto open
timeout /t 2 /nobreak >nul
goto wait
:open
set "FLAGS=--autoplay-policy=no-user-gesture-required --app=%URL%"
for %%B in ("%ProgramFiles%\Google\Chrome\Application\chrome.exe" "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe" "%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe") do (
  if exist %%B ( start "" %%B --user-data-dir="%LOCALAPPDATA%\JarvisScreen" %FLAGS% & exit /b 0 )
)
for %%B in ("%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe" "%ProgramFiles%\Microsoft\Edge\Application\msedge.exe") do (
  if exist %%B ( start "" %%B --user-data-dir="%LOCALAPPDATA%\JarvisScreenEdge" %FLAGS% & exit /b 0 )
)
start "" "%URL%"
