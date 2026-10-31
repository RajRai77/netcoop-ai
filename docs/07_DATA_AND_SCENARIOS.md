# Data, scenarios and ground truth

## Allowed input sources and labeling

Every investigation declares `data_mode = synthetic | recorded | emulated | live | mock`. `mock` only for clearly labeled unit-level tests, NEVER to claim multi-agent production interoperability. Inputs may be organizer-provided, independently created synthetic, lab/emulation telemetry or explicitly authorized live streams. Production campus access is not required.

## Data packaging contract

Place documented scenario source files under `data/scenarios/` when implementation begins. Each scenario should contain:

- `manifest.json`: `scenario_id`, origin/mode, generator/source + version, seed if synthetic, license/access, topology snapshot pointer, time range, known limitations.
- `telemetry.json` or CSV: actual data consumed by the app, with record identity, units, source, timestamps; no outcome hints in features.
- `topology.json`: versioned nodes/links/services/uncertainty. Must be able to represent multiple paths.
- `ground_truth.json`: causal injected fault(s) or external trustworthy labels; **kept separate from diagnosis input**; may contain `unresolvable`/`unknown` cases.

Do not load `ground_truth.json` into production diagnosis code or allow agent prompts to see it. Evaluator only.

## Starter scenario matrix (planned; NOT yet created)

| ID | Scenario | Expected observable behaviour / caveat |
| --- | --- | --- |
| S00 | Healthy under monitored coverage | `healthy` only if monitoring coverage sufficiently defined |
| S01 | Link congestion | High utilization + temporal queue drops/latency; localize uplink where supported |
| S02 | Interface degradation | CRC/errors/flaps + packet loss; compare to congestion |
| S03 | Device CPU overload | Elevated CPU and relevant downstream symptoms; avoid assumption of causality |
| S04 | Device/link down | Path failures and affected branch; respect redundant paths |
| S05 | Weak Wi-Fi signal | Low RSSI / signal quality plus retries; mark missing radio telemetry |
| S06 | Wireless interference | Distinguish good RSSI from low SNR/high retransmissions where data exists |
| S07 | DNS failure | DNS query failures while basic path reachability may remain |
| S08 | DHCP failure | New lease failures vs existing connectivity evidence |
| S09 | Shared upstream issue | Multi-branch impact localized to a supported common dependency |
| S10 | Compound faults | Two independent faults, with overlap and proper uncertainty |
| S11 | Ambiguous evidence | Must issue requested check or `ambiguous`, not fake certainty |
| S12 | Missing / stale / malformed records | Typed validation, partial result or rejection |
| S13 | Schema/unit interoperability | Aliases and explicitly convertible units, plus unsupported version rejection |
| S14 | Agent timeout / duplicate response | Recovery/coverage status, no double count |
| S15 | Out-of-library unknown fault | `unknown_fault` or evidence-backed incomplete interpretation |

Use negative/contradictory/time-shift variants of each type; include observation windows and fault onset intervals. The table is a scenario plan, not a claim that all cases are covered by the implemented engine.

## Independent evaluation principles

- Freeze labeled hold-out topologies and fault-intensity distributions before tuning ranking rules.
- Split by topology, causal mechanism, source/generator where possible; do not only vary random seeds of identical signature generation.
- Baselines get the same available starting observations and legitimate verification budget.
- Report failure cases; no guaranteed accuracy or calibration figures.
- Real-world lab experiments must run only with permission and isolation; heavy emulators are *not* required for the web application's normal operation.

## External resources (optional)

Organizer-provided Colab synthetic generator and scenarios: prefer when available, but record generator assumptions. Containerlab/NetOpsBench: useful for authorized independent emulated experiments, Linux/Docker/network capabilities may be required. NetBox/Batfish are context adapters, not datasets or labels.
