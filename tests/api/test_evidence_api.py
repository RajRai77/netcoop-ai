"""HTTP API for incidents and evidence (Gate 1 scope; no diagnosis)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from netcoop.api.app import create_app
from netcoop.config import Settings
from netcoop.storage import make_engine, migrate
from tests.conftest import batch, example, meas, record


@pytest.fixture
def client_factory(tmp_path):
    url = f"sqlite:///{(tmp_path / 'api.db').as_posix()}"
    engine = make_engine(url)
    migrate.upgrade(engine)
    engine.dispose()

    def make(**kw):
        return TestClient(create_app(Settings(database_url=url, **kw)))
    return make


def test_create_ingest_and_read_back(client_factory):
    c = client_factory()
    r = c.post("/api/incidents", json={"data_mode": "synthetic", "topology": example("topology")})
    assert r.status_code == 201, r.text
    inc = r.json()["incident"]
    assert inc["topology_snapshot_id"] == "TOPO-DEMO-001"
    iid = inc["incident_id"]

    rep = c.post(f"/api/incidents/{iid}/telemetry", json=example("telemetry-batch"))
    assert rep.status_code == 200, rep.text
    assert rep.json()["observations_added"] == 3

    ev = c.get(f"/api/incidents/{iid}/evidence").json()
    assert len(ev["observations"]) == 3
    raw_ref = ev["observations"][0]["raw_record_ref"]
    raw = c.get(f"/api/raw-records/{raw_ref}")
    assert raw.status_code == 200 and raw.json()["raw_id"] == raw_ref
    assert c.get(f"/api/incidents/{iid}").json()["evidence_counts"]["observations"] == 3


def test_typed_errors(client_factory):
    c = client_factory(max_upload_bytes=2000)
    iid = c.post("/api/incidents", json={"data_mode": "synthetic"}).json()["incident"]["incident_id"]
    r = c.post(f"/api/incidents/{iid}/telemetry", content=b"{oops")
    assert r.status_code == 422 and r.json()["error"]["code"] == "MALFORMED_JSON"
    r = c.post(f"/api/incidents/{iid}/telemetry", content=b"x" * 5000)
    assert r.status_code == 413 and r.json()["error"]["code"] == "PAYLOAD_TOO_LARGE"
    r = c.post("/api/incidents/INC-nope/telemetry", json=batch(record()))
    assert r.status_code == 404 and r.json()["error"]["code"] == "UNKNOWN_INCIDENT"
    r = c.post(f"/api/incidents/{iid}/telemetry", json=batch(record(), data_mode="recorded"))
    assert r.status_code == 422 and r.json()["error"]["code"] == "DATA_MODE_MISMATCH"
    bad_topo = example("topology"); bad_topo["links"][0]["to"] = "GHOST"
    r = c.post("/api/incidents", json={"data_mode": "synthetic", "topology": bad_topo})
    assert r.status_code == 422 and r.json()["error"]["code"] == "TOPOLOGY_INVALID"


def test_partial_batch_reports_per_record_status(client_factory):
    c = client_factory()
    iid = c.post("/api/incidents", json={"data_mode": "synthetic"}).json()["incident"]["incident_id"]
    body = batch(record("ok"), record("bad", {"metric": "packet_loss", "value": 0.02}))
    rep = c.post(f"/api/incidents/{iid}/telemetry", json=body).json()
    assert [r["status"] for r in rep["records"]] == ["accepted", "rejected"]
    assert "MISSING_UNIT" in [i["code"] for i in rep["issues"]]


def test_bearer_token_enforced_when_configured(client_factory):
    c = client_factory(api_token="t0ken-for-tests")
    assert c.post("/api/incidents", json={"data_mode": "synthetic"}).status_code == 401
    assert c.post("/api/incidents", json={"data_mode": "synthetic"},
                  headers={"Authorization": "Bearer wrong"}).status_code == 401
    ok = c.post("/api/incidents", json={"data_mode": "synthetic"},
                headers={"Authorization": "Bearer t0ken-for-tests"})
    assert ok.status_code == 201
    assert c.get("/health/live").status_code == 200  # health stays open


def test_api_without_database_is_503():
    c = TestClient(create_app(Settings(database_url=None)))
    assert c.post("/api/incidents", json={"data_mode": "synthetic"}).status_code == 503


def test_unknown_data_mode_rejected(client_factory):
    r = client_factory().post("/api/incidents", json={"data_mode": "production"})
    assert r.status_code == 422


def test_oversized_json_body_is_refused_before_parsing(client_factory):
    c = client_factory(max_upload_bytes=1000)
    big = {"data_mode": "synthetic", "title": "x", "topology": {"pad": "y" * 5000}}
    r = c.post("/api/incidents", json=big)
    assert r.status_code == 413 and r.json()["error"]["code"] == "PAYLOAD_TOO_LARGE"
