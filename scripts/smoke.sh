#!/usr/bin/env sh
# Smoke test against a running stack: health, placeholder page, and one real
# evidence round-trip using the synthetic example files in spec/examples.
# Usage: BASE_URL=http://127.0.0.1:8000 [NETCOOP_API_TOKEN=...] sh scripts/smoke.sh
set -eu
BASE_URL="${BASE_URL:-http://127.0.0.1:8000}"
DIR="$(cd "$(dirname "$0")/.." && pwd)"
AUTH=""
if [ -n "${NETCOOP_API_TOKEN:-}" ]; then AUTH="Authorization: Bearer ${NETCOOP_API_TOKEN}"; fi
fail=0

req() {  # method path [body-file]
  if [ $# -ge 3 ]; then
    curl -sS -o - -w '\n%{http_code}' -X "$1" -H 'Content-Type: application/json' ${AUTH:+-H "$AUTH"} --data-binary "@$3" "$BASE_URL$2"
  else
    curl -sS -o - -w '\n%{http_code}' -X "$1" ${AUTH:+-H "$AUTH"} "$BASE_URL$2"
  fi
}

check() {  # name expected-status substring response
  code=$(printf '%s' "$4" | tail -n1); text=$(printf '%s' "$4" | sed '$d')
  if [ "$code" = "$2" ] && printf '%s' "$text" | grep -q "$3"; then echo "PASS $1 ($code)"
  else echo "FAIL $1: status=$code body=$(printf '%s' "$text" | head -c 300)"; fail=1; fi
}

check live  200 '"status":"live"'      "$(req GET /health/live)"
check ready 200 '"status":"ready"'     "$(req GET /health/ready)"
check index 200 'Not yet implemented'  "$(req GET /)"

tmp=$(mktemp)
printf '{"data_mode":"synthetic","title":"smoke"}' > "$tmp"
resp=$(req POST /api/incidents "$tmp"); check "create incident" 201 '"incident_id"' "$resp"
iid=$(printf '%s' "$resp" | sed '$d' | sed -n 's/.*"incident_id":"\([^"]*\)".*/\1/p')
if [ -n "$iid" ]; then
  check "ingest example" 200 '"observations_added":3' "$(req POST "/api/incidents/$iid/telemetry" "$DIR/spec/examples/telemetry-batch-example.json")"
  check "read evidence" 200 '"observation_id"' "$(req GET "/api/incidents/$iid/evidence")"
fi
rm -f "$tmp"
exit $fail
