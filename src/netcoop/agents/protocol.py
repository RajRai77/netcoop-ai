"""NDEP agent envelopes and the specialist catalogue (transport-independent).

The same JSON text is carried in-process (unit tests / evaluation baselines) or
inside A2A messages and artifacts (deployed and integration runs).
"""

from __future__ import annotations

import json
from typing import Any

from netcoop.spec import validator

MEDIA_TYPE = "application/vnd.netcoop.ndep+json"
AGENT_VERSION = "0.1.0"
PROTOCOL_VERSION = "1.0.0"

SPECIALISTS: dict[str, dict] = {
    "performance-agent": {
        "name": "NetCoop Performance Agent",
        "description": "Latency, jitter, packet loss, throughput, link utilization and queue-drop analysis.",
        "metrics": ["latency", "jitter", "packet_loss", "throughput", "link_utilization", "queue_drops_rate",
                    "queue_drops"],
        "uses_topology": False,
    },
    "infrastructure-agent": {
        "name": "NetCoop Infrastructure Agent",
        "description": "Device CPU/memory, interface errors and state, wireless signal/SNR/retries.",
        "metrics": ["cpu_utilization", "memory_utilization", "crc_errors", "interface_errors", "device_status",
                    "interface_status", "rssi", "snr", "wireless_retry_rate"],
        "uses_topology": False,
    },
    "connectivity-agent": {
        "name": "NetCoop Connectivity & Services Agent",
        "description": "Reachability, DNS/DHCP service health and topology-based affected-scope analysis.",
        "metrics": ["reachability", "dns_query_failure_rate", "dhcp_lease_failure_rate"],
        "uses_topology": True,
    },
}


class ProtocolError(ValueError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


def dumps(obj: Any) -> str:
    # allow_nan=False: NDEP never carries NaN/Infinity on the wire.
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def loads(text: str, schema: str) -> dict:
    def no_dups(pairs):
        d = {}
        for k, v in pairs:
            if k in d:
                raise ProtocolError("MALFORMED", f"duplicate key {k!r}")
            d[k] = v
        return d

    def bad_const(c):
        raise ProtocolError("MALFORMED", f"non-finite number {c} not allowed")

    try:
        doc = json.loads(text, object_pairs_hook=no_dups, parse_constant=bad_const)
    except ProtocolError:
        raise
    except ValueError as exc:
        raise ProtocolError("MALFORMED", f"not valid JSON: {exc}") from None
    errors = [f"{'/'.join(map(str, e.absolute_path)) or '<root>'}: {e.message}" for e in validator(schema).iter_errors(doc)]
    if errors:
        raise ProtocolError("SCHEMA_INVALID", "; ".join(errors[:5]))
    return doc
