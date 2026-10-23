"""ACAPS - Adaptive Context-Aware Packet Scheduling.

DESIGN PRINCIPLE
    Deadline feasibility takes priority over class criticality when a packet is genuinely at
    risk. Criticality is used WITHIN the appropriate urgency tier rather than being converted
    into an arbitrary numerical weight.

There is NO weighted score anywhere in this file. The decision is a lexicographic hierarchy
over quantities that are MEASURED from the simulation clock and the queue:

    1. MEASURE   for every waiting packet p at decision time t
         waiting   = t - arrival
         remaining = deadline - t
         service   = transmission time of p on this link
         slack     = remaining - service      (how long p can still wait and finish on time)

    2. CLASSIFY
         INFEASIBLE : slack < 0                           cannot meet its deadline even if sent now
         liveWork   = sum of service over all non-INFEASIBLE packets
         AT_RISK    : slack < liveWork - service(p)       would miss its deadline if sent LAST
         SAFE       : otherwise                           would still make it even if sent last

    3. AGE       effectiveRank = max(0, criticalityRank - promotions)
         promotions = min(maxPromotionLevels, floor(waiting / (quantumFraction * delayBudget)))

    4. SELECT    first non-empty tier wins:
         AT_RISK     -> min (slack, effectiveRank, arrival, packetId)      least slack first
         SAFE        -> min (effectiveRank, deadline, arrival, packetId)   criticality, then EDF
         INFEASIBLE  -> min (effectiveRank, deadline, arrival, packetId)   triage: saveable first

Every key ends in (arrival, packetId), so the order is total: there is always exactly one winner.
Complexity: O(n) per decision (two passes over the n waiting packets), n <= queue capacity.

Feasibility vs urgency (kept distinct):
    * INFEASIBLE is FEASIBILITY: a property of the packet alone (not enough time left).
    * AT_RISK / SAFE is URGENCY: depends on the queue backlog. A deeper backlog turns more
      packets AT_RISK. Expired/infeasible packets are served last, so they are excluded from
      the backlog that other packets have to wait behind.
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from acaps.config.models import AgingConfig
from acaps.core.packet import Packet
from acaps.core.state import SchedulingState
from acaps.schedulers.base import Decision, ReasonCode, Scheduler, SchedulerName


class Tier(StrEnum):
    AT_RISK = "AT_RISK"
    SAFE = "SAFE"
    INFEASIBLE = "INFEASIBLE"


@dataclass(frozen=True, slots=True)
class Assessment:
    """Everything ACAPS knows about one waiting packet at one decision instant."""

    packet: Packet
    waiting_us: int
    remaining_us: int
    service_us: int
    slack_us: int
    tier: Tier
    promotions: int
    effective_rank: int


def _at_risk_key(a: Assessment, rank: int) -> tuple[int, int, int, int]:
    return (a.slack_us, rank, a.packet.arrival_time_us, a.packet.packet_id)


def _ranked_key(a: Assessment, rank: int) -> tuple[int, int, int, int]:
    return (rank, a.packet.deadline_us, a.packet.arrival_time_us, a.packet.packet_id)


class ACAPSScheduler(Scheduler):
    name = SchedulerName.ACAPS

    def __init__(self, aging: AgingConfig | None = None) -> None:
        self.aging = aging or AgingConfig()

    # ---- aging -----------------------------------------------------------------

    def aging_quantum_us(self, delay_budget_us: int) -> int:
        """One promotion per this much waiting; relative to the packet's OWN delay budget."""
        return max(1, round(self.aging.quantum_fraction * delay_budget_us))

    def promotions(self, packet: Packet, waiting_us: int) -> int:
        """Bounded, deterministic, computed from actual waiting time only (no stored state)."""
        earned = waiting_us // self.aging_quantum_us(packet.delay_budget_us)
        return min(self.aging.max_promotion_levels, earned)

    def effective_rank(self, packet: Packet, waiting_us: int) -> int:
        return max(0, packet.criticality_rank - self.promotions(packet, waiting_us))

    # ---- steps 1-3: measure, classify, age --------------------------------------

    def assess(self, state: SchedulingState) -> tuple[list[Assessment], int]:
        """Measure, classify and age every waiting packet. Returns (assessments, liveWorkUs)."""
        measured = []
        live_work_us = 0
        for p in state.waiting:
            waiting_us = state.waiting_time_us(p)
            remaining_us = state.remaining_deadline_us(p)
            service_us = state.estimated_service_time_us(p)
            slack_us = remaining_us - service_us
            if slack_us >= 0:
                live_work_us += service_us  # only saveable packets delay the others
            measured.append((p, waiting_us, remaining_us, service_us, slack_us))

        assessments = []
        for p, waiting_us, remaining_us, service_us, slack_us in measured:
            if slack_us < 0:
                tier = Tier.INFEASIBLE
            elif slack_us < live_work_us - service_us:  # would miss if sent after all others
                tier = Tier.AT_RISK
            else:
                tier = Tier.SAFE
            promotions = self.promotions(p, waiting_us)
            assessments.append(
                Assessment(
                    packet=p,
                    waiting_us=waiting_us,
                    remaining_us=remaining_us,
                    service_us=service_us,
                    slack_us=slack_us,
                    tier=tier,
                    promotions=promotions,
                    effective_rank=max(0, p.criticality_rank - promotions),
                )
            )
        return assessments, live_work_us

    # ---- step 4: select -----------------------------------------------------------

    def select(self, state: SchedulingState, explain_candidates: bool = False) -> Decision:
        if len(state.waiting) == 1:
            return Decision(state.waiting[0], ReasonCode.ONLY_CANDIDATE)

        assessments, live_work_us = self.assess(state)
        by_tier = {t: [a for a in assessments if a.tier is t] for t in Tier}

        if by_tier[Tier.AT_RISK]:
            tier, pool, key = Tier.AT_RISK, by_tier[Tier.AT_RISK], _at_risk_key
        elif by_tier[Tier.SAFE]:
            tier, pool, key = Tier.SAFE, by_tier[Tier.SAFE], _ranked_key
        else:
            tier, pool, key = Tier.INFEASIBLE, by_tier[Tier.INFEASIBLE], _ranked_key

        winner = min(pool, key=lambda a: key(a, a.effective_rank))
        # Counterfactual for the log: who would win if aging were switched off (raw class rank)?
        raw_winner = min(pool, key=lambda a: key(a, a.packet.criticality_rank))
        aging_changed = winner is not raw_winner

        if tier is Tier.AT_RISK:
            reason = ReasonCode.AT_RISK_LEAST_SLACK
        elif tier is Tier.SAFE:
            reason = (
                ReasonCode.SAFE_AGING_CHANGED_CHOICE if aging_changed else ReasonCode.SAFE_BY_CRITICALITY
            )
        else:
            reason = ReasonCode.INFEASIBLE_TRIAGE

        details: dict[str, Any] = {
            "tier": tier.value,
            "agingChangedChoice": aging_changed,
            "waitingTimeUs": winner.waiting_us,
            "remainingDeadlineUs": winner.remaining_us,
            "slackUs": winner.slack_us,
            "criticalityRank": winner.packet.criticality_rank,
            "effectiveRank": winner.effective_rank,
            "liveWorkUs": live_work_us,
            "atRiskCount": len(by_tier[Tier.AT_RISK]),
            "safeCount": len(by_tier[Tier.SAFE]),
            "infeasibleCount": len(by_tier[Tier.INFEASIBLE]),
        }
        candidate_info = None
        if explain_candidates:
            candidate_info = {
                a.packet.packet_id: {
                    "tier": a.tier.value,
                    "slackUs": a.slack_us,
                    "promotions": a.promotions,
                    "effectiveRank": a.effective_rank,
                }
                for a in assessments
            }
        return Decision(winner.packet, reason, details, candidate_info)


def make_scheduler(name: SchedulerName, aging: AgingConfig | None = None) -> Scheduler:
    """Factory used by the experiment runner (kept here to avoid an extra module)."""
    from acaps.schedulers.fifo import FIFOScheduler
    from acaps.schedulers.static_priority import StaticPriorityScheduler

    if name is SchedulerName.FIFO:
        return FIFOScheduler()
    if name is SchedulerName.STATIC_PRIORITY:
        return StaticPriorityScheduler()
    if name is SchedulerName.ACAPS:
        return ACAPSScheduler(aging)
    raise ValueError(f"unknown scheduler {name!r}")
