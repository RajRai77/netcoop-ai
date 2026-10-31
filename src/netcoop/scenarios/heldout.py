"""Held-out scenario specifications (randomized, generated AFTER the knowledge freeze).

Differs from the dev set in campus size (3x3 instead of 2x2), seeds, fault locations,
severities (including subtle sub-threshold cases), information conditions (what is
uploaded vs. only in an archive vs. absent), compound faults and unmodeled faults.

Ground-truth fields are derived from the injected faults and the information
condition only (never from the engine):
  diagnosable_initial      - the fault's signature source is in the initial upload
  diagnosable_with_archive - ... or in the recorded archive (reachable via verification)
  subtle                   - severity below the generator's nominal range
"""

from __future__ import annotations

import hashlib
import random
from pathlib import Path

from netcoop.knowledge import __file__ as _kfile

CAMPUS = {"n_dist": 3, "acc_per_dist": 3, "hosts_per_acc": 1}
ALL_SOURCES = ["dhcp-monitor", "dns-monitor", "nms", "probe-collector", "reachability-prober", "snmp-poller", "wlc"]
SIGNATURE_SOURCE = {
    "LINK_CONGESTION": "snmp-poller", "INTERFACE_DEGRADATION": "snmp-poller", "DEVICE_CPU_OVERLOAD": "snmp-poller",
    "DEVICE_DOWN": "nms", "WEAK_WIFI_SIGNAL": "wlc", "WIRELESS_INTERFERENCE": "wlc", "DNS_FAILURE": "dns-monitor",
    "DHCP_FAILURE": "dhcp-monitor", "UNMODELED_PATH_ISSUE": None,
}


def signature_source(fault: dict) -> str | None:
    """Collector that observes the fault's signature in the generated world. AP status comes from
    the wireless controller, switch status from the NMS (corrected for v3; v1/v2 annotated AP-down
    as NMS-observable although the generator never emitted AP status)."""
    if fault["type"] == "DEVICE_DOWN" and fault["location"].startswith("AP-"):
        return "wlc"
    return SIGNATURE_SOURCE[fault["type"]]


CONDITIONS = {
    "full": (ALL_SOURCES, []),
    "probes+archive": (["probe-collector", "reachability-prober"],
                       ["dhcp-monitor", "dns-monitor", "nms", "snmp-poller", "wlc"]),
    "probes-only": (["probe-collector", "reachability-prober"], []),
    "signature-in-archive": (None, None),  # everything except the signature source; that one is archived
}


def knowledge_fingerprint() -> dict:
    """SHA-256 of the canonical JSON content (independent of line endings / checkout OS)."""
    import json

    from netcoop.evidence.ids import canonical_json

    kdir = Path(_kfile).resolve().parent
    return {p.name: hashlib.sha256(canonical_json(json.loads(p.read_text(encoding="utf-8"))).encode()).hexdigest()
            for p in sorted(kdir.glob("*.json"))}


def _location(rng: random.Random, fault: str) -> str:
    d, a = rng.randint(1, 3), rng.randint(1, 3)
    if fault in ("LINK_CONGESTION", "INTERFACE_DEGRADATION"):
        return rng.choice([f"DIST-{d}:ge0/{a}", f"CORE-1:ge0/{d}", f"ACC-{d}-{a}:ge1/1"])
    if fault == "DEVICE_CPU_OVERLOAD":
        return rng.choice([f"ACC-{d}-{a}", f"DIST-{d}"])
    if fault == "DEVICE_DOWN":
        return rng.choice([f"ACC-{d}-{a}", f"DIST-{d}", f"AP-{d}-{a}"])
    if fault in ("WEAK_WIFI_SIGNAL", "WIRELESS_INTERFERENCE"):
        return f"AP-{d}-{a}"
    if fault == "DNS_FAILURE":
        return "DNS-1"
    if fault == "DHCP_FAILURE":
        return "DHCP-1"
    return f"ACC-{d}-{a}"


def heldout_specs(n: int = 60, seed: int = 20261101) -> list[dict]:
    rng = random.Random(seed)
    fp = knowledge_fingerprint()
    modeled = [f for f in SIGNATURE_SOURCE if f != "UNMODELED_PATH_ISSUE"]
    specs = []
    for i in range(n):
        kind = rng.choices(["single", "healthy", "compound", "unmodeled"], weights=[70, 10, 12, 8])[0]
        faults = []
        if kind == "single":
            ft = rng.choice(modeled)
            faults = [{"type": ft, "location": _location(rng, ft)}]
        elif kind == "compound":
            a, b = rng.sample(["LINK_CONGESTION", "INTERFACE_DEGRADATION", "DEVICE_CPU_OVERLOAD",
                               "WEAK_WIFI_SIGNAL", "WIRELESS_INTERFERENCE"], 2)
            la, lb = _location(rng, a), _location(rng, b)
            if la.split(":")[0] == lb.split(":")[0]:
                lb = _location(rng, b)
            faults = [{"type": a, "location": la}, {"type": b, "location": lb}]
        elif kind == "unmodeled":
            faults = [{"type": "UNMODELED_PATH_ISSUE", "location": _location(rng, "UNMODELED_PATH_ISSUE")}]
        subtle = rng.random() < 0.12
        for f in faults:
            f["severity"] = round(rng.uniform(0.35, 0.6), 2) if subtle else round(rng.uniform(0.8, 1.4), 2)
            f["onset_step"] = rng.randint(1, 5)
        cond = rng.choices(list(CONDITIONS), weights=[45, 25, 10, 20])[0]
        init, arch = CONDITIONS[cond]
        sig_sources = {signature_source(f) for f in faults if signature_source(f)}
        if cond == "signature-in-archive":
            arch = sorted(sig_sources) or ["snmp-poller"]
            init = [s for s in ALL_SOURCES if s not in arch]
        diag_init = bool(faults) and kind != "unmodeled" and sig_sources <= set(init)
        diag_arch = bool(faults) and kind != "unmodeled" and sig_sources <= set(init) | set(arch)
        spec = {
            "id": (f"H{i:03d}-{kind}" if seed == 20261101 else f"V{seed % 100:02d}-{i:03d}-{kind}"), "title": f"Held-out {kind} ({cond})", "seed": 5000 + i, "campus": CAMPUS,
            "faults": faults, "initial_sources": init, "archive_sources": arch,
            "spikes": [{"node": f"ACC-{rng.randint(1, 3)}-{rng.randint(1, 3)}", "step": rng.randint(2, 9)}]
            if rng.random() < 0.25 else [],
            "malformed": rng.random() < 0.15,
            "expected_status": "healthy" if kind == "healthy" else ("unknown_fault" if kind == "unmodeled"
                                                                  else ("diagnosed" if diag_arch else "ambiguous")),
            "expected_status_without_verification": "healthy" if kind == "healthy" else (
                "unknown_fault" if kind == "unmodeled" else ("diagnosed" if diag_init else "ambiguous")),
            "tags": [kind, cond] + (["subtle"] if subtle else []),
            "ground_truth_extra": {"condition": cond, "diagnosable_initial": diag_init,
                                   "diagnosable_with_archive": diag_arch, "subtle": subtle,
                                   "frozen_knowledge_sha256": fp},
            "limitations": ["Held-out synthetic scenario: same generator family as the dev set (different "
                            "topology size, seeds, severities and information conditions)."],
        }
        if kind == "healthy" or kind == "unmodeled":
            spec["expected_status_note"] = "status expected when the relevant data is fully observed"
        specs.append(spec)
    return specs
