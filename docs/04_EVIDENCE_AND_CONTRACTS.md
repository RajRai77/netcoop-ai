# Network Diagnostic Evidence Profile (NDEP) — draft v1.0

**Design status:** Proposed project-owned domain contract; not an industry standard and not a complete formal protocol. A2A handles task transport and artifact exchange. NDEP handles *meaning*; OpenConfig/YANG/gNMI handles compatible network-source semantics. JSON Schema handles structure; explicit code handles temporal/unit/domain invariants.

## Source-of-truth objects

1. **RawObservation:** immutable source payload/bytes or stable hash/pointer, acquisition mode, source identity, ingestion timestamp, content type, source schema/version. Never edit.
2. **NormalizedObservation:** `observation_id`, `incident_id`, `raw_record_ref`, `source`, `subject`, `measurement`, `observed_at`, `ingested_at`, `quality`, transformation and registry version. A source record may yield multiple normalized observations.
3. **Finding:** `finding_id`, `agent_id`, `claim`, `subject`, `observation_refs`, `rule_or_model_version`, time window, polarity, caveats, and optional supersedes reference. This is an **interpretation**, not a raw fact.
4. **Challenge:** `challenge_id`, hypothesis and finding references, exact requested observation/check, target agent, observation window, authorization and deadline.
5. **Diagnosis:** `incident_id`, `status`, suspected cause or `null`, affected scope, alternatives, confidence category, evidence snapshot ID, topology snapshot ID, supporting evidence references, actionable recommendations, limitations, engine/policy version.

Proposed schema files in `spec/`. They must be versioned. Source source-of-truth original raw payload should be retained as needed for reproducibility and privacy rules.

## Semantic requirements

- Numeric metric payloads MUST specify explicit units; validated against a versioned metric registry. No implicit guesses: `0.02` could be a fraction (2%) or percent (0.02%).
- Canonical display units examples: latency/jitter `ms`, packet loss `percent` from an *explicit* source unit, link utilization `percent`, throughput `bit/s`, CPU/memory `percent`, RSSI `dBm`, SNR `dB`, queue/CRC rate `count/s` for derived rates, cumulative counters `count` with monotonic-counter semantics.
- Use metric-specific range validators: `rssi=-78 dBm` is valid even though negative packet loss is not; reject `NaN`, infinite numbers, overflow, invalid timestamp/time-zone, and illegal negative values where applicable.
- Counter rate requires at least two valid samples, known intervals, reset/wrap detection and temporal ordering. Do not subtract across counter resets as though monotonic.
- `observed_at` is event time; `ingested_at` is receipt time. Preserve both and explicit observation window for aggregates. Require UTC timestamps with timezone in canonical records.
- Staleness is an explicit flag determined per metric using configured freshness policy; do not equate stale with zero, or simply lower every finding's score blindly.
- Validate device, interface, link, wireless AP and service identities against snapshot/aliases with auditable resolution; unknown identities must be marked or rejected depending on policy.
- Observations derived from the same source/sample group must retain common lineage IDs to avoid counting duplicates as independent support.
- Derived predictions, recommendations and AI text must never appear in the raw-measurement field.

## Example relationship

```
raw:R1 --normalized_with:registry-1.0--> observation:O1
raw:R1 --normalized_with:registry-1.0--> observation:O2
observation:O1 + observation:O2 --> finding:F1 (agent:infrastructure)
observation:O1 --> finding:F2 (agent:performance)
F1,F2 --share R1 lineage--> not two independent sensor confirmations
F1,F2 + graph:snapshot7 --> hypothesis:H1
hypothesis:H1 --more evidence required--> challenge:C1
challenge:C1 --> observation:O3 --> report:revision2
```

## Versioning and compatibility

- Pin `schema_version` and `metric_registry_version`; store both in each record or its versioned ingestion context.
- Backward-compatible additions may introduce optional fields with documented defaults. Semantic changes, renames or unit interpretation changes require explicit adapters/up-casters, tests and an ADR amendment.
- Maintain fixtures for malformed units, unsupported schema versions, missing essential IDs, contradictory time and stale data. Rejected records should generate typed errors and audit entries; avoid silently dropping important data.
- Validate both on sender and receiver of A2A artifacts. Transport authentication is not a guarantee of domain semantic correctness.

## Reporting contract

Original PS requires JSON; field set remains easy to understand for judges: `incident_id`, `status`, `suspected_root_cause`, `affected_devices`, `supporting_evidence`, `alternative_causes`, `recommended_actions`, `evidence_sources`, `limitations`, plus `confidence_category`, `evidence_snapshot_id`, `topology_snapshot_id` and `engine_version`.

- `status`: `diagnosed`, `ambiguous`, `insufficient_evidence`, `unknown_fault`, `healthy`, `operational_error`.
- `confidence_category`: `high_support`, `moderate_support`, `ambiguous`, `insufficient`, `not_applicable`. Support is **not** a statistical probability.
- `confidence` (report 1.2.0, 2026-11-01): calibrated estimate that a conclusion with this (`status`, `confidence_category`) is correct,
  measured on a held-out set: (k+1)/(n+2) with a 95 % Wilson interval, recorded in `confidence_basis` (method, n, correct, set,
  caveats). Source: `src/netcoop/knowledge/calibration/confidence.json`, produced by `scripts/calibrate_confidence.py`. `null` with a
  reason when no calibration applies (e.g. knowledge changed). The category remains the rule-based verdict; the number never
  replaces it and is never displayed as the category.
- Source profiles may declare `field_path_separator: "."` (json-records only) to address nested fields such as
  `metrics.latency_ms`; without it nested objects are UNMAPPED_FIELD. Used by `organizer-colab-json`.
- `suspected_root_cause`: nullable for non-diagnosed outcomes. Do not force a diagnosis when evidence cannot establish one.
- Each supporting evidence item must reference a real stored observation/finding and provide a unit where it presents a numeric value.
- `recommended_actions` are operator recommendations, not automatically executed changes.

See `spec/examples/` for **invented/synthetic** sample records that demonstrate structure, not real network data.
