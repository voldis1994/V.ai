@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Main Brain OS - UPGRADE MODEL

echo.
echo ============================================
echo   Main Brain OS - UPGRADE MODEL
echo ============================================
echo.
echo Qwen 1.5B NEPROT uzdevumus (samekle / iemacies /
echo izskaidro / uztaisi programu). Vajag lielaku modeli.
echo.
echo Profiles:
echo   [1] standard  - Qwen 3B  (~4 GB)  - minimums
echo   [2] capable   - Qwen 7B  (~10 GB) - ieteicams (16GB RAM+)
echo   [3] cancel
echo.
choice /C 123 /N /M "Choose 1, 2 or 3: "
set SEL=%ERRORLEVEL%
if "%SEL%"=="3" goto :eof
if "%SEL%"=="1" set "PROFILE=standard"
if "%SEL%"=="2" set "PROFILE=capable"

echo.
echo [1] Stop old processes...
taskkill /F /IM MainBrain.exe >nul 2>&1
taskkill /F /IM python.exe >nul 2>&1
taskkill /F /IM llama-server.exe >nul 2>&1
timeout /t 2 /nobreak >nul

echo [2] Download GGUF profile: %PROFILE%
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\download_models.ps1" -Profile %PROFILE% -AcceptDownloads -Force
if errorlevel 1 (
  echo [ERROR] Model download failed.
  pause
  exit /b 1
)

echo [3] Sync backend + rebuild...
if exist "%~dp0FIX_BACKEND.bat" (
  call "%~dp0FIX_BACKEND.bat"
) else (
  echo [WARN] FIX_BACKEND.bat missing - start MainBrain.exe manually after pull.
)

echo.
echo Done. Header should show Qwen2.5-3B or Qwen2.5-7B, not 1.5B.
echo Try:  izskaidro kas ir Python
echo       iemacies ka uztaisīt vienkāršu kalkulatoru
echo       uztaisi Python failu hello.py
pause
endlocal
