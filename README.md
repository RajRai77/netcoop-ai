# NetCoop AI

Evidence-first, interoperable multi-agent network fault diagnosis
(Agentic AI Grand Finale, IIT Bhubaneswar — "NetCoop AI" challenge).

> **Status: Gate 0 skeleton.** There is **no diagnosis engine, no agents and no
> telemetry ingestion yet**. The app currently serves health endpoints and a
> placeholder page. See [docs/14_PROJECT_PROGRESS.md](docs/14_PROJECT_PROGRESS.md)
> for what is actually implemented and verified, and
> [docs/10_BUILD_GATES.md](docs/10_BUILD_GATES.md) for the build plan.

## Layout

| Path | Purpose |
| --- | --- |
| `src/netcoop/` | Application package (FastAPI app in `api/app.py`) |
| `tests/` | pytest suite |
| `spec/` | Draft NDEP JSON Schemas and synthetic examples (not official organizer schemas) |
| `docs/` | Architecture, ADRs, gates, progress log |
| `Dockerfile`, `compose.yaml`, `compose.production.yaml`, `deploy/Caddyfile` | Container deployment |
| `scripts/smoke.sh` | Health smoke test against a running stack |

## Local development (no Docker)

Requires Python 3.12 and [uv](https://docs.astral.sh/uv/).

```sh
uv sync --locked          # install exact locked dependencies
uv run pytest             # run tests
uv run uvicorn netcoop.api.app:app --port 8000
```

Without a database, `/health/live` returns 200 and `/health/ready` returns 503
(`database` check fails) — that is the intended behaviour. Point
`NETCOOP_DATABASE_URL` at a PostgreSQL instance to make it ready.

## Docker Compose (development)

Requires Docker Engine with the Compose plugin (v2.24+ for `!reset` in the
production override).

```sh
cp .env.example .env      # then set POSTGRES_PASSWORD to a real secret
docker compose config
docker compose up -d --build --wait
BASE_URL=http://127.0.0.1:8000 sh scripts/smoke.sh
docker compose down       # keeps data; `down -v` DELETES the database volume
```

Only the web port is published, and only on `127.0.0.1`. PostgreSQL stays on
the internal network.

## Production (single Linux VPS)

```sh
cp .env.example .env      # set POSTGRES_PASSWORD, NETCOOP_DOMAIN, ACME_EMAIL
docker compose -f compose.yaml -f compose.production.yaml config
docker compose -f compose.yaml -f compose.production.yaml up -d --build --wait
BASE_URL=https://$NETCOOP_DOMAIN sh scripts/smoke.sh
```

In production only Caddy (ports 80/443) is public; the web container has no
published port and source code is not mounted. DNS for `NETCOOP_DOMAIN` must
point at the VPS before Caddy can obtain a certificate.

**Not yet verified:** the Compose stack has not been built or run on any
machine as of the last progress entry. Backups, migrations and authentication
are later gates (G1/G6).
