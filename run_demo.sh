#!/usr/bin/env bash
set -e
ROOT="$(cd "$(dirname "$0")" && pwd)"
echo "OILTRACE AI"
echo "1) Backend: http://localhost:8000/docs"
echo "2) Frontend: http://localhost:5173"
(cd "$ROOT/backend" && uvicorn main:app --reload --port 8000) &
BACKEND_PID=$!
trap 'kill $BACKEND_PID 2>/dev/null || true' EXIT
cd "$ROOT/frontend"
npm run dev
