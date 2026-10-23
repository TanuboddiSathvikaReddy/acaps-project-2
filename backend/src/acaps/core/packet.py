"""Packet model.

Strict separation (required by the project brief):

  A. INITIAL PACKET INFORMATION  -> `Packet`        (immutable, known at creation)
  B. DYNAMICALLY CALCULATED STATE -> `PacketRecord`  (mutable, one per packet per run,
                                                     filled in ONLY by the simulation)

`Packet` objects live in the shared, immutable workload. Every scheduler run gets its own
`PacketRecord`s, so replaying the same workload can never leak state between schedulers.
"""

from dataclasses import dataclass
from enum import StrEnum


@dataclass(frozen=True, slots=True)
class Packet:
    """Information that is actually known when the packet is created."""

    packet_id: int
    traffic_class: str
    arrival_time_us: int  # creation time == arrival time at the queue
    size_bytes: int
    source: str
    destination: str
    criticality_rank: int  # 0 = most critical (fixed property of the traffic class)
    delay_budget_us: int  # application delay requirement of the class

    @property
    def deadline_us(self) -> int:
        """Absolute deadline = arrivalTime + delayBudget."""
        return self.arrival_time_us + self.delay_budget_us


class PacketStatus(StrEnum):
    WAITING = "WAITING"
    IN_SERVICE = "IN_SERVICE"
    DELIVERED = "DELIVERED"
    DROPPED = "DROPPED"


class DropReason(StrEnum):
    QUEUE_OVERFLOW = "QUEUE_OVERFLOW"  # buffer full on arrival (packet loss)
    DEADLINE_EXPIRED = "DEADLINE_EXPIRED"  # removed at its deadline (policy DROP_EXPIRED)


class Outcome(StrEnum):
    ON_TIME = "ON_TIME"  # delivered, txEnd <= deadline
    LATE = "LATE"  # delivered, txEnd >  deadline  (deadline miss, NOT a loss)
    DROPPED = "DROPPED"


@dataclass(slots=True)
class PacketRecord:
    """Dynamic state of one packet during one scheduler run. Never randomly assigned."""

    packet: Packet
    status: PacketStatus = PacketStatus.WAITING
    enqueue_time_us: int | None = None
    tx_start_us: int | None = None
    tx_end_us: int | None = None
    drop_time_us: int | None = None
    drop_reason: DropReason | None = None
    deadline_missed: bool = False
    overtaken_count: int = 0  # times a later-queued packet was selected ahead of this one

    @property
    def waiting_time_us(self) -> int | None:
        """transmissionStart - arrival (delivered), or dropTime - arrival (expired drop)."""
        if self.tx_start_us is not None:
            return self.tx_start_us - self.packet.arrival_time_us
        if self.drop_reason is DropReason.DEADLINE_EXPIRED and self.drop_time_us is not None:
            return self.drop_time_us - self.packet.arrival_time_us
        return None  # overflow-dropped packets never waited

    @property
    def service_time_us(self) -> int | None:
        """transmissionEnd - transmissionStart."""
        if self.tx_start_us is None or self.tx_end_us is None:
            return None
        return self.tx_end_us - self.tx_start_us

    @property
    def total_delay_us(self) -> int | None:
        """transmissionEnd - arrival  (= waiting + service)."""
        if self.tx_end_us is None:
            return None
        return self.tx_end_us - self.packet.arrival_time_us

    @property
    def outcome(self) -> Outcome | None:
        if self.status is PacketStatus.DROPPED:
            return Outcome.DROPPED
        if self.status is PacketStatus.DELIVERED:
            return Outcome.LATE if self.deadline_missed else Outcome.ON_TIME
        return None
