"""Gate 1 evidence foundation: incidents, topology, raw records, observations,
ingestions/issues, findings + refs, audit events; append-only triggers.

Revision ID: 0001
Revises:
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

ID = 200
TS = 32
APPEND_ONLY = (
    "topology_snapshots", "raw_records", "observations", "ingestions", "ingestion_issues",
    "findings", "finding_observation_refs", "audit_events",
)


def upgrade() -> None:
    op.create_table(
        "topology_snapshots",
        sa.Column("topology_snapshot_id", sa.String(ID), primary_key=True),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("observed_at", sa.String(TS), nullable=False),
        sa.Column("stored_at", sa.String(TS), nullable=False),
        sa.Column("body", sa.Text, nullable=False),
    )
    op.create_table(
        "incidents",
        sa.Column("incident_id", sa.String(ID), primary_key=True),
        sa.Column("data_mode", sa.String(20), nullable=False),
        sa.Column("topology_snapshot_id", sa.String(ID),
                  sa.ForeignKey("topology_snapshots.topology_snapshot_id"), nullable=True),
        sa.Column("title", sa.String(500), nullable=True),
        sa.Column("created_at", sa.String(TS), nullable=False),
    )
    op.create_table(
        "ingestions",
        sa.Column("ingestion_id", sa.String(80), primary_key=True),
        sa.Column("incident_id", sa.String(ID), sa.ForeignKey("incidents.incident_id"), nullable=False),
        sa.Column("batch_id", sa.String(ID), nullable=True),
        sa.Column("source_id", sa.String(ID), nullable=False),
        sa.Column("received_at", sa.String(TS), nullable=False),
        sa.Column("summary", sa.Text, nullable=False),
    )
    op.create_table(
        "raw_records",
        sa.Column("raw_id", sa.String(80), primary_key=True),
        sa.Column("incident_id", sa.String(ID), sa.ForeignKey("incidents.incident_id"), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("source_id", sa.String(ID), nullable=False),
        sa.Column("source_type", sa.String(100), nullable=False),
        sa.Column("data_mode", sa.String(20), nullable=False),
        sa.Column("source_schema", sa.String(100), nullable=False),
        sa.Column("source_record_id", sa.String(ID), nullable=True),
        sa.Column("batch_id", sa.String(ID), nullable=True),
        sa.Column("ingestion_id", sa.String(80), sa.ForeignKey("ingestions.ingestion_id"), nullable=False),
        sa.Column("admission", sa.String(10), nullable=False),
        sa.Column("received_at", sa.String(TS), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.UniqueConstraint("incident_id", "content_hash", name="uq_raw_incident_content"),
    )
    where = sa.text("admission = 'admitted' AND source_record_id IS NOT NULL")
    op.create_index(
        "uq_raw_admitted_source_record", "raw_records", ["incident_id", "source_id", "source_record_id"],
        unique=True, sqlite_where=where, postgresql_where=where,
    )
    op.create_table(
        "observations",
        sa.Column("observation_id", sa.String(80), primary_key=True),
        sa.Column("incident_id", sa.String(ID), sa.ForeignKey("incidents.incident_id"), nullable=False),
        sa.Column("raw_id", sa.String(80), sa.ForeignKey("raw_records.raw_id"), nullable=False),
        sa.Column("lineage_group", sa.String(80), nullable=False),
        sa.Column("metric", sa.String(100), nullable=False),
        sa.Column("subject_key", sa.String(1000), nullable=False),
        sa.Column("observed_at", sa.String(TS), nullable=False),
        sa.Column("validation", sa.String(12), nullable=False),
        sa.Column("freshness", sa.String(10), nullable=False),
        sa.Column("registry_version", sa.String(20), nullable=False),
        sa.Column("body", sa.Text, nullable=False),
    )
    op.create_index("ix_obs_incident_metric", "observations", ["incident_id", "metric"])
    op.create_index("ix_obs_incident_time", "observations", ["incident_id", "observed_at"])
    op.create_index("ix_obs_lineage", "observations", ["lineage_group"])
    op.create_table(
        "ingestion_issues",
        sa.Column("issue_pk", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("ingestion_id", sa.String(80), sa.ForeignKey("ingestions.ingestion_id"), nullable=False),
        sa.Column("incident_id", sa.String(ID), sa.ForeignKey("incidents.incident_id"), nullable=False),
        sa.Column("raw_id", sa.String(80), sa.ForeignKey("raw_records.raw_id"), nullable=True),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("severity", sa.String(12), nullable=False),
        sa.Column("record_index", sa.Integer, nullable=True),
        sa.Column("measurement_index", sa.Integer, nullable=True),
        sa.Column("message", sa.Text, nullable=False),
    )
    op.create_index("ix_issue_incident", "ingestion_issues", ["incident_id"])
    op.create_table(
        "findings",
        sa.Column("finding_id", sa.String(ID), primary_key=True),
        sa.Column("incident_id", sa.String(ID), sa.ForeignKey("incidents.incident_id"), nullable=False),
        sa.Column("agent_id", sa.String(ID), nullable=False),
        sa.Column("claim", sa.String(ID), nullable=False),
        sa.Column("polarity", sa.String(10), nullable=False),
        sa.Column("supersedes_finding_id", sa.String(ID), sa.ForeignKey("findings.finding_id"),
                  nullable=True, unique=True),
        sa.Column("created_at", sa.String(TS), nullable=False),
        sa.Column("stored_at", sa.String(TS), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("body", sa.Text, nullable=False),
    )
    op.create_index("ix_finding_incident", "findings", ["incident_id"])
    op.create_table(
        "finding_observation_refs",
        sa.Column("finding_id", sa.String(ID), sa.ForeignKey("findings.finding_id"), primary_key=True),
        sa.Column("observation_id", sa.String(80), sa.ForeignKey("observations.observation_id"), primary_key=True),
    )
    op.create_table(
        "audit_events",
        sa.Column("event_pk", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("incident_id", sa.String(ID), nullable=True),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("created_at", sa.String(TS), nullable=False),
        sa.Column("detail", sa.Text, nullable=False),
    )
    _create_append_only_triggers()


def downgrade() -> None:
    _drop_append_only_triggers()
    for t in ("audit_events", "finding_observation_refs", "findings", "ingestion_issues", "observations"):
        op.drop_table(t)
    op.drop_index("uq_raw_admitted_source_record", table_name="raw_records")
    for t in ("raw_records", "ingestions", "incidents", "topology_snapshots"):
        op.drop_table(t)


def _create_append_only_triggers() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "sqlite":
        for t in APPEND_ONLY:
            for action in ("UPDATE", "DELETE"):
                op.execute(
                    f"CREATE TRIGGER {t}_no_{action.lower()} BEFORE {action} ON {t} "
                    f"BEGIN SELECT RAISE(ABORT, 'netcoop: {t} is append-only'); END;"
                )
    elif dialect == "postgresql":
        op.execute(
            """
            CREATE FUNCTION netcoop_forbid_mutation() RETURNS trigger AS $$
            BEGIN
              RAISE EXCEPTION 'netcoop: % is append-only', TG_TABLE_NAME;
            END;
            $$ LANGUAGE plpgsql;
            """
        )
        for t in APPEND_ONLY:
            op.execute(
                f"CREATE TRIGGER {t}_no_mutation BEFORE UPDATE OR DELETE ON {t} "
                f"FOR EACH ROW EXECUTE FUNCTION netcoop_forbid_mutation();"
            )
            op.execute(
                f"CREATE TRIGGER {t}_no_truncate BEFORE TRUNCATE ON {t} "
                f"FOR EACH STATEMENT EXECUTE FUNCTION netcoop_forbid_mutation();"
            )
    else:
        raise RuntimeError(f"append-only triggers not implemented for dialect {dialect!r}")


def _drop_append_only_triggers() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "sqlite":
        for t in APPEND_ONLY:
            for action in ("update", "delete"):
                op.execute(f"DROP TRIGGER IF EXISTS {t}_no_{action}")
    elif dialect == "postgresql":
        for t in APPEND_ONLY:
            op.execute(f"DROP TRIGGER IF EXISTS {t}_no_mutation ON {t}")
            op.execute(f"DROP TRIGGER IF EXISTS {t}_no_truncate ON {t}")
        op.execute("DROP FUNCTION IF EXISTS netcoop_forbid_mutation()")
