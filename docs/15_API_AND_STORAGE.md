# Draft API, persistence and consistency design

**Status:** Developer proposal subject to API/schema compatibility review. It is not implemented.

## HTTP API (suggested)

| Method | Endpoint | Contract |
| --- | --- | --- |
| GET | `/health/live` | `200` if process responsive; no DB needed |
| GET | `/health/ready` | `200` only when required DB/services ready; `503` when not |
| POST | `/api/incidents` | Validated scenario/telemetry upload or selected case, explicit data mode; `201/202` with `incident_id` |
| GET | `/api/incidents/{id}` | State, timestamps, agent task coverage, revision |
| GET | `/api/incidents/{id}/report` | Structured JSON document validated against `spec/report.schema.json` |
| GET | `/api/incidents/{id}/evidence` | Paginated, permission-scoped references/lineage |
| GET | `/api/incidents/{id}/events` | Authorized timeline, may be polled/streamed |

If public, require appropriate authentication or restricted demo access. Upload endpoints must enforce MIME/content checks, size limits, JSON structural complexity, validation and retention controls. Be careful with file paths/SSRF if supporting URLs. Use generated internal IDs, no user-supplied filesystem paths.

## PostgreSQL tables (conceptual)

`incidents` (id/status/data_mode/evidence_snapshot/version/times); `raw_records` (hash/source/content ref/retention); `observations` (normalized metric/time/subject/quality/raw_ref/lineage); `findings` (agent/claim/revision/obs_ref); `topology_snapshots`; `agent_tasks` (logical_id/idempotency/status/deadline/artifact_ref); `challenges`; `hypotheses`/`hypothesis_evaluations`; `reports` (immutable revision/json content); `audit_events`; `outbox_events` only if asynchronous external delivery needs transactional outbox.

Foreign keys and unique constraints for observation IDs, logical task IDs, report revisions and lineage. Use transactions so report snapshot references point only to committed evidence. Persist coordinator state before external task submission and reconcile after restart. Do not allow each external agent full-write DB credentials by default; return A2A artifacts to coordinator and validate before persistence.

## API semantics and workflow

- `POST` is idempotent with optional client-provided idempotency token scoped to authenticated user; duplicated submission returns same logical incident or clear conflict.
- Task retries re-use logical `task_id` with separate attempt IDs. Repeated responses must never add double evidence support.
- Late response after report: make a new report revision if policy allows, never rewrite earlier conclusion silently.
- Domain IDs remain stable string IDs. Never expose internal DB integer IDs as agent identity.
- Health/readiness indicate separate runtime state; diagnosis `insufficient_evidence` is **not** a server error.
- For errors, return typed machine-readable code + human-readable explanation, and audit relevant metadata without leaking secrets.

## Data storage migration

Use SQLAlchemy/Alembic or equivalent mature migration tooling, PostgreSQL in deployed Compose from the start. Use repeatable migrations on fresh DB and upgrade; write a backup/restore test. SQLite support only if warranted for isolated tests, not a second incompatible production database.
