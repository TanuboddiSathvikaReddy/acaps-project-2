"""Scenario presets: plain configuration objects over ONE simulation engine.

RESEARCH-FAIRNESS NOTE
    These presets were fixed BEFORE any scheduler comparison was run and are not tuned
    afterwards. They are defined by LOAD REGIME (offered load rho = lambda*E[size]*8 / C),
    not by which scheduler they favour. All numbers are simulation parameters, not
    networking standards.
    (The two size-neutral variants, emergencyBurstSizeNeutral and networkOverloadSizeNeutral, were
    added after the first comparison run; see docs/EXPERIMENTS.md section 8.4.)

Resolution order for a request:  BASE  ->  scenario preset  ->  fields sent in the request.
Merging rules: scalars replace; `classes` merge per class and per field; `sizeModel` and
`trafficMix` are replaced wholesale; small option objects merge field by field.
"""

import copy
from dataclasses import dataclass, field
from typing import Any, Mapping

from acaps.config.models import (
    FixedSize,
    SimulationConfig,
    reject_legacy_fields,
)

# ---- base ("custom") configuration: every class uses the default fixed packet size -------
BASE_CONFIG: dict[str, Any] = {
    "incomingRate": 400,  # packets/s
    "linkBandwidthMbps": 5.0,
    "queueCapacity": 100,  # packets
    "packetSize": 1200,  # bytes, default for classes without a size model
    "simulationDuration": 10,  # seconds
    "randomSeed": 42,
    "trafficMix": {"emergency": 0.20, "video": 0.30, "gps": 0.20, "normal": 0.30},
    "classes": {  # rank 0 = most critical; budgets are SIMULATION parameters
        "emergency": {"criticalityRank": 0, "delayBudgetMs": 50},
        "video": {"criticalityRank": 1, "delayBudgetMs": 150},
        "gps": {"criticalityRank": 2, "delayBudgetMs": 100},
        "normal": {"criticalityRank": 3, "delayBudgetMs": 500},
    },
    "arrivalModel": "poisson",
    "expiredPacketPolicy": "TRANSMIT_LATE",
}

# Class-correlated packet sizes used by the presets (illustrative simulation parameters).
_VARIABLE_SIZES: dict[str, Any] = {
    "emergency": {"sizeModel": {"type": "uniform", "minBytes": 100, "maxBytes": 400}},
    "video": {"sizeModel": {"type": "uniform", "minBytes": 800, "maxBytes": 1400}},
    "gps": {"sizeModel": {"type": "uniform", "minBytes": 60, "maxBytes": 140}},
    "normal": {
        "sizeModel": {
            "type": "discrete",
            "values": [
                {"bytes": 64, "probability": 0.4},
                {"bytes": 1500, "probability": 0.6},
            ],
        }
    },
}


@dataclass(frozen=True)
class Preset:
    label: str
    description: str
    overrides: dict[str, Any] = field(default_factory=dict)


_HEAVY: dict[str, Any] = {"incomingRate": 800, "linkBandwidthMbps": 5.0, "classes": _VARIABLE_SIZES}

PRESETS: dict[str, Preset] = {
    "custom": Preset(
        "Custom",
        "Base configuration; every class uses the default fixed packetSize. "
        "Override any field in the request.",
    ),
    "normalTraffic": Preset(
        "Normal Traffic",
        "Light load (rho ~ 0.43). Queue stays short; schedulers are expected to look similar.",
        {"incomingRate": 400, "classes": _VARIABLE_SIZES},
    ),
    "heavyTraffic": Preset(
        "Heavy Traffic",
        "Heavy but sub-critical load (rho ~ 0.87). Queue builds up intermittently.",
        _HEAVY,
    ),
    "emergencyBurst": Preset(
        "Emergency Burst",
        "Moderate base load with a 1 s burst at t=4 s: 3x the rate and 60% emergency traffic.",
        {
            "incomingRate": 500,
            "trafficMix": {"emergency": 0.10, "video": 0.30, "gps": 0.20, "normal": 0.40},
            "bursts": [
                {
                    "startTime": 4,
                    "duration": 1,
                    "rateMultiplier": 3,
                    "trafficMixOverride": {
                        "emergency": 0.60,
                        "video": 0.15,
                        "gps": 0.10,
                        "normal": 0.15,
                    },
                }
            ],
            "classes": _VARIABLE_SIZES,
        },
    ),
    "videoHeavy": Preset(
        "Video Heavy",
        "60% of packets are large video packets (rho ~ 0.88).",
        {
            "incomingRate": 600,
            "trafficMix": {"emergency": 0.05, "video": 0.60, "gps": 0.10, "normal": 0.25},
            "classes": _VARIABLE_SIZES,
        },
    ),
    "networkOverload": Preset(
        "Network Overload",
        "Sustained overload (rho ~ 1.08): 800 packets/s offered to a 4 Mbps link.",
        {"incomingRate": 800, "linkBandwidthMbps": 4.0, "classes": _VARIABLE_SIZES},
    ),
    "mixedTraffic": Preset(
        "Mixed Traffic",
        "Moderate base load (rho ~ 0.65) with two 1 s bursts at 2x rate (t=3 s and t=7 s).",
        {
            "incomingRate": 600,
            "bursts": [
                {"startTime": 3, "duration": 1, "rateMultiplier": 2},
                {"startTime": 7, "duration": 1, "rateMultiplier": 2},
            ],
            "classes": _VARIABLE_SIZES,
        },
    ),
    # sizeNeutralControl is filled in below (it is derived from heavyTraffic).
}

# Keys whose values are replaced wholesale instead of merged.
_REPLACE_KEYS = {"trafficMix", "sizeModel", "sizeNeutralModel", "trafficMixOverride", "values"}


def _deep_merge(base: dict[str, Any], over: Mapping[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(base)
    for key, value in over.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict) and key not in _REPLACE_KEYS:
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


def resolve_config(request: Mapping[str, Any] | None = None) -> SimulationConfig:
    """Turn a (possibly partial) request into a fully validated SimulationConfig."""
    request = {k: v for k, v in (request or {}).items() if v is not None}
    reject_legacy_fields(request)
    scenario = request.pop("scenario", None) or "custom"
    if scenario not in PRESETS:
        raise ValueError(f"unknown scenario {scenario!r}; available: {sorted(PRESETS)}")
    merged = _deep_merge(BASE_CONFIG, PRESETS[scenario].overrides)
    merged = _deep_merge(merged, request)
    merged["scenario"] = scenario
    return SimulationConfig.model_validate(merged)


def make_size_neutral(config: SimulationConfig) -> SimulationConfig:
    """Return the SIZE-NEUTRAL CONTROL of a configuration.

    Everything (rate, bandwidth, mix, bursts, deadlines, ranks, queue, seed) is identical, but every
    class uses the SAME size model: `sizeNeutralModel` if given, otherwise a FIXED size chosen as
    follows.

    Size rule: the mean packet size of the PEAK-LOAD PERIOD (the rate segment with the highest
    offered bit rate). Reason: packet loss happens when load is highest, so the control must keep
    the overload window's offered load unchanged. For scenarios with a single traffic mix this is
    simply the mix-weighted mean size (offered load unchanged everywhere). For a scenario whose
    burst uses a different class mix (emergencyBurst) it keeps the BURST load unchanged, while the
    calmer base period gets lighter; the derived `burstOfferedLoad` shows both.

    Because arrival times and class choices come from streams that do not depend on sizes, the
    control workload has exactly the same arrival times and classes as the original.
    """
    model = config.size_neutral_model
    if model is None:

        def mean_size(mix: dict[str, float]) -> float:
            return sum(p * config.classes[c].size_model.mean_bytes for c, p in mix.items())

        peak = max(config.rate_segments(), key=lambda seg: seg.rate_pps * mean_size(seg.mix))
        model = FixedSize(bytes=max(1, round(mean_size(peak.mix))))
    control = config.model_copy(deep=True)
    for cls in control.classes.values():
        cls.size_model = model.model_copy(deep=True)
    control.scenario = f"{config.scenario}+sizeNeutral"
    return control


PRESETS["sizeNeutralControl"] = Preset(
    "Size-Neutral Control",
    "heavyTraffic with every class using the same fixed size (mix-weighted mean), so scheduling "
    "effects can be separated from packet-size effects.",
    {**_HEAVY, "classes": {c: {"sizeModel": {"type": "fixed", "bytes": 678}} for c in BASE_CONFIG["classes"]}},
)


def _size_neutral_variant(source: str) -> Preset:
    """Preset = `source` with every class on the common fixed size chosen by make_size_neutral."""
    control = make_size_neutral(resolve_config({"scenario": source}))
    model = next(iter(control.classes.values())).size_model.model_dump(by_alias=True, mode="json")
    return Preset(
        f"{PRESETS[source].label} (size-neutral)",
        f"{source} with every class using the same fixed packet size ({model['bytes']} B), so scheduler "
        f"differences can be separated from class-correlated packet-size effects. Same rate, "
        f"bandwidth, queue, mix, bursts, deadlines, ranks and seeds as {source}.",
        {**PRESETS[source].overrides, "classes": {c: {"sizeModel": model} for c in BASE_CONFIG["classes"]}},
    )


PRESETS["emergencyBurstSizeNeutral"] = _size_neutral_variant("emergencyBurst")
PRESETS["networkOverloadSizeNeutral"] = _size_neutral_variant("networkOverload")


def list_presets() -> list[str]:
    return list(PRESETS)
