@echo off
REM CaseWeave RQ Background Worker Startup Script
setlocal

set PYTHON=C:\Users\VIGNESH\AppData\Local\Programs\Python\Python311\python.exe
if not exist "%PYTHON%" set PYTHON=py -3.11
if not exist "%PYTHON%" set PYTHON=python

cd /d "%~dp0backend"
echo [CaseWeave] Starting RQ Pipeline Worker...
"%PYTHON%" worker.py

