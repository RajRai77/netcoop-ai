"""Deterministic synthetic campus scenario generator (data_mode = synthetic).

Writes, per scenario: manifest.json, topology.json, telemetry.json (initial upload),
archive.json (recorded observations available on request), ground_truth.json
(evaluator only; never read by the diagnosis code).

Fault effects are propagated with the generator's OWN parent/child tree logic, not
the engine's topology module, so labels do not simply mirror the engine's model.
Honest caveat: the same team wrote the generator and the engine, so this is not an
independent benchmark (see docs/21_EVALUATION.md).
"""

from __future__ import annotations

import csv
import io
import json
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

GENERATOR_VERSION = "netcoop-scengen/1"
STEP_S = 60
STEPS = 11


@dataclass
class Campus:
    nodes: dict[str, dict] = field(default_factory=dict)  # id -> {type, role}
    links: list[dict] = field(default_factory=list)
    parent: dict[str, str] = field(default_factory=dict)  # child -> parent (physical tree)
    uplink_iface: dict[str, tuple[str, str]] = field(default_factory=dict)  # child -> (parent, parent iface)
    segments: dict[str, str] = field(default_factory=dict)  # segment -> access switch

    def children(self, n: str) -> list[str]:
        return [c for c, p in self.parent.items() if p == n]

    def descendants(self, n: str) -> set[str]:
        out, stack = set(), [n]
        while stack:
            for c in self.children(stack.pop()):
                if c not in out:
                    out.add(c)
                    stack.append(c)
        return out


def build_campus(n_dist: int, acc_per_dist: int, hosts_per_acc: int, prefix: str = "") -> Campus:
    c = Campus()
    core = f"{prefix}CORE-1"
    c.nodes[core] = {"type": "device", "role": "core"}
    for svc in ("DNS-1", "DHCP-1"):
        sid = f"{prefix}{svc}"
        c.nodes[sid] = {"type": "service", "role": "server", "service_kind": svc.split("-")[0].lower()}
        c.links.append({"id": f"L-{core}-{sid}", "from": core, "to": sid, "type": "physical"})
    for d in range(1, n_dist + 1):
        dist = f"{prefix}DIST-{d}"
        c.nodes[dist] = {"type": "device", "role": "distribution"}
        c.parent[dist] = core
        c.uplink_iface[dist] = (core, f"ge0/{d}")
        c.links.append({"id": f"L-{core}-{dist}", "from": core, "to": dist, "type": "physical",
                        "from_interface": f"ge0/{d}"})
        for a in range(1, acc_per_dist + 1):
            acc = f"{prefix}ACC-{d}-{a}"
            c.nodes[acc] = {"type": "device", "role": "access"}
            c.parent[acc] = dist
            c.uplink_iface[acc] = (dist, f"ge0/{a}")
            c.links.append({"id": f"L-{dist}-{acc}", "from": dist, "to": acc, "type": "physical",
                            "from_interface": f"ge0/{a}"})
            ap = f"{prefix}AP-{d}-{a}"
            c.nodes[ap] = {"type": "ap", "role": "access"}
            c.parent[ap] = acc
            c.uplink_iface[ap] = (acc, "ge1/1")
            c.links.append({"id": f"L-{acc}-{ap}", "from": acc, "to": ap, "type": "physical",
                            "from_interface": "ge1/1"})
            seg = f"{prefix}SEG-{d}-{a}"
            c.nodes[seg] = {"type": "segment", "role": "client"}
            c.segments[seg] = acc
            c.parent[seg] = acc
            c.links.append({"id": f"L-{acc}-{seg}", "from": acc, "to": seg, "type": "logical"})
            for svc in ("DNS-1", "DHCP-1"):
                c.links.append({"id": f"D-{seg}-{svc}", "from": seg, "to": f"{prefix}{svc}", "type": "dependency"})
            for h in range(1, hosts_per_acc + 1):
                host = f"{prefix}H-{d}-{a}-{h}"
                c.nodes[host] = {"type": "host", "role": "client"}
                c.parent[host] = acc
                c.links.append({"id": f"L-{acc}-{host}", "from": acc, "to": host, "type": "physical"})
    return c


def topology_doc(c: Campus, snap_id: str, observed_at: str) -> dict:
    return {
        "schema_version": "1.1.0", "topology_snapshot_id": snap_id, "kind": "synthetic", "observed_at": observed_at,
        "nodes": [{"id": n, **v} for n, v in sorted(c.nodes.items())],
        "links": c.links,
        "limitations": ["Synthetic campus topology produced by " + GENERATOR_VERSION + "; intended = observed by construction"],
    }


# -- telemetry ----------------------------------------------------------------------------

def _ts(t0: datetime, k: int) -> str:
    return (t0 + timedelta(seconds=STEP_S * k)).strftime("%Y-%m-%dT%H:%M:%SZ")


class Telemetry:
    """Builds per-source record lists. Values come from baselines + injected faults."""

    def __init__(self, c: Campus, rng: random.Random, t0: datetime):
        self.c, self.rng, self.t0 = c, rng, t0
        self.records: dict[str, list[dict]] = {s: [] for s in
                                               ("probe-collector", "snmp-poller", "wlc", "reachability-prober",
                                                "dns-monitor", "dhcp-monitor", "nms")}
        self.mods: dict[tuple[str, str], list] = {}  # (node or iface key, metric) -> [(onset_k, fn)]
        self.down: dict[str, int] = {}  # node -> onset step (device down)
        self.counter: dict[tuple[str, str], int] = {}

    def mod(self, key: str, metric: str, onset: int, fn) -> None:
        self.mods.setdefault((key, metric), []).append((onset, fn))

    def val(self, key: str, metric: str, k: int, base: float) -> float:
        v = base
        for onset, fn in self.mods.get((key, metric), []):
            if k >= onset:
                v = fn(v)
        return v

    def is_down(self, n: str, k: int) -> bool:
        cur = n
        while cur is not None:
            if cur in self.down and k >= self.down[cur]:
                return True
            cur = self.c.parent.get(cur)
        return False

    def generate(self) -> None:
        r, c = self.rng, self.c
        for k in range(STEPS):
            ts = _ts(self.t0, k)
            for n, meta in sorted(c.nodes.items()):
                if meta["type"] in ("device", "ap") and meta["role"] != "core" or meta["type"] == "ap":
                    if not self.is_down(n, k):
                        ms = [
                            {"metric": "latency", "value": round(self.val(n, "latency", k, r.uniform(4, 15)), 2), "unit": "ms", "kind": "gauge"},
                            {"metric": "jitter", "value": round(self.val(n, "jitter", k, r.uniform(0.5, 4)), 2), "unit": "ms", "kind": "gauge"},
                            {"metric": "packet_loss", "value": round(min(100, self.val(n, "packet_loss", k, r.uniform(0, 0.2))), 3), "unit": "percent", "kind": "gauge"},
                        ]
                    else:  # probe still runs from the core; total loss, no RTT
                        ms = [{"metric": "packet_loss", "value": 100.0, "unit": "percent", "kind": "gauge"}]
                    self.records["probe-collector"].append(
                        {"record_id": f"probe-{n}-{k}", "subject": {"device_id": n}, "observed_at": ts, "measurements": ms})
                if meta["type"] in ("device", "ap", "host", "service"):
                    sub = {"service_id": n} if meta["type"] == "service" else {"device_id": n}
                    self.records["reachability-prober"].append(
                        {"record_id": f"reach-{n}-{k}", "subject": sub, "observed_at": ts,
                         "measurements": [{"metric": "reachability", "value": not self.is_down(n, k), "unit": "boolean", "kind": "state"}]})
                if meta["type"] == "device":
                    if self.is_down(n, k):
                        if n in self.down:  # the NMS marks the failed device itself as down
                            self.records["nms"].append({"record_id": f"nms-{n}-{k}", "subject": {"device_id": n}, "observed_at": ts,
                                                        "measurements": [{"metric": "device_status", "value": "down", "unit": "state", "kind": "state"}]})
                        continue  # cannot be polled
                    self.records["snmp-poller"].append({"record_id": f"snmp-{n}-{k}", "subject": {"device_id": n}, "observed_at": ts, "measurements": [
                        {"metric": "cpu_utilization", "value": round(min(100, self.val(n, "cpu_utilization", k, r.uniform(8, 40))), 1), "unit": "percent", "kind": "gauge"},
                        {"metric": "memory_utilization", "value": round(r.uniform(30, 60), 1), "unit": "percent", "kind": "gauge"},
                        {"metric": "device_status", "value": "up", "unit": "state", "kind": "state"}]})
                    self.records["nms"].append({"record_id": f"nms-{n}-{k}", "subject": {"device_id": n}, "observed_at": ts,
                                                "measurements": [{"metric": "device_status", "value": "up", "unit": "state", "kind": "state"}]})
                if meta["type"] == "ap" and n in self.down and k >= self.down[n]:
                    # the wireless controller reports the AP it lost as down (only the failed AP itself,
                    # same convention as the NMS for switches)
                    self.records["wlc"].append({"record_id": f"wlc-status-{n}-{k}", "subject": {"device_id": n}, "observed_at": ts,
                                                "measurements": [{"metric": "device_status", "value": "down", "unit": "state", "kind": "state"}]})
                if meta["type"] == "ap" and not self.is_down(n, k):
                    self.records["wlc"].append({"record_id": f"wlc-{n}-{k}", "subject": {"device_id": n}, "observed_at": ts, "measurements": [
                        {"metric": "device_status", "value": "up", "unit": "state", "kind": "state"},
                        {"metric": "rssi", "value": round(self.val(n, "rssi", k, r.uniform(-64, -50)), 1), "unit": "dBm", "kind": "gauge"},
                        {"metric": "snr", "value": round(self.val(n, "snr", k, r.uniform(28, 40)), 1), "unit": "dB", "kind": "gauge"},
                        {"metric": "wireless_retry_rate", "value": round(min(100, self.val(n, "wireless_retry_rate", k, r.uniform(2, 8))), 1), "unit": "percent", "kind": "gauge"}]})
            for child, (dev, iface) in sorted(c.uplink_iface.items()):
                if self.is_down(dev, k):
                    continue
                key = f"{dev}:{iface}"
                crc = self.counter.get((key, "crc"), r.randint(0, 50))
                crc += int(self.val(key, "crc_increment", k, r.choice([0, 0, 1])))
                qd = self.counter.get((key, "qd"), r.randint(0, 20))
                qd += int(self.val(key, "qd_increment", k, r.choice([0, 0, 0, 1])))
                self.counter[(key, "crc")], self.counter[(key, "qd")] = crc, qd
                link_down = self.is_down(child, k) and child in self.down
                self.records["snmp-poller"].append({"record_id": f"snmp-{key}-{k}", "subject": {"device_id": dev, "interface_id": iface},
                                                    "observed_at": ts, "measurements": [
                    {"metric": "link_utilization", "value": round(min(100, self.val(key, "link_utilization", k, r.uniform(12, 55))) if not link_down else 0.0, 1), "unit": "percent", "kind": "gauge"},
                    {"metric": "crc_errors", "value": crc, "unit": "count", "kind": "cumulative_counter"},
                    {"metric": "queue_drops", "value": qd, "unit": "count", "kind": "cumulative_counter"},
                    {"metric": "interface_status", "value": "down" if link_down else "up", "unit": "state", "kind": "state"}]})
            for seg in sorted(c.segments):
                if self.is_down(seg, k):
                    continue
                self.records["dns-monitor"].append({"record_id": f"dns-{seg}-{k}", "subject": {"segment_id": seg}, "observed_at": ts, "measurements": [
                    {"metric": "dns_query_failure_rate", "value": round(min(100, self.val(seg, "dns_query_failure_rate", k, r.uniform(0, 1))), 2), "unit": "percent", "kind": "gauge"}]})
                self.records["dhcp-monitor"].append({"record_id": f"dhcp-{seg}-{k}", "subject": {"segment_id": seg}, "observed_at": ts, "measurements": [
                    {"metric": "dhcp_lease_failure_rate", "value": round(min(100, self.val(seg, "dhcp_lease_failure_rate", k, r.uniform(0, 1))), 2), "unit": "percent", "kind": "gauge"}]})


def _affected_probes(c: Campus, node: str) -> list[str]:
    """Probe targets whose path traverses `node` (node itself + descendants with probes)."""
    out = [node] + sorted(c.descendants(node))
    return [n for n in out if c.nodes[n]["type"] in ("device", "ap") and c.nodes[n]["role"] != "core"]


def inject(t: Telemetry, fault: dict, onset: int, rng: random.Random) -> None:
    c, ft, loc = t.c, fault["type"], fault["location"]
    up = lambda lo, hi: (lambda v: v + rng.uniform(lo, hi))  # noqa: E731
    setv = lambda lo, hi: (lambda v: rng.uniform(lo, hi))  # noqa: E731
    sev = fault.get("severity", 1.0)
    if ft in ("LINK_CONGESTION", "INTERFACE_DEGRADATION"):
        dev, iface = loc.split(":", 1)
        child = next(ch for ch, (p, i) in c.uplink_iface.items() if p == dev and i == iface)
        if ft == "LINK_CONGESTION":
            t.mod(loc, "link_utilization", onset, setv(88 + 4 * sev, 99))
            t.mod(loc, "qd_increment", onset, setv(150 * sev, 500 * sev))
            for n in _affected_probes(c, child):
                t.mod(n, "latency", onset, up(110 * sev, 260 * sev))
                t.mod(n, "jitter", onset, up(30 * sev, 60 * sev))
                t.mod(n, "packet_loss", onset, up(1.2 * sev, 4 * sev))
        else:
            t.mod(loc, "crc_increment", onset, setv(30 * sev, 120 * sev))
            for n in _affected_probes(c, child):
                t.mod(n, "packet_loss", onset, up(2 * sev, 6 * sev))
                t.mod(n, "latency", onset, up(5, 40))
    elif ft == "DEVICE_CPU_OVERLOAD":
        t.mod(loc, "cpu_utilization", onset, setv(92 + 2 * min(sev, 1), 99.5))
        for n in _affected_probes(c, loc):
            t.mod(n, "latency", onset, up(120 * sev, 300 * sev))
            t.mod(n, "jitter", onset, up(30 * sev, 70 * sev))
    elif ft == "DEVICE_DOWN":
        t.down[loc] = onset
    elif ft == "WEAK_WIFI_SIGNAL":
        t.mod(loc, "rssi", onset, setv(-88, -78))
        t.mod(loc, "snr", onset, setv(8, 16))
        t.mod(loc, "wireless_retry_rate", onset, setv(22, 40))
        t.mod(loc, "packet_loss", onset, up(2 * sev, 5 * sev))
        t.mod(loc, "latency", onset, up(60, 160))
    elif ft == "WIRELESS_INTERFERENCE":
        t.mod(loc, "snr", onset, setv(9, 17))
        t.mod(loc, "wireless_retry_rate", onset, setv(24, 45))
        t.mod(loc, "packet_loss", onset, up(2 * sev, 5 * sev))
    elif ft == "DNS_FAILURE":
        for seg in c.segments:
            t.mod(seg, "dns_query_failure_rate", onset, setv(30 * sev, 70 * sev))
    elif ft == "DHCP_FAILURE":
        for seg in c.segments:
            t.mod(seg, "dhcp_lease_failure_rate", onset, setv(40 * sev, 90 * sev))
    elif ft == "UNMODELED_PATH_ISSUE":  # e.g. MTU/route flap: user-visible symptoms only
        for n in _affected_probes(c, loc):
            t.mod(n, "latency", onset, up(150, 300))
            t.mod(n, "packet_loss", onset, up(3, 8))
    else:
        raise ValueError(f"unknown injected fault {ft}")


def _batch(source: str, records: list[dict], data_mode: str = "synthetic") -> dict:
    stype = {"probe-collector": "active-probe", "snmp-poller": "snmp", "wlc": "wireless-controller",
             "reachability-prober": "icmp-prober", "dns-monitor": "service-monitor",
             "dhcp-monitor": "service-monitor", "nms": "nms"}[source]
    return {"schema_version": "1.0.0", "batch_id": f"{source}-batch",
            "source": {"source_id": source, "data_mode": data_mode, "source_type": stype}, "records": records}


def write_scenario(out_dir: Path, spec: dict, split: str = "dev") -> Path:
    rng = random.Random(spec["seed"])
    sizes = spec.get("campus", {"n_dist": 2, "acc_per_dist": 2, "hosts_per_acc": 2})
    c = build_campus(**sizes)
    t_end = datetime(2026, 10, 31, 10, 0, 0, tzinfo=timezone.utc)
    t0 = t_end - timedelta(seconds=STEP_S * (STEPS - 1))
    tel = Telemetry(c, rng, t0)
    for f in spec.get("faults", []):
        inject(tel, f, f.get("onset_step", 3), rng)
    tel.generate()

    # noise / data-quality perturbations (applied to the initial upload only)
    initial_sources = spec.get("initial_sources") or sorted(tel.records)
    archive_sources = spec.get("archive_sources", [])
    initial = {s: list(tel.records[s]) for s in initial_sources}
    archive = {s: list(tel.records[s]) for s in archive_sources}
    for drop in spec.get("drop_records", []):  # e.g. {"source": "snmp-poller", "match": "crc"}
        for d in (initial, archive):
            if drop["source"] in d:
                d[drop["source"]] = [r for r in d[drop["source"]] if drop["match"] not in r["record_id"]]
    extra_bad: list[dict] = []
    for spike in spec.get("spikes", []):  # single anomalous sample - must not become a diagnosis
        recs = initial["probe-collector"]
        tgt = [r for r in recs if r["subject"].get("device_id") == spike["node"]][spike.get("step", 5)]
        for m in tgt["measurements"]:
            if m["metric"] == "latency":
                m["value"] = round(m["value"] + 400, 2)
    if spec.get("malformed"):
        extra_bad = [
            {"record_id": "bad-1", "subject": {"device_id": "ACC-1-1"}, "observed_at": _ts(t0, 9),
             "measurements": [{"metric": "packet_loss", "value": 0.02}]},  # no unit -> rejected
            {"record_id": "bad-2", "subject": {"device_id": "ACC-1-1"}, "observed_at": "2026-10-31 09:59:00",
             "measurements": [{"metric": "latency", "value": 12, "unit": "ms", "kind": "gauge"}]},  # no timezone
            {"record_id": "bad-3", "subject": {"device_id": "ACC-1-1"}, "observed_at": _ts(t0, 9),
             "measurements": [{"metric": "latency", "value": "fast", "unit": "ms", "kind": "gauge"}]},
            {"record_id": "bad-4", "subject": {"device_id": "GHOST-9"}, "observed_at": _ts(t0, 9),
             "measurements": [{"metric": "latency", "value": 900, "unit": "ms", "kind": "gauge"}]},  # unknown device
            {"record_id": "stale-1", "subject": {"device_id": "ACC-2-1"}, "observed_at": _ts(t0 - timedelta(hours=2), 0),
             "measurements": [{"metric": "latency", "value": 950, "unit": "ms", "kind": "gauge"}]},  # stale
        ]
    batches = [_batch(s, initial[s]) for s in sorted(initial) if initial[s]]
    if extra_bad:
        batches.append(_batch("probe-collector", extra_bad) | {"batch_id": "probe-collector-late-batch"})

    sid = spec["id"]
    d = out_dir / sid
    d.mkdir(parents=True, exist_ok=True)
    snap = f"TOPO-{sid}"
    (d / "topology.json").write_text(json.dumps(topology_doc(c, snap, _ts(t0, 0)), separators=(",", ":")), encoding="utf-8")
    telemetry_file, profile = "telemetry.json", None
    if spec.get("csv_profile"):
        # vendor CSV export of the probe + interface data (declared profile campus-snmp-csv)
        telemetry_file, profile = "telemetry.csv", spec["csv_profile"]
        (d / telemetry_file).write_text(_vendor_csv(tel, t0), encoding="utf-8")
        (d / "telemetry.json").unlink(missing_ok=True)
    else:
        (d / telemetry_file).write_text(json.dumps({"batches": batches}, separators=(",", ":")), encoding="utf-8")
    if archive:
        (d / "archive.json").write_text(json.dumps({"schema_version": "1.0.0", "archive_id": f"ARCHIVE-{sid}",
                                                    "batches": [_batch(s, archive[s]) for s in sorted(archive)]},
                                                   indent=1), encoding="utf-8")
    else:
        (d / "archive.json").unlink(missing_ok=True)
    gt = {"scenario_id": sid, "faults": [{"fault_type": f["type"], "location": f["location"]} for f in spec.get("faults", [])],
          "expected_status": spec["expected_status"],
          "expected_status_without_verification": spec.get("expected_status_without_verification", spec["expected_status"]),
          "notes": spec.get("notes", ""), "generator": GENERATOR_VERSION, "seed": spec["seed"],
          **spec.get("ground_truth_extra", {})}
    (d / "ground_truth.json").write_text(json.dumps(gt, indent=1), encoding="utf-8")
    manifest = {
        "schema_version": "1.1.0", "scenario_id": sid, "title": spec["title"], "data_mode": "synthetic",
        "source_description": f"Synthetic campus telemetry from {GENERATOR_VERSION} (seed {spec['seed']}); "
                              "fault injected by the generator; not real network data.",
        "telemetry_file": telemetry_file, "telemetry_profile": profile, "topology_file": "topology.json",
        "archive_file": "archive.json" if archive else None, "ground_truth_file": "ground_truth.json",
        "time_window": {"start": _ts(t0, 0), "end": _ts(t0, STEPS - 1)},
        "reference_time": (t_end + timedelta(seconds=5)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "seed": spec["seed"], "split": split, "tags": spec.get("tags", []),
        # The generator spec is NOT copied here: it contains the injected faults (labels),
        # and the manifest is readable by the diagnosis side. Labels live only in ground_truth.json.
        "generator": {"version": GENERATOR_VERSION, "seed": spec["seed"]},
        "limitations": ["Synthetic data; values and fault signatures follow the generator's model",
                        "Generator and diagnosis engine were written by the same team (not an independent benchmark)"]
                       + spec.get("limitations", []),
    }
    (d / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    return d


def _vendor_csv(tel: Telemetry, t0: datetime) -> str:
    """Probe + interface data as a vendor CSV (IST times without offset, loss as ratio, Mbps)."""
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["poll_id", "poll_time", "hostname", "ifName", "ifUtilPct", "lossRatio", "rttMs", "outMbps",
                "inErrors", "poller_host", "vendor_note"])
    ist = timezone(timedelta(hours=5, minutes=30))
    for r in tel.records["snmp-poller"]:
        if "interface_id" not in r["subject"]:
            continue
        ts = datetime.fromisoformat(r["observed_at"]).astimezone(ist).strftime("%Y-%m-%d %H:%M:%S")
        m = {x["metric"]: x["value"] for x in r["measurements"]}
        w.writerow([r["record_id"], ts, r["subject"]["device_id"], r["subject"]["interface_id"],
                    m["link_utilization"], "", "", round(m["link_utilization"] * 10, 1), m["crc_errors"], "poller-a", ""])
    for r in tel.records["probe-collector"]:
        ts = datetime.fromisoformat(r["observed_at"]).astimezone(ist).strftime("%Y-%m-%d %H:%M:%S")
        m = {x["metric"]: x["value"] for x in r["measurements"]}
        w.writerow([r["record_id"], ts, r["subject"]["device_id"], "", "", round(m["packet_loss"] / 100, 5),
                    m.get("latency", ""), "", "", "poller-a", "probe"])
    return buf.getvalue()


def load_scenario(d: Path) -> dict:
    return json.loads((d / "manifest.json").read_text(encoding="utf-8"))
