"""Real A2A interoperability: three specialist servers as separate OS processes.

Nothing here is mocked: the coordinator reaches the agents over HTTP JSON-RPC
(a2a-sdk 1.3.0) with bearer tokens, exactly as in the local launcher.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest

from netcoop.agents.protocol import SPECIALISTS, dumps
from netcoop.launcher import ManagedProcess, ServiceSpec, free_port
from netcoop.orchestration.coordinator import Coordinator
from netcoop.orchestration.ports import A2AAgentPort, InProcessAgentPort, TransportError
from netcoop.scenarios.loader import load_into

BASE = Path(__file__).resolve().parents[2] / "data" / "scenarios"
TOKEN = "integration-test-token"


@pytest.fixture(scope="module")
def agents(tmp_path_factory):
    uploads = tmp_path_factory.mktemp("uploads")
    logs = tmp_path_factory.mktemp("logs")
    procs, urls = [], {}
    for aid in SPECIALISTS:
        port = free_port("127.0.0.1")
        spec = ServiceSpec(name=aid, health_url=f"http://127.0.0.1:{port}/health",
                           argv=[sys.executable, "-m", "netcoop.agents.server", "--agent", aid, "--port", str(port)],
                           env={"NETCOOP_AGENT_TOKEN": TOKEN, "NETCOOP_SCENARIOS_DIR": str(BASE),
                                "NETCOOP_ARCHIVE_UPLOADS_DIR": str(uploads)})
        procs.append(ManagedProcess(spec, logs / f"{aid}.log").start())
        urls[aid] = f"http://127.0.0.1:{port}/"
    try:
        for p in procs:
            p.wait_ready()
        yield {"urls": urls, "uploads": uploads, "procs": {p.spec.name: p for p in procs}}
    finally:
        for p in procs:
            p.stop()


def a2a_ports(agents, token=TOKEN):
    return [A2AAgentPort(aid, url, token) for aid, url in agents["urls"].items()]


@pytest.mark.parametrize("sid", ["S04-device-down", "S10-compound", "S11-ambiguous-resolvable", "S15-unknown-fault"])
def test_a2a_diagnosis_equals_in_process_semantics(store, agents, sid):
    inc_a = load_into(store, BASE, sid)["incident"]
    r_a2a = Coordinator(store, a2a_ports(agents)).run(inc_a.incident_id)
    inc_l = load_into(store, BASE, sid)["incident"]
    r_loc = Coordinator(store, [InProcessAgentPort(a, BASE, None) for a in SPECIALISTS]).run(inc_l.incident_id)
    assert r_a2a["transport"] == "a2a" and r_loc["transport"] == "in-process"
    for k in ("status", "suspected_root_cause", "confidence_category", "affected_devices"):
        assert r_a2a[k] == r_loc[k], k
    attempts = store.list_attempts(inc_a.incident_id)
    inv = [a for a in attempts if a["task_type"] == "investigate"]
    assert inv and all(a["transport"] == "a2a" and a["detail"]["a2a_task_id"] for a in inv)
    assert {a["agent_id"] for a in inv if a["outcome"] == "completed"} == set(SPECIALISTS)
    # each stored finding was produced by the agent named on it, over A2A
    by_agent: dict[str, set] = {}
    for a in inv:
        by_agent.setdefault(a["agent_id"], set()).update(a["detail"].get("findings_stored", []))
    for f in store.list_findings(inc_a.incident_id, current_only=False):
        assert f.finding_id in by_agent[f.agent_id]


def test_exact_numbers_survive_a2a_round_trip(agents):
    """NDEP JSON travels as an A2A text part: big counters, decimals and timestamps are exact."""
    rec = {"record_id": "R-big", "subject": {"device_id": "SW-1", "interface_id": "eth0"},
           "observed_at": "2026-10-31T15:29:59.123456+05:30",
           "measurements": [{"metric": "crc_errors", "value": 18446744073709551615, "unit": "count",
                             "kind": "cumulative_counter"},
                            {"metric": "link_utilization", "value": 0.1, "unit": "percent", "kind": "gauge"},
                            {"metric": "latency", "value": 1e-300, "unit": "ms", "kind": "gauge"}]}
    archive = {"schema_version": "1.0.0", "archive_id": "A", "batches": [
        {"schema_version": "1.0.0", "source": {"source_id": "snmp", "data_mode": "synthetic", "source_type": "snmp"},
         "records": [rec]}]}
    (agents["uploads"] / "INC-EXACT.json").write_text(json.dumps(archive), encoding="utf-8")
    task = {"schema_version": "1.0.0", "task_id": "T-exact", "task_type": "verify", "incident_id": "INC-EXACT",
            "agent_id": "infrastructure-agent", "issued_at": "2026-10-31T10:00:00Z",
            "deadline_at": "2026-10-31T10:01:00Z", "data_mode": "synthetic", "archive_ref": "upload:INC-EXACT",
            "challenge": {"schema_version": "1.0.0", "challenge_id": "CH-exact", "incident_id": "INC-EXACT",
                          "target_agent_id": "infrastructure-agent", "hypothesis_ids": ["H1", "H2"], "finding_refs": [],
                          "question_type": "discriminating_measurement",
                          "requested_observation": {"metric": "crc_errors", "subject": rec["subject"],
                                                    "window": {"start": "2026-10-31T09:00:00Z",
                                                               "end": "2026-10-31T11:00:00Z"}},
                          "authorization_scope": "recorded_replay", "deadline_at": "2026-10-31T10:01:00Z"}}
    port = A2AAgentPort("infrastructure-agent", agents["urls"]["infrastructure-agent"], TOKEN)
    reply = asyncio.run(port.send(dumps(task), 15))
    res = json.loads(reply.text)
    assert res["status"] == "completed", res
    got = res["telemetry_batches"][0]["records"][0]
    assert got == rec
    assert type(got["measurements"][0]["value"]) is int and got["measurements"][0]["value"] == 2**64 - 1
    assert got["measurements"][1]["value"] == 0.1 and got["observed_at"] == rec["observed_at"]
    assert reply.meta["a2a_task_id"] and reply.meta["a2a_message_id"]


def test_wrong_token_is_rejected_and_reported(store, agents):
    inc = load_into(store, BASE, "S01-congestion")["incident"]
    r = Coordinator(store, a2a_ports(agents, token="wrong")).run(inc.incident_id)
    assert r["status"] == "operational_error"  # no specialist accepted a task
    outcomes = {a["outcome"] for a in store.list_attempts(inc.incident_id) if a["task_type"] == "investigate"}
    assert outcomes == {"unauthorized"}
    assert store.list_findings(inc.incident_id) == []


def test_agent_card_impersonation_is_refused(agents):
    # configured as infrastructure-agent but the URL serves the performance agent's card
    port = A2AAgentPort("infrastructure-agent", agents["urls"]["performance-agent"], TOKEN)
    with pytest.raises(TransportError) as e:
        asyncio.run(port.discover(5))
    assert e.value.kind == "protocol"


def test_agent_crash_mid_incident_is_reported_honestly(store, agents, tmp_path):
    """Kill one specialist process; the diagnosis continues with partial coverage and says so."""
    proc = agents["procs"]["connectivity-agent"]
    inc = load_into(store, BASE, "S04-device-down")["incident"]
    proc.stop()
    try:
        r = Coordinator(store, a2a_ports(agents)).run(inc.incident_id)
    finally:
        proc.start()
        proc.wait_ready()
    assert "connectivity-agent" in r["coverage"]["agents_failed"]
    assert any("connectivity-agent unavailable" in x for x in r["limitations"])
    assert "connectivity-agent" not in r["evidence_sources"]
    assert r["status"] != "operational_error"  # the other two specialists still contributed


def test_card_protocol_version_is_checked(agents, monkeypatch):
    from a2a.types import AgentCard

    port = A2AAgentPort("performance-agent", agents["urls"]["performance-agent"], TOKEN)
    real = asyncio.run(port.discover(5)).card
    assert {"protocolBinding": "JSONRPC", "protocolVersion": "1.0"}.items() <= real["supportedInterfaces"][0].items()
    import a2a.client as client_mod

    class OldCardResolver:
        def __init__(self, *a, **k):
            pass

        async def get_agent_card(self):
            from netcoop.agents.server import build_card
            card = build_card("performance-agent", agents["urls"]["performance-agent"])
            card.supported_interfaces[0].protocol_version = "0.3"
            return card

    monkeypatch.setattr(client_mod, "A2ACardResolver", OldCardResolver)
    with pytest.raises(TransportError) as e:
        asyncio.run(A2AAgentPort("performance-agent", agents["urls"]["performance-agent"], TOKEN).discover(5))
    assert e.value.kind == "protocol" and "protocol 1.0" in str(e.value)
    assert isinstance(real, dict) and AgentCard  # real card is unaffected
