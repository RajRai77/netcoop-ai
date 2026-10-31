"""FastAPI entrypoint.

Gate 1 scope: health, incident creation and validated evidence ingestion/read-back.
There is NO diagnosis yet (Gate 2); the UI page says so.
"""

from __future__ import annotations

import hmac
import uuid
from collections.abc import Callable

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from netcoop import __version__
from netcoop.api.health import CheckResult, check_database
from netcoop.config import Settings
from netcoop.evidence.errors import EvidenceError, IssueCode
from netcoop.evidence.models import DataMode, TopologySnapshot
from netcoop.evidence.normalize import Limits
from netcoop.evidence.registry import default_registry
from netcoop.evidence.timeutil import utcnow
from netcoop.ledger import ingest_telemetry
from netcoop.storage import SqlEvidenceStore, make_engine, migrate

PLACEHOLDER_HTML = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><title>NetCoop AI</title></head>
<body style="font-family: sans-serif; max-width: 44rem; margin: 3rem auto; line-height: 1.5">
<h1>NetCoop AI</h1>
<p><strong>Diagnosis: Not yet implemented.</strong> This build (Gate 1) validates and
stores telemetry evidence only. No agents run and no root cause is produced.
Nothing on this page reflects real network data.</p>
<ul>
<li>Health: <a href="/health/live">/health/live</a>, <a href="/health/ready">/health/ready</a></li>
<li>API docs: <a href="/docs">/docs</a></li>
<li>Metric registry version: {registry}</li>
</ul>
<p>Version {version}</p>
</body></html>
"""


class CreateIncident(BaseModel):
    model_config = ConfigDict(extra="forbid")

    data_mode: DataMode
    title: str | None = Field(default=None, max_length=500)
    topology: dict | None = None


def _error(status: int, code: str, message: str, issues=None) -> JSONResponse:
    body = {"error": {"code": code, "message": message}}
    if issues is not None:
        body["error"]["issues"] = [i.model_dump(mode="json") for i in issues]
    return JSONResponse(body, status_code=status)


def create_app(
    settings: Settings | None = None,
    db_check: Callable[[], CheckResult] | None = None,
) -> FastAPI:
    settings = settings or Settings.from_env()
    engine = make_engine(settings.database_url, connect_timeout_s=settings.db_connect_timeout_s) \
        if settings.database_url else None
    store = SqlEvidenceStore(engine) if engine is not None else None
    head = migrate.head_revision()
    limits = Limits(max_payload_bytes=settings.max_upload_bytes, max_records=settings.max_records_per_batch)
    if db_check is None:
        def db_check() -> CheckResult:
            return check_database(engine, head)

    app = FastAPI(title="NetCoop AI", version=__version__)

    @app.exception_handler(EvidenceError)
    async def _evidence_error(_req: Request, exc: EvidenceError):
        status = 404 if exc.codes == [IssueCode.UNKNOWN_INCIDENT] else (
            413 if exc.codes == [IssueCode.PAYLOAD_TOO_LARGE] else 422)
        return _error(status, str(exc.issues[0].code), "request refused", exc.issues)

    def require_store() -> SqlEvidenceStore:
        if store is None:
            raise HTTPException(503, "database not configured (set NETCOOP_DATABASE_URL)")
        return store

    def require_auth(request: Request) -> None:
        if settings.api_token is None:
            return
        header = request.headers.get("authorization", "")
        supplied = header[7:] if header.lower().startswith("bearer ") else ""
        if not hmac.compare_digest(supplied.encode(), settings.api_token.encode()):
            raise HTTPException(401, "missing or invalid bearer token", headers={"WWW-Authenticate": "Bearer"})

    api = [Depends(require_auth)]

    @app.get("/health/live")
    def live() -> dict:
        return {"status": "live", "version": __version__}  # deliberately no DB access

    @app.get("/health/ready")
    def ready() -> JSONResponse:
        db = db_check()
        return JSONResponse({
            "status": "ready" if db.ok else "not_ready",
            "version": __version__,
            "checks": {"database": {"ok": db.ok, "detail": db.detail}},
        }, status_code=200 if db.ok else 503)

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return PLACEHOLDER_HTML.format(version=__version__, registry=default_registry().version)

    @app.post("/api/incidents", status_code=201, dependencies=api)
    def create_incident(body: CreateIncident, s: SqlEvidenceStore = Depends(require_store)) -> dict:
        now = utcnow()
        topo_id = None
        if body.topology is not None:
            try:
                topo = TopologySnapshot.model_validate(body.topology)
            except ValueError as exc:
                raise EvidenceError.single(IssueCode.TOPOLOGY_INVALID, f"topology: {exc}") from None
            s.put_topology(topo, stored_at=now)
            topo_id = topo.topology_snapshot_id
        incident_id = f"INC-{uuid.uuid4().hex[:16]}"
        inc = s.create_incident(incident_id, body.data_mode, created_at=now,
                                topology_snapshot_id=topo_id, title=body.title)
        return {"incident": inc.model_dump(mode="json"), "status": "open",
                "diagnosis": "not implemented (Gate 2)"}

    @app.post("/api/incidents/{incident_id}/telemetry", dependencies=api)
    async def post_telemetry(incident_id: str, request: Request, s: SqlEvidenceStore = Depends(require_store)):
        declared = request.headers.get("content-length")
        if declared is not None and declared.isdigit() and int(declared) > limits.max_payload_bytes:
            raise EvidenceError.single(IssueCode.PAYLOAD_TOO_LARGE,
                                       f"payload is {declared} bytes; limit {limits.max_payload_bytes}")
        payload = bytearray()
        async for chunk in request.stream():
            payload.extend(chunk)
            if len(payload) > limits.max_payload_bytes:
                raise EvidenceError.single(IssueCode.PAYLOAD_TOO_LARGE,
                                           f"payload exceeds {limits.max_payload_bytes} bytes")
        report = ingest_telemetry(s, incident_id, bytes(payload), limits=limits)
        return report.model_dump(mode="json")

    @app.get("/api/incidents/{incident_id}", dependencies=api)
    def get_incident(incident_id: str, s: SqlEvidenceStore = Depends(require_store)) -> dict:
        inc = s.get_incident(incident_id)
        if inc is None:
            raise HTTPException(404, f"incident {incident_id!r} not found")
        return {"incident": inc.model_dump(mode="json"), "evidence_counts": s.count_incident_evidence(incident_id),
                "diagnosis": "not implemented (Gate 2)"}

    @app.get("/api/incidents/{incident_id}/evidence", dependencies=api)
    def get_evidence(incident_id: str, limit: int = 200, offset: int = 0, metric: str | None = None,
                     s: SqlEvidenceStore = Depends(require_store)) -> dict:
        if s.get_incident(incident_id) is None:
            raise HTTPException(404, f"incident {incident_id!r} not found")
        limit = max(1, min(limit, 1000))
        obs = s.list_observations(incident_id, metric=metric, limit=limit, offset=max(0, offset))
        return {
            "incident_id": incident_id, "limit": limit, "offset": offset,
            "observations": [o.to_json_dict() for o in obs],
            "issues": [i.model_dump(mode="json") for i in s.list_issues(incident_id)],
        }

    @app.get("/api/raw-records/{raw_id}", dependencies=api)
    def get_raw(raw_id: str, s: SqlEvidenceStore = Depends(require_store)) -> dict:
        raw = s.get_raw_record(raw_id)
        if raw is None:
            raise HTTPException(404, f"raw record {raw_id!r} not found")
        return raw.model_dump(mode="json")

    app.state.store = store
    return app


def _app_from_env() -> FastAPI:
    return create_app()


app = _app_from_env()
