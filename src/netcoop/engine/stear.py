"""STEaR: spatio-temporal, topology-constrained abductive hypothesis evaluation.

Deterministic and LLM-free. Input: current agent findings, the observations they
reference, a topology snapshot (optional) and the versioned fault library.
Output: every candidate hypothesis with its evidence accounting, the selected
explanation (0-2 root causes), competitors, and a status/support decision.

Ranking is lexicographic (documented in docs/05 and below); it yields an ORDER
and a support CATEGORY, never a probability.

  rank key = (signature state: confirmed < plausible < contradicted,
              more present symptoms explained,
              more independent lineage groups among explaining evidence,
              fewer missing discriminating observations,
              fewer temporal inconsistencies,
              smaller impact scope (more specific location),
              hypothesis id)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from netcoop.evidence.models import Finding, NormalizedObservation, Subject
from netcoop.knowledge import fault_library
from netcoop.topology import Location, TopologyGraph, location_of

ENGINE_VERSION = "stear/0.1"
HINT_CLAIMS = {"COMMON_UPSTREAM_DEPENDENCY", "COMMON_SERVICE_DEPENDENCY"}
UNKNOWN_HYPOTHESIS = "H-UNKNOWN"
MAX_HYPOTHESES = 400


@dataclass
class Sym:
    finding: Finding
    loc: Location
    entities: frozenset[str]
    onset: datetime | None
    lineages: frozenset[str]
    sources: frozenset[tuple[str, str]]  # (lineage_group, source_id) pairs behind this finding

    @property
    def fid(self) -> str:
        return self.finding.finding_id


@dataclass
class Hypothesis:
    hid: str
    fault: str
    loc: Location
    scope: frozenset[str]
    status: str = "plausible"  # confirmed | plausible | contradicted
    signature: list[str] = field(default_factory=list)  # finding ids establishing the signature
    explained: list[str] = field(default_factory=list)
    contradictions: list[str] = field(default_factory=list)
    missing: list[tuple[str, dict]] = field(default_factory=list)  # (claim, subject) not yet observed
    temporal_issues: list[str] = field(default_factory=list)
    lineages: set[str] = field(default_factory=set)
    source_pairs: set[tuple[str, str]] = field(default_factory=set)
    reasons: list[str] = field(default_factory=list)

    @property
    def independent_sources(self) -> int:
        return independent_sources(self.source_pairs)

    def rank_key(self):
        state = {"confirmed": 0, "plausible": 1, "contradicted": 2}[self.status]
        return (state, -len(self.explained), -self.independent_sources, -len(self.lineages), len(self.missing),
                len(self.temporal_issues), len(self.scope), self.hid)

    def to_dict(self, rank: int | None = None) -> dict:
        return {
            "hypothesis_id": self.hid, "fault_type": self.fault, "location": self.loc.key,
            "location_subject": self.loc.subject(), "status": self.status, "rank": rank,
            "explained_findings": self.explained, "signature_findings": self.signature,
            "contradictions": self.contradictions,
            "missing_discriminators": [{"claim": c, "subject": s} for c, s in self.missing],
            "temporal_issues": self.temporal_issues, "independent_lineage_groups": len(self.lineages),
            "independent_sources": self.independent_sources,
            "impact_scope": sorted(self.scope), "reasons": self.reasons,
        }


@dataclass
class Evaluation:
    status: str
    confidence_category: str
    causes: list[Hypothesis]
    competitors: list[Hypothesis]
    hypotheses: list[Hypothesis]
    present_symptoms: list[str]
    unexplained: list[str]
    coverage_ratio: float
    decision_basis: list[str]
    limitations: list[str]
    symptoms: dict[str, Sym]
    # domains the topology says exist but with no fresh normal reading: [(domain, claims, candidate subjects)]
    coverage_gaps: list[tuple[str, list[str], list[dict]]] = field(default_factory=list)

    @property
    def leader(self) -> Hypothesis | None:
        return self.causes[0] if self.causes else (
            self.hypotheses[0] if self.hypotheses and self.hypotheses[0].status != "contradicted" else None)


def independent_sources(pairs: set[tuple[str, str]]) -> int:
    """Number of independent evidence sources. Sources that share a lineage group (one
    physical sample relayed by several collectors) are merged into one."""
    parent: dict[str, str] = {}

    def find(x):
        while parent.setdefault(x, x) != x:
            x = parent[x]
        return x

    by_lineage: dict[str, list[str]] = {}
    for lg, src in pairs:
        by_lineage.setdefault(lg, []).append(src)
        find(src)
    for srcs in by_lineage.values():
        for other in srcs[1:]:
            parent[find(other)] = find(srcs[0])
    return len({find(s) for s in parent})


def _primary_node(s: Subject) -> str | None:
    return s.device_id or s.service_id or s.segment_id


class Stear:
    def __init__(self, topology: TopologyGraph, library: dict | None = None, *,
                 use_topology: bool = True, use_temporal: bool = True):
        self.lib = library or fault_library()
        self.topo = topology if use_topology else TopologyGraph(None)
        self.use_temporal = use_temporal
        self.symptom_claims = set(self.lib["symptom_claims"])
        self.tolerance = timedelta(seconds=self.lib["temporal_tolerance_s"])

    # -- helpers ------------------------------------------------------------------------
    def _entities(self, s: Subject) -> frozenset[str]:
        if not self.topo.available:
            n = _primary_node(s)
            return frozenset({n} if n else set())
        ents = set(self.topo.entities(s))
        if s.device_id and s.interface_id:  # an interface also concerns its link peer
            lid = self.topo.link_for_interface(s.device_id, s.interface_id)
            if lid:
                a, b, _, _ = self.topo.links[lid]
                ents |= {a, b}
        return frozenset(ents)

    def _scope(self, loc: Location) -> frozenset[str]:
        if not self.topo.available:
            return frozenset({loc.node} if loc.node else set())
        sc = self.topo.scope(loc)
        return sc if sc else frozenset({loc.node} if loc.node else set())

    @staticmethod
    def _at(f: Finding, loc: Location) -> bool:
        s = f.subject
        if loc.kind == "interface":
            return s.device_id == loc.node and s.interface_id == loc.interface
        if loc.kind == "link":
            return s.link_id == loc.link
        return _primary_node(s) == loc.node

    def _claim_state(self, claim: str, findings: list[Finding], pred) -> tuple[str, list[str]]:
        hits = [f for f in findings if f.claim == claim and pred(f)]
        pres = [f.finding_id for f in hits if f.polarity == "present"]
        if pres:
            return "present", pres
        if any(f.polarity == "unknown" for f in hits):
            return "unknown", [f.finding_id for f in hits if f.polarity == "unknown"]
        absn = [f.finding_id for f in hits if f.polarity == "absent"]
        return ("absent", absn) if absn else ("missing", [])

    def _node_type_ok(self, fault: dict, node: str | None) -> bool:
        types = fault.get("location_types")
        if not types or not self.topo.available or node is None:
            return True
        t = self.topo.node_types.get(node)
        if t is not None and t not in types:
            return False
        kinds = fault.get("service_kinds")
        if kinds and t == "service":
            declared = self.topo.service_kinds.get(node)
            return declared is None or declared in kinds
        return True

    # -- main ---------------------------------------------------------------------------
    def evaluate(self, findings: list[Finding], observations: dict[str, NormalizedObservation]) -> Evaluation:
        limitations: list[str] = []
        if not self.topo.available:
            limitations.append("No topology snapshot: impact scope and localization are limited to the measured components.")
        elif not self.topo.has_roots:
            limitations.append("Topology has no 'core' role nodes: upstream impact scope cannot be computed.")
        if not self.use_temporal:
            limitations.append("Temporal consistency checks disabled (ablation).")

        syms: dict[str, Sym] = {}
        for f in findings:
            obs = [observations[r] for r in f.observation_refs if r in observations]
            onset = min((o.observed_at for o in obs), default=None) if f.polarity != "absent" else None
            syms[f.finding_id] = Sym(f, location_of(f.subject), self._entities(f.subject), onset,
                                     frozenset(o.lineage_group for o in obs),
                                     frozenset((o.lineage_group, o.source.source_id) for o in obs))
        present = [s for s in syms.values() if s.finding.polarity == "present" and s.finding.claim in self.symptom_claims]
        hints = [s for s in syms.values() if s.finding.polarity == "present" and s.finding.claim in HINT_CLAIMS]
        P = {s.fid for s in present}

        hyps = self._generate(present, hints, list(syms.values()))
        for h in hyps.values():
            self._assess(h, findings, syms, P)
        hyps = {k: h for k, h in hyps.items() if h.explained or h.status == "confirmed"}
        ranked = sorted(hyps.values(), key=Hypothesis.rank_key)
        valid = [h for h in ranked if h.status != "contradicted"]

        basis: list[str] = []
        usable = [o for o in observations.values() if o.quality.validation == "passed" and o.quality.freshness == "current"]
        if not usable:
            return Evaluation("insufficient_evidence", "insufficient", [], [], ranked, sorted(P), sorted(P), 0.0,
                              ["No fresh, validated observations were available."], limitations, syms)
        if not P:
            agents_absent = {s.finding.agent_id for s in syms.values() if s.finding.polarity == "absent"}
            perf_absent = any(s.finding.polarity == "absent" and s.finding.claim in
                              {"HIGH_LATENCY", "PACKET_LOSS", "HIGH_LINK_UTILIZATION"} for s in syms.values())
            gaps = self._coverage_gaps(syms)
            if gaps:
                names = [g[0] for g in gaps]
                basis.append(f"No anomaly in the monitored data, but these domains exist in the topology and have no "
                             f"fresh normal reading: {names}. Missing data is not evidence of normality.")
                limitations.append(f"Unmonitored domains: {names}.")
                ev = Evaluation("insufficient_evidence", "insufficient", [], [], ranked, [], [], 0.0, basis,
                                limitations, syms)
                ev.coverage_gaps = gaps
                return ev
            if len(agents_absent) >= 2 and perf_absent:
                basis.append(f"No persistent anomaly in fresh data; normal readings reported by {sorted(agents_absent)}.")
                unknowns = [s.fid for s in syms.values() if s.finding.polarity == "unknown"]
                if unknowns:
                    limitations.append(f"{len(unknowns)} transient or conflicting reading(s) were not treated as faults.")
                return Evaluation("healthy", "not_applicable", [], [], ranked, [], [], 1.0, basis, limitations, syms)
            basis.append("No anomaly detected, but monitoring coverage is too thin to call the network healthy "
                         "(needs normal readings from >=2 specialists including a performance metric).")
            return Evaluation("insufficient_evidence", "insufficient", [], [], ranked, [], [], 0.0, basis,
                              limitations, syms)

        if not valid:
            basis.append(f"{len(P)} persistent symptom(s) observed; every modeled explanation is contradicted by "
                         "observed evidence or none applies.")
            return Evaluation("unknown_fault", "insufficient", [], [], ranked, sorted(P), sorted(P), 0.0, basis,
                              limitations, syms)

        explainable = set().union(*(set(h.explained) for h in valid))
        unexplainable = sorted(P - explainable)
        h1 = valid[0]
        if h1.status != "confirmed" and unexplainable:
            basis.append(f"{len(unexplainable)} persistent symptom(s) cannot be explained by any surviving modeled "
                         "hypothesis, and no cause is confirmed.")
            plaus = [h for h in valid if h.status == "plausible"][:8]
            return Evaluation("unknown_fault", "insufficient", [], plaus, ranked, sorted(P), unexplainable, 0.0,
                              basis, limitations, syms)
        causes = [h1]
        if h1.status == "confirmed":
            rest = P - set(h1.explained)
            if rest:
                extra = [h for h in valid[1:] if h.status == "confirmed" and set(h.explained) & rest]
                if extra:
                    extra.sort(key=lambda h: (-len(set(h.explained) & rest), h.rank_key()))
                    causes.append(extra[0])
                    basis.append(f"Second concurrent fault {extra[0].hid} explains {len(set(extra[0].explained) & rest)} "
                                 f"symptom(s) not explained by {h1.hid} (bounded to 2 faults).")
        explained_all = set().union(*(set(h.explained) for h in causes))
        unexplained = sorted(P - explained_all)
        coverage = len(explained_all & P) / len(P)

        competitors = []
        for h in valid:
            if h in causes or h.status != "plausible":
                continue
            for c in causes:
                if set(h.explained) & set(c.explained) and len(h.explained) >= len(set(h.explained) & set(c.explained)) \
                        and len(h.explained) >= len(c.explained):
                    competitors.append(h)
                    break

        if h1.status == "plausible":
            if competitors:
                basis.append(f"{len(competitors) + 1} hypotheses explain the symptoms equally well and none has its "
                             "signature observed; discriminating evidence is missing.")
                status, cat = "ambiguous", "ambiguous"
            else:
                basis.append(f"Only {h1.hid} explains the symptoms, but its characteristic signature has not been "
                             "observed; not enough evidence to diagnose.")
                status, cat = "insufficient_evidence", "insufficient"
            return Evaluation(status, cat, [], [h1] + competitors, ranked, sorted(P), sorted(P), 0.0, basis,
                              limitations, syms)

        n_sources = independent_sources(set().union(*(h.source_pairs for h in causes)))
        temporal = any(h.temporal_issues for h in causes)
        # A plausible (unverified) hypothesis that would explain symptoms the selected causes leave
        # unexplained is a possible concurrent fault: it blocks high support and is a verification target.
        second = [h for h in valid if h not in causes and h not in competitors and h.status == "plausible"
                  and set(h.explained) & set(unexplained)]
        second.sort(key=lambda h: (-len(set(h.explained) & set(unexplained)), h.rank_key()))
        if second:
            basis.append(f"Possible concurrent fault not yet verified: {', '.join(h.hid for h in second[:3])} would "
                         f"explain {len(set(second[0].explained) & set(unexplained))} unexplained symptom(s).")
            competitors = competitors + second[:4]
        high = not competitors and n_sources >= 2 and not temporal and coverage >= 0.6
        for c in causes:
            basis.append(f"{c.hid}: signature observed ({', '.join(c.signature)}); explains {len(c.explained)} symptom "
                         f"finding(s) using {c.independent_sources} independent source(s) "
                         f"({len(c.lineages)} sample lineage group(s)).")
        if competitors:
            basis.append(f"Not high support: {len(competitors)} competing hypothesis(es) remain unverified: "
                         f"{', '.join(h.hid for h in competitors[:5])}.")
        if n_sources < 2:
            basis.append("Not high support: all explaining evidence comes from a single independent source "
                         "(no independent corroboration).")
        if temporal:
            basis.append("Not high support: temporal ordering inconsistencies were found.")
        if coverage < 0.6:
            basis.append(f"Not high support: only {coverage:.0%} of present symptoms are explained.")
        if unexplained:
            limitations.append(f"{len(unexplained)} symptom finding(s) remain unexplained by the selected cause(s).")
        return Evaluation("diagnosed", "high_support" if high else "moderate_support", causes, competitors, ranked,
                          sorted(P), unexplained, coverage, basis, limitations, syms)

    # -- monitoring coverage -----------------------------------------------------------------
    def _coverage_gaps(self, syms: dict[str, Sym]) -> list[tuple[str, list[str], list[dict]]]:
        domains = {k: v for k, v in self.lib.get("coverage_domains", {}).items() if not k.startswith("_")}
        normal = {s.finding.claim for s in syms.values() if s.finding.polarity == "absent"}
        gaps = []
        for name, d in sorted(domains.items()):
            req = d["required"]
            if req != "always":
                if not self.topo.available:
                    continue  # cannot know the domain exists; stated as a topology limitation instead
                if "service_kind" in req and req["service_kind"] not in self.topo.service_kinds.values():
                    continue
                if "node_type" in req and req["node_type"] not in self.topo.node_types.values():
                    continue
            if normal & set(d["claims"]):
                continue
            stype = d.get("probe_subject_type")
            subjects: list[dict] = []
            if stype and self.topo.available:
                key = "segment_id" if stype == "segment" else "device_id"
                subjects = [{key: n} for n, t in sorted(self.topo.node_types.items()) if t == stype][:2]
            gaps.append((name, list(d["claims"]), subjects))
        return gaps

    # -- hypothesis generation ------------------------------------------------------------
    def _generate(self, present: list[Sym], hints: list[Sym], all_syms: list[Sym]) -> dict[str, Hypothesis]:
        node_locs: dict[str, Location] = {}
        iface_locs: dict[str, Location] = {}
        link_locs: dict[str, Location] = {}

        def add(loc: Location) -> None:
            if loc.kind == "interface":
                iface_locs[loc.key] = loc
                node_locs[loc.node] = Location("node", node=loc.node)
            elif loc.kind == "link":
                link_locs[loc.key] = loc
            elif loc.node:
                node_locs[loc.node] = loc

        for s in all_syms:  # every observed component
            add(s.loc)
        for s in hints:
            add(Location("node", node=_primary_node(s.finding.subject)))
        # interfaces of links attached to symptomatic nodes, and lowest common upstream of symptoms
        if self.topo.available:
            sym_nodes = {n for s in present for n in s.entities}
            for lid, (a, b, ai, bi) in self.topo.links.items():
                if a in sym_nodes or b in sym_nodes:
                    if ai:
                        add(Location("interface", node=a, interface=ai))
                    if bi:
                        add(Location("interface", node=b, interface=bi))
            by_claim: dict[str, set[str]] = {}
            for s in present:
                by_claim.setdefault(s.finding.claim, set()).update(s.entities)
            for ents in list(by_claim.values()) + ([sym_nodes] if len(sym_nodes) > 1 else []):
                if len(ents) < 2:
                    continue
                covering = [n for n in self.topo.node_types if ents <= self._scope(Location("node", node=n))]
                if covering:
                    best = min(len(self._scope(Location("node", node=n))) for n in covering)
                    for n in covering:
                        if len(self._scope(Location("node", node=n))) == best:
                            add(Location("node", node=n))
                for lid, (a, b, ai, bi) in self.topo.links.items():
                    if ents <= self._scope(Location("link", link=lid)):
                        if ai:
                            add(Location("interface", node=a, interface=ai))
                        if bi:
                            add(Location("interface", node=b, interface=bi))

        hyps: dict[str, Hypothesis] = {}
        for fname, fault in sorted(self.lib["faults"].items()):
            locs = list(iface_locs.values()) if fault["location"] == "interface" else list(node_locs.values())
            for loc in sorted(locs, key=lambda x: x.key):
                if fault["location"] == "node" and not self._node_type_ok(fault, loc.node):
                    continue
                hid = f"H-{fname}-{loc.key}"
                hyps[hid] = Hypothesis(hid=hid, fault=fname, loc=loc, scope=self._scope(loc))
                if len(hyps) >= MAX_HYPOTHESES:
                    return hyps
        return hyps

    # -- hypothesis assessment -------------------------------------------------------------
    def _assess(self, h: Hypothesis, findings: list[Finding], syms: dict[str, Sym], P: set[str]) -> None:
        fault = self.lib["faults"][h.fault]
        at = lambda f: self._at(f, h.loc)  # noqa: E731
        in_scope = lambda f: bool(syms[f.finding_id].entities & h.scope)  # noqa: E731
        sig_pred = in_scope if fault.get("signature_scope") == "scope" else at

        sig_states = {c: self._claim_state(c, findings, sig_pred) for c in fault["signature_any"]}
        sig_present = [fid for st, ids in sig_states.values() if st == "present" for fid in ids]
        req_states = {c: self._claim_state(c, findings, at) for c in fault.get("require_absent", [])}
        con_states = {c: self._claim_state(c, findings, at) for c in fault.get("contradicted_by", [])}

        mode = fault.get("signature_contradiction", "all_absent")
        absent_claims = [c for c, (st, _) in sig_states.items() if st == "absent"]
        if sig_present:
            h.signature = sig_present
        elif (mode == "all_absent" and len(absent_claims) == len(sig_states)) or (mode == "any_absent" and absent_claims):
            h.contradictions.append(f"signature {absent_claims if mode == 'any_absent' else fault['signature_any']} "
                                    f"observed normal at {h.loc.key}")
        else:
            for c, (st, _) in sig_states.items():
                if st in ("missing", "unknown") and fault.get("signature_scope") != "scope":
                    h.missing.append((c, h.loc.subject()))
        for c, (st, ids) in req_states.items():
            if st == "present":
                h.contradictions.append(f"{c} present at {h.loc.key} ({', '.join(ids)}) but must be absent")
            elif st in ("missing", "unknown"):
                h.missing.append((c, h.loc.subject()))
        for c, (st, ids) in con_states.items():
            if st == "present":
                h.contradictions.append(f"{c} present at {h.loc.key} ({', '.join(ids)}) contradicts {h.fault}")

        local = set(fault["signature_any"]) | set(fault.get("corroborating", []))
        effects = set(fault.get("effects", []))
        cause_onsets = [syms[fid].onset for fid in sig_present if syms[fid].onset]
        cause_onset = min(cause_onsets) if cause_onsets else None
        explained = []
        for fid in sorted(P):
            s = syms[fid]
            f = s.finding
            ok = (f.claim in local and (sig_pred(f) if f.claim in fault["signature_any"] else at(f))) or \
                 (f.claim in effects and in_scope(f))
            if not ok:
                continue
            if (self.use_temporal and cause_onset and s.onset and f.claim in effects and fid not in sig_present
                    and s.onset < cause_onset - self.tolerance):
                h.temporal_issues.append(f"{fid} ({f.claim}) began {(cause_onset - s.onset).total_seconds():.0f}s "
                                         f"before the {h.fault} signature")
                continue
            explained.append(fid)
            h.lineages |= set(s.lineages)
            h.source_pairs |= set(s.sources)
        h.explained = explained
        if h.contradictions:
            h.status = "contradicted"
        elif sig_present and not h.missing:
            h.status = "confirmed"
        elif sig_present:
            h.status = "plausible"  # signature seen, but a required-absent condition is unverified
            h.reasons.append("signature observed; required-absent condition not yet verified")
        else:
            h.status = "plausible"
