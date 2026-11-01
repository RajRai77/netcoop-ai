#!/bin/sh
# One command: install the locked Python environment and start NetCoop AI
# (API + three A2A specialist agents + the React app) at http://127.0.0.1:8000/
# Needs uv (https://docs.astral.sh/uv/); uv fetches Python 3.12 if it is missing.
set -e
cd "$(dirname "$0")"
uv sync --locked
if [ ! -f frontend/dist/index.html ] && command -v npm >/dev/null 2>&1; then
  (cd frontend && npm ci --no-audit --no-fund && npm run build)
fi
exec uv run python scripts/run_local.py "$@"
