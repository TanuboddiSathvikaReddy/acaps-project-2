"""Discrete-event simulation of ONE link with ONE finite buffer (a finite-buffer G/G/1/K system).

    arrivals -> [ BoundedQueue (K waiting packets) ] -> scheduler picks -> [ link / server ] -> departure

Time model     integer microseconds; the clock jumps from event to event.
Events         ARRIVAL, DEPARTURE, DEADLINE_EXPIRY (see core/events.py for equal-time order).
Server         non-preemptive and work-conserving: a transmission is never interrupted, and the
               server never idles while packets wait. After EVERY event, if the server is idle and
               the queue is non-empty, the scheduler is asked for the next packet.
Drop policy    tail-drop, class-blind, decided by the NETWORK (identical for every scheduler).
End of run     arrivals exist only in [0, duration). The simulation then keeps running until every
               accepted packet is delivered or dropped ("drain phase"), so every packet gets a
               final outcome and the accounting identity holds exactly.

The engine only OBSERVES and APPLIES: waiting time, remaining deadline, occupancy and
congestion are computed from timestamps and queue contents, never assigned randomly.
"""

from dataclasses import dataclass, field
from typing import Any

from acaps.config.models import ExpiredPacketPolicy, SimulationConfig
from acaps.core.events import EventKind, EventQueue, LogEvent, LogEventType
from acaps.core.network import CongestionLevel, NetworkModel
from acaps.core.packet import DropReason, Packet, PacketRecord, PacketStatus
from acaps.core.queue import BoundedQueue
from acaps.core.state import RateWindow, SchedulingState
from acaps.core.timeunits import BITS_PER_BYTE, US_PER_MS
from acaps.schedulers.base import Scheduler, SchedulerName
from acaps.traffic.workload import Workload, compute_fingerprint


class SchedulerError(RuntimeError):
    """A scheduler returned something that is not a waiting packet."""


@dataclass(slots=True)
class DecisionRecord:
    time_us: int
    chosen_packet_id: int
    chosen_class: str
    queue_length: int
    occupancy: float
    congestion_level: CongestionLevel
    reason_code: str
    details: dict[str, Any]
    candidates: list[dict[str, Any]] | None = None


@dataclass(slots=True)
class TimelinePoint:
    """Queue/server state, sampled whenever the queue length or server state changes."""

    time_us: int
    queue_length: int
    occupancy: float
    congestion_level: CongestionLevel
    server_busy: bool
    observed_arrival_rate_pps: float
    observed_arrival_rate_bps: float
    observed_departure_rate_pps: float
    observed_departure_rate_bps: float


@dataclass
class RunRecord:
    """Everything one scheduler run produced."""

    scheduler: SchedulerName
    workload: Workload  # the SAME object for every scheduler
    workload_fingerprint: str  # recomputed at the end of the run (proves it was not altered)
    records: list[PacketRecord]  # in packet-id order
    decisions: list[DecisionRecord]
    timeline: list[TimelinePoint]
    events: list[LogEvent] | None
    end_time_us: int  # max(duration, last departure): the observation window is [0, end]
    busy_time_us: int
    max_queue_length: int


class SimulationEngine:
    def __init__(
        self,
        config: SimulationConfig,
        workload: Workload,
        scheduler: Scheduler,
        include_event_log: bool | None = None,
        include_decision_candidates: bool | None = None,
    ) -> None:
        self.config = config
        self.workload = workload
        self.scheduler = scheduler
        self.log_events = config.options.include_event_log if include_event_log is None else include_event_log
        self.log_candidates = (
            config.options.include_decision_candidates
            if include_decision_candidates is None
            else include_decision_candidates
        )
        self.network = NetworkModel(config.link_bandwidth_mbps, config.queue_capacity, config.congestion_thresholds)
        self._window_us = round(config.observed_rate_window_ms * US_PER_MS)

    # ------------------------------------------------------------------ public

    def run(self) -> RunRecord:
        self._reset()
        for packet in self.workload.packets:
            self._packets[packet.packet_id] = packet
            self._events.push(packet.arrival_time_us, EventKind.ARRIVAL, packet.packet_id)
        self._sample_timeline(force=True)

        while self._events:
            time_us, kind, packet_id = self._events.pop()
            self._now = time_us
            packet = self._packets[packet_id]
            if kind is EventKind.ARRIVAL:
                self._on_arrival(packet)
            elif kind is EventKind.DEPARTURE:
                self._on_departure(packet)
            else:
                self._on_deadline_expiry(packet)
            self._dispatch()
            self._sample_timeline()

        self._now = max(self.workload.duration_us, self._last_departure_us)
        self._sample_timeline(force=True)
        return RunRecord(
            scheduler=self.scheduler.name,
            workload=self.workload,
            workload_fingerprint=compute_fingerprint(self.workload.packets, self.workload.duration_us),
            records=[self._records[pid] for pid in sorted(self._records)],
            decisions=self._decisions,
            timeline=self._timeline,
            events=self._log if self.log_events else None,
            end_time_us=self._now,
            busy_time_us=self._busy_time_us,
            max_queue_length=self._max_queue_length,
        )

    # ------------------------------------------------------------------ state

    def _reset(self) -> None:
        """Fresh state for every run: replaying a workload can never leak state."""
        self._now = 0
        self._queue = BoundedQueue(self.config.queue_capacity)
        self._events = EventQueue()
        self._packets: dict[int, Packet] = {}
        self._records: dict[int, PacketRecord] = {}
        self._server_busy = False
        self._busy_time_us = 0
        self._last_departure_us = 0
        self._max_queue_length = 0
        self._decisions: list[DecisionRecord] = []
        self._timeline: list[TimelinePoint] = []
        self._log: list[LogEvent] = []
        self._arrivals = RateWindow(self._window_us)
        self._departures = RateWindow(self._window_us)

    # ------------------------------------------------------------------ event handlers

    def _on_arrival(self, packet: Packet) -> None:
        record = PacketRecord(packet)
        self._records[packet.packet_id] = record
        self._arrivals.add(self._now, packet.size_bytes * BITS_PER_BYTE)
        self._log_event(
            LogEventType.PACKET_CREATED,
            packet,
            trafficClass=packet.traffic_class,
            sizeBytes=packet.size_bytes,
            deadlineUs=packet.deadline_us,
            criticalityRank=packet.criticality_rank,
        )
        self._log_event(LogEventType.PACKET_ARRIVED, packet)

        if not self._queue.try_enqueue(packet):
            # Tail-drop: the buffer is full. This is PACKET LOSS (not a deadline miss).
            record.status = PacketStatus.DROPPED
            record.drop_reason = DropReason.QUEUE_OVERFLOW
            record.drop_time_us = self._now
            self._log_event(
                LogEventType.PACKET_DROPPED,
                packet,
                reason=DropReason.QUEUE_OVERFLOW.value,
                queueLength=len(self._queue),
            )
            return

        record.enqueue_time_us = self._now
        self._events.push(packet.deadline_us, EventKind.DEADLINE_EXPIRY, packet.packet_id)
        self._log_event(
            LogEventType.PACKET_QUEUED,
            packet,
            queueLength=len(self._queue),
            occupancy=self._queue.occupancy,
        )

    def _on_departure(self, packet: Packet) -> None:
        record = self._records[packet.packet_id]
        record.tx_end_us = self._now
        record.status = PacketStatus.DELIVERED
        record.deadline_missed = self._now > packet.deadline_us  # met means txEnd <= deadline
        self._server_busy = False
        self._last_departure_us = self._now
        self._departures.add(self._now, packet.size_bytes * BITS_PER_BYTE)
        self._log_event(
            LogEventType.PACKET_TRANSMISSION_COMPLETED,
            packet,
            waitingTimeUs=record.waiting_time_us,
            serviceTimeUs=record.service_time_us,
            totalDelayUs=record.total_delay_us,
            deadlineMissed=record.deadline_missed,
        )

    def _on_deadline_expiry(self, packet: Packet) -> None:
        """The clock has reached the packet's absolute deadline (remainingDeadline == 0)."""
        record = self._records[packet.packet_id]
        if record.status is PacketStatus.WAITING:
            record.deadline_missed = True  # even if sent now it would finish after the deadline
            self._log_event(LogEventType.DEADLINE_MISSED, packet, state="WAITING")
            if self.config.expired_packet_policy is ExpiredPacketPolicy.DROP_EXPIRED:
                self._queue.remove(packet)
                record.status = PacketStatus.DROPPED
                record.drop_reason = DropReason.DEADLINE_EXPIRED
                record.drop_time_us = self._now
                self._log_event(
                    LogEventType.PACKET_DROPPED, packet, reason=DropReason.DEADLINE_EXPIRED.value
                )
        elif record.status is PacketStatus.IN_SERVICE and record.tx_end_us > packet.deadline_us:
            # Non-preemptive: it cannot be aborted, but it is now certain to finish late.
            record.deadline_missed = True
            self._log_event(LogEventType.DEADLINE_MISSED, packet, state="IN_SERVICE")
        # Already delivered (on time) or dropped: nothing to do.

    # ------------------------------------------------------------------ scheduling

    def _dispatch(self) -> None:
        """If the link is idle and packets wait, ask the scheduler and start transmitting."""
        if self._server_busy or len(self._queue) == 0:
            return
        state = self._build_state()
        decision = self.scheduler.select(state, explain_candidates=self.log_candidates)
        chosen = decision.packet

        # Every packet queued AHEAD of the chosen one was overtaken (used by the starvation metric).
        for waiting in state.waiting:
            if waiting is chosen:
                break
            self._records[waiting.packet_id].overtaken_count += 1
        try:
            self._queue.remove(chosen)
        except KeyError as exc:
            raise SchedulerError(f"{self.scheduler.name} chose a packet that is not waiting") from exc

        self._record_decision(state, decision)

        record = self._records[chosen.packet_id]
        service_us = self.network.tx_time_us(chosen.size_bytes)
        record.status = PacketStatus.IN_SERVICE
        record.tx_start_us = self._now
        record.tx_end_us = self._now + service_us  # known in advance: deterministic service time
        self._server_busy = True
        self._busy_time_us += service_us
        self._events.push(record.tx_end_us, EventKind.DEPARTURE, chosen.packet_id)
        self._log_event(
            LogEventType.PACKET_TRANSMISSION_STARTED,
            chosen,
            waitingTimeUs=record.waiting_time_us,
            serviceTimeUs=service_us,
            expectedEndUs=record.tx_end_us,
        )

    def _build_state(self) -> SchedulingState:
        waiting = self._queue.items()
        occupancy = len(waiting) / self._queue.capacity
        arrival_pps, _ = self._arrivals.rates(self._now)
        departure_pps, _ = self._departures.rates(self._now)
        return SchedulingState(
            now_us=self._now,
            waiting=waiting,
            queue_capacity=self._queue.capacity,
            congestion_level=self.network.congestion_level(occupancy),
            tx_time_us=self.network.tx_time_us,
            observed_arrival_rate_pps=arrival_pps,
            observed_departure_rate_pps=departure_pps,
        )

    def _record_decision(self, state: SchedulingState, decision: Any) -> None:
        candidates = None
        if self.log_candidates:
            candidates = state.candidate_snapshots()
            extra = decision.candidate_info or {}
            for row in candidates:
                row.update(extra.get(row["packetId"], {}))
        chosen = decision.packet
        self._decisions.append(
            DecisionRecord(
                time_us=self._now,
                chosen_packet_id=chosen.packet_id,
                chosen_class=chosen.traffic_class,
                queue_length=state.queue_length,
                occupancy=state.occupancy,
                congestion_level=state.congestion_level,
                reason_code=decision.reason_code.value,
                details=decision.details,
                candidates=candidates,
            )
        )
        self._log_event(
            LogEventType.SCHEDULER_DECISION,
            chosen,
            reasonCode=decision.reason_code.value,
            queueLength=state.queue_length,
            congestionLevel=state.congestion_level.value,
            **decision.details,
        )

    # ------------------------------------------------------------------ observation

    def _sample_timeline(self, force: bool = False) -> None:
        length = len(self._queue)
        self._max_queue_length = max(self._max_queue_length, length)
        last = self._timeline[-1] if self._timeline else None
        if (
            not force
            and last is not None
            and last.queue_length == length
            and last.server_busy == self._server_busy
        ):
            return  # nothing changed
        arrival_pps, arrival_bps = self._arrivals.rates(self._now)
        departure_pps, departure_bps = self._departures.rates(self._now)
        occupancy = self._queue.occupancy
        point = TimelinePoint(
            time_us=self._now,
            queue_length=length,
            occupancy=occupancy,
            congestion_level=self.network.congestion_level(occupancy),
            server_busy=self._server_busy,
            observed_arrival_rate_pps=arrival_pps,
            observed_arrival_rate_bps=arrival_bps,
            observed_departure_rate_pps=departure_pps,
            observed_departure_rate_bps=departure_bps,
        )
        if last is not None and last.time_us == self._now:
            self._timeline[-1] = point  # keep only the settled state at each instant
        else:
            self._timeline.append(point)

    def _log_event(self, event_type: LogEventType, packet: Packet, **data: Any) -> None:
        if self.log_events:
            self._log.append(LogEvent(self._now, event_type, packet.packet_id, data))
