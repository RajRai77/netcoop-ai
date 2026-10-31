"""Cross-platform local launcher (Windows and Linux; no Docker needed).

Starts each NetCoop service as its own OS process, waits for health, and shuts
everything down cleanly: three specialist A2A agent processes plus the web/coordinator.

  uv run python scripts/run_local.py                 # run until Ctrl+C
  uv run python scripts/run_local.py --check         # start, smoke-test, stop (exit code)
  uv run python scripts/run_local.py --port auto     # pick a free port
"""

from __future__ import annotations

import argparse
import secrets
import json
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

IS_WINDOWS = os.name == "nt"
REPO_ROOT = Path(__file__).resolve().parents[2]


class LaunchError(RuntimeError):
    pass


# -- environment checks ------------------------------------------------------------------

def preflight() -> None:
    if sys.version_info < (3, 12):
        raise LaunchError(f"Python 3.12+ required, found {sys.version.split()[0]}. Install 3.12 and run `uv sync --locked`.")
    missing = []
    for mod in ("fastapi", "uvicorn", "sqlalchemy", "alembic", "pydantic", "jsonschema"):
        try:
            __import__(mod)
        except ImportError:
            missing.append(mod)
    if missing:
        raise LaunchError(f"missing Python packages {missing}. Run `uv sync --locked` in {REPO_ROOT}.")


def port_is_free(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        if IS_WINDOWS:
            s.setsockopt(socket.SOL_SOCKET, getattr(socket, "SO_EXCLUSIVEADDRUSE", socket.SO_REUSEADDR), 1)
        try:
            s.bind((host, port))
        except OSError:
            return False
    return True


def free_port(host: str) -> int:
    with socket.socket() as s:
        s.bind((host, 0))
        return s.getsockname()[1]


def resolve_port(host: str, requested: str) -> int:
    if requested == "auto":
        return free_port(host)
    try:
        port = int(requested)
    except ValueError:
        raise LaunchError(f"--port must be a number or 'auto', got {requested!r}") from None
    if not port_is_free(host, port):
        raise LaunchError(f"port {port} on {host} is already in use. Stop the other program, "
                          f"or use --port <other> / --port auto.")
    return port


# -- process management --------------------------------------------------------------------

@dataclass
class ServiceSpec:
    name: str
    argv: list[str]
    health_url: str
    env: dict[str, str] = field(default_factory=dict)
    ready_timeout_s: float = 30.0


class ManagedProcess:
    """A child process in its own process group so it can be stopped gracefully."""

    def __init__(self, spec: ServiceSpec, log_path: Path | None = None):
        self.spec = spec
        self.log_path = log_path
        self._log = None
        self.proc: subprocess.Popen | None = None

    def start(self) -> "ManagedProcess":
        env = {**os.environ, **self.spec.env, "NETCOOP_PARENT_PID": str(os.getpid())}
        kw: dict = {"env": env, "cwd": str(REPO_ROOT)}
        if self.log_path is not None:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            self._log = open(self.log_path, "ab")
            kw.update(stdout=self._log, stderr=subprocess.STDOUT)
        if IS_WINDOWS:
            kw["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            kw["start_new_session"] = True
        self.proc = subprocess.Popen(self.spec.argv, **kw)
        return self

    def wait_ready(self) -> None:
        deadline = time.monotonic() + self.spec.ready_timeout_s
        last = "no response"
        while time.monotonic() < deadline:
            if self.proc.poll() is not None:
                raise LaunchError(f"{self.spec.name} exited early with code {self.proc.returncode}{self._log_hint()}")
            try:
                with urllib.request.urlopen(self.spec.health_url, timeout=2) as r:
                    if r.status == 200:
                        return
            except urllib.error.HTTPError as e:
                last = f"HTTP {e.code}: {e.read()[:300].decode(errors='replace')}"
            except OSError as e:
                last = type(e).__name__
            time.sleep(0.3)
        raise LaunchError(f"{self.spec.name} not ready after {self.spec.ready_timeout_s:.0f}s ({last}){self._log_hint()}")

    def _log_hint(self) -> str:
        return f"; see log {self.log_path}" if self.log_path else ""

    def stop(self, timeout_s: float = 10.0) -> int | None:
        p = self.proc
        if p is None:
            return None
        if p.poll() is None:
            try:
                if IS_WINDOWS:
                    p.send_signal(signal.CTRL_BREAK_EVENT)  # graceful for uvicorn on Windows
                else:
                    os.killpg(p.pid, signal.SIGTERM)
                p.wait(timeout=timeout_s)
            except (subprocess.TimeoutExpired, OSError):
                p.kill()
                p.wait(timeout=5)
        if self._log:
            self._log.close()
        return p.returncode


# -- services --------------------------------------------------------------------------------

AGENT_IDS = ("performance-agent", "infrastructure-agent", "connectivity-agent")


def services(host: str, port: int, database_url: str, agent_ports: dict[str, int], token: str,
             scenarios_dir: Path, uploads_dir: Path) -> list[ServiceSpec]:
    """Three independent specialist A2A servers + the web/coordinator process."""
    specs = []
    for aid, ap in agent_ports.items():
        specs.append(ServiceSpec(
            name=aid,
            argv=[sys.executable, "-m", "netcoop.agents.server", "--agent", aid, "--host", host, "--port", str(ap)],
            health_url=f"http://{host}:{ap}/health",
            env={"NETCOOP_AGENT_TOKEN": token, "NETCOOP_SCENARIOS_DIR": str(scenarios_dir),
                 "NETCOOP_ARCHIVE_UPLOADS_DIR": str(uploads_dir)},
        ))
    specs.append(ServiceSpec(
        name="web",
        argv=[sys.executable, "-m", "uvicorn", "netcoop.api.app:app", "--host", host, "--port", str(port),
              "--log-level", "info"],
        health_url=f"http://{host}:{port}/health/ready",
        env={"NETCOOP_DATABASE_URL": database_url, "NETCOOP_AGENT_TOKEN": token,
             "NETCOOP_AGENTS": json.dumps({aid: f"http://{host}:{ap}/" for aid, ap in agent_ports.items()}),
             "NETCOOP_SCENARIOS_DIR": str(scenarios_dir), "NETCOOP_ARCHIVE_UPLOADS_DIR": str(uploads_dir)},
    ))
    return specs


def _http(method: str, url: str, body: bytes | None = None) -> tuple[int, dict | str]:
    req = urllib.request.Request(url, data=body, method=method, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read()
            status = r.status
    except urllib.error.HTTPError as e:
        raw, status = e.read(), e.code
    text = raw.decode("utf-8", errors="replace")
    try:
        return status, json.loads(text)
    except ValueError:
        return status, text


def smoke(base: str, scenario: str = "S11-ambiguous-resolvable") -> list[tuple[str, bool, str]]:
    """Exercise the real running services end to end over A2A."""
    out: list[tuple[str, bool, str]] = []
    s, _ = _http("GET", f"{base}/health/live")
    out.append(("live", s == 200, str(s)))
    s, _ = _http("GET", f"{base}/health/ready")
    out.append(("ready", s == 200, str(s)))
    s, b = _http("GET", f"{base}/")
    out.append(("browser UI served", s == 200 and "NetCoop AI" in str(b), str(s)))
    s, b = _http("GET", f"{base}/api/agents")
    avail = [a["agent_id"] for a in b.get("agents", []) if a.get("status") == "available"] if isinstance(b, dict) else []
    out.append(("3 specialist agents discoverable over A2A", s == 200 and len(avail) == 3, f"{s} {avail}"))
    s, b = _http("POST", f"{base}/api/incidents", json.dumps({"scenario_id": scenario}).encode())
    out.append((f"create incident from {scenario}", s == 201, str(s)))
    if s != 201:
        return out
    iid = b["incident"]["incident_id"]
    s, _ = _http("POST", f"{base}/api/incidents/{iid}/diagnose", json.dumps({"verification": True}).encode())
    out.append(("start diagnosis", s == 202, str(s)))
    report = None
    for _ in range(240):
        s, r = _http("GET", f"{base}/api/incidents/{iid}/report")
        if s == 200:
            report = r
            break
        time.sleep(0.5)
    out.append(("report produced", report is not None, "timeout" if report is None else report["status"]))
    if report is None:
        return out
    out.append(("report transport is a2a", report.get("transport") == "a2a", str(report.get("transport"))))
    out.append(("diagnosis", report["status"] != "operational_error",
                f"{report['status']} / {report['suspected_root_cause']} / {report['confidence_category']}"))
    s, tl = _http("GET", f"{base}/api/incidents/{iid}/timeline")
    attempts = tl.get("attempts", []) if isinstance(tl, dict) else []
    a2a = [a for a in attempts if a["transport"] == "a2a" and a["detail"].get("a2a_task_id")]
    agents = sorted({a["agent_id"] for a in a2a if a["task_type"] == "investigate" and a["outcome"] == "completed"})
    out.append((">=2 specialists completed real A2A tasks", len(agents) >= 2, f"{len(a2a)} A2A exchanges; {agents}"))
    contributors = report.get("evidence_sources", [])
    out.append(("one report uses evidence from >=2 agents", len(contributors) >= 2, str(contributors)))
    return out


# -- entry point -----------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="run_local", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", default="8000", help="port number or 'auto'")
    p.add_argument("--data-dir", default=str(REPO_ROOT / "var"), help="local data directory (SQLite DB, logs)")
    p.add_argument("--database-url", default=None,
                   help="override database (default: $NETCOOP_DATABASE_URL or SQLite in --data-dir)")
    p.add_argument("--check", action="store_true", help="start, run a smoke test, stop; exit 0 only if all pass")
    p.add_argument("--scenarios-dir", default=None, help="packaged scenarios (default: data/scenarios)")
    p.add_argument("--cors-origin", action="append", default=[],
                   help="allow a separate frontend origin, e.g. http://localhost:5173 (repeatable)")
    args = p.parse_args(argv)

    procs: list[ManagedProcess] = []
    try:
        preflight()
        from netcoop.storage import make_engine, migrate
        from netcoop.storage.engine import DatabaseConfigError, redact

        data_dir = Path(args.data_dir).resolve()
        data_dir.mkdir(parents=True, exist_ok=True)
        url = args.database_url or os.environ.get("NETCOOP_DATABASE_URL") or \
            f"sqlite:///{(data_dir / 'netcoop.db').as_posix()}"
        try:
            engine = make_engine(url)
            migrate.upgrade(engine)
            rev = migrate.current_revision(engine)
            engine.dispose()
        except DatabaseConfigError as exc:
            raise LaunchError(str(exc)) from None
        except Exception as exc:
            raise LaunchError(f"database {redact(url)} not usable: {type(exc).__name__}: {exc}") from None
        print(f"[netcoop] database {redact(url)} at schema revision {rev}")

        port = resolve_port(args.host, args.port)
        agent_ports: dict[str, int] = {}
        for aid in AGENT_IDS:
            ap = free_port(args.host)
            while ap == port or ap in agent_ports.values():
                ap = free_port(args.host)
            agent_ports[aid] = ap
        token = secrets.token_hex(24)  # per-run secret shared only with child processes
        scenarios_dir = Path(args.scenarios_dir).resolve() if args.scenarios_dir else REPO_ROOT / "data" / "scenarios"
        uploads_dir = data_dir / "archives"
        uploads_dir.mkdir(parents=True, exist_ok=True)
        log_dir = data_dir / "logs"
        specs = services(args.host, port, url, agent_ports, token, scenarios_dir, uploads_dir)
        if args.cors_origin:
            specs[-1].env["NETCOOP_CORS_ORIGINS"] = ",".join(args.cors_origin)
        for spec in specs:
            mp = ManagedProcess(spec, log_dir / f"{spec.name}.log" if args.check else None).start()
            procs.append(mp)
            mp.wait_ready()
            print(f"[netcoop] {spec.name} ready (pid {mp.proc.pid}, {spec.health_url.rsplit('/', 1)[0]})")
        base = f"http://{args.host}:{port}"

        if args.check:
            results = smoke(base)
            for name, ok, detail in results:
                print(f"[netcoop] {'PASS' if ok else 'FAIL'} {name} ({detail})")
            return 0 if results and all(ok for _, ok, _ in results) else 1

        print(f"[netcoop] open {base}/  (API docs {base}/docs). Press Ctrl+C to stop.")
        if not IS_WINDOWS:
            signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
        while all(mp.proc.poll() is None for mp in procs):
            time.sleep(0.5)
        dead = [mp.spec.name for mp in procs if mp.proc.poll() is not None]
        print(f"[netcoop] service(s) exited unexpectedly: {dead}", file=sys.stderr)
        return 1
    except LaunchError as exc:
        print(f"[netcoop] error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("[netcoop] stopping...")
        return 0
    finally:
        for mp in reversed(procs):
            code = mp.stop()
            print(f"[netcoop] {mp.spec.name} stopped (exit {code})")
