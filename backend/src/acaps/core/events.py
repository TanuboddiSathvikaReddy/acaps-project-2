"""Discrete-event machinery: the future-event list and the event-log vocabulary."""

import heapq
from dataclasses import dataclass, field
from enum import IntEnum, StrEnum
from typing import Any


class EventKind(IntEnum):
    """Internal simulation events. The integer value is the processing order at EQUAL times.

    Order at equal time (documented in docs/ARCHITECTURE.md):
        0 DEADLINE_EXPIRY  - bookkeeping first, so an expired packet is never scheduled
        1 DEPARTURE        - the link becomes free
        2 ARRIVAL          - new packets show up
    Remaining ties are broken by packet id, so processing order is fully deterministic.
    """

    DEADLINE_EXPIRY = 0
    DEPARTURE = 1
    ARRIVAL = 2


class EventQueue:
    """Future-event list ordered by (time_us, kind, packet_id)."""

    def __init__(self) -> None:
        self._heap: list[tuple[int, int, int]] = []

    def push(self, time_us: int, kind: EventKind, packet_id: int) -> None:
        heapq.heappush(self._heap, (time_us, int(kind), packet_id))

    def pop(self) -> tuple[int, EventKind, int]:
        time_us, kind, packet_id = heapq.heappop(self._heap)
        return time_us, EventKind(kind), packet_id

    def __len__(self) -> int:
        return len(self._heap)

    def __bool__(self) -> bool:
        return bool(self._heap)


class LogEventType(StrEnum):
    """Vocabulary of the optional human/UI-facing event log."""

    PACKET_CREATED = "PACKET_CREATED"
    PACKET_ARRIVED = "PACKET_ARRIVED"
    PACKET_QUEUED = "PACKET_QUEUED"
    SCHEDULER_DECISION = "SCHEDULER_DECISION"
    PACKET_TRANSMISSION_STARTED = "PACKET_TRANSMISSION_STARTED"
    PACKET_TRANSMISSION_COMPLETED = "PACKET_TRANSMISSION_COMPLETED"
    PACKET_DROPPED = "PACKET_DROPPED"
    DEADLINE_MISSED = "DEADLINE_MISSED"


@dataclass(slots=True)
class LogEvent:
    time_us: int
    type: LogEventType
    packet_id: int
    data: dict[str, Any] = field(default_factory=dict)
