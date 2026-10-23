"""Static (fixed) Priority.

The priority of a packet is a FIXED function of its traffic class (criticalityRank, 0 = highest,
configured per scenario). It never changes with waiting time, deadline or queue state:
no aging, no deadline awareness. Within one class the order is FIFO.

Consequence (by design): a continuous stream of high-priority packets can starve lower classes.
"""

from acaps.schedulers.base import Decision, ReasonCode, Scheduler, SchedulerName
from acaps.core.state import SchedulingState


class StaticPriorityScheduler(Scheduler):
    name = SchedulerName.STATIC_PRIORITY

    def select(self, state: SchedulingState, explain_candidates: bool = False) -> Decision:
        chosen = min(
            state.waiting,
            key=lambda p: (p.criticality_rank, p.arrival_time_us, p.packet_id),
        )
        reason = (
            ReasonCode.ONLY_CANDIDATE
            if len(state.waiting) == 1
            else ReasonCode.STATIC_PRIORITY_CLASS
        )
        return Decision(chosen, reason)
