"""Typed validation issues. Every rejection/quarantine carries a machine-readable code."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class IssueCode(StrEnum):
    # Batch / document level
    MALFORMED_JSON = "MALFORMED_JSON"
    PAYLOAD_TOO_LARGE = "PAYLOAD_TOO_LARGE"
    TOO_MANY_RECORDS = "TOO_MANY_RECORDS"
    SCHEMA_INVALID = "SCHEMA_INVALID"
    UNSUPPORTED_SCHEMA_VERSION = "UNSUPPORTED_SCHEMA_VERSION"
    DATA_MODE_MISMATCH = "DATA_MODE_MISMATCH"
    UNKNOWN_INCIDENT = "UNKNOWN_INCIDENT"
    PROFILE_INVALID = "PROFILE_INVALID"
    UNKNOWN_PROFILE = "UNKNOWN_PROFILE"
    CSV_MALFORMED = "CSV_MALFORMED"
    UNMAPPED_FIELD = "UNMAPPED_FIELD"
    TIMEZONE_FROM_PROFILE = "TIMEZONE_FROM_PROFILE"
    # Record identity / integrity
    DUPLICATE_RECORD = "DUPLICATE_RECORD"
    RECORD_ID_CONFLICT = "RECORD_ID_CONFLICT"
    # Subject
    INVALID_SUBJECT = "INVALID_SUBJECT"
    UNKNOWN_SUBJECT = "UNKNOWN_SUBJECT"
    SUBJECT_UNVERIFIED = "SUBJECT_UNVERIFIED"
    # Time
    INVALID_TIMESTAMP = "INVALID_TIMESTAMP"
    MISSING_TIMEZONE = "MISSING_TIMEZONE"
    FUTURE_TIMESTAMP = "FUTURE_TIMESTAMP"
    INVALID_WINDOW = "INVALID_WINDOW"
    WINDOW_REQUIRED = "WINDOW_REQUIRED"
    STALE_OBSERVATION = "STALE_OBSERVATION"
    # Measurement semantics
    UNKNOWN_METRIC = "UNKNOWN_METRIC"
    MISSING_VALUE = "MISSING_VALUE"
    MISSING_UNIT = "MISSING_UNIT"
    UNSUPPORTED_UNIT = "UNSUPPORTED_UNIT"
    UNIT_CONVERTED = "UNIT_CONVERTED"
    TYPE_MISMATCH = "TYPE_MISMATCH"
    NON_FINITE_VALUE = "NON_FINITE_VALUE"
    OUT_OF_RANGE = "OUT_OF_RANGE"
    INVALID_STATE_VALUE = "INVALID_STATE_VALUE"
    MISSING_KIND = "MISSING_KIND"
    KIND_MISMATCH = "KIND_MISMATCH"
    # Counters
    COUNTER_INSUFFICIENT_SAMPLES = "COUNTER_INSUFFICIENT_SAMPLES"
    COUNTER_RESET = "COUNTER_RESET"
    COUNTER_TIMESTAMP_CONFLICT = "COUNTER_TIMESTAMP_CONFLICT"
    COUNTER_MIXED_LINEAGE = "COUNTER_MIXED_LINEAGE"
    IMPOSSIBLE_RATE = "IMPOSSIBLE_RATE"
    # Findings / topology
    UNKNOWN_OBSERVATION_REF = "UNKNOWN_OBSERVATION_REF"
    INVALID_SUPERSEDES = "INVALID_SUPERSEDES"
    FINDING_CONFLICT = "FINDING_CONFLICT"
    TOPOLOGY_INVALID = "TOPOLOGY_INVALID"
    TOPOLOGY_CONFLICT = "TOPOLOGY_CONFLICT"
    UNKNOWN_TOPOLOGY = "UNKNOWN_TOPOLOGY"


class Severity(StrEnum):
    REJECT = "reject"  # not admitted as evidence (raw record is still retained)
    QUARANTINE = "quarantine"  # admitted, flagged as not trustworthy for inference
    WARNING = "warning"  # admitted; informational (e.g. unit converted, stale)


class Issue(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    code: IssueCode
    severity: Severity
    message: str
    record_index: int | None = None
    record_id: str | None = None
    measurement_index: int | None = None
    path: str | None = None


class EvidenceError(Exception):
    """A whole document/operation was refused. Carries typed issues."""

    def __init__(self, issues: list[Issue]):
        self.issues = issues
        super().__init__("; ".join(f"{i.code}: {i.message}" for i in issues))

    @classmethod
    def single(cls, code: IssueCode, message: str, **kw) -> "EvidenceError":
        return cls([Issue(code=code, severity=Severity.REJECT, message=message, **kw)])

    @property
    def codes(self) -> list[IssueCode]:
        return [i.code for i in self.issues]
