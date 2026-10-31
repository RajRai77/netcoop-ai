"""The evaluator itself must work (it is not imported by the other tests)."""

from __future__ import annotations

import shutil
from pathlib import Path

from netcoop.evaluation.runner import METHODS, code_fingerprint, evaluate, to_markdown

BASE = Path(__file__).resolve().parents[2] / "data" / "scenarios"


def test_code_fingerprint_is_stable_and_line_ending_independent():
    a, b = code_fingerprint(), code_fingerprint()
    assert a["diagnosis_code_sha256"] == b["diagnosis_code_sha256"]
    assert len(a["diagnosis_code_sha256"]) == 64


def test_evaluate_one_scenario_end_to_end(tmp_path):
    shutil.copytree(BASE / "S01-congestion", tmp_path / "S01-congestion")
    methods = [m for m in METHODS if m.name in ("A_threshold", "D_full")]
    res = evaluate({"mini": tmp_path}, methods, progress=lambda *_: None)
    s = res["sets"]["mini"]["summary"]
    assert s["D_full"]["acceptable_outcome"] == {"count": 1, "of": 1}
    assert res["code"]["diagnosis_code_sha256"]
    assert "Set `mini`" in to_markdown(res)
