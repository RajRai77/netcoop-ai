# Testing, rubric verification, scientific evaluation

**No checks have been executed merely by creating this document.** Record actual commands/results in `14_PROJECT_PROGRESS.md`.

## Automated test groups (suggested paths)

| Group | Required assertions |
| --- | --- |
| `tests/contracts/` | JSON Schema conformance, version conflicts, invalid units, malformed values, payload limits |
| `tests/normalization/` | Explicit unit conversion, timestamp handling, stale/counter reset, missing!=zero |
| `tests/agents/` | Domain findings, evidence refs, challenge replies, refusal when data unavailable |
| `tests/inference/` | Contradictions, provenance dedup, topology/temporal consistency, tie/abstain, bounded multi-fault |
| `tests/integration/` | >=2 separate A2A agents + coordinator + evidence store + one report |
| `tests/resilience/` | Timeout, crash, duplicate delivery, bad artifact, late result, coordinator restart |
| `tests/api/` | JSON report valid, upload restrictions, status/health, error behaviour, basic auth policy |
| `tests/deployment/` | Docker Compose config, build, health, E2E workflow, restart persistence, backup/restore |
| `tests/benchmark/` | Held-out scenario evaluation, baselines, confidence/coverage and efficiency analysis |

## Original PS acceptance traceability (ALL mandatory)

| Requirement | Proof to collect | Pass gate |
| --- | --- | --- |
| >=2 distinct collaborating agents | real A2A tasks from separate processes and distinct findings | G4 |
| Documented structured interoperability | schemas, unit registry, malformed/version test and real validated exchange | G1, G4 |
| Multi-agent evidence contributes to one diagnosis | final report references findings from >=2 agents | G4 |
| Missing/malformed/incompatible input handled | negative fixtures + typed errors + safe outcome | G2 |
| Root cause, evidence, actions in JSON | JSON Schema validated report on reproducible scenario | G2 |
| Reproducible testing/setup | one-command test + documented data origin and dependency lock | G2/G6 |

## Metrics (never invent numbers)

- Fault-type top-1 accuracy; device/link/service localization rate; top-3 candidate recall.
- Wrong-confident-decision rate, abstention coverage and selective risk; evaluate when system says `unknown` or `ambiguous`.
- Multi-fault precision/recall and unknown fault rejection; distinguish false alarm from missing coverage.
- Interop schema pass rate / semantic interpretation test correctness, agent failures and recovered incident fraction.
- Verification usefulness: fraction of initially ambiguous incidents resolved correctly by **new** evidence, number/cost of extra requests, diagnostic latency.
- Where numeric probability model actually exists: reliability plot, Brier and ECE, plus held-out calibration split. Otherwise omit numerical probability claims.
- Latency percentiles measured on selected environment/hardware; no arbitrary p95 promises.

## Mandatory comparative experiments (planned)

1. Baseline A: centralized deterministic fault signature/rule correlation.
2. Baseline B: same hypothesis engine **without** topology/temporal context.
3. Baseline C: same engine with spatial/temporal context, no active verification.
4. Full: spatial/temporal context plus active verification with equal information/tool budget.

Ablation: remove provenance grouping, drop contradiction check, disable topology, disable verification; measure change. For fairness compare initial observations, permissions and total measurement budget.

## Reliability acceptance tests (planned)

- Inject A2A timeout and duplicate artifact: no double counting and clear partial coverage.
- Restart application services: committed case history persists; reconcile incomplete tasks.
- `docker compose down` then `up`: persistent volume retains data. **Never** use `down -v` during persistence test.
- Verify backup **and restoration** to a fresh volume, not just backup command success.
- Public API should not expose DB/admin/agent ports; rejected untrusted inputs and large uploads fail safely.
- No active probe without permission; no hidden remediation actions.

## Evidence of passing

Record command, OS, dependency lock hash/commit, input scenario IDs, output artifacts, date and results. Failed or skipped tests must be explicit. Screenshots alone are not conformance evidence.
