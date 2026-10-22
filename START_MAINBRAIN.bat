@echo off
setlocal EnableExtensions
chcp 65001 >nul
title Main Brain OS — uzstādīšana un palaišana

echo.
echo ============================================
echo   Main Brain OS — sākuma instalācija
echo ============================================
echo.
echo Šis fails:
echo   1) lejupielādē/.uzstāda .NET 8, Python 3.12+, WebView2
echo   2) izveido .venv un instalē Python atkarības
echo   3) sagatavo datu mapes
echo   4) pēc izvēles palaiž izstrādes vidi
echo.
echo GGUF AI modeļi NETIEK lejupielādēti automātiski (tie ir lieli).
echo.

cd /d "%~dp0"
if not exist "scripts\bootstrap_windows.ps1" (
  echo [KĻŪDA] Nav atrasts scripts\bootstrap_windows.ps1
  echo Palaidiet šo .bat no Main Brain OS projekta saknes.
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
echo   [1] Uzstādīt visu un palaist ^(ieteicams^)
echo   [2] Tikai uzstādīt ^(nepalaiž programmu^)
echo   [3] Uzstādīt + izstrādes testu rīki ^(pytest u.c.^)
echo   [4] Atcelt
echo.
set /p CHOICE="Ievadiet numuru: "

if "%CHOICE%"=="4" goto :cancel
if "%CHOICE%"=="2" goto :install_only
if "%CHOICE%"=="3" goto :install_dev
if "%CHOICE%"=="1" goto :install_start
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

:cancel
echo Atcelts.
pause
exit /b 0

:end
echo.
if errorlevel 1 (
  echo [KĻŪDA] Bootstrap beidzās ar kļūdu. Skatiet ziņojumus augstāk.
  pause
  exit /b 1
)
echo Gatavs. Ja UI nesākas, palaidiet: scripts\start_dev.ps1
echo Vai uzbūvēiet laidienu: scripts\build_release.ps1
echo.
pause
endlocal
