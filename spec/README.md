# NDEP proposed machine-readable starter artifacts

`*.schema.json` under this folder are **proposed starter domain contracts** for implementation, not a complete official standard or evidence of real telemetry. They will be refined and frozen with versioning in Gate 1. `examples/` are **invented synthetic examples** illustrating the file shapes, not benchmark data.

- `observation.schema.json`: normalized measurement with required explicit units, timestamps, source, lineage.
- `finding.schema.json`: typed specialist finding referencing source observations.
- `challenge.schema.json`: coordinator's requested discriminating evidence.
- `report.schema.json`: required JSON diagnosis with supporting references and defined support categories.
- `topology.schema.json` / `scenario-manifest.schema.json`: versioned graph snapshot and reproducible source manifest.
- `telemetry-batch.schema.json`: envelope for submitting raw source measurements (added 2026-10-31). Per-record semantics are enforced by the domain validator, so one bad record is reported without hiding the rest.
- `metric_registry.json` (1.1.0): metric vocabulary, permitted units, explicit conversion factors, unit spelling aliases, allowed kinds, freshness policy. Source-specific field mappings must be verified, not guessed.

JSON Schema validates shapes, **not full semantic correctness**. Implement domain validators for unit semantics, valid numerical ranges, clock/time windows, counter resets, data lineage, duplicate observations and topology consistency.

When implementing, test that every example conforms, that an invalid variant is rejected, and that JSON Schema and Pydantic semantics agree.
