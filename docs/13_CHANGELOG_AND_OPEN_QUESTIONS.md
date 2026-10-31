# Living change log and open decisions

## Baseline 2026-10-31 — documentation handoff

- Consolidated 4 sessions + deeper architecture/tool review + buildability and deployment decisions.
- Evolved from Claude's original 8-agent custom protocol proposal to three extensible specialist domains with external A2A, NDEP evidence semantics, spatio-temporal abductive engine, bounded verification, explicit abstention.
- Replaced mandatory Temporal production orchestration with a testable database-backed state machine for deployed v1; Temporal as an optional upgrade.
- Chose PostgreSQL in initial Docker Compose to avoid later production storage migration; SQLite may be used in independent unit tests only where safe.
- Chose Docker Compose on Linux VPS with HTTPS reverse proxy as final host target, with optional emulation/NetBox/Batfish separate from web startup.
- Added executable gates, deployment smoke/backup requirements, and scientific baseline/ablation evaluation.
- This pack is **documentation only**. No software/deployment/test claims are implied.

## 2026-10-31 — Gate 0 session 1 (no ADR change)

- Added Gate 0 skeleton (uv project, FastAPI health endpoints, placeholder UI, Dockerfile, Compose files, Caddy, CI). No architecture decision changed.
- Open question 1 partly answered: dev machine is Windows 11, 12 logical CPUs, ~15.7 GB RAM, **no Docker, no WSL, CPU virtualization disabled in firmware**. VPS provider/domain still unknown.
- Open question 3 partly answered: PyPI `a2a-sdk` latest is 1.3.0 (requires Python >=3.10). Not installed or pinned yet; binding/Inspector compatibility still unverified (Gate 4).

## Unresolved, must verify before irreversible implementation

1. Host OS, CPU/RAM, Docker availability, public domain and VPS provider/budget. No assumption of campus privileges.
2. Organizer-provided data generator's actual schema/units and sample scenarios; verify rather than invent aliases.
3. Pinned A2A SDK/protocol versions, exact A2A binding and Inspector compatibility.
4. Which first fault classes have ground-truth examples and discriminating observations available.
5. Freshness windows, metric ontology and detailed temporal/semantic validation rules.
6. Whether report access requires authentication in public demo, with minimum safe default.
7. Whether extra observation can be obtained in recorded scenarios or only from live-authorized tools. Avoid a planner that selects non-existent checks.
8. Concrete candidate scoring/stopping thresholds: define *before* test-tuning; assess on hold-out data.
9. Public hosting capacity/performance, privacy requirements and retention policy.

## ADR amendment log

Append each change with date, reason, impact on deployment/PS tests, migration, exact status. See ADR template in `03_ARCHITECTURE_DECISIONS.md`.
