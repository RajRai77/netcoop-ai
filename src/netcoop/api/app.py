"""FastAPI entrypoint: evidence API, diagnosis workflow API and the browser UI.

Diagnosis runs in a background thread and is driven by the DB-persisted coordinator.
Specialists are reached over A2A (NETCOOP_AGENTS). In-process specialists are only
allowed when NETCOOP_ALLOW_IN_PROCESS_AGENTS=true (tests); reports label the transport.
"""

from __future__ import annotations

import json
import threading
import uuid
from collections.abc import Callable
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from netcoop import __version__
from netcoop.agents.protocol import SPECIALISTS
from netcoop.api.health import CheckResult, check_database
from netcoop.config import Settings
from netcoop.engine.planner import VerificationPolicy
from netcoop.evidence.adapters import builtin_profile, list_builtin_profiles, validate_profile
from netcoop.evidence.errors import EvidenceError, IssueCode
from netcoop.evidence.models import DataMode, TopologySnapshot
from netcoop.evidence.normalize import Limits
from netcoop.evidence.registry import default_registry
from netcoop.evidence.timeutil import parse_timestamp, utcnow
from netcoop.knowledge import detector_rules, fault_library
from netcoop.ledger import ingest_telemetry
from netcoop.orchestration.coordinator import Coordinator, CoordinatorOptions, incident_lock
from netcoop.orchestration.ports import InProcessAgentPort, TransportError, ports_from_config
from netcoop.scenarios.loader import list_scenarios, load_into
from netcoop.spec import validator
from netcoop.storage import SqlEvidenceStore, make_engine, migrate
from netcoop.storage.investigation import TERMINAL_STATES

WEB_DIR = Path(__file__).resolve().parents[1] / "web"


class CreateIncident(BaseModel):
    model_config = ConfigDict(extra="forbid")

    data_mode: DataMode | None = None
    title: str | None = Field(default=None, max_length=500)
    topology: dict | None = None
    scenario_id: str | None = Field(default=None, max_length=120)
    reference_time: str | None = Field(default=None, description="Capture time used as freshness reference")


class DiagnoseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    verification: bool = True
    max_rounds: int = Field(default=2, ge=0, le=5)
    total_budget: int = Field(default=6, ge=0, le=20)


def _error(status: int, code: str, message: str, issues=None) -> JSONResponse:
    body = {"error": {"code": code, "message": message}}
    if issues is not None:
        body["error"]["issues"] = [i.model_dump(mode="json") for i in issues]
    return JSONResponse(body, status_code=status)


def create_app(settings: Settings | None = None, db_check: Callable[[], CheckResult] | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    engine = make_engine(settings.database_url, connect_timeout_s=settings.db_connect_timeout_s) \
        if settings.database_url else None
    store = SqlEvidenceStore(engine) if engine is not None else None
    head = migrate.head_revision()
    limits = Limits(max_payload_bytes=settings.max_upload_bytes, max_records=settings.max_records_per_batch)
    scenarios_dir = Path(settings.scenarios_dir) if settings.scenarios_dir else None
    uploads_dir = Path(settings.uploads_dir) if settings.uploads_dir else None
    a2a_ports = ports_from_config(settings.agents, settings.agent_token)
    if db_check is None:
        def db_check() -> CheckResult:
            return check_database(engine, head)

    def make_ports():
        if a2a_ports:
            return a2a_ports
        if settings.allow_in_process_agents:
            return [InProcessAgentPort(a, scenarios_dir, uploads_dir) for a in SPECIALISTS]
        return []

    runs: dict[str, threading.Thread] = {}

    def start_run(incident_id: str, opts: CoordinatorOptions) -> str:
        ports = make_ports()
        if not ports:
            raise HTTPException(503, "No specialist agents configured (set NETCOOP_AGENTS); "
                                     "start them with scripts/run_local.py")
        if incident_lock(incident_id).locked():
            raise HTTPException(409, f"a diagnosis for {incident_id} is already running")
        run_id = f"RUN-{uuid.uuid4().hex[:16]}"

        def work():
            try:
                Coordinator(store, ports, opts).run(incident_id, run_id)
            except Exception as exc:  # recorded as an event so the UI shows it
                store.append_event(incident_id, run_id, "OPERATIONAL_ERROR", "coordinator",
                                   {"error": f"{type(exc).__name__}: {exc}"}, utcnow())

        t = threading.Thread(target=work, name=f"diagnose-{incident_id}", daemon=True)
        runs[incident_id] = t
        t.start()
        return run_id

    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def lifespan(_app):
        resume()
        yield

    from netcoop.api.auth import AuthError, Authenticator, Principal

    authenticator = Authenticator(settings)  # raises AuthConfigError: unsafe or incomplete auth config never starts
    app = FastAPI(title="NetCoop AI", version=__version__, lifespan=lifespan)
    if settings.cors_origins:
        from fastapi.middleware.cors import CORSMiddleware

        if "*" in settings.cors_origins and authenticator.mode != "none":
            raise ValueError("NETCOOP_CORS_ORIGINS='*' is not allowed when authentication is enabled")
        app.add_middleware(CORSMiddleware, allow_origins=list(settings.cors_origins), allow_credentials=False,
                           allow_methods=["GET", "POST"], allow_headers=["Authorization", "Content-Type"],
                           expose_headers=["Content-Disposition"])

    @app.middleware("http")
    async def limit_body(request: Request, call_next):
        """Global request-size guard (endpoints that stream bodies also enforce it)."""
        declared = request.headers.get("content-length")
        if declared and declared.isdigit() and int(declared) > limits.max_payload_bytes:
            return _error(413, "PAYLOAD_TOO_LARGE", f"request body exceeds {limits.max_payload_bytes} bytes")
        if request.method in ("POST", "PUT", "PATCH") and declared is None and                 request.headers.get("transfer-encoding", "").lower() == "chunked" and request.url.path.startswith("/api/incidents")                 and not request.url.path.endswith(("/telemetry", "/archive")):
            return _error(411, "LENGTH_REQUIRED", "Content-Length is required for this endpoint")
        return await call_next(request)

    @app.exception_handler(EvidenceError)
    async def _evidence_error(_req: Request, exc: EvidenceError):
        status = 404 if exc.codes == [IssueCode.UNKNOWN_INCIDENT] else (
            413 if exc.codes == [IssueCode.PAYLOAD_TOO_LARGE] else 422)
        return _error(status, str(exc.issues[0].code), "request refused", exc.issues)

    def require_store() -> SqlEvidenceStore:
        if store is None:
            raise HTTPException(503, "database not configured (set NETCOOP_DATABASE_URL)")
        return store

    def require_auth(request: Request) -> Principal:
        """Authenticate, and in multi-user (Clerk) mode enforce incident ownership for every route that has an
        {incident_id} path parameter (reads, uploads, diagnosis, SSE stream, exports). Unknown and foreign incidents
        get the same 404, so incident ids of other users cannot be probed."""
        try:
            p = authenticator.authenticate(request.headers.get("authorization"))
        except AuthError as exc:
            raise HTTPException(401, exc.reason, headers={"WWW-Authenticate": "Bearer"}) from None
        request.state.principal = p
        iid = request.path_params.get("incident_id")
        if iid is not None and p.multi_user:
            inc = store.get_incident(iid) if store is not None else None
            if inc is None or inc.owner_id != p.user_id:
                raise HTTPException(404, f"incident {iid!r} not found")
        return p

    def catalog_auth(request: Request) -> None:
        """Shared, non-personal catalog (meta, agent status, recorded evaluation results): public in Clerk mode so
        the landing page can show live status to signed-out visitors; unchanged (token required) in token mode."""
        if authenticator.mode != "clerk":
            require_auth(request)

    api = [Depends(require_auth)]
    catalog = [Depends(catalog_auth)]

    def owner_of(request: Request) -> str | None:
        p: Principal = request.state.principal
        return p.user_id if p.multi_user else None

    def incident_or_404(s: SqlEvidenceStore, iid: str):
        inc = s.get_incident(iid)
        if inc is None:
            raise HTTPException(404, f"incident {iid!r} not found")
        return inc

    async def read_body(request: Request) -> bytes:
        declared = request.headers.get("content-length")
        if declared is not None and declared.isdigit() and int(declared) > limits.max_payload_bytes:
            raise EvidenceError.single(IssueCode.PAYLOAD_TOO_LARGE,
                                       f"payload is {declared} bytes; limit {limits.max_payload_bytes}")
        payload = bytearray()
        async for chunk in request.stream():
            payload.extend(chunk)
            if len(payload) > limits.max_payload_bytes:
                raise EvidenceError.single(IssueCode.PAYLOAD_TOO_LARGE, f"payload exceeds {limits.max_payload_bytes} bytes")
        return bytes(payload)

    # -- health & meta ------------------------------------------------------------------
    @app.get("/health/live")
    def live() -> dict:
        return {"status": "live", "version": __version__}

    @app.get("/health/ready")
    def ready() -> JSONResponse:
        db = db_check()
        return JSONResponse({"status": "ready" if db.ok else "not_ready", "version": __version__,
                             "checks": {"database": {"ok": db.ok, "detail": db.detail}}},
                            status_code=200 if db.ok else 503)

    @app.get("/api/meta", dependencies=catalog)
    def meta() -> dict:
        return {"version": __version__, "environment": settings.deployment_env,
                "metric_registry_version": default_registry().version,
                "detector_rules": detector_rules()["version"], "fault_library": fault_library()["version"],
                "agent_transport": "a2a" if a2a_ports else ("in-process" if settings.allow_in_process_agents else "none"),
                "auth_required": authenticator.mode != "none", "auth_mode": authenticator.mode, "max_upload_bytes": settings.max_upload_bytes,
                "uploads_archive_enabled": uploads_dir is not None}

    @app.get("/api/agents", dependencies=catalog)
    async def agents() -> dict:
        out = []
        for p in make_ports():
            entry = {"agent_id": p.agent_id, "transport": p.transport, "url": getattr(p, "url", None)}
            try:
                d = await p.discover(3)
                entry.update(status="available", skills=d.skills, metrics=sorted(d.metrics),
                             name=d.card.get("name"), version=d.card.get("version"))
            except TransportError as exc:
                entry.update(status="unavailable", error=f"{exc.kind}: {exc}")
            out.append(entry)
        return {"agents": out}

    eval_dir = Path(settings.eval_dir) if settings.eval_dir else None

    def _eval_sets() -> dict[str, Path]:
        if eval_dir is None or not eval_dir.is_dir():
            return {}
        return {d.name: d / "results.json" for d in sorted(eval_dir.iterdir()) if (d / "results.json").is_file()}

    @app.get("/api/evaluations", dependencies=catalog)
    def evaluations() -> dict:
        """Generated evaluation results committed in eval/ (summaries only; nothing computed here)."""
        out = []
        for name, path in _eval_sets().items():
            doc = json.loads(path.read_text(encoding="utf-8"))
            out.append({"name": name, "git_commit": doc.get("git_commit"), "knowledge": doc.get("knowledge"),
                        "platform": doc.get("platform"), "transport": doc.get("transport"),
                        "sets": {k: {"scenarios": v["scenarios"],
                                     "knowledge_frozen_before_generation": v.get("knowledge_frozen_before_generation"),
                                     "summary": v["summary"]} for k, v in doc["sets"].items()}})
        return {"evaluations": out, "note": "Synthetic data; generator and engine share authors (docs/21)."}

    @app.get("/api/evaluations/{name}", dependencies=catalog)
    def evaluation(name: str) -> JSONResponse:
        sets = _eval_sets()
        if name not in sets:
            raise HTTPException(404, f"evaluation {name!r} not found")
        return JSONResponse(json.loads(sets[name].read_text(encoding="utf-8")))

    @app.get("/api/profiles", dependencies=api)
    def profiles() -> dict:
        return {"profiles": [builtin_profile(p) for p in list_builtin_profiles()]}

    @app.get("/api/scenarios", dependencies=api)
    def scenarios() -> dict:
        return {"scenarios": list_scenarios(scenarios_dir) if scenarios_dir else []}

    # -- incidents & evidence -------------------------------------------------------------
    @app.get("/api/incidents", dependencies=api)
    def incidents(request: Request, limit: int = 100, s: SqlEvidenceStore = Depends(require_store)) -> dict:
        summaries = s.latest_report_summaries()
        out = []
        p: Principal = request.state.principal
        for inc in s.list_incidents(min(max(limit, 1), 500), owner_id=p.user_id, owned_only=p.multi_user):
            out.append({**inc.model_dump(mode="json"), "workflow": s.workflow_state(inc.incident_id),
                        "latest_report": summaries.get(inc.incident_id)})
        return {"incidents": out}

    @app.post("/api/incidents", status_code=201, dependencies=api)
    def create_incident(body: CreateIncident, request: Request, s: SqlEvidenceStore = Depends(require_store)) -> dict:
        now = utcnow()
        owner = owner_of(request)  # from the verified session only; never from the request body
        if body.scenario_id:
            if scenarios_dir is None:
                raise HTTPException(404, "no scenario directory configured")
            loaded = load_into(s, scenarios_dir, body.scenario_id, now=now, owner_id=owner)
            return {"incident": loaded["incident"].model_dump(mode="json"),
                    "ingestions": [r.model_dump(mode="json") for r in loaded["ingestions"]]}
        if body.data_mode is None:
            raise HTTPException(422, "data_mode is required unless scenario_id is given")
        topo_id = None
        if body.topology is not None:
            try:
                topo = TopologySnapshot.model_validate(body.topology)
            except ValueError as exc:
                raise EvidenceError.single(IssueCode.TOPOLOGY_INVALID, f"topology: {exc}") from None
            s.put_topology(topo, stored_at=now)
            topo_id = topo.topology_snapshot_id
        ref = None
        if body.reference_time:
            try:
                ref = parse_timestamp(body.reference_time)
            except ValueError as exc:
                raise EvidenceError.single(IssueCode.INVALID_TIMESTAMP, f"reference_time: {exc}") from None
        iid = f"INC-{uuid.uuid4().hex[:16]}"
        inc = s.create_incident(iid, body.data_mode, created_at=now, topology_snapshot_id=topo_id, title=body.title,
                                archive_ref=f"upload:{iid}" if uploads_dir else None, reference_time=ref,
                                owner_id=owner)
        return {"incident": inc.model_dump(mode="json"), "ingestions": []}

    @app.post("/api/incidents/{incident_id}/telemetry", dependencies=api)
    async def post_telemetry(incident_id: str, request: Request, profile: str | None = None,
                             s: SqlEvidenceStore = Depends(require_store)):
        payload = await read_body(request)
        prof = None
        if profile == "inline":
            raise HTTPException(422, "use POST /api/incidents/{id}/telemetry?profile=<builtin id>")
        if profile:
            prof = builtin_profile(profile)
        return ingest_telemetry(s, incident_id, payload, limits=limits, profile=prof).model_dump(mode="json")

    @app.post("/api/incidents/{incident_id}/archive", dependencies=api)
    async def post_archive(incident_id: str, request: Request, s: SqlEvidenceStore = Depends(require_store)):
        """Upload recorded observations that agents may query during verification (recorded_replay).
        They are NOT evidence until an agent returns them for a specific challenge."""
        inc = incident_or_404(s, incident_id)
        if uploads_dir is None or inc.archive_ref != f"upload:{incident_id}":
            raise HTTPException(409, "archive uploads are not enabled for this incident")
        payload = await read_body(request)
        try:
            doc = json.loads(payload)
        except ValueError as exc:
            raise EvidenceError.single(IssueCode.MALFORMED_JSON, f"archive is not JSON: {exc}") from None
        if not isinstance(doc, dict) or not isinstance(doc.get("batches"), list):
            raise EvidenceError.single(IssueCode.SCHEMA_INVALID, "archive must be {\"batches\": [TelemetryBatch...]}")
        for i, b in enumerate(doc["batches"]):
            errs = [e.message for e in validator("telemetry-batch").iter_errors(b)]
            if errs:
                raise EvidenceError.single(IssueCode.SCHEMA_INVALID, f"batch {i}: {errs[0]}")
            if b["source"]["data_mode"] != inc.data_mode:
                raise EvidenceError.single(IssueCode.DATA_MODE_MISMATCH, f"batch {i} data_mode differs from incident")
        uploads_dir.mkdir(parents=True, exist_ok=True)
        path = uploads_dir / f"{incident_id}.json"
        if path.exists():
            raise HTTPException(409, "an archive was already uploaded for this incident (archives are immutable)")
        path.write_text(json.dumps({"schema_version": "1.0.0", "archive_id": f"UPLOAD-{incident_id}",
                                    "batches": doc["batches"]}), encoding="utf-8")
        s.audit(incident_id, "archive_uploaded", {"batches": len(doc["batches"]),
                                                  "records": sum(len(b["records"]) for b in doc["batches"])}, utcnow())
        return {"archive_ref": inc.archive_ref, "batches": len(doc["batches"])}

    @app.get("/api/incidents/{incident_id}", dependencies=api)
    def get_incident(incident_id: str, s: SqlEvidenceStore = Depends(require_store)) -> dict:
        inc = incident_or_404(s, incident_id)
        wf = s.workflow_state(incident_id)
        return {"incident": inc.model_dump(mode="json"), "evidence_counts": s.count_incident_evidence(incident_id),
                "workflow": wf, "running": bool(wf and wf["state"] not in TERMINAL_STATES | {"INTERRUPTED"}
                                                and incident_lock(incident_id).locked()),
                "reports": s.list_reports(incident_id)}

    @app.get("/api/incidents/{incident_id}/evidence", dependencies=api)
    def get_evidence(incident_id: str, limit: int = 200, offset: int = 0, metric: str | None = None,
                     s: SqlEvidenceStore = Depends(require_store)) -> dict:
        incident_or_404(s, incident_id)
        limit = max(1, min(limit, 2000))
        obs = s.list_observations(incident_id, metric=metric, limit=limit, offset=max(0, offset))
        return {"incident_id": incident_id, "limit": limit, "offset": offset,
                "observations": [o.to_json_dict() for o in obs],
                "derived_rates": s.list_derived_rates(incident_id),
                "issues": [i.model_dump(mode="json") for i in s.list_issues(incident_id)]}

    @app.get("/api/incidents/{incident_id}/findings", dependencies=api)
    def get_findings(incident_id: str, all_revisions: bool = False, s: SqlEvidenceStore = Depends(require_store)):
        incident_or_404(s, incident_id)
        return {"findings": [f.to_json_dict() for f in s.list_findings(incident_id, current_only=not all_revisions)]}

    @app.get("/api/incidents/{incident_id}/timeline", dependencies=api)
    def timeline(incident_id: str, s: SqlEvidenceStore = Depends(require_store)) -> dict:
        incident_or_404(s, incident_id)
        attempts = s.list_attempts(incident_id)
        for a in attempts:
            a["detail"] = {k: v for k, v in a["detail"].items() if k != "response_text"}
        return {"events": s.list_events(incident_id), "attempts": attempts,
                "challenges": s.list_challenges(incident_id)}

    @app.get("/api/incidents/{incident_id}/stream", dependencies=api)
    async def stream(incident_id: str, request: Request, after: int = 0, s: SqlEvidenceStore = Depends(require_store)):
        """Server-Sent Events: `workflow` (workflow event), `attempt` (agent task attempt, no raw artifact),
        `challenge` (verification outcome), `report` (new report revision summary), `end` (run finished).
        Resume with ?after=<last workflow seq>. Read back from the ledger; nothing is synthesized."""
        import asyncio

        from fastapi.responses import StreamingResponse

        incident_or_404(s, incident_id)

        def sse(event: str, data: dict, eid: str | None = None) -> str:
            head = f"id: {eid}\n" if eid else ""
            return f"{head}event: {event}\ndata: {json.dumps(data, separators=(',', ':'))}\n\n"

        async def gen():
            last_seq, seen_attempts, seen_outcomes, last_rev = after, set(), set(), None
            idle = 0
            while True:
                if await request.is_disconnected():
                    return
                events, attempts, chs, reps = await asyncio.to_thread(lambda: (
                    s.list_events(incident_id), s.list_attempts(incident_id), s.list_challenges(incident_id),
                    s.list_reports(incident_id)))
                sent = False
                for e in events:
                    if e["seq"] > last_seq:
                        last_seq = e["seq"]
                        sent = True
                        yield sse("workflow", e, str(e["seq"]))
                for a in attempts:
                    if a["attempt_id"] not in seen_attempts:
                        seen_attempts.add(a["attempt_id"])
                        sent = True
                        yield sse("attempt", {**a, "detail": {k: v for k, v in a["detail"].items()
                                                                if k != "response_text"}})
                for c in chs:
                    for o in c["outcomes"]:
                        key = (c["challenge"]["challenge_id"], o["at"])
                        if key not in seen_outcomes:
                            seen_outcomes.add(key)
                            sent = True
                            yield sse("challenge", {"challenge": c["challenge"], "outcome": o})
                if reps and reps[-1]["revision"] != last_rev:
                    last_rev = reps[-1]["revision"]
                    sent = True
                    yield sse("report", reps[-1])
                running = incident_lock(incident_id).locked()
                if events and events[-1]["state"] in TERMINAL_STATES and not running:
                    yield sse("end", {"state": events[-1]["state"], "revision": last_rev})
                    return
                idle = 0 if sent else idle + 1
                if idle and idle % 15 == 0:
                    yield ": keep-alive\n\n"
                if idle > 600 and not running:  # nothing happening for ~10 min and no run: close
                    return
                await asyncio.sleep(1.0)

        return StreamingResponse(gen(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    @app.get("/api/incidents/{incident_id}/attempts/{attempt_id}", dependencies=api)
    def attempt(incident_id: str, attempt_id: str, s: SqlEvidenceStore = Depends(require_store)) -> dict:
        for a in s.list_attempts(incident_id):
            if a["attempt_id"] == attempt_id:
                return a
        raise HTTPException(404, "attempt not found")

    @app.get("/api/incidents/{incident_id}/topology", dependencies=api)
    def topology(incident_id: str, s: SqlEvidenceStore = Depends(require_store)) -> dict:
        inc = incident_or_404(s, incident_id)
        topo = s.get_topology(inc.topology_snapshot_id) if inc.topology_snapshot_id else None
        return {"topology": topo.to_json_dict() if topo else None}

    @app.post("/api/incidents/{incident_id}/diagnose", status_code=202, dependencies=api)
    def diagnose(incident_id: str, body: DiagnoseRequest | None = None, s: SqlEvidenceStore = Depends(require_store)):
        incident_or_404(s, incident_id)
        body = body or DiagnoseRequest()
        opts = CoordinatorOptions(task_timeout_s=settings.task_timeout_s, verification=VerificationPolicy(
            enabled=body.verification, max_rounds=body.max_rounds, total_budget=body.total_budget))
        return {"incident_id": incident_id, "run_id": start_run(incident_id, opts), "status": "started"}

    @app.get("/api/incidents/{incident_id}/report", dependencies=api)
    def report(incident_id: str, revision: int | None = None, s: SqlEvidenceStore = Depends(require_store)):
        incident_or_404(s, incident_id)
        r = s.get_report(incident_id, revision)
        if r is None:
            raise HTTPException(404, "no report yet; POST /api/incidents/{id}/diagnose")
        return JSONResponse(r, headers={"Content-Disposition": f'inline; filename="{incident_id}-r{r["revision"]}.json"'})

    @app.get("/api/incidents/{incident_id}/report.txt", dependencies=api)
    def report_text(incident_id: str, revision: int | None = None, s: SqlEvidenceStore = Depends(require_store)):
        r = s.get_report(incident_id, revision)
        if r is None:
            raise HTTPException(404, "no report yet")
        from netcoop.engine.text import report_to_text

        return PlainTextResponse(report_to_text(r))

    @app.get("/api/raw-records/{raw_id}", dependencies=api)
    def get_raw(raw_id: str, request: Request, s: SqlEvidenceStore = Depends(require_store)) -> dict:
        raw = s.get_raw_record(raw_id)
        p: Principal = request.state.principal
        if raw is not None and p.multi_user:
            inc = s.get_incident(raw.incident_id)
            if inc is None or inc.owner_id != p.user_id:
                raw = None  # same answer as a missing record
        if raw is None:
            raise HTTPException(404, f"raw record {raw_id!r} not found")
        return raw.model_dump(mode="json")

    @app.get("/api/profiles/{profile_id}", dependencies=api)
    def profile(profile_id: str) -> dict:
        return validate_profile(builtin_profile(profile_id))

    # -- UI --------------------------------------------------------------------------------
    if WEB_DIR.is_dir():
        app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")
    dist = Path(settings.frontend_dist).resolve() if settings.frontend_dist else None
    spa = dist is not None and (dist / "index.html").is_file()

    @app.get("/legacy" if spa else "/", include_in_schema=False)
    def index():
        return FileResponse(WEB_DIR / "index.html")

    if spa:
        # Built React app (single-origin deployment). API, health and docs routes above take precedence;
        # unknown /api/* and /health/* paths stay 404 instead of returning the app.
        if (dist / "assets").is_dir():
            app.mount("/assets", StaticFiles(directory=dist / "assets"), name="spa-assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa_route(path: str):
            if path.split("/", 1)[0] in ("api", "health", "static", "docs", "redoc", "openapi.json"):
                raise HTTPException(status_code=404, detail="Not Found")
            f = (dist / path).resolve()
            if path and f.is_file() and dist in f.parents:
                return FileResponse(f)
            return FileResponse(dist / "index.html")

    # -- crash recovery: resume runs that were interrupted (e.g. process killed) ------------------
    def resume() -> None:
        if store is None or not settings.resume_on_start or not db_check().ok:
            return
        for iid, run_id in store.unfinished_runs():
            store.append_event(iid, run_id, "INTERRUPTED", "coordinator",
                               {"reason": "process restarted while the run was in progress"}, utcnow())
            if make_ports():
                try:
                    start_run(iid, CoordinatorOptions(task_timeout_s=settings.task_timeout_s))
                except HTTPException:
                    pass

    app.state.store = store
    return app


def _app_from_env() -> FastAPI:
    from netcoop.procwatch import start_parent_watchdog

    start_parent_watchdog()  # only active when started by the local launcher
    return create_app()


app = _app_from_env()
