"""Versioned metric registry: allowed units, explicit conversions, ranges, kinds."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from netcoop.spec import load_json

VALUE_TYPES = {"number", "integer", "enum", "boolean"}


@dataclass(frozen=True)
class MetricDef:
    name: str
    canonical_unit: str
    allowed_units: tuple[str, ...]
    value_type: str
    allowed_kinds: tuple[str, ...]
    min: float | int | None = None
    max: float | int | None = None
    allowed_values: tuple[str, ...] = ()
    max_rate_per_s: float | None = None
    max_age_s: float | None = None


@dataclass(frozen=True)
class MetricRegistry:
    version: str
    metrics: dict[str, MetricDef]
    unit_aliases: dict[str, str]
    conversions: dict[tuple[str, str], float]
    default_max_age_s: float
    max_future_skew_s: float

    @classmethod
    def from_dict(cls, data: dict) -> "MetricRegistry":
        metrics: dict[str, MetricDef] = {}
        for name, m in data["metrics"].items():
            if m["value_type"] not in VALUE_TYPES:
                raise ValueError(f"registry metric {name}: unknown value_type {m['value_type']!r}")
            if m["canonical_unit"] not in m["allowed_units"]:
                raise ValueError(f"registry metric {name}: canonical unit not in allowed_units")
            metrics[name] = MetricDef(
                name=name,
                canonical_unit=m["canonical_unit"],
                allowed_units=tuple(m["allowed_units"]),
                value_type=m["value_type"],
                allowed_kinds=tuple(m["allowed_kinds"]),
                min=m.get("min"),
                max=m.get("max"),
                allowed_values=tuple(m.get("allowed_values", ())),
                max_rate_per_s=m.get("max_rate_per_s"),
                max_age_s=m.get("max_age_s"),
            )
        reg = cls(
            version=data["metric_registry_version"],
            metrics=metrics,
            unit_aliases=dict(data.get("unit_aliases", {})),
            conversions={(c["from"], c["to"]): c["factor"] for c in data.get("conversions", [])},
            default_max_age_s=data["freshness_policy"]["default_max_age_s"],
            max_future_skew_s=data["freshness_policy"]["max_future_skew_s"],
        )
        # Every non-canonical allowed unit needs an explicit factor; no implicit 1:1.
        for m in reg.metrics.values():
            for u in m.allowed_units:
                if u != m.canonical_unit and (u, m.canonical_unit) not in reg.conversions:
                    raise ValueError(f"registry metric {m.name}: no conversion {u} -> {m.canonical_unit}")
        return reg

    def resolve_unit(self, unit: str) -> str:
        """Map a spelling alias ('%') to the registry unit ('percent'). Meaning never changes."""
        return self.unit_aliases.get(unit, unit)

    def factor(self, unit: str, canonical: str) -> float | int:
        return 1 if unit == canonical else self.conversions[(unit, canonical)]

    def max_age_s(self, metric: MetricDef) -> float:
        return metric.max_age_s if metric.max_age_s is not None else self.default_max_age_s


@lru_cache(maxsize=1)
def default_registry() -> MetricRegistry:
    return MetricRegistry.from_dict(load_json("metric_registry.json"))
