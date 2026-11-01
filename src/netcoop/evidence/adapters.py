"""Source-profile adapters: vendor CSV / JSON records -> NDEP TelemetryBatch.

The profile declares every mapping (field names, units, kinds, timezone). The
adapter never infers meaning from column names or values. Output keeps the
original vendor row as the raw record content, so provenance shows exactly what
was received.
"""

from __future__ import annotations

import csv
import io
import json
import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from netcoop.evidence.errors import EvidenceError, Issue, IssueCode, Severity
from netcoop.evidence.ids import canonical_json, sha256_hex
from netcoop.evidence.registry import MetricRegistry, default_registry
from netcoop.spec import spec_dir, validator

_INT = re.compile(r"^[+-]?\d+$")
_NUM = re.compile(r"^[+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?$")
_NONFINITE = {"nan": float("nan"), "inf": float("inf"), "+inf": float("inf"), "-inf": float("-inf"),
              "infinity": float("inf"), "-infinity": float("-inf")}
_HAS_OFFSET = re.compile(r"(Z|[+-]\d{2}:?\d{2})$")
PROFILE_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")


@dataclass
class AdaptedBatch:
    batch: dict
    originals: list[dict]
    source_schema: str
    issues: list[Issue]


def validate_profile(profile: dict) -> dict:
    errors = [f"{'/'.join(map(str, e.absolute_path)) or '<root>'}: {e.message}"
              for e in validator("source-profile").iter_errors(profile)]
    if errors:
        raise EvidenceError([Issue(code=IssueCode.PROFILE_INVALID, severity=Severity.REJECT, message=m)
                             for m in errors])
    reg = default_registry()
    for col, m in profile["measurements"].items():
        if m["metric"] not in reg.metrics:
            raise EvidenceError.single(IssueCode.PROFILE_INVALID,
                                       f"column {col!r} maps to unknown metric {m['metric']!r}")
    return profile


@lru_cache(maxsize=None)
def builtin_profile(profile_id: str) -> dict:
    if not PROFILE_ID.match(profile_id or ""):
        raise EvidenceError.single(IssueCode.UNKNOWN_PROFILE, f"invalid profile id {profile_id!r}")
    path = spec_dir() / "profiles" / f"{profile_id}.json"
    if not path.is_file():
        raise EvidenceError.single(IssueCode.UNKNOWN_PROFILE, f"no built-in source profile {profile_id!r}")
    return validate_profile(json.loads(path.read_text(encoding="utf-8")))


def list_builtin_profiles() -> list[str]:
    d = spec_dir() / "profiles"
    return sorted(p.stem for p in d.glob("*.json")) if d.is_dir() else []


def _flatten(row: dict, sep: str, prefix: str = "") -> dict:
    """Nested JSON object -> {"a.b": value}. Only objects are descended; lists and scalars are kept as values."""
    out: dict[str, Any] = {}
    for k, v in row.items():
        key = f"{prefix}{sep}{k}" if prefix else str(k)
        if isinstance(v, dict) and v:
            out.update(_flatten(v, sep, key))
        else:
            out[key] = v
    return out


def _csv_value(raw: str, value_type: str) -> Any:
    """CSV cells are text; convert only by the target metric's declared type."""
    text = raw.strip()
    if text == "":
        return None  # missing; normalizer reports MISSING_VALUE (never zero)
    if value_type == "boolean":
        return {"true": True, "false": False}.get(text, text)  # anything else -> TYPE_MISMATCH later
    if value_type == "enum":
        return text
    if text.lower() in _NONFINITE:
        return _NONFINITE[text.lower()]
    if _INT.match(text):
        return int(text)
    if _NUM.match(text):
        return float(text)
    return text  # non-numeric text -> TYPE_MISMATCH later (no coercion)


def adapt(payload: bytes | str, profile: dict, registry: MetricRegistry | None = None,
          max_rows: int = 10_000) -> AdaptedBatch:
    registry = registry or default_registry()
    profile = validate_profile(profile)
    text = payload.decode("utf-8-sig") if isinstance(payload, bytes) else payload
    issues: list[Issue] = []

    if profile["format"] == "csv":
        try:
            reader = csv.DictReader(io.StringIO(text), strict=True)
            rows = list(reader)
        except csv.Error as exc:
            raise EvidenceError.single(IssueCode.CSV_MALFORMED, f"CSV parse error: {exc}") from None
        if reader.fieldnames is None:
            raise EvidenceError.single(IssueCode.CSV_MALFORMED, "CSV has no header row")
        if len(set(reader.fieldnames)) != len(reader.fieldnames):
            raise EvidenceError.single(IssueCode.CSV_MALFORMED, "CSV header has duplicate column names")
        for i, r in enumerate(rows):
            if None in r:  # more cells than header columns
                raise EvidenceError.single(IssueCode.CSV_MALFORMED, f"row {i + 2} has more cells than the header")
        typed = False
        originals = rows
    else:
        try:
            rows = json.loads(text)
        except ValueError as exc:
            raise EvidenceError.single(IssueCode.MALFORMED_JSON, f"payload is not valid JSON: {exc}") from None
        if not isinstance(rows, list) or not all(isinstance(r, dict) for r in rows):
            raise EvidenceError.single(IssueCode.SCHEMA_INVALID, "json-records payload must be an array of objects")
        typed = True
    originals = rows  # raw records keep the payload exactly as received
    sep = profile.get("field_path_separator")
    if sep and profile["format"] == "json-records":
        rows = [_flatten(r, sep) for r in rows]
    if not rows:
        raise EvidenceError.single(IssueCode.SCHEMA_INVALID, "no data rows")
    if len(rows) > max_rows:
        raise EvidenceError.single(IssueCode.TOO_MANY_RECORDS, f"{len(rows)} rows; limit {max_rows}")

    ts_field = profile["timestamp"]["field"]
    tz = profile["timestamp"].get("timezone")
    rid_spec = profile["record_id"]
    subj_map = profile["subject"]
    meas_map = profile["measurements"]
    origin_field = profile.get("origin_sample_field")
    known = {ts_field, *subj_map.values(), *meas_map, *profile.get("ignore_fields", [])}
    if "field" in rid_spec:
        known.add(rid_spec["field"])
    if origin_field:
        known.add(origin_field)

    unmapped = sorted({k for r in rows for k in r} - known)
    if unmapped:
        issues.append(Issue(code=IssueCode.UNMAPPED_FIELD, severity=Severity.WARNING,
                            message=f"fields not declared by profile {profile['profile_id']} were ignored: {unmapped}"))
    tz_applied = 0
    records = []
    for i, row in enumerate(rows):
        rec: dict[str, Any] = {}
        if "field" in rid_spec:
            v = row.get(rid_spec["field"])
            rec["record_id"] = str(v) if v not in (None, "") else None
        else:
            rec["record_id"] = "row-" + sha256_hex(canonical_json(row))[:24]
        if rec["record_id"] is None:
            rec.pop("record_id")  # schema rejects the record -> typed issue, kept as raw
        ts = row.get(ts_field)
        if isinstance(ts, str) and tz and not _HAS_OFFSET.search(ts.strip()):
            ts = ts.strip() + tz
            tz_applied += 1
        rec["observed_at"] = ts
        subject = {}
        for key, col in subj_map.items():
            v = row.get(col)
            if v not in (None, ""):
                subject[key] = str(v)
        rec["subject"] = subject
        if origin_field and row.get(origin_field) not in (None, ""):
            rec["origin_sample_id"] = str(row[origin_field])
        ms = []
        for col, m in meas_map.items():
            if col not in row:
                continue  # column absent: not measured (not the same as an empty cell)
            v = row[col]
            if not typed:
                if (v is None or v.strip() == "") and profile.get("empty_cell", "missing_value") == "not_measured":
                    continue  # declared by the profile: blank = not applicable, not a missing value
                v = _csv_value(v, registry.metrics[m["metric"]].value_type)
            entry = {"metric": m["metric"], "value": v, "unit": m["unit"]}
            if "kind" in m:
                entry["kind"] = m["kind"]
            ms.append(entry)
        rec["measurements"] = ms
        records.append(rec)
    if tz_applied:
        issues.append(Issue(code=IssueCode.TIMEZONE_FROM_PROFILE, severity=Severity.WARNING,
                            message=f"{tz_applied} timestamp(s) had no offset; applied declared profile timezone {tz}"))
    batch = {"schema_version": "1.0.0", "source": dict(profile["source"]), "records": records}
    return AdaptedBatch(batch=batch, originals=originals, source_schema=f"profile:{profile['profile_id']}@{profile['version']}",
                        issues=issues)
