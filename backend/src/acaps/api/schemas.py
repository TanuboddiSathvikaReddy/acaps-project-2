"""Request schemas. Every field is optional: missing fields come from the scenario preset
(or from the base configuration when no scenario is given). Explicit fields override the preset."""

import json
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic.alias_generators import to_camel

from acaps.config.models import reject_legacy_fields


class SimulationRequest(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")

    scenario: str | None = None
    incoming_rate: float | None = Field(default=None, description="packets/s, all classes combined")
    link_bandwidth_mbps: float | None = Field(default=None, description="link capacity in Mbps")
    queue_capacity: int | None = Field(default=None, description="waiting packets")
    packet_size: int | None = Field(default=None, description="default packet size in bytes")
    simulation_duration: float | None = Field(default=None, description="seconds")
    traffic_mix: dict[str, float] | None = None
    random_seed: int | None = None
    classes: dict[str, dict[str, Any]] | None = None
    arrival_model: str | None = None
    bursts: list[dict[str, Any]] | None = None
    expired_packet_policy: str | None = None
    congestion_thresholds: dict[str, Any] | None = None
    aging: dict[str, Any] | None = None
    starvation: dict[str, Any] | None = None
    observed_rate_window_ms: float | None = None
    size_neutral_model: dict[str, Any] | None = None
    options: dict[str, Any] | None = None

    @model_validator(mode="before")
    @classmethod
    def _reject_legacy(cls, data: Any) -> Any:
        reject_legacy_fields(data)
        return data

    def to_config_request(self) -> dict[str, Any]:
        return self.model_dump(by_alias=True, exclude_none=True)


class ExperimentRequest(SimulationRequest):
    runs: int = Field(default=30, ge=1, le=200, description="number of consecutive seeds")

    def to_config_request(self) -> dict[str, Any]:
        return self.model_dump(by_alias=True, exclude_none=True, exclude={"runs"})


def validation_detail(error: Exception) -> Any:
    """JSON-safe error detail for a 422 response."""
    if hasattr(error, "json"):
        return json.loads(error.json(include_url=False))
    return [{"loc": [], "msg": str(error), "type": "value_error"}]
