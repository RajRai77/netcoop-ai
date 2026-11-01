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


@lru_cache(maxsize=None)
def confidence_calibration() -> dict | None:
    p = _DIR / "calibration" / "confidence.json"  # not in the knowledge fingerprint (top-level *.json only)
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else None


def confidence_for(status: str, category: str) -> tuple[float | None, dict]:
    """Calibrated confidence for a conclusion (status, support category), or None with the reason.

    Values come from scripts/calibrate_confidence.py (held-out results). They are only used while the
    knowledge files are byte-identical to those the calibration was measured with."""
    import hashlib

    from netcoop.evidence.ids import canonical_json

    cal = confidence_calibration()
    if cal is None:
        return None, {"method": "none", "reason": "no calibration file"}
    current = {p.name: hashlib.sha256(canonical_json(json.loads(p.read_text(encoding="utf-8"))).encode()).hexdigest()
               for p in sorted(_DIR.glob("*.json"))}
    if current != cal["knowledge"]["sha256"]:
        return None, {"method": "none", "reason": "knowledge changed since calibration; re-run held-out evaluation"}
    key = f"{status}|{category}"
    cell = cal["cells"].get(key)
    if cell is None:
        return None, {"method": "none", "reason": f"no held-out cases with conclusion {key}"}
    src = cal["source"]
    return cell["confidence"], {
        "method": "empirical_heldout", "calibration_version": cal["calibration_version"], "conclusion": key,
        "n": cell["n"], "correct": cell["correct"], "wilson_95": cell["wilson_95"], "estimator": cal["estimator"],
        "set": src["set"], "evaluation_method": src["method"], "meaning": cal["meaning"], "caveats": cal["caveats"],
    }


def claim_sources() -> dict[str, list[dict]]:
    """claim -> rules (metric, agent) able to establish it. Used by the verification planner."""
    out: dict[str, list[dict]] = {}
    for r in detector_rules()["rules"]:
        out.setdefault(r["claim"], []).append(r)
    return out
