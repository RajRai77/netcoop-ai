"""Calibrated `confidence` in the report (schema 1.2.0).

The numbers are derived by scripts/calibrate_confidence.py from held-out results; these tests check that the
checked-in calibration reproduces from its source file, that reports carry exactly the calibrated value with its
basis, and that no number is produced when the knowledge it was measured with has changed.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

import netcoop.knowledge as knowledge
from netcoop.agents.protocol import SPECIALISTS
from netcoop.engine.planner import VerificationPolicy
from netcoop.evidence.ids import canonical_json
from netcoop.orchestration.coordinator import Coordinator, CoordinatorOptions
from netcoop.orchestration.ports import InProcessAgentPort
from netcoop.scenarios.loader import load_into
from netcoop.spec import validator

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "data" / "scenarios"


def test_calibration_reproduces_from_its_source():
    cal = knowledge.confidence_calibration()
    assert cal is not None
    src = ROOT / cal["source"]["results"]
    res = json.loads(src.read_text(encoding="utf-8"))
    assert hashlib.sha256(canonical_json(res).encode()).hexdigest() == cal["source"]["results_sha256_canonical"]
    cases = res["sets"][cal["source"]["set"]]["cases"][cal["source"]["method"]]
    counts: dict[str, list[int]] = {}
    for c in cases:
        ok = c["score"]["exact_cause"] if c["status"] == "diagnosed" else c["score"]["acceptable"]
        n = counts.setdefault(f"{c['status']}|{c['category']}", [0, 0])
        n[0] += bool(ok)
        n[1] += 1
    assert {k: [v["correct"], v["n"]] for k, v in cal["cells"].items()} == counts
    for v in cal["cells"].values():
        assert v["confidence"] == round((v["correct"] + 1) / (v["n"] + 2), 2)
        assert 0 < v["confidence"] < 1  # never certainty from a finite sample
        assert v["wilson_95"][0] <= v["correct"] / v["n"] <= v["wilson_95"][1]


def _run(store, sid):
    inc = load_into(store, BASE, sid)["incident"]
    ports = [InProcessAgentPort(a, BASE, None) for a in SPECIALISTS]
    return Coordinator(store, ports, CoordinatorOptions(verification=VerificationPolicy(enabled=True))).run(inc.incident_id)


def test_report_carries_calibrated_confidence(store):
    r = _run(store, "S04-device-down")
    assert list(validator("report").iter_errors(r)) == []
    assert r["schema_version"] == "1.2.0"
    cell = knowledge.confidence_calibration()["cells"][f"{r['status']}|{r['confidence_category']}"]
    assert r["confidence"] == cell["confidence"]
    b = r["confidence_basis"]
    assert b["method"] == "empirical_heldout" and b["n"] == cell["n"] and b["correct"] == cell["correct"]
    assert any("confidence" in lim and "held-out" in lim for lim in r["limitations"])


def test_no_confidence_when_knowledge_changed(store, monkeypatch):
    cal = json.loads(json.dumps(knowledge.confidence_calibration()))
    cal["knowledge"]["sha256"]["fault_library.json"] = "0" * 64
    monkeypatch.setattr(knowledge, "confidence_calibration", lambda: cal)
    value, basis = knowledge.confidence_for("diagnosed", "high_support")
    assert value is None and basis["method"] == "none" and "knowledge changed" in basis["reason"]


def test_unseen_conclusion_has_no_number():
    value, basis = knowledge.confidence_for("operational_error", "insufficient")
    assert value is None and basis["method"] == "none"


@pytest.mark.parametrize("sid", ["ORG-03-hardware-failure"])
def test_organizer_report_states_calibration_scope(store, sid):
    r = _run(store, sid)
    assert r["confidence"] is not None
    assert any("not validated on other data sources" in lim for lim in r["limitations"])
