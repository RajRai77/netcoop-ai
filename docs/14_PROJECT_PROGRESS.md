# CURRENT IMPLEMENTATION STATUS — UPDATE EVERY CLAUDE CODE SESSION

**Last updated:** 2026-10-31 (Gate 1 session)
**Current state:** Evidence foundation implemented and tested **on Windows with SQLite**: NDEP models, semantic validation, counter rates, provenance/lineage, duplicate and conflict handling, finding revisions, append-only SQL ledger with migrations, minimal ingest/evidence API, CLI, cross-platform local launcher. **No diagnosis, no specialist agents, no NetCoop A2A exchange, no report generation.** Nothing has run on PostgreSQL, Docker or CI.
**Current build gate:** G1 — **implemented; SQLite-verified; PostgreSQL verification outstanding**. G0 — **partial** (Docker/CI never executed).
**Branch:** `gate0-skeleton` (local only, nothing pushed). Last green commit: see "Commits" below.
**Deployed URL:** NONE.
**Verified environment:** Windows 11 Home 10.0.26200, 12 logical CPUs, ~15.7 GB RAM. Python 3.12.10, uv 0.11.24, git 2.51.0, Node 25.6.1, SQLite 3.49.1. **No Docker, no WSL, CPU virtualization disabled in firmware, no PostgreSQL server.** Full dependency matrix: `docs/20_PLATFORM_COMPATIBILITY.md`.
**Official PS PDF:** `references/official-problem-statement.pdf` **does not exist**. Requirements rely on the summary in `docs/01_PROBLEM_REQUIREMENTS.md`.

## How to run (verified on Windows, 2026-10-31)

```text
uv sync --locked
uv run pytest                                   # 185 passed, 31 skipped (PostgreSQL variants)
uv run python scripts/run_local.py --check      # start, smoke-test (5 checks), stop
uv run python scripts/run_local.py              # serve on http://127.0.0.1:8000 until Ctrl+C
uv run netcoop --help                           # db upgrade/current/downgrade, incident create, ingest, evidence
```

## Gate 1 checklist (actual status)

| G1 item | Status | Evidence |
| --- | --- | --- |
| Pydantic models mirroring `spec/` (observation, finding, topology) + RawRecord | PASS | `tests/contracts/test_model_schema_agreement.py`: round-trip + 24 "both reject" mutations |
| Telemetry batch input contract | PASS | new `spec/telemetry-batch.schema.json` + example; validated in tests |
| Metric registry with explicit units/conversions | PASS | registry 1.1.0; refuses a registry missing a conversion factor |
| Invalid/missing units, ambiguous packet loss | PASS | `MISSING_UNIT`, `UNSUPPORTED_UNIT`; `0.02 percent` vs `0.02 ratio` -> 2 % kept distinct |
| NaN/Inf, type coercion, ranges, state/boolean strictness | PASS | `tests/normalization/test_semantics.py` |
| Timestamps (naive, date-only, epoch numbers, future, offsets, windows) | PASS | typed codes `MISSING_TIMEZONE`, `INVALID_TIMESTAMP`, `FUTURE_TIMESTAMP`, `INVALID_WINDOW` |
| Stale observations | PASS | kept, flagged `stale`, freshness `stale`; never zeroed/dropped |
| Counter resets / impossible rates / timestamp conflicts / mixed sources | PASS | `tests/normalization/test_counters.py` (rates are computed, **not yet persisted**) |
| Schema version incompatibility | PASS | `UNSUPPORTED_SCHEMA_VERSION`; duplicate JSON keys -> `MALFORMED_JSON` |
| Immutable raw records, deterministic IDs | PASS | content-hashed raw records; rejected records also retained |
| Duplicate detection (in-batch and cross-batch) | PASS | re-submission adds 0 observations |
| Record-id conflict | PASS | original kept, new content stored as rejected raw + `RECORD_ID_CONFLICT` |
| Provenance / independence | PASS | two agents on one source record = 1 lineage group; relayed copies with shared `origin_sample_id` = 1 |
| Finding traceability + superseding revisions | PASS | unknown refs refused; linear revision chain; edit-in-place refused; branching refused |
| Topology snapshots | PASS | validated, immutable; unknown subjects quarantined |
| DB-enforced append-only evidence | PASS on SQLite | UPDATE/DELETE refused on all 8 evidence tables |
| Migrations | PASS on SQLite | upgrade/downgrade/upgrade repeatable; migration matches table metadata (autogenerate diff empty) |
| Persistence across API **process** restart | PASS on SQLite | `tests/integration/test_processes.py::test_evidence_survives_api_process_restart` (real uvicorn processes) |
| Same tests on PostgreSQL | **NOT EXECUTED** | 30 parametrized storage tests + 1 health test skip without `NETCOOP_TEST_DATABASE_URL`; CI job `test-postgres` written, never run |
| CSV / vendor field-name adapters (source profiles) | **NOT IMPLEMENTED** | planned; see "Remaining" |

## Gate 0 checklist (unchanged except where noted)

| G0 item | Status |
| --- | --- |
| Python env, uv lock, pytest, layout, health endpoints, placeholder UI, `.env.example`, README | PASS (local) |
| Dockerfile / compose / Caddy | WRITTEN, NEVER BUILT. Updated this session: image ships `spec/`, runs `netcoop db upgrade` before uvicorn; production compose requires `NETCOOP_API_TOKEN` |
| Wheel packaging used by the image | PASS (local): wheel contains `netcoop/_spec/*` and migrations; fresh venv install ran `netcoop db upgrade` using packaged spec |
| `scripts/smoke.sh` | PASS against a local uvicorn + SQLite (6/6 checks). **Never run against Compose.** |
| CI (`test-linux`, `test-windows`, `test-postgres`, `compose-smoke`) | WRITTEN, NEVER RUN (needs a push; not authorized) |
| `docker compose up` + health | **BLOCKED** (no Docker locally) |

## A2A early compatibility check

- `a2a-sdk[http-server]==1.3.0` pinned (`>=1.3,<1.4` in pyproject, exact in `uv.lock`).
- `src/netcoop/interop/a2a_probe.py` is a **probe, not a NetCoop agent**: it returns a hash and field types and does no diagnosis.
- Verified on Windows: agent card served at `/.well-known/agent-card.json`; JSON-RPC `SendMessage` (header `A2A-Version: 1.0`) between two OS processes; SHA-256 of the sent text matched the server's receipt; uint64-max integer preserved as int.
- Finding: A2A `data` parts carry numbers as protobuf doubles (ints become floats, >2^53 loses precision). Gate 4 must pick a wire encoding that keeps NDEP numbers exact (text/JSON part, or schema-aware decoding). Recorded as an open question.
- Evidence contracts (`netcoop.evidence`) do not import A2A, HTTP or DB code.

## Session log

```text
Date/time: 2026-10-31 (Gate 1 session)
Git branch / commits: gate0-skeleton; 4a641b8 (G0 skeleton), 2829064 (G1 evidence/ledger), + final G1 commit (see git log)
Current gate and exact status: G1 implemented, SQLite-verified, PostgreSQL unverified; G0 Docker/CI still unexecuted
Files added: src/netcoop/{spec,ledger,cli,launcher}.py; src/netcoop/evidence/{errors,timeutil,registry,ids,models,
  normalize,counters,integrity}.py; src/netcoop/storage/{__init__,engine,tables,repository,sql_store,migrate}.py;
  src/netcoop/storage/migrations/{env.py,versions/0001_evidence_foundation.py}; src/netcoop/interop/a2a_probe.py;
  scripts/run_local.py; spec/telemetry-batch.schema.json; spec/examples/telemetry-batch-example.json;
  tests/{conftest.py, contracts/, normalization/, storage/, api/, integration/}; docs/20_PLATFORM_COMPATIBILITY.md
Files changed: spec/metric_registry.json (1.0.0 -> 1.1.0), src/netcoop/{config.py, api/app.py, api/health.py},
  pyproject.toml, uv.lock, Dockerfile, compose.yaml, compose.production.yaml, .env.example, scripts/smoke.sh,
  .github/workflows/ci.yml, tests/test_health.py, tests/test_spec_examples.py, README.md, docs/13, docs/15, spec/README.md
Commands actually executed: uv add (sqlalchemy, alembic, pydantic, jsonschema, a2a-sdk[http-server]); uv lock; uv sync --locked;
  uv run pytest (several times); A2A probe serve/call + raw curl JSON-RPC; scripts/run_local.py --check;
  sh scripts/smoke.sh vs local uvicorn; uv build --wheel; fresh-venv wheel install + netcoop db upgrade;
  deliberate mutation of two normalizer rules (4 tests failed as expected, then restored, all pass)
Observed results: pytest 185 passed, 31 skipped, 0 failed, 1 warning (Starlette TestClient httpx deprecation).
  launcher --check: 5/5 PASS. smoke.sh: 6/6 PASS (local, not Compose).
  Failures hit and fixed during the session: one test expectation ignored a correct SUBJECT_UNVERIFIED warning
  (test now filters reject-severity); placeholder wording broke the G0 "Not yet implemented" check (wording restored).
Test scenarios validated: none (no diagnosis). Data used: synthetic spec/examples only.
Independent A2A processes/transport checked: SDK probe only (2 processes, JSON-RPC). No NetCoop agents exist.
Docker Compose build/health/restart/backup status: NOT RUN (no Docker)
Public deployment address/status: none
Open failures/blockers: no PostgreSQL or Docker execution yet (high); CI never run (needs push authorization)
What is NOT yet implemented/verified: see "Remaining Gate 1 work" and "Not implemented" below
Next single most valuable, testable task: run CI (PostgreSQL + Compose) once a push is authorized;
  then finish G1 source-profile/CSV adapter; then Gate 2 (awaiting user authorization)
ADR/spec updates required: none to ADRs. Spec draft changes logged in docs/13 (registry 1.1.0, telemetry-batch schema).
```

## Remaining Gate 1 work

- **PostgreSQL execution** of the storage/health tests (CI `test-postgres`, or any reachable PostgreSQL via `NETCOOP_TEST_DATABASE_URL`).
- **Source-profile adapters** for incompatible field names (declared alias maps, no guessing) and **CSV** input. Not started.
- Persisting derived counter rates as evidence with multi-observation lineage (rates currently computed in memory only).
- Report revisions belong to Gate 2 (reports do not exist yet).

## Not implemented (later gates)

Diagnosis engine, specialist agents, NetCoop A2A exchange, coordinator, STEaR verification, reports, UI beyond placeholder, backups/restore, authentication beyond an optional static bearer token, rate limiting.

## Known limitations (honest)

- Independence counting relies on declared provenance (`source_id`, `record_id`, `origin_sample_id`). If two collectors relay one sample without declaring `origin_sample_id`, they are counted as two lineages. Not detected heuristically.
- Counter values must be JSON integers; exporters that emit `1200.0` are rejected (`TYPE_MISMATCH`) by design.
- Append-only triggers mean data retention/purge needs an explicit future admin migration; no delete path exists.
- API token is a single static secret; no per-user auth yet. Local default has no token and binds to 127.0.0.1.
- RSSI range -120..0 dBm and counter `max_rate_per_s` are documented sanity bounds, not device capability models.

## Session handoff template (Claude Code: REPLACE placeholders with facts after every session)

```text
Date/time:
Git branch / last passing commit:
Current gate and exact status:
Files added/changed:
Commands actually executed:
Observed results: PASS / FAIL / SKIP with relevant log excerpt:
Test scenarios validated (IDs and data provenance):
Independent A2A processes/transport checked:
Docker Compose build/health/restart/backup status:
Public deployment address/status (if any):
Open failures/blockers and risk level:
What is NOT yet implemented/verified:
Next single most valuable, testable task:
ADR/spec updates required:
```

## Guardrails for future sessions

- This file is **what is actually true**; if it says not verified, Claude may not claim otherwise.
- On a new session read this and `CLAUDE.md`, run the most relevant test to establish current state, then continue from the next gate.
- Never turn a failed test green by changing golden ground truth or inserting mocked results into real integration paths.
