"""Incident ownership for multi-user hosted deployments (Clerk authentication).

owner_id is the verified Clerk user id (`sub` claim) of the account that created the incident. It is nullable:
incidents created before this migration, and incidents created in single-operator modes (auth none/token), have no
owner. In Clerk mode the API only exposes incidents whose owner_id equals the caller's verified user id, so
pre-existing unowned records are NOT visible to any signed-in user (documented policy, docs/27).

Revision ID: 0003
Revises: 0002
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("incidents") as b:
        b.add_column(sa.Column("owner_id", sa.String(200), nullable=True))
    op.create_index("ix_incidents_owner_created", "incidents", ["owner_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_incidents_owner_created", table_name="incidents")
    with op.batch_alter_table("incidents") as b:
        b.drop_column("owner_id")
