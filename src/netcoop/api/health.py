"""Dependency checks used by /health/ready."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import Engine, text


@dataclass(frozen=True)
class CheckResult:
    ok: bool
    detail: str


def check_database(engine: Engine | None, expected_revision: str) -> CheckResult:
    """Connect, run SELECT 1 and require the schema to be migrated to head.

    Never echoes the URL (it can hold credentials); reports only the error type.
    """
    if engine is None:
        return CheckResult(False, "NETCOOP_DATABASE_URL is not configured")
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1")).fetchone()
        from netcoop.storage.migrate import current_revision

        rev = current_revision(engine)
    except Exception as exc:
        return CheckResult(False, f"database unreachable ({type(exc).__name__})")
    if rev != expected_revision:
        return CheckResult(False, f"schema revision {rev!r}, expected {expected_revision!r}; run `netcoop db upgrade`")
    return CheckResult(True, "ok")
