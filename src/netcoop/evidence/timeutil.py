"""Strict RFC 3339 timestamp handling. Canonical form: UTC with 'Z'."""

from __future__ import annotations

from datetime import UTC, datetime

from netcoop.evidence.errors import IssueCode


class TimestampError(ValueError):
    def __init__(self, code: IssueCode, message: str):
        self.code = code
        super().__init__(message)


def parse_timestamp(value: object) -> datetime:
    """Parse an ISO 8601 / RFC 3339 string with an explicit offset; return UTC.

    Rejects non-strings (no epoch-number guessing), date-only values and naive times.
    """
    if not isinstance(value, str) or not value.strip():
        raise TimestampError(
            IssueCode.INVALID_TIMESTAMP,
            f"timestamp must be a non-empty string, got {type(value).__name__}",
        )
    text = value.strip()
    if "T" not in text and " " not in text:
        raise TimestampError(IssueCode.INVALID_TIMESTAMP, f"timestamp {value!r} has no time component")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        raise TimestampError(IssueCode.INVALID_TIMESTAMP, f"timestamp {value!r} is not valid ISO 8601") from None
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise TimestampError(
            IssueCode.MISSING_TIMEZONE,
            f"timestamp {value!r} has no timezone offset; refusing to assume one",
        )
    return dt.astimezone(UTC)


def to_canonical(dt: datetime) -> str:
    """Fixed-width UTC text that sorts chronologically: 2026-10-31T10:00:00.000000Z."""
    if dt.tzinfo is None:
        raise ValueError("naive datetime")
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def utcnow() -> datetime:
    return datetime.now(UTC)
