"""Shared fixtures. `store` runs on SQLite always and on PostgreSQL when
NETCOOP_TEST_DATABASE_URL is set (Linux CI); otherwise the postgres variant is SKIPPED."""

from __future__ import annotations

import copy
import json
import os
from datetime import timedelta
from pathlib import Path

import pytest

from netcoop.evidence.timeutil import parse_timestamp
from netcoop.storage import SqlEvidenceStore, make_engine, migrate

SPEC = Path(__file__).resolve().parents[1] / "spec"
NOW = parse_timestamp("2026-10-31T10:00:05Z")


@pytest.fixture
def now():
    return NOW


def example(name: str) -> dict:
    return json.loads((SPEC / "examples" / f"{name}-example.json").read_text(encoding="utf-8"))


def batch(*records: dict, data_mode: str = "synthetic", source_id: str = "fixture-collector", **extra) -> dict:
    return {
        "schema_version": "1.0.0",
        "source": {"source_id": source_id, "data_mode": data_mode, "source_type": "file"},
        "records": [copy.deepcopy(r) for r in records],
        **extra,
    }


def record(record_id: str = "R1", *measurements: dict, subject=None, observed_at="2026-10-31T10:00:00Z", **extra) -> dict:
    return {
        "record_id": record_id,
        "subject": subject or {"device_id": "SW-01", "interface_id": "eth1"},
        "observed_at": observed_at,
        "measurements": list(measurements) or [{"metric": "link_utilization", "value": 50.0, "unit": "percent", "kind": "gauge"}],
        **extra,
    }


def meas(metric: str, value, unit, kind=None) -> dict:
    m = {"metric": metric, "value": value, "unit": unit}
    if kind is not None:
        m["kind"] = kind
    return m


def later(seconds: float):
    return NOW + timedelta(seconds=seconds)


def _postgres_url() -> str | None:
    return os.environ.get("NETCOOP_TEST_DATABASE_URL")


@pytest.fixture(params=["sqlite", pytest.param("postgres", marks=pytest.mark.postgres)])
def db_url(request, tmp_path):
    if request.param == "sqlite":
        return f"sqlite:///{(tmp_path / 'ledger.db').as_posix()}"
    url = _postgres_url()
    if not url:
        pytest.skip("NETCOOP_TEST_DATABASE_URL not set; PostgreSQL variant not executed")
    engine = make_engine(url)
    try:
        migrate.downgrade(engine, "base")
    finally:
        engine.dispose()
    return url


@pytest.fixture
def store(db_url):
    engine = make_engine(db_url)
    migrate.upgrade(engine)
    s = SqlEvidenceStore(engine)
    yield s
    engine.dispose()
