# Diagnostic intelligence — STEaR working design

**STEaR is a provisional project name**, meaning spatio-temporal evidence-seeking abductive reasoning. It is not claimed to be a published new algorithm or a calibrated probabilistic model. Correctness must be established empirically.

## Input and output

Input: immutable normalized observations, typed agent findings, time window, optional versioned physical/routing/service topology, available *authorized* additional checks, fault-knowledge model version. Output: ranked candidate explanations with support/contradiction/missing evidence, affected location candidates, uncertainty, and a recommended next verification or stop decision.

## Formal hypothesis object

`H = (fault_type, component_or_service, time_interval, predicted_symptom_constraints, affected_scope, required_conditions, potential_contradictions, model_version)`.

Starter candidates (do not fabricate proof): `LINK_CONGESTION`, `INTERFACE_DEGRADATION`, `DEVICE_CPU_OVERLOAD`, `DEVICE_DOWN`, `WEAK_WIFI_SIGNAL`, `WIRELESS_INTERFERENCE`, `DNS_FAILURE`, `DHCP_FAILURE`, `PATH_OR_ROUTE_FAILURE`, `UNKNOWN`. Multiple candidates may coexist; protect against combinatorial search by bounded fault-set size and explicit complexity penalty.

## Deterministic reasoning steps

1. **Validate time-aligned context:** gather a coherent evidence snapshot and topology version. Any out-of-window measurements are kept but marked non-comparable.
2. **Extract symptoms:** metric-specific rule detectors (persistence, baseline, CUSUM/robust deviation optional), with lineage/quality flags. Thresholds are configuration data, not unexamined universal truths.
3. **Generate candidate hypotheses:** select modeled faults, locations and time windows consistent with observed affected scope and topology. Do not force a single root cause or assume a tree topology.
4. **Evaluate per candidate:** explicit support coverage, independent provenance groups, strong contradictions, data-quality eligibility, temporal compatibility, path/service-dependency consistency and missing discriminating observations.
5. **Rank explanations:** a deterministic lexicographic or documented weighted criterion, e.g. prioritize hard-constraint validity, independent evidence coverage, contradictions, scope consistency and simplicity. A numeric score is **support**, not a probability; tie and abstention conditions are explicit.
6. **Select verification:** if leading hypotheses cannot be distinguished, enumerate available safe checks, determine which predictions differ, prefer new independent and low-cost evidence, and send a typed challenge.
7. **Re-evaluate and stop:** integrate *new* observations; stop on documented sufficiency, exhaustion, safety/latency budget or no informative available checks. Preserve each result revision.

## Important epistemic safeguards

- Time order is not proof of causality. A high CPU measurement does not by itself prove CPU overload caused packet loss.
- Topology graph = candidate propagation paths, not verified causal mechanism. Intended inventory != actual forwarding != observed traffic.
- Duplicate source metrics, overlapping temporal aggregates and shared telemetry collectors can create correlated evidence; maintain measurement lineage groups.
- Missing observation is unknown, not absent symptom; negative evidence requires an actual, recent, reliable observation under conditions where a fault predicts the symptom.
- Counterfactual checks are meaningful only when the test has different expected outcomes under competing hypotheses.
- Report unmodeled causes via `unknown_fault` or qualified alternatives; do not force the nearest modeled cause.
- Multi-fault search: start with one and two concurrent hypotheses; expand only with measured need. Complexity penalty must be documented, not arbitrary hidden magic.

## Example decision (invented educational case)

Initial observations: high latency and packet loss in one link's affected scope. Both uplink congestion and physical interface degradation remain compatible. Planner seeks contemporaneous CRC error trend and egress queue-drop / utilization trend if available and authorized. If new evidence supports one hypothesis more strongly, revise; if both remain compatible, emit `ambiguous` with specific next steps. Never generate pretend CRC samples to conclude.

## Verification choice without fake probabilities

For each candidate check:

```
permitted? -> available? -> independent from existing evidence?
-> predictions differ across live hypotheses?
-> expected diagnostic benefit vs time/cost/safety
```

Selection may use a documented rule table or a deterministic utility ranking. **Do not calculate Shannon information gain from invented probabilities**. It may be added later if fault likelihoods are genuinely validated. Retries of the same source do not automatically yield independent evidence.

## Stopping policy

- `diagnosed`: supported explanation passes configurable hard checks, sufficiency coverage, material contradiction and affected-scope criteria.
- `ambiguous`: multiple credible explanations remain; more evidence unavailable or outside budget.
- `insufficient_evidence`: observations needed even to establish plausible explanations are missing/unusable.
- `unknown_fault`: anomalous evidence not explained adequately by available hypotheses.
- `healthy`: no detected fault under stated monitoring coverage and time range.
- `operational_error`: diagnosis could not be executed reliably due to system failure (not the same as uncertainty about the network).

## Calibration policy

Initially use documented `confidence_category` support levels with exact conditions and unit tests. Calibrated numeric probabilities only if representative labeled held-out data exists and ECE/Brier/reliability is evaluated; never multiply an alleged calibrated posterior by an ad hoc data-quality factor and call it calibrated.

## Proof of innovation

Compare fixed-rule baseline, centralized hypothesis engine, same engine without topology/temporal context, and engine with active checks on the same held-out cases. Record correct-cause/affected-device, abstention, false confident diagnosis, diagnostic cost and latency. If active verification does not help, do not claim that it does.
