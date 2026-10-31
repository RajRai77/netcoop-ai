"""Engine factory. The only place that knows about SQLite vs PostgreSQL connection details."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.engine import make_url


class DatabaseConfigError(ValueError):
    pass


def normalize_url(url: str) -> str:
    """Accept 'postgresql://' (libpq style) and select the installed psycopg 3 driver."""
    if not url or not url.strip():
        raise DatabaseConfigError("database URL is empty")
    url = url.strip()
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    backend = make_url(url).get_backend_name()
    if backend not in ("sqlite", "postgresql"):
        raise DatabaseConfigError(f"unsupported database backend {backend!r}; use sqlite or postgresql")
    return url


def make_engine(url: str, *, connect_timeout_s: int = 5) -> Engine:
    url = normalize_url(url)
    u = make_url(url)
    if u.get_backend_name() == "sqlite":
        if u.database and u.database != ":memory:":
            parent = Path(u.database).expanduser().resolve().parent
            if not parent.exists():
                raise DatabaseConfigError(f"SQLite directory does not exist: {parent}")
        engine = create_engine(url, connect_args={"check_same_thread": False, "timeout": 30})

        @event.listens_for(engine, "connect")
        def _sqlite_pragmas(dbapi_conn, _record):  # pragma: no cover - exercised by every sqlite test
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")  # SQLite does not enforce FKs unless asked
            cur.execute("PRAGMA busy_timeout=30000")
            cur.close()

        return engine
    return create_engine(url, pool_pre_ping=True, connect_args={"connect_timeout": connect_timeout_s})


def redact(url: str) -> str:
    try:
        return make_url(normalize_url(url)).render_as_string(hide_password=True)
    except Exception:
        return "<unparseable database URL>"
