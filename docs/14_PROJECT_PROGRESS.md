# CURRENT IMPLEMENTATION STATUS — UPDATE EVERY CLAUDE CODE SESSION

**Last updated:** 2026-10-31 (full implementation session, Phases A–H)
**Current state:** The complete workflow runs locally on Windows. Telemetry → validated evidence → 3 independent A2A specialist processes → competing hypotheses → spatio-temporal reasoning → targeted verification → evidence-backed JSON report → browser UI. No LLM is used. Data is synthetic only. **Not done:** public VPS/HTTPS deployment, backup/restore drill, live read-only collectors, recorded demo video, independent (non-self-generated) labeled data.
**Branch:** `gate0-skeleton` (pushed; user-authorized). `main` is untouched.
**Last green commit / CI:** see "CI" below (filled from the actual run).
**Deployed URL:** NONE.
**Verified environment:** Windows 11 Home 10.0.26200, 12 logical CPUs, ~15.7 GB RAM, Python 3.12.10, uv 0.11.24, Node 25.6.1, SQLite 3.49.1. No Docker/WSL/virtualization and no local PostgreSQL. Docker and PostgreSQL are exercised only in GitHub Actions.
**Official PS PDF:** `references/official-problem-statement.pdf` **does not exist**; requirements come from `docs/01_PROBLEM_REQUIREMENTS.md`.

## How to run (verified on Windows)

```text
uv sync --locked
uv run python scripts/run_local.py               # 3 A2A agents + web on http://127.0.0.1:8000
uv run python scripts/run_local.py --check       # full A2A diagnosis end to end: 11/11 PASS (observed)
uv run pytest                                    # see "Tests" for observed counts
uv run python scripts/evaluate.py                # writes eval/results/{results.json,RESULTS.md}
uv run python scripts/generate_scenarios.py [--heldout]
BASE_URL=http://127.0.0.1:8000 node tests/frontend/ui_smoke.mjs   # after `npm install` in tests/frontend
```

## Gate status (docs/10)

| Gate | Status | Evidence |
|---|---|---|
| G0 skeleton | PASS (CI) | earlier CI run 41213586252; compose now has agents (see CI) |
| G1 evidence | PASS | normalization/contract/storage tests; PostgreSQL variants in CI `test-postgres` |
| G1 carry-over: CSV + source profiles, persisted counter rates | DONE | `tests/normalization/test_adapters_and_topology.py`; S13 scenario |
| G2 first truthful vertical slice | PASS (local) | `POST /api/incidents` + `/diagnose` + `/report` schema-valid; CLI/API/UI share one engine |
| G3 robust reasoning | PASS on dev set | 17 labeled dev scenarios x {no-verification, verification}: all expectations met (`tests/inference/test_dev_scenarios.py`) |
| G4 real A2A | PASS (local) | `tests/integration/test_a2a_agents.py`: 3 agent processes; A2A results equal in-process; reports cite >=2 agents |
| G5 active evidence seeking | PASS on dev set | S09/S11 ambiguous without verification, correctly diagnosed with it; S16 stays ambiguous (no data). Compared against the no-verification baseline in the evaluation |
| G6 deployability/resilience | PARTIAL | local: crash resume, agent crash, retries, invalid artifacts, restart persistence; Compose in CI; **not done:** VPS, external HTTPS, backup/restore drill |
| G7 evaluation/submission | PARTIAL | evaluation framework + held-out set + generated results; demo script written; **video not recorded** |

## What exists (implemented and tested)

- **Evidence Fabric:**
  - NDEP models and schemas, metric registry 1.2.0 with explicit conversions only.
  - Typed rejections; stale observations flagged, unknown subjects quarantined.
  - Counter rates with reset/impossible-rate detection, persisted.
  - Content-hashed immutable raw records (rejected ones too); duplicate and conflict handling.
  - Sample lineage and independent-source counting.
  - Declared vendor CSV/JSON source profiles; finding revisions; DB-enforced append-only tables (15).
  - Migrations 0001–0002 on SQLite (local) and PostgreSQL (CI).
- **Specialists** (`src/netcoop/agents/`):
  - Performance, Infrastructure and Connectivity, each with domain detectors (persistence, transient, source conflict).
  - Connectivity adds topology scope analysis.
  - Every agent validates incoming payloads and answers verification only from authorized recorded archives (never synthesizes).
- **A2A:** a2a-sdk 1.3.0 JSON-RPC; agent cards with skills/metric tags; allowlisted discovery; bearer tokens; NDEP as exact JSON text parts; Task + artifact.
- **STEaR engine:** fault library (9 modeled faults), abductive generation over topology impact scopes (redundancy-aware), signature/contradiction/temporal checks, independent-source support, at most 2 concurrent faults, unknown-fault and abstention rules, documented lexicographic ranking.
- **Planner:** bounded discriminating checks with dedup, budget and stop reasons; NDEP challenges persisted with outcomes.
- **Coordinator:**
  - DB-persisted workflow events and A2A task attempts (request/response hashes, A2A task/message ids, raw artifact).
  - Retries with logical task ids; validation of artifacts (spoofing, foreign refs, wrong task).
  - Snapshots and report revisions; operational-error path; crash resume on startup.
- **API/CLI/UI:**
  - FastAPI endpoints (README) and the `netcoop` CLI.
  - Vanilla-JS browser UI: history, scenarios, upload, validation view, progress, hypotheses, verification, A2A exchanges, timeline, evidence, findings, topology, report download.
- **Launcher:** Windows/Linux; 4 processes; port checks; per-run token; graceful stop; parent watchdog.
- **Deployment files:** Dockerfile (shared image), compose with 3 agent containers on an internal network, production overlay with Caddy; CI jobs `test-linux`, `test-windows`, `test-postgres`, `evaluation`, `compose-smoke`.
- **Evaluation:** baselines A/B, STEaR without verification, full, ablations; held-out generator with a knowledge-freeze fingerprint; results rendered from JSON.

## Tests (observed)

Filled in at the end of the session from actual commands (see Session log).

## Known limitations / risks

- Synthetic data only. Generator and engine have the same authors. Dev-set results are optimistic, because two model fixes were made after dev failures (docs/21, docs/13).
- Verification uses recorded archives; `read_only` live checks answer `unavailable`.
- A `healthy` verdict covers only the monitored domains; domains with no data are reported as coverage gaps but do not block `healthy`. Open question 14.
- The UI is tested by syntax check, API endpoint checks and a jsdom DOM smoke test. There is no real-browser or visual test.
- Single-node; no HA; backup/restore not yet drilled; no public deployment.
- In-process transport exists only for tests and evaluation (reports say `transport: in-process`). The app refuses to diagnose without A2A agents unless `NETCOOP_ALLOW_IN_PROCESS_AGENTS=true`.

## Session log

Filled in at the end of the session.

## Guardrails for future sessions

- This file is **what is actually true**; if it says not verified, Claude may not claim otherwise.
- On a new session read this and `CLAUDE.md`, run `uv run pytest` and `scripts/run_local.py --check`, then continue from "Next".
- Never turn a failed test green by changing golden ground truth or inserting mocked results into real integration paths. Never tune on the held-out set; regenerate a new held-out set (new seed) after any knowledge change and report both.
