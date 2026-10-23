"""Locks the FROZEN Phase 1 event-ordering convention (docs/ARCHITECTURE.md section 7.1).

Same-microsecond events are processed one at a time as DEADLINE_EXPIRY, DEPARTURE, ARRIVAL (then by
packet id), and a scheduling decision is taken after every single event. These tests document the
convention; they do not argue that it is the only reasonable one."""

import pytest

from acaps.core.packet import DropReason
from helpers import make_config, pkt, rec, run_engine

ALL = ("FIFO", "STATIC_PRIORITY", "ACAPS")


@pytest.mark.parametrize("scheduler", ALL)
def test_a_decision_after_a_departure_does_not_see_an_arrival_of_the_same_microsecond(scheduler):
    """p1 leaves the link at t=1000 while an EMERGENCY packet (p3) arrives at exactly t=1000.
    The departure-triggered decision happens first, among packets already waiting (p2, normal), for
    every scheduler, even Static Priority. Then p3 is processed."""
    cfg = make_config(queueCapacity=5)
    run = run_engine(cfg, [pkt(1), pkt(2, "normal"), pkt(3, "emergency", t=1000)], scheduler)
    assert rec(run, 2).tx_start_us == 1000     # chosen at the departure instant
    assert rec(run, 3).tx_start_us == 2000     # the same-microsecond arrival waited for it


@pytest.mark.parametrize("scheduler", ALL)
def test_a_departure_frees_a_buffer_slot_before_a_same_microsecond_arrival_is_admitted(scheduler):
    """Buffer of ONE waiting packet. At t=1000 the departure-triggered decision takes p2 out of the
    buffer, so the arrival p3 (same microsecond) finds room and is not dropped."""
    cfg = make_config(queueCapacity=1)
    run = run_engine(cfg, [pkt(1), pkt(2), pkt(3, t=1000)], scheduler)
    assert rec(run, 3).drop_reason is None and rec(run, 3).tx_start_us == 2000


@pytest.mark.parametrize("scheduler", ALL)
def test_two_simultaneous_arrivals_at_an_idle_link_are_served_in_packet_id_order(scheduler):
    """The scheduler does not choose between them: the lower id is the only candidate at its decision.
    (Even Static Priority sends the lower-id NORMAL packet before the higher-id EMERGENCY packet.)"""
    run = run_engine(make_config(), [pkt(1, "normal"), pkt(2, "emergency")], scheduler)
    assert rec(run, 1).tx_start_us == 0 and rec(run, 2).tx_start_us == 1000


def test_expiry_is_processed_before_a_departure_so_an_expired_packet_is_never_scheduled():
    """p2's deadline is exactly p1's departure instant. DEADLINE_EXPIRY comes first, so under
    DROP_EXPIRED p2 is removed before the departure-triggered decision."""
    cfg = make_config(expiredPacketPolicy="DROP_EXPIRED")
    run = run_engine(cfg, [pkt(1), pkt(2, budget_us=1000)], "FIFO")
    r = rec(run, 2)
    assert r.drop_reason is DropReason.DEADLINE_EXPIRED and r.drop_time_us == 1000 and r.tx_start_us is None


def test_a_transmission_ending_exactly_at_the_deadline_is_on_time_and_recorded_as_such():
    run = run_engine(make_config(), [pkt(1, budget_us=1000)])
    r = rec(run, 1)
    assert r.tx_end_us == r.packet.deadline_us and not r.deadline_missed


def test_the_convention_is_identical_for_every_scheduler_on_a_workload_with_many_coincidences():
    """Constant arrivals at exactly the service time create a same-microsecond arrival/departure at
    every packet. All schedulers must see the identical timeline of transmissions."""
    cfg = make_config()
    packets = [pkt(i + 1, ["normal", "emergency", "gps"][i % 3], t=i * 1000) for i in range(30)]
    timelines = {s: [(r.packet.packet_id, r.tx_start_us) for r in run_engine(cfg, packets, s).records] for s in ALL}
    assert timelines["FIFO"] == timelines["STATIC_PRIORITY"] == timelines["ACAPS"]
