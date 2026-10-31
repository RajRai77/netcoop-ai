# NDEP proposed machine-readable starter artifacts

`*.schema.json` under this folder are **proposed starter domain contracts** for implementation, not a complete official standard or evidence of real telemetry. They will be refined and frozen with versioning in Gate 1. `examples/` are **invented synthetic examples** illustrating the file shapes, not benchmark data.

- `observation.schema.json`: normalized measurement with required explicit units, timestamps, source, lineage.
- `finding.schema.json`: typed specialist finding referencing source observations.
- `challenge.schema.json`: coordinator's requested discriminating evidence.
- `report.schema.json`: required JSON diagnosis with supporting references and defined support categories.
- `topology.schema.json` / `scenario-manifest.schema.json`: versioned graph snapshot and reproducible source manifest.
- `metric_registry.json`: seed metric vocabulary and permitted units; source-specific mappings must be verified, not guessed.

JSON Schema validates shapes, **not full semantic correctness**. Implement domain validators for unit semantics, valid numerical ranges, clock/time windows, counter resets, data lineage, duplicate observations and topology consistency.

When implementing, test that every example conforms, that an invalid variant is rejected, and that JSON Schema and Pydantic semantics agree.
