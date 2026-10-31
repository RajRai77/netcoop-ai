"""STEaR unit behaviour on hand-built findings (no agents)."""

from __future__ import annotations

from netcoop.engine.stear import Stear
from netcoop.evidence.models import Finding, NormalizedObservation, TopologySnapshot
from netcoop.topology import TopologyGraph


def obs(oid, device, metric, value, unit, t="2026-10-31T10:00:00Z", lineage=None, iface=None):
    subj = {"device_id": device} | ({"interface_id": iface} if iface else {})
    return NormalizedObservation.model_validate({
        "observation_id": oid, "incident_id": "I", "raw_record_ref": "R-" + oid,
        "source": {"source_id": "s", "data_mode": "synthetic", "source_type": "t"}, "subject": subj,
        "measurement": {"metric": metric, "value": value, "unit": unit, "kind": "gauge"}, "observed_at": t,
        "ingested_at": "2026-10-31T10:05:00Z", "quality": {"validation": "passed", "freshness": "current", "flags": []},
        "lineage_group": lineage or "LG-" + oid, "metric_registry_version": "1.2.0"})


def finding(fid, agent, claim, polarity, device, refs, iface=None):
    subj = {"device_id": device} | ({"interface_id": iface} if iface else {})
    return Finding.model_validate({"finding_id": fid, "incident_id": "I", "agent_id": agent, "claim": claim,
                                   "polarity": polarity, "subject": subj, "observation_refs": refs,
                                   "rule_or_model_version": "t", "created_at": "2026-10-31T10:05:00Z", "caveats": []})


TOPO = TopologySnapshot.model_validate({
    "schema_version": "1.1.0", "topology_snapshot_id": "T", "kind": "synthetic", "observed_at": "2026-10-31T10:00:00Z",
    "limitations": [], "nodes": [{"id": "C", "type": "device", "role": "core"}, {"id": "A", "type": "device"},
                                 {"id": "B", "type": "device"}],
    "links": [{"id": "L1", "from": "C", "to": "A", "type": "physical", "from_interface": "g1"},
              {"id": "L2", "from": "A", "to": "B", "type": "physical", "from_interface": "g2"}]})


def evaluate(findings, observations, topo=TOPO, **kw):
    return Stear(TopologyGraph(topo), **kw).evaluate(findings, {o.observation_id: o for o in observations})


def test_shared_lineage_prevents_high_support():
    # utilization and latency come from the same source record -> one lineage group
    o = [obs("u", "A", "link_utilization", 95, "percent", lineage="LG1", iface="g2"),
         obs("u2", "A", "link_utilization", 96, "percent", lineage="LG1", iface="g2"),
         obs("l", "B", "latency", 300, "ms", lineage="LG1"), obs("c", "A", "cpu_utilization", 10, "percent")]
    f = [finding("F1", "performance-agent", "HIGH_LINK_UTILIZATION", "present", "A", ["u", "u2"], iface="g2"),
         finding("F2", "performance-agent", "HIGH_LATENCY", "present", "B", ["l"]),
         finding("F3", "infrastructure-agent", "HIGH_CPU", "absent", "A", ["c"])]
    ev = evaluate(f, o)
    assert ev.status == "diagnosed" and ev.causes[0].hid == "H-LINK_CONGESTION-A:g2"
    assert ev.confidence_category == "moderate_support"
    assert any("single independent source" in b for b in ev.decision_basis)


def test_effect_before_cause_is_temporal_issue():
    o = [obs("u", "A", "link_utilization", 95, "percent", t="2026-10-31T10:08:00Z", iface="g2"),
         obs("l", "B", "latency", 300, "ms", t="2026-10-31T10:00:00Z")]
    f = [finding("F1", "performance-agent", "HIGH_LINK_UTILIZATION", "present", "A", ["u"], iface="g2"),
         finding("F2", "performance-agent", "HIGH_LATENCY", "present", "B", ["l"])]
    h = {x.hid: x for x in evaluate(f, o).hypotheses}["H-LINK_CONGESTION-A:g2"]
    assert h.temporal_issues and "F2" not in h.explained
    h2 = {x.hid: x for x in evaluate(f, o, use_temporal=False).hypotheses}["H-LINK_CONGESTION-A:g2"]
    assert "F2" in h2.explained  # the ablation switch really disables the check


def test_symptom_outside_scope_is_not_explained():
    o = [obs("u", "A", "link_utilization", 95, "percent", iface="g2"), obs("l", "C", "latency", 300, "ms")]
    f = [finding("F1", "performance-agent", "HIGH_LINK_UTILIZATION", "present", "A", ["u"], iface="g2"),
         finding("F2", "performance-agent", "HIGH_LATENCY", "present", "C", ["l"])]  # C is upstream of A:g2
    h = {x.hid: x for x in evaluate(f, o).hypotheses}["H-LINK_CONGESTION-A:g2"]
    assert "F2" not in h.explained


def test_one_specialist_reporting_normal_is_not_healthy():
    o = [obs("l", "A", "latency", 5, "ms")]
    f = [finding("F1", "performance-agent", "HIGH_LATENCY", "absent", "A", ["l"])]
    assert evaluate(f, o).status == "insufficient_evidence"


def test_no_usable_observations():
    assert evaluate([], []).status == "insufficient_evidence"


def test_without_topology_reports_limitation():
    o = [obs("u", "A", "link_utilization", 95, "percent", iface="g2")]
    ev = evaluate([finding("F1", "performance-agent", "HIGH_LINK_UTILIZATION", "present", "A", ["u"], iface="g2")],
                  o, topo=None)
    assert any("No topology" in x for x in ev.limitations)


def test_all_explanations_contradicted_is_unknown_fault():
    o = [obs("l", "B", "latency", 300, "ms"), obs("l2", "B", "latency", 310, "ms"),
         obs("u", "A", "link_utilization", 20, "percent", iface="g2"), obs("c", "B", "cpu_utilization", 10, "percent"),
         obs("c2", "A", "cpu_utilization", 10, "percent"), obs("e", "A", "crc_errors", 1, "count", iface="g2")]
    f = [finding("F1", "performance-agent", "HIGH_LATENCY", "present", "B", ["l", "l2"]),
         finding("F2", "performance-agent", "HIGH_LINK_UTILIZATION", "absent", "A", ["u"], iface="g2"),
         finding("F3", "infrastructure-agent", "HIGH_CPU", "absent", "B", ["c"]),
         finding("F4", "infrastructure-agent", "HIGH_CPU", "absent", "A", ["c2"]),
         finding("F5", "infrastructure-agent", "CRC_ERRORS", "absent", "A", ["e"], iface="g2")]
    # with the interface state unobserved, a link/path failure is still possible -> not 'unknown'
    assert evaluate(f, o).status == "insufficient_evidence"
    o.append(obs("s", "A", "interface_status", "up", "state", iface="g2"))
    f.append(finding("F6", "infrastructure-agent", "INTERFACE_DOWN", "absent", "A", ["s"], iface="g2"))
    ev = evaluate(f, o)
    assert ev.status == "unknown_fault" and ev.causes == []


def test_relayed_copies_count_as_one_source():
    from netcoop.engine.stear import independent_sources
    assert independent_sources({("LG1", "collector-a"), ("LG1", "collector-b")}) == 1
    assert independent_sources({("LG1", "snmp"), ("LG2", "snmp")}) == 1  # repeated polls of one source
    assert independent_sources({("LG1", "snmp"), ("LG2", "probe")}) == 2
    assert independent_sources({("LG1", "a"), ("LG1", "b"), ("LG2", "b"), ("LG3", "c")}) == 2
