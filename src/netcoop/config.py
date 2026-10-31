"""Runtime settings read from environment variables (see .env.example)."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    # libpq connection string, e.g. postgresql://user:pass@db:5432/netcoop
    database_url: str | None
    # Seconds allowed for the readiness DB probe.
    db_connect_timeout_s: int
    # Label shown in the UI/health output; diagnosis data modes come later (G1+).
    deployment_env: str

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            database_url=os.environ.get("NETCOOP_DATABASE_URL") or None,
            db_connect_timeout_s=int(os.environ.get("NETCOOP_DB_CONNECT_TIMEOUT_S", "3")),
            deployment_env=os.environ.get("NETCOOP_ENV", "development"),
        )
