"""Identifiability: observationally equivalent explanations must not be forced into one cause."""

from __future__ import annotations

from netcoop.evidence.models import TopologySnapshot
from tests.inference.test_engine import evaluate, finding, obs

# CORE -(g1)- SW -(p1)- AP ; plus a CPU-able switch for the distinguishability check
TOPO = TopologySnapshot.model_validate({
    "schema_version": "1.1.0", "topology_snapshot_id": "T-AP", "kind": "synthetic",
    "observed_at": "2026-10-31T10:00:00Z", "limitations": [],
    "nodes": [{"id": "CORE", "type": "device", "role": "core"}, {"id": "SW", "type": "device"},
              {"id": "AP", "type": "ap"}],
    "links": [{"id": "L1", "from": "CORE", "to": "SW", "type": "physical", "from_interface": "g1"},
              {"id": "L2", "from": "SW", "to": "AP", "type": "physical", "from_interface": "p1"}]})


def ap_outage_evidence():
    o = [obs("ifs1", "SW", "interface_status", "down", "state", iface="p1", lineage="LG-snmp1"),
         obs("ifs2", "SW", "interface_status", "down", "state", iface="p1", t="2026-10-31T10:01:00Z", lineage="LG-snmp2"),
         obs("r1", "AP", "reachability", False, "boolean", lineage="LG-probe1"),
         obs("r2", "AP", "reachability", False, "boolean", t="2026-10-31T10:01:00Z", lineage="LG-probe2"),
         obs("swr", "SW", "reachability", True, "boolean"), obs("swc", "SW", "cpu_utilization", 12, "percent"),
         obs("cr", "CORE", "reachability", True, "boolean")]
    f = [finding("F-if", "infrastructure-agent", "INTERFACE_DOWN", "present", "SW", ["ifs1", "ifs2"], iface="p1"),
         finding("F-ur", "connectivity-agent", "UNREACHABLE", "present", "AP", ["r1", "r2"]),
         finding("F-swr", "connectivity-agent", "UNREACHABLE", "absent", "SW", ["swr"]),
         finding("F-swc", "infrastructure-agent", "HIGH_CPU", "absent", "SW", ["swc"]),
         finding("F-cr", "connectivity-agent", "UNREACHABLE", "absent", "CORE", ["cr"])]
    return o, f


def test_ap_down_vs_port_down_without_ap_status_is_ambiguous():
    o, f = ap_outage_evidence()
    ev = evaluate(f, o, topo=TOPO)
    assert ev.status == "ambiguous" and ev.causes == []
    ids = {h.hid for h in ev.competitors}
    assert {"H-DEVICE_DOWN-AP", "H-LINK_OR_PATH_FAILURE-SW:p1"} <= ids
    assert any("observationally equivalent" in b for b in ev.decision_basis)
    # the missing discriminator is the AP status - exactly what the planner should request
    ap = next(h for h in ev.competitors if h.hid == "H-DEVICE_DOWN-AP")
    assert ("DEVICE_DOWN_STATE", {"device_id": "AP"}) in ap.missing


def test_ap_status_down_identifies_the_ap():
    o, f = ap_outage_evidence()
    o.append(obs("aps", "AP", "device_status", "down", "state", lineage="LG-wlc"))
    f.append(finding("F-aps", "infrastructure-agent", "DEVICE_DOWN_STATE", "present", "AP", ["aps"]))
    ev = evaluate(f, o, topo=TOPO)
    assert ev.status == "diagnosed" and ev.causes[0].hid == "H-DEVICE_DOWN-AP"


def test_ap_status_up_identifies_the_link():
    o, f = ap_outage_evidence()
    o.append(obs("aps", "AP", "device_status", "up", "state", lineage="LG-wlc"))
    f.append(finding("F-aps", "infrastructure-agent", "DEVICE_DOWN_STATE", "absent", "AP", ["aps"]))
    ev = evaluate(f, o, topo=TOPO)
    assert ev.status == "diagnosed" and ev.causes[0].hid == "H-LINK_OR_PATH_FAILURE-SW:p1"


def test_reachable_device_is_not_down():
    o, f = ap_outage_evidence()
    h = {x.hid: x for x in evaluate(f, o, topo=TOPO).hypotheses}
    assert h["H-DEVICE_DOWN-SW"].status == "contradicted"  # SW answers probes


def test_distinguishable_diagnosis_is_not_downgraded_to_ambiguous():
    # congestion is confirmed by utilization, which CPU overload does not predict -> still diagnosed
    o = [obs("u1", "SW", "link_utilization", 95, "percent", iface="p1", lineage="LG-a"),
         obs("u2", "SW", "link_utilization", 96, "percent", iface="p1", t="2026-10-31T10:01:00Z", lineage="LG-b"),
         obs("l1", "AP", "latency", 300, "ms", lineage="LG-c"),
         obs("l2", "AP", "latency", 320, "ms", t="2026-10-31T10:01:00Z", lineage="LG-d")]
    o[2] = o[2].model_copy(update={"source": o[2].source.model_copy(update={"source_id": "probe"})})
    o[3] = o[3].model_copy(update={"source": o[3].source.model_copy(update={"source_id": "probe"})})
    f = [finding("F-u", "performance-agent", "HIGH_LINK_UTILIZATION", "present", "SW", ["u1", "u2"], iface="p1"),
         finding("F-l", "performance-agent", "HIGH_LATENCY", "present", "AP", ["l1", "l2"])]
    ev = evaluate(f, o, topo=TOPO)
    assert ev.status == "diagnosed" and ev.causes[0].hid == "H-LINK_CONGESTION-SW:p1"
    assert not any("observationally equivalent" in b for b in ev.decision_basis)
