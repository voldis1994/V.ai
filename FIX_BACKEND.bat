@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Main Brain OS - FIX BACKEND

echo.
echo === Main Brain OS - FIX BACKEND ===
echo.

echo [1] Stop old processes...
taskkill /F /IM MainBrain.exe >nul 2>&1
taskkill /F /IM python.exe >nul 2>&1
taskkill /F /IM llama-server.exe >nul 2>&1
timeout /t 2 /nobreak >nul

echo [2] Check chat.py exists...
if not exist "%~dp0src\backend\mainbrain\brain\chat.py" (
  echo [ERROR] Missing chat.py - your folder is TOO OLD.
  echo Download NEW zip:
  echo   https://github.com/voldis1994/V.ai/archive/refs/heads/main.zip
  echo Extract and run FIX_BACKEND.bat from the NEW folder.
  pause
  exit /b 1
)

echo [3] Copy backend into release...
if not exist "%~dp0release\win-x64\backend" mkdir "%~dp0release\win-x64\backend"
xcopy /E /Y /I "%~dp0src\backend\mainbrain" "%~dp0release\win-x64\backend\mainbrain" >nul
echo     OK

echo [4] Find Python...
set "PY="
if exist "%~dp0release\win-x64\runtime-venv\Scripts\python.exe" set "PY=%~dp0release\win-x64\runtime-venv\Scripts\python.exe"
if "%PY%"=="" if exist "%~dp0.venv\Scripts\python.exe" set "PY=%~dp0.venv\Scripts\python.exe"
if "%PY%"=="" (
  where py >nul 2>&1 && for /f "delims=" %%i in ('py -3.12 -c "import sys; print(sys.executable)" 2^>nul') do set "PY=%%i"
)
if "%PY%"=="" (
  echo [ERROR] Python not found. Run START_MAINBRAIN.bat first.
  pause
  exit /b 1
)
echo     Python: %PY%

echo [5] Build MainBrain.exe...
where dotnet >nul 2>&1
if not errorlevel 1 (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\build_release.ps1"
) else (
  echo [WARN] dotnet not in PATH - skip build
)

echo.
echo Starting MainBrain.exe ...
if exist "%~dp0release\win-x64\MainBrain.exe" (
  start "" "%~dp0release\win-x64\MainBrain.exe"
) else (
  echo [ERROR] No MainBrain.exe - run START_MAINBRAIN.bat
)
echo.
echo If error again, open this log and send a photo:
echo   %LOCALAPPDATA%\MainBrainOS\logs\backend.log
pause
endlocal
