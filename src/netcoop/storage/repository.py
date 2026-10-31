"""Storage-independent repository contract for the evidence ledger.

Domain code depends on this Protocol only. `SqlEvidenceStore` implements it for both
SQLite (local) and PostgreSQL (deployed) through one SQLAlchemy code path.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict

from netcoop.evidence.errors import Issue
from netcoop.evidence.models import (
    DataMode,
    Finding,
    NormalizedObservation,
    RawRecord,
    Timestamp,
    TopologySnapshot,
)
from netcoop.evidence.normalize import NormalizedBatch, RecordStatus


class Incident(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    incident_id: str
    data_mode: DataMode
    topology_snapshot_id: str | None
    title: str | None
    created_at: Timestamp
    archive_ref: str | None = None
    scenario_id: str | None = None
    reference_time: Timestamp | None = None


class RecordResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    record_index: int
    record_id: str | None
    raw_id: str
    status: RecordStatus
    observation_ids: list[str]


class IngestionReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ingestion_id: str
    incident_id: str
    batch_id: str | None
    received_at: Timestamp
    metric_registry_version: str
    counts: dict[str, int]
    observations_added: int
    records: list[RecordResult]
    issues: list[Issue]


class StoredIssue(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ingestion_id: str
    raw_id: str | None
    code: str
    severity: str
    record_index: int | None
    measurement_index: int | None
    message: str


PutResult = Literal["created", "unchanged"]


class EvidenceStore(Protocol):
    def schema_revision(self) -> str | None: ...
    def audit(self, incident_id: str | None, event_type: str, detail: dict, at: datetime) -> None: ...

    def create_incident(
        self, incident_id: str, data_mode: str, *, created_at: datetime,
        topology_snapshot_id: str | None = None, title: str | None = None,
        archive_ref: str | None = None, scenario_id: str | None = None, reference_time: datetime | None = None,
    ) -> Incident: ...
    def list_incidents(self, limit: int = 100) -> list[Incident]: ...
    def get_incident(self, incident_id: str) -> Incident | None: ...

    def put_topology(self, snapshot: TopologySnapshot, *, stored_at: datetime) -> PutResult: ...
    def get_topology(self, topology_snapshot_id: str) -> TopologySnapshot | None: ...

    def commit_ingestion(self, batch: NormalizedBatch) -> IngestionReport: ...
    def get_raw_record(self, raw_id: str) -> RawRecord | None: ...
    def get_observation(self, observation_id: str) -> NormalizedObservation | None: ...
    def list_observations(
        self, incident_id: str, *, metric: str | None = None, limit: int = 1000, offset: int = 0
    ) -> list[NormalizedObservation]: ...
    def observations_by_ids(self, incident_id: str, ids: list[str]) -> dict[str, NormalizedObservation]: ...
    def list_issues(self, incident_id: str) -> list[StoredIssue]: ...
    def count_incident_evidence(self, incident_id: str) -> dict[str, int]: ...

    def put_finding(self, finding: Finding, *, stored_at: datetime) -> PutResult: ...
    def get_finding(self, finding_id: str) -> Finding | None: ...
    def list_findings(self, incident_id: str, *, current_only: bool = True) -> list[Finding]: ...
    def finding_history(self, finding_id: str) -> list[Finding]: ...
    def independent_support(self, incident_id: str, finding_ids: list[str]) -> dict: ...
