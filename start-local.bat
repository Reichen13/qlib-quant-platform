@echo off
setlocal
cd /d "%~dp0"

if not exist "backend" (
  echo [ERROR] Please run this file from the qlib project root.
  pause
  exit /b 1
)

start "Qlib Backend 8000" cmd /k "cd /d %~dp0 && call scripts\start-backend-local.bat"
start "Qlib Frontend 5173" cmd /k "cd /d %~dp0 && call scripts\start-frontend-local.bat"

echo.
echo Qlib local services are starting in two new windows.
echo.
echo Frontend: http://localhost:5173
echo Backend:  http://127.0.0.1:8000/health
echo.
echo Keep both opened windows running. Press Ctrl+C in those windows to stop.
echo.
pause
