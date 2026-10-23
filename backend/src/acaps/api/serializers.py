"""Convert backend objects into the documented JSON contract (docs/API.md).

The data model is UI-neutral: plain records, timelines and decisions. Times are integer
microseconds in packet-level data (`...Us`) and float milliseconds in aggregate metrics (`...Ms`).
"""

from typing import Any

from acaps import SCHEMA_VERSION
from acaps.config.models import SimulationConfig
from acaps.core.network import describe_network
from acaps.core.packet import Packet, PacketRecord
from acaps.engine.simulation import DecisionRecord, RunRecord, TimelinePoint
from acaps.experiments.runner import SchedulerRun, SimulationResult


def config_to_dict(config: SimulationConfig) -> dict[str, Any]:
    """Resolved configuration plus derived (informational) values."""
    resolved = config.model_dump(by_alias=True, mode="json")
    resolved["derived"] = describe_network(config)
    return resolved


def packet_to_dict(p: Packet) -> dict[str, Any]:
    return {
        "packetId": p.packet_id,
        "trafficClass": p.traffic_class,
        "arrivalTimeUs": p.arrival_time_us,
        "sizeBytes": p.size_bytes,
        "source": p.source,
        "destination": p.destination,
        "criticalityRank": p.criticality_rank,
        "delayBudgetUs": p.delay_budget_us,
        "deadlineUs": p.deadline_us,
    }


def record_to_dict(r: PacketRecord) -> dict[str, Any]:
    return {
        "packetId": r.packet.packet_id,
        "outcome": r.outcome.value if r.outcome else None,
        "dropReason": r.drop_reason.value if r.drop_reason else None,
        "enqueueTimeUs": r.enqueue_time_us,
        "txStartUs": r.tx_start_us,
        "txEndUs": r.tx_end_us,
        "dropTimeUs": r.drop_time_us,
        "waitingTimeUs": r.waiting_time_us,
        "serviceTimeUs": r.service_time_us,
        "totalDelayUs": r.total_delay_us,
        "deadlineMissed": r.deadline_missed,
        "overtakenCount": r.overtaken_count,
    }


def decision_to_dict(d: DecisionRecord) -> dict[str, Any]:
    out = {
        "timeUs": d.time_us,
        "chosenPacketId": d.chosen_packet_id,
        "chosenClass": d.chosen_class,
        "queueLength": d.queue_length,
        "occupancy": round(d.occupancy, 6),
        "congestionLevel": d.congestion_level.value,
        "reasonCode": d.reason_code,
        "details": d.details,
    }
    if d.candidates is not None:
        out["candidates"] = d.candidates
    return out


def timeline_point_to_dict(t: TimelinePoint) -> dict[str, Any]:
    return {
        "timeUs": t.time_us,
        "queueLength": t.queue_length,
        "occupancy": round(t.occupancy, 6),
        "congestionLevel": t.congestion_level.value,
        "serverBusy": t.server_busy,
        "observedArrivalRatePps": round(t.observed_arrival_rate_pps, 3),
        "observedArrivalRateBps": round(t.observed_arrival_rate_bps, 1),
        "observedDepartureRatePps": round(t.observed_departure_rate_pps, 3),
        "observedDepartureRateBps": round(t.observed_departure_rate_bps, 1),
    }


def _downsample(points: list[TimelinePoint], max_points: int) -> list[TimelinePoint]:
    """Evenly strided subset that always keeps the first and last point."""
    if len(points) <= max_points:
        return points
    stride = (len(points) - 1) / (max_points - 1)
    indices = sorted({round(i * stride) for i in range(max_points)})
    return [points[i] for i in indices]


def run_to_dict(scheduler_run: SchedulerRun, config: SimulationConfig) -> dict[str, Any]:
    run: RunRecord = scheduler_run.run
    opts = config.options
    out: dict[str, Any] = {
        "metrics": scheduler_run.metrics,
        "packets": [record_to_dict(r) for r in run.records],
    }
    if opts.include_queue_timeline:
        out["queueTimeline"] = [
            timeline_point_to_dict(t) for t in _downsample(run.timeline, opts.max_timeline_points)
        ]
    if opts.include_decisions:
        out["decisions"] = [decision_to_dict(d) for d in run.decisions]
    if run.events is not None:
        out["events"] = [
            {"timeUs": e.time_us, "type": e.type.value, "packetId": e.packet_id, "data": e.data}
            for e in run.events
        ]
    return out


def simulation_to_dict(result: SimulationResult) -> dict[str, Any]:
    config = result.config
    out: dict[str, Any] = {
        "schemaVersion": SCHEMA_VERSION,
        "config": config_to_dict(config),
        "workload": {
            "fingerprint": result.workload.fingerprint,
            "packetCount": len(result.workload),
            "packets": [packet_to_dict(p) for p in result.workload.packets],
        },
        "schedulers": {name.value: run_to_dict(run, config) for name, run in result.runs.items()},
        "comparison": result.comparison,
    }
    control = result.size_neutral_control
    if control is not None:
        out["sizeNeutralControl"] = {
            "config": config_to_dict(control.config),
            "workloadFingerprint": control.workload.fingerprint,
            "packetCount": len(control.workload),
            "schedulers": {n.value: {"metrics": r.metrics} for n, r in control.runs.items()},
            "comparison": control.comparison,
        }
    return out


def experiment_to_dict(config: SimulationConfig, experiment: dict[str, Any]) -> dict[str, Any]:
    return {"schemaVersion": SCHEMA_VERSION, "config": config_to_dict(config), **experiment}
