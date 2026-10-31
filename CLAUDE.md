# NetCoop AI — project instructions for Claude Code

You are implementing **NetCoop AI: an evidence-first, interoperable multi-agent network fault diagnosis system**. The user prioritizes engineering truth, scientific evaluation, reliability, and **an actually deployable working project**, not a polished fake demo. Never promise every fault can be diagnosed.

## Non-negotiable rules

1. **Read this file first.** Read `docs/00_SOURCE_OF_TRUTH.md` and `docs/14_PROJECT_PROGRESS.md` at session start. Open other documents only as relevant; do not improvise architecture or change an ADR silently.
2. **Follow the official hackathon PS** as summarized in `docs/01_PROBLEM_REQUIREMENTS.md`: functional agents collaborate, structured interoperable messages, actual multi-agent evidence fusion, robust input handling, and a **structured JSON report with cause/evidence/affected scope/confidence category/actions/limitations**.
3. **No fake evidence, fake live mode, invented benchmarks, or cosmetic agent chatter.** Every finding links to real input records. Clearly label `synthetic`, `recorded`, `emulated`, `live` and `mock` modes. Do not claim tests or deployments passed unless commands were actually executed.
4. **Maintain deployability from the first slice.** Implement real `Dockerfile`, `compose.yaml`, `compose.production.yaml`, health endpoints, env templates, persistent storage, smoke tests, and production instructions. Docker Compose on one Linux VPS is the selected target.
5. **Build in vertical slices, not all at once.** Follow `docs/10_BUILD_GATES.md`. At every gate preserve a runnable, tested, end-to-end path and create a Git checkpoint. Never break the last known-good path for optional tooling.
6. **Core diagnosis is deterministic and testable without an LLM or live network.** Specialist agents can use deterministic tools; any LLM is optional, cannot invent telemetry or override validation, and must have an offline fallback.
7. **Preserve semantics.** Reject unknown units, ambiguous fractions, stale observations, invalid schema, missing topology or impossible counter rates without silent coercion. Missing != zero; source repetition != independent corroboration.
8. **Treat root cause as hypothesis, not certainty.** Support contradictory evidence, incomplete telemetry, competing causes, unknown/multi-fault possibilities, explicit abstention. A heuristic score is **not** a calibrated probability.
9. **Agent independence must be real.** Initial goal: three specialist domains; at least two independently running A2A agents exchange typed findings and influence one diagnosis. Never replace remote exchange with a simulated transcript while claiming compliance.
10. **Security:** production network access read-only and explicitly authorized; never run privileged scans or network remediation; no hard-coded credentials; validate untrusted payloads; no secrets in Git/logs.
11. **Protocol boundaries:** A2A transports tasks/artifacts; the versioned NDEP domain contract describes diagnostic evidence; OpenConfig/gNMI is only a supported telemetry source. A2A is not the durable evidence ledger.
12. **After each work session**, update `docs/14_PROJECT_PROGRESS.md` with changed files, actual commands/results, open bugs, tested deployment state, and next gate. Do not hide red tests; report limitations honestly.

## Current architecture (ADR-001..006; see `docs/03_ARCHITECTURE_DECISIONS.md`)

- Python 3.12+; `uv` with locked dependencies; FastAPI API + a minimal browser UI; pytest; Pydantic/JSON Schema; NetworkX; a documented fault library.
- Three core specialists: **Performance**, **Infrastructure**, **Connectivity/Services**. Additional wireless or DNS/DHCP specialists can be plugged in later.
- **Evidence Fabric** normalizes telemetry with units, timestamps, provenance, versions and clear data-quality flags. Versioned append-only evidence records and topology snapshots.
- **STEaR (working name)**: spatio-temporal, topology/dependency-constrained abductive hypothesis comparison, then **bounded evidence-seeking verification** if ambiguity can be reduced by an authorized available observation. Treat this as a *hypothesis/design* requiring evaluation, not a proven new algorithm.
- Use A2A SDK with a pinned version for external agent interfaces. Keep a local `AgentPort` for deterministic unit tests; do not claim local invocation meets inter-agent integration requirements.
- **PostgreSQL for the deployed Compose stack from the start**, SQL migrations, volumes/backups; SQLite only as a separate test/local fallback if explicitly supported. Durable DB-backed coordinator for deployable v1; Temporal optional later, **not required to start**.
- NetBox, Batfish, gNMIc, Containerlab, NetOpsBench, LangGraph and an LLM are optional adapters/tools, not boot-critical services.

## Work loop

- Start: inspect files and `docs/14_PROJECT_PROGRESS.md`; identify the next failed acceptance gate.
- Before changing code: state a small implementation plan and the commands you will run.
- Implement: one contract or vertical slice; add negative/edge-case tests; execute them.
- Verify: `pytest`, schema validation, and when relevant `docker compose config`, health and E2E smoke test. Do not invent results.
- Finish: summarize implementation, actual output, blockers, and update progress/ADR if a decision changed.

## Reading map

- `docs/01_PROBLEM_REQUIREMENTS.md` — original PS requirements and judge checklist
- `docs/02_ARCHITECTURE.md` — logical/physical components and trust boundaries
- `docs/03_ARCHITECTURE_DECISIONS.md` — selected/rejected/deferred tech decisions
- `docs/04_EVIDENCE_AND_CONTRACTS.md` — units, schema and reporting invariants
- `docs/05_DIAGNOSTIC_ENGINE.md` — hypothesis engine and verification planner
- `docs/06_AGENTS_AND_ORCHESTRATION.md` — A2A roles, workflow and conflicts
- `docs/08_TESTING_AND_EVALUATION.md` — scientific/quality gates
- `docs/09_DEPLOYMENT_AND_OPERATIONS.md` — single-server Compose, security, smoke tests
- `docs/10_BUILD_GATES.md` — exact sequence and blocking criteria
- `docs/11_RISKS_AND_FALLBACKS.md` — dependencies that must not block core
- `docs/14_PROJECT_PROGRESS.md` — session handoff/current truth

**Priority order:** correctness/safety > mandatory PS compliance > reproducible deployed vertical slice > advanced innovation > UI polish. Do not optimize to mere hackathon speed at the expense of correctness.
