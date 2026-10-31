import os
import socket

import pytest
from fastapi.testclient import TestClient

from netcoop.api.app import create_app
from netcoop.api.health import CheckResult, check_database
from netcoop.config import Settings


def _settings(url: str | None) -> Settings:
    return Settings(database_url=url, db_connect_timeout_s=2, deployment_env="test")


def _closed_port() -> int:
    # Bind then release a port so nothing is listening on it.
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_live_does_not_need_database():
    client = TestClient(create_app(_settings(None)))
    r = client.get("/health/live")
    assert r.status_code == 200
    assert r.json()["status"] == "live"


def test_ready_is_503_when_database_not_configured():
    client = TestClient(create_app(_settings(None)))
    r = client.get("/health/ready")
    assert r.status_code == 503
    body = r.json()
    assert body["status"] == "not_ready"
    assert body["checks"]["database"]["ok"] is False


def test_ready_is_503_when_database_unreachable_and_hides_credentials():
    url = f"postgresql://netcoop:s3cret-pw@127.0.0.1:{_closed_port()}/netcoop"
    client = TestClient(create_app(_settings(url)))
    r = client.get("/health/ready")
    assert r.status_code == 503
    assert "s3cret-pw" not in r.text
    assert "unreachable" in r.json()["checks"]["database"]["detail"]


def test_ready_is_200_when_dependency_check_passes():
    app = create_app(_settings(None), db_check=lambda: CheckResult(True, "ok"))
    r = TestClient(app).get("/health/ready")
    assert r.status_code == 200
    assert r.json()["status"] == "ready"


def test_placeholder_page_says_not_implemented():
    r = TestClient(create_app(_settings(None))).get("/")
    assert r.status_code == 200
    assert "Not yet implemented" in r.text


def test_ready_is_503_when_schema_not_migrated(tmp_path):
    url = f"sqlite:///{(tmp_path / 'empty.db').as_posix()}"
    r = TestClient(create_app(_settings(url))).get("/health/ready")
    assert r.status_code == 503
    assert "run `netcoop db upgrade`" in r.json()["checks"]["database"]["detail"]


def test_ready_is_200_with_migrated_sqlite(tmp_path):
    from netcoop.storage import make_engine, migrate
    url = f"sqlite:///{(tmp_path / 'ok.db').as_posix()}"
    engine = make_engine(url)
    migrate.upgrade(engine)
    engine.dispose()
    r = TestClient(create_app(_settings(url))).get("/health/ready")
    assert r.status_code == 200, r.text


@pytest.mark.postgres
def test_check_database_against_real_postgres():
    url = os.environ.get("NETCOOP_TEST_DATABASE_URL")
    if not url:
        pytest.skip("NETCOOP_TEST_DATABASE_URL not set")
    from netcoop.storage import make_engine, migrate
    engine = make_engine(url)
    try:
        migrate.upgrade(engine)
        assert check_database(engine, migrate.head_revision()).ok
    finally:
        engine.dispose()
