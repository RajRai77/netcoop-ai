"""Detector semantics: persistence, transients, source conflicts, staleness."""

from __future__ import annotations

from netcoop.agents.detectors import evaluate
from netcoop.knowledge import detector_rules
from tests.inference.test_engine import obs

RULES = [r for r in detector_rules()["rules"] if r["metric"] == "link_utilization"]
PERSIST = detector_rules()["persistence"]


def util(oid, value, source, t):
    o = obs(oid, "SW", "link_utilization", value, "percent", t=t, iface="p1")
    return o.model_copy(update={"source": o.source.model_copy(update={"source_id": source})})


def test_contradictory_sources_give_unknown_with_conflict_caveat():
    o = [util("a1", 95, "snmp-a", "2026-10-31T10:00:00Z"), util("a2", 96, "snmp-a", "2026-10-31T10:01:00Z"),
         util("b1", 20, "snmp-b", "2026-10-31T10:00:00Z"), util("b2", 22, "snmp-b", "2026-10-31T10:01:00Z")]
    (ev,) = evaluate(o, RULES, PERSIST)
    assert ev.polarity == "unknown"
    assert any("SOURCE_CONFLICT" in c for c in ev.caveats)
    assert set(ev.refs) == {"a1", "a2", "b1", "b2"}  # both sides stay traceable


def test_single_spike_is_transient_not_present():
    o = [util("a1", 95, "snmp", "2026-10-31T10:00:00Z"), util("a2", 30, "snmp", "2026-10-31T10:01:00Z")]
    (ev,) = evaluate(o, RULES, PERSIST)
    assert ev.polarity == "unknown" and any("TRANSIENT" in c for c in ev.caveats)


def test_stale_data_never_yields_absent():
    o = util("a1", 20, "snmp", "2026-10-31T10:00:00Z")
    o = o.model_copy(update={"quality": o.quality.model_copy(update={"freshness": "stale"})})
    assert evaluate([o], RULES, PERSIST) == []  # a coverage gap, not evidence of normality


def test_coverage_gap_blocks_healthy():
    from netcoop.engine.stear import Stear
    from netcoop.evidence.models import TopologySnapshot
    from netcoop.topology import TopologyGraph
    from tests.inference.test_engine import finding

    topo = TopologySnapshot.model_validate({
        "schema_version": "1.1.0", "topology_snapshot_id": "T", "kind": "synthetic", "observed_at": "2026-10-31T10:00:00Z",
        "limitations": [], "nodes": [{"id": "C", "type": "device", "role": "core"},
                                     {"id": "DNS", "type": "service", "service_kind": "dns"},
                                     {"id": "SEG", "type": "segment"}],
        "links": [{"id": "L", "from": "C", "to": "DNS", "type": "physical"},
                  {"id": "D", "from": "SEG", "to": "DNS", "type": "dependency"}]})
    o = [obs("l", "C", "latency", 5, "ms"), obs("c", "C", "cpu_utilization", 10, "percent")]
    f = [finding("F1", "performance-agent", "HIGH_LATENCY", "absent", "C", ["l"]),
         finding("F2", "infrastructure-agent", "HIGH_CPU", "absent", "C", ["c"])]
    ev = Stear(TopologyGraph(topo)).evaluate(f, {x.observation_id: x for x in o})
    assert ev.status == "insufficient_evidence"
    assert [g[0] for g in ev.coverage_gaps] == ["dns"]
    assert ev.coverage_gaps[0][2] == [{"segment_id": "SEG"}]  # planner can request DNS data per segment
