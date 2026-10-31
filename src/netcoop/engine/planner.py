"""Bounded evidence-seeking verification planner (the 'evidence-seeking' in STEaR).

Given an evaluation that is not yet high-support, choose observations whose
presence/absence would change the status of live hypotheses:

  permitted? -> an agent declares the metric? -> not already requested?
  -> decisive for >=1 live hypothesis (signature / required-absent claim at its location)?
  -> rank: number of live hypotheses it decides (desc), best rank of those hypotheses, metric cost

No probabilities or 'information gain' are computed (docs/05: no invented likelihoods).
The planner never produces values; agents fetch real recorded/authorized data or say 'unavailable'.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from netcoop.engine.stear import UNKNOWN_HYPOTHESIS, Evaluation, Hypothesis
from netcoop.evidence.ids import derive_id
from netcoop.evidence.timeutil import to_canonical
from netcoop.knowledge import claim_sources

COUNTER_COST = 2  # counters need >=2 samples, so a check costs more data
DEFAULT_COST = 1


@dataclass
class VerificationPolicy:
    enabled: bool = True
    max_rounds: int = 2
    checks_per_round: int = 3
    total_budget: int = 6
    authorization_scope: str = "recorded_replay"


@dataclass
class Check:
    agent_id: str
    metric: str
    claim: str
    subject: dict
    decides: list[str] = field(default_factory=list)
    best_rank: int = 10**6
    cost: int = DEFAULT_COST

    @property
    def key(self) -> str:
        return f"{self.agent_id}|{self.metric}|{sorted(self.subject.items())}"


def plan(ev: Evaluation, capabilities: dict[str, set[str]], already: set[str], budget_left: int,
         policy: VerificationPolicy) -> list[Check]:
    if not policy.enabled or budget_left <= 0 or ev.confidence_category == "high_support":
        return []
    if ev.status not in ("ambiguous", "insufficient_evidence", "diagnosed"):
        return []
    live: list[Hypothesis] = list(ev.causes) + list(ev.competitors)
    if not live:
        return []
    rank_of = {h.hid: i for i, h in enumerate(ev.hypotheses)}
    sources = claim_sources()
    checks: dict[str, Check] = {}
    for h in live:
        for claim, subject in h.missing:
            for rule in sources.get(claim, []):
                agent, metric = rule["agent"], rule["metric"]
                if metric not in capabilities.get(agent, set()):
                    continue
                c = Check(agent, metric, claim, subject,
                          cost=COUNTER_COST if rule.get("source") == "counter_rate" else DEFAULT_COST)
                if c.key in already:
                    continue
                c = checks.setdefault(c.key, c)
                if h.hid not in c.decides:
                    c.decides.append(h.hid)
                c.best_rank = min(c.best_rank, rank_of.get(h.hid, 10**6))
    ordered = sorted(checks.values(), key=lambda c: (-len(c.decides), c.best_rank, c.cost, c.key))
    return ordered[: min(policy.checks_per_round, budget_left)]


def challenge_doc(c: Check, ev: Evaluation, incident_id: str, window: tuple[datetime, datetime],
                  now: datetime, policy: VerificationPolicy, deadline_s: float) -> dict:
    """NDEP Challenge (spec/challenge.schema.json). Discriminates >=2 hypotheses;
    when only one modeled hypothesis is live the alternative is the unmodeled H-UNKNOWN."""
    others = [h.hid for h in list(ev.causes) + list(ev.competitors) if h.hid not in c.decides]
    hyp_ids = list(dict.fromkeys(c.decides + (others[:3] or [UNKNOWN_HYPOTHESIS])))
    if len(hyp_ids) < 2:
        hyp_ids.append(UNKNOWN_HYPOTHESIS)
    refs = sorted({fid for h in list(ev.causes) + list(ev.competitors) if h.hid in c.decides for fid in h.explained})
    start, end = window
    cid = derive_id("CH", incident_id, c.agent_id, c.metric, c.key, to_canonical(start), to_canonical(end), length=24)
    return {
        "schema_version": "1.0.0", "challenge_id": cid, "incident_id": incident_id, "target_agent_id": c.agent_id,
        "hypothesis_ids": hyp_ids, "finding_refs": refs,
        "question_type": "discriminating_measurement" if len(c.decides) >= 1 and others else "missing_evidence",
        "requested_observation": {"metric": c.metric, "subject": c.subject,
                                  "window": {"start": to_canonical(start), "end": to_canonical(end)}},
        "authorization_scope": policy.authorization_scope,
        "deadline_at": to_canonical(now + timedelta(seconds=deadline_s)),
        "note": f"Decides {c.claim} for {', '.join(c.decides)}. Return recorded/authorized observations only; "
                "never generate values.",
    }
