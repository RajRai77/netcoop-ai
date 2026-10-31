"""End-to-end diagnosis of every labeled dev scenario (in-process transport).

Expectations come from data/scenarios/*/ground_truth.json, written by the generator
from the injected faults. Never edit them to make a run pass.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from netcoop.agents.protocol import SPECIALISTS
from netcoop.engine.planner import VerificationPolicy
from netcoop.orchestration.coordinator import Coordinator, CoordinatorOptions
from netcoop.orchestration.ports import InProcessAgentPort
from netcoop.scenarios.loader import list_scenarios, load_into
from netcoop.spec import validator

BASE = Path(__file__).resolve().parents[2] / "data" / "scenarios"
IDS = [s["scenario_id"] for s in list_scenarios(BASE)]


def run(store, sid, verify):
    inc = load_into(store, BASE, sid)["incident"]
    ports = [InProcessAgentPort(a, BASE, None) for a in SPECIALISTS]
    opts = CoordinatorOptions(verification=VerificationPolicy(enabled=verify))
    return Coordinator(store, ports, opts).run(inc.incident_id)


def truth_text(gt):
    return " + ".join(f"{f['fault_type']} at {f['location']}" for f in gt["faults"]) or None


@pytest.mark.parametrize("verify", [False, True], ids=["no-verification", "verification"])
@pytest.mark.parametrize("sid", IDS)
def test_dev_scenario_matches_ground_truth(store, sid, verify):
    gt = json.loads((BASE / sid / "ground_truth.json").read_text(encoding="utf-8"))
    r = run(store, sid, verify)
    assert list(validator("report").iter_errors(r)) == []
    expected = gt["expected_status"] if verify else gt["expected_status_without_verification"]
    assert r["status"] == expected, r["decision_basis"]
    if r["status"] == "diagnosed":
        assert r["suspected_root_cause"] == truth_text(gt)
        assert r["confidence_category"] in ("high_support", "moderate_support")
        for item in r["supporting_evidence"]:  # every value is a stored observation with its unit
            o = store.get_observation(item["observation_id"])
            assert o is not None and o.measurement.value == item["value"] and o.measurement.unit == item["unit"]
    else:
        assert r["suspected_root_cause"] is None
    assert r["transport"] == "in-process"


def test_verification_changes_outcome_only_with_new_evidence(store):
    r = run(store, "S11-ambiguous-resolvable", True)
    v = r["verification"]
    assert v["challenges"] and any(c["outcome"] == "obtained" for c in v["challenges"])
    new_ids = {i for c in v["challenges"] for i in c["new_observation_ids"]}
    used = {e["observation_id"] for e in r["supporting_evidence"]}
    assert used & new_ids, "diagnosis must rest on the newly obtained evidence"
    for c in v["challenges"]:
        for oid in c["new_observation_ids"]:
            raw = store.get_raw_record(store.get_observation(oid).raw_record_ref)
            assert raw.batch_id == c["challenge_id"]  # traceable to the challenge that obtained it


def test_unresolvable_ambiguity_stays_ambiguous_and_says_why(store):
    r = run(store, "S16-ambiguous-unresolvable", True)
    assert r["status"] == "ambiguous"
    assert all(c["outcome"] == "unavailable" for c in r["verification"]["challenges"])
    assert r["verification"]["stopped_because"] == "requested checks returned no new evidence"
    assert len(r["alternative_causes"]) >= 2


def test_rerun_creates_new_revision_and_keeps_old(store):
    inc = load_into(store, BASE, "S01-congestion")["incident"]
    ports = [InProcessAgentPort(a, BASE, None) for a in SPECIALISTS]
    r1 = Coordinator(store, ports).run(inc.incident_id)
    r2 = Coordinator(store, ports).run(inc.incident_id)
    assert (r1["revision"], r2["revision"]) == (1, 2)
    assert store.get_report(inc.incident_id, 1)["run_id"] == r1["run_id"]
    assert r1["evidence_snapshot_id"] == r2["evidence_snapshot_id"]  # same evidence -> same snapshot
    assert r1["suspected_root_cause"] == r2["suspected_root_cause"]
    states = [e["state"] for e in store.list_events(inc.incident_id)]
    assert states.count("DIAGNOSED") == 2 and states[0] == "NEW"
