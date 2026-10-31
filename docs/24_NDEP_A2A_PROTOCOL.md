# NDEP over A2A — the interoperability contract (as implemented)

**Status:** implemented and tested (see "Proof" below). NDEP (Network Diagnostic Evidence Profile) is a project-owned domain contract; A2A (a2a-sdk 1.3.0, protocol 1.0, JSON-RPC binding) is the transport. All schemas live in `spec/` and are validated on **both** sender and receiver.

## Layers

| Layer | What it carries | Where |
|---|---|---|
| A2A JSON-RPC 1.0 | discovery (Agent Card), `SendMessage`, Task, Artifact, task state | a2a-sdk; `src/netcoop/agents/server.py`, `src/netcoop/orchestration/ports.py` |
| NDEP envelopes | AgentTask (request), AgentResult (artifact) | `spec/agent-task.schema.json`, `spec/agent-result.schema.json` |
| NDEP evidence objects | NormalizedObservation, Finding, Challenge, TopologySnapshot, TelemetryBatch | `spec/*.schema.json` |
| Semantics | units, ranges, kinds, freshness, counters, lineage | `spec/metric_registry.json` (1.2.0), `src/netcoop/evidence/normalize.py` |

## Agents and discovery

Three specialists, each an independent OS process / container:

| agent_id | Domain metrics (from its Agent Card skill tags `metric:*`) |
|---|---|
| `performance-agent` | latency, jitter, packet_loss, throughput, link_utilization, queue_drops_rate, queue_drops |
| `infrastructure-agent` | cpu_utilization, memory_utilization, crc_errors, interface_errors, device_status, interface_status, rssi, snr, wireless_retry_rate |
| `connectivity-agent` | reachability, dns_query_failure_rate, dhcp_lease_failure_rate (+ topology scope analysis) |

Card: `GET /.well-known/agent-card.json` (public). Skills: `investigate`, `verify`. Tags include `agent:<id>` and `metric:<name>`.

**Trust rules (coordinator side, `A2AAgentPort.discover`):** the agent id and its expected card name come from local configuration (`NETCOOP_AGENTS`), never from the remote card. The card must match the allowlisted name, declare both skills and `agent:<id>`, and may not claim metrics outside its allowlisted domain. All requests except the card require `Authorization: Bearer <NETCOOP_AGENT_TOKEN>`. Tests: `test_agent_card_impersonation_is_refused`, `test_wrong_token_is_rejected_and_reported`.

## Message exchange

```
coordinator                                        specialist
    | GET /.well-known/agent-card.json  --------->  |
    | <------------------------------  AgentCard    |
    | POST / JSON-RPC SendMessage                   |
    |   Message{role=USER, parts=[Part{text=<AgentTask JSON>,
    |            media_type="application/vnd.netcoop.ndep+json"}]}  --> |
    |                     Task{state=COMPLETED, artifacts=[            |
    | <--------------------   Artifact{name="ndep-agent-result",       |
    |                          parts=[Part{text=<AgentResult JSON>,    |
    |                                      media_type=ndep+json}]}]}   |
```

**Why a text part, not an A2A `data` part:** A2A `data` parts are `google.protobuf.Value`; every number becomes a double (integers turn into floats, values above 2^53 lose precision). NDEP carries cumulative counters up to 2^64-1, so JSON is sent as exact text. Verified by `test_exact_numbers_survive_a2a_round_trip` (uint64 max, 0.1, 1e-300, microsecond timestamp with offset all round-trip byte-exact).

## AgentTask (coordinator -> specialist)

| field | meaning |
|---|---|
| `task_id` | logical idempotency key = hash(incident, agent, task type, observation ids sent). Retries reuse it. |
| `task_type` | `investigate` (analyse evidence) or `verify` (answer a Challenge) |
| `agent_id` | intended recipient; an agent refuses tasks addressed to another agent (`WRONG_AGENT`) |
| `data_mode` | `synthetic` / `recorded` / `emulated` / `live` / `mock` — always propagated |
| `case.observations` | NDEP NormalizedObservations of this agent's metric domain only (validated by the agent) |
| `case.topology` | TopologySnapshot or null (connectivity agent uses it) |
| `case.prior_findings` | this agent's current findings, so it can issue revisions (`supersedes_finding_id`) |
| `case.analysis_time` | deterministic: latest observed_at of the evidence (keeps findings idempotent) |
| `challenge` | NDEP Challenge for `verify` |
| `archive_ref` | `scenario:<id>` or `upload:<incident>`: the authorized recorded source agents may query |

## AgentResult (specialist -> coordinator)

| field | meaning |
|---|---|
| `status` | `completed`, `unavailable` (nothing measurable — never fabricated), `refused` (out of domain / invalid / unauthorized scope), `failed` (agent error) |
| `findings` | NDEP Findings: `claim`, `polarity` (present/absent/unknown), `subject`, `observation_refs` (ids that were sent), `rule_or_model_version`, `caveats`, `supersedes_finding_id` |
| `telemetry_batches` | `verify` only: recorded source records returned **unchanged** from the archive |
| `coverage` | metrics received, stale/quarantined ignored, metrics with no data (a gap, not health) |

**Coordinator acceptance checks** (`Coordinator._accept`): schema-valid; `agent_id` and `task_id` match the request; every finding's `agent_id` equals the sender (spoofing refused); `observation_refs` ⊆ observations sent to that agent; store-level checks (refs exist, revision chain linear, edits refused). Returned telemetry is ingested through the normal NDEP validator and tagged with the challenge id as `batch_id`. Tests: `tests/resilience/test_coordinator_failures.py`.

## Finding claims (detector-rules/1)

`HIGH_LATENCY` (>100 ms), `HIGH_JITTER` (>30 ms), `PACKET_LOSS` (>1 %), `HIGH_LINK_UTILIZATION` (>=85 %), `QUEUE_DROPS` (>1/s), `HIGH_CPU` (>=90 %), `HIGH_MEMORY` (>=90 %), `CRC_ERRORS` / `INTERFACE_ERRORS` (counter rate >0.1/s), `DEVICE_DOWN_STATE`, `DEVICE_DEGRADED_STATE`, `INTERFACE_DOWN`, `WEAK_SIGNAL` (<-75 dBm), `LOW_SNR` (<20 dB), `HIGH_WIRELESS_RETRIES` (>15 %), `UNREACHABLE`, `DNS_FAILURES` / `DHCP_FAILURES` (>5 %); topology hints `COMMON_UPSTREAM_DEPENDENCY`, `COMMON_SERVICE_DEPENDENCY`. Present needs >=2 anomalous fresh samples from one source; one sample -> `unknown` (transient); disagreeing sources -> `unknown` + `SOURCE_CONFLICT`; absent needs fresh normal samples. Thresholds are engineering defaults (`src/netcoop/knowledge/detector_rules.json`), not universal truths.

## Challenge (verification request)

`spec/challenge.schema.json`: `hypothesis_ids` (>=2; the unmodeled alternative is `H-UNKNOWN`), exact `requested_observation` (metric, subject, window), `authorization_scope` (`recorded_replay` implemented; `read_only` live collectors are not configured, so agents answer `unavailable`), `deadline_at`. Outcomes persisted: `obtained`, `no_new_evidence`, `unavailable`, `refused`, `failed`.

## Failure semantics

| situation | behaviour |
|---|---|
| timeout / connection error | retried once with the same `task_id`; attempts recorded separately |
| wrong token (401) | `unauthorized`, not retried; agent excluded; limitation in report |
| invalid / spoofed artifact | `invalid`; nothing stored |
| no specialist completes a task | `operational_error` report (no claim about the network) |
| agent crash mid-incident | partial coverage; report lists the missing domain |
| duplicate delivery | findings are content-addressed -> `unchanged`, never double-counted |

## Proof (executed tests)

`tests/integration/test_a2a_agents.py` (3 real agent processes; A2A results equal in-process results for S04/S10/S11/S15; exact numbers; token; impersonation; crash), `tests/integration/test_processes.py` (launcher end-to-end over A2A), `scripts/run_local.py --check`, `scripts/smoke.sh`, CI `compose-smoke` (containers on an internal network).
