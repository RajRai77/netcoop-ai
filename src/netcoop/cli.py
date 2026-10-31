"""`netcoop` command line: database migrations and evidence ingestion.

Examples:
  netcoop db upgrade --database-url sqlite:///var/netcoop.db
  netcoop incident create --data-mode synthetic --topology spec/examples/topology-example.json
  netcoop ingest INC-... spec/examples/telemetry-batch-example.json
  netcoop evidence INC-...
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from pathlib import Path

EXIT_OK, EXIT_CONFIG, EXIT_REFUSED = 0, 2, 3


def _url(args) -> str:
    url = args.database_url or os.environ.get("NETCOOP_DATABASE_URL")
    if not url:
        print(
            "error: no database configured.\n"
            "  Pass --database-url, or set NETCOOP_DATABASE_URL, e.g.\n"
            "    sqlite:///var/netcoop.db                (local)\n"
            "    postgresql://user:pass@host:5432/netcoop (server)\n"
            "  `uv run python scripts/run_local.py` configures a local SQLite database for you.",
            file=sys.stderr,
        )
        raise SystemExit(EXIT_CONFIG)
    return url


def _store(args):
    from netcoop.storage import SqlEvidenceStore, make_engine
    from netcoop.storage.engine import DatabaseConfigError

    try:
        return SqlEvidenceStore(make_engine(_url(args)))
    except DatabaseConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(EXIT_CONFIG) from None


def _print(obj) -> None:
    print(json.dumps(obj, indent=2, ensure_ascii=False))


def cmd_db(args) -> int:
    from netcoop.storage import migrate
    from netcoop.storage.engine import redact

    store = _store(args)
    try:
        if args.action == "upgrade":
            migrate.upgrade(store.engine)
        elif args.action == "downgrade":
            migrate.downgrade(store.engine, args.revision)
        print(f"database: {redact(_url(args))}")
        print(f"schema revision: {migrate.current_revision(store.engine)} (head {migrate.head_revision()})")
    finally:
        store.engine.dispose()
    return EXIT_OK


def cmd_backup(args) -> int:
    """SQLite online backup (consistent copy via the sqlite3 backup API). PostgreSQL: scripts/backup.sh."""
    import sqlite3

    from sqlalchemy.engine import make_url

    from netcoop.storage.engine import normalize_url

    u = make_url(normalize_url(_url(args)))
    if u.get_backend_name() != "sqlite":
        print("error: `netcoop db backup` supports SQLite; for PostgreSQL use scripts/backup.sh (pg_dump)",
              file=sys.stderr)
        return EXIT_CONFIG
    target = Path(args.file)
    if target.exists():
        print(f"error: {target} already exists (backups are never overwritten)", file=sys.stderr)
        return EXIT_CONFIG
    target.parent.mkdir(parents=True, exist_ok=True)
    src, dst = sqlite3.connect(u.database), sqlite3.connect(target)
    with dst:
        src.backup(dst)
    src.close()
    dst.close()
    print(f"backup written: {target}")
    return EXIT_OK


def cmd_incident_create(args) -> int:
    from netcoop.evidence.models import TopologySnapshot
    from netcoop.evidence.timeutil import utcnow

    store = _store(args)
    now = utcnow()
    topo_id = None
    if args.topology:
        topo = TopologySnapshot.model_validate(json.loads(Path(args.topology).read_text(encoding="utf-8")))
        store.put_topology(topo, stored_at=now)
        topo_id = topo.topology_snapshot_id
    inc = store.create_incident(f"INC-{uuid.uuid4().hex[:16]}", args.data_mode, created_at=now,
                                topology_snapshot_id=topo_id, title=args.title)
    _print(inc.model_dump(mode="json"))
    return EXIT_OK


def cmd_ingest(args) -> int:
    from netcoop.ledger import ingest_telemetry

    from netcoop.evidence.adapters import builtin_profile, validate_profile

    profile = None
    if args.profile:
        p = Path(args.profile)
        profile = validate_profile(json.loads(p.read_text(encoding="utf-8"))) if p.suffix == ".json" and p.is_file()             else builtin_profile(args.profile)
    report = ingest_telemetry(_store(args), args.incident_id, Path(args.file).read_bytes(), profile=profile)
    _print(report.model_dump(mode="json"))
    return EXIT_OK


def cmd_evidence(args) -> int:
    store = _store(args)
    obs = store.list_observations(args.incident_id, limit=args.limit)
    _print({"observations": [o.to_json_dict() for o in obs],
            "issues": [i.model_dump(mode="json") for i in store.list_issues(args.incident_id)]})
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="netcoop", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--database-url", help="SQLAlchemy URL (default: $NETCOOP_DATABASE_URL)")
    sub = p.add_subparsers(dest="command", required=True)

    db = sub.add_parser("db", help="schema migrations")
    db_sub = db.add_subparsers(dest="action", required=True)
    db_sub.add_parser("upgrade", help="migrate to the latest schema")
    db_sub.add_parser("current", help="show schema revision")
    down = db_sub.add_parser("downgrade", help="migrate down (DESTROYS data below that revision)")
    down.add_argument("revision")
    db.set_defaults(func=cmd_db)
    bk = db_sub.add_parser("backup", help="SQLite: consistent online backup to a new file")
    bk.add_argument("file")
    bk.set_defaults(func=cmd_backup)

    inc = sub.add_parser("incident", help="incidents")
    inc_sub = inc.add_subparsers(dest="action", required=True)
    create = inc_sub.add_parser("create")
    create.add_argument("--data-mode", required=True, choices=["synthetic", "recorded", "emulated", "live", "mock"])
    create.add_argument("--title")
    create.add_argument("--topology", help="topology snapshot JSON file")
    create.set_defaults(func=cmd_incident_create)

    ing = sub.add_parser("ingest", help="ingest a TelemetryBatch JSON file")
    ing.add_argument("incident_id")
    ing.add_argument("file")
    ing.add_argument("--profile", help="built-in source profile id, or path to a profile JSON (for CSV/vendor input)")
    ing.set_defaults(func=cmd_ingest)

    ev = sub.add_parser("evidence", help="print stored observations and issues")
    ev.add_argument("incident_id")
    ev.add_argument("--limit", type=int, default=1000)
    ev.set_defaults(func=cmd_evidence)
    return p


def main(argv: list[str] | None = None) -> int:
    from netcoop.evidence.errors import EvidenceError

    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except EvidenceError as exc:
        _print({"error": {"code": str(exc.issues[0].code),
                          "issues": [i.model_dump(mode="json") for i in exc.issues]}})
        return EXIT_REFUSED


if __name__ == "__main__":
    sys.exit(main())
