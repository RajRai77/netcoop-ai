"""Reproducible comparison of NetCoop against baselines and ablations.

Methods (all receive the same initial observations; only 'full*' may request more):
  A_threshold        centralized threshold alerting: the highest-priority fired detector
                     names the cause at its own subject (no topology, no hypotheses)
  B_centralized      STEaR hypothesis engine without topology or temporal context, no verification
  C_stear_noverify   STEaR with topology + temporal checks, no active verification
  D_full             C + bounded evidence-seeking verification (agents query recorded archives)
  D_full_no_topology / D_full_no_temporal   ablations of D

Specialists run in-process for speed; the same NDEP payloads and code are used over
A2A in tests/integration/test_a2a_agents.py (equivalence asserted there). Results are
written to JSON and a Markdown summary is rendered FROM that JSON. No number is typed by hand.
"""

from __future__ import annotations

import json
import platform
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from netcoop.agents.protocol import SPECIALISTS
from netcoop.engine.planner import VerificationPolicy
from netcoop.knowledge import detector_rules, fault_library
from netcoop.orchestration.coordinator import Coordinator, CoordinatorOptions
from netcoop.orchestration.ports import InProcessAgentPort
from netcoop.scenarios.heldout import knowledge_fingerprint
from netcoop.scenarios.loader import list_scenarios, load_into
from netcoop.storage import SqlEvidenceStore, make_engine, migrate

ABSTAIN = {"ambiguous", "insufficient_evidence", "unknown_fault"}

# Baseline A: fixed priority of detector claims -> fault type at the claim's own subject.
THRESHOLD_RULES = [
    ("DEVICE_DOWN_STATE", "DEVICE_DOWN"), ("INTERFACE_DOWN", "LINK_OR_PATH_FAILURE"),
    ("UNREACHABLE", "DEVICE_DOWN"), ("DNS_FAILURES", "DNS_FAILURE"), ("DHCP_FAILURES", "DHCP_FAILURE"),
    ("CRC_ERRORS", "INTERFACE_DEGRADATION"), ("INTERFACE_ERRORS", "INTERFACE_DEGRADATION"),
    ("HIGH_LINK_UTILIZATION", "LINK_CONGESTION"), ("HIGH_CPU", "DEVICE_CPU_OVERLOAD"),
    ("WEAK_SIGNAL", "WEAK_WIFI_SIGNAL"), ("LOW_SNR", "WIRELESS_INTERFERENCE"),
    ("HIGH_WIRELESS_RETRIES", "WEAK_WIFI_SIGNAL"), ("PACKET_LOSS", "LINK_CONGESTION"),
    ("HIGH_LATENCY", "LINK_CONGESTION"),
]


@dataclass
class Method:
    name: str
    verify: bool
    topology: bool = True
    temporal: bool = True
    threshold: bool = False


METHODS = [
    Method("A_threshold", verify=False, topology=False, temporal=False, threshold=True),
    Method("B_centralized", verify=False, topology=False, temporal=False),
    Method("C_stear_noverify", verify=False),
    Method("D_full", verify=True),
    Method("D_full_no_topology", verify=True, topology=False),
    Method("D_full_no_temporal", verify=True, temporal=False),
]


def _truth(gt: dict) -> set[tuple[str, str]]:
    return {(f["fault_type"], f["location"]) for f in gt["faults"]}


def _causes(report: dict) -> set[tuple[str, str]]:
    return {(c["fault_type"], c["location"]) for c in report.get("root_causes", [])}


def _threshold_decision(store, iid: str) -> dict:
    """Baseline A on the same findings the specialists produced (centralized rule pick)."""
    fs = [f for f in store.list_findings(iid) if f.polarity == "present"]
    for claim, fault in THRESHOLD_RULES:
        hits = sorted((f for f in fs if f.claim == claim), key=lambda f: f.subject.key())
        if hits:
            s = hits[0].subject
            loc = f"{s.device_id}:{s.interface_id}" if s.device_id and s.interface_id else (
                s.device_id or s.service_id or s.segment_id)
            return {"status": "diagnosed", "causes": {(fault, loc)}, "category": "rule"}
    return {"status": "healthy", "causes": set(), "category": "rule"}


def score(case: dict, gt: dict, method: Method) -> dict:
    truth = _truth(gt)
    diagnosable = gt.get("diagnosable_with_archive" if method.verify else "diagnosable_initial")
    if diagnosable is None:  # dev set: derived from the expected status of this information condition
        exp = gt["expected_status"] if method.verify else gt["expected_status_without_verification"]
        diagnosable = exp == "diagnosed"
    status, causes = case["status"], case["causes"]
    healthy_truth = not truth
    unmodeled = any(t[0] == "UNMODELED_PATH_ISSUE" for t in truth)
    exact = status == "diagnosed" and causes == truth
    out = {
        "exact_cause": exact,
        "fault_type_correct": status == "diagnosed" and {c[0] for c in causes} == {t[0] for t in truth},
        "localization_correct": status == "diagnosed" and {c[1] for c in causes} == {t[1] for t in truth},
        "any_cause_correct": status == "diagnosed" and bool(causes & truth),
        "confident_wrong": status == "diagnosed" and not exact,
        "high_support_wrong": case.get("category") == "high_support" and not exact,
        "abstained": status in ABSTAIN,
        "false_healthy": status == "healthy" and not healthy_truth,
        "healthy_correct": healthy_truth and status == "healthy",
        "unknown_detected": unmodeled and status == "unknown_fault",
        "multi_fault_recall": (len(causes & truth) / len(truth)) if len(truth) > 1 else None,
        "diagnosable": bool(diagnosable),
    }
    # an outcome is acceptable if it is right when the data allow it, and an abstention when they do not
    if healthy_truth:
        out["acceptable"] = status == "healthy"
    elif unmodeled:
        out["acceptable"] = status in ABSTAIN
    elif diagnosable:
        out["acceptable"] = exact
    else:
        out["acceptable"] = status in ABSTAIN or exact
    return out


def run_case(store, base: Path, sid: str, method: Method) -> dict:
    inc = load_into(store, base, sid)["incident"]
    ports = [InProcessAgentPort(a, base, None) for a in SPECIALISTS]
    opts = CoordinatorOptions(use_topology=method.topology, use_temporal=method.temporal,
                              verification=VerificationPolicy(enabled=method.verify))
    t0 = time.perf_counter()
    r = Coordinator(store, ports, opts).run(inc.incident_id)
    elapsed = time.perf_counter() - t0
    v = r.get("verification") or {}
    case = {"scenario_id": sid, "method": method.name, "status": r["status"], "category": r["confidence_category"],
            "causes": _causes(r), "suspected_root_cause": r["suspected_root_cause"], "seconds": round(elapsed, 3),
            "checks_requested": len(v.get("challenges", [])),
            "checks_obtained": sum(1 for c in v.get("challenges", []) if c["outcome"] == "obtained"),
            "new_observations": sum(len(c["new_observation_ids"]) for c in v.get("challenges", []))}
    if method.threshold:
        d = _threshold_decision(store, inc.incident_id)
        case.update(status=d["status"], causes=d["causes"], category=d["category"],
                    suspected_root_cause=" + ".join(f"{a} at {b}" for a, b in sorted(d["causes"])) or None,
                    checks_requested=0, checks_obtained=0, new_observations=0)
    return case


def summarize(cases: list[dict]) -> dict:
    n = len(cases)
    if not n:
        return {}

    def rate(key, subset=None):
        sub = [c for c in (subset or cases) if c["score"][key] is not None]
        return {"count": sum(1 for c in sub if c["score"][key]), "of": len(sub)}

    faulty = [c for c in cases if not c["score"]["healthy_correct"] and c["truth"]]
    diagnosable = [c for c in faulty if c["score"]["diagnosable"] and not c["unmodeled"]]
    non_diag = [c for c in faulty if not c["score"]["diagnosable"] or c["unmodeled"]]
    healthy = [c for c in cases if not c["truth"]]
    multi = [c for c in cases if len(c["truth"]) > 1]
    secs = sorted(c["seconds"] for c in cases)
    return {
        "cases": n,
        "acceptable_outcome": rate("acceptable"),
        "exact_cause_on_diagnosable": rate("exact_cause", diagnosable),
        "fault_type_on_diagnosable": rate("fault_type_correct", diagnosable),
        "localization_on_diagnosable": rate("localization_correct", diagnosable),
        "confident_wrong_all": rate("confident_wrong"),
        "high_support_wrong_all": rate("high_support_wrong"),
        "abstained_when_not_diagnosable": rate("abstained", non_diag),
        "false_healthy_on_faulty": rate("false_healthy", faulty),
        "healthy_correct": rate("healthy_correct", healthy),
        "unknown_detected": rate("unknown_detected", [c for c in cases if c["unmodeled"]]),
        "multi_fault_full_recall": {"count": sum(1 for c in multi if c["score"]["multi_fault_recall"] == 1.0),
                                    "of": len(multi)},
        "checks_requested_total": sum(c["checks_requested"] for c in cases),
        "checks_obtained_total": sum(c["checks_obtained"] for c in cases),
        "seconds_median": secs[n // 2], "seconds_max": secs[-1],
    }


def code_fingerprint() -> dict:
    """Provenance of the code actually imported: HEAD, uncommitted changes, and a SHA-256 over the
    diagnosis-relevant source files as they were when evaluation started."""
    import hashlib

    import netcoop

    root = Path(netcoop.__file__).resolve().parent
    parts = ["engine", "agents", "knowledge", "evidence", "orchestration", "scenarios", "storage", "evaluation"]
    h = hashlib.sha256()
    files = sorted(p for d in parts for p in (root / d).rglob("*") if p.suffix in (".py", ".json"))
    files += [root / "ledger.py", root / "topology.py", root / "spec.py"]
    for p in files:
        h.update(p.relative_to(root).as_posix().encode())
        h.update(p.read_bytes().replace(b"\r\n", b"\n"))
    dirty = None
    try:
        out = subprocess.run(["git", "status", "--porcelain", "--", "src", "spec"], capture_output=True, text=True,
                             timeout=10, cwd=root.parents[1]).stdout
        dirty = sorted(line[3:] for line in out.splitlines() if line.strip())
    except OSError:
        pass
    return {"diagnosis_code_sha256": h.hexdigest(), "uncommitted_changes": dirty}


def git_commit() -> str | None:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=10).stdout.strip() or None
    except OSError:
        return None


def evaluate(sets: dict[str, Path], methods: list[Method] = METHODS, progress=print) -> dict:
    tmp = tempfile.mkdtemp(prefix="netcoop-eval-")

    def fresh_store(tag: str):
        """One small SQLite ledger per scenario (isolation + avoids an ever-growing file)."""
        eng = make_engine(f"sqlite:///{Path(tmp, f'{tag}.db').as_posix()}")
        migrate.upgrade(eng)
        return eng, SqlEvidenceStore(eng)
    results: dict = {
        "generated_by": "netcoop.evaluation.runner", "git_commit": git_commit(), "code": code_fingerprint(),
        "platform": f"{platform.system()} {platform.release()} / Python {platform.python_version()}",
        "knowledge": {"detector_rules": detector_rules()["version"], "fault_library": fault_library()["version"],
                      "sha256": knowledge_fingerprint()},
        "transport": "in-process (same specialist code and NDEP payloads as A2A; see integration tests)",
        "sets": {},
    }
    for set_name, base in sets.items():
        scen = list_scenarios(base)
        frozen_ok = None
        cases_by_method: dict[str, list[dict]] = {m.name: [] for m in methods}
        for sc in scen:
            sid = sc["scenario_id"]
            gt = json.loads((base / sid / "ground_truth.json").read_text(encoding="utf-8"))
            if "frozen_knowledge_sha256" in gt:
                frozen_ok = (frozen_ok is not False) and gt["frozen_knowledge_sha256"] == results["knowledge"]["sha256"]
            engine, store = fresh_store(f"{set_name}-{sid}")
            for m in methods:
                case = run_case(store, base, sid, m)
                case["truth"] = sorted(_truth(gt))
                case["unmodeled"] = any(t[0] == "UNMODELED_PATH_ISSUE" for t in case["truth"])
                case["score"] = score(case, gt, m)
                case["causes"] = sorted(case["causes"])
                cases_by_method[m.name].append(case)
            engine.dispose()
            for f in Path(tmp).glob(f"{set_name}-{sid}.db*"):
                f.unlink(missing_ok=True)
            progress(f"[{set_name}] {sid}: " + ", ".join(
                f"{m.name}={cases_by_method[m.name][-1]['status']}{'' if cases_by_method[m.name][-1]['score']['acceptable'] else '(x)'}"
                for m in methods))
        results["sets"][set_name] = {
            "path": str(base), "scenarios": len(scen),
            "knowledge_frozen_before_generation": frozen_ok,
            "summary": {m: summarize(c) for m, c in cases_by_method.items()},
            "cases": cases_by_method,
        }
    return results


def _fmt(x) -> str:
    if isinstance(x, dict) and "count" in x:
        return f"{x['count']}/{x['of']}" + (f" ({100 * x['count'] / x['of']:.0f}%)" if x["of"] else "")
    return str(x)


def to_markdown(res: dict) -> str:
    L = ["# NetCoop AI - evaluation results (generated)", "",
         f"Generated by `scripts/evaluate.py` from commit `{res['git_commit']}` on {res['platform']}.",
         f"Knowledge: {res['knowledge']['detector_rules']}, {res['knowledge']['fault_library']}. "
         f"Transport: {res['transport']}.", "",
         "All numbers below are computed from the JSON written next to this file. Data are synthetic; "
         "generator and engine were written by the same team, so these are internal consistency results, "
         "not an independent benchmark.", ""]
    rows = ["acceptable_outcome", "exact_cause_on_diagnosable", "fault_type_on_diagnosable",
            "localization_on_diagnosable", "confident_wrong_all", "high_support_wrong_all",
            "abstained_when_not_diagnosable", "false_healthy_on_faulty", "healthy_correct", "unknown_detected",
            "multi_fault_full_recall", "checks_requested_total", "checks_obtained_total", "seconds_median",
            "seconds_max"]
    for name, s in res["sets"].items():
        L += [f"## Set `{name}` ({s['scenarios']} scenarios)", ""]
        if s.get("knowledge_frozen_before_generation") is not None:
            L.append(f"Knowledge files unchanged since this set was generated: **{s['knowledge_frozen_before_generation']}**")
            L.append("")
        methods = list(s["summary"])
        L.append("| metric | " + " | ".join(methods) + " |")
        L.append("|---|" + "---|" * len(methods))
        for r in rows:
            L.append(f"| {r} | " + " | ".join(_fmt(s["summary"][m].get(r, "")) for m in methods) + " |")
        L.append("")
        bad = [(m, c) for m in ("C_stear_noverify", "D_full") for c in s["cases"].get(m, []) if not c["score"]["acceptable"]]
        if bad:
            L += ["Failure cases (C/D):", ""]
            for m, c in bad:
                L.append(f"- {m} `{c['scenario_id']}`: got {c['status']} {c['suspected_root_cause']}; truth {c['truth']}")
            L.append("")
    return "\n".join(L) + "\n"
