#!/usr/bin/env bash
# Start the OILTRACE API and dashboard together.
set -e
ROOT="$(cd "$(dirname "$0")" && pwd)"

PY="$ROOT/backend/.venv/bin/python"
if [ ! -x "$PY" ]; then
  echo "No virtualenv at backend/.venv — create it first:"
  echo "  cd backend && python3 -m venv .venv && .venv/bin/python -m pip install -r ../requirements.txt"
  exit 1
fi

echo "API       http://localhost:8000  (docs at /docs)"
echo "Dashboard http://localhost:5173"
echo

cd "$ROOT/backend" && "$PY" -m uvicorn main:app --reload --port 8000 &
API_PID=$!
trap 'kill $API_PID 2>/dev/null || true' EXIT

cd "$ROOT/frontend" && npm run dev
