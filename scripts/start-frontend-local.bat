@echo off
setlocal
cd /d "%~dp0\..\frontend"

echo [Qlib Frontend] Starting Vite on http://localhost:5173 ...
echo.

if not exist "node_modules" (
  echo node_modules not found. Running npm install first...
  npm install
  if errorlevel 1 (
    echo [ERROR] npm install failed.
    pause
    exit /b 1
  )
)

npm run dev
