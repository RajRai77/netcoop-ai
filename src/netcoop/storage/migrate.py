"""Programmatic Alembic: upgrade/downgrade/current without an alembic.ini file."""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Engine

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


def _config(url: str | None = None, connection=None) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS_DIR))
    # URL goes in attributes, not the ini parser, so '%' in passwords is safe.
    cfg.attributes["url"] = url
    if connection is not None:
        cfg.attributes["connection"] = connection
    return cfg


def head_revision() -> str:
    return ScriptDirectory.from_config(_config()).get_current_head()


def upgrade(engine: Engine, revision: str = "head") -> None:
    with engine.begin() as conn:
        command.upgrade(_config(connection=conn), revision)


def downgrade(engine: Engine, revision: str) -> None:
    with engine.begin() as conn:
        command.downgrade(_config(connection=conn), revision)


def current_revision(engine: Engine) -> str | None:
    with engine.connect() as conn:
        return MigrationContext.configure(conn).get_current_revision()
