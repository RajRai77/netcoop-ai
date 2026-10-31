#!/usr/bin/env sh
# Gate 0 smoke test: checks liveness, readiness (DB reachable) and placeholder page.
# Usage: BASE_URL=http://127.0.0.1:8000 sh scripts/smoke.sh
set -eu
BASE_URL="${BASE_URL:-http://127.0.0.1:8000}"
fail=0

check() {  # name, path, expected status, expected substring
  body=$(curl -sS -o - -w '\n%{http_code}' "$BASE_URL$2") || { echo "FAIL $1: request error"; fail=1; return; }
  code=$(printf '%s' "$body" | tail -n1)
  text=$(printf '%s' "$body" | sed '$d')
  if [ "$code" = "$3" ] && printf '%s' "$text" | grep -q "$4"; then
    echo "PASS $1 ($code)"
  else
    echo "FAIL $1: status=$code body=$(printf '%s' "$text" | head -c 300)"; fail=1
  fi
}

check live  /health/live  200 '"status":"live"'
check ready /health/ready 200 '"status":"ready"'
check index /             200 'Not yet implemented'
exit $fail
