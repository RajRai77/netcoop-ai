# CURRENT IMPLEMENTATION STATUS — UPDATE EVERY CLAUDE CODE SESSION

**Last updated:** 2026-11-01 (backend completion checkpoint)
**State:** Backend complete for the approved local/CI scope. Telemetry → validated evidence → 3 independent A2A specialist processes → competing hypotheses → spatio-temporal, topology-aware reasoning → bounded evidence-seeking verification → evidence-backed JSON report → API/SSE/UI. No LLM is used, and all data is synthetic. **Ready for frontend integration** (see "Readiness").
**Branch:** `gate0-skeleton` (pushed, user-authorized; `main` untouched). Latest commit and CI: see "CI".
**Deployed URL:** NONE. VPS/HTTPS deployment is out of the current scope (owner decision).
**Environment:** Windows 11 (no Docker/WSL/virtualization), Python 3.12.10, uv 0.11.24. PostgreSQL and Docker run only in GitHub Actions.
**Official PS PDF:** `references/official-problem-statement.pdf` does not exist; requirements come from `docs/01`.

## Commands (verified)

```text
uv sync --locked
uv run python scripts/run_local.py [--port 8000] [--cors-origin http://localhost:5173]   # 3 A2A agents + web
uv run python scripts/run_local.py --check          # full A2A diagnosis smoke, 11 checks
uv run pytest                                       # 294 passed, 99 skipped (PostgreSQL variants), 0 failed (2026-11-01)
BASE_URL=http://127.0.0.1:8000 sh scripts/smoke.sh  # also used against Compose in CI
uv run python scripts/evaluate.py --sets heldout-v3 --methods A_threshold B_centralized C_stear_noverify D_full
uv run python scripts/export_openapi.py             # docs/openapi.json
```

## Backend architecture completion matrix

V = implemented and verified by executed tests. U = implemented, not verified in that environment. P = partial. M = missing / out of scope.

| Capability | Status | Evidence |
|---|---|---|
| NDEP contracts (observation, finding, challenge, topology 1.1, report 1.1, telemetry batch, source profile, agent task/result) | V | `tests/contracts/`, `tests/test_spec_examples.py` |
| Semantic validation: units/conversions, NaN, ranges, kinds, timestamps, staleness vs declared reference time, unknown subjects | V | `tests/normalization/test_semantics.py` |
| JSON + CSV/vendor adapters via declared source profiles (no inference) | V | `tests/normalization/test_adapters_and_topology.py`, scenario S13 |
| Provenance: immutable raw records, lineage, independent-source counting, duplicates/conflicts, finding revisions | V | `tests/storage/test_ledger.py`, `tests/inference/test_engine.py` |
| Counter rates with reset / impossible-rate detection, persisted | V | `tests/normalization/test_counters.py` |
| Append-only evidence ledger, 15 tables with DB triggers; migrations 0001–0002 | V SQLite, V PostgreSQL (CI) | `test_append_only_tables_reject_update_and_delete`, CI `test-postgres` |
| Three independent A2A specialists (a2a-sdk 1.3.0 JSON-RPC, NDEP exact-JSON text parts, bearer auth) | V | `tests/integration/test_a2a_agents.py` (A2A == in-process semantics, exact uint64 round trip, token, impersonation, protocol version, crash) |
| Discovery allowlist, timeouts, retries (same logical task id), invalid/spoofed/old-schema artifacts, no-agent → operational_error | V | `tests/resilience/test_coordinator_failures.py` |
| STEaR: abductive hypotheses over topology impact scope (redundancy-aware), temporal checks, contradictions, unknown fault, ≤2 concurrent faults, abstention, identifiability rule, coverage-aware healthy | V | `tests/inference/` (dev scenarios S00–S20 × {verification on/off}), held-out v1–v3 |
| Bounded verification planner (recorded_replay archives; never synthesizes) | V | S09/S11/S19 (resolved), S16/S20 (stay ambiguous), `tests/agents/test_runtime.py` |
| `read_only` live verification (gNMI/SNMP collectors) | M (optional) | agents answer `unavailable`; adapter point documented in docs/20 |
| Persistent workflow events, A2A task attempts, challenges, snapshots, report revisions, crash resume | V | `test_interrupted_run_is_resumed_on_startup`, `test_rerun_creates_new_revision_and_keeps_old`, `test_evidence_survives_api_process_restart` |
| Structured JSON report (schema-validated) + text report + recommendations | V | every scenario test validates against `spec/report.schema.json` |
| REST API, SSE stream, opt-in CORS, request-size guard, bearer token, OpenAPI export, evaluations API | V | `tests/api/` |
| Browser UI (built-in vanilla JS) | V (jsdom smoke) | `tests/frontend/ui_smoke.mjs` 13/13. Separate React frontend: being built by another agent |
| Windows single-command start, port checks, per-run token, graceful stop, orphan prevention | V | `tests/integration/test_processes.py`, CI `test-windows` |
| PostgreSQL backend | V (CI) | CI `test-postgres` |
| Docker Compose: 3 agent containers, internal networks, only web published, restart persistence, DB-stop readiness | V (CI) | CI `compose-smoke` |
| Backup/restore (pg_dump/pg_restore onto a fresh volume; SQLite online backup) | V SQLite locally; PostgreSQL drill in CI | see "CI" for the run containing the drill |
| Production overlay (Caddy HTTPS, read-only containers) | U | `compose -f … -f compose.production.yaml config` validated in CI; never started; no domain/VPS |
| Rate limiting, per-user auth, retention/purge | M | single static API token only; documented limitation |
| MCP, LLM narration, HITL approval | M (optional per PS) | not required; diagnosis works without an LLM |
| Scientific evaluation (baselines, ablations, held-out v1/v2/v3) | V | `eval/results-frozen-2ff9bca`, `eval/results-heldout-v2`, `eval/results-heldout-v3` (+ `PROVENANCE.md`) |
| Demo video | M | script in docs/22; to be recorded after React integration |

## Evaluation (generated files; synthetic, same-author generator — not independent benchmarks)

| set | knowledge | D_full acceptable | D confident-wrong | D high-support-wrong | C_noverify acceptable | threshold A acceptable |
|---|---|---|---|---|---|---|
| v1 | fault-library/1 | 49/60 | 3/60 | 3/60 | 51/60 | 20/60 |
| v2 | fault-library/2 | 53/60 | 6/60 | 0/60 | 55/60 | 18/60 |
| v3 | fault-library/3 | 59/60 | 1/60 | 0/60 | 57/60 | 22/60 |

v3 provenance: `95e3e6e` plus uncommitted persistence-only changes. A targeted replay from a clean worktree matched 44/44 cases; 49 scenarios were not replayed (`eval/results-heldout-v3/PROVENANCE.md`). v1/v2 AP-down annotation caveat: see docs/21.

## Unresolved diagnosis weaknesses

- Unmodeled faults come out as `ambiguous`, never `unknown_fault` (v3: 0/4 detected as unknown), because some modeled hypothesis remains unverifiable.
- Compound faults: second-fault recall remains limited (v3 1/2; V03-014 missed a subtle wireless interference).
- `healthy` needs coverage of every declared domain. Without verification data, healthy networks with unmonitored DNS/DHCP/wireless are reported as `insufficient_evidence` (by design).
- Thresholds are engineering defaults; the fault library covers 9 fault types.

## Test / CI evidence

- Local full regression 2026-11-01: **294 passed, 99 skipped, 0 failed** (Windows, SQLite). One earlier full run had one intermittent failure under heavy load that did not reproduce in isolation or in the next full run (test not identified).
- Real A2A workflow executed and recorded in docs/25 (S19: AP-down resolved by one A2A verification check).
- CI: see the "CI" section, filled in from the run for the final commit.

## CI

(updated after the push of this checkpoint)

## Readiness

READY FOR FRONTEND INTEGRATION — contract in `docs/25_FRONTEND_INTEGRATION.md` and `docs/openapi.json`, plus a recorded real workflow. Conditions: run the backend with `--cors-origin <frontend origin>` (or a Vite proxy); show `data_mode`, `limitations` and the support category (not a probability).

## Repository hygiene note

Commit `538e59c` (pushed) unintentionally included part of the separate `frontend/` work via `git add -A`. History is not rewritten; the owner decides. Since then, backend commits stage explicit paths only.

## Guardrails for future sessions

- This file is **what is actually true**; if it says not verified, Claude may not claim otherwise.
- Never tune on a held-out set; after a knowledge change, freeze, generate a new seed, evaluate, and keep old results.
- Never stage `frontend/` (owned by another agent). Never use `git add -A`.
