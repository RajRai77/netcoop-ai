"""Recorded-archive observation source used by agents to answer verification challenges.

An archive is recorded telemetry that exists but was not part of the initial
upload (for example a collector's history). The agent *queries* it for the exact
metric/subject/window requested. It returns matching recorded records unchanged
or reports that nothing matches. It never synthesizes values.

Archive file format: {"schema_version": "1.0.0", "archive_id": str, "batches": [TelemetryBatch, ...]}
References: "scenario:<id>" -> <scenarios_dir>/<id>/archive.json
            "upload:<incident_id>" -> <uploads_dir>/<incident_id>.json
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from netcoop.evidence.timeutil import TimestampError, parse_timestamp

REF = re.compile(r"^(scenario|upload):([A-Za-z0-9._-]{1,120})$")


class ArchiveError(ValueError):
    pass


class RecordedArchive:
    def __init__(self, scenarios_dir: Path | None, uploads_dir: Path | None):
        self.scenarios_dir = scenarios_dir
        self.uploads_dir = uploads_dir

    def _path(self, ref: str) -> Path | None:
        m = REF.match(ref or "")
        if not m:
            raise ArchiveError(f"invalid archive reference {ref!r}")
        kind, name = m.groups()
        base = self.scenarios_dir if kind == "scenario" else self.uploads_dir
        if base is None:
            return None
        path = (base / name / "archive.json") if kind == "scenario" else (base / f"{name}.json")
        try:
            path.resolve().relative_to(base.resolve())
        except ValueError:
            raise ArchiveError("archive reference escapes the archive directory") from None
        return path if path.is_file() else None

    def query(self, ref: str, metric: str, subject: dict, start: str, end: str) -> list[dict]:
        path = self._path(ref)
        if path is None:
            return []
        doc = json.loads(path.read_text(encoding="utf-8"))
        try:
            t0, t1 = parse_timestamp(start), parse_timestamp(end)
        except TimestampError as exc:
            raise ArchiveError(f"invalid window: {exc}") from None
        out = []
        for b in doc.get("batches", []):
            recs = []
            for r in b.get("records", []):
                if r.get("subject") != subject:
                    continue
                if not any(m.get("metric") == metric for m in r.get("measurements", [])):
                    continue
                try:
                    ts = parse_timestamp(r.get("observed_at"))
                except TimestampError:
                    continue  # malformed archive record: not returned (the coordinator would reject it anyway)
                if t0 <= ts <= t1:
                    recs.append(r)  # returned whole and unchanged: it is the recorded source record
            if recs:
                out.append({"schema_version": b.get("schema_version", "1.0.0"), "source": b["source"],
                            "records": recs})
        return out
