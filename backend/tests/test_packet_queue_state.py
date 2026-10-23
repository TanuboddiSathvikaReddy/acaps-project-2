"""Packet model, queue model, and the measurements a scheduler can observe."""

from acaps.core.queue import BoundedQueue
from helpers import make_state, pkt, MS


def test_deadline_is_arrival_plus_delay_budget():
    p = pkt(1, "emergency", t=20 * MS)  # budget 50 ms
    assert p.deadline_us == 70 * MS


def test_waiting_time_and_remaining_deadline_are_derived_from_the_clock():
    p = pkt(1, "emergency", t=0)  # deadline 50 ms
    for now, waiting, remaining in [(0, 0, 50 * MS), (30 * MS, 30 * MS, 20 * MS), (60 * MS, 60 * MS, -10 * MS)]:
        state = make_state(now, [p])
        assert state.waiting_time_us(p) == waiting
        assert state.remaining_deadline_us(p) == remaining
    assert make_state(60 * MS, [p]).deadline_status(p) == "EXPIRED"
    assert make_state(10 * MS, [p]).deadline_status(p) == "OPEN"


def test_example_from_the_brief_deadline_200ms():
    p = pkt(1, "emergency", t=0, budget_us=200 * MS)
    assert make_state(50 * MS, [p]).remaining_deadline_us(p) == 150 * MS
    assert make_state(150 * MS, [p]).remaining_deadline_us(p) == 50 * MS


def test_slack_is_remaining_deadline_minus_service_time():
    p = pkt(1, "video", t=0, size=1250)  # 10 ms at 1 Mbps, deadline 150 ms
    state = make_state(100 * MS, [p])
    assert state.estimated_service_time_us(p) == 10 * MS
    assert state.slack_us(p) == 50 * MS - 10 * MS


def test_queue_occupancy_is_length_over_capacity():
    q = BoundedQueue(4)
    assert q.occupancy == 0.0
    for i in range(1, 3):
        assert q.try_enqueue(pkt(i))
    assert q.occupancy == 0.5
    state = make_state(0, [pkt(1), pkt(2), pkt(3)], capacity=12)
    assert state.queue_length == 3 and state.occupancy == 0.25


def test_queue_tail_drop_and_removal():
    q = BoundedQueue(2)
    a, b, c = pkt(1), pkt(2), pkt(3)
    assert q.try_enqueue(a) and q.try_enqueue(b)
    assert q.is_full and not q.try_enqueue(c)
    assert [p.packet_id for p in q.items()] == [1, 2]  # arrival order kept
    q.remove(a)
    assert len(q) == 1 and q.try_enqueue(c)
    assert [p.packet_id for p in q.items()] == [2, 3]
