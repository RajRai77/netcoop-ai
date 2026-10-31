# Source of truth, status, and conflict resolution

## Status

This is an implementation specification/handoff package, **not proof of a working system**. Prepared after four architecture brainstorming sessions, an open-source alternatives review, a deployment discussion and a buildability review. Proposals are explicitly labeled.

## Authority order

1. **Original hackathon organizer problem statement** (when available as PDF/text) — hard external obligations.
2. **User's explicit latest direction** — quality-first engineering, honest evidence, no fake demo, and easy public deployment.
3. **Approved ADRs** in `03_ARCHITECTURE_DECISIONS.md` — design choices; modify only by writing an ADR amendment.
4. **Contracts and acceptance tests** in `04_EVIDENCE_AND_CONTRACTS.md`, `06_AGENTS_AND_ORCHESTRATION.md`, `08_TESTING_AND_EVALUATION.md`, and `spec/`.
5. **Implementation progress** in `14_PROJECT_PROGRESS.md` — only source for *what is actually implemented and tested*.
6. Other design notes and previous brainstorms — useful context, not overriding decisions.

## Decided vs not yet decided

- **Decided (architecture):** Evidence-first, agent exchange, deterministic diagnostic core, explicit uncertainty; three core specialist domains; A2A at external agent boundary; schema-checked NDEP; independent validation; deployment via Docker Compose; audited stored evidence; baseline comparisons.
- **Selected implementation baseline (revisable with reasons):** Python, FastAPI, NetworkX, PostgreSQL Compose, DB-backed coordinator, minimal browser UI, pytest. Pin dependency versions in actual lockfile only after preflight.
- **Conditional:** OpenConfig/gNMI, NetBox, Batfish, Temporal, Containerlab/NetOpsBench, LLM, streaming infrastructure. Buildable without them.
- **Unproven:** STEaR novelty and accuracy, active verification improvement, numeric confidence calibration, performance/SLOs, readiness for internet exposure. No code or test result is implied by this pack.

## Change protocol

If design or dependencies need to change, write an amendment in `03_ARCHITECTURE_DECISIONS.md` describing the current choice, why it fails, alternatives, accepted trade-off and how the new choice still meets official PS, deployment and verification requirements. Record the change in `13_CHANGELOG_AND_OPEN_QUESTIONS.md`. Never silently adapt the architecture while coding.

## Files to read on a new Claude Code session

`CLAUDE.md` -> `docs/14_PROJECT_PROGRESS.md` -> `docs/10_BUILD_GATES.md` -> the domain-specific document for the next gate. Re-read PS/ADR/architecture if there is ambiguity. No need to paste the whole package into every prompt.
