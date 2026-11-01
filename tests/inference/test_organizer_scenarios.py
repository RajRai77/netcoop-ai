"""Diagnosis of the scenarios built from the organizer's sample generator (PS section 5).

The generator labels faults with symptom classes ("latency_spike", "hardware_failure") that are not root causes in
the NetCoop fault library, so the ground truth (written by scripts/build_organizer_scenarios.py before any run)
only states what the data can establish: whether a fault exists and on which device. Never edit ground_truth.json
to make a run pass.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from netcoop.agents.protocol import SPECIALISTS
from netcoop.engine.planner import VerificationPolicy
from netcoop.evidence.adapters import adapt, builtin_profile
from netcoop.orchestration.coordinator import Coordinator, CoordinatorOptions
from netcoop.orchestration.ports import InProcessAgentPort
from netcoop.scenarios.loader import list_scenarios, load_into
from netcoop.spec import validator

BASE = Path(__file__).resolve().parents[2] / "data" / "scenarios"
IDS = [s["scenario_id"] for s in list_scenarios(BASE) if s.get("split") == "organizer"]
SYMPTOM_FREE = {"COMMON_UPSTREAM_DEPENDENCY", "COMMON_SERVICE_DEPENDENCY"}


def test_organizer_scenarios_exist():
    assert {"ORG-01-normal", "ORG-02-latency-spike", "ORG-03-hardware-failure", "ORG-04-schema-drift"} <= set(IDS)


def run(store, sid):
    loaded = load_into(store, BASE, sid)
    inc = loaded["incident"]
    ports = [InProcessAgentPort(a, BASE, None) for a in SPECIALISTS]
    r = Coordinator(store, ports, CoordinatorOptions(verification=VerificationPolicy(enabled=True))).run(inc.incident_id)
    return loaded, r


@pytest.mark.parametrize("sid", IDS)
def test_organizer_scenario(store, sid):
    gt = json.loads((BASE / sid / "ground_truth.json").read_text(encoding="utf-8"))
    loaded, r = run(store, sid)
    assert list(validator("report").iter_errors(r)) == []
    exp = gt["expected"]
    if "status" in exp:
        assert r["status"] == exp["status"], r["decision_basis"]
    if "status_not" in exp:
        assert r["status"] != exp["status_not"], r["decision_basis"]
    findings = store.list_findings(loaded["incident"].incident_id)
    anomalous = {f.subject.device_id for f in findings if f.polarity == "present" and f.claim not in SYMPTOM_FREE}
    if "anomalies_only_at" in exp:
        assert anomalous == {exp["anomalies_only_at"]}
    if "root_cause_location_if_diagnosed" in exp and r["status"] == "diagnosed":
        assert {c["location"].split(":")[0] for c in r["root_causes"]} == {exp["root_cause_location_if_diagnosed"]}
        assert exp["root_cause_location_if_diagnosed"] in r["affected_devices"]
    for item in r["supporting_evidence"]:  # every value is a stored observation with its unit
        o = store.get_observation(item["observation_id"])
        assert o is not None and o.measurement.value == item["value"] and o.measurement.unit == item["unit"]
    # undefined generator fields are reported, never silently used
    unmapped = [i for rep in loaded["ingestions"] for i in rep.issues if i.code == "UNMAPPED_FIELD"]
    assert unmapped and "metrics.queue_drops" in unmapped[0].message and "status" in unmapped[0].message


def test_profile_maps_organizer_record_without_inference():
    rec = {"timestamp": "2026-10-31T09:50:00Z", "device_id": "SW_CAMPUS_3",
           "metrics": {"cpu_utilization_pct": 99.9, "link_utilization_pct": 100.0, "packet_loss_pct": 21.5,
                       "latency_ms": 712.3, "queue_drops": 9000, "interface_errors": 300}, "status": "Critical"}
    out = adapt(json.dumps([rec]), builtin_profile("organizer-colab-json"))
    ms = {m["metric"]: (m["value"], m["unit"]) for m in out.batch["records"][0]["measurements"]}
    assert ms == {"cpu_utilization": (99.9, "percent"), "link_utilization": (100.0, "percent"),
                  "packet_loss": (21.5, "percent"), "latency": (712.3, "ms")}
    assert out.batch["records"][0]["subject"] == {"device_id": "SW_CAMPUS_3"}
    assert out.originals == [rec]  # raw record keeps the nested payload exactly as received
    msg = [i.message for i in out.issues if i.code == "UNMAPPED_FIELD"][0]
    assert "metrics.interface_errors" in msg and "metrics.queue_drops" in msg and "status" in msg


def test_nested_paths_need_explicit_opt_in():
    prof = dict(builtin_profile("organizer-colab-json"))
    prof.pop("field_path_separator")
    rec = {"timestamp": "2026-10-31T09:50:00Z", "device_id": "SW_CAMPUS_3", "metrics": {"latency_ms": 10.0}}
    out = adapt(json.dumps([rec]), prof)
    assert out.batch["records"][0]["measurements"] == []  # nothing read from the nested object
    assert any(i.code == "UNMAPPED_FIELD" and "metrics" in i.message for i in out.issues)


def test_schema_drift_is_reported_record_by_record(store):
    loaded = load_into(store, BASE, "ORG-04-schema-drift")
    issues = [i for rep in loaded["ingestions"] for i in rep.issues]
    codes = {i.code for i in issues}
    assert {"UNMAPPED_FIELD", "TYPE_MISMATCH", "OUT_OF_RANGE", "DUPLICATE_RECORD"} <= codes, codes
    by_record = {}
    for i in issues:
        if i.record_index is not None:
            by_record.setdefault(i.record_index, set()).add(i.severity)
    assert "reject" in by_record.get(11, set())  # device_id removed
    assert "reject" in by_record.get(21, set())  # non-ISO timestamp
    assert "metrics.latency_s" in [i.message for i in issues if i.code == "UNMAPPED_FIELD"][0]
