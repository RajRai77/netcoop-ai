"""Pydantic models and spec/*.schema.json must accept and reject the same documents."""

from __future__ import annotations

import copy

import pytest
from pydantic import ValidationError

from netcoop.evidence.models import Finding, NormalizedObservation, TopologySnapshot
from netcoop.evidence.registry import default_registry
from netcoop.evidence.timeutil import parse_timestamp
from netcoop.spec import load_json, validator
from tests.conftest import example

MODELS = {"observation": NormalizedObservation, "finding": Finding, "topology": TopologySnapshot}
TS_FIELDS = {"observed_at", "ingested_at", "created_at", "start", "end"}


def _same_instants(a, b):
    """Compare JSON docs treating timestamps as instants (formatting may differ)."""
    if isinstance(a, dict):
        assert a.keys() == b.keys()
        for k in a:
            if k in TS_FIELDS:
                assert parse_timestamp(a[k]) == parse_timestamp(b[k])
            else:
                _same_instants(a[k], b[k])
    elif isinstance(a, list):
        assert len(a) == len(b)
        for x, y in zip(a, b):
            _same_instants(x, y)
    else:
        assert a == b and type(a) is type(b)


@pytest.mark.parametrize("name", MODELS)
def test_example_round_trips_through_model_and_stays_schema_valid(name):
    doc = example(name)
    model = MODELS[name].model_validate(doc)
    out = model.to_json_dict()
    assert list(validator(name).iter_errors(out)) == []
    _same_instants(doc, out)


def _mutations(name: str):
    """(description, mutate-fn) pairs that the schema must reject."""
    base = example(name)
    req = load_json(f"{name}.schema.json")["required"]
    for field in req:
        if field == "schema_version":
            continue  # models default it; covered by wrong-version case below
        yield f"missing {field}", (lambda d, f=field: d.pop(f))
    yield "extra top-level field", lambda d: d.__setitem__("probability", 0.9)
    yield "wrong schema_version", lambda d: d.__setitem__("schema_version", "9.9.9")
    if "subject" in base:
        yield "subject without anchor", lambda d: d.__setitem__("subject", {"interface_id": "eth1"})
    if name == "observation":
        yield "bad data_mode", lambda d: d["source"].__setitem__("data_mode", "production")
        yield "bad kind", lambda d: d["measurement"].__setitem__("kind", "average")
        yield "missing unit", lambda d: d["measurement"].pop("unit")
        yield "bad validation", lambda d: d["quality"].__setitem__("validation", "ok")
        yield "duplicate flags", lambda d: d["quality"].__setitem__("flags", ["a", "a"])
    if name == "finding":
        yield "empty observation_refs", lambda d: d.__setitem__("observation_refs", [])
        yield "duplicate observation_refs", lambda d: d.__setitem__("observation_refs", ["A", "A"])
        yield "bad polarity", lambda d: d.__setitem__("polarity", "maybe")
    if name == "topology":
        yield "bad node type", lambda d: d["nodes"][0].__setitem__("type", "router")
        yield "bad link type", lambda d: d["links"][0].__setitem__("type", "wireless")


CASES = [(n, desc, fn) for n in MODELS for desc, fn in _mutations(n)]


@pytest.mark.parametrize("name,desc,mutate", CASES, ids=[f"{n}:{d}" for n, d, _ in CASES])
def test_schema_and_model_both_reject(name, desc, mutate):
    doc = copy.deepcopy(example(name))
    mutate(doc)
    assert not validator(name).is_valid(doc), f"schema accepted: {desc}"
    with pytest.raises(ValidationError):
        MODELS[name].model_validate(doc)


@pytest.mark.parametrize("ts", ["2026-10-31T10:00:00", "2026-10-31", 1793440800])
def test_model_rejects_naive_or_non_string_timestamps(ts):
    doc = example("observation")
    doc["observed_at"] = ts
    with pytest.raises(ValidationError):
        NormalizedObservation.model_validate(doc)


def test_model_rejects_non_finite_values():
    doc = example("observation")
    doc["measurement"]["value"] = float("nan")
    with pytest.raises(ValidationError):
        NormalizedObservation.model_validate(doc)


def test_telemetry_batch_example_is_valid():
    assert list(validator("telemetry-batch").iter_errors(example("telemetry-batch"))) == []


def test_registry_is_internally_consistent():
    reg = default_registry()
    assert reg.version == load_json("metric_registry.json")["metric_registry_version"]
    canonical = {m.canonical_unit for m in reg.metrics.values()}
    all_units = {u for m in reg.metrics.values() for u in m.allowed_units}
    for (src, dst), factor in reg.conversions.items():
        assert dst in canonical and src in all_units and factor > 0
    for alias, target in reg.unit_aliases.items():
        assert target in all_units, f"alias {alias} -> unknown unit {target}"
        assert alias not in all_units, f"alias {alias} shadows a real unit"
    kinds = {"gauge", "cumulative_counter", "derived_rate", "interval_summary", "state"}
    for m in reg.metrics.values():
        assert set(m.allowed_kinds) <= kinds and m.allowed_kinds
        if m.value_type == "enum":
            assert m.allowed_values


def test_registry_without_conversion_factor_is_refused():
    from netcoop.evidence.registry import MetricRegistry
    data = copy.deepcopy(load_json("metric_registry.json"))
    data["conversions"] = [c for c in data["conversions"] if c["from"] != "s"]
    with pytest.raises(ValueError, match="no conversion s -> ms"):
        MetricRegistry.from_dict(data)
