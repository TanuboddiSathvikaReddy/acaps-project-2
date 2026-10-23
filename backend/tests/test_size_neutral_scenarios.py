"""The size-neutral versions of emergencyBurst and networkOverload."""

import pytest

from acaps.config.presets import PRESETS, make_size_neutral, resolve_config
from acaps.core.network import describe_network
from acaps.core.packet import DropReason
from acaps.experiments.runner import run_simulation
from acaps.traffic.generator import TrafficGenerator

PAIRS = [("emergencyBurst", "emergencyBurstSizeNeutral"), ("networkOverload", "networkOverloadSizeNeutral")]


def _sizes(cfg):
    return {n: c.size_model.model_dump_json() for n, c in cfg.classes.items()}


@pytest.mark.parametrize("source,neutral", PAIRS)
def test_neutral_preset_is_exactly_the_derived_control_of_its_source(source, neutral):
    derived = make_size_neutral(resolve_config({"scenario": source}))
    preset = resolve_config({"scenario": neutral})
    assert _sizes(preset) == _sizes(derived)
    assert len(set(_sizes(preset).values())) == 1                       # ONE size model for all classes
    assert preset.model_dump(exclude={"scenario", "classes"}) == derived.model_dump(exclude={"scenario", "classes"})


@pytest.mark.parametrize("source,neutral", PAIRS)
def test_only_packet_sizes_differ_from_the_source_scenario(source, neutral):
    a, b = resolve_config({"scenario": source}), resolve_config({"scenario": neutral})
    for field in ("incoming_rate", "link_bandwidth_mbps", "queue_capacity", "traffic_mix", "bursts",
                  "random_seed", "simulation_duration", "expired_packet_policy", "aging", "arrival_model"):
        assert getattr(a, field) == getattr(b, field), field
    assert {(n, c.criticality_rank, c.delay_budget_ms) for n, c in a.classes.items()} == \
           {(n, c.criticality_rank, c.delay_budget_ms) for n, c in b.classes.items()}


@pytest.mark.parametrize("source,neutral", PAIRS)
def test_the_overload_window_keeps_the_same_offered_load(source, neutral):
    a = describe_network(resolve_config({"scenario": source}))
    b = describe_network(resolve_config({"scenario": neutral}))
    peak = lambda d: max([d["offeredLoad"], *d["burstOfferedLoad"]])
    assert peak(a) > 1.0 and peak(b) == pytest.approx(peak(a), rel=0.01)


def test_neutral_size_rule_uses_the_peak_load_period_not_the_base_mix():
    cfg = resolve_config({"scenario": "emergencyBurst"})
    size = next(iter(make_size_neutral(cfg).classes.values())).size_model.bytes
    assert size == 464            # burst mix mean (60% small emergency packets), NOT the base-mix 745
    # a scenario with one mix everywhere: mix-weighted mean, unchanged from before
    assert next(iter(make_size_neutral(resolve_config({"scenario": "heavyTraffic"})).classes.values())).size_model.bytes == 678


def test_explicit_size_neutral_model_overrides_the_rule():
    cfg = resolve_config({"scenario": "heavyTraffic", "sizeNeutralModel": {"type": "fixed", "bytes": 500}})
    assert {c.size_model.bytes for c in make_size_neutral(cfg).classes.values()} == {500}


@pytest.mark.parametrize("source,neutral,duration", [("emergencyBurst", "emergencyBurstSizeNeutral", 6),
                                                     ("networkOverload", "networkOverloadSizeNeutral", 3)])
def test_same_arrival_times_and_classes_as_the_source_scenario(source, neutral, duration):
    a = TrafficGenerator(resolve_config({"scenario": source, "simulationDuration": duration})).generate()
    b = TrafficGenerator(resolve_config({"scenario": neutral, "simulationDuration": duration})).generate()
    assert [(p.arrival_time_us, p.traffic_class) for p in a.packets] == [(p.arrival_time_us, p.traffic_class) for p in b.packets]
    assert len({p.size_bytes for p in b.packets}) == 1 and len({p.size_bytes for p in a.packets}) > 1


@pytest.mark.parametrize("neutral,duration", [("emergencyBurstSizeNeutral", 6), ("networkOverloadSizeNeutral", 3)])
def test_overflow_loss_is_identical_across_schedulers_when_all_packets_have_one_size(neutral, duration):
    """Equal service times => identical departure instants for any work-conserving scheduler =>
    identical queue LENGTH over time => class-blind tail-drop drops exactly the same packets."""
    result = run_simulation(resolve_config({"scenario": neutral, "simulationDuration": duration}),
                            include_size_neutral_control=False)
    dropped = {
        name.value: {r.packet.packet_id for r in run.run.records if r.drop_reason is DropReason.QUEUE_OVERFLOW}
        for name, run in result.runs.items()
    }
    assert len(dropped["FIFO"]) > 0                          # the scenario really is overloaded
    assert dropped["STATIC_PRIORITY"] == dropped["FIFO"] == dropped["ACAPS"]
    # ... while WHO misses deadlines still depends on the scheduler
    misses = {n.value: r.metrics["overall"]["deadlineMissRate"] for n, r in result.runs.items()}
    assert misses["FIFO"] > misses["ACAPS"]


def test_new_presets_are_listed_by_the_api():
    from fastapi.testclient import TestClient
    from acaps.api.app import app
    names = {s["name"] for s in TestClient(app).get("/api/v1/scenarios").json()}
    assert {"emergencyBurstSizeNeutral", "networkOverloadSizeNeutral"} <= names <= set(PRESETS)
