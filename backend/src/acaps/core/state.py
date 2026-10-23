"""SchedulingState: what a scheduler is allowed to look at when it must pick a packet.

Everything here is MEASURED from the simulation clock and the queue contents. Nothing is
configured or random. The simulator builds a fresh state at every scheduling decision.
"""

from collections import deque
from dataclasses import dataclass
from typing import Any, Callable

from acaps.core.network import CongestionLevel
from acaps.core.packet import Packet


@dataclass(frozen=True)
class SchedulingState:
    now_us: int
    waiting: tuple[Packet, ...]  # in queue (arrival) order; the packet in service is excluded
    queue_capacity: int
    congestion_level: CongestionLevel
    tx_time_us: Callable[[int], int]  # size(bytes) -> transmission time (us) on this link
    observed_arrival_rate_pps: float = 0.0
    observed_departure_rate_pps: float = 0.0

    # ---- queue state ------------------------------------------------------
    @property
    def queue_length(self) -> int:
        return len(self.waiting)

    @property
    def occupancy(self) -> float:
        return len(self.waiting) / self.queue_capacity

    # ---- per-packet measurements (all derived from timestamps) -----------
    def waiting_time_us(self, packet: Packet) -> int:
        """currentWaitingTime = now - arrivalTime."""
        return self.now_us - packet.arrival_time_us

    def remaining_deadline_us(self, packet: Packet) -> int:
        """remainingDeadline = deadline - now (<= 0 means expired)."""
        return packet.deadline_us - self.now_us

    def estimated_service_time_us(self, packet: Packet) -> int:
        return self.tx_time_us(packet.size_bytes)

    def slack_us(self, packet: Packet) -> int:
        """How long the packet can still wait and finish on time = remaining - service time."""
        return self.remaining_deadline_us(packet) - self.estimated_service_time_us(packet)

    def deadline_status(self, packet: Packet) -> str:
        return "EXPIRED" if self.remaining_deadline_us(packet) <= 0 else "OPEN"

    def candidate_snapshots(self) -> list[dict[str, Any]]:
        """Plain-dict view of every waiting packet (for the decision log / UI)."""
        return [
            {
                "packetId": p.packet_id,
                "trafficClass": p.traffic_class,
                "sizeBytes": p.size_bytes,
                "arrivalTimeUs": p.arrival_time_us,
                "waitingTimeUs": self.waiting_time_us(p),
                "deadlineUs": p.deadline_us,
                "remainingDeadlineUs": self.remaining_deadline_us(p),
                "criticalityRank": p.criticality_rank,
                "estimatedServiceTimeUs": self.estimated_service_time_us(p),
                "deadlineStatus": self.deadline_status(p),
            }
            for p in self.waiting
        ]


class RateWindow:
    """Sliding-window rate MEASUREMENT (never configured).

    Rate over the window (now - W, now]; during the first W microseconds the divisor is `now`
    so early rates are not artificially low.
    """

    def __init__(self, window_us: int) -> None:
        self.window_us = window_us
        self._events: deque[tuple[int, int]] = deque()  # (time_us, bits)
        self._bits = 0

    def add(self, time_us: int, bits: int) -> None:
        self._events.append((time_us, bits))
        self._bits += bits

    def rates(self, now_us: int) -> tuple[float, float]:
        """Return (packets/s, bits/s) over the window ending at now."""
        horizon = now_us - self.window_us
        while self._events and self._events[0][0] <= horizon:
            self._bits -= self._events.popleft()[1]
        span_us = min(now_us, self.window_us)
        if span_us <= 0:
            return 0.0, 0.0
        span_s = span_us / 1e6
        return len(self._events) / span_s, self._bits / span_s
