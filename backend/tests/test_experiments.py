"""Workload determinism, replay fairness, size-neutral control, aggregation (brief section 35)."""

import json
import statistics

import pytest

from acaps.api.serializers import simulation_to_dict
from acaps.config.presets import make_size_neutral, resolve_config
from acaps.experiments import runner
from acaps.experiments.aggregate import aggregate_metric_dicts, delta_metric_dicts, summarize_values
from acaps.experiments.runner import run_experiment, run_simulation
from acaps.traffic.generator import TrafficGenerator


def small(scenario="heavyTraffic", **kw):
    return resolve_config({"scenario": scenario, "simulationDuration": 2, **kw})


# ---------------------------------------------------------------- workload generation


def test_same_seed_gives_identical_workload_and_fingerprint():
    a, b = TrafficGenerator(small()).generate(), TrafficGenerator(small()).generate()
    assert a.packets == b.packets and a.fingerprint == b.fingerprint


def test_different_seed_gives_a_different_workload():
    a = TrafficGenerator(small(randomSeed=1)).generate()
    b = TrafficGenerator(small(randomSeed=2)).generate()
    assert a.fingerprint != b.fingerprint


def test_packet_ids_are_unique_and_arrivals_sorted_and_inside_duration():
    w = TrafficGenerator(small()).generate()
    ids = [p.packet_id for p in w.packets]
    assert len(set(ids)) == len(ids)
    times = [p.arrival_time_us for p in w.packets]
    assert times == sorted(times) and 0 <= times[0] and times[-1] < w.duration_us


def test_packet_count_is_close_to_rate_times_duration():
    w = TrafficGenerator(small("normalTraffic", simulationDuration=10)).generate()
    assert len(w) == pytest.approx(4000, rel=0.06)  # Poisson: ~ +-3 sigma is ~ 5%


def test_constant_arrival_model_is_exactly_evenly_spaced():
    cfg = small(arrivalModel="constant", incomingRate=100, simulationDuration=1)
    times = [p.arrival_time_us for p in TrafficGenerator(cfg).generate().packets]
    assert len(times) == 100 and set(b - a for a, b in zip(times, times[1:])) == {10_000}


def test_class_mix_is_followed():
    w = TrafficGenerator(small("normalTraffic", simulationDuration=10)).generate()
    share = {c: sum(p.traffic_class == c for p in w.packets) / len(w) for c in ("emergency", "video", "gps", "normal")}
    for c, expected in {"emergency": 0.2, "video": 0.3, "gps": 0.2, "normal": 0.3}.items():
        assert share[c] == pytest.approx(expected, abs=0.03)


def test_packet_sizes_follow_class_size_models():
    w = TrafficGenerator(small("heavyTraffic", simulationDuration=5)).generate()
    for p in w.packets:
        if p.traffic_class == "emergency":
            assert 100 <= p.size_bytes <= 400
        elif p.traffic_class == "video":
            assert 800 <= p.size_bytes <= 1400
        elif p.traffic_class == "gps":
            assert 60 <= p.size_bytes <= 140
        else:
            assert p.size_bytes in (64, 1500)
    normal = [p.size_bytes for p in w.packets if p.traffic_class == "normal"]
    assert sum(s == 1500 for s in normal) / len(normal) == pytest.approx(0.6, abs=0.05)


def test_burst_changes_the_arrival_rate_inside_its_window():
    cfg = small("emergencyBurst", simulationDuration=8)
    w = TrafficGenerator(cfg).generate()
    inside = [p for p in w.packets if 4_000_000 <= p.arrival_time_us < 5_000_000]
    outside = [p for p in w.packets if p.arrival_time_us < 4_000_000]
    assert len(inside) == pytest.approx(1500, rel=0.12)          # 3 x 500 pkt/s for 1 s
    assert len(outside) / 4 == pytest.approx(500, rel=0.08)
    assert sum(p.traffic_class == "emergency" for p in inside) / len(inside) == pytest.approx(0.6, abs=0.06)


def test_changing_a_size_model_does_not_move_arrivals_or_class_sequence():
    base = small("heavyTraffic")
    other = small("heavyTraffic", classes={"video": {"sizeModel": {"type": "fixed", "bytes": 500}}})
    a, b = TrafficGenerator(base).generate(), TrafficGenerator(other).generate()
    assert [(p.arrival_time_us, p.traffic_class) for p in a.packets] == [(p.arrival_time_us, p.traffic_class) for p in b.packets]
    # one size draw per packet regardless of class: other classes keep exactly the same sizes
    for pa, pb in zip(a.packets, b.packets):
        if pa.traffic_class != "video":
            assert pa.size_bytes == pb.size_bytes
        else:
            assert pb.size_bytes == 500


def test_class_order_in_the_request_does_not_change_the_workload():
    a = small(trafficMix={"emergency": 0.2, "video": 0.3, "gps": 0.2, "normal": 0.3})
    b = small(trafficMix={"normal": 0.3, "gps": 0.2, "video": 0.3, "emergency": 0.2})
    assert TrafficGenerator(a).generate().fingerprint == TrafficGenerator(b).generate().fingerprint


# ---------------------------------------------------------------- replay fairness


def test_all_schedulers_replay_the_identical_workload():
    result = run_simulation(small())
    fingerprints = {r.run.workload_fingerprint for r in result.runs.values()}
    assert fingerprints == {result.workload.fingerprint}
    assert all(r.run.workload is result.workload for r in result.runs.values())
    generated = {r.metrics["overall"]["generated"] for r in result.runs.values()}
    assert generated == {len(result.workload)}


def test_workload_is_generated_exactly_once_per_seed(monkeypatch):
    calls = []
    original = TrafficGenerator.generate
    monkeypatch.setattr(TrafficGenerator, "generate", lambda self: calls.append(1) or original(self))
    run_simulation(small(), include_size_neutral_control=False)
    assert len(calls) == 1


def test_a_full_simulation_is_bit_for_bit_reproducible():
    a = json.dumps(simulation_to_dict(run_simulation(small())), sort_keys=True)
    b = json.dumps(simulation_to_dict(run_simulation(small())), sort_keys=True)
    assert a == b


def test_schedulers_can_be_run_in_any_order_with_identical_results(monkeypatch):
    forward = run_simulation(small()).metrics
    monkeypatch.setattr(runner, "SCHEDULER_ORDER", tuple(reversed(runner.SCHEDULER_ORDER)))
    backward = run_simulation(small()).metrics
    assert forward == backward   # no state leaks from one run into the next


def test_link_is_work_conserving_so_all_schedulers_deliver_the_same_bits_when_nothing_drops():
    result = run_simulation(small("normalTraffic"))
    bits = {r.metrics["overall"]["deliveredBits"] for r in result.runs.values()}
    assert len(bits) == 1


# ---------------------------------------------------------------- size-neutral control


def test_size_neutral_control_changes_only_packet_sizes():
    cfg = small("heavyTraffic")
    control = make_size_neutral(cfg)
    assert control.incoming_rate == cfg.incoming_rate
    assert control.link_bandwidth_mbps == cfg.link_bandwidth_mbps
    assert control.traffic_mix == cfg.traffic_mix and control.random_seed == cfg.random_seed
    assert {(n, c.criticality_rank, c.delay_budget_ms) for n, c in control.classes.items()} == \
           {(n, c.criticality_rank, c.delay_budget_ms) for n, c in cfg.classes.items()}
    sizes = {c.size_model.model_dump_json() for c in control.classes.values()}
    assert len(sizes) == 1  # every class uses the same size model

    a, b = TrafficGenerator(cfg).generate(), TrafficGenerator(control).generate()
    assert [(p.arrival_time_us, p.traffic_class) for p in a.packets] == [(p.arrival_time_us, p.traffic_class) for p in b.packets]
    assert {p.size_bytes for p in b.packets} == {678}   # mix-weighted mean of the variable sizes
    assert sum(p.size_bytes for p in b.packets) == pytest.approx(sum(p.size_bytes for p in a.packets), rel=0.04)


def test_size_neutral_control_is_included_on_request_and_shares_the_result_shape():
    result = run_simulation(small("heavyTraffic"), include_size_neutral_control=True)
    control = result.size_neutral_control
    assert control is not None and control.workload.fingerprint != result.workload.fingerprint
    assert set(control.runs) == set(result.runs)
    assert control.config.scenario == "heavyTraffic+sizeNeutral"


def test_size_neutral_preset_matches_the_derived_control():
    preset = resolve_config({"scenario": "sizeNeutralControl"})
    assert {c.size_model.model_dump_json() for c in preset.classes.values()} == {'{"type":"fixed","bytes":678}'}


# ---------------------------------------------------------------- aggregation


def test_summarize_values_uses_sample_standard_deviation_and_skips_none():
    s = summarize_values([1.0, 2.0, 4.0, None])
    assert s["n"] == 3 and s["mean"] == pytest.approx(7 / 3) and s["min"] == 1.0 and s["max"] == 4.0
    assert s["std"] == pytest.approx(statistics.stdev([1, 2, 4]))
    assert summarize_values([5.0])["std"] is None
    assert summarize_values([None, None]) == {"mean": None, "std": None, "min": None, "max": None, "n": 0}


def test_aggregate_and_delta_recurse_over_nested_metrics():
    runs = [{"overall": {"x": 1.0, "y": None}, "q": {"z": 10}}, {"overall": {"x": 3.0, "y": None}, "q": {"z": 20}}]
    agg = aggregate_metric_dicts(runs)
    assert agg["overall"]["x"]["mean"] == 2.0 and agg["q"]["z"]["mean"] == 15 and agg["overall"]["y"]["n"] == 0
    assert delta_metric_dicts({"a": 5, "b": None, "c": {"d": 2}}, {"a": 3, "b": 1, "c": {"d": 7}}) == {"a": 2, "b": None, "c": {"d": -5}}


def test_experiment_repeats_over_consecutive_seeds_with_paired_deltas():
    cfg = small("networkOverload", simulationDuration=1, randomSeed=10)
    exp = run_experiment(cfg, runs=4, include_size_neutral_control=False)
    assert [r["seed"] for r in exp["runs"]] == [10, 11, 12, 13]
    assert len({r["workloadFingerprint"] for r in exp["runs"]}) == 4
    fifo_misses = [r["schedulers"]["FIFO"]["overall"]["deadlineMissRate"] for r in exp["runs"]]
    agg = exp["aggregate"]["FIFO"]["overall"]["deadlineMissRate"]
    assert agg["n"] == 4 and agg["mean"] == pytest.approx(statistics.fmean(fifo_misses), abs=1e-5)
    assert agg["std"] == pytest.approx(statistics.stdev(fifo_misses), abs=1e-5)
    acaps = [r["schedulers"]["ACAPS"]["overall"]["deadlineMissRate"] for r in exp["runs"]]
    paired = exp["pairedDeltasVsFifo"]["ACAPS"]["overall"]["deadlineMissRate"]
    assert paired["mean"] == pytest.approx(statistics.fmean(a - f for a, f in zip(acaps, fifo_misses)), abs=1e-5)
    assert "FIFO" not in exp["pairedDeltasVsFifo"]


def test_experiment_with_size_neutral_control():
    exp = run_experiment(small("heavyTraffic", simulationDuration=1), runs=2, include_size_neutral_control=True)
    assert exp["sizeNeutralControl"]["scenario"] == "heavyTraffic+sizeNeutral"
    assert len(exp["sizeNeutralControl"]["runs"]) == 2
