# Security / threat model — MVP and deployment

## Assets to protect

Network telemetry (may include internal hostnames/IPs), device names/configurations, source credentials, diagnosis histories, service tokens, agent endpoints, public API availability and operator trust in recommendations.

## Attack surfaces and mitigations

| Surface | Risk | Required mitigation |
| --- | --- | --- |
| User uploads | Resource exhaustion, malicious JSON, path traversal | Limit size/depth, validate content/schema, generated safe filenames, no shell execution from file data |
| External telemetry source | Forged records, wrong units, stale/out-of-order values | Authenticated/approved adapters, raw provenance, strict semantics and typed errors |
| A2A agent discovery | Untrusted Agent Card / malicious agent | Allowlisted registry + authenticated identity and per-agent capabilities; reject untrusted agents |
| Agent artifacts | Fabricated finding or replay/double count | Schema validation, task/artifact IDs, source lineage and dedup; trust is never based on self-confidence field |
| Active measurement tools | SSRF, unauthorized scanning, network changes | Tool allowlist, scoped read-only credentials, outbound target allowlist, explicit approval; no privileged automation |
| Browser and public API | Unauthorized evidence disclosure, CSRF, injection, brute-force | Session/API auth where required, TLS, origin/CORS policy, rate limits, output escaping and secure cookies |
| Docker stack | Secrets leaked, exposed DB/agent ports, privilege escalation | Only Caddy public, internal private networks, run non-root, secret mounting, no Docker socket, no privileged net |
| DB / audit | Unauthorized tampering, lost records | Least-privilege DB roles, append-only semantics, backups and test restore, audit retention policy |
| LLM (if enabled) | Prompt injection from telemetry/text, hallucinated action | Treat all external text untrusted, no execute permission, schema-grounded bounded output, deterministic fallback |
| Reports | Unsupported confidence or hidden failure | Evidence references, status/limitations, explicit observation coverage, error status |

## Demo deployment hardening

- Do not leave an unauthenticated public endpoint that permits unrestricted uploads or arbitrary external network probe requests.
- Do not share campus credentials, private IP inventories or sensitive real data publicly.
- If demo data is synthetic, say so. The product still functions as real software; claims of real-time campus monitoring would be false without authorized integration.
- Validate HTTPS from outside the VPS, container port exposure, secret rotation, DB access control and error log redaction.
- No auto-remediation in core; recommendations are human-reviewed.
