@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo === Main Brain — latviešu balss (Everita) ===
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\install_latvian_voice.ps1" %*
if errorlevel 1 pause
exit /b %ERRORLEVEL%
