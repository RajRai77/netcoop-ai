# NetCoop AI — evidence-seeking federated network diagnosis

Interoperable multi-agent network fault diagnosis for the *Agentic AI Grand Finale, IIT Bhubaneswar* challenge
("NetCoop AI — Multi-Agent Network Fault Diagnosis and Interoperability").

Three independent specialist agents (Performance, Infrastructure, Connectivity & Services) analyse validated
telemetry and exchange typed **NDEP** findings over **A2A**. A deterministic engine (**STEaR**) compares competing
root-cause hypotheses across topology and time. When the leading explanations cannot be separated, it **asks a
specific agent for a discriminating observation**. It then reports a diagnosis with traceable evidence, or honestly
abstains. No LLM is required, and none is used.

> Status and verified results: [docs/14_PROJECT_PROGRESS.md](docs/14_PROJECT_PROGRESS.md) ·
> Evaluation: [eval/results/RESULTS.md](eval/results/RESULTS.md) (generated) and [docs/21_EVALUATION.md](docs/21_EVALUATION.md) ·
> Protocol: [docs/24_NDEP_A2A_PROTOCOL.md](docs/24_NDEP_A2A_PROTOCOL.md)

All bundled data is **synthetic** and labelled as such. No live campus network is accessed. Recommended actions are
for a human operator and are never executed automatically.

## Quick start (Windows or Linux, no Docker, no cloud, no API keys)

Requires Python 3.12 and [uv](https://docs.astral.sh/uv/).

```sh
git clone https://github.com/RajRai77/netcoop-ai.git && cd netcoop-ai
uv sync --locked
uv run python scripts/run_local.py            # http://127.0.0.1:8000  (Ctrl+C stops everything)
```

The launcher checks Python and dependencies, creates a SQLite database in `./var`, applies migrations, then starts
**four OS processes**: three specialist A2A servers on free localhost ports, and the web/coordinator. Agents get a fresh
random bearer token per run. The launcher waits for health, reports startup failures and port conflicts, and shuts down
cleanly. Children also exit if the launcher is killed.

```sh
uv run python scripts/run_local.py --check        # start, run a full A2A diagnosis, verify, stop (exit 0/1)
uv run python scripts/run_local.py --port auto    # if 8000 is busy
uv run pytest                                     # test suite (PostgreSQL variants skip without a DB)
uv run python scripts/evaluate.py                 # baselines vs NetCoop -> eval/results/
```

In the browser: **New incident → labeled scenario → Create & diagnose**. You can also upload NDEP JSON or vendor CSV
(via a declared source profile), plus an optional recorded archive for verification.

## How it works

```
telemetry (JSON / CSV via declared profile)
   -> Evidence Fabric: strict units, timestamps, ranges, kinds, freshness, counter resets,
      immutable raw records, lineage, duplicates/conflicts      (src/netcoop/evidence)
   -> append-only evidence ledger (SQLite local / PostgreSQL)    (src/netcoop/storage)
   -> coordinator --A2A JSON-RPC, NDEP JSON text parts--> performance | infrastructure | connectivity agents
   -> STEaR: hypotheses x locations from the fault library and topology impact scope;
      signature / contradiction / temporal checks; independent-source support; <=2 concurrent faults;
      unknown-fault and abstention rules                          (src/netcoop/engine/stear.py)
   -> if not separable: planner picks discriminating checks -> agent queries an authorized recorded
      source -> new observations ingested and validated -> re-investigate -> re-evaluate (bounded)
   -> structured JSON report (spec/report.schema.json) + text + browser UI; every revision kept
```

| Rubric area | Where it lives |
|---|---|
| Interoperability & protocol (30 %) | `spec/*.schema.json`, [docs/24](docs/24_NDEP_A2A_PROTOCOL.md), `src/netcoop/agents/server.py`, `src/netcoop/orchestration/ports.py`, `tests/integration/test_a2a_agents.py` |
| Diagnostic accuracy & evidence (25 %) | `src/netcoop/engine/`, `src/netcoop/knowledge/*.json`, `tests/inference/`, `eval/results/RESULTS.md` |
| Orchestration & conflict resolution (15 %) | `src/netcoop/orchestration/coordinator.py`, `src/netcoop/engine/planner.py`, `tests/resilience/` |
| Robustness to bad data (15 %) | `src/netcoop/evidence/normalize.py`, `adapters.py`, `counters.py`, `tests/normalization/`, scenarios S12/S13 |
| Innovation, usability, extensibility (10 %) | evidence-seeking verification, browser UI (`src/netcoop/web/`), declared source profiles, pluggable agents |
| Code, docs, demo (5 %) | this README, `docs/`, [docs/22 demo script](docs/22_DEMO_SCRIPT.md) |

### Report (excerpt of a real `S11` run)

`status`, `suspected_root_cause`, `confidence_category` (a documented **support category**, not a probability),
`affected_devices`, `supporting_evidence[]` (observation id, finding id, metric, value, unit), `alternative_causes`,
`recommended_actions`, `evidence_sources` (agents), `limitations`, `evidence_snapshot_id`, `topology_snapshot_id`,
plus `root_causes`, `hypotheses`, `verification.challenges[]`, `coverage`, `decision_basis`, `transport`.

## Scenarios

`data/scenarios/` contains 17 labeled synthetic scenarios: healthy, congestion, interface degradation, CPU overload,
device down, weak Wi-Fi, interference, DNS, DHCP, upstream outage needing verification, compound faults, an ambiguity
that verification resolves, the same ambiguity with no extra data (stays ambiguous), malformed/stale/unknown-device
input, vendor CSV with ratios/Mbps/IST timestamps, an unmodeled fault, and a transient spike. Regenerate with
`uv run python scripts/generate_scenarios.py`. The 60-case held-out set is generated with `--heldout`, after the
knowledge freeze.

## API (main endpoints)

`GET /health/live`, `/health/ready` · `GET /api/agents` (live A2A discovery) · `GET /api/scenarios` ·
`POST /api/incidents` (`{scenario_id}` or `{data_mode, title, topology, reference_time}`) ·
`POST /api/incidents/{id}/telemetry[?profile=…]` · `POST /api/incidents/{id}/archive` ·
`POST /api/incidents/{id}/diagnose` (`{verification}`) · `GET /api/incidents/{id}` · `/report[?revision]` · `/report.txt` ·
`/timeline` (events, A2A attempts, challenges) · `/attempts/{attempt_id}` (raw artifact) · `/evidence` · `/findings` ·
`/topology` · `/stream` (Server-Sent Events) · `GET /api/raw-records/{raw_id}` · `GET /api/evaluations[/{name}]`. Interactive docs: `/docs`; exported contract [docs/openapi.json](docs/openapi.json); frontend guide [docs/25_FRONTEND_INTEGRATION.md](docs/25_FRONTEND_INTEGRATION.md). Separate frontend dev server: `uv run python scripts/run_local.py --cors-origin http://localhost:5173`. If `NETCOOP_API_TOKEN` is set, `/api/*`
needs `Authorization: Bearer …`.

CLI: `uv run netcoop --database-url sqlite:///var/netcoop.db db upgrade | incident create | ingest [--profile] | evidence`.

## Docker Compose (Linux)

```sh
cp .env.example .env      # set POSTGRES_PASSWORD, NETCOOP_AGENT_TOKEN (hex), optionally NETCOOP_API_TOKEN
docker compose up -d --build --wait
BASE_URL=http://127.0.0.1:8000 sh scripts/smoke.sh
docker compose down       # keeps data; `down -v` DELETES the database volume
```

Backup/restore: `sh scripts/backup.sh` / `sh scripts/restore.sh <file>` (Compose, pg_dump custom format; CI restores onto a fresh volume). Local SQLite: `uv run netcoop --database-url sqlite:///var/netcoop.db db backup backups/netcoop.db`.

Services: `db` (PostgreSQL 17, internal), `web`, `agent-performance`, `agent-infrastructure`, `agent-connectivity`.
The agents sit on an internal network and are reached by service DNS. Only `web` is published, on 127.0.0.1.
Production overlay: `-f compose.production.yaml` adds Caddy HTTPS, read-only containers and log limits, and requires
`NETCOOP_API_TOKEN`, `NETCOOP_DOMAIN` and `ACME_EMAIL`. This is verified in GitHub Actions (`compose-smoke`). A public
VPS deployment has **not** been performed.

## Honest limitations

- Synthetic evaluation data from one generator family. Same-author generator and engine. No organizer dataset yet.
- Detector thresholds are engineering defaults, and the fault library covers 9 fault types. Anything else is reported
  as `unknown_fault`.
- Verification queries recorded archives (`recorded_replay`). Live read-only collectors (gNMI/SNMP) are adapter points
  and are not implemented.
- Support categories are rule-based, not calibrated probabilities.
- Single-node Compose is not highly available. The public HTTPS (Caddy) deployment on a VPS has not been performed; backup/restore is drilled in CI only.
