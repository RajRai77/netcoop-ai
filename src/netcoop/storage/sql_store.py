"""SQLAlchemy implementation of EvidenceStore (SQLite and PostgreSQL, one code path)."""

from __future__ import annotations

import json
import uuid
from collections import Counter
from datetime import datetime

from sqlalchemy import Engine, and_, func, select
from sqlalchemy.exc import IntegrityError

from netcoop.evidence.errors import EvidenceError, Issue, IssueCode, Severity
from netcoop.evidence.ids import canonical_json, sha256_hex
from netcoop.evidence.integrity import independent_support, validate_finding, validate_topology
from netcoop.evidence.models import Finding, NormalizedObservation, RawRecord, SourceRef, TopologySnapshot
from netcoop.evidence.normalize import NormalizedBatch
from netcoop.evidence.timeutil import to_canonical
from netcoop.storage import migrate
from netcoop.storage.investigation import InvestigationStoreMixin
from netcoop.storage.repository import (
    Incident,
    IngestionReport,
    PutResult,
    RecordResult,
    StoredIssue,
)
from netcoop.storage.tables import (
    audit_events,
    finding_observation_refs,
    findings,
    incidents,
    ingestion_issues,
    ingestions,
    observations,
    raw_records,
    topology_snapshots,
)

STATUSES = ("accepted", "quarantined", "partially_rejected", "rejected", "duplicate", "conflict")


class SqlEvidenceStore(InvestigationStoreMixin):
    def __init__(self, engine: Engine):
        self.engine = engine

    # -- meta ----------------------------------------------------------------
    def schema_revision(self) -> str | None:
        return migrate.current_revision(self.engine)

    def audit(self, incident_id: str | None, event_type: str, detail: dict, at: datetime) -> None:
        with self.engine.begin() as conn:
            self._audit(conn, incident_id, event_type, detail, at)

    def _audit(self, conn, incident_id: str | None, event_type: str, detail: dict, at: datetime) -> None:
        conn.execute(audit_events.insert().values(
            incident_id=incident_id, event_type=event_type, created_at=to_canonical(at),
            detail=canonical_json(detail),
        ))

    # -- incidents -------------------------------------------------------------
    def create_incident(self, incident_id, data_mode, *, created_at, topology_snapshot_id=None, title=None,
                        archive_ref=None, scenario_id=None) -> Incident:
        inc = Incident(incident_id=incident_id, data_mode=data_mode, topology_snapshot_id=topology_snapshot_id,
                       title=title, created_at=created_at, archive_ref=archive_ref, scenario_id=scenario_id)
        with self.engine.begin() as conn:
            if topology_snapshot_id is not None and conn.execute(
                select(topology_snapshots.c.topology_snapshot_id).where(
                    topology_snapshots.c.topology_snapshot_id == topology_snapshot_id)
            ).first() is None:
                raise EvidenceError.single(IssueCode.UNKNOWN_TOPOLOGY,
                                           f"topology snapshot {topology_snapshot_id!r} is not stored")
            try:
                conn.execute(incidents.insert().values(
                    incident_id=incident_id, data_mode=inc.data_mode, topology_snapshot_id=topology_snapshot_id,
                    title=title, created_at=to_canonical(inc.created_at), archive_ref=archive_ref,
                    scenario_id=scenario_id,
                ))
            except IntegrityError:
                raise EvidenceError.single(IssueCode.SCHEMA_INVALID,
                                           f"incident {incident_id!r} already exists") from None
            self._audit(conn, incident_id, "incident_created",
                        {"data_mode": data_mode, "topology_snapshot_id": topology_snapshot_id}, inc.created_at)
        return inc

    def list_incidents(self, limit: int = 100) -> list[Incident]:
        q = select(incidents).order_by(incidents.c.created_at.desc(), incidents.c.incident_id).limit(limit)
        with self.engine.connect() as conn:
            return [Incident.model_validate(dict(r)) for r in conn.execute(q).mappings()]

    def get_incident(self, incident_id: str) -> Incident | None:
        with self.engine.connect() as conn:
            row = conn.execute(select(incidents).where(incidents.c.incident_id == incident_id)).mappings().first()
        return Incident.model_validate(dict(row)) if row else None

    # -- topology --------------------------------------------------------------
    def put_topology(self, snapshot: TopologySnapshot, *, stored_at: datetime) -> PutResult:
        validate_topology(snapshot)
        body = canonical_json(snapshot.to_json_dict())
        digest = sha256_hex(body)
        with self.engine.begin() as conn:
            existing = conn.execute(select(topology_snapshots.c.content_hash).where(
                topology_snapshots.c.topology_snapshot_id == snapshot.topology_snapshot_id)).scalar()
            if existing is not None:
                if existing == digest:
                    return "unchanged"
                raise EvidenceError.single(
                    IssueCode.TOPOLOGY_CONFLICT,
                    f"topology {snapshot.topology_snapshot_id!r} already stored with different content; "
                    "snapshots are immutable - use a new snapshot id",
                )
            conn.execute(topology_snapshots.insert().values(
                topology_snapshot_id=snapshot.topology_snapshot_id, content_hash=digest, kind=snapshot.kind,
                observed_at=to_canonical(snapshot.observed_at), stored_at=to_canonical(stored_at), body=body,
            ))
            self._audit(conn, None, "topology_stored",
                        {"topology_snapshot_id": snapshot.topology_snapshot_id, "content_hash": digest}, stored_at)
        return "created"

    def get_topology(self, topology_snapshot_id: str) -> TopologySnapshot | None:
        with self.engine.connect() as conn:
            body = conn.execute(select(topology_snapshots.c.body).where(
                topology_snapshots.c.topology_snapshot_id == topology_snapshot_id)).scalar()
        return TopologySnapshot.model_validate(json.loads(body)) if body else None

    # -- ingestion -------------------------------------------------------------
    def commit_ingestion(self, batch: NormalizedBatch) -> IngestionReport:
        try:
            return self._commit_ingestion(batch)
        except IntegrityError:
            # A concurrent ingestion committed the same record first; re-classify once.
            return self._commit_ingestion(batch)

    def _commit_ingestion(self, batch: NormalizedBatch) -> IngestionReport:
        ingestion_id = f"ING-{uuid.uuid4().hex}"
        issues: list[Issue] = list(batch.issues)
        results: list[RecordResult] = []
        obs_added = 0
        with self.engine.begin() as conn:
            if conn.execute(select(incidents.c.incident_id).where(
                    incidents.c.incident_id == batch.incident_id)).first() is None:
                raise EvidenceError.single(IssueCode.UNKNOWN_INCIDENT, f"incident {batch.incident_id!r} does not exist")

            raws_by_id = {r.raw_id: r for r in batch.raw_records}
            planned: list[tuple[RawRecord, str, list[NormalizedObservation]]] = []
            for out in batch.outcomes:
                status = out.status
                obs = batch.observations_for(out.raw_id) if status not in ("duplicate", "conflict", "rejected") else []
                if status == "duplicate":
                    results.append(RecordResult(record_index=out.record_index, record_id=out.record_id,
                                                raw_id=out.raw_id, status="duplicate", observation_ids=[]))
                    continue
                raw = raws_by_id[out.raw_id]
                exists = conn.execute(select(raw_records.c.raw_id).where(and_(
                    raw_records.c.incident_id == batch.incident_id,
                    raw_records.c.content_hash == raw.content_hash))).first()
                if exists is not None:
                    issues.append(Issue(code=IssueCode.DUPLICATE_RECORD, severity=Severity.WARNING,
                                        message="identical record already stored for this incident; not counted again",
                                        record_index=out.record_index, record_id=out.record_id))
                    results.append(RecordResult(record_index=out.record_index, record_id=out.record_id,
                                                raw_id=exists[0], status="duplicate", observation_ids=[]))
                    continue
                if obs and raw.source_record_id is not None:
                    clash = conn.execute(select(raw_records.c.raw_id).where(and_(
                        raw_records.c.incident_id == batch.incident_id,
                        raw_records.c.source_id == raw.source.source_id,
                        raw_records.c.source_record_id == raw.source_record_id,
                        raw_records.c.admission == "admitted"))).first()
                    if clash is not None:
                        issues.append(Issue(
                            code=IssueCode.RECORD_ID_CONFLICT, severity=Severity.REJECT,
                            message=f"record_id {raw.source_record_id!r} already admitted as {clash[0]} with "
                                    "different content; stored copy is kept, this one is rejected",
                            record_index=out.record_index, record_id=out.record_id))
                        status, obs = "conflict", []
                planned.append((raw, "admitted" if obs else "rejected", obs))
                results.append(RecordResult(record_index=out.record_index, record_id=out.record_id,
                                            raw_id=raw.raw_id, status=status,
                                            observation_ids=[o.observation_id for o in obs]))

            counts = Counter(r.status for r in results)
            summary = {
                "records": len(results), **{s: counts.get(s, 0) for s in STATUSES},
                "observations_added": sum(len(o) for _, _, o in planned),
                "issues": len(issues), "metric_registry_version": batch.registry_version,
            }
            conn.execute(ingestions.insert().values(
                ingestion_id=ingestion_id, incident_id=batch.incident_id, batch_id=batch.batch_id,
                source_id=batch.source.source_id, received_at=to_canonical(batch.ingested_at),
                summary=canonical_json(summary),
            ))
            for raw, admission, obs in planned:
                conn.execute(raw_records.insert().values(
                    raw_id=raw.raw_id, incident_id=raw.incident_id, content_hash=raw.content_hash,
                    source_id=raw.source.source_id, source_type=raw.source.source_type,
                    data_mode=raw.source.data_mode, source_schema=raw.source_schema,
                    source_record_id=raw.source_record_id, batch_id=raw.batch_id, ingestion_id=ingestion_id,
                    admission=admission, received_at=to_canonical(raw.received_at), content=raw.content,
                ))
                for o in obs:
                    conn.execute(observations.insert().values(
                        observation_id=o.observation_id, incident_id=o.incident_id, raw_id=o.raw_record_ref,
                        lineage_group=o.lineage_group, metric=o.measurement.metric,
                        subject_key=o.subject.key(), observed_at=to_canonical(o.observed_at),
                        validation=o.quality.validation, freshness=o.quality.freshness,
                        registry_version=o.metric_registry_version, body=canonical_json(o.to_json_dict()),
                    ))
                    obs_added += 1
            stored_raw = {raw.raw_id for raw, _, _ in planned}
            idx_to_raw = {r.record_index: r.raw_id for r in results}
            for issue in issues:
                raw_ref = idx_to_raw.get(issue.record_index) if issue.record_index is not None else None
                conn.execute(ingestion_issues.insert().values(
                    ingestion_id=ingestion_id, incident_id=batch.incident_id,
                    raw_id=raw_ref if raw_ref in stored_raw else None,
                    code=str(issue.code), severity=str(issue.severity), record_index=issue.record_index,
                    measurement_index=issue.measurement_index, message=issue.message,
                ))
            self._audit(conn, batch.incident_id, "telemetry_ingested",
                        {"ingestion_id": ingestion_id, **summary}, batch.ingested_at)

        return IngestionReport(
            ingestion_id=ingestion_id, incident_id=batch.incident_id, batch_id=batch.batch_id,
            received_at=batch.ingested_at, metric_registry_version=batch.registry_version,
            counts={"records": len(results), **{s: counts.get(s, 0) for s in STATUSES}},
            observations_added=obs_added, records=results, issues=issues,
        )

    def get_raw_record(self, raw_id: str) -> RawRecord | None:
        with self.engine.connect() as conn:
            r = conn.execute(select(raw_records).where(raw_records.c.raw_id == raw_id)).mappings().first()
        if r is None:
            return None
        return RawRecord(
            raw_id=r["raw_id"], incident_id=r["incident_id"], content_hash=r["content_hash"],
            source=SourceRef(source_id=r["source_id"], data_mode=r["data_mode"], source_type=r["source_type"]),
            source_schema=r["source_schema"], source_record_id=r["source_record_id"], batch_id=r["batch_id"],
            received_at=r["received_at"], content=r["content"],
        )

    def get_observation(self, observation_id: str) -> NormalizedObservation | None:
        with self.engine.connect() as conn:
            body = conn.execute(select(observations.c.body).where(
                observations.c.observation_id == observation_id)).scalar()
        return NormalizedObservation.model_validate(json.loads(body)) if body else None

    def list_observations(self, incident_id, *, metric=None, limit=1000, offset=0) -> list[NormalizedObservation]:
        q = select(observations.c.body).where(observations.c.incident_id == incident_id)
        if metric is not None:
            q = q.where(observations.c.metric == metric)
        q = q.order_by(observations.c.observed_at, observations.c.observation_id).limit(limit).offset(offset)
        with self.engine.connect() as conn:
            return [NormalizedObservation.model_validate(json.loads(b)) for b in conn.execute(q).scalars()]

    def observations_by_ids(self, incident_id, ids) -> dict[str, NormalizedObservation]:
        if not ids:
            return {}
        q = select(observations.c.body).where(and_(
            observations.c.incident_id == incident_id, observations.c.observation_id.in_(list(ids))))
        with self.engine.connect() as conn:
            obs = [NormalizedObservation.model_validate(json.loads(b)) for b in conn.execute(q).scalars()]
        return {o.observation_id: o for o in obs}

    def list_issues(self, incident_id) -> list[StoredIssue]:
        q = select(ingestion_issues).where(ingestion_issues.c.incident_id == incident_id).order_by(
            ingestion_issues.c.issue_pk)
        with self.engine.connect() as conn:
            rows = conn.execute(q).mappings().all()
        return [StoredIssue.model_validate({k: v for k, v in r.items() if k not in ("issue_pk", "incident_id")})
                for r in rows]

    def count_incident_evidence(self, incident_id) -> dict[str, int]:
        with self.engine.connect() as conn:
            def n(table) -> int:
                return conn.execute(select(func.count()).select_from(table).where(
                    table.c.incident_id == incident_id)).scalar_one()
            return {
                "raw_records": n(raw_records), "observations": n(observations), "issues": n(ingestion_issues),
                "ingestions": n(ingestions), "findings": n(findings),
            }

    # -- findings --------------------------------------------------------------
    def put_finding(self, finding: Finding, *, stored_at: datetime) -> PutResult:
        body = canonical_json(finding.to_json_dict())
        digest = sha256_hex(body)
        with self.engine.begin() as conn:
            existing = conn.execute(select(findings.c.content_hash).where(
                findings.c.finding_id == finding.finding_id)).scalar()
            if existing is not None:
                if existing == digest:
                    return "unchanged"  # idempotent re-delivery (e.g. duplicate agent artifact)
                raise EvidenceError.single(
                    IssueCode.FINDING_CONFLICT,
                    f"finding {finding.finding_id!r} already stored with different content; "
                    "findings are immutable - submit a revision with supersedes_finding_id",
                )
            if conn.execute(select(incidents.c.incident_id).where(
                    incidents.c.incident_id == finding.incident_id)).first() is None:
                raise EvidenceError.single(IssueCode.UNKNOWN_INCIDENT, f"incident {finding.incident_id!r} does not exist")
            obs = self._obs_map(conn, finding.incident_id, list(finding.observation_refs))
            superseded = None
            already = False
            if finding.supersedes_finding_id is not None:
                b = conn.execute(select(findings.c.body).where(
                    findings.c.finding_id == finding.supersedes_finding_id)).scalar()
                superseded = Finding.model_validate(json.loads(b)) if b else None
                already = conn.execute(select(findings.c.finding_id).where(
                    findings.c.supersedes_finding_id == finding.supersedes_finding_id)).first() is not None
            validate_finding(finding, obs, superseded, already)
            conn.execute(findings.insert().values(
                finding_id=finding.finding_id, incident_id=finding.incident_id, agent_id=finding.agent_id,
                claim=finding.claim, polarity=finding.polarity, supersedes_finding_id=finding.supersedes_finding_id,
                created_at=to_canonical(finding.created_at), stored_at=to_canonical(stored_at),
                content_hash=digest, body=body,
            ))
            for ref in finding.observation_refs:
                conn.execute(finding_observation_refs.insert().values(finding_id=finding.finding_id,
                                                                      observation_id=ref))
            self._audit(conn, finding.incident_id, "finding_stored",
                        {"finding_id": finding.finding_id, "agent_id": finding.agent_id,
                         "supersedes": finding.supersedes_finding_id}, stored_at)
        return "created"

    def _obs_map(self, conn, incident_id, ids) -> dict[str, NormalizedObservation]:
        q = select(observations.c.body).where(and_(
            observations.c.incident_id == incident_id, observations.c.observation_id.in_(ids)))
        obs = [NormalizedObservation.model_validate(json.loads(b)) for b in conn.execute(q).scalars()]
        return {o.observation_id: o for o in obs}

    def get_finding(self, finding_id) -> Finding | None:
        with self.engine.connect() as conn:
            b = conn.execute(select(findings.c.body).where(findings.c.finding_id == finding_id)).scalar()
        return Finding.model_validate(json.loads(b)) if b else None

    def list_findings(self, incident_id, *, current_only=True) -> list[Finding]:
        q = select(findings.c.body).where(findings.c.incident_id == incident_id)
        if current_only:
            newer = select(findings.c.supersedes_finding_id).where(findings.c.supersedes_finding_id.is_not(None))
            q = q.where(findings.c.finding_id.not_in(newer.scalar_subquery()))
        q = q.order_by(findings.c.created_at, findings.c.finding_id)
        with self.engine.connect() as conn:
            return [Finding.model_validate(json.loads(b)) for b in conn.execute(q).scalars()]

    def finding_history(self, finding_id) -> list[Finding]:
        """Revision chain containing finding_id, oldest first."""
        chain: list[Finding] = []
        with self.engine.connect() as conn:
            def load(fid):
                b = conn.execute(select(findings.c.body).where(findings.c.finding_id == fid)).scalar()
                return Finding.model_validate(json.loads(b)) if b else None
            cur = load(finding_id)
            if cur is None:
                return []
            while cur.supersedes_finding_id:  # walk back to the root
                prev = load(cur.supersedes_finding_id)
                if prev is None:
                    break
                cur = prev
            while cur is not None:
                chain.append(cur)
                nxt = conn.execute(select(findings.c.finding_id).where(
                    findings.c.supersedes_finding_id == cur.finding_id)).scalar()
                cur = load(nxt) if nxt else None
        return chain

    def independent_support(self, incident_id, finding_ids) -> dict:
        fs = [f for f in (self.get_finding(fid) for fid in finding_ids) if f is not None]
        if len(fs) != len(set(finding_ids)):
            raise EvidenceError.single(IssueCode.UNKNOWN_OBSERVATION_REF, "unknown finding id(s)")
        refs = sorted({r for f in fs for r in f.observation_refs})
        return independent_support(fs, self.observations_by_ids(incident_id, refs))
