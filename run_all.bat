@echo off
REM One command: infrastructure (MySQL + Redis in Docker), then backend, worker and frontend, each in its own window.
REM Before the first run: copy backend\.env.example to backend\.env, fill in META_API_KEY and the MYSQL_* values,
REM and set MYSQL_ROOT_PASSWORD / MYSQL_PASSWORD in your shell so docker compose can start MySQL.
setlocal
cd /d "%~dp0"
docker compose up -d
if errorlevel 1 (echo [CaseWeave] docker compose failed. Is Docker running? & exit /b 1)
start "CaseWeave backend" cmd /k "%~dp0run_backend.bat"
start "CaseWeave worker" cmd /k "%~dp0run_worker.bat"
start "CaseWeave frontend" cmd /k "cd /d %~dp0frontend && npm install && npm run dev"
echo [CaseWeave] Starting. Open http://localhost:3000 in a minute. First sign-in: user admin, you will be asked to choose a password.
