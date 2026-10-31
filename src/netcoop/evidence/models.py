"""Typed NDEP contract models. Field-for-field mirrors of spec/*.schema.json.

Structure lives here and in the JSON Schemas (contract tests keep them in agreement).
Domain semantics (units, ranges, freshness, counters, lineage) live in
netcoop.evidence.normalize / counters / integrity, not in these models.
"""

from __future__ import annotations

import math
from datetime import datetime
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    PlainSerializer,
    StrictBool,
    StrictFloat,
    StrictInt,
    StrictStr,
    field_validator,
    model_validator,
)

from netcoop.evidence.timeutil import parse_timestamp, to_canonical

NDEP_SCHEMA_VERSION = "1.0.0"


def _ts(value: object) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise ValueError("naive datetime not allowed")
        return parse_timestamp(value.isoformat())
    return parse_timestamp(value)


# UTC-aware timestamp; accepts only RFC 3339 strings with offsets (or aware datetimes).
Timestamp = Annotated[datetime, BeforeValidator(_ts), PlainSerializer(to_canonical, return_type=str)]
NonEmpty = Annotated[str, Field(min_length=1)]
DataMode = Literal["synthetic", "recorded", "emulated", "live", "mock"]
Kind = Literal["gauge", "cumulative_counter", "derived_rate", "interval_summary", "state"]
Value = StrictBool | StrictInt | StrictFloat | StrictStr


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    def to_json_dict(self) -> dict:
        """JSON-compatible dict; omits unset optional subject keys to match schemas."""
        return self.model_dump(mode="json", by_alias=True, exclude_none=False)


class SourceRef(_Model):
    source_id: NonEmpty
    data_mode: DataMode
    source_type: NonEmpty


class Subject(_Model):
    device_id: NonEmpty | None = None
    interface_id: NonEmpty | None = None
    service_id: NonEmpty | None = None
    segment_id: NonEmpty | None = None
    link_id: NonEmpty | None = None

    @model_validator(mode="after")
    def _any_anchor(self) -> "Subject":
        if not (self.device_id or self.service_id or self.segment_id or self.link_id):
            raise ValueError("subject needs at least one of device_id, service_id, segment_id, link_id")
        return self

    def to_json_dict(self) -> dict:
        return self.model_dump(mode="json", exclude_none=True)

    def key(self) -> str:
        """Stable textual key, e.g. 'device=SW-01|interface=eth1'."""
        parts = [f"{k.removesuffix('_id')}={v}" for k, v in self.to_json_dict().items()]
        return "|".join(parts)


class Window(_Model):
    start: Timestamp
    end: Timestamp


class Measurement(_Model):
    metric: NonEmpty
    value: Value
    unit: NonEmpty
    kind: Kind
    window: Window | None = None

    @field_validator("value")
    @classmethod
    def _finite(cls, v: Value) -> Value:
        if isinstance(v, float) and not math.isfinite(v):
            raise ValueError("non-finite measurement value")
        return v

    def to_json_dict(self) -> dict:
        d = self.model_dump(mode="json", exclude={"window"})
        if self.window is not None:
            d["window"] = self.window.to_json_dict()
        return d


class Quality(_Model):
    validation: Literal["passed", "quarantined", "rejected"]
    freshness: Literal["current", "stale", "unknown"]
    flags: tuple[str, ...] = ()

    @field_validator("flags")
    @classmethod
    def _unique(cls, v: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(v)) != len(v):
            raise ValueError("quality flags must be unique")
        return v


class NormalizedObservation(_Model):
    schema_version: Literal["1.0.0"] = NDEP_SCHEMA_VERSION
    observation_id: NonEmpty
    incident_id: NonEmpty
    raw_record_ref: NonEmpty
    source: SourceRef
    subject: Subject
    measurement: Measurement
    observed_at: Timestamp
    ingested_at: Timestamp
    quality: Quality
    lineage_group: NonEmpty
    metric_registry_version: NonEmpty
    transformation_id: str | None = None

    def to_json_dict(self) -> dict:
        d = self.model_dump(mode="json", exclude={"subject", "measurement", "quality"})
        d["subject"] = self.subject.to_json_dict()
        d["measurement"] = self.measurement.to_json_dict()
        d["quality"] = self.quality.model_dump(mode="json")
        d["quality"]["flags"] = list(self.quality.flags)
        return d


class Finding(_Model):
    """A specialist's interpretation of observations. Not a raw fact."""

    schema_version: Literal["1.0.0"] = NDEP_SCHEMA_VERSION
    finding_id: NonEmpty
    incident_id: NonEmpty
    agent_id: NonEmpty
    claim: NonEmpty
    polarity: Literal["present", "absent", "unknown"]
    subject: Subject
    observation_refs: tuple[NonEmpty, ...] = Field(min_length=1)
    rule_or_model_version: NonEmpty
    created_at: Timestamp
    caveats: tuple[str, ...]
    supersedes_finding_id: str | None = None

    @field_validator("observation_refs")
    @classmethod
    def _unique_refs(cls, v: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(v)) != len(v):
            raise ValueError("observation_refs must be unique")
        return v

    def to_json_dict(self) -> dict:
        d = self.model_dump(mode="json", exclude={"subject"})
        d["subject"] = self.subject.to_json_dict()
        d["observation_refs"] = list(self.observation_refs)
        d["caveats"] = list(self.caveats)
        return d


class TopologyNode(_Model):
    id: str
    type: Literal["device", "service", "ap", "segment", "host"]


class TopologyLink(_Model):
    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    id: str
    from_: str = Field(alias="from")
    to: str
    type: Literal["physical", "logical", "dependency", "routing"]
    directed: bool | None = None

    def to_json_dict(self) -> dict:
        return self.model_dump(mode="json", by_alias=True, exclude_none=True)


class TopologySnapshot(_Model):
    schema_version: Literal["1.0.0"] = NDEP_SCHEMA_VERSION
    topology_snapshot_id: NonEmpty
    kind: Literal["intended", "observed", "modeled", "synthetic"]
    observed_at: Timestamp
    nodes: tuple[TopologyNode, ...]
    links: tuple[TopologyLink, ...]
    limitations: tuple[str, ...]

    def to_json_dict(self) -> dict:
        d = self.model_dump(mode="json", exclude={"nodes", "links", "limitations"})
        d["nodes"] = [n.model_dump(mode="json") for n in self.nodes]
        d["links"] = [link.to_json_dict() for link in self.links]
        d["limitations"] = list(self.limitations)
        return d


class RawRecord(_Model):
    """Immutable copy of one source record exactly as received (plus receipt metadata).

    Internal ledger object; not part of the NDEP wire contract. `content` is the
    canonical JSON of the received record and is never modified.
    """

    raw_id: NonEmpty
    incident_id: NonEmpty
    content_hash: NonEmpty  # sha256 of canonical JSON of {"source_id", "record"}
    source: SourceRef
    source_schema: NonEmpty  # e.g. "ndep-telemetry-batch@1.0.0"
    source_record_id: str | None
    batch_id: str | None
    received_at: Timestamp
    content: str
