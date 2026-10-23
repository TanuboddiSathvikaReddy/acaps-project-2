"""Discrete-event engine behaviour and the edge cases from the brief (section 34)."""

import pytest

from acaps.core.packet import DropReason, Outcome
from acaps.metrics.engine import MetricsEngine
from acaps.traffic.generator import TrafficGenerator
from helpers import MS, make_config, pkt, rec, run_engine


# ---------------------------------------------------------------- basic timing


def test_empty_workload_does_not_crash_and_gives_empty_metrics():
    cfg = make_config()
    run = run_engine(cfg, [], "ACAPS")
    m = MetricsEngine().compute(run, cfg.classes, cfg.queue_capacity)
    assert run.records == [] and run.decisions == []
    assert m["overall"]["generated"] == 0
    assert m["overall"]["packetLossRate"] is None and m["overall"]["avgWaitingTimeMs"] is None
    assert m["queue"]["maxQueueLength"] == 0


def test_single_packet_timestamps_and_delays():
    run = run_engine(make_config(), [pkt(1, size=125, t=5000)])
    r = rec(run, 1)
    assert (r.tx_start_us, r.tx_end_us) == (5000, 6000)
    assert r.waiting_time_us == 0            # txStart - arrival
    assert r.service_time_us == 1000         # txEnd - txStart = 125*8 bits / 1 Mbps
    assert r.total_delay_us == 1000          # txEnd - arrival
    assert r.outcome is Outcome.ON_TIME


def test_waiting_time_and_total_delay_for_queued_packets():
    run = run_engine(make_config(), [pkt(1), pkt(2), pkt(3)])  # 3 simultaneous 1 ms packets
    assert [rec(run, i).waiting_time_us for i in (1, 2, 3)] == [0, 1000, 2000]
    assert [rec(run, i).total_delay_us for i in (1, 2, 3)] == [1000, 2000, 3000]
    for i in (1, 2, 3):
        r = rec(run, i)
        assert r.total_delay_us == r.waiting_time_us + r.service_time_us


def test_transmission_time_depends_on_size_and_bandwidth_only():
    run = run_engine(make_config(), [pkt(1, size=125), pkt(2, size=1250)])
    assert rec(run, 1).service_time_us == 1000
    assert rec(run, 2).service_time_us == 10000
    fast = run_engine(make_config(linkBandwidthMbps=10.0), [pkt(1, size=1250)])
    assert rec(fast, 1).service_time_us == 1000


# ---------------------------------------------------------------- arrival rate vs service rate


def _spaced(n, gap_us, size=125):
    return [pkt(i + 1, t=i * gap_us, size=size) for i in range(n)]


def test_arrival_slower_than_service_queue_stays_empty():
    run = run_engine(make_config(), _spaced(20, 2000))  # 1 ms service, 2 ms spacing
    assert all(r.waiting_time_us == 0 for r in run.records)
    assert run.max_queue_length == 0


def test_arrival_equal_to_service_no_queue_builds():
    # departure at t and arrival at t: DEPARTURE is processed first, so the link is free.
    run = run_engine(make_config(), _spaced(20, 1000))
    assert all(r.waiting_time_us == 0 for r in run.records)
    assert run.max_queue_length == 0


def test_arrival_faster_than_service_queue_grows_then_drains_after_arrivals_stop():
    run = run_engine(make_config(), _spaced(30, 500), duration_us=15_000)  # 2x overload
    waits = [rec(run, i).waiting_time_us for i in range(1, 31)]
    assert waits == sorted(waits) and waits[-1] > waits[0]     # waiting emerges and grows
    assert run.max_queue_length >= 14
    assert run.timeline[-1].queue_length == 0                    # drained by the end
    assert run.end_time_us == 30_000                             # drain phase ran past the duration


# ---------------------------------------------------------------- overflow


def test_queue_overflow_drops_are_recorded_with_reason():
    cfg = make_config(queueCapacity=2)
    run = run_engine(cfg, [pkt(i) for i in range(1, 6)])  # 5 simultaneous arrivals
    # #1 goes straight into service, #2 and #3 fill the buffer, #4 and #5 overflow
    assert [rec(run, i).drop_reason for i in (1, 2, 3)] == [None, None, None]
    for i in (4, 5):
        r = rec(run, i)
        assert r.drop_reason is DropReason.QUEUE_OVERFLOW and r.outcome is Outcome.DROPPED
        assert r.drop_time_us == 0 and r.tx_start_us is None
    assert run.max_queue_length == 2


def test_continuous_overload_accounting_holds_for_every_scheduler():
    cfg = make_config(queueCapacity=5)
    packets = _spaced(200, 300)  # arrivals 3.3x faster than the link can serve
    for name in ("FIFO", "STATIC_PRIORITY", "ACAPS"):
        run = run_engine(cfg, packets, name, duration_us=60_000)
        m = MetricsEngine().compute(run, cfg.classes, cfg.queue_capacity)["overall"]
        assert m["generated"] == m["delivered"] + m["droppedOverflow"] + m["droppedExpired"]
        assert m["droppedOverflow"] > 100


# ---------------------------------------------------------------- deadlines


def test_extremely_short_deadline_always_missed_and_counted_as_late_not_loss():
    cfg = make_config()
    run = run_engine(cfg, [pkt(1, budget_us=1), pkt(2, t=10_000, budget_us=1)])
    for i in (1, 2):
        r = rec(run, i)
        assert r.outcome is Outcome.LATE and r.deadline_missed and r.drop_reason is None
    m = MetricsEngine().compute(run, cfg.classes, cfg.queue_capacity)["overall"]
    assert m["deadlineMissRate"] == 1.0 and m["packetLossRate"] == 0.0


def test_extremely_long_deadline_never_missed():
    cfg = make_config()
    run = run_engine(cfg, [pkt(i, budget_us=10**12) for i in range(1, 11)])
    assert not any(r.deadline_missed for r in run.records)


def test_deadline_met_means_tx_end_le_deadline():
    # exactly on the deadline is met; one microsecond later is missed
    run = run_engine(make_config(), [pkt(1, budget_us=1000), pkt(2, t=5000, budget_us=999)])
    assert not rec(run, 1).deadline_missed and rec(run, 1).tx_end_us == 1000
    assert rec(run, 2).deadline_missed


def test_expired_packet_transmit_late_policy_delivers_it_late():
    cfg = make_config(expiredPacketPolicy="TRANSMIT_LATE")
    run = run_engine(cfg, [pkt(1), pkt(2, budget_us=500)])  # #2 expires while #1 is being sent
    r = rec(run, 2)
    assert r.outcome is Outcome.LATE and r.deadline_missed
    assert (r.tx_start_us, r.tx_end_us) == (1000, 2000)


def test_expired_packet_drop_policy_drops_at_the_deadline_instant():
    cfg = make_config(expiredPacketPolicy="DROP_EXPIRED")
    run = run_engine(cfg, [pkt(1), pkt(2, budget_us=500)])
    r = rec(run, 2)
    assert r.drop_reason is DropReason.DEADLINE_EXPIRED
    assert r.drop_time_us == 500 and r.waiting_time_us == 500 and r.deadline_missed
    m = MetricsEngine().compute(run, cfg.classes, cfg.queue_capacity)["overall"]
    # an expiry drop is BOTH a loss and a deadline miss; overflow would be loss only
    assert m["droppedExpired"] == 1 and m["deadlineMisses"] == 1 and m["packetLossRate"] == 0.5


def test_overflow_is_loss_but_not_a_deadline_miss():
    cfg = make_config(queueCapacity=1)
    run = run_engine(cfg, [pkt(i) for i in range(1, 5)])
    m = MetricsEngine().compute(run, cfg.classes, cfg.queue_capacity)["overall"]
    assert m["droppedOverflow"] == 2 and m["deadlineMisses"] == 0
    assert m["packetLossRate"] == 0.5 and m["deadlineMissRate"] == 0.0


def test_non_preemptive_packet_in_service_is_not_aborted_when_its_deadline_passes():
    cfg = make_config(expiredPacketPolicy="DROP_EXPIRED")
    run = run_engine(cfg, [pkt(1, size=1250, budget_us=5000)])  # needs 10 ms, budget 5 ms
    r = rec(run, 1)
    assert r.outcome is Outcome.LATE and r.tx_end_us == 10_000


# ---------------------------------------------------------------- ties and simultaneity


def test_simultaneous_arrivals_are_ordered_by_packet_id_deterministically():
    cfg = make_config()
    packets = [pkt(3), pkt(1), pkt(2)]
    a = run_engine(cfg, packets)
    b = run_engine(cfg, list(reversed(packets)))
    assert [(r.packet.packet_id, r.tx_start_us) for r in a.records] == \
           [(r.packet.packet_id, r.tx_start_us) for r in b.records]
    assert [rec(a, i).tx_start_us for i in (1, 2, 3)] == [0, 1000, 2000]


def test_duplicate_packet_ids_are_rejected():
    from acaps.traffic.workload import Workload
    with pytest.raises(ValueError):
        Workload.from_packets([pkt(1), pkt(1, t=5)], 1000)


def test_multiple_equal_deadlines_and_equal_priority_resolve_by_arrival_then_id():
    cfg = make_config()
    # blocker keeps the link busy so that a real decision among 3 equal packets is needed
    blocker = pkt(0, size=1250)
    same = [pkt(2, "gps", t=100), pkt(1, "gps", t=100), pkt(3, "gps", t=100)]
    for name in ("STATIC_PRIORITY", "ACAPS"):
        run = run_engine(cfg, [blocker] + same, name)
        order = sorted((r.tx_start_us, r.packet.packet_id) for r in run.records if r.packet.packet_id)
        assert [pid for _, pid in order] == [1, 2, 3], name


# ---------------------------------------------------------------- events, timeline, decisions


def test_event_log_contains_the_required_event_types_in_time_order():
    cfg = make_config(queueCapacity=1, expiredPacketPolicy="DROP_EXPIRED")
    run = run_engine(cfg, [pkt(1), pkt(2, budget_us=500), pkt(3), pkt(4)], "ACAPS", include_event_log=True)
    types = {e.type.value for e in run.events}
    assert {"PACKET_CREATED", "PACKET_ARRIVED", "PACKET_QUEUED", "SCHEDULER_DECISION",
            "PACKET_TRANSMISSION_STARTED", "PACKET_TRANSMISSION_COMPLETED",
            "PACKET_DROPPED", "DEADLINE_MISSED"} <= types
    times = [e.time_us for e in run.events]
    assert times == sorted(times)


def test_event_log_is_off_by_default():
    assert run_engine(make_config(), [pkt(1)]).events is None


def test_decision_log_records_the_state_seen_by_the_scheduler():
    cfg = make_config(queueCapacity=10)
    run = run_engine(cfg, [pkt(1), pkt(2), pkt(3)], "FIFO")
    second = run.decisions[1]  # at t=1000: packets 2 and 3 waiting
    assert second.time_us == 1000 and second.queue_length == 2 and second.occupancy == 0.2
    assert second.chosen_packet_id == 2


def test_timeline_reports_queue_length_and_time_weighted_mean():
    cfg = make_config(simulationDuration=0.003)  # window = 3000 us
    run = run_engine(cfg, [pkt(1), pkt(2), pkt(3)], duration_us=3000)
    m = MetricsEngine().compute(run, cfg.classes, cfg.queue_capacity)["queue"]
    # 2 waiting for 1000 us, 1 waiting for 1000 us, 0 for 1000 us -> mean 1.0
    assert m["meanQueueLength"] == pytest.approx(1.0)
    assert m["maxQueueLength"] == 2
    assert m["congestionTimeShare"]["LOW"] == pytest.approx(1.0)  # 2/100 occupancy


def test_observed_rates_are_measured_not_configured():
    # 250 B = 2 ms service, arrivals every 1 ms: arrivals ~1000 pkt/s, departures ~500 pkt/s.
    cfg = make_config()
    run = run_engine(cfg, _spaced(100, 1000, size=250), duration_us=100_000)
    sampled = [t for t in run.timeline if 40_000 <= t.time_us <= 100_000]
    assert len(sampled) > 10  # the test must actually exercise the measurement
    for t in sampled:
        assert t.observed_arrival_rate_pps == pytest.approx(1000, rel=0.05)
        assert t.observed_departure_rate_pps == pytest.approx(500, rel=0.08)
        assert t.observed_arrival_rate_bps == pytest.approx(1000 * 250 * 8, rel=0.05)


# ---------------------------------------------------------------- generated workload edge cases


def test_all_emergency_and_all_normal_and_no_emergency():
    for mix, present in [
        ({"emergency": 1.0, "video": 0, "gps": 0, "normal": 0}, {"emergency"}),
        ({"emergency": 0, "video": 0, "gps": 0, "normal": 1.0}, {"normal"}),
        ({"emergency": 0, "video": 0.4, "gps": 0.3, "normal": 0.3}, {"video", "gps", "normal"}),
    ]:
        cfg = make_config(trafficMix=mix, incomingRate=300, arrivalModel="poisson")
        workload = TrafficGenerator(cfg).generate()
        assert {p.traffic_class for p in workload.packets} == present
        for name in ("FIFO", "STATIC_PRIORITY", "ACAPS"):
            run = run_engine(cfg, list(workload.packets), name)
            MetricsEngine().compute(run, cfg.classes, cfg.queue_capacity)  # invariants must hold


def test_zero_incoming_rate_produces_an_empty_but_valid_run():
    cfg = make_config(incomingRate=0)
    assert len(TrafficGenerator(cfg).generate()) == 0
