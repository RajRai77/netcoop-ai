"""Evidence-integrity rules that span records: topology validity, finding checks,
revision chains and provenance independence.

These functions are pure; the store calls them with committed state.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from netcoop.evidence.errors import EvidenceError, Issue, IssueCode, Severity
from netcoop.evidence.models import Finding, NormalizedObservation, TopologySnapshot


def validate_topology(t: TopologySnapshot) -> None:
    problems: list[str] = []
    node_ids = [n.id for n in t.nodes]
    link_ids = [lk.id for lk in t.links]
    dup_nodes = sorted({x for x in node_ids if node_ids.count(x) > 1})
    dup_links = sorted({x for x in link_ids if link_ids.count(x) > 1})
    if dup_nodes:
        problems.append(f"duplicate node ids {dup_nodes}")
    if dup_links:
        problems.append(f"duplicate link ids {dup_links}")
    if any(not x.strip() for x in node_ids + link_ids):
        problems.append("empty node/link id")
    known = set(node_ids)
    for lk in t.links:
        missing = [e for e in (lk.from_, lk.to) if e not in known]
        if missing:
            problems.append(f"link {lk.id} references unknown nodes {missing}")
        if lk.from_ == lk.to:
            problems.append(f"link {lk.id} is a self-loop")
    if problems:
        raise EvidenceError([Issue(code=IssueCode.TOPOLOGY_INVALID, severity=Severity.REJECT, message=p)
                             for p in problems])


def validate_finding(
    f: Finding,
    observations: Mapping[str, NormalizedObservation],
    superseded: Finding | None,
    already_superseded: bool,
) -> list[str]:
    """Return caveats to append (none today) or raise EvidenceError.

    observations: committed observations of this incident, by id.
    superseded: the finding named in f.supersedes_finding_id, if it exists.
    """
    missing = [r for r in f.observation_refs if r not in observations]
    if missing:
        raise EvidenceError.single(
            IssueCode.UNKNOWN_OBSERVATION_REF,
            f"finding {f.finding_id} references observations not stored for incident {f.incident_id}: {missing}",
        )
    if f.supersedes_finding_id is not None:
        if superseded is None:
            raise EvidenceError.single(IssueCode.INVALID_SUPERSEDES,
                                       f"supersedes unknown finding {f.supersedes_finding_id!r}")
        if superseded.finding_id == f.finding_id:
            raise EvidenceError.single(IssueCode.INVALID_SUPERSEDES, "finding cannot supersede itself")
        if superseded.incident_id != f.incident_id or superseded.agent_id != f.agent_id:
            raise EvidenceError.single(
                IssueCode.INVALID_SUPERSEDES,
                "a revision must come from the same agent and incident as the finding it supersedes",
            )
        if already_superseded:
            raise EvidenceError.single(
                IssueCode.INVALID_SUPERSEDES,
                f"finding {superseded.finding_id} already has a revision; revise the latest one instead",
            )
        if f.created_at < superseded.created_at:
            raise EvidenceError.single(IssueCode.INVALID_SUPERSEDES, "revision is older than the finding it supersedes")
    return []


def lineage_groups(observations: Iterable[NormalizedObservation]) -> set[str]:
    return {o.lineage_group for o in observations}


def independent_support(
    findings: Iterable[Finding], observations: Mapping[str, NormalizedObservation]
) -> dict:
    """How much *independent* evidence a set of findings rests on.

    Several agents interpreting the same observations (or observations from the
    same source sample) share lineage and count once.
    """
    findings = list(findings)
    groups: set[str] = set()
    obs_ids: set[str] = set()
    for f in findings:
        for ref in f.observation_refs:
            obs_ids.add(ref)
            groups.add(observations[ref].lineage_group)
    return {
        "findings": len(findings),
        "agents": len({f.agent_id for f in findings}),
        "distinct_observations": len(obs_ids),
        "independent_lineage_groups": len(groups),
        "lineage_groups": sorted(groups),
    }
