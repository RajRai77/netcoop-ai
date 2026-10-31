"""Plain-text rendering of a report (for CLI and download). Adds no facts beyond the JSON."""

from __future__ import annotations


def report_to_text(r: dict) -> str:
    L = []
    L.append(f"NetCoop AI diagnosis - incident {r['incident_id']} (revision {r['revision']})")
    L.append(f"Generated {r['generated_at']} | engine {r['engine_version']} | data mode {r['data_mode']} | "
             f"transport {r.get('transport', '?')}")
    L.append("")
    L.append(f"STATUS: {r['status']}    SUPPORT: {r['confidence_category']} (a support category, not a probability)")
    L.append(f"Probable root cause: {r['suspected_root_cause'] or 'not determined'}")
    if r["affected_devices"]:
        L.append(f"Affected: {', '.join(r['affected_devices'])}")
    L.append("")
    L.append(r.get("explanation", ""))
    if r.get("decision_basis"):
        L.append("")
        L.append("Why:")
        L += [f"  - {b}" for b in r["decision_basis"]]
    L.append("")
    L.append("Supporting evidence (stored observations):")
    for e in r["supporting_evidence"][:30]:
        L.append(f"  - {e['metric']} = {e['value']} {e['unit']}  [{e['observation_id']} via {e['finding_id']}] "
                 f"{e['interpretation']}")
    if r["alternative_causes"]:
        L.append("")
        L.append("Alternatives considered:")
        L += [f"  - {a}" for a in r["alternative_causes"]]
    v = r.get("verification") or {}
    if v.get("challenges"):
        L.append("")
        L.append(f"Targeted verification ({v.get('rounds', 0)} round(s); stopped: {v.get('stopped_because')}):")
        for c in v["challenges"]:
            L.append(f"  - ask {c['target_agent_id']} for {c['metric']} at {c['subject']} -> {c['outcome']}"
                     f" ({len(c['new_observation_ids'])} new observation(s))")
    L.append("")
    L.append("Recommended actions (for a human operator; nothing is executed automatically):")
    L += [f"  - {a}" for a in r["recommended_actions"]]
    L.append("")
    L.append("Limitations:")
    L += [f"  - {x}" for x in r["limitations"]]
    L.append("")
    L.append(f"Evidence snapshot {r['evidence_snapshot_id']} | topology {r['topology_snapshot_id']} | "
             f"specialists: {', '.join(r['evidence_sources']) or 'none'}")
    return "\n".join(L) + "\n"
