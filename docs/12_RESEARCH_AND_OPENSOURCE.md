# Research and open-source technology reference

These are **candidate tools/research references**, not a claim that we successfully installed or fully audited every project. Review official releases, Python/runtime compatibility, security, licensing and maintenance **before** adding a dependency. Pin exact versions/digests only after actual preflight.

## Core selected references

- **Claude Code / CLAUDE.md:** https://support.claude.com/en/articles/14553240-give-claude-context-claude-md-and-better-prompts — root-level project memory, concise instructions.
- **A2A specification:** https://a2a-protocol.org/latest/ ; **Python SDK:** https://github.com/a2aproject/a2a-python ; **A2A Inspector:** https://github.com/a2aproject/a2a-inspector — agent discovery, tasks, structured artifacts and conformance.
- **OpenConfig/gNMI:** https://github.com/openconfig/gnmi ; **gNMIc:** https://github.com/openconfig/gnmic — optional standards-based telemetry collection.
- **JSON Schema:** https://json-schema.org/draft/2020-12 — structural contract validation; cannot by itself enforce network semantics.
- **Pydantic:** https://github.com/pydantic/pydantic — typed models and JSON Schema generation, with custom validators.
- **NetworkX:** https://networkx.org/ — deterministic graph/path algorithms.
- **PostgreSQL:** https://www.postgresql.org/ — durable structured evidence and migrations.
- **Docker Compose:** https://docs.docker.com/compose/how-tos/production/ — deploy on single server with production overrides.
- **Caddy:** https://caddyserver.com/docs/ — HTTPS reverse proxy, only when DNS/ports/cert policy works.
- **OpenTelemetry:** https://opentelemetry.io/docs/ — internal platform tracing, not network fault telemetry source itself.

## Conditional tool alternatives / inspiration

- **Temporal:** https://github.com/temporalio/temporal — reliable workflow engine for later scale; no need for deployed v1; development server not production.
- **LangGraph:** https://github.com/langchain-ai/langgraph — optional agent-local graph workflows, not incident state authority.
- **NetBox:** https://github.com/netbox-community/netbox — intended inventory, not live forwarding truth.
- **Batfish:** https://github.com/batfish/batfish — config-snapshot network analysis, only where supported and configs available.
- **Containerlab:** https://github.com/srl-labs/containerlab — isolated emulation under Linux/Docker capabilities; separate from public web.
- **NetOpsBench:** https://github.com/NetX-lab/NetOpsBench — independent troubleshooting benchmark candidate; verify coverage, OS prerequisites and licensing.
- **Mininet:** https://github.com/mininet/mininet — simpler lab alternative for certain forwarding/link experiments.
- **STAR:** https://github.com/CSTCloudOps/STAR — research inspiration for spatial/temporal root-cause localization. Do not copy/claim its model as ours or treat its outcomes as externally validated on our setting.
- **PyRCA:** https://github.com/salesforce/PyRCA — RCA methods inspiration; applicability/data assumptions need independent tests.
- **RCAEval:** https://github.com/phamquiluan/RCAEval — RCA evaluation inspiration; assess whether datasets apply to network-domain diagnosis.
- **MCP:** https://modelcontextprotocol.io/ — optional tool access interface, *not equivalent to A2A agent collaboration*.
- **RFC 8345:** https://www.rfc-editor.org/rfc/rfc8345 — network topology YANG model framework.
- **RFC 9417:** https://www.rfc-editor.org/rfc/rfc9417 — service assurance dependency graph.

## Conclusions carried forward

- A2A vs OpenConfig vs JSON Schema is a false either/or: agent transport, telemetry semantics and evidence-schema validation solve distinct problems.
- Active diagnosis, topology/temporal RCA and agent orchestration have substantial prior art; **do not claim their individual invention**.
- Proposed contribution is a testable *integration* of semantic evidence contracts, federated agent investigations, topology/dependency-based candidate evaluation and cost-/safety-bounded evidence seeking under missing/conflicting telemetry.
- Target is a robust engineering system with measurable advantage, not guaranteed hackathon victory.
