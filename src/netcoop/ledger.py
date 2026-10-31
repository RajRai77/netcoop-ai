"""Application service: validated telemetry ingestion into the evidence ledger."""

from __future__ import annotations

from datetime import datetime

from netcoop.evidence.errors import EvidenceError, IssueCode
from netcoop.evidence.normalize import Limits, normalize_batch
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
) -> IngestionReport:
    """Normalize and commit one TelemetryBatch. Whole-batch refusals are audited, then raised."""
    now = now or utcnow()
    incident = store.get_incident(incident_id)
    if incident is None:
        raise EvidenceError.single(IssueCode.UNKNOWN_INCIDENT, f"incident {incident_id!r} does not exist")
    topology = store.get_topology(incident.topology_snapshot_id) if incident.topology_snapshot_id else None
    try:
        batch = normalize_batch(
            payload, incident_id=incident_id, ingested_at=now, registry=registry,
            topology=topology, expected_data_mode=incident.data_mode, limits=limits,
        )
    except EvidenceError as exc:
        store.audit(incident_id, "telemetry_batch_rejected",
                    {"issues": [i.model_dump(mode="json") for i in exc.issues]}, now)
        raise
    return store.commit_ingestion(batch)
