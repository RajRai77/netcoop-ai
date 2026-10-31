# Risk register and fallbacks

| Risk / likelihood & impact | Warning sign / trigger | No-dead-end response |
| --- | --- | --- |
| No reliable scenario labels (critical) | Cannot confirm correct fault | Produce manifest + independent ground truth and hold-out cases before reporting accuracy; allow honest unknown |
| Fault signatures too similar (critical) | Contradictions/ties on same data | Support ambiguity + targeted new check, don't force confidence |
| A2A SDK incompatibility (high) | Agent Card, task or artifact failure | Pin official SDK/protocol, isolate A2A adapter, test 2 endpoints first; keep core `AgentPort` working but don't claim final interop |
| Docker/Compose unavailable (high) | Can't run containerized stack | Continue Python tests, but maintain Docker blocker and reserve Linux VPS validation |
| NetOpsBench/Containerlab unavailable (high) | OS/privileged network setup blocked | Use documented recorded/organizer data and independent fixtures; benchmark remains optional |
| No production gNMI access (high) | No compatible device/permissions | Use file/API adapter, label data mode; never scan or impersonate campus feed |
| NetBox/Batfish no config data (medium) | Missing actual config/routing | Use supplied/observed topology with explicit caveats; don't fake forwarding models |
| Semantic unit ambiguity (high) | packet_loss field missing unit | Reject/quarantine and typed reason, no guess |
| Graph topology stale/incorrect (high) | Actual path differs from inventory | Version observed/intended/modeled states separately; lower localization specificity |
| Active check adds no evidence (high) | Re-asks same source, check unavailable | Dedup lineage, stop within budget, abstain |
| Agent unavailable/timeout (medium) | Missing result | Bounded retry, explicit coverage, no fabricated agent finding |
| DB restart/volume lost (high) | History disappears | Persistent named volume, migrations, backup/restore drill, DB health |
| SQLite-to-Postgres drift (medium) | Different queries/migrations | Use Postgres for Compose from first deployment; no divergent storage implementations |
| Proxy/TLS failure (high) | Public URL fails | Validate DNS/firewall/ports/ACME; do not claim hosted status until external HTTPS smoke passes |
| LLM tokens/quota/hallucination (medium) | Model unavailable/invents measurement | Core deterministic offline mode; narration only if grounded/validated |
| Public endpoint abused (high) | Upload floods/SSRF/untrusted agent | Access control, size/rate limits, outbound allowlist, no privileged containers; see threat model |
| Claude Code context drift (high) | Repeats or contradicts decisions | Root CLAUDE.md, ADRs, gate and progress file; required end-of-session updates |
| Too much architecture up front (high) | Many services but no diagnosis | Gate-based vertical slices; last known-good commit; optional tools stay optional |

## Escalation rule

If blocked: state **precise failing command/error**, impact on acceptance, attempted fixes, safe fallback and unresolved risk. Do not rearchitect unrelated modules, change expected outputs to green, or skip a mandatory gate without stating failure.
