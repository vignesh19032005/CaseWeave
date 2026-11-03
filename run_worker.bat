@echo off
REM CaseWeave RQ Background Worker Startup Script
setlocal

REM Uses the Python on your PATH. To use a specific one: set PYTHON=C:\path\to\python.exe before running.
if "%PYTHON%"=="" set PYTHON=python

cd /d "%~dp0backend"
echo [CaseWeave] Starting RQ Pipeline Worker...
"%PYTHON%" worker.py

