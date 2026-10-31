"""Runtime settings read from environment variables (see .env.example)."""

from __future__ import annotations

import os
from dataclasses import dataclass


class ConfigError(ValueError):
    pass


def _int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError:
        raise ConfigError(f"{name} must be an integer, got {raw!r}") from None


@dataclass(frozen=True)
class Settings:
    # SQLAlchemy URL: sqlite:///path/to/netcoop.db  or  postgresql://user:pass@host:5432/db
    database_url: str | None
    db_connect_timeout_s: int = 3
    deployment_env: str = "development"
    # If set, every /api/* request needs "Authorization: Bearer <token>".
    api_token: str | None = None
    max_upload_bytes: int = 5 * 1024 * 1024
    max_records_per_batch: int = 10_000

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            database_url=os.environ.get("NETCOOP_DATABASE_URL") or None,
            db_connect_timeout_s=_int("NETCOOP_DB_CONNECT_TIMEOUT_S", 3),
            deployment_env=os.environ.get("NETCOOP_ENV", "development"),
            api_token=os.environ.get("NETCOOP_API_TOKEN") or None,
            max_upload_bytes=_int("NETCOOP_MAX_UPLOAD_BYTES", 5 * 1024 * 1024),
            max_records_per_batch=_int("NETCOOP_MAX_RECORDS_PER_BATCH", 10_000),
        )
