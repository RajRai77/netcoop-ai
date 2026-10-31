"""Case coordinator: a DB-persisted workflow that runs one diagnosis.

NEW -> VALIDATING -> DISCOVERING -> INVESTIGATING -> CORRELATING
    -> (VERIFYING -> INVESTIGATING -> CORRELATING)*
    -> DIAGNOSED | AMBIGUOUS | INSUFFICIENT_EVIDENCE | UNKNOWN_FAULT | HEALTHY | OPERATIONAL_ERROR

Every transition is an append-only workflow event; every agent exchange is an
append-only task attempt with request/response hashes and A2A ids; each final
outcome is a new report revision. The coordinator is not a diagnostic specialist:
it never creates findings and never invents observations.
"""

from __future__ import annotations

import asyncio
import hashlib
import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from pydantic import ValidationError

from netcoop.agents.protocol import ProtocolError, dumps, loads
from netcoop.engine.planner import VerificationPolicy, challenge_doc, plan
from netcoop.engine.report import build_report
from netcoop.engine.stear import Stear
from netcoop.evidence.errors import EvidenceError
from netcoop.evidence.ids import derive_id
from netcoop.evidence.models import Finding
from netcoop.evidence.timeutil import to_canonical, utcnow
from netcoop.knowledge import detector_rules, fault_library
from netcoop.ledger import ingest_telemetry
from netcoop.orchestration.ports import Discovery, TransportError
from netcoop.topology import TopologyGraph

_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


def incident_lock(incident_id: str) -> threading.Lock:
    with _locks_guard:
        return _locks.setdefault(incident_id, threading.Lock())


@dataclass
class CoordinatorOptions:
    task_timeout_s: float = 20.0
    discover_timeout_s: float = 5.0
    retries: int = 1
    verification: VerificationPolicy = field(default_factory=VerificationPolicy)
    use_topology: bool = True
    use_temporal: bool = True


class Coordinator:
    def __init__(self, store, ports: list, options: CoordinatorOptions | None = None,
                 clock: Callable[[], datetime] = utcnow):
        self.store = store
        self.ports = {p.agent_id: p for p in ports}
        self.opt = options or CoordinatorOptions()
        self.clock = clock

    # -- public ---------------------------------------------------------------------
    def run(self, incident_id: str, run_id: str | None = None) -> dict:
        lock = incident_lock(incident_id)
        if not lock.acquire(blocking=False):
            raise RuntimeError(f"a diagnosis for {incident_id} is already running")
        try:
            return asyncio.run(self._run(incident_id, run_id or f"RUN-{uuid.uuid4().hex[:16]}"))
        finally:
            lock.release()

    # -- workflow ---------------------------------------------------------------------
    def _event(self, iid, run_id, state, detail=None, actor="coordinator"):
        self.store.append_event(iid, run_id, state, actor, detail or {}, self.clock())

    async def _run(self, iid: str, run_id: str) -> dict:
        inc = self.store.get_incident(iid)
        if inc is None:
            raise EvidenceError.single("UNKNOWN_INCIDENT", f"incident {iid!r} does not exist")
        self._event(iid, run_id, "NEW", {"agents_configured": sorted(self.ports),
                                         "transport": self._transport_label()})
        try:
            return await self._investigate(inc, run_id)
        except Exception as exc:  # honest operational failure, not a network diagnosis
            return self._operational_report(inc, run_id, [f"Coordinator failure: {type(exc).__name__}: {exc}"],
                                            {"error": f"{type(exc).__name__}: {exc}"})

    def _transport_label(self) -> str:
        kinds = {p.transport for p in self.ports.values()}
        return "a2a" if kinds == {"a2a"} else ("in-process" if kinds == {"in-process"} else "mixed")

    async def _investigate(self, inc, run_id: str) -> dict:
        iid = inc.incident_id
        topo_snap = self.store.get_topology(inc.topology_snapshot_id) if inc.topology_snapshot_id else None
        observations = self.store.list_observations(iid, limit=100_000)
        counts = {k: sum(1 for o in observations if o.quality.validation == k) for k in ("passed", "quarantined")}
        stale = sum(1 for o in observations if o.quality.freshness == "stale")
        issues = self.store.list_issues(iid)
        self._event(iid, run_id, "VALIDATING", {
            "observations": len(observations), **counts, "stale": stale,
            "rejected_issues": sum(1 for i in issues if i.severity == "reject"),
            "topology_snapshot_id": inc.topology_snapshot_id})
        extra_limits: list[str] = []
        if counts["quarantined"]:
            extra_limits.append(f"{counts['quarantined']} observation(s) quarantined (e.g. unknown subject) and not used.")
        if stale:
            extra_limits.append(f"{stale} stale observation(s) were kept but not used as current evidence.")
        rej = sum(1 for i in issues if i.severity == "reject")
        if rej:
            extra_limits.append(f"{rej} input record/measurement rejection(s) during validation (see evidence issues).")

        # DISCOVERING
        caps: dict[str, Discovery] = {}
        failed: dict[str, str] = {}
        for aid, port in sorted(self.ports.items()):
            t0 = self.clock()
            try:
                caps[aid] = await port.discover(self.opt.discover_timeout_s)
                outcome, err = "completed", None
            except TransportError as exc:
                failed[aid] = f"{exc.kind}: {exc}"
                outcome, err = exc.kind, str(exc)
            self.store.record_attempt({
                "attempt_id": f"AT-{uuid.uuid4().hex}", "task_id": derive_id("DISC", iid, run_id, aid, length=20),
                "attempt_no": 1, "incident_id": iid, "run_id": run_id, "agent_id": aid, "task_type": "discover",
                "transport": port.transport, "outcome": outcome, "started_at": to_canonical(t0),
                "finished_at": to_canonical(self.clock()),
                "detail": {"error": err, "skills": caps[aid].skills if aid in caps else None,
                           "metrics": sorted(caps[aid].metrics) if aid in caps else None}})
        self._event(iid, run_id, "DISCOVERING", {"available": sorted(caps), "unavailable": failed})
        for aid, why in failed.items():
            extra_limits.append(f"Specialist {aid} unavailable ({why}); its domain was not analysed.")
        if not caps:
            return self._operational_report(inc, run_id, extra_limits + ["No specialist agent could be reached."],
                                            {"agents_failed": failed})

        engine = Stear(TopologyGraph(topo_snap), use_topology=self.opt.use_topology,
                       use_temporal=self.opt.use_temporal)
        policy = self.opt.verification
        window = self._window(observations)
        requested: set[str] = set()
        challenges_out: list[dict] = []
        budget = policy.total_budget
        rounds = 0
        stop_reason = "verification disabled" if not policy.enabled else None
        agent_cov: dict[str, dict] = {}
        responded: set[str] = set()

        while True:
            observations = self.store.list_observations(iid, limit=100_000)
            await self._investigate_round(inc, run_id, observations, topo_snap, caps, rounds, agent_cov,
                                          responded, failed, extra_limits)
            if not responded:
                return self._operational_report(
                    inc, run_id, extra_limits + ["No specialist agent completed an investigation task; "
                                                 "nothing about the network was concluded."],
                    {"agents_failed": failed, "agents_available": sorted(caps)})
            findings = self.store.list_findings(iid)
            obs_map = {o.observation_id: o for o in observations}
            ev = engine.evaluate(findings, obs_map)
            self._event(iid, run_id, "CORRELATING", {
                "round": rounds, "status": ev.status, "category": ev.confidence_category,
                "leader": ev.leader.hid if ev.leader else None,
                "causes": [h.hid for h in ev.causes], "competitors": [h.hid for h in ev.competitors][:10],
                "hypotheses": len(ev.hypotheses), "present_symptoms": len(ev.present_symptoms)})
            if not policy.enabled:
                break
            if rounds >= policy.max_rounds:
                stop_reason = stop_reason or f"round limit ({policy.max_rounds}) reached"
                break
            checks = plan(ev, {a: d.metrics for a, d in caps.items()}, requested, budget, policy)
            if not checks:
                stop_reason = ("leading explanation already has high support" if ev.confidence_category == "high_support"
                               else "no further discriminating check is available" if budget > 0
                               else "verification budget exhausted")
                break
            rounds += 1
            obtained = 0
            self._event(iid, run_id, "VERIFYING", {"round": rounds, "checks": [
                {"agent": c.agent_id, "metric": c.metric, "subject": c.subject, "decides": c.decides} for c in checks]})
            for c in checks:
                requested.add(c.key)
                budget -= 1
                ch = challenge_doc(c, ev, iid, window, self.clock(), policy, self.opt.task_timeout_s)
                self.store.put_challenge(ch, run_id, self.clock())
                rec = await self._challenge(inc, run_id, ch, c)
                challenges_out.append(rec)
                obtained += rec["outcome"] == "obtained"
            if not obtained:
                stop_reason = "requested checks returned no new evidence"
                observations = self.store.list_observations(iid, limit=100_000)
                break

        # final snapshot + report revision
        findings = self.store.list_findings(iid)
        observations = self.store.list_observations(iid, limit=100_000)
        obs_map = {o.observation_id: o for o in observations}
        ev = engine.evaluate(findings, obs_map)
        snapshot_id = self.store.put_snapshot(iid, {
            "observation_ids": sorted(obs_map), "finding_ids": sorted(f.finding_id for f in findings),
            "topology_snapshot_id": inc.topology_snapshot_id,
            "knowledge": {"detector_rules": detector_rules()["version"], "fault_library": fault_library()["version"]},
        }, self.clock())
        coverage = {"agents_configured": sorted(self.ports), "agents_available": sorted(caps),
                    "agents_responded": sorted(responded), "agents_failed": failed, "per_agent": agent_cov}
        verification = {"enabled": policy.enabled, "rounds": rounds, "budget": policy.total_budget,
                        "checks_used": policy.total_budget - budget, "stopped_because": stop_reason,
                        "challenges": challenges_out}
        missing_agents = sorted(set(self.ports) - responded)
        if missing_agents and ev.status == "healthy":
            extra_limits.append("Healthy conclusion is limited to the domains of responding agents.")
        rev = self.store.next_report_revision(iid)
        report = build_report(incident=inc, revision=rev, run_id=run_id, ev=ev, findings=findings,
                              observations=obs_map, snapshot_id=snapshot_id,
                              topology_snapshot_id=inc.topology_snapshot_id, generated_at=self.clock(),
                              transport=self._report_transport(), coverage=coverage, verification=verification,
                              extra_limitations=extra_limits)
        self.store.put_report(report, self.clock())
        self._event(iid, run_id, ev.status.upper(), {"revision": rev, "snapshot_id": snapshot_id,
                                                      "suspected_root_cause": report["suspected_root_cause"],
                                                      "confidence_category": report["confidence_category"]})
        return report

    def _report_transport(self) -> str:
        return "a2a" if self._transport_label() == "a2a" else "in-process"

    @staticmethod
    def _window(observations) -> tuple[datetime, datetime]:
        times = [o.observed_at for o in observations] or [utcnow()]
        return min(times), max(times)

    # -- investigation tasks ------------------------------------------------------------
    async def _investigate_round(self, inc, run_id, observations, topo_snap, caps, round_no, agent_cov,
                                 responded, failed, extra_limits):
        prior = self.store.list_findings(inc.incident_id)
        analysis_time = to_canonical(max((o.observed_at for o in observations), default=self.clock()))
        jobs = []
        for aid, disc in sorted(caps.items()):
            domain = [o for o in observations if o.measurement.metric in disc.metrics]
            req = {
                "schema_version": "1.0.0", "task_type": "investigate", "incident_id": inc.incident_id,
                "agent_id": aid, "issued_at": to_canonical(self.clock()),
                "deadline_at": to_canonical(self.clock() + timedelta(seconds=self.opt.task_timeout_s)),
                "data_mode": inc.data_mode,
                "case": {"analysis_time": analysis_time, "observations": [o.to_json_dict() for o in domain],
                         "topology": topo_snap.to_json_dict() if topo_snap else None,
                         "prior_findings": [f.to_json_dict() for f in prior if f.agent_id == aid]},
            }
            # logical idempotency key: same agent + same evidence state -> same task id
            req["task_id"] = derive_id("TASK", inc.incident_id, aid, "investigate",
                                       *sorted(o.observation_id for o in domain), length=24)
            jobs.append(self._exchange(inc, run_id, aid, req, {o.observation_id for o in domain}))
        results = await asyncio.gather(*jobs)
        for aid, res in zip(sorted(caps), results):
            if res["outcome"] == "completed":
                responded.add(aid)
                agent_cov[aid] = res.get("coverage", {})
                failed.pop(aid, None)
            else:
                failed[aid] = f"{res['outcome']}: {res.get('error')}"
                msg = f"Specialist {aid} did not contribute in round {round_no} ({res['outcome']}: {res.get('error')})."
                if msg not in extra_limits:
                    extra_limits.append(msg)
        self._event(inc.incident_id, run_id, "INVESTIGATING", {
            "round": round_no, "results": {aid: {k: r.get(k) for k in ("outcome", "findings_stored",
                                                                        "findings_unchanged", "error")}
                                           for aid, r in zip(sorted(caps), results)}})

    async def _exchange(self, inc, run_id, aid, req: dict, allowed_refs: set[str]) -> dict:
        """Send one task with bounded retries; validate and persist its result."""
        port = self.ports[aid]
        text = dumps(req)
        req_hash = hashlib.sha256(text.encode()).hexdigest()
        last: dict = {"outcome": "failed", "error": "not attempted"}
        for attempt in range(1, self.opt.retries + 2):
            t0 = self.clock()
            detail = {"request_sha256": req_hash, "request_bytes": len(text)}
            try:
                reply = await port.send(text, self.opt.task_timeout_s)
                detail.update(reply.meta)
                detail["response_sha256"] = hashlib.sha256(reply.text.encode()).hexdigest()
                detail["response_text"] = reply.text if len(reply.text) <= 200_000 else None
                res = self._accept(inc, aid, req, reply.text, allowed_refs)
                outcome = res["outcome"]
                detail.update({k: v for k, v in res.items() if k not in ("coverage",)})
            except TransportError as exc:
                outcome, res = exc.kind, {"outcome": exc.kind, "error": str(exc)}
                detail["error"] = str(exc)
            self.store.record_attempt({
                "attempt_id": f"AT-{uuid.uuid4().hex}", "task_id": req["task_id"], "attempt_no": attempt,
                "incident_id": inc.incident_id, "run_id": run_id, "agent_id": aid, "task_type": req["task_type"],
                "transport": port.transport, "outcome": outcome, "started_at": to_canonical(t0),
                "finished_at": to_canonical(self.clock()), "detail": detail})
            last = res
            if outcome not in ("timeout", "unreachable"):
                break  # retry only transient transport failures; same logical task id
        return last

    def _accept(self, inc, aid, req, text: str, allowed_refs: set[str]) -> dict:
        try:
            res = loads(text, "agent-result")
        except ProtocolError as exc:
            return {"outcome": "invalid", "error": f"{exc.code}: {exc}"}
        if res["agent_id"] != aid or res["task_id"] != req["task_id"]:
            return {"outcome": "invalid", "error": "result agent_id/task_id does not match the request"}
        if res["status"] != "completed":
            return {"outcome": res["status"], "error": (res.get("error") or {}).get("message") or "; ".join(res["notes"]),
                    "result": res}
        if req["task_type"] == "verify":
            return {"outcome": "completed", "result": res}
        stored, unchanged, rejected = [], [], []
        for fd in res["findings"]:
            try:
                f = Finding.model_validate(fd)
            except ValidationError as exc:
                rejected.append(f"invalid finding: {exc.errors()[0]['msg']}")
                continue
            if f.agent_id != aid or f.incident_id != inc.incident_id:
                rejected.append(f"{f.finding_id}: agent/incident mismatch (possible spoofing)")
                continue
            if not set(f.observation_refs) <= allowed_refs:
                rejected.append(f"{f.finding_id}: references observations not sent to this agent")
                continue
            try:
                r = self.store.put_finding(f, stored_at=self.clock())
            except EvidenceError as exc:
                rejected.append(f"{f.finding_id}: {exc}")
                continue
            (stored if r == "created" else unchanged).append(f.finding_id)
        out = {"outcome": "completed" if not rejected else "partially_invalid", "findings_stored": stored,
               "findings_unchanged": unchanged, "findings_rejected": rejected, "coverage": res.get("coverage", {})}
        if rejected and not stored and not unchanged and res["findings"]:
            out["outcome"] = "invalid"
        if out["outcome"] == "partially_invalid":
            out["outcome"] = "completed"
            out["error"] = f"{len(rejected)} finding(s) rejected"
        return out

    async def _challenge(self, inc, run_id, ch: dict, check) -> dict:
        req = {"schema_version": "1.0.0", "task_type": "verify", "incident_id": inc.incident_id,
               "agent_id": ch["target_agent_id"], "issued_at": to_canonical(self.clock()),
               "deadline_at": ch["deadline_at"], "data_mode": inc.data_mode, "challenge": ch,
               "archive_ref": inc.archive_ref,
               "task_id": derive_id("TASK", inc.incident_id, ch["challenge_id"], "verify", length=24)}
        res = await self._exchange(inc, run_id, ch["target_agent_id"], req, set())
        rec = {"challenge_id": ch["challenge_id"], "target_agent_id": ch["target_agent_id"],
               "metric": check.metric, "claim": check.claim, "subject": check.subject, "decides": check.decides,
               "new_observation_ids": [], "outcome": None, "note": None}
        if res["outcome"] == "completed":
            result = res["result"]
            added = []
            for b in result["telemetry_batches"]:
                try:
                    rep = ingest_telemetry(self.store, inc.incident_id, b, now=self.clock(),
                                           batch_id=ch["challenge_id"])
                except EvidenceError as exc:
                    rec["note"] = f"returned batch refused by validator: {exc}"
                    continue
                added += [oid for r in rep.records for oid in r.observation_ids]
            rec["new_observation_ids"] = added
            rec["outcome"] = "obtained" if added else "no_new_evidence"
            rec["note"] = rec["note"] or "; ".join(result["notes"])
        else:
            rec["outcome"] = {"unavailable": "unavailable", "refused": "refused"}.get(res["outcome"], "failed")
            rec["note"] = res.get("error")
        self.store.put_challenge_outcome(ch["challenge_id"], rec["outcome"], rec, self.clock())
        return rec

    def _operational_report(self, inc, run_id: str, limits: list[str], coverage: dict) -> dict:
        from netcoop.engine.stear import Evaluation

        ev = Evaluation("operational_error", "not_applicable", [], [], [], [], [], 0.0,
                        ["Diagnosis was not executed reliably; this is a system failure, not a network finding."],
                        [], {})
        obs = self.store.list_observations(inc.incident_id, limit=100_000)
        snap = self.store.put_snapshot(inc.incident_id, {"observation_ids": sorted(o.observation_id for o in obs),
                                                         "finding_ids": [], "operational_error": True}, self.clock())
        rev = self.store.next_report_revision(inc.incident_id)
        report = build_report(incident=inc, revision=rev, run_id=run_id, ev=ev, findings=[], observations={},
                              snapshot_id=snap, topology_snapshot_id=inc.topology_snapshot_id,
                              generated_at=self.clock(), transport=self._report_transport(),
                              coverage=coverage, verification={"enabled": False, "challenges": []},
                              extra_limitations=limits)
        self.store.put_report(report, self.clock())
        self._event(inc.incident_id, run_id, "OPERATIONAL_ERROR", {"revision": rev, **coverage})
        return report
