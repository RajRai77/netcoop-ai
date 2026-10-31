# Agent interfaces, A2A and orchestrator

## Components

**Performance Agent:** latency, jitter, throughput, loss, utilization, congestion evidence; can request comparable time windows.

**Infrastructure Agent:** device CPU/memory, interface CRC/errors, state/flaps, queue drops, available AP signal/counters; can inspect related device counters.

**Connectivity & Services Agent:** affected paths, reachability, DNS/DHCP, topology and service dependencies; localizes path/service scope with explicit topology version and uncertainty.

**Case Coordinator:** determines relevant capabilities, starts tasks, waits with deadlines, records results, invokes inference, sends targeted challenges, maintains limited retries and status. It is **not** a fourth diagnostic specialist; can expose A2A client capability without pretending to be a specialist.

**Canonical local interface `AgentPort`:** `describe_capabilities()` and `investigate(case_view, request) -> structured artifact` plus optional `verify(challenge, case_view)`. Both local and A2A adapters implement identical semantics and contracts. Independent-agent integration tests must use real A2A processes.

## A2A scope

Use **official, pinned-version A2A SDK** for discovery, external task requests, status updates and structured artifacts. Return real typed finding/challenge results as A2A artifacts or structured payloads according to the pinned SDK. Version and schema compatibility must be tested; agent identity/authentication is separate from self-advertised capabilities. Do not reimplement the entire A2A transport as custom NCP. MCP may later expose diagnostic tools, but is optional.

## Task workflow (logical)

```
NEW -> VALIDATING -> DISCOVERING -> INVESTIGATING -> CORRELATING
       -> (VERIFYING -> CORRELATING)*
       -> DIAGNOSED | AMBIGUOUS | INSUFFICIENT_EVIDENCE
          | UNKNOWN_FAULT | HEALTHY | OPERATIONAL_ERROR
```

Each state transition should be persisted with incident ID, actor, timestamp, causal trigger, task IDs and evidence snapshot. Repeat verification only while an available safe check is likely to provide discriminating evidence and budget remains. Final reports reference exact evidence and topology snapshot IDs.

## Conflict taxonomy and policy

- Unit/schema conflict -> normalization adapter or typed error; never a majority vote.
- Time-window or identity mismatch -> align/resolve identities before declaring contradiction.
- Sensor disagreement -> inspect freshness, lineage and source health; optionally request independent measurement.
- Hypothesis conflict -> inference engine identifies which new observations discriminate candidates.
- Agent timeout/crash -> bounded retry with idempotency, record missing coverage, continue if safe or report operational/insufficient state.
- Evidence arrives late -> immutable new revision of case outcome, never rewrite earlier conclusion without audit record.
- Multiple simultaneous failures -> bounded multi-hypothesis evaluation, not forced single winner.

## Required tracking IDs

`incident_id`, `task_id` (logical idempotency key), `agent_id/version`, `message_id`, `artifact_id`, `finding_id`, `observation_ids`, `evidence_snapshot_id`, `topology_snapshot_id`, `trace_id`, optional `challenge_id` and `supersedes_id`.

## Retry/idempotency

Use deterministic logical task ID per incident/agent/request version. Never count a task response twice. Network retry means *at least once* attempts are possible, not exactly once. Duplicate effects (DB commits, probe operations) require idempotent service boundaries. Persist task state and reconcile after coordinator restart; detect an agent's capabilities and unavailable status. Do not assume A2A's transport messages are the durable ledger.

## Minimum real collaboration acceptance test

1. Start Performance and Infrastructure **in separate processes/containers** exposing compatible A2A endpoints.
2. Send incident task. Both return schema-valid diagnostic artifacts with `observation_refs` to **distinct relevant evidence**.
3. Coordinator combines them into one hypothesis evaluation.
4. For an ambiguous case, request a targeted extra observation from exactly one suitable agent, with a new evidence record if available; if not, report ambiguity.
5. Capture message/task IDs, response types, stored evidence and final JSON output. A local fake transcript is unacceptable.
