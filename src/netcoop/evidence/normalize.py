"""Semantic normalization of a TelemetryBatch into immutable raw records + observations.

Pure function of (payload, incident, clock, registry, topology): no I/O. Cross-batch
duplicate/conflict detection happens in the store, which sees committed state.

Rules (see docs/04_EVIDENCE_AND_CONTRACTS.md):
- Units are required and must be listed for the metric; conversions only via registry.
- Missing value is MISSING_VALUE, never zero. No string->number or 0/1->bool coercion.
- Timestamps need explicit offsets; future beyond skew is rejected; age beyond policy
  marks the observation stale (kept, flagged), it is not dropped or zeroed.
- Unknown subjects (vs. the supplied topology) are quarantined, not silently accepted.
- One bad measurement does not reject its siblings; one bad record does not reject the batch.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Literal

from netcoop.evidence.errors import EvidenceError, Issue, IssueCode, Severity
from netcoop.evidence.ids import canonical_json, derive_id, sha256_hex
from netcoop.evidence.models import (
    Measurement,
    NormalizedObservation,
    Quality,
    RawRecord,
    SourceRef,
    Subject,
    TopologySnapshot,
    Window,
)
from netcoop.evidence.registry import MetricDef, MetricRegistry, default_registry
from netcoop.evidence.timeutil import TimestampError, parse_timestamp
from netcoop.spec import validator

BATCH_SCHEMA_VERSIONS = {"1.0.0"}
BATCH_SOURCE_SCHEMA = "ndep-telemetry-batch@1.0.0"
NORMALIZER_VERSION = "ndep-normalize/1"
SUBJECT_KEYS = ("device_id", "interface_id", "service_id", "segment_id", "link_id")


@dataclass(frozen=True)
class Limits:
    max_payload_bytes: int = 5 * 1024 * 1024
    max_records: int = 10_000


RecordStatus = Literal[
    "accepted", "quarantined", "partially_rejected", "rejected", "duplicate", "conflict"
]


@dataclass
class RecordOutcome:
    record_index: int
    record_id: str | None
    raw_id: str
    status: RecordStatus
    observation_ids: list[str] = field(default_factory=list)


@dataclass
class NormalizedBatch:
    incident_id: str
    batch_id: str | None
    source: SourceRef
    ingested_at: datetime
    registry_version: str
    raw_records: list[RawRecord]
    observations: list[NormalizedObservation]
    issues: list[Issue]
    outcomes: list[RecordOutcome]

    def observations_for(self, raw_id: str) -> list[NormalizedObservation]:
        return [o for o in self.observations if o.raw_record_ref == raw_id]


def parse_payload(payload: bytes | str | dict, limits: Limits) -> dict:
    """Bytes -> dict. Rejects oversize payloads and duplicate JSON keys (ambiguous)."""
    if isinstance(payload, dict):
        return payload
    raw = payload.encode("utf-8") if isinstance(payload, str) else payload
    if len(raw) > limits.max_payload_bytes:
        raise EvidenceError.single(
            IssueCode.PAYLOAD_TOO_LARGE, f"payload is {len(raw)} bytes; limit {limits.max_payload_bytes}"
        )

    def no_dup_keys(pairs: list[tuple[str, Any]]) -> dict:
        seen: dict[str, Any] = {}
        for k, v in pairs:
            if k in seen:
                raise ValueError(f"duplicate JSON key {k!r}")
            seen[k] = v
        return seen

    try:
        doc = json.loads(raw.decode("utf-8"), object_pairs_hook=no_dup_keys)
    except (UnicodeDecodeError, ValueError) as exc:
        raise EvidenceError.single(IssueCode.MALFORMED_JSON, f"payload is not valid JSON: {exc}") from None
    if not isinstance(doc, dict):
        raise EvidenceError.single(IssueCode.SCHEMA_INVALID, "telemetry batch must be a JSON object")
    return doc


def _schema_errors_by_record(doc: dict) -> tuple[list[str], dict[int, list[tuple[list, str]]]]:
    batch_errors: list[str] = []
    per_record: dict[int, list[tuple[list, str]]] = {}
    for err in validator("telemetry-batch").iter_errors(doc):
        path = list(err.absolute_path)
        if len(path) >= 2 and path[0] == "records" and isinstance(path[1], int):
            per_record.setdefault(path[1], []).append((path[2:], err.message))
        else:
            loc = "/".join(str(p) for p in path) or "<root>"
            batch_errors.append(f"{loc}: {err.message}")
    return batch_errors, per_record


def normalize_batch(
    payload: bytes | str | dict,
    *,
    incident_id: str,
    ingested_at: datetime,
    registry: MetricRegistry | None = None,
    topology: TopologySnapshot | None = None,
    expected_data_mode: str | None = None,
    limits: Limits = Limits(),
    originals: list[dict] | None = None,
    source_schema: str = BATCH_SOURCE_SCHEMA,
    pre_issues: list[Issue] | None = None,
    batch_id: str | None = None,
    reference_time: datetime | None = None,
) -> NormalizedBatch:
    """originals: when a source-profile adapter produced the batch, the vendor rows
    (same order as records). They become the immutable raw record content."""
    registry = registry or default_registry()
    doc = parse_payload(payload, limits)

    version = doc.get("schema_version")
    if version not in BATCH_SCHEMA_VERSIONS:
        raise EvidenceError.single(
            IssueCode.UNSUPPORTED_SCHEMA_VERSION,
            f"telemetry batch schema_version {version!r} not supported; supported: {sorted(BATCH_SCHEMA_VERSIONS)}",
        )
    records = doc.get("records")
    if isinstance(records, list) and len(records) > limits.max_records:
        raise EvidenceError.single(
            IssueCode.TOO_MANY_RECORDS, f"{len(records)} records; limit {limits.max_records}"
        )
    batch_errors, record_schema_errors = _schema_errors_by_record(doc)
    if batch_errors:
        raise EvidenceError(
            [Issue(code=IssueCode.SCHEMA_INVALID, severity=Severity.REJECT, message=m) for m in batch_errors]
        )

    source = SourceRef.model_validate(doc["source"])
    if expected_data_mode is not None and source.data_mode != expected_data_mode:
        raise EvidenceError.single(
            IssueCode.DATA_MODE_MISMATCH,
            f"batch data_mode {source.data_mode!r} differs from incident data_mode {expected_data_mode!r}",
        )

    if originals is not None and len(originals) != len(records):
        raise ValueError("originals must align with records")
    ctx = _Ctx(incident_id, source, ingested_at, registry, topology, batch_id or doc.get("batch_id"), source_schema)
    # Freshness/future checks use the declared reference time (capture time of a recorded
    # replay) when given; otherwise the real ingestion time.
    ctx.as_of = reference_time or ingested_at
    ctx.issues.extend(pre_issues or [])
    for i, rec in enumerate(records):
        ctx.record(i, rec, record_schema_errors.get(i, []), originals[i] if originals is not None else None)
    return NormalizedBatch(
        incident_id=incident_id,
        batch_id=ctx.batch_id,
        source=source,
        ingested_at=ingested_at,
        registry_version=registry.version,
        raw_records=ctx.raws,
        observations=ctx.observations,
        issues=ctx.issues,
        outcomes=ctx.outcomes,
    )


class _Ctx:
    def __init__(self, incident_id, source, ingested_at, registry, topology, batch_id, source_schema):
        self.source_schema: str = source_schema
        self.incident_id: str = incident_id
        self.source: SourceRef = source
        self.ingested_at: datetime = ingested_at
        self.reg: MetricRegistry = registry
        self.topology: TopologySnapshot | None = topology
        self.batch_id: str | None = batch_id
        self.raws: list[RawRecord] = []
        self.observations: list[NormalizedObservation] = []
        self.issues: list[Issue] = []
        self.outcomes: list[RecordOutcome] = []
        self._hash_seen: dict[str, str] = {}
        self._record_ids: dict[str, str] = {}
        if topology is not None:
            self._node_ids = {n.id for n in topology.nodes}
            self._link_ids = {lk.id for lk in topology.links}

    # -- helpers ---------------------------------------------------------------
    def _issue(self, code, severity, message, i, rid, j=None, path=None) -> Issue:
        issue = Issue(
            code=code, severity=severity, message=message,
            record_index=i, record_id=rid, measurement_index=j, path=path,
        )
        self.issues.append(issue)
        return issue

    # -- per record --------------------------------------------------------------
    def record(self, i: int, rec: Any, schema_errs: list[tuple[list, str]], original: Any = None) -> None:
        raw_obj = rec if original is None else original
        content = canonical_json(raw_obj)
        content_hash = sha256_hex(canonical_json(
            {"source_id": self.source.source_id, "source_schema": self.source_schema, "record": raw_obj}))
        raw_id = derive_id("RAW", self.incident_id, content_hash)
        rid = rec.get("record_id") if isinstance(rec, dict) and isinstance(rec.get("record_id"), str) else None

        if content_hash in self._hash_seen:
            self._issue(IssueCode.DUPLICATE_RECORD, Severity.WARNING,
                        "identical record already present earlier in this batch; not counted again", i, rid)
            self.outcomes.append(RecordOutcome(i, rid, self._hash_seen[content_hash], "duplicate"))
            return
        self._hash_seen[content_hash] = raw_id
        self.raws.append(RawRecord(
            raw_id=raw_id, incident_id=self.incident_id, content_hash=content_hash, source=self.source,
            source_schema=self.source_schema, source_record_id=rid, batch_id=self.batch_id,
            received_at=self.ingested_at, content=content,
        ))
        if rid is not None and rid in self._record_ids:
            self._issue(IssueCode.RECORD_ID_CONFLICT, Severity.REJECT,
                        f"record_id {rid!r} reused in this batch with different content", i, rid)
            self.outcomes.append(RecordOutcome(i, rid, raw_id, "conflict"))
            return
        if rid is not None:
            self._record_ids[rid] = raw_id

        status, obs_ids = self._validate_record(i, rid, raw_id, rec, schema_errs)
        self.outcomes.append(RecordOutcome(i, rid, raw_id, status, obs_ids))

    def _validate_record(self, i, rid, raw_id, rec, schema_errs) -> tuple[RecordStatus, list[str]]:
        if not isinstance(rec, dict):
            self._issue(IssueCode.SCHEMA_INVALID, Severity.REJECT, "record must be a JSON object", i, rid)
            return "rejected", []

        record_level_rejects = 0
        flags: list[str] = []
        quarantined = False

        # Structural errors outside measurements reject the record.
        meas_schema_errs: dict[int, list[str]] = {}
        for path, msg in schema_errs:
            if len(path) >= 2 and path[0] == "measurements" and isinstance(path[1], int):
                meas_schema_errs.setdefault(path[1], []).append(f"{'/'.join(map(str, path[2:])) or '<measurement>'}: {msg}")
            elif not (path and path[0] in ("subject", "observed_at", "window")):
                # subject/time problems get specific codes below
                loc = "/".join(map(str, path)) or "<record>"
                self._issue(IssueCode.SCHEMA_INVALID, Severity.REJECT, f"{loc}: {msg}", i, rid, path=loc)
                record_level_rejects += 1

        subject = self._subject(i, rid, rec.get("subject"))
        if subject is None:
            record_level_rejects += 1

        observed_at = self._time(i, rid, rec.get("observed_at"), "observed_at")
        if observed_at is None:
            record_level_rejects += 1
        window = None
        if "window" in rec:
            window = self._window(i, rid, rec["window"], observed_at)
            if window is None:
                record_level_rejects += 1

        if record_level_rejects:
            return "rejected", []

        if self.topology is None:
            flags.append("subject_unverified")
            self._issue(IssueCode.SUBJECT_UNVERIFIED, Severity.WARNING,
                        "no topology snapshot supplied; subject identity not verified", i, rid)
        else:
            unknown = self._unknown_subject_ids(subject)
            if unknown:
                quarantined = True
                flags.append("unknown_subject")
                self._issue(IssueCode.UNKNOWN_SUBJECT, Severity.QUARANTINE,
                            f"subject ids not in topology {self.topology.topology_snapshot_id}: {unknown}", i, rid,
                            path="subject")

        lineage = derive_id(
            "LG",
            *(("origin", rec["origin_sample_id"]) if isinstance(rec.get("origin_sample_id"), str)
              else ("record", self.source.source_id, rid or raw_id)),
            length=24,
        )

        measurements = rec.get("measurements")
        if not isinstance(measurements, list) or not measurements:
            self._issue(IssueCode.SCHEMA_INVALID, Severity.REJECT, "measurements must be a non-empty array", i, rid)
            return "rejected", []

        obs_ids: list[str] = []
        rejected_meas = 0
        for j, m in enumerate(measurements):
            obs = self._measurement(i, rid, j, m, raw_id, subject, observed_at, window, lineage,
                                    flags, quarantined, meas_schema_errs.get(j, []))
            if obs is None:
                rejected_meas += 1
            else:
                self.observations.append(obs)
                obs_ids.append(obs.observation_id)

        if not obs_ids:
            return "rejected", []
        if rejected_meas:
            return "partially_rejected", obs_ids
        return ("quarantined" if quarantined else "accepted"), obs_ids

    def _subject(self, i, rid, subj) -> Subject | None:
        if not isinstance(subj, dict):
            self._issue(IssueCode.INVALID_SUBJECT, Severity.REJECT, "subject must be an object", i, rid, path="subject")
            return None
        extra = sorted(set(subj) - set(SUBJECT_KEYS))
        bad = [k for k in SUBJECT_KEYS if k in subj and (not isinstance(subj[k], str) or not subj[k].strip())]
        problems = []
        if extra:
            problems.append(f"unknown subject keys {extra}")
        if bad:
            problems.append(f"subject ids must be non-empty strings: {bad}")
        if not any(isinstance(subj.get(k), str) and subj.get(k) for k in ("device_id", "service_id", "segment_id", "link_id")):
            problems.append("needs one of device_id, service_id, segment_id, link_id")
        if "interface_id" in subj and "device_id" not in subj:
            problems.append("interface_id requires device_id (interfaces are device-scoped)")
        if problems:
            self._issue(IssueCode.INVALID_SUBJECT, Severity.REJECT, "; ".join(problems), i, rid, path="subject")
            return None
        return Subject.model_validate(subj)

    def _unknown_subject_ids(self, s: Subject) -> list[str]:
        unknown = [v for v in (s.device_id, s.service_id, s.segment_id) if v and v not in self._node_ids]
        if s.link_id and s.link_id not in self._link_ids:
            unknown.append(s.link_id)
        return unknown

    def _time(self, i, rid, value, path) -> datetime | None:
        try:
            ts = parse_timestamp(value)
        except TimestampError as exc:
            message = f"{path} is required" if value is None else str(exc)
            self._issue(exc.code, Severity.REJECT, message, i, rid, path=path)
            return None
        skew = timedelta(seconds=self.reg.max_future_skew_s)
        if ts > self.as_of + skew:
            self._issue(IssueCode.FUTURE_TIMESTAMP, Severity.REJECT,
                        f"{path} {value!r} is later than the reference time plus {self.reg.max_future_skew_s}s skew",
                        i, rid, path=path)
            return None
        return ts

    def _window(self, i, rid, w, observed_at) -> Window | None:
        if not isinstance(w, dict) or set(w) != {"start", "end"}:
            self._issue(IssueCode.INVALID_WINDOW, Severity.REJECT, "window must be {start, end}", i, rid, path="window")
            return None
        start = self._time(i, rid, w.get("start"), "window.start")
        end = self._time(i, rid, w.get("end"), "window.end")
        if start is None or end is None:
            return None
        if start > end:
            self._issue(IssueCode.INVALID_WINDOW, Severity.REJECT, "window.start is after window.end", i, rid, path="window")
            return None
        if observed_at is not None and not (start <= observed_at <= end):
            self._issue(IssueCode.INVALID_WINDOW, Severity.REJECT,
                        "observed_at lies outside the observation window", i, rid, path="window")
            return None
        return Window(start=start, end=end)

    def _measurement(self, i, rid, j, m, raw_id, subject, observed_at, window, lineage,
                     record_flags, quarantined, schema_errs) -> NormalizedObservation | None:
        def reject(code: IssueCode, msg: str) -> None:
            self._issue(code, Severity.REJECT, msg, i, rid, j, path=f"measurements/{j}")

        if not isinstance(m, dict):
            reject(IssueCode.SCHEMA_INVALID, "measurement must be an object")
            return None
        metric_name = m.get("metric")
        mdef: MetricDef | None = self.reg.metrics.get(metric_name) if isinstance(metric_name, str) else None
        if mdef is None:
            reject(IssueCode.UNKNOWN_METRIC,
                   f"metric {metric_name!r} is not in registry {self.reg.version}")
            return None
        if m.get("value") is None:
            reject(IssueCode.MISSING_VALUE, f"{metric_name}: value is missing/null (missing is not zero)")
            return None
        unit_in = m.get("unit")
        if not isinstance(unit_in, str) or not unit_in.strip():
            reject(IssueCode.MISSING_UNIT, f"{metric_name}: unit is required; refusing to guess "
                                           f"(allowed: {list(mdef.allowed_units)})")
            return None
        unit = self.reg.resolve_unit(unit_in)
        if unit not in mdef.allowed_units:
            reject(IssueCode.UNSUPPORTED_UNIT,
                   f"{metric_name}: unit {unit_in!r} not allowed (allowed: {list(mdef.allowed_units)})")
            return None

        flags = list(record_flags)
        kind = m.get("kind")
        if kind is None:
            if len(mdef.allowed_kinds) != 1:
                reject(IssueCode.MISSING_KIND,
                       f"{metric_name}: kind required, metric allows {list(mdef.allowed_kinds)}")
                return None
            kind = mdef.allowed_kinds[0]
            flags.append("kind_from_registry")
        elif kind not in mdef.allowed_kinds:
            reject(IssueCode.KIND_MISMATCH,
                   f"{metric_name}: kind {kind!r} not allowed (allowed: {list(mdef.allowed_kinds)})")
            return None
        if kind == "interval_summary" and window is None:
            reject(IssueCode.WINDOW_REQUIRED, f"{metric_name}: interval_summary requires a window")
            return None

        value = self._value(reject, mdef, m["value"], unit)
        if value is _BAD:
            return None
        if schema_errs:  # any structural problem not already covered above
            reject(IssueCode.SCHEMA_INVALID, "; ".join(schema_errs))
            return None

        transformation = None
        if unit_in != unit:
            flags.append(f"unit_alias:{unit_in}->{unit}")
        if unit != mdef.canonical_unit:
            flags.append(f"unit_converted:{unit}->{mdef.canonical_unit}")
            transformation = f"{NORMALIZER_VERSION}:unit:{unit}->{mdef.canonical_unit}"
            self._issue(IssueCode.UNIT_CONVERTED, Severity.WARNING,
                        f"{metric_name}: {m['value']!r} {unit} converted to {value!r} {mdef.canonical_unit}",
                        i, rid, j)

        freshness = "current"
        age = (self.as_of - observed_at).total_seconds()
        if age > self.reg.max_age_s(mdef):
            freshness = "stale"
            flags.append("stale")
            self._issue(IssueCode.STALE_OBSERVATION, Severity.WARNING,
                        f"{metric_name}: observed {age:.0f}s before the reference time; policy max {self.reg.max_age_s(mdef):.0f}s",
                        i, rid, j)

        obs_id = derive_id("OBS", raw_id, str(j), self.reg.version)
        return NormalizedObservation(
            observation_id=obs_id,
            incident_id=self.incident_id,
            raw_record_ref=raw_id,
            source=self.source,
            subject=subject,
            measurement=Measurement(metric=metric_name, value=value, unit=mdef.canonical_unit,
                                    kind=kind, window=window),
            observed_at=observed_at,
            ingested_at=self.ingested_at,
            quality=Quality(validation="quarantined" if quarantined else "passed",
                            freshness=freshness, flags=tuple(dict.fromkeys(flags))),
            lineage_group=lineage,
            metric_registry_version=self.reg.version,
            transformation_id=transformation,
        )

    def _value(self, reject, mdef: MetricDef, v: Any, unit: str):
        name = mdef.name
        vt = mdef.value_type
        if vt == "boolean":
            if not isinstance(v, bool):
                reject(IssueCode.TYPE_MISMATCH, f"{name}: expected JSON boolean, got {type(v).__name__} (no 0/1 or string coercion)")
                return _BAD
            return v
        if vt == "enum":
            if not isinstance(v, str):
                reject(IssueCode.TYPE_MISMATCH, f"{name}: expected string state, got {type(v).__name__}")
                return _BAD
            if v not in mdef.allowed_values:
                reject(IssueCode.INVALID_STATE_VALUE, f"{name}: {v!r} not in {list(mdef.allowed_values)}")
                return _BAD
            return v
        # numeric
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            reject(IssueCode.TYPE_MISMATCH, f"{name}: expected JSON number, got {type(v).__name__} (no string coercion)")
            return _BAD
        if isinstance(v, float) and not math.isfinite(v):
            reject(IssueCode.NON_FINITE_VALUE, f"{name}: value {v!r} is not finite")
            return _BAD
        if vt == "integer" and not isinstance(v, int):
            reject(IssueCode.TYPE_MISMATCH, f"{name}: counter value must be an integer, got {v!r}")
            return _BAD
        factor = self.reg.factor(unit, mdef.canonical_unit)
        if factor == 1:
            out = v
        else:
            exact = Decimal(str(v)) * Decimal(str(factor))  # avoids 0.085*1000 = 85.00000000000001
            out = int(exact) if isinstance(v, int) and exact == exact.to_integral_value() else float(exact)
        try:
            finite = math.isfinite(float(out))
        except OverflowError:
            finite = False
        if not finite:
            reject(IssueCode.OUT_OF_RANGE, f"{name}: value overflows a finite double")
            return _BAD
        if mdef.min is not None and out < mdef.min:
            reject(IssueCode.OUT_OF_RANGE, f"{name}: {out} {mdef.canonical_unit} below minimum {mdef.min}")
            return _BAD
        if mdef.max is not None and out > mdef.max:
            reject(IssueCode.OUT_OF_RANGE, f"{name}: {out} {mdef.canonical_unit} above maximum {mdef.max}")
            return _BAD
        return out


_BAD = object()
