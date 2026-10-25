@echo off
setlocal EnableExtensions
cd /d "%~dp0"

REM This .bat must stay ASCII + CRLF. Menu lives in PowerShell (UTF-8 safe).
where powershell >nul 2>&1
if errorlevel 1 (
  echo [ERROR] PowerShell not found.
  pause
  exit /b 1
)

if not exist "%~dp0scripts\start_mainbrain.ps1" (
  echo [ERROR] Missing scripts\start_mainbrain.ps1
  echo Run this from the repo folder that contains START_MAINBRAIN.bat
  echo Current: %CD%
  pause
  exit /b 1
)

if not exist "%~dp0scripts\bootstrap_windows.ps1" (
  echo [ERROR] Missing scripts\bootstrap_windows.ps1
  echo Make sure you cloned the full repo from GitHub main branch.
  pause
  exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start_mainbrain.ps1" %*
set ERR=%ERRORLEVEL%
echo.
if not "%ERR%"=="0" (
  echo [ERROR] Exit code %ERR%
  pause
  exit /b %ERR%
)
pause
endlocal
