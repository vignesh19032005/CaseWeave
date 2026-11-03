@echo off
REM CaseWeave Backend Startup Script
REM Usage:
REM   run_backend.bat          (Runs standard HTTP on port 8010)
REM   run_backend.bat --ssl    (Runs HTTPS with generated localhost cert)

setlocal

REM Uses the Python on your PATH. To use a specific one: set PYTHON=C:\path\to\python.exe before running.
if "%PYTHON%"=="" set PYTHON=python

cd /d "%~dp0backend"

if "%1"=="--ssl" (
    echo [CaseWeave] Starting backend with TLS (HTTPS) on https://127.0.0.1:8010 ...
    if not exist "certs\localhost.crt" (
        echo [CaseWeave] Certs not found. Generating localhost certificate...
        "%PYTHON%" scripts\generate_localhost_cert.py
    )
    "%PYTHON%" -m uvicorn api:app --host 127.0.0.1 --port 8010 --ssl-keyfile certs\localhost.key --ssl-certfile certs\localhost.crt --reload
) else (
    echo [CaseWeave] Starting backend on http://127.0.0.1:8010 ...
    "%PYTHON%" -m uvicorn api:app --host 127.0.0.1 --port 8010 --reload
)

