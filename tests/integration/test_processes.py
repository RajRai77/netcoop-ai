"""Real OS-process tests: launcher, API restart persistence, A2A probe, CLI.

These start actual subprocesses on localhost (no mocks)."""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys

import pytest

from netcoop.launcher import ManagedProcess, ServiceSpec, _http, free_port, port_is_free
from tests.conftest import example

PY = sys.executable


def web(tmp_path, port, url, tag):
    spec = ServiceSpec(
        name="web", health_url=f"http://127.0.0.1:{port}/health/ready",
        argv=[PY, "-m", "uvicorn", "netcoop.api.app:app", "--host", "127.0.0.1", "--port", str(port)],
        env={"NETCOOP_DATABASE_URL": url},
    )
    return ManagedProcess(spec, tmp_path / f"web-{tag}.log")


def test_launcher_check_mode_end_to_end(tmp_path):
    r = subprocess.run([PY, "scripts/run_local.py", "--check", "--port", "auto", "--data-dir", str(tmp_path)],
                       capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stdout + r.stderr
    assert r.stdout.count("PASS") == 11 and "FAIL" not in r.stdout, r.stdout
    assert "report transport is a2a (a2a)" in r.stdout
    assert (tmp_path / "netcoop.db").is_file()


def test_launcher_reports_busy_port(tmp_path):
    import socket
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        s.listen()
        busy = s.getsockname()[1]
        assert not port_is_free("127.0.0.1", busy)
        r = subprocess.run([PY, "scripts/run_local.py", "--check", "--port", str(busy), "--data-dir", str(tmp_path)],
                           capture_output=True, text=True, timeout=60)
    assert r.returncode == 2
    assert "already in use" in r.stderr


def test_launcher_rejects_unsupported_database(tmp_path):
    r = subprocess.run([PY, "scripts/run_local.py", "--check", "--database-url", "mysql://x/y",
                        "--data-dir", str(tmp_path)], capture_output=True, text=True, timeout=60)
    assert r.returncode == 2 and "unsupported database backend" in r.stderr


def test_evidence_survives_api_process_restart(tmp_path):
    url = f"sqlite:///{(tmp_path / 'restart.db').as_posix()}"
    assert subprocess.run([PY, "-m", "netcoop.cli", "--database-url", url, "db", "upgrade"],
                          capture_output=True, timeout=60).returncode == 0
    port = free_port("127.0.0.1")
    base = f"http://127.0.0.1:{port}"

    first = web(tmp_path, port, url, "1").start()
    try:
        first.wait_ready()
        s, b = _http("POST", f"{base}/api/incidents", json.dumps({"data_mode": "synthetic"}).encode())
        assert s == 201
        iid = b["incident"]["incident_id"]
        s, rep = _http("POST", f"{base}/api/incidents/{iid}/telemetry", json.dumps(example("telemetry-batch")).encode())
        assert s == 200 and rep["observations_added"] == 3
        s, before = _http("GET", f"{base}/api/incidents/{iid}/evidence")
    finally:
        first.stop()
    assert first.proc.poll() is not None

    second = web(tmp_path, port, url, "2").start()
    try:
        second.wait_ready()
        s, after = _http("GET", f"{base}/api/incidents/{iid}/evidence")
        assert s == 200
        assert after["observations"] == before["observations"]
        assert len(after["observations"]) == 3
    finally:
        second.stop()


def test_a2a_sdk_probe_across_two_processes(tmp_path):
    """Compatibility probe only: real A2A JSON-RPC between two OS processes.

    This is NOT evidence of NetCoop agent interoperability (Gate 4)."""
    from netcoop.interop.a2a_probe import call

    port = free_port("127.0.0.1")
    spec = ServiceSpec(name="a2a-probe", health_url=f"http://127.0.0.1:{port}/.well-known/agent-card.json",
                       argv=[PY, "-m", "netcoop.interop.a2a_probe", "serve", "--port", str(port)])
    server = ManagedProcess(spec, tmp_path / "a2a.log").start()
    try:
        server.wait_ready()
        s, card = _http("GET", spec.health_url)
        assert s == 200 and card["supportedInterfaces"][0]["protocolBinding"] == "JSONRPC"
        doc = {"counter": 18446744073709551615, "ratio": 0.02, "flag": True}
        receipt = asyncio.run(call(f"http://127.0.0.1:{port}", doc))
        assert receipt["sha256"] == receipt["_sent_sha256"]  # byte-exact transfer as text part
        assert receipt["field_types"] == {"counter": "int", "flag": "bool", "ratio": "float"}
    finally:
        server.stop()


def test_cli_ingest_and_typed_refusal(tmp_path):
    url = f"sqlite:///{(tmp_path / 'cli.db').as_posix()}"

    def cli(*args):
        return subprocess.run([PY, "-m", "netcoop.cli", "--database-url", url, *args],
                              capture_output=True, text=True, timeout=60)

    assert cli("db", "upgrade").returncode == 0
    r = cli("incident", "create", "--data-mode", "synthetic", "--topology", "spec/examples/topology-example.json")
    assert r.returncode == 0, r.stderr
    iid = json.loads(r.stdout)["incident_id"]
    r = cli("ingest", iid, "spec/examples/telemetry-batch-example.json")
    assert r.returncode == 0 and json.loads(r.stdout)["observations_added"] == 3
    bad = tmp_path / "bad.json"
    bad.write_text('{"schema_version": "2.0.0"}', encoding="utf-8")
    r = cli("ingest", iid, str(bad))
    assert r.returncode == 3 and json.loads(r.stdout)["error"]["code"] == "UNSUPPORTED_SCHEMA_VERSION"


def test_cli_without_database_gives_helpful_error():
    import os
    env = {k: v for k, v in os.environ.items() if k != "NETCOOP_DATABASE_URL"}
    r = subprocess.run([PY, "-m", "netcoop.cli", "db", "current"], capture_output=True, text=True, env=env, timeout=60)
    assert r.returncode == 2 and "no database configured" in r.stderr


def test_children_exit_when_launcher_is_killed(tmp_path):
    """Hard-kill the launcher; its agent/web children must not linger as orphans."""
    import time
    import urllib.request

    port = free_port("127.0.0.1")
    launcher = subprocess.Popen([PY, "scripts/run_local.py", "--port", str(port), "--data-dir", str(tmp_path)],
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        deadline = time.time() + 90
        up = False
        while time.time() < deadline:
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{port}/health/ready", timeout=2)
                up = True
                break
            except OSError:
                time.sleep(0.5)
        assert up, "stack did not start"
    finally:
        launcher.kill()  # no graceful shutdown: TerminateProcess / SIGKILL
        launcher.wait(timeout=10)
    deadline = time.time() + 20
    while time.time() < deadline and not port_is_free("127.0.0.1", port):
        time.sleep(0.5)
    assert port_is_free("127.0.0.1", port), "web child kept running after the launcher was killed"
