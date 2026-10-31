"""Cross-platform local launcher (Windows and Linux; no Docker needed).

Starts each NetCoop service as its own OS process, waits for health, and shuts
everything down cleanly. Gate 1 runs one service (web). Specialist A2A agents will
be added to `services()` as separate processes in Gate 4 - never as in-process calls.

  uv run python scripts/run_local.py                 # run until Ctrl+C
  uv run python scripts/run_local.py --check         # start, smoke-test, stop (exit code)
  uv run python scripts/run_local.py --port auto     # pick a free port
"""

from __future__ import annotations

import argparse
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
        env = {**os.environ, **self.spec.env}
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

def services(host: str, port: int, database_url: str, extra_env: dict[str, str]) -> list[ServiceSpec]:
    return [
        ServiceSpec(
            name="web",
            argv=[sys.executable, "-m", "uvicorn", "netcoop.api.app:app", "--host", host, "--port", str(port),
                  "--log-level", "info"],
            health_url=f"http://{host}:{port}/health/ready",
            env={"NETCOOP_DATABASE_URL": database_url, **extra_env},
        ),
    ]


def _http(method: str, url: str, body: bytes | None = None) -> tuple[int, dict | str]:
    req = urllib.request.Request(url, data=body, method=method, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            raw = r.read()
            status = r.status
    except urllib.error.HTTPError as e:
        raw, status = e.read(), e.code
    text = raw.decode("utf-8", errors="replace")
    try:
        return status, json.loads(text)
    except ValueError:
        return status, text


def smoke(base: str) -> list[tuple[str, bool, str]]:
    """Exercise the real running service with the synthetic example files."""
    out: list[tuple[str, bool, str]] = []
    s, b = _http("GET", f"{base}/health/live")
    out.append(("live", s == 200, str(s)))
    s, b = _http("GET", f"{base}/health/ready")
    out.append(("ready", s == 200, str(s)))
    from netcoop.spec import spec_dir
    topo = (spec_dir() / "examples/topology-example.json").read_text(encoding="utf-8")
    s, b = _http("POST", f"{base}/api/incidents",
                 json.dumps({"data_mode": "synthetic", "title": "launcher smoke", "topology": json.loads(topo)}).encode())
    ok = s == 201
    out.append(("create incident", ok, str(s)))
    if not ok:
        return out
    iid = b["incident"]["incident_id"]
    tel = (spec_dir() / "examples/telemetry-batch-example.json").read_bytes()
    s, b = _http("POST", f"{base}/api/incidents/{iid}/telemetry", tel)
    out.append(("ingest example batch", s == 200 and isinstance(b, dict) and b.get("observations_added", 0) > 0,
                f"{s} observations_added={b.get('observations_added') if isinstance(b, dict) else '?'}"))
    s, b = _http("GET", f"{base}/api/incidents/{iid}/evidence")
    n = len(b.get("observations", [])) if isinstance(b, dict) else 0
    out.append(("read back evidence", s == 200 and n > 0, f"{s} observations={n}"))
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
        log_dir = data_dir / "logs"
        for spec in services(args.host, port, url, {}):
            mp = ManagedProcess(spec, log_dir / f"{spec.name}.log" if args.check else None).start()
            procs.append(mp)
            mp.wait_ready()
            print(f"[netcoop] {spec.name} ready (pid {mp.proc.pid})")
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
