"""Topology graph utilities: impact scope with redundant paths respected.

Impact scope of a component X = X itself, plus every node that loses all paths to
the upstream roots (nodes with role 'core') when X is removed, plus dependents of
any service inside that set (dependency links). With redundancy, removing X may
disconnect nobody, so X explains nothing beyond itself - that is intended.

The graph is a model of *candidate propagation paths*, not a verified causal
mechanism (docs/05). Without core roots, scopes degrade to the component itself
and callers must report that limitation.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import networkx as nx

from netcoop.evidence.models import Subject, TopologySnapshot

PHYSICAL_TYPES = {"physical", "logical", "routing"}


@dataclass(frozen=True)
class Location:
    """Where a fault hypothesis is placed. kind: node | interface | link."""

    kind: str
    node: str | None = None
    interface: str | None = None
    link: str | None = None

    @property
    def key(self) -> str:
        if self.kind == "interface":
            return f"{self.node}:{self.interface}"
        if self.kind == "link":
            return f"link:{self.link}"
        return str(self.node)

    def subject(self) -> dict:
        if self.kind == "interface":
            return {"device_id": self.node, "interface_id": self.interface}
        if self.kind == "link":
            return {"link_id": self.link}
        return {"device_id": self.node}


def location_of(subject: Subject) -> Location:
    if subject.device_id and subject.interface_id:
        return Location("interface", node=subject.device_id, interface=subject.interface_id)
    if subject.link_id and not (subject.device_id or subject.service_id or subject.segment_id):
        return Location("link", link=subject.link_id)
    return Location("node", node=subject.device_id or subject.service_id or subject.segment_id)


class TopologyGraph:
    def __init__(self, snapshot: TopologySnapshot | None):
        self.snapshot = snapshot
        self.g = nx.MultiGraph()
        self.dependents: dict[str, set[str]] = {}
        self.links: dict[str, tuple[str, str, str | None, str | None]] = {}
        self.node_types: dict[str, str] = {}
        self.service_kinds: dict[str, str] = {}
        self.roots: set[str] = set()
        if snapshot is None:
            return
        for n in snapshot.nodes:
            self.g.add_node(n.id)
            self.node_types[n.id] = n.type
            if n.service_kind:
                self.service_kinds[n.id] = n.service_kind
            if n.role == "core":
                self.roots.add(n.id)
        for lk in snapshot.links:
            self.links[lk.id] = (lk.from_, lk.to, lk.from_interface, lk.to_interface)
            if lk.type == "dependency":
                # 'from' depends on 'to' (e.g. segment -> DNS service)
                self.dependents.setdefault(lk.to, set()).add(lk.from_)
            elif lk.type in PHYSICAL_TYPES:
                self.g.add_edge(lk.from_, lk.to, key=lk.id)

    @property
    def available(self) -> bool:
        return self.snapshot is not None

    @property
    def has_roots(self) -> bool:
        return bool(self.roots)

    def snapshot_id(self) -> str | None:
        return self.snapshot.topology_snapshot_id if self.snapshot else None

    def link_for_interface(self, device: str, interface: str) -> str | None:
        for lid, (a, b, ai, bi) in self.links.items():
            if (a == device and ai == interface) or (b == device and bi == interface):
                return lid
        return None

    def _reachable(self, h: nx.MultiGraph) -> set[str]:
        reach: set[str] = set()
        for r in self.roots:
            if r in h:
                reach |= nx.node_connected_component(h, r)
        return reach

    def _disconnected_without(self, h: nx.MultiGraph) -> set[str]:
        """Nodes connected to a root in the full graph that lose that connection in h.

        Nodes never physically connected to a root (e.g. services modelled only by
        dependency links) are not 'disconnected' by any single failure."""
        if not hasattr(self, "_baseline_reach"):
            self._baseline_reach = self._reachable(self.g)
        return (self._baseline_reach & set(h.nodes)) - self._reachable(h)

    def _with_dependents(self, nodes: set[str]) -> set[str]:
        out = set(nodes)
        frontier = list(nodes)
        while frontier:
            n = frontier.pop()
            for d in self.dependents.get(n, ()):
                if d not in out:
                    out.add(d)
                    frontier.append(d)
        return out

    @lru_cache(maxsize=4096)
    def scope(self, loc: Location) -> frozenset[str]:
        """Nodes whose symptoms this location could explain (always includes the location)."""
        if loc.kind == "interface":
            lid = self.link_for_interface(loc.node, loc.interface) if self.available else None
            if lid is None:
                return frozenset(self._with_dependents({loc.node}))
            return self.scope(Location("link", link=lid)) | {loc.node}
        if loc.kind == "link":
            if loc.link not in self.links:
                return frozenset()
            a, b, _, _ = self.links[loc.link]
            base = {a, b}
            if self.has_roots and self.g.has_edge(a, b, key=loc.link):
                h = self.g.copy()
                h.remove_edge(a, b, key=loc.link)
                base |= self._disconnected_without(h)
            return frozenset(self._with_dependents(base))
        node = loc.node
        base = {node}
        if self.has_roots and node in self.g:
            h = self.g.copy()
            h.remove_node(node)
            base |= self._disconnected_without(h)
        return frozenset(self._with_dependents(base))

    def entities(self, subject: Subject) -> set[str]:
        """Topology nodes a measurement subject refers to (for scope membership)."""
        out = {x for x in (subject.device_id, subject.service_id, subject.segment_id) if x}
        if subject.link_id and subject.link_id in self.links:
            a, b, _, _ = self.links[subject.link_id]
            out |= {a, b}
        return out

    def candidate_upstreams(self, node: str) -> list[Location]:
        """Locations whose scope contains `node` (node itself, upstream nodes/links, services it depends on)."""
        if not self.available or node not in self.node_types:
            return [Location("node", node=node)]
        out = []
        for n in self.node_types:
            loc = Location("node", node=n)
            if node in self.scope(loc):
                out.append(loc)
        for lid in self.links:
            if self.links[lid][0] in self.g and self.g.has_edge(self.links[lid][0], self.links[lid][1], key=lid):
                loc = Location("link", link=lid)
                if node in self.scope(loc):
                    out.append(loc)
        return out

    def to_view(self) -> dict:
        """Plain dict for UI rendering."""
        if not self.snapshot:
            return {"available": False}
        return {"available": True, **self.snapshot.to_json_dict()}
