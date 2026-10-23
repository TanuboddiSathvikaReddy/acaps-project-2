"""MetricsEngine: turns one RunRecord into numbers. Formulas are documented in docs/METRICS.md.

Notation (after the drain phase):
    G   generated packets                 A   accepted (entered the queue) = D + L_e
    D   delivered                         O   delivered on time (txEnd <= deadline)
    L_o dropped by queue overflow         L_e dropped by deadline expiry
    W   observation window [0, endTime],  endTime = max(duration, last departure)

Rules:
    * Denominators are stated for every rate and never mixed.
    * An empty denominator gives None (never 0 and never NaN).
    * Invariants G = D + L_o + L_e and A = D + L_e are CHECKED; a violation raises an error
      instead of silently reporting invalid metrics.
"""

import math
from collections import defaultdict
from typing import Any, Iterable

from acaps.core.network import CongestionLevel
from acaps.core.packet import DropReason, PacketRecord, PacketStatus
from acaps.core.timeunits import BITS_PER_BYTE, US_PER_MS, US_PER_S
from acaps.engine.simulation import RunRecord


class MetricsInvariantError(AssertionError):
    """The run's packet accounting is inconsistent."""


def _ratio(numerator: float, denominator: float) -> float | None:
    return None if denominator == 0 else round(numerator / denominator, 6)


def _ms(microseconds: float | None) -> float | None:
    return None if microseconds is None else round(microseconds / US_PER_MS, 6)


def _percentile_nearest_rank(sorted_values: list[int], q: float) -> int | None:
    if not sorted_values:
        return None
    rank = max(1, math.ceil(q * len(sorted_values)))
    return sorted_values[rank - 1]


class MetricsEngine:
    def __init__(self, excessive_wait_fraction: float = 0.8) -> None:
        self.excessive_wait_fraction = excessive_wait_fraction

    def compute(self, run: RunRecord, class_names: Iterable[str], queue_capacity: int) -> dict[str, Any]:
        window_us = run.end_time_us
        names = sorted(class_names)
        by_class: dict[str, list[PacketRecord]] = defaultdict(list)
        for record in run.records:
            by_class[record.packet.traffic_class].append(record)

        overall = self._summarize(run.records, window_us)
        overall["utilization"] = _ratio(run.busy_time_us, window_us)
        overall["observationWindowMs"] = _ms(window_us)
        per_class = {name: self._summarize(by_class.get(name, []), window_us) for name in names}
        self._check_invariants(run, overall, per_class)
        return {
            "overall": overall,
            "perClass": per_class,
            "queue": self._queue_stats(run, queue_capacity),
        }

    # ------------------------------------------------------------------ per record set

    def _summarize(self, records: list[PacketRecord], window_us: int) -> dict[str, Any]:
        generated = len(records)
        delivered = [r for r in records if r.status is PacketStatus.DELIVERED]
        on_time = [r for r in delivered if not r.deadline_missed]
        overflow = [r for r in records if r.drop_reason is DropReason.QUEUE_OVERFLOW]
        expired = [r for r in records if r.drop_reason is DropReason.DEADLINE_EXPIRED]
        accepted = generated - len(overflow)

        d, o, l_o, l_e = len(delivered), len(on_time), len(overflow), len(expired)
        missed = (d - o) + l_e  # late deliveries + expiry drops (overflow drops are LOSS, not misses)

        waits = [r.waiting_time_us for r in delivered]
        services = [r.service_time_us for r in delivered]
        delays = sorted(r.total_delay_us for r in delivered)
        delivered_bits = sum(r.packet.size_bytes for r in delivered) * BITS_PER_BYTE

        # Excessive wait / starvation are measured over ACCEPTED packets. Expired drops waited
        # from arrival until their drop instant.
        accepted_records = [r for r in records if r.drop_reason is not DropReason.QUEUE_OVERFLOW]
        excessive = [
            r
            for r in accepted_records
            if r.waiting_time_us is not None
            and r.waiting_time_us > self.excessive_wait_fraction * r.packet.delay_budget_us
        ]
        starved = [r for r in excessive if r.overtaken_count >= 1]

        jitter_sum, jitter_pairs = self._jitter_sum_and_pairs(delivered)
        window_s = window_us / US_PER_S

        return {
            "generated": generated,
            "accepted": accepted,
            "delivered": d,
            "deliveredOnTime": o,
            "deliveredLate": d - o,
            "droppedOverflow": l_o,
            "droppedExpired": l_e,
            "dropped": l_o + l_e,
            "packetLossRate": _ratio(l_o + l_e, generated),
            "deadlineMisses": missed,
            "deadlineMissRate": _ratio(missed, generated),
            "deadlineMissRateAccepted": _ratio(missed, accepted),
            "onTimeRate": _ratio(o, generated),
            "avgWaitingTimeMs": _ms(sum(waits) / d) if d else None,
            "avgServiceTimeMs": _ms(sum(services) / d) if d else None,
            "avgTotalDelayMs": _ms(sum(delays) / d) if d else None,
            "maxWaitingTimeMs": _ms(max(waits)) if d else None,
            "p95TotalDelayMs": _ms(_percentile_nearest_rank(delays, 0.95)),
            "throughputPps": _ratio(d, window_s),
            "throughputBps": _ratio(delivered_bits, window_s),
            "deliveredBits": delivered_bits,
            "meanPacketSizeBytes": _ratio(sum(r.packet.size_bytes for r in records), generated),
            "jitterMs": _ms(jitter_sum / jitter_pairs) if jitter_pairs else None,
            "excessiveWaitCount": len(excessive),
            "starvationCount": len(starved),
            "excessiveWaitRateAccepted": _ratio(len(excessive), accepted),
            "starvationRateAccepted": _ratio(len(starved), accepted),
        }

    @staticmethod
    def _jitter_sum_and_pairs(delivered: list[PacketRecord]) -> tuple[int, int]:
        """Delay variation between CONSECUTIVE delivered packets of the SAME class.

        d_i = totalDelay of the i-th delivered packet of the class, in departure order
        jitter = mean over consecutive pairs of |d_i - d_(i-1)|      (IPDV-style, RFC 3393)

        The overall figure pools the per-class pairs, so it measures delay variation within
        each class instead of the (large, expected) difference between different classes.
        """
        sequences: dict[str, list[PacketRecord]] = defaultdict(list)
        for record in delivered:
            sequences[record.packet.traffic_class].append(record)
        total, pairs = 0, 0
        for sequence in sequences.values():
            sequence.sort(key=lambda r: (r.tx_end_us, r.packet.packet_id))
            for previous, current in zip(sequence, sequence[1:]):
                total += abs(current.total_delay_us - previous.total_delay_us)
                pairs += 1
        return total, pairs

    # ------------------------------------------------------------------ queue behaviour

    @staticmethod
    def _queue_stats(run: RunRecord, capacity: int) -> dict[str, Any]:
        """Time-weighted statistics over [0, endTime]: each timeline point holds until the next.

        meanQueueLength = (integral of queueLength dt) / W     (packets WAITING, not in service)
        """
        window_us = run.end_time_us
        if window_us <= 0 or not run.timeline:
            return {
                "meanQueueLength": None,
                "meanOccupancy": None,
                "maxQueueLength": run.max_queue_length,
                "maxOccupancy": _ratio(run.max_queue_length, capacity),
                "congestionTimeShare": None,
            }
        area = 0
        time_in_level = {level: 0 for level in CongestionLevel}
        for a, b in zip(run.timeline, run.timeline[1:]):
            dt = max(0, min(b.time_us, window_us) - a.time_us)
            area += a.queue_length * dt
            time_in_level[a.congestion_level] += dt
        mean_length = area / window_us
        return {
            "meanQueueLength": round(mean_length, 6),
            "meanOccupancy": round(mean_length / capacity, 6),
            "maxQueueLength": run.max_queue_length,
            "maxOccupancy": _ratio(run.max_queue_length, capacity),
            "congestionTimeShare": {
                level.value: round(time_in_level[level] / window_us, 6) for level in CongestionLevel
            },
        }

    # ------------------------------------------------------------------ invariants

    @staticmethod
    def _check_invariants(run: RunRecord, overall: dict[str, Any], per_class: dict[str, Any]) -> None:
        for record in run.records:
            if record.status not in (PacketStatus.DELIVERED, PacketStatus.DROPPED):
                raise MetricsInvariantError(
                    f"packet {record.packet.packet_id} has no final outcome ({record.status})"
                )
        g, d = overall["generated"], overall["delivered"]
        l_o, l_e, a = overall["droppedOverflow"], overall["droppedExpired"], overall["accepted"]
        if g != len(run.workload.packets):
            raise MetricsInvariantError("generated count differs from the workload size")
        if g != d + l_o + l_e:
            raise MetricsInvariantError(f"G ({g}) != D + L_o + L_e ({d + l_o + l_e})")
        if a != d + l_e:
            raise MetricsInvariantError(f"A ({a}) != D + L_e ({d + l_e})")
        for key in ("generated", "accepted", "delivered", "droppedOverflow", "droppedExpired", "deadlineMisses"):
            class_total = sum(stats[key] for stats in per_class.values())
            if class_total != overall[key]:
                raise MetricsInvariantError(f"per-class {key} ({class_total}) != overall ({overall[key]})")
