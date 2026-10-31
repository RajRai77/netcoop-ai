"""Append-only investigation ledger: derived rates, workflow timeline, agent task
attempts, challenges and their outcomes, evidence snapshots, report revisions.

Mixed into SqlEvidenceStore so both SQLite and PostgreSQL share one implementation.
"""

from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import and_, func, select
from sqlalchemy.exc import IntegrityError

from netcoop.evidence.counters import CounterRate
from netcoop.evidence.errors import EvidenceError, IssueCode
from netcoop.evidence.ids import canonical_json, derive_id
from netcoop.evidence.timeutil import to_canonical
from netcoop.storage.tables import (
    agent_task_attempts,
    challenge_outcomes,
    challenges,
    derived_rates,
    evidence_snapshots,
    reports,
    workflow_events,
)

TERMINAL_STATES = {"DIAGNOSED", "AMBIGUOUS", "INSUFFICIENT_EVIDENCE", "UNKNOWN_FAULT", "HEALTHY", "OPERATIONAL_ERROR"}


def rate_to_dict(r: CounterRate) -> dict:
    return {
        "subject_key": r.subject_key, "metric": r.metric, "rate_metric": r.rate_metric, "value": r.value,
        "unit": r.unit, "window_start": to_canonical(r.window_start), "window_end": to_canonical(r.window_end),
        "input_observation_ids": list(r.input_observation_ids), "lineage_groups": list(r.lineage_groups),
        "transformation_id": r.transformation_id,
    }


class InvestigationStoreMixin:
    engine = None  # provided by SqlEvidenceStore

    # -- derived counter rates ------------------------------------------------------
    def put_derived_rates(self, incident_id: str, rates: list[CounterRate]) -> int:
        added = 0
        with self.engine.begin() as conn:
            for r in rates:
                did = derive_id("RATE", incident_id, *r.input_observation_ids, r.transformation_id)
                if conn.execute(select(derived_rates.c.derived_id).where(derived_rates.c.derived_id == did)).first():
                    continue
                body = {"derived_id": did, "incident_id": incident_id, **rate_to_dict(r)}
                conn.execute(derived_rates.insert().values(
                    derived_id=did, incident_id=incident_id, metric=r.rate_metric, subject_key=r.subject_key,
                    window_end=to_canonical(r.window_end), body=canonical_json(body)))
                added += 1
        return added

    def list_derived_rates(self, incident_id: str) -> list[dict]:
        q = select(derived_rates.c.body).where(derived_rates.c.incident_id == incident_id).order_by(
            derived_rates.c.window_end, derived_rates.c.derived_id)
        with self.engine.connect() as conn:
            return [json.loads(b) for b in conn.execute(q).scalars()]

    # -- workflow timeline ----------------------------------------------------------
    def append_event(self, incident_id: str, run_id: str, state: str, actor: str, detail: dict, at: datetime) -> None:
        with self.engine.begin() as conn:
            conn.execute(workflow_events.insert().values(
                incident_id=incident_id, run_id=run_id, state=state, actor=actor,
                created_at=to_canonical(at), detail=canonical_json(detail)))

    def list_events(self, incident_id: str) -> list[dict]:
        q = select(workflow_events).where(workflow_events.c.incident_id == incident_id).order_by(
            workflow_events.c.event_pk)
        with self.engine.connect() as conn:
            return [{"seq": r["event_pk"], "run_id": r["run_id"], "state": r["state"], "actor": r["actor"],
                     "at": r["created_at"], "detail": json.loads(r["detail"])} for r in conn.execute(q).mappings()]

    def workflow_state(self, incident_id: str) -> dict | None:
        q = select(workflow_events).where(workflow_events.c.incident_id == incident_id).order_by(
            workflow_events.c.event_pk.desc()).limit(1)
        with self.engine.connect() as conn:
            r = conn.execute(q).mappings().first()
        return {"state": r["state"], "run_id": r["run_id"], "at": r["created_at"]} if r else None

    def unfinished_runs(self) -> list[tuple[str, str]]:
        """(incident_id, run_id) whose latest event is not terminal - e.g. after a crash."""
        latest = select(workflow_events.c.incident_id, func.max(workflow_events.c.event_pk).label("pk")).group_by(
            workflow_events.c.incident_id).subquery()
        q = select(workflow_events.c.incident_id, workflow_events.c.run_id, workflow_events.c.state).join(
            latest, workflow_events.c.event_pk == latest.c.pk)
        with self.engine.connect() as conn:
            return [(i, r) for i, r, s in conn.execute(q) if s not in TERMINAL_STATES and s != "INTERRUPTED"]

    # -- agent task attempts ------------------------------------------------------------
    def record_attempt(self, a: dict) -> None:
        with self.engine.begin() as conn:
            conn.execute(agent_task_attempts.insert().values(
                attempt_id=a["attempt_id"], task_id=a["task_id"], attempt_no=a["attempt_no"],
                incident_id=a["incident_id"], run_id=a["run_id"], agent_id=a["agent_id"], task_type=a["task_type"],
                transport=a["transport"], outcome=a["outcome"], started_at=a["started_at"],
                finished_at=a["finished_at"], detail=canonical_json(a.get("detail", {}))))

    def list_attempts(self, incident_id: str) -> list[dict]:
        q = select(agent_task_attempts).where(agent_task_attempts.c.incident_id == incident_id).order_by(
            agent_task_attempts.c.started_at, agent_task_attempts.c.attempt_id)
        with self.engine.connect() as conn:
            rows = conn.execute(q).mappings().all()
        return [{**{k: r[k] for k in r.keys() if k != "detail"}, "detail": json.loads(r["detail"])} for r in rows]

    # -- challenges -------------------------------------------------------------------
    def put_challenge(self, challenge: dict, run_id: str, at: datetime) -> bool:
        with self.engine.begin() as conn:
            if conn.execute(select(challenges.c.challenge_id).where(
                    challenges.c.challenge_id == challenge["challenge_id"])).first():
                return False
            conn.execute(challenges.insert().values(
                challenge_id=challenge["challenge_id"], incident_id=challenge["incident_id"], run_id=run_id,
                created_at=to_canonical(at), body=canonical_json(challenge)))
        return True

    def put_challenge_outcome(self, challenge_id: str, outcome: str, detail: dict, at: datetime) -> None:
        with self.engine.begin() as conn:
            conn.execute(challenge_outcomes.insert().values(
                challenge_id=challenge_id, outcome=outcome, created_at=to_canonical(at), detail=canonical_json(detail)))

    def list_challenges(self, incident_id: str) -> list[dict]:
        with self.engine.connect() as conn:
            rows = conn.execute(select(challenges).where(challenges.c.incident_id == incident_id).order_by(
                challenges.c.created_at, challenges.c.challenge_id)).mappings().all()
            out = []
            for r in rows:
                outs = conn.execute(select(challenge_outcomes).where(
                    challenge_outcomes.c.challenge_id == r["challenge_id"]).order_by(
                    challenge_outcomes.c.outcome_pk)).mappings().all()
                out.append({"challenge": json.loads(r["body"]), "run_id": r["run_id"], "created_at": r["created_at"],
                            "outcomes": [{"outcome": o["outcome"], "at": o["created_at"],
                                          "detail": json.loads(o["detail"])} for o in outs]})
        return out

    # -- snapshots & reports ------------------------------------------------------------
    def put_snapshot(self, incident_id: str, body: dict, at: datetime) -> str:
        sid = derive_id("SNAP", incident_id, canonical_json(body))
        with self.engine.begin() as conn:
            if not conn.execute(select(evidence_snapshots.c.snapshot_id).where(
                    evidence_snapshots.c.snapshot_id == sid)).first():
                conn.execute(evidence_snapshots.insert().values(
                    snapshot_id=sid, incident_id=incident_id, created_at=to_canonical(at),
                    body=canonical_json({"snapshot_id": sid, "incident_id": incident_id, **body})))
        return sid

    def get_snapshot(self, snapshot_id: str) -> dict | None:
        with self.engine.connect() as conn:
            b = conn.execute(select(evidence_snapshots.c.body).where(
                evidence_snapshots.c.snapshot_id == snapshot_id)).scalar()
        return json.loads(b) if b else None

    def next_report_revision(self, incident_id: str) -> int:
        with self.engine.connect() as conn:
            cur = conn.execute(select(func.max(reports.c.revision)).where(reports.c.incident_id == incident_id)).scalar()
        return (cur or 0) + 1

    def put_report(self, report: dict, at: datetime) -> int:
        try:
            with self.engine.begin() as conn:
                conn.execute(reports.insert().values(
                    incident_id=report["incident_id"], revision=report["revision"], status=report["status"],
                    evidence_snapshot_id=report["evidence_snapshot_id"], created_at=to_canonical(at),
                    body=canonical_json(report)))
        except IntegrityError:
            raise EvidenceError.single(IssueCode.SCHEMA_INVALID,
                                       f"report revision {report['revision']} already exists or snapshot missing") from None
        return report["revision"]

    def get_report(self, incident_id: str, revision: int | None = None) -> dict | None:
        q = select(reports.c.body).where(reports.c.incident_id == incident_id)
        q = q.where(reports.c.revision == revision) if revision is not None else q.order_by(
            reports.c.revision.desc()).limit(1)
        with self.engine.connect() as conn:
            b = conn.execute(q).scalar()
        return json.loads(b) if b else None

    def list_reports(self, incident_id: str) -> list[dict]:
        q = select(reports.c.revision, reports.c.status, reports.c.created_at, reports.c.evidence_snapshot_id).where(
            reports.c.incident_id == incident_id).order_by(reports.c.revision)
        with self.engine.connect() as conn:
            return [dict(r) for r in conn.execute(q).mappings()]

    def latest_report_summaries(self) -> dict[str, dict]:
        latest = select(reports.c.incident_id, func.max(reports.c.revision).label("rev")).group_by(
            reports.c.incident_id).subquery()
        q = select(reports.c.incident_id, reports.c.revision, reports.c.status, reports.c.body).join(
            latest, and_(reports.c.incident_id == latest.c.incident_id, reports.c.revision == latest.c.rev))
        with self.engine.connect() as conn:
            out = {}
            for iid, rev, status, body in conn.execute(q):
                b = json.loads(body)
                out[iid] = {"revision": rev, "status": status, "suspected_root_cause": b.get("suspected_root_cause"),
                            "confidence_category": b.get("confidence_category")}
        return out
