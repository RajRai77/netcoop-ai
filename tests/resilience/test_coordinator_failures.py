"""Coordinator robustness: retries, invalid artifacts, spoofing, duplicates, late
evidence and crash recovery. Fake ports here test the COORDINATOR's validation;
they are not presented as agent interoperability."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from netcoop.agents.protocol import SPECIALISTS, dumps
from netcoop.api.app import create_app
from netcoop.config import Settings
from netcoop.orchestration.coordinator import Coordinator
from netcoop.orchestration.ports import A2AAgentPort, InProcessAgentPort, Reply, TransportError
from netcoop.scenarios.loader import load_into
from netcoop.spec import validator
from tests.conftest import NOW, batch, meas, record

BASE = Path(__file__).resolve().parents[2] / "data" / "scenarios"


def local(aid):
    return InProcessAgentPort(aid, BASE, None)


class Flaky(InProcessAgentPort):
    """Fails the first `fail` sends with a transient transport error."""

    def __init__(self, aid, fail=1, kind="timeout"):
        super().__init__(aid, BASE, None)
        self.fail, self.kind, self.calls = fail, kind, 0

    async def send(self, text, timeout_s):
        self.calls += 1
        if self.calls <= self.fail:
            raise TransportError(self.kind, "injected transient failure")
        return await super().send(text, timeout_s)


class Tamper(InProcessAgentPort):
    """Returns a modified result to exercise coordinator-side validation."""

    def __init__(self, aid, mode):
        super().__init__(aid, BASE, None)
        self.mode = mode

    async def send(self, text, timeout_s):
        r = await super().send(text, timeout_s)
        if self.mode == "garbage":
            return Reply("{not json", r.meta)
        res = json.loads(r.text)
        if self.mode == "spoof":
            for f in res["findings"]:
                f["agent_id"] = "infrastructure-agent"
        if self.mode == "foreign_refs":
            for f in res["findings"]:
                f["observation_refs"] = ["OBS-not-sent-to-this-agent"]
        if self.mode == "wrong_task":
            res["task_id"] = "someone-elses-task"
        return Reply(dumps(res), r.meta)


def ports(**override):
    return [override.get(a, local(a)) for a in SPECIALISTS]


def test_transient_failure_is_retried_with_same_logical_task(store):
    inc = load_into(store, BASE, "S01-congestion")["incident"]
    flaky = Flaky("performance-agent")
    r = Coordinator(store, ports(**{"performance-agent": flaky})).run(inc.incident_id)
    att = [a for a in store.list_attempts(inc.incident_id)
           if a["agent_id"] == "performance-agent" and a["task_type"] == "investigate"]
    assert [a["attempt_no"] for a in att] == [1, 2] and len({a["task_id"] for a in att}) == 1
    assert [a["outcome"] for a in att] == ["timeout", "completed"]
    assert r["status"] == "diagnosed"


def test_persistent_failure_gives_partial_coverage_not_fiction(store):
    inc = load_into(store, BASE, "S01-congestion")["incident"]
    r = Coordinator(store, ports(**{"performance-agent": Flaky("performance-agent", fail=99)})).run(inc.incident_id)
    assert "performance-agent" in r["coverage"]["agents_failed"]
    assert "performance-agent" not in r["evidence_sources"]
    assert not [f for f in store.list_findings(inc.incident_id) if f.agent_id == "performance-agent"]
    assert any("performance-agent" in x for x in r["limitations"])
    assert r["status"] != "diagnosed" or r["suspected_root_cause"] != "LINK_CONGESTION at DIST-2:ge0/1" \
        or r["confidence_category"] != "high_support"  # cannot reach full support without the utilization domain


def test_invalid_spoofed_and_foreign_artifacts_are_rejected(store):
    for mode in ("garbage", "spoof", "foreign_refs", "wrong_task"):
        inc = load_into(store, BASE, "S01-congestion")["incident"]
        r = Coordinator(store, ports(**{"performance-agent": Tamper("performance-agent", mode)})).run(inc.incident_id)
        att = [a for a in store.list_attempts(inc.incident_id)
               if a["agent_id"] == "performance-agent" and a["task_type"] == "investigate"]
        assert att[-1]["outcome"] == "invalid", (mode, att[-1])
        assert not [f for f in store.list_findings(inc.incident_id) if f.agent_id == "performance-agent"], mode
        if mode == "spoof":  # findings claiming another agent's identity were not stored under that identity
            assert all(f.observation_refs for f in store.list_findings(inc.incident_id))
        assert list(validator("report").iter_errors(r)) == []


def test_no_agents_reachable_is_operational_error(store):
    inc = load_into(store, BASE, "S01-congestion")["incident"]
    dead = [A2AAgentPort(a, "http://127.0.0.1:9/", None) for a in SPECIALISTS]
    r = Coordinator(store, dead).run(inc.incident_id)
    assert r["status"] == "operational_error" and r["suspected_root_cause"] is None
    assert list(validator("report").iter_errors(r)) == []
    assert store.workflow_state(inc.incident_id)["state"] == "OPERATIONAL_ERROR"


def test_duplicate_delivery_does_not_double_count(store):
    inc = load_into(store, BASE, "S02-interface-degradation")["incident"]
    r1 = Coordinator(store, ports()).run(inc.incident_id)
    n1 = len(store.list_findings(inc.incident_id, current_only=False))
    r2 = Coordinator(store, ports()).run(inc.incident_id)
    assert len(store.list_findings(inc.incident_id, current_only=False)) == n1
    second = [a for a in store.list_attempts(inc.incident_id) if a["run_id"] == r2["run_id"]
              and a["task_type"] == "investigate"]
    assert all(not a["detail"]["findings_stored"] for a in second)
    assert r1["hypotheses"][0]["independent_sources"] == r2["hypotheses"][0]["independent_sources"]


def test_late_evidence_creates_new_revision(store):
    inc = load_into(store, BASE, "S16-ambiguous-unresolvable")["incident"]
    r1 = Coordinator(store, ports()).run(inc.incident_id)
    assert r1["status"] == "ambiguous"
    from netcoop.ledger import ingest_telemetry
    crc = [record(f"late-{k}", meas("crc_errors", 100 + 90 * k, "count", "cumulative_counter"),
                  subject={"device_id": "DIST-2", "interface_id": "ge0/2"},
                  observed_at=f"2026-10-31T09:5{k}:00Z") for k in range(4)]
    ingest_telemetry(store, inc.incident_id, batch(*crc, source_id="late-snmp"), now=NOW)
    r2 = Coordinator(store, ports()).run(inc.incident_id)
    assert r2["revision"] == 2 and r2["evidence_snapshot_id"] != r1["evidence_snapshot_id"]
    assert store.get_report(inc.incident_id, 1)["status"] == "ambiguous"  # history preserved
    assert r2["status"] in ("diagnosed", "ambiguous")


def test_interrupted_run_is_resumed_on_startup(db_url):
    from netcoop.storage import SqlEvidenceStore, make_engine, migrate
    engine = make_engine(db_url)
    migrate.upgrade(engine)
    s = SqlEvidenceStore(engine)
    inc = load_into(s, BASE, "S03-cpu-overload")["incident"]
    s.append_event(inc.incident_id, "RUN-crashed", "NEW", "coordinator", {}, NOW)
    s.append_event(inc.incident_id, "RUN-crashed", "INVESTIGATING", "coordinator", {}, NOW)  # process died here
    engine.dispose()
    settings = Settings(database_url=db_url, allow_in_process_agents=True, scenarios_dir=str(BASE))
    with TestClient(create_app(settings)) as c:
        import time
        for _ in range(120):
            if c.get(f"/api/incidents/{inc.incident_id}/report").status_code == 200:
                break
            time.sleep(0.5)
        rep = c.get(f"/api/incidents/{inc.incident_id}/report").json()
        states = [e["state"] for e in c.get(f"/api/incidents/{inc.incident_id}/timeline").json()["events"]]
    assert "INTERRUPTED" in states and rep["status"] == "diagnosed"
    assert rep["suspected_root_cause"] == "DEVICE_CPU_OVERLOAD at ACC-2-2"
