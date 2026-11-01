# Backend contract for the separate React/TypeScript frontend

Everything below is implemented and exercised by tests (`tests/api/`, `tests/integration/`, `tests/frontend/ui_smoke.mjs`).
Machine-readable contract: [`docs/openapi.json`](openapi.json), regenerated with `uv run python scripts/export_openapi.py`.
NDEP payload schemas: `spec/*.schema.json`. The report schema is `spec/report.schema.json` (1.1.0).

## Start the backend for frontend development

```sh
uv sync --locked
uv run python scripts/run_local.py --port 8000 --cors-origin http://localhost:5173
```

This starts 3 specialist A2A agents and the web/coordinator on `http://127.0.0.1:8000`. Alternatively, set
`NETCOOP_CORS_ORIGINS=http://localhost:5173` (comma-separated). CORS is **off by default**. `*` is refused when an API
token is configured. A Vite proxy (`/api` → `http://127.0.0.1:8000`) also works and needs no CORS.

## Authentication

- No token is configured by default locally (the API binds to 127.0.0.1).
- If `NETCOOP_API_TOKEN` is set (required by `compose.production.yaml`), every `/api/*` request needs `Authorization: Bearer <token>`. `/health/*` stays open.
- `EventSource` cannot send headers. With a token, consume the stream with a fetch-based SSE client (e.g. `@microsoft/fetch-event-source`).
- `401` means a missing or bad token. There are no cookies or sessions.

## Errors

- Typed refusals: `{"error": {"code": "<IssueCode>", "message": str, "issues": [Issue]}}`.
  - `422` validation (e.g. `MALFORMED_JSON`, `UNSUPPORTED_SCHEMA_VERSION`, `DATA_MODE_MISMATCH`, `TOPOLOGY_INVALID`)
  - `413` `PAYLOAD_TOO_LARGE` (default 5 MiB)
  - `404` `UNKNOWN_INCIDENT`
- FastAPI-style `{"detail": ...}`: `404` not found, `409` run already in progress / archive already uploaded, `503` no database or no agents configured.
- `Issue`: `{code, severity: reject|quarantine|warning, message, record_index, record_id, measurement_index, path}`.

## Typical workflow

1. `GET /api/meta`, `GET /api/agents`: platform pills. Agents show `status: available|unavailable`, `skills`, `metrics`, `transport: a2a`.
2. Either
   - **Scenario:** `GET /api/scenarios`, then `POST /api/incidents {"scenario_id": "S11-ambiguous-resolvable"}`, or
   - **Upload:** `POST /api/incidents {"data_mode": "recorded", "title": "...", "topology": {...}?, "reference_time": "...Z"?}`, then
     `POST /api/incidents/{id}/telemetry` (body: NDEP TelemetryBatch JSON, or CSV with `?profile=<id>` from `GET /api/profiles`),
     optionally `POST /api/incidents/{id}/archive` (`{"batches": [TelemetryBatch...]}`: recorded data agents may query during verification).
3. `POST /api/incidents/{id}/diagnose {"verification": true, "max_rounds": 2, "total_budget": 6}` returns `202 {incident_id, run_id, status: "started"}`.
4. Live progress: `GET /api/incidents/{id}/stream` (SSE; see below), or poll `GET /api/incidents/{id}` (`running`, `workflow`).
5. Results:
   - `GET /api/incidents/{id}/report[?revision=n]` (JSON) and `/report.txt` (plain text)
   - `/timeline`, `/findings`, `/evidence`, `/topology`
   - `GET /api/raw-records/{raw_id}`, `GET /api/incidents/{id}/attempts/{attempt_id}` (raw A2A artifact text)
6. Re-running a diagnosis creates a new report revision; old revisions remain.

## Response shapes (main fields)

| endpoint | shape |
|---|---|
| `GET /api/incidents` | `{incidents: [{incident_id, data_mode, title, created_at, topology_snapshot_id, archive_ref, scenario_id, reference_time, workflow: {state, run_id, at} \| null, latest_report: {revision, status, suspected_root_cause, confidence_category} \| null}]}` |
| `GET /api/incidents/{id}` | `{incident, evidence_counts: {raw_records, observations, issues, ingestions, findings}, workflow, running: bool, reports: [{revision, status, created_at, evidence_snapshot_id}]}` |
| `POST /api/incidents` | `201 {incident, ingestions: [IngestionReport]}` |
| `POST .../telemetry` | `IngestionReport {ingestion_id, incident_id, batch_id, received_at, metric_registry_version, counts: {records, accepted, quarantined, partially_rejected, rejected, duplicate, conflict}, observations_added, records: [{record_index, record_id, raw_id, status, observation_ids}], issues: [Issue]}` |
| `GET .../evidence?limit&offset&metric` | `{observations: [NDEP NormalizedObservation], derived_rates: [{derived_id, subject_key, rate_metric, value, unit, window_start, window_end, input_observation_ids, lineage_groups}], issues: [StoredIssue]}` |
| `GET .../findings?all_revisions` | `{findings: [NDEP Finding]}` |
| `GET .../timeline` | `{events: [{seq, run_id, state, actor, at, detail}], attempts: [{attempt_id, task_id, attempt_no, agent_id, task_type: discover\|investigate\|verify, transport, outcome, started_at, finished_at, detail: {a2a_task_id, a2a_message_id, a2a_context_id, request_sha256, response_sha256, findings_stored, findings_unchanged, findings_rejected, error}}], challenges: [{challenge: NDEP Challenge, run_id, created_at, outcomes: [{outcome, at, detail: {new_observation_ids, note, ...}}]}]}` |
| `GET .../topology` | `{topology: NDEP TopologySnapshot \| null}`. Nodes have `type`, `role`, `service_kind`; links have `from_interface`/`to_interface` |
| `GET .../report` | NDEP report 1.1.0: `status`, `suspected_root_cause`, `confidence_category`, `affected_devices`, `supporting_evidence[]`, `alternative_causes`, `recommended_actions`, `limitations`, `root_causes[]`, `hypotheses[]` (rank, status, explained_findings, missing_discriminators, contradictions, independent_sources), `verification {rounds, challenges[], stopped_because}`, `coverage`, `decision_basis`, `transport`, `explanation` |
| `GET /api/evaluations` | `{evaluations: [{name, git_commit, knowledge, sets: {<set>: {scenarios, knowledge_frozen_before_generation, summary: {<method>: metrics}}}}], note}`. Full cases: `GET /api/evaluations/{name}` |

Workflow states: `NEW, VALIDATING, DISCOVERING, INVESTIGATING, CORRELATING, VERIFYING, INTERRUPTED`. Terminal states:
`DIAGNOSED, AMBIGUOUS, INSUFFICIENT_EVIDENCE, UNKNOWN_FAULT, HEALTHY, OPERATIONAL_ERROR`. The report `status` is the lowercase
terminal state. `confidence_category` is one of `high_support, moderate_support, ambiguous, insufficient, not_applicable`; it is a
**support category, not a probability**. Do not render it as a percentage.

## Event stream: `GET /api/incidents/{id}/stream[?after=<seq>]`

`text/event-stream`. Events, all read back from the ledger:

| event | data |
|---|---|
| `workflow` (`id:` = seq) | a timeline event |
| `attempt` | a task attempt (without the raw artifact text) |
| `challenge` | `{challenge, outcome}` |
| `report` | `{revision, status, created_at, evidence_snapshot_id}` |
| `end` | `{state, revision}`; the stream closes |

Keep-alive comments are sent every ~15 s. Reconnect with `?after=<last seq>`.

## Honesty requirements for the UI

- Always show the incident `data_mode`. Scenarios are `synthetic`.
- Report 1.2.0 adds `confidence` (calibrated on held-out data, may be `null`) and `confidence_basis` (n, correct, Wilson 95 % interval, set, caveats). Show it with its basis; keep `confidence_category` as the verdict and never render the category as a percentage.
- Scenarios with `split: "organizer"` come from the organizer's PS sample generator; label them as such.
- Do not show a diagnosis that is not in a report. Do not animate fake agent chatter.
- Show `limitations` and `alternative_causes`.
- Mock fixtures in the frontend must be clearly labeled and switched off when the backend is reachable.

## SSE ordering and reconnect

- The stream sends **only events newer than `?after=`**, which is matched against the workflow `seq`. On each poll cycle (~1 s), new items go out in this order: `workflow`, then `attempt`, then `challenge`, then `report`.
- A finished run is replayed from the ledger on connect: first all events, then `end`.
- To reconnect: remember the last `workflow` id (`id:` line) and reconnect with `?after=<id>`. `attempt`/`challenge` events are de-duplicated per connection only, so a new connection resends them; de-duplicate by `attempt_id` / `(challenge_id, at)` on the client.
- `end` is sent once the latest workflow state is terminal and no run is in progress. The server then closes the stream.

## Executed workflow (real output, 2026-11-01, Windows, `scripts/run_local.py --port 8797 --cors-origin http://localhost:5173`)

Scenario `S19-ap-down-status-in-archive` (synthetic): an AP is down, and only probe, switch and NMS data are uploaded. The AP
status exists only in the wireless controller's recorded archive. The engine finds the AP-down and port-failure explanations
observationally equivalent, asks the infrastructure agent for the AP status over A2A, receives the recorded record, and then
diagnoses the AP. Output is truncated for length.

### 1. Platform: agents discovered over A2A
```
$ curl -s http://127.0.0.1:8797/api/agents
{
 "agents": [
  {
   "agent_id": "connectivity-agent",
   "transport": "a2a",
   "url": "http://127.0.0.1:59839/",
   "status": "available",
   "skills": [
    "investigate",
    "verify"
   ],
   "metrics": [
    "dhcp_lease_failure_rate",
    "dns_query_failure_rate",
    "reachability"
   ],
   "name": "NetCoop Connectivity & Services Agent",
   "version": "0.1.0"
  },
  {
   "agent_id": "infrastructure-agent",
   "transport": "a2a",
   "url": "http://127.0.0.1:59838/",
   "status": "available",
   "skills": [
    "investigate",
    "verify"
   ],
   "metrics": [
    "cpu_utilization",
    "crc_errors",
    "device_status",
    "interface_errors",
    "interface_status",
    "memory_utilization",
    "rssi",
    "snr",
    "wireless_retry_rate"
   ],
   "name": "NetCoop Infrastructure Agent",
   "version": "0.1.0"
  },
  {
   "agent_id": "performance-agent",
   "transport": "a2a",
  
```
### 2. CORS preflight from the React dev origin
```
$ curl -s -i -X OPTIONS http://127.0.0.1:8797/api/incidents -H 'Origin: http://localhost:5173' -H 'Access-Control-Request-Method: POST' -H 'Access-Control-Request-Headers: content-type' | tr -d '\r' | grep -i 'HTTP/\|access-control'
HTTP/1.1 200 OK
vary: Origin, Access-Control-Request-Method, Access-Control-Request-Headers, Access-Control-Request-Private-Network
access-control-allow-methods: GET, POST
access-control-max-age: 600
access-control-allow-headers: Accept, Accept-Language, Authorization, Content-Language, Content-Type
access-control-allow-origin: http://localhost:5173

```
### 3. Create incident from scenario S19 (done): incident_id = INC-6e30cf3eb9bc4d6a
### 4. Start diagnosis with verification
```
$ curl -s -X POST http://127.0.0.1:8797/api/incidents/INC-6e30cf3eb9bc4d6a/diagnose -H 'Content-Type: application/json' -d '{"verification": true}'
{
 "incident_id": "INC-6e30cf3eb9bc4d6a",
 "run_id": "RUN-31c01ca9bb404613",
 "status": "started"
}
```
### 5. Live SSE stream (event lines only)
```
$ curl -s -N --max-time 120 http://127.0.0.1:8797/api/incidents/INC-6e30cf3eb9bc4d6a/stream | grep '^event:' | sort | uniq -c
     10 event: attempt
      1 event: challenge
      1 event: end
      1 event: report
      9 event: workflow

```
### 6. Final report (key fields)
```
$ curl -s http://127.0.0.1:8797/api/incidents/INC-6e30cf3eb9bc4d6a/report | python -c "import sys,json; r=json.load(sys.stdin); print(json.dumps({k:r[k] for k in ('status','suspected_root_cause','confidence_category','affected_devices','evidence_sources','transport','decision_basis')}|{'challenges':[{k:c[k] for k in ('target_agent_id','metric','subject','outcome')} for c in r['verification']['challenges']]}, indent=1))"
{
 "status": "diagnosed",
 "suspected_root_cause": "DEVICE_DOWN at AP-2-1",
 "confidence_category": "high_support",
 "affected_devices": [
  "AP-2-1"
 ],
 "evidence_sources": [
  "connectivity-agent",
  "infrastructure-agent",
  "performance-agent"
 ],
 "transport": "a2a",
 "decision_basis": [
  "H-DEVICE_DOWN-AP-2-1: signature observed (F-47f46c1879cb52166ef9c939); explains 4 symptom finding(s) using 4 independent source(s) (20 sample lineage group(s))."
 ],
 "challenges": [
  {
   "target_agent_id": "infrastructure-agent",
   "metric": "device_status",
   "subject": {
    "device_id": "AP-2-1"
   },
   "outcome": "obtained"
  }
 ]
}
```
### 7. A2A task attempts (agent, type, outcome, a2a_task_id)
```
$ curl -s http://127.0.0.1:8797/api/incidents/INC-6e30cf3eb9bc4d6a/timeline | python -c "import sys,json; t=json.load(sys.stdin); [print(a['agent_id'], a['task_type'], a['transport'], a['outcome'], a['detail'].get('a2a_task_id')) for a in t['attempts']]"
connectivity-agent discover a2a completed None
infrastructure-agent discover a2a completed None
performance-agent discover a2a completed None
connectivity-agent investigate a2a completed 3989e240-0e02-4eb9-897a-2f23afa601a2
infrastructure-agent investigate a2a completed 29d17c67-6695-4695-91d3-942f1c305eb6
performance-agent investigate a2a completed 41177790-1df1-413d-aea1-dd81661ae129
infrastructure-agent verify a2a completed 0b5f63f3-8829-4983-b2fc-f676e99e6ad1
connectivity-agent investigate a2a completed c2a023de-84e3-42b8-b251-245587a46032
infrastructure-agent investigate a2a completed e97287df-c311-417d-a8ec-3ce730527ee7
performance-agent investigate a2a completed a09356f4-7cc0-4aec-bae9-5f252cb271c1

```
