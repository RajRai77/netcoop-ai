"""Source-profile/CSV adapters, persisted counter rates, topology impact scope."""

from __future__ import annotations

import copy

import pytest

from netcoop.evidence.adapters import adapt, builtin_profile, list_builtin_profiles
from netcoop.evidence.errors import EvidenceError, IssueCode
from netcoop.evidence.models import Subject, TopologySnapshot
from netcoop.ledger import ingest_telemetry
from netcoop.topology import Location, TopologyGraph
from tests.conftest import NOW, later

HEADER = "poll_id,poll_time,hostname,ifName,ifUtilPct,lossRatio,rttMs,outMbps,inErrors,poller_host,vendor_note"


def csv_rows(*rows: str) -> str:
    return "\n".join([HEADER, *rows]) + "\n"


def test_builtin_profile_is_listed_and_valid():
    assert "campus-snmp-csv" in list_builtin_profiles()
    assert builtin_profile("campus-snmp-csv")["format"] == "csv"
    for bad in ("../etc/passwd", "nope"):
        with pytest.raises(EvidenceError) as e:
            builtin_profile(bad)
        assert e.value.codes == [IssueCode.UNKNOWN_PROFILE]


def test_csv_maps_declared_columns_units_and_timezone(store):
    store.create_incident("INC-1", "synthetic", created_at=NOW)
    payload = csv_rows("p1,2026-10-31 15:29:00,SW-01,eth1,91.5,0.02,140,850,100,poller-a,x")
    rep = ingest_telemetry(store, "INC-1", payload, profile=builtin_profile("campus-snmp-csv"), now=later(0))
    assert rep.counts["accepted"] == 1
    obs = {o.measurement.metric: o for o in store.list_observations("INC-1")}
    assert obs["packet_loss"].measurement.value == 2.0  # declared 'ratio' -> percent
    assert obs["throughput"].measurement.value == 850_000_000
    assert obs["interface_errors"].measurement.value == 100
    assert obs["latency"].observed_at.isoformat() == "2026-10-31T09:59:00+00:00"  # +05:30 declared by profile
    codes = [i.code for i in rep.issues]
    assert IssueCode.UNMAPPED_FIELD in codes and IssueCode.TIMEZONE_FROM_PROFILE in codes
    raw = store.get_raw_record(obs["latency"].raw_record_ref)
    assert '"ifUtilPct":"91.5"' in raw.content  # raw record is the original vendor row
    assert raw.source_schema == "profile:campus-snmp-csv@1"


def test_csv_cells_are_not_coerced(store):
    store.create_incident("INC-1", "synthetic", created_at=NOW)
    payload = csv_rows("p1,2026-10-31 15:29:00,SW-01,eth1,high,,NaN,850,12.5,a,b")
    rep = ingest_telemetry(store, "INC-1", payload, profile=builtin_profile("campus-snmp-csv"), now=later(0))
    codes = {i.code for i in rep.issues if i.severity == "reject"}
    assert {IssueCode.TYPE_MISMATCH, IssueCode.MISSING_VALUE, IssueCode.NON_FINITE_VALUE} <= codes
    assert [o.measurement.metric for o in store.list_observations("INC-1")] == ["throughput"]
    assert rep.records[0].status == "partially_rejected"


def test_malformed_csv_is_refused():
    prof = builtin_profile("campus-snmp-csv")
    with pytest.raises(EvidenceError) as e:
        adapt(HEADER + "\np1,2026-10-31 15:29:00,SW-01,eth1,1,1,1,1,1,a,b,EXTRA\n", prof)
    assert e.value.codes == [IssueCode.CSV_MALFORMED]
    with pytest.raises(EvidenceError) as e:
        adapt("a,a\n1,2\n", prof)
    assert e.value.codes == [IssueCode.CSV_MALFORMED]


def test_invalid_profile_is_refused():
    prof = copy.deepcopy(builtin_profile("campus-snmp-csv"))
    prof["measurements"]["x"] = {"metric": "made_up_metric", "unit": "percent"}
    with pytest.raises(EvidenceError) as e:
        adapt(csv_rows(), prof)
    assert e.value.codes == [IssueCode.PROFILE_INVALID]
    prof = copy.deepcopy(builtin_profile("campus-snmp-csv"))
    del prof["timestamp"]
    with pytest.raises(EvidenceError) as e:
        adapt(csv_rows(), prof)
    assert e.value.codes == [IssueCode.PROFILE_INVALID]


def test_counter_rates_are_persisted_with_lineage(store):
    store.create_incident("INC-1", "synthetic", created_at=NOW)
    payload = csv_rows("p1,2026-10-31 15:28:00,SW-01,eth1,10,0,5,1,100,a,",
                       "p2,2026-10-31 15:29:00,SW-01,eth1,10,0,5,1,700,a,")
    ingest_telemetry(store, "INC-1", payload, profile=builtin_profile("campus-snmp-csv"), now=later(0))
    (rate,) = store.list_derived_rates("INC-1")
    assert rate["rate_metric"] == "interface_errors_rate" and rate["value"] == 10.0 and rate["unit"] == "count/s"
    assert len(rate["input_observation_ids"]) == 2
    # re-ingesting identical data adds nothing
    ingest_telemetry(store, "INC-1", payload, profile=builtin_profile("campus-snmp-csv"), now=later(1))
    assert len(store.list_derived_rates("INC-1")) == 1


# --- topology impact scope -------------------------------------------------------------

def topo(links, roles=None):
    nodes = sorted({x for lk in links for x in (lk[1], lk[2])})
    roles = roles or {"CORE": "core"}
    return TopologySnapshot.model_validate({
        "schema_version": "1.1.0", "topology_snapshot_id": "T", "kind": "synthetic",
        "observed_at": "2026-10-31T10:00:00Z", "limitations": [],
        "nodes": [{"id": n, "type": "service" if n.startswith("DNS") else "device",
                   **({"role": roles[n]} if n in roles else {})} for n in nodes],
        "links": [{"id": lid, "from": a, "to": b, "type": t, **extra} for lid, a, b, t, extra in links],
    })


TREE = [("L1", "CORE", "DIST", "physical", {"from_interface": "ge1"}),
        ("L2", "DIST", "ACC1", "physical", {"from_interface": "ge2"}),
        ("L3", "DIST", "ACC2", "physical", {"from_interface": "ge3"}),
        ("L4", "ACC1", "AP1", "physical", {}),
        ("D1", "ACC1", "DNS1", "dependency", {})]


def test_scope_of_upstream_device_contains_downstream():
    g = TopologyGraph(topo(TREE))
    assert g.scope(Location("node", node="DIST")) == {"DIST", "ACC1", "ACC2", "AP1"}
    assert g.scope(Location("node", node="ACC1")) == {"ACC1", "AP1"}
    assert g.scope(Location("interface", node="DIST", interface="ge2")) == {"DIST", "ACC1", "AP1"}


def test_redundant_path_limits_scope():
    redundant = TREE + [("L5", "CORE", "ACC1", "physical", {})]
    g = TopologyGraph(topo(redundant))
    assert g.scope(Location("node", node="DIST")) == {"DIST", "ACC2"}  # ACC1 still reaches CORE via L5


def test_parallel_links_are_redundant():
    par = TREE + [("L2b", "DIST", "ACC1", "physical", {})]
    g = TopologyGraph(topo(par))
    assert g.scope(Location("link", link="L2")) == {"DIST", "ACC1"}  # nothing disconnected


def test_service_scope_includes_dependents():
    g = TopologyGraph(topo(TREE))
    assert g.scope(Location("node", node="DNS1")) == {"DNS1", "ACC1"}


def test_without_roots_scope_is_component_only():
    g = TopologyGraph(topo(TREE, roles={"NONE": "core"}))
    assert not g.has_roots
    assert g.scope(Location("node", node="DIST")) == {"DIST"}
    assert TopologyGraph(None).scope(Location("node", node="X")) == {"X"}


def test_entities_and_upstream_candidates():
    g = TopologyGraph(topo(TREE))
    assert g.entities(Subject(device_id="AP1")) == {"AP1"}
    keys = {loc.key for loc in g.candidate_upstreams("AP1")}
    assert {"AP1", "ACC1", "DIST", "CORE", "link:L1", "link:L2", "link:L4"} <= keys
