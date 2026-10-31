"""Rates from cumulative counters, with explicit reset/ordering/lineage checks.

A rate needs two valid samples of the same counter series, a positive interval and
a non-decreasing value. A decrease is reported as COUNTER_RESET (reset or wrap -
we cannot tell which without a declared counter width) and no rate is produced
across it. Samples relayed by different collectors (different lineage) are not
differenced, because they may not share a counter base.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from netcoop.evidence.errors import Issue, IssueCode, Severity
from netcoop.evidence.models import NormalizedObservation
from netcoop.evidence.registry import MetricRegistry, default_registry

COUNTER_RATE_VERSION = "ndep-counter-rate/1"


@dataclass(frozen=True)
class CounterRate:
    subject_key: str
    metric: str
    rate_metric: str
    value: float
    unit: str  # always "count/s"
    window_start: datetime
    window_end: datetime
    input_observation_ids: tuple[str, str]
    lineage_groups: tuple[str, ...]
    transformation_id: str = COUNTER_RATE_VERSION


def _series_source(o: NormalizedObservation) -> str:
    return o.source.source_id


def derive_counter_rates(
    observations: list[NormalizedObservation], registry: MetricRegistry | None = None
) -> tuple[list[CounterRate], list[Issue]]:
    registry = registry or default_registry()
    series: dict[tuple[str, str, str], list[NormalizedObservation]] = {}
    for o in observations:
        if o.measurement.kind != "cumulative_counter" or o.quality.validation != "passed":
            continue
        series.setdefault((o.subject.key(), o.measurement.metric, _series_source(o)), []).append(o)

    rates: list[CounterRate] = []
    issues: list[Issue] = []

    def issue(code: IssueCode, msg: str) -> None:
        issues.append(Issue(code=code, severity=Severity.WARNING, message=msg))

    # Same subject+metric reported by more than one source: never difference across them.
    by_subject_metric: dict[tuple[str, str], set[str]] = {}
    for subj, metric, src in series:
        by_subject_metric.setdefault((subj, metric), set()).add(src)
    for (subj, metric), srcs in by_subject_metric.items():
        if len(srcs) > 1:
            issue(IssueCode.COUNTER_MIXED_LINEAGE,
                  f"{metric} on {subj} reported by several sources {sorted(srcs)}; rates computed per source only")

    for (subj, metric, _src), samples in sorted(series.items()):
        mdef = registry.metrics[metric]
        ordered = sorted(samples, key=lambda o: (o.observed_at, o.observation_id))
        # collapse exact repeats; conflicting values at one instant are unusable
        uniq: list[NormalizedObservation] = []
        for o in ordered:
            if uniq and uniq[-1].observed_at == o.observed_at:
                if uniq[-1].measurement.value != o.measurement.value:
                    issue(IssueCode.COUNTER_TIMESTAMP_CONFLICT,
                          f"{metric} on {subj}: different values at {o.observed_at.isoformat()} "
                          f"({uniq[-1].observation_id}, {o.observation_id}); sample dropped from rate series")
                    uniq.pop()
                continue
            uniq.append(o)
        if len(uniq) < 2:
            issue(IssueCode.COUNTER_INSUFFICIENT_SAMPLES,
                  f"{metric} on {subj}: {len(uniq)} usable sample(s); a rate needs at least 2")
            continue
        for a, b in zip(uniq, uniq[1:]):
            dt = (b.observed_at - a.observed_at).total_seconds()
            delta = b.measurement.value - a.measurement.value
            if delta < 0:
                issue(IssueCode.COUNTER_RESET,
                      f"{metric} on {subj}: counter decreased {a.measurement.value} -> {b.measurement.value} "
                      f"between {a.observation_id} and {b.observation_id} (reset or wrap); no rate across it")
                continue
            rate = delta / dt
            if mdef.max_rate_per_s is not None and rate > mdef.max_rate_per_s:
                issue(IssueCode.IMPOSSIBLE_RATE,
                      f"{metric} on {subj}: derived {rate:.3g}/s exceeds sanity bound {mdef.max_rate_per_s:g}/s "
                      f"({a.observation_id} -> {b.observation_id}); likely missed reset; not used")
                continue
            rates.append(CounterRate(
                subject_key=subj, metric=metric, rate_metric=f"{metric}_rate", value=rate, unit="count/s",
                window_start=a.observed_at, window_end=b.observed_at,
                input_observation_ids=(a.observation_id, b.observation_id),
                lineage_groups=tuple(dict.fromkeys((a.lineage_group, b.lineage_group))),
            ))
    return rates, issues
