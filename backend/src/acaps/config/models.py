"""Simulation configuration (what the USER controls).

The user describes network CONDITIONS: traffic rate, link bandwidth, buffer size, packet
sizes, traffic mix, deadlines. The user never enters latency, waiting time or congestion;
those emerge from the simulation.

Every default / threshold in this file is a SIMULATION PARAMETER, not a networking standard.
"""

import math
import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic.alias_generators import to_camel

from acaps.core.timeunits import mbps_to_bps, ms_to_us, seconds_to_us

MAX_PACKET_BYTES = 65535  # sanity limit (IPv4 maximum), not an MTU model
MAX_EXPECTED_PACKETS = 500_000  # guard against accidental huge runs
_CLASS_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")

# The previous design used serviceRate (packets/s). It was replaced by an independent link
# bandwidth so that bandwidth can never change just because packet size changes.
LEGACY_FIELDS = {
    "serviceRate": (
        "'serviceRate' was removed. Use 'linkBandwidthMbps' (link capacity in Mbps). "
        "Transmission time is derived from packet size and link bandwidth."
    ),
    "service_rate": (
        "'service_rate' was removed. Use 'link_bandwidth_mbps' (link capacity in Mbps)."
    ),
}


def reject_legacy_fields(data: Any) -> None:
    """Raise a clear error for removed fields instead of silently ignoring them."""
    if isinstance(data, dict):
        for key, hint in LEGACY_FIELDS.items():
            if key in data:
                raise ValueError(hint)


class CamelModel(BaseModel):
    """camelCase in the JSON API, snake_case in Python; unknown fields are errors."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")


# --------------------------------------------------------------------------- enums


class ArrivalModel(StrEnum):
    POISSON = "poisson"  # exponential inter-arrival gaps (memoryless)
    CONSTANT = "constant"  # evenly spaced arrivals (useful for clean deterministic tests)


class ExpiredPacketPolicy(StrEnum):
    TRANSMIT_LATE = "TRANSMIT_LATE"  # expired packets stay queued and are delivered late
    DROP_EXPIRED = "DROP_EXPIRED"  # expired packets are dropped at the deadline instant


# --------------------------------------------------------------------------- size models


class FixedSize(CamelModel):
    type: Literal["fixed"] = "fixed"
    bytes: int = Field(ge=1, le=MAX_PACKET_BYTES)

    def sample(self, u: float) -> int:
        return self.bytes

    @property
    def mean_bytes(self) -> float:
        return float(self.bytes)

    @property
    def min_possible(self) -> int:
        return self.bytes

    @property
    def max_possible(self) -> int:
        return self.bytes


class UniformSize(CamelModel):
    """Uniform integer size in [min_bytes, max_bytes]."""

    type: Literal["uniform"] = "uniform"
    min_bytes: int = Field(ge=1, le=MAX_PACKET_BYTES)
    max_bytes: int = Field(ge=1, le=MAX_PACKET_BYTES)

    @model_validator(mode="after")
    def _check_range(self) -> "UniformSize":
        if self.min_bytes > self.max_bytes:
            raise ValueError("minBytes must be <= maxBytes")
        return self

    def sample(self, u: float) -> int:
        span = self.max_bytes - self.min_bytes + 1
        return self.min_bytes + min(int(u * span), span - 1)

    @property
    def mean_bytes(self) -> float:
        return (self.min_bytes + self.max_bytes) / 2

    @property
    def min_possible(self) -> int:
        return self.min_bytes

    @property
    def max_possible(self) -> int:
        return self.max_bytes


class DiscreteChoice(CamelModel):
    bytes: int = Field(ge=1, le=MAX_PACKET_BYTES)
    probability: float = Field(gt=0, le=1)


class DiscreteSize(CamelModel):
    """A few named sizes with probabilities (e.g. small ACK-like and full-size packets)."""

    type: Literal["discrete"] = "discrete"
    values: list[DiscreteChoice] = Field(min_length=1)

    @model_validator(mode="after")
    def _check_probabilities(self) -> "DiscreteSize":
        total = sum(v.probability for v in self.values)
        if not math.isclose(total, 1.0, abs_tol=1e-6):
            raise ValueError(f"discrete size probabilities must sum to 1 (got {total})")
        return self

    def sample(self, u: float) -> int:
        cumulative = 0.0
        for choice in self.values:
            cumulative += choice.probability
            if u < cumulative:
                return choice.bytes
        return self.values[-1].bytes  # guards float rounding of the cumulative sum

    @property
    def mean_bytes(self) -> float:
        return sum(v.bytes * v.probability for v in self.values)

    @property
    def min_possible(self) -> int:
        return min(v.bytes for v in self.values)

    @property
    def max_possible(self) -> int:
        return max(v.bytes for v in self.values)


SizeModel = Annotated[Union[FixedSize, UniformSize, DiscreteSize], Field(discriminator="type")]


# --------------------------------------------------------------------------- sub-configs


class ClassConfig(CamelModel):
    """One traffic class. criticalityRank: 0 = most critical. Equal ranks are allowed."""

    criticality_rank: int = Field(ge=0)
    delay_budget_ms: float = Field(gt=0)
    size_model: SizeModel | None = None  # None -> fixed(packetSize)
    source: str | None = None
    destination: str = "sink"

    @property
    def delay_budget_us(self) -> int:
        return max(1, ms_to_us(self.delay_budget_ms))


class Burst(CamelModel):
    """A time window with a different arrival rate (and optionally a different class mix)."""

    start_time: float = Field(ge=0)  # seconds
    duration: float = Field(gt=0)  # seconds
    rate_multiplier: float = Field(gt=0)
    traffic_mix_override: dict[str, float] = Field(default_factory=dict)


class CongestionThresholds(CamelModel):
    """occupancy < medium -> LOW ; < high -> MEDIUM ; else HIGH. Simulation parameters."""

    medium: float = Field(default=0.30, gt=0, lt=1)
    high: float = Field(default=0.70, gt=0, le=1)

    @model_validator(mode="after")
    def _check_order(self) -> "CongestionThresholds":
        if self.medium >= self.high:
            raise ValueError("congestionThresholds.medium must be < high")
        return self


class AgingConfig(CamelModel):
    """Aging: +1 class promotion per (quantumFraction x own delay budget) waited, capped."""

    quantum_fraction: float = Field(default=0.25, gt=0)
    max_promotion_levels: int = Field(default=2, ge=0)  # 0 disables aging


class StarvationConfig(CamelModel):
    """A packet has 'excessive wait' if waiting > fraction x its own delay budget."""

    excessive_wait_fraction: float = Field(default=0.8, gt=0)


class OutputOptions(CamelModel):
    include_event_log: bool = False
    include_decisions: bool = True
    include_decision_candidates: bool = False
    include_queue_timeline: bool = True
    include_size_neutral_control: bool = False
    max_timeline_points: int = Field(default=2000, ge=2)


@dataclass(frozen=True)
class RateSegment:
    """A period of constant arrival rate and constant class mix."""

    start_us: int
    end_us: int
    rate_pps: float
    mix: dict[str, float]


# --------------------------------------------------------------------------- main config


class SimulationConfig(CamelModel):
    scenario: str = "custom"

    incoming_rate: float = Field(ge=0)  # packets/s, all classes combined
    link_bandwidth_mbps: float = Field(gt=0)  # link capacity C, INDEPENDENT of packet size
    queue_capacity: int = Field(ge=1)  # packets WAITING (the packet in service is not counted)
    packet_size: int = Field(ge=1, le=MAX_PACKET_BYTES)  # default size for classes w/o sizeModel
    simulation_duration: float = Field(gt=0)  # seconds of traffic generation
    traffic_mix: dict[str, float]
    random_seed: int
    classes: dict[str, ClassConfig]

    arrival_model: ArrivalModel = ArrivalModel.POISSON
    bursts: list[Burst] = Field(default_factory=list)
    expired_packet_policy: ExpiredPacketPolicy = ExpiredPacketPolicy.TRANSMIT_LATE
    congestion_thresholds: CongestionThresholds = Field(default_factory=CongestionThresholds)
    aging: AgingConfig = Field(default_factory=AgingConfig)
    starvation: StarvationConfig = Field(default_factory=StarvationConfig)
    observed_rate_window_ms: float = Field(default=500.0, gt=0)
    size_neutral_model: SizeModel | None = None  # used only by the size-neutral control
    options: OutputOptions = Field(default_factory=OutputOptions)

    @model_validator(mode="before")
    @classmethod
    def _reject_legacy(cls, data: Any) -> Any:
        reject_legacy_fields(data)
        return data

    @model_validator(mode="after")
    def _validate_and_resolve(self) -> "SimulationConfig":
        if not self.classes:
            raise ValueError("at least one traffic class is required")
        for name in self.classes:
            if not _CLASS_NAME.match(name):
                raise ValueError(f"invalid class name {name!r} (use letters, digits, underscore)")
        if mbps_to_bps(self.link_bandwidth_mbps) < 1:
            raise ValueError("linkBandwidthMbps is too small")
        if seconds_to_us(self.simulation_duration) < 1:
            raise ValueError("simulationDuration is too small")

        _check_mix(self.traffic_mix, self.classes, "trafficMix")
        for i, burst in enumerate(self.bursts):
            if burst.traffic_mix_override:
                _check_mix(burst.traffic_mix_override, self.classes, f"bursts[{i}].trafficMixOverride")
        ordered = sorted(self.bursts, key=lambda b: b.start_time)
        for a, b in zip(ordered, ordered[1:]):
            if a.start_time + a.duration > b.start_time:
                raise ValueError("bursts must not overlap")

        # Resolve size models: every class ends up with an explicit model.
        for cls in self.classes.values():
            if cls.size_model is None:
                cls.size_model = FixedSize(bytes=self.packet_size)

        expected = sum(
            seg.rate_pps * (seg.end_us - seg.start_us) / 1e6 for seg in self.rate_segments()
        )
        if expected > MAX_EXPECTED_PACKETS:
            raise ValueError(
                f"expected packet count {expected:.0f} exceeds the limit of {MAX_EXPECTED_PACKETS}"
            )
        return self

    # ---- derived helpers -------------------------------------------------

    @property
    def duration_us(self) -> int:
        return seconds_to_us(self.simulation_duration)

    @property
    def link_bandwidth_bps(self) -> int:
        return mbps_to_bps(self.link_bandwidth_mbps)

    def rate_segments(self) -> list[RateSegment]:
        """Split [0, duration) into windows of constant rate and mix (base + bursts)."""
        end_of_run = self.duration_us
        base_rate = self.incoming_rate
        segments: list[RateSegment] = []
        cursor = 0
        for burst in sorted(self.bursts, key=lambda b: b.start_time):
            start = min(seconds_to_us(burst.start_time), end_of_run)
            end = min(seconds_to_us(burst.start_time + burst.duration), end_of_run)
            if start > cursor:
                segments.append(RateSegment(cursor, start, base_rate, self.traffic_mix))
            if end > start:
                mix = burst.traffic_mix_override or self.traffic_mix
                segments.append(RateSegment(start, end, base_rate * burst.rate_multiplier, mix))
            cursor = max(cursor, end)
        if cursor < end_of_run:
            segments.append(RateSegment(cursor, end_of_run, base_rate, self.traffic_mix))
        return segments


def _check_mix(mix: dict[str, float], classes: dict[str, ClassConfig], label: str) -> None:
    unknown = sorted(set(mix) - set(classes))
    if unknown:
        raise ValueError(f"{label} references unknown classes: {unknown}")
    if any(p < 0 for p in mix.values()):
        raise ValueError(f"{label} probabilities must be >= 0")
    total = sum(mix.values())
    if not math.isclose(total, 1.0, abs_tol=1e-6):
        raise ValueError(f"{label} must sum to 1 (got {total})")
