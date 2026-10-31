"""Investigation ledger: derived rates, workflow events, agent task attempts,
challenges + outcomes, evidence snapshots, report revisions; incident archive refs.

Revision ID: 0002
Revises: 0001
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

ID = 200
TS = 32
NEW_APPEND_ONLY = ("derived_rates", "workflow_events", "agent_task_attempts", "challenges",
                   "challenge_outcomes", "evidence_snapshots", "reports")


def upgrade() -> None:
    with op.batch_alter_table("incidents") as b:
        b.add_column(sa.Column("archive_ref", sa.String(ID), nullable=True))
        b.add_column(sa.Column("scenario_id", sa.String(ID), nullable=True))
        b.add_column(sa.Column("reference_time", sa.String(TS), nullable=True))
    op.create_table(
        "derived_rates",
        sa.Column("derived_id", sa.String(80), primary_key=True),
        sa.Column("incident_id", sa.String(ID), sa.ForeignKey("incidents.incident_id"), nullable=False),
        sa.Column("metric", sa.String(100), nullable=False),
        sa.Column("subject_key", sa.String(1000), nullable=False),
        sa.Column("window_end", sa.String(TS), nullable=False),
        sa.Column("body", sa.Text, nullable=False),
    )
    op.create_index("ix_rate_incident", "derived_rates", ["incident_id"])
    op.create_table(
        "workflow_events",
        sa.Column("event_pk", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("incident_id", sa.String(ID), sa.ForeignKey("incidents.incident_id"), nullable=False),
        sa.Column("run_id", sa.String(80), nullable=False),
        sa.Column("state", sa.String(40), nullable=False),
        sa.Column("actor", sa.String(ID), nullable=False),
        sa.Column("created_at", sa.String(TS), nullable=False),
        sa.Column("detail", sa.Text, nullable=False),
    )
    op.create_index("ix_wf_incident", "workflow_events", ["incident_id"])
    op.create_table(
        "agent_task_attempts",
        sa.Column("attempt_id", sa.String(80), primary_key=True),
        sa.Column("task_id", sa.String(ID), nullable=False),
        sa.Column("attempt_no", sa.Integer, nullable=False),
        sa.Column("incident_id", sa.String(ID), sa.ForeignKey("incidents.incident_id"), nullable=False),
        sa.Column("run_id", sa.String(80), nullable=False),
        sa.Column("agent_id", sa.String(ID), nullable=False),
        sa.Column("task_type", sa.String(20), nullable=False),
        sa.Column("transport", sa.String(20), nullable=False),
        sa.Column("outcome", sa.String(20), nullable=False),
        sa.Column("started_at", sa.String(TS), nullable=False),
        sa.Column("finished_at", sa.String(TS), nullable=False),
        sa.Column("detail", sa.Text, nullable=False),
    )
    op.create_index("ix_task_incident", "agent_task_attempts", ["incident_id"])
    op.create_table(
        "challenges",
        sa.Column("challenge_id", sa.String(ID), primary_key=True),
        sa.Column("incident_id", sa.String(ID), sa.ForeignKey("incidents.incident_id"), nullable=False),
        sa.Column("run_id", sa.String(80), nullable=False),
        sa.Column("created_at", sa.String(TS), nullable=False),
        sa.Column("body", sa.Text, nullable=False),
    )
    op.create_index("ix_challenge_incident", "challenges", ["incident_id"])
    op.create_table(
        "challenge_outcomes",
        sa.Column("outcome_pk", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("challenge_id", sa.String(ID), sa.ForeignKey("challenges.challenge_id"), nullable=False),
        sa.Column("outcome", sa.String(20), nullable=False),
        sa.Column("created_at", sa.String(TS), nullable=False),
        sa.Column("detail", sa.Text, nullable=False),
    )
    op.create_table(
        "evidence_snapshots",
        sa.Column("snapshot_id", sa.String(80), primary_key=True),
        sa.Column("incident_id", sa.String(ID), sa.ForeignKey("incidents.incident_id"), nullable=False),
        sa.Column("created_at", sa.String(TS), nullable=False),
        sa.Column("body", sa.Text, nullable=False),
    )
    op.create_table(
        "reports",
        sa.Column("report_pk", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("incident_id", sa.String(ID), sa.ForeignKey("incidents.incident_id"), nullable=False),
        sa.Column("revision", sa.Integer, nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("evidence_snapshot_id", sa.String(80), sa.ForeignKey("evidence_snapshots.snapshot_id"),
                  nullable=False),
        sa.Column("created_at", sa.String(TS), nullable=False),
        sa.Column("body", sa.Text, nullable=False),
        sa.UniqueConstraint("incident_id", "revision", name="uq_report_revision"),
    )
    _triggers(create=True)


def downgrade() -> None:
    _triggers(create=False)
    for t in ("reports", "evidence_snapshots", "challenge_outcomes", "challenges", "agent_task_attempts",
              "workflow_events", "derived_rates"):
        op.drop_table(t)
    with op.batch_alter_table("incidents") as b:
        b.drop_column("reference_time")
        b.drop_column("scenario_id")
        b.drop_column("archive_ref")


def _triggers(create: bool) -> None:
    dialect = op.get_bind().dialect.name
    for t in NEW_APPEND_ONLY:
        if dialect == "sqlite":
            for action in ("UPDATE", "DELETE"):
                name = f"{t}_no_{action.lower()}"
                if create:
                    op.execute(f"CREATE TRIGGER {name} BEFORE {action} ON {t} "
                               f"BEGIN SELECT RAISE(ABORT, 'netcoop: {t} is append-only'); END;")
                else:
                    op.execute(f"DROP TRIGGER IF EXISTS {name}")
        elif dialect == "postgresql":
            if create:
                op.execute(f"CREATE TRIGGER {t}_no_mutation BEFORE UPDATE OR DELETE ON {t} "
                           f"FOR EACH ROW EXECUTE FUNCTION netcoop_forbid_mutation();")
                op.execute(f"CREATE TRIGGER {t}_no_truncate BEFORE TRUNCATE ON {t} "
                           f"FOR EACH STATEMENT EXECUTE FUNCTION netcoop_forbid_mutation();")
            else:
                op.execute(f"DROP TRIGGER IF EXISTS {t}_no_mutation ON {t}")
                op.execute(f"DROP TRIGGER IF EXISTS {t}_no_truncate ON {t}")
        else:
            raise RuntimeError(f"append-only triggers not implemented for dialect {dialect!r}")
