@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Main Brain OS - FIX BACKEND

echo.
echo === Main Brain OS - backend labosana ===
echo.

echo [1/5] Aptur vecos procesus...
taskkill /F /IM MainBrain.exe >nul 2>&1
taskkill /F /IM python.exe >nul 2>&1
taskkill /F /IM llama-server.exe >nul 2>&1
timeout /t 2 /nobreak >nul

echo [2/5] Kop? jaun?ko backend uz release...
if exist "%~dp0src\backend\mainbrain" (
  if not exist "%~dp0release\win-x64\backend" mkdir "%~dp0release\win-x64\backend"
  xcopy /E /Y /I "%~dp0src\backend\mainbrain" "%~dp0release\win-x64\backend\mainbrain" >nul
  echo      OK: release\win-x64\backend\mainbrain
) else (
  echo      [ERROR] Nav src\backend\mainbrain - lejupiel?d?jiet JAUNU main ZIP
  echo      https://github.com/voldis1994/V.ai/archive/refs/heads/main.zip
  pause
  exit /b 1
)

if not exist "%~dp0src\backend\mainbrain\brain\chat.py" (
  echo [ERROR] Nav chat.py - jums ir VEC? mape. Lejupiel?d?jiet jaunu ZIP no main.
  pause
  exit /b 1
)

echo [3/5] P?rbauda Python 3.12...
set PY=
where py >nul 2>&1 && for /f "delims=" %%i in ('py -3.12 -c "import sys; print(sys.executable)" 2^>nul') do set PY=%%i
if "%PY%"=="" if exist "%~dp0.release\win-x64\runtime-venv\Scripts\python.exe" set PY=%~dp0release\win-x64\runtime-venv\Scripts\python.exe
if "%PY%"=="" if exist "%~dp0.release\win-x64\runtime-venv\Scripts\python.exe" set PY=%~dp0release\win-x64\runtime-venv\Scripts\python.exe
if "%PY%"=="" if exist "%~dp0.release\win-x64\runtime-venv\Scripts\python.exe" set PY=%~dp0release\win-x64\runtime-venv\Scripts\python.exe
if "%PY%"=="" if exist "%~dp0release\win-x64\runtime-venv\Scripts\python.exe" set PY=%~dp0release\win-x64\runtime-venv\Scripts\python.exe
if "%PY%"=="" if exist "%~dp0.venv\Scripts\python.exe" set PY=%~dp0.venv\Scripts\python.exe
if "%PY%"=="" (
  echo [ERROR] Python 3.12 nav atrasts. Palaidiet START_MAINBRAIN.bat vispirms.
  pause
  exit /b 1
)
echo      Python: %PY%

echo [4/5] Test? importu un /health...
set PYTHONPATH=%~dp0src\backend
set MAINBRAIN_API_TOKEN=fix-local-token
start "MainBrain-API" /MIN "%PY%" -m mainbrain.api
timeout /t 4 /nobreak >nul
powershell -NoProfile -Command "try { (Invoke-WebRequest http://127.0.0.1:8765/health -UseBasicParsing).Content; exit 0 } catch { Write-Host $_.Exception.Message; exit 1 }"
if errorlevel 1 (
  echo [ERROR] Backend neatsaka. Skatiet log: %%LOCALAPPDATA%%\MainBrainOS\logs\backend.log
  pause
  exit /b 1
)

powershell -NoProfile -Command "try { $r=Invoke-WebRequest http://127.0.0.1:8765/chat -Method POST -ContentType 'application/json' -Headers @{Authorization='Bearer fix-local-token'} -Body '{\"message\":\"sveiki\",\"session_id\":\"fix\"}' -UseBasicParsing; Write-Host $r.Content; exit 0 } catch { Write-Host $_.Exception.Message; if ($_.Exception.Response.StatusCode.value__ -eq 404) { exit 2 }; exit 0 }"
if errorlevel 2 (
  echo [ERROR] /chat joprojam 404 - chat.py nav ieladeets
  pause
  exit /b 1
)

echo [5/5] Buve MainBrain.exe...
where dotnet >nul 2>&1
if errorlevel 1 (
  echo [WARN] dotnet nav PATH - izlaid?s b?vi. Backend tests OK; palaidiet exe no release ja jau ir.
) else (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\build_release.ps1"
)

echo.
echo === GATAVS ===
echo Palaidiet: release\win-x64\MainBrain.exe
echo Vai darbvirsmas iscelu Main Brain OS
echo.
if exist "%~dp0release\win-x64\MainBrain.exe" (
  start "" "%~dp0release\win-x64\MainBrain.exe"
)
pause
endlocal
