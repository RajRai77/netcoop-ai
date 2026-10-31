"""FastAPI entrypoint. Gate 0: health endpoints and a placeholder page only."""

from __future__ import annotations

from collections.abc import Callable

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse

from netcoop import __version__
from netcoop.api.health import CheckResult, check_postgres
from netcoop.config import Settings

PLACEHOLDER_HTML = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><title>NetCoop AI</title></head>
<body style="font-family: sans-serif; max-width: 40rem; margin: 3rem auto;">
<h1>NetCoop AI</h1>
<p><strong>Not yet implemented.</strong> This is the Gate 0 deployment skeleton.
No diagnosis, agents or telemetry ingestion exist yet, and nothing on this page
reflects real network data.</p>
<p>Health: <a href="/health/live">/health/live</a> &middot;
<a href="/health/ready">/health/ready</a></p>
<p>Version {version}</p>
</body></html>
"""


def create_app(
    settings: Settings | None = None,
    db_check: Callable[[], CheckResult] | None = None,
) -> FastAPI:
    settings = settings or Settings.from_env()
    if db_check is None:
        def db_check() -> CheckResult:
            return check_postgres(settings.database_url, settings.db_connect_timeout_s)

    app = FastAPI(title="NetCoop AI", version=__version__)

    @app.get("/health/live")
    def live() -> dict:
        # Process is up; deliberately does not touch the database.
        return {"status": "live", "version": __version__}

    @app.get("/health/ready")
    def ready() -> JSONResponse:
        db = db_check()
        body = {
            "status": "ready" if db.ok else "not_ready",
            "version": __version__,
            "checks": {"database": {"ok": db.ok, "detail": db.detail}},
        }
        return JSONResponse(body, status_code=200 if db.ok else 503)

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return PLACEHOLDER_HTML.format(version=__version__)

    return app


app = create_app()
