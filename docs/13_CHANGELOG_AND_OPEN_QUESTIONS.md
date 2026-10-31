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

## 2026-10-31 — Gate 1 session (no ADR change)

- **User decisions recorded (latest explicit direction, authority level 2):** one canonical implementation; Windows-native local development without Docker/WSL; SQLite for local use behind the same repository abstraction, PostgreSQL verified separately in Linux CI; Docker/Compose maintained and executed in GitHub Actions; no Lite version. This is consistent with ADR-006 ("SQLite only as a local fallback if explicitly supported"): it is now explicitly supported, and there is still only **one** storage implementation (SQLAlchemy Core, one Alembic migration), not two divergent ones.
- Dependencies added: SQLAlchemy 2.1.6, Alembic 1.20.1, Pydantic 2.14.2 (explicit), jsonschema 4.26.0 (now runtime), a2a-sdk 1.3.0 `[http-server]` (pinned via lock; compatibility probe only).
- **Spec draft changes (not ADR changes):** `metric_registry.json` 1.0.0 -> 1.1.0: added `unit_aliases` (spelling only), `conversions` (explicit factors), `allowed_kinds` (replaces single `kind`), `value_type`, `freshness_policy`, `max_rate_per_s` for counters, metrics `memory_utilization`, `interface_errors`, `queue_drops`, unit `Gbit/s`, explicit `ratio` unit for `packet_loss`, RSSI bounds -120..0 dBm. New `telemetry-batch.schema.json` 1.0.0 (raw measurement submission envelope). Observation/finding/topology schemas unchanged (still 1.0.0).
- Batch `data_mode` must equal the incident's `data_mode` (`DATA_MODE_MISMATCH`), so modes cannot be mixed silently. Revisit if mixed-mode incidents are needed.
- Open question 3 updated: a2a-sdk 1.3.0 JSON-RPC binding works on Windows between two processes (probe). gRPC binding not installed. Inspector not tried.

## 2026-10-31 — Full implementation session (Phases A-H; no ADR change)

Architecture unchanged (ADR-001..006). Implementation decisions recorded here:

- **Spec additions (backward-compatible, draft):** metric registry 1.2.0 (`interface_status`); topology 1.1.0 (optional node `role`, `label`, `service_kind`; link `from_interface`/`to_interface`); report 1.1.0 (optional `root_causes`, `hypotheses`, `verification`, `coverage`, `agent_contributions`, `decision_basis`, `transport`, `explanation`, ...; all 1.0.0 required fields unchanged); scenario-manifest 1.1.0 (`archive_file`, `reference_time`, `telemetry_profile`, `split`); new `source-profile.schema.json` (declared vendor mappings incl. `empty_cell`), `agent-task.schema.json`, `agent-result.schema.json`.
- **A2A wire encoding (open question 10 resolved):** NDEP JSON as an A2A text part with media type `application/vnd.netcoop.ndep+json`; data parts rejected because protobuf `Value` loses integer precision. Verified by test.
- **Freshness reference:** incidents carry an optional declared `reference_time` (capture time of a recorded replay); staleness/future checks use it, ingestion time is still recorded truthfully.
- **Support rule:** `high_support` requires >=2 independent *sources* (sources sharing a sample lineage are merged), not merely 2 samples.
- **No specialist completed a task -> `operational_error`** (a system failure, not a network conclusion).
- **Model fixes made after dev-set failures (disclosed in docs/21):** DNS/DHCP faults are localized only to services of the matching `service_kind`; interface degradation is contradicted by a fresh normal reading of any of its error counters (`signature_contradiction: any_absent`); symptoms no surviving hypothesis can explain yield `unknown_fault` when nothing is confirmed.
- **Label hygiene:** scenario manifests no longer embed the generator spec (it contained the injected faults). Labels live only in `ground_truth.json`, which no diagnosis code reads.
- **Knowledge freeze** for evaluation at commit `20b551b` (fingerprint method fixed to canonical JSON in `2ff9bca`); held-out set generated afterwards and not committed (52 MB; deterministic regeneration).
- Dependencies added: networkx 3.7 (pure Python).

New open questions:
13. Live read-only collectors (gNMI/SNMP) for `read_only` challenges are not implemented; only `recorded_replay`.
14. Healthy verdicts are limited to monitored domains; should missing domains (e.g. no DNS monitor) block `healthy`?
15. Independent (organizer or lab) labeled data is still needed for a non-self-referential accuracy claim.

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
10. **(RESOLVED 2026-10-31: JSON text part, see docs/24)** Gate 4 A2A wire encoding for NDEP artifacts. A2A `data` parts are protobuf `Value` (doubles): ints become floats and integers >2^53 lose precision. Options: send NDEP JSON as a text part with media type `application/vnd.netcoop.ndep+json` (exact; verified in probe), or `data` part plus schema-aware decoding (lossy for large counters). Decide before Gate 4.
11. Retention/purge policy vs append-only triggers: needs a deliberate admin migration path if deletion is ever required.
12. Should observations relayed by different collectors without a shared `origin_sample_id` be heuristically flagged as possible duplicates?

## ADR amendment log

Append each change with date, reason, impact on deployment/PS tests, migration, exact status. See ADR template in `03_ARCHITECTURE_DECISIONS.md`.
