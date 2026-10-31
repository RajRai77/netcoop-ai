# Engineering & progress continuity

- Verify each change with real command output; never write 'tests pass' or 'deployed' unless observed.
- Build APIs and typed interfaces first; isolate external dependencies behind adapters. Do not add services/frameworks without a measured requirement.
- Required rubric capabilities take precedence over optional agents, LangGraph, Temporal, Batfish, NetBox, Kubernetes, Kafka and LLM features.
- Use an actual A2A exchange between independently running specialist processes for interop proof; provide Inspector/conformance evidence if supported.
- After every session update `docs/14_PROJECT_PROGRESS.md`, `docs/13_CHANGELOG_AND_OPEN_QUESTIONS.md` (if ADR/open question changed), and any relevant acceptance checkboxes.
- Never silently edit `CLAUDE.md` or ADRs to justify an accidental implementation divergence. Document the proposed change and rationale first.
