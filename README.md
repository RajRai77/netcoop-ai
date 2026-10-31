# NetCoop AI

Evidence-first, interoperable multi-agent network fault diagnosis
(Agentic AI Grand Finale, IIT Bhubaneswar — "NetCoop AI" challenge).

> **Status: Gate 1 (evidence foundation).** Telemetry is validated, normalized and
> stored in an append-only evidence ledger. There is **no diagnosis engine, no
> specialist agents and no report yet**. See
> [docs/14_PROJECT_PROGRESS.md](docs/14_PROJECT_PROGRESS.md) for exactly what is
> implemented and verified, and [docs/10_BUILD_GATES.md](docs/10_BUILD_GATES.md) for the plan.

## Quick start (Windows or Linux, no Docker)

Requires Python 3.12 and [uv](https://docs.astral.sh/uv/).

```sh
git clone <repository> && cd netcoop-ai
uv sync --locked
uv run python scripts/run_local.py            # http://127.0.0.1:8000, Ctrl+C to stop
```

The launcher checks the environment, creates a local SQLite database in `./var`,
applies migrations, starts the API as a separate process, waits for readiness,
and shuts it down cleanly. Useful options:

```sh
uv run python scripts/run_local.py --check        # start, smoke-test, stop (exit code 0/1)
uv run python scripts/run_local.py --port auto    # if 8000 is busy
uv run python scripts/run_local.py --database-url postgresql://user:pass@host:5432/netcoop
uv run pytest                                     # test suite
```

## What works now

- **NDEP contracts** in [spec/](spec/): observation, finding, topology, telemetry batch (draft JSON Schemas) and a versioned metric registry. Pydantic models in `src/netcoop/evidence/models.py` are tested to accept/reject the same documents as the schemas.
- **Semantic validation** (`src/netcoop/evidence/normalize.py`): units are mandatory and converted only by registry factors. `0.02` packet loss without a unit is rejected, not guessed. NaN/Inf, string-to-number coercion, out-of-range values, naive/future timestamps and bad windows get typed rejection codes. Stale data is kept and flagged. Unknown devices are quarantined against the topology snapshot.
- **Evidence integrity:** content-hashed immutable raw records (rejected ones too), deterministic observation IDs, duplicate and record-id conflict detection, lineage groups so two agents reading one source sample count as one piece of evidence, findings that must reference stored observations, linear revision chains (`supersedes_finding_id`).
- **Counters** (`src/netcoop/evidence/counters.py`): rates only from valid pairs; resets, conflicting samples, impossible rates and mixed sources are reported, never differenced.
- **Persistence:** one SQLAlchemy implementation for SQLite (local) and PostgreSQL (deployed), an Alembic migration, and database triggers that refuse UPDATE/DELETE on evidence tables.

## API (Gate 1 subset)

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/health/live`, `/health/ready` | liveness; readiness (DB reachable and schema at head) |
| POST | `/api/incidents` | create incident `{data_mode, title?, topology?}` |
| POST | `/api/incidents/{id}/telemetry` | submit a TelemetryBatch; returns per-record status and typed issues |
| GET | `/api/incidents/{id}`, `/api/incidents/{id}/evidence`, `/api/raw-records/{raw_id}` | read back |

Interactive docs at `/docs`. If `NETCOOP_API_TOKEN` is set, `/api/*` requires `Authorization: Bearer <token>`.

## CLI

```sh
uv run netcoop --database-url sqlite:///var/netcoop.db db upgrade
uv run netcoop --database-url sqlite:///var/netcoop.db incident create --data-mode synthetic --topology spec/examples/topology-example.json
uv run netcoop --database-url sqlite:///var/netcoop.db ingest <INCIDENT_ID> spec/examples/telemetry-batch-example.json
uv run netcoop --database-url sqlite:///var/netcoop.db evidence <INCIDENT_ID>
```

## Layout

| Path | Purpose |
| --- | --- |
| `src/netcoop/evidence/` | NDEP models, registry, normalization, counters, integrity rules (no I/O, no transport) |
| `src/netcoop/storage/` | repository contract, SQL store, engine, migrations |
| `src/netcoop/api/` | FastAPI app |
| `src/netcoop/interop/a2a_probe.py` | A2A SDK compatibility probe (**not** a diagnostic agent) |
| `src/netcoop/launcher.py`, `scripts/run_local.py` | cross-platform local launcher |
| `spec/` | draft NDEP schemas, metric registry, synthetic examples (not official organizer schemas) |
| `docs/` | architecture, ADRs, gates, progress, platform matrix ([docs/20](docs/20_PLATFORM_COMPATIBILITY.md)) |

## Docker Compose (Linux)

Not yet executed anywhere (no Docker on the development machine). It is meant to be verified by the GitHub Actions `compose-smoke` job or on the target VPS.

```sh
cp .env.example .env      # set POSTGRES_PASSWORD (hex), optionally NETCOOP_API_TOKEN
docker compose config
docker compose up -d --build --wait
BASE_URL=http://127.0.0.1:8000 sh scripts/smoke.sh
docker compose down       # keeps data; `down -v` DELETES the database volume
```

Production: `docker compose -f compose.yaml -f compose.production.yaml up -d --build --wait`. That requires `NETCOOP_DOMAIN`, `ACME_EMAIL` and `NETCOOP_API_TOKEN`. Only Caddy (80/443) is public; PostgreSQL and the app stay on internal networks. The web container runs migrations on start.

## Data honesty

All bundled data is **synthetic** and labeled so. Every incident carries a `data_mode` (`synthetic | recorded | emulated | live | mock`), and batches with a different mode are refused. No live campus data or network access is used.
