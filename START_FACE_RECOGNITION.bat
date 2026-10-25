@echo off
setlocal
cd /d "%~dp0"
title Main Brain OS - Face Recognition
if not exist "%~dp0apps\face_recognition\RUN_FACE_APP.bat" (
  echo [ERROR] Missing apps\face_recognition
  pause
  exit /b 1
)
call "%~dp0apps\face_recognition\RUN_FACE_APP.bat"
endlocal
