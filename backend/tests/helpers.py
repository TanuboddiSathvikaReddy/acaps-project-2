"""Shared test helpers. Default link is 1 Mbps, so transmission time in us = size_bytes * 8
(125 B = 1000 us = 1 ms), which keeps hand calculations easy."""

from acaps.config.presets import resolve_config
from acaps.core.network import CongestionLevel, NetworkModel
from acaps.core.packet import Packet
from acaps.core.state import SchedulingState
from acaps.engine.simulation import RunRecord, SimulationEngine
from acaps.schedulers.acaps import make_scheduler
from acaps.schedulers.base import SchedulerName
from acaps.traffic.workload import Workload

RANK = {"emergency": 0, "video": 1, "gps": 2, "normal": 3}
BUDGET_MS = {"emergency": 50, "video": 150, "gps": 100, "normal": 500}
MS = 1000  # microseconds per millisecond


def make_config(**overrides):
    """Config on a 1 Mbps link with the default four classes and fixed packet sizes."""
    request = {"linkBandwidthMbps": 1.0, "simulationDuration": 1, "queueCapacity": 100}
    request.update(overrides)
    return resolve_config(request)


def pkt(pid, cls="normal", t=0, size=125, budget_us=None, rank=None):
    return Packet(
        packet_id=pid,
        traffic_class=cls,
        arrival_time_us=t,
        size_bytes=size,
        source=f"{cls}-src",
        destination="sink",
        criticality_rank=RANK[cls] if rank is None else rank,
        delay_budget_us=BUDGET_MS[cls] * MS if budget_us is None else budget_us,
    )


def run_engine(config, packets, scheduler="FIFO", duration_us=None, **kwargs) -> RunRecord:
    workload = Workload.from_packets(packets, duration_us or config.duration_us)
    sched = make_scheduler(SchedulerName(scheduler), config.aging)
    return SimulationEngine(config, workload, sched, **kwargs).run()


def rec(run: RunRecord, packet_id: int):
    return next(r for r in run.records if r.packet.packet_id == packet_id)


def make_state(now_us, packets, capacity=100, bandwidth_bps=1_000_000):
    """Hand-built SchedulingState (waiting list in the order given)."""
    network = NetworkModel(bandwidth_bps / 1e6, capacity, make_config().congestion_thresholds)
    return SchedulingState(
        now_us=now_us,
        waiting=tuple(packets),
        queue_capacity=capacity,
        congestion_level=CongestionLevel.LOW,
        tx_time_us=network.tx_time_us,
    )


def drain(scheduler, packets, start_us, bandwidth_bps=1_000_000):
    """Serve `packets` one by one with `scheduler` starting at start_us (no new arrivals).
    Returns [(packet_id, completion_us), ...] in service order."""
    network = NetworkModel(bandwidth_bps / 1e6, 100, make_config().congestion_thresholds)
    waiting, now, order = list(packets), start_us, []
    while waiting:
        state = make_state(now, waiting, bandwidth_bps=bandwidth_bps)
        chosen = scheduler.select(state).packet
        waiting.remove(chosen)
        now += network.tx_time_us(chosen.size_bytes)
        order.append((chosen.packet_id, now))
    return order
