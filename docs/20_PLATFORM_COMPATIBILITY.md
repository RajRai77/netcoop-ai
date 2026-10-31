# Platform compatibility matrix (Gates 1–4)

**Policy (user directive, 2026-10-31):** the full diagnostic application must run natively on Windows wherever its dependencies allow. Docker, WSL2 and virtualization are **not** prerequisites for local development. Linux-only tools are isolated behind adapters and exercised in Linux CI or a remote/VPS environment. Nothing is deleted or replaced by a weaker substitute; anything not executed is marked unverified.

**Legend:** **V-Win** = installed and exercised by tests on the dev machine (Windows 11, Python 3.12.10, 2026-10-31). **PyPI** = only package metadata checked (pure-Python wheel / Windows wheel exists); not installed or run. **Unverified** = not checked.

## Core application (required for the local recorded-data workflow)

| Component / version | Role | Native Windows | Linux-only? | External service | Test environment | Status / risk |
| --- | --- | --- | --- | --- | --- | --- |
| Python 3.12.10, uv 0.11.24 | runtime, lockfile | yes | no | no | Win (local), Linux + Windows CI (written, not run) | V-Win |
| FastAPI 0.162.0, uvicorn 0.54.0 | API, process server | yes (asyncio loop; `uvloop` not installed on Windows) | no | no | Win local; Linux in Docker | V-Win. Graceful stop on Windows via CTRL_BREAK; uvicorn exits with code 3 after a clean shutdown (re-raised SIGBREAK) |
| Pydantic 2.14.2, jsonschema 4.26.0 | NDEP contracts | yes | no | no | Win | V-Win |
| SQLAlchemy 2.1.6, Alembic 1.20.1 | single repository implementation + migrations | yes | no | no | Win (SQLite) | V-Win on SQLite |
| SQLite 3.49.1 (stdlib) | local persistence | yes | no | no | Win | V-Win, including append-only triggers |
| PostgreSQL 17 + psycopg 3.3.6 (binary) | deployed persistence | client yes (installed); server not installed locally | no (server runs on Windows too, not used here) | yes | Linux CI service container (`test-postgres` job) | **psycopg import only on Win. No PostgreSQL test has executed anywhere yet.** |
| a2a-sdk 1.3.0 `[http-server]` (+ protobuf 7.36.2, sse-starlette 3.6.0) | inter-agent transport | yes | no | no | Win: 3 specialist processes + coordinator on localhost; Linux: Compose containers (CI) | V-Win: card discovery, bearer auth, JSON-RPC `SendMessage` -> Task + artifact, exact-number round trip, impersonation refusal, crash handling (`tests/integration/test_a2a_agents.py`). gRPC binding not installed. |
| networkx 3.7 | topology impact scope | yes (pure Python) | no | no | Win + Linux CI | V-Win (`tests/normalization/test_adapters_and_topology.py`) |
| Local launcher `scripts/run_local.py` | starts/stops 3 agents + web, port checks, per-run token, parent watchdog | yes | no | no | Win (+ Windows CI job) | V-Win (`--check` full A2A diagnosis, busy port, bad DB URL, children exit after launcher hard-kill) |

## Optional integrations (must not block core startup)

| Component | Role | Native Windows | Linux-only? | Equivalent / isolation | Test environment | Status / risk |
| --- | --- | --- | --- | --- | --- | --- |
| Docker Engine + Compose v2.24+ | container deployment | not available on this machine (virtualization disabled) | Linux target | Python-native launcher locally; Compose in GitHub Actions `compose-smoke` | Ubuntu CI / VPS | Files written; **never executed** |
| Caddy 2.10 | HTTPS reverse proxy | (cross-platform upstream; unverified) | used only in Linux production compose | none needed locally (localhost only) | VPS | Unverified |
| pygnmi 0.8.15 (gNMI client) | OpenConfig/gNMI telemetry adapter | PyPI: pure Python; depends on grpcio (Windows wheels on PyPI for 1.85.1) | no | behind telemetry-source adapter | needs a gNMI target (lab/authorized device) | PyPI only. No gNMI target available. |
| gNMIc (Go CLI) | alternative gNMI collector | Unverified | Unverified | prefer pygnmi in-process; gNMIc optional | Linux CI/lab | Unverified |
| pysnmp 7.1.30 | SNMP adapter | PyPI: pure Python | no | behind adapter | needs SNMP agent | PyPI only |
| pybatfish (client) | modeled forwarding (optional) | PyPI: pure Python client | **Batfish server runs as a Java service, normally in Docker** | client behind adapter; server remote/Linux | Linux CI/remote | Server unavailable locally; optional |
| pynetbox 7.9.0 | intended-state inventory (optional) | PyPI: pure Python | NetBox server is an external service | adapter; NetBox is never forwarding truth | remote NetBox | PyPI only |
| Containerlab, SONiC images | emulated fault labs for evaluation | **no** | **yes** (Linux, Docker, privileged networking) | none equivalent on Windows; do not substitute | separate Linux lab host | Not required for app startup; evaluation capability preserved as unverified |
| NetOpsBench | benchmark scenarios | Unverified | likely Linux | recorded/organizer fixtures instead | Linux lab | Unverified |
| Temporal | durable workflow (deferred, ADR-006) | — | — | DB-backed coordinator | — | Not planned for v1 |

## Known platform differences (handled explicitly)

- **Process stop:** Windows has no SIGTERM for console children. The launcher starts children in a new process group and sends `CTRL_BREAK_EVENT`; POSIX uses `SIGTERM` to the process group. Both fall back to kill after 10 s.
- **Port checks:** Windows uses `SO_EXCLUSIVEADDRUSE` so a port held by another process is detected.
- **Line endings:** `.gitattributes` forces LF so shell scripts and Dockerfiles work on Linux after a Windows checkout.
- **SQLite vs PostgreSQL:** same SQLAlchemy code and the same migration. Differences: append-only triggers are dialect-specific (SQLite `RAISE(ABORT)`; PostgreSQL PL/pgSQL function plus a TRUNCATE trigger); SQLite needs `PRAGMA foreign_keys=ON` per connection (set in `engine.py`); partial unique index uses `sqlite_where`/`postgresql_where`. SQLite results do **not** prove PostgreSQL behavior; the parametrized storage tests run on PostgreSQL only in CI.
- **A2A numbers:** A2A structured `data` parts use `google.protobuf.Value` (doubles), so integers come back as floats and values above 2^53 lose precision. The probe sends NDEP JSON as a text part and verified a byte-exact SHA-256 match with a uint64-max counter. The Gate 4 wire choice must keep exact numeric fidelity; see `docs/13` open questions.

## Verification still owed

1. Push to GitHub so `test-linux`, `test-windows`, `test-postgres`, `compose-smoke` run (needs user authorization).
2. Real PostgreSQL run of all storage tests (30 currently skipped locally).
3. Docker build, Compose health, restart persistence, and Caddy TLS (Gate 0/6).
