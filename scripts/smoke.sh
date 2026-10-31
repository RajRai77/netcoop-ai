#!/usr/bin/env sh
# Smoke test against a running stack (local launcher or Docker Compose):
# health, browser UI, A2A agent discovery, one evidence round-trip, and one full
# diagnosis over A2A on a packaged synthetic scenario.
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

incident_id() {  # extract the first incident_id from a response body
  printf '%s' "$1" | sed '$d' | grep -o '"incident_id":"[^"]*"' | head -n1 | cut -d'"' -f4
}

check live  200 '"status":"live"'      "$(req GET /health/live)"
check ready 200 '"status":"ready"'     "$(req GET /health/ready)"
check index 200 'NetCoop AI'           "$(req GET /)"
check agents 200 '"status":"available"' "$(req GET /api/agents)"

tmp=$(mktemp)
printf '{"data_mode":"synthetic","title":"smoke"}' > "$tmp"
resp=$(req POST /api/incidents "$tmp"); check "create incident" 201 '"incident_id"' "$resp"
iid=$(incident_id "$resp")
if [ -n "$iid" ]; then
  check "ingest example" 200 '"observations_added":3' "$(req POST "/api/incidents/$iid/telemetry" "$DIR/spec/examples/telemetry-batch-example.json")"
  check "read evidence" 200 '"observation_id"' "$(req GET "/api/incidents/$iid/evidence")"
fi

printf '{"scenario_id":"S11-ambiguous-resolvable"}' > "$tmp"
resp=$(req POST /api/incidents "$tmp"); check "scenario incident" 201 '"incident_id"' "$resp"
sid=$(incident_id "$resp")
if [ -n "$sid" ]; then
  printf '{"verification":true}' > "$tmp"
  check "start diagnosis" 202 '"run_id"' "$(req POST "/api/incidents/$sid/diagnose" "$tmp")"
  i=0; rep=""
  while [ $i -lt 120 ]; do
    rep=$(req GET "/api/incidents/$sid/report")
    [ "$(printf '%s' "$rep" | tail -n1)" = "200" ] && break
    i=$((i+1)); sleep 1
  done
  check "report over a2a" 200 '"transport":"a2a"' "$rep"
  check "report diagnosed" 200 '"status":"diagnosed"' "$rep"
fi
rm -f "$tmp"
exit $fail
