@echo off
setlocal
cd /d "%~dp0"
title Main Brain - Face Recognition

where python >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Python not in PATH
  pause
  exit /b 1
)

echo Installing deps...
python -m pip install -r requirements.txt
if errorlevel 1 (
  echo [ERROR] pip failed
  pause
  exit /b 1
)

echo.
echo Starting face recognition...
echo   E = enroll name   R = recognize on/off   Q = quit
echo.
python face_app.py
echo.
pause
endlocal
