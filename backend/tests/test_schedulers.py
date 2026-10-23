"""FIFO, Static Priority and ACAPS decision rules (brief section 35, items 6-9)."""

import random

import pytest

from acaps.config.models import AgingConfig
from acaps.schedulers.acaps import ACAPSScheduler, Tier
from acaps.schedulers.fifo import FIFOScheduler
from acaps.schedulers.static_priority import StaticPriorityScheduler
from helpers import MS, drain, make_config, make_state, pkt, rec, run_engine


# ================================================================ FIFO / Static Priority


def test_fifo_selects_earliest_arrival_ignoring_class_and_deadline():
    waiting = [pkt(1, "normal", t=0), pkt(2, "emergency", t=10), pkt(3, "emergency", t=20)]
    assert FIFOScheduler().select(make_state(30, waiting)).packet.packet_id == 1


def test_fifo_order_in_a_full_run_is_arrival_order():
    cfg = make_config()
    packets = [pkt(1, "normal", t=0, size=1250), pkt(2, "normal", t=1), pkt(3, "emergency", t=2), pkt(4, "gps", t=3)]
    run = run_engine(cfg, packets, "FIFO")
    order = [r.packet.packet_id for r in sorted(run.records, key=lambda r: r.tx_start_us)]
    assert order == [1, 2, 3, 4]


def test_static_priority_selects_highest_class_then_fifo_within_class():
    waiting = [pkt(1, "normal", t=0), pkt(2, "gps", t=5), pkt(3, "video", t=6), pkt(4, "video", t=4)]
    assert StaticPriorityScheduler().select(make_state(10, waiting)).packet.packet_id == 4  # video, earlier
    order = [pid for pid, _ in drain(StaticPriorityScheduler(), waiting, 10)]
    assert order == [4, 3, 2, 1]


def test_static_priority_never_changes_with_waiting_time():
    # a normal packet that has waited 10 minutes still loses to a brand-new emergency packet
    old_normal = pkt(1, "normal", t=0)
    new_emergency = pkt(2, "emergency", t=599_999 * MS)
    state = make_state(600_000 * MS, [old_normal, new_emergency])
    assert StaticPriorityScheduler().select(state).packet.packet_id == 2


def test_static_priority_ranks_come_from_scenario_configuration():
    swapped = [pkt(1, "normal", rank=0), pkt(2, "emergency", rank=5)]
    assert StaticPriorityScheduler().select(make_state(0, swapped)).packet.packet_id == 1


# ================================================================ ACAPS: measurement & tiers


def _assess(scheduler, now_us, packets):
    assessments, live = scheduler.assess(make_state(now_us, packets))
    return {a.packet.packet_id: a for a in assessments}, live


def test_acaps_slack_and_tiers():
    s = ACAPSScheduler()
    # video 1250 B (10 ms), deadline 150 ms; at t=100 ms: remaining 50, slack 40
    a, _ = _assess(s, 100 * MS, [pkt(1, "video", size=1250), pkt(2, "normal", size=125)])
    assert (a[1].waiting_us, a[1].remaining_us, a[1].service_us, a[1].slack_us) == (100 * MS, 50 * MS, 10 * MS, 40 * MS)
    assert a[1].tier is Tier.SAFE


def test_infeasible_when_slack_negative_including_expired():
    s = ACAPSScheduler()
    expired = pkt(1, "emergency", t=0)                       # deadline 50 ms
    too_late = pkt(2, "video", t=0, size=1250, budget_us=105 * MS)  # remaining 5 ms < 10 ms service
    a, _ = _assess(s, 100 * MS, [expired, too_late, pkt(3, "normal", t=90 * MS)])
    assert a[1].tier is Tier.INFEASIBLE and a[1].remaining_us < 0
    assert a[2].tier is Tier.INFEASIBLE and a[2].remaining_us > 0 and a[2].slack_us < 0


def test_live_work_excludes_infeasible_packets():
    """Correction from the design review: expired packets are served last, so they must not
    inflate the backlog that other packets are judged against."""
    s = ACAPSScheduler()
    candidate = pkt(1, "emergency", t=0, budget_us=110 * MS)  # remaining 10 ms, svc 1 ms -> slack 9 ms
    other = pkt(2, "normal", t=0)                               # 1 ms
    dead_weight = pkt(3, "video", t=0, size=12500, budget_us=95 * MS)  # 100 ms service, expired
    a, live = _assess(s, 100 * MS, [candidate, other, dead_weight])
    assert live == 2 * MS                                       # only packets 1 and 2
    assert a[3].tier is Tier.INFEASIBLE
    assert a[1].tier is Tier.SAFE                               # 9 ms slack >= 1 ms of other live work


def test_at_risk_means_would_miss_deadline_if_sent_last():
    s = ACAPSScheduler()
    # two 1 ms packets: A has 1 ms slack (would finish at deadline-? if sent last it waits 1 ms -> ok)
    a_ok = pkt(1, "gps", t=0, budget_us=3 * MS + 1000)   # remaining 3 ms + 1 us... slack 2001 us
    b = pkt(2, "normal", t=0)
    a, _ = _assess(s, 0, [a_ok, b])
    assert a[1].tier is Tier.SAFE       # slack 2.001 ms >= 1 ms other work
    tight = pkt(1, "gps", t=0, budget_us=1500)           # slack 500 us < 1 ms other work
    a, _ = _assess(s, 0, [tight, b])
    assert a[1].tier is Tier.AT_RISK


def test_urgency_is_queue_dependent_but_feasibility_is_not():
    s = ACAPSScheduler()
    p = pkt(1, "video", t=0, size=125, budget_us=20 * MS)       # slack 19 ms
    light = _assess(s, 0, [p, pkt(2, size=125)])[0][1]
    heavy = _assess(s, 0, [p] + [pkt(i, size=125) for i in range(2, 40)])[0][1]  # 38 ms of other work
    assert light.tier is Tier.SAFE and heavy.tier is Tier.AT_RISK
    assert light.slack_us == heavy.slack_us  # feasibility measure unchanged


# ================================================================ ACAPS: selection hierarchy


def test_at_risk_packet_beats_safe_emergency_deadline_feasibility_over_criticality():
    """DESIGN PRINCIPLE: deadline feasibility takes priority over class criticality when a
    packet is genuinely at risk."""
    s = ACAPSScheduler()
    at_risk_normal = pkt(1, "normal", t=0, budget_us=4 * MS)         # slack 3 ms
    safe_emergency = pkt(2, "emergency", t=0)                          # slack 49 ms
    filler = pkt(3, "video", size=625)                                 # 5 ms of extra backlog
    state = make_state(0, [safe_emergency, filler, at_risk_normal])
    assessments, _ = s.assess(state)
    tiers = {a.packet.packet_id: a.tier for a in assessments}
    assert tiers[1] is Tier.AT_RISK and tiers[2] is Tier.SAFE
    decision = s.select(state)
    assert decision.packet.packet_id == 1 and decision.reason_code == "AT_RISK_LEAST_SLACK"


def test_among_at_risk_least_slack_wins_then_effective_rank_then_arrival_then_id():
    s = ACAPSScheduler()
    filler = pkt(9, "normal", size=1250)  # big backlog so that everything below is AT_RISK
    a = pkt(1, "emergency", t=0, budget_us=8 * MS)   # slack 7 ms
    b = pkt(2, "normal", t=0, budget_us=6 * MS)      # slack 5 ms  <- least slack
    assert s.select(make_state(0, [a, b, filler])).packet.packet_id == 2
    # equal slack -> lower effective rank (emergency) wins
    c = pkt(3, "normal", t=0, budget_us=8 * MS)
    assert s.select(make_state(0, [c, a, filler])).packet.packet_id == 1
    # equal slack and rank -> earlier arrival wins, then lower packet id
    d = pkt(4, "gps", t=0, budget_us=8 * MS)
    e = pkt(5, "gps", t=0, budget_us=8 * MS)
    assert s.select(make_state(0, [e, d, filler])).packet.packet_id == 4


def test_no_at_risk_uses_effective_rank_then_deadline_then_arrival():
    s = ACAPSScheduler()
    emergency = pkt(1, "emergency", t=0)
    gps = pkt(2, "gps", t=0)
    assert s.select(make_state(0, [gps, emergency])).packet.packet_id == 1
    # same class: earlier absolute deadline wins even if it arrived later (budget differs)
    early_deadline = pkt(3, "gps", t=10 * MS, budget_us=30 * MS)   # deadline 40 ms
    late_deadline = pkt(4, "gps", t=0, budget_us=100 * MS)         # deadline 100 ms
    assert s.select(make_state(20 * MS, [late_deadline, early_deadline])).packet.packet_id == 3


def test_all_infeasible_triage_serves_most_critical_first():
    s = ACAPSScheduler()
    late_normal = pkt(1, "normal", t=0, budget_us=1 * MS)
    late_emergency = pkt(2, "emergency", t=0, budget_us=1 * MS)
    decision = s.select(make_state(10 * MS, [late_normal, late_emergency]))
    assert decision.packet.packet_id == 2 and decision.reason_code.value == "INFEASIBLE_TRIAGE"


def test_expired_packet_is_served_only_after_every_saveable_packet():
    s = ACAPSScheduler()
    expired_emergency = pkt(1, "emergency", t=0)          # long expired at t=200 ms
    fresh_normal = pkt(2, "normal", t=190 * MS)
    order = [pid for pid, _ in drain(s, [expired_emergency, fresh_normal], 200 * MS)]
    assert order == [2, 1]


def test_single_candidate_reason_code():
    d = ACAPSScheduler().select(make_state(0, [pkt(1)]))
    assert d.reason_code.value == "ONLY_CANDIDATE"


def test_acaps_decision_is_deterministic_and_input_order_independent():
    s = ACAPSScheduler()
    packets = [pkt(i, c, t=i * MS, size=125 + 50 * i) for i, c in enumerate(["normal", "gps", "video", "emergency", "gps", "normal"], 1)]
    winners = set()
    rng = random.Random(1)
    for _ in range(20):
        rng.shuffle(packets)
        winners.add(s.select(make_state(80 * MS, list(packets))).packet.packet_id)
    assert len(winners) == 1


# ================================================================ ACAPS: aging


def test_aging_promotes_by_fraction_of_own_delay_budget_and_is_bounded():
    s = ACAPSScheduler()  # quantum 25% of budget, cap 2
    normal = pkt(1, "normal")            # budget 500 ms -> quantum 125 ms
    gps = pkt(2, "gps")                  # budget 100 ms -> quantum 25 ms
    assert s.aging_quantum_us(normal.delay_budget_us) == 125 * MS
    assert s.aging_quantum_us(gps.delay_budget_us) == 25 * MS
    assert s.promotions(normal, 0) == 0 and s.promotions(normal, 124_999) == 0
    assert s.promotions(normal, 125 * MS) == 1 and s.promotions(normal, 250 * MS) == 2
    assert s.promotions(normal, 10_000 * MS) == 2                        # capped
    assert s.effective_rank(normal, 10_000 * MS) == 1                    # rank 3 - 2
    assert s.effective_rank(pkt(3, "emergency"), 10_000 * MS) == 0        # floored at 0
    assert s.promotions(gps, 25 * MS) == 1                               # same 25% of a SHORTER budget


def test_aging_lets_an_old_low_class_packet_overtake_a_new_higher_class_packet():
    old_normal = pkt(1, "normal", t=40 * MS)     # waited 260 ms -> 2 promotions -> effective rank 1
    new_gps = pkt(2, "gps", t=300 * MS)          # rank 2
    state = make_state(300 * MS, [new_gps, old_normal])
    with_aging = ACAPSScheduler().select(state)
    assert with_aging.packet.packet_id == 1
    assert with_aging.reason_code.value == "SAFE_AGING_CHANGED_CHOICE"
    assert with_aging.details["agingChangedChoice"] is True
    no_aging = ACAPSScheduler(AgingConfig(max_promotion_levels=0)).select(state)
    assert no_aging.packet.packet_id == 2 and no_aging.reason_code.value == "SAFE_BY_CRITICALITY"


def test_aging_is_bounded_so_it_cannot_reach_emergency_level():
    old_normal = pkt(1, "normal", t=0)  # budget 500 ms: SAFE, waited 490 ms = 3+ quanta, cap is 2
    new_emergency = pkt(2, "emergency", t=490 * MS)
    state = make_state(490 * MS, [old_normal, new_emergency])
    assert ACAPSScheduler().assess(state)[0][0].tier is Tier.SAFE
    assert ACAPSScheduler().select(state).packet.packet_id == 2
    assert ACAPSScheduler().effective_rank(old_normal, 490 * MS) == 1  # never 0 for rank 3, cap 2


def test_aging_never_overrides_the_deadline_tiers():
    """An aged packet cannot jump ahead of an AT_RISK packet just because it waited long."""
    s = ACAPSScheduler()
    at_risk = pkt(1, "normal", t=199 * MS, budget_us=10 * MS)   # remaining 9 ms, slack 8 ms, not yet promoted
    aged_safe = pkt(2, "normal", t=0)                           # waited 200 ms -> 1 promotion
    filler = pkt(3, "video", t=195 * MS, size=1250)             # 10 ms of backlog
    state = make_state(200 * MS, [aged_safe, filler, at_risk])
    assessments, _ = s.assess(state)
    by_id = {a.packet.packet_id: a for a in assessments}
    assert by_id[1].tier is Tier.AT_RISK and by_id[2].tier is Tier.SAFE
    assert by_id[2].effective_rank < by_id[1].effective_rank    # aging DID improve packet 2 ...
    assert s.select(state).packet.packet_id == 1                # ... but the tier still decides


def test_low_class_packet_is_not_starved_by_a_continuous_stream_of_emergency_packets():
    """Engine-level starvation check. Emergency packets arrive twice as fast as the link can
    serve them. Static Priority serves the normal packet only after the whole burst; ACAPS
    serves it as soon as it would otherwise miss its deadline."""
    cfg = make_config()
    emergencies = [pkt(i, "emergency", t=(i - 1) * 500, size=125, budget_us=200 * MS) for i in range(1, 120)]
    normal = pkt(1000, "normal", t=100, size=125, budget_us=40 * MS)        # arrives while link busy
    static = run_engine(cfg, emergencies + [normal], "STATIC_PRIORITY")
    acaps = run_engine(cfg, emergencies + [normal], "ACAPS")
    assert rec(static, 1000).deadline_missed and rec(static, 1000).tx_start_us > 100 * MS
    assert not rec(acaps, 1000).deadline_missed and rec(acaps, 1000).tx_end_us <= normal.deadline_us
    # ACAPS protects the low class without hurting the emergencies' own deadlines
    assert not any(rec(acaps, i).deadline_missed for i in range(1, 120))


# ================================================================ ACAPS: properties


def test_property_serving_another_packet_never_turns_a_safe_packet_at_risk():
    """Without new arrivals, once SAFE a packet stays SAFE until it is served (viva claim)."""
    rng = random.Random(7)
    scheduler = ACAPSScheduler()
    classes = ["emergency", "video", "gps", "normal"]
    for _ in range(150):
        n = rng.randint(2, 12)
        now = rng.randint(50, 200) * MS
        waiting = [
            pkt(i, rng.choice(classes), t=now - rng.randint(0, 45) * MS, size=rng.choice([64, 125, 400, 1000, 1500]))
            for i in range(1, n + 1)
        ]
        was_safe: set[int] = set()
        while waiting:
            state = make_state(now, waiting)
            assessments, _ = scheduler.assess(state)
            tiers = {a.packet.packet_id: a.tier for a in assessments}
            for pid in was_safe & set(tiers):
                assert tiers[pid] is Tier.SAFE, (pid, tiers)
            was_safe |= {pid for pid, t in tiers.items() if t is Tier.SAFE}
            chosen = scheduler.select(state).packet
            waiting.remove(chosen)
            now += state.estimated_service_time_us(chosen)


# ================================================================ Worked example (design section 5)


@pytest.fixture(scope="module")
def worked_example():
    """Five packets compete at t = 300 ms on a 1 Mbps link (svc = bytes*8 us).
    A blocker keeps the link busy until exactly 300 ms so all five are waiting."""
    cfg = make_config(queueCapacity=100)
    blocker = pkt(0, "normal", t=0, size=37_500, budget_us=10_000 * MS)         # 300 ms
    p1 = pkt(1, "normal", t=0, size=1500)         # 12 ms, deadline 500
    p2 = pkt(2, "gps", t=290 * MS, size=250)      # 2 ms,  deadline 390
    p3 = pkt(3, "video", t=173 * MS, size=1250)   # 10 ms, deadline 323
    p4 = pkt(4, "emergency", t=285 * MS, size=125)  # 1 ms, deadline 335
    p5 = pkt(5, "video", t=140 * MS, size=1000)   # 8 ms,  deadline 290 (already expired)
    packets = [blocker, p1, p2, p3, p4, p5]
    runs = {n: run_engine(cfg, packets, n, duration_us=500 * MS) for n in ("FIFO", "STATIC_PRIORITY", "ACAPS")}
    return packets, runs


def test_worked_example_state_at_the_first_decision(worked_example):
    packets, runs = worked_example
    decision = next(d for d in runs["ACAPS"].decisions if d.time_us == 300 * MS)
    assert decision.queue_length == 5 and decision.occupancy == 0.05
    assert decision.chosen_packet_id == 3 and decision.reason_code == "AT_RISK_LEAST_SLACK"
    assert decision.details["tier"] == "AT_RISK" and decision.details["slackUs"] == 13 * MS
    assert decision.details["liveWorkUs"] == 25 * MS
    assert (decision.details["atRiskCount"], decision.details["safeCount"], decision.details["infeasibleCount"]) == (1, 3, 1)


def test_worked_example_acaps_service_order_and_completion_times(worked_example):
    _, runs = worked_example
    done = {i: rec(runs["ACAPS"], i).tx_end_us for i in range(1, 6)}
    assert done == {3: 310 * MS, 4: 311 * MS, 1: 323 * MS, 2: 325 * MS, 5: 333 * MS}
    order = [d.chosen_packet_id for d in runs["ACAPS"].decisions if d.time_us >= 300 * MS]
    assert order == [3, 4, 1, 2, 5]
    reasons = [d.reason_code for d in runs["ACAPS"].decisions if d.time_us >= 300 * MS]
    assert reasons == ["AT_RISK_LEAST_SLACK", "SAFE_BY_CRITICALITY", "SAFE_AGING_CHANGED_CHOICE",
                       "SAFE_BY_CRITICALITY", "ONLY_CANDIDATE"]


def test_worked_example_fifo_and_static_priority_completion_times(worked_example):
    _, runs = worked_example
    fifo = {i: rec(runs["FIFO"], i).tx_end_us for i in range(1, 6)}
    static = {i: rec(runs["STATIC_PRIORITY"], i).tx_end_us for i in range(1, 6)}
    assert fifo == {1: 312 * MS, 5: 320 * MS, 3: 330 * MS, 4: 331 * MS, 2: 333 * MS}
    assert static == {4: 301 * MS, 5: 309 * MS, 3: 319 * MS, 2: 321 * MS, 1: 333 * MS}


def test_worked_example_deadline_misses(worked_example):
    _, runs = worked_example
    missed = {n: {i for i in range(1, 6) if rec(r, i).deadline_missed} for n, r in runs.items()}
    assert missed == {"FIFO": {3, 5}, "STATIC_PRIORITY": {5}, "ACAPS": {5}}
    # the link is work-conserving: all schedulers finish the last packet at the same instant
    assert {max(r.tx_end_us for r in run.records) for run in runs.values()} == {333 * MS}
