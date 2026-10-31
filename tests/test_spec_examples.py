"""Baseline check that the draft NDEP schemas are valid and their examples conform.

These are starter contracts (see spec/README.md), not official organizer schemas.
"""

import copy
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

SPEC = Path(__file__).resolve().parents[1] / "spec"
NAMES = ["observation", "finding", "challenge", "report", "topology", "scenario-manifest", "telemetry-batch"]


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize("name", NAMES)
def test_schema_is_valid_draft_2020_12(name):
    Draft202012Validator.check_schema(_load(SPEC / f"{name}.schema.json"))


@pytest.mark.parametrize("name", NAMES)
def test_example_conforms(name):
    schema = _load(SPEC / f"{name}.schema.json")
    example = _load(SPEC / "examples" / f"{name}-example.json")
    errors = list(Draft202012Validator(schema).iter_errors(example))
    assert errors == [], [e.message for e in errors]


@pytest.mark.parametrize("name", NAMES)
def test_example_missing_required_field_is_rejected(name):
    schema = _load(SPEC / f"{name}.schema.json")
    example = _load(SPEC / "examples" / f"{name}-example.json")
    for field in schema.get("required", []):
        broken = copy.deepcopy(example)
        broken.pop(field, None)
        assert not Draft202012Validator(schema).is_valid(broken), f"{name} accepted missing {field!r}"


def test_report_rejects_unknown_top_level_field():
    schema = _load(SPEC / "report.schema.json")
    example = _load(SPEC / "examples" / "report-example.json")
    example["probability"] = 0.93  # invented numeric confidence must not slip in
    assert not Draft202012Validator(schema).is_valid(example)


def test_metric_registry_parses_and_lists_units():
    reg = _load(SPEC / "metric_registry.json")
    assert reg["metrics"], "registry has no metrics"
    for name, m in reg["metrics"].items():
        assert m.get("allowed_units"), f"{name} has no allowed_units"
