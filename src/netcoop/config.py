"""Runtime settings read from environment variables (see .env.example)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


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


def _bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    if raw.lower() in ("1", "true", "yes", "on"):
        return True
    if raw.lower() in ("0", "false", "no", "off"):
        return False
    raise ConfigError(f"{name} must be true/false, got {raw!r}")


def _default_scenarios_dir() -> str | None:
    d = REPO_ROOT / "data" / "scenarios"
    return str(d) if d.is_dir() else None


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
    # Specialist A2A endpoints: JSON {"performance-agent": "http://host:port/", ...}
    agents: str | None = None
    agent_token: str | None = None
    # Testing/evaluation only: run specialists inside this process (reports say transport=in-process).
    allow_in_process_agents: bool = False
    scenarios_dir: str | None = None
    uploads_dir: str | None = None
    resume_on_start: bool = True
    task_timeout_s: int = 20

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            database_url=os.environ.get("NETCOOP_DATABASE_URL") or None,
            db_connect_timeout_s=_int("NETCOOP_DB_CONNECT_TIMEOUT_S", 3),
            deployment_env=os.environ.get("NETCOOP_ENV", "development"),
            api_token=os.environ.get("NETCOOP_API_TOKEN") or None,
            max_upload_bytes=_int("NETCOOP_MAX_UPLOAD_BYTES", 5 * 1024 * 1024),
            max_records_per_batch=_int("NETCOOP_MAX_RECORDS_PER_BATCH", 10_000),
            agents=os.environ.get("NETCOOP_AGENTS") or None,
            agent_token=os.environ.get("NETCOOP_AGENT_TOKEN") or None,
            allow_in_process_agents=_bool("NETCOOP_ALLOW_IN_PROCESS_AGENTS", False),
            scenarios_dir=os.environ.get("NETCOOP_SCENARIOS_DIR") or _default_scenarios_dir(),
            uploads_dir=os.environ.get("NETCOOP_ARCHIVE_UPLOADS_DIR") or None,
            resume_on_start=_bool("NETCOOP_RESUME_ON_START", True),
            task_timeout_s=_int("NETCOOP_TASK_TIMEOUT_S", 20),
        )
