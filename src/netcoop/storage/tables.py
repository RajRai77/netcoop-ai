"""SQLAlchemy Core table definitions (single implementation for SQLite and PostgreSQL).

Timestamps are stored as fixed-width canonical UTC text (see timeutil.to_canonical)
so ordering and round-trips are identical on both backends. Full NDEP documents are
stored as canonical JSON text in `body`; indexed columns exist only for lookup.
"""

from __future__ import annotations

from sqlalchemy import (
    Column,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
    text,
)

metadata = MetaData()

ID = 200
TS = 32

incidents = Table(
    "incidents", metadata,
    Column("incident_id", String(ID), primary_key=True),
    Column("data_mode", String(20), nullable=False),
    Column("topology_snapshot_id", String(ID), ForeignKey("topology_snapshots.topology_snapshot_id"), nullable=True),
    Column("title", String(500), nullable=True),
    Column("created_at", String(TS), nullable=False),
)

topology_snapshots = Table(
    "topology_snapshots", metadata,
    Column("topology_snapshot_id", String(ID), primary_key=True),
    Column("content_hash", String(64), nullable=False),
    Column("kind", String(20), nullable=False),
    Column("observed_at", String(TS), nullable=False),
    Column("stored_at", String(TS), nullable=False),
    Column("body", Text, nullable=False),
)

raw_records = Table(
    "raw_records", metadata,
    Column("raw_id", String(80), primary_key=True),
    Column("incident_id", String(ID), ForeignKey("incidents.incident_id"), nullable=False),
    Column("content_hash", String(64), nullable=False),
    Column("source_id", String(ID), nullable=False),
    Column("source_type", String(100), nullable=False),
    Column("data_mode", String(20), nullable=False),
    Column("source_schema", String(100), nullable=False),
    Column("source_record_id", String(ID), nullable=True),
    Column("batch_id", String(ID), nullable=True),
    Column("ingestion_id", String(80), ForeignKey("ingestions.ingestion_id"), nullable=False),
    Column("admission", String(10), nullable=False),  # admitted | rejected
    Column("received_at", String(TS), nullable=False),
    Column("content", Text, nullable=False),
    UniqueConstraint("incident_id", "content_hash", name="uq_raw_incident_content"),
)
# A source record id identifies at most one *admitted* raw record per incident and source.
Index(
    "uq_raw_admitted_source_record", raw_records.c.incident_id, raw_records.c.source_id,
    raw_records.c.source_record_id, unique=True,
    sqlite_where=text("admission = 'admitted' AND source_record_id IS NOT NULL"),
    postgresql_where=text("admission = 'admitted' AND source_record_id IS NOT NULL"),
)

observations = Table(
    "observations", metadata,
    Column("observation_id", String(80), primary_key=True),
    Column("incident_id", String(ID), ForeignKey("incidents.incident_id"), nullable=False),
    Column("raw_id", String(80), ForeignKey("raw_records.raw_id"), nullable=False),
    Column("lineage_group", String(80), nullable=False),
    Column("metric", String(100), nullable=False),
    Column("subject_key", String(1000), nullable=False),
    Column("observed_at", String(TS), nullable=False),
    Column("validation", String(12), nullable=False),
    Column("freshness", String(10), nullable=False),
    Column("registry_version", String(20), nullable=False),
    Column("body", Text, nullable=False),
)
Index("ix_obs_incident_metric", observations.c.incident_id, observations.c.metric)
Index("ix_obs_incident_time", observations.c.incident_id, observations.c.observed_at)
Index("ix_obs_lineage", observations.c.lineage_group)

ingestions = Table(
    "ingestions", metadata,
    Column("ingestion_id", String(80), primary_key=True),
    Column("incident_id", String(ID), ForeignKey("incidents.incident_id"), nullable=False),
    Column("batch_id", String(ID), nullable=True),
    Column("source_id", String(ID), nullable=False),
    Column("received_at", String(TS), nullable=False),
    Column("summary", Text, nullable=False),
)

ingestion_issues = Table(
    "ingestion_issues", metadata,
    Column("issue_pk", Integer, primary_key=True, autoincrement=True),
    Column("ingestion_id", String(80), ForeignKey("ingestions.ingestion_id"), nullable=False),
    Column("incident_id", String(ID), ForeignKey("incidents.incident_id"), nullable=False),
    Column("raw_id", String(80), ForeignKey("raw_records.raw_id"), nullable=True),
    Column("code", String(50), nullable=False),
    Column("severity", String(12), nullable=False),
    Column("record_index", Integer, nullable=True),
    Column("measurement_index", Integer, nullable=True),
    Column("message", Text, nullable=False),
)
Index("ix_issue_incident", ingestion_issues.c.incident_id)

findings = Table(
    "findings", metadata,
    Column("finding_id", String(ID), primary_key=True),
    Column("incident_id", String(ID), ForeignKey("incidents.incident_id"), nullable=False),
    Column("agent_id", String(ID), nullable=False),
    Column("claim", String(ID), nullable=False),
    Column("polarity", String(10), nullable=False),
    Column("supersedes_finding_id", String(ID), ForeignKey("findings.finding_id"), nullable=True, unique=True),
    Column("created_at", String(TS), nullable=False),
    Column("stored_at", String(TS), nullable=False),
    Column("content_hash", String(64), nullable=False),
    Column("body", Text, nullable=False),
)
Index("ix_finding_incident", findings.c.incident_id)

finding_observation_refs = Table(
    "finding_observation_refs", metadata,
    Column("finding_id", String(ID), ForeignKey("findings.finding_id"), primary_key=True),
    Column("observation_id", String(80), ForeignKey("observations.observation_id"), primary_key=True),
)

audit_events = Table(
    "audit_events", metadata,
    Column("event_pk", Integer, primary_key=True, autoincrement=True),
    Column("incident_id", String(ID), nullable=True),
    Column("event_type", String(50), nullable=False),
    Column("created_at", String(TS), nullable=False),
    Column("detail", Text, nullable=False),
)

# Tables whose rows may never be updated or deleted (enforced by DB triggers).
APPEND_ONLY_TABLES = (
    "topology_snapshots", "raw_records", "observations", "ingestions", "ingestion_issues",
    "findings", "finding_observation_refs", "audit_events",
)
