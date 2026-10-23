"""Network model: one link, one finite buffer.

INPUTS   linkBandwidthMbps (independent), queueCapacity (packets), congestion thresholds
DERIVED  transmission time per packet, congestion level from queue occupancy

The link bandwidth NEVER depends on packet size. Only transmission time does:
    transmissionTime = packetSizeBits / linkBandwidthBps
"""

from enum import StrEnum
from typing import Any

from acaps.config.models import CongestionThresholds, SimulationConfig
from acaps.core.timeunits import mbps_to_bps, transmission_time_us, us_to_ms


class CongestionLevel(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class NetworkModel:
    def __init__(
        self, link_bandwidth_mbps: float, queue_capacity: int, thresholds: CongestionThresholds
    ) -> None:
        self.bandwidth_bps = mbps_to_bps(link_bandwidth_mbps)
        self.queue_capacity = queue_capacity
        self.thresholds = thresholds
        self._tx_cache: dict[int, int] = {}

    def tx_time_us(self, size_bytes: int) -> int:
        cached = self._tx_cache.get(size_bytes)
        if cached is None:
            cached = transmission_time_us(size_bytes, self.bandwidth_bps)
            self._tx_cache[size_bytes] = cached
        return cached

    def congestion_level(self, occupancy: float) -> CongestionLevel:
        """Derived from queue occupancy; thresholds are configurable simulation parameters."""
        if occupancy < self.thresholds.medium:
            return CongestionLevel.LOW
        if occupancy < self.thresholds.high:
            return CongestionLevel.MEDIUM
        return CongestionLevel.HIGH


def describe_network(config: SimulationConfig) -> dict[str, Any]:
    """Informational quantities derived from the configuration (never fed to a scheduler)."""
    bps = config.link_bandwidth_bps
    network = NetworkModel(config.link_bandwidth_mbps, config.queue_capacity, config.congestion_thresholds)

    def mean_size(mix: dict[str, float]) -> float:
        return sum(p * config.classes[c].size_model.mean_bytes for c, p in mix.items())

    def load(rate: float, mix: dict[str, float]) -> float:
        return rate * mean_size(mix) * 8 / bps

    base_mean = mean_size(config.traffic_mix)
    used = {c for c, p in config.traffic_mix.items() if p > 0}
    for burst in config.bursts:
        used |= {c for c, p in burst.traffic_mix_override.items() if p > 0}
    max_size = max(config.classes[c].size_model.max_possible for c in used)
    # Upper bound on the delay of an ACCEPTED packet under FIFO: (K+1) worst-case transmissions.
    fifo_bound_us = (config.queue_capacity + 1) * network.tx_time_us(max_size)

    by_class: dict[str, Any] = {}
    warnings: list[str] = []
    for name, cls in sorted(config.classes.items()):
        model = cls.size_model
        budget_us = cls.delay_budget_us
        quantum_us = max(1, round(config.aging.quantum_fraction * budget_us))
        by_class[name] = {
            "criticalityRank": cls.criticality_rank,
            "delayBudgetUs": budget_us,
            "agingQuantumUs": quantum_us,
            "sizeModel": model.model_dump(by_alias=True, mode="json"),
            "meanSizeBytes": model.mean_bytes,
            "txTimeUs": {
                "min": network.tx_time_us(model.min_possible),
                "mean": model.mean_bytes * 8 / bps * 1e6,
                "max": network.tx_time_us(model.max_possible),
            },
        }
        if name in used and budget_us >= fifo_bound_us:
            warnings.append(
                f"class '{name}': delay budget {us_to_ms(budget_us):.1f} ms >= FIFO delay bound "
                f"{us_to_ms(fifo_bound_us):.1f} ms, so FIFO can never miss this deadline "
                f"(other schedulers can, because they may serve packets out of arrival order)."
            )

    return {
        "linkBandwidthBps": bps,
        "meanPacketSizeBytes": base_mean,
        "offeredLoad": load(config.incoming_rate, config.traffic_mix),
        "equivalentPacketRatePps": bps / (8 * base_mean),
        "fifoWaitBoundUs": fifo_bound_us,
        "burstOfferedLoad": [
            load(
                config.incoming_rate * b.rate_multiplier,
                b.traffic_mix_override or config.traffic_mix,
            )
            for b in config.bursts
        ],
        "byClass": by_class,
        "warnings": warnings,
    }
