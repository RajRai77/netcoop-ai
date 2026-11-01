"""Derive the report's numeric `confidence` from held-out evaluation results.

    uv run python scripts/calibrate_confidence.py \
        --results eval/results-heldout-v3-replay-dfull/results.json --set heldout-v3 --method D_full

For every (status, support category) the full method produced on the held-out set, count how often that
conclusion was right:
  * diagnosed -> the reported root cause(s) exactly matched the injected fault(s);
  * any other status -> the outcome was acceptable (correct healthy call, or an abstention where the data
    cannot identify the cause).
confidence = (k + 1) / (n + 2)  (Laplace rule of succession; never 0 or 1 on finite samples), reported with the
95 % Wilson interval and n. Writes src/netcoop/knowledge/calibration/confidence.json. The knowledge files
(detector rules, fault library) must be byte-identical to those the results were produced with.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KNOW = ROOT / "src" / "netcoop" / "knowledge"
OUT = KNOW / "calibration" / "confidence.json"  # subfolder: not part of the knowledge fingerprint


def _canon_sha(obj) -> str:
    """SHA-256 of canonical JSON (independent of line endings / checkout OS)."""
    from netcoop.evidence.ids import canonical_json

    return hashlib.sha256(canonical_json(obj).encode()).hexdigest()


def wilson(k: int, n: int, z: float = 1.959964) -> list[float]:
    if n == 0:
        return [0.0, 1.0]
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(max(0.0, c - h), 3), round(min(1.0, c + h), 3)]


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--results", required=True)
    p.add_argument("--set", required=True)
    p.add_argument("--method", default="D_full")
    a = p.parse_args()
    path = ROOT / a.results
    raw = path.read_bytes()
    res = json.loads(raw)
    from netcoop.scenarios.heldout import knowledge_fingerprint  # same canonical-JSON hash the evaluator records
    know = knowledge_fingerprint()
    if res["knowledge"]["sha256"] != know:
        print(f"knowledge files differ from those used for {a.results}; refusing to calibrate", file=sys.stderr)
        return 2
    cases = res["sets"][a.set]["cases"][a.method]
    cells: dict[str, dict] = {}
    for c in cases:
        key = f"{c['status']}|{c['category']}"
        ok = bool(c["score"]["exact_cause"]) if c["status"] == "diagnosed" else bool(c["score"]["acceptable"])
        cell = cells.setdefault(key, {"n": 0, "correct": 0})
        cell["n"] += 1
        cell["correct"] += ok
    for cell in cells.values():
        cell["confidence"] = round((cell["correct"] + 1) / (cell["n"] + 2), 2)
        cell["wilson_95"] = wilson(cell["correct"], cell["n"])
    out = {
        "calibration_version": "confidence-calibration/1",
        "meaning": "Probability that a conclusion of this status and support category is correct, estimated as "
                   "(k+1)/(n+2) from how often the same conclusion was correct on a held-out evaluation set.",
        "correct_means": {"diagnosed": "reported root cause(s) exactly match the injected fault(s)",
                          "other": "outcome acceptable: correct healthy call, or abstention where the data cannot identify the cause"},
        "estimator": "laplace (k+1)/(n+2), interval: Wilson 95 %",
        "source": {"results": a.results, "results_sha256_canonical": _canon_sha(res), "set": a.set,
                   "scenarios": res["sets"][a.set]["scenarios"], "method": a.method, "git_commit": res.get("git_commit"),
                   "code": res.get("code"),
                   "knowledge_frozen_before_generation": res["sets"][a.set].get("knowledge_frozen_before_generation")},
        "knowledge": {"detector_rules": res["knowledge"]["detector_rules"], "fault_library": res["knowledge"]["fault_library"],
                      "sha256": know},
        "caveats": [
            "Measured on synthetic scenarios from the project's own generator (same authors as the engine); "
            "not validated on real networks or on other data sources",
            "Small samples: see n and the 95 % interval for each category",
        ],
        "cells": dict(sorted(cells.items())),
    }
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    for k, v in out["cells"].items():
        print(f"{k:38s} {v['correct']}/{v['n']} -> {v['confidence']}  95% {v['wilson_95']}")
    print(f"wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
