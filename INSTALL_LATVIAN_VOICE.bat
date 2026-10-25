@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo === Main Brain - latviesu balss (Everita) ===
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\install_latvian_voice.ps1" %*
set ERR=%ERRORLEVEL%
if not "%ERR%"=="0" (
  echo.
  echo [ERROR] Instalacija neizdevas. Kods: %ERR%
  pause
  exit /b %ERR%
)
echo.
pause
exit /b 0
