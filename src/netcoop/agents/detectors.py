"""Rule-based symptom detectors used by specialist agents (deterministic, no LLM).

Each detector turns validated observations into a claim with polarity:
- present: condition holds persistently in fresh, validated data from one source
- absent: fresh, validated samples exist and none meet the condition
- unknown: a single anomalous sample (transient), or sources disagree
- (no finding): nothing fresh to look at -> reported as a coverage gap, never 'absent'
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime

from netcoop.evidence.counters import derive_counter_rates
from netcoop.evidence.models import NormalizedObservation, Subject

MAX_REFS = 25
_RANK = {"absent": 0, "unknown": 1, "present": 2}


@dataclass
class Sample:
    value: object
    at: datetime
    refs: tuple[str, ...]
    long_interval: bool = False


@dataclass
class Evaluation:
    claim: str
    subject: Subject
    polarity: str
    refs: list[str]
    onset: datetime | None
    caveats: list[str] = field(default_factory=list)
    metrics: list[str] = field(default_factory=list)


@dataclass
class _SourceVerdict:
    verdict: str
    anomalous: list[Sample]
    used: list[Sample]
    metrics: set[str]


def _cond(rule: dict, v) -> bool:
    op = rule["op"]
    if op == "in":
        return any(v is x if isinstance(x, bool) else v == x for x in rule["values"])
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return False
    t = rule["threshold"]
    return {"gt": v > t, "ge": v >= t, "lt": v < t, "le": v <= t}[op]


def usable(observations: list[NormalizedObservation]) -> tuple[list[NormalizedObservation], dict]:
    fresh, stale, quarantined = [], 0, 0
    for o in observations:
        if o.quality.validation != "passed":
            quarantined += 1
        elif o.quality.freshness != "current":
            stale += 1
        else:
            fresh.append(o)
    return fresh, {"stale_ignored": stale, "quarantined_ignored": quarantined}


def _samples(rule: dict, items: list[NormalizedObservation], min_interval_s: float) -> list[Sample]:
    if rule.get("source") == "counter_rate":
        rates, _ = derive_counter_rates(items)
        return [Sample(r.value, r.window_end, r.input_observation_ids) for r in rates]
    out = []
    for o in items:
        w = o.measurement.window
        long_iv = bool(w and o.measurement.kind == "interval_summary"
                       and (w.end - w.start).total_seconds() >= min_interval_s)
        out.append(Sample(o.measurement.value, w.start if (w and long_iv) else o.observed_at,
                          (o.observation_id,), long_iv))
    return out


def evaluate(observations: list[NormalizedObservation], rules: list[dict], persistence: dict) -> list[Evaluation]:
    fresh, _ = usable(observations)
    groups: dict[tuple[str, str, str], list[NormalizedObservation]] = defaultdict(list)
    subjects: dict[str, Subject] = {}
    for o in fresh:
        k = o.subject.key()
        groups[(o.measurement.metric, k, o.source.source_id)].append(o)
        subjects[k] = o.subject

    # (claim, subject_key) -> source_id -> merged verdict across rules for that claim
    verdicts: dict[tuple[str, str], dict[str, _SourceVerdict]] = defaultdict(dict)
    for rule in rules:
        min_n = rule.get("min_samples", persistence["min_samples"])
        for (metric, skey, src), items in groups.items():
            if metric != rule["metric"]:
                continue
            samples = _samples(rule, items, persistence["min_interval_summary_s"])
            if not samples:
                continue
            anom = [s for s in samples if _cond(rule, s.value)]
            if len(anom) >= min_n or any(s.long_interval for s in anom):
                v = "present"
            elif anom:
                v = "unknown"
            else:
                v = "absent"
            tag = metric + (":rate" if rule.get("source") == "counter_rate" else "")
            cur = verdicts[(rule["claim"], skey)].get(src)
            new = _SourceVerdict(v, anom, anom if v != "absent" else samples, {tag})
            if cur is None or _RANK[v] > _RANK[cur.verdict]:
                verdicts[(rule["claim"], skey)][src] = new
            elif _RANK[v] == _RANK[cur.verdict]:
                cur.anomalous += anom
                cur.used += new.used
                cur.metrics |= {tag}

    out: list[Evaluation] = []
    for (claim, skey), per_src in sorted(verdicts.items()):
        kinds = {sv.verdict for sv in per_src.values()}
        caveats: list[str] = []
        if "present" in kinds and "absent" in kinds:
            polarity = "unknown"
            chosen = list(per_src.values())
            pres = sorted(s for s, sv in per_src.items() if sv.verdict == "present")
            absn = sorted(s for s, sv in per_src.items() if sv.verdict == "absent")
            caveats.append(f"SOURCE_CONFLICT: anomalous per {pres}, normal per {absn}; needs an independent measurement")
        else:
            polarity = max(kinds, key=_RANK.get)
            chosen = [sv for sv in per_src.values() if sv.verdict == polarity]
            if polarity == "unknown":
                caveats.append("TRANSIENT: a single anomalous sample; persistence not established")
        refs: list[str] = []
        onset = None
        for sv in chosen:
            for s in sv.used:
                refs.extend(s.refs)
            for s in sv.anomalous:
                onset = s.at if onset is None or s.at < onset else onset
        refs = sorted(dict.fromkeys(refs))
        if len(refs) > MAX_REFS:
            caveats.append(f"{len(refs)} supporting observations; first {MAX_REFS} by id referenced")
            refs = refs[:MAX_REFS]
        out.append(Evaluation(claim=claim, subject=subjects[skey], polarity=polarity, refs=refs,
                              onset=onset if polarity != "absent" else None, caveats=caveats,
                              metrics=sorted(set().union(*(sv.metrics for sv in chosen)))))
    return out
