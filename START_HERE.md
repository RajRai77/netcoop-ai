# NetCoop AI — Claude Code Handoff Pack

**Status:** Architecture and requirements package; **not an implemented application**. Last prepared: 2026-10-31.

## Where to put these files

**Extract the ZIP into your Git repository root**, preserving paths. The main instruction file is `CLAUDE.md` at the **repository root**, not inside `.claude/`. Claude Code loads root `CLAUDE.md` when run from that project. `.claude/rules/*.md` provides additional instructions. `docs/` stores the detailed, durable engineering knowledge. `spec/` contains proposed machine-readable starter contracts and examples.

Expected layout (additional application files will be created during development):

```text
netcoop-ai/
├── CLAUDE.md                  # automatically loaded project instructions
├── .claude/rules/             # persistent guardrails
├── docs/                      # durable decision and design records
├── spec/                      # proposed JSON Schemas and example artifacts
├── src/                       # Claude Code will implement
├── tests/                     # Claude Code will implement
├── Dockerfile                 # Claude Code will implement
├── compose.yaml              # Claude Code will implement
├── compose.production.yaml   # Claude Code will implement
└── README.md                  # Claude Code will implement
```

Do **not** put the entire extracted package only into `.claude/`, or the root memory file will not be in the right place. If `.claude/` already exists, merge its contents without deleting local settings.

## First Claude Code session

1. Open a terminal at the repository root and run `claude`.
2. Tell Claude: **"Read CLAUDE.md, then docs/00_SOURCE_OF_TRUTH.md, docs/01_PROBLEM_REQUIREMENTS.md, docs/02_ARCHITECTURE.md, docs/03_ARCHITECTURE_DECISIONS.md, docs/10_BUILD_GATES.md, and docs/14_PROJECT_PROGRESS.md. Do not implement everything. First perform Gate 0: inspect my environment, report blockers and a minimal testable next step. Do not report success without executed checks."**
3. Keep `docs/14_PROJECT_PROGRESS.md` updated at the end of every working session; preserve the most recent passing Git commit.
4. Before implementation, cross-check this pack against the actual official PS file and organizer's sample generator if they are available in the repository.

## Three important caveats

- The JSON Schemas under `spec/` are proposed *starter specifications*, not official challenge schemas. Refine them with compatible migrations; do not silently break consumers.
- A2A, gNMI and the external benchmarking tools are optional integrations for particular layers, **not dependencies of core deterministic diagnosis**. For final rubric compliance, at least two independent functional agents must exchange real structured findings.
- No submitted scenario, telemetry value, test score, security guarantee or deployment verification is claimed to exist yet. Evidence must be produced by code and tests.

## Source references

Original organizer problem statement and Claude's earlier 25-page blueprint were supplied in the ChatGPT project. **They are separate sources from this handoff ZIP.** The authoritative constraints from the organizer are summarized in `docs/01_PROBLEM_REQUIREMENTS.md`. The blueprint was an alternative proposal; our final architecture is documented in this pack. If you have the original PDF, also place it at `references/official-problem-statement.pdf` for traceability.
