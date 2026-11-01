"""Create an incident from a packaged scenario (manifest + topology + telemetry).

Ground truth is NEVER read here; it is for the evaluator only.
"""

from __future__ import annotations

import json
import re
import uuid
from pathlib import Path

from netcoop.evidence.adapters import builtin_profile
from netcoop.evidence.errors import EvidenceError, IssueCode
from netcoop.evidence.models import TopologySnapshot
from netcoop.evidence.timeutil import parse_timestamp, utcnow
from netcoop.ledger import ingest_telemetry
from netcoop.spec import validator

SCENARIO_ID = re.compile(r"^[A-Za-z0-9._-]{1,120}$")


def scenario_dir(base: Path, scenario_id: str) -> Path:
    if not SCENARIO_ID.match(scenario_id or ""):
        raise EvidenceError.single(IssueCode.SCHEMA_INVALID, f"invalid scenario id {scenario_id!r}")
    d = base / scenario_id
    if not (d / "manifest.json").is_file():
        raise EvidenceError.single(IssueCode.SCHEMA_INVALID, f"scenario {scenario_id!r} not found")
    return d


def list_scenarios(base: Path) -> list[dict]:
    out = []
    if not base.is_dir():
        return out
    for d in sorted(p for p in base.iterdir() if (p / "manifest.json").is_file()):
        m = json.loads((d / "manifest.json").read_text(encoding="utf-8"))
        out.append({k: m.get(k) for k in ("scenario_id", "title", "data_mode", "tags", "split", "telemetry_profile",
                                          "reference_time", "limitations", "source_description")}
                   | {"has_archive": bool(m.get("archive_file"))})
    return out


def load_into(store, base: Path, scenario_id: str, *, incident_id: str | None = None, now=None,
              owner_id: str | None = None) -> dict:
    d = scenario_dir(base, scenario_id)
    m = json.loads((d / "manifest.json").read_text(encoding="utf-8"))
    errs = [e.message for e in validator("scenario-manifest").iter_errors(m)]
    if errs:
        raise EvidenceError.single(IssueCode.SCHEMA_INVALID, f"manifest invalid: {errs[0]}")
    now = now or utcnow()
    topo = TopologySnapshot.model_validate(json.loads((d / m["topology_file"]).read_text(encoding="utf-8")))
    store.put_topology(topo, stored_at=now)
    inc = store.create_incident(
        incident_id or f"INC-{uuid.uuid4().hex[:16]}", m["data_mode"], created_at=now,
        topology_snapshot_id=topo.topology_snapshot_id, title=m.get("title"),
        archive_ref=f"scenario:{scenario_id}" if m.get("archive_file") else None, scenario_id=scenario_id,
        reference_time=parse_timestamp(m["reference_time"]) if m.get("reference_time") else None, owner_id=owner_id)
    reports = []
    raw = (d / m["telemetry_file"]).read_bytes()
    if m.get("telemetry_profile"):
        reports.append(ingest_telemetry(store, inc.incident_id, raw, profile=builtin_profile(m["telemetry_profile"]),
                                        now=now))
    else:
        for b in json.loads(raw)["batches"]:
            reports.append(ingest_telemetry(store, inc.incident_id, b, now=now))
    return {"incident": inc, "ingestions": reports, "manifest": m}
