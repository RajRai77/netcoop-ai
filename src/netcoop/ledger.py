"""Application service: validated telemetry ingestion into the evidence ledger."""

from __future__ import annotations

from datetime import datetime

from netcoop.evidence.adapters import adapt
from netcoop.evidence.counters import derive_counter_rates
from netcoop.evidence.errors import EvidenceError, IssueCode
from netcoop.evidence.normalize import BATCH_SOURCE_SCHEMA, Limits, normalize_batch
from netcoop.evidence.registry import MetricRegistry
from netcoop.evidence.timeutil import utcnow
from netcoop.storage.repository import EvidenceStore, IngestionReport


def ingest_telemetry(
    store: EvidenceStore,
    incident_id: str,
    payload: bytes | str | dict,
    *,
    now: datetime | None = None,
    limits: Limits = Limits(),
    registry: MetricRegistry | None = None,
    profile: dict | None = None,
    batch_id: str | None = None,
) -> IngestionReport:
    """Normalize and commit one TelemetryBatch (or vendor payload via a declared source
    profile). Whole-batch refusals are audited, then raised. Counter rates derivable from
    the incident's counters are persisted afterwards (append-only, idempotent)."""
    now = now or utcnow()
    incident = store.get_incident(incident_id)
    if incident is None:
        raise EvidenceError.single(IssueCode.UNKNOWN_INCIDENT, f"incident {incident_id!r} does not exist")
    topology = store.get_topology(incident.topology_snapshot_id) if incident.topology_snapshot_id else None
    try:
        kw: dict = {}
        if profile is not None:
            raw = payload if isinstance(payload, (bytes, str)) else __import__("json").dumps(payload)
            if len(raw) > limits.max_payload_bytes:
                raise EvidenceError.single(IssueCode.PAYLOAD_TOO_LARGE,
                                           f"payload is {len(raw)} bytes; limit {limits.max_payload_bytes}")
            adapted = adapt(raw, profile, max_rows=limits.max_records)
            payload = adapted.batch
            kw = {"originals": adapted.originals, "source_schema": adapted.source_schema, "pre_issues": adapted.issues}
        else:
            kw = {"source_schema": BATCH_SOURCE_SCHEMA}
        batch = normalize_batch(
            payload, incident_id=incident_id, ingested_at=now, registry=registry,
            topology=topology, expected_data_mode=incident.data_mode, limits=limits, batch_id=batch_id, **kw,
        )
    except EvidenceError as exc:
        store.audit(incident_id, "telemetry_batch_rejected",
                    {"issues": [i.model_dump(mode="json") for i in exc.issues]}, now)
        raise
    report = store.commit_ingestion(batch)
    if report.observations_added:
        counters = [o for o in store.list_observations(incident_id, limit=100_000)
                    if o.measurement.kind == "cumulative_counter"]
        rates, _issues = derive_counter_rates(counters, registry)
        store.put_derived_rates(incident_id, rates)
    return report
