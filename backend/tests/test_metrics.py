"""Metric formulas, denominators, invariants (brief section 35, item 10)."""

import pytest

from acaps.core.packet import DropReason, PacketRecord, PacketStatus
from acaps.metrics.engine import MetricsEngine, MetricsInvariantError, _percentile_nearest_rank
from helpers import MS, make_config, pkt, run_engine


def metrics_for(cfg, run):
    return MetricsEngine().compute(run, cfg.classes, cfg.queue_capacity)


def delivered(p, start, end):
    r = PacketRecord(p, status=PacketStatus.DELIVERED, tx_start_us=start, tx_end_us=end)
    r.deadline_missed = end > p.deadline_us
    return r


def test_delay_averages_throughput_and_utilization_by_hand():
    cfg = make_config(simulationDuration=1)
    run = run_engine(cfg, [pkt(1), pkt(2), pkt(3)])  # waits 0/1/2 ms, service 1 ms each
    o = metrics_for(cfg, run)["overall"]
    assert o["avgWaitingTimeMs"] == pytest.approx(1.0)
    assert o["avgServiceTimeMs"] == pytest.approx(1.0)
    assert o["avgTotalDelayMs"] == pytest.approx(2.0)      # = waiting + service on average
    assert o["maxWaitingTimeMs"] == pytest.approx(2.0)
    assert o["p95TotalDelayMs"] == pytest.approx(3.0)      # nearest-rank over [1,2,3] ms
    assert o["throughputPps"] == pytest.approx(3.0)        # 3 packets / 1 s window
    assert o["throughputBps"] == pytest.approx(3 * 125 * 8)
    assert o["utilization"] == pytest.approx(0.003)        # 3 ms busy of 1 s


def test_loss_rate_and_accounting_identities_with_overflow():
    cfg = make_config(queueCapacity=2)
    run = run_engine(cfg, [pkt(i) for i in range(1, 6)])
    o = metrics_for(cfg, run)["overall"]
    assert (o["generated"], o["accepted"], o["delivered"], o["droppedOverflow"]) == (5, 3, 3, 2)
    assert o["packetLossRate"] == pytest.approx(0.4)
    assert o["generated"] == o["delivered"] + o["dropped"]
    assert o["accepted"] == o["delivered"] + o["droppedExpired"]


def test_deadline_miss_rate_uses_generated_and_accepted_denominators_explicitly():
    cfg = make_config(queueCapacity=1)
    late = pkt(1, size=1250, budget_us=5000)                        # 10 ms service -> late
    run = run_engine(cfg, [late, pkt(2), pkt(3), pkt(4)])           # #3, #4 overflow
    o = metrics_for(cfg, run)["overall"]
    assert o["deadlineMisses"] == 1
    assert o["deadlineMissRate"] == pytest.approx(1 / 4)            # / generated
    assert o["deadlineMissRateAccepted"] == pytest.approx(1 / 2)    # / accepted
    assert o["onTimeRate"] == pytest.approx(1 / 4)


def test_per_class_metrics_sum_to_overall():
    cfg = make_config(queueCapacity=3)
    packets = [pkt(i, c, size=200) for i, c in enumerate(["emergency", "video", "gps", "normal", "normal", "video", "gps", "emergency"], 1)]
    m = metrics_for(cfg, run_engine(cfg, packets, "STATIC_PRIORITY"))
    for key in ("generated", "accepted", "delivered", "droppedOverflow", "deadlineMisses"):
        assert sum(c[key] for c in m["perClass"].values()) == m["overall"][key]


def test_empty_denominators_give_none_not_zero_or_nan():
    cfg = make_config(trafficMix={"emergency": 1.0, "video": 0, "gps": 0, "normal": 0})
    run = run_engine(cfg, [pkt(1, "emergency")])
    video = metrics_for(cfg, run)["perClass"]["video"]
    assert video["generated"] == 0
    for key in ("packetLossRate", "deadlineMissRate", "avgWaitingTimeMs", "p95TotalDelayMs", "jitterMs", "meanPacketSizeBytes"):
        assert video[key] is None


def test_percentile_is_nearest_rank():
    values = list(range(1, 101))
    assert _percentile_nearest_rank(values, 0.95) == 95
    assert _percentile_nearest_rank([7], 0.95) == 7
    assert _percentile_nearest_rank([], 0.95) is None


# ---------------------------------------------------------------- jitter


def test_jitter_is_mean_abs_delay_difference_between_consecutive_same_class_packets():
    # class "normal" delays (departure order): 1 ms, 4 ms, 2 ms -> |4-1|=3, |2-4|=2 -> mean 2.5 ms
    recs = [
        delivered(pkt(1, "normal", t=0), 0, 1 * MS),
        delivered(pkt(2, "normal", t=10 * MS), 10 * MS, 14 * MS),
        delivered(pkt(3, "normal", t=20 * MS), 20 * MS, 22 * MS),
    ]
    total, pairs = MetricsEngine._jitter_sum_and_pairs(recs)
    assert (total, pairs) == (5 * MS, 2)


def test_jitter_does_not_compare_packets_of_different_classes():
    recs = [
        delivered(pkt(1, "normal", t=0), 0, 1 * MS),        # delay 1 ms
        delivered(pkt(2, "emergency", t=5 * MS), 5 * MS, 105 * MS),  # delay 100 ms (other class)
        delivered(pkt(3, "normal", t=10 * MS), 10 * MS, 12 * MS),    # delay 2 ms
    ]
    total, pairs = MetricsEngine._jitter_sum_and_pairs(recs)
    assert (total, pairs) == (1 * MS, 1)  # only the two normal packets are compared


def test_jitter_is_none_with_fewer_than_two_delivered_packets_of_a_class():
    cfg = make_config()
    run = run_engine(cfg, [pkt(1, "normal"), pkt(2, "gps", t=5000)])
    m = metrics_for(cfg, run)
    assert m["overall"]["jitterMs"] is None and m["perClass"]["normal"]["jitterMs"] is None


# ---------------------------------------------------------------- excessive wait / starvation


def test_excessive_wait_versus_starvation():
    engine = MetricsEngine(excessive_wait_fraction=0.8)
    p = pkt(1, "gps")  # budget 100 ms -> threshold 80 ms
    waited_long_not_overtaken = delivered(p, 90 * MS, 91 * MS)
    waited_long_overtaken = delivered(pkt(2, "gps"), 90 * MS, 91 * MS)
    waited_long_overtaken.overtaken_count = 3
    waited_briefly_overtaken = delivered(pkt(3, "gps"), 10 * MS, 11 * MS)
    waited_briefly_overtaken.overtaken_count = 3
    s = engine._summarize([waited_long_not_overtaken, waited_long_overtaken, waited_briefly_overtaken], 10**6)
    assert s["excessiveWaitCount"] == 2       # both long waits
    assert s["starvationCount"] == 1          # only the one that was also overtaken


def test_fifo_can_never_starve_a_packet_by_definition():
    cfg = make_config(queueCapacity=100)
    packets = [pkt(i, ["normal", "emergency", "gps", "video"][i % 4], t=i * 300, size=125) for i in range(200)]
    run = run_engine(cfg, packets, "FIFO", duration_us=60_000)
    m = metrics_for(cfg, run)["overall"]
    assert m["excessiveWaitCount"] > 0 and m["starvationCount"] == 0   # long waits exist, nobody overtaken


def test_overtaken_count_is_recorded_by_the_engine():
    cfg = make_config()
    blocker = pkt(0, size=1250)
    normal = pkt(1, "normal", t=1)
    emergencies = [pkt(2, "emergency", t=2), pkt(3, "emergency", t=3)]
    run = run_engine(cfg, [blocker, normal, *emergencies], "STATIC_PRIORITY")
    counts = {r.packet.packet_id: r.overtaken_count for r in run.records}
    assert counts[1] == 2 and counts[2] == 0 and counts[3] == 0  # normal overtaken by both


# ---------------------------------------------------------------- invariants


def test_invariant_violation_raises_instead_of_reporting_bad_metrics():
    cfg = make_config()
    run = run_engine(cfg, [pkt(1), pkt(2)])
    run.records[0].status = PacketStatus.WAITING   # simulate a lost packet
    with pytest.raises(MetricsInvariantError):
        metrics_for(cfg, run)


def test_queue_time_share_sums_to_one():
    cfg = make_config(queueCapacity=10, simulationDuration=0.02)
    run = run_engine(cfg, [pkt(i, size=250, t=i * 500) for i in range(40)], duration_us=20_000)
    share = metrics_for(cfg, run)["queue"]["congestionTimeShare"]
    assert sum(share.values()) == pytest.approx(1.0, abs=1e-5)
    assert share["HIGH"] > 0   # the buffer filled up
