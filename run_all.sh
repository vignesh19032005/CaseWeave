#!/usr/bin/env bash
# One command: infrastructure (MySQL + Redis in Docker), then backend, worker and frontend.
# Before the first run: cp backend/.env.example backend/.env, fill in META_API_KEY and the MYSQL_* values,
# and export MYSQL_ROOT_PASSWORD / MYSQL_PASSWORD so docker compose can start MySQL.
set -euo pipefail
cd "$(dirname "$0")"
docker compose up -d
(cd backend && python -m uvicorn api:app --host 127.0.0.1 --port 8010 &)
(cd backend && python worker.py &)
cd frontend && npm install && npm run dev
