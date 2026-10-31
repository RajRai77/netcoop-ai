"""Specialist agent logic: request text in -> result text out.

Used unchanged by the A2A server (netcoop.agents.server) and by the in-process
AgentPort (unit tests and evaluation baselines only). Each specialist only looks
at its own metric domain; the connectivity agent additionally analyses topology.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from netcoop.agents.archive import ArchiveError, RecordedArchive
from netcoop.agents.detectors import Evaluation, evaluate, usable
from netcoop.agents.protocol import AGENT_VERSION, SPECIALISTS, ProtocolError, dumps, loads
from netcoop.evidence.ids import derive_id
from netcoop.evidence.models import Finding, NormalizedObservation, TopologySnapshot
from netcoop.knowledge import detector_rules
from netcoop.spec import validator
from netcoop.topology import Location, TopologyGraph


@dataclass
class AgentConfig:
    agent_id: str
    archive: RecordedArchive


def _result(task_id: str, agent_id: str, status: str, *, findings=None, batches=None, coverage=None, notes=None,
            error=None) -> str:
    doc = {"schema_version": "1.0.0", "task_id": task_id, "agent_id": agent_id, "agent_version": AGENT_VERSION,
           "rule_version": detector_rules()["version"], "status": status, "findings": findings or [],
           "telemetry_batches": batches or [], "coverage": coverage or {}, "notes": notes or []}
    if error:
        doc["error"] = {"code": error[0], "message": error[1]}
    return dumps(doc)


def handle(cfg: AgentConfig, request_text: str) -> str:
    try:
        req = loads(request_text, "agent-task")
    except ProtocolError as exc:
        return _result("unknown", cfg.agent_id, "refused", error=(exc.code, str(exc)))
    tid = req["task_id"]
    if req["agent_id"] != cfg.agent_id:
        return _result(tid, cfg.agent_id, "refused",
                       error=("WRONG_AGENT", f"task addressed to {req['agent_id']!r}, this is {cfg.agent_id!r}"))
    try:
        if req["task_type"] == "investigate":
            return investigate(cfg, req)
        return verify(cfg, req)
    except ProtocolError as exc:
        return _result(tid, cfg.agent_id, "refused", error=(exc.code, str(exc)))
    except Exception as exc:  # agent bug: report honestly, never fabricate a result
        return _result(tid, cfg.agent_id, "failed", error=("AGENT_ERROR", f"{type(exc).__name__}: {exc}"))


def _parse_case(req: dict) -> tuple[list[NormalizedObservation], TopologySnapshot | None, list[Finding]]:
    case = req["case"]
    try:
        obs = [NormalizedObservation.model_validate(o) for o in case["observations"]]
        topo = TopologySnapshot.model_validate(case["topology"]) if case.get("topology") else None
        prior = [Finding.model_validate(f) for f in case["prior_findings"]]
    except ValidationError as exc:
        raise ProtocolError("SCHEMA_INVALID", f"case payload invalid: {exc.errors()[0]['msg']}") from None
    for o in obs:
        if o.incident_id != req["incident_id"]:
            raise ProtocolError("SCHEMA_INVALID", f"observation {o.observation_id} belongs to another incident")
    return obs, topo, prior


def investigate(cfg: AgentConfig, req: dict) -> str:
    spec = SPECIALISTS[cfg.agent_id]
    obs, topo, prior = _parse_case(req)
    domain = [o for o in obs if o.measurement.metric in spec["metrics"]]
    rules_doc = detector_rules()
    rules = [r for r in rules_doc["rules"] if r["agent"] == cfg.agent_id]
    evals = evaluate(domain, rules, rules_doc["persistence"])
    notes: list[str] = []
    if cfg.agent_id == "connectivity-agent":
        evals += _scope_analysis(evals, topo, notes)

    analysis_time = req["case"]["analysis_time"]
    prior_by_key = {(f.claim, f.subject.key()): f for f in prior if f.agent_id == cfg.agent_id}
    findings = []
    for ev in evals:
        f = _finding(cfg.agent_id, req["incident_id"], ev, analysis_time, rules_doc["version"])
        old = prior_by_key.get((ev.claim, ev.subject.key()))
        if old is not None:
            if old.finding_id == f.finding_id:
                findings.append(old.to_json_dict())  # unchanged; re-delivery is idempotent
                continue
            f = f.model_copy(update={"supersedes_finding_id": old.finding_id,
                                     "created_at": max(f.created_at, old.created_at)})
        findings.append(f.to_json_dict())

    fresh, dropped = usable(domain)
    counts: dict[str, int] = {}
    for o in domain:
        counts[o.measurement.metric] = counts.get(o.measurement.metric, 0) + 1
    coverage = {
        "metrics_received": counts, "fresh_observations": len(fresh), **dropped,
        "no_data_for_metrics": sorted(m for m in spec["metrics"] if m not in counts),
        "subjects": len({o.subject.key() for o in domain}),
        "claims": {p: sum(1 for e in evals if e.polarity == p) for p in ("present", "absent", "unknown")},
    }
    return _result(req["task_id"], cfg.agent_id, "completed", findings=findings, coverage=coverage, notes=notes)


def _finding(agent_id: str, incident_id: str, ev: Evaluation, analysis_time: str, rules_version: str) -> Finding:
    fid = derive_id("F", agent_id, incident_id, ev.claim, ev.subject.key(), ev.polarity, *ev.refs, rules_version,
                    length=24)
    caveats = list(ev.caveats)
    if ev.metrics:
        caveats.append(f"basis: {', '.join(ev.metrics)}")
    return Finding.model_validate({
        "finding_id": fid, "incident_id": incident_id, "agent_id": agent_id, "claim": ev.claim,
        "polarity": ev.polarity, "subject": ev.subject.to_json_dict(), "observation_refs": ev.refs,
        "rule_or_model_version": f"{rules_version}:{ev.claim}", "created_at": analysis_time, "caveats": caveats,
    })


def _scope_analysis(evals: list[Evaluation], topo: TopologySnapshot | None, notes: list[str]) -> list[Evaluation]:
    """Topology analysis: lowest common upstream of unreachable nodes / common service of
    DNS-DHCP failures. Emits hint findings (not measurements of the upstream)."""
    if topo is None:
        notes.append("No topology supplied: affected-scope analysis skipped.")
        return []
    g = TopologyGraph(topo)
    out: list[Evaluation] = []
    for claim, hint, kind in (("UNREACHABLE", "COMMON_UPSTREAM_DEPENDENCY", "device_id"),
                              ("DNS_FAILURES", "COMMON_SERVICE_DEPENDENCY", "service_id"),
                              ("DHCP_FAILURES", "COMMON_SERVICE_DEPENDENCY", "service_id")):
        hits = [e for e in evals if e.claim == claim and e.polarity == "present"]
        ents = {n for e in hits for n in g.entities(e.subject)}
        if len(ents) < 2:
            continue
        nodes = [n for n, t in g.node_types.items() if (t == "service") == (kind == "service_id")]
        covering = [n for n in nodes if ents <= g.scope(Location("node", node=n)) and n not in ents]
        if not covering:
            notes.append(f"{claim} on {sorted(ents)}: no single common {'service' if kind == 'service_id' else 'upstream'} in topology.")
            continue
        best = min(len(g.scope(Location("node", node=n))) for n in covering)
        refs = sorted({r for e in hits for r in e.refs})
        onset = min((e.onset for e in hits if e.onset), default=None)
        from netcoop.evidence.models import Subject
        for n in sorted(covering):
            if len(g.scope(Location("node", node=n))) == best:
                out.append(Evaluation(claim=hint, subject=Subject(**{kind: n}), polarity="present", refs=refs,
                                      onset=onset, caveats=[f"topology-derived from {claim} on {sorted(ents)} "
                                                            f"(snapshot {topo.topology_snapshot_id}); not a measurement of {n}"],
                                      metrics=["topology"]))
    return out


def verify(cfg: AgentConfig, req: dict) -> str:
    ch = req["challenge"]
    errs = [e.message for e in validator("challenge").iter_errors(ch)]
    if errs:
        raise ProtocolError("SCHEMA_INVALID", f"challenge invalid: {errs[0]}")
    tid = req["task_id"]
    if ch["target_agent_id"] != cfg.agent_id or ch["incident_id"] != req["incident_id"]:
        raise ProtocolError("WRONG_AGENT", "challenge not addressed to this agent/incident")
    metric = ch["requested_observation"]["metric"]
    if metric not in SPECIALISTS[cfg.agent_id]["metrics"]:
        return _result(tid, cfg.agent_id, "refused", notes=[f"{metric} is outside this agent's domain"])
    if ch["authorization_scope"] != "recorded_replay":
        return _result(tid, cfg.agent_id, "unavailable",
                       notes=["No live read-only collector is configured for this agent; nothing was measured."])
    ref = req.get("archive_ref")
    if not ref:
        return _result(tid, cfg.agent_id, "unavailable", notes=["Incident has no recorded archive to query."])
    w = ch["requested_observation"]["window"]
    try:
        batches = cfg.archive.query(ref, metric, ch["requested_observation"]["subject"], w["start"], w["end"])
    except ArchiveError as exc:
        return _result(tid, cfg.agent_id, "refused", error=("ARCHIVE_REF", str(exc)))
    if not batches:
        return _result(tid, cfg.agent_id, "unavailable",
                       notes=[f"No recorded {metric} for {ch['requested_observation']['subject']} in the window."])
    n = sum(len(b["records"]) for b in batches)
    return _result(tid, cfg.agent_id, "completed", batches=batches,
                   notes=[f"Returned {n} recorded record(s) from archive {ref}; values are unmodified source records."])


def make_config(agent_id: str, scenarios_dir: str | Path | None, uploads_dir: str | Path | None) -> AgentConfig:
    if agent_id not in SPECIALISTS:
        raise ValueError(f"unknown specialist {agent_id!r}; choose from {sorted(SPECIALISTS)}")
    return AgentConfig(agent_id, RecordedArchive(Path(scenarios_dir) if scenarios_dir else None,
                                                 Path(uploads_dir) if uploads_dir else None))
