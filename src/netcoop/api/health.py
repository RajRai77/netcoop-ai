"""Dependency checks used by /health/ready."""

from __future__ import annotations

from dataclasses import dataclass

import psycopg


@dataclass(frozen=True)
class CheckResult:
    ok: bool
    detail: str


def check_postgres(database_url: str | None, timeout_s: int) -> CheckResult:
    """Open a connection and run SELECT 1. Never echo the URL (it holds credentials)."""
    if not database_url:
        return CheckResult(False, "NETCOOP_DATABASE_URL is not configured")
    try:
        with psycopg.connect(database_url, connect_timeout=timeout_s) as conn:
            conn.execute("SELECT 1").fetchone()
    except Exception as exc:  # report the failure type, not connection secrets
        return CheckResult(False, f"database unreachable ({type(exc).__name__})")
    return CheckResult(True, "ok")
