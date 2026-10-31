"""Counter-rate derivation: resets, ordering, insufficient samples, mixed sources."""

from __future__ import annotations

from netcoop.evidence.counters import derive_counter_rates
from netcoop.evidence.errors import IssueCode
from netcoop.evidence.normalize import normalize_batch
from tests.conftest import NOW, batch, later, meas, record


def obs(samples, source_id="col-a", metric="crc_errors"):
    """samples: list of (record_id, iso_ts, value)."""
    recs = [record(rid, meas(metric, v, "count", "cumulative_counter"), observed_at=ts) for rid, ts, v in samples]
    return normalize_batch(batch(*recs, source_id=source_id), incident_id="I", ingested_at=later(600)).observations


def ts(sec: int) -> str:
    return f"2026-10-31T10:{sec // 60:02d}:{sec % 60:02d}Z"


def test_rate_from_two_samples_out_of_order_input():
    rates, issues = derive_counter_rates(obs([("b", ts(60), 1600), ("a", ts(0), 1000)]))
    assert issues == []
    (r,) = rates
    assert r.value == 10.0 and r.unit == "count/s" and r.rate_metric == "crc_errors_rate"
    assert len(r.input_observation_ids) == 2


def test_reset_produces_no_rate_across_it():
    rates, issues = derive_counter_rates(obs([("a", ts(0), 5000), ("b", ts(60), 20), ("c", ts(120), 620)]))
    assert [i.code for i in issues] == [IssueCode.COUNTER_RESET]
    assert [r.value for r in rates] == [10.0]  # only the post-reset pair


def test_single_sample_is_insufficient():
    rates, issues = derive_counter_rates(obs([("a", ts(0), 5)]))
    assert rates == [] and [i.code for i in issues] == [IssueCode.COUNTER_INSUFFICIENT_SAMPLES]


def test_conflicting_values_at_same_instant_are_dropped():
    rates, issues = derive_counter_rates(obs([("a", ts(0), 5), ("b", ts(0), 9), ("c", ts(60), 65)]))
    codes = [i.code for i in issues]
    assert IssueCode.COUNTER_TIMESTAMP_CONFLICT in codes
    assert IssueCode.COUNTER_INSUFFICIENT_SAMPLES in codes
    assert rates == []


def test_impossible_rate_is_not_used():
    rates, issues = derive_counter_rates(obs([("a", ts(0), 0), ("b", ts(1), 10**12)]))
    assert rates == [] and [i.code for i in issues] == [IssueCode.IMPOSSIBLE_RATE]


def test_different_sources_are_not_differenced_together():
    o = obs([("a", ts(0), 100)], source_id="col-a") + obs([("b", ts(60), 700)], source_id="col-b")
    rates, issues = derive_counter_rates(o)
    assert rates == []
    assert IssueCode.COUNTER_MIXED_LINEAGE in [i.code for i in issues]


def test_non_counter_observations_ignored():
    o = normalize_batch(batch(record("a")), incident_id="I", ingested_at=NOW).observations
    assert derive_counter_rates(o) == ([], [])
