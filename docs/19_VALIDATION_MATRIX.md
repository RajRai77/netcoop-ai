# Gate-oriented validation matrix — intended proof

All rows are **planned**, unverified until commands and artifacts are recorded.

| Dimension | Fixture / method | Expected proof | Gate |
| --- | --- | --- | --- |
| Structural JSON | valid + malformed payload | typed accept/reject | G1 |
| Unit mismatch | bps vs Mbps and ambiguous `0.02` | explicit correct conversion or rejection | G1 |
| Time/counter | stale sample, out-of-order, reset | validity flags, no nonsensical rate | G1 |
| First diagnosis | labeled congestion with 2 source metrics | evidence-backed report | G2 |
| Clear alternative | physical interface errors vs congestion | not blind threshold selection | G3 |
| Unsupported fault | unseen anomaly / no matching library | unknown or qualified ambiguity | G3 |
| Multi-fault | two simultaneous independent causes | bounded multi-hypothesis handling | G3 |
| Provenance independence | same sensor read by 2 agents | no doubled support | G3 |
| Topology validity | redundant path; missing/old snapshot | justified localization or limitation | G3 |
| A2A real interop | 2 specialist server processes | task/artifact wire evidence and one report | G4 |
| Agent incompatibility | old schema/invalid artifact | typed error and version handling | G4 |
| Agent failure | timeout/retry/duplicate result | partial coverage, dedup, never fictional reply | G4/G6 |
| Active verification | ambiguous initial evidence + independent new observation | new evidence linked to revised result or honest abstention | G5 |
| Public UI | recorded scenario through web | real activity, JSON download, mode label | G6 |
| Restart persistence | stop and restart containers | committed data remains | G6 |
| HTTPS/private ports | remote probe & port scan of owned VPS | HTTPS works, DB/agents not publicly reachable | G6 |
| Backup restoration | fresh volume restored | same case report retrievable | G6 |
| Comparison | held-out baseline vs full | honest saved metrics and ablations | G7 |

Define actual `pytest` selectors / smoke-script commands when source files exist; never claim a planned test selector is implemented.
