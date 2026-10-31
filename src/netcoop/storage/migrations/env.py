"""Alembic environment. Configured programmatically by netcoop.storage.migrate."""

from __future__ import annotations

from alembic import context

from netcoop.storage.engine import make_engine
from netcoop.storage.tables import metadata

config = context.config


def run_migrations_online() -> None:
    connection = config.attributes.get("connection")
    if connection is not None:
        _run(connection)
        return
    engine = make_engine(config.attributes["url"])
    try:
        with engine.begin() as conn:
            _run(conn)
    finally:
        engine.dispose()


def _run(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=metadata,
        render_as_batch=connection.dialect.name == "sqlite",
        transactional_ddl=True,
    )
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    raise RuntimeError("offline (SQL script) migrations are not supported; run `netcoop db upgrade`")
run_migrations_online()
