#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ -x "$ROOT/.venv/bin/python" ]]; then
  PYTHON="$ROOT/.venv/bin/python"
else
  PYTHON="${PYTHON:-python3}"
fi

BACK_PID=""
FRONT_PID=""

cleanup() {
  trap - EXIT INT TERM
  if [[ -n "$BACK_PID" ]]; then
    kill "$BACK_PID" 2>/dev/null || true
  fi
  if [[ -n "$FRONT_PID" ]]; then
    kill "$FRONT_PID" 2>/dev/null || true
  fi
  wait 2>/dev/null || true
}
trap cleanup EXIT INT TERM

printf 'Backend:  http://localhost:8000\n'
printf 'Frontend: http://localhost:5173\n'

( cd "$ROOT" && exec "$PYTHON" -m app.main ) &
BACK_PID=$!

( cd "$ROOT/Alpha-front" && exec ./node_modules/.bin/vite --host 0.0.0.0 --strictPort ) &
FRONT_PID=$!

wait -n "$BACK_PID" "$FRONT_PID"
