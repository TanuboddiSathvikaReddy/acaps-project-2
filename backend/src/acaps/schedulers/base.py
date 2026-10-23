"""Common scheduler interface.

A scheduler is a PURE FUNCTION of the current SchedulingState: select(state) -> Decision.
It has no memory, no randomness and no access to the future, so the three schedulers can be
swapped without touching the network model.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, ClassVar

from acaps.core.packet import Packet
from acaps.core.state import SchedulingState


class SchedulerName(StrEnum):
    FIFO = "FIFO"
    STATIC_PRIORITY = "STATIC_PRIORITY"
    ACAPS = "ACAPS"


class ReasonCode(StrEnum):
    ONLY_CANDIDATE = "ONLY_CANDIDATE"
    FIFO_HEAD = "FIFO_HEAD"
    STATIC_PRIORITY_CLASS = "STATIC_PRIORITY_CLASS"
    AT_RISK_LEAST_SLACK = "AT_RISK_LEAST_SLACK"
    SAFE_BY_CRITICALITY = "SAFE_BY_CRITICALITY"
    SAFE_AGING_CHANGED_CHOICE = "SAFE_AGING_CHANGED_CHOICE"
    INFEASIBLE_TRIAGE = "INFEASIBLE_TRIAGE"


@dataclass(frozen=True)
class Decision:
    packet: Packet
    reason_code: ReasonCode
    details: dict[str, Any] = field(default_factory=dict)  # scheduler-specific, for the log
    candidate_info: dict[int, dict[str, Any]] | None = None  # per-packet extras (optional)


class Scheduler(ABC):
    name: ClassVar[SchedulerName]

    @abstractmethod
    def select(self, state: SchedulingState, explain_candidates: bool = False) -> Decision:
        """Choose ONE packet from state.waiting (which is never empty)."""
