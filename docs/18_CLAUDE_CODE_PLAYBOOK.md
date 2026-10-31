# Claude Code — repeatable work protocol

The repository root `CLAUDE.md` is automatic project memory. Detailed docs are read on demand. **Do not paste entire huge docs into every prompt**. Use specific references and preserve test evidence.

## FIRST session prompt (copy)

> Read `CLAUDE.md`, `docs/00_SOURCE_OF_TRUTH.md`, `docs/01_PROBLEM_REQUIREMENTS.md`, `docs/02_ARCHITECTURE.md`, `docs/03_ARCHITECTURE_DECISIONS.md`, `docs/10_BUILD_GATES.md`, and `docs/14_PROJECT_PROGRESS.md`. Do not generate the whole system. Inspect local OS, Python, Docker, Node (if needed), git, available organizer files, and A2A SDK compatibility. Propose Gate 0 smallest testable plan and commands. Execute Gate 0 only after verifying dependencies, then record actual outcomes and update `docs/14_PROJECT_PROGRESS.md`. Never claim tests passed without running them.

## Subsequent session prompt (copy)

> Read `CLAUDE.md` and `docs/14_PROJECT_PROGRESS.md`, run the fastest relevant existing smoke test and identify the next unfinished gate in `docs/10_BUILD_GATES.md`. Implement only that gate's smallest testable slice. Respect the relevant contracts, A2A boundaries and deployability. Execute positive and negative tests. At end update progress with commands/results, state exact unverified items, and preserve last green Git commit.

## When a surprising dependency fails

> Do not retry blindly or replace the architecture with mocks. Identify failing command/versions, scope impact, compatibility evidence, and propose smallest safe fallback from `docs/11_RISKS_AND_FALLBACKS.md`. Retain core tests. If an ADR needs amendment, document it first.

## Before pushing/deploying

> Run all tests, schema checks, dependency lock checks, `docker compose config`, full clean environment start, A2A integration exchange, API JSON report smoke, restart persistence and security exposure checks. Record *actual* results. Do not deploy secret-filled files or tell me the project is production-ready unless observed.

## At the end of EVERY session

> Update `docs/14_PROJECT_PROGRESS.md` with Git commit, files changed, real commands/results, current gate, open issues and next testable step. Update ADR log only if choices changed. Do not rewrite ground-truth fixtures for implementation convenience.

## Useful optional slash prompt organization

These prompts are ordinary Markdown files, not guaranteed Claude Code slash commands. A user can paste them, or promote to an official Claude Code skill once its installed version and syntax are verified.
