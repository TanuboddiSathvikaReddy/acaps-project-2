"""FIFO: the clean baseline.

Selects the packet that entered the queue first. No priority, no deadline awareness, no aging.
"""

from acaps.schedulers.base import Decision, ReasonCode, Scheduler, SchedulerName
from acaps.core.state import SchedulingState


class FIFOScheduler(Scheduler):
    name = SchedulerName.FIFO

    def select(self, state: SchedulingState, explain_candidates: bool = False) -> Decision:
        # Total order (arrivalTime, packetId): the earliest arrival wins; equal arrival time
        # (simultaneous arrivals) is resolved by packet id.
        chosen = min(state.waiting, key=lambda p: (p.arrival_time_us, p.packet_id))
        reason = ReasonCode.ONLY_CANDIDATE if len(state.waiting) == 1 else ReasonCode.FIFO_HEAD
        return Decision(chosen, reason)
