"""Independent validation of the engine against textbook queueing theory."""

import pytest

from acaps.experiments.runner import run_simulation
from acaps.config.presets import resolve_config


def _md1_config(**kw):
    """M/D/1: Poisson arrivals, fixed 1250 B packets on 5 Mbps -> deterministic 2 ms service,
    huge buffer so nothing is dropped."""
    cfg = {"incomingRate": 350, "packetSize": 1250, "linkBandwidthMbps": 5, "queueCapacity": 100_000,
           "simulationDuration": 60, "randomSeed": 3, "classes": {c: {} for c in ("emergency", "video", "gps", "normal")}}
    cfg.update(kw)
    return resolve_config(cfg)


@pytest.fixture(scope="module")
def md1():
    return run_simulation(_md1_config(), include_size_neutral_control=False)


def test_fifo_mean_waiting_time_matches_the_pollaczek_khinchine_formula(md1):
    # M/D/1: Wq = rho * S / (2 * (1 - rho)),  S = 2 ms, rho = 350 * 2 ms = 0.7  ->  2.333 ms
    measured = md1.metrics["FIFO"]["overall"]["avgWaitingTimeMs"]
    assert measured == pytest.approx(0.7 * 2.0 / (2 * 0.3), rel=0.08)


def test_utilization_and_throughput_match_offered_load(md1):
    o = md1.metrics["FIFO"]["overall"]
    assert o["utilization"] == pytest.approx(0.7, rel=0.05)
    assert o["throughputPps"] == pytest.approx(350, rel=0.05)
    assert o["packetLossRate"] == 0.0


def test_work_conservation_equal_sizes_give_identical_mean_wait_for_every_scheduler(md1):
    """With equal service times and no drops, ANY work-conserving non-preemptive scheduler has
    the same departure instants, hence the same mean waiting time. Only WHICH packet waits
    differs. If this fails, one scheduler is idling the link or losing work."""
    waits = {n.value: m["overall"]["avgWaitingTimeMs"] for n, m in md1.metrics.items()}
    assert waits["STATIC_PRIORITY"] == pytest.approx(waits["FIFO"], abs=1e-6)
    assert waits["ACAPS"] == pytest.approx(waits["FIFO"], abs=1e-6)
    assert {m["overall"]["utilization"] for m in md1.metrics.values()} == {md1.metrics["FIFO"]["overall"]["utilization"]}


def test_scheduling_changes_who_waits_not_how_long_on_average(md1):
    """...but per-class waiting DOES differ, which is the whole point of scheduling."""
    fifo = md1.metrics["FIFO"]["perClass"]["emergency"]["avgWaitingTimeMs"]
    static = md1.metrics["STATIC_PRIORITY"]["perClass"]["emergency"]["avgWaitingTimeMs"]
    assert static < fifo
