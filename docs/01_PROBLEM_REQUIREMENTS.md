# Official problem statement — requirements & traceability

**Source:** user-provided *NetCoop AI — Multi-Agent Network Fault Diagnosis and Interoperability* (Agentic AI Grand Finale; IIT Bhubaneswar context). This document is a faithful engineering summary, not a replacement for the original PS.

## Goal

Develop an **interoperable multi-agent diagnostic system** whose specialized agents analyze different parts of network health, exchange structured findings, correlate evidence, identify a probable root cause and affected scope where possible, report alternatives/uncertainty and recommend corrective actions.

## Mandatory (per original PS)

- At least **two functional cooperating agents** with distinct network responsibilities; four to five are encouraged but not mandatory.
- Structured inter-agent communication with documented message formats, field meanings and units.
- Orchestrated tasks; findings from multiple agents must contribute to **one** diagnosis.
- Network fault diagnosis from provided/authorized telemetry with supporting evidence and affected devices or segments when identifiable.
- Unified report: probable cause, evidence, confidence estimate **or clearly defined category**, alternatives/uncertainty as relevant, limitations and practical recommended actions.
- Basic validation/error handling: malformed, missing or incompatible data must be handled and errors reported clearly.
- Reproducible test cases, sample inputs, code, setup instructions and a demo.
- **A structured JSON diagnostic report is required**. Markdown or dashboard is extra.

## Optional per PS (not mandatory)

MCP, HITL, persistent workflows/pause-resume, dashboard, automated remediation. CLI is sufficient in original PS; **publicly deployed UI is the user's additional goal**. Production campus access is NOT required. Authorized synthetic, organizer-supplied or lab data is acceptable if labeled honestly. Automated changes to campus infrastructure are forbidden without explicit permission.

## Example fault cases from PS

Normal; congestion/high utilization/queue drops; weak Wi-Fi; Ethernet/interface errors; DNS/DHCP failures; telemetry interoperability failure (units, aliases, schema, missing fields). Also test CPU overload, upstream device impact, multiple faults, unknown faults and agent failure as engineering extensions.

## Scoring rubric — exact weights

| Criterion | Weight |
| --- | ---: |
| Agent interoperability and protocol design | 30% |
| Diagnostic accuracy and evidence quality | 25% |
| Agent orchestration and conflict resolution | 15% |
| Robustness to missing/inconsistent/incompatible data | 15% |
| Innovation, usability and extensibility | 10% |
| Code quality, documentation and demonstration | 5% |

## Original minimum acceptance criteria — release blockers

1. >=2 distinct collaborating agents.
2. Structured inter-agent communication.
3. Evidence from multiple agents contributes to one diagnosis.
4. At least one malformed, missing or incompatible input handled.
5. Report with probable cause, supporting evidence, recommended action.
6. Reproducible run using supplied or documented test data.

## Official deliverables

GitHub source repo with setup and tests; README describing architecture and protocol; sample data/scenarios; **3–5 minute demo recording**; working runnable CLI or dashboard. The user also requires a publicly deployable web experience.

## Minimum compliance proof

Map each acceptance criterion to a tested command/artifact in `08_TESTING_AND_EVALUATION.md`, e.g. A2A integration test transcript, schema conformance test, actual multi-agent evidence links, malformed-input test, JSON report schema test and clean-run instructions. Do **not** claim A2A implementation alone proves meaningful collaboration.
