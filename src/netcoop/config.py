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


def _authorized_parties() -> tuple[str, ...]:
    """Origins allowed as a session token's `azp`: CLERK_AUTHORIZED_PARTIES, else this service's own public URL
    (Render sets RENDER_EXTERNAL_URL) plus the configured CORS origins (e.g. a Netlify frontend)."""
    explicit = os.environ.get("CLERK_AUTHORIZED_PARTIES", "")
    raw = explicit.split(",") if explicit.strip() else [os.environ.get("RENDER_EXTERNAL_URL", ""),
                                                         *os.environ.get("NETCOOP_CORS_ORIGINS", "").split(",")]
    return tuple(dict.fromkeys(o.strip().rstrip("/") for o in raw if o.strip() and o.strip() != "*"))


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
    # Browser origins allowed to call the API cross-origin (e.g. a separate React dev server).
    cors_origins: tuple[str, ...] = ()
    # Directory with generated evaluation results (eval/results-*/results.json), served read-only.
    eval_dir: str | None = None
    # Optional built React app (frontend/dist). When set, it is served at / and the minimal UI moves to /legacy.
    frontend_dist: str | None = None
    # Authentication (src/netcoop/api/auth.py). None = derived: "token" if api_token is set, else "none".
    auth_mode: str | None = None
    clerk_publishable_key: str | None = None
    clerk_secret_key: str | None = None
    clerk_jwt_key: str | None = None
    clerk_issuer: str | None = None
    clerk_authorized_parties: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.auth_mode is None:
            object.__setattr__(self, "auth_mode", "token" if self.api_token else "none")

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
            eval_dir=os.environ.get("NETCOOP_EVAL_DIR") or (str(REPO_ROOT / "eval") if (REPO_ROOT / "eval").is_dir() else None),
            cors_origins=tuple(o.strip() for o in os.environ.get("NETCOOP_CORS_ORIGINS", "").split(",") if o.strip()),
            frontend_dist=os.environ.get("NETCOOP_FRONTEND_DIST") or None,
            auth_mode=(os.environ.get("NETCOOP_AUTH_MODE") or "").strip().lower() or None,
            # the same public key the frontend is built with may be reused (it only identifies the instance)
            clerk_publishable_key=os.environ.get("CLERK_PUBLISHABLE_KEY") or os.environ.get("VITE_CLERK_PUBLISHABLE_KEY") or None,
            clerk_secret_key=os.environ.get("CLERK_SECRET_KEY") or None,
            clerk_jwt_key=os.environ.get("CLERK_JWT_KEY") or None,
            clerk_issuer=os.environ.get("CLERK_ISSUER") or None,
            clerk_authorized_parties=_authorized_parties(),
        )
