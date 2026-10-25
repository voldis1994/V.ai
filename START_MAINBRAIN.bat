@echo off
setlocal EnableExtensions
chcp 65001 >nul
title Main Brain OS — uzstādīšana un palaišana

echo.
echo ============================================
echo   Main Brain OS — sākuma instalācija
echo ============================================
echo.
echo Primārā AI: llama.cpp llama-server + GGUF
echo Ollama NAV nepieciešama ^(tikai neobligāta rezerve^).
echo.
echo Šis fails:
echo   - uzstāda .NET 8, Python, WebView2, .venv
echo   - uzstāda llama-server
echo   - pēc izvēles lejupielādē GGUF modeļus
echo.

cd /d "%~dp0"
if not exist "scripts\bootstrap_windows.ps1" (
  echo [KĻŪDA] Nav atrasts scripts\bootstrap_windows.ps1
  pause
  exit /b 1
)

where powershell >nul 2>&1
if errorlevel 1 (
  echo [KĻŪDA] PowerShell nav atrasts.
  pause
  exit /b 1
)

echo Izvēle:
echo   [1] Uzstādīt rīkus un palaist ^(bez GGUF^)
echo   [2] Tikai uzstādīt rīkus ^(bez GGUF, nepalaiž^)
echo   [3] Uzstādīt rīkus + izstrādes testu pakotnes
echo   [4] Uzstādīt rīkus + GGUF light ^(~2 GB^) un palaist
echo   [5] Uzstādīt rīkus + GGUF standard ^(~6–10 GB, +vision^) un palaist
echo   [6] Tikai lejupielādēt GGUF light modeļus
echo   [7] Atcelt
echo.
set /p CHOICE="Ievadiet numuru: "

if "%CHOICE%"=="7" goto :cancel
if "%CHOICE%"=="1" goto :install_start
if "%CHOICE%"=="2" goto :install_only
if "%CHOICE%"=="3" goto :install_dev
if "%CHOICE%"=="4" goto :install_models_light
if "%CHOICE%"=="5" goto :install_models_standard
if "%CHOICE%"=="6" goto :models_only
echo Nederīga izvēle.
pause
exit /b 1

:install_start
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\bootstrap_windows.ps1" -AcceptDownloads
goto :end

:install_only
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\bootstrap_windows.ps1" -AcceptDownloads -SkipStart
goto :end

:install_dev
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\bootstrap_windows.ps1" -AcceptDownloads -IncludeDevTools
goto :end

:install_models_light
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\bootstrap_windows.ps1" -AcceptDownloads -DownloadModels -ModelProfile light
goto :end

:install_models_standard
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\bootstrap_windows.ps1" -AcceptDownloads -DownloadModels -ModelProfile standard
goto :end

:models_only
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\download_models.ps1" -Profile light -AcceptDownloads
goto :end

:cancel
echo Atcelts.
pause
exit /b 0

:end
echo.
if errorlevel 1 (
  echo [KĻŪDA] Process beidzās ar kļūdu. Skatiet ziņojumus augstāk.
  pause
  exit /b 1
)
echo Gatavs.
echo llama-server: %%LOCALAPPDATA%%\MainBrainOS\llama
echo GGUF:         %%LOCALAPPDATA%%\MainBrainOS\models
echo API:          http://127.0.0.1:8080/v1
echo Ja serveris nav startējis: scripts\start_llama_server.ps1
echo.
pause
endlocal
