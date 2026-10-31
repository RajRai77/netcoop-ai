"""Canonical JSON and deterministic content-derived identifiers."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_json(obj: Any) -> str:
    """Deterministic JSON text: sorted keys, no whitespace, UTF-8 preserved.

    NaN/Infinity are kept (allow_nan) so a malformed raw record can still be stored
    byte-faithfully for audit; they are rejected by semantic validation.
    """
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=True)


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def derive_id(prefix: str, *parts: str, length: int = 32) -> str:
    return f"{prefix}-{sha256_hex(chr(31).join(parts))[:length]}"
