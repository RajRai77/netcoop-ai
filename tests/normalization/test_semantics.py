"""Semantic validation of measurements: units, values, kinds, subjects, time, staleness."""

from __future__ import annotations

import pytest

from netcoop.evidence.errors import EvidenceError, IssueCode, Severity
from netcoop.evidence.models import TopologySnapshot
from netcoop.evidence.normalize import Limits, normalize_batch
from netcoop.spec import validator
from tests.conftest import NOW, batch, example, later, meas, record


def run(payload, **kw):
    kw.setdefault("incident_id", "INC-T")
    kw.setdefault("ingested_at", NOW)
    return normalize_batch(payload, **kw)


def codes(result, severity=None):
    return [i.code for i in result.issues if severity is None or i.severity == severity]


def one(m, **rec_kw):
    return run(batch(record("R1", m, **rec_kw)))


# --- happy path + contract -----------------------------------------------------------

def test_example_batch_produces_schema_valid_observations():
    res = run(example("telemetry-batch"))
    assert [o.status for o in res.outcomes] == ["accepted", "accepted"]
    assert len(res.observations) == 3
    for o in res.observations:
        assert list(validator("observation").iter_errors(o.to_json_dict())) == []


def test_one_record_two_measurements_share_raw_record_and_lineage():
    res = run(example("telemetry-batch"))
    a, b = res.observations[0], res.observations[1]
    assert a.raw_record_ref == b.raw_record_ref
    assert a.lineage_group == b.lineage_group
    assert a.observation_id != b.observation_id


def test_ids_are_deterministic():
    r1, r2 = run(example("telemetry-batch")), run(example("telemetry-batch"))
    assert [o.observation_id for o in r1.observations] == [o.observation_id for o in r2.observations]


# --- units ---------------------------------------------------------------------------

def test_missing_unit_is_rejected_not_guessed():
    res = one({"metric": "packet_loss", "value": 0.02})
    assert IssueCode.MISSING_UNIT in codes(res, Severity.REJECT)
    assert res.observations == []


def test_ambiguous_packet_loss_needs_explicit_unit_and_both_readings_are_kept_distinct():
    pct = one(meas("packet_loss", 0.02, "percent", "gauge")).observations[0]
    ratio = one(meas("packet_loss", 0.02, "ratio", "gauge")).observations[0]
    assert pct.measurement.value == 0.02 and pct.measurement.unit == "percent"
    assert ratio.measurement.value == 2.0 and ratio.measurement.unit == "percent"
    assert ratio.transformation_id.endswith("unit:ratio->percent")


@pytest.mark.parametrize("unit", ["fraction", "Percent", "pct", "dB"])
def test_unlisted_unit_is_rejected(unit):
    res = one(meas("packet_loss", 1.0, unit, "gauge"))
    assert codes(res, Severity.REJECT) == [IssueCode.UNSUPPORTED_UNIT]


def test_unit_alias_is_spelling_only():
    o = one(meas("link_utilization", 40, "%", "gauge")).observations[0]
    assert o.measurement.unit == "percent" and o.measurement.value == 40
    assert "unit_alias:%->percent" in o.quality.flags
    assert o.transformation_id is None  # no value change


@pytest.mark.parametrize("value,unit,expected", [
    (0.085, "s", 85.0), (1.5, "Mbit/s", 1_500_000.0), (2, "Gbit/s", 2_000_000_000), (250, "kbps", 250_000),
])
def test_explicit_conversions_are_exact(value, unit, expected):
    metric = "latency" if unit == "s" else "throughput"
    o = one(meas(metric, value, unit, "gauge")).observations[0]
    assert o.measurement.value == expected
    assert IssueCode.UNIT_CONVERTED in codes(one(meas(metric, value, unit, "gauge")), Severity.WARNING)


# --- values ---------------------------------------------------------------------------

def test_missing_value_is_not_zero():
    for m in ({"metric": "cpu_utilization", "unit": "percent", "kind": "gauge"},
              meas("cpu_utilization", None, "percent", "gauge")):
        res = one(m)
        assert codes(res, Severity.REJECT) == [IssueCode.MISSING_VALUE]
        assert res.observations == []


def test_nan_and_infinity_from_raw_json_are_rejected():
    raw = (b'{"schema_version":"1.0.0","source":{"source_id":"s","data_mode":"synthetic","source_type":"file"},'
           b'"records":[{"record_id":"a","subject":{"device_id":"D"},"observed_at":"2026-10-31T10:00:00Z",'
           b'"measurements":[{"metric":"latency","value":NaN,"unit":"ms","kind":"gauge"},'
           b'{"metric":"jitter","value":Infinity,"unit":"ms","kind":"gauge"},'
           b'{"metric":"cpu_utilization","value":12.5,"unit":"percent","kind":"gauge"}]}]}')
    res = run(raw)
    assert codes(res, Severity.REJECT) == [IssueCode.NON_FINITE_VALUE, IssueCode.NON_FINITE_VALUE]
    assert [o.measurement.metric for o in res.observations] == ["cpu_utilization"]
    assert res.outcomes[0].status == "partially_rejected"


@pytest.mark.parametrize("value", ["94", True, [94]])
def test_numeric_metric_rejects_non_numbers_without_coercion(value):
    res = one(meas("link_utilization", value, "percent", "gauge"))
    assert IssueCode.TYPE_MISMATCH in codes(res, Severity.REJECT) or IssueCode.SCHEMA_INVALID in codes(res)
    assert res.observations == []


@pytest.mark.parametrize("metric,value,unit", [
    ("link_utilization", 100.5, "percent"), ("packet_loss", -1, "percent"), ("packet_loss", 1.5, "ratio"),
    ("latency", -3, "ms"), ("rssi", 5, "dBm"),
])
def test_out_of_range_values_rejected(metric, value, unit):
    res = one(meas(metric, value, unit, "gauge"))
    assert codes(res, Severity.REJECT) == [IssueCode.OUT_OF_RANGE]


def test_negative_rssi_is_valid():
    assert one(meas("rssi", -78, "dBm", "gauge")).observations[0].measurement.value == -78


def test_state_and_boolean_metrics_are_strict():
    assert one(meas("device_status", "down", "state")).observations[0].measurement.value == "down"
    assert codes(one(meas("device_status", "DOWN", "state")), Severity.REJECT) == [IssueCode.INVALID_STATE_VALUE]
    assert one(meas("reachability", False, "boolean")).observations[0].measurement.value is False
    assert codes(one(meas("reachability", 0, "boolean")), Severity.REJECT) == [IssueCode.TYPE_MISMATCH]
    assert codes(one(meas("reachability", "false", "boolean")), Severity.REJECT) == [IssueCode.TYPE_MISMATCH]


def test_counter_must_be_integer():
    assert codes(one(meas("crc_errors", 10.0, "count", "cumulative_counter")), Severity.REJECT) == [IssueCode.TYPE_MISMATCH]


def test_unknown_metric_rejected():
    assert codes(one(meas("magic_score", 1, "percent", "gauge")), Severity.REJECT) == [IssueCode.UNKNOWN_METRIC]


# --- kinds ----------------------------------------------------------------------------

def test_kind_defaults_only_when_registry_allows_exactly_one():
    o = one(meas("crc_errors", 5, "count")).observations[0]
    assert o.measurement.kind == "cumulative_counter" and "kind_from_registry" in o.quality.flags
    assert codes(one(meas("latency", 5, "ms")), Severity.REJECT) == [IssueCode.MISSING_KIND]


def test_kind_mismatch_rejected():
    assert codes(one(meas("crc_errors", 5, "count", "gauge")), Severity.REJECT) == [IssueCode.KIND_MISMATCH]


def test_interval_summary_requires_window():
    assert codes(one(meas("latency", 5, "ms", "interval_summary")), Severity.REJECT) == [IssueCode.WINDOW_REQUIRED]


# --- time -----------------------------------------------------------------------------

@pytest.mark.parametrize("ts,code", [
    ("2026-10-31T10:00:00", IssueCode.MISSING_TIMEZONE),
    ("2026-10-31", IssueCode.INVALID_TIMESTAMP),
    ("yesterday", IssueCode.INVALID_TIMESTAMP),
    (1793440800, IssueCode.INVALID_TIMESTAMP),
])
def test_bad_timestamps_reject_the_record(ts, code):
    res = one(meas("latency", 5, "ms", "gauge"), observed_at=ts)
    assert code in codes(res, Severity.REJECT)
    assert res.outcomes[0].status == "rejected"


def test_timezone_offset_is_converted_to_utc():
    o = one(meas("latency", 5, "ms", "gauge"), observed_at="2026-10-31T15:30:00+05:30").observations[0]
    assert o.observed_at.isoformat() == "2026-10-31T10:00:00+00:00"


def test_future_timestamp_beyond_skew_rejected():
    res = one(meas("latency", 5, "ms", "gauge"), observed_at="2026-10-31T10:05:00Z")
    assert codes(res, Severity.REJECT) == [IssueCode.FUTURE_TIMESTAMP]


def test_stale_observation_is_kept_and_flagged_not_dropped():
    res = run(batch(record("R1", meas("latency", 5, "ms", "gauge"), observed_at="2026-10-31T09:00:00Z")))
    o = res.observations[0]
    assert o.quality.freshness == "stale" and "stale" in o.quality.flags
    assert o.quality.validation == "passed" and o.measurement.value == 5
    assert IssueCode.STALE_OBSERVATION in codes(res, Severity.WARNING)


def test_window_must_contain_observed_at_and_be_ordered():
    bad_order = {"start": "2026-10-31T10:00:00Z", "end": "2026-10-31T09:59:00Z"}
    outside = {"start": "2026-10-31T09:58:00Z", "end": "2026-10-31T09:59:00Z"}
    for w in (bad_order, outside):
        res = one(meas("latency", 5, "ms", "interval_summary"), window=w)
        assert codes(res, Severity.REJECT) == [IssueCode.INVALID_WINDOW]


# --- subject / topology ---------------------------------------------------------------

def test_subject_rules():
    assert IssueCode.INVALID_SUBJECT in codes(one(meas("latency", 1, "ms", "gauge"), subject={"interface_id": "eth1"}), Severity.REJECT)
    assert IssueCode.INVALID_SUBJECT in codes(one(meas("latency", 1, "ms", "gauge"), subject={"device_id": ""}), Severity.REJECT)
    assert IssueCode.INVALID_SUBJECT in codes(one(meas("latency", 1, "ms", "gauge"), subject={"device_id": "D", "vlan": "1"}), Severity.REJECT)


def test_unknown_subject_is_quarantined_against_topology():
    topo = TopologySnapshot.model_validate(example("topology"))
    good = run(batch(record("R1", meas("latency", 1, "ms", "gauge"), subject={"device_id": "SW-01"})), topology=topo)
    bad = run(batch(record("R2", meas("latency", 1, "ms", "gauge"), subject={"device_id": "SW-99"})), topology=topo)
    assert good.observations[0].quality.validation == "passed"
    assert "subject_unverified" not in good.observations[0].quality.flags
    o = bad.observations[0]
    assert o.quality.validation == "quarantined" and "unknown_subject" in o.quality.flags
    assert bad.outcomes[0].status == "quarantined"


def test_without_topology_subject_is_marked_unverified():
    o = one(meas("latency", 1, "ms", "gauge")).observations[0]
    assert "subject_unverified" in o.quality.flags


# --- batch-level ----------------------------------------------------------------------

def test_unsupported_schema_version_rejects_batch():
    b = batch(record()); b["schema_version"] = "2.0.0"
    with pytest.raises(EvidenceError) as e:
        run(b)
    assert e.value.codes == [IssueCode.UNSUPPORTED_SCHEMA_VERSION]


def test_malformed_json_and_duplicate_keys_rejected():
    for raw in (b"{not json", b'{"schema_version":"1.0.0","schema_version":"1.0.0"}'):
        with pytest.raises(EvidenceError) as e:
            run(raw)
        assert e.value.codes == [IssueCode.MALFORMED_JSON]


def test_payload_and_record_limits():
    with pytest.raises(EvidenceError) as e:
        run(b"x" * 101, limits=Limits(max_payload_bytes=100))
    assert e.value.codes == [IssueCode.PAYLOAD_TOO_LARGE]
    with pytest.raises(EvidenceError) as e:
        run(batch(record("a"), record("b")), limits=Limits(max_records=1))
    assert e.value.codes == [IssueCode.TOO_MANY_RECORDS]


def test_envelope_schema_error_and_data_mode_mismatch():
    b = batch(record()); b["source"]["data_mode"] = "production"
    with pytest.raises(EvidenceError) as e:
        run(b)
    assert IssueCode.SCHEMA_INVALID in e.value.codes
    with pytest.raises(EvidenceError) as e:
        run(batch(record(), data_mode="recorded"), expected_data_mode="synthetic")
    assert e.value.codes == [IssueCode.DATA_MODE_MISMATCH]


def test_unknown_record_field_rejects_only_that_record():
    good, bad = record("ok"), record("bad")
    bad["temperature"] = 40
    res = run(batch(good, bad))
    assert [o.status for o in res.outcomes] == ["accepted", "rejected"]
    assert IssueCode.SCHEMA_INVALID in codes(res, Severity.REJECT)


def test_in_batch_duplicate_and_record_id_conflict():
    r = record("R1")
    changed = record("R1", meas("link_utilization", 51.0, "percent", "gauge"))
    res = run(batch(r, r, changed))
    assert [o.status for o in res.outcomes] == ["accepted", "duplicate", "conflict"]
    assert len(res.observations) == 1


def test_origin_sample_id_links_lineage_across_collectors():
    a = run(batch(record("A1", origin_sample_id="SNMP-SW01-eth1-t0"), source_id="collector-a"))
    b = run(batch(record("B7", origin_sample_id="SNMP-SW01-eth1-t0"), source_id="collector-b"))
    c = run(batch(record("C1"), source_id="collector-c"))
    assert a.observations[0].lineage_group == b.observations[0].lineage_group
    assert a.observations[0].lineage_group != c.observations[0].lineage_group


def test_ingested_at_reference_is_used_for_staleness():
    res = run(batch(record("R1", meas("latency", 5, "ms", "gauge"))), ingested_at=later(3600))
    assert res.observations[0].quality.freshness == "stale"
