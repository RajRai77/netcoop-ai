"""Build the structured JSON diagnosis (spec/report.schema.json 1.1.0) from an evaluation.

Every number in supporting_evidence is copied from a stored observation (value + unit);
the text explanation is generated from the structured fields and adds no facts.
"""

from __future__ import annotations

from netcoop.engine.stear import ENGINE_VERSION, Evaluation
from netcoop.evidence.models import Finding, NormalizedObservation
from netcoop.evidence.timeutil import to_canonical
from netcoop.knowledge import detector_rules, fault_library
from netcoop.spec import validator

MAX_EVIDENCE = 60
CLAIM_TEXT = {
    "present": "{claim} observed by {agent}",
    "absent": "{claim} checked and NOT observed by {agent}",
    "unknown": "{claim} inconclusive per {agent}",
}


class ReportInvalid(ValueError):
    pass


def build_report(*, incident, revision: int, run_id: str, ev: Evaluation, findings: list[Finding],
                 observations: dict[str, NormalizedObservation], snapshot_id: str, topology_snapshot_id: str | None,
                 generated_at, transport: str, coverage: dict, verification: dict, extra_limitations: list[str]) -> dict:
    lib = fault_library()
    fmap = {f.finding_id: f for f in findings}
    causes = ev.causes
    if causes:
        suspected = " + ".join(f"{h.fault} at {h.loc.key}" for h in causes)
    else:
        suspected = None

    # supporting evidence: findings that explain the selected cause(s), else the present symptoms
    support_fids: list[str] = []
    for h in causes:
        support_fids += [fid for fid in h.signature + h.explained if fid not in support_fids]
    if not causes:
        support_fids = list(ev.present_symptoms)
    # discriminating negative evidence that eliminated competitors is also evidence
    eliminated = [h for h in ev.hypotheses if h.status == "contradicted" and h.explained]
    neg_fids = []
    for h in eliminated[:10]:
        for fid, f in fmap.items():
            if f.polarity == "absent" and fid not in neg_fids and fid not in support_fids and any(
                    f.claim in c for c in h.contradictions):
                neg_fids.append(fid)
    evidence = []
    for fid in support_fids + neg_fids:
        f = fmap.get(fid)
        if f is None:
            continue
        for ref in f.observation_refs[:4]:
            o = observations.get(ref)
            if o is None:
                continue
            evidence.append({
                "observation_id": o.observation_id, "finding_id": f.finding_id, "metric": o.measurement.metric,
                "value": o.measurement.value, "unit": o.measurement.unit,
                "interpretation": CLAIM_TEXT[f.polarity].format(claim=f.claim, agent=f.agent_id)
                + f" at {f.subject.key()}",
            })
            if len(evidence) >= MAX_EVIDENCE:
                break
        if len(evidence) >= MAX_EVIDENCE:
            break

    affected: list[str] = []
    for h in causes:
        nodes = {n for fid in h.explained for n in ev.symptoms[fid].entities} & set(h.scope)
        affected += [n for n in sorted(nodes | ({h.loc.node} if h.loc.node else set())) if n not in affected]
    if not causes:
        affected = sorted({n for fid in ev.present_symptoms for n in ev.symptoms[fid].entities})

    alternatives = []
    for h in ev.competitors:
        miss = ", ".join(sorted({c for c, _ in h.missing})) or "signature"
        alternatives.append(f"{h.fault} at {h.loc.key} (plausible; not verified: {miss} missing)")
    for h in eliminated[:8]:
        alternatives.append(f"{h.fault} at {h.loc.key} (ruled out: {h.contradictions[0]})")

    actions: list[str] = []
    for h in causes:
        actions += [r.format(location=h.loc.key) for r in lib["faults"][h.fault]["recommendations"]]
    if ev.status == "ambiguous":
        for h in ev.competitors[:4]:
            for c, subj in h.missing[:2]:
                actions.append(f"Obtain {c} evidence for {subj} to test {h.fault} (read-only)")
    if ev.status == "unknown_fault":
        actions.append("Escalate to an engineer: symptoms persist but every modeled cause was ruled out; collect "
                       "packet captures/logs on the affected path (read-only)")
    if ev.status == "insufficient_evidence":
        actions.append("Provide more telemetry (performance and infrastructure metrics with explicit units) "
                       "for the affected components")
    if ev.status == "healthy":
        actions.append("No action needed; keep monitoring")
    actions = list(dict.fromkeys(actions)) or ["No action recommended"]

    limitations = list(dict.fromkeys(
        ["confidence_category is a documented support category, not a probability"]
        + [c for h in causes for c in lib["faults"][h.fault].get("caveats", [])]
        + ev.limitations + extra_limitations
        + ([f"Data mode: {incident.data_mode}; no live network was accessed"] if incident.data_mode != "live" else [])))

    contributions: dict[str, list[str]] = {}
    for f in findings:
        contributions.setdefault(f.agent_id, []).append(f.finding_id)
    used_agents = sorted({fmap[fid].agent_id for fid in support_fids + neg_fids if fid in fmap})

    rank = {h.hid: i + 1 for i, h in enumerate(ev.hypotheses)}
    report = {
        "schema_version": "1.1.0", "incident_id": incident.incident_id, "revision": revision, "status": ev.status,
        "suspected_root_cause": suspected, "confidence_category": ev.confidence_category,
        "affected_devices": affected, "supporting_evidence": evidence, "alternative_causes": alternatives,
        "recommended_actions": actions, "evidence_sources": used_agents, "limitations": limitations,
        "evidence_snapshot_id": snapshot_id, "topology_snapshot_id": topology_snapshot_id,
        "engine_version": ENGINE_VERSION, "data_mode": incident.data_mode, "generated_at": to_canonical(generated_at),
        "run_id": run_id, "transport": transport,
        "root_causes": [{"hypothesis_id": h.hid, "fault_type": h.fault, "location": h.loc.key,
                         "support": ev.confidence_category, "affected_scope": sorted(h.scope)} for h in causes],
        "hypotheses": [h.to_dict(rank.get(h.hid)) for h in ev.hypotheses[:40]],
        "verification": verification, "coverage": coverage,
        "agent_contributions": contributions, "unexplained_symptoms": ev.unexplained,
        "decision_basis": ev.decision_basis,
        "knowledge_versions": {"detector_rules": detector_rules()["version"], "fault_library": lib["version"]},
    }
    report["explanation"] = explain(report)
    errors = [f"{'/'.join(map(str, e.absolute_path))}: {e.message}" for e in validator("report").iter_errors(report)]
    if errors:
        raise ReportInvalid("; ".join(errors[:5]))
    return report


def explain(r: dict) -> str:
    head = {
        "diagnosed": f"Probable root cause: {r['suspected_root_cause']} ({r['confidence_category'].replace('_', ' ')}).",
        "ambiguous": "Ambiguous: several explanations fit the evidence and could not be separated.",
        "insufficient_evidence": "Insufficient evidence to determine a root cause.",
        "unknown_fault": "Unknown fault: symptoms persist but no modeled cause fits the evidence.",
        "healthy": "No fault detected in the monitored scope.",
        "operational_error": "The diagnosis could not be completed because of a system failure.",
    }[r["status"]]
    parts = [head]
    if r["affected_devices"]:
        parts.append(f"Affected: {', '.join(r['affected_devices'][:12])}.")
    parts.append(f"Based on {len(r['supporting_evidence'])} evidence item(s) from {', '.join(r['evidence_sources']) or 'no agent'}.")
    v = r.get("verification") or {}
    if v.get("challenges"):
        got = sum(1 for c in v["challenges"] if c.get("outcome") == "obtained")
        parts.append(f"Verification: {len(v['challenges'])} targeted check(s) requested, {got} returned new evidence.")
    if r["alternative_causes"]:
        parts.append(f"Alternatives considered: {len(r['alternative_causes'])}.")
    return " ".join(parts)
