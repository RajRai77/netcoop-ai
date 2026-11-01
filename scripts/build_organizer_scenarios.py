"""Build reproducible scenarios from the organizer's sample input generator (PS section 5).

    uv run python scripts/build_organizer_scenarios.py          # writes data/scenarios/ORG-*/

The generator (data/organizer/ps_sample_generator.py) is used exactly as supplied. This harness only:
  * seeds Python's `random` module (the generator draws all values from it);
  * fixes the clock: the generator calls datetime.utcnow(); the module-level name `datetime` is pointed at a
    clock that returns the scheduled poll time, so files are reproducible;
  * selects devices by rejection sampling: the generator picks SW_CAMPUS_1..10 at random, so calls are repeated
    until the wanted device comes out, and the other outputs are discarded.
No value produced by the generator is changed, except in ORG-04, whose mutations are listed in its manifest.

The generator provides no topology. Each scenario carries an ASSUMED star topology (ASSUMED-CORE plus the ten
switches) so impact scope can be shown; this is stated in the topology and manifest limitations.
"""

from __future__ import annotations

import contextlib
import copy
import datetime as _dt
import hashlib
import importlib.util
import io
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GEN_FILE = ROOT / "data" / "organizer" / "ps_sample_generator.py"
OUT = ROOT / "data" / "scenarios"
DEVICES = [f"SW_CAMPUS_{i}" for i in range(1, 11)]
START = _dt.datetime(2026, 10, 31, 9, 50, 0)
POLLS = 10          # one poll per device per minute, 09:50 .. 09:59
FAULT_FROM = 5      # fault visible from 09:55
REFERENCE_TIME = "2026-10-31T10:00:05Z"


class _Clock:
    now = START

    @classmethod
    def utcnow(cls):
        return cls.now


def load_generator():
    spec = importlib.util.spec_from_file_location("ps_sample_generator", GEN_FILE)
    mod = importlib.util.module_from_spec(spec)
    with contextlib.redirect_stdout(io.StringIO()):  # the file prints an example record on import
        spec.loader.exec_module(mod)
    mod.datetime = _Clock  # fixed clock; generator code untouched
    return mod


def records(mod, seed: int, fault: tuple[str, str] | None) -> list[dict]:
    random.seed(seed)
    out = []
    for poll in range(POLLS):
        _Clock.now = START + _dt.timedelta(minutes=poll)
        for dev in DEVICES:
            ftype = fault[0] if fault and dev == fault[1] and poll >= FAULT_FROM else "normal"
            while True:  # rejection sampling on the generator's own device choice
                r = mod.generate_telemetry(ftype)
                if r["device_id"] == dev:
                    out.append(r)
                    break
    return out


def topology(sid: str) -> dict:
    return {
        "schema_version": "1.1.0", "topology_snapshot_id": f"TOPO-{sid}", "kind": "modeled",
        "observed_at": "2026-10-31T09:50:00Z",
        "nodes": [{"id": "ASSUMED-CORE", "type": "device", "role": "core"}]
                 + [{"id": d, "type": "device", "role": "access"} for d in DEVICES],
        "links": [{"id": f"L-CORE-{d}", "from": "ASSUMED-CORE", "to": d, "type": "physical"} for d in DEVICES],
        "limitations": ["Assumed star topology authored by NetCoop: the organizer's generator provides no topology. "
                        "ASSUMED-CORE is a placeholder node without telemetry."],
    }


SCENARIOS = [
    {"id": "ORG-01-normal", "title": "Organizer data: normal operation (10 campus switches)", "seed": 9001,
     "fault": None, "tags": ["organizer", "healthy"]},
    {"id": "ORG-02-latency-spike", "title": "Organizer data: latency spike on SW_CAMPUS_7", "seed": 9002,
     "fault": ("latency_spike", "SW_CAMPUS_7"), "tags": ["organizer", "latency"]},
    {"id": "ORG-03-hardware-failure", "title": "Organizer data: hardware failure on SW_CAMPUS_3", "seed": 9003,
     "fault": ("hardware_failure", "SW_CAMPUS_3"), "tags": ["organizer", "hardware"]},
    {"id": "ORG-04-schema-drift", "title": "Organizer data with schema drift: renamed field, bad units, missing IDs",
     "seed": 9002, "fault": ("latency_spike", "SW_CAMPUS_7"), "tags": ["organizer", "interop", "robustness"],
     "mutate": True},
]

MUTATIONS = [  # record numbers are 0-based positions in the clean list, before the duplicate is inserted
    "record 3: metrics.latency_ms renamed to metrics.latency_s and divided by 1000 (unit drift) -> UNMAPPED_FIELD",
    "record 11: device_id removed -> record rejected (no subject)",
    "record 21: timestamp replaced by '31/10/2026 09:52' (not ISO 8601) -> record rejected",
    "record 33: metrics.packet_loss_pct given as the string '0.0%' -> measurement rejected (type mismatch)",
    "record 41: exact duplicate of record 40 appended -> reported as duplicate, counted once",
    "record 47: metrics.cpu_utilization_pct = 140 (impossible percentage) -> measurement rejected (out of range)",
]


def mutate(recs: list[dict]) -> list[dict]:
    r = copy.deepcopy(recs)
    m = r[3]["metrics"]
    m["latency_s"] = round(m.pop("latency_ms") / 1000, 5)
    r[11].pop("device_id")
    r[21]["timestamp"] = "31/10/2026 09:52"
    r[33]["metrics"]["packet_loss_pct"] = "0.0%"
    r[47]["metrics"]["cpu_utilization_pct"] = 140
    r.insert(41, copy.deepcopy(r[40]))
    return r


def main() -> int:
    mod = load_generator()
    gen_sha = hashlib.sha256(GEN_FILE.read_bytes()).hexdigest()
    for s in SCENARIOS:
        d = OUT / s["id"]
        d.mkdir(parents=True, exist_ok=True)
        recs = records(mod, s["seed"], s["fault"])
        if s.get("mutate"):
            recs = mutate(recs)
        (d / "telemetry.json").write_text(json.dumps(recs, indent=1) + "\n", encoding="utf-8")
        (d / "topology.json").write_text(json.dumps(topology(s["id"]), indent=1) + "\n", encoding="utf-8")
        fault = s["fault"]
        gt = {
            "scenario_id": s["id"], "faults": [],
            "organizer_faults": [{"generator_fault_type": fault[0], "device_id": fault[1],
                                  "from": (START + _dt.timedelta(minutes=FAULT_FROM)).isoformat() + "Z"}] if fault else [],
            "expected": ({"status": "healthy"} if not fault else
                         {"status_not": "healthy", "anomalies_only_at": fault[1], "root_cause_location_if_diagnosed": fault[1]}),
            "notes": "The generator's fault types are symptom classes, not root causes in the NetCoop fault library, so "
                     "only fault presence and the faulted device are used as ground truth. Written by the harness "
                     "before any diagnosis was run.",
        }
        (d / "ground_truth.json").write_text(json.dumps(gt, indent=1) + "\n", encoding="utf-8")
        limitations = [
            "Synthetic data from the organizer's sample generator (PS section 5), not real network data",
            "The generator provides no topology; the star topology is an assumption by NetCoop",
            "queue_drops, interface_errors and status are not used: their meaning is not defined by the generator",
        ]
        if s.get("mutate"):
            limitations.append("Six records were deliberately corrupted by NetCoop to test robustness (see mutations)")
        manifest = {
            "schema_version": "1.1.0", "scenario_id": s["id"], "title": s["title"], "data_mode": "synthetic",
            "source_description": "Records produced by the organizer's sample input generator (PS section 5), "
                                  "values unmodified; seeded, fixed clock, device chosen by rejection sampling.",
            "telemetry_file": "telemetry.json", "telemetry_profile": "organizer-colab-json",
            "topology_file": "topology.json", "archive_file": None, "ground_truth_file": "ground_truth.json",
            "time_window": {"start": "2026-10-31T09:50:00Z", "end": "2026-10-31T10:00:00Z"},
            "reference_time": REFERENCE_TIME, "seed": s["seed"], "split": "organizer", "tags": s["tags"],
            "generator": {"version": "ps-sample-generator (organizer, unmodified)", "file": "data/organizer/ps_sample_generator.py",
                          "sha256": gen_sha, "harness": "scripts/build_organizer_scenarios.py", "seed": s["seed"],
                          **({"mutations": MUTATIONS} if s.get("mutate") else {})},
            "limitations": limitations,
        }
        (d / "manifest.json").write_text(json.dumps(manifest, indent=1) + "\n", encoding="utf-8")
        print(f"{s['id']}: {len(recs)} records")
    return 0


if __name__ == "__main__":
    sys.exit(main())
