# Deployment first — Docker Compose on one Linux VPS

**Status:** Target design to implement and verify, not a deployed system. The user requires a hosted working web application. The official PS only requires runnable CLI or optional dashboard, so public hosting is an additional project requirement.

## Target service split

- `web`: FastAPI API + minimal browser UI + DB-backed case coordinator + deterministic engine (can be separate worker later).
- `agent-performance`, `agent-infrastructure`, `agent-connectivity`: independent A2A HTTP servers on **internal** Docker network; at least two active for mandatory interop.
- `db`: PostgreSQL, named persistent data volume; Alembic migrations.
- `proxy`: Caddy terminating TLS, only public entrypoint. Configure DNS / ports 80+443 / cert management before claiming HTTPS works.

Only the reverse proxy should be publicly accessible. Do not publish Postgres or agent ports. Internal A2A URLs must use Docker service DNS, not `localhost`. Use compose health checks and `depends_on: condition: service_healthy` where needed; this alone does not guarantee app-level readiness, so expose `/health/live` and `/health/ready`.

## Minimum application endpoints (planned)

- `GET /health/live`, `GET /health/ready` — liveness vs dependencies.
- `POST /api/incidents` — ingest approved input (size-limited); return incident ID.
- `GET /api/incidents/{id}` — workflow status + progress.
- `GET /api/incidents/{id}/report` — schema-validated JSON outcome.
- `GET /api/incidents/{id}/evidence` — authorized evidence and lineage view.
- `GET /` — simple browser UI (upload/choose a labeled scenario, launch, view evidence/messages/results). Avoid unverified claims of live sources.

## Deployment artifacts to create as part of coding (NOT included as functional code in this pack)

- `Dockerfile` multi-stage or minimal production image, pinned Python dependencies, non-root runtime.
- `compose.yaml`, `compose.production.yaml` (private service networks, persistent DB volume, health checks, restart policy, resource logging limits).
- `.env.example` with **non-secret placeholders only** and descriptions. Real `.env` ignored by Git; use Docker Compose secrets where appropriate.
- `alembic/` and migrations; startup migrate step or explicit deployment migration command.
- `scripts/smoke.sh` (or equivalent) executes end-to-end case and validates JSON report.
- `scripts/backup.sh`, `scripts/restore.sh` tested on fresh volume.
- `README.md` with deployment steps, licensing/data modes and rollback instructions.

## Clean-server validation sequence

1. Install supported Linux/Docker Engine with Compose plugin. Ensure CPU/RAM/disk are adequate **for actual measured workload**. Prior planning estimate 4 vCPU / 8 GB RAM / 30–50 GB SSD excludes large network labs.
2. `git clone`, configure DNS, create secrets, `cp .env.example .env` then fill environment securely.
3. `docker compose -f compose.yaml -f compose.production.yaml config` — must validate.
4. Build and `up -d --build`; run migrations and verify all health checks, internal A2A connectivity, valid DB.
5. Import a documented non-sensitive recorded scenario through the **public browser or API**. Check JSON report, agent task provenance, modes and audit events.
6. Restart services; verify report/history still present. Back up and restore on fresh DB volume. Test erroneous input and one agent unavailable.
7. Open public domain via HTTPS from an external client. Ensure only proxy is reachable, upload size limits and credentials set, no test admin endpoint exposed.
8. Document exact Git commit, deployed image versions, test run/date and demonstrated limitations.

## Fallbacks and safe modes

- No live network connectivity: recorded or synthetic authorized sources remain functional, clearly labeled. This is NOT the same as live campus diagnosis.
- No external graph tools: use versioned topology JSON/NetworkX and disclose missing path information.
- No Temporal: DB-backed persisted state machine; don't deploy Temporal `start-dev` as a production service.
- Agent unavailable: report incomplete coverage or operational failure, never fabricate an A2A reply.
- No LLM API: no impact on deterministic diagnosis or required report.

## Production cautions

- Single VPS Compose is **not highly available**. Backups, restore drills, correct permissions, capacity monitoring and restart policies improve recovery, but host failure remains a single point of failure.
- Restrict uploaded files, auth/access, audit logs and retention; do not store sensitive campus info unprotected.
- Do not run Containerlab with privileged Docker access in the public API container. Run lab/benchmark separately, offline/controlled.
- Release checklist requires basic security review: authentication for incident/evidence endpoints, trusted A2A agents, outbound access allowlist, secrets, request rate limits and TLS verified.
- Never claim deployment complete until the actual clean-server E2E test passes.
