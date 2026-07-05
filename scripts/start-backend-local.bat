@echo off
setlocal
cd /d "%~dp0\.."

if "%API_KEY%"=="" set "API_KEY=local-dev-key"

set "PYTHON_EXE="
if exist ".venv\Scripts\python.exe" set "PYTHON_EXE=%CD%\.venv\Scripts\python.exe"
if "%PYTHON_EXE%"=="" if exist "C:\Users\Jason\AppData\Local\Programs\Python\Python312\python.exe" set "PYTHON_EXE=C:\Users\Jason\AppData\Local\Programs\Python\Python312\python.exe"
if "%PYTHON_EXE%"=="" set "PYTHON_EXE=C:\Users\Jason\AppData\Local\Programs\Python\Python312\python.exe"
if "%PYTHON_EXE%"=="" set "PYTHON_EXE=python"

set "MLFLOW_ALLOW_FILE_STORE=true"
echo.
echo [Qlib Backend] Starting FastAPI on 127.0.0.1:8000 ...
echo [Qlib Backend] Python: %PYTHON_EXE%
echo [Qlib Backend] Local server management key: %API_KEY%
echo.
echo Use this key in the web page when it asks for Server API_KEY.
echo.

"%PYTHON_EXE%" -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
