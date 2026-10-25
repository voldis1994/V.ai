@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Main Brain OS - Full Setup

echo.
echo ============================================
echo   Main Brain OS - ONE-CLICK FULL SETUP
echo ============================================
echo.
echo This will:
echo   1) Install .NET 8, Python, WebView2
echo   2) Install llama-server (local AI)
echo   3) Download GGUF models (~2 GB)
echo   4) Build MainBrain.exe
echo   5) Create Desktop shortcut for daily use
echo   6) Start the app
echo.
echo Ollama is NOT required.
echo.
echo Press any key to start (or Ctrl+C to cancel)...
pause >nul

where powershell >nul 2>&1
if errorlevel 1 (
  echo [ERROR] PowerShell not found.
  pause
  exit /b 1
)

if not exist "%~dp0scripts\setup_full.ps1" (
  echo [ERROR] Missing scripts\setup_full.ps1
  echo Download the FULL repo from:
  echo   https://github.com/voldis1994/V.ai/archive/refs/heads/main.zip
  echo Extract it, then run START_MAINBRAIN.bat from that folder.
  pause
  exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\setup_full.ps1"
set ERR=%ERRORLEVEL%
echo.
if not "%ERR%"=="0" (
  echo [ERROR] Setup finished with code %ERR%
  pause
  exit /b %ERR%
)

echo.
echo Setup finished.
echo Daily use: Desktop shortcut "Main Brain OS" or release\win-x64\MainBrain.exe
echo.
pause
endlocal
