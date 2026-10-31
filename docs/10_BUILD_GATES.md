# Build Gates — no-dead-end implementation plan

**Purpose:** Every gate produces independently verifiable software. Do not implement an advanced feature before a simpler *runnable end-to-end* path exists. A deployment smoke test stays green as the system grows. Record commands, status and evidence in `14_PROJECT_PROGRESS.md`; do not mark planned as passed.

## Gate 0 — Preflight, repo bootstrap, deployment skeleton

**Produce:** Python 3.12+ environment, `uv` lock, Git repo, test runner, source layout, Dockerfile, Compose + Postgres + FastAPI `/health/live` and `/health/ready`, `.env.example`, README install notes, CI smoke check, a placeholder UI explicitly saying not yet implemented.

**PASS:** dependency install/lock, `pytest` baseline, `docker compose config`, `docker compose up -d --build`, health requests succeed. Do not fake successful core diagnosis; placeholder route is acceptable at G0 only.

**Fallback:** If Docker unavailable, test Python-only locally, but G0 Docker pass remains **blocked** until a suitable environment is available. Do not declare deployment gate complete.

## Gate 1 — Schema, evidence and persistence

**Produce:** Pydantic models + JSON Schema (based on `spec/` drafts), unit registry, raw/normalized records, PostgreSQL migrations, versioned topology input, typed errors and provenance. Persist/retrieve one recorded observation.

**PASS:** tests for invalid/missing units, ambiguous packet-loss fraction, NaN, timestamps, stale/counter resets, schema changes; persisted evidence survives API process restart.

## Gate 2 — One truthful full vertical slice

**Produce:** deterministic analysis of ONE well-documented labeled scenario (e.g. congestion vs non-congestion), real observations, source-linked report, affected scope, support category, alternative/limitations and read-only corrective recommendations. CLI + API + minimal browser must use same domain engine.

**PASS:** `POST /api/incidents` + `GET /api/incidents/{id}/report` valid against schema; checked against ground truth; API/browser/CLI consistent; Compose smoke test passes. This is the first **runnable diagnosis** checkpoint.

## Gate 3 — Robust reasoning and honest uncertainty

**Produce:** three domain modules, fault hypothesis definitions, network graph constraints, temporal checks, independent provenance groups, missing/contradictory/unknown, bounded two-fault candidate evaluation, explicit abstention.

**PASS:** contrasting normal/congestion/interface/DNS-or-DHCP or weak Wi-Fi scenarios + ambiguity/invalid cases; report explains what is and is not known. No fabricated numeric confidence.

## Gate 4 — Real A2A interoperability and collaboration [PS critical]

**Produce:** two then three *independently running* A2A specialist services using pinned official SDK. Typed finding artifacts; trusted capability registry; timeout/error handling; coordinator combines distinct findings in one report.

**PASS:** real A2A task exchange, automated integration test, one report includes observation-linked findings from >=2 specialist agents; A2A protocol/Inspector check where supported; can identify which agent failed. This is not met by importing Python classes or playing back a canned transcript.

## Gate 5 — Bounded active evidence seeking

**Produce:** hypothesis-discrimination planner, request/response typed contract, at least one independently labeled ambiguous case with an actually obtainable new observation, budget/stopping rules, no unsafe probes.

**PASS:** original observation set yields ambiguity; planner requests a valid check; evidence record differs and is traceable; diagnosis is appropriately updated OR remains ambiguous; compare against no-verification baseline. Never manufacture the follow-up value.

## Gate 6 — Deployability, resilience and demo end-to-end

**Produce:** secured HTTPS via Caddy, functioning browser workflow, persisted audit, startup migrations, named volumes, health/readiness, backup/restore, crash/duplicate tests, README clean-server procedure. Separate benchmark lab if available.

**PASS:** clean Linux VPS deployment, browser upload -> A2A processing -> structured JSON report, Docker restart preserves case, one agent crash handled honestly, external HTTPS works, no internal ports publicly exposed, backup restore tested.

## Gate 7 — Scientific evaluation, polish, submission

**Produce:** held-out tests, baselines, ablations, interop conformance results, error analysis, benchmark report and 3–5 min recorded demo showing ACTUAL execution. README/architecture and sample files updated.

**PASS:** reported metrics recomputed from saved evaluation output; unsupported scenarios clearly listed; correct PS deliverables included; no claims unsupported by tests.

## Priority and triage when time is limited

**Never skip G2 or G4.** First prioritize PS minimum acceptance plus deployed working flow. G5 is strongest differentiator, but only after the verified baseline. Optional dependencies (Temporal, NetBox, Batfish, network emulation, LangGraph, LLM) must never block G1–G4 or the deployment smoke test. If a gate fails, isolate/revert to last good commit; fix in small steps; report blockers, not simulated success.

## Session command template

```text
Current gate:
Last passing commit:
Files to change:
Expected behaviour:
Positive tests:
Negative tests:
Actual executed commands and results:
Docker health status:
Fallback if blocked:
What is still unverified:
```
