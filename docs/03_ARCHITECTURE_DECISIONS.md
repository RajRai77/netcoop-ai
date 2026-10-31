# Architecture Decision Records (ADR) — version 2.1 baseline

**Process:** These choices were made in four brainstorming sessions and subsequent deep-research/buildability/deployment reviews. `accepted for current implementation` does not mean tested or independently verified. If replacing a decision, add an ADR amendment rather than quietly rewriting history.

| ID | Decision | Status | Important boundary |
| --- | --- | --- | --- |
| ADR-001 | A2A for independent agent interactions; NDEP (JSON Schema + domain semantics) for evidence; OpenConfig/gNMI where available for telemetry | Accepted baseline | Three different layers; A2A isn't data durability or telemetry collection |
| ADR-002 | Topology-/dependency-/temporal-constrained abductive diagnosis, bounded evidence seeking, competing and multi-fault hypotheses, abstention | Accepted research direction | Scoring and novelty unproven; heuristic support isn't probability |
| ADR-003 | Federated specialist roles with case coordinator; authoritative evidence ledger; actual structured challenge/response | Accepted | No agent voting, arbitrary LLM conversations, or mandatory fixed number of agents |
| ADR-004 | Versioned observations/findings/snapshots, safety, recovery, reproducible benchmark/baseline/ablation tests | Accepted | Separate diagnostic correctness from runtime uptime |
| ADR-005 | Docker Compose on one Linux VPS; public HTTPS entry, private internal services, persistent data, smoke test and documentation | Accepted deployment target | External emulation and optional network tools don't boot with web core |
| ADR-006 | Modular diagnostic core first; 3 core specialists; DB-backed coordinator for deployed v1; optional Temporal later; optional NetBox/Batfish/lab; PostgreSQL in Compose | Accepted implementation baseline | Real A2A exchanges required before final compliance claims |

## Selected/rejected/conditional decisions

| Domain | Selected NOW | Deferred/conditional | Rejected as default |
| --- | --- | --- | --- |
| Language/test | Python 3.12+, uv, pytest, Pydantic, JSON Schema | Other-language A2A interoperability tests | Entire codebase in LLM prompts without tests |
| Agent transport | Pinned official A2A SDK, one compatible HTTP binding | Additional bindings, MCP tool integration | Invented full substitute protocol NCP/1.0 |
| Evidence | NDEP domain schema, deterministic units, raw/normalized/finding separation | gNMI YANG identity mappings, external evidence APIs | Unvalidated free-text telemetry |
| Coordinator | Small DB-persisted explicit state machine | Temporal after real resilience need | Mandatory Temporal production cluster from first build |
| Storage | PostgreSQL container + migrations and backups | SQLite isolated unit test backend | In-memory-only production evidence |
| Topology | NetworkX + supplied/versioned snapshots + observed paths | NetBox, Batfish | NetBox as actual forwarding truth |
| Agents | Performance, Infrastructure, Connectivity/Services | Wireless or DNS/DHCP specialized plugin | 8 agents just for appearance |
| Inference | Constraint/coverage ranking with contradiction and uncertainty | Calibrated model after independent labels | Invented posterior % or single tree ancestor |
| Evaluation | Supplied/organizer fixtures, fault injection, baseline/ablation | Containerlab/NetOpsBench if supported | Self-generated training/test twins and unsupported win claims |
| Interface | FastAPI + minimal browser UI + CLI | Streamlit/React if compelling UX need | UI before working diagnosis |

## Why ADR-006 revises earlier design

Earlier Session 3 endorsed Temporal and 5 specialists in the **target architecture**. Deep-research/buildability review exposed unnecessary initial integration risk. Target is now **3 core specialist domains + extension**, **DB-backed durable coordinator with an upgrade port for Temporal**, and **Postgres in the deployed Compose stack from first deploy**. This is a conscious revision, not a lost decision.

Earlier discussions suggested SQLite first and PostgreSQL later. To avoid migration surprise, prefer Postgres from first Compose-based vertical slice, while keeping lightweight isolated SQLite tests only if needed. Do not maintain two divergent production storage implementations.

## Architecture change template

```text
ADR amendment ID:
Date / author:
Current design / problem:
Alternatives and evidence:
New choice / why:
Impact on PS, safety, deployment, tests, external schema compatibility:
Migration + rollback plan:
Approval / verification status:
```
