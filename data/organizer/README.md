# Organizer sample input generator

`ps_sample_generator.py` is the sample telemetry generator linked from the official problem statement
(section 5, "Sample-Input-generator-code-COLAB"), copied as supplied by the team on 2026-11-01. Do not edit it:
`scripts/build_organizer_scenarios.py` records its SHA-256 in every `ORG-*` manifest.

How NetCoop uses it:

- `scripts/build_organizer_scenarios.py` calls `generate_telemetry()` unchanged. It seeds Python's `random`, fixes the
  clock the function reads, and keeps only calls that picked the wanted device (rejection sampling). Values are not
  altered, except for the six documented mutations in `ORG-04-schema-drift`.
- Records are ingested with the declared profile `spec/profiles/organizer-colab-json.json`. Units come from the field
  suffixes (`_pct`, `_ms`). `queue_drops`, `interface_errors` and `status` are left unmapped because the generator
  does not define their meaning; every ingestion reports them as `UNMAPPED_FIELD`.
- The generator's fault types (`latency_spike`, `hardware_failure`) are symptom classes, so the ground truth uses only
  fault presence and the faulted device.
