"""Versioned diagnostic knowledge: detector rules and the fault library (JSON data)."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

_DIR = Path(__file__).resolve().parent


@lru_cache(maxsize=None)
def detector_rules() -> dict:
    return json.loads((_DIR / "detector_rules.json").read_text(encoding="utf-8"))


@lru_cache(maxsize=None)
def fault_library() -> dict:
    return json.loads((_DIR / "fault_library.json").read_text(encoding="utf-8"))


def claim_sources() -> dict[str, list[dict]]:
    """claim -> rules (metric, agent) able to establish it. Used by the verification planner."""
    out: dict[str, list[dict]] = {}
    for r in detector_rules()["rules"]:
        out.setdefault(r["claim"], []).append(r)
    return out
