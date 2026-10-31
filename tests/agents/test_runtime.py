"""Specialist runtime: receiver-side validation, domain separation, honest verify."""

from __future__ import annotations

import json
from pathlib import Path

from netcoop.agents.protocol import dumps
from netcoop.agents.runtime import handle, make_config

BASE = Path(__file__).resolve().parents[2] / "data" / "scenarios"


def task(agent="performance-agent", **kw):
    t = {"schema_version": "1.0.0", "task_id": "T1", "task_type": "investigate", "incident_id": "I", "agent_id": agent,
         "issued_at": "2026-10-31T10:00:00Z", "deadline_at": "2026-10-31T10:01:00Z", "data_mode": "synthetic",
         "case": {"analysis_time": "2026-10-31T10:00:00Z", "observations": [], "prior_findings": []}}
    t.update(kw)
    return t


def call(agent, t):
    return json.loads(handle(make_config(agent, BASE, None), t if isinstance(t, str) else dumps(t)))


def test_refuses_task_for_other_agent():
    r = call("infrastructure-agent", task("performance-agent"))
    assert r["status"] == "refused" and r["error"]["code"] == "WRONG_AGENT"


def test_refuses_malformed_and_nan():
    assert call("performance-agent", "{not json")["status"] == "refused"
    assert call("performance-agent", '{"schema_version": NaN}')["error"]["code"] == "MALFORMED"


def test_refuses_invalid_observation_payload():
    t = task()
    t["case"]["observations"] = [{"observation_id": "x"}]
    r = call("performance-agent", t)
    assert r["status"] == "refused" and r["error"]["code"] == "SCHEMA_INVALID"


def test_empty_case_reports_coverage_gap_not_health():
    r = call("performance-agent", task())
    assert r["status"] == "completed" and r["findings"] == []
    assert "latency" in r["coverage"]["no_data_for_metrics"]


def challenge(metric="crc_errors", agent="infrastructure-agent", scope="recorded_replay"):
    return {"schema_version": "1.0.0", "challenge_id": "CH1", "incident_id": "I", "target_agent_id": agent,
            "hypothesis_ids": ["H1", "H2"], "finding_refs": [], "question_type": "discriminating_measurement",
            "requested_observation": {"metric": metric, "subject": {"device_id": "DIST-2", "interface_id": "ge0/2"},
                                      "window": {"start": "2026-10-31T09:50:00Z", "end": "2026-10-31T10:00:00Z"}},
            "authorization_scope": scope, "deadline_at": "2026-10-31T10:01:00Z"}


def verify_task(ch, ref="scenario:S11-ambiguous-resolvable", agent="infrastructure-agent"):
    t = task(agent, task_type="verify", challenge=ch, archive_ref=ref)
    del t["case"]
    return t


def test_verify_returns_unmodified_recorded_records():
    r = call("infrastructure-agent", verify_task(challenge()))
    assert r["status"] == "completed"
    recs = [x for b in r["telemetry_batches"] for x in b["records"]]
    assert len(recs) == 11
    archive = json.loads((BASE / "S11-ambiguous-resolvable" / "archive.json").read_text(encoding="utf-8"))
    originals = {x["record_id"]: x for b in archive["batches"] for x in b["records"]}
    assert all(originals[x["record_id"]] == x for x in recs)


def test_verify_without_data_is_unavailable_never_fabricated():
    r = call("infrastructure-agent", verify_task(challenge(), ref="scenario:S16-ambiguous-unresolvable"))
    assert r["status"] == "unavailable" and r["telemetry_batches"] == []
    r = call("infrastructure-agent", verify_task(challenge(scope="read_only")))
    assert r["status"] == "unavailable" and r["telemetry_batches"] == []
    r = call("performance-agent", verify_task(challenge(agent="performance-agent"), agent="performance-agent"))
    assert r["status"] == "refused"  # crc_errors is outside the performance domain


def test_verify_rejects_path_traversal_ref():
    r = call("infrastructure-agent", verify_task(challenge(), ref="scenario:.."))
    assert r["status"] in ("refused", "unavailable") and r["telemetry_batches"] == []
