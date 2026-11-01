"""Evidence ledger: persistence, duplicates, conflicts, immutability, findings, provenance.

Runs on SQLite (always) and PostgreSQL (only when NETCOOP_TEST_DATABASE_URL is set).
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from netcoop.evidence.errors import EvidenceError, IssueCode
from netcoop.evidence.models import Finding, TopologySnapshot
from netcoop.ledger import ingest_telemetry
from netcoop.storage import SqlEvidenceStore, make_engine, migrate
from netcoop.storage.tables import APPEND_ONLY_TABLES
from tests.conftest import NOW, batch, example, later, meas, record


def new_incident(store, incident_id="INC-1", data_mode="synthetic", topology_snapshot_id=None):
    return store.create_incident(incident_id, data_mode, created_at=NOW, topology_snapshot_id=topology_snapshot_id)


def finding(fid, obs_refs, agent="performance-agent", supersedes=None, created="2026-10-31T10:00:06Z", claim="X"):
    return Finding.model_validate({
        "finding_id": fid, "incident_id": "INC-1", "agent_id": agent, "claim": claim, "polarity": "present",
        "subject": {"device_id": "SW-01"}, "observation_refs": obs_refs, "rule_or_model_version": "test-rule/1",
        "created_at": created, "caveats": [], "supersedes_finding_id": supersedes,
    })


# --- migrations -----------------------------------------------------------------------

def test_schema_at_head(store):
    assert store.schema_revision() == migrate.head_revision() == "0003"


def test_migration_matches_table_metadata(store):
    from alembic.autogenerate import compare_metadata
    from alembic.runtime.migration import MigrationContext

    from netcoop.storage.tables import metadata
    with store.engine.connect() as conn:
        diffs = compare_metadata(MigrationContext.configure(conn), metadata)
    assert diffs == []


def test_downgrade_then_upgrade_is_repeatable(db_url):
    engine = make_engine(db_url)
    try:
        migrate.upgrade(engine)
        migrate.downgrade(engine, "base")
        assert migrate.current_revision(engine) is None
        migrate.upgrade(engine)
        assert migrate.current_revision(engine) == "0003"
    finally:
        engine.dispose()


# --- ingestion, duplicates, conflicts ------------------------------------------------

def test_ingest_and_read_back_exact_observations(store):
    new_incident(store)
    rep = ingest_telemetry(store, "INC-1", example("telemetry-batch"), now=NOW)
    assert rep.counts["accepted"] == 2 and rep.observations_added == 3
    stored = store.list_observations("INC-1")
    assert {o.observation_id for o in stored} == {i for r in rep.records for i in r.observation_ids}
    for o in stored:
        assert store.get_observation(o.observation_id) == o
        raw = store.get_raw_record(o.raw_record_ref)
        assert raw is not None and raw.content  # every observation traces to an immutable raw record


def test_resubmission_is_duplicate_and_adds_nothing(store):
    new_incident(store)
    ingest_telemetry(store, "INC-1", example("telemetry-batch"), now=NOW)
    rep = ingest_telemetry(store, "INC-1", example("telemetry-batch"), now=later(1))
    assert rep.counts["duplicate"] == 2 and rep.observations_added == 0
    assert store.count_incident_evidence("INC-1")["observations"] == 3


def test_record_id_reuse_with_new_content_is_conflict_and_original_kept(store):
    new_incident(store)
    ingest_telemetry(store, "INC-1", batch(record("R1")), now=NOW)
    rep = ingest_telemetry(store, "INC-1", batch(record("R1", meas("link_utilization", 99.0, "percent", "gauge"))),
                           now=later(1))
    assert rep.records[0].status == "conflict" and rep.observations_added == 0
    assert IssueCode.RECORD_ID_CONFLICT in [i.code for i in rep.issues]
    (o,) = store.list_observations("INC-1")
    assert o.measurement.value == 50.0
    # the conflicting payload is still retained as a rejected raw record for audit
    assert store.count_incident_evidence("INC-1")["raw_records"] == 2


def test_rejected_record_is_retained_with_typed_issue(store):
    new_incident(store)
    rep = ingest_telemetry(store, "INC-1", batch(record("R1", {"metric": "packet_loss", "value": 0.02})), now=NOW)
    assert rep.records[0].status == "rejected"
    raw = store.get_raw_record(rep.records[0].raw_id)
    assert raw is not None and '"value":0.02' in raw.content
    rejects = [i for i in store.list_issues("INC-1") if i.severity == "reject"]
    assert [i.code for i in rejects] == ["MISSING_UNIT"] and rejects[0].raw_id == raw.raw_id


def test_rejected_record_id_can_later_be_admitted_with_corrected_content(store):
    new_incident(store)
    ingest_telemetry(store, "INC-1", batch(record("R1", {"metric": "packet_loss", "value": 0.02})), now=NOW)
    rep = ingest_telemetry(store, "INC-1", batch(record("R1", meas("packet_loss", 0.02, "ratio", "gauge"))),
                           now=later(1))
    assert rep.records[0].status == "accepted"


def test_unknown_incident_and_data_mode_mismatch(store):
    with pytest.raises(EvidenceError) as e:
        ingest_telemetry(store, "NOPE", batch(record()), now=NOW)
    assert e.value.codes == [IssueCode.UNKNOWN_INCIDENT]
    new_incident(store, data_mode="recorded")
    with pytest.raises(EvidenceError) as e:
        ingest_telemetry(store, "INC-1", batch(record(), data_mode="synthetic"), now=NOW)
    assert e.value.codes == [IssueCode.DATA_MODE_MISMATCH]


def test_topology_bound_incident_quarantines_unknown_subjects(store):
    topo = TopologySnapshot.model_validate(example("topology"))
    assert store.put_topology(topo, stored_at=NOW) == "created"
    assert store.put_topology(topo, stored_at=NOW) == "unchanged"
    new_incident(store, topology_snapshot_id=topo.topology_snapshot_id)
    rep = ingest_telemetry(store, "INC-1", batch(record("R1", subject={"device_id": "SW-404"})), now=NOW)
    assert rep.records[0].status == "quarantined"
    assert store.list_observations("INC-1")[0].quality.validation == "quarantined"


def test_topology_snapshot_is_immutable_and_validated(store):
    topo = example("topology")
    store.put_topology(TopologySnapshot.model_validate(topo), stored_at=NOW)
    topo["limitations"] = ["edited"]
    with pytest.raises(EvidenceError) as e:
        store.put_topology(TopologySnapshot.model_validate(topo), stored_at=NOW)
    assert e.value.codes == [IssueCode.TOPOLOGY_CONFLICT]
    broken = example("topology")
    broken["topology_snapshot_id"] = "T2"
    broken["links"][0]["to"] = "GHOST"
    with pytest.raises(EvidenceError) as e:
        store.put_topology(TopologySnapshot.model_validate(broken), stored_at=NOW)
    assert e.value.codes == [IssueCode.TOPOLOGY_INVALID]
    with pytest.raises(EvidenceError) as e:
        new_incident(store, incident_id="INC-X", topology_snapshot_id="T-missing")
    assert e.value.codes == [IssueCode.UNKNOWN_TOPOLOGY]


# --- immutability (DB-enforced) -------------------------------------------------------

@pytest.mark.parametrize("table", APPEND_ONLY_TABLES)
def test_append_only_tables_reject_update_and_delete(store, table):
    new_incident(store)
    ingest_telemetry(store, "INC-1", example("telemetry-batch"), now=NOW)
    obs = store.list_observations("INC-1")
    store.put_finding(finding("F1", [obs[0].observation_id]), stored_at=NOW)
    store.put_topology(TopologySnapshot.model_validate(example("topology")), stored_at=NOW)
    _seed_investigation_rows(store, obs)
    for stmt in (f"UPDATE {table} SET {_any_text_column(table)} = {_any_text_column(table)}", f"DELETE FROM {table}"):
        with pytest.raises(DBAPIError, match="append-only"):
            with store.engine.begin() as conn:
                conn.execute(text(stmt))


def _seed_investigation_rows(store, obs):
    from netcoop.evidence.counters import CounterRate
    store.put_derived_rates("INC-1", [CounterRate("device=SW-01", "crc_errors", "crc_errors_rate", 1.0, "count/s",
                                                  NOW, later(60), (obs[0].observation_id, obs[1].observation_id),
                                                  (obs[0].lineage_group,))])
    store.append_event("INC-1", "RUN-1", "INVESTIGATING", "coordinator", {}, NOW)
    store.record_attempt({"attempt_id": "AT-1", "task_id": "T-1", "attempt_no": 1, "incident_id": "INC-1",
                          "run_id": "RUN-1", "agent_id": "performance-agent", "task_type": "investigate",
                          "transport": "a2a", "outcome": "completed", "started_at": "2026-10-31T10:00:05.000000Z",
                          "finished_at": "2026-10-31T10:00:06.000000Z"})
    ch = example("challenge")
    ch["incident_id"] = "INC-1"
    store.put_challenge(ch, "RUN-1", NOW)
    store.put_challenge_outcome(ch["challenge_id"], "unavailable", {}, NOW)
    sid = store.put_snapshot("INC-1", {"observation_ids": [o.observation_id for o in obs]}, NOW)
    rep = example("report")
    rep.update(incident_id="INC-1", evidence_snapshot_id=sid)
    store.put_report(rep, NOW)


def _any_text_column(table: str) -> str:
    return {
        "derived_rates": "body", "workflow_events": "detail", "agent_task_attempts": "detail",
        "challenges": "body", "challenge_outcomes": "detail", "evidence_snapshots": "body", "reports": "body",
        "topology_snapshots": "body", "raw_records": "content", "observations": "body", "ingestions": "summary",
        "ingestion_issues": "message", "findings": "body", "finding_observation_refs": "observation_id",
        "audit_events": "detail",
    }[table]


# --- findings, revisions, provenance ---------------------------------------------------

@pytest.fixture
def seeded(store):
    new_incident(store)
    ingest_telemetry(store, "INC-1", example("telemetry-batch"), now=NOW)
    obs = {o.measurement.metric: o for o in store.list_observations("INC-1")}
    return store, obs


def test_finding_must_reference_stored_observations(seeded):
    store, _ = seeded
    with pytest.raises(EvidenceError) as e:
        store.put_finding(finding("F1", ["OBS-does-not-exist"]), stored_at=NOW)
    assert e.value.codes == [IssueCode.UNKNOWN_OBSERVATION_REF]


def test_finding_redelivery_is_idempotent_but_edit_is_refused(seeded):
    store, obs = seeded
    f = finding("F1", [obs["link_utilization"].observation_id])
    assert store.put_finding(f, stored_at=NOW) == "created"
    assert store.put_finding(f, stored_at=later(1)) == "unchanged"
    with pytest.raises(EvidenceError) as e:
        store.put_finding(finding("F1", [obs["link_utilization"].observation_id], claim="EDITED"), stored_at=NOW)
    assert e.value.codes == [IssueCode.FINDING_CONFLICT]


def test_revision_chain_supersedes_without_rewriting(seeded):
    store, obs = seeded
    u, lat = obs["link_utilization"].observation_id, obs["latency"].observation_id
    store.put_finding(finding("F1", [u]), stored_at=NOW)
    store.put_finding(finding("F1r2", [u, lat], supersedes="F1", created="2026-10-31T10:01:00Z"), stored_at=NOW)
    assert [f.finding_id for f in store.list_findings("INC-1")] == ["F1r2"]
    assert [f.finding_id for f in store.list_findings("INC-1", current_only=False)] == ["F1", "F1r2"]
    assert [f.finding_id for f in store.finding_history("F1")] == ["F1", "F1r2"]
    assert store.get_finding("F1").observation_refs == (u,)  # original preserved


@pytest.mark.parametrize("bad", [
    dict(supersedes="F-missing"),
    dict(supersedes="F1", agent="infrastructure-agent"),
    dict(supersedes="F1", created="2026-10-31T09:00:00Z"),
])
def test_invalid_revisions_rejected(seeded, bad):
    store, obs = seeded
    u = obs["link_utilization"].observation_id
    store.put_finding(finding("F1", [u]), stored_at=NOW)
    with pytest.raises(EvidenceError) as e:
        store.put_finding(finding("F2", [u], **bad), stored_at=NOW)
    assert e.value.codes == [IssueCode.INVALID_SUPERSEDES]


def test_revision_cannot_branch(seeded):
    store, obs = seeded
    u = obs["link_utilization"].observation_id
    store.put_finding(finding("F1", [u]), stored_at=NOW)
    store.put_finding(finding("F2", [u], supersedes="F1", created="2026-10-31T10:01:00Z"), stored_at=NOW)
    with pytest.raises(EvidenceError) as e:
        store.put_finding(finding("F3", [u], supersedes="F1", created="2026-10-31T10:02:00Z"), stored_at=NOW)
    assert e.value.codes == [IssueCode.INVALID_SUPERSEDES]


def test_two_agents_reading_same_source_record_are_not_independent(seeded):
    store, obs = seeded
    # link_utilization and crc_errors come from the SAME raw record REC-001
    store.put_finding(finding("FP", [obs["link_utilization"].observation_id], agent="performance-agent"), stored_at=NOW)
    store.put_finding(finding("FI", [obs["crc_errors"].observation_id], agent="infrastructure-agent"), stored_at=NOW)
    s = store.independent_support("INC-1", ["FP", "FI"])
    assert s["agents"] == 2 and s["distinct_observations"] == 2
    assert s["independent_lineage_groups"] == 1
    # latency comes from a different record -> a second, independent lineage
    store.put_finding(finding("FL", [obs["latency"].observation_id], agent="connectivity-agent"), stored_at=NOW)
    assert store.independent_support("INC-1", ["FP", "FI", "FL"])["independent_lineage_groups"] == 2


def test_relayed_copies_of_one_sample_count_once(store):
    new_incident(store)
    r_a = ingest_telemetry(store, "INC-1", batch(record("A1", origin_sample_id="S-1"), source_id="collector-a"), now=NOW)
    r_b = ingest_telemetry(store, "INC-1", batch(record("B9", origin_sample_id="S-1"), source_id="collector-b"), now=NOW)
    oa, ob = r_a.records[0].observation_ids[0], r_b.records[0].observation_ids[0]
    store.put_finding(finding("F1", [oa]), stored_at=NOW)
    store.put_finding(finding("F2", [ob], agent="infrastructure-agent"), stored_at=NOW)
    assert store.independent_support("INC-1", ["F1", "F2"])["independent_lineage_groups"] == 1


# --- persistence across process/engine restart -----------------------------------------

def test_evidence_survives_engine_restart(db_url):
    e1 = make_engine(db_url)
    migrate.upgrade(e1)
    s1 = SqlEvidenceStore(e1)
    new_incident(s1)
    rep = ingest_telemetry(s1, "INC-1", example("telemetry-batch"), now=NOW)
    before = s1.list_observations("INC-1")
    e1.dispose()

    e2 = make_engine(db_url)
    try:
        s2 = SqlEvidenceStore(e2)
        assert s2.schema_revision() == "0003"
        assert s2.get_incident("INC-1").data_mode == "synthetic"
        assert s2.list_observations("INC-1") == before
        assert len(before) == rep.observations_added == 3
    finally:
        e2.dispose()


def test_audit_trail_records_ingestions_and_rejections(store):
    new_incident(store)
    ingest_telemetry(store, "INC-1", batch(record()), now=NOW)
    with pytest.raises(EvidenceError):
        ingest_telemetry(store, "INC-1", {"schema_version": "9"}, now=NOW)
    with store.engine.connect() as conn:
        events = [r[0] for r in conn.execute(text(
            "SELECT event_type FROM audit_events WHERE incident_id = 'INC-1' ORDER BY event_pk"))]
    assert events == ["incident_created", "telemetry_ingested", "telemetry_batch_rejected"]
